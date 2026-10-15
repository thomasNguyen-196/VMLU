## Purpose

Score Legal NLI-150 (binary entailment Có/Không over a legal passage) on Qwen3.5
through the frozen MC runner: map the two choices onto letters, keep scoring
identical to every other MC run, report against the recomputed majority baseline.

## ADDED Requirements

### Requirement: Binary-to-letter adapter
The system SHALL build the runner input with ids `LG-NLI-0001…0150` in source
order, choices prefixed `A. Có` / `B. Không`, gold letter Có→A / Không→B, with
the source sha256 pinned and verified before the run, so the input is a pure
function of the source file (runner untouched).

#### Scenario: Source drift
- **WHEN** the source sha256 differs from the pinned value
- **THEN** the adapter aborts before writing any input row

### Requirement: Frozen MC scoring
The system SHALL score with the byte-frozen `build_prompt` / `extract_answer`
(temperature 0, seed 42, max-tokens 4 — Qwen3.5 non-thinking) and recompute
accuracy from the per-row `correct` column, refusing to publish on any mismatch
with `accuracy_*`, so NLI numbers are comparable with MC-6/MC-10.

#### Scenario: Recompute mismatch
- **WHEN** the accuracy file disagrees with the per-row recompute
- **THEN** no dashboard write happens; the run is investigated, never patched

### Requirement: Baseline reporting
The system SHALL recompute the majority-class baseline from the gold column
(never hardcoded) and report accuracy alongside it (expected ~50% on 75/75),
so the lift over chance is explicit.

#### Scenario: Baseline check
- **WHEN** the gold distribution is read
- **THEN** the baseline letter, count, and rate are derived from it and recorded
  in the dashboard block and the measurement card

### Requirement: Dashboard block
The system SHALL patch a `legal_nli` block (overall accuracy, baseline, by-gold
A/B split, card MC-13, model id) into the dashboard blob, leaving every other
key untouched.

#### Scenario: Patch isolation
- **WHEN** the NLI patch runs
- **THEN** only the `legal_nli` key changes; vmlu/vbench/reading/legal/bidlqa
  byte-identical
