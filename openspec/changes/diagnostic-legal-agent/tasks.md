Model and endpoint for every request task below: Qwen3.5-9B-65K (Q4_K_M GGUF on llama.cpp) through the IEC gateway over the openvpn3 `member-shared-tcp` tunnel, Chat Completions via dsh 0.2.2-rc.1 and the loopback proxy.

## 0. Owner approval

- [x] 0.1 The owner approves the design, or changes it. These choices are open to change:
  - the two instructions (design §6);
  - the request cap of 30 per attempt and the 300 s per-request timeout;
  - the statuses that count as wrong (§7);
  - the three Holm-adjusted questions, and the 2.24-point margin against MC-111's B (§11);
  - leaving dsh's compaction, repeated-tool reminder and persona as shipped (§3);
  - the smoke test (§10).

  Nothing below except 1.x is built until the owner approves.

  (2026-11-12: the owner approved the design unchanged: "duyệt".)

## 1. Corpus folder and provisions (offline)

- [x] 1.1 Build the corpus folder with whole texts, the added pages and the off-site texts, with fail-closed checks and tests.

  (2026-11-12:
  - **Folder.** `all_res/diagnostic_legal_agent/corpus_v1`: 310 files, 44,487,455 characters, none truncated; folder SHA-256 `5f3240a2…`.
  - **Added and off-site documents.** 6 pages added and 3 off-site texts (`added_documents_v1.json`, `offsite_documents_v1.json`).
  - **Checks.** The leak check passed.)
- [x] 1.2 Run the gold-aware coverage audit of the 81 items without MC-100 provisions, and the owner's spot-check of 14 of them.

  (2026-11-12:
  - **Audit.** 4 agent batches.
  - **Owner check.** 14 of 14 agreed; reviewer nttung245.)
- [x] 1.3 Freeze `data/diagnostic_legal_agent/item_provisions_v1.jsonl` from code, with anchor lines checked against the folder.

  (2026-11-12:
  - **Contents.** 134 items and 180 provisions: 126 `supports_gold`, 2 `contradicts_gold`, 6 `unclear`; 28 owner-labelled rows.
  - **Checks.** 22 module tests pass; ruff and bandit are clean.)

## 2. Harness, proxy and trajectory (offline)

- [x] 2.1 Write `dsh_profile_v1.yml` from the probe's patch, changing only the route `baseURL`. Write the runner's check of the install lockfile, the dsh version and the node version.

  (2026-11-12: done. Below the header comment, the profile differs from the probe's patch only in the `baseURL` line's comment. `check_harness` checks the lockfile, `dsh/package.json` 0.2.2-rc.1, node v24.20.0 and bwrap.)
- [x] 2.2 Implement `code_benchmark/dsh_proxy.py`, the proxy and the in-sandbox relay. Verify with tests against a local fake upstream:
  - the temperature is added, and a body that already has one is refused;
  - the key is swapped, and the dummy key never reaches the upstream;
  - the stream passes through unchanged;
  - the request cap gives `request_cap`;
  - timeouts, 4xx and 5xx are classified;
  - a change of the response model id pauses the run;
  - the log records each request and response.

  (2026-11-12: `dsh_proxy.py`, `dsh_relay.py`, `fake_chat_upstream.py`; `test_dsh_proxy.py` has 10 tests, all passing.
  - **Gateway header.** The proxy also adds `x-9router-token-saver: off`, as MC-90 to MC-111 did.
  - **A race, fixed.** Stopping the proxy now joins every handler, so all records exist before they are read.)
- [x] 2.3 Implement the sandbox launcher: bwrap with no network, tmpfs HOME and DSH_HOME, `env -i`, the read-only folder at `/work/van-ban-phap-luat`, and the relay. Run dsh end to end against the fake server with scripted `glob`, `grep` and `read` calls. Record the exact `read` and `grep` result formats from that run.

  (2026-11-12: done, with isolation tightened beyond the probe; see design §4.
  - **Sandbox check.** `read` of the repository `.env` gives "not found", and `grep` over `/home` finds nothing.
  - **Selftest.** `run_legal_agent --selftest` passes. A normal attempt is complete with every hit; the cap gives `request_cap`; a 503 is technical. Temperature 1.0 is in every request sent.
  - **Finding.** dsh's `--json` tool results are previews of about 6 KB, while the model receives up to about 50 KB. Hits therefore come from the proxy's recorded request bodies (design §9).)
- [x] 2.4 Implement the trajectory parser and the `seen`, `read` and `opened` hit rules in `diagnostic_legal_agent.py`. Test them with the result formats recorded in 2.3, including prefix stripping and a heading found by `grep` only.

  (2026-11-12: `corpus_file`, `parse_read`, `parse_grep`, `model_observations` and `provision_hits`, with 5 tests. The tests cover a result removed by compaction, a tool error, a result that never reached the model, a heading found by grep only, and a spilled grep file read back.)

## 3. Prompts, manifest, runner and analysis (offline)

