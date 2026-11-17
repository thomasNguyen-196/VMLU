Model and endpoint for every request task below: Qwen3.5-9B-65K (Q4_K_M GGUF on llama.cpp) through the IEC gateway over the openvpn3 `member-shared-tcp` tunnel. Agent arms go through dsh 0.2.2-rc.1 or omp 18.0.0 and the loopback proxies; direct arms use the campaign request (Responses API).

## 0. Owner decisions

- [x] 0.1 The owner approves the design, or changes it. The open choices are at the end of design §Decisions: Part S size, pooled Part M, the M1 margin, the Part S Holm family, and DSH in Part S. Nothing in §2–§6 is built until the owner approves.

  (2026-11-14: approved unchanged with all five defaults: "duyệt". That means Part S at 400 items, pooled Part M, the 2.24-point margin on M1, Holm over S1–S3, and DSH kept in Part S.)
- [x] 0.2 The owner returns the spot-check labels for the 14 sampled VMLU items (`all_res/diagnostic_legal_agent_v2/audit/review_sheet.md`). They are recorded in `audit/review_labels.json` with the reviewer's name.

  (2026-11-14: at the owner's request Claude proposed a label and a reason for each item; the owner approved all 14 unchanged ("duyệt"). All 14 agree with the audit agents. The file records `proposed_by` and says the check is not independent of the audit agents, which were also Claude. Closest calls: 38-0014, 40-0005, 45-0003. 42-0004 stays off the stale-gold list: Luật Viên chức 2025 is not in corpus_v2.)

## 1. Inputs (offline)

- [x] 1.1 Coverage audit of the 112 VMLU law items: four gold-aware agents; every quote checked by code; 23 missing pages fetched and stored.

  (2026-11-14: 86 `supports_gold`, 4 `unclear`, 1 `contradicts_gold`, 21 `no_provision`.)
- [x] 1.2 `added_documents_v2.json` (25 pages) and `diagnostic_legal_agent_v2.py`, with 8 tests.

  (2026-11-14: corpus_v2 has 335 files, folder SHA-256 `2b40c1c7…`. All corpus_v1 files are unchanged. Leak check passes with one recorded exemption.)
- [x] 1.3 ViBidLQA mapping. The decree half is excluded. 926 law items are usable over 90 articles. Provisions dry run: all anchors resolve.
- [x] 1.4 Write `item_provisions_v2.jsonl` (`provisions --folder`) after 0.2.

  (2026-11-14: 1,038 items (112 VMLU, 926 ViBidLQA) and 1,100 provisions; every anchor resolves. Manifest frozen: 512 items, 4,896 attempts, SHA-256 `c494674c…`. Preflight: harness_and_folder, endpoint_identity and reused_pins pass; the card, detail card, frozen hashes and budget wait for 4.1 and 5.1. Selftest 4/4 and the 25 tests still pass.)
- [x] 1.5 `agent_prompts_v2.json` (design §4) and the Part S sample (design §1), with its per-split counts and SHA-256.

  (2026-11-14:
  - **Prompts by reference.** `agent_prompts_v2.json` references MC-112's prompt file (`3f760fd1…`) and MC-96's protocol (`a8c5d481…`) by SHA-256, so the texts are reused rather than copied. Tests check that the tasks equal `la.arm_task` and that the closed-book prompt equals `diagnostic_k2.closed_book_prompt` byte for byte.
  - **The sample.** 400 of 926 items: train 256, val 62, test 82.
  - **ViBidLQA items keep the project's frozen items.** Val and test use main-v1's ids and prompts; train uses MC-95's. O's prompt is therefore main-v1's frozen reading prompt, and C's question is the text MC-96 sent.
  - **Protocol.** `protocol.json` is written. It also fixes the descriptive stale-gold list: 13 VMLU items whose audit note says the current law in the folder changes or repeals the answer.
  - **Manifest.** Freezing waits for 1.4.)

## 2. Runner (offline)

- [ ] 2.1 `run_legal_agent_v2.py`:
  - the manifest (design §2 order and run identity);
  - dispatch per arm: dsh path, omp path or campaign request;
  - the corpus_v2 rebuild and provision check;
  - the gates;
  - statuses;
  - scoring (design §7);
  - the budget guard;
  - `--resume`.

  It imports MC-112's and MC-113's modules without editing them. Add C to `diagnostic_prospective.ARMS`.

  (2026-11-14: done.
  - **Dispatch.** One gate and shared guards. dsh attempts go through `rla.run_sandboxed`/`classify`; omp attempts through `rlo.run_sandboxed`/`rules_for`/`classify`, keeping MC-113's registered system-prompt and task checks; direct arms through `pr.make_request`.
  - **Scoring.** `dp.score_arm_rows`, then vi-reading-v3 for part S, with the v2 values and gold-token recall kept beside.
  - **C added** to `dp.ARMS`.)
- [x] 2.2 `--selftest` against scripted fake servers: one MC and one span task through each harness.

  (2026-11-14: 4/4 PASS. Statuses, temperature 1.0, provision hits and span F1 are all correct, and omp's system prompt still matches MC-113's registered hash on this host. The cap and 503 cases are MC-112's and MC-113's own selftests, whose paths are unchanged. The direct path is unit-tested with a stub instead of a fake Responses server.)
- [x] 2.3 Offline tests: manifest order and identity, task bytes (OMPF = DSHF), span scoring of verbose and labelled answers, status mapping, gate refusals. CI-clean: ruff, bandit and `test_suite`.

  (2026-11-14:
  - **Tests.** `test_diagnostic_legal_agent_v2.py` has 13 tests. `test_run_legal_agent_v2.py` has 12, for dispatch, guards, halt and scoring, plus the analysis tests listed in 3.1.
  - **Checks.** Ruff and bandit on `code_benchmark` are clean, `test_suite` passes 287, and MC-112's and MC-113's tests still pass.)

## 3. Analysis (offline)

- [x] 3.1 `analyze_legal_agent_v2.py`, plan `diagnostic-legal-agent-v2` (design §11). It takes pooled inputs by registered SHA-256 and uses Holm per part. Tests on synthetic scores, including a changed reference score file.

  (2026-11-14: done. Its tests check Holm, the margin, coverage and the reference-hash refusal. The report keys are registered at 5.1.)

## 4. Smoke test (needs the VPN; ask the owner first)

- [x] 4.1 `smoke_questions_v2.json` (design §10). Run DSHF and OMPF once each on the three questions.
  - **Record:** response model ids, tool calls, span scoring, and cost per attempt.
  - **Set from it:** the budget (1.5 × projection), written into `protocol.json`.

  (2026-11-14, done in two runs, each with the owner's go to open the VPN:
  - **Run 1,** 20:40–21:03 (`smoke/20261114T135954Z`, `45ed162b…`). The VPN took 19 minutes to connect, with 224 reconnects. 5 of 6 attempts completed. smoke-s1 with dsh was technical: the proxy's first upstream connection timed out after 132 s. Per the spec the owner was told, and agreed to a re-run.
  - **Run 2,** 21:42–21:44 (`smoke/20261114T144335Z`, `d2e70a7d…`): 6 of 6 completed.
  - **Checks.** omp's system-prompt sha matched MC-113 in all 6 omp attempts. The model id was `Qwen3.5-9B-65K`. Span scoring works.
  - **Budget: 550,000,000,** following MC-113's method: MC-112/113's real costs scaled by the smoke's span/MC ratios (dsh 2.12, omp 2.25). Projection 360.1M × 1.5. Expected duration is about 13–17 h, not the design's 10 h.
  - **Manifest re-frozen** for the new protocol hash: `426d390f…`.)

## 5. Card and registration

- [x] 5.1 Write the MC-114 root block (appended to `measurement_card.md`, staging only its hunk), the detail card and `registration.json`. The full preflight must show every gate passing.

  (2026-11-14: root block appended, detail card `docs/measurement_cards/MC-114-diagnostic-legal-agent-v2.md` and `registration.json` (21 frozen hashes, smoke reports, code, 12 report keys) written. Preflight: all 7 gates PASS, endpoint_calls=0. Tests: 312 OK; ruff clean.)
- [x] 5.2 Commit `pre-register MC-114` with the owner's go.

  (2026-11-14: `a56ea7a`, owner "yes"; only the MC-114 root hunk staged.)

## 6. Run and analysis

- [x] 6.1 Run as a `systemd-run --user` unit with a VPN watcher. Interrupted launches resume with `--resume` as new units.

  (Launch 1, unit `mc114-legal-agent-v2-launch1`, 2026-11-14 22:00:36 to 2026-11-15 05:18:51 +07: 4,896 of 4,896 attempts final, no technical failure, 131.4M of 550M tokens. Watcher `mc114-watch` closed the VPN at 05:19:39.)
- [ ] 6.2 Add the run record to the detail card. Run the analysis once and commit the record and the report hash.

  (2026-11-15: run record appended; analysis run once at 10:06 +07, report SHA-256 `6c063d47…`. Commit waits for the owner's go.)
