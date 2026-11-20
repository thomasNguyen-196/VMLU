Arm for every request task below: OMPS, which is omp 18.0.0 as OMPF with `--system-prompt <dsh's system prompt for the model>`.
- **Qwen:** IEC `Qwen3.5-9B-65K` over the VPN.
- **MiMo:** OpenCode Go `mimo-v2.6-flash`.

## 0. Owner decisions

- [x] 0.1 The owner chooses the harness component to test first.

  (2026-11-20, "okay làm 3 đi": omp's system prompt, ahead of thinking, which IEC cannot switch on, and more models.)
- [x] 0.2 The owner approves this design: dsh's prompt verbatim as the replacement, OMPS only, comparators from the registered score files, P1–P3 with Holm over three.

  (2026-11-20, "okay", with an addition: observe the harness's flow log, because what sets a harness apart is the actions it performs. This became design §8.)

## 1. Build (offline)

- [x] 1.0 `harness_flow.py`: one action timeline per attempt from `events.jsonl` and `proxy_log.jsonl` for dsh and omp (design §8), with tests. Run it on MC-112 to MC-116 (Phase 1b, exploratory) before MC-117's data exist.

  (2026-11-20: `harness_flow.py` with 7 tests; `analyze_harness_flows.py`; report `0344d454…`; doc `docs/research/legal-agent-flows-2026-11-20.md`. The finding is who chooses the read window: in omp, 32–42% of Qwen's reads are pages the harness cut (16–40% with the middle elided), against 1.5–2.8% of MiMo's. Qwen answers straight from a grep in 51% of MC attempts in omp (13% in dsh). For MC-117 the mechanism indicators are the share of model-chosen read windows and the share of answers straight after a grep, OMPS against OMPF.)

- [x] 1.1 `data/diagnostic_legal_agent_omp_prompt/`: the protocol and both dsh prompt texts (hashes `d6bd65aa…`, `54d89951…`).

  (2026-11-20: both prompt files hash as recorded; protocol built from MC-116's shared blocks plus the two model specifications and MC-116's score file `18c86a13…` as a reference.)
- [x] 1.2 `diagnostic_legal_agent_omp_prompt.py`: protocol loader, OMPS overlays on MC-113's and MC-116's omp specifications, and the manifest built from MC-115's OMPF items (design §2), with tests.
- [x] 1.3 `run_legal_agent_omp_prompt.py --model qwen|mimo`: wraps MC-115's and MC-116's runners, with identity on halted rows and stall handling (design §4), a self-test against scripted servers, and the smoke test, with tests.
- [x] 1.4 `analyze_legal_agent_omp_prompt.py`: the registered analysis (design §7), with tests on synthetic cells and a dry run on relabelled earlier draws.
- [x] 1.5 Checks: the new tests, `test_suite`, `test_parsing`, ruff and bandit, the self-test and the offline preflight for both models.

  (2026-11-20: manifest 646 items, 1,292 OMPS attempts, `f6b106b5…`, every task equal to MC-115's OMPF task. Self-test 4/4 PASS: the first system message is dsh's prompt + omp's blocks, `b868301f…` (Qwen) and `32a43405…` (MiMo), as the offline capture; caps 4,096 and 16,000. 7 + 6 + 5 new tests; a recovered stall is now complete where the registered rule made it fatal; a halt writes loadable rows. Dry run on relabelled earlier draws (Qwen OMPF r3-r4, MiMo OMPF r1-r2 as OMPS): P2 0.00, P1 −0.41 (M) and +0.36 (S) = MC-115's drift, P3 = −P1; the original interaction reproduces 14.63 and 11.64. `diagnostic_prospective.ARMS` gains OMPS (appended; scored like OMPF), as MC-112 to MC-114 added theirs. ruff, bandit, test_parsing, test_suite 287 OK; MC-112 to MC-116 tests OK. Preflight for both models: harness and folders pass; card, frozen hashes, budget, smoke and pins wait for §2–§3.)

## 2. Smoke test (ask the owner first; the VPN for Qwen)

- [x] 2.1 `--smoke --execute` per model: 4 attempts in all, no benchmark item. Record the reports and their SHA-256 in the protocol.

  (2026-11-20, about 21:30 +07, owner's go "chạy smoke test đi". MiMo first, without the VPN (`8dc9d37b…`); then Qwen with the VPN open, closed right after (`fe4e2897…`). 4 of 4 complete, HTTP 200, no stall. Every first system message started with dsh's prompt and equalled the offline capture (Qwen `b868301f…`, MiMo `32a43405…`). Response models and body keys as each model's OMPF.)
- [x] 2.2 From the reports: the system-prompt pins and the budgets. Freeze `manifest_v1.json`.

  (Pins: the two hashes above. Budgets: 110,000,000 per model. Qwen: 72,004 × 1,292 × 0.7675 × 1.5 = 107.1M. MiMo: 80,036 × 1,292 × 0.6476 × 1.5 = 100.5M. The basis is in `protocol.smoke.budget_basis`, because the model blocks have a closed key set. Protocol `cc03b7ee…`. Manifest frozen: self-hash `8952e672…`, file `b4fef546…`; it differs from the build-time `f6b106b5…` only because the protocol hash is an input.)

## 3. Registration

- [x] 3.1 The MC-117 root block, the detail card and `registration.json`.

  (2026-11-20: the root block was appended to `measurement_card.md` with no other line changed. Detail card `docs/measurement_cards/MC-117-diagnostic-legal-agent-omp-prompt.md`. `registration.json` holds the frozen hashes, prompt files, smoke reports, code (`harness_flow.py` `f2e8c219…` included), the plan id and the report keys. Full preflight for both models: 8 of 8 gates pass, `endpoint_calls=0`. ruff, bandit, test_parsing and test_suite (287) OK; 25 MC-117 and flow tests OK; `openspec validate --strict` OK.)
- [ ] 3.2 With the owner's go, commit `pre-register MC-117`. Every preflight gate must pass for both models.

## 4. Run (ask the owner first)

- [ ] 4.1 Launch both models as `systemd-run --user` units (Qwen with the VPN), and use `--resume` after technical stops.
- [ ] 4.2 Record the runs in the detail card.

## 5. Analysis and record

- [ ] 5.1 Run the analysis once, and record the report's SHA-256 and the results.
- [ ] 5.2 Update the thesis draft and Notion, with the owner's go.
