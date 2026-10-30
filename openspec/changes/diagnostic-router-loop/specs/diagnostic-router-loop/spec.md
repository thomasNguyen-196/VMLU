## Purpose

A closed-loop router that reads a student model's answer, judges with retrieved evidence and recorded experience whether and why the answer is weak, applies an enhancement and asks again, for several student models, under registered rules that keep the gold out of every request and count every cost.

## ADDED Requirements

### Requirement: Gold-free runtime inputs
At runtime the router and the loop SHALL see only:
- the item's request (question, options, passage when the task gives one);
- the student's answers in earlier rounds;
- retrieved evidence;
- the experience store;
- the student model's frozen weakness map.

They SHALL NOT see the gold, audit labels, or any outcome of the item being answered. The experience store SHALL exclude every item of the evaluation set it serves.

#### Scenario: An evaluation item in the experience store
- **WHEN** the experience store holds a case whose item belongs to the evaluation set
- **THEN** building the loop manifest fails and no request is sent

### Requirement: No answer injection
A prescription SHALL carry only evidence text, procedural instructions, tool access, a harness or a model to escalate to. It SHALL NOT carry an option letter offered as the answer, the text of an option offered as the answer, or the router's own answer.

Code SHALL check every prescription before the student is asked again. A prescription that fails the check SHALL be discarded and logged, and the item SHALL continue as if the router had prescribed nothing.

#### Scenario: A hint that names the answer
- **WHEN** a prescription contains "đáp án là B" or the full text of one option introduced as correct
- **THEN** the prescription is discarded, the event is logged, and the student is not re-asked with it

### Requirement: Bounded loop with a registered stop rule
The loop SHALL run at most the registered number of rounds, and never more than 3 enhancement rounds after the first answer. It SHALL stop early under the registered stop rule. The final answer SHALL follow the registered selection rule, and every round's answer SHALL be kept.

#### Scenario: Answers keep changing
- **WHEN** the student gives a different answer in every round
- **THEN** the loop stops after the last registered round and the selection rule chooses the final answer

### Requirement: Every cost counted
Each item SHALL record:
- the tokens and latency of every student call and every router call;
- every retrieval and tool call.

Usage a provider does not report SHALL be recorded as unknown, never as zero. Comparisons SHALL report quality together with cost.

#### Scenario: A provider omits usage
- **WHEN** a router response carries no token usage
- **THEN** the item's cost is marked unknown for that call, and summaries count how many costs are unknown

### Requirement: Per-model weakness map on disjoint items
Each student model's weakness map SHALL be built from a calibration run on items disjoint from its evaluation items. The map states which enhancement helps that model on which dataset or question group. It SHALL be frozen, with its SHA-256 registered, before that model's evaluation starts.

#### Scenario: Calibration and evaluation overlap
- **WHEN** an item appears in both the calibration set and the evaluation set of a student model
- **THEN** the evaluation preflight fails

### Requirement: Pre-registered held-out evaluation
The evaluation SHALL be pre-registered on items never used to design the loop or the router. Every student model SHALL be compared with:
- always-B;
- the best fixed enhancement per dataset, chosen on calibration data;
- the rule loop;
- the router answering the item itself.

A registered primary comparison and reading rule SHALL decide the outcome. Legal MC SHALL be reported as exploratory, because all of its items have been used.

#### Scenario: The router alone is better
- **WHEN** the router answering by itself scores higher than the loop at a similar or lower cost
- **THEN** the report states that the loop adds no value over using the router model directly

### Requirement: Fallback to a learned router only on a failed rule
A learned router (deep learning) SHALL be built only when the router-critic fails its registered reading rule. It SHALL be trained only on outcome data that excludes its evaluation items. It SHALL be reported as exploratory unless it is evaluated on held-out items under its own registration.

#### Scenario: The router-critic passes
- **WHEN** the router-critic meets its registered reading rule
- **THEN** the learned router stays future work
