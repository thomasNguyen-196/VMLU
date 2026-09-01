"""Inference runner for the 400-question reading-comprehension eval set (issue #3).

Consumes `eval_set_manifest.csv` (from make_eval_sample.py) plus the two
question_only source JSONs, calls the model on each {context, question} pair,
and writes per-item free-text answers:

  all_res/ollama_result/reading_answers_<model>.csv

This is deliberately SEPARATE from test_ollama.py: that harness is the frozen
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
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from openai import OpenAI

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.test_ollama import call_model_with_retry, verify_credentials
except ImportError:
    from test_ollama import call_model_with_retry, verify_credentials

load_dotenv()

DEFAULT_MANIFEST = Path("eval_set_manifest.csv")
CHECKPOINT_PREFIX = "reading_result_"  # never collides with raw_result_*.csv of the MC run


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
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    need = {"dataset", "item_id", "stratum", "question"}
    if not rows:
        raise SystemExit(f"Error: empty manifest {path}")
    missing = need - set(rows[0])
    if missing:
        raise SystemExit(f"Error: manifest {path} lacks columns: {sorted(missing)}")
    return rows


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
    return f"{row['dataset']}:{row['item_id']}"


def find_latest_reading_checkpoint(folder: Path) -> Path | None:
    best, best_n = None, -1
    for p in folder.glob(f"{CHECKPOINT_PREFIX}*.csv"):
        m = re.search(r"reading_result_(\d+)\.csv", p.name)
        if m and int(m.group(1)) > best_n:
            best, best_n = p, int(m.group(1))
    return best


def parse_args():
    ap = argparse.ArgumentParser(description="Run the 400-question reading eval (issue #3).")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--squad-file", type=Path,
                    default=Path("vmlu_squad_v1/vi_squad_benchmark_question_only.json"))
    ap.add_argument("--drop-file", type=Path,
                    default=Path("vmlu_drop_v1/vi_drop_benchmark_3309_question_only.json"))
    ap.add_argument("--model", type=str, default=None, help="overrides OPENAI_MODEL")
    ap.add_argument("--base-url", type=str, default=None, help="overrides OPENAI_BASE_URL")
    ap.add_argument("--api-key", type=str, default=None, help="overrides OPENAI_API_KEY")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-tokens", type=int, default=48,
                    help="answer budget (extractive spans are short; 48 is generous)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="first N manifest rows only")
    ap.add_argument("--resume", action="store_true",
                    help="continue from the newest reading_result_*.csv checkpoint")
    args = ap.parse_args()
    if args.limit is not None and args.limit <= 0:
        ap.error("--limit must be > 0")
    return args


def main():
    args = parse_args()
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY") or "ollama"
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL")
    model = args.model or os.environ.get("OPENAI_MODEL")
    if not base_url or not model:
        print("Error: set OPENAI_BASE_URL / OPENAI_MODEL (or pass --base-url/--model).", file=sys.stderr)
        sys.exit(1)

    os.makedirs("logs", exist_ok=True)
    result_folder = Path("all_res/ollama_result")
    result_folder.mkdir(parents=True, exist_ok=True)
    sanitized_model = re.sub(r"[^a-zA-Z0-9_-]", "_", model)

    logging.basicConfig(filename=f"logs/reading_{sanitized_model}.log", level=logging.INFO,
                        format="%(asctime)s - %(levelname)s: %(message)s")
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger("").addHandler(console)

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

    client = OpenAI(base_url=base_url, api_key=api_key)
    logging.info("Verifying endpoint connectivity and credentials...")
    verify_credentials(client, model)

    existing: dict[str, dict] = {}
    if args.resume:
        cp = find_latest_reading_checkpoint(result_folder)
        if cp:
            logging.info(f"Resuming from checkpoint: {cp}")
            with open(cp, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing[resume_key(row)] = row

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
                write_csv(result_folder / f"{CHECKPOINT_PREFIX}{len(done)}.csv", done)
        return index

    def write_csv(path: Path, rows: list[dict]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["dataset", "item_id", "stratum",
                                              "question", "context_words", "raw_response"])
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
