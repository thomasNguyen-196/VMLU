## 1. Worklist and corpus sources (offline)

- [x] 1.1 Write `data/diagnostic_legal_retrieval/protocol.json`: pool, reuse of MC-100's strata and evidence, corpus roles and caps, reader, unit, retrieval, arms, analysis and operational limits. Add a worklist command that writes the 134 question stems without options or gold. Verify:
  - 134 stems;
  - a test checks that no stem holds an option line or the gold.

  (2026-10-29: `diagnostic_legal_retrieval stems` wrote 4 batches of 34, 34, 33 and 33 stems to `all_res/diagnostic_legal_retrieval/source_lists/`; no stem holds an option line or "Đáp án". The agents' files live in `all_res/`, not in a temporary scratchpad, after the restart that cleared MC-100's.)
- [x] 1.2 Four agents list the documents for their stems (hethongphapluat.com only):
  - up to 3 `topical` documents per item;
  - their `predecessor` documents;
  - up to 5 `distractor` documents per batch.

  Merge the lists by URL and freeze `corpus_sources_v1.json`. Verify:
  - every item has a topical document or is listed as uncovered;
  - every role is valid and every URL is https;
  - a test shows the merge is deterministic.

  (2026-10-29: 303 documents, SHA-256 `852286d5…`: 193 topical, 98 predecessor, 12 distractor. Uncovered: LG-0007, whose notice is not on the site. The merge first stopped on 09/VBHN-VPQH, a number printed on two consolidated texts of different years. Consolidated numbers restart each year, so the merge now qualifies such a number by the year its page title prints (2022, 2025); any other clash still fails. Batch 4 had already written 13/VBHN-VPQH (2013) and (2023) this way. The rule is in the protocol's `merge` and has a test.)

## 2. Corpus (offline)

- [x] 2.1 Implement reader v1 (MC-100's reader, plus footnote-marker headings and attached documents read whole) and the unit split (articles over 6,000 characters cut at line boundaries). Verify with tests:
  - a footnote-marker heading;
  - an attached Quy chế with several articles, ending at a signature line;
  - a 48,000-character article split into parts of at most 6,000 characters, each opening with the heading;
  - unique unit ids.
- [x] 2.2 Fetch and store every page, build `corpus.jsonl` and its manifest, run the leak check and list omitted documents. Verify:
  - every page matches the SHA-256 in its fetch log;
  - the leak check passes.

  Report here the counts of documents, units and omitted documents.

  (2026-10-29: all 303 pages stored and hash-checked; the store also holds pages the agents checked but did not list, 358 in all. 24,265 units (1,581 parts of split articles), 36.0 million characters, from 302 documents; omitted: QCVN 113:2024/BGTVT, whose page has no article elements. Leak check passed; 6 options occur verbatim. Corpus SHA-256 `66e4a349…`. The corpus is about twice the size first expected, because the agents listed predecessors for most topical documents.)

## 3. Retrieval and K evidence (offline)

- [x] 3.1 Write `retrieval_v1.json` (the `bm25-article-v0` settings, top 2, the unit) and build and freeze the K evidence for the 134 items. Verify:
  - every record has two units with matching text hashes, plus the corpus and configuration hashes;
  - no record carries an answer-bearing key;
  - a test shows the loader rejects a swapped unit.

  (2026-10-29: K evidence SHA-256 `97d058b2…`, 134 records; a mean of 5,237 characters per item, maximum 11,736; of the 268 units, 213 come from topical documents, 54 from predecessors, 1 from a distractor.)
- [x] 3.2 Report hit@1, hit@2 and hit@3 against MC-100's oracle articles on its 53 items, and the document overlap. Write them here before registration. If hit@2 is below 50%, pause before registration and report to the owner. Verify: all 53 items are covered.

  (2026-10-29, before registration: hit@1 31, hit@2 40, hit@3 41 of 53. Hit@2 is 75%, above the pause threshold. The corpus holds 43 of MC-100's 45 oracle documents; 52 of the 53 items have one of theirs in it.)

## 4. Manifest, runner and analysis (offline)

- [x] 4.1 Build and freeze the manifest: B and K on the 134 items, O on the 53 with provisions, two draws each, 642 attempts. Verify:
  - the B prompts equal the main-v1 prompts byte for byte;
  - each K prompt is its block followed by the frozen prompt;
  - the O prompts equal MC-100's;
  - no prompt carries the gold;
  - the MC-100 file hashes are checked.

  (2026-10-29: self-hash `fb055964…`; B 268, K 268, O 106; the manifest test passes on the real files.)
- [x] 4.2 Implement `code_benchmark/run_legal_retrieval.py` on the campaign engine, with these gates: card heading, detail card, frozen hashes, endpoint identity; and the registered limits. Verify:
  - the offline preflight prints `endpoint_calls=0`;
  - a gate test.

  (2026-10-29: the runner hands the engine a retrieval trace for every K row, built from the frozen K evidence. All four gates pass offline, with `endpoint_calls=0`.)
- [x] 4.3 Implement `code_benchmark/analyze_legal_retrieval.py` (plan `diagnostic-legal-retrieval-v1`). Verify on synthetic data:
  - the primary comparison and the reading rule in both directions;
  - the stratum blocks and the hit and miss split;
  - the gold check;
  - the report keys.

## 5. Registration and run (MC-101)

- [x] 5.1 Register MC-101: the root block, the detail card, and `registration.json` with every hash and the report keys. Commit as `pre-register MC-101`. Verify that the offline preflight passes every gate.
- [ ] 5.2 Run with `--execute` on Qwen3.5-9B-65K at the IEC endpoint: openvpn3 `member-shared-tcp`, endpoint host resolved through the in-tunnel DNS. Verify:
  - every attempt is complete;
  - one response model throughout.

  Append the run record to the detail card, then close the VPN.
- [ ] 5.3 Run the analysis once, apply the reading rule and report it here.