- [x] 3.1 Write `agent_prompts_v1.json` and `protocol.json`. Build `manifest_v1.json`: 536 attempts, item-major, DSH-r1, DSHF-r1, DSH-r2 and DSHF-r2 for each item, self-hashed. Verify by test:
  - each task equals the instruction, a blank line, then the frozen B prompt;
  - no task carries gold, a provision or a label.

  (2026-11-12:
  - **Prompt check.** Each base prompt must hash to the prompt MC-111's B sent for the item, and all 134 do.
  - **Manifest.** Frozen once, as a draft. It changes when the smoke test sets the budget and the response model id in `protocol.json`, so it is frozen again at 4.2.
  - **Smoke questions.** `smoke_questions_v1.json` holds the three questions written for the smoke test and a three-file fictional folder.)
- [x] 3.2 Implement `code_benchmark/run_legal_agent.py` on the campaign engine. It has the statuses of design §7, the budget guard, `condition.json`, per-attempt directories (events, stderr, session files, proxy log) and every registration gate. Without `--execute` it only runs a preflight: it rebuilds the folder, checks the provisions and checks the hashes, with `endpoint_calls=0`. Test it with a mocked attempt function.

  (2026-11-12:
  - **Tests.** `test_run_legal_agent.py` covers classification, sandbox binds, the request row and the budget stop.
  - **Preflight.** About 30 s, including a fresh folder rebuild. `harness_and_folder` and `endpoint_identity` pass. The registration gates, the budget and the response model id fail, as expected before 4 and 5.
  - **End to end.** An engine run of 4 real items with the fake server went through scoring and hit detection.)
- [x] 3.3 Implement `code_benchmark/analyze_legal_agent.py` (plan `diagnostic-legal-agent-v1`), and test it on synthetic rows: the three questions, Holm, the margin rule and the descriptive blocks.

  (2026-11-12: tests cover the margin rule in both directions, behaviour, retrieval and accuracy by retrieval. CI gates: ruff and bandit are clean, `test_parsing` passes, and `test_suite` has 287 tests passing. The related suites have 168 tests passing.)

## 4. Smoke test on IEC (no benchmark item)

- [x] 4.1 Ask the owner before opening the VPN. Run the three smoke questions of design §10 once each through the full path. Record:
  - whether tool calls parse;
  - the request bodies as sent, with temperature 1.0 and no other change;
  - the response model id;
  - steps, requests, tokens and time per attempt.

  Compute nothing as a score. If tool calls fail, stop and report to the owner.

  (2026-11-13: the owner said "okay". The VPN was open from 00:01:07 to 00:01:33 +07.
  - **Report.** `all_res/diagnostic_legal_agent/smoke/20261112T170115Z/smoke_report.json`, SHA-256 `e9db8bcd…`.
  - **Tool calls.** They parse. Every request carried temperature 1.0 and no other added field.
  - **Model id.** `Qwen3.5-9B-65K`, the alias, not the GGUF path. No reasoning text came back.
  - **Cost.** smoke-1 (DSHF, synthetic folder): 6 requests, 7,170 tokens. smoke-2 (DSHF, corpus): 3 requests, 9,988 tokens. smoke-3 (DSH): no tool call, 1,036 tokens. 0.4–3.0 s per request.
  - **Answers.** The frozen extractor read a letter from all three.)
- [x] 4.2 Set the budget guard to 1.5 times the projected total, and write it into `protocol.json`.

  (2026-11-13: budget 50,000,000 and `expected_response_model` `Qwen3.5-9B-65K`, written into `protocol.json` with their basis.
  - **Budget basis.** The smoke test's own projection is 4.4 million, but its questions are easy. The basis is a scenario of five requests and about 80,000 re-sent tokens per searching attempt, × 1.5.
  - **Manifest.** Re-frozen: `6e760d34…`.)

## 5. Registration and run (MC-112)

- [x] 5.1 Write the MC-112 root block and `docs/measurement_cards/MC-112-diagnostic-legal-agent.md`, and `registration.json` with every hash of design §12. Show the card to the owner.

  (2026-11-13:
  - **Card.** The root block is appended at the end of `measurement_card.md`, and `build_benchmark_reports.card_index` parses it.
  - **Registration.** `registration.json` holds the 13 frozen hashes, the manifest file hash, the smoke report hash and the 13 report keys.
  - **Preflight.** With a fresh folder rebuild, all 7 gates pass, with `endpoint_calls=0`.)
- [x] 5.2 With the owner's go, commit `pre-register MC-112` before any benchmark-item request.

  (2026-11-13: the owner said "commit rồi chạy đi". Committed as `b894881` on dev, holding only the MC-112 hunk of `measurement_card.md`.)
- [x] 5.3 With the owner's go and the VPN open, launch as a `systemd-run --user` unit. On completion, append the run record (facts of execution only) to the detail card.

  (2026-11-13:
  - **Launch 1.** 11:24 +07. The machine shut down at 12:38 with 517 of 536 attempts complete.
  - **Launch 2.** `--resume` at 14:03, after the owner said "continue". It finished 536 of 536 by 14:06, with no technical failure, 27.1M tokens and 1,972 requests.
  - **VPN.** Closed by the watcher at 14:06:56.
  - **Run record.** Appended to the detail card.)
- [x] 5.4 Run the registered analysis once and record its report hash in the run record.

  (2026-11-13 14:07 +07: report `5da875d1…`, with the 13 registered keys.)
