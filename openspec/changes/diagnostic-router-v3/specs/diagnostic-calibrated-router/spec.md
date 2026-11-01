## Purpose

Router v3 is a frozen calibration procedure. For each dataset it scores always-B, the v2 cascade and always-S on a small labelled calibration sample, keeps the best, and writes the choices as a rule in the closed grammar of the existing router.

## ADDED Requirements

### Requirement: Frozen calibration procedure

The procedure SHALL be a data file with a closed set of keys. The file SHALL fix:

- the candidate policies, exactly always-B, the v2 cascade and always-S;
- the number of calibration items per dataset;
- the score per task: accuracy for multiple choice, mean token-F1 for reading;
- the tie rule: fewer mean reported tokens, then the order always-B, v2 cascade, always-S;
- the probe: arm B, two samples, `normalized-answer-v1`.

A file with an unknown key, a missing key or an unsupported value SHALL be refused.

#### Scenario: Unsupported score
- **WHEN** the procedure names exact match as the reading score
- **THEN** loading it fails and nothing is calibrated

### Requirement: Choice per dataset

On the calibration items of a dataset, in one rotation, the procedure SHALL score each candidate. Each candidate's outcome is the answer that deployment would return:

- always-B returns the answering B draw;
- always-S returns the S draw;
- the v2 cascade returns the B draw when the two B answers agree and the S draw otherwise.

The candidate with the highest score SHALL be chosen, and ties SHALL be broken by the registered tie rule. The procedure SHALL refuse to calibrate a dataset whose calibration sample does not have exactly the registered size.

#### Scenario: S best on calibration
- **WHEN** always-S has the highest accuracy on a multiple-choice dataset's calibration items
- **THEN** the dataset's policy is always-S

#### Scenario: Equal scores
- **WHEN** always-B and the v2 cascade have the same score
- **THEN** the one with fewer mean reported tokens is chosen

#### Scenario: Reading scored by token-F1
- **WHEN** the dataset is a reading dataset
- **THEN** each candidate is scored by the mean token-F1 of its answers, not by exact match

### Requirement: Rule emission

The choices SHALL be written as a rule of the closed grammar that `diagnostic_router.load_rule` accepts:

- always-B or always-S becomes one condition on the dataset;
- the v2 cascade becomes a condition on the dataset with `probe: disagree` sending the item to S, followed by a condition on the dataset alone sending it to B;
- the rule declares the probe only when a cascade is chosen;
- the default arm is B.

Routing a dataset's items with the emitted rule SHALL give the same decisions and probe costs as the chosen policy.

#### Scenario: Cascade emitted
- **WHEN** a dataset's choice is the v2 cascade
- **THEN** its items are probed, those whose B answers differ go to S, and the others are answered by the first B draw

#### Scenario: Fixed policy emitted
- **WHEN** a dataset's choice is always-S
- **THEN** its items go to S without a probe
