## 1. Contract and prompts (offline)

- [x] 1.1 Add `data/diagnostic_prospective_v1/protocol.json` (arms, phases, caps, replicate policy, eligible datasets, extractor and analysis ids) and `prompt_templates_v1.json`; verify with a loader test that rejects unknown arms or phases and prints each template's SHA-256.
- [x] 1.2 Implement arm prompt builders in `code_benchmark/diagnostic_prospective.py` that derive S, O, K and KS from the frozen main-v1 prompts by head and tail surgery; verify B prompts equal the main-v1 prompt hashes for all 1,299 items and that a corrupted skeleton exits with the item key.
- [x] 1.3 Implement the evidence-record validator (verbatim provisions, hashes, no answer letters or rationales, Legal-MC-only eligibility); verify unit tests for leakage, an ineligible item and a hash mismatch.

## 2. Manifests (offline)

- [x] 2.1 Build the `core` manifest from the locked pilot selection (60 anchors, `<ARM>-r<k>` ids, item-major order); verify 360 B/S attempts, plus 36 oracle attempts when 12 oracle records are supplied (K and KS add 72 once retrieval evidence exists), and unique run keys.
- [x] 2.2 Build the `wide` manifest (1,239 non-anchor items, arms B and S, replicate r1); verify 2,478 attempts, per-dataset item counts 134/138/188/188/591 and disjointness from core.
- [x] 2.3 Freeze the wide manifest as `data/diagnostic_prospective_v1/wide_v1.json` with an overwrite guard (2026-10-22, manifest SHA-256 `d5f022d6…c5e432e5c297`); verify that the committed file equals the manifest the runner rebuilds and that the registration hashes match (`test_committed_wide_registration_matches_its_frozen_artifacts`).
- [ ] 2.4 (blocked until the oracle evidence of task 7.1 exists) Freeze the core manifest the same way; verify the same equality.

## 3. Scoring and parity (offline)

- [x] 3.1 Implement the per-arm scoring wrapper (frozen chain for B/O/K, final-segment rule for S/KS, per-arm summaries, format-compliance fields); verify B parity against the frozen scorer on a fixture of historical-style responses.
- [x] 3.2 Add fixtures for reasoning that mentions other options, markdown on the final line, a missing label and reading final lines; verify each expected prediction in the unit tests.

## 4. Runner (offline until gated)

- [x] 4.1 Implement `code_benchmark/run_diagnostic_prospective.py`: preflight with `endpoint_calls=0`, fail-closed gates, condition freeze, process-local resolver shim and token budget guard; verify the preflight exits 0 offline and prints item, arm and attempt counts.
- [x] 4.2 Add `code_benchmark/test_diagnostic_prospective.py` with a fake transport covering execute, resume refusal on a changed condition, budget pause and each gate; verify `.venv/bin/python -m unittest code_benchmark.test_diagnostic_prospective` passes.
- [x] 4.3 Run `uvx ruff@0.16.1 check .`, the bandit command from CI and both CI test suites; verify exit code 0 for each (the repo-wide `ruff check .` also reports 9 findings in the untracked scratch file `.codex/probe_muse13_provider.py`, which this change does not touch; the new files are clean).

- [x] 4.4 Add the opt-in operational guards after two endpoint stalls on 2026-10-22 (`--max-in-flight`, `--stop-after-timeouts`, `--note`, `operator_events.jsonl`); verify `.venv/bin/python -m unittest code_benchmark.test_diagnostic_prospective` passes (45 tests) and that the registered path (no options) is unchanged.

## 5. Prompt development on synthetic prompts

Model Qwen3.5-9B-65K (served as `Qwen3.5-9B-Q4_K_M.gguf` by llama.cpp), endpoint `http://llmapi.iec/v1` over the IEC VPN (profile `member-shared-tcp`), Responses API, streaming, temperature 1.0, output cap 4096.

- [x] 5.1 Write a synthetic development set of at least 36 prompts (multiple choice and reading, no benchmark text); verify by hash that none equals a main-v1 prompt.
- [x] 5.2 Iterate S wording until final-label compliance on the synthetic set is at least 95% (met by the first draft on two independent seeds, 72/72); verify `synthetic-dev-results.md` records the seeds, outcomes and the template hash used. The hash is frozen in `registration.json` at task 6.4.

## 6. Pre-registration package

- [x] 6.1 Draft the core and wide measurement cards and `preregistration-draft.json` in this change folder; verify every field of `data/diagnostic_v1/experiment_preregistration_template.json` is mapped or explicitly marked not applicable.
- [x] 6.2 Write the analysis-plan section (tests, corrections, intervals, seeds, router-rule placeholder); verify it names every metric the analysis code computes.
- [ ] 6.3 (blocked until `audit-report.json` is final) Copy the confirmed controls into `data/diagnostic_v1/protocol.json`; verify `diagnostic.py` readiness lists no unresolved control and rebuild the pilot only if the demo page is still needed.
- [x] 6.4 Register the wide card as MC-90 in `measurement_card.md` and `docs/measurement_cards/` and commit with a title containing `pre-register MC-90` (the wide card needs neither 6.3 nor the completed audit: it touches no anchor); verify the runner's preflight reports every gate PASS with `endpoint_calls=0`.
- [ ] 6.5 (blocked until 6.3) Register the core card in the same way and fill the core entries of `registration.json`.

