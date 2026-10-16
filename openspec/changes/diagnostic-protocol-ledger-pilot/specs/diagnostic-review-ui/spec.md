## Purpose

Implement the revision-4 diagnostic methodology with explicit evidence scope, reviewer provenance and immutable benchmark boundaries.

## ADDED Requirements

### Requirement: Verified local revision-4 loading
The route SHALL validate pilot/protocol/schema/hash identities, 60 unique keys and the 15-key subset before rendering. Registered contrasts SHALL be exposed only after controls/provenance and evidence artifact hashes are checked. A missing/invalid snapshot SHALL show a setup error rather than a stale form.

#### Scenario: Invalid artifact
- **WHEN** a pilot or contrast artifact hash differs
- **THEN** the route refuses the affected unverified packet

### Requirement: Zustand scope and revision isolation
Drafts SHALL be stored in a revision-4 Zustand persist namespace, with bucket identity including pilot/protocol/reviewer/scope. Reviewer and scope SHALL be collected before the active draft is shown. Old v1/v2/v3 draft keys and the v3 Zustand store SHALL remain unchanged and downloadable for the same reviewer/scope. Human outcomes/attestations SHALL NOT be automatically migrated.

#### Scenario: Old v3 draft exists
- **WHEN** the same reviewer enters revision 4
- **THEN** the old draft is available for download and no old signoff fills a new review

### Requirement: Separate answer audit and optional cause controls
The UI SHALL display source question, model output, input, gold, scores and provenance read-only. It SHALL replace the common Observation/Supported dropdown with audit evidence kind/reference and separate input/corpus scope. Observed issues and optional per-hypothesis support SHALL be separate. No-issue items SHALL not ask for causal support. Only matching verified contrasts SHALL be selectable as contrast_supported.

#### Scenario: Item 2 answer verified
- **WHEN** the reviewer confirms the law named in the input
- **THEN** the audit can finish with no issue, input-span reference and no cause hypothesis

### Requirement: Primary-only provisional proposals
For primary-60, verified local AI proposals MAY seed blank reviewer-specific draft rows while preserving existing data. They SHALL not set human status or attestations. independent-15 SHALL not fetch/display/seed proposals. A reviewer exposed to suggestions SHALL not claim a blind second review.

#### Scenario: Independent scope starts
- **WHEN** a second reviewer enters independent-15
- **THEN** no suggestion endpoint is fetched and the reviewer begins with an own blank/saved human-only draft

### Requirement: Exact revision-4 CSV export
CSV SHALL use the exact importer column order and immutable source content. It SHALL identify the active scope on every row, retain 60 or fixed 15 keys, serialize per-hypothesis support as JSON and observed/cause labels as controlled sets. Incomplete draft judgments SHALL be exported blank. Matching human and blind attestation text SHALL appear only after explicit user confirmation.

#### Scenario: Incomplete AI draft exported
- **WHEN** suggestions exist without final human signoff
- **THEN** the CSV has source/scope rows but blank judgment fields and cannot count as completed reviews


### Requirement: Reviewer progress synchronized through backend
The system SHALL persist working review progress in MongoDB through a backend API, partitioned by normalized reviewer identity, pilot/protocol hashes and scope. Zustand SHALL remain the browser cache for immediate editing and unsynced changes. A different browser using the same self-declared reviewer identity SHALL restore the synchronized progress. Atomic database revision checks SHALL reject stale writes; failed saves SHALL retain local edits and expose retry and JSON backup. Working progress SHALL NOT automatically become an imported human audit record.

#### Scenario: AI proposals are not human work
- **WHEN** a primary reviewer opens 60 prefilled AI proposals without editing or attesting
- **THEN** all 60 SHALL appear as not started; only actual human changes SHALL add editor metadata and mark in-progress status

#### Scenario: Resume across clients
- **WHEN** a reviewer edits an item, the backend acknowledges the save, and the reviewer opens another browser using the same identity and pilot/scope
- **THEN** the item values, editor metadata and progress status SHALL be restored from MongoDB without requiring the original browser cache

#### Scenario: Existing local progress and historical backups
- **WHEN** current v4 progress is first synchronized
- **THEN** existing reviewer values SHALL be preserved, historical edit times SHALL NOT be fabricated and v1/v2/v3 backups SHALL remain available under a collapsed rubric-history control

#### Scenario: Concurrent edits
- **WHEN** two clients write against the same database revision
- **THEN** only one write SHALL succeed; the other SHALL receive an explicit conflict and SHALL retain its local changes
