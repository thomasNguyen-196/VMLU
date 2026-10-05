## Purpose

Defines the RQ1 variance-decomposition table: one auditable place where every
measured harness/prompt variable appears with its effect size, CI, metric name,
and the run-to-run noise floor it has to beat.

## Requirements

### Requirement: No number in the table is typed by hand
The table SHALL be generated from run artifacts, and every contrast it shows SHALL
be declared by path. A declared artifact that does not exist SHALL stop the
generator — a decomposition table that quietly drops an arm is worse than none.

#### Scenario: A declared arm was deleted
- **WHEN** a declared compare CSV is missing
- **THEN** the generator exits with a message naming the source, dataset and card,
  and writes nothing.

#### Scenario: The declared set matches disk
- **WHEN** every declared path exists
- **THEN** the generator emits the CSV, the noise CSV and the markdown, and prints
  one line per contrast.

### Requirement: Metrics stay named and are never merged
Each row SHALL carry its own metric name. `accuracy`, `EM`,
`agreement_with_arm_A` and `valid_rate` are different quantities, so the table
SHALL NOT rank or total across them.

#### Scenario: A row has no metric name
- **WHEN** a contrast's artifact carries no metric
- **THEN** the row still renders with the metric it was declared with, never a
  blank.

### Requirement: The noise floor travels with the contrasts
The generator SHALL compute each repeated cell's run-to-run spread at a fixed `n`,
keep each cell separate, and never pool across `n`. Cells with a single run SHALL
NOT appear (they have no spread).

#### Scenario: Repeated cell on disk
- **WHEN** a cell has two or more runs at the same `n`
- **THEN** it appears with min, max, run count and spread equal to `max − min`.

#### Scenario: All runs are at one `n`
- **WHEN** every run of a cell uses the same item count
- **THEN** the noise table reports that `n`, and the caveat text is generated from
  the run counts rather than written by hand.

### Requirement: Caveats are generated, not asserted
The output SHALL state that a cross-model row is a different model pair rather than
a harness contrast, that metric names are not interchangeable, and which model the
noise floor belongs to.

#### Scenario: A tiny p-value
- **WHEN** a McNemar p is below 0.001
- **THEN** it is rendered in scientific notation, never rounded to `0.000`.