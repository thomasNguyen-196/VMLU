"""Patch the reading-comprehension block into web/public/benchmark-data.json.

Reads the scorer's own outputs and writes a `reading` key, leaving every other
key in the dashboard blob untouched (the file also carries ad-hoc VMLU/V-Bench
sections that this script must not rebuild).

  in : all_res/ollama_result/<model>/reading_scores_<model>.csv
       all_res/ollama_result/<model>/reading_summary_<model>.csv
       review_records/review_nttung245_<slug>.csv      (accept / reject counts)
  out: web/public/benchmark-data.json  ->  .reading

Run from repo root:
  .venv/bin/python code_benchmark/build_dashboard_reading.py
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
MEASUREMENT_CARD = Path("measurement_card.md")

STRATUM_LABELS = {
    "short-direct": "Ngắn — trả lời trực tiếp",
    "mid-direct": "Trung bình — trả lời trực tiếp",
    "long-direct": "Dài — trả lời trực tiếp",
    "short-infer": "Ngắn — phải suy luận",
    "mid-infer": "Trung bình — phải suy luận",
    "long-infer": "Dài — phải suy luận",
    "add_sub": "Cộng / trừ hai thành phần",
    "comparison": "So sánh",
    "count": "Đếm",
    "selection": "Chọn thông tin",
    "other": "Khác",
}


def pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def read_rows(path: Path, **kw) -> list[dict]:
    return read_csv_checked(path, **kw)


def main() -> None:
    ap = argparse.ArgumentParser(description="Add the reading eval block to the dashboard blob.")
    ap.add_argument("--dashboard", type=Path, default=DASHBOARD)
    ap.add_argument("--answers", type=Path, default=None,
                    help="reading_answers_<model>.csv (default: newest)")
    ap.add_argument("--review-record", type=Path, default=None,
                    help="review_*.csv for the accept/reject split (default: match by model slug; "
                         "pass the gold-defining record when scoring a different model on the same frozen gold)")
    args = ap.parse_args()

    answers = args.answers
    if answers is None:
        found = sorted(RESULTS_DIR.rglob("reading_answers_*.csv"))
        if not found:
            raise SystemExit(f"Error: no reading_answers_*.csv under {RESULTS_DIR}")
        answers = found[-1]
    slug_full = answers.stem.removeprefix("reading_answers_")

    scores = read_rows(answers.parent / f"reading_scores_{slug_full}.csv",
                       required={"dataset", "item_id", "stratum", "em", "f1"},
                       label="scores")
    summary_rows = read_rows(answers.parent / f"reading_summary_{slug_full}.csv",
                             required={"dataset", "n", "em_count", "em", "char_f1"},
                             label="summary")

    # The summary file is the published table; recomputing from per-item scores must
    # agree with it. A mismatch means the dashboard would show numbers nobody can
    # reproduce from the scores CSV, so fail instead of writing the blob.
    for row in summary_rows:
        sub = scores if row["dataset"] == "ALL" else [
            r for r in scores if r["dataset"] == row["dataset"]]
        if not sub:
            continue
        em = round(sum(int(r["em"]) for r in sub) / len(sub) * 100, 2)
        if len(sub) != int(row["n"]) or abs(em - float(row["em"])) > 0.01:
            raise SystemExit(
                f"Error: summary disagrees with scores for {row['dataset']}: "
                f"summary n={row['n']} EM={row['em']}, recomputed n={len(sub)} EM={em}")

    # Review decisions give the accept/reject split behind the optimistic bias note.
    # NOTE: two different naming conventions coexist — the runner writes
    # `reading_answers_<sanitize_model>.csv` (case preserved) while review records
    # use `slug()` (lowercased). Match on the slugified stem, not on the stem itself.
    def slug(s: str) -> str:
        import re as _re
        import unicodedata as _ud
        s = _ud.normalize("NFD", s.strip().lower())
        s = "".join(c for c in s if not _ud.combining(c))
        return _re.sub(r"[^a-z0-9]+", "_", s).strip("_")

    want = slug(slug_full)
    if args.review_record is not None:
        reviews = [args.review_record]
        if not reviews[0].exists():
            raise SystemExit(f"Error: --review-record not found: {reviews[0]}")
    else:
        reviews = [p for p in Path("review_records").glob("review_*.csv")
                   if slug(p.stem) .endswith(want) or want.endswith(slug(p.stem))]
    if not reviews:
        raise SystemExit(
            f"Error: no review record matching model slug {want!r} in review_records/ — "
            f"expected review_<reviewer>_{want}.csv or pass --review-record")
    decisions = read_rows(reviews[0], required={"dataset", "decision"}, label="review")

    def group(subset: list[dict]) -> dict:
        n = len(subset)
        em = sum(int(r["em"]) for r in subset)
        return {
            "n": n,
            "em_count": em,
            "em": pct(em, n),
            "char_f1": round(sum(float(r["f1"]) for r in subset) / n * 100, 2) if n else 0.0,
        }

    by_source = {}
    for ds in ("squad", "drop"):
        sub = [r for r in scores if r["dataset"] == ds]
        if not sub:
            continue
        block = group(sub)
        block["label"] = "Vi-SQuAD" if ds == "squad" else "Vi-DROP"
        block["reject_count"] = sum(
            1 for r in decisions if r["dataset"] == ds and r["decision"] == "reject")
        block["strata"] = []
        for stratum in dict.fromkeys(r["stratum"] for r in sub):
            ss = [r for r in sub if r["stratum"] == stratum]
            g = group(ss)
            g["stratum"] = stratum
            g["label"] = STRATUM_LABELS.get(stratum, stratum)
            block["strata"].append(g)
        by_source[ds] = block

    overall = group(scores)
    overall["label"] = "Tổng"

    card_hash = hashlib.sha256(MEASUREMENT_CARD.read_bytes()).hexdigest() if MEASUREMENT_CARD.exists() else ""

    blob = json.loads(args.dashboard.read_text(encoding="utf-8"))
    blob["reading"] = {
        "benchmark_name": "Reading comprehension — 400 câu tiền đăng ký (Vi-SQuAD + Vi-DROP)",
        "date": "2026-09-12",
        "condition": ("open-book · zero-shot · no-CoT · 48 token · seed 42 · temperature 0 — "
                      "card MC-3"),
        "measurement_card_hash": card_hash,
        "overall": overall,
        "sources": [by_source[k] for k in ("squad", "drop") if k in by_source],
        "caveat": ("Đáp án tham chiếu của 321/400 câu được kế thừa từ chính câu trả lời của mô "
                   "hình (người duyệt bấm chấp nhận). Vì vậy EM/char-F1 ở đây là cận trên có "
                   "thiên lệch thuận, không phải điểm năng lực. Con số accept-rate nằm ở phụ lục "
                   "của docs/agents/reading-results-table.md."),
        "scorer": "code_benchmark/score_reading_eval.py",
    }

    args.dashboard.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    print(f"patched {args.dashboard} from {slug_full}")
    print(f"  overall n={overall['n']} EM={overall['em']} char-F1={overall['char_f1']}")
    for v in by_source.values():
        print(f"  {v['label']:8s} n={v['n']} EM={v['em']} char-F1={v['char_f1']} rejects={v['reject_count']}")


if __name__ == "__main__":
    main()
