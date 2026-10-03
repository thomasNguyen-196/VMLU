## Purpose

Defines the position-bias measurement on legal_mc-146: a deterministic
choice-shuffle re-run of the same model under the same inference flags,
compared paired-item against the source-order baseline. It answers whether MC
accuracy depends on *where* the gold answer sits, separately from whether the
model knows the answer.

## Requirements

### Requirement: Pre-registered shuffle condition
The shuffle SHALL be fully determined by committed artifacts before any
shuffled inference: a fixed `SHUFFLE_SEED`, a per-item deterministic
permutation independent of input order, and a tracked shuffle manifest
quoting the source sha256 and the shuffled-input sha256.

#### Scenario: Re-running the adapter reproduces the input
- **WHEN** the adapter runs twice on the same source with the same seed
- **THEN** both output files are byte-identical.

#### Scenario: Input order does not matter
- **WHEN** source rows are fed in a different order
- **THEN** each item's shuffled choices and remapped gold are unchanged.

### Requirement: Gold follows the text, never the letter
The shuffled gold letter SHALL point at the same choice text as the original
gold. Items whose choice texts are not unique SHALL abort the adapter with an
error instead of guessing.

#### Scenario: Correct remap
- **WHEN** gold text `T` sits at position B in source order and at position D
  after shuffling
- **THEN** the shuffled gold is `D` and the item's choice-text set is unchanged.

#### Scenario: Ambiguous item
- **WHEN** two choices of one item have identical text
- **THEN** the adapter exits non-zero and names the item id.

### Requirement: Frozen runner and paired comparison
The shuffled run SHALL use the byte-identical `run_mc_eval.py` prompt/parser/
scorer path, and the comparison SHALL join baseline and shuffled results
per item id, reporting accuracy on both sides with a paired uncertainty
estimate plus the accuracy-by-gold-position breakdown.

#### Scenario: Baseline recompute
- **WHEN** the compare runs
- **THEN** it recomputes baseline accuracy from the stored arm-A final and
  refuses to proceed if it is not 130/146 (the MC-31 value).

#### Scenario: Small-n honesty
- **WHEN** the 95% CI of Δ includes 0
- **THEN** the card reports "below resolution at n=146" and follow-up shuffles
  stay closed.
