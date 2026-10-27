## Why

Router v2 (MC-94) beat always-B on VMLU valid (76.7% against 68.3%, Holm p 0.0007) but trailed always-S (80.0%; Holm p 0.076, replication 0.017): on VMLU, S also helps where B's two answers agree (B 79.9%, S 84.9%, mean of the two rotations). Taken together, the wide draws (MC-90 to MC-92) and MC-94 show three regimes:

- S helps even where B is consistent: VMLU and Vi-DROP, where always-S is best.
- S helps only where B's two answers differ: Vi-SQuAD, Legal MC and ViBidLQA, where the v2 cascade is best.
- S does not help: Legal NLI, where always-B is best.

A per-dataset choice among always-B, the v2 cascade and always-S covers all three. On the existing draws, choosing that policy from 60 labelled calibration items per dataset loses 0.5 to 1.7 points on average against the best policy on each dataset's other items (an exploratory check on used draws, 300 random samples per dataset). Router v2's hand-written condition "Vi-DROP to S" is this choice made by dataset name. The semantic review of MC-94 adds a constraint: on ViBidLQA, 34 of the 50 answers that lost on exact match were right in meaning, so a reading choice made on exact match would follow answer formatting.

## What Changes

- **Router v3 is a frozen calibration procedure, not a fixed rule.**
  - For each dataset, B answers 60 labelled calibration items twice and S answers them once.
  - Always-B, the v2 cascade and always-S are scored on those items: accuracy for multiple choice, mean token-F1 for reading.
  - The highest score wins. A tie goes to the policy with fewer mean reported tokens.
  - The choices are written as a rule in the existing closed grammar, and the existing router executes it.
- **A second held-out set that no router has seen.** Each dataset has 60 calibration items and 300 test items, built with the main-v1 builders:
  - VMLU valid items outside MC-94;
  - VM14K medical multiple choice with four options, a domain no router has met;
  - ViBidLQA train items.

  Arms B and S run with two draws each, 4,320 attempts in all. The set has its own protocol, manifest, registration and measurement card MC-95. The runner reuses the MC-93 engine, scorers and registered limits.
- **The procedure is evaluated once.** In each rotation, the calibration items produce the rule, and that rule routes the test items. v3 is compared with the frozen v2 rule, always-B and always-S.
- **Arm K and retrieval (K2) are the next change.**

## Capabilities

### New Capabilities
- `diagnostic-calibrated-router`: the calibration procedure and its frozen description, the choice of a policy per dataset, and its translation into a rule of the closed grammar.
- `diagnostic-router-v3-heldout`: the second held-out set, its registration, and the single evaluation of the procedure.

### Modified Capabilities
None. The router grammar, the v1 and v2 rules and every v1 and v2 artifact stay as registered. This includes protocols, manifests, `router_v1.json`, `router_v2.json` and cards MC-90 to MC-94.

## Non-goals

- No arm K, corpus or retrieval change. K2 is the next change.
- No trained classifier, no item-level learned feature and no second model.
- No margin or cost exchange rate in the choice. The project owner chose accuracy first, with ties going to the cheaper policy.
- No re-evaluation of v1 or v2 on their own sets.
- No claim of a pristine held-out set:
  - VMLU valid and VM14K were answered by earlier benchmark runs, though never used to design or evaluate a router.
  - ViBidLQA train shares passages with the val and test splits.

## Evaluation regime

Regime B-style only, as MC-90 to MC-94: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint. Regimes A and C are not touched.

## Impact

- **Code:**
  - a calibration module beside `code_benchmark/diagnostic_router.py` (choice, frozen procedure, rule emission);
  - a held-out v3 manifest builder with loaders for VM14K and ViBidLQA train;
  - a held-out v3 runner on the campaign engine;
  - the v3 evaluation in `code_benchmark/analyze_diagnostic_router.py`;
  - tests for all of these.
- **Data:** `data/diagnostic_router_v3/` holds the procedure, protocol, manifest and registration.
- **Cards:** MC-95 in `measurement_card.md` and `docs/measurement_cards/`.
- **Endpoint use:** about 4,320 attempts and 3 million reported tokens over the IEC VPN.
