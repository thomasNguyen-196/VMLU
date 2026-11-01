## Purpose

ViBidLQA questions asked without their passage, a frozen corpus of ViBidLQA passages with BM25 top-2 retrieval, and the four arms that answer them: closed book, retrieved passages, retrieved passages with reasoning, and the question's own passage as a ceiling.

## ADDED Requirements

### Requirement: Closed-book task variant
The K2 set SHALL contain ViBidLQA train questions under the dataset id `bidlqa-train-retrieval`. A question qualifies when it appears once across the train, val and test splits and was not among the items of MC-95. The source files SHALL be pinned by SHA-256.

The set SHALL hold 360 items: the lowest sha256(seed, dataset:item) ranks, with seed 42. The 60 lowest-ranked items SHALL be the calibration items, and the manifest SHALL record them.

#### Scenario: Item used by MC-95
- **WHEN** a ViBidLQA train question belongs to the MC-95 manifest
- **THEN** it is not in the pool of the K2 set

### Requirement: Frozen passage corpus and retrieval
The corpus SHALL be the unique passages of the three pinned ViBidLQA splits, unique after NFC, case folding and whitespace collapse. Each passage SHALL be identified by the SHA-256 of its normalized text and kept in id order.

Retrieval SHALL follow a registered configuration:

- **Query:** the question text.
- **Tokens:** NFC lower-cased runs of word characters plus adjacent pairs.
- **Scoring:** BM25 with k1 1.2 and b 0.75.
- **Ties:** corpus order.
- **Kept:** the two best passages.

The manifest SHALL record, for every item, the two passage ids and scores and whether the item's own passage is among them. A configuration with another unit, query, top-k or tokenizer SHALL be refused.

#### Scenario: Deterministic ranking
- **WHEN** the corpus and configuration are rebuilt from the pinned sources
- **THEN** every item's two passages and scores equal the frozen record

### Requirement: Arm prompts
Each item SHALL have four arms with two draws each:

- **B (closed book):** the registered closed-book prompt with the question.
- **K:** the frozen ViBidLQA reading prompt, whose passage slot holds the two retrieved passages in rank order separated by a blank line.
- **KS:** the frozen S reading prompt with the same two passages.
- **O:** the frozen ViBidLQA reading prompt with the item's own passage. O is a ceiling and is never deployable.

No prompt SHALL carry the gold answer. B, K and O SHALL be scored on the raw response and KS from the text after its last final-answer label, by the frozen scorers of the prospective campaign.

#### Scenario: Retrieval misses the own passage
- **WHEN** the item's own passage is not among the two retrieved passages
- **THEN** the K and KS prompts still carry the two retrieved passages, and only O carries the own passage

### Requirement: K2 run gates
Execution SHALL require all of the following:

- the registered card heading and detail card;
- the registered SHA-256 of the K2 protocol, campaign protocol, prompt templates, retrieval configuration and manifest;
- the campaign's endpoint and model;
- the registered SHA-256 of the K2 procedure.

The registered limits of 4 requests in flight and a breaker after 4 network failures SHALL apply, and other values SHALL be refused. Without `--execute`, the runner SHALL send no request.

#### Scenario: Changed retrieval configuration
- **WHEN** the retrieval configuration differs from its registered SHA-256
- **THEN** execution is refused before any request
