## Purpose

Defines how the responses of each campaign arm are reduced to a scored prediction and how arms are compared, so that gains from reasoning or evidence are not confused with parser or format effects.

## ADDED Requirements

### Requirement: Frozen scoring for baseline and direct-answer arms
Arms B, O and K, whose prompts request an answer only, SHALL be scored with the frozen multiple-choice parser and the frozen reading extractor and metrics applied to the raw response, without modification.

#### Scenario: Baseline score equals the frozen scorer
- **WHEN** a B-arm response is scored
- **THEN** the prediction and correctness equal those the frozen scoring functions return for the same raw response

### Requirement: Final-answer segment for reasoning arms
Arms S and KS, whose prompts request a visible reasoning trace, SHALL be scored from the segment after the last final-answer label of the raw response. For multiple-choice items, a response with no such label SHALL be scored as unparsed and the frozen parser SHALL NOT be applied to the whole response. For reading items the frozen last-label extraction applies. The raw response SHALL be retained unchanged.

#### Scenario: Reasoning that mentions other options
- **WHEN** an S-arm response discusses "đáp án A" and "đáp án B" in its reasoning and ends with the line "Đáp án: C"
- **THEN** the prediction is C

#### Scenario: Missing final label
- **WHEN** an S-arm multiple-choice response contains reasoning but no final-answer label
- **THEN** the prediction is empty, the attempt counts as incorrect and stays in the denominator, and its format flag is false

### Requirement: Format compliance is reported separately
For every arm the summary SHALL report the share of completed attempts whose response carried the required final-answer label and, for reading arms, the share whose final line contained no markdown emphasis. Accuracy, exact match and token-F1 SHALL be computed over all completed attempts, with non-compliant attempts retained.

#### Scenario: Non-compliance is visible
- **WHEN** 3 of 100 completed S-arm attempts lack the final label
- **THEN** the summary reports 97 percent compliance and the 3 attempts remain scored as incorrect

### Requirement: Per-arm summaries never pool arms
Summaries SHALL be produced per arm and dataset. No headline metric SHALL be computed over attempts of different arms.

#### Scenario: Two arms in one run
- **WHEN** a run contains B and S attempts for the same items
- **THEN** the summary lists separate rows for B and S

### Requirement: Paired outcome definitions
An item-level outcome SHALL be the majority of correct attempts across replicates for the core phase and the single attempt for the wide phase. A rescue SHALL be an item whose B outcome is incorrect and whose arm outcome is correct; a regression SHALL be the reverse. Recovery SHALL be rescues divided by B-incorrect items, regression SHALL be regressions divided by B-correct items, and net gain SHALL be the difference in correct items over all paired items. For reading items the correctness used SHALL be exact match; items with token-F1 at least 0.8 and exact match zero SHALL be listed as semantic-audit candidates and not counted as correct.

#### Scenario: Recovery and regression denominators
- **WHEN** 20 of 60 core items are B-incorrect and 8 of them are correct under S
- **THEN** S recovery is 8/20 and regression is computed over the 40 B-correct items

### Requirement: Discordant pairs are exported in both directions
The analysis SHALL export every item whose outcome differs between an arm and B, rescues and regressions alike, with both raw responses and prompt hashes, for human semantic review.

#### Scenario: Regressions are not dropped
- **WHEN** S regresses on 3 items and rescues 8
- **THEN** the export lists all 11 items with their direction

### Requirement: Noise-floor routing ceiling
Any reported oracle-routing ceiling SHALL be accompanied by the same ceiling computed over the replicates of arm B alone, and by the difference between them.

#### Scenario: Ceiling with a null router
- **WHEN** the oracle ceiling over arms B, S, O, K and KS is reported
- **THEN** the oracle ceiling over the B replicates is reported next to it

### Requirement: Replicate-noise reference
The analysis SHALL report, for the core phase, the attempt-level rescue and regression rates between replicates of arm B itself next to each arm's attempt-level rescue and regression rates against B, pairing the attempts that share a replicate number. When B has a single attempt per item the noise reference SHALL be reported as unavailable rather than estimated.

#### Scenario: Arm rate read against noise
- **WHEN** B attempts turn from incorrect to correct between replicates on 10 percent of the cases that started incorrect, and S rescues 40 percent of them
- **THEN** the report shows both rates side by side so that the rescue is read against the 10 percent noise

#### Scenario: Single draw has no reference
- **WHEN** every item has exactly one B attempt
- **THEN** the noise reference is reported as unavailable

### Requirement: Secondary analyses stay secondary
The report SHALL label as secondary, and SHALL NOT let them replace the primary metrics: a sensitivity analysis restricted to items whose attempts of a reasoning arm all carried the final-answer label; for reading, the paired token-F1 difference with a passage-cluster interval; and a flag on each reading rescue where B already matched the gold with mean token-F1 at or above the audit threshold.

#### Scenario: Compliant-only sensitivity
- **WHEN** one of four S items has an attempt without the final label
- **THEN** the sensitivity block counts only the other three items and states that one item was excluded, while the primary block still counts all four

#### Scenario: Format-suspect rescue
- **WHEN** an item is incorrect under B by exact match, B's mean token-F1 is 0.9 and S is correct by exact match
- **THEN** the rescue is counted and flagged as format-suspect

### Requirement: Baseline parity gate
For the wide phase the analysis SHALL compare the B accuracy or exact match per dataset with the registered reference interval of the earlier direct-API run and SHALL report any dataset outside its interval before any arm effect is interpreted. The gate SHALL NOT be computed for the core anchors, which are a purposive sample.

#### Scenario: Out-of-interval baseline
- **WHEN** B on a wide dataset falls outside the reference interval
- **THEN** the report states that the gate failed and that effects must not be interpreted before the infrastructure is checked

#### Scenario: Core has no gate
- **WHEN** the core phase is analysed
- **THEN** the parity gate is reported as not applicable

### Requirement: Noise reference from a baseline supplement
When a registered supplement provides a second draw of arm B for the items of a single-draw phase, the analysis SHALL report per family: the drift between the two baseline draws (exact McNemar); the B-versus-B recovery and regression rates with Wilson intervals and the agreement rate; the comparison of the other arm with the second baseline draw; the comparison of that arm with the second baseline draw on the items the first baseline draw got wrong and on those it got right, with a Holm correction over the families and conditions; the stable categories; and an oracle ceiling next to the ceiling over the two baseline draws. It SHALL list its result keys in the registration entry, and it SHALL NOT repeat or replace the registered single-draw analysis of the phase.

#### Scenario: Selection on the first draw only
- **WHEN** S is compared with the second baseline draw on the items the first baseline draw got wrong
- **THEN** both comparands are fresh draws, so regression to the mean affects them alike and the difference isolates the arm effect

#### Scenario: Drift is not noise
- **WHEN** the second baseline draw differs systematically from the first (McNemar p below 0.05 in a family, or failed parity)
- **THEN** the noise estimates of that family are labelled run-to-run drift rather than sampling noise

#### Scenario: Result keys are registered
- **WHEN** the analysis function returns its report
- **THEN** its top-level and per-family keys equal the lists in the registration entry
