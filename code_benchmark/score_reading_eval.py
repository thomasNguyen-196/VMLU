"""Score the 400-question reading-comprehension eval: EM + char-F1 against gold.

Consumes the gold published by the review pass and the model answers:

  data/review_gold_agreed.csv                       (dataset, item_id, gold_answer)
  all_res/ollama_result/reading_answers_<model>.csv (dataset, item_id, raw_response)

and writes per-item scores plus a summary table:

  all_res/ollama_result/reading_scores_<model>.csv
  all_res/ollama_result/reading_summary_<model>.csv

UNITS — the same name `em` means two different things, do not mix them up when
reading the outputs:

  per-item  em   : {0, 1}         binary per question — a fractional value here is a BUG
  per-item  f1   : [0, 1]         partial credit (character F1)
  summary   em_count : int        NUMBER OF CORRECT QUESTIONS — the number to check by hand
  summary   em   : 0..100 (%)     em_count / n * 100 — a RATE, not a per-item score
  summary   char_f1 : 0..100 (%)  mean of the per-item f1 values

So the summary `em` of 80.25 is 321/400*100, not an average of partial scores.
EM stays binary per item; only the division introduces decimals. With n=400 the
smallest step of summary `em` is 1/400 = 0.25.

WHY THIS EXISTS: the review UI reports an "accept rate" — the share of model
answers a single reviewer confirmed as the reference. That is NOT accuracy: the
reference was inherited from the model's own output, so any error the reviewer
missed counts as correct. EM / char-F1 measured against that fixed reference is
the reportable number; accept rate belongs in an appendix.

Usage (repo root):
  .venv/bin/python code_benchmark/score_reading_eval.py
  .venv/bin/python code_benchmark/score_reading_eval.py --answers path.csv --gold path.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path

try:
    from code_benchmark.common import write_csv_atomic, setup_logging, item_key
except ImportError:
    from common import write_csv_atomic, setup_logging, item_key

RESULTS_DIR = Path("all_res/ollama_result")
GOLD_DEFAULT = Path("data/review_gold_agreed.csv")

SCORE_COLS = ["dataset", "item_id", "stratum", "gold_answer", "raw_response",
              "prediction", "em", "f1", "exact_raw"]

# Gold answers that mean "the passage cannot answer this" (Vi-SQuAD unanswerable,
# 5.4% of the source set). A model that says something else is wrong.
NO_ANSWER_RE = re.compile(
    r"^\s*(no\s*answer|kh[oô]ng\s+c[oó]\s+c[aâ]u\s+tr[ảa]\s+l[ờo]i|"
    r"kh[oô]ng\s+t[ìi]m\s+th[ấa]y)\s*[.!]?\s*$",
    re.IGNORECASE | unicodedata.normalize("NFC", "") if False else re.IGNORECASE,
)

# Percentages, decimals and thousands separators: "30,40%" == "30.40 %" == "30.4%".
_PCT_RE = re.compile(r"^(-?\d+(?:[.,]\d+)?)\s*%$")
_GROUPED_RE = re.compile(r"^\d{1,3}(?:[.,\s]\d{3})+$")
_NUM_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def strip_diacritics(s: str) -> str:
    """NFD-decompose then drop combining marks — for a diacritic-insensitive variant."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def to_number(s: str) -> float | None:
    """Parse a Vietnamese-format number, tolerating ./, as either separator.

    '1.234,5' -> 1234.5  |  '1,234.5' -> 1234.5  |  '32.100' -> 32100  |  '0.400' -> 0.4
    Returns None when the string is not a plain number.
    """
    t = s.strip().rstrip("%").strip()
    if not t:
        return None
    has_dot, has_comma = "." in t, "," in t
    if has_dot and has_comma:
        # The LAST separator is the decimal one; the other groups thousands.
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif has_comma or has_dot:
        sep = "," if has_comma else "."
        int_part, _, frac = t.rpartition(sep)
        digits = int_part.lstrip("-")
        # A separator followed by exactly 3 digits groups thousands ('32.100') —
        # unless the integer part is a bare zero, where only a decimal makes
        # sense ('0.400' is 0.4, never 400).
        is_thousands = (
            len(frac) == 3
            and frac.isdigit()
            and digits.isdigit()
            and digits != "0"
            and not digits.startswith("0")
        )
        t = t.replace(sep, "") if is_thousands else f"{int_part}.{frac}"
    try:
        return float(t)
    except ValueError:
        return None


def normalize_answer(s: str) -> str:
    """Casefold, collapse whitespace, drop trailing punctuation — the comparison form."""
    s = unicodedata.normalize("NFC", s or "").strip().casefold()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" \t\n\r.,;:!?\"'()[]{}")
    return s


def canonical_variants(s: str) -> set[str]:
    """Equivalent surface forms of one answer string, for Exact Match.

    The published gold answers are free text ('Bằng nhau, mỗi quân đoàn có 3 sư đoàn'),
    so EM is scored as: normalized string equality, diacritic-insensitive equality,
    or numeric equality when both sides are numbers.
    """
    base = normalize_answer(s)
    if not base:
        return {""}
    forms = {base, strip_diacritics(base)}
    m = _PCT_RE.match(base)
    num = to_number(m.group(1)) if m else (to_number(base) if _NUM_RE.match(base) or _GROUPED_RE.match(base) else None)
    if num is not None:
        # Canonical numeric spelling catches 30,4 == 30.40 == 30.4%
        forms.add(f"{num:g}")
    return {f for f in forms if f is not None}


