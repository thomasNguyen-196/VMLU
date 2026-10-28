## 1. Retrieval, items and procedure

- [x] 1.1 Write `data/diagnostic_k2/retrieval_k2.json` (passage corpus of the three pinned ViBidLQA splits, query = question, corpus v0 tokens with bigrams, BM25 k1 1.2 b 0.75, top 2, ties by corpus order) and `data/diagnostic_k2/procedure_k2.json` (candidates always-B, always-K, K cascade, always-KS; 60 calibration items; mean token-F1; tie toward the more thorough; probe K x2 `normalized-answer-v1`). Loaders refuse unknown keys or values. Verify with unit tests. (2026-10-27: `retrieval_k2.json` sha256 693916f2…, `procedure_k2.json` e7f2daa7…; `diagnostic_k2.load_retrieval_config` and `load_procedure`; `TestConfiguration`.)
- [x] 1.2 Allow a probe of arm K in `diagnostic_router` and keep B-probe rules unchanged. Verify that router v2 and every v3 rule still validate and route as before, a K-probe rule validates, and an S probe is refused. (2026-10-27: `diagnostic_router.PROBE_ARMS = ("B", "K")`; the v3 procedure keeps its B probe explicitly. The router, calibration, v2 and v3 tests pass unchanged, and `TestRules` covers the K and S probes.)
- [x] 1.3 Implement the K2 module:
  - corpus and BM25 index;
  - the closed-book pool (outside MC-95), the sample of 360 with 60 calibration items;
  - the prompts of B, K, KS and O;
  - the manifest with each item's retrieval record;
  - the procedure's choice with the tie toward thoroughness;
  - the rule emission.

  Verify with unit tests on synthetic draws:
  - equal scores choose the more thorough candidate;
  - the cascade returns KS on disagreement with both K answers in its cost;
  - the emitted rule routes like the chosen candidate;
  - the K prompt carries the two retrieved passages and O the own passage;
  - no prompt carries the gold.

  (2026-10-27: `code_benchmark/diagnostic_k2.py`; `TestChoice`, `TestRules`, `TestPrompts`.)

## 2. Set, runner and registration

- [x] 2.1 Write `data/diagnostic_k2/protocol.json` with these contents:
  - the model, transport, scoring and budget blocks of the campaign protocol;
  - the dataset `bidlqa-train-retrieval`, 360 items with 60 for calibration, seed 42;
  - arms B, K, KS and O with 2 draws each;
  - the closed-book prompt;
  - the analysis block.

  Build and freeze `heldout_k2.json`. Verify that:
  - it rebuilds from the sources;
  - no item belongs to MC-95;
  - every K and KS prompt parses as a frozen reading prompt.

  (2026-10-27: `protocol.json` sha256 a8c5d481…. `heldout_k2.json` has self-hash 366bf449…, 360 items and 2,880 attempts, and a corpus of 863 passages with hash b501bdcb…. The pool outside MC-95 holds 1,488 items. On the 300 test items the own passage is at rank 1 for 184 and in the top 2 for 231; on the 60 calibration items, 40 and 46. Covered by `TestFrozenManifest`.)
- [x] 2.2 Implement `run_k2_heldout.py` on the campaign engine with the gates of the spec and the registered limits. Verify that the offline preflight prints `endpoint_calls=0`, passes when registered and fails for a changed retrieval configuration, procedure or manifest. (2026-10-27: `code_benchmark/run_k2_heldout.py`; `TestK2Gates`.)
- [x] 2.3 Implement `analyze_diagnostic_router k2`. Verify with a hand-worked synthetic case covering:
  - the calibration choice per rotation and the emitted rule;
  - the sign-flip tests with Holm;
  - the per-policy metrics, regret and retrieval split;
  - the report keys.

  (2026-10-27: `analyze_diagnostic_router k2` (`evaluate_k2`, `sign_flip_p`, `bootstrap_mean_ci`); `TestStatistics` and `TestK2Evaluation`.)
- [x] 2.4 Register MC-96 (root block, detail card, `registration.json` with the hashes and report keys) and commit it as `pre-register MC-96`. Verify that the preflight passes every gate. (2026-10-27: root block in `measurement_card.md`, `docs/measurement_cards/MC-96-diagnostic-k2-retrieval.md`, `data/diagnostic_k2/registration.json` with the procedure hash e7f2daa7… and the report keys. The offline preflight passes all five gates with `endpoint_calls=0`.)

## 3. Run and evaluation

- [x] 3.1 Run the K2 set with `--execute` (IEC endpoint, VPN `member-shared-tcp`, tunnel DNS). Verify that 2,880 attempts complete with a constant response model id, and append the run record to the MC-96 detail card. (2026-10-28: two launches. The first stopped on a missing retrieval trace after 8 B and O attempts, before any K or KS request. The runner was fixed in `3b0841c` and the run resumed. 2,880 of 2,880 attempts completed with a constant response model id and 3,106,511 reported tokens. The run record is in the card.)
- [x] 3.2 Evaluate once with `analyze_diagnostic_router k2`, and verify the report keys. (2026-10-28: run once, and the keys of `analysis/k2_report.json` match the registration. Token-F1 figures below are percentages.
  - Rotation 1 (primary). Calibration chose the K cascade: always-B 13.6, always-K 56.5, cascade 61.7, always-KS 59.6. On the 300 test items the router (the cascade, 169 items sent to KS) scored 62.0. Always-K scored 59.7 (Holm p 0.151) and always-KS 61.0 (Holm p 0.300), so the confirmatory test is not met. The router used 3,946 reported tokens per item, against 1,442 for always-K and 1,920 for always-KS.
  - Rotation 2 (replication). Calibration chose the cascade again. The router scored 60.7, against 58.7 for always-K (Holm 0.150) and 58.2 for always-KS (Holm 0.025).
  - The cascade was best in hindsight in both rotations, so regret was 0.
  - O scored 66.6 and always-B 14.5. On the 231 items whose own passage is in the top 2, K scored 67.9 and O 67.9. On the 69 others, K scored 32.0 and O 62.1.)
- [ ] 3.3 Add the result to the Notion core-results page and the thesis plan, keeping internal hostnames and addresses out.
