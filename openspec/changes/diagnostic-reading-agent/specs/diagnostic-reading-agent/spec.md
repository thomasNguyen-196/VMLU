## Purpose

Test whether the legal-agent findings hold on general Vietnamese reading. The findings are:
- the harness gap reverses between Qwen3.5-9B and MiMo-V2.6-Flash;
- omp's default system prompt carries the interaction.

Both models answer the 400 Reading-400 questions by searching a folder of long article files. Five arms run in one window: DSHF, OMPF, OMPS, C and O, two draws each. The registration is fixed before the first request.

## ADDED Requirements

### Requirement: Long-file reading corpus
The build SHALL write every distinct passage of the viSQuAD and Vi-DROP source files, deduplicated on NFC-normalised text with source bytes kept, in SHA-256 order into files of 50 passages, one sentence per line, with no line over 600 characters, so that only whitespace changes. Each passage SHALL be preceded by a `## Đoạn NNNN` heading. The build SHALL record each passage's file and line range, and SHALL fail when a Reading-400 item's passage is missing from the corpus.

#### Scenario: Corpus counts
- **WHEN** the corpus is built from the source files on disk
- **THEN** it holds 2,284 passages in 46 files, and all 400 items map to exactly one passage

### Requirement: Closed-book agent task
Every DSHF, OMPF and OMPS attempt SHALL send the same task: the registered reading DSHF instruction, a blank line, then MC-96's closed-book prompt on the item's question, byte for byte. C SHALL send the closed-book prompt alone. O SHALL send the frozen reading prompt with the item's own passage.

#### Scenario: A task differs
- **WHEN** an agent attempt's task bytes differ from the manifest's task for that item
- **THEN** the build or preflight fails before any request

### Requirement: OMPS differs from OMPF only in the system prompt
OMPS SHALL run omp exactly as the model's OMPF, adding `--system-prompt` with dsh's system prompt for that model. That prompt SHALL be MC-117's file when the smoke test shows that dsh sends it in this work directory, and otherwise the message the smoke test recorded, saved and hashed.

#### Scenario: dsh's prompt changes with the work directory
- **WHEN** the smoke test's DSHF first system message differs from MC-117's file for the model
- **THEN** OMPS uses the recorded message, and the card states the difference

### Requirement: Paging check before the smoke test
The self-test SHALL read one corpus file without offset or limit in each harness, and SHALL record whether omp cuts or elides the page.

#### Scenario: omp shows a whole file
- **WHEN** omp returns a corpus file whole, without paging or elision
- **THEN** the smoke test is blocked until the owner decides the group size

### Requirement: Arms, draws and routes
Each model SHALL run 400 items × 5 arms × 2 draws = 4,000 attempts. Per item and draw, the arms SHALL follow an order permuted by seed 7.
- Qwen SHALL use MC-115's route.
- MiMo SHALL use MC-116's route.
- Both SHALL use temperature 1.0, a request cap of 30, a 65,024-token context and a response-model pin.

#### Scenario: Another model answers
- **WHEN** a response names a model other than the pin
- **THEN** the attempt is fatal and the run halts with every row written and loadable

### Requirement: Stalls and halted rows as in MC-117
A stream that ends with no chunk naming a model SHALL be recorded as `network` (`stream_stalled`), and the attempt SHALL be technical. A row written without a request SHALL carry its run key, shard, lane, model, protocol, profile and card ids.

#### Scenario: A stalled stream
- **WHEN** an agent attempt's stream ends without a model chunk
- **THEN** the attempt is technical and `--resume` sends it again

### Requirement: Smoke test before registration
Before registration, and only with the owner's go, the runner SHALL run four questions outside Reading-400 once per arm and model: 40 attempts. It SHALL record statuses, body keys, response models, first system messages and their hashes, the paging check, and tokens. No benchmark item SHALL be sent.

#### Scenario: A smoke attempt fails
- **WHEN** a smoke attempt does not complete
- **THEN** registration is blocked until the owner decides

### Requirement: Registered tests
The analysis SHALL run once, after both runs are final, on item means over the two draws, and SHALL test H1 (Qwen's OMPF − DSHF), H2 (MiMo's OMPF − DSHF), H3 (ι = H2 − H1) and H4 (P3 = (OMPS − OMPF)_MiMo − (OMPS − OMPF)_Qwen), with Holm over the four in each of two families: gold-token recall R (primary) and vi-reading-v3 token-F1 (continuity).

#### Scenario: Holm within a family
- **WHEN** the four R tests have p-values
- **THEN** Holm adjusts them together, separately from the four token-F1 tests

### Requirement: Test statistics
Each test SHALL use the mean per-item difference, a two-sided paired sign-flip p-value (20,000 resamples, seed 7) and a 95% percentile bootstrap interval (2,000 resamples, seed 7), with no margin.

#### Scenario: Reproducible statistics
- **WHEN** the analysis runs twice on the same score files
- **THEN** every difference, interval and p-value is identical

### Requirement: Reading rules
The report SHALL read H1 and H2 as "OMPF better/worse than DSHF" only with a Holm-adjusted p below 0.05, H3 as "recurs" or "reversed" only with a Holm-adjusted p below 0.05 in that direction, and H4 as carrying the interaction only when P3 is negative with a Holm-adjusted p below 0.05.

#### Scenario: Reading H3
- **WHEN** ι on R is positive with a Holm-adjusted p below 0.05
- **THEN** the report says that the legal interaction recurs on general reading

#### Scenario: Reading H4 without an interaction
- **WHEN** H3 is not detected
- **THEN** H4 is reported but not read as carrying an interaction

### Requirement: Judge sample
After the runs, a blind judge SHALL label the draw-1 answers of DSHF, OMPF and OMPS for both models on 100 items drawn by seed 7: 600 answers. The judge is Claude Opus 5.5 under the rubric of `docs/research/reading-judge-2026-11-25/plan.md`, and judging is blind to arm, model and score. The report SHALL give, per cell, the judge accuracy, R's bias and TP/FP/FN/TN, and the bias difference between arms within each model.

#### Scenario: R's bias differs between harnesses
- **WHEN** R's bias differs between two arms of one model by more than 5 points
- **THEN** the report flags every R-based test that uses those arms as possibly driven by scoring

### Requirement: Beside the tests
The report SHALL give, without tests:
- P1, P2 and the remaining interaction;
- DSHF − C and O − DSHF per model;
- splits by source set, Vi-DROP category and BM25 retrievability;
- a sensitivity run without the 7 flagged golds;
- gold-passage read and answer-seen rates;
- the score given the same read state;
- action flows, format compliance, outcomes, requests, tool calls and tokens.

#### Scenario: Gold passage read
- **WHEN** a read output of an attempt contains the first 80 normalised characters of the item's passage
- **THEN** the attempt counts as having read the gold passage
