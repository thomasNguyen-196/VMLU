# Proposal: RQ1 — one auditable variance-decomposition table (thesis)

## Why

`docs/harness-evolution-thesis-plan.md` RQ1 asks how much of a measured score is
capability vs. harness engineering. The repo already holds the measurements
(MC-15…MC-23, MC-30, MC-31/32, MC-36, MC-44) but they live in prose across ~30
cards, so the thesis's headline claim has no single artifact behind it, and the
three things a reader needs next to each number — its CI, its noise floor, and its
metric name — are scattered.

The harness display layer (`build_dashboard_harness.py`) computes a *ladder*: one
variance source (the scaffold) across many datasets. RQ1 needs the other axis —
**many variance sources side by side**, including the ones that live in other
pipelines entirely (option order in `compare_position_bias.py`, calibration in
`run_mc_calibration_eval.py`).

## What Changes

- `code_benchmark/build_rq1_decomposition.py` reads the run artifacts of every
  declared contrast and emits `docs/rq1-decomposition.csv`,
  `docs/rq1-decomposition-noise.csv` and the generated
  `docs/rq1-decomposition.md`.
- A noise floor computed from the repeated 28K cells (spread of the same condition
  across repeats at a fixed `n`), emitted next to the contrasts it bounds.
- Tests: a missing artifact is an error, declared sources must exist, metrics stay
  named per row, cells are never collapsed or pooled across `n`, and a tiny `p` is
  never rendered as `0.000`.

## Capabilities

### New Capabilities
- `rq1-decomposition`: the declared-source contract, the no-hand-typed-number
  rule, per-row metric naming, and the noise floor travelling with the table.

## Impact

- New: the generator, three tracked outputs, `TestRq1Decomposition`.
- Untouched: every runner, scorer, card, and the harness block. It reads artifacts;
  it writes only its own three files.

## Non-goals

- No new inference. Every row already exists on disk.
- No re-scoring, no cross-arm pooling, no ranking across metrics.