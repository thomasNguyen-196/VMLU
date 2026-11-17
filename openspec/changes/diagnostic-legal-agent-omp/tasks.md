Model and endpoint for every request task below: Qwen3.5-9B-65K (Q4_K_M GGUF on llama.cpp) through the IEC gateway over the openvpn3 `member-shared-tcp` tunnel, Chat Completions via `omp` 18.0.0 and the loopback proxy.

## 0. Owner approval

- [x] 0.1 The owner approves the design, or changes it. The open choices are at the end of design §Decisions:
  - forced arm only;
  - omp's retries switched off;
  - omp's read, grep and compaction left as shipped;
  - the 2.24-point margin on the harness question;
  - smoke-4.

  Nothing below is built until the owner approves.

  (2026-11-13: offline probe done before this proposal, with no model and no network. Evidence is in `all_res/diagnostic_legal_agent_omp/probe_20261113/`. The owner approved the design unchanged, with all five defaults: "duyệt".)

## 1. omp configuration and parser (offline)

- [x] 1.1 Write `data/diagnostic_legal_agent_omp/omp_config_v1.json` (design §3). Write the runner's check of the binary SHA-256 and `omp --version`. Verify against the scripted server:
  - the request keys equal the probe's eight;
  - `max_completion_tokens` is 4096;
  - there is no temperature and no reasoning field;
  - only `read`, `grep` and `glob` are offered;
  - with `retry.enabled: false`, a 503 gives exactly one request;
  - with `startup.checkUpdate: false`, nothing is attempted besides the relay.

  (2026-11-13:
  - **Config.** `omp_config_v1.json` is written, and `omp config list` shows `retry.enabled false` and `startup.checkUpdate false`. `check_harness` checks the binary SHA-256 `69065aef…`, `omp/18.0.0` and the config hash.
  - **Requests.** Keys, cap, no temperature and the three tools are as in the probe.
  - **Retries.** `retry.enabled: false` does not stop omp's retry of a 503: four retries in about 10 s. The proxy now refuses every request after a technical failure (design §5). With that, the selftest's 503 case is technical, with the next request refused.
  - **Session.** `--no-session` was dropped, because with it omp's spill read-back fails (design §3).)
- [x] 1.2 Record omp's end-of-attempt events against the scripted server, for each case:
  - a normal answer;
  - stop at the cap (`finish_reason: length`);
  - the proxy's 429 at the request cap;
  - a 4xx;
  - a 5xx;
  - `--max-time`.

  Fix the status mapping of design §7 in tests.

  (2026-11-13: `--selftest` passes all six cases. `--max-time` ends with stop reason `aborted` ("Deadline exceeded") and exit 0, and is mapped to technical `wall_clock`. omp also retries the cap's 429; the attempt is still `request_cap`. The mapping is fixed in `test_run_legal_agent_omp.Classify`.)
- [x] 1.3 Fill the context against the scripted server to see which compaction method fires, and whether it sends its own model request. Record the result in design §9 and in the parser's tests. Change nothing in omp's compaction.

  (2026-11-13:
  - **Threshold.** Compaction fires at about 56,800 reported tokens.
  - **Requests.** The handoff request adds `tool_choice: none` and keeps the 4096 cap. The short-summary fallback has no tools, another system prompt and a cap of 512. The request-shape rule was widened to fit both (design §5); unchanged, it would have paused the run at the first compaction.
  - **Elided results.** Shaking can replace a fresh read before the model sees it, which counts as `opened` only.)
- [x] 1.4 Implement `code_benchmark/omp_trajectory.py`, which yields MC-112's observation shape. Test it with the probe's recorded results:
  - a whole-file read with an elided middle;
  - a selector read (`:40-60`, `:64`, `:raw`);
  - grep blocks with match and context lines;
  - grep paging;
  - glob;
  - an `artifact://` read-back of a spilled read and of a spilled grep;
  - a directory read;
  - a URL or `omp://` read;
  - a tool error;
  - a result that never reached the model.

  Feed the observations to MC-112's `provision_hits` unchanged.

  (2026-11-13: `omp_trajectory.py`, with 11 tests covering every case above and a shaken stub. On the probe's recorded runs, the hits are as expected.)

## 2. Runner, proxy checks and analysis (offline)

- [x] 2.1 Implement `code_benchmark/run_legal_agent_omp.py`.
  - **Contents:** the `omp` sandbox (design §4); the proxy subclass with the four request-shape checks (design §5); the status mapping; the manifest builder; the gates; `--execute`, `--resume`, `--selftest` and `--smoke`.
  - **Preflight.** Without `--execute`, only a preflight runs: it rebuilds the folder, checks the provisions and checks every hash, with `endpoint_calls=0`.
  - **Tests,** with the scripted server:
    - the sandbox cannot read the repository `.env` or `/home`;
    - each request-shape check refuses and pauses;
    - the task check passes byte for byte;
    - the budget stop works.

  (2026-11-13: done. `test_run_legal_agent_omp.py` has 20 tests. Preflight takes about 34 s with a fresh folder rebuild. `harness_and_folder` and `endpoint_identity` pass. The card, hashes, budget, response model and system-prompt gates fail, as expected before 3 and 4.)
- [x] 2.2 Build `manifest_v1.json`: 268 attempts, item-major, self-hashed. Test that each task's SHA-256 equals MC-112's DSHF task hash for its item, and that no task carries gold, a provision or a label. Add `OMPF` to `diagnostic_prospective.ARMS`.

  (2026-11-13: frozen as a draft, self-hash `7514d441…`. It changes when the smoke test fills `protocol.json`, so it is frozen again at 3.2. All 268 task hashes equal MC-112's DSHF hashes. `OMPF` is added.)
- [x] 2.3 Implement `code_benchmark/analyze_legal_agent_omp.py` (plan `diagnostic-legal-agent-omp-v1`). Test it on synthetic rows:
  - the two questions;
  - Holm;
  - the margin in both directions;
  - the paired retrieval comparison with DSHF;
  - accuracy by retrieval.

  (2026-11-13: done.
  - **Tests.** Covered in `test_run_legal_agent_omp.Analysis`.
  - **Dry run.** Fake OMPF rows, MC-112's DSHF relabelled, went through `build_report` end to end. It reproduced MC-112's DSHF hits (seen 61.57, read 53.73, opened 69.03) and DSHF − B = −1.49.
  - **Context arms.** MC-111's round-1 file has B, K, K10 and O only, so SEL is not in the context.)
- [x] 2.4 Check the CI gates and the related suites: ruff, bandit, `test_parsing`, `test_suite`, and MC-112's tests, which must pass unchanged.

  (2026-11-13:
  - **Lint and security.** ruff and bandit are clean on the change's files. ruff's remaining errors are all in other sessions' untracked `.codex/` and `notebooks/` files.
  - **Tests.** `test_parsing` passes, and `test_suite` has 287 tests passing. The related suites (omp trajectory, omp runner, MC-112's runner, proxy and module) have 80 tests passing.)

## 3. Smoke test on IEC (no benchmark item)

- [x] 3.1 Ask the owner before opening the VPN. Run smoke-1 to smoke-3 with the OMPF instruction, and smoke-4 (design §10), once each through the full path. Record:
  - whether tool calls parse;
  - the request bodies as sent;
  - the system-prompt hash, which must equal the probe's `3d04a885…`;
  - the response model id;
  - whether reasoning text returns;
  - whether the 4,096 cap holds;
  - steps, requests, tokens and time.

  Compute nothing as a score. If tool calls fail, the prompt differs or the cap is ignored, stop and report to the owner.

  (2026-11-13: the owner said "okay". VPN open 21:24:14–21:25:34 (+07). Report `all_res/diagnostic_legal_agent_omp/smoke/20261113T142416Z/smoke_report.json` (`20c27051…`).
  - **Tool calls** parse: smoke-1 and smoke-2 grepped twice each, smoke-3 read the folder listing and one file, smoke-4 called glob and read.
  - **Requests.** The system-prompt hash equals the probe's `3d04a885…` on all four. The task arrived byte for byte. Only the probe's eight keys were received; temperature 1.0 was sent. No reasoning text. Response model `Qwen3.5-9B-65K`.
  - **Cap.** smoke-4 stopped with `length` at 4,096 completion tokens and mapped to `answer_cap`.
  - **Cost.** 12,854 / 15,601 / 49,272 / 20,738 tokens; 3–4 requests; 7–50 s per attempt.)
- [x] 3.2 Write the budget guard (1.5 times the projected total), `expected_response_model` and the system-prompt hash into `protocol.json`, with their basis. Re-freeze the manifest.

  (2026-11-13: budget 70,000,000 = MC-112 DSHF's actual 25.7M × 1.79, the larger smoke cost ratio omp/dsh, × 1.5, rounded up. `expected_response_model` `Qwen3.5-9B-65K`; `system_prompt_sha256` `3d04a885…`. Manifest re-frozen: self-hash `1fadcab9…`, file `a4c5eef0…`. Preflight: budget, response model and system-prompt gates now pass; only the card, detail card and frozen hashes wait for 4.1.)

## 4. Registration and run (MC-113)

- [x] 4.1 Write:
  - the MC-113 root block;
  - `docs/measurement_cards/MC-113-diagnostic-legal-agent-omp.md`;
  - `registration.json`, with every hash of design §12.

  Show the card to the owner.

  (2026-11-13, the owner said "okay": root block appended after MC-112; detail card written; `registration.json` holds the 15 frozen hashes, the manifest file, the system prompt, the smoke questions and report, the runner, parser and analysis, and the 14 report keys. Full preflight with a fresh folder rebuild: all eight gates pass, `endpoint_calls=0`.)
- [x] 4.2 With the owner's go, commit `pre-register MC-113` before any benchmark-item request. Stage only the MC-113 hunk of `measurement_card.md`.
- [x] 4.3 With the owner's go and the VPN open, launch as a `systemd-run --user` unit. When it completes, append the run record (facts of execution only) to the detail card.
- [x] 4.4 Run the registered analysis once and record its report hash in the run record.

  (2026-11-13: the owner said "yes". Pre-registered as `9e8906f`. Unit `mc113-legal-agent-omp-launch1` ran 21:38:47–22:52 +07: 268/268 final in one launch (267 `complete`, 1 `answer_cap`), no technical failure, 1,308 requests, 21.9M tokens. omp cancelled 12 parallel handoff requests at the end of 12 attempts, all of which completed (run record). Analysis run once at 22:52; report `b28270cb…`. Run record appended to the detail card.)
