## Purpose

Score ViBidLQA (bid-auction QA with passage context) on Qwen3.5 with the same
EM/char-F1 discipline as the reading-400 eval: full test/val runs, gold from the
file itself, dashboard-patched numbers reproducible from the scores CSV.

## Requirements

### Requirement: BidLQA manifest split
The system SHALL build two manifests from the source files — test (603) and val
(482) — each row carrying context, question, and gold from its source line, with
stable item ids (`BIDLQA-T-0001…`, `BIDLQA-V-0001…`) and a pinned source sha256,
so a rerun on the same files reproduces the same item set.

#### Scenario: Manifest rebuild
- **WHEN** the manifest builder runs against the pinned source files
- **THEN** test has 603 rows, val has 482 rows, every gold non-empty, and the
  source sha256 matches the manifest header (else fail fast)

### Requirement: Open-book inference parity
The system SHALL run both splits through the existing reading pipeline with the
MC-3 condition (open-book prompt, 48-token budget, temperature 0, seed 42), so
BidLQA numbers are comparable with the reading-400 numbers.

#### Scenario: Condition drift
- **WHEN** inference runs with a different prompt template or token budget
- **THEN** the run is recorded under a NEW card id, never merged into the
  MC-11/MC-12 aggregates

### Requirement: EM/char-F1 scoring on file gold
The system SHALL score each split with EM + char-F1 against the file's own gold
answers and write per-item scores plus a summary, each summary carrying the
measurement-card hash, so the dashboard shows only reproducible numbers.

#### Scenario: Summary mismatch
- **WHEN** the summary EM disagrees with a recompute from the per-item scores
- **THEN** the dashboard patch refuses to write (same gate as the reading builder)

### Requirement: Dashboard block
The system SHALL patch a `bidlqa` block (test + val overall EM/char-F1, card ids,
model id) into the dashboard blob, leaving every other key untouched.

#### Scenario: Patch isolation
- **WHEN** the bidlqa patch runs
- **THEN** only the `bidlqa` key changes; vmlu/vbench/reading/legal byte-identical
