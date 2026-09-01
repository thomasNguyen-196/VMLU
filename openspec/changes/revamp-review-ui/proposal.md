# Proposal: revamp-review-ui

## Why

The 400-item reading-comprehension review pass (issue #3) is the human-acceptance step that turns model answers into gold, and reviewers will spend hours in `review_ui.html`. The current page buries prev/next at the bottom of the side panel, gives no overview of the 400 decisions, locks all reviewer state in one browser's localStorage (export-file-ping-pong per session), and re-implements the CSV join/export logic in client-side JavaScript that duplicates the Python pipeline. This is the study's critical path to gold data — it deserves an instrument-grade UI and a real separation of concerns.

## What Changes

- **Next.js review app** `web/` (Next 16 + React 19 + Tailwind v4, localhost single-researcher tool — user-directed stack choice; rev 1's stdlib Python backend is superseded): the primary UI is React components, and its logic lives in Next **API route handlers** that (a) read the validated item blob the Python side emits (`build_review_ui.py export-blob` → `web/data/review-blob.json`, so the workbook × answers join and its fail-fast checks stay in Python, never duplicated), (b) persist reviewer state on disk per (reviewer, model) with atomic writes into the same `review_state/*.json` schema the fallback uses, (c) generate the pipeline-compatible review CSV server-side (replacing the client-side exporter), and (d) list existing review buckets so progress is visible without sharing a browser profile.
- **`build_review_ui.py` becomes the data + fallback layer**: a new `export-blob` subcommand emits the validated blob for the Next app; `build` keeps producing the self-contained `review_ui.html` as the zero-install offline fallback (localStorage, works from `file://` with no network).
- **Redesigned review UI** (the Next app is primary; the static template stays the fallback — one design system, two renderings):
  - Persistent bottom **navigation dock**: large Prev/Next buttons, item counter, "next unreviewed" jump — always visible, never buried.
  - Full-width **decision filmstrip**: a 400-cell progress ruler (passage-grouped, dataset-marked, color-coded by decision) that doubles as overview, progress bar, and jump-to navigation. The signature element.
  - An **"exam-instrument" design system**: intentional token palette where color means only decision state, a Vietnamese-first type pairing (Be Vietnam Pro body / Fraunces display / JetBrains Mono for model output). In `web/` the tokens live in Tailwind v4 `@theme` with `next/font` self-hosting the fonts; the static fallback hand-writes the same tokens in CSS so `review_ui.html` works fully offline (`file://`, no internet).
  - Next mode: autosave to disk with a live saved-indicator; static mode: keeps today's localStorage behavior with the same state schema (existing reviewer state and export/import files remain loadable — no `--apply` data loss).
  - Kept: keyboard shortcuts, decision semantics (accept→model answer is gold, reject→correction is gold), export CSV columns byte-compatible with `export_annotation_workbooks.py review`.

## Capabilities

### New Capabilities
- `review-server`: the Next API-route backend for the review pass — item-blob API fed by the Python validator, disk-persisted per-(reviewer, model) state, server-side pipeline-compatible CSV export, bucket listing.
- `review-ui`: reviewer-facing behavior contract — navigation dock, decision filmstrip, offline-capable static build, Next/static dual mode, state-schema continuity, keyboard protocol.

### Modified Capabilities
<!-- eval-scoring is untouched: the review CSV contract consumed by `export_annotation_workbooks.py review` stays byte-identical, and no MC-pipeline behavior changes. -->

## Impact

- **Code**: new `web/` Next.js app (routes: `/api/blob`, `/api/state`, `/api/export`, `/api/reviews`; client island UI); `code_benchmark/build_review_ui.py` grows `export-blob` (and the rev-1 `serve` subcommand is dropped with `review_server.py`); `code_benchmark/review_ui_template.html` is the redesigned static fallback (already Tailwind-free, hand-written CSS). `export_annotation_workbooks.py` and `test_ollama.py`: unchanged.
- **Data contracts**: review CSV export schema unchanged (9 columns); state JSON `schema_version: 1` and `review_state/` file layout shared across Next and static modes, so old localStorage exports still import.
- **Toolchain**: `web/` needs Node (nvm-managed v24 present) + `npm ci`; Python CI (ruff/bandit/unittest) untouched; cross-mode export-equivalence + slug parity tests run Node/bun from the existing unittest suite (skip when absent). New gitignored: `web/data/` (derived blob).
- **Research protocol**: blind-protocol split (this is the REVIEW pass; blind gold pass stays a separate workbook pipeline) is preserved and reinforced in UI copy.

## Non-goals

- No database, no auth/HTTPS, no multi-user sync conflict resolution beyond per-(reviewer, model) file scoping. Next.js is the app framework (user-directed); no *additional* backend framework (Flask/FastAPI/Django) is introduced. This is a single-researcher-machine tool; a shared deployment is out of scope.
- No changes to the inference runner (`run_reading_eval.py`), manifest sampler, or the blind 2-annotator gold merge pipeline.
- No adjudication UI (disagreement resolution stays CSV-driven via `export_annotation_workbooks.py review`).
- No runtime upload of new `reading_answers_<model>.csv` to a live server — adding models stays a build/serve-time step (restart with more `--answers`).
- Regimes: touches none of the A/B/C inference regimes (PROPOSAL.md) — the 400-item reading set and its golds are regime-agnostic evaluation data; only the human review tooling changes.
