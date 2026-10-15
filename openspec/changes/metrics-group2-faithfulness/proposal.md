# Proposal: Faithfulness of reading answers — citation condition + validated judge (metrics group 2.2)

## Why

EM/char-F1 measure whether an answer matches the gold span; they say nothing
about whether the answer is **supported by the passage**. A model can land the
right span for the wrong reason (copy the year that appears in an unrelated
sentence), and the current reading-400 numbers cannot tell. The plan
(`docs/metrics-plan-3-nhom.md` group 2.2) marks this the remaining group-2
measurement and sets an honest stop: the judge instrument must be validated on
human labels first, or the faithfulness number is meaningless and the line of
work stops there.

## What Changes

- **New condition** on `Qwen3.5-9B-65K` @ IEC: reading-400 answered with a
  **verbatim citation** of the supporting passage text (new prompt, bytes
  pre-registered; the frozen `build_reading_prompt` / `score_reading_eval.py`
  stay untouched). New runner `run_reading_cite_eval.py`, output slug
  `Qwen3_5-9B-65K-cite` — a distinct condition, never mixed with MC-31's
  reading-400 row.
- **New judge tool** `judge_faithfulness.py`: a pre-registered judge prompt
  (structured JSON verdict) scored through an OpenAI-compatible endpoint.
  Judge model is disclosed per run; recommended primary is `MiMo V2.5` via
  OpenCode Zen Go (independent family — not the model under test), with
  `Qwen3.5-9B-65K` via IEC as a fallback carrying an explicit self-judge
  caveat.
- **Judge validation gate** (the plan's stop condition): ~60 human-labeled
  items (pre-registered sampling rule, seed 42) before any full judge pass;
  proceed only if raw agreement ≥ 80% **and** Cohen's κ ≥ 0.6. One documented
  judge-prompt iteration allowed; failing that, stop and publish the negative
  instrument result instead of a faithfulness score.
- **Metrics** (definitions frozen before the run): compliance rate (both
  fields parsed), EM/char-F1 on the answer field via the frozen scorer,
  mechanical verbatim-citation rate (citation ⊆ context, no judge needed),
  judge-supported rate, and the joint `correct ∧ supported`; a cross-tab
  separates "right answer, unsupported citation" from "wrong answer, supported
  citation".
- **Cards**: MC-37 (pre-register, before any model call) and MC-38 (results +
  gate decision).

## Capabilities

### New Capabilities
- `faithfulness-eval`: the citation-condition contract (new prompt pinned, new
  label namespace, frozen scorer untouched), the validated-judge contract
  (validation before scoring, pre-registered gate, negative-result path), and
  the mechanical-vs-semantic metric separation.

### Modified Capabilities
<!-- none: eval-scoring, the frozen reading prompt/scorer, and every existing
     reading condition keep their bytes and their rows -->

## Impact

- New: `code_benchmark/run_reading_cite_eval.py`, `code_benchmark/judge_faithfulness.py`
  (run + validate subcommands), `code_benchmark/test_suite.py` (offline tests),
  `measurement_card.md` (MC-37 + MC-38), `docs/model-insights.md` (§1.5 on
  results), per-item artifacts under `all_res/ollama_result/<slug>/`.
- Untouched: `run_reading_eval.py` (verified byte-identical by diff),
  `score_reading_eval.py`, `data/eval_set_manifest.csv`, the MC-31 65K row.
- Endpoints: IEC internal (answers) + judge endpoint disclosed per card
  (MiMo/Zen Go or IEC). Preflight before each live step; `--resume` never
  crosses conditions or judge models.
- Optional follow-on (not gated here): a curated `/results` insight seed for
  `reading-400 × qwen3-5-9b-65k` once MC-38 exists.

## Non-goals

- No ViHallu / hallucination benchmark (group 4 gap — stays a documented gap).
- No safety rows, no new base model, no prompt change to any existing card.
- No "faithfulness" claim without the human validation gate — the instrument
  failure itself is the publishable outcome if the gate fails.
- No second citation format, no multi-citation parsing: one answer + one
  citation, or the item is counted unparsed.
