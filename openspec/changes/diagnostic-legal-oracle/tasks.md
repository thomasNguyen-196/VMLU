## 1. Selection and evidence (offline)

- [x] 1.1 Write `data/diagnostic_legal_oracle/protocol.json` (selection rule and sources) and `select_items` in `code_benchmark/diagnostic_legal_oracle.py`. Verify:
  - the 134-item pool, with both draws present;
  - 28 `wrong` and 28 `right` items.

  (2026-10-29: `wrong` = 28, 12 of them missed on both draws; `right` = 28.)
- [x] 1.2 Locate the oracle provisions for the 56 items with four agents blind to the stratum. Store every source page with its SHA-256.

  (2026-10-29: 66 pages stored. Provisions for 53 items: 74 provisions from 45 documents. Nothing found for 3 items: LG-0007 cites a Party notice without articles; LG-0024's page skips the governing articles; LG-0070 cites a 2025 draft decree that is not on the site. One location was amended per the agent's own note: LG-0126 names the attached Quy chế (`part`); the raw row is kept beside the batch file.)

  (Correction, 2026-10-29 evening: the agents' working files, including that raw row and the batch files, sat in a temporary scratchpad that a machine restart at 20:10 +07 cleared. The frozen evidence file, the stored pages, the review sheet and the owner's review in `all_res/diagnostic_legal_oracle/` remain.)
- [x] 1.3 Build the evidence records by code: verbatim article text, or heading line and named clauses. Write the owner's review sheet for the 14-item sample.

  (2026-10-29: 56 draft records, all built from the stored pages: `supports_gold` 48, `contradicts_gold` 2, `unclear` 3, `not_found` 3. 8 provisions are clause cuts of articles over 6,000 characters; evidence per item has a mean of 2,587 characters and a maximum of 7,172. Two reader exceptions were added before any freeze and recorded in the design and the protocol's `reader`: a page breaking off inside its last article (NĐ 99/2022), and attached Quy chế without article markup (QĐ 05/2025/QĐ-TTg, QĐ 21/QĐ-SGDVN). Review sample: LG-0001, 0021, 0027, 0028, 0038, 0065, 0072, 0078, 0082, 0111, 0122, 0137, 0138, 0142.)
- [x] 1.4 Import the owner's review, freeze `oracle_evidence_v1.jsonl` and report agent–owner agreement.

  (2026-10-29: reviewer `nttung245`, AI-assisted. Agreement 14/14. The owner's option equals the gold on 12 of 14; on LG-0001 and LG-0082, both `contradicts_gold`, it is the option the agent had read from the law. Final labels: `wrong` 23 `supports_gold`, 2 `contradicts_gold`, 3 `unclear`; `right` 25 `supports_gold`, 3 `not_found`. Evidence SHA-256 `367632d7…`; owner review `9e69313c…`, kept in `all_res/`.)

## 2. Manifest, runner and analysis (offline)

- [x] 2.1 Build and freeze `manifest_v1.json`: B for all items, O for items with a provision, two draws each. Verify:
  - the B prompts equal the frozen main-v1 prompts byte for byte;
  - no prompt carries the gold.

  (2026-10-29: 218 attempts, B 112, O 106; self-hash `4eb235e6…`. The manifest stores `gold_sha256` only, as the campaign manifests do.)
- [x] 2.2 Implement `code_benchmark/run_legal_oracle.py` on the campaign engine, with these gates: card heading, detail card, frozen hashes, endpoint identity. Verify that the offline preflight prints `endpoint_calls=0`.

  (2026-10-29: all four gates pass; `endpoint_calls=0`.)
- [x] 2.3 Implement `code_benchmark/analyze_legal_oracle.py` (plan `diagnostic-legal-oracle-v1`). Verify on synthetic data:
  - the primary set and the strata;
  - the reading rule's two conditions.

  (2026-10-29: unit tests, plus one end-to-end pass on synthetic scores for all 218 attempts, deleted afterwards: the report keys match the registration and the gold check reads the hashed owner review.)

## 3. Registration and run (MC-100)

- [x] 3.1 Register MC-100:
  - the root block;
  - the detail card;
  - `registration.json` with the frozen hashes.

  Commit as `pre-register MC-100`.
- [x] 3.2 Run with `--execute`, with the VPN on. Verify:
  - every attempt is complete;
  - one response model throughout.

  Append the run record to the detail card.

  (2026-10-29 15:55–15:56 +07, one launch: 218/218 complete, finish reason `stop` throughout, the registered model id in every row, none at the cap, none unparsed, 132,134 tokens. Run record appended; VPN closed after the run.)
- [x] 3.3 Run the analysis once, apply the reading rule and report it here.

  (2026-10-29, report SHA-256 `f0ac91f0…`. Primary set, O against fresh B:
  - `wrong` (23 items): B 37.0%, O 82.6%, +45.7 points (95% bootstrap +26.1 to +63.0; sign-flip p = 0.0004); 17 items better, 2 worse, 4 equal; 6 clear rescues, no clear regression.
  - `right` (25 items): B 94.0%, O 96.0%, +2.0 points (−4.0 to +10.0; p = 1.0); no clear rescue or regression.
  - **Reading rule met** (gain ≥ 20 in `wrong`, loss ≤ 10 in `right`): a retrieval study on Legal MC is worth building.

  Descriptive:
  - `wrong` items missed on both earlier draws: 20.8% → 70.8%; missed on one: 54.5% → 95.5%.
  - `unclear` (3 items): 33.3% → 50.0%.
  - `contradicts_gold` (2 items, scored against the gold): 50.0% → 25.0%. Gold check on those two items, four answers per arm: B picked the gold's option 2 times and the owner's 1; O picked the gold's 1 time and the owner's 3. With the law in hand, Qwen moved to the option the law supports.
  - Share answering A: B 50.9%, O 53.8%. Mean tokens per attempt: B 229, O 1,005.)
