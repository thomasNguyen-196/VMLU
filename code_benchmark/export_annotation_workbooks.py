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

review: merges the two Export-CSV files from review_ui.html (build_review_ui).
Semantics chosen with the project owner: accept => the MODEL answer becomes
gold; reject => the reviewer's corrected answer becomes gold. Prints each
reviewer's acceptance % and raw decision agreement (IAA), writes
review_gold_agreed.csv + review_adjudication.csv; --apply fills agreed golds.

  | A      | B      | corrections match? | outcome            | gold            |
  | accept | accept | -                  | agreed             | model answer    |
  | accept | reject | -                  | adjudicate         | blank           |
  | reject | accept | -                  | adjudicate         | blank           |
  | reject | reject | normalize(cA)==cB  | agreed             | A's correction  |
  | reject | reject | differ/blank       | adjudicate         | blank           |
  | unset* | any    | -                  | skipped            | untouched       |

NOTE the two passes are separate pipelines: `merge` consumes BLIND workbooks
(model answer not shown); `review` consumes model-visible review exports.
Running --apply on review outputs is the intended gold source for this project
(the review UI doubles as the gold tool by owner decision); the blind workbook
pipeline remains available if stricter IAA (kappa) is wanted for the thesis.

Shares its loaders with run_reading_eval.py (so: run with .venv python, from
the repo root, like the test suite). Local artifacts (annotation_workbooks/,
adjudication.csv, gold_agreed.csv, review_*.csv, state_*.json) are gitignored;
the FILLED manifest is the committed record.
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
        filled, still = apply_gold(args.manifest, res["agreed"])
        print(f"--apply: manifest updated with {filled} agreed golds "
              f"({still} rows still empty until adjudication pass)")


REVIEW_COLS = ["annotator", "model", "dataset", "item_id", "stratum",
               "decision", "model_answer", "corrected_answer", "note"]


def apply_gold(manifest_path: Path, gold_pairs: list[tuple[str, str]]) -> tuple[int, int]:
    """Write (dataset:item_id -> gold) pairs into the manifest's gold_answer
    column, preserving column order. Shared by `merge --apply` and
    `review --apply`. Returns (filled, still_empty)."""
    rows = load_manifest(manifest_path)
    by_key = {key_of(r): r for r in rows}
    for k, g in gold_pairs:
        if k not in by_key:
            raise SystemExit(f"Error: gold key {k} not in manifest {manifest_path}")
        by_key[k]["gold_answer"] = g
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["dataset", "item_id", "stratum",
                                          "passage_id", "question", "gold_answer"])
        w.writeheader()
        w.writerows(rows)
    return len(gold_pairs), sum(1 for r in rows if not r["gold_answer"].strip())


