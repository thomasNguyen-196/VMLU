"""Build review_ui.html — the human-acceptance review tool for the 400-item
reading eval set (issue #3 step 2 UI).

Joins three sources into ONE self-contained HTML (Tailwind CDN, HTML-REPORT.md
house pattern, no build step):

  * annotation_workbooks/annotator_A.csv  -> static columns + embedded context,
    kept in workbook order (passage-contiguous: read once, answer many). Its
    gold_answer/note are EMPTY at this stage and intentionally NOT embedded —
    this is the review pass (model answers visible by design); the blind gold
    pass stays a separate pipeline.
  * reading_answers_<model>.csv (repeatable) -> {model: raw_answer} per item,
    joined on dataset:item_id. The first model becomes the embedded default;
    the UI's file-picker loads additional models client-side.

Reviewer state lives in browser localStorage keyed by
(dataset:item_id, annotator, model) and leaves via Export CSV / state JSON —
see review_ui_template.html. Review CSVs are merged by
`export_annotation_workbooks.py review`.

Run from repo root:
  .venv/bin/python code_benchmark/build_review_ui.py build
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.export_annotation_workbooks import key_of
except ImportError:
    from export_annotation_workbooks import key_of

SCHEMA_VERSION = 1
WORKBOOK_COLS = {"passage_key", "dataset", "item_id", "stratum", "question", "context"}
ANSWER_COLS = {"dataset", "item_id", "raw_response"}
ANSWER_PREFIX = "reading_answers_"


def model_from_filename(path: Path) -> str:
    """'reading_answers_Qwen3_8-27B-Q4_K_M_gguf.csv' -> that model tag.
    Sliced between prefix and suffix — never split on '_' (model names contain
    underscores: the sanitized model column in the CSV header path)."""
    name = Path(path).name
    if not (name.startswith(ANSWER_PREFIX) and name.endswith(".csv")):
        raise ValueError(f"{name}: expected {ANSWER_PREFIX}<model>.csv")
    model = name[len(ANSWER_PREFIX):-len(".csv")]
    if not model:
        raise ValueError(f"{name}: empty model name")
    return model


def load_workbook(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"Error: empty workbook {path}")
    missing = WORKBOOK_COLS - set(rows[0])
    if missing:
        raise SystemExit(f"Error: workbook {path} lacks columns: {sorted(missing)}")
    return rows


def load_answers_csv(path: Path) -> tuple[str, dict[str, str]]:
    """-> (model, {dataset:item_id -> raw_response}). Fail-fast: required
    columns, duplicate keys (same id twice = ambiguous join)."""
    model = model_from_filename(path)
    out: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"Error: empty answers CSV {path}")
    missing = ANSWER_COLS - set(rows[0])
    if missing:
        raise SystemExit(f"Error: {path} lacks columns: {sorted(missing)}")
    for r in rows:
        k = key_of(r)
        if k in out:
            raise SystemExit(f"Error: duplicate key {k} in {path}")
        out[k] = str(r["raw_response"]).strip()
    return model, out


def review_items(book_rows: list[dict],
                 answers: dict[str, dict[str, str]]) -> tuple[list[dict], dict[str, str]]:
    """Merge workbook rows with per-model answers. Workbook order is the
    output order (passage-contiguous). Every answer key must exist in the
    workbook — drift means the wrong answers CSV paired with this manifest,
    the same fail-fast contract as join_manifest(). A model missing whole
    coverage is an error; an item a model simply lacks gets None (UI shows
    'n/a'). Returns (items, passages) with contexts deduped by passage_key."""
    valid = {key_of(r) for r in book_rows}
    for model, amap in answers.items():
        unknown = sorted(set(amap) - valid)
        if unknown:
            raise SystemExit(f"Error: answers for model '{model}' contain {len(unknown)} "
                             f"unknown item keys (first: {unknown[0]}) — wrong CSV pairing?")
    passages = {r["passage_key"]: r["context"] for r in book_rows}
    items = []
    for r in book_rows:
        k = key_of(r)
        items.append({"dataset": r["dataset"], "item_id": str(r["item_id"]),
                      "stratum": r["stratum"], "passage_key": r["passage_key"],
                      "question": r["question"],
                      "answers": {m: amap.get(k) for m, amap in answers.items()}})
    return items, passages


def build_blob(book_rows: list[dict], answers: dict[str, dict[str, str]],
               created: str) -> dict:
    items, passages = review_items(book_rows, answers)
    return {"schema_version": SCHEMA_VERSION, "created": created,
            "models": list(answers), "passages": passages, "items": items}


def embed_json(obj: dict) -> str:
    r"""JSON for <script type="application/json"> embedding. `</` -> `<\/` is a
    JSON-escape no-op ("\/" == "/") that still breaks a premature
    </script> close; U+2028/29 are legal JSON but line terminators in JS
    literals — escape defensively. ensure_ascii=False keeps Vietnamese text
    compact."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (s.replace("</", "<\\/")
             .replace(chr(0x2028), "\\u2028")   # JS line terminators: legal in
             .replace(chr(0x2029), "\\u2029"))  # JSON but crash <script> parses


