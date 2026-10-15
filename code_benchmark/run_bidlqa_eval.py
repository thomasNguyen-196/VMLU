"""Inference runner for ViBidLQA test/val on Qwen3.5 (change qwen35-gold-matrix-2).

ViBidLQA rows are {context, question, answer} free-text reading items — the
same open-book MC-3 condition as the 400-question reading eval: the FROZEN
build_reading_prompt from run_reading_eval (imported, never copied),
48-token budget, temperature 0, seed 42. Only the source join differs
(BidLQA jsonl instead of squad/drop), so this thin runner owns the BidLQA
manifest join while run_reading_eval.py stays byte-frozen.

  manifests  : data/bidlqa_val_manifest.csv (482, BIDLQA-V-0001..) +
               data/bidlqa_test_manifest.csv (603, BIDLQA-T-0001..),
               MANIFEST_COLS shape; doubles as scorer --gold.
  answers    : all_res/ollama_result/<model>/reading_answers_bidlqa_<split>_<model>.csv
               (reading_answers_* shape so score_reading_eval.py works
               unchanged; the bidlqa infix keeps MC-3's file untouched)
  checkpoints: bidlqa_<split>_result_<count>_<model>.csv (never collides
               with reading_result_*; --resume only picks its own split+model)

Source sha256 is pinned per split (module constants); any drift aborts
before any inference or manifest write. Rebuild: --build-manifest rewrites
the CSV from source (row count + non-empty gold asserted).

Run from repo root:
  .venv/bin/python code_benchmark/run_bidlqa_eval.py --split val --build-manifest
  .venv/bin/python code_benchmark/run_bidlqa_eval.py --split val --model Qwen3.5-9B-28K --workers 4
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import (sanitize_model, resolve_endpoint, model_dirs,
                                       MANIFEST_COLS,
                                       read_csv_checked, add_endpoint_args,
                                       parse_endpoint_args, setup_logging, item_key,
                                       write_csv_atomic)
    from code_benchmark.checkpoint import checkpoint_name, find_latest_checkpoint
    from code_benchmark.llm import build_client, verify_credentials, call_model_with_retry
    from code_benchmark.run_reading_eval import build_reading_prompt, ANSWER_COLS
except ImportError:
    from common import (sanitize_model, resolve_endpoint, model_dirs,
                        MANIFEST_COLS,
                        read_csv_checked, add_endpoint_args,
                        parse_endpoint_args, setup_logging, item_key,
                        write_csv_atomic)
    from checkpoint import checkpoint_name, find_latest_checkpoint
    from llm import build_client, verify_credentials, call_model_with_retry
    from run_reading_eval import build_reading_prompt, ANSWER_COLS

load_dotenv()

# Pinned source identity (sha256 of the exact bytes; drift aborts the run).
BIDLQA_VAL_SOURCE = Path("v_legal_slsp/bidlqa/ViBidLQA_val.jsonl")
BIDLQA_TEST_SOURCE = Path("v_legal_slsp/bidlqa/ViBidLQA_test.jsonl")
BIDLQA_VAL_SHA = "4cafca9de80ebdcd20d0267245a0fcd86245ff4c5985669cb3ef7cc9c433e800"
BIDLQA_TEST_SHA = "b99b94842a32ed6f9151c804adc202c8a54f3362ab30be9c4dfe06b02eb6358d"
BIDLQA_VAL_MANIFEST = Path("data/bidlqa_val_manifest.csv")
BIDLQA_TEST_MANIFEST = Path("data/bidlqa_test_manifest.csv")

SPLITS = ("val", "test")


def split_config(split: str) -> dict:
    """Per-split (source, sha, manifest, id prefix, checkpoint prefix)."""
    if split == "val":
        return {"source": BIDLQA_VAL_SOURCE, "sha": BIDLQA_VAL_SHA,
                "manifest": BIDLQA_VAL_MANIFEST, "id_prefix": "BIDLQA-V",
                "ckpt_prefix": "bidlqa_val_result_", "n": 482}
    if split == "test":
        return {"source": BIDLQA_TEST_SOURCE, "sha": BIDLQA_TEST_SHA,
                "manifest": BIDLQA_TEST_MANIFEST, "id_prefix": "BIDLQA-T",
                "ckpt_prefix": "bidlqa_test_result_", "n": 603}
    raise SystemExit(f"Error: --split must be one of {SPLITS}, got {split!r}")


def load_source(source: Path, sha: str) -> list[dict]:
    """Read + verify the BidLQA jsonl: sha pin, row shape, non-empty fields."""
    if not source.exists():
        raise SystemExit(f"Error: source not found: {source}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != sha:
        raise SystemExit(f"Error: source drift for {source}: sha {digest} != pinned {sha}")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    for i, r in enumerate(rows, start=1):
        for field in ("context", "question", "answer"):
            if not str(r.get(field, "")).strip():
                raise SystemExit(f"Error: empty {field} at {source} line {i}")
    return rows


def build_manifest_rows(src_rows: list[dict], id_prefix: str) -> list[dict]:
    """Source order -> stable ids; single auction stratum (all BidLQA is bid-law QA)."""
    return [{"dataset": "bidlqa", "item_id": f"{id_prefix}-{i:04d}",
             "stratum": "auction", "passage_id": str(i),
             "question": r["question"].strip(), "gold_answer": r["answer"].strip()}
            for i, r in enumerate(src_rows, start=1)]


def verify_join(manifest: list[dict], src_rows: list[dict], id_prefix: str) -> None:
    """Manifest must be the exact 1:1 image of source (order, ids, questions, gold)."""
    want_ids = [f"{id_prefix}-{i:04d}" for i in range(1, len(src_rows) + 1)]
    got_ids = [str(r["item_id"]) for r in manifest]
    if got_ids != want_ids:
        raise SystemExit(f"Error: manifest ids drift for {id_prefix}: "
                         f"n={len(got_ids)} want n={len(want_ids)}, e.g. {got_ids[:3]}")
    for m, s in zip(manifest, src_rows, strict=True):
        if str(m["question"]).strip() != str(s["question"]).strip():
            raise SystemExit(f"Error: question drift for {m['item_id']}")
        if str(m["gold_answer"]).strip() != str(s["answer"]).strip():
            raise SystemExit(f"Error: gold drift for {m['item_id']}")


def cmd_build_manifest(cfg: dict, out: Path) -> None:
    src_rows = load_source(cfg["source"], cfg["sha"])
    if len(src_rows) != cfg["n"]:
        raise SystemExit(f"Error: {cfg['source']} has {len(src_rows)} rows, want {cfg['n']}")
    rows = build_manifest_rows(src_rows, cfg["id_prefix"])
    verify_join(rows, src_rows, cfg["id_prefix"])
    write_csv_atomic(out, rows, MANIFEST_COLS)
    print(f"wrote {out} n={len(rows)} ids {rows[0]['item_id']}..{rows[-1]['item_id']}")


def parse_args():
    ap = argparse.ArgumentParser(description="Run the ViBidLQA eval (MC-3 condition).")
    ap.add_argument("--split", choices=SPLITS, required=True,
                    help="BidLQA split to run (val 482 / test 603)")
    ap.add_argument("--source", type=Path, default=None,
                    help="BidLQA jsonl (default: per-split source)")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="BidLQA manifest CSV (default: per-split data/ file)")
    ap.add_argument("--manifest-out", type=Path, default=None,
                    help="--build-manifest destination (default: per-split data/ file)")
    ap.add_argument("--build-manifest", action="store_true",
                    help="rebuild the manifest CSV from source and exit (no inference)")
    add_endpoint_args(ap, max_tokens_default=48,
                      max_tokens_help="answer budget (same 48 as MC-3)",
                      resume_help="continue from the newest bidlqa_<split>_result_<count>_<model>.csv checkpoint")
    return parse_endpoint_args(ap)


def main():
    args = parse_args()
    cfg = split_config(args.split)
    source = args.source or cfg["source"]
    manifest_path = args.manifest or cfg["manifest"]

    if args.build_manifest:
        cmd_build_manifest(cfg, args.manifest_out or cfg["manifest"])
        return

    base_url, api_key, model = resolve_endpoint(args)
    sanitized_model = sanitize_model(model)
    result_folder, _, logs_folder = model_dirs(model)
    setup_logging(logs_folder / f"bidlqa_{args.split}_{sanitized_model}.log")
    logging.info(f"Model: {model} @ {base_url} | split={args.split} "
                 f"workers={args.workers} temp={args.temperature} seed={args.seed} "
                 f"max_tokens={args.max_tokens}")

    src_rows = load_source(source, cfg["sha"])
    manifest = read_csv_checked(manifest_path,
                                required={"dataset", "item_id", "stratum", "question",
                                          "gold_answer"},
                                label="bidlqa-manifest")
    verify_join(manifest, src_rows, cfg["id_prefix"])
    items = [{**m, "context": s["context"]} for m, s in zip(manifest, src_rows, strict=True)]
    if args.limit:
        items = items[: args.limit]
    total = len(items)
    logging.info(f"Joined {total} manifest rows to contexts (split={args.split})")

    client = build_client(base_url, api_key)
    logging.info("Verifying endpoint connectivity and credentials...")
    verify_credentials(client, model)

    ckpt_prefix = cfg["ckpt_prefix"]
    existing: dict[str, dict] = {}
    if args.resume:
        cp = find_latest_checkpoint(result_folder, model, prefix=ckpt_prefix)
        if cp:
            logging.info(f"Resuming from checkpoint: {cp}")
            with open(cp, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing[item_key(row)] = row
        else:
            others = sorted(result_folder.glob(f"{ckpt_prefix}*.csv"))
            if others:
                logging.warning("No checkpoint for model '%s' under prefix '%s' — starting fresh.",
                                model, ckpt_prefix)

    results: list[dict | None] = [None] * total
    to_process = []
    for i, item in enumerate(items):
        k = item_key(item)
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
                with open(result_folder / checkpoint_name(model, len(done),
                                                          prefix=ckpt_prefix),
                          "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=ANSWER_COLS)
                    w.writeheader()
                    w.writerows(done)
        return index

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
    out_path = result_folder / f"reading_answers_bidlqa_{args.split}_{sanitized_model}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ANSWER_COLS)
        w.writeheader()
        w.writerows(done)
    empty = sum(1 for r in done if not r["raw_response"])
    logging.info(f"Wrote {len(done)} answers -> {out_path} | empty responses: {empty}")
    logging.info("NOTE: file gold lives in the manifest CSV — score with "
                 "score_reading_eval.py --answers <this file> --gold <manifest>.")


if __name__ == "__main__":
    main()
