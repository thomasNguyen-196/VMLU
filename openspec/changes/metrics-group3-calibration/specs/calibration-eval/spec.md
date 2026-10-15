## Purpose

Defines the MC calibration measurement: capturing the first-token distribution
over options A–E from the gateway's `logprobs` and reporting accuracy, ECE,
Brier, and a reliability table for the frozen multiple-choice condition.

## Requirements

### Requirement: Logprobs availability is probed, not assumed
The calibration run SHALL only proceed when the gateway is probed to return
`logprobs` for the model under test; the probe result SHALL be recorded in the
card before the run.

#### Scenario: Gateway returns logprobs
- **WHEN** a probe request with `logprobs=true` returns per-token logprobs for
  the model
- **THEN** the calibration run may proceed and the card records the probe.

#### Scenario: Gateway does not return logprobs
- **WHEN** the probe returns no logprobs (or the model is offline)
- **THEN** calibration stops and the gap is recorded — no score is forced.

### Requirement: Frozen condition plus a read-only option
The calibration run SHALL reuse the byte-frozen `build_prompt` and
`extract_answer` and the frozen gold, differing from the baseline MC condition
only by `logprobs` capture; the answer-letter distribution SHALL be built from
the first generated token's top logprobs over **exactly the letters the prompt
offers** (derived from the prompt's own option block, never a hard-coded A–E),
renormalized over those letters, with absent letters scored 0 and never invented,
and the count of letters found recorded per item. Mass falling outside the
offered letters SHALL be reported separately as `off_options_mass` rather than
folded into the answer's confidence.

#### Scenario: First token is the bare letter
- **WHEN** the first generated token is `B` and the prompt offers A–D while its
  top logprobs also list `E`
- **THEN** `p_A..p_D` are the probabilities renormalized over the four offered
  letters, `confidence = p[answer]`, and `E`'s share is reported as
  `off_options_mass` — never folded into the confidence.

#### Scenario: Prompt option block is malformed
- **WHEN** the option block is not a contiguous `A..` prefix
- **THEN** the run fails fast instead of guessing a letter set.

#### Scenario: Unusable distribution
- **WHEN** fewer than two letters appear in the first token's top logprobs
- **THEN** the item is flagged unusable, excluded from the calibration metrics,
  and still counted in the accuracy denominator.

### Requirement: Calibration metrics are defined before the run
The report SHALL compute accuracy, mean confidence, ECE with a fixed bin count,
Brier score (confidence and multiclass), and a reliability table, and SHALL
state that the distribution is the first-token belief over options, not a
full-answer calibration claim.

#### Scenario: Per-subject breakdown on a multi-subject set
- **WHEN** the dataset's ids are `XX-YYYY`
- **THEN** the report breaks accuracy / confidence / ECE down by category and by
  subject using the frozen `subject_category` map, so a per-subject row means
  the same thing as a row in the MC accuracy table.

#### Scenario: Run-to-run variation is measured, not assumed away
- **WHEN** a re-run of an unchanged condition yields a different accuracy
- **THEN** the difference is recorded as backend non-determinism with its size
  in items, and the affected metrics are reported with that margin rather than
  as exact values.

#### Scenario: Perfectly calibrated fixture
- **WHEN** confidence equals empirical accuracy in every bin
- **THEN** ECE is 0.
