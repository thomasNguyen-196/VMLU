## 1. Harness code — the `all` tool condition

- [x] 1.1 Add the `all` sentinel to `code_benchmark/run_harness_eval.py`
  (`build_argv`: `all` → omit both `--tools` and `--no-tools`; record the run
  condition as `tools=all (omp default)`; update `--tools` help). Verify with
  `python -m unittest code_benchmark.test_suite` from repo root: the existing
  `none`/explicit-menu argv tests stay green and a new `all` test shows no
  `--tools`/`--no-tools` in argv.
- [x] 1.2 Add the argv/condition test cases (`none` | explicit menu | `all`,
  `resolve_tools` labels) in `code_benchmark/test_suite.py`. Verify
  `python -m unittest code_benchmark.test_suite` and
  `python code_benchmark/test_parsing.py` both pass, and `ruff check .` is clean.

## 2. Agent dirs + condition capture

- [x] 2.1 Create `.omp-qwen65k-real/` (models.yml: provider `iec`, model
  `Qwen3.5-9B-65K`, `contextWindow: 65024`, `maxTokens: 4096`, `reasoning: false`)
  and `.omp-qwen65k-pinned/` (same but `baseUrl: http://127.0.0.1:8799/v1`), each
  with its `.env` token; add both patterns to `.gitignore`. Verify
  `git check-ignore .omp-qwen65k-real .omp-qwen65k-pinned` prints both.
- [x] 2.2 Run `capture_scaffold.py --agent-dir .omp-qwen65k-real --pin temperature=0`
  and send one item through omp with `--tools` omitted. Verify the capture file
  exists, records `pinned_by_proxy.temperature`, and its inventory matches the
  planning reading (11 tools, ~50.3k chars of schemas, ~14.2k prompt tokens).

## 3. Pre-register MC-31

- [x] 3.1 Write `MC-31` into `measurement_card.md` **before any run**: model
  `Qwen3.5-9B-65K` @ `https://llmapi.iec-uit.com/v1`; condition (clean scaffold,
  neutral system prompt, `--tools all`, `temperature=0` pinned, HOME override,
  sandbox `/tmp`); slugs (`Qwen3_5-9B-65K`, `ompT65_Qwen3_5-9B-65K`); datasets and
  order; worker policy (4, cap 6); the capacity reading (n_ctx 65,024, prefill
  ~3.2–3.6k tok/s, decode ~105 tok/s, 14,177-token request, 32-way blackout
  incident) and the probe commands used. Verify the card text is committed and
  contains no post-hoc numbers.
- [x] 3.2 Preflight the arm endpoint/model (`preflight_endpoint` path via a
  dry run or a 1-token call) and record the 200 in the run log before task 5.1.

## 4. Arm A re-baseline — Qwen3.5-9B-65K @ IEC

- [x] 4.1 Legal arm A (`run_legal_arm_a.py`, model `Qwen3.5-9B-65K`, endpoint IEC):
  verify the byte-parity gate matches the stored arm-A prompts 146/146
  (legal_mc) and 150/150 (legal_nli) before accepting the files.
- [x] 4.2 Reading/bidlqa arm A (`run_reading_eval.py`, model `Qwen3.5-9B-65K`):
  verify `reading_answers`/`reading_scores` cover 400 + 482 items against the
  pre-registered manifest.
- [x] 4.3 V-Bench arm A (`run_vbench_eval.py`, model `Qwen3.5-9B-65K`):
  verify the MC letters (4,141) and agentic (1,000) artifacts exist and the
  valid-summary matches the frozen parser.

## 5. Arm B — clean scaffold × default-all tools — Qwen3.5-9B-65K @ IEC via proxy

- [x] 5.1 Start `capture_scaffold.py --pin temperature=0`, then run `legal_mc`
  and `legal_nli` with `HOME=/tmp/fakehome`, absolute `PI_CODING_AGENT_DIR`,
  `--tools all --system-prompt minimal --workers 4`. Verify ledgers 146/150 with
  `harness_failures_*.csv` absent or explained.
- [x] 5.2 Run `reading400` and `bidlqa_val` the same way (`--resume` on any
  restart). Verify ledgers 400/482.
- [x] 5.3 Run `vbench_agentic` (1,000). Verify ledger 1,000 and schema-validity
  summary.
- [ ] 5.4 Run `vbench_mc` (4,141; last, may span restarts with `--resume`).
  Verify ledger 4,141 and list the empty/unparsed rows with a diagnosis.
- [ ] 5.5 For every dataset run `run_harness_eval.py compare --dataset … --tag vsA`
  against the 65K arm A. Verify each compare CSV carries n, delta, CI, and
  `arm_b_failures`, and copy the numbers into MC-31.

## 6. Dashboard, contracts, suite

- [ ] 6.1 Register the two 65K arms in `build_dashboard_harness.py`
  (`ARM_MODEL`, `ARM_DATASETS`, `REPRESENTATIVE` for `Qwen3.5-9B-65K` → `T65`) and
  run the builder. Verify `git diff` touches only `web/public/benchmark-data.json`
  harness block (+ `harness_report.html`, gitignored).
- [ ] 6.2 Run `cd web && bunx tsc --noEmit` and
  `bun test lib/harness-block.test.ts`; update the registry assertions if they
  fail. Verify both green.
- [ ] 6.3 Run the full offline suite (`python -m unittest code_benchmark.test_suite`)
  and `ruff check .` from repo root. Verify green before calling the change done.

## 7. Follow-on (not gated by this change)

- [ ] 7.1 MiMo default-all arm (label `ompM6all_mimo-v2.5` @ OpenCode Zen Go,
  model **`mimo-v2.5`** — đã chốt 2026-09-30; vẫn đọc id verbatim từ `/models` của
  gateway khi chạy, nếu khác thì ghi lại vào card; pin `reasoning_effort`;
  separate card) — run only after the 65K ladder is complete.
- [ ] 7.2 If the run-time capacity reading differs from the MC-31 pre-registration
  (e.g. 65K node changed), update the card with the new reading and a note, not a
  silent edit of the plan.
