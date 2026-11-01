## Context

See `proposal.md` for the motivation.

Router v2 (`data/diagnostic_router_v2/router_v2.json`) is a rule in the closed grammar of `code_benchmark/diagnostic_router.py`. That grammar has dataset, prompt-length and cue conditions and an optional B probe, and the rule was evaluated once on 600 held-out items (MC-94, `analyze_diagnostic_router heldout`). The held-out runner (`run_router_v2_heldout.py`) runs on the engine, guards, scorers and registered limits of the prospective campaign (`run_diagnostic_prospective.py`).

Every item of wide and MC-94 has two draws of B and of S, so the outcome of always-B, always-S and the v2 cascade is known for each rotation. The datasets with gold answers that no router has used are:

- **VMLU valid:** 444 of 744 items remain outside MC-94.
- **VM14K:** 11,111 four-option items in 9 categories, plus 6 marked unknown (`data/vm14k_manifest.json`).
- **ViBidLQA train:** 1,928 items; every answer is a span of its passage, and no frozen manifest exists yet.

## Goals / Non-Goals

**Goals:**
- A router that chooses, per dataset, the policy the data favour (always-B, the v2 cascade or always-S) from a small labelled calibration sample. The choice runs through the same routing code as v1 and v2.
- A confirmatory test on items no router has seen, including a domain no router has met.

**Non-Goals:**
- Arm K, retrieval or the corpus (the next change, K2).
- A trained or item-level learned router.
- Any change to v1 or v2 artifacts.

## Decisions

1. **v3 is a procedure that writes a rule.**
   - The frozen artifact is `data/diagnostic_router_v3/procedure_v3.json`. It fixes the candidate policies, the calibration size, the score per task, the tie rule and the probe.
   - Calibration produces a rule in the existing closed grammar:
     - one condition per dataset for always-B or always-S;
     - for the cascade, a pair of conditions: the dataset with `probe: disagree` goes to S, then the dataset alone goes to B.
   - The existing `route` executes that rule, so v3, v2 and the fixed policies share one code path, and cost accounting (lazy probe, first B answer reused) is unchanged.
   - Rejected: a separate selector program beside the router, which would leave v3 on a code path the earlier routers do not use.

2. **Candidates, score and tie.**
   - The candidates are always-B, the v2 cascade (B twice; S when the parsed answers differ under `normalized-answer-v1`) and always-S.
   - On a dataset's calibration items, in one rotation, each candidate is scored:
     - multiple choice: the share of correct items;
     - reading: the mean token-F1 of the answer the policy returns.
   - The highest score wins. On an exact tie, the lower mean reported tokens wins. If tokens tie too, the order is always-B, v2, always-S, cheapest first.
   - Rejected alternatives:
     - **Exact match for reading.** It mostly rewards answer formatting: 34 of 50 losing ViBidLQA answers in MC-94 were right in meaning.
     - **A cost exchange rate or a margin.** The project owner chose accuracy first, with ties going to the cheaper policy.
     - **Choosing per VMLU category.** In the exploration, S stays best in every category.

3. **Calibration size 60.**
   - A first exploration on wide and MC-94 (exact match for reading) drew calibration samples at random and scored the chosen policy on the remaining items. With 30 items, the wrong policy was chosen more often: VMLU picks S in 73% of samples at 30 items and 87% at 60.
   - The registered procedure was then checked on the same draws (`analyze_diagnostic_router calibration-check`: token-F1 for reading, 300 random 60-item samples per dataset, regret measured on the other items of the same rotation). The mean regret was 0.5 to 1.7 points per dataset. The modal choice per dataset:
     - always-S on VMLU valid and Vi-DROP;
     - the v2 cascade on Vi-SQuAD, Legal MC and both ViBidLQA splits;
     - always-B on Legal NLI.
   - The calibration cost is reported per dataset: B twice and S once on 60 items.

4. **Held-out set.** Items are ranked by sha256(seed, tab, dataset:item) with seed 42, as in MC-94. Each dataset gets 60 calibration and 300 test items:

   | Dataset | Pool | Sampling |
   |---|---|---|
   | VMLU valid | 444 items outside MC-94 | 360 by VMLU category, in proportion (largest remainder) |
   | VM14K | four-option items, shuffled0 variant | 360 by the manifest's category, in proportion |
   | ViBidLQA train | questions that appear once across train, val and test (1,848 items) | 360 at random |

   - Inside each dataset, calibration takes 60 of the 360 in proportion to the strata, and the lowest ranks come first. The rest is the test set.
   - VMLU and VM14K prompts come from the frozen `build_prompt`. ViBidLQA train prompts come from `build_reading_prompt` with the source pinned by SHA-256.
   - Rejected: VMLU dev, whose dataset id differs from valid and would split VMLU into two datasets for calibration.

5. **Rotations, as in MC-94.**
   - Rotation 1: B1 answers, B2 is the probe's second answer, S1 on escalation.
   - Rotation 2: the same with the draws swapped.
   - Calibration and test use the same rotation, so rotation 2 replicates the whole procedure, calibration included.
   - Rotation 1 is primary. The outcome of an item is the single draw the deployment returns.

6. **Families and tests.**
   - **Multiple choice (VMLU valid and VM14K, 600 test items) is the primary family.** In rotation 1:
     - exact McNemar of v3 against the frozen v2 rule and against always-S, with Holm over the two;
     - always-B reported beside them;
     - for each policy, accuracy with a Wilson interval and mean reported tokens per test item, probe included.
   - **Reading (ViBidLQA train) is descriptive.** It reports mean token-F1 and exact match per policy, plus the items whose exact-match correctness differs between v3 and a fixed policy, for an optional semantic review.
   - **Per dataset:** the chosen policy in each rotation, the three calibration scores, the policy best on the test items in hindsight, and the regret against it.

7. **Separate protocol and runner on the campaign engine.**
   - `data/diagnostic_router_v3/protocol.json` copies the campaign's model, transport, scoring and budget blocks; a test asserts equality. The budget cap is the campaign's 5 million tokens per run, against about 3 million expected.
   - A v3 runner mirrors the v2 one with its own gates, adding a procedure hash gate.
   - Rejected: generalising the v2 runner in place, whose SHA-256 is recorded in the MC-94 run record.

## Risks / Trade-offs

- **[Power]** On VMLU, v3 is expected to pick S, which beat v2 by 18 to 8 discordant items in MC-94 (p 0.08 on its own). VM14K may favour S or not → the test pools both datasets; the result is reported whatever its sign, and the per-dataset regret shows whether the choice was right.
- **[The calibration sample picks the wrong policy]** → the regret against the best policy in hindsight is reported per dataset and rotation.
- **[Exact match versus meaning on reading]** → reading is descriptive. Token-F1 decides the reading choice, and the semantic review of discordant items stays optional.
- **[VM14K answered by earlier runs (MC-14, MC-14b); ViBidLQA train shares passages with val and test]** → stated as comparison limits.
- **[Endpoint drift since MC-94]** → the runner stops on a model-id change.

## Migration Plan

Additive only: a new module, data under `data/diagnostic_router_v3/` and card MC-95. Rollback is deleting the new files; no v1 or v2 artifact or hash changes.
