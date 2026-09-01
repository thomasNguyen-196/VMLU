## Purpose

Defines the self-scoring behavior of the VMLU evaluation pipeline: when ground-truth answers are present in the input, the system reports accuracy (overall, per-subject, per-category) alongside model answers; when absent, it preserves the leaderboard-submission behavior unchanged.

## Requirements

### Requirement: Gold-answer detection at load time
The system SHALL determine, from the loaded question records, whether the input provides a ground-truth `answer` for every record, and SHALL treat the run as "scorable" only in that case. Mixed inputs (some records with `answer`, some without) SHALL be treated as non-scorable with a warning logged.

#### Scenario: Scorable input (dev.jsonl / valid.jsonl)
- **WHEN** every loaded record contains a non-empty `answer` field
- **THEN** the run is marked scorable and scoring is performed after inference

#### Scenario: Non-scorable input (test.jsonl)
- **WHEN** no loaded record contains an `answer` field
- **THEN** the run is marked non-scorable and no scoring or new columns are produced

#### Scenario: Mixed input
- **WHEN** only some loaded records contain `answer`
- **THEN** the run is marked non-scorable, a warning is logged, and behavior matches the no-gold case

### Requirement: Correctness comparison
For scorable runs, the system SHALL compare each model answer against the gold answer using case-insensitive exact match of the option letter after the existing answer-extraction normalization, and SHALL record a binary correctness value per question. An unparseable model answer (empty string) SHALL be recorded as incorrect.

#### Scenario: Matching answer
- **WHEN** the gold answer is `B` and the model answer parses to `B`
- **THEN** the record is marked correct

#### Scenario: Non-matching answer
- **WHEN** the gold answer is `B` and the model answer parses to `D`
- **THEN** the record is marked incorrect

#### Scenario: Unparseable model output
- **WHEN** the model output yields no parsable option letter
- **THEN** the record is marked incorrect and counted in the accuracy denominator

### Requirement: Enriched per-question output for scorable runs
For scorable runs, the full-evaluation CSV SHALL contain, in addition to the existing columns, `gold_answer` (the ground-truth letter) and `correct` (1 or 0). The `submission.csv` format SHALL remain `id,answer` with the model's answers in both scorable and non-scorable runs.

#### Scenario: Scorable run outputs
- **WHEN** a scorable run completes
- **THEN** `full_evaluation_<model>.csv` includes `gold_answer` and `correct` columns and `submission.csv` is unchanged in format

#### Scenario: Non-scorable run outputs
- **WHEN** a non-scorable run completes
- **THEN** `full_evaluation_<model>.csv` and `submission.csv` are exactly as before this change (no new columns, no accuracy file)

### Requirement: Accuracy aggregation and reporting
For scorable runs, the system SHALL report accuracy as a percentage of correct answers at three levels: overall, per-subject (subject = numeric prefix of `id`, 01–58), and per-category (each subject mapped to exactly one of STEM, Humanities, Social Science, Other per the official VMLU subject numbering). The per-question accuracy file SHALL be persisted under the results directory, and the console summary SHALL include overall accuracy with the correct/total counts.

#### Scenario: Overall and per-subject report
- **WHEN** a scorable run of N questions completes
- **THEN** overall accuracy equals correct/N, and per-subject rows exist for every subject present in the run

#### Scenario: Category roll-up
- **WHEN** per-subject accuracy is computed
- **THEN** each subject's questions roll up into exactly one of the four categories, and the sum of category question counts equals the total number of questions

#### Scenario: Unknown subject prefix
- **WHEN** a record's subject prefix is outside the 01–58 mapping
- **THEN** it is reported under an `unknown` category and the run still completes (no silent drop)

### Requirement: Resume compatibility
The scoring summary SHALL be computed from the merged set of all completed results at the end of a run, so that resuming from a checkpoint produced before scoring existed (or from a partially completed run) yields correct final accuracy as long as every question has a final model answer.

#### Scenario: Resume from pre-scoring checkpoint
- **WHEN** a scorable run resumes from a checkpoint CSV lacking the `correct` column and finishes all remaining questions
- **THEN** the final full-evaluation CSV and accuracy summary are complete and correct for all questions

### Requirement: Prompt and parsing contracts preserved
The scoring feature SHALL NOT modify the prompt template string, the answer-extraction logic, the retry/authentication behavior, or any output format used by the non-scorable path.

#### Scenario: Parity tests remain green
- **WHEN** the existing parity test suite runs against the modified pipeline
- **THEN** `build_prompt` and `extract_answer` behavior is byte-identical to the pre-change reference
