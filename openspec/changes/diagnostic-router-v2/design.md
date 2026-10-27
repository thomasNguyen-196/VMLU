## Context

See `proposal.md` for the motivation. Router v1 is a closed-grammar rule over runtime features (`code_benchmark/diagnostic_router.py`): the dataset, the length of the frozen B prompt and cue words of a hashed lexicon. It was designed on the wide draws, frozen as `data/diagnostic_prospective_v1/router_v1.json` and evaluated once on the 60 core anchors (MC-93). The campaign protocol `data/diagnostic_prospective_v1/protocol.json` is frozen with two phases (core, wide) and five datasets; its runner (`run_diagnostic_prospective.py`) already provides the request engine, budget and outage guards, registered concurrency limits, the resolver shim, resume rules and arm scoring. Every wide item has two draws of B and of S (MC-90, MC-91, MC-92). No Vi-DROP or Legal MC item remains outside wide and core; ViBidLQA val (482) and VMLU valid (744) have gold answers, load with the frozen main-v1 prompt builders, and parse with the S prompt surgery.

## Goals / Non-Goals

**Goals:**
- One grammar for v1 and v2 rules, so that every policy, the fixed ones included, goes through the same routing code.
- A confirmatory test of v2 on items no router has seen, with cost counted as deployment would pay it.

**Non-Goals:**
- Changing any v1 artifact or the frozen campaign protocol.
- Arm K or the corpus (K2 is later).

## Decisions

1. **The probe is part of the rule grammar, not a separate cascade program.** A rule may declare `probe: {arm: B, samples: 2, agreement: normalized-answer-v1}` and a condition may test `probe: agree | disagree`. Routing stays a pure function of what deployment knows: the request features and, after the probe, the model's own two answers. Alternative rejected: a hard-coded cascade beside the router, which would leave fixed policies and v1 on a different code path and make the comparison less exact.

2. **Lazy probing with static features first.** Conditions are read in order; inside a condition the dataset, prompt length and cues are checked before the probe, so a Vi-DROP item sent to S pays no probe. When the final arm is B, the first probe answer is reused. Alternative rejected: probing every item, which charges two B requests to items the rule would send to S anyway.

3. **Agreement on parsed answers.** Multiple choice compares the parsed letter; reading compares the exact-match normalization of the parsed answer (`vi_multimodel.normalize_em_answer`). An empty parse counts as disagreement, so an unparsed B answer is escalated rather than trusted. Alternatives rejected: token-F1 similarity (adds a threshold to tune) and log-probabilities (the endpoint's support is unverified).

4. **Families, with multiple choice as the primary test.** The wide design fit showed that most of the reading gain outside Vi-DROP is exact-match formatting (rotation 1: 54 of 69 rescues in the escalated group were measurement effects). The held-out evaluation is therefore split into a multiple-choice family (VMLU valid, scored exactly: the confirmatory test) and a reading family (ViBidLQA val: exact match, token-F1 and a semantic review of the discordant items, descriptive). Decided by the project owner on 2026-10-27 together with the choice of v2b.

5. **Rotations instead of a majority.** Deployment answers with single draws, so single-draw outcomes are evaluated. On wide, both rotations (B1 answer with B2 probe and S1; B2 answer with B1 probe and S2) are averaged for the design fit. On the held-out set the first rotation is the registered primary analysis and the second its replication, which keeps one binary outcome per item and policy for McNemar.

6. **Held-out set from datasets with spare gold.** ViBidLQA val (300 of 482, random, seed 42) and VMLU valid (300 of 744, by category in proportion, seed 42) were never used to design or evaluate a router. Items are rebuilt with the main-v1 builders; VMLU valid prompts are byte-identical to the main-v1 manifest. Neither dataset has a Vi-DROP item, so v1 equals always-B there and the test isolates the probe's contribution; the Vi-DROP condition is supported only by the wide design fit and the v1 core result. Legal syllogism (144) is left out because its answers are free text that exact match cannot score.

7. **A separate protocol and runner that reuse the campaign engine.** `data/diagnostic_router_v2/protocol.json` copies the campaign's model, transport, scoring and budget blocks (a test asserts equality) and adds the held-out datasets, the sampling rule and arms B and S with two replicates. A held-out runner module imports the campaign runner's request engine, guards, limits, resolver shim, resume and scoring functions and adds its own manifest, registration and gates. Alternative rejected: a third phase in the frozen campaign protocol, which would change its hash and every artifact bound to it.

8. **Candidates committed before their fits.** The pure cascade and "Vi-DROP to S, otherwise escalate disagreements" were already explored on wide while planning (disclosed in the card); the candidate files are nevertheless committed before the registered design fit is computed, and the owner's choice is frozen by hash before the held-out run.

## Risks / Trade-offs

- [The probe roughly doubles B's prompt cost; the endpoint caches only about 22 prompt tokens] → report mean reported tokens with the probe and the quality–cost position of every policy; no claim that v2 is cheaper than S.
- [Exact match penalises S's longer reading answers] → report token-F1 beside exact match and the semantic-review block of the first rotation on wide; a semantic review of held-out discordant items stays optional.
- [The probe gained nothing on the core anchors in an exploratory check (61.1% against v1's 62.2%, n = 60)] → the held-out test decides; the result is reported whatever its sign.
- [Endpoint drift since MC-93] → the runner stops on a model-id change; B accuracy on the held-out VMLU items can be compared with earlier main-v1 runs as a parity check.
- [ViBidLQA val shares legal source documents with the test split] → state it as a comparison limit; items and questions are distinct.

## Migration Plan

Additive only: new modules, data under `data/diagnostic_router_v2/`, card MC-94. Rollback is deleting the new files; no v1 artifact or hash changes.
