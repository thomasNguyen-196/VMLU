# Design: faithfulness judge instrument v2 (MC-39)

## Context

- The citation condition (MC-37) produced 400 answers with citations; EM 65,00;
  compliance 100%. The only thing that failed was the judge (MC-38).
- MC-38 diagnosis: MiMo V2.5 (reasoning off) is lenient on arithmetic and on
  the "answer must match the question's ask" rule, and varies run-to-run.
- Available judge endpoints: OpenCode Zen Go lists stronger models
  (`kimi-k3`, `glm-5.3`, `deepseek-v4-pro`, `qwen3.8-max`, `mimo-v2.5-pro`, …).
- The 60 MC-38 human labels exist and are frozen — they are the *dev* set now.

## Decisions

### D1 — Judge = kimi-k3 (different family)
Dev probe on 4 labeled items: `kimi-k3` returned the human-consistent verdict on
the 3 non-questionable items (`drop:8335` unsupported ×3, `drop:5493`
unsupported ×2 + 1 format error, a clear `yes` item supported ×3) and its
reasoning shows the right mechanism ("câu trả lời chỉ là con số, không kèm lựa
chọn"). `qwen3.8-max` scored the same but is the Qwen family of the model under
test → rejected (self-preference risk). `glm-5.3` / `deepseek-v4-pro` failed to
parse on 2 of 4 dev items. `mimo-v2.5-pro` failed to parse on 2 of 4.
Selection used the DEV set only — never the test set.

### D2 — Dev/test separation (the point of this change)
The gate must run on data the instrument was not selected on:
- **dev** = the 60 MC-38 labels (`data/faithfulness_labels_Qwen3_5-9B-65K-cite.csv`),
- **test** = a fresh 60, `--seed 43`, `--exclude` the dev file, same 15×4
  stratification. Fresh human labels committed before any judge verdict.

### D3 — Instrument config (pre-registered in MC-39)
`kimi-k3`, prompt = MC-38 v2 bytes (unchanged), temperature 0, seed 42,
`reasoning_effort` **omitted** (provider default — reasoning judges need it),
`max_tokens=1500`, parse-retry 2 (format only). Any change to these is a new
instrument.

### D4 — Parser + re-ask (format, never a guess)
`parse_judge_verdict` first tries JSON (bare / first{…last}); if that fails it
takes the **last** explicit `"verdict"` field (reasoning traces mention the
field while thinking — the final one is the answer). `judge_once` re-asks up to
2 times when the reply does not parse; if all attempts fail the item is a
`judge_error`, counted, and the validation refuses to score it. No keyword
fallback ever invents a verdict.

### D5 — Gate and one-shot rule
Same thresholds: agreement ≥ 0,80 **and** Cohen's κ ≥ 0,60, on the fresh 60.
**No in-card iteration**: if v2 fails, 2.2 closes permanently with the negative
result (a further instrument needs its own pre-registration and fresh labels,
and is not assumed to be worth the cost).

### D6 — If the gate passes
Full 400-item judge pass (same config, `--resume`-free, judge model pinned),
then MC-40: compliance, EM/char-F1, verbatim rate, supported rate, joint
`correct ∧ supported`, cross-tab, and the disclosed caveat that the *test* κ is
a single-sample estimate. Optional `/results` seed for `reading-400 × 65k`.

## Risks

| Risk | Mitigation |
|---|---|
| Judge non-determinism drags κ | kimi-k3 stable on repeats; gate is a single pre-registered evaluation; disclosed |
| Test sample overlaps dev | `--exclude` + a unit test on disjointness |
| Tuning on the test by accident | instrument selected on dev only; test judged once |
| Cost of a strong judge | 60 validation + ≤400 full calls, disclosed in MC-39 |
