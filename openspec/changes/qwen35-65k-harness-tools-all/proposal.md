# Proposal: Qwen3.5-9B-65K re-baseline + default-all-tools harness arm

## Why

The IEC gateway no longer serves `Qwen3.5-9B-28K` (its node is offline — HTTP 503
today); only `Qwen3.5-9B-65K` is running. Every Qwen harness conclusion
(MC-15…MC-30) is therefore stranded on a condition that cannot be re-run, and the
project's stated direction is to measure the harness **as used**: omp's
default-all tool menu, not the six-tool menu the old tool cells used.

Two facts make this a scoped plan rather than a re-run: (1) a new model tag is a
new condition (MC-4/MC-29 doctrine: never resume, never compare across tags), and
(2) the 65K node is throughput-bound and fragile — probing measured ~3.2k prefill
tok/s aggregate, `n_ctx = 65,024`, and a captured default-all request of
14,177 prompt tokens/item, which prices the full arm at ~90M prompt tokens
(~8–10h) and caused a ~6-minute gateway blackout under a 32-way probe.

## What Changes

- `run_harness_eval.py`: accept a `--tools all` sentinel that **omits** the
  `--tools` flag from omp's argv (omp's own default menu, measured at 11 tools in
  this flag context), alongside the existing `none` and explicit-menu behaviors;
  the condition string is recorded per run and never mixed with other conditions.
- New measured arms on `Qwen3.5-9B-65K` (new tag ⇒ new slugs, new card MC-31):
  arm A (direct, byte-frozen prompts) and arm B (`omp` clean scaffold +
  default-all tools, `temperature=0` pinned via the capture proxy) across the
  full ladder: reading400, legal_mc, legal_nli, bidlqa_val, vbench_agentic,
  vbench_mc.
- Server-reality evidence recorded with the card: llama.cpp fingerprint
  `b11243-fc07d781e`, `n_ctx 65,024`, prefilling/decoding rates, the default-all
  request inventory (11 tools, 50,348 chars of schemas, 14,177 prompt tokens),
  the blackout incident, and the probe method so it is re-runnable.
- Worker policy for long arms: `--workers` ≤ 6 (default 4), one dataset per run,
  preflight before each, `--resume` between; no high-concurrency probes against
  the shared gateway.
- MiMo V2.5 arm `M7` (same default-all sentinel, Zen Go, `reasoning_effort`
  pinned) is a follow-on phase, not part of this change's gate.

## Capabilities

### New Capabilities
- `harness-eval`: the measurement contract of the omp harness arm — three-valued
  tool condition (`none` | explicit menu | `all`), clean-scaffold guards, model-tag
  identity (no cross-tag resume), and the pre-run endpoint capability probe that a
  long arm must pass before spending items.

### Modified Capabilities
<!-- none: eval-scoring and the frozen prompt/parser contracts are untouched -->

## Impact

- `code_benchmark/run_harness_eval.py` (tool sentinel, condition label),
  `code_benchmark/build_dashboard_harness.py` (new arm registry + coverage),
  `code_benchmark/test_suite.py` (argv + registry tests), `.gitignore`
  (the 65K agent dir), `measurement_card.md` (MC-31 + server evidence).
- Endpoints: IEC `https://llmapi.iec-uit.com/v1` (Qwen3.5-9B-65K, via
  `capture_scaffold.py` pinning hop); MiMo runs later through OpenCode Zen Go.
- Evaluation regime: touches **Regime A** (capability; frozen prompts, zero-shot,
  temperature 0) on the harness-elicitation axis (MC-15…); Regimes B and C
  (quantization/edge, reasoning budget) are out of scope.

## Non-goals

- Not re-running, invalidating, or merging with the 28K results — they keep their
  cards and labels; 65K is a different condition, not a replacement number.
- No omp default-persona arm for this change: the system prompt stays the neutral
  line (clean family, same as H5/M6), so the tool gene stays interpretable.
- No scoring-metric changes; `vbench_mc` stays agreement-with-arm-A only (no
  local gold), and no leaderboard upload is part of this change.
- No server tuning, no admin access, no attempt to extract host configuration
  beyond what the public API exposes.
