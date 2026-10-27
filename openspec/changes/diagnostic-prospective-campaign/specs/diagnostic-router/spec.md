## Purpose

Defines the rule-based router that picks one deployable arm per item from features known at request time, how its rule is frozen before the core run, and how it is evaluated once on core, so that a routing gain is never fitted and measured on the same outcomes.

## ADDED Requirements

### Requirement: Rule over runtime features only
A router rule SHALL be a versioned data file with a closed grammar: an ordered list of conditions, each naming one arm, and a default arm. A condition SHALL test only the item's dataset, the length in characters of its frozen B prompt, or case-insensitive literal cue words in its question text, and the first condition that matches SHALL decide. Every arm named SHALL be deployable (B, S, K or KS). Validation SHALL fail on any other key or arm; gold answers, audit fields and the outcomes of any arm SHALL never be features. Arm O SHALL NOT be selectable, because its reviewer-cited provisions do not exist at request time.

Every condition and the default SHALL declare `targets`, the labels of the audit taxonomy that the routed arm is meant to address. Validation SHALL accept as targets of S only `reasoning_gap` and `reading_representation_gap`, of K only `external_evidence_gap`, `parametric_knowledge_gap` and `parametric_knowledge_error`, of KS their union, and of B none, and SHALL require at least one target for any arm other than B. Targets SHALL NOT change which arm is selected.

#### Scenario: Forbidden feature
- **WHEN** a condition tests `gold_validity` or any other key outside the grammar
- **THEN** validation fails and names the key

#### Scenario: Oracle arm is not deployable
- **WHEN** a condition or the default names arm O
- **THEN** validation fails

#### Scenario: First matching condition decides
- **WHEN** an item matches the second and the third condition but not the first
- **THEN** the router selects the arm of the second condition

#### Scenario: Arm that cannot address its target
- **WHEN** a condition routes to S with the target `external_evidence_gap`
- **THEN** validation fails and names the arm and the target

### Requirement: Rule frozen before the core run
The SHA-256 of the chosen rule file SHALL be recorded in the core registration entry and in the core measurement card before the first core request, together with the SHA-256 of the cue lexicon and the best fixed arm: B or S, whichever has the higher mean accuracy over its two wide draws. The evaluator SHALL refuse a rule or lexicon whose SHA-256 differs from the registered value, and the core run SHALL refuse to execute while the rule file or the lexicon is missing or differs from it.

#### Scenario: Rule edited after registration
- **WHEN** the rule file changes after the core registration
- **THEN** the router evaluation exits naming both hashes and reports nothing

#### Scenario: Core launch without the frozen rule
- **WHEN** the core run is executed while the rule file is missing or its SHA-256 differs from the registration
- **THEN** the router gate fails and no core request is sent

### Requirement: Designed on wide, evaluated once on core
Candidate rules SHALL be fitted on wide outcomes only, and figures computed on wide SHALL be labelled design fit and reported without tests or intervals. Cue words SHALL come from a lexicon grouped by need whose SHA-256 is recorded before any cue-level outcome on wide is computed. For the reading items of the first draw pair, the design fit SHALL report per routed group the exact-match rescues and regressions of S against B and how many of them the semantic review found to be measurement effects. The frozen rule SHALL be evaluated once on core, with the item outcome defined as the strict majority of replicates, as in the core analysis.

#### Scenario: Cue outside the lexicon
- **WHEN** a candidate rule tests a cue word that is not in the hashed lexicon, or one whose need group shares no target with the condition
- **THEN** loading the rule fails and names the cue

#### Scenario: Wide figures are not evidence
- **WHEN** router accuracy on wide is reported
- **THEN** it is labelled design fit and carries no p-value or interval

#### Scenario: Measurement effect visible in the design fit
- **WHEN** a candidate keeps B on Vi-SQuAD items where the semantic review found S right in meaning on most of its exact-match regressions
- **THEN** the design fit reports those regressions as measurement effects next to the exact-match counts

### Requirement: Router report on core
The evaluation set SHALL be the core anchors whose manifest contains the arm the rule selects for them; the rule and the manifest fix it before the run, and the anchors left out SHALL be listed. On that set the report SHALL give, for the router, always-B, always-S and the registered best fixed arm, the accuracy with a Wilson interval and the mean reported total tokens per item, with unreported usage counted as unknown, not zero; exact two-sided McNemar tests of the router against always-B and against always-S with Holm correction over the two; and the ceiling over the deployable arms available per item next to the ceiling over the B replicates, as defined for oracle routing with arm O left out. A secondary block SHALL repeat the comparisons without the anchors whose adjudicated gold is not valid and state how many were removed. A descriptive detection block SHALL report, over the evaluation set, how many anchors whose adjudicated audit records at least one diagnostic hypothesis the router sent to an arm whose declared targets include one of them, in total and per label, and how many no-issue anchors it sent to an arm other than B. The adjudicated labels SHALL be read from the anchor-diagnosis file whose SHA-256 is recorded in the core registration entry and SHALL score the routing only. The keys of the report SHALL equal the list in the core registration entry.

#### Scenario: Evidence arm selected where no evidence exists
- **WHEN** the rule selects KS for a Legal MC anchor that has no evidence arm
- **THEN** that anchor is outside the evaluation set for every policy and appears in the list of excluded anchors

#### Scenario: Cost next to accuracy
- **WHEN** the router selects S on some items and B on the others
- **THEN** its mean tokens per item averages, over the evaluation set, the mean reported total tokens of the selected arm on each item

#### Scenario: Suspect gold in the evaluation set
- **WHEN** two anchors of the evaluation set have adjudicated gold `suspect`
- **THEN** the secondary block counts only the other anchors and states that two were removed, while the primary block counts all of them

#### Scenario: Diagnosis scores the routing without steering it
- **WHEN** an anchor's adjudicated hypothesis is `reasoning_gap` and the router selects S with the target `reasoning_gap`
- **THEN** the detection block counts the anchor as detected, and the router selects the same arm when the anchor-diagnosis file is absent

#### Scenario: Anchor-diagnosis file changed after registration
- **WHEN** the SHA-256 of the anchor-diagnosis file differs from the core registration entry
- **THEN** the router evaluation exits naming both hashes and reports nothing
