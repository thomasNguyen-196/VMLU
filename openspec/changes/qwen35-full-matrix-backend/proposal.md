## Why

Qwen3.5-9B-28K on the IEC endpoint has completed two datasets: VMLU-test MC
(9,833 valid) and V-Bench (MC 100% valid per domain, agentic 986/1,000).
Verified gaps remain before this model counts as "fully evaluated":

- Reading-400 (200 SQuAD + 200 DROP) has a final 400/400 agreed gold
  (`data/gold/review_gold_agreed.csv`, adjudication empty) but **no run** for
  this model — no `reading_*` file under its result dir.
- Gold MC sets (`valid.jsonl` 744 / `dev.jsonl` 303 / `all_gold.jsonl` 1,047)
  were never run on Qwen3.5, so there is no local accuracy to display.
- 14 V-Bench agentic rows sit in `vbench_failures_*.csv`
  (`hallucinated_arg`, `truncated_output`).
- LegalSLM matrix (multichoice 146 + nli 150 + syllogism 144 + ViBidLQA_test
  603) was run on `qwen38-nothink`, never on Qwen3.5.
- Results live as gitignored per-model CSVs plus a single-model
  `web/public/benchmark-data.json` blob — no durable multi-model store.

## What Changes

- **Phase 0** — Fill `gold_answer` in `data/eval_set_manifest.csv` from the
  agreed gold (400/400 keys already match; standalone commit as the
  pre-registration audit trail).
- **Phase 1** — Full 400-question reading run on Qwen3.5 → EM/char-F1 scoring
  on the agreed gold → patch `.reading` into the dashboard blob.
- **Phase 2** — Full MC runs on `valid` / `dev` / `all_gold` (gold → local
  `accuracy_*` for the frontend); rebuild the `test` submission CSV for
  vmlu.ai upload.
- **Phase 3** — V-Bench retry: `--retry-unparsed` first, `--guided` for
  leftovers, `--submission-only` rebuild for vbench.ai upload.
- **Phase 4** — LegalSLM matrix on Qwen3.5: multichoice-146 via the frozen MC
  runner; nli/syllogism/ViBidLQA_test after a format probe (adapter script if
  needed — the runner stays untouched).
- **Phase 5** — MongoDB results backend: `runs` / `mc_items` /
  `reading_items` / `vbench_items` / `summaries` / `models` collections, Next.js
  API routes in `web/`, one-shot CSV migration, dashboard blob becomes a DB
  view with multi-model compare.
- **Phase 6** — Submit: VMLU test CSV → vmlu.ai, V-Bench jsonl → vbench.ai.

## Capabilities

### New Capabilities

- `reading-full`: full 400-question reading run + agreed-gold scoring +
  dashboard patch for one model.
- `mc-gold-matrix`: full MC runs on all gold-bearing sets with accuracy
  artifacts, plus test-submission rebuild.
- `vbench-retry`: ordered retry protocol (direct re-call, then guided
  interview) with condition labeling.
- `legal-matrix`: LegalSLM multichoice via the MC runner plus format-probed
  adapters for the remaining three files.
- `results-backend`: MongoDB store, ingest migration, API routes, DB-backed
  multi-model dashboard.

### Modified Capabilities

(none — additive; prompt/parser/review contracts stay byte-frozen)

## Impact

- Code: new migration script + `web/app/api/*` results routes (+ one DB
  client in `web/lib/`); runners untouched except via their existing CLI flags.
- Outputs: per-model CSVs exactly as today, plus Mongo collections and a
  multi-model dashboard. Python deps unchanged for Phases 0–4; backend adds a
  Mongo driver to `web/` only.
- Docs: `measurement_card.md` entry per new run (the scorer refuses to run
  without it).

## Non-goals

- Seatau telecom excluded (explicit request — no tasks, no schema for it).
- No changes to `build_prompt` / `extract_answer` / `REVIEW_COLS` / `slug()` /
  `SCHEMA_VERSION` — parity tests must stay green throughout.
- No regime B/C work (quantization, reasoning-token budgets) — Regime A only.
- No dialog-dataset (`vmlu_dialog_v1`) pipeline — no runner supports it.
- No bootstrap CIs, confusion matrices, or blind-annotation protocol changes.

## Evaluation regime touched

Regime **A** (official template, temperature 0, seed 42, short answer budgets).
The backend (Phase 5) is regime-agnostic infrastructure.
