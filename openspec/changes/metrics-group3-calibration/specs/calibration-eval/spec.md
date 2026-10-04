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
the first generated token's top logprobs over exactly the letters A–E, with
absent letters scored 0 and never invented, and the count of letters found
recorded per item.

#### Scenario: First token is the bare letter
- **WHEN** the first generated token is `B` and its top logprobs list A–E
- **THEN** `p_A..p_E` are the renormalized letter probabilities and
  `confidence = p[answer]`.

#### Scenario: Unusable distribution
- **WHEN** fewer than two letters appear in the first token's top logprobs
- **THEN** the item is flagged unusable, excluded from the calibration metrics,
  and still counted in the accuracy denominator.

### Requirement: Calibration metrics are defined before the run
The report SHALL compute accuracy, mean confidence, ECE with a fixed bin count,
Brier score (confidence and multiclass), and a reliability table, and SHALL
state that the distribution is the first-token belief over options, not a
full-answer calibration claim.

#### Scenario: Perfectly calibrated fixture
- **WHEN** confidence equals empirical accuracy in every bin
- **THEN** ECE is 0.
