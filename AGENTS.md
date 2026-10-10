# Repository Guidelines

## Project Overview

VMLU is a Vietnamese multitask LLM benchmark: 58 subjects, 10,880 MC questions (STEM/Humanities/Social/Other) plus active pre-registered 400-item reading eval (200 Vi-SQuAD + 200 Vi-DROP) and external V-Bench leaderboard arm.

## Architecture & Data Flow

Python eval toolkit (`code_benchmark/` package) + Next.js 16 review/results app (`web/`). Three independent inference pipelines share kernel `common.py` / `llm.py` / `checkpoint.py`, one shared human-review layer.

- **MC (frozen):** `vmlu_mqa_v1.5/*.jsonl` (`id,question,choices[],answer`) → `run_mc_eval.py` prompts OpenAI-compatible endpoint (`ThreadPool`, 30×30s retry) → `all_res/ollama_result/<model>/raw_result_<n>_<slug>.csv` → `full_evaluation_<model>.csv`, `accuracy_<model>.csv`, `submissions/<model>/submission.csv` (`id,answer`).
- **Reading-400:** `make_eval_sample.py` → `data/eval_set_manifest.csv` (gold empty, pre-registered) + source JSONs → `run_reading_eval.py` (open-book Vietnamese prompt) → `reading_result_<n>_<slug>.csv` → `reading_answers_<model>.csv` (free text; EM/char-F1 scored later via `score_reading_eval.py`).
- **V-Bench (external, no local gold):** `v_bench/public-test.jsonl` → `run_vbench_eval.py` `--track mc|agentic` → `vbench_result_<n>_<slug>.csv` → `submissions/<model>/submission_vbench_<model>.jsonl` (server-side scoring at vbench.ai).
- **Harness arm:** `run_harness_eval.py run|compare|speed` replays same items through `omp` coding agent with byte-identical prompts. One condition per `--label` slug.
- **Review/display:** `build_review_ui.py` joins workbook + answers → `review_ui.html` + tracked `web/data/review-blob.json`; `build_dashboard_*.py` patches one key of `web/public/benchmark-data.json` → `web/lib/*.ts` validators → `/harness`, `/benchmark` pages.

Byte-frozen contracts throughout: `build_prompt`/`extract_answer`, `slug()`, `REVIEW_COLS`, `SCHEMA_VERSION=1`, `itemKey=dataset:item_id`. Fail-fast `SystemExit` on drift; never guess.

## Key Directories

- `code_benchmark/` — all pipelines: `run_*` runners, `make_*` samplers/adapters, `score_*` scorers, `build_*`/`export_*` dashboard/review builders, `common.py`/`llm.py`/`checkpoint.py` kernel. `legacy/` is frozen history — leave alone.
- `web/` — Next.js 16 review app: `app/` pages + `app/api/` disk APIs, `lib/` concurrency-free logic + validators, `components/` UI.
- `vmlu_mqa_v1.5/`, `vmlu_squad_v1/`, `vmlu_drop_v1/`, `v_bench/` — gitignored datasets (unpacked from `vmlu_datasets.zip`; V-Bench re-fetchable).
- `data/` — tracked contracts: `eval_set_manifest.csv` (pre-reg 400, never regenerate casually), `example_submission.csv`, `sample_submission.jsonl`; gitignored `data/gold/`.
- `submissions/<model>/`, `all_res/ollama_result/<model>/`, `logs/<model>/` — gitignored per-model outputs (checkpoints + finals + uploadables + logs).
- `annotation_workbooks/`, `review_state/` — gitignored local artifacts; `review_records/` — tracked shared sync log (commit + push to hand over).
- `openspec/specs/` — canonical specs (`eval-scoring/spec.md` authoritative); `docs/`, `docs/agents/`, `measurement_card.md` (MC-n cards), `tools/html2pdf_server.py` (loopback PDF dev service).

## Development Commands

Run from repo root with `.venv/bin/python` (no build step):

