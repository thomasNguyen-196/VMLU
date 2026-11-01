## Why

Router v1 (MC-93) answered 39 of the 60 core anchors against 36 for always-B and 34 for always-S, but the difference is not significant (Holm p 0.50), the rule decides by dataset name only and never learns whether a particular item is hard for the model. On the wide draws, two B answers to the same question separate the items sharply: where they agree (733 items) B is right 72.3% of the time and S 66.3%; where they differ (506 items) B is right 17.4% and S 32.2%. Escalating only the disagreements to S reaches 56.7% exact match on wide against 53.1% for v1 and for always-S (design fit). The 60 core anchors are now used, so a confirmatory test of such a rule needs items that no router has seen.

## What Changes

- The router rule grammar gains an optional probe: arm B answered twice, and a condition may test whether the two normalized answers agree. The probe runs only when a condition needs it, its cost is counted, and its first answer is the B answer.
- Router v2 candidates are fitted on the wide draws (B1, B2, S1, S2) through two rotations, committed before their fits; the project owner picks one, which is frozen by SHA-256 as `router_v2.json`.
- A held-out set never used by any router: 300 ViBidLQA val items and 300 VMLU valid items (seed 42), arms B and S with two draws each (2,400 attempts), its own protocol, manifest and registration, and measurement card MC-94. The runner reuses the MC-93 engine, scorers and registered limits.
- The frozen v2 rule is evaluated once on the held-out set against always-B (which equals v1 there, since the set has no Vi-DROP item) and always-S, with token cost including the probe.
- Better retrieval for arm K (K2) is deferred to a later change.

## Capabilities

### New Capabilities
- `diagnostic-adaptive-router`: router rules with a B probe and an answer-agreement feature, lazy probing, cost accounting, and the design fit of probe rules on draws.
- `diagnostic-router-heldout`: the held-out set, its registration, and the single evaluation of the frozen v2 rule.

### Modified Capabilities
None. The v1 router contract lives in the active change `diagnostic-prospective-campaign` and is not changed; every v1 artifact (protocol, manifests, `router_v1.json`, cards MC-90 to MC-93) stays as registered.

## Non-goals

- No change to arm K, the corpus or retrieval (K2 is a later change), and no new arm prompt.
- No learned or trained router; no second model; no change to evaluation regimes.
- No re-evaluation of v1 on the core anchors; v1's registered result stands.
- No claim of a pristine held-out set: the held-out items were answered by earlier benchmark runs, though never used to design or evaluate a router.

## Evaluation regime

Regime B-style only, as MC-90 to MC-93: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint. Regimes A and C are not touched.

## Impact

- Code: `code_benchmark/diagnostic_router.py` (probe grammar and routing), `code_benchmark/analyze_diagnostic_router.py` (rotation design fit and held-out evaluation), a held-out manifest builder and a held-out runner that reuses `run_diagnostic_prospective.py`, with tests.
- Data: `data/diagnostic_router_v2/` (protocol, candidates, frozen rule, manifest, registration).
- Cards: MC-94 in `measurement_card.md` and `docs/measurement_cards/`.
- Endpoint use: about 2,400 attempts and 2 million reported tokens over the IEC VPN.
