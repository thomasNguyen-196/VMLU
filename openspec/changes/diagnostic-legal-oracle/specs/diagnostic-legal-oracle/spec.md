## Purpose

The Legal MC oracle test measures what the provision that governs a question does to the student model's answer. It reports both directions: wrong answers it fixes and right answers it breaks. Only then does the project build a legal corpus and test retrieval on Legal MC.

## ADDED Requirements

### Requirement: Fixed item selection
The items SHALL be selected from the wide-phase Legal MC items by a rule in the protocol, using only the registered B draws of MC-90 and MC-91:
- every item missed on at least one draw;
- a fixed hash-ordered sample of the items answered correctly on both.

The manifest SHALL record the SHA-256 of both score files. The selection SHALL fail closed when an item lacks a draw or the pool size differs from the protocol.

#### Scenario: Changed source draws
- **WHEN** the MC-91 scores file no longer has the SHA-256 the manifest records
- **THEN** the preflight fails and no request is sent

### Requirement: Verbatim oracle evidence without gold in requests
Every provision SHALL be:
- text extracted by code, verbatim, from a stored source page whose SHA-256 is logged;
- either a whole article, or, for an article over 6,000 characters, its heading line and named clauses.

No request SHALL carry the gold answer, a support label or an agent's rationale. Evidence records SHALL pass the campaign's provision checks and SHALL carry no answer-bearing key. The evidence file SHALL be frozen and its SHA-256 registered before the first request.

#### Scenario: Paraphrased provision
- **WHEN** a provision's text is not found verbatim in its stored source page
- **THEN** building the evidence file fails and nothing is frozen

### Requirement: Arms and rebuild
Arm B SHALL send the item's frozen main-v1 prompt byte for byte. Arm O SHALL send the campaign evidence block with the item's provisions followed by the same frozen prompt. Each arm SHALL run two draws. The runner SHALL rebuild the manifest from the frozen items, the evidence file and the templates, and SHALL refuse to run when anything differs.

#### Scenario: Evidence file edited after registration
- **WHEN** the evidence file differs from the registered SHA-256
- **THEN** the frozen-hash gate fails and no request is sent

### Requirement: Registered analysis and reading rule
The analysis SHALL be fixed before data and run once. On items whose final support label is `supports_gold`, for each stratum, it SHALL report O against fresh B draws:
- the mean per-item difference with its bootstrap interval and sign-flip p-value;
- clear rescues and clear regressions.

A retrieval study on Legal MC SHALL be judged worth building only when both hold:
- in stratum `wrong`, O is at least 20 points above B;
- in stratum `right`, O is at most 10 points below B.

#### Scenario: Oracle fixes little
- **WHEN** O exceeds fresh B by fewer than 20 points in stratum `wrong`
- **THEN** the report marks the retrieval study as not worth building, whatever happens in stratum `right`
