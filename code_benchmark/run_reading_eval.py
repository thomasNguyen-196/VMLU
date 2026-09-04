"""Inference runner for the 400-question reading-comprehension eval set (issue #3).

Consumes `eval_set_manifest.csv` (from make_eval_sample.py) plus the two
question_only source JSONs, calls the model on each {context, question} pair,
and writes per-item free-text answers:

  all_res/ollama_result/reading_answers_<model>.csv

This is deliberately SEPARATE from run_mc_eval.py: that harness is the frozen
multiple-choice pipeline (A-E contract, 4-token budget); reading comprehension
needs a context prompt and a long answer budget. No scoring happens here —
gold_answer is empty until the 2-annotator pass (EM + char-F1 script comes
after that).

Run from repo root:
  .venv/bin/python code_benchmark/run_reading_eval.py --workers 4 --resume
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import (sanitize_model, resolve_endpoint, RESULTS_DIR,
                                       MANIFEST_DEFAULT, SQUAD_DEFAULT, DROP_DEFAULT,
                                       read_csv_checked, add_endpoint_args,
                                       parse_endpoint_args, setup_logging)
    from code_benchmark.checkpoint import (READING_PREFIX, checkpoint_name,
                                           find_latest_checkpoint)
    from code_benchmark.llm import build_client, verify_credentials, call_model_with_retry
    from code_benchmark.common import item_key
except ImportError:
    from common import (sanitize_model, resolve_endpoint, RESULTS_DIR,
                        MANIFEST_DEFAULT, SQUAD_DEFAULT, DROP_DEFAULT,
                        read_csv_checked, add_endpoint_args,
                        parse_endpoint_args, setup_logging)
    from checkpoint import READING_PREFIX, checkpoint_name, find_latest_checkpoint
    from llm import build_client, verify_credentials, call_model_with_retry
    from common import item_key

load_dotenv()

CHECKPOINT_PREFIX = READING_PREFIX  # never collides with raw_result_*.csv of the MC run

# Free-text answer rows: read by build_review_ui.py; fieldnames shared by the
# checkpoint writer and the final answers file.
ANSWER_COLS = ["dataset", "item_id", "stratum", "question", "context_words", "raw_response"]


def build_reading_prompt(context: str, question: str) -> str:
    """Vietnamese open-book instruction. New contract (this script only) —
    unlike build_prompt, NOT shared with legacy MC scripts."""
    return (
        "Đọc đoạn văn dưới đây và trả lời câu hỏi bằng một cụm từ hoặc số ngắn gọn, "
        "lấy nguyên văn trong đoạn văn khi có thể.\n\n"
        + context.strip()
        + "\n\nCâu hỏi: " + question + "\nTrả lời: "
    )


def load_manifest(path: Path) -> list[dict]:
    return read_csv_checked(path, required={"dataset", "item_id", "stratum", "question"},
                            label="manifest")


def index_sources(squad_path: Path, drop_path: Path) -> dict[tuple[str, str], dict]:
    """(dataset, item_id) -> source record, for context lookup + question audit."""
    idx: dict[tuple[str, str], dict] = {}
    for ds, p in (("squad", squad_path), ("drop", drop_path)):
        with open(p, encoding="utf-8") as f:
            for rec in json.load(f).get("data", []):
                key = ds, str(rec.get("id", rec.get("question_id")))
                idx[key] = rec
    return idx


def join_manifest(manifest: list[dict], idx: dict[tuple[str, str], dict]) -> list[dict]:
    """Attach context to each manifest row; fail-fast on unknown id or question
    text drift (the manifest is pre-registered — a mismatch means wrong source)."""
    out = []
    for row in manifest:
        key = (row["dataset"], str(row["item_id"]))
        if key not in idx:
            raise SystemExit(f"Error: manifest row not found in sources: {key}")
        src = idx[key]
        if str(src["question"]).strip() != str(row["question"]).strip():
            raise SystemExit(f"Error: question text drift for {key} — regenerate manifest")
        out.append({**row, "context": src["context"]})
    return out


def resume_key(row: dict) -> str:
    return item_key(row)


def find_latest_reading_checkpoint(folder: Path, model: str) -> Path | None:
    """Newest checkpoint for THIS model only — reading_result_<count>_<model>.csv.
    Legacy reading_result_<count>.csv files carry no model identity and are never
    picked (a different model's --resume used to silently reuse their answers)."""
    return find_latest_checkpoint(folder, model, prefix=CHECKPOINT_PREFIX)


def parse_args():
    ap = argparse.ArgumentParser(description="Run the 400-question reading eval (issue #3).")
    ap.add_argument("--manifest", type=Path, default=MANIFEST_DEFAULT)
    ap.add_argument("--squad-file", type=Path, default=SQUAD_DEFAULT)
    ap.add_argument("--drop-file", type=Path, default=DROP_DEFAULT)
    add_endpoint_args(ap, max_tokens_default=48,
                      max_tokens_help="answer budget (extractive spans are short; 48 is generous)",
                      resume_help="continue from the newest reading_result_<count>_<model>.csv checkpoint for this model")
    return parse_endpoint_args(ap)


def main():
    args = parse_args()
    base_url, api_key, model = resolve_endpoint(args)

    result_folder = RESULTS_DIR
    result_folder.mkdir(parents=True, exist_ok=True)
    sanitized_model = sanitize_model(model)

    setup_logging(f"logs/reading_{sanitized_model}.log")

    logging.info(f"Model: {model} @ {base_url} | workers={args.workers} "
                 f"temp={args.temperature} seed={args.seed} max_tokens={args.max_tokens}")

    manifest = load_manifest(args.manifest)
    idx = index_sources(args.squad_file, args.drop_file)
    items = join_manifest(manifest, idx)
    if args.limit:
        items = items[: args.limit]
    total = len(items)
    logging.info(f"Joined {total} manifest rows to contexts "
                 f"({sum(r['dataset'] == 'squad' for r in items)} squad / "
                 f"{sum(r['dataset'] == 'drop' for r in items)} drop)")

    client = build_client(base_url, api_key)
    logging.info("Verifying endpoint connectivity and credentials...")
    verify_credentials(client, model)

    existing: dict[str, dict] = {}
    if args.resume:
        cp = find_latest_reading_checkpoint(result_folder, model)
        if cp:
            logging.info(f"Resuming from checkpoint: {cp}")
            with open(cp, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing[resume_key(row)] = row
        else:
            others = sorted(result_folder.glob(f"{CHECKPOINT_PREFIX}*.csv"))
            if others:
                logging.warning(
                    "No checkpoint found for model '%s' — the reading_result_*.csv files present "
                    "belong to other models or lack any model identity, so none can be resumed "
                    "safely. Starting fresh.", model)

    results: list[dict | None] = [None] * total
    to_process = []
    for i, item in enumerate(items):
        k = resume_key(item)
        if k in existing:
            results[i] = existing[k]
        else:
            to_process.append((i, item))
    logging.info(f"Remaining to evaluate: {len(to_process)}/{total}")

    lock = Lock()
    completed = len(existing)

    def process(index: int, item: dict):
        nonlocal completed
        raw = call_model_with_retry(
            client=client, model=model,
            prompt=build_reading_prompt(item["context"], item["question"]),
            temperature=args.temperature, seed=args.seed, max_tokens=args.max_tokens)
        row = {"dataset": item["dataset"], "item_id": item["item_id"],
               "stratum": item["stratum"], "question": item["question"],
               "context_words": len(item["context"].split()),
               "raw_response": raw.strip()}
        with lock:
            results[index] = row
            completed += 1
            done = [r for r in results if r is not None]
            if completed % 100 == 0 or completed == total:
                write_csv(result_folder / checkpoint_name(model, len(done), prefix=CHECKPOINT_PREFIX), done)
        return index

    def write_csv(path: Path, rows: list[dict]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ANSWER_COLS)
            w.writeheader()
            w.writerows(rows)

    start = time.time()
    if to_process:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process, i, it): i for i, it in to_process}
            for fut in as_completed(futs):
                fut.result()
    else:
        logging.info("All items already resolved from checkpoint.")
    dur = time.time() - start
    logging.info(f"Time taken: {dur:.1f}s ({dur/60:.2f} mins)")

    done = [r for r in results if r is not None]
    out_path = result_folder / f"reading_answers_{sanitized_model}.csv"
    write_csv(out_path, done)
    empty = sum(1 for r in done if not r["raw_response"])
    logging.info(f"Wrote {len(done)} answers -> {out_path} | empty responses: {empty}")
    logging.info("NOTE: no accuracy computed — gold_answer is unfilled until the "
                 "2-annotator pass; scoring (EM + char-F1) runs afterwards.")


if __name__ == "__main__":
    main()
