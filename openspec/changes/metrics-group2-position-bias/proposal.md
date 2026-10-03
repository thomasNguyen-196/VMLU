# Proposal: Position-bias measurement on legal_mc (metrics group 2.1)

## Why

Every MC accuracy in this repo (MC-10, MC-31 arm A, …) is measured with choices
in **source order** — and the source order is gold-position-biased: legal_mc has
91/146 gold = A (62.3% majority baseline). If the model partly exploits "answer A
is likely", the reported accuracy overstates position-robust capability. Nobody
has measured this; the plan `docs/metrics-plan-3-nhom.md` (group 2.1) marks it
the cheapest open validity threat: one re-run, no new gold needed.

## What Changes

- New adapter `code_benchmark/make_shuffled_mc_input.py`: deterministic per-item
  shuffle of legal_mc choices (seed pre-registered) + remapped golds. Emits a
  shuffled input JSONL for the **unchanged** `run_mc_eval.py` and a committed
  shuffle manifest.
- One new arm-A-equivalent run on `Qwen3.5-9B-65K` (146 items, same temp/seed/
  max_tokens/workers as MC-31 arm A), outputs isolated under shuffled names —
  `run_mc_eval.py`, `build_prompt`, `extract_answer` stay byte-identical.
- New compare `code_benchmark/compare_position_bias.py`: accuracy orig vs
  shuffled, Δ with paired bootstrap CI + McNemar, flip analysis, and
  accuracy-by-gold-position (the table that separates "A-bias exploit" from
  "position sensitivity").
- Two measurement-card blocks: MC-35 (pre-register, before any infer) and MC-36
  (results).

## Capabilities

### New Capabilities
- `position-bias`: the shuffle-manifest contract (per-item deterministic
  permutation, gold-text preservation, committed before infer) and the
  orig-vs-shuffled paired comparison contract for MC accuracy.

### Modified Capabilities
<!-- none: eval-scoring and the frozen prompt/parser contracts are untouched -->

## Impact

- New: `code_benchmark/make_shuffled_mc_input.py`,
  `code_benchmark/compare_position_bias.py`,
  `data/legal_slm_multichoice_shuffled_s1234_manifest.json` (tracked),
  shuffled input JSONL (tracked or gitignored build artifact — decided in
  design), `measurement_card.md` (MC-35 + MC-36).
- Untouched: `code_benchmark/run_mc_eval.py` (verified byte-identical by diff),
  `openspec/specs/eval-scoring/spec.md`, dashboard block (no change — see
  non-goals), all harness arms and their cards.
- Endpoint: IEC internal `http://llmapi.iec/v1` over VPN (the working 65K path
  from MC-31/MC-32); preflight before the run, `--resume` never crosses
  conditions.

## Non-goals

- No harness-arm (`omp`) shuffle — `docs/metrics-plan-3-nhom.md` defers that
  ("quyết sau"); this change measures the **model**, not the scaffold.
- No NLI shuffle (binary A/B — trivially uninformative), no VMLU-1047 or
  VM14K shuffle (follow-ups only if the legal_mc effect exceeds the noise
  floor: CI width on n=146 is ~±7 points).
- No dashboard `/harness` change: this is an arm-A validity check, not a
  harness comparison. Results live in the card + `docs/model-insights.md`.
- No prompt/parser/scorer changes of any kind.
