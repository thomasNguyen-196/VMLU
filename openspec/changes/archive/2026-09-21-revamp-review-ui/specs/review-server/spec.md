## Purpose

Defines the local backend for the human-acceptance review pass (Next.js API routes + a Python emitter): the joined review data is validated and emitted by the existing Python pipeline and served to the app; reviewer decisions persist on disk; the CSV consumed by the downstream gold-merge pipeline is produced server-side — so the review tool no longer depends on a single browser's storage or on client-side re-implementation of pipeline logic.

## ADDED Requirements

### Requirement: Data emission reuses the validated join
The system SHALL provide an `export-blob` command that loads the annotator workbook and every `reading_answers_<model>.csv` using the existing fail-fast join validation (required columns, duplicate keys, unknown item keys, coverage == workbook size unless explicitly relaxed) and writes the resulting blob to the app's data file; it SHALL exit non-zero without writing when validation fails. The app SHALL refuse to run against a missing or malformed blob and surface the exact command to regenerate it.

#### Scenario: Clean emission
- **WHEN** `export-blob` is invoked with a workbook and answer CSVs that pass all existing join checks
- **THEN** the blob file is written with schema_version 1 and the app boots and lists its models

#### Scenario: Validation failure
- **WHEN** any answer CSV fails an existing join check (e.g. covers fewer items than the workbook without the relaxation flag)
- **THEN** the command exits with the same kind of clear error message the build command produces, and the blob file is not overwritten

### Requirement: Item data served as JSON
The system SHALL expose the joined review blob (same content and `schema_version` as the static build embeds — models, deduped passages, passage-contiguous items with per-model answers) via a JSON endpoint, and SHALL serve the review application shell at the site root.

#### Scenario: Fetch items
- **WHEN** the client requests the items endpoint
- **THEN** it receives the full blob with every item's per-model answers, in workbook order

### Requirement: Reviewer state persisted on disk per (reviewer, model)
The system SHALL accept a save of one reviewer's decision state — keyed by reviewer name and model, with the same per-item record shape (decision, correction, note) the localStorage schema uses — and SHALL persist it as one JSON file per (reviewer, model) bucket under a gitignored directory, using an atomic write so a crash cannot leave a half-written file. A save MUST NOT overwrite another bucket, and reviewer-name matching SHALL use the same diacritic-insensitive slug as the current UI so buckets cannot silently collide.

#### Scenario: Autosave round-trip
- **WHEN** the client saves state for reviewer "linh" on model M and a later request loads that bucket
- **THEN** the returned state equals the saved state (all item keys, decisions, corrections, notes)

#### Scenario: Concurrent buckets isolated
- **WHEN** reviewer "linh" saves state for model M1 while reviewer "hoang" has saved state for model M1 and M2
- **THEN** each bucket file is independent and no save modifies a bucket belonging to a different (reviewer, model) pair

#### Scenario: Corrupt bucket file
- **WHEN** a state file on disk is unparseable
- **THEN** the load endpoint reports the bucket as unreadable rather than serving empty state as if it were the truth, and the client surfaces that to the reviewer

### Requirement: Server-side review CSV export
The system SHALL produce, on request, a review CSV for a given (reviewer, model) bucket whose header and row content are byte-compatible with what `export_annotation_workbooks.py review` accepts today: columns `annotator,model,dataset,item_id,stratum,decision,model_answer,corrected_answer,note`, one row per item in workbook order, corrected answer populated only for rejects, UTF-8 with BOM so Vietnamese opens correctly in spreadsheet apps.

#### Scenario: Export feeds the existing merge
- **WHEN** an exported CSV from server mode is passed to `export_annotation_workbooks.py review --a ... --b ...`
- **THEN** the merge computes acceptance stats, IAA, and gold exactly as it does for a CSV exported by the current localStorage UI

#### Scenario: Unanswered items
- **WHEN** the bucket has no decision for some items
- **THEN** those rows carry an empty decision cell and the merge's existing "reviewed" accounting ignores them

### Requirement: Review bucket discovery
The system SHALL list existing (reviewer, model) buckets with their item-decision counts and last-saved time, so a reviewer can pick up their own bucket and see — without opening a browser profile — what state exists on disk.

#### Scenario: List after saves
- **WHEN** two reviewers have each saved state for one model
- **THEN** the listing shows both buckets, distinguishable by reviewer and model, with correct reviewed/total counts

### Requirement: Localhost-only tool
The system SHALL run the app and its API routes on localhost (the framework's default dev/prod-bind behavior, no public exposure step documented or offered), SHALL NOT implement authentication beyond the reviewer-name gate, and its documented use is a single researcher machine; serving state written by one reviewer to another reviewer's session in a shared deployment is out of scope.

#### Scenario: Default bind
- **WHEN** the app is started through its documented commands
- **THEN** it is reachable on localhost only
