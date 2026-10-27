## Purpose

A held-out item set that no router has seen, registered before its first request, on which the frozen router v2 is evaluated once against fixed-arm policies, with cost reported beside accuracy.

## ADDED Requirements

### Requirement: Held-out set
The held-out set SHALL contain items never used to design or evaluate a router: 300 ViBidLQA val items drawn at random and 300 VMLU valid items drawn by VMLU category in proportion to its size, both with seed 42. Items SHALL be rebuilt from their sources with the frozen main-v1 prompt builders, and arms B and S SHALL run with two draws each under the model, transport, scoring and budget of the MC-93 campaign. The protocol, the manifest and the frozen rule SHALL be recorded by SHA-256 in a registration and measurement card MC-94 before the first held-out request.

#### Scenario: Rebuilt manifest
- **WHEN** the held-out manifest is rebuilt from the sources and the protocol
- **THEN** its SHA-256 equals the registered value and it holds 2,400 attempts

#### Scenario: Campaign conditions differ
- **WHEN** the held-out protocol's model, transport, scoring or budget differs from the MC-93 campaign protocol
- **THEN** the held-out tests fail

### Requirement: Held-out run gates
With `--execute` the held-out runner SHALL refuse to start unless the MC-94 heading and detail card exist, the manifest and protocol hashes equal the registration, the endpoint host and model equal those of the campaign, and the frozen v2 rule on disk carries the registered SHA-256. The registered concurrency limits SHALL apply by default and other values SHALL be refused.

#### Scenario: Rule edited after registration
- **WHEN** `router_v2.json` changes after MC-94 is registered
- **THEN** the router gate fails and no held-out request is sent

### Requirement: Single evaluation on the held-out set
The frozen v2 rule SHALL be evaluated once, per family: multiple choice (VMLU valid) is the primary family, because its answers are scored exactly; reading (ViBidLQA val) is secondary, because exact match there mostly measures answer formatting. The primary analysis SHALL use the first rotation (first B answer as the answer, second B answer as the probe's second answer, first S answer on escalation) with single-draw item outcomes, and SHALL report per family: accuracy with Wilson intervals and mean reported tokens including the probe for v2, always-B and always-S; exact McNemar tests of v2 against always-B and against always-S with Holm correction over the two; the escalation rate; and B and S accuracy on agreeing and disagreeing items. The confirmatory claim SHALL rest on the primary family and rotation only. The second rotation SHALL be reported as a replication; reading SHALL also carry token-F1 and the list of items whose correctness differs between v2 and a fixed policy, for an AI-assisted semantic review reported as descriptive.

#### Scenario: v1 on the held-out set
- **WHEN** v1 routes the held-out items
- **THEN** every item goes to B, and the report states that v1 equals always-B on this set

#### Scenario: Report keys
- **WHEN** the held-out evaluation is written
- **THEN** its top-level keys equal the list recorded in the registration
