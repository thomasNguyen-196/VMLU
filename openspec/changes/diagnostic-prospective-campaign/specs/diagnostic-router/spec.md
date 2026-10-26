## Purpose

Defines the rule-based router that picks one deployable arm per item from features known at request time, how its rule is frozen before the core run, and how it is evaluated once on core, so that a routing gain is never fitted and measured on the same outcomes.

## ADDED Requirements

### Requirement: Rule over runtime features only
A router rule SHALL be a versioned data file with a closed grammar: an ordered list of conditions, each naming one arm, and a default arm. A condition SHALL test only the item's dataset, the length in characters of its frozen B prompt, or case-insensitive literal cue words in its question text, and the first condition that matches SHALL decide. Every arm named SHALL be deployable (B, S, K or KS). Validation SHALL fail on any other key or arm; gold answers, audit fields and the outcomes of any arm SHALL never be features. Arm O SHALL NOT be selectable, because its reviewer-cited provisions do not exist at request time.

#### Scenario: Forbidden feature
- **WHEN** a condition tests `gold_validity` or any other key outside the grammar
- **THEN** validation fails and names the key

#### Scenario: Oracle arm is not deployable
- **WHEN** a condition or the default names arm O
- **THEN** validation fails

#### Scenario: First matching condition decides
- **WHEN** an item matches the second and the third condition but not the first
- **THEN** the router selects the arm of the second condition

### Requirement: Rule frozen before the core run
The SHA-256 of the chosen rule file SHALL be recorded in the core registration entry and in the core measurement card before the first core request, together with the best fixed arm: B or S, whichever has the higher mean accuracy over its two wide draws. The evaluator SHALL refuse a rule whose SHA-256 differs from the registered value.

#### Scenario: Rule edited after registration
- **WHEN** the rule file changes after the core registration
- **THEN** the router evaluation exits naming both hashes and reports nothing

### Requirement: Designed on wide, evaluated once on core
Candidate rules SHALL be fitted on wide outcomes only, and figures computed on wide SHALL be labelled design fit and reported without tests or intervals. The frozen rule SHALL be evaluated once on core, with the item outcome defined as the strict majority of replicates, as in the core analysis.

#### Scenario: Wide figures are not evidence
- **WHEN** router accuracy on wide is reported
- **THEN** it is labelled design fit and carries no p-value or interval

### Requirement: Router report on core
The evaluation set SHALL be the core anchors whose manifest contains the arm the rule selects for them; the rule and the manifest fix it before the run, and the anchors left out SHALL be listed. On that set the report SHALL give, for the router, always-B, always-S and the registered best fixed arm, the accuracy with a Wilson interval and the mean reported total tokens per item, with unreported usage counted as unknown, not zero; exact two-sided McNemar tests of the router against always-B and against always-S with Holm correction over the two; and the ceiling over the deployable arms available per item next to the ceiling over the B replicates, as defined for oracle routing with arm O left out. A secondary block SHALL repeat the comparisons without the anchors whose adjudicated gold is not valid and state how many were removed. The keys of the report SHALL equal the list in the core registration entry.

#### Scenario: Evidence arm selected where no evidence exists
- **WHEN** the rule selects KS for a Legal MC anchor that has no evidence arm
- **THEN** that anchor is outside the evaluation set for every policy and appears in the list of excluded anchors

#### Scenario: Cost next to accuracy
- **WHEN** the router selects S on some items and B on the others
- **THEN** its mean tokens per item averages, over the evaluation set, the mean reported total tokens of the selected arm on each item

#### Scenario: Suspect gold in the evaluation set
- **WHEN** two anchors of the evaluation set have adjudicated gold `suspect`
- **THEN** the secondary block counts only the other anchors and states that two were removed, while the primary block counts all of them
