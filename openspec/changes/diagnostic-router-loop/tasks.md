## 0. Scope and access (30/10–1/11)

- [ ] 0.1 Check access, quota, price and usage reporting for each candidate: Muse Spark 1.3 and MiMo V2.6 Flash (OpenCode or direct API), Jev 1.13 paid, and Qwen3.5-9B on the IEC endpoint. Verify with one harmless probe per model, with no benchmark item sent. Record the results in design.md.
- [ ] 0.2 Owner decisions: router-critic model, student models, monthly budget, and whether escalation (E8) is a menu item. Verify that they are recorded under "Decisions pending the owner".
- [ ] 0.3 Update the thesis scope on Notion (the second student model moves into the core), with the owner's approval. Verify that the plan page names the loop and the chosen models.

## 1. Offline foundations, no benchmark request (1/11–5/11)

- [x] 1.1 Simulate the rule loop (B twice, then on disagreement the dataset's best existing arm) on all existing Qwen data:
  - VMLU from MC-94 and MC-95;
  - VM14K from MC-95;
  - wide reading from MC-90 to MC-92 and MC-97;
  - ViBidLQA from MC-94 and MC-96;
  - Legal MC from MC-100 and MC-101.

  Report quality against cost beside always-B, the best fixed arm and the oracle-detector ceiling, with both draw orders averaged. Verify with a script whose numbers reproduce the 87.3 / 84.3 / 91.4 Legal MC check, and label every figure exploratory.

  (2026-10-30: `simulate_router_loop` reproduces 84.33 / 87.31 / 91.42 on MC-101; the report is in `all_res/diagnostic_router_loop/simulation/rule_loop_sim.json`. Where the enhancement helps little on average (Legal MC, Vi-SQuAD, ViBidLQA), the loop beats both always-B and always-F. Where S helps a lot (Vi-DROP, VMLU, VM14K), always-S still beats the loop, because asking twice misses consistent errors. Everywhere, the ideal detector sits 5–20 points higher, so the detector is where the critic must earn its cost.)
- [x] 1.6 (added 2026-10-30) Use the stronger model's logged answers (MC-80/81, Muse Spark 1.3 direct) as a free proxy for the critic. Two detectors and a cascade, all from existing logs:
  - **Muse as detector:** flag B when Muse's answer differs from it.
  - **Muse alone.**
  - **Cascade:** ask B twice; on disagreement take Muse's answer.

  Verify that `simulate_router_loop` reports them in its `strong_model` blocks.

  (Exploratory. **Multiple choice:** Muse flags most of B's errors with few false flags: VMLU caught 161 of 188, false flags 15 of 412; Legal MC caught 37 of 42, false flags 8 of 226. The flag-to-F loop lifts VMLU to 84.2 against always-S 80.8. Muse alone is higher still (VMLU 91.0, Legal MC 93.3): on multiple choice, judging an answer is solving the item. The cascade reaches 92.5 on Legal MC with Muse on 16% of items and one sixth of its tokens. On Legal NLI it reaches 92.8, above both Qwen (92.0) and Muse (81.9). **Reading:** exact-match disagreement is a poor detector, with false flags of 91 of 359 on Vi-SQuAD and 466 of 817 on ViBidLQA. On Vi-DROP the flag-to-S loop (77.4) beats Muse alone (73.4) and always-S (75.9). The critic therefore earns a request mainly as a meaning-level judge of free-text answers and as a chooser among fixes, so MC-102 should pilot on reading rather than on VMLU.)
- [ ] 1.2 Build the experience store from the ledger and the run outputs: one case per item, model, arm and draw. Verify with tests:
  - leave-one-out (an item never sees its own cases);
  - an exclusion list removes the evaluation items;
  - retrieval returns similar cases.
- [ ] 1.3 Implement enhancement wrappers E3 (clause-level retrieval), E4 (critic-selected evidence) and E7 (self-consistency vote) as registered arms. Verify with tests:
  - prompts render from frozen templates;
  - evidence is verbatim with its hash;
  - no gold appears in any prompt.
- [ ] 1.4 Review MC-80 to MC-89 (direct API against `omp` full tools for four models): per model and dataset, where the harness helped or hurt, and at what cost. Verify that a short table is recorded here, from the frozen scores only.
- [ ] 1.5 Implement the leak check for router prescriptions (option letters in answer patterns, option text, answer phrases). Verify with tests: crafted hints are rejected and clean evidence passes.

## 2. Weakness map per model (5/11–10/11)

- [x] 2.0 (added 2026-10-30, pulled forward at the owner's request; the owner chose MiMo V2.6 Flash) MC-103: MiMo V2.6 Flash's weakness map on the 180 MC-95 calibration items (VMLU valid, VM14K and ViBidLQA train, 60 each).
  - **Arms.** B twice and S once on every item, and Q once on ViBidLQA: 600 attempts on the direct OpenCode Go chat-completions route. The prompts are MC-95's byte for byte.
  - **Analysis.** It compares MiMo, dataset by dataset, with Qwen's logged B-r1, B-r2 and S-r1 on the same items: arm means, fix gains against B-r1, rescue and damage counts, noise, the rule loop, the point and reliable maps, and the interaction.
  - **Verify.** The offline preflight passes every gate with `endpoint_calls=0`, `test_diagnostic_weakness_map` passes, and a synthetic end-to-end analysis matches the registered report keys.

  (2026-10-30: config `afa923de…`, manifest `18ea6429…`, card MC-103; all four gates pass offline, 10 tests pass, and the synthetic analysis (Qwen's rows standing in for the student) matches the registered report keys. Qwen's reference map on these items, point / reliable: VMLU S / S, VM14K B / B, ViBidLQA S / B.)

  (2026-10-30 11:06–11:51 +07, three launches; run record appended.
  - **Launch 1** was rejected, with no answer received: it lacked the routing session header (4 × HTTP 400). Fixed in `608cd85`.
  - **Launches 2 and 3** completed 600/600, with model id `mimo-v2.6-flash` throughout. The 3 attempts on VMLU item `04-0018` used the whole 20,000-token cap.
  - **Cost.** 433,335 tokens, about USD 0.10 at list price.)

  (2026-10-30, analysis run once, report SHA-256 `0a9a94a0…`, maps `15f10f79…`. Draw-1 means are B-r1, B-r2 and S-r1; each fix is compared with B-r1, with 95% bootstrap intervals.
  - **VMLU valid (accuracy, 60 items):**
    - MiMo: 80.0, 78.3 and 76.7. S −3.3 (−15.0 to +8.3); 5 rescued, 7 damaged.
    - Qwen: 60.0, 66.7 and 75.0. S +15.0 (+3.3 to +26.7; p 0.037).
    - Interaction −18.3 (−35.0 to −1.7; p 0.053). Maps, point / reliable: MiMo B / B, Qwen S / S.
  - **VM14K (accuracy):**
    - MiMo: 78.3, 80.0 and 83.3. S +5.0 (−3.3 to +15.0).
    - Qwen: 76.7, 73.3 and 70.0. S −6.7 (−20.0 to +6.7).
    - Interaction +11.7 (−3.3 to +26.7; p 0.21). Maps: MiMo S / B, Qwen B / B.
  - **ViBidLQA train (token-F1):**
    - MiMo: 58.5, 61.9 and 79.5, with Q-r1 75.1. S +21.0 (+13.1 to +29.5); Q +16.6 (+8.2 to +26.0).
    - Qwen: 59.1, 58.5 and 66.8. S +7.7 (−0.5 to +16.0; p 0.07).
    - Interaction +13.3 (+3.0 to +23.7; p 0.020). Maps: MiMo S / S, Qwen S / B.
  - **The maps differ:** the point maps on VMLU and VM14K, the reliable maps on ViBidLQA and VMLU.
  - **Rule loop (descriptive):** MiMo 83.3, 86.7 and 78.8; Qwen 65.0, 76.7 and 64.2 (VMLU, VM14K, ViBidLQA).
  - **Noise:** MiMo's two B draws agree on 47, 49 and 17 of 60 items.

  The following are exploratory: they were found after seeing the data and are not results.
  - **Markdown on ViBidLQA.** 29 of MiMo's 60 ViBidLQA B-r1 answers are bolded with `**`. The frozen tokenizer keeps the asterisks on the first and last word, so a bolded answer that matches the gold word for word scores below 1. With the asterisks removed, MiMo's B-r1 rises to 72.0 and S's gain falls to +7.5 (+1.9 to +13.7), the same size as Qwen's. Most of the ViBidLQA interaction is therefore format, not reasoning.
  - **VMLU.** The VMLU contrast compares letters only and is not affected. There, S helps the non-thinking Qwen and does not help MiMo, which thinks by default.)
- [ ] 2.1 Design the calibration set: about 60 fresh items per dataset (VMLU, VM14K, ViBidLQA), disjoint from every earlier router set and from the planned evaluation items. Verify that a manifest test proves disjointness.
- [ ] 2.2 Register and run calibration for Qwen3.5-9B-65K on the IEC endpoint (openvpn3 `member-shared-tcp`, in-tunnel DNS): B twice plus E0–E4 and E7 once each. Verify that every attempt is complete with one response model, and record the run in its card.
- [ ] 2.3 Register and run the same calibration for each chosen API student, with the model id and endpoint recorded per card. Verify the same way, plus the budget guard.
- [ ] 2.4 Freeze one weakness map per model (rescue rate, damage rate and cost per enhancement, dataset and cause group). Verify that its SHA-256 is recorded and a test rejects a map built on evaluation items.

## 3. Router-critic design check (10/11–17/11)

- [x] 3.0 (added 2026-10-30, pulled forward at the owner's request for early results) MC-102: a reading pilot of the critic, replayed on Qwen's logged answers. Muse Spark 1.3 judges Qwen's B-r1 answer on the 376 Vi-DROP and Vi-SQuAD items of the menu set and prescribes keep, S or Q. The loop takes the logged draw-1 answer, so no student request is sent. Primary: critic loop against the rule loop on token-F1, with a reading rule of at least +1.0 point and p < 0.05. Verify that the offline preflight passes every gate with `endpoint_calls=0` and that the tests pass (`test_diagnostic_router_critic`).

  (2026-10-30: config `a08b5dad…`, manifest `8a13231a…`, card MC-102; the synthetic end-to-end analysis matches the registered report keys. Draw-1 references on the 376 items, token-F1: always-B 72.3, always-S 82.6, rule loop 82.2, Muse alone 82.4, per-item bound 90.4.)

  (2026-10-30 10:10–10:29 +07, one launch at the owner's go-ahead: 376/376 complete, the registered model id in every row, 834,002 Muse tokens. Nine responses hit the 4,096-token cap and one came back empty; none of the ten has a verdict, so each keeps B-r1. Run record appended.)

  (2026-10-30, analysis run once, report SHA-256 `8fe42d10…`.
  - **Primary, 376 items, token-F1:** critic loop 83.2, rule loop 82.2, +1.1 points (95% bootstrap −1.4 to +3.9; sign-flip p = 0.42); 38 items better, 37 worse, 301 equal. **Reading rule not met: the reading critic stops at the design stage.**
  - **Vi-DROP:** always-B 52.4, always-S 76.0, rule loop 70.3, critic loop 75.8, Muse alone 73.4, Muse-answer proxy 77.3, bound 84.0.
  - **Vi-SQuAD:** always-B 92.2, always-S 89.1, rule loop 94.0, critic loop 90.7, Muse alone 91.3, Muse-answer proxy 93.0, bound 96.9.
  - **Detector** (B-r1 counts as wrong when its token-F1 is below 0.5):
    - Vi-DROP: 69 of 85 wrong answers caught, with 6 false flags (recall 81%, precision 92%).
    - Vi-SQuAD: 1 of 9 wrong answers caught, with 11 false flags (recall 11%, precision 8%).
  - **Prescriptions on `sai`:** `suy_luan` 77 (56 rescued, 3 damaged), `trich_dan` 6 (1 rescued, 3 damaged), `giu` 4. Muse never answered `khong_chac`, so that variant equals the critic loop.
  - **Cost per item:** Muse 2,218 tokens; Qwen 579 in the critic loop against 1,044 in the rule loop.

  On Vi-DROP, where Qwen errs often (mostly counting and arithmetic), Muse is a good judge and prescribes S, but always-S scores the same without a critic. On Vi-SQuAD, where Qwen is already right 95% of the time, Muse's false flags outnumber its catches, and Q damages correct answers. Muse alone reads no better than Qwen with S (82.4 against 82.6), so it has no edge when judging lookup answers.

  The following are exploratory: they were chosen after seeing the data, on the same items, and are not results.
  - The fixed per-dataset rule (Vi-DROP → S, Vi-SQuAD → B) scores 84.1.
  - The critic used on Vi-DROP only scores 84.0.
  - The critic consulted only when B-r1 and B-r2 disagree scores 79.5.)
- [ ] 3.1 Implement the critic client with the closed output (verdict, cause, prescription, rationale), its prompt template and the leak check. Verify with mocked-transport tests: malformed or leaking outputs fall back to the rule loop.
- [ ] 3.2 Write the design-check reading rule before data, run the critic on the calibration items of every student (critic model and endpoint recorded) and score it offline. Report:
  - verdict recall and precision against gold;
  - the rescue and damage rates of its prescriptions;
  - its recall on confident errors;
  - the focus-note ablation;
  - cost.

  Verify that the go or no-go decision is reported here.
- [ ] 3.3 Fix the Phase 4 conditions (stage-2 coverage, rounds, stop and selection rules) from 3.2, on calibration data only. Verify that they are written into the Phase 4 registration draft.

## 4. Held-out evaluation (17/11–30/11)

- [ ] 4.1 Build and freeze the evaluation manifests: about 300 fresh items per dataset per student. Conditions: always-B, best fixed, rule loop, critic loop (n ≤ 3), router alone. Verify:
  - B prompts are byte-identical to the frozen main prompts;
  - no gold or answer appears in any prompt;
  - the items are disjoint from calibration and the experience store.
- [ ] 4.2 Register the evaluation card(s): primary comparison (critic loop against rule loop per student, Holm), reading rule and cost reporting. Commit `pre-register MC-n`. Verify that the offline preflight passes every gate.
- [ ] 4.3 Run each student and the critic on their recorded endpoints. Verify that every attempt is complete, model ids are constant and unknown costs are counted. Append the run record.
- [ ] 4.4 Run the registered analysis once and report it here and on Notion with the owner's approval.

## 5. Fallback: learned router (December, only if 3.2 or 4.4 fails)

- [ ] 5.1 Assemble the training table from all outcome data, without evaluation items, and the features of design Decision 8. Verify with a test that grouped cross-validation keeps every item in one fold.
- [ ] 5.2 Fit logistic regression, gradient boosting and a small MLP. Pick the policy by cross-validated expected gain minus cost. Verify that a report states it is exploratory unless 5.3 runs.
- [ ] 5.3 If time allows, register and run a held-out evaluation of the learned policy. Verify as in 4.2–4.4.
