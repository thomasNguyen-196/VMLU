## 1. Calibration procedure

- [x] 1.1 Write `data/diagnostic_router_v3/procedure_v3.json` with these fields: candidates always-B, v2 cascade and always-S; 60 calibration items; accuracy for multiple choice and mean token-F1 for reading; ties to fewer mean tokens; probe B x2 `normalized-answer-v1`. Add a loader that refuses unknown keys or values. Verify with unit tests: a valid procedure, an unknown key, exact match as the reading score, and a wrong candidate list. (2026-10-27: `data/diagnostic_router_v3/procedure_v3.json` sha256 470d28a4…; `diagnostic_calibration.load_procedure`; `TestProcedure`.)
- [x] 1.2 Implement the choice per dataset (rotation draws, scores, tie rule, sample size check) and the rule emission. Verify with unit tests on synthetic draws:
  - S best gives always-S;
  - equal scores go to the cheaper policy;
  - reading uses token-F1;
  - the emitted rule loads with `diagnostic_router.load_rule` and routes like the chosen policy, probe cost included.

  (2026-10-27: `diagnostic_calibration.choose` and `emit_rule`; `TestChoice` and `TestRuleEmission`.)
- [x] 1.3 Exploratory check on the used draws (wide and MC-94): the procedure's choices per dataset with 60-item samples and the regret against the best policy in hindsight. It is reported as design information, not as a result. (2026-10-27, `all_res/diagnostic_router_v3/design/calibration_check.json`, token-F1 for reading, 300 random 60-item samples per dataset: mean regret 0.5 to 1.7 points. The modal choice was always-S on VMLU valid (251 of 300 samples) and Vi-DROP (270); the v2 cascade on Vi-SQuAD (209), Legal MC (213), ViBidLQA test (203) and val (155, always-S 142); and always-B on Legal NLI (201).)

## 2. Held-out v3 set and registration

- [x] 2.1 Write `data/diagnostic_router_v3/protocol.json`:
  - model, transport, scoring and budget copied from the campaign protocol;
  - datasets VMLU valid, VM14K and ViBidLQA train;
  - arms B and S with 2 replicates;
  - 60 + 300 items per dataset, seed 42.

  Verify with a test that the copied blocks equal the campaign's. (2026-10-27: `data/diagnostic_router_v3/protocol.json` sha256 e435c7f6…; `TestV3Protocol` also refuses another transport or calibration size.)
- [x] 2.2 Add loaders for VM14K (four options, shuffled0, `build_prompt`) and ViBidLQA train (source pinned by SHA-256, `build_reading_prompt`, questions that appear once across the splits). Build and freeze the manifest with each item's role. Verify that:
  - it rebuilds byte-for-byte from the sources;
  - every prompt parses for B and S;
  - no VMLU item belongs to MC-94;
  - calibration and test items are disjoint.

  (2026-10-27: `code_benchmark/diagnostic_heldout_v3.py`. Pools: VMLU valid outside MC-94, 444; VM14K four-option, 11,094 once empty questions and placeholder options are left out; ViBidLQA train with unique questions, 1,848. `heldout_v3.json` self-hash e4780be9…: 1,080 items and 4,320 attempts, 60 calibration items per dataset. The test rebuilds it from the sources and finds no MC-94 item; every item parses for the router.)
- [x] 2.3 Implement the v3 runner on the campaign engine. Gates: card, detail card, manifest and protocol hashes, endpoint identity, procedure hash; the registered limits of 4 in flight and a breaker after 4 failures. Verify that the offline preflight prints `endpoint_calls=0`, passes when registered and fails for a changed procedure or manifest. (2026-10-27: `code_benchmark/run_router_v3_heldout.py` on the campaign engine, with a gate on the procedure and v2 rule hashes; `TestV3Gates`. The evaluation is `analyze_diagnostic_router heldout-v3`; `TestV3Evaluation`.)
- [x] 2.4 Register MC-95: root block, detail card, and a registration with the procedure hash and the report keys. Commit it as `pre-register MC-95`, and verify the preflight passes every gate. (2026-10-27: root block in `measurement_card.md`, `docs/measurement_cards/MC-95-diagnostic-router-v3-heldout.md`, `data/diagnostic_router_v3/registration.json` with the procedure (470d28a4…) and v2 rule (0585b9a8…) hashes and the report keys; the offline preflight passes all five gates with `endpoint_calls=0`.)

## 3. Run and evaluation

- [x] 3.1 Run the held-out v3 phase with `--execute` on Qwen3.5-9B-65K (IEC endpoint, VPN `member-shared-tcp`, tunnel DNS). Verify that 4,320 attempts complete with a constant response model id, and append the run record to the MC-95 detail card. (2026-10-27: one launch, 19:38 to 22:34 +07; 4,320 of 4,320 complete, no failed attempt, the registered model id in every row, 3,222,161 reported tokens. Run record appended to `docs/measurement_cards/MC-95-diagnostic-router-v3-heldout.md`.)
- [x] 3.2 Evaluate the procedure once. Verify the report keys equal the registered list. Contents:
  - per rotation, calibration and emitted rule;
  - the multiple-choice family in rotation 1 as primary: v3 against v2 and against always-S, McNemar with Holm; Wilson intervals; tokens with the probe;
  - per dataset, the choice, regret and calibration cost;
  - reading as descriptive.

  (2026-10-27: `analysis/router_v3_report.json`, report keys equal to the registered list.
  - Rotation 1 chose always-S for VMLU and ViBidLQA and always-B for VM14K. On VM14K's 60 calibration items B and the cascade tied at 76.7% against S at 70.0%, and the tie went to the cheaper B; on the test items B scored 54.3% against v2 61.7% and S 61.3%, a regret of 7.3 points.
  - Multiple choice, rotation 1 (primary, 600 test items): v3 67.8% at 563 tokens per item, v2 69.2% at 697, always-B 62.2% at 129, always-S 71.3% at 1,067. v3 against v2 +35/−43, Holm p 0.43; against always-S +33/−54, Holm p 0.063. Neither difference is significant.
  - Rotation 2 chose always-S everywhere, so v3 equals always-S (71.7%); against v2 +37/−22, Holm p 0.135.
  - Reading (descriptive): mean token-F1 regret of 0.4 and 0.2 points against v2, which costs twice the tokens of S.)
- [ ] 3.3 Add the result to the Notion core-results page and the thesis plan, keeping internal hostnames and addresses out.
