Model and endpoint for every request task below: Qwen3.5-9B-65K (Q4_K_M GGUF on llama.cpp) through the IEC gateway over the openvpn3 `member-shared-tcp` tunnel. Agent arms go through dsh 0.2.2-rc.1 or omp 18.0.0 and the loopback proxies; direct arms use the campaign request (Responses API).

## 0. Owner decisions

- [x] 0.1 The owner approves the design or changes it. The open choices are at the end of design §Decisions: baseline draws, primary data, the margin against B, the smoke test.

  (2026-11-16: the owner answered "duyệt": all four defaults kept (B/C get draws 3–4; primary tests on 4-draw means; margin 2.24 on M1–M3; a 4-attempt smoke test), with the go for the smoke test.)

## 1. Build (offline)

- [x] 1.1 `diagnostic_legal_agent_draws.py`: protocol loader and manifest builder (design §3), with tests.

  (2026-11-16: 646 items, 3,876 attempts (DSHF 1,292, OMPF 1,292, B 492, C 800); 134 items on corpus_v1, 512 on corpus_v2. All three earlier manifests rebuild to their frozen files. Every one of the 3,876 prompts has the SHA-256 of its arm's draw-1 row in MC-111's, MC-112's, MC-113's or MC-114's score file. 9 tests.)
- [x] 1.2 `run_legal_agent_draws.py`: per-item folder, gates, condition, smoke test, scoring (design §2, §4, §5), with tests.

  (2026-11-16: 6 tests. Adds a `smoke_passed` gate: every registered smoke report must hash as registered, with every attempt complete and omp's system prompt matching MC-113's.)
- [x] 1.3 `analyze_legal_agent_draws.py`: the registered analysis (design §7), with tests on synthetic cells.

  (2026-11-16: 9 tests. Dry run on a scratch copy of draws 1-2 relabelled as 3-4, only to exercise the code: the means equal MC-112/113/114's.)
- [x] 1.4 `protocol.json` and the frozen `manifest_v1.json`.

  (2026-11-16: `protocol.json` written. The manifest is frozen after 2.1, because the smoke report's hash goes into the protocol, whose hash goes into the manifest. Frozen after the smoke test: protocol `9df2bd5f…`; manifest self-hash `81f28256…`, file `217ceab4…`.)
- [x] 1.5 Checks: the new tests, `test_suite`, ruff and bandit on the new files, the selftest against scripted servers, and the offline preflight.

  (2026-11-16: 24 new tests OK; test_suite 287 OK; test_parsing OK; MC-114's runner and module tests OK; ruff and bandit clean. Selftest 4/4 PASS, including omp's registered system prompt. Preflight with corpus_v2's fresh rebuild: endpoint_identity, budget_set, reused_pins_set PASS, both folders hash as registered; card, detail card, frozen hashes and smoke wait for §2-§3.)

## 2. Smoke test (needs the VPN; ask the owner first)

- [x] 2.1 Run `--smoke --execute`: 4 attempts, no benchmark item. Record the report and its SHA-256 in the protocol.

  (2026-11-16 14:40–14:42 +07, owner's go ("duyệt"); VPN opened and closed by the script. 4 of 4 complete, omp's system prompt matched in both omp attempts, the `smoke-s2` dsh attempt opened a file only corpus_v2 holds. Report `20261116T074049Z/smoke_report.json`, SHA-256 `46d24a6b…`.)

## 3. Registration

- [x] 3.1 Root block MC-115 in `measurement_card.md`, the detail card and `registration.json`.

  (2026-11-16: offline preflight, all 8 gates PASS, endpoint_calls=0; 24 new tests, test_suite 287, test_parsing, ruff and bandit OK.)
- [ ] 3.2 With the owner's go, commit `pre-register MC-115`. Every preflight gate must pass.

## 4. Run (needs the VPN; ask the owner first)

- [ ] 4.1 Launch `--execute --tunnel-dns <in-tunnel DNS>` as a `systemd-run --user` unit with a VPN watcher; `--resume` after a technical stop.
- [ ] 4.2 Record the run in the detail card: start, end, outcomes, volume, model ids, proxy checks.

## 5. Analysis and record

- [ ] 5.1 Run the analysis once; record the report's SHA-256 and the results in the card.
- [ ] 5.2 Update the thesis draft (§4.8) and Notion with the outcome, as for MC-114.
