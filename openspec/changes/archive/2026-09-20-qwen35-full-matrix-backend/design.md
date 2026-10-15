## Context

Current verified state (2026-09-20):

- Model under test: `Qwen3.5-9B-28K` (dot form — the endpoint's live model id;
  `Qwen3_5-9B-28K` 404/502s) via the IEC OpenAI-compatible endpoint
  (`OPENAI_BASE_URL` in `.env`; always pass `--model Qwen3.5-9B-28K` because
  `.env`'s `OPENAI_MODEL` still points at the dead `Qwen3.8-27B-Q4_K_M.gguf`).
  Both spellings sanitize to the same result dir `Qwen3_5-9B-28K/`.
- Done: `full_evaluation_Qwen3_5-9B-28K.csv` (VMLU test, 9,833 valid),
  `vbench_full_evaluation_*` + `vbench_valid_summary_*` (MC 100%/domain,
  agentic 986/1,000), `submission_vmlu_test_*` + `submission_vbench_*` under
  `submissions/Qwen3_5-9B-28K/`.
- Gold: `data/gold/review_gold_agreed.csv` = 400 rows (200 squad + 200 drop),
  key-set equal to `data/eval_set_manifest.csv`; `review_adjudication.csv`
  header-only. Manifest `gold_answer` column still empty.
- Dashboard: `web/public/benchmark-data.json` keys
  `model_info|vmlu|vbench|reading|legal` (single model). Patch scripts:
  `build_dashboard_reading.py` (`.reading`), `build_dashboard_legal.py`
  (`.legal`, recompute-and-refuse). Scorer `score_reading_eval.py` requires
  `measurement_card.md` and writes `reading_scores_*` + `reading_summary_*`.
- V-Bench runner flags: `--resume --retry-unparsed`, `--resume --guided`
  (numbered interview = third elicitation condition), `--submission-only`,
  `--prompt-style minimal|detailed` (one condition per `--model` slug).
- Web API surface already has `web/app/api/{blob,export,records,reviews,state}`.
- Legal sources: `data/legal_slm_multichoice_manifest.json` (146) and
  `v_legal_slsp/legal_slm/{multichoice,nli,syllogism}.jsonl` (146/150/144) +
  `v_legal_slsp/bidlqa/ViBidLQA_test.jsonl` (603). Only multichoice matches the
  MC runner's `{id, question, choices[], answer}` shape.

## Goals / Non-Goals

**Goals:** every dataset Qwen3.5 can run has a full run with model+endpoint
recorded; every gold-bearing set is scored on that gold; the dashboard shows
all of it; all of it lands in a queryable multi-model store.

**Non-Goals:** see proposal (seatau, regime B/C, dialog pipeline, contract
changes, advanced statistics).

## Decisions

**D1. Phase 0 goes through the agreed-gold → manifest `--apply` path, one
commit.** The 400/400 key match is verified; the commit message records the
gold source + row counts. Verify after: 400 non-empty `gold_answer`,
key-set equality re-checked (drift = wrong source, fail fast).

**D2. Reading order is run → score → patch, all full-400, no `--limit`.**
`run_reading_eval.py --model Qwen3.5-9B-28K --workers 4`, then
`score_reading_eval.py` on defaults (newest answers + agreed gold), then
`build_dashboard_reading.py`. Report EM as `em_count` + rate, never the
per-item column; accept-rate stays out of accuracy claims (see scorer
docstring).

**D3. Gold MC sets rerun with identical sampling config** (temperature 0,
seed 42) so accuracy is comparable across sets. Recompute accuracy from
`full_evaluation_*` before trusting `accuracy_*` (same discipline as the
legal dashboard script).

**D4. V-Bench retry is ordered: `--retry-unparsed` before `--guided`.**
Direct re-call fixes truncation/parser drift without changing the elicitation
condition; `--guided` only for leftovers, kept on the same `--model` slug +
`minimal` style, and labeled as the third condition in every report. Target:
`vbench_failures_*` empty/deleted, then `--submission-only` rebuild.

**D5. Legal multichoice rides the frozen MC runner; the other three files get
a format probe first.** Probe keys/shape of nli/syllogism/ViBidLQA_test; if
they differ from `{id, question, choices[], answer}`, write a small adapter —
never widen the runner loader (it must keep rejecting non-MC shapes).
Multichoice + manifest cross-check mirrors `build_dashboard_legal.py`
semantics before any `.legal` patch for Qwen3.5.

**D6. MongoDB over PostgreSQL, served through the existing Next app.**
Rationale: five datasets × three answer shapes (letter / free text / JSON
tool calls) = ragged documents; the read pattern is key-lookup
`(run_id, item_id)` plus precomputed summaries — no JOINs to justify
PostgreSQL, and JSONB would erase its advantage. Collections: `runs`
(model, dataset, condition, config, measurement_card_hash, n, created_at),
`mc_items` / `reading_items` / `vbench_items` (run_id, item_id, answer, gold,
correct/score, raw_response; index on `(run_id, item_id)`), `summaries`
(precomputed accuracy/EM/F1 + per-category/subject rows for direct frontend
reads), `models` (params, quantization, endpoint). One migration script
imports every existing CSV + gold with row-count verification; summaries carry
`measurement_card_hash`. Cutover: new API routes first, dashboard read-path
last; `benchmark-data.json` generation keeps working until then.

**D7. Execution order 0→1→2→3→4 sequential on the IEC endpoint** (no parallel
runs against one gateway); Phase 5 anytime in parallel; Phase 6 last. Every
run note records model + endpoint + commit.

## Risks / Trade-offs

- [Endpoint flakiness mid-run] → per-model checkpoints + `--resume` exist on
  all three runners; phase tasks verify counts before proceeding.
- [Guided answers not comparable to minimal] → D4 labeling; never merged
  silently into minimal aggregates.
- [Legal non-MC formats need bespoke scoring] → probe may shrink Phase 4 to
  multichoice-only with the rest explicitly deferred, not half-built.
- [Blob→DB cutover breaks dashboard] → old blob path stays green until the
  DB-backed view is verified row-for-row.
- [Local gold accuracy ≠ leaderboard] → docs keep calling dev/valid/all_gold
  a local probe, never "the VMLU score".

## Migration Plan

One commit per phase (0–4 runs, 5 backend, 6 submissions record). Rollback =
revert the phase commit; CSVs stay the source of truth until the migration
row-count check passes. No persisted-schema dependency before Phase 5.

## Open Questions

- Scoring metric for ViBidLQA (EM/char-F1 like reading, or its own official
  metric?) — answered by the D5 probe.
- Does the multi-model dashboard compare block on Phase 5, or ship an
  incremental two-model blob first? (Default: block — the blob is
  single-model by construction.)
