# Repository Guidelines

## Project Overview

VMLU (Vietnamese Multitask Language Understanding) — evaluation of Vietnamese language models: the 58-subject, 10,880-question multiple-choice benchmark (ZaloAI-Jaist/VMLU, ACL-2025 paper in repo) plus a **pre-registered 400-question reading-comprehension eval** (issue #3: 200 Vi-SQuAD + 200 Vi-DROP, seed 42). Active work is the reading-eval gold-annotation + human-review pass; the MC pipeline is frozen.

## Architecture & Data Flow

Three independent pipelines, one shared review layer. Contracts are **byte-frozen across surfaces** and asserted by CI.

**MC pipeline** (frozen):
`vmlu_mqa_v1.5/<file>.jsonl` (`id, question, choices[], answer?`) → `code_benchmark/run_mc_eval.py` prompts → OpenAI-compatible endpoint (ThreadPool `--workers`, 30×30s retry, auth fail-fast) → per-model `all_res/ollama_result/<model>/raw_result_<n>_<model>.csv` checkpoints → finals `full_evaluation_<model>.csv`, `accuracy_<model>.csv`, `submissions/<model>/submission.csv` (`id,answer`; redirect with `--submission-out`).
Scoring: `detect_scorable` is all-or-none (mixed gold → no scoring, warning); case-insensitive exact letter match; unparseable = incorrect but stays in denominator; subject = id prefix `XX-YYYY` via the in-code `SUBJECTS` dict (**`data/dataset_stat.csv` ordering is different — never use it**); unknown prefixes get an explicit "unknown" bucket.

**Reading pipeline**:
`make_eval_sample.py` → `data/eval_set_manifest.csv` (6 cols; `gold_answer` ships empty — pre-registration) → `run_reading_eval.py` (manifest + source JSON join with question-drift fail-fast; open-book Vietnamese prompt, 48-token budget; per-model checkpoints `all_res/ollama_result/<model>/reading_result_<n>_<model>.csv`) → `reading_answers_<model>.csv` in the same model dir (free text; no scoring here — EM/char-F1 is a later step).

**V-Bench pipeline** (external leaderboard, vbench.ai release v2026.03.28):
`v_bench/public-test.jsonl` (gitignored download; `id:int, question, choices[], function[], domain`) → `run_vbench_eval.py` → per-model `submissions/<model>/submission_vbench_<model>.jsonl` uploaded at vbench.ai (server-side scoring, no gold, aggregate-only). Tracks: `mc` (letter answer via the FROZEN shared `build_prompt`/`extract_answer`, clamped to the row's choice count) + `agentic` (`[{"<fn>":{args}}]` validated against the row's own schemas — required present, enum verbatim, unknown/hallucinated fields rejected; invalid calls are dropped, never guessed — braceless `["fn":{…}]` output is rebracketed but its content is never altered). **Prompt conditions** (`--prompt-style`, agentic): `minimal` (default; honest condition — question verbatim + row schema + official format line, nothing else) vs `detailed` (role+rules+example+no-CoT variant); keep one condition per `--model` slug so checkpoints never mix — richer prompting measures the prompt, and few-shot/CoT must stay controlled ablations. Safety rows are skipped (not scored this release). Per-model checkpoints `all_res/ollama_result/<model>/vbench_result_<n>_<model>.csv` + `vbench_valid_summary_<model>.csv`; `--submission-only` rebuilds the jsonl from the latest checkpoint; `--resume --retry-unparsed` re-calls ONLY rows unparsed under the current parser; `--resume --guided` re-asks unparsed agentic rows as a numbered interview (model answers by number, tool assembles JSON, transcript in `raw_response`; `load_checkpoint` must NOT re-derive guided rows from their transcript) — guided answers are a THIRD elicitation condition and must be labeled as such when scoring/ablicting. Still-failing rows go verbatim with a diagnosis to `vbench_failures_<model>.csv` (deleted on a clean pass) — a wrong model answer stays wrong, unshipped but logged.

**Harness arm** (`run_harness_eval.py` — same model, agent scaffold instead of a direct prompt; the RQ1 decomposition):
`run --dataset {legal_mc,legal_nli,reading400,bidlqa_val,vbench_agentic}` → one `omp` process per item: the **byte-identical** arm-A prompt (frozen `build_prompt`/`build_reading_prompt`; the legal adapters are re-derived from source and hard-failed against arm A's stored prompts), delivered inside the `omp` coding agent. The measured harness is pinned by `PI_CODING_AGENT_DIR=.omp-iec/` (gitignored: `models.yml` provider + `config.yml` with every model role pinned to the one model under test, `.env` token) — **never** run it against the everyday `~/.omp` profile, and note the agent dir must reach `run_item` as an **absolute** path (each item runs with `cwd` = its own sandbox). **⚠ `PI_CODING_AGENT_DIR` does NOT isolate the scaffold**: omp also reads `~/.omp/agent/APPEND_SYSTEM.md` from the *default* agent dir, so a measured arm silently inherits the machine's reply-style rules (worth 14 accuracy points and 130× the output tokens — card MC-22); an empty file in the custom agent dir does not shadow it, only a `HOME` override does, and `warn_about_scaffold_leaks` shouts about it on every run. Isolation of config/providers is NOT isolation of the scaffold. Per item: a fresh empty temp dir holding only `item.json` (no gold, no dataset), `--cwd` on it, no `--add-dir`; `audit_transcript` records network attempts and tool-call path escapes (a convention, not an enforcement — `bash` can still `cd` out; 2 failed attempts / 1.178 items, 0 gold leaked). Nothing is repaired: unparsed/empty/exit≠0 items land verbatim with a diagnosis in `harness_failures_<dataset>_<slug>.csv`. One condition per `--label` slug; checkpoints `harness_<dataset>_result_<count>_<slug>.csv`; the ledger is the source of truth and the arm-A-shaped projection (`full_evaluation_<dataset>_*` / `reading_answers_*`) is what the **frozen** scorers read. Ablations: `--tools none` (H1, maps to omp's `--no-tools`) and `--system-prompt minimal` (H3/H4, sentinel → `MINIMAL_SYSTEM_PROMPT`). `--dataset vbench_agentic` reuses the **frozen** V-Bench agentic prompt + validator and has **no local gold**: `compare` measures schema VALIDITY (per item on both sides — the direct arm's from its own checkpoint, since its `vbench_valid_summary` was computed exactly that way) and the run writes `vbench_valid_summary_<slug>.csv` plus an uploadable `submissions/<slug>/submission_vbench_<slug>.jsonl` (invalid rows ship an empty answer, never a guess). `compare` does the paired table (2×2, Δ, paired bootstrap CI seed 42, exact McNemar); `--arm-a-slug` accepts any finished arm so arm-vs-arm is first-class (`_mc_eval_path` resolves both naming schemes) and `--tag` prevents overwrites. `speed` rows carry `arm` = the registry name and `side` = `direct`|`omp`: the probe CSV's own `arm` column is the PAIR id (`A_direct`/`B_omp_h2`, hardcoded in `_speed_summary`), so only the `n=24, workers=4` cells are mutually comparable — H2's probe is `n=40` (MC-25). The block also carries `secondary_metrics` (EM on the verbatim reply vs EM on the same reply with the wrapper peeled off, scored by the same frozen scorer) — an ATTRIBUTION metric that never replaces the headline EM. Every `run` **preflights the endpoint** with one 1-token call (45s) and aborts with a diagnosis if it is down — a harness arm has no per-item retry, so without this a gateway outage (observed 2026-09-27: IEC accepted TCP, never answered HTTP) would turn every item into a `--max-time` "model failure" (card MC-24). It fired on a real outage: the poller found the gateway back at 13:55 and every stage resumed with 0 preflight failures. `speed` is the **cost** probe (both arms, same items, same `--workers`): wall/model time/process overhead/TTFT/prompt+completion tokens. **Never trust `input + cacheRead` as request size** — the IEC gateway's cache counter is cumulative, which inflated MC-19 by ~8×; use `capture_scaffold.py` (localhost logging reverse proxy) to record the exact request bytes a condition sends. One condition = one claim: with the leak removed the measured cost of being inside `omp` is −5,6…−22,3 points (cards MC-15…MC-23, read together), **flat across the persona × tools cells** (all contrasts p ≥ 0,40) — so neither gene may be blamed. `build_dashboard_harness.py` persists the whole ladder for display: it patches `web/public/benchmark-data.json["harness"]` (**every** number read from the run artifacts and cross-checked against the per-item file; a per-item file with no compare aborts, and a patch that touches any other key is refused) and writes the offline `harness_report.html`. The Next app surfaces it at `/harness` via `web/lib/harness-block.ts` (validates the block, fails loud on a stale one; contract tests in `harness-block.test.ts`).

**Review layer** (one data contract, three surfaces — Python builder, Next app, static fallback):
`build_review_ui.py` joins workbook + answers (fail-fast: unknown keys, coverage unless `--allow-partial`) → `review_ui.html` (offline fallback, localStorage) and `web/data/review-blob.json` (**tracked**; Next app input). Decision semantics: accept ⇒ model answer becomes gold; reject ⇒ reviewer's correction (reject without correction is flagged, lands in adjudication). State autosaves to gitignored `review_state/<slug(reviewer)>__<slug(model)>.json`; exporting CSV publishes the 9-column record to tracked `review_records/review_<slug>_<slug>.csv` (peer locks in split-400). Merge: `export_annotation_workbooks.py review --a --b [--apply]` (both-reviewer intersection; drift/difference → adjudication) or `merge-split` (union; N≥1 reviewer — a fully-owned split is legal).
The blind `merge` workflow (`annotation_workbooks/`) is the separate stricter-IAA path — **blind books never contain model answers**; do not `--apply` review golds into the manifest while annotation is still running (print reminder in `build_review_ui.py`).

## Key Directories

- `code_benchmark/` — all pipeline Python (a real package: `__init__.py`). Shared kernel: `common.py` (stdlib-only — slug, `dataset:item_id` key, endpoint/argparse/logging resolution, atomic CSV; the two dependency-free files run through it on system python3), `llm.py` (client + retry + probe), `checkpoint.py` (per-model checkpoint naming/lookup). Runners: `run_mc_eval.py` (MC pipeline, ex `test_ollama.py`) + `run_reading_eval.py` + `run_vbench_eval.py` (V-Bench public test, imports the frozen MC prompt/parser) + `run_harness_eval.py` (harness arm: same items through the `omp` agent, `run|compare|speed`) + `capture_scaffold.py` (localhost logging proxy — records the exact request bytes a condition sends; capture-only, its SSE pass-through does not complete a run). `build_dashboard_harness.py` writes the harness block + `harness_report.html`. `legacy/` is frozen history (openai==0.28.0 / transformers+GPU; excluded from every linter, not in CI) — leave it alone.
- `web/` — Next.js 16 review app (own `web/AGENTS.md`). App code in `components/`, concurrency-free logic in `lib/`, disk APIs in `app/api/`.
- `vmlu_mqa_v1.5/`, `vmlu_squad_v1/`, `vmlu_drop_v1/` — gitignored datasets (unpacked from tracked `vmlu_datasets.zip`). SQuAD: `{id, question, context}`; DROP: `{question_id, category, context, question}`; MQA: `{id, question, choices[], answer}`.
- `v_bench/` — gitignored V-Bench public-test download from vbench.ai (re-fetchable; source of truth is the site).
- `data/` — repo-root data files, no longer scattered. **Tracked contracts:** `eval_set_manifest.csv` (pre-registered 400), `dataset_stat.csv` (source snapshot; its subject ordering is NOT the code's), `example_submission.csv` (VMLU upload template), `sample_submission.jsonl` (V-Bench official sample). **Gitignored/derived:** `data/gold/` (`review_gold_agreed.csv`/`review_adjudication.csv`/`gold_agreed.csv`/`adjudication.csv` — regenerate via `export_annotation_workbooks.py`).
- `submissions/<model>/`, `all_res/ollama_result/<model>/`, `logs/<model>/` — gitignored per-model outputs (checkpoints + finals + uploadables + logs); `annotation_workbooks/`, `review_state/` — gitignored local artifacts.
- `review_records/` — **tracked** shared sync log (the durable record for split-400; commit + push to hand work over).
- `openspec/` — spec-driven design docs; canonical spec `openspec/specs/eval-scoring/spec.md`. `docs/agents/` — agent workspace conventions.

## Development Commands

All from repo root with `.venv/bin/python` unless noted:

```bash
# MC evaluation (gold answers required for scoring: use all_gold.jsonl / dev / valid)
python code_benchmark/run_mc_eval.py --folder vmlu_mqa_v1.5 --file all_gold.jsonl --workers 4 [--resume]

# Reading comprehension inference
python code_benchmark/run_reading_eval.py --workers 4 [--resume]

# V-Bench public test -> uploadable submission (no gold; scoring is server-side)
python code_benchmark/run_vbench_eval.py --workers 4 [--resume] [--track mc|agentic] [--submission-only]
python code_benchmark/run_vbench_eval.py --resume --retry-unparsed   # re-call only unparsed rows
python code_benchmark/run_vbench_eval.py --resume --guided           # numbered-interview retry (agentic)
python code_benchmark/run_vbench_eval.py --track agentic --prompt-style minimal   # honest default condition
# Stratified manifest (stdlib-only; regenerating changes the pre-registration!)
python code_benchmark/make_eval_sample.py

# Gold/review tools
python code_benchmark/export_annotation_workbooks.py build
python code_benchmark/export_annotation_workbooks.py merge --apply
python code_benchmark/export_annotation_workbooks.py review --a A.csv --b B.csv [--apply]
python code_benchmark/export_annotation_workbooks.py merge-split review_records/*.csv [--apply]

# Blob + fallback (regenerate blob after every run_reading_eval / answers change)
python code_benchmark/build_review_ui.py export-blob     # -> web/data/review-blob.json
python code_benchmark/build_review_ui.py build           # -> review_ui.html

# Web app
cd web && npm install && npm run dev    # 127.0.0.1 only; blob is re-read per request (force-dynamic)
cd web && bunx tsc --noEmit             # typecheck (no script exists for it)
```

Env: `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY` (default `"ollama"`) via `.env`; CLI flags override. `VMLU_REVIEW_BLOB` / `VMLU_REVIEW_STATE_DIR` / `VMLU_REVIEW_RECORDS_DIR` override the web app's paths.

## Code Conventions & Common Patterns

- **Fail-fast everywhere**: `SystemExit` on contract drift, duplicate/unknown keys, header mismatch, mixed identities. Never guess, never silently skip (exception: web `parseCsvRows` is documented fail-open — locks only).
- **Byte-frozen contracts**: `extract_answer`/`build_prompt` (MC), `REVIEW_COLS` (9 columns, BOM+CRLF, one per item in workbook order), `slug()` rule (lowercase, NFD-strip diacritics, non-alnum → `_`, trim `_`), `SCHEMA_VERSION = 1`, StateEnvelope shape `{schema_version, annotator, model, saved_at, items:{key:{d,c,n}}}`. Changing one = deliberate multi-surface change (Python + `web/lib/` + template) with CI parity updates. `test_parsing.py` deliberately duplicates the parser — never dedupe.
- **Pre-registration**: manifest committed before any gold annotation; `join_manifest` treats question-text drift as wrong source.
- **Per-model checkpoints**: `raw_result_<count>_<model>.csv` / `reading_result_<count>_<model>.csv` / `vbench_result_<count>_<model>.csv` (`sanitize_model`: non-`[a-zA-Z0-9_-]` → `_`) under `all_res/ollama_result/<model>/` (+ finals/scores/summaries/scores in the same dir; uploadables in `submissions/<model>/`; logs in `logs/<model>/`). Legacy count-only files carry no model identity and are never resumed (kept under `all_res/ollama_result/legacy-untagged/`).
- **Single source of truth**: `SUBJECTS` (subject map; official README numbering), `REVIEW_COLS` (Python vs `web/lib/export-csv.ts`), `SCHEMA_VERSION`, `itemKey = dataset:item_id` (universal key).
- **Blind protocol**: gold annotation without model answers; state is per-`(reviewer, model)` slug bucket — never import another reviewer's state.
- **Concurrency**: `ThreadPoolExecutor` + one `Lock` around shared results; checkpoints every 100; atomic file writes via tmp + rename.
- **Web patterns**: keyboard protocol (`j/k/a/r/u/e/n/t/Home/End/?`; ignored while typing); NavDock boundaries disable (no wrap) while next-unreviewed wraps; Filmstrip = one cell per item grouped per passage; decisions blocked while a bucket is loading; model switch flushes the pending autosave.
- Lint scope is deliberately narrow: ruff `F,B,E9` only, bandit skips `B101/B311` by design; `legacy/` excluded everywhere.

## Important Files

- `code_benchmark/run_mc_eval.py` — MC pipeline: prompt/parser contract, `SUBJECTS`, checkpoint + scoring (retry/auth now in `llm.py`).
- `code_benchmark/common.py` — the shared kernel both runners import (stdlib-only): `sanitize_model`, `item_key`/`split_item_key`, `resolve_endpoint`, `add_endpoint_args`, `setup_logging`, `read_csv_checked`, `write_csv_atomic`.
- `code_benchmark/make_eval_sample.py` — sampler constants (`DROP_PINNED=40`, `PASSAGE_CAP=2`, `SQUAD_INFER_FLOOR=5`, bounds 230/400).
- `code_benchmark/run_reading_eval.py`, `run_vbench_eval.py`, `export_annotation_workbooks.py`, `build_review_ui.py` — reading + V-Bench pipelines and gold/review tools (subcommands `build|merge|review|merge-split`, `build|export-blob`).
- `data/eval_set_manifest.csv` — the pre-registered 400; `gold_answer` filled only via `--apply`.
- `web/data/review-blob.json` — tracked blob input (regenerate via `export-blob`; the revamp design doc's claim it's gitignored is stale).
- `web/lib/types.ts` (TS contract mirror), `web/lib/slug.ts`, `web/components/hooks/` (persistence+peer-sync / transfer / keyboard), `ReviewApp.tsx` (orchestration/layout only).
- `code_benchmark/review_ui_template.html` — static fallback whose JS mirrors `web/lib` (parity asserted).
- `.github/workflows/ci.yml`, `ruff.toml`, `.bandit.yml`, `pyrightconfig.json`, `.env.example`, `vmlu_datasets.zip`.

## Runtime/Tooling Preferences

- Python 3.12 in `.venv` (uv-managed per openspec context). Actual runtime deps: `openai`, `pandas`, `python-dotenv`, `tqdm`. `requirements.txt` is a frozen legacy snapshot (torch/nvidia GPU stack for `legacy/`) — do not install it to run the pipelines; CI installs only the four.
- Node ≥ 22 or bun for TS execution (contract tests use whichever is on PATH, skip when neither).
- Next 16.3.4, React 19, TypeScript strict, Tailwind v4 via PostCSS; dev/start bind loopback only — localhost tool with no auth beyond the reviewer-name gate; single-researcher, last-atomic-write-wins.
- **Code intelligence order: CodeGraph first → context-mode → grep/read last**: repo has `.codegraph/` (gitignored; rebuild with `codegraph init` after cloning). Use `codegraph_explore` (MCP) or `codegraph explore "<symbols or question>"` for locating/understanding code (verbatim source + call paths + blast radius; daemon auto-syncs). Use `ctx_search`/`ctx_execute` for indexed content and large-output processing. Fall back to grep/read/glob only for configs, docs, dataset files, or confirming one small detail. When a response shows the staleness banner, read those files directly.
- For symbol renames, prefer an IDE-aware refactor or CodeGraph call-site review (`codegraph callers`/`codegraph impact`) over naive find-and-replace — `extract_answer`/`build_prompt` have deliberately duplicated copies in the test scripts that grep-based renames will silently miss.
- Git: conventional commits; CI gates PRs/pushes to `main` (ruff + bandit + tests). The web app is not build-gated in CI — typecheck it locally.

## Testing & QA

- Suite: `python code_benchmark/test_parsing.py` (standalone parity reference, 17 cases, run as a script) and `python -m unittest code_benchmark.test_suite` (73 tests / 17 classes; **must run from repo root** — package imports). Both offline: tempdirs + `MagicMock`, no network or keys.
- The suite covers every pure pipeline function: allocator invariants, stratum functions, manifest shape/caps, checkpoint model isolation, review classifiers (`review` vs `merge-split` semantics), blob validation, render guard, and cross-surface contracts.
- `TestNextContracts` runs the real TS modules (`web/lib/slug.ts`, `web/lib/export-csv.ts`) against the Python/JS references — slug parity + export-CSV byte compatibility fed back through Python `read_review`. Skips when neither bun nor node ≥ 22 is on PATH.
- Full benchmark runs (`run_mc_eval.py`, `run_reading_eval.py`, `run_vbench_eval.py`) need a live endpoint and models — not CI-gated.
