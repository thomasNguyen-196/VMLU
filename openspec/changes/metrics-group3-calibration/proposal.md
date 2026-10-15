# Proposal: MC calibration from logprobs (metrics group 3.1, MC-41/42)

## Why

Group 3.1 of `docs/metrics-plan-3-nhom.md` starts with a probe: does the
gateway expose `logprobs`? Probed 2026-10-04: **yes** — the IEC gateway returns
`logprob` + `top_logprobs` per token for `Qwen3.5-9B-65K`, and on the frozen MC
prompt the first generated token is the bare answer letter with the five A–E
options in its `top_logprobs`. The "no logprobs → stop" branch does not fire, so
the plan's follow-up is now a bounded, cheap measurement: **is the model's
confidence calibrated?**

## What Changes

- New runner `run_mc_calibration_eval.py` (`run` | `report`): re-runs the
  frozen MC condition with `logprobs=true, top_logprobs=20`, builds a
  probability distribution over A–E from the first token, and reports
  accuracy / ECE / Brier / a reliability table / over-confidence.
- First measurement: `legal_mc-146` on `Qwen3.5-9B-65K` (gold from the frozen
  manifest, ~3 min). A larger `vmlu-mqa-all-gold` (1,047) pass is an optional
  follow-up, not part of this change.
- Cards: MC-41 (probe + pre-register) and MC-42 (results).

## Capabilities

### New Capabilities
- `calibration-eval`: the logprobs-availability contract, the first-token
  A–E distribution rule, the frozen-prompt/scorer reuse, and the
  ECE/Brier/reliability definitions.

## Impact

- New: `code_benchmark/run_mc_calibration_eval.py`, tests in `test_suite.py`,
  `measurement_card.md` (MC-41/42), per-item artifacts under
  `all_res/ollama_result/Qwen3_5-9B-65K/`.
- Untouched: `build_prompt`/`extract_answer` (frozen), every existing MC card.
  Requesting logprobs is a read-only option — the report checks the accuracy
  against the MC-31 baseline as a sanity note, not a gate.

## Non-goals

- No safety work (group 3.2 — needs a rubric and new gold).
- No temperature/decoding change; the calibration condition is the frozen MC
  condition plus logprobs capture only.
- No claim of full-distribution calibration beyond what the first-token
  distribution supports (stated as a limitation).
