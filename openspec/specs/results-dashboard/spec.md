## Purpose

DB-backed frontend views that let users pick a model, then a dataset that model actually ran, then inspect the run summary and per-item results — with multi-model comparison verified row-for-row against the file blob before the old blob read-path is retired.

## Requirements

### Requirement: Model-then-dataset navigation
The system SHALL expose read-only API routes `GET /api/results/models`, `GET /api/results/datasets`, `GET /api/results/runs?model=<model_id>&dataset=<dataset_id>`, `GET /api/results/summary?run=<run_id>`, and `GET /api/results/items?run=<run_id>&item=<item_id>` that read from Mongo and return registry/run/summary/item documents, so the frontend navigates model → dataset → run → item without recomputing aggregates.

#### Scenario: Browse flow
- **WHEN** the user opens the results view
- **THEN** the model selector lists registry models, picking one lists only datasets that model ran, picking one shows the run summary plus per-category/subject rows

#### Scenario: Per-item drill-down
- **WHEN** the user requests one item of a run
- **THEN** the API returns answer, gold, correctness/score, and raw response for that (run_id, item_id)

### Requirement: Multi-model dashboard view
The system SHALL expose a DB-backed dashboard view comparing at least the two evaluated models (`qwen3.5-9b-28k` vs `qwen38-nothink`) across all datasets, verified row-for-row against the file-based blob before the old blob read-path is retired.

#### Scenario: Cutover check
- **WHEN** the DB-backed view renders alongside the file blob
- **THEN** every displayed number matches the blob's corresponding value before cutover is approved

### Requirement: Old blob path stays green
The system SHALL keep the existing `benchmark-data.json` file read-path working until the DB-backed view passes the row-for-row cutover check, so the dashboard never regresses mid-migration.

#### Scenario: Pre-cutover regression
- **WHEN** the DB view is not yet verified
- **THEN** the existing benchmark page renders unchanged from the file blob