```bash
# MC / reading / V-Bench
python code_benchmark/run_mc_eval.py --folder vmlu_mqa_v1.5 --file all_gold.jsonl --workers 4 [--resume]
python code_benchmark/run_reading_eval.py --workers 4 [--resume]
python code_benchmark/run_vbench_eval.py --workers 4 [--resume] [--track mc|agentic] [--submission-only|--retry-unparsed|--guided]

# Harness arm — HOME override MANDATORY, absolute --agent-dir
HOME=/tmp/fakehome python code_benchmark/run_harness_eval.py run --dataset legal_mc --workers 6 \
  --label <slug> --tools none --system-prompt minimal --agent-dir .omp-clean
python code_benchmark/run_harness_eval.py compare --dataset legal_mc --label <slug> --tag vsA
python code_benchmark/run_harness_eval.py speed --dataset legal_mc --label <slug>

# Review / annotation (export-blob after every answers change)
python code_benchmark/build_review_ui.py export-blob
python code_benchmark/build_review_ui.py build
python code_benchmark/export_annotation_workbooks.py build
python code_benchmark/export_annotation_workbooks.py review --a A.csv --b B.csv [--apply]
python code_benchmark/export_annotation_workbooks.py merge-split review_records/*.csv [--apply]

# Lint + tests (CI mirror)
uvx ruff@0.16.1 check .
uvx --from bandit bandit -r code_benchmark -c .bandit.yml -q
python code_benchmark/test_parsing.py
python -m unittest code_benchmark.test_suite  # MUST run from root

# Web (local-only, not CI-gated)
cd web && npm run dev    # 127.0.0.1:3000, blob re-read per request
cd web && bunx tsc --noEmit
cd web && bun test lib/harness-block.test.ts
```

Mongo only for `/benchmark` (`/harness` needs nothing): `docker run -d --name vmlu-mongo -p 27017:27017 -v vmlu-mongo-data:/data/db mongo:7`, then `seed_registries.py && migrate_results_to_mongo.py && verify_results_db.py`.

## Code Conventions & Common Patterns

- **Formatting:** ruff `F,B,E9` only (style E/W/C/I ungated), `target py312`, `line-length 120`; `from __future__ import annotations`; module docstring with WHY + run-from-root example.
- **Naming:** `run_*` runners, `make_*` samplers/adapters, `score_*` scorers, `build_dashboard_*` blob patchers, `test_*` tests; funcs `snake_case` (`build_prompt`, `extract_answer`, `sanitize_model`, `find_latest_checkpoint`); consts `UPPER` (`SUBJECTS`, `REVIEW_COLS`, `SCHEMA_VERSION`, `DROP_PINNED=40`, `PASSAGE_CAP=2`). Per-model `sanitize_model` (`[^a-zA-Z0-9_-]→_`) distinct from reviewer `slug()` (lowercase, NFD-strip, non-alnum→`_`).
- **Error handling:** fail-fast everywhere, e.g. `raise SystemExit(f"Error: duplicate key {k}")`, `read_csv_checked(path, required=...)`, sha256/gold cross-checks. LLM generic errors retry 30×30s, auth probe fail-fast; unparseable answers stay in denominator. Atomic writes via tmp+rename (`write_csv_atomic`). Only documented fail-open: web `parseCsvRows`.
- **Async:** no asyncio — `ThreadPoolExecutor(max_workers=4) + threading.Lock + tqdm`, checkpoints every 100. Local HTTP via `ThreadingHTTPServer` on `127.0.0.1`.
- **DI:** argparse + env: shared `add_endpoint_args()` + `resolve_endpoint()` (flag > env > fail with hint; temp 0.0, seed 42, workers 4). `common.py` stays stdlib-only; dual-import `try: code_benchmark.X except ImportError: X` for root-vs-direct runs. `model_dirs(model)` seam returns `(results, submissions, logs)`.
- **State:** files, not memory — per-model dirs, `StateEnvelope {schema_version, annotator, model, saved_at, items:{key:{d,c,n}}}`, universal `itemKey=dataset:item_id` mirrored in `web/lib/types.ts`. Web: logic in `lib/`, disk in `app/api/`, keyboard `j/k/a/r/u/e/n/t`.

## Important Files

