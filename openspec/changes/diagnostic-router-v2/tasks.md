## 1. Router grammar with a probe

- [x] 1.1 Add the probe block and the `probe` feature to the rule grammar (arm B, two samples, closed agreement rule; a condition may test the probe only when the rule declares one) and verify unit tests for a valid probe rule, a probe condition without a probe, a wrong probe arm or sample count and an unknown agreement rule. (2026-10-27: `probe` block and `probe` feature in `code_benchmark/diagnostic_router.py`; `TestProbeGrammar`.)
- [x] 1.2 Route with a lazy probe (static features first, probe only when a condition needs it, first probe answer reused for B, empty parse counts as disagreement) and verify unit tests, including an item decided before the probe at no probe cost and an escalated item charged both B answers plus S. (2026-10-27: `route(rule, features, probe_agrees)`, `needs_probe`, `answers_agree`, `Decision.probed`; `TestProbeRouting` and `TestProbeDesignFit`.)

## 2. Design fit on wide

- [x] 2.1 Write the v2 candidates in `data/diagnostic_router_v2/router_candidates/` (pure cascade; Vi-DROP to S and the cascade elsewhere) and commit them before computing their fits; verify they load with the cue lexicon. (2026-10-27: `v2a-cascade.json` sha256 17975245…, `v2b-drop-cascade.json` sha256 0585b9a8…, committed before the registered fit; both policies had been explored on the wide draws while planning the change.)
- [ ] 2.2 Implement the two-rotation design fit (accuracy and tokens of the rule, always-B and always-S; escalation share; B and S accuracy on agreeing and disagreeing items; per dataset and condition; semantic block of the first rotation) and verify unit tests on synthetic draws; run it on the wide draws of Qwen3.5-9B-65K (MC-90, MC-91, MC-92) and report it beside v1.
- [ ] 2.3 Have the project owner choose a candidate, freeze it as `data/diagnostic_router_v2/router_v2.json` (byte copy) and verify a test keeps it equal to a committed candidate.

## 3. Held-out set and registration

- [ ] 3.1 Write `data/diagnostic_router_v2/protocol.json` (model, transport, scoring and budget copied from the campaign protocol; datasets VMLU valid and ViBidLQA val; arms B and S; 2 replicates; 300 + 300 items, seed 42) and verify a test that the copied blocks equal the campaign's.
- [ ] 3.2 Build and freeze the held-out manifest (2,400 attempts) and verify it rebuilds byte-for-byte from the sources, every prompt parses, and no item belongs to the wide or core sets.
- [ ] 3.3 Implement the held-out runner on the MC-93 engine for Qwen3.5-9B-65K on the IEC endpoint (gates: card, detail card, manifest and protocol hashes, endpoint identity, router v2 hash; registered limits of 4 in flight and a breaker after 4 failures) and verify the offline preflight prints `endpoint_calls=0`, passes when registered and fails for a changed rule or manifest.
- [ ] 3.4 Register MC-94 (root block, detail card, registration with the rule hash and the report keys) and commit it as `pre-register MC-94`; verify the preflight passes every gate.

## 4. Run and evaluation

- [ ] 4.1 Run the held-out phase with `--execute` on Qwen3.5-9B-65K (IEC endpoint, VPN `member-shared-tcp`, tunnel DNS) and verify 2,400 attempts complete with a constant response model id; append the run record to the MC-94 detail card.
- [ ] 4.2 Evaluate the frozen v2 rule once (first rotation primary, second as replication; McNemar of v2 against always-B and always-S with Holm; Wilson intervals; tokens with the probe; escalation share; agreeing and disagreeing items; per-dataset descriptive; token-F1 for reading) and verify the report keys equal the registered list.
- [ ] 4.3 Add the result to the Notion core-results page and the thesis plan, keeping internal hostnames and addresses out.
