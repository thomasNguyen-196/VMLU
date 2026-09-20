## ADDED Requirements

### Requirement: Run registry
The system SHALL record one document per benchmark run with model, dataset,
prompt condition, runner config (temperature, seed, max-tokens, workers),
measurement-card hash, question count, and timestamp, so every stored result
is traceable to its measurement conditions.

#### Scenario: New run ingested
- **WHEN** a completed run's outputs are ingested
- **THEN** a `runs` document exists carrying model, dataset, condition,
  config, measurement_card_hash, n, and created_at, and every per-item
  document references it by run_id

### Requirement: Per-item result stores
The system SHALL store per-item results in dataset-appropriate collections
(`mc_items` / `reading_items` / `vbench_items`) with run_id, item_id, model
answer, gold, correctness/score, and raw response, indexed on
`(run_id, item_id)` for key lookup.

#### Scenario: Item lookup
- **WHEN** the frontend requests items for a (run_id, item_id) pair
- **THEN** the matching document is returned with answer, gold,
  correctness/score, and raw_response

#### Scenario: Ragged shapes preserved
- **WHEN** MC letter answers, reading free-text answers, and V-Bench JSON
  tool calls are stored
- **THEN** each keeps its native shape in its own collection with no lossy
  normalization into a single table

### Requirement: Precomputed summaries
The system SHALL serve dashboard numbers from precomputed `summaries`
documents (overall accuracy/EM/char-F1 plus per-category and per-subject
rows), each carrying the source `measurement_card_hash`, so the frontend
never recomputes aggregates at read time.

#### Scenario: Dashboard read
- **WHEN** the dashboard requests a model's summary for a dataset
- **THEN** it receives overall, per-category, and per-subject rows with
  matching measurement_card_hash and no server-side recomputation

### Requirement: Migration verification
The migration script SHALL verify row counts of every imported CSV against
its source file and refuse to mark the migration complete on any mismatch.

#### Scenario: Count mismatch
- **WHEN** an imported collection's count differs from its source CSV
- **THEN** migration aborts with the offending file and counts named, and
  no partial import is marked complete

### Requirement: Multi-model dashboard view
The system SHALL expose a DB-backed dashboard view comparing at least the
two evaluated models (Qwen3.5-9B-28K vs qwen38-nothink) across all datasets,
verified row-for-row against the file-based blob before the old blob
read-path is retired.

#### Scenario: Cutover check
- **WHEN** the DB-backed view renders alongside the file blob
- **THEN** every displayed number matches the blob's corresponding value
  before cutover is approved
