## Purpose

The K2 calibration procedure decides, from a small labelled calibration sample, whether to answer without retrieval, with retrieved passages, with retrieved passages and reasoning, or with a cascade between the last two. It writes the choice as a rule of the closed router grammar. MC-96 evaluates it once.

## ADDED Requirements

### Requirement: K2 calibration procedure
The procedure SHALL be a data file with a closed set of keys. The file SHALL fix:

- the candidates, from least to most thorough: always-B, always-K, the K cascade, always-KS;
- the number of calibration items;
- mean token-F1 as the score;
- the tie rule: the more thorough candidate;
- the probe: arm K, two samples, `normalized-answer-v1`.

An unknown key, a missing key or another value SHALL be refused.

#### Scenario: Cheaper tie rule
- **WHEN** the procedure names fewer tokens as its tie rule
- **THEN** loading it fails

### Requirement: Choice with ties toward thoroughness
On the calibration items, in one rotation, each candidate SHALL be scored on the answers deployment would return:

- always-B returns the B draw;
- always-K returns the answering K draw;
- always-KS returns the KS draw;
- the K cascade returns the K draw when the two K answers agree, otherwise the KS draw.

The highest mean token-F1 SHALL win. Scores within 1e-12 SHALL count as equal, and among equal scores the more thorough candidate SHALL win. A calibration sample of another size SHALL be refused.

#### Scenario: Equal scores
- **WHEN** always-K and the K cascade have equal mean token-F1
- **THEN** the K cascade is chosen

### Requirement: Probe arm K
A router rule's probe MAY name arm K as well as arm B. With arm K, the probe SHALL answer twice with K. When the decision is K, the first probe answer SHALL stand, and the item's cost SHALL include both K answers.

Validation SHALL still refuse:

- any other probe arm;
- a sample count other than two;
- an unknown agreement rule.

Rules with a B probe SHALL validate and route as before.

#### Scenario: Probe arm S
- **WHEN** a rule declares a probe of arm S
- **THEN** validation fails

### Requirement: Rule emission
The choice SHALL be written as a rule of the closed grammar:

- always-B, always-K and always-KS each become one condition on the dataset;
- the K cascade becomes a condition on the dataset with `probe: disagree` sending the item to KS, followed by a condition on the dataset alone sending it to K;
- the K probe is declared only when the cascade is chosen;
- the default is B.

The router SHALL read only the closed-book request (the dataset, the B prompt and the question), never a passage. Routing with the emitted rule SHALL give the chosen candidate's answers and costs.

#### Scenario: Cascade emitted
- **WHEN** the choice is the K cascade
- **THEN** items whose K answers differ go to KS, and the others keep the first K answer

### Requirement: Single evaluation of K2
The procedure SHALL be evaluated once, on the 300 test items, in two rotations:

- **Rotation 1:** the first draws answer and the second K draw is the probe.
- **Rotation 2:** the draws are swapped.

In each rotation the calibration items choose and the emitted rule routes the test items.

The primary analysis is rotation 1: the router against always-K and against always-KS on per-item token-F1, with two-sided paired sign-flip tests (20,000 resamples, seed 7) and Holm over the two.

For the router and every candidate and for O, the report SHALL also give:

- mean token-F1 with a bootstrap interval;
- exact match with a Wilson interval;
- mean reported tokens with the probe;
- per rotation, the calibration scores, choice, cost and regret against the best candidate in hindsight;
- retrieval hits, and token-F1 on hits and on misses.

The report's top-level keys SHALL equal the registered list.

#### Scenario: Calibration and test kept apart
- **WHEN** an item is a calibration item
- **THEN** it never enters a test comparison
