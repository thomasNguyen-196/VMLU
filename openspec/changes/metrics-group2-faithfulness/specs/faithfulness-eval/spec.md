## Purpose

Defines the faithfulness measurement on reading-400: a pre-registered citation
condition scored by the frozen EM/char-F1 scorer, plus a judge instrument that
must pass a human-validation gate before any faithfulness number may be
published.

## Requirements

### Requirement: Pre-registered citation condition
The citation run SHALL use a new, pre-registered prompt whose bytes are frozen
in the measurement card before any model call; the frozen
`build_reading_prompt` and `score_reading_eval.py` SHALL remain byte-identical.
The run SHALL carry a distinct label slug and SHALL NOT be compared row-to-row
with any existing reading condition.

#### Scenario: New prompt, frozen scorer
- **WHEN** the citation run completes
- **THEN** `git diff` on `run_reading_eval.py` and `score_reading_eval.py` is
  empty and the summary cites the card hash recorded before the run.

#### Scenario: Extraction never repairs
- **WHEN** the model's reply lacks one of the two fields
- **THEN** the missing field is empty, the item counts as unparsed, and no
  content is inferred from the rest of the reply.

### Requirement: Validated judge instrument
Before any full judge pass, the judge SHALL be validated against human labels
on a pre-registered sample: raw agreement ≥ 80% and Cohen's κ ≥ 0.6, with the
judge verdicts hidden from the labeler. On failure, at most one documented
prompt iteration is allowed; a second failure SHALL stop the measurement and
publish the instrument-failure result instead of a faithfulness score.

#### Scenario: Gate passed
- **WHEN** agreement and κ meet the thresholds on the frozen labels
- **THEN** the full judge pass may run and MC-38 reports the gate numbers.

#### Scenario: Gate failed twice
- **WHEN** the iterated judge still misses a threshold
- **THEN** no faithfulness metric is published, and the card records the
  agreement/κ numbers as the outcome of the line of work.

### Requirement: Mechanical and semantic evidence stay separate
The comparison SHALL report the verbatim-citation check (citation ⊆ context,
no judge) and the judge-supported rate as separate metrics, and SHALL report
compliance, unparsed items, and judge errors as their own buckets; no metric
may fold an unparsed or judge-error item into either side.

#### Scenario: Right answer, unsupported citation
- **WHEN** the answer matches gold and the judge says the citation does not
  support it
- **THEN** the item appears in the `correct ∧ ¬supported` cell and the headline
  `correct ∧ supported` does not count it.
