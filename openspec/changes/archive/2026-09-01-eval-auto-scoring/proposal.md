## Why

`test_ollama.py` currently produces model answers but never compares them to ground truth: the `answer` column in its output CSVs is the *model's* parsed answer, and accuracy exists only after submitting to vmlu.ai. For the local eval sets (`dev.jsonl` 303 + `valid.jsonl` 744 = 1,047 questions, all with gold `answer`), we need immediate self-scoring to establish the Vi-MQA baseline — used as the pretraining-coverage probe for the ≤8B model matrix and as the negative control arm of the reading-comprehension tool evaluation.

## What Changes

- `test_ollama.py`: detect at load time whether input records carry a gold `answer` field.
  - Gold present (dev/valid): after inference, compare model answer vs gold; add `gold_answer` and `correct` (0/1) columns to `full_evaluation_<model>.csv`; print and persist a summary of accuracy — overall %, per-subject (58 subjects via `id` prefix), per-category (STEM / Humanities / Social Science / Other via the subject→category map).
  - No gold (test): behavior unchanged — `submission.csv` only, no new columns, no summary (leaderboard flow untouched).
- New subject→category mapping (58 subjects → 4 categories, per the official VMLU README numbering) as a shared constant in `test_ollama.py`.
- `--resume` compatibility: checkpoints written before this change lack the new columns; scoring summary is computed from the merged final results, so resuming an old checkpoint still yields correct totals once all rows complete.
- Unit tests for the scorer (comparison, aggregation, missing/unparsed answers) in `test_suite.py`; `test_parsing.py` parity contract untouched (`build_prompt`/`extract_answer` byte-identical).

## Capabilities

### New Capabilities

- `eval-scoring`: self-scoring behavior of the benchmark pipeline — gold detection, correctness comparison, accuracy aggregation (overall/subject/category), output schema, and no-gold fallback.

### Modified Capabilities

(none — `openspec/specs/` is empty; this is the repo's first spec)

## Impact

- Code: `code_benchmark/test_ollama.py` (loader, result assembly, new `score_results()` + category map, summary printing), `code_benchmark/test_suite.py` (scorer tests).
- Outputs: `full_evaluation_<model>.csv` gains two columns **only** for gold inputs; `submission.csv` unchanged; new `all_res/ollama_result/accuracy_<model>.csv` for gold runs.
- No new dependencies (pandas already present). No changes to `build_prompt`, `extract_answer`, retry/auth logic, or the CI gate contract.

## Non-goals

- No scoring of `test.jsonl` locally (gold is withheld by design; leaderboard submission remains the only path).
- No per-category model comparisons or regime-C budget analysis — that is results reporting, not pipeline behavior.
- No changes to reading-comprehension datasets (Vi-SQuAD/Vi-DROP gold annotation is a separate future change).
- No deduplication of the deliberately duplicated `extract_answer`/`build_prompt` copies in test scripts.

## Evaluation regime touched

Regime **A** primarily (BF16, official template, `--max-tokens 4` zero/few-shot runs on dev+valid); the scoring logic is regime-agnostic and will also cover regime B/C runs on the same local sets.
