## Purpose

Durable, queryable store for every benchmark result with proper identity: each model gets one canonical id, each dataset gets its own id, and every run and item carries both — so the frontend can browse model → dataset → run → item with full provenance.

## ADDED Requirements

### Requirement: Model registry
The system SHALL maintain a `models` collection where each model has exactly one canonical `_id` (stable, lowercase, URL-safe, e.g. `qwen3.5-9b-28k`), with `display_name`, `dir_slugs[]` (existing CSV directory names), `endpoint_ids[]`, quantization/params/endpoint/notes, so every result row resolves to one model identity regardless of filename spelling variants.

#### Scenario: Model lookup by canonical id
- **WHEN** the frontend requests `GET /api/results/models/qwen3.5-9b-28k`
- **THEN** it receives one document with display name, directory slugs, endpoints, and notes

#### Scenario: No duplicate model identities
- **WHEN** migration ingests CSVs from `Qwen3_5-9B-28K/`, `qwen38-nothink/`, and `Qwen3_8-27B-Q4_K_M_gguf/`
- **THEN** each maps to exactly one registry `_id`, and every run/item carries that `model_id`

### Requirement: Dataset registry
The system SHALL maintain a `datasets` collection where each dataset has exactly one stable `_id` (e.g. `vmlu-mqa-valid`, `vbench-public-test`, `reading-400`, `legal-mc-146`, `legal-nli-150`, `bidlqa-val`, `bidlqa-test`), with `benchmark`, `split`, `n`, `source_file`, `source_sha256`, `gold_kind` (withheld/local/file/reviewed), and `manifest_path`, so runs are comparable only within the same dataset id.

#### Scenario: Dataset lookup
- **WHEN** the frontend requests `GET /api/results/datasets/bidlqa-val`
- **THEN** it receives n=482, source file + sha256, gold kind, and manifest path

#### Scenario: Run carries both ids
- **WHEN** any run or per-item document is read
- **THEN** it carries both `model_id` and `dataset_id` (denormalized on items for join-free queries)

### Requirement: Run registry
The system SHALL record one document per benchmark run in `runs` with `_id` = `{model_id}__{dataset_id}__{card_id}`, carrying model, dataset, prompt condition, runner config (temperature, seed, max-tokens, workers), measurement-card hash, question count, and timestamp, so every stored result is traceable to its measurement conditions.

#### Scenario: New run ingested
- **WHEN** a completed run's outputs are ingested
- **THEN** a `runs` document exists carrying model_id, dataset_id, condition, config, measurement_card_hash, n, and created_at, and every per-item document references it by run_id

### Requirement: Per-item result stores
The system SHALL store per-item results in dataset-appropriate collections (`mc_items` / `reading_items` / `vbench_items`) with run_id, model_id, dataset_id, item_id, model answer, gold, correctness/score, and raw response, with a unique index on `(run_id, item_id)` for key lookup.

#### Scenario: Item lookup
- **WHEN** the frontend requests items for a (run_id, item_id) pair
- **THEN** the matching document is returned with answer, gold, correctness/score, and raw_response

#### Scenario: Ragged shapes preserved
- **WHEN** MC letter answers, reading free-text answers, and V-Bench JSON tool calls are stored
- **THEN** each keeps its native shape in its own collection with no lossy normalization into a single table

### Requirement: Precomputed summaries
The system SHALL serve dashboard numbers from precomputed `summaries` documents (one per run: overall accuracy/EM/char-F1 plus per-category and per-subject rows where applicable), each carrying the source `measurement_card_hash` plus `model_id` and `dataset_id`, so the frontend never recomputes aggregates at read time.

#### Scenario: Dashboard read
- **WHEN** the dashboard requests a model's summary for a dataset
- **THEN** it receives overall, per-category, and per-subject rows with matching measurement_card_hash and no server-side recomputation

### Requirement: Migration verification
The migration script SHALL seed both registries first, then verify row counts of every imported CSV against its source file, and refuse to mark the migration complete on any count mismatch or any run/item missing `model_id`/`dataset_id`.

#### Scenario: Count mismatch
- **WHEN** an imported collection's count differs from its source CSV
- **THEN** migration aborts with the offending file and counts named, and no partial import is marked complete

#### Scenario: Missing identity
- **WHEN** any document would be written without `model_id` or `dataset_id`
- **THEN** migration aborts with the offending document named
