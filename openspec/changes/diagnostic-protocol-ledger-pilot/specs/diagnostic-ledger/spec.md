## Purpose

Provide an offline observation ledger whose coverage, scores, and provenance are verifiable against declared benchmark artifacts and whose failure view does not erase successful observations.

## ADDED Requirements

### Requirement: Explicit artifact sources and identity verification
The system SHALL import only declared supported source families with manifest, run metadata, predictions, scores, summary, protocol/scorer references, and file checksums. It SHALL join using exact dataset, item, and replicate identities scoped to the source run. It SHALL reject duplicate keys, extra items, mismatched prompt hashes, conflicting gold/output values, and unverified manifest identities before publishing a ledger.

#### Scenario: Derived MC-72 manifest
- **WHEN** MC-72 is declared with its derived manifest and parent provenance
- **THEN** its own manifest identity is retained and parent membership/prompt equality are checked without replacing its manifest hash with the parent hash

#### Scenario: Duplicate prediction
- **WHEN** two prediction rows have the same observation key within a declared run
- **THEN** import fails with the source and key instead of selecting the last row

### Requirement: Complete observation and missingness accounting
The ledger SHALL account for every expected observation in the declared manifest, including correct answers, incorrect answers, parse failures, request errors, and missing results. Each row SHALL preserve source-run identity, `itemKey=dataset:item_id`, replicate, artifact/line references, raw prompt/response when present, source gold/prediction/scores, execution details, and known resources. Missing fields SHALL have explicit null/status/reason semantics; error/missing rows SHALL NOT become scored answers by default.

#### Scenario: Incomplete source
- **WHEN** an expected request is missing or failed
- **THEN** coverage includes that observation with an execution status, score fields are null unless an original score exists, and the source is flagged incomplete

### Requirement: Source-specific frozen score parity
For completed local-gold observations the system SHALL verify prediction and metric parity using the declared historical scorer and compare derived dataset aggregates to the supplied summary at its recorded rounding precision. It SHALL report expected, completed, scored, missing, failed, unparsed, and truncated counts separately. A mismatch SHALL block successful ledger publication; unsupported scorer versions SHALL fail explicitly.

#### Scenario: Empty parsed MC answer
- **WHEN** a completed MC output cannot be parsed under the frozen extractor
- **THEN** its original incorrect score remains in the completed scoring denominator and its parse status is separately recorded

#### Scenario: Reading lexical parity
- **WHEN** a completed reading observation uses the supported V1 scorer
- **THEN** its final-answer extraction, EM, token-F1, and recorded legacy scores reproduce the original score fields without semantic-audit overrides

### Requirement: Failure view and conservative security projection
The system SHALL derive a failure view while retaining the all-observation ledger and SHALL distinguish execution/format/measurement flags from unproven capability hypotheses. It SHALL import only allowlisted metadata fields, exclude credentials and authorization headers, and publish local outputs atomically without changing input artifacts or overwriting a different provenance snapshot.

#### Scenario: Rebuild against changed source bytes
- **WHEN** an output namespace already contains a different input or protocol hash
- **THEN** the rebuild fails or requires a new namespace, preserving the old snapshot

#### Scenario: Credential-bearing run metadata
- **WHEN** run metadata includes credential-source details or authorization fields
- **THEN** ledger metadata omits those fields and does not serialize the complete run object
