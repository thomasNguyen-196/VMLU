"""Patch the VM14K block (MC-14b) into web/public/benchmark-data.json.

Reads the frozen MC runner's own outputs and writes a `vm14k` key, leaving
every other key in the dashboard blob untouched (the file also carries
VMLU/V-Bench/reading/legal/bidlqa sections that this script must not rebuild).

  in : all_res/ollama_result/<model>/full_evaluation_vm14k_<model>.csv  (id,answer,gold_answer,correct)
       all_res/ollama_result/<model>/accuracy_vm14k_<model>.csv         (overall/category/subject-unknown)
       data/vm14k_manifest.json            (12.488 ids + gold + n_choices + difficulty_level)
       measurement_card.md                                 (hash provenance)
  out: web/public/benchmark-data.json  ->  .vm14k

The script recomputes accuracy from the per-row `correct` column and refuses
to write when the recompute disagrees with accuracy_vm14k_<model>.csv, when any
full_evaluation id lacks manifest gold, or when the two golds disagree for
the same id. Majority-class baseline (A=3915/12488) is recomputed from the
full CSV golds, never hardcoded. Difficulty / n_choices breakdowns are joined
from the pre-registered manifest (the run's own item rows carry no stratum).

Run from repo root:
  .venv/bin/python code_benchmark/build_dashboard_vm14k.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from code_benchmark.common import read_csv_checked
    from code_benchmark.vm14k_taxonomy import CATEGORY_ORDER
except ImportError:
    from common import read_csv_checked
    from vm14k_taxonomy import CATEGORY_ORDER

DASHBOARD = Path("web/public/benchmark-data.json")
RESULTS_DIR = Path("all_res/ollama_result")
MANIFEST = Path("data/vm14k_manifest.json")
MEASUREMENT_CARD = Path("measurement_card.md")

FULL_COLS = {"id", "answer", "gold_answer", "correct"}
ACC_COLS = {"level", "name", "n", "correct", "accuracy"}
DIFFICULTY_ORDER = ["Easy", "Medium", "Challenging", "Hard"]


def pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Add the VM14K block to the dashboard blob.")
    ap.add_argument("--dashboard", type=Path, default=DASHBOARD)
    ap.add_argument("--full", type=Path,
                    default=RESULTS_DIR / "Qwen3_5-9B-28K" / "full_evaluation_vm14k_Qwen3_5-9B-28K.csv",
                    help="full_evaluation_vm14k_<model>.csv (default: the MC-14b file)")
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--card", type=str, default="MC-14b",
                    help="measurement card id for this run (default: MC-14b)")
    ap.add_argument("--max-tokens", type=int, default=4,
                    help="generation budget recorded in the condition string (default: 4)")
    ap.add_argument("--workers", type=int, default=8,
                    help="worker count recorded in the condition string (default: 8)")
    ap.add_argument("--model-id", type=str, default=None,
                    help="model label recorded in the block (default: derived from --full filename)")
    ap.add_argument("--block", type=str, default="vm14k",
                    help="dashboard key to patch (default: vm14k)")
    args = ap.parse_args()
    full = args.full
    slug = full.stem.removeprefix("full_evaluation_vm14k_")

    rows = read_csv_checked(full, required=FULL_COLS, label="full")
    if not rows:
        raise SystemExit(f"Error: empty full evaluation {full}")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    man_by_id = {it["id"]: it for it in manifest["items"]}
    if len(man_by_id) != manifest["n"]:
        raise SystemExit(
            f"Error: manifest {args.manifest} lists n={manifest['n']} "
            f"but carries {len(man_by_id)} items")

    # Every evaluated id must be a manifest id, and the runner's gold column
    # must agree with the manifest gold (both derive from the same source
    # file; a mismatch means the input was rebuilt mid-run).
    for r in rows:
        rid = str(r["id"])
        want = man_by_id.get(rid)
        if want is None:
            raise SystemExit(f"Error: id {rid} in {full} not in manifest {args.manifest}")
        if str(r["gold_answer"]).strip().upper() != str(want["gold"]).strip().upper():
            raise SystemExit(
                f"Error: gold mismatch for {rid}: full has {r['gold_answer']!r}, "
                f"manifest has {want['gold']!r}")

    # Recompute from per-row correct; cross-check the accuracy file the
    # runner wrote (same rule as the legal builder: dashboard shows only
    # numbers reproducible from the CSVs).
    acc_path = full.parent / f"accuracy_vm14k_{slug}.csv"
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
    gold_counts = Counter(str(r["gold_answer"]).strip().upper() for r in rows)
    majority_letter, majority_n = gold_counts.most_common(1)[0]
    majority_baseline = pct(majority_n, n)

    # Breakdowns join the pre-registered manifest (category, difficulty_level,
    # n_choices); correctness comes from the run's own per-row `correct` column.
    correct_by_id = {str(r["id"]): int(r["correct"]) for r in rows}
    by_category: dict[str, dict[str, int]] = {}
    by_difficulty: dict[str, dict[str, int]] = {}
    by_n_choices: dict[int, dict[str, int]] = {}
    for rid, item in man_by_id.items():
        for key, store in (("category", by_category), ("difficulty_level", by_difficulty)):
            label = str(item.get(key, "") or "unknown")
            cell = store.setdefault(label, {"n": 0, "correct": 0})
            cell["n"] += 1
            cell["correct"] += correct_by_id[rid]
        try:
            nc = int(item.get("n_choices", 0))
        except (TypeError, ValueError) as err:
            raise SystemExit(f"Error: manifest item {rid} has bad n_choices {item.get('n_choices')!r}") from err
        ncell = by_n_choices.setdefault(nc, {"n": 0, "correct": 0})
        ncell["n"] += 1
        ncell["correct"] += correct_by_id[rid]

    card_hash = hashlib.sha256(MEASUREMENT_CARD.read_bytes()).hexdigest() if MEASUREMENT_CARD.exists() else ""

    blob = json.loads(args.dashboard.read_text(encoding="utf-8"))
    before = {k: v for k, v in blob.items() if k != args.block}
    model_label = args.model_id or slug
    blob[args.block] = {
        "benchmark_name": "VM14K public release — trắc nghiệm Y khoa tiếng Việt (12.488 câu, shuffled0)",
        "date": "2026-09-22",
        "condition": (f"closed-book · zero-shot · no-CoT · {args.max_tokens} token · seed 42 · "
                      f"temperature 0 · workers {args.workers} — "
                      f"card {args.card} · frozen build_prompt/extract_answer"),
        "measurement_card": args.card,
        "measurement_card_hash": card_hash,
        "model_id": model_label,
        "source_sha256": manifest.get("source_sha256", ""),
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
        "by_category": [
            {"category": g, "n": by_category[g]["n"], "correct": by_category[g]["correct"],
             "accuracy": pct(by_category[g]["correct"], by_category[g]["n"])}
            for g in CATEGORY_ORDER if g in by_category
        ] + [
            {"category": g, "n": c["n"], "correct": c["correct"],
             "accuracy": pct(c["correct"], c["n"])}
            for g, c in sorted(by_category.items()) if g not in CATEGORY_ORDER
        ],
        "by_difficulty": [
            {"difficulty": d, "n": by_difficulty[d]["n"], "correct": by_difficulty[d]["correct"],
             "accuracy": pct(by_difficulty[d]["correct"], by_difficulty[d]["n"])}
            for d in DIFFICULTY_ORDER if d in by_difficulty
        ] + [
            {"difficulty": d, "n": c["n"], "correct": c["correct"],
             "accuracy": pct(c["correct"], c["n"])}
            for d, c in sorted(by_difficulty.items()) if d not in DIFFICULTY_ORDER
        ],
        "by_n_choices": [
            {"n_choices": nc, "n": c["n"], "correct": c["correct"],
             "accuracy": pct(c["correct"], c["n"])}
            for nc, c in sorted(by_n_choices.items())
        ],
        "blank_ids": blanks,
        "caveat": ("Public release lệch paper (12.488 dòng/file, không rõ partition; private 2k "
                   "không có) + không license (research-use, trích dẫn paper + HF). "
                   "1.377/12.488 dòng ≠ 4 lựa chọn (1.240 Đúng/Sai, 15 câu 1 lựa chọn, "
                   "34 dòng placeholder optionE/F/G); ~6% trùng lặp giữ nguyên (không dedupe). "
                   "Model 9B vượt giới hạn ≤4B của suite — ghi rõ khi công bố. "
                   "Chỉ đối chiếu hướng với V-Bench medicine, không trừ phần trăm (khác dạng câu)."),
    }

    args.dashboard.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    after = {k: v for k, v in json.loads(args.dashboard.read_text(encoding="utf-8")).items()
             if k != args.block}
    if after != before:
        raise SystemExit(f"Error: patch touched keys outside {args.block!r} — refusing to leave a dirty blob")
    print(f"patched {args.dashboard} [.{args.block}] from {slug}")
    print(f"  overall n={n} correct={correct} acc={accuracy} valid={valid} blanks={len(blanks)}")
    print(f"  baseline {majority_letter}={majority_n}/{n} ({majority_baseline}%)")


if __name__ == "__main__":
    main()
