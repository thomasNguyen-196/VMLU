## Purpose

Router rules that decide per item from runtime features and, when a rule asks for it, from whether two answers of arm B to the same request agree, so that items the model answers inconsistently can be escalated to another arm at a counted cost.

## ADDED Requirements

### Requirement: Probe in the rule grammar
A router rule MAY declare a probe: arm B answered twice under the frozen B prompt, compared by a named agreement rule from a closed set. A condition MAY test the probe outcome (`agree` or `disagree`) only when the rule declares a probe. Two answers agree when both parse to a non-empty answer and the normalized answers are equal: the parsed letter for multiple choice, the exact-match normalization for reading. Validation SHALL fail on a probe arm other than B, a sample count other than two, an unknown agreement rule, or a condition that tests the probe in a rule without one. The probe uses only the model's own answers; gold answers, audit fields and scores SHALL never enter it.

#### Scenario: Probe condition without a probe
- **WHEN** a rule has a condition testing `disagree` but declares no probe
- **THEN** validation fails and names the condition

#### Scenario: Unparsed answers
- **WHEN** either probe answer is empty after parsing
- **THEN** the probe outcome is `disagree`

### Requirement: Lazy probe and cost
Conditions SHALL be evaluated in order with the runtime features first; the probe SHALL run only when a condition whose other features hold needs its outcome. When the decision is B and the probe ran, the first probe answer SHALL be the answer, with no further B request. The cost of an item SHALL include both probe answers whenever the probe ran, plus the selected arm when it is not B.

#### Scenario: Decided before the probe
- **WHEN** a Vi-DROP item matches a condition that sends it to S before any probe condition
- **THEN** no probe runs and the item's cost is that of S alone

#### Scenario: Escalation cost
- **WHEN** the probe answers differ and the item is escalated to S
- **THEN** the item's cost is both B answers plus the S answer, and the S answer is the answer

### Requirement: Design fit of probe rules on draws
Probe rules SHALL be fitted on outcomes where every item has two draws of B and of S, through two rotations: (first B answer, second B answer, first S answer) and (second B answer, first B answer, second S answer). The design fit SHALL report, labelled as design fit and without tests or intervals: accuracy and mean reported tokens for the rule, always-B and always-S; the share of items escalated; accuracy of B and of S on the items whose probe agrees and on those whose probe disagrees; the same per dataset and per condition; and, for the reading items of the first rotation, the exact-match rescues and regressions of the escalated group and how many the semantic review found to be measurement effects.

#### Scenario: Two rotations
- **WHEN** a probe rule is fitted on the wide draws
- **THEN** each reported accuracy is the mean of the two rotations and carries no p-value or interval

### Requirement: Candidates frozen before their fits
Candidate v2 rules SHALL be committed before their design fits are computed, and the chosen rule SHALL be frozen as a byte copy of one candidate whose SHA-256 is recorded before the first held-out request.

#### Scenario: Frozen rule differs from every candidate
- **WHEN** `router_v2.json` is not byte-identical to a committed candidate
- **THEN** the router tests fail
