Arm for every request task below: OMPS, which is omp 18.0.0 as OMPF with `--system-prompt <dsh's system prompt for the model>`.
- **Qwen:** IEC `Qwen3.5-9B-65K` over the VPN.
- **MiMo:** OpenCode Go `mimo-v2.6-flash`.

## 0. Owner decisions

- [x] 0.1 The owner chooses the harness component to test first.

  (2026-11-20, "okay làm 3 đi": omp's system prompt, ahead of thinking, which IEC cannot switch on, and more models.)
- [x] 0.2 The owner approves this design: dsh's prompt verbatim as the replacement, OMPS only, comparators from the registered score files, P1–P3 with Holm over three.

  (2026-11-20, "okay", with an addition: observe the harness's flow log, because what sets a harness apart is the actions it performs. This became design §8.)

## 1. Build (offline)

- [ ] 1.0 `harness_flow.py`: one action timeline per attempt from `events.jsonl` and `proxy_log.jsonl` for dsh and omp (design §8), with tests. Run it on MC-112 to MC-116 (Phase 1b, exploratory) before MC-117's data exist.

  (2026-11-20: `harness_flow.py` with 7 tests; `analyze_harness_flows.py`; report `0344d454…`; doc `docs/research/legal-agent-flows-2026-11-20.md`. The finding is who chooses the read window: in omp, 32–42% of Qwen's reads are pages the harness cut (16–40% with the middle elided), against 1.5–2.8% of MiMo's. Qwen answers straight from a grep in 51% of MC attempts in omp (13% in dsh). For MC-117 the mechanism indicators are the share of model-chosen read windows and the share of answers straight after a grep, OMPS against OMPF.)

- [ ] 1.1 `data/diagnostic_legal_agent_omp_prompt/`: the protocol and both dsh prompt texts (hashes `d6bd65aa…`, `54d89951…`).
- [ ] 1.2 `diagnostic_legal_agent_omp_prompt.py`: protocol loader, OMPS overlays on MC-113's and MC-116's omp specifications, and the manifest built from MC-115's OMPF items (design §2), with tests.
- [ ] 1.3 `run_legal_agent_omp_prompt.py --model qwen|mimo`: wraps MC-115's and MC-116's runners, with identity on halted rows and stall handling (design §4), a self-test against scripted servers, and the smoke test, with tests.
- [ ] 1.4 `analyze_legal_agent_omp_prompt.py`: the registered analysis (design §7), with tests on synthetic cells and a dry run on relabelled earlier draws.
- [ ] 1.5 Checks: the new tests, `test_suite`, `test_parsing`, ruff and bandit, the self-test and the offline preflight for both models.

## 2. Smoke test (ask the owner first; the VPN for Qwen)

- [ ] 2.1 `--smoke --execute` per model: 4 attempts in all, no benchmark item. Record the reports and their SHA-256 in the protocol.
- [ ] 2.2 From the reports: the system-prompt pins and the budgets. Freeze `manifest_v1.json`.

## 3. Registration

- [ ] 3.1 The MC-117 root block, the detail card and `registration.json`.
- [ ] 3.2 With the owner's go, commit `pre-register MC-117`. Every preflight gate must pass for both models.

## 4. Run (ask the owner first)

- [ ] 4.1 Launch both models as `systemd-run --user` units (Qwen with the VPN), and use `--resume` after technical stops.
- [ ] 4.2 Record the runs in the detail card.

## 5. Analysis and record

- [ ] 5.1 Run the analysis once, and record the report's SHA-256 and the results.
- [ ] 5.2 Update the thesis draft and Notion, with the owner's go.
