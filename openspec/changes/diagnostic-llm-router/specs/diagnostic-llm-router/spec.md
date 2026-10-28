## Purpose

The LLM router reads a reading item's passage and question and returns one group from a closed list. The arm that group maps to answers the question: B, S or Q. The groups and the mapping come from the student model's measured behaviour on the design items. The router is evaluated once on fresh items, with the passage-and-question baseline as the main comparator.

## ADDED Requirements

### Requirement: Router input and output
The router SHALL receive the item's passage and question only. It SHALL never receive the gold answer, any outcome, or any audit field. The router model SHALL be Muse Spark 1.3. The router SHALL return exactly one group name from a registered closed list; any other output SHALL route the item to a registered default arm. The router SHALL NOT write instructions or answers for the student model.

#### Scenario: Output outside the list
- **WHEN** the router's output is not a registered group name
- **THEN** the item goes to the default arm, and the row records that the router output was not recognised

### Requirement: Groups and mapping from experiments
The closed list of groups, their definitions, the router prompt, the default arm and the mapping rule SHALL be registered before any router request. The mapping rule SHALL:

- fit on the design items only, with two draws each of B, S and Q;
- give each group the arm with the highest mean token-F1 over the design items the router put in that group;
- break ties within 1e-12 toward the more thorough arm, in the order B < Q < S;
- give a group with fewer design items than the registered minimum the arm with the best mean token-F1 over all design items.

The mapping SHALL be frozen before any held-out request.

#### Scenario: Small group
- **WHEN** fewer design items than the registered minimum fall in a group
- **THEN** that group maps to the arm with the best mean token-F1 over all design items

### Requirement: Design-stage router check
Before any held-out request, the router SHALL label the ViBidLQA design items of the menu set once each (MC-98). The Muse grouping SHALL be mapped to arms by the registered cross-draw rule. It SHALL be compared, on the same items and by the same rule, with always-B, always-Q, always-S and a keyword grouping of the question text that was frozen before any router request.

The registered reading rule SHALL decide the next step. The router is promising when its cross-draw routing score exceeds always-S by at least 1.0 token-F1 point and exceeds the keyword grouping. Only a promising router SHALL proceed to a held-out evaluation.

#### Scenario: Router not better than keywords
- **WHEN** the Muse grouping's cross-draw score does not exceed the keyword grouping's
- **THEN** the router is not promising and no held-out evaluation is run

### Requirement: Held-out evaluation with the passage baseline
The router SHALL be evaluated once on fresh items that carry their passage and that no design step used. The held-out set SHALL be ViBidLQA train items not used by MC-95 or MC-96. Each held-out item SHALL have two draws each of B, S and Q, and one router call.

The primary comparisons SHALL be on per-item token-F1:

- the router against always-B, which is the passage-and-question baseline;
- the router against always-S;
- each with a two-sided paired sign-flip test, and Holm over the two.

Tokens per item SHALL include the router's tokens, reported apart from the student model's because the router is another model. always-Q and the per-dataset rule SHALL be reported as description.

#### Scenario: Router tokens
- **WHEN** the cost of the router policy is reported
- **THEN** it includes the router call's tokens as well as the tokens of the chosen arm
