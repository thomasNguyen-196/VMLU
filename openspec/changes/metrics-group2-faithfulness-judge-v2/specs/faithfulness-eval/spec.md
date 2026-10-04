## MODIFIED Requirements

### Requirement: Validated judge instrument
Before any full judge pass, the judge SHALL be validated against human labels
on a pre-registered sample: raw agreement ≥ 80% and Cohen's κ ≥ 0.6, with the
judge verdicts hidden from the labeler. On failure, at most one documented
prompt iteration is allowed; a second failure SHALL stop the measurement and
publish the instrument-failure result instead of a faithfulness score.

The instrument SHALL be selected on a **dev** sample and gated on a **fresh
test** sample disjoint from it; a changed instrument (model, prompt, or decoding
config) SHALL be a new pre-registration, never a retroactive pass of an earlier
gate.

#### Scenario: Gate passed
- **WHEN** agreement and κ meet the thresholds on the frozen labels
- **THEN** the full judge pass may run and the results card reports the gate numbers.

#### Scenario: Gate failed twice
- **WHEN** the iterated judge still misses a threshold
- **THEN** no faithfulness metric is published, and the card records the
  agreement/κ numbers as the outcome of the line of work.

#### Scenario: Instrument selected on dev, gated on fresh test
- **WHEN** a judge instrument is chosen using one labeled sample
- **THEN** the gate runs on a different, disjoint sample whose labels are
  committed before any verdict is produced for it, and the results card states
  which sample was dev and which was test.

### Requirement: Format-only re-ask
The judge tool SHALL re-ask an item only when the reply fails to parse, and
SHALL record a `judge_error` when every attempt fails; it SHALL NOT infer a
verdict from keywords or partial output.

#### Scenario: Unparseable reply
- **WHEN** every attempt returns text with no valid verdict
- **THEN** the item is a `judge_error`, the validation refuses to score it, and
  no verdict is guessed.
