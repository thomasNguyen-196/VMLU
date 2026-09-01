# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repo supports a research study on **small open-weight LLMs (≤8B) for Vietnamese** (see `PROPOSAL.md`). Two related halves:

1. **Benchmark tooling** (`code_benchmark/`): evaluates models against **VMLU** — a Vietnamese multitask benchmark of 58 subjects / 10,880 multiple-choice questions (downloadable from [vmlu.ai](https://vmlu.ai); on disk the data sits in gitignored folders like `vmlu/test.jsonl` or `vmlu_mqa_v1.5/`, see Datasets below). The current pipeline runs via Ollama / any OpenAI-compatible endpoint.
2. **Research proposal** (`PROPOSAL.md`): this study is "Stage 0" — establishing a capability–efficiency baseline (VMLU + V-Bench, VialectBench, ViGLUE) across a 10-model matrix (Qwen3 0.6B–8B, Gemma-3, Llama-3.2, Phi-4-mini, BloomVN) under three regimes: **A** (BF16, no quantization, official chat template), **B** (INT4/AWQ/GGUF edge), **C** (reasoning-token budgets 128/512/2048 for thinking models).

Doc languages vary by file: `README.md`, `AGENTS.md`, `PROPOSAL.md` are in English; `PLAN.md` and `REVIEW.md` (a completed, resolved record of the Ollama migration) are in Vietnamese.

## Commands

**Interpreter**: use `.venv/bin/python` (uv-managed, Python 3.12, has `openai`/`pandas`/`python-dotenv`/`tqdm` installed). System `python3` is 3.14 with **no deps** — `test_ollama.py` and `test_suite.py` fail on import there. The only thing that runs on system `python3` is `test_parsing.py` (deliberately dependency-free). The venv has **no pip** — install with `uv pip install -r requirements.txt --python .venv/bin/python` (`uv` is on PATH).

All `code_benchmark/` scripts are run **from the repo root or `code_benchmark/`**.

```bash
# 1. Environment: copy and fill in .env
cp .env.example .env
# OPENAI_BASE_URL must point at the /v1 path of the Ollama/OpenAI-compatible
# gateway (e.g. http://localhost:11434/v1); OPENAI_API_KEY may be a dummy
# string like "ollama"; OPENAI_MODEL is the model tag to evaluate.

# 2. Run the benchmark (working dir can be repo root or code_benchmark/)
.venv/bin/python code_benchmark/test_ollama.py --folder "./vmlu" --workers 4
# Quick sanity run:  --limit 20 --workers 4
# Useful knobs: --file <jsonl name>, --temperature (default 0.0), --seed 42,
#               --max-tokens (default 4 — raise it for regime C / thinking models)
# Resume after interruption:  --resume   (auto-picks newest raw_result_*.csv)

# 3. Build the 400-question reading-comprehension eval manifest (issue #3)
.venv/bin/python code_benchmark/make_eval_sample.py   # -> eval_set_manifest.csv (200 SQuAD + 200 DROP, seed 42)
# Stdlib-only (runs on system python3 too). DROP: proportional by primary category
# with `count` pinned to 40 (oversample). SQuAD: context-length x direct/infer cells,
# *-infer pinned to 5 each, max PASSAGE_CAP questions per passage. gold_answer ships
# EMPTY — filled by the 2-annotator pass. The committed CSV is the pre-registration.

# 4. Annotate / review the eval set (issue #3)
.venv/bin/python code_benchmark/export_annotation_workbooks.py build     # -> annotation_workbooks/annotator_{A,B}.csv (blind, context embedded)
.venv/bin/python code_benchmark/export_annotation_workbooks.py merge     # compare the 2 filled books -> gold_agreed/adjudication (+ --apply)
# PRIMARY review tool = the Next.js app in web/ (localhost, state autosaved to disk):
.venv/bin/python code_benchmark/build_review_ui.py export-blob           # -> web/data/review-blob.json (the validated workbook×answers join)
cd web && npm install && npm run dev                                     # -> http://localhost:3000 (state -> review_state/*.json)
# OFFLINE fallback = one self-contained HTML (localStorage only, works from file://, no network — email it to a reviewer):
.venv/bin/python code_benchmark/build_review_ui.py build                 # -> review_ui.html
# Both modes share the 9-column review CSV + the {schema_version:1,annotator,model,saved_at,items} state
# envelope. Whichever produced the CSV, the merge step is the same:
.venv/bin/python code_benchmark/export_annotation_workbooks.py review --a review_A.csv --b review_B.csv   # acceptance% + IAA + gold (accept -> model answer, reject -> correction); --apply fills manifest
# review is the REVIEW pass (answers visible); merge is the BLIND gold pass — two pipelines, do not cross-apply.
# SPLIT THE 400 between 2 reviewers (each item reviewed ONCE, disjoint shares):
# Export CSV in the web app ALSO publishes it to review_records/*.csv (TRACKED — the shared
# work log). At startup the app reads every peer CSV there and locks those items read-only
# (hatched filmstrip cells; `t` skips them), so nobody reviews the same item twice. Flow:
# reviewer 1 reviews -> Export CSV -> git commit+push review_records/ -> reviewer 2 pulls,
# sees 1's items locked, reviews the rest -> exports+pushes. Final gold = UNION of records:
.venv/bin/python code_benchmark/export_annotation_workbooks.py merge-split review_records/*.csv   # union accept/reject -> gold (reject needs correction); disagreements -> adjudication; --apply fills manifest

# 5. Tests
.venv/bin/python code_benchmark/test_parsing.py   # standalone parity tests (also works on system python3)
.venv/bin/python -m unittest code_benchmark.test_suite   # run from REPO ROOT: imports `code_benchmark.test_ollama` as a package

# 6. Legacy scripts (historical only, need a venv pinned to openai==0.28.0)
cd code_benchmark && GPT_KEY="<KEY>" python3 legacy/test_gpt.py
cd code_benchmark && python3 legacy/test_prompt.py --llm "bigscience/bloom-1b7" --folder "./vmlu_v1.5/" --device "cuda"
```

## Datasets on disk

`vmlu_datasets.zip` (3.5 MB, untracked) unpacks into four gitignored folders at repo root, and **only one is directly consumable by `test_ollama.py`**:

- `vmlu_mqa_v1.5/` — the classic MC format (`{id, question, choices[], answer}` JSONL): `test.jsonl` has all 10,880 questions, plus `dev.jsonl` (303) / `valid.jsonl` (744). Works with `--folder ./vmlu_mqa_v1.5 --file test.jsonl`.
- `vmlu_drop_v1/`, `vmlu_squad_v1/`, `vmlu_dialog_v1/` — **"question_only" JSON** (one big `{__count__, data[]}` object; keys like `question_id/category/context/question`, `queries`), **no `choices`/`answer` fields** → the `test_ollama.py` loader will not accept them. They are for human/leaderboard-submission evaluation flows, not the MC pipeline.

## Evaluation pipeline (`code_benchmark/test_ollama.py`)

A single self-contained script, best understood as a pipeline:

1. **Config** — env vars (`OPENAI_BASE_URL`/`OPENAI_API_KEY`/`OPENAI_MODEL`) with CLI overrides (`--base-url`, `--api-key`, `--model`); missing base URL or model → clear error + `sys.exit(1)`. `--limit` must be a positive integer.
2. **Fail-fast credential probe** — `verify_credentials()` sends a 1-token "ping" at startup; any failure exits before the workload starts.
3. **Load** — reads `test.jsonl` (name overridable via `--file`) as `{id, question, choices[], answer}` per line from `--folder`; falls back to `../<folder>`; empty file → exit 1. Choices may be 4 or 5 options.
4. **Prompt** — `build_prompt()` wraps the question + choices in a Vietnamese instruction asking for only the answer letter, ending `"Đáp án: "`. This string is a **contract with the legacy scripts** — keep it byte-identical.
5. **Inference** — `call_model_with_retry()`: retries generic errors up to 30×30s, but **never retries** `AuthenticationError`/`PermissionDeniedError`/401/403 (re-raised to fail fast); returns `""` on exhaustion.
6. **Parsing** — `extract_answer()`: 4-tier regex (exact letter → Vietnamese/English key phrases → standalone upper/lowercase letter). Always returns **uppercase A–E** to match the official submission format; returns `""` when no answer is found.
7. **Concurrency & checkpointing** — `ThreadPoolExecutor(--workers)`; results indexed by original order; every 100 completions a thread-safe (lock) snapshot is written to `all_res/ollama_result/raw_result_<N>.csv`. `--resume` loads the checkpoint with the largest numeric suffix (see `find_latest_checkpoint()`) and skips already-answered ids.
8. **Auto-scoring (gold inputs only)** — if EVERY loaded record has a non-empty `answer` (dev.jsonl/valid.jsonl), `detect_scorable()` enables scoring: end-of-run, `score_row()` adds `gold_answer` + `correct` columns (case-insensitive letter match; unparseable model answer = incorrect, still counted) and `build_accuracy_rows()` writes `all_res/ollama_result/accuracy_<model>.csv` (long format `level,name,n,correct,accuracy`: overall + per-category + per-subject) and logs overall % + category table. Mixed gold/no-gold input → warning + non-scorable. Inputs without gold (test.jsonl) keep the exact old behavior — scoring is computed from merged results so pre-scoring checkpoints remain resumable. Subject→category mapping lives in the `SUBJECTS` dict keyed by `id` prefix using the **official VMLU README numbering** — deliberately NOT `dataset_stat.csv`, whose ordering differs.
9. **Outputs** (all gitignored): `all_res/ollama_result/full_evaluation_<model>.csv` (full results incl. raw responses, + the two scoring columns on gold inputs), `logs/<sanitized_model>.log`, and `submission.csv` — the final `id,answer` CSV written to the current working directory (identical schema in both modes).

### Key invariants & gotchas

- **Submission answers must be uppercase `{A,B,C,D,E,''}`** — matches `example_submission.csv` and the vmlu.ai submission portal. Answers are uppercased in `extract_answer`.
- `extract_answer` uses unicode word boundaries (`(?<!\w)([A-E])(?!\w)`) so Vietnamese words containing ASCII letters (e.g. `các`, `bói`) are never misread as options.
- `test_parsing.py` deliberately **duplicates** `extract_answer`/`build_prompt` rather than importing them — it is the standalone parity reference. `test_suite.py` imports from the package and must run from the repo root.
- The 30×30s retry cadence (15 min/case) is the default; auth errors are excluded from it deliberately — don't "fix" the retry loop back into touching auth errors.
- Data/output paths gitignored: `vmlu/`, `all_res/`, `logs/`, `submission.csv`, `leaderboard.json`, `vmlu_v*`, `review_state/` (the review server's per-reviewer×model working buckets — private, never shared). The **`review_records/*.csv`** published-export folder and **`web/data/review-blob.json`** (the shared items+answers snapshot, so every reviewer's app serves the identical eval) are the durable, TRACKED records (root-level `review_*.csv`/`state_*.json`/`review_ui.html` are still gitignored via anchored `/*` patterns — keep those two un-ignored). `.env*` ignored except `.env.example`/templates — keep it that way.
- `requirements.txt` is a **frozen env snapshot** and contains heavy leftovers (`torch==2.1.2`, `nvidia-*`, `transformers`). The only packages `test_ollama.py` actually needs are `openai>=1.0.0`, `python-dotenv>=1.0.0`, `pandas`, `tqdm`. The pinned GPU stack only matters for `legacy/test_prompt.py`.
- Legacy scripts read old data paths (`vmlu_v2/`, `vmlu_v1.5/`) relative to `code_benchmark/`; `test_gpt.py` needs a venv with `openai==0.28.0` and the `GPT_KEY` env var.

## CI (light syntax + security review)

`.github/workflows/ci.yml` gates PRs and pushes to `main` with two jobs (pattern mirrors `../AI-Image`):

1. **python-static** — `ruff check .` (rules `F,B,E9` = syntax/logic/bugbear only, no style rules; config in `ruff.toml`) + `bandit -r code_benchmark -c .bandit.yml -q` (security; `B101` skipped for test asserts, `B311` skipped — `random.Random` there is reproducible-sampling only, never crypto; `code_benchmark/legacy/` excluded as historical research records).
2. **tests** — `test_parsing.py` (parity contract) + `python -m unittest code_benchmark.test_suite`.

Reproduce the gate locally before pushing:

```bash
uvx ruff@0.16.1 check .                                          # versions pinned in ci.yml
uvx --from bandit bandit -r code_benchmark -c .bandit.yml -q
.venv/bin/python code_benchmark/test_parsing.py
.venv/bin/python -m unittest code_benchmark.test_suite
```

The gate deliberately does **not** run `test_ollama.py` (needs a live endpoint/models) and never lints `legacy/` (frozen `openai==0.28.0` scripts — their unused imports document the original research setup).

## Agent skills

`.claude/skills/` hosts the engineering skill set reused from `../AI-Image` (23 general skills: `/review-and-fix`, `/max-effort-code-audit`, `/diagnosing-bugs`, `/grilling`, `/domain-modeling`, `/codebase-design`, `/tdd`, `/prototype`, `/triage`, `/to-spec`, `/to-tickets`, `/handoff`, `/teach`, `/ask-matt`, `/writing-for-agents`, `/improve-codebase-architecture`, `/grill-with-docs`, `/setup-matt-pocock-skills`, + the 5 openspec ones below). Repo config for them:

### Issue tracker

Issues and specs live as GitHub Issues on `thomasNguyen-196/VMLU`, driven by the `gh` CLI (logged in as `nttung245`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) — labels must be created once in the GitHub repo before `/triage` can apply them. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root, created lazily by `/domain-modeling`. See `docs/agents/domain.md`.

Also imported from AI-Image: the 5 `openspec-*` skills + `/opsx:*` commands (propose/explore/apply/archive/sync). `openspec` CLI (bun-global, v1.10.0) was run with `openspec init --tools none`; scaffold lives in `openspec/` (`config.yaml` carries project context + artifact rules, `changes/` + `specs/` start empty). Not imported by design: the 8 frontend/imagegen design skills (web-app specific).

## Code intelligence

- The repo has `.codegraph/` (index is gitignored; rebuild with `codegraph init`): use **CodeGraph before grep/find/Read** when locating or understanding code. `codegraph_explore` (MCP) or `codegraph explore "<symbols or question>"` returns verbatim source plus call paths and blast radius; the daemon auto-syncs file changes. Code intelligence order: **CodeGraph first → context-mode** (`ctx_search`/`ctx_execute` for indexed content and large-output processing) **→ grep/read/glob last** (configs, docs, dataset files, or confirming one small detail only).
- For symbol renames, prefer an IDE-aware refactor or CodeGraph call-site review (`codegraph callers`/`codegraph impact`) over naive find-and-replace — `extract_answer`/`build_prompt` have deliberately duplicated copies in the test scripts that grep-based renames will silently miss.