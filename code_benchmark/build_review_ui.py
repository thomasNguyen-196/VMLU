"""Data + fallback layer of the human-acceptance review pass (issue #3 step 2).

Joins two sources through ONE fail-fast code path (openspec revamp-review-ui):

  * annotation_workbooks/annotator_A.csv  -> static columns + embedded context,
    kept in workbook order (passage-contiguous: read once, answer many). Its
    gold_answer/note are EMPTY at this stage and intentionally NOT embedded —
    this is the review pass (model answers visible by design); the blind gold
    pass stays a separate pipeline.
  * reading_answers_<model>.csv (repeatable) -> {model: raw_answer} per item,
    joined on dataset:item_id.

Two outputs from the same validated join:

  build        -> review_ui.html: self-contained STATIC FALLBACK (localStorage,
                  works from file:// with no network) for a reviewer without a
                  dev environment.
  export-blob  -> web/data/review-blob.json: the item blob consumed by the
                  PRIMARY tool, the Next.js app in `web/` (state autosaved to
                  disk via its API routes; see web/ and the change design).

Review CSVs from either tool are merged by `export_annotation_workbooks.py
review`; the state envelope {schema_version:1, annotator, model, saved_at,
items:{key:{d,c,n}}} is shared across both (and with the pre-redesign UI).

Run from repo root:
  .venv/bin/python code_benchmark/build_review_ui.py build
  .venv/bin/python code_benchmark/build_review_ui.py export-blob
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


def validated_blob(args) -> dict:
    """Shared fail-fast join for both `build` and `export-blob` (the whole point
    of the two-command split: the Next app never re-implements column,
    duplicate-key, unknown-key, or coverage validation)."""
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
    return build_blob(book_rows, answers, created=date.today().isoformat())


def main():
    ap = argparse.ArgumentParser(description="Review-pass data + fallback (issue #3 / revamp-review-ui).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = {
        "--workbook": dict(type=Path, default=Path("annotation_workbooks/annotator_A.csv")),
        "--answers": dict(type=Path, action="append", default=None,
                          help=f"{ANSWER_PREFIX}<model>.csv (repeatable; default: every match under all_res/ollama_result/)"),
        "--allow-partial": dict(action="store_true",
                                help="permit model coverage < 400 items (default: fail — silent gaps skew acceptance %)"),
    }
    bp = sub.add_parser("build", help="self-contained static fallback review_ui.html (offline, localStorage)")
    for flag, kw in common.items():
        bp.add_argument(flag, **kw)
    bp.add_argument("--template", type=Path, default=Path("code_benchmark/review_ui_template.html"))
    bp.add_argument("--out", type=Path, default=Path("review_ui.html"))
    ep = sub.add_parser("export-blob", help="emit web/data/review-blob.json for the Next.js app in web/")
    for flag, kw in common.items():
        ep.add_argument(flag, **kw)
    ep.add_argument("--out", type=Path, default=Path("web/data/review-blob.json"))
    args = ap.parse_args()

    blob = validated_blob(args)

    if args.cmd == "export-blob":
        # atomic-ish: the app refuses a half-written blob, so write then rename
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(args.out)
        print(f"{args.out}: {len(blob['items'])} items, {len(blob['passages'])} passages | "
              f"models: {', '.join(blob['models'])}")
        print("next:  cd web && npm install && npm run dev   (primary review app)")
    else:
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
