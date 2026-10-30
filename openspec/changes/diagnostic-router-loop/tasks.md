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

- [ ] 2.1 Design the calibration set: about 60 fresh items per dataset (VMLU, VM14K, ViBidLQA), disjoint from every earlier router set and from the planned evaluation items. Verify that a manifest test proves disjointness.
- [ ] 2.2 Register and run calibration for Qwen3.5-9B-65K on the IEC endpoint (openvpn3 `member-shared-tcp`, in-tunnel DNS): B twice plus E0–E4 and E7 once each. Verify that every attempt is complete with one response model, and record the run in its card.
- [ ] 2.3 Register and run the same calibration for each chosen API student, with the model id and endpoint recorded per card. Verify the same way, plus the budget guard.
- [ ] 2.4 Freeze one weakness map per model (rescue rate, damage rate and cost per enhancement, dataset and cause group). Verify that its SHA-256 is recorded and a test rejects a map built on evaluation items.

## 3. Router-critic design check (10/11–17/11)

- [ ] 3.0 (added 2026-10-30, pulled forward at the owner's request for early results) MC-102: a reading pilot of the critic, replayed on Qwen's logged answers. Muse Spark 1.3 judges Qwen's B-r1 answer on the 376 Vi-DROP and Vi-SQuAD items of the menu set and prescribes keep, S or Q. The loop takes the logged draw-1 answer, so no student request is sent. Primary: critic loop against the rule loop on token-F1, with a reading rule of at least +1.0 point and p < 0.05. Verify that the offline preflight passes every gate with `endpoint_calls=0` and that the tests pass (`test_diagnostic_router_critic`).

  (2026-10-30: config `a08b5dad…`, manifest `8a13231a…`, card MC-102; the synthetic end-to-end analysis matches the registered report keys. Draw-1 references on the 376 items, token-F1: always-B 72.3, always-S 82.6, rule loop 82.2, Muse alone 82.4, per-item bound 90.4.)
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