## 7. Evidence and corpus (blocked until the 12 Legal MC anchors are audited)

- [ ] 7.1 Extract oracle evidence from the audit `evidence_reference` values and the provision texts; verify the validator accepts all 12 records.
- [ ] 7.2 Build corpus v0 (full texts of the cited documents plus distractors, chunked by article, hashed, provenance recorded); verify that no benchmark answer, model output or gold text is present.
- [ ] 7.3 Implement lexical retrieval with a hashed configuration and a retrieval trace; verify the reviewer-cited article appears in the top k for the 12 anchors or that the misses are listed.

## 8. Execution (wide: registered as MC-90; core: blocked until 6.5)

Model Qwen3.5-9B-65K, endpoint `http://llmapi.iec/v1` over the IEC VPN (profile `member-shared-tcp`), self-reported `Qwen3.5-9B-Q4_K_M.gguf`, resolver shim via `172.16.30.1`.

- [ ] 8.1 Run `wide` with `--execute`; verify 2,478 attempts complete, the response model id is constant and per-arm summaries are written.
- [ ] 8.2 Run `core` after 6.5 and `inference_ready`; verify 396 attempts complete (B 180, S 180, O 36; 468 only if K and KS are later registered for the same anchors) and `condition.json` matches the card.
- [ ] 8.3 Register both outputs as diagnostic ledger sources; verify the coverage and score-parity reports pass.

## 9. Analysis code (offline, before data)

- [x] 9.1 Implement paired outcomes, rescue, regression and net gain; verify unit tests reproduce the worked example in the scoring spec.
- [x] 9.2 Implement exact McNemar, Wilson and passage-cluster bootstrap intervals and Holm correction; verify against hand-computed small cases.
- [x] 9.3 Implement the noise-floor oracle ceiling and the two-direction discordant-pair export; verify on synthetic outcomes.
- [x] 9.4 Add the plan additions agreed on 2026-10-22 (B-versus-B replicate noise reference, compliant-only sensitivity, reading token-F1 difference with a format-suspect rescue flag, wide-only parity gate against MC-83); verify the 23 analysis tests pass, including the test that the protocol names every reported metric.

## 11. Wide noise reference (supplement `wide-b-r2`, card MC-91; added 2026-10-22 after the MC-90 results)

- [x] 11.1 Implement registered supplements in the contract and the runner (own registration entry, manifest, card, output directory and registered operational limits); verify the registered MC-90 manifest and condition are unchanged and that the supplement manifest reuses the B-r1 prompt, input and gold hashes under `B-r2`.
- [x] 11.2 Implement `noise_reference` (drift, B-versus-B noise, S against a second baseline draw, S against noise given the first draw, stable categories, oracle with a noise floor, Holm over four contrasts); verify the hand-worked example in the tests.
- [x] 11.3 Register MC-91: root block, detail card, registration entry with the frozen manifest hash and the analysis keys; verify the runner's preflight reports every gate PASS with `endpoint_calls=0` and that the registration-lock tests pass.
- [x] 11.4 Run `wide-b-r2` with `--supplement wide-b-r2` over the VPN; verify 1,239 attempts complete, the response model id is constant and `operator_events.jsonl` records the registered limits. (2026-10-22 18:55-19:04 +07, one launch, no failed attempt.)
- [x] 11.5 Run `noise_reference` on the MC-90 and MC-91 scores; report the parity gate and the drift check first, then the noise rates and the S-versus-noise contrasts. (`analysis/noise_report.json` under the MC-91 output directory.)
- [x] 11.6 Add the dated run record of MC-91 to its detail card after the run ends.

## 12. Semantic review of the MC-90 discordant pairs (AI-assisted, blind; added 2026-10-22)

- [ ] 12.1 Build a reproducible, seeded review packet: every EM-discordant reading item (rescue: the B answer; regression: the S answer) and a stratified sample of the both-wrong items (both answers), as separate blind units without arm, direction or stratum; verify the key file maps every unit back and the packet carries no arm information.
- [ ] 12.2 Have two independent reviewers label each unit against the gold answer (correct, partial, incorrect) with a one-line reason; adjudicate the disagreements blind; verify the label files cover every unit.
- [ ] 12.3 Unblind and estimate the semantic rescues, regressions and net effect with a stratified interval; report agreement between reviewers and state that the review is AI-assisted and not a blind human review.

## 10. Verification and handoff

- [x] 10.1 Run `openspec validate diagnostic-prospective-campaign --strict`; verify it passes.
- [x] 10.2 Record the compatibility impact in this change (existing artifacts, frozen scorers, `protocol.json` and the pilot packet unchanged); verify with `git status` that only new files appear.