def read_review(path: Path) -> tuple[dict, dict[str, dict]]:
    """One review_ui.html Export CSV -> (meta, {dataset:item_id -> row}).
    Fail-fast: header mismatch (schema drift), empty file, duplicate keys,
    illegal decision values, mixed annotator/model within one file. A reject
    with blank corrected_answer is NOT an error — it is counted in
    meta["blank_rejects"] and routed to adjudication (missing_correction),
    so a long review session is never un-mergeable. BOM tolerated (utf-8-sig)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        if rdr.fieldnames != REVIEW_COLS:
            raise SystemExit(f"Error: {path} header mismatch — expected exactly {REVIEW_COLS}, "
                             f"got {rdr.fieldnames}")
        rows = list(rdr)
    if not rows:
        raise SystemExit(f"Error: empty review file {path}")
    metas = {(r["annotator"], r["model"]) for r in rows}
    if len(metas) != 1:
        raise SystemExit(f"Error: {path} mixes annotator/model across rows ({metas})")
    annotator, model = metas.pop()
    out: dict[str, dict] = {}
    blank = 0
    for r in rows:
        if r["decision"] not in ("", "accept", "reject"):
            raise SystemExit(f"Error: {path}: illegal decision {r['decision']!r} at "
                             f"{key_of(r)} (hand-edited file?)")
        if r["decision"] == "reject" and not r["corrected_answer"].strip():
            blank += 1
        k = key_of(r)
        if k in out:
            raise SystemExit(f"Error: duplicate key {k} in {path}")
        out[k] = r
    return {"annotator": annotator, "model": model, "n": len(rows),
            "blank_rejects": blank}, out


def gold_from_reviews(a: dict[str, dict], b: dict[str, dict]) -> dict:
    """Pure classifier over the two review maps of the SAME model.
    accept => gold is the model answer; reject+reject with matching
    corrections => gold is A's (stripped) correction; anything else with both
    decisions => adjudication. Unset on either side => skipped (never counted
    into acceptance/IAA denominators of the BOTH view)."""
    both = sorted(set(a) & set(b))
    gold: list[tuple[str, str]] = []
    adjud: list[tuple[str, str, str, str]] = []  # (key, reason, a_val, b_val)
    skipped: list[str] = []
    reviewed_a = reviewed_b = agreed_decisions = 0
    accept_a = accept_b = 0
    for k in both:
        ra, rb = a[k], b[k]
        da, db = ra["decision"], rb["decision"]
        if da == "accept":
            reviewed_a += 1
            accept_a += 1
        elif da == "reject":
            reviewed_a += 1
        if db == "accept":
            reviewed_b += 1
            accept_b += 1
        elif db == "reject":
            reviewed_b += 1
        if not da or not db:
            skipped.append(k)
            continue
        if da == db:
            agreed_decisions += 1
        if da == "accept" and db == "accept":
            ma, mb = ra["model_answer"].strip(), rb["model_answer"].strip()
            if not ma:
                adjud.append((k, "missing_model_answer", ma, mb))
            elif ma != mb:  # same model column must be byte-identical across files
                adjud.append((k, "model_answer_drift", ma, mb))
            else:
                gold.append((k, ma))
        elif da == "accept" and db == "reject":
            adjud.append((k, "accept_vs_reject",
                          ra["model_answer"].strip(), rb["corrected_answer"].strip()))
        elif da == "reject" and db == "accept":
            adjud.append((k, "reject_vs_accept",
                          ra["corrected_answer"].strip(), rb["model_answer"].strip()))
        else:  # both reject
            ca, cb = ra["corrected_answer"].strip(), rb["corrected_answer"].strip()
            if not ca or not cb:
                adjud.append((k, "missing_correction", ca, cb))
            elif normalize_answer(ca) == normalize_answer(cb):
                gold.append((k, ca))  # A's (stripped) correction — they are equivalent
            else:
                adjud.append((k, "corrections_differ", ca, cb))
    return {"both": both, "reviewed_a": reviewed_a, "reviewed_b": reviewed_b,
            "accept_a": accept_a, "accept_b": accept_b,
            "decisions_agreed": agreed_decisions, "gold_agreed": gold,
            "adjudication": adjud, "skipped": skipped}


def review_stats(res: dict, annot_a: str, annot_b: str) -> str:
    """Pure formatter for the console block (testable metric math)."""
    n_both = len(res["both"])
    reviewed_both = n_both - len(res["skipped"])
    pct = lambda c, n: f"{100 * c / n:.1f}%" if n else "—"
    lines = [
        f"items in both files: {n_both}  reviewed_by_both: {reviewed_both}  skipped(unset): {len(res['skipped'])}",
        f"A ({annot_a}): accepted {res['accept_a']}/{res['reviewed_a']} = {pct(res['accept_a'], res['reviewed_a'])} acceptance",
        f"B ({annot_b}): accepted {res['accept_b']}/{res['reviewed_b']} = {pct(res['accept_b'], res['reviewed_b'])} acceptance",
        f"decision agreement on both-reviewed: {res['decisions_agreed']}/{reviewed_both} = "
        f"{pct(res['decisions_agreed'], reviewed_both)} (raw IAA; formal kappa belongs to the reporting pass)",
        f"gold agreed: {len(res['gold_agreed'])}  |  adjudication: {len(res['adjudication'])}",
    ]
    reasons: dict[str, int] = {}
    for _, r, _, _ in res["adjudication"]:
        reasons[r] = reasons.get(r, 0) + 1
    if reasons:
        lines.append("adjudication reasons: " + "  ".join(f"{k}={v}" for k, v in sorted(reasons.items())))
    return "\n".join(lines)


def cmd_review(args):
    meta_a, a = read_review(args.a)
    meta_b, b = read_review(args.b)
    if meta_a["model"] != meta_b["model"]:
        raise SystemExit(f"Error: cross-model merge refused — A reviewed "
                         f"'{meta_a['model']}', B '{meta_b['model']}' (accepted gold is "
                         "the model's own text; mixing models silently corrupts it)")
    if meta_a["annotator"] == meta_b["annotator"]:
        raise SystemExit(f"Error: both files are by '{meta_a['annotator']}' — two "
                         "independent reviewers required (blind protocol)")
    for m, src in ((meta_a, args.a), (meta_b, args.b)):
        if m["blank_rejects"]:
            print(f"warning: {src} has {m['blank_rejects']} reject(s) without corrected "
                  "answer -> routed to adjudication (missing_correction)")

    res = gold_from_reviews(a, b)
    print(review_stats(res, meta_a["annotator"], meta_b["annotator"]))

    # optional context re-join for the adjudication sheet (same source the UI embedded)
    ctx: dict[str, dict] = {}
    if args.workbook and args.workbook.exists():
        ctx = read_book(args.workbook)

    with open(args.out_gold, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "item_id", "gold_answer"])
        for k, g in res["gold_agreed"]:
            w.writerow([*k.split(":", 1), g])
    with open(args.out_adjud, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "item_id", "stratum", "reason", "answer_A", "answer_B",
                    "question", "context"])
        for k, reason, va, vb in res["adjudication"]:
            ds, iid = k.split(":", 1)
            src = a.get(k) or b.get(k) or {}
            wb = ctx.get(k, {})
            w.writerow([ds, iid, src.get("stratum", ""), reason, va, vb,
                        wb.get("question", ""), wb.get("context", "")])
    print(f"agreed gold -> {args.out_gold} | adjudication -> {args.out_adjud}"
          + ("" if ctx else " (adjudication question/context blank: --workbook not found)"))

    if args.apply:
        filled, still = apply_gold(args.manifest, res["gold_agreed"])
        print(f"--apply: manifest got {filled} review-agreed golds; {still} rows still empty")


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

    rp = sub.add_parser("review", help="merge two review_ui.html export CSVs "
                        "(accept -> model answer gold; reject -> correction gold)")
    rp.add_argument("--a", type=Path, required=True)
    rp.add_argument("--b", type=Path, required=True)
    rp.add_argument("--workbook", type=Path, default=Path("annotation_workbooks/annotator_A.csv"),
                    help="enriches review_adjudication.csv rows with question + context")
    rp.add_argument("--manifest", type=Path, default=Path("eval_set_manifest.csv"))
    rp.add_argument("--out-gold", type=Path, default=Path("review_gold_agreed.csv"))
    rp.add_argument("--out-adjud", type=Path, default=Path("review_adjudication.csv"))
    rp.add_argument("--apply", action="store_true",
                    help="write review-agreed golds into the manifest")
    rp.set_defaults(func=cmd_review)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
