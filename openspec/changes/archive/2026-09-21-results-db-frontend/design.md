## Context

See proposal.md (Why). Current verified state:

- Results live as gitignored per-model CSVs under `all_res/ollama_result/<dir_slug>/` (finals: `full_evaluation_*.csv` + `accuracy_*.csv` for MC/legal/NLI; `reading_answers_*` + `reading_scores_*` + `reading_summary_*` for reading/BidLQA; `vbench_full_evaluation_*` + `vbench_valid_summary_*` + `vbench_server_scores_*` for V-Bench) plus tracked manifests in `data/` (`eval_set_manifest.csv`, `bidlqa_{val,test}_manifest.csv`, `legal_nli_manifest.json`, `legal_slm_multichoice_manifest.json`) and the single-model blob `web/public/benchmark-data.json` (keys `model_info|vmlu|vbench|reading|legal|legal_nli|bidlqa`).
- Filename identity is messy: `sanitize_model` (case-preserving, `[^a-zA-Z0-9_-]` → `_`) names dirs/files (`Qwen3_5-9B-28K`, `qwen38-nothink`, `Qwen3_8-27B-Q4_K_M_gguf`), while `web/lib/slug.ts` (lowercase + NFD-strip + `[^a-z0-9]+` → `_`) names review buckets. Neither is URL-clean nor stable across spellings (`Qwen3.5-9B-28K` vs `Qwen3_5-9B-28K`).
- Mongo `vmlu-mongo` runs at `mongodb://127.0.0.1:27017/`, ping OK via `docker exec ... mongosh`. No `pymongo` in `.venv` yet, no `mongodb` dep in `web/` yet. Existing web seams: `web/lib/blob.ts` (file-blob read), `web/app/api/{blob,export,records,reviews,state}` (review pass, untouched).
- Contracts frozen: `build_prompt`/`extract_answer`, `build_reading_prompt`, EM/char-F1 math, `REVIEW_COLS`, `SCHEMA_VERSION`, both slug rules. Runners/scorers/builders are read-only inputs to this change.

## Goals / Non-Goals

**Goals:** every result CSV gets a durable home with proper identity (one canonical id per model, one id per dataset, both stamped on every run/item); one idempotent migration with row-count + identity gates; read-only API (`models`, `datasets`, `runs`, `summary`, `items`); a DB-backed frontend view (model selector → dataset selector → run → item, plus ≥2-model compare) verified row-for-row against the blob before the old path retires.

**Non-Goals:** new inference, condition changes, scorer rewrites, auth, remote Atlas, blob-schema reshaping, review-pass changes.

## Decisions

**D1. Canonical `model_id` rule (one id per model).** New rule, pinned here: `model_id = lower(NFD-strip(sanitize_model(model)))` with `[^a-z0-9]+ → '-'`, trimmed — i.e. lowercase, hyphen-joined, URL-safe. Examples: `Qwen3.5-9B-28K` → `qwen3-5-9b-28k`; `qwen38-nothink` → `qwen38-nothink`; `Qwen3_8-27B-Q4_K_M_gguf` → `qwen3-8-27b-q4-k-m-gguf`. The `models` registry (`_id` = `model_id`) keeps `dir_slugs[]` (every observed CSV dir spelling) + `endpoint_ids[]` so old filenames resolve to exactly one id. Rationale: hyphens read better in URLs than the review slug's underscores, and one rule absorbs all current + future spelling variants.

**D2. `dataset_id` per evaluated set (one id per dataset).** Fixed vocabulary (no free text): `vmlu-mqa-valid` (744), `vmlu-mqa-dev` (303), `vmlu-mqa-all-gold` (1047), `vmlu-mqa-test` (9833, withheld gold), `vbench-public-test` (5141), `reading-400`, `legal-mc-146`, `legal-nli-150`, `bidlqa-val` (482), `bidlqa-test` (603). The `datasets` registry carries `benchmark/split/n/source_file/source_sha256/gold_kind/manifest_path`. V-Bench tracks (`mc`/`agentic`) stay a per-item field, not separate datasets; reading keeps its `squad`/`drop` source field per item.

