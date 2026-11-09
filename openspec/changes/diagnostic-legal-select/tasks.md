## 0. Owner approval

- [x] 0.1 The owner approves the design, or changes it. The choices the owner can change:
  - the depth (k = 10);
  - the candidate order (rank order);
  - the fallback for an unparsed selection (BM25's top 2);
  - the two Holm-adjusted questions;
  - the K10 control.

  Nothing below is built until the owner approves.

  (2026-11-08: the owner approved the design unchanged: "ok duyệt thiết kế, bắt đầu viết code đi".)

## 1. Pre-check and candidates (offline)

- [x] 1.1 Move the post hoc pre-check from the scratchpad to `code_benchmark/analyze_legal_retrieval_misses.py`, with a test, and record its output here. Verify that it reproduces the numbers in proposal.md:
  - 13 misses: 1 missing document, 3 in the same document, 9 in other documents;
  - the document-oracle ceiling: hit@2 45 of 53.

  (2026-11-08: 53 items.
  - **Classes:** 40 hit, 1 `doc_missing`, 0 `unit_missing`, 3 `same_doc`, 9 `other_doc`.
  - **Corpus agents:** they had listed the oracle document for that very item in 11 of the 13 misses.
  - **Document-oracle ceiling:** hit@2 45. It turns LG-0021, LG-0072, LG-0099, LG-0111 and LG-0125 into hits, items where K scores 50.0 and O 90.0.
  - **On hits:** B 72.5, K 76.2, O 83.8.
  - A test on the real files checks the classes and the ceiling.)
- [x] 1.2 Write `data/diagnostic_legal_select/protocol.json` and `select_template_v1.json`. Build and freeze `candidates_v1.jsonl` for the 134 items. Verify:
  - 10 units per record, each with a matching text hash;
  - the first two units equal MC-101's K evidence;
  - oracle coverage at depth 10 is 47 of 53;
  - no record carries an answer-bearing key.

  (2026-11-08: candidates SHA-256 `c348085a…`, 134 records. The loader checks every unit against the corpus and the first two against MC-101's K evidence. Oracle coverage at depth 2, 5 and 10: 40, 42 and 47 of 53. Characters per record: mean 28,725, maximum 58,170. Protocol `7b8c338a…`, selection template `1112aaca…`.)

## 2. Parser, prompts and manifests (offline)

- [x] 2.1 Implement the selection prompt renderer and the parser. Verify with tests:
  - one and two numbers;
  - `Không có`;
  - three numbers with a duplicate;
  - out-of-range numbers;
  - backticks and bold;
  - no selection line;
  - a line that names a number and `không có`.

  (2026-11-08: covered by `TestParser` and `TestPrompts`. Two more cases are tested: the last selection line wins, and the label is case-insensitive.)
- [x] 2.2 Build and freeze the round-1 manifest: B, K, K10 and SEL step 1 on the 134 items and O on the 53, two draws each, 1,178 attempts. Implement the round-2 builder from a ledger. Verify:
  - B prompts equal the main-v1 prompts byte for byte;
  - K prompts equal MC-101's;
  - O prompts equal MC-100's;
  - no prompt carries the gold;
  - the round-2 builder is deterministic and maps draw r to draw r, on a synthetic ledger.

  (2026-11-08:
  - **Manifest.** `manifest_round1_v1.json`, self-hash `fb53e15f…`, file SHA-256 `c968f6cf…`. It holds 1,178 attempts: B 268, K 268, K10 268, PICK 268, O 106.
  - **Prompts.** B, K and O equal MC-101's prompts byte for byte, and no prompt carries an answer-key line.
  - **Round-2 builder.** Tested on a synthetic ledger, including an incomplete PICK, which stops round 2.
  - **Shared arm list.** `diagnostic_prospective.ARMS` gains K10, PICK and SEL, as it gained Q before. MC-110's condition records that module's hash only as `wrapper_sha256`, an implementation field, so its resume is unaffected.)

## 3. Runner and analysis (offline)

- [x] 3.1 Implement `code_benchmark/run_legal_select.py` on the campaign engine. It needs these gates: card heading, detail card, frozen hashes, endpoint identity, and round 2 only after round 1 is complete. It also needs the registered limits, including the 8,000,000-token budget guard. Verify:
  - the offline preflight prints `endpoint_calls=0`;
  - a gate test;
  - a resume test for round 2.

  (2026-11-08:
  - **Runner.** Round 1 and round 2 run in `round1/` and `round2/`, under one budget guard across both. Round 2 is built from the round-1 ledger, written once and refused on any later difference.
  - **Tests.** A gate test, and the round-2 rewrite and refusal test.
  - **Preflight.** The offline preflight needs `registration.json`, which comes with task 4.1, so `endpoint_calls=0` is checked there.)
- [x] 3.2 Implement `code_benchmark/analyze_legal_select.py` (plan `diagnostic-legal-select-v1`). Verify on synthetic data:
  - both questions in both directions;
  - the Holm adjustment;
  - selection hits with empty and unparsed selections counted as misses;
  - the stratum blocks;
  - the report keys.

  (2026-11-08: all covered by `TestAnalysis`, plus an offline end-to-end test on the real manifest with synthetic answers. It scores round 1, builds round 2, scores SEL and runs the analysis, with no request. The module and test checks:
  - `code_benchmark.test_diagnostic_legal_select`: 21 tests;
  - together with `test_diagnostic_legal_retrieval`, `test_diagnostic_prospective` and `test_suite`: 388 tests, OK;
  - `test_parsing`: OK;
  - ruff and bandit: clean on the new files.)

## 4. Registration and run (MC-111)

- [x] 4.1 Register MC-111: the root block, the detail card, and `registration.json` with every hash and the report keys. Commit as `pre-register MC-111`. Verify that the offline preflight passes every gate.

  (2026-11-09: the owner approved the registration: "okay, bạn có thể thực hiện".
  - **Files.** The root block `## MC-111` in `measurement_card.md`, the detail card `docs/measurement_cards/MC-111-diagnostic-legal-select.md`, and `data/diagnostic_legal_select/registration.json`. The registration holds the 14 frozen hashes copied from the round-1 manifest, MC-100's and MC-101's references, and the 16 report keys.
  - **Preflight.** It was run offline with `python -m code_benchmark.run_legal_select`. All four gates passed: card_registered, detail_card, frozen_hashes and endpoint_identity. It printed `endpoint_calls=0`.
  - **Tests.** The same 388 tests pass, and MC-110's 34 still pass.
  - **MC-110.** It was running at the time (launch 5). Only its `measurement_card_hash` changes, and its resume treats that field as an implementation field.)
- [x] 4.2 Run with `--execute` on Qwen3.5-9B-65K (Q4_K_M GGUF, llama.cpp) at the IEC endpoint `llmapi.iec/v1`: openvpn3 `member-shared-tcp`, endpoint host resolved through the in-tunnel DNS 172.16.30.1. Ask the owner before opening the VPN. Verify:
  - every attempt of both rounds is complete;
  - one response model throughout.

  Append the run record, with the round-2 manifest hash, to the detail card, then close the VPN.

  (2026-11-09: the owner said "bạn có thể chạy MC-111 task 4.2 nhưng cần quan sát xem có ảnh hướng đến Mimo process không".
  - **Run.** One launch, 16:25 to 16:54 +07. Round 1: 1,178 of 1,178 attempts complete. Round 2: 268 of 268 SEL attempts complete; its manifest self-hash is `db3a57eb…`. There were no failures, the response model was the same throughout and the run used 5.46M tokens.
  - **Record.** The run record, with both manifests and the output hashes, is in the detail card. The VPN was closed at 16:56.
  - **MC-110.** MiMo ran in parallel. Its route and its error pattern stayed the same while the VPN was open.)
- [x] 4.3 Run the analysis once, apply the rule and report it here.

  (2026-11-09 21:01 +07, after the owner said "okay, chạy phân tích MC-111 task 4.3 đi". Report `analysis/legal_select_report.json`, SHA-256 `5d799c2d…`; the 16 registered keys.
  - **Filter, 53 items with MC-100 oracle provisions:** PICK's selection hit 74.5%, BM25 top 2 75.5%, −0.9 points (95% bootstrap −11.3 to +9.4; sign-flip p = 1.0, Holm 1.0); 5 items better, 6 worse, 42 equal. **Not met: no evidence that Qwen filters better than BM25's order.**
  - **Route, 134 items:** always-SEL 86.2%, always-B 86.6%, −0.4 points (−5.6 to +4.9; p = 1.0, Holm 1.0); 18 better, 16 worse, 100 equal; 1 clear rescue, 4 clear regressions. **Not met: always-B stays the Legal MC route.**
  - **MC-100 stratum `wrong`, 23 items:** B 52.2%, K 65.2%, K10 54.3%, SEL 58.7%, O 80.4%. Only O beats B (+28.3; p = 0.003). Share of O's gain kept: K 46%, SEL 23%, K10 8%. SEL against O −21.7 (p = 0.017).
  - **Stratum `right`, 25 items:** B 100%, K 94%, K10 96%, SEL 94%, O 98%.
  - **The 78 items outside MC-100:** B 94.2%, K 96.2%, K10 95.5%, SEL 94.2%.
  - **Selection:**
    - 237 of 268 draws picked, 30 `none`, 1 unparsed. Most picks were 2 articles (202).
    - Positions 1 and 2 were picked most often (167 and 131), and 37% of selections were exactly BM25's top 2.
    - Precision on oracle items was 0.50.
    - On the 47 items whose top 10 holds an oracle article, a draw hit it 84% of the time.
    - On the 6 items without one, the answer was `none` in 33% of draws.
    - SEL was right in 84.8% of draws when the selection hit and 48.1% when it missed.
  - **Gold check:** on the two `contradicts_gold` items, SEL gave the gold's option 4 of 4 times, O the owner's option 4 of 4.
  - **Long context:** K10 (8.3k prompt tokens) scored no better than K (1.7k).
  - **Replication against MC-101:** pool B 86.6 (MC-101: 84.3), pool K 88.1 (84.7), `wrong` O 80.4 (84.8).)
