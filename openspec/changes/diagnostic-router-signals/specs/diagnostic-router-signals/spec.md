## Purpose

Router signals are measured on design items, and every signal is compared on the same footing. A signal can come from a System One model reading the question or the cheap arm's answer, or from the student model's own confidence. The footing is the same cross-fitted routing score, the same student-model cost, and the same share of an estimated ideal gain. A registered reading rule decides which policies earn a held-out evaluation.

## ADDED Requirements

### Requirement: Signal requests carry no gold
A signal request SHALL carry only:
- the item's passage and question, taken from its frozen reading prompt;
- for post-hoc requests, also the answer the cheap arm actually gave on a registered draw.

It SHALL never carry the gold answer, a score, an audit field, or the outputs of any other arm. The questions asked of the System One model SHALL be registered in a configuration file whose SHA-256 the registration records.

#### Scenario: Post-hoc state
- **WHEN** a post-hoc request is built for an item and draw 1
- **THEN** its state holds the passage, the question and the scored B-r1 prediction of MC-90, and no gold answer

### Requirement: Frozen manifest and rebuild
The manifest SHALL list every signal request with its run key and the SHA-256 of its request body, and SHALL be self-hashed and frozen before the first request. The runner SHALL rebuild every request from the frozen items, the configuration and the registered answer sources, and SHALL refuse to run when any request differs from the manifest.

#### Scenario: Changed answer source
- **WHEN** the MC-90 or MC-91 scores file no longer has the SHA-256 the manifest records
- **THEN** the preflight fails and no request is sent

### Requirement: Free route and halts
The runner SHALL call only the registered host, path and model, with the credential resolved in the process and never written to outputs. Execution SHALL halt when any of these happens:
- a response reports a non-zero cost or a billing source other than free;
- the response model differs from the registered model;
- an authentication error occurs;
- the registered number of consecutive network failures is reached.

Rate-limit and server errors SHALL be retried in-run only up to the registered count and wait, with each retry recorded. Completed responses SHALL be terminal.

#### Scenario: Billing changes
- **WHEN** a response reports `billing_source` other than `free` or a cost above zero
- **THEN** the run halts after recording that response, and requests already sent finish

### Requirement: Ceiling estimates
For each dataset and arm pair with two draws of both arms, the analysis SHALL report:
- the correlation of the per-item benefit between draws;
- the number of items where each arm wins both draws;
- the gain over the better fixed arm of choosing each item's arm on one draw and scoring the other;
- the distribution-free cap on an ideal router's gain;
- the normal-model estimate of that gain.

#### Scenario: Two-sided benefit
- **WHEN** both arms win both draws on some items
- **THEN** the report gives both counts, so that a one-sided benefit, where a fixed arm already captures the gain, is visible

### Requirement: Cross-fitted policy comparison
Every policy SHALL be scored so that no choice is fitted and scored on the same outcomes.

- A pre-hoc policy chooses its arm on one draw and is scored on the other, both ways, averaged.
- A learned rule is fitted on training folds grouped by passage, on one draw, and scored on the held-out fold on the other draw.
- A post-hoc policy decides from the answer actually produced on a draw and is scored on that draw. A threshold it uses is chosen on the other draw.

Each policy SHALL report its mean student-model tokens per item. The System One model's tokens SHALL be reported apart.

#### Scenario: Post-hoc cost
- **WHEN** a post-hoc policy escalates an item from B to S
- **THEN** its student-model cost for that item is the tokens of B plus the tokens of S

### Requirement: Reading rule
A policy SHALL be promising when either of these holds against the best fixed per-dataset policy on the same items:
- its pooled score exceeds that policy by at least 1.0 point;
- its pooled score is within 0.5 points of that policy at no more than 60% of its mean student-model tokens.

Only a promising policy SHALL proceed to a held-out evaluation, on its own card.

#### Scenario: Cheaper but worse
- **WHEN** a policy uses 40% of the tokens of the best fixed policy and scores 0.8 points below it
- **THEN** it is not promising
