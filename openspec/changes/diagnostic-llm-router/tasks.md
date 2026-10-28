## 1. Arm Q and the design run (MC-97)

- [x] 1.1 Teach `diagnostic_prospective` arm Q for replicate ids and scoring only. `CAMPAIGN_ARMS` keeps the protocol check and `build_arm_prompt`; `FINAL_LABEL_ARMS` scores S, KS and Q from the last final-answer label. Verify:
  - the campaign tests pass unchanged;
  - Q is scored from its final `Trả lời:` line, not its `Trích dẫn:` line;
  - `build_arm_prompt(item, "Q")` is refused.
- [x] 1.2 Write `data/diagnostic_llm_router/protocol.json` (Q head, layout, inherited blocks, plan `diagnostic-menu-q-v1`) and `code_benchmark/diagnostic_menu.py`. Freeze `menu_q_v1.json`. Verify:
  - the manifest rebuilds from the sources;
  - every item's frozen prompt hashes to its MC-90 B prompt;
  - every Q prompt is head + passage + question label + question + newline;
  - no prompt carries the gold.

  (2026-10-28: `protocol.json` sha256 0b9dc30e…; manifest self-hash 993694c4…, 967 items, 1,934 attempts.)
- [x] 1.3 Implement `code_benchmark/run_menu_q.py` on the campaign engine with the gates of the spec and the registered limits. Verify that the offline preflight prints `endpoint_calls=0`, passes when registered, and fails for a changed manifest or registration.
- [x] 1.4 Register MC-97: root block, detail card `docs/measurement_cards/MC-97-diagnostic-quote-arm-wide.md`, and `registration.json` with the hashes. Commit as `pre-register MC-97`. Verify that the preflight passes every gate.
- [x] 1.5 Run MC-97 with `--execute` (IEC endpoint, VPN `member-shared-tcp`, tunnel DNS). Verify 1,934 complete attempts with a constant response model id, and append the run record to the MC-97 detail card. (2026-10-28: one launch, 15:27–15:59 +07. 1,934 of 1,934 attempts complete, finish reason `stop`, a constant model id, none at the cap, 1,572,599 reported tokens. The run record is in the card.)
- [x] 1.6 Run the descriptive analysis `diagnostic-menu-q-v1` once and report it. (2026-10-28: `analysis/menu_report.json`. Token-F1, where "winner repeats" means the arm that wins draw 1 also wins draw 2:

  | Dataset | B | Q | S | Choose on draw 1, score draw 2 | Same draws (luck counted) | Winner repeats |
  | --- | --- | --- | --- | --- | --- | --- |
  | Pooled | 68.1 | 66.3 | 72.4 | 73.3 | 81.3 | 55.8% of 251 decided items |
  | ViBidLQA | 64.6 | 62.7 | 65.9 | 67.4 | 75.6 | 49.0% of 200 |
  | Vi-DROP | 54.5 | 54.6 | 75.9 | 72.2 | 83.8 | 90.6% of 32 |
  | Vi-SQuAD | 92.8 | 89.5 | 89.2 | 92.9 | 96.7 | 68.4% of 19 |

  - The per-dataset rule (Vi-SQuAD B; Vi-DROP and ViBidLQA S) scores 73.06.
  - On ViBidLQA, Q cut over-long answers from 24.2% to 21.9% of attempts. It raised partial answers from 10.2% to 15.1% and wrong answers from 9.6% to 11.1%.
  - Q against B over all items: better on 297, worse on 336.)

## 2. Router design check on the design items (MC-98, registered before any router request)

After MC-97 the owner chose a quick check of the Muse router on the design items before any held-out evaluation.

- [x] 2.1 From the MC-97 analysis, write `data/diagnostic_llm_router/router_v1.json` with:
  - the six groups with their definitions, in order;
  - the Muse Spark 1.3 router prompt: passage and question in, one `Nhóm: <id>` line out;
  - the parsing rule and the route (direct OpenCode Go Responses, credential from the local OpenCode auth store);
  - the cross-draw mapping rule (ties to the more thorough arm, minimum group of 20, fallback S);
  - the frozen keyword comparator;
  - plan `diagnostic-router-labels-v1` with its reading rule.

  Implement `code_benchmark/diagnostic_llm_router.py`, `run_router_labels.py` and `analyze_router_labels.py`, and freeze `router_labels_v1.json`, one call for each of the 591 ViBidLQA design items. Verify with unit tests on synthetic cells and a fake client: the prompt, the parsing, the keyword groups, the cross-draw mapping worked by hand, the reading rule, the gates, the call record and the halts. (2026-10-28: `router_v1.json` sha256 15ffc94b…; manifest self-hash 53692d08…; `test_diagnostic_llm_router`.)
- [x] 2.2 Register MC-98: root block, detail card `docs/measurement_cards/MC-98-diagnostic-llm-router-design-check.md`, and `registration_labels.json`. Commit as `pre-register MC-98`. Verify that the offline preflight passes every gate.
- [x] 2.3 Run MC-98 with `--execute`. Verify 591 complete calls with a constant response model id, and append the run record to the MC-98 detail card. (2026-10-28: 16:15–16:47 +07. 591 of 591 complete, a constant model id, no halt. 26 calls ended at the cap during hidden reasoning and take S. 1,819,635 reported tokens, 3,079 per call, 2,197 of them reasoning. The run record is in the card.)
- [x] 2.4 Run `analyze_router_labels` once and apply the reading rule. If the router is promising, plan section 3; otherwise the router line stops at the design stage and section 3 is not run. (2026-10-28: `analysis/router_labels_report.json`.
  - Cross-draw token-F1 on the 591 items: Muse grouping 66.16, keyword grouping 66.25, always-S 65.88, always-B 64.63, always-Q 62.67; the per-item bound is 67.38.
  - Muse minus always-S: +0.28 points (95% interval -1.11 to +1.69, sign-flip p 0.70).
  - Muse minus keywords: -0.09 points (p 0.87).
  - Groups: `so_hieu` 156 (B 63.0, S 60.4, Q 56.0, so B on both draws); every other group maps to S, except `toan_bo` on draw 1, which maps to Q; 26 unrecognised.
  - The reading rule is not met (+0.28 < 1.0, and below the keyword grouping). The router line stops at the design stage, and section 3 is not run.)

## 3. Held-out evaluation (only if MC-98 reads promising; registered before its first request)

- [ ] 3.1 Build the held-out set (300 ViBidLQA train items with their passages, not used by MC-95 or MC-96) and register its card:
  - B, S and Q two draws each, one router call per item;
  - primary: the router against always-B and always-S on token-F1, with paired sign-flip tests and Holm;
  - tokens per item include the router's.
- [ ] 3.2 Run, evaluate once, and report on the Notion core-results page and the thesis plan, keeping internal hostnames and addresses out.
