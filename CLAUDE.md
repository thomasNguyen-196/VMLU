# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repo supports a research study on **small open-weight LLMs (≤8B) for Vietnamese** (see `PROPOSAL.md`) and has grown into a pre-registered benchmarking workbench with three layers:

1. **Benchmark tooling** (`code_benchmark/`): runners, scorers and dashboard builders for several evaluation *arms* — **VMLU** (Vietnamese multitask MC benchmark: 58 subjects / 10,880 questions, from [vmlu.ai](https://vmlu.ai); data sits in gitignored folders, see Datasets), a 400-item reading-comprehension set, V-Bench, legal/BiDLQA/VM14K sets, an `omp` coding-agent "harness" arm and a multi-model Vietnamese suite (see *Evaluation arms*). The MC/reading/V-Bench runners call Ollama or any OpenAI-compatible endpoint; the harness and multi-model arms go through the `omp` agent or provider APIs.
2. **Results/review app** (`web/`): Next.js 16 — the human-review UI for the reading eval plus the dashboards that publish results (see *Web app*).
3. **Research record**: `PROPOSAL.md` is "Stage 0", a capability–efficiency baseline (VMLU + V-Bench, VialectBench, ViGLUE) across a 10-model matrix (Qwen3 0.6B–8B, Gemma-3, Llama-3.2, Phi-4-mini, BloomVN) under three regimes: **A** (BF16, no quantization, official chat template), **B** (INT4/AWQ/GGUF edge), **C** (reasoning-token budgets 128/512/2048 for thinking models). `docs/` holds the metric/thesis plans; `measurement_card.md` + `openspec/` hold the pre-registration trail (see *Pre-registration & provenance*).

Doc languages vary: `README.md`, `AGENTS.md`, `PROPOSAL.md` are English; `measurement_card.md`, `CONTEXT.md`, the web UI strings and many `docs/` files are Vietnamese. `AGENTS.md` is a parallel condensed guide for other agents — if you change a command or contract documented here, check it for the same statement.

## Commands

**Interpreter**: use `.venv/bin/python` (uv-managed, Python 3.12, has `openai`/`pandas`/`python-dotenv`/`tqdm` installed). System `python3` is 3.14 with **no deps** — the runners and `test_suite.py` fail on import there. `make_eval_sample.py` + `test_parsing.py` are the two dependency-free files that run on system `python3` too (they import only `code_benchmark/common.py`, which is stdlib-only by design). The venv has **no pip** — install with `uv pip install -r requirements.txt --python .venv/bin/python` (`uv` is on PATH). The web app uses `npm` for dev/build/lint and `bun` for tests/typecheck.

**Package layout**: `code_benchmark/` is a real package (`__init__.py`). Three extracted seams are shared by the pipelines: `common.py` (stdlib-only kernel: slug, item key, endpoint/logging/argparse, atomic CSV, `model_dirs`), `llm.py` (client + retry + probe), `checkpoint.py` (per-model checkpoint naming/lookup). Most other files are runners (`run_*`, `retry_*`), samplers/adapters (`make_*`), scorers (`score_*`) or builders (`build_*`/`export_*`/`migrate_*`); the rest are domain modules (`vi_multimodel*.py`, `harness_genome.py`, `diagnostic.py`, …). Scripts dual-import (`try: from code_benchmark… except ImportError: …`) so they work from the repo root or from `code_benchmark/`; the newer campaign and `retry_*` scripts document running from the repo root (some as `python -m code_benchmark.<name>`). `code_benchmark/legacy/` stays frozen.

```bash
# 1. Environment: copy and fill in .env (gitignored)
cp .env.example .env
# OPENAI_BASE_URL must point at the /v1 path of the Ollama/OpenAI-compatible gateway
# (e.g. http://localhost:11434/v1); OPENAI_API_KEY may be a dummy string like "ollama";
# OPENAI_MODEL is the model tag to evaluate. The campaign drivers read other keys from the
# same .env (9ROUTER_BASE_URL/9ROUTER_API_KEY, OPENCODE_GO_*, JUDGE_*).

# 2. Run the MC benchmark (working dir can be repo root or code_benchmark/)
.venv/bin/python code_benchmark/run_mc_eval.py --folder ./vmlu_mqa_v1.5 --file all_gold.jsonl --workers 4
# all_gold.jsonl (dev+valid, has gold) is auto-scored; test.jsonl (no gold) only yields a submission
# Quick sanity run:  --limit 20 --workers 4
# Useful knobs: --temperature (default 0.0), --seed 42, --max-tokens (default 4 — raise it for
#               regime C / thinking models)
# Resume after interruption:  --resume   (auto-picks the newest raw_result_*.csv for this model)

# 3. Build the 400-question reading-comprehension eval manifest (issue #3)
.venv/bin/python code_benchmark/make_eval_sample.py   # -> data/eval_set_manifest.csv (200 SQuAD + 200 DROP, seed 42)
# Stdlib-only (runs on system python3 too). DROP: proportional by primary category
# with `count` pinned to 40 (oversample). SQuAD: context-length x direct/infer cells,
# *-infer pinned to 5 each, max PASSAGE_CAP questions per passage. gold_answer ships
# EMPTY — filled by the 2-annotator pass. The committed CSV is the pre-registration.
.venv/bin/python code_benchmark/run_reading_eval.py --workers 4 [--resume]   # -> free-text answers per model
.venv/bin/python code_benchmark/score_reading_eval.py --answers <reading_answers_*.csv>   # EM + char-F1

# 4. Annotate / review the eval set (issue #3)
.venv/bin/python code_benchmark/export_annotation_workbooks.py build     # -> annotation_workbooks/annotator_{A,B}.csv (blind, context embedded)
.venv/bin/python code_benchmark/export_annotation_workbooks.py merge     # compare the 2 filled books -> gold_agreed/adjudication (+ --apply)
# PRIMARY review tool = the Next.js app in web/ (localhost, state autosaved to disk):
.venv/bin/python code_benchmark/build_review_ui.py export-blob           # -> web/data/review-blob.json (the validated workbook×answers join; rerun after ANY answers change)
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

# 5. Tests (CI runs the first two)
.venv/bin/python code_benchmark/test_parsing.py                        # standalone parity tests (also works on system python3)
.venv/bin/python -m unittest code_benchmark.test_suite                 # run from the REPO ROOT: imports the package modules
.venv/bin/python -m unittest code_benchmark.test_suite.TestVMLUBenchmark.test_extract_answer_accuracy   # single test (dotted: class or class.method)
# Offline but NOT in CI — per-feature modules, same dotted form, e.g.:
.venv/bin/python -m unittest code_benchmark.test_diagnostic code_benchmark.test_benchmark_reports code_benchmark.test_score_reading
# test_generative*.py are live-endpoint runners despite the name — never run them as tests.

# 6. Web app (cd web) — local-only; nothing here is CI-gated
npm run dev                          # 127.0.0.1:3000, loopback-only (from an agent session start it detached: setsid nohup npm run dev &)
npm run build ; npm run lint ; bunx tsc --noEmit
bun test                             # all lib/*.test.ts (bun:test)
bun test lib/harness-block.test.ts   # single file

# 7. Legacy scripts (historical only, need a venv pinned to openai==0.28.0)
cd code_benchmark && GPT_KEY="<KEY>" python3 legacy/test_gpt.py
cd code_benchmark && python3 legacy/test_prompt.py --llm "bigscience/bloom-1b7" --folder "./vmlu_v1.5/" --device "cuda"
```

## Evaluation arms (where things live)

All code is in `code_benchmark/`; outputs land in gitignored per-model / per-campaign dirs under `all_res/`, `submissions/`, `logs/`.

| Arm | Run → score | Notes |
| --- | --- | --- |
| **MC / VMLU-MQA** | `run_mc_eval.py` | The frozen A–E pipeline (below). VM14K reuses it via `make_vm14k_input.py` + `run_vm14k_mc14.sh`; shuffled-option runs via `make_shuffled_mc_input.py` + `run_shuffled_mc.py` |
| **Reading-400** | `make_eval_sample.py` → `run_reading_eval.py` → `score_reading_eval.py` | Pre-registered manifest, human-reviewed gold, EM + char-F1 |
| **V-Bench** | `run_vbench_eval.py` (MC + agentic tracks), `score_arg_credit.py` | No local gold — scored server-side at vbench.ai; locally only syntactic validity is computed |
| **Legal / BiDLQA** | `run_legal_arm_a.py` (legal MC/NLI direct baseline), `run_bidlqa_eval.py` | |
| **Harness (omp)** | `run_harness_eval.py run\|compare\|speed` | Same items through the `omp` coding agent — see *Harness arm* |
| **Vietnamese multi-model** | `make_vi_multimodel*_manifest.py` → `run_vi_multimodel_eval.py` / `run_vi_multimodel_expansion.py` → `score_vi_multimodel*.py` | Contracts in `vi_multimodel.py` (v1: six datasets) and `vi_multimodel_expansion.py` (v2: VMLU + V-Bench); frozen manifests/protocols/profiles in `data/vi_multimodel_*`; `run_vi_multimodel_go_campaign.py` schedules/auto-resumes whole profile×phase sets; `export_vi_multimodel_submissions.py` builds the upload files |
| **Metric add-ons** | `run_mc_calibration_eval.py`; `compare_position_bias.py`; `run_reading_cite_eval.py` + `judge_faithfulness.py` + `label_faithfulness.py`; `build_rq1_decomposition.py` | Calibration, position bias, citation faithfulness, harness-vs-model variance (RQ1); planned in `docs/metrics-plan-3-nhom.md` and `docs/harness-evolution-thesis-plan.md` |
| **Diagnostic** | `diagnostic.py` (`readiness`, `build-ledger`, `prepare-pilot`, `import-review`, `adjudicate`, `audit-report`, …) | Offline: audits frozen V1 artifacts and the prospective-campaign runs (adapter `diagnostic_campaign_ledger.py`), never calls a model; contract in `data/diagnostic_v1/`; reviewed in the web `/diagnostic` page |
| **Campaign drivers** | `run_<model>_<arm>_mcNN.py`, `retry_*` | One pre-registered run each — see *Campaign drivers* |

## Pre-registration & provenance

Read this before running anything that produces a number.

- **`measurement_card.md`** (repo root, Vietnamese) is the append-only registry of measurement conditions: one `## MC-n` block per run. A new run adds a new block; old blocks are never edited, and conditions are never merged (no "best of" columns — e.g. MC-2 vs MC-2b). Cards are pre-registered before the first benchmark-item request (commits are titled `pre-register MC-n`). Runs from MC-76 on also have a detail card in `docs/measurement_cards/MC-NN-*.md`, linked from the root block.
- Runners and scorers stamp **`measurement_card_hash`** (sha256 of the whole root file) into their outputs and `SystemExit` if the file is missing, so every score traces back to the card state at run time (recoverable from git — the reason old blocks stay untouched).
- `build_benchmark_reports.py` parses `## MC-n` headings (`^#{2,3} (MC-\d+[a-z]?)`) and keys cards by id: keep the heading format and keep ids unique.
- Campaign drivers also freeze a `condition.json` (sampling, route, runner/scorer/manifest sha256) next to their outputs; `--resume` refuses to continue if the inference condition would change.
- Protocol and spec changes go through `openspec/` (`specs/` = canonical, `eval-scoring/spec.md` authoritative for scoring; `changes/` = active proposals) — see the `opsx:*` and `vmlu-protocols` skills.
- **Generated — don't hand-edit**: `docs/rq1-decomposition.*` (`build_rq1_decomposition.py`), `web/data/*.json` and `web/public/{benchmark-data.json,benchmark-condition-reports.csv}` (the `build_*` scripts; `web/data/model-behavior-changelog.json` comes from `docs/model-behavior-changelog.md`), `data/gold/`.

## Campaign drivers (`run_<model>_<arm>_mcNN.py`, `retry_*`)

Each is one pre-registered run (Muse Spark via 9Router/OpenCode Go, Qwen3.5-9B on the IEC gateway, MiMo V2.6; MC-80–85 direct API, MC-86–89 `omp` full-tools) that hard-codes its card id, protocol id and `all_res/<campaign>/` output dir and reuses the `vi_multimodel*` contract and scorers. Conventions to copy rather than improvise:

- **`--execute` sends requests; without it the script only runs a preflight** (inputs, hashes, counts, `endpoint_calls=0`). Some have `--score` to score existing outputs offline. `--resume` re-runs only missing/technical failures; answers that completed — including unparsed or length-limited ones — are never retried automatically.
- Recovering those is a separate `retry_*` module (`python -m code_benchmark.retry_<name> [--execute]`) with its own attempt ledger and separately recorded timeout; it keeps the parent artifacts and overlays only the selected keys.
- Credentials come from `.env` keys other than `OPENAI_*`; the base URL must be the API root, not `/chat/completions` or `/responses`.
- `run_vi_multimodel_go_campaign.py` adopts runs that already hold their per-phase `.run.lock` flock and auto-resumes (≤3 launches).
- Several have a matching offline `test_<campaign>.py` (mocked transport; not CI-gated).

## Harness arm (`run_harness_eval.py`) — isolation gotchas

Arm B re-runs frozen items (byte-identical prompts, frozen parser/scorers, answers never repaired) through the `omp` coding agent and compares against arm A's direct-API numbers; one condition per `--label` slug. The measured condition leaks easily — arms through MC-26 were silently contaminated — so the runner guards it, and you must not work around the guards:

- **Override `HOME`** for a clean scaffold: `--agent-dir` (a gitignored `.omp-*/` dir with `models.yml` + token) isolates omp's config/providers, but omp still reads `~/.omp/agent/APPEND_SYSTEM.md` (that leak cost 14 accuracy points, card MC-22). Example: `HOME=/tmp/fakehome .venv/bin/python code_benchmark/run_harness_eval.py run --dataset legal_mc --workers 6 --label <slug> --tools none --system-prompt minimal --agent-dir .omp-clean`.
- **The item sandbox (`--scratch`, default `$TMPDIR/vmlu-harness-<slug>`) must sit outside any tree containing `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`/`.cursorrules`** — omp inlines them into every item's system prompt (this repo's own AGENTS.md once did, 27.5k chars). The runner hard-fails otherwise; `--allow-project-instructions` is only for deliberately measuring a project-scoped agent.
- Conditions are declared, not improvised: `harness_genome.py` defines one as a frozen, fail-fast-validated `Genome` (closed gene grammar; `genome_id` = hash of its canonical JSON; `required_declarations()` lists text its card must carry), `genome_to_cli.py` turns a genome into the exact `run_harness_eval.py` command, and `capture_scaffold.py` records the request omp really sends.

## Datasets on disk

`vmlu_datasets.zip` (3.5 MB, untracked) unpacks into four gitignored folders, and **only one is directly consumable by `run_mc_eval.py`**:

- `vmlu_mqa_v1.5/` — the classic MC format (`{id, question, choices[], answer}` JSONL): `test.jsonl` (9,833 questions, **no gold** — scored server-side by vmlu.ai), `dev.jsonl` (303) and `valid.jsonl` (744) with gold, and `all_gold.jsonl` (= dev + valid, 1,047 — the locally scorable set). 303 + 744 + 9,833 = the 10,880 total. Works with `--folder ./vmlu_mqa_v1.5 --file <name>`.
- `vmlu_drop_v1/`, `vmlu_squad_v1/`, `vmlu_dialog_v1/` — **"question_only" JSON** (one big `{__count__, data[]}` object; keys like `question_id/category/context/question`, `queries`), **no `choices`/`answer` fields** → the `run_mc_eval.py` loader will not accept them. They are consumed by the reading pipeline (`make_eval_sample.py` / `run_reading_eval.py`) and human/leaderboard-submission flows, not the MC pipeline.

Other gitignored data folders (local READMEs inside): `v_bench/` (V-Bench public test, re-fetchable), `v_legal_slsp/` (legal + ViBidLQA), `v_med_vm14k/` (VM14K). Tracked contracts live in `data/` (`eval_set_manifest.csv`, `vi_multimodel_*` manifests/protocols, `diagnostic_v1/`, `example_submission.csv`, …).

## MC pipeline (`code_benchmark/run_mc_eval.py`)

The frozen reference pipeline; the other arms borrow its prompt/parser or its conventions.

1. **Config** — `common.resolve_endpoint()`: env vars (`OPENAI_BASE_URL`/`OPENAI_API_KEY`/`OPENAI_MODEL`) with CLI overrides (`--base-url`, `--api-key`, `--model`) from the shared `add_endpoint_args` flag group; missing base URL or model → clear error + exit 1. `--limit` must be a positive integer. A 1-token "ping" (`llm.verify_credentials()`) fails fast before the workload starts.
2. **Load** — `{id, question, choices[], answer}` JSONL from `--folder` (falls back to `../<folder>`); empty file → exit 1; 4 or 5 choices.
3. **Prompt** — `build_prompt()` wraps the question + choices in a Vietnamese instruction asking for only the answer letter, ending `"Đáp án: "`. This string is a **contract with the legacy scripts** — keep it byte-identical.
4. **Inference** — `llm.call_model_with_retry()`: retries generic errors up to 30×30s, but **never retries** `AuthenticationError`/`PermissionDeniedError`/401/403 (re-raised to fail fast); returns `""` on exhaustion.
5. **Parsing** — `extract_answer()`: 4-tier regex (exact letter → Vietnamese/English key phrases → standalone upper/lowercase letter). Always returns **uppercase A–E** to match the official submission format; `""` when no answer is found.
6. **Concurrency & checkpointing** — `ThreadPoolExecutor(--workers)`; results indexed by original order; every 100 completions a lock-guarded snapshot is written to `all_res/ollama_result/<model>/raw_result_<N>_<model>.csv` (per-model dir via `common.model_dirs()`). `--resume` loads the checkpoint with the largest numeric suffix for THIS model (`checkpoint.find_latest_checkpoint()`) and skips already-answered ids.
7. **Auto-scoring (gold inputs only)** — if EVERY loaded record has a non-empty `answer` (`dev`/`valid`/`all_gold`), `detect_scorable()` enables scoring: at the end `score_row()` adds `gold_answer` + `correct` (case-insensitive letter match; an unparseable model answer is incorrect but still counted) and `build_accuracy_rows()` writes `accuracy_<model>.csv` (long format `level,name,n,correct,accuracy`: overall + per-category + per-subject) and logs overall % + a category table. Mixed gold/no-gold input → warning + non-scorable. Scoring is computed from merged results, so pre-scoring checkpoints remain resumable. The subject→category mapping is the `SUBJECTS` dict keyed by `id`.
8. **Outputs** (all gitignored, per-model): `all_res/ollama_result/<model>/full_evaluation_<model>.csv` (full results incl. raw responses, + the two scoring columns on gold inputs), `logs/<model>/<sanitized_model>.log`, and `submissions/<model>/submission.csv` — the final `id,answer` CSV (redirect with `--submission-out <path>`). V-Bench mirrors this (`all_res/ollama_result/<model>/vbench_*`, `submissions/<model>/submission_vbench_<model>.jsonl`); reading writes answers/scores/summaries under the same per-model dir.

### Key invariants & gotchas

- **Submission answers must be uppercase `{A,B,C,D,E,''}`** — matches `data/example_submission.csv` and the vmlu.ai submission portal. Answers are uppercased in `extract_answer`.
- `extract_answer` uses unicode word boundaries (`(?<!\w)([A-E])(?!\w)`) so Vietnamese words containing ASCII letters (e.g. `các`, `bói`) are never misread as options.
- `test_parsing.py` deliberately **duplicates** `extract_answer`/`build_prompt` rather than importing them — it is the standalone parity reference. `test_suite.py` imports from the package and must run from the repo root.
- Byte-frozen shared contracts: `build_prompt`/`extract_answer`, reviewer `slug()` (distinct from the per-model `sanitize_model`), `REVIEW_COLS`, `SCHEMA_VERSION=1`, `itemKey = dataset:item_id` (mirrored in `web/lib/types.ts` and the standalone review HTML). Drift ends in `SystemExit("Error: …")` by design — never guess a mapping or silently drop a row. Withheld-gold sets (V-Bench, VMLU test) never get a local `accuracy`/`correct`; unparseable answers stay in the denominator.
- The 30×30s retry cadence (15 min/case) is the default; auth errors are excluded from it deliberately — don't "fix" the retry loop back into touching auth errors.
- **Gitignored**: `vmlu/`, `all_res/` (per-model dirs `all_res/ollama_result/<model>/`, per-campaign dirs `all_res/<campaign>/`, legacy untagged under `legacy-untagged/`), `logs/` (per-model `logs/<model>/`), `submissions/` (per-model; condition variants under `submissions/conditions/`), `report/`, `data/gold/` (derived reading golds — regenerate via `export_annotation_workbooks.py`), `leaderboard.json`, `vmlu_v*`, `review_state/` (the review server's per-reviewer×model buckets — private, never shared), and the `.omp-*/` harness agent dirs. `.gitignore` lists each `.omp-*/` dir **individually** and they hold provider tokens — add any new one before a `git add -A`. `.env*` is ignored except `.env.example`/templates — keep it that way.
- **Tracked on purpose**: `review_records/*.csv` (the shared review work log), `web/data/*.json` + `web/public/*` (published result blobs; `review-blob.json` is the shared items+answers snapshot so every reviewer's app serves the identical eval), `docs/measurement_cards/`, the `data/` manifests. Keep `review_records/*.csv` and `web/data/review-blob.json` un-ignored (root-level `review_*.csv`/`state_*.json`/`review_ui.html` are still ignored via anchored `/*` patterns).
- `requirements.txt` is a **frozen env snapshot** and contains heavy leftovers (`torch==2.1.2`, `nvidia-*`, `transformers`). The only packages `run_mc_eval.py` actually needs are `openai>=1.0.0`, `python-dotenv>=1.0.0`, `pandas`, `tqdm`. The pinned GPU stack only matters for `legacy/test_prompt.py`.
- `common.py` is **stdlib-only** (make_eval_sample/test_parsing run on the bare system python3 through it) — never add openai/pandas/dotenv imports there; endpoint-touching helpers live in `llm.py`.
- Legacy scripts read old data paths (`vmlu_v2/`, `vmlu_v1.5/`) relative to `code_benchmark/`; `test_gpt.py` needs a venv with `openai==0.28.0` and the `GPT_KEY` env var.

## Web app (`web/`)

Next.js 16 / React 19 / Tailwind 4, loopback-only (`next dev -H 127.0.0.1`). **Next 16 differs from older versions**: `web/AGENTS.md` (rewritten by `next dev`; `web/CLAUDE.md` just imports it) says to read `web/node_modules/next/dist/docs/` before changing routing or config. Routes: `/` (reading review), `/benchmark`, `/harness`, `/multimodel`, `/results`, `/table`, `/changelog`, `/diagnostic`.

- **Python computes, the app displays.** Builders write the tracked data surfaces (`web/data/*.json`; `web/public/benchmark-data.json`, which holds one named block per arm and is patched in place by `build_dashboard_*.py`), and `web/lib/*.ts` validators (e.g. `harness-block.ts`) fail loudly on a stale or half-written block instead of rendering zeros. A changed Python schema therefore needs the matching validator and its `*.test.ts`. Dashboard builders must preserve every unrelated block.
- Review-app state lives on disk (`review_state/`, `review_records/`; override with `VMLU_REVIEW_BLOB` / `VMLU_REVIEW_STATE_DIR` / `VMLU_REVIEW_RECORDS_DIR`); the page re-reads the blob per request (`force-dynamic`), so `export-blob` takes effect on reload.
- **MongoDB is optional.** Only code going through `web/lib/db.ts` needs it (`app/api/results/*`, `app/api/notes`, `lib/benchmark-view.ts` for `/benchmark`, `lib/vi-multimodel.ts`, `lib/diagnostic-progress-server.ts`; `VMLU_MONGO_URI` / `VMLU_MONGO_DB`); `/harness` reads only the static block. Setup is in `docs/results-backend.md`: `docker run -d --name vmlu-mongo -p 27017:27017 -v vmlu-mongo-data:/data/db mongo:7`, then `seed_registries.py` → `migrate_results_to_mongo.py` → `verify_results_db.py` (CSV finals vs DB vs blob). The lab PC deployment (`deploy.yml`) gets its data only through `tools/push_data_to_pc.py` (SSH, dry run unless `--execute`; it then runs `tools/seed_db.ps1` there), never through git.

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

The gate deliberately does **not** run the eval runners (they need a live endpoint/models), the per-campaign `test_*.py` modules, or any web check (`tsc`, `bun test`, lint, build), and never lints `legacy/` (frozen `openai==0.28.0` scripts — their unused imports document the original research setup). Run the relevant non-gated checks yourself when you touch those areas.

## Agent skills

`.claude/skills/` (mirrored for Codex under `.agents/skills/`) has two groups. **Project-specific — use these first**: `vmlu-eval-ops` (run/resume/package an arm), `vmlu-protocols` (any prompt/metric/manifest/schema change), `vmlu-results-data` (score runs, refresh dashboard blocks), `vmlu-review-ops` (annotation workbooks, review exports, review-UI data). **General** engineering skills reused from `../AI-Image` (`/review-and-fix`, `/diagnosing-bugs`, `/tdd`, `/grilling`, `/triage`, `/to-spec`, `/handoff`, … plus the 5 `openspec-*` skills and `/opsx:*` commands). The `openspec` CLI (bun-global, v1.10.0) was initialised with `--tools none`; its scaffold is `openspec/` (`config.yaml` holds project context + artifact rules). The 8 frontend/imagegen design skills were deliberately not imported. Repo config for them:

### Issue tracker

Issues and specs live as GitHub Issues on `thomasNguyen-196/VMLU`, driven by the `gh` CLI (logged in as `nttung245`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) — labels must be created once in the GitHub repo before `/triage` can apply them. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` (Vietnamese glossary of benchmark terms) + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Code intelligence

- The repo has `.codegraph/` (index is gitignored; rebuild with `codegraph init`): use **CodeGraph before grep/find/Read** when locating or understanding code. `codegraph_explore` (MCP) or `codegraph explore "<symbols or question>"` returns verbatim source plus call paths and blast radius; the daemon auto-syncs file changes. Code intelligence order: **CodeGraph first → context-mode** (`ctx_search`/`ctx_execute` for indexed content and large-output processing) **→ grep/read/glob last** (configs, docs, dataset files, or confirming one small detail only).
- For symbol renames, prefer an IDE-aware refactor or CodeGraph call-site review (`codegraph callers`/`codegraph impact`) over naive find-and-replace — `extract_answer`/`build_prompt` have deliberately duplicated copies in the test scripts that grep-based renames will silently miss.
