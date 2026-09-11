"""VMLU benchmark evaluation toolkit (code_benchmark).

Layout:
  * run_mc_eval.py       — multiple-choice VMLU runner (frozen A-E contract)
  * run_reading_eval.py  — 400-item reading-comprehension runner
  * make_eval_sample.py  — stratified eval-set sampler (pre-registration)
  * export_annotation_workbooks.py — blind gold workbooks + review merges
  * build_review_ui.py   — review-pass join -> static HTML fallback / Next blob
  * common.py / llm.py / checkpoint.py — shared kernel (stdlib-only `common`)
  * legacy/              — frozen history, never linted or imported
"""
