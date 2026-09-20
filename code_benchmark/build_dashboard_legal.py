"""Patch the LegalSLM-multichoice block (MC-6) into web/public/benchmark-data.json.

Reads the frozen MC runner's own outputs and writes a `legal` key, leaving
every other key in the dashboard blob untouched (the file also carries
VMLU/V-Bench/reading sections that this script must not rebuild).

  in : all_res/ollama_result/<model>/full_evaluation_<model>.csv   (id,answer,gold_answer,correct)
       data/legal_slm_multichoice_manifest.json            (LG-0001..LG-0146 + gold)
       measurement_card.md                                 (hash provenance)
  out: web/public/benchmark-data.json  ->  .legal

The script recomputes accuracy from the per-row `correct` column and refuses
to write when the recompute disagrees with accuracy_<model>.csv, when any
full_evaluation id lacks manifest gold, or when the two golds disagree for
the same id. Majority-class baseline (A=91/146) is recomputed from manifest
golds, never hardcoded.

Run from repo root:
  .venv/bin/python code_benchmark/build_dashboard_legal.py [--model qwen38-nothink]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from code_benchmark.common import read_csv_checked
except ImportError:
    from common import read_csv_checked

DASHBOARD = Path("web/public/benchmark-data.json")
RESULTS_DIR = Path("all_res/ollama_result")
MANIFEST = Path("data/legal_slm_multichoice_manifest.json")
MEASUREMENT_CARD = Path("measurement_card.md")

FULL_COLS = {"id", "answer", "gold_answer", "correct"}
ACC_COLS = {"level", "name", "n", "correct", "accuracy"}


def pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Add the LegalSLM multichoice block to the dashboard blob.")
    ap.add_argument("--dashboard", type=Path, default=DASHBOARD)
    ap.add_argument("--full", type=Path, default=RESULTS_DIR / "qwen38-nothink" / "full_evaluation_qwen38-nothink.csv",
                    help="full_evaluation_<model>.csv (default: the MC-6 file; pass explicitly for another model)")
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--card", type=str, default="MC-6",
                    help="measurement card id for this run (default: MC-6)")
    ap.add_argument("--max-tokens", type=int, default=512,
                    help="generation budget recorded in the condition string (default: 512)")
    ap.add_argument("--model-id", type=str, default=None,
                    help="model label recorded in the block (default: derived from --full filename)")
    ap.add_argument("--block", type=str, default="legal",
                    help="dashboard key to patch (default: legal; use legal_nli for the NLI run)")
    args = ap.parse_args()
    full = args.full
    slug = full.stem.removeprefix("full_evaluation_")

    rows = read_csv_checked(full, required=FULL_COLS, label="full")
    if not rows:
        raise SystemExit(f"Error: empty full evaluation {full}")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    gold_by_id = {it["id"]: it["gold"] for it in manifest["items"]}
    if len(gold_by_id) != manifest["n"]:
        raise SystemExit(
            f"Error: manifest {args.manifest} lists n={manifest['n']} "
            f"but carries {len(gold_by_id)} items")

    # Every evaluated id must be a manifest id, and the runner's gold column
    # must agree with the manifest gold (both derive from the same source
    # file; a mismatch means the input was rebuilt mid-run).
    for r in rows:
        rid = str(r["id"])
        want = gold_by_id.get(rid)
        if want is None:
            raise SystemExit(f"Error: id {rid} in {full} not in manifest {args.manifest}")
        if str(r["gold_answer"]).strip().upper() != str(want).strip().upper():
            raise SystemExit(
                f"Error: gold mismatch for {rid}: full has {r['gold_answer']!r}, "
                f"manifest has {want!r}")

    # Recompute from per-row correct; cross-check the accuracy file the
    # runner wrote (same rule as the reading builder: dashboard shows only
    # numbers reproducible from the CSVs).
    acc_path = full.parent / f"accuracy_{slug}.csv"
    if not acc_path.exists():
        raise SystemExit(f"Error: missing runner accuracy file {acc_path}")
    acc_rows = read_csv_checked(acc_path, required=ACC_COLS, label="accuracy")
    overall = next((a for a in acc_rows if a["level"] == "overall"), None)
    if overall is None:
        raise SystemExit(f"Error: no overall row in {acc_path}")
    n = len(rows)
    correct = sum(int(r["correct"]) for r in rows)
    accuracy = pct(correct, n)
    if int(overall["n"]) != n or int(overall["correct"]) != correct \
            or abs(float(overall["accuracy"]) - accuracy) > 0.01:
        raise SystemExit(
            f"Error: {acc_path} overall disagrees with {full}: "
            f"accuracy n={overall['n']} correct={overall['correct']} acc={overall['accuracy']}, "
            f"recomputed n={n} correct={correct} acc={accuracy}")
    valid = sum(1 for r in rows if str(r.get("answer", "")).strip())
    blanks = [str(r["id"]) for r in rows if not str(r.get("answer", "")).strip()]
    wrong_parsed = sum(1 for r in rows if str(r.get("answer", "")).strip() and not int(r["correct"]))

    by_gold: dict[str, dict[str, int]] = {}
    for r in rows:
        g = str(r["gold_answer"]).strip().upper()
        cell = by_gold.setdefault(g, {"n": 0, "correct": 0})
        cell["n"] += 1
        cell["correct"] += int(r["correct"])

    from collections import Counter
    gold_counts = Counter(gold_by_id.values())
    majority_letter, majority_n = gold_counts.most_common(1)[0]
    majority_baseline = pct(majority_n, len(gold_by_id))

    card_hash = hashlib.sha256(MEASUREMENT_CARD.read_bytes()).hexdigest() if MEASUREMENT_CARD.exists() else ""

    blob = json.loads(args.dashboard.read_text(encoding="utf-8"))
    before = {k: v for k, v in blob.items() if k != args.block}
    model_label = args.model_id or slug
    benchmark_name = ("VLSP2025-LegalSLM public-test — nli (suy luận entailment, nhị phân Có/Không qua MC runner)"
                      if args.block == "legal_nli" else
                      "VLSP2025-LegalSLM public-test — multichoice (luật, trắc nghiệm)")
    caveat = (
        "Model >4B trong khi suite giới hạn ≤4B — ghi rõ khi công bố. "
        "Cấm so ngang VMLU 73% (suite khác dạng).")
    if blanks:
        caveat = (f"{len(blanks)} câu raw rỗng tính sai; nguyên nhân chưa rõ. " + caveat)
    blob[args.block] = {
        "benchmark_name": benchmark_name,
        "date": "2026-09-19",
        "condition": (f"closed-book · zero-shot · no-CoT · {args.max_tokens} token · seed 42 · temperature 0 — "
                      f"card {args.card} · frozen build_prompt/extract_answer"),
        "measurement_card": args.card,
        "measurement_card_hash": card_hash,
        "model_id": model_label,
        "overall": {
            "n": n,
            "correct": correct,
            "accuracy": accuracy,
            "valid": valid,
            "blanks": len(blanks),
            "wrong_parsed": wrong_parsed,
        },
        "baseline": {
            "majority_letter": majority_letter,
            "majority_n": majority_n,
            "majority_accuracy": majority_baseline,
            "label": f"Luôn đáp {majority_letter}",
        },
        "by_gold": [
            {"gold": g, "n": c["n"], "correct": c["correct"], "accuracy": pct(c["correct"], c["n"])}
            for g, c in sorted(by_gold.items())
        ],
        "blank_ids": blanks,
        "caveat": caveat,
    }

    args.dashboard.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    after = {k: v for k, v in json.loads(args.dashboard.read_text(encoding="utf-8")).items()
             if k != args.block}
    if after != before:
        raise SystemExit(f"Error: patch touched keys outside {args.block!r} — refusing to leave a dirty blob")
    print(f"patched {args.dashboard} [.{args.block}] from {slug}")
    print(f"  overall n={n} correct={correct} acc={accuracy} valid={valid} blanks={len(blanks)}")
    print(f"  baseline {majority_letter}={majority_n}/{len(gold_by_id)} ({majority_baseline}%)")


if __name__ == "__main__":
    main()
