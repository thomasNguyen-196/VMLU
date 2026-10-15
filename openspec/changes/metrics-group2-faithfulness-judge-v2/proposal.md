# Proposal: Faithfulness judge, instrument v2 — stronger judge, fresh test (metrics group 2.2, MC-39)

## Why

MC-38 closed 2.2 because the judge failed the human-validation gate (κ 0.19 →
0.29, both < 0.60). A dev-set diagnosis showed the failure was **not** the
criterion but the instrument: (a) the judge ran with `reasoning_effort="none"`,
and (b) MiMo V2.5 is weak at the arithmetic/answer-type checks and is
non-deterministic at temperature 0. On the discriminating dev items a stronger,
different-family judge (`kimi-k3`) gives the human-consistent verdict and is
stable across repeats. The plan's stop was for *that* instrument; a new,
pre-registered instrument on a **fresh** test sample is the honest way to try
again — never a retroactive pass of the old gate.

## What Changes

- **New judge instrument (v2)**: `kimi-k3` @ OpenCode Zen Go (a different
  family from the model under test — no self-preference), the MC-38 v2 judge
  prompt unchanged, **no `reasoning_effort` pin** (provider default), reply
  budget 1500 tokens, and a parse-retry that re-asks only when the reply does
  not parse (format, never a guessed verdict).
- **Dev/test split**: the MC-38 60 labeled items become the *dev* set (the
  instrument was selected on it); the gate runs on a **fresh 60** (seed 43,
  disjoint from dev by construction). Human labels for the fresh set are
  committed before any judge verdict on it.
- **One shot**: MC-39 has no in-card prompt iteration. Pass → full 400-item
  judge pass and the first published faithfulness numbers (MC-40). Fail → 2.2
  is closed permanently with the negative result.
- Tooling: `judge_faithfulness.py` gains the reasoning-fallback parser,
  `judge_once` re-ask, `--exclude`, and the new judge defaults (tasks §1).

## Capabilities

### Modified Capabilities
- `faithfulness-eval`: adds the dev/test separation (an instrument is selected
  on dev and gated on fresh data), the "a changed instrument is a new
  pre-registration" rule, and the format-only re-ask contract.

## Impact

- `code_benchmark/judge_faithfulness.py` (parser fallback, `judge_once`,
  `--exclude`, defaults), `code_benchmark/test_suite.py` (4 new tests),
  `measurement_card.md` (MC-39 pre-register + MC-40 results),
  `data/faithfulness_labels_*_test.csv` (fresh, tracked), per-item artifacts
  under `all_res/ollama_result/Qwen3_5-9B-65K/`.
- Untouched: the citation run (`reading_cite_*`, MC-37/38) — the answers and
  EM are reused; only the judging changes. `run_reading_eval.py` /
  `score_reading_eval.py` stay byte-frozen.

## Non-goals

- No change to the citation condition, the answers, or the EM numbers.
- No re-labeling of the MC-38 dev labels (frozen).
- No claim from the dev-set probe — it only *selected* the instrument.
- No self-family judge (`qwen3.8-max` works but is the model under test's
  family; rejected for that reason).