def char_f1(pred: str, gold: str) -> float:
    """Character-level F1 between prediction and gold (order-insensitive multiset).

    Character F1 is the standard companion to EM on extractive QA: a partially
    correct span still earns partial credit, which matters because the answer
    budget is 48 tokens and Vietnamese answers vary in length.
    """
    p = normalize_answer(pred)
    g = normalize_answer(gold)
    if not p and not g:
        return 1.0
    if not p or not g:
        return 0.0
    common = Counter(p) & Counter(g)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(p)
    recall = overlap / len(g)
    return 2 * precision * recall / (precision + recall)


def score_pair(pred_raw: str, gold_raw: str) -> tuple[str, float, bool, bool]:
    """-> (prediction_used, f1, em, exact_raw).

    `prediction_used` is the cleaned form actually compared; `exact_raw` records
    whether the model emitted the answer verbatim (no cleanup needed).
    """
    pred = (pred_raw or "").strip()
    gold = (gold_raw or "").strip()
    exact_raw = normalize_answer(pred) == normalize_answer(gold)
    em = bool(canonical_variants(pred) & canonical_variants(gold))
    return pred, char_f1(pred, gold), em, exact_raw


def read_csv_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


MEASUREMENT_CARD = Path("measurement_card.md")


def measurement_card_hash(path: Path = MEASUREMENT_CARD) -> str:
    """sha256 of the condition document. Every run stamps this into its output so
    a score can always be traced back to the exact measurement conditions."""
    if not path.exists():
        raise SystemExit(f"Error: {path} missing — every scored run must cite a measurement card")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description="EM + char-F1 for the 400-question reading eval.")
    ap.add_argument("--answers", type=Path, default=None,
                    help="reading_answers_<model>.csv (default: newest in all_res/ollama_result/)")
    ap.add_argument("--gold", type=Path, default=GOLD_DEFAULT)
    ap.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    args = ap.parse_args()

    setup_logging(Path("logs") / "score_reading_eval.log")

    answers_path = args.answers
    if answers_path is None:
        candidates = sorted(RESULTS_DIR.glob("reading_answers_*.csv"))
        if not candidates:
            raise SystemExit(f"Error: no reading_answers_*.csv in {RESULTS_DIR}")
        answers_path = candidates[-1]
    if not answers_path.exists():
        raise SystemExit(f"Error: answers file not found: {answers_path}")
    if not args.gold.exists():
        raise SystemExit(f"Error: gold file not found: {args.gold}")

    gold = {(r["dataset"], str(r["item_id"])): r["gold_answer"] for r in read_csv_rows(args.gold)}
    answers = read_csv_rows(answers_path)

    missing = [item_key(r) for r in answers if (r["dataset"], str(r["item_id"])) not in gold]
    if missing:
        raise SystemExit(f"Error: {len(missing)} answer rows have no gold, e.g. {missing[:5]}")
    unknown = sorted(set(gold) - {(r["dataset"], str(r["item_id"])) for r in answers})
    if unknown:
        raise SystemExit(f"Error: {len(unknown)} gold rows have no answer, e.g. {unknown[:5]}")

    model_slug = answers_path.stem.removeprefix("reading_answers_")
    card_hash = measurement_card_hash()
    rows = []
    for r in answers:
        key = (r["dataset"], str(r["item_id"]))
        pred, f1, em, exact_raw = score_pair(r.get("raw_response", ""), gold[key])
        rows.append({
            "dataset": key[0], "item_id": key[1],
            "stratum": r.get("stratum", ""),
            "gold_answer": gold[key],
            "raw_response": r.get("raw_response", ""),
            "prediction": pred,
            "em": int(em),
            "f1": f"{f1:.6f}",
            "exact_raw": int(exact_raw),
        })

    scores_path = args.out_dir / f"reading_scores_{model_slug}.csv"
    write_csv_atomic(scores_path, rows, SCORE_COLS)

    # --- summary, per source and overall -------------------------------------
    summary = []
    groups: list[tuple[str, list[dict]]] = [(ds, [r for r in rows if r["dataset"] == ds])
                                            for ds in ("squad", "drop")]
    groups.append(("ALL", rows))
    for ds, sub in groups:
        n = len(sub)
        if not n:
            continue
        em_rate = sum(r["em"] for r in sub) / n * 100
        f1_mean = sum(float(r["f1"]) for r in sub) / n * 100
        summary.append({
            "dataset": ds,
            "n": n,
            "em_count": sum(r["em"] for r in sub),
            "em": f"{em_rate:.2f}",
            "char_f1": f"{f1_mean:.2f}",
            "exact_raw_count": sum(r["exact_raw"] for r in sub),
            "measurement_card_hash": card_hash,
        })

    summary_path = args.out_dir / f"reading_summary_{model_slug}.csv"
    write_csv_atomic(summary_path, summary, ["dataset", "n", "em_count", "em", "char_f1",
                                             "exact_raw_count",
                                             "measurement_card_hash"])

    logging.info("Scored %d items from %s", len(rows), answers_path)
    logging.info("measurement_card_hash=%s", card_hash)
    for s in summary:
        logging.info("  %-6s n=%-4s EM=%-6s char-F1=%-6s (exact-raw %s)",
                     s["dataset"], s["n"], s["em"], s["char_f1"], s["exact_raw_count"])
    logging.info("Wrote %s and %s", scores_path, summary_path)


if __name__ == "__main__":
    main()