- Entry: `code_benchmark/run_mc_eval.py`, `run_reading_eval.py`, `run_vbench_eval.py`, `run_harness_eval.py`, `make_eval_sample.py`, `export_annotation_workbooks.py`, `build_review_ui.py`, `build_dashboard_harness.py`; web `app/harness/page.tsx`, `lib/harness-block.ts`.
- Config: `ruff.toml`, `.bandit.yml`, `pyrightconfig.json` (scope only, not gated), `.env.example`, `openspec/config.yaml`, `web/package.json`, `web/tsconfig.json`, `web/eslint.config.mjs`, `.github/workflows/ci.yml`.
- Key modules: `code_benchmark/common.py`, `llm.py`, `checkpoint.py`, `review_ui_template.html` (static fallback, JS mirrors `web/lib`); contracts `data/eval_set_manifest.csv`, `web/data/review-blob.json`, `openspec/specs/eval-scoring/spec.md`, `measurement_card.md`.

## Runtime/Tooling Preferences

- **Python 3.12** via uv-managed `.venv` (`.venv/bin/python`; venv has no pip — `uv pip install --python .venv/bin/python`). System `python3` is bare — only stdlib-only `make_eval_sample.py` / `test_parsing.py` run there. Deps: `openai pandas python-dotenv tqdm` only; `requirements.txt` is frozen GPU snapshot — never install wholesale. `common.py` must stay stdlib-only.
- **Node ≥22 or bun** for TS execution only; `npm` in `web/` (`npm install`, `npm run dev/build/start/lint`); `bunx`/`npx` for `tsc --noEmit`, `bun test`. No Dockerfile/Makefile/pyproject; no pinned node file.
- **Env:** `OPENAI_BASE_URL` (must end `/v1`), `OPENAI_API_KEY` (default `ollama`), `OPENAI_MODEL` (CLI flags override; `run_harness_eval.py` ignores it, pins its own). Web overrides `VMLU_REVIEW_BLOB` / `VMLU_REVIEW_STATE_DIR` / `VMLU_REVIEW_RECORDS_DIR`; results browser `VMLU_MONGO_URI` / `VMLU_MONGO_DB`; harness `PI_CODING_AGENT_DIR` (absolute `.omp-*/` path — isolates config, not scaffold; `HOME` override still required). `.env` gitignored, read by legacy runners only.
- **Constraints:** `legacy/` excluded from ruff+bandit; `test_parsing.py` duplication intentional — never dedupe; web dev/start loopback-only, start detached (`setsid nohup npm run dev &`); live-endpoint runners and web build never CI-gated.

## Testing & QA

- **Python `unittest` (stdlib) only** — no pytest/jest/vitest. Main suite `code_benchmark/test_suite.py` (~130 tests/24 classes, tempdirs + MagicMock, offline, root-only package imports) + standalone parity reference `code_benchmark/test_parsing.py` (17 cases, run as script) + `test_score_reading.py` (EM/char-F1). `test_generative*.py` are live-endpoint runners despite `test_` prefix — not CI.
- **Web `bun:test`** (local-only): `web/lib/harness-block.test.ts`, `insights.test.ts`, `results-api.test.ts` (in-memory fake DB, no Mongo); `TestNextContracts` in `test_suite.py` shells to real `web/lib/slug.ts` + `export-csv.ts` (skips without bun/node≥22).
- **Gates (`.github/workflows/ci.yml`, PR+push to `main`):** `ruff check .` + `bandit -r code_benchmark -c .bandit.yml -q` (skips `B101` asserts, `B311` seeded sampling by design) + both Python suites exit 0. **No coverage gate** anywhere; style rules, pyright, web build/typecheck/tests, `openspec validate`, and all live benchmark runs are explicitly not gated.

## Codex Skills

- Project skills are exposed through `.agents/skills/`, with each skill linked to its source under `.claude/skills/`. Invoke one directly with `$skill-name`, or let Codex select it from its description.
- Some source skills name Claude or OpenCode tools and slash commands. Treat those names as workflow intent and use the equivalent Codex capabilities; do not assume tools such as `webfetch`, `Task`, `AskUserQuestion`, or `/opsx:*` exist in Codex.
