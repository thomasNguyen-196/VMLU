## Purpose

Measure whether retrieval from a question-based legal corpus (arm K) improves Qwen3.5-9B on Legal MC over the frozen closed-book prompt (arm B), and how much of the oracle gain of MC-100 (arm O) it keeps, under a registration fixed before the first request.

## ADDED Requirements

### Requirement: Item set
The test SHALL run on the 134 Legal MC items of the wide phase, the pool of MC-100. It SHALL reuse MC-100's strata and frozen oracle evidence for the mechanism analysis, checked against their registered SHA-256. The preflight SHALL fail when the pool, the strata or the oracle evidence differ from what MC-100 registered.

#### Scenario: Changed oracle evidence
- **WHEN** `data/diagnostic_legal_oracle/oracle_evidence_v1.jsonl` no longer has the SHA-256 registered for MC-100
- **THEN** building the manifest fails and no request is sent

### Requirement: Question-based corpus built without the answer
The corpus documents SHALL be chosen from the question stems alone. Whoever chooses them SHALL NOT see the options, the gold, the strata or any MC-100 evidence. Every document SHALL come from hethongphapluat.com, its page stored with its SHA-256, and carry one role: `topical`, `predecessor` or `distractor`.

Code SHALL extract the corpus text verbatim from the stored pages. A document whose page yields no article SHALL be listed as omitted, with its reason, and never filled in by hand.

The sources list and the corpus SHALL be frozen before any retrieval query runs. The build SHALL fail when a question stem appears verbatim in the corpus or when a corpus unit carries an answer-key line.

#### Scenario: A question copied into the corpus
- **WHEN** a stored page contains a Legal MC question stem verbatim within a corpus unit
- **THEN** the corpus build fails and nothing is frozen

#### Scenario: A page without articles
- **WHEN** a listed document's stored page yields no article
- **THEN** the document is recorded as omitted with its reason, and the corpus is built from the others

### Requirement: Retrieval and frozen K evidence
For each item, the retriever SHALL rank the corpus units by BM25 with the registered configuration. The query SHALL be the item's question and options exactly as the frozen B prompt carries them, never the gold. The top 2 units SHALL form the item's K evidence.

The K evidence file SHALL record, for every item:
- the units' verbatim text and its hash;
- the ranking scores;
- the query hash;
- the corpus hash;
- the configuration hash.

It SHALL be frozen, and its SHA-256 registered, before the first request.

#### Scenario: Changed corpus
- **WHEN** the built corpus no longer matches the corpus hash recorded in the K evidence file
- **THEN** the runner refuses to run

### Requirement: Arms and rebuild
Every request SHALL send exactly the prompt of its arm:
- B: the item's frozen main-v1 prompt, byte for byte;
- K: the campaign evidence block with the item's K evidence, followed by the same frozen prompt;
- O: the campaign evidence block with the item's MC-100 oracle provisions, followed by the same frozen prompt. O runs only on items that have provisions.

Each arm SHALL run two draws. The runner SHALL rebuild the manifest from the frozen items, the K evidence, the oracle evidence and the templates, and SHALL refuse to run when anything differs. No prompt SHALL carry the gold, a support label or an agent's note.

#### Scenario: A K prompt
- **WHEN** the manifest is built
- **THEN** every K prompt is the evidence block rendered from that item's frozen K evidence followed by the item's frozen B prompt

### Requirement: Registered analysis and reading rule
The analysis SHALL be fixed before data and run once. Its item score SHALL be the mean correctness over the two draws.

The primary comparison SHALL be always-K against always-B over the 134 items: the mean per-item difference, with a percentile bootstrap interval and a two-sided paired sign-flip p-value.

The reading rule SHALL decide whether K becomes the Legal MC arm of the router: K does when its mean exceeds B's and the p-value is below 0.05.

The report SHALL also give, as description:
- per MC-100 stratum, K against B and K against O on the items whose provisions support the gold;
- retrieval hits against the MC-100 oracle articles, and K's accuracy when retrieval hits and when it misses;
- each arm's choices on the items whose provisions contradict the gold;
- mean reported tokens per arm.

#### Scenario: K helps overall
- **WHEN** always-K's mean exceeds always-B's over the 134 items with a two-sided p-value below 0.05
- **THEN** the report states that K should be the Legal MC arm of the router

#### Scenario: K does not help overall
- **WHEN** always-K's mean does not exceed always-B's, or the p-value is 0.05 or more
- **THEN** the report states that always-B stays the Legal MC route, and the per-stratum results are reported as description only
