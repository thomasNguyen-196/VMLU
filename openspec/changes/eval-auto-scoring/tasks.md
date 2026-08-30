## 1. Mapping foundation

- [x] 1.1 Add `SUBJECTS: dict[int, tuple[str, str]]` (official VMLU numbering → (name, category)) to `code_benchmark/test_ollama.py`; verify with a unit test in `test_suite.py` asserting 58 entries, category split 21 STEM / 10 Social Science / 18 Humanities / 9 Other, and spot checks (18→STEM intro-programming, 28→Social Science macroeconomics, 39→Humanities civil law, 51→Other clinical pharmacology)
- [x] 1.2 Add pure function `score_results(rows, gold_by_id)` (per-row `gold_answer`/`correct`; empty model answer = incorrect; unknown prefix → `unknown` bucket) and unit tests in `test_suite.py` covering match/mismatch/empty/unknown cases — run from repo root: `.venv/bin/python -m unittest code_benchmark.test_suite`

## 2. Pipeline integration

- [x] 2.1 Detect scorable input in `load_questions` per spec (all-have-gold / none / mixed→warn+non-scorable); verify by loading `dev.jsonl` (scorable), `test.jsonl` (non-scorable) and a synthesized mixed list in a unit test
- [x] 2.2 At end of run, when scorable: call `score_results` over merged results, add `gold_answer`+`correct` columns to `full_evaluation_<model>.csv` rows, write `all_res/ollama_result/accuracy_<model>.csv` (long format: level/name/n/correct/accuracy), print overall + 4-category summary; when non-scorable verify byte-for-byte old output schema (no new columns, no accuracy file)
- [x] 2.3 Confirm resume compatibility: in a unit test, build a pre-scoring-style checkpoint CSV (no new columns), merge with remaining results, score end-of-run, assert totals correct

## 3. Verification

- [x] 3.1 Run the parity contract unchanged: `.venv/bin/python code_benchmark/test_parsing.py` → all PASS (build_prompt/extract_answer untouched)
- [x] 3.2 Smoke run on `valid.jsonl` with `--limit 50 --workers 4 --seed 42` — model + endpoint must be recorded in the run note for reproducibility: current `.env` is `Qwen3.8-27B-Q4_K_M.gguf @ https://llmapi.iec-uit.com/v1` (any OpenAI-compatible server, e.g. local Ollama, acceptable); verify console shows overall % + category table, `accuracy_<model>.csv` exists with category counts summing to 50, `submission.csv` still `id,answer` (result: 42/50 = 84%, all 50 in Social Science as first 50 valid rows are subjects 28+36; schemas confirmed)
- [x] 3.3 CI mirror locally: `uvx ruff@0.16.1 check .` exit 0 and `uvx --from bandit bandit -r code_benchmark -c .bandit.yml -q` exit 0; then push branch and confirm both PR checks pass
- [x] 3.4 Full local scoring run (record model + endpoint as in 3.2): `.venv/bin/python code_benchmark/test_ollama.py --folder ./vmlu_mqa_v1.5 --file valid.jsonl --workers 4` → 744/744 answered, per-subject table covers 58 subjects; spot-check 3 subject rows against `full_evaluation_*.csv` by hand (result @ Qwen3.8-27B-Q4_K_M.gguf @ https://llmapi.iec-uit.com/v1, 182s: overall 540/744 = 72.58%; STEM 78.68 / SocSci 75.57 / Humanity 68.56 / Other 62.50; independent recompute from full_evaluation CSV: 0 mismatches across all 58 subjects, `correct` column fully consistent)

## 4. Docs

- [x] 4.1 Update CLAUDE.md pipeline section (steps 7–8: scoring behavior, new accuracy output, `SUBJECTS` mapping source note incl. the `dataset_stat.csv` ordering trap) — verify wording matches implemented flags/columns
