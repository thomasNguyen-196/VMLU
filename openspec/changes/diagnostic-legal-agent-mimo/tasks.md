Model and endpoint for every request task below: `mimo-v2.6-flash` through OpenCode Go (`https://opencode.ai/zen/go/v1`, chat completions), thinking at the provider's default. Agent arms go through dsh 0.2.2-rc.1 or omp 18.0.0 and MC-112's loopback proxy; direct arms use MiMo's direct request. No VPN.

## 0. Owner decisions

- [x] 0.1 The owner chooses the second model and approves the design.

  (2026-11-19: the owner chose MiMo-V2.6-Flash over GLM-5.3-Flash; said thinking cannot be turned off, only its level set; the probe found the level has no effect on this route either. The owner approved ("duyệt"): thinking at the provider's default, cap 16,000 per response, context window 65,024 kept, MC-115's whole design in one card.)

## 1. Build (offline)

- [x] 1.1 `dsh_profile_mimo_v1.yml` and `omp_config_mimo_v1.json`: MC-112's profile and MC-113's configuration with only the model route replaced (design §2).

  (2026-11-19: scripted-server capture: dsh sends `max_completion_tokens` 16,000; omp's body keys and system prompt `616bebaf…` recorded; omp compacts between 56,000 and 57,000 reported tokens with either configuration.)
- [x] 1.2 `diagnostic_legal_agent_mimo.py`: protocol loader, harness overlays and manifest builder (design §3), with tests.

  (2026-11-19: 646 items, 3,876 attempts (DSHF 1,292, OMPF 1,292, B 492, C 800); 134 items on corpus_v1; every task, input and gold equals MC-115's. 7 tests.)
- [x] 1.3 `run_legal_agent_mimo.py`: route, per-try session, provider errors, direct request, gates, condition, self-test and smoke test (design §2, §4–§6), with tests.

  (2026-11-19: 14 tests with a mocked client. Self-test 4/4 PASS against scripted servers, including omp's registered shape and system prompt and the 16,000 cap in every dsh and omp request.)
- [x] 1.4 `analyze_legal_agent_mimo.py`: the registered analysis (design §8), with tests on synthetic cells.

  (2026-11-19: 4 tests. Dry run on MC-115's draws 3–4 relabelled as 1–2, only to exercise the code: M1 −5.89, M2 +1.83, S1 −0.95, S2 +15.98, which equal MC-115's draws-3–4-only values; Qwen's draws 1–4 give M1 −7.42 and S1 −2.62, as MC-115 reported.)
- [x] 1.5 Checks: the new tests, `test_suite`, `test_parsing`, MC-115's tests, ruff and bandit on the new files, the self-test and the offline preflight.

  (2026-11-19: 25 new tests OK; test_suite 287 OK; test_parsing OK; MC-115's module and runner tests OK; ruff and bandit clean; preflight endpoint_calls=0, with card, detail card, frozen hashes, budget, smoke and pins waiting for §2–§3.)

## 2. Smoke test (OpenCode Go; ask the owner first)

- [x] 2.1 Run `--smoke --execute`: 6 attempts, no benchmark item (design §6). Record the report and its SHA-256 in the protocol.

  (2026-11-19 ~10:40 +07, owner's go ("đồng ý"): 6 of 6 complete, every HTTP status 200, model id `mimo-v2.6-flash` on every request, omp's system prompt as pinned in both omp attempts, largest completion 172 tokens, reasoning 28–178 tokens per attempt. Report `20261119T034032Z/smoke_report.json`, SHA-256 `a4bafda5…`.)
- [x] 2.2 From the report: the response-model pins (dsh, omp, direct) and the budget guard; the owner decides the cap if any request ended at 16,000. Freeze `manifest_v1.json`.

  (2026-11-19: pins `mimo-v2.6-flash`; no request near the cap, so 16,000 kept; budget 470,000,000 (310.0M projected from MC-115's real costs × the smoke's MiMo-to-Qwen ratios, × 1.5, rounded up). Protocol `8eaf86f5…`; manifest frozen, self-hash `c81a6fc9…`, file `841929df…`.)

## 3. Registration

- [x] 3.1 Root block MC-116 in `measurement_card.md`, the detail card and `registration.json` (with the report keys).

  (2026-11-19: offline preflight, all 8 gates PASS, endpoint_calls=0.)
- [x] 3.2 With the owner's go, commit `pre-register MC-116`. Every preflight gate must pass.

  (2026-11-19, owner "yes": commit db0b7ca on dev, all 8 gates PASS.)

## 4. Run (OpenCode Go; ask the owner first)

- [x] 4.1 Launch `--execute` as a `systemd-run --user` unit; `--resume` after a technical stop or a usage limit.

  (2026-11-19: launch 1, unit `mc116-mimo-launch1`, started 10:50 +07. At 12:56 +07: 779 of 3,876 attempts recorded, no duplicate run key; 5 technical (network: `RemoteDisconnected`/`SSLEOFError` from the provider between 12:28 and 12:33 +07), left for `--resume`; 10 complete at the 16,000 cap (`answer_cap`).)

  (Launch 1 halted at 18:36 +07 after 2,941 complete: at 18:30–18:31 OpenCode Go sent two HTTP 200 streams with no model-bearing chunk (one dsh request idled 300 s), and MC-112's proxy reads a missing model id as `model_drift`, which is fatal. The halted-before-send row that followed has no `shard`, `lane`, `model_id` or `protocol_id` (`_blocked_row`), so the engine's progress print raised `KeyError` and the 3 attempts still in flight were never written to the ledger; their `try-1` folders stay on disk and they re-run as `try-2` with fresh sessions. Resume 2 (16:06 UTC) was refused before any request (`checkpoint condition drift`, the same row); the row was moved verbatim to `halted_rows_unloadable.jsonl`, the original ledger kept as `attempts.launch1-original.jsonl` (see `ledger_repair_20261119.json`). Resume 3, unit `mc116-mimo-resume3`, from 23:10 +07 with the registered runner unchanged; the 8 technical attempts re-ran and completed.)

  (Resume 3 halted at 23:31 +07 after 2,969 complete, the same way: `BIDLQA-TR-1293:OMPF-r2`'s third request got a 30,645-byte stream with one chunk and no model id after 924 s, as `OMPF-r1` had in launch 1; omp re-sent and answered, but the proxy had recorded `model_drift`. From 00:01 +07 on 2026-11-20 the unit `mc116-mimo-relauncher` (`all_res/diagnostic_legal_agent_mimo/run/mc116_relauncher.py`, operational, owner's go to resume after stalls) repeats the manual step: it moves `halted_before_send` rows aside (backup and note each time) and resumes only when every fatal row since the last launch is such a row or a `model_drift` whose drift records all lack a model id. Any other halt (429, 401–404, a real model change, budget, outage) stops it; at most 6 launches.)
- [x] 4.2 Record the run in the detail card: start, end, outcomes, volume, model ids, cost estimate, halts.

  (2026-11-20: complete at 06:44 +07, 3,876 of 3,876 final; run record appended to the detail card. 175.9M reported tokens of 470M; cost estimate USD 8.94; `mimo-v2.6-flash` in every attempt.)

## 5. Analysis and record

- [x] 5.1 Run the analysis once; record the report's SHA-256 and the results in the card.

  (2026-11-20 ~09:35 +07: report `b6f8a7cb…`. M1 OMPF − DSHF +5.69 [3.05; 8.54], Holm p 0.0002, OMPF better; M2 DSHF − B +4.07 [−0.41; 8.74], Holm p 0.109, no clear difference; S1 OMPF − DSHF +7.36 [4.90; 9.65], Holm p 0.0001, OMPF better; S2 DSHF − C +26.47, Holm p 0.0001, DSHF better. Beside: the harness gap reverses from Qwen's (−8.94 M, −4.28 S on draws 1–2); MiMo minus Qwen in the gap +14.63 [9.15; 20.12] M and +11.64 [7.71; 15.43] S.)
- [ ] 5.2 Update the thesis draft and Notion with the outcome, as for MC-115.