def render_html(template: str, blob_json: str, placeholder: str = '"__VMLU_DATA__"') -> str:
    n = template.count(placeholder)
    if n != 1:
        raise SystemExit(f"Error: template placeholder {placeholder} found {n}x (need 1)")
    return template.replace(placeholder, blob_json)


def default_answers() -> list[Path]:
    return sorted(Path("all_res/ollama_result").glob(f"{ANSWER_PREFIX}*.csv"))


def main():
    ap = argparse.ArgumentParser(description="Build review_ui.html (issue #3 review pass).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    bp = sub.add_parser("build", help="join workbook + answers CSVs into one HTML")
    bp.add_argument("--workbook", type=Path, default=Path("annotation_workbooks/annotator_A.csv"))
    bp.add_argument("--answers", type=Path, action="append", default=None,
                    help=f"{ANSWER_PREFIX}<model>.csv (repeatable; default: every match under all_res/ollama_result/)")
    bp.add_argument("--template", type=Path,
                    default=Path("code_benchmark/review_ui_template.html"))
    bp.add_argument("--out", type=Path, default=Path("review_ui.html"))
    bp.add_argument("--allow-partial", action="store_true",
                    help="permit model coverage < 400 items (default: fail — silent gaps skew acceptance %)")
    args = ap.parse_args()

    paths = args.answers or default_answers()
    if not paths:
        raise SystemExit("Error: no reading_answers_*.csv found; run run_reading_eval.py first")

    answers: dict[str, dict[str, str]] = {}
    for p in paths:
        model, amap = load_answers_csv(p)
        if model in answers:
            raise SystemExit(f"Error: model '{model}' given twice ({p})")
        answers[model] = amap

    book_rows = load_workbook(args.workbook)
    n = len(book_rows)
    if not args.allow_partial:
        for m, amap in answers.items():
            if len(amap) != n:
                raise SystemExit(f"Error: model '{m}' covers {len(amap)}/{n} items; "
                                 "re-run the reader or pass --allow-partial")
    blob = build_blob(book_rows, answers, created=date.today().isoformat())

    template = args.template.read_text(encoding="utf-8")
    html = render_html(template, embed_json(blob))
    args.out.write_text(html, encoding="utf-8")
    print(f"{args.out}: {len(blob['items'])} items, {len(blob['passages'])} passages, "
          f"{len(html)//1024} KB | models: {', '.join(blob['models'])}")
    print("REMINDER: this is the REVIEW pass (model answers visible by design); "
          "the blind 2-annotator gold pass stays separate — do not --apply review golds "
          "into the manifest before it finishes (issue #3).")


if __name__ == "__main__":
    sys.exit(main())
