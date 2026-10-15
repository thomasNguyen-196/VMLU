"""Patch the ViBidLQA block into web/public/benchmark-data.json.

Reads the scorer's own outputs for ONE split and writes
`blob["bidlqa"][split]`, leaving every other top-level key untouched
(the file also carries vmlu/vbench/reading/legal sections that this
script must not rebuild).

  in : all_res/ollama_result/<model>/reading_answers_bidlqa_<split>_<model>.csv
       all_res/ollama_result/<model>/reading_scores_bidlqa_<split>_<model>.csv
       all_res/ollama_result/<model>/reading_summary_bidlqa_<split>_<model>.csv
       data/bidlqa_<split>_manifest.csv            (file gold; scorer --gold)
  out: web/public/benchmark-data.json  ->  .bidlqa.<split>

The summary file is the published table; recomputing EM from the per-item
scores must agree with it (same gate as build_dashboard_reading.py).
File gold (not reviewed gold) is recorded in the caveat.

Run from repo root:
  .venv/bin/python code_benchmark/build_dashboard_bidlqa.py --split val \\
      --answers all_res/ollama_result/Qwen3_5-9B-28K/reading_answers_bidlqa_val_Qwen3_5-9B-28K.csv \\
      --card MC-12 --model-id Qwen3.5-9B-28K
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from code_benchmark.common import read_csv_checked
    from code_benchmark.run_bidlqa_eval import split_config
except ImportError:
    from common import read_csv_checked
    from run_bidlqa_eval import split_config

DASHBOARD = Path("web/public/benchmark-data.json")
RESULTS_DIR = Path("all_res/ollama_result")
MEASUREMENT_CARD = Path("measurement_card.md")


def pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Add the ViBidLQA block to the dashboard blob.")
    ap.add_argument("--dashboard", type=Path, default=DASHBOARD)
    ap.add_argument("--split", choices=("val", "test"), required=True,
                    help="BidLQA split to patch (val 482 / test 603)")
    ap.add_argument("--answers", type=Path, default=None,
                    help="reading_answers_bidlqa_<split>_<model>.csv (default: newest)")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="bidlqa manifest CSV = scorer gold (default: per-split data/ file)")
    ap.add_argument("--card", type=str, required=True,
                    help="measurement card id for this run (e.g. MC-12)")
    ap.add_argument("--max-tokens", type=int, default=48,
                    help="generation budget recorded in the condition string (default: 48)")
    ap.add_argument("--model-id", type=str, default=None,
                    help="model label recorded in the block (default: derived from --answers filename)")
    args = ap.parse_args()

    cfg = split_config(args.split)

    answers = args.answers
    if answers is None:
        found = sorted(RESULTS_DIR.rglob(f"reading_answers_bidlqa_{args.split}_*.csv"))
        if not found:
            raise SystemExit(f"Error: no reading_answers_bidlqa_{args.split}_*.csv under {RESULTS_DIR}")
        answers = found[-1]
    if not answers.exists():
        raise SystemExit(f"Error: answers file not found: {answers}")
    slug_full = answers.stem.removeprefix("reading_answers_")
    want_prefix = f"bidlqa_{args.split}_"
    if not slug_full.startswith(want_prefix):
        raise SystemExit(f"Error: {answers} is not a bidlqa-{args.split} answers file "
                         f"(want infix {want_prefix!r})")

    scores = read_csv_checked(answers.parent / f"reading_scores_{slug_full}.csv",
                              required={"dataset", "item_id", "stratum", "em", "f1"},
                              label="scores")
    summary_rows = read_csv_checked(answers.parent / f"reading_summary_{slug_full}.csv",
                                    required={"dataset", "n", "em_count", "em", "char_f1"},
                                    label="summary")
    if not scores:
        raise SystemExit(f"Error: empty scores for {answers}")
    if {str(r['dataset']) for r in scores} != {"bidlqa"}:
        raise SystemExit("Error: bidlqa scores carry non-bidlqa datasets: "
                         f"{sorted({str(r['dataset']) for r in scores})}")

    # The summary file is the published table; recomputing from per-item
    # scores must agree with it, else the dashboard would show numbers
    # nobody can reproduce from the scores CSV.
    overall_row = next((r for r in summary_rows if r["dataset"] == "ALL"), None)
    if overall_row is None:
        raise SystemExit(f"Error: no ALL row in reading_summary_{slug_full}.csv")
    n = len(scores)
    em_count = sum(int(r["em"]) for r in scores)
    em = pct(em_count, n)
    if int(overall_row["n"]) != n or abs(float(overall_row["em"]) - em) > 0.01:
        raise SystemExit(
            f"Error: summary disagrees with scores: "
            f"summary n={overall_row['n']} EM={overall_row['em']}, "
            f"recomputed n={n} EM={em}")
    char_f1 = round(sum(float(r["f1"]) for r in scores) / n * 100, 2) if n else 0.0

    manifest_path = args.manifest or cfg["manifest"]
    gold_rows = read_csv_checked(manifest_path, required={"dataset", "item_id", "gold_answer"},
                                 label="manifest")
    gold_ids = {(r["dataset"], str(r["item_id"])) for r in gold_rows}
    score_ids = {(r["dataset"], str(r["item_id"])) for r in scores}
    if gold_ids != score_ids:
        missing = sorted(gold_ids - score_ids)[:5]
        extra = sorted(score_ids - gold_ids)[:5]
        raise SystemExit(f"Error: manifest/scores id mismatch for {args.split}: "
                         f"gold={len(gold_ids)} scores={len(score_ids)}, "
                         f"e.g. missing={missing} extra={extra}")
    if args.manifest is None and len(gold_rows) != cfg["n"]:
        raise SystemExit(f"Error: manifest {manifest_path} has {len(gold_rows)} rows, "
                         f"want {cfg['n']}")

    empty = sum(1 for r in scores if not str(r.get("raw_response", "")).strip())
    card_hash = hashlib.sha256(MEASUREMENT_CARD.read_bytes()).hexdigest() if MEASUREMENT_CARD.exists() else ""
    model_label = args.model_id or slug_full.removeprefix(want_prefix)

    blob = json.loads(args.dashboard.read_text(encoding="utf-8"))
    before = {k: v for k, v in blob.items() if k != "bidlqa"}
    block = {
        "benchmark_name": "ViBidLQA — đấu thầu (đọc hiểu, open-book)",
        "date": "2026-09-20",
        "condition": (f"open-book · zero-shot · no-CoT · {args.max_tokens} token · seed 42 · "
                      f"temperature 0 — card {args.card} · frozen build_reading_prompt"),
        "measurement_card": args.card,
        "measurement_card_hash": card_hash,
        "model_id": model_label,
        "source_sha256": cfg["sha"],
        "overall": {
            "n": n,
            "em_count": em_count,
            "em": em,
            "char_f1": char_f1,
            "empty": empty,
        },
        "caveat": ("Gold lấy nguyên văn trong file (file-gold, không qua review 2 người). "
                   "EM/char-F1 chấm bằng code_benchmark/score_reading_eval.py --gold manifest."),
        "scorer": "code_benchmark/score_reading_eval.py",
    }
    bidlqa = blob.get("bidlqa") or {}
    bidlqa[args.split] = block
    blob["bidlqa"] = bidlqa

    args.dashboard.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    after = {k: v for k, v in json.loads(args.dashboard.read_text(encoding="utf-8")).items()
             if k != "bidlqa"}
    if after != before:
        raise SystemExit("Error: patch touched keys outside 'bidlqa' — refusing to leave a dirty blob")
    print(f"patched {args.dashboard} [.bidlqa.{args.split}] from {slug_full}")
    print(f"  overall n={n} EM={em_count}/{n}={em} char-F1={char_f1} empty={empty}")


if __name__ == "__main__":
    main()
