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

## 2. Router design (registered before any router request)

- [ ] 2.1 From the MC-97 analysis, write the closed list of groups with their definitions and the Muse Spark 1.3 router prompt (passage and question in, one group name out), the default arm, and the mapping rule (best mean token-F1 per group on the design labels, ties to the more thorough arm, a minimum group size).
- [ ] 2.2 Register the router's labelling of the design items on its own card, run it, fit the mapping by the registered rule, and freeze the router and the mapping.

## 3. Held-out evaluation (registered before its first request)

- [ ] 3.1 Build the held-out set (300 ViBidLQA train items with their passages, not used by MC-95 or MC-96) and register its card:
  - B, S and Q two draws each, one router call per item;
  - primary: the router against always-B and always-S on token-F1, with paired sign-flip tests and Holm;
  - tokens per item include the router's.
- [ ] 3.2 Run, evaluate once, and report on the Notion core-results page and the thesis plan, keeping internal hostnames and addresses out.
