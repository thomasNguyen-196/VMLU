# Design: MC calibration from logprobs (group 3.1)

## Context

- Probe (2026-10-04): IEC `/v1/chat/completions` with `logprobs=true,
  top_logprobs=5` returns `choices[0].logprobs.content[0].top_logprobs` with
  per-token logprob + top alternatives. On the frozen MC prompt the first
  generated token is the bare letter (`"B"`), and `top_logprobs[0]` held exactly
  `A,B,C,D,E` (checked on 3 legal_mc items). `Qwen3.5-9B-28K` is offline (503).
- Frozen MC contract: `build_prompt` / `extract_answer` (byte-frozen); gold for
  legal_mc comes from `data/legal_slm_multichoice_manifest.json` via
  `load_legal_mc`.

## Decisions

### D1 — Condition
`legal_mc-146`, `Qwen3.5-9B-65K` @ IEC internal, `temperature=0`, `seed=42`,
`max_tokens=4`, **plus** `logprobs=true, top_logprobs=20`. The prompt and parser
are byte-identical to MC-31 arm A; requesting logprobs is read-only, so the
letters should not move — the report prints the accuracy and notes it against
the MC-31 baseline (130/146), without gating on it (the backend is not fully
deterministic at temp 0).

### D2 — A–E distribution from the first token
From `logprobs.content[0].top_logprobs`, take tokens **exactly equal** to one of
`A,B,C,D,E`, `p_c = exp(logprob_c)`, renormalize over the letters present;
absent letters get 0 (never invented). `n_letters_found` is recorded; an item
with `< 2` letters is flagged **unusable** and excluded from the calibration
metrics but kept in the accuracy denominator. `confidence = p[chosen letter]`.

### D3 — Metrics
- `accuracy` (frozen scorer), `mean_confidence` (usable items).
- `ECE` with 10 equal-width bins (`idx = min(int(c·10), 9)`).
- `brier_confidence = mean((conf − correct)²)`;
  `brier_multiclass = mean(Σ_c (p_c − 1{chosen gold})²)`.
- reliability table (bin, n, mean confidence, accuracy) + `overconfidence =
  mean_conf − accuracy`.

### D4 — Scope
First pass = `legal_mc-146` (one domain, 146 items — a coarse curve, stated as a
limitation). `vmlu-mqa-all-gold` (1,047, 58 subjects) is the natural extension
if the first pass is clean; it is not part of this change.

## Risks

| Risk | Mitigation |
|---|---|
| logprobs token shape differs (space/prefix) | rule accepts only bare letters; `n_letters_found` surfaces misses; probe confirmed the shape |
| First-token distribution ≠ full-answer distribution | stated limitation: it is the model's first-token belief over options, the standard MC calibration object |
| Backend non-determinism | accuracy reported as-is, compared to MC-31 as a note, not a gate |
| 146 items → coarse bins | bins printed with n; VMLU-1047 follow-up if needed |
