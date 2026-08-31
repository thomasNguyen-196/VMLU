"""Annotation workbooks for the 400-item reading eval set (issue #3, step 2).

build: joins eval_set_manifest.csv to the source JSONs and writes two
IDENTICAL, INDEPENDENT workbooks (annotator_A.csv / annotator_B.csv):

  passage_key, dataset, item_id, stratum, question, context, gold_answer, note

* `context` is embedded per row — annotators never touch the raw JSON.
* Rows are sorted (dataset, passage_id, item_id) so questions sharing one
  passage stay adjacent: read the passage once, answer all its questions.
* Model answers are DELIBERATELY absent (blind protocol — seeing the model's
  response anchors the gold annotation and inflates agreement).

merge: reads the two filled workbooks, classifies each item as agreed /
disagreement under a conservative normalization (casefold, whitespace,
trailing punctuation — number formats like "15,00%" vs "15.00%" are NOT
auto-merged), writes gold_agreed.csv + adjudication.csv, and with --apply
fills the agreed values into eval_set_manifest.csv's gold_answer column.
Disagreements stay blank in the manifest until the adjudication pass.

Shares its loaders with run_reading_eval.py (so: run with .venv python, from
the repo root, like the test suite). Local artifacts (annotation_workbooks/,
adjudication.csv, gold_agreed.csv) are gitignored; the FILLED manifest is the
committed record.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.run_reading_eval import index_sources, join_manifest, load_manifest
except ImportError:
    from run_reading_eval import index_sources, join_manifest, load_manifest

WORKBOOK_COLS = ["passage_key", "dataset", "item_id", "stratum", "question",
                 "context", "gold_answer", "note"]


def key_of(row: dict) -> str:
    return f"{row['dataset']}:{row['item_id']}"


def workbook_rows(joined: list[dict]) -> list[dict]:
    """Add passage grouping key and order rows so one passage's questions are
    contiguous (annotator reads each context exactly once)."""
    rows = []
    for r in joined:
        rows.append({
            "passage_key": f"{r['dataset']}:{r['passage_id']}",
            "dataset": r["dataset"], "item_id": str(r["item_id"]),
            "stratum": r["stratum"], "question": r["question"],
            "context": r["context"], "gold_answer": "", "note": "",
        })
    rows.sort(key=lambda r: (r["dataset"], int(r["passage_key"].split(":")[1]),
                             int(r["item_id"])))
    return rows


def normalize_answer(s: str) -> str:
    """Conservative equivalence for agreement: NFKC, casefold, collapsed
    whitespace, trailing sentence punctuation dropped. Decimal/thousand
    separators are left untouched — format variants must reach adjudication."""
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    s = re.sub(r"\s+", " ", s).strip().strip(".;:•")
    return s


def merge_answers(a: dict[str, str], b: dict[str, str]) -> dict:
    """Pure classifier over {item_key: gold_answer} maps from the two books.
    Only items with BOTH answers filled are scored for agreement."""
    both = sorted(k for k in set(a) & set(b) if a[k].strip() and b[k].strip())
    agreed = [(k, a[k].strip()) for k in both if normalize_answer(a[k]) == normalize_answer(b[k])]
    disagreements = [(k, a[k].strip(), b[k].strip()) for k in both
                     if normalize_answer(a[k]) != normalize_answer(b[k])]
    empty = {
        "empty_a": sorted(k for k in set(a) & set(b) if not a[k].strip() and b[k].strip()),
        "empty_b": sorted(k for k in set(a) & set(b) if a[k].strip() and not b[k].strip()),
        "empty_both": sorted(k for k in set(a) & set(b) if not a[k].strip() and not b[k].strip()),
    }
    return {"both": both, "agreed": agreed, "disagreements": disagreements, **empty}


def read_book(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        return {key_of(r): r for r in csv.DictReader(f)}


def cmd_build(args):
    manifest = load_manifest(args.manifest)
    idx = index_sources(args.squad_file, args.drop_file)
    joined = join_manifest(manifest, idx)
    rows = workbook_rows(joined)
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    for name in ("annotator_A.csv", "annotator_B.csv"):
        with open(out / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=WORKBOOK_COLS)
            w.writeheader()
            w.writerows(rows)  # identical seeds; they diverge only via human filling
    n_pass = len({r["passage_key"] for r in rows})
    print(f"wrote 2 workbooks ({len(rows)} rows, {n_pass} passages, "
          f"~{sum(len(r['context']) for r in rows)//len(rows)} chars context/row avg) -> {out}/")
    print("blind protocol: NO model answers in the books; annotators fill gold_answer independently")


def cmd_merge(args):
    a_book, b_book = read_book(args.a), read_book(args.b)
    res = merge_answers({k: r["gold_answer"] for k, r in a_book.items()},
                        {k: r["gold_answer"] for k, r in b_book.items()})
    n_both = len(res["both"])
    if not n_both:
        print("no item has both annotations filled yet — nothing to merge")
        return
    agree = len(res["agreed"])
    print(f"filled both: {n_both}  |  agreed: {agree} ({100*agree/n_both:.1f}%)  "
          f"|  disagreements: {len(res['disagreements'])}")
    for k in ("empty_a", "empty_b", "empty_both"):
        if res[k]:
            print(f"  {k}: {len(res[k])}")

    with open(args.out_agreed, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "item_id", "gold_answer"])
        for k, g in res["agreed"]:
            ds, iid = k.split(":", 1)
            w.writerow([ds, iid, g])
    with open(args.out_adjud, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "item_id", "question", "context", "answer_A", "answer_B"])
        for k, ga, gb in res["disagreements"]:
            ds, iid = k.split(":", 1)
            src = a_book[k]
            w.writerow([ds, iid, src["question"], src["context"], ga, gb])
    print(f"agreed -> {args.out_agreed} | to adjudicate -> {args.out_adjud}")

    if args.apply:
        rows = load_manifest(args.manifest)
        by_key = {key_of(r): r for r in rows}
        filled = 0
        for k, g in res["agreed"]:
            by_key[k]["gold_answer"] = g
            filled += 1
        with open(args.manifest, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["dataset", "item_id", "stratum",
                                              "passage_id", "question", "gold_answer"])
            w.writeheader()
            w.writerows(rows)
        print(f"--apply: manifest updated with {filled} agreed golds "
              f"({len(rows)-sum(1 for r in rows if r['gold_answer'].strip())} rows still empty "
              "until adjudication pass)")


def main():
    ap = argparse.ArgumentParser(description="Build/merge the 400-item gold annotation workbooks.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    bp = sub.add_parser("build", help="write the two blind annotator workbooks")
    bp.add_argument("--manifest", type=Path, default=Path("eval_set_manifest.csv"))
    bp.add_argument("--squad-file", type=Path,
                    default=Path("vmlu_squad_v1/vi_squad_benchmark_question_only.json"))
    bp.add_argument("--drop-file", type=Path,
                    default=Path("vmlu_drop_v1/vi_drop_benchmark_3309_question_only.json"))
    bp.add_argument("--out-dir", type=Path, default=Path("annotation_workbooks"))
    bp.set_defaults(func=cmd_build)

    mp = sub.add_parser("merge", help="compare the two filled workbooks")
    mp.add_argument("--a", type=Path, default=Path("annotation_workbooks/annotator_A.csv"))
    mp.add_argument("--b", type=Path, default=Path("annotation_workbooks/annotator_B.csv"))
    mp.add_argument("--manifest", type=Path, default=Path("eval_set_manifest.csv"))
    mp.add_argument("--out-agreed", type=Path, default=Path("gold_agreed.csv"))
    mp.add_argument("--out-adjud", type=Path, default=Path("adjudication.csv"))
    mp.add_argument("--apply", action="store_true",
                    help="write agreed golds into the manifest (irreversible-ish: git diff shows it)")
    mp.set_defaults(func=cmd_merge)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