**D3. Composite `run_id` = `{model_id}__{dataset_id}__{card_id}`** (e.g. `qwen3-5-9b-28k__bidlqa-val__mc-12`). Human-readable, unique across re-runs, and directly cites the measurement card. A rerun = new card = new run document; old runs are never overwritten.

**D4. Items denormalize both ids.** Every document in `mc_items`/`reading_items`/`vbench_items` carries `run_id` + `model_id` + `dataset_id` (unique index on `(run_id, item_id)`). This is a deliberate, documented duplication: the read pattern is key-lookup without joins, and a missing id fails the migration gate (spec: Migration verification).

**D5. Migration is a deep Module behind one command.** Module `migrate_results_to_mongo` — Interface: `migrate_results_to_mongo.py [--uri ...] [--db vmlu] [--drop] [--only <model_id>]` → exit 0 + row-count report, or non-zero naming the offending file/count. Implementation (hidden behind the Interface): registry seeding → per-file readers (MC/reading/V-Bench shapes) → upsert runs/items/summaries → verify pass. Idempotent upserts make re-runs safe; `--drop` is opt-in. The Module accepts its Mongo client as a dependency (no hard-constructed client) so unit tests run against a fake/mongomock-style Adapter through the same Seam.

**D6. Web DB access is one deep Module.** Module `web/lib/db.ts` — Interface: `getModels()`, `getDatasets()`, `getRuns(model?, dataset?)`, `getSummary(run_id)`, `getItem(run_id, item_id)` (read-only; never aggregates at read time). One shared client Adapter behind the Seam; route handlers stay thin pass-throughs. Depth test: deleting it must push Mongo plumbing into every route — otherwise it is not earning its keep.

**D7. API routes are thin Adapters over the Module.** `web/app/api/results/{models,datasets,runs,summary,items}` — each validates query params (400 on missing `run`/`item`), returns registry/run/summary/item JSON with `Cache-Control: no-store`, and never touches the file blob. No new review-pass routes; existing `api/{blob,export,records,reviews,state}` untouched.

**D8. Frontend view is model → dataset → run → item.** New route (e.g. `web/app/results/page.tsx`) with a model selector fed by `models`, a dataset selector filtered to datasets that model ran, a summary panel fed by `summaries`, and a per-item lookup. Multi-model compare renders ≥2 runs side by side from the same `dataset_id`. No blob import in the new view.

**D9. Cutover is row-for-row or not at all.** A verify script (or task step) diffs every DB-backed number against `benchmark-data.json` + source CSVs (overall, per-category/subject, EM/F1, baselines, card hashes). The old `/benchmark` blob path stays the default until the diff is empty; cutover = point the page at the API, never a flag-day rewrite.

## Risks / Trade-offs

- [Two slug rules already exist; a third id rule adds confusion] → D1 pins the derivation with examples; registries map old spellings instead of renaming files.
- [`pymongo` + `mongodb` are new deps] → scoped: `uv pip` for migration only (never `requirements.txt`), `web/`-only driver; CI gate unchanged.
- [10k-row V-Bench/VMLU imports are slow without bulk ops] → bulk upserts + `(run_id, item_id)` index built once; verify pass streams counts, not full docs.
- [Local-only Mongo drifts from CI] → migration + API covered by offline unit tests (fake Adapter); live import verified manually against row counts, not in CI.

## Migration Plan

Seed registries → import Qwen3.5 finals first (MC-7..MC-13) → import `qwen38-nothink` + `Qwen3_8-27B-Q4_K_M_gguf` for compare → verify row-for-row vs blob → build API → build view → cutover check. Rollback = drop `vmlu` db + revert view route; CSVs + blob remain source of truth throughout.

## Open Questions

- None blocking: model-id hyphen rule (D1) vs reusing the review underscore slug — default is hyphens per D1; flag now if underscores are preferred, before migration writes ids.
