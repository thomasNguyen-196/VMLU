## Purpose

Implement the revision-4 diagnostic methodology with explicit evidence scope, reviewer provenance and immutable benchmark boundaries.

## ADDED Requirements

### Requirement: Versioned offline protocol and three readiness gates
The system SHALL validate ledger schema v1 separately from annotation revision 4, diagnostic-review-v4 and diagnostic-rubric-v3. It SHALL distinguish preparation_ready, audit_complete and inference_ready. Unset prospective baseline/model/endpoint, split/corpus, budget, replicate/stability and verifier controls SHALL block inference. This change SHALL NOT execute model inference.

#### Scenario: Offline ready, runtime controls absent
- **WHEN** Offline ledger/pilot checks pass but prospective controls are not preregistered
- **THEN** preparation is ready and inference is blocked with explicit reasons

### Requirement: Historical boundaries and research scope
The system SHALL preserve original prompt/extraction, gold, scorer versions, denominators, source conditions and model artifacts. Diagnostic judgments SHALL be separate. The claimed scope SHALL be Vietnamese tasks; claims of language-specific gaps SHALL require separately versioned matched-language variants and translation validation. Withheld gold SHALL not yield invented per-item labels.

#### Scenario: Annotation revision changes
- **WHEN** review revision is changed
- **THEN** old source bytes, ordered anchors and historical metrics are preserved

### Requirement: Claim-specific evidence and operational hypotheses
The protocol SHALL distinguish audit evidence, observed phenomena, input sufficiency, corpus availability and per-hypothesis support. It SHALL separate external-evidence from parametric-knowledge hypotheses, retriever from assembly and generator, reading from instructions, parser from harness, measurement from instability. Unknown cause SHALL be an empty hypothesis set; mixed SHALL be derived. Human review/confidence SHALL NOT establish controlled attribution.

#### Scenario: Passage confirms an answer
- **WHEN** a correct answer is supported by a specific input span
- **THEN** the answer audit needs no causal evidence tier and does not assert absence of latent gaps

### Requirement: Prospective interventions and runtime isolation
A future B SHALL be run in the same registered campaign as S/K/KS. Diagnostic contrasts SHALL isolate content/length/position and prompting/tools/compute where relevant, separately from end-to-end deployment comparisons. Runtime routing SHALL predict quality/cost under budget and SHALL exclude gold, offline cause labels and all-arm outcomes. Action policy, all-arm failure and verifier false accept/reject and abstention metrics SHALL be preregistered. 720 arm attempts SHALL NOT be assumed to be 720 model calls. Unknown costs SHALL remain missing.

#### Scenario: Historical baseline used for audit
- **WHEN** historical outputs exist but a new campaign is planned
- **THEN** historical data remains an audit anchor and a new prospective B is required
