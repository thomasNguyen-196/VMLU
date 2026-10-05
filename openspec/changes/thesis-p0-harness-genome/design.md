# Design: P0 — harness genome, guard, evidence bundles

## Context

The repo's "harness conditions" are long invocations, e.g.

```
run_harness_eval.py run --dataset legal_mc --label ompH5clean_Qwen3_5-9B-28K \
    --tools none --system-prompt minimal --agent-dir .omp-clean
```

That is a condition, but it is not an *object*: it cannot be hashed, stored,
crossovered, or checked against the frozen surface. Every arm card in
`measurement_card.md` documents the same facts in prose, which is why the arms are
auditable but not programmatically comparable.

## Decisions

### D1 — Genome shape: nested like the plan, flattened inside the dataclass
The plan's §4 JSON is nested (`fewshot: {k, selection}`, `resources: {...}`).
`Genome` keeps it nested in `to_dict()` — the plan's JSON is the on-disk
contract — but flattens those leaves into typed dataclass fields so an invalid
combination (elicitation `fewshot_k` with `k=0`) is unrepresentable rather than
merely rejected. Frozen dataclass: a genome is a value, not a thing you edit in
place.

### D2 — Enums are closed, and the guard is fail-fast
Unknown group ⇒ `SystemExit`. Out-of-enum ⇒ `SystemExit`. Never coerce, never
default, never drop the field: a silent default is how a mutation becomes an
unnoticed condition change. Matches the repo's fail-fast doctrine.

### D3 — The frozen surface is a *closed registry + fingerprint*, not a deny-list alone
A deny-list on key names is trivially evaded (`template_id: "extract_answer_v2"`).
So the real defence is positive:

1. `TEMPLATE_IDS` — the only legal prompt builders, each mapped to its
   byte-frozen function. A new template must be added here with its card.
2. Per-template `max_tokens_ceiling` — **derived from measured runner defaults**,
   not invented: `mc_frozen` 4 (`run_mc_eval.add_endpoint_args`), `reading_frozen`
   48 (`run_reading_eval.add_endpoint_args`), `vbench_mc` 64 (the guided-ask
   budget, `run_vbench_eval.py:864`), `vbench_agentic` 512
   (`run_vbench_eval.py:701`). Exceeding a ceiling is the concrete reward-hack
   this catches: a larger budget lets an MC model write a rationale whose *last*
   letter the byte-frozen parser might then read — accuracy up, capability flat.
   V-Bench templates carry no ceiling (their budget is a resource gene, not a
   frozen contract) but are capped at 512 by `MAX_TOKENS_HARD_CAP`.
3. `frozen_fingerprints()` — sha256 of `inspect.getsource` of `build_prompt`,
   `extract_answer` and `_validate_call`. Recorded in every evidence bundle, so a
   lineage that quietly edited the parser is visible in the artifacts.

`DENY_KEYS` and the value-shape check remain as a second net: no string value may
contain a path separator, a newline, or `def `/`import ` — a config value is a
config value, not a place to smuggle code.

### D4 — `tools` is a reviewed menu, never synthesized (§7)
`TOOL_MENU` is the closed set from the plan (`none`, `calculator`, `date_arith`,
`enum_verbatim_lookup`). `"none"` must appear alone — `"none"` beside `calculator`
is a contradiction that would otherwise resolve silently in one direction.
Synthesis (free codegen) stays P4 and would need the sandbox.

### D5 — Declarations, not silent flags
Some genomes make a run a *different kind of measurement* even though they are
valid: `guided_fallback=true` is a third elicitation condition (it must never be
pooled with the first two); `temperature>0` makes the run non-deterministic (and
MC-44 just measured how little that matters at temp 0 — a temp>0 arm needs its
own repeatability floor); `samples_per_item>1` reports a vote, not an answer;
`option_order=seed_shuffle` needs the seed recorded, because MC-36 measured that
option order is a variance source and an unreproducible shuffle is uninterpretable.
`required_declarations()` returns these as card text; the caller prints them and
the pre-registration card carries them.

### D6 — Evidence bundles *link* artifacts, never copy or move them
`collect_evidence()` writes `genome.json`, `frozen_fingerprints.json`,
`harness.diff`, `budget.json`, `manifest.json` and a `README.md` into
`all_res/evidence/<genome_id>/`, and **references** the arm's existing CSVs by
path (repo convention: results stay in `all_res/ollama_result/<slug>/`, gitignored
per-model). Copying would create a second source of truth; the repo has already
been bitten by exactly that (the review blob vs the static fallback). `genome.diff`
is empty and `code_changed=false` for a config-only mutation — an honest empty,
because most mutations *should* be config-only.

`genome_id` = `sha256` over the canonical JSON (sorted keys, no whitespace),
truncated — so two candidates that differ anywhere get different ids, and the
evidence folder name is the identity.

## Risks

| Risk | Mitigation |
|---|---|
| The genome becomes a second way to spell a measurement, drifting from the CLI | the genome stores only values the CLI already takes; P1 maps gene → flag and the mapping table is part of P1, not of P0 |
| Fingerprint churn from unrelated edits | hashes are over function source, not file source; recorded per candidate so a change is *visible*, and a diff in the bundle is the signal |
| `MAX_TOKENS_HARD_CAP` looks arbitrary | it is the plan's own `resources.max_tokens: 512` genome default, applied as the outer bound; per-template ceilings are cited to their runner line |
| Guard drift from the plan | every enum in `harness_genome.py` cites the §4/§7 line it encodes; changing the plan means changing the file on purpose |
| No seed runs in this change | stated in the proposal's non-goals; seeds ship as genomes to be run under their own card |