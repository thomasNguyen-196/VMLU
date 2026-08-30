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

# 3. Tests
.venv/bin/python code_benchmark/test_parsing.py   # standalone parity tests (also works on system python3)
.venv/bin/python -m unittest code_benchmark.test_suite   # run from REPO ROOT: imports `code_benchmark.test_ollama` as a package

# 4. Legacy scripts (historical only, need a venv pinned to openai==0.28.0)
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
8. **Outputs** (all gitignored): `all_res/ollama_result/full_evaluation_<model>.csv` (full results incl. raw responses), `logs/<sanitized_model>.log`, and `submission.csv` — the final `id,answer` CSV written to the current working directory.

### Key invariants & gotchas

- **Submission answers must be uppercase `{A,B,C,D,E,''}`** — matches `example_submission.csv` and the vmlu.ai submission portal. Answers are uppercased in `extract_answer`.
- `extract_answer` uses unicode word boundaries (`(?<!\w)([A-E])(?!\w)`) so Vietnamese words containing ASCII letters (e.g. `các`, `bói`) are never misread as options.
- `test_parsing.py` deliberately **duplicates** `extract_answer`/`build_prompt` rather than importing them — it is the standalone parity reference. `test_suite.py` imports from the package and must run from the repo root.
- The 30×30s retry cadence (15 min/case) is the default; auth errors are excluded from it deliberately — don't "fix" the retry loop back into touching auth errors.
- Data/output paths gitignored: `vmlu/`, `all_res/`, `logs/`, `submission.csv`, `leaderboard.json`, `vmlu_v*`. `.env*` ignored except `.env.example`/templates — keep it that way.
- `requirements.txt` is a **frozen env snapshot** and contains heavy leftovers (`torch==2.1.2`, `nvidia-*`, `transformers`). The only packages `test_ollama.py` actually needs are `openai>=1.0.0`, `python-dotenv>=1.0.0`, `pandas`, `tqdm`. The pinned GPU stack only matters for `legacy/test_prompt.py`.
- Legacy scripts read old data paths (`vmlu_v2/`, `vmlu_v1.5/`) relative to `code_benchmark/`; `test_gpt.py` needs a venv with `openai==0.28.0` and the `GPT_KEY` env var.

## Code intelligence

- The repo has `.codegraph/` (index is gitignored; rebuild with `codegraph init`): use **CodeGraph before grep/find/Read** when locating or understanding code. `codegraph_explore` (MCP) or `codegraph explore "<symbols or question>"` returns verbatim source plus call paths and blast radius; the daemon auto-syncs file changes. Code intelligence order: **CodeGraph first → context-mode** (`ctx_search`/`ctx_execute` for indexed content and large-output processing) **→ grep/read/glob last** (configs, docs, dataset files, or confirming one small detail only).
- For symbol renames, prefer an IDE-aware refactor or CodeGraph call-site review (`codegraph callers`/`codegraph impact`) over naive find-and-replace — `extract_answer`/`build_prompt` have deliberately duplicated copies in the test scripts that grep-based renames will silently miss.