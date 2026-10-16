## Purpose

Implement the revision-4 diagnostic methodology with explicit evidence scope, reviewer provenance and immutable benchmark boundaries.

## ADDED Requirements

### Requirement: Locked pilot selection and source provenance
The system SHALL retain the declared 60-item pilot, 12 per dataset, and 15-key second-review subset, 3 per dataset. Selection/exposure/source hashes SHALL be preserved across review revisions without resampling. Pilot proportions SHALL NOT be extrapolated to population gap rates or clean-heldout performance.

#### Scenario: Rebind revision 3
- **WHEN** revision 4 is prepared
- **THEN** source question/output/gold/metrics, ordered 60 keys and 15 independent keys are identical

### Requirement: Scoped answer audit and strict import
Review-v4 SHALL require semantic/gold/outcome judgments, separate input and corpus scope, audit evidence kind/reference, rationale, scope, assistance and human attestation. no_observed_issue SHALL have correct semantics, valid gold, reviewed status and empty issue/hypothesis/support sets. issue_observed SHALL require an observed phenomenon but MAY have no known cause. unresolved SHALL be deferred without forced labels. Corpus present/absent SHALL have a scoped reference. Source edits, unknown labels and schema drift SHALL fail import.

#### Scenario: Error with unknown cause
- **WHEN** an answer is incorrect but mechanisms are not distinguishable
- **THEN** a reviewed issue can retain empty cause hypotheses without being labeled success

### Requirement: Registered support per hypothesis
Every selected hypothesis SHALL have one support object: label, status, evidence_reference, contrast_id. contrast_supported SHALL match a registered reviewed contrast/replay for this item and label, affirmative supports_hypothesis, controlled conditions and verified artifact hash tied to pilot identity. Deterministic replay SHALL only support declared evidence/component labels; parametric/reading/reasoning/instruction/generator/harness/instability claims require controlled model comparisons. Input insufficiency SHALL NOT alone exclude an external-evidence hypothesis; other premises SHALL be label-specific.

#### Scenario: Missing-input support
- **WHEN** a registered matching contrast supports external_evidence_gap and input is insufficient
- **THEN** the label can be eligible without forcing input sufficient

### Requirement: Blind scope and honest paired agreement
Independent packets SHALL use exactly the fixed 15 keys, human_only and explicit blind self-attestation with identity distinct from primary. Reports SHALL count only valid primary/independent pairs and SHALL state AI-assisted versus human-only design. Browser IDs SHALL be described as self-attested, not authenticated persons. Two primary IDs SHALL NOT satisfy the blind gate.

#### Scenario: Two primary reviewers
- **WHEN** two IDs submit primary packets
- **THEN** the independent gate remains pending

### Requirement: Adjudication and supervision separation
Reviews and adjudication events SHALL be append-only and SHALL never edit original gold/scores. Deferred/conflicting judgments SHALL be excluded from causal supervision. Resolving the audit process SHALL NOT invent a final cause label. Eligibility SHALL be per hypothesis with verified matching support; no-issue controls SHALL be retained separately as negative/control data.

#### Scenario: No human imports
- **WHEN** only AI proposals and packets exist
- **THEN** audit completion, measured agreement and causal/action supervision remain absent
