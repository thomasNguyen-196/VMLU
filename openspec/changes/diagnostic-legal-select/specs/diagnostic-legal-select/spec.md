## Purpose

Measure whether Qwen3.5-9B, given BM25's top 10 legal units for a Legal MC item, selects the article that governs the question better than BM25's top 2, and whether answering from its own selection beats the closed-book prompt. The registration is fixed before the first request.

## ADDED Requirements

### Requirement: Item set and frozen inputs
The test SHALL run on the 134 Legal MC items of MC-101's pool. It SHALL reuse:
- MC-101's corpus, retrieval configuration and K evidence;
- MC-100's strata, support labels, oracle evidence and owner review.

Each input SHALL be checked against its registered SHA-256. The preflight SHALL fail when any of them differs.

#### Scenario: Changed corpus
- **WHEN** the built corpus no longer matches MC-101's registered corpus hash
- **THEN** building the candidates fails and no request is sent

### Requirement: Frozen top-10 candidates
For each item, the candidate file SHALL hold the top 10 units of MC-101's BM25 ranking for the item's query, in rank order. Each unit SHALL carry its verbatim text and hash, its score, and the query, corpus and configuration hashes. Each record's first two units SHALL equal MC-101's K evidence for that item. The file SHALL be frozen, and its SHA-256 registered, before the first request.

#### Scenario: Candidates disagree with MC-101
- **WHEN** an item's first two candidates differ from its MC-101 K evidence
- **THEN** the candidate build fails

### Requirement: Selection prompt and parser
The step-1 prompt SHALL be the frozen selection template rendered with:
- the item's 10 candidates in the campaign's evidence-item format;
- the item's question and options exactly as the frozen B prompt carries them.

No prompt SHALL carry the gold, a support label, a stratum or an oracle locator.

The parser SHALL read the last line starting with `Đoạn liên quan:` after NFC normalization and stripping backticks and `*`:
- It SHALL keep the integers from 1 to 10 in the order written, without duplicates, at most two.
- Without such an integer, a line containing `không có` SHALL give an empty selection.
- Any other response SHALL be `unparsed`.

#### Scenario: Three numbers
- **WHEN** the last selection line is `Đoạn liên quan: 4, 1, 4, 9`
- **THEN** the selection is units 4 and 1

#### Scenario: No selection line
- **WHEN** the response has no line starting with `Đoạn liên quan:`
- **THEN** the selection is `unparsed`, step 2 uses BM25's top 2, and the filter analysis counts the draw as a miss

### Requirement: Arms, rounds and rebuild
Every request SHALL send exactly the prompt of its arm:
- **B:** the frozen main-v1 prompt;
- **K:** the evidence block with MC-101's top 2, then the frozen prompt;
- **K10:** the evidence block with the 10 candidates, then the frozen prompt;
- **SEL step 1:** the selection prompt;
- **SEL step 2:** the evidence block with the selected units, then the frozen prompt. It SHALL be the frozen prompt alone when the selection is empty, and SHALL use BM25's top 2 when the selection is unparsed;
- **O:** the evidence block with MC-100's oracle provisions, then the frozen prompt, on items with provisions only.

Each arm SHALL run two draws. Draw r of step 2 SHALL use draw r of step 1.

Round 2 (step 2) SHALL start only after every step-1 attempt is complete. Its manifest SHALL be built from the round-1 ledger by the registered rule, self-hashed and recorded.

The runner SHALL rebuild both manifests and refuse to run when anything differs.

#### Scenario: Resume after round 1
- **WHEN** the runner resumes and the round-1 ledger yields a step-2 manifest whose hash differs from the recorded one
- **THEN** the runner refuses to run

### Requirement: Registered analysis
The analysis SHALL be fixed before data and run once. Item scores SHALL be means over the two draws. Two questions SHALL be tested, with percentile bootstrap intervals and two-sided paired sign-flip p-values, Holm-adjusted at α = 0.05:
- **Filter:** on the 53 oracle items, SEL's selection hit against BM25's top-2 hit. A hit SHALL mean that the selection holds an oracle article, matched by document number and article number with any part counting. An empty or unparsed selection SHALL be a miss.
- **Route:** always-SEL against always-B on the 134 items.

The report SHALL also give, as description:
- per stratum: B, K, K10, SEL and O, and their differences;
- the share of O's gain kept in stratum `wrong`;
- selection counts, positions, precision and recall within reach;
- SEL's accuracy by selection outcome;
- the gold check;
- tokens per arm;
- the replication of MC-101's B, K and O.

#### Scenario: Qwen filters better than BM25
- **WHEN** SEL's mean selection hit exceeds BM25's top-2 hit on the 53 items and the Holm-adjusted p-value is below 0.05
- **THEN** the report states that Qwen filters retrieved legal evidence better than BM25's order

#### Scenario: SEL does not beat B
- **WHEN** always-SEL's mean does not exceed always-B's, or its Holm-adjusted p-value is 0.05 or more
- **THEN** the report states that always-B stays the Legal MC route, and the stratum results are description only
