## Purpose

A second held-out set that no router has seen, registered before its first request. On it, the frozen v3 procedure is evaluated once against the frozen v2 rule and the fixed policies, with cost reported beside accuracy.

## ADDED Requirements

### Requirement: Held-out v3 set

The set SHALL contain three datasets, each split into 60 calibration items and 300 test items:

- **VMLU valid:** items outside MC-94, drawn by VMLU category in proportion to its size.
- **VM14K:** four-option items from the shuffled0 variant, drawn by the manifest's category in proportion to its size.
- **ViBidLQA train:** items whose question appears once across the train, val and test splits, drawn at random.

Sampling SHALL use seed 42 and ranks by sha256(seed, tab, dataset:item). Inside each dataset, calibration SHALL take its 60 items in proportion to the strata, and the lowest ranks SHALL come first.

Items SHALL be built with the frozen main-v1 prompt builders, from sources pinned by SHA-256. Arms B and S SHALL run with two draws each under the model, transport, scoring and budget of the MC-93 campaign. The protocol, the manifest (which records each item's role) and the procedure SHALL be recorded by SHA-256 in a registration and measurement card MC-95 before the first request.

#### Scenario: Rebuilt manifest
- **WHEN** the manifest is rebuilt from the sources and the protocol
- **THEN** its SHA-256 equals the registered value, it holds 4,320 attempts, and no VMLU item belongs to MC-94

#### Scenario: Campaign conditions differ
- **WHEN** the held-out v3 protocol's model, transport, scoring or budget differs from the MC-93 campaign protocol
- **THEN** the tests fail

### Requirement: Held-out v3 run gates

With `--execute`, the runner SHALL refuse to start unless all of these hold:

- the MC-95 heading and detail card exist;
- the protocol, campaign protocol, template and manifest hashes equal the registration;
- the endpoint host and model equal the campaign's;
- the procedure file carries the registered SHA-256.

The registered concurrency limits SHALL apply by default, and other values SHALL be refused.

#### Scenario: Procedure edited after registration
- **WHEN** `procedure_v3.json` changes after MC-95 is registered
- **THEN** the procedure gate fails and no request is sent

### Requirement: Single evaluation of v3

The procedure SHALL be evaluated once, per rotation:

- the calibration items of each dataset produce the dataset's choice and the emitted rule;
- the emitted rule routes the test items.

**Primary analysis.** It SHALL use rotation 1 and the multiple-choice family (VMLU valid and VM14K test items), and SHALL report, for v3, the frozen v2 rule, always-B and always-S:

- accuracy with Wilson intervals;
- mean reported tokens per test item, probe included;
- exact McNemar tests of v3 against v2 and against always-S, with Holm over the two.

The confirmatory claim SHALL rest on this analysis only.

**Per dataset and rotation, the evaluation SHALL also report:**

- the three calibration scores and the choice;
- the policy best on the test items in hindsight and the regret against it;
- the calibration cost in reported tokens.

**Rotation 2** SHALL be reported as a replication, calibration included.

**Reading (ViBidLQA train)** SHALL be descriptive: mean token-F1 and exact match per policy, plus the items whose exact-match correctness differs between v3 and a fixed policy.

#### Scenario: Report keys
- **WHEN** the evaluation is written
- **THEN** its top-level keys equal the list recorded in the registration

#### Scenario: Calibration and test kept apart
- **WHEN** an item is a calibration item
- **THEN** it is never counted among the test items of any policy
