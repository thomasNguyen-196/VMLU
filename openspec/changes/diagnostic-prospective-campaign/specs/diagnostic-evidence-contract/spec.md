## Purpose

Defines the evidence artifacts that arms O, K and KS consume so that evidence is attributable, hash-bound, free of benchmark answers and applied only where the input lacks it.

## ADDED Requirements

### Requirement: Oracle evidence artifact
Oracle evidence SHALL be stored as one record per item containing, for each provision, the document identifier, locator (article, clause, point), verbatim text, text hash and source reference, plus the reviewer identity and the hash of the review export it was derived from. A record SHALL NOT contain the answer, an option letter, a rationale or a solution.

#### Scenario: Answer leakage is rejected
- **WHEN** an oracle record includes the gold option letter or a reviewer rationale
- **THEN** validation fails and the record is not usable

### Requirement: Eligibility by input insufficiency and valid gold
Evidence arms SHALL apply only to items of datasets declared eligible by the campaign protocol (version 1: Legal MC) whose audited input-evidence sufficiency is insufficient. The runner SHALL reject evidence for any other item. For the core registration, evidence records SHALL be built from the adjudicated audit and only for eligible anchors whose adjudicated gold validity is valid. When both oracle and retrieved evidence are supplied, they SHALL cover the same items, so that arms O, K and KS run on the same anchors.

#### Scenario: Open-book item
- **WHEN** an evidence record names a reading item whose prompt already contains its passage
- **THEN** validation fails with the item key

#### Scenario: Suspect gold gets no evidence arm
- **WHEN** a Legal MC anchor has insufficient input evidence but adjudicated gold validity `suspect`
- **THEN** no evidence record is built for it and it keeps arms B and S only

#### Scenario: Oracle and retrieved evidence differ in coverage
- **WHEN** the core manifest is built with oracle evidence for an anchor that has no retrieved evidence
- **THEN** manifest construction fails and names the anchor

### Requirement: Versioned corpus and retrieval trace
A retrieval corpus SHALL be a versioned, hashed set of documents with provenance, and SHALL NOT contain benchmark answers, model outputs or annotation gold. Every K and KS attempt SHALL record the retrieval configuration hash, the ranked document and chunk identifiers, their scores and the exact text injected.

#### Scenario: Trace is complete
- **WHEN** a K-arm attempt is recorded
- **THEN** its row lists the retrieved chunk identifiers, their scores and the SHA-256 of the injected evidence block

### Requirement: Frozen evidence block
Evidence SHALL enter the prompt through a frozen template whose hash is part of the manifest, so that the input hash of an evidence arm changes if and only if the evidence text or the template changes.

#### Scenario: Evidence change alters the input hash
- **WHEN** one character of an evidence text changes
- **THEN** the item's input hash differs from the frozen manifest and the run refuses to start
