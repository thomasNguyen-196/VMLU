# Proposal: P0 — harness genome spec, guard, and evidence bundles (thesis RQ2/RQ4)

## Why

`docs/harness-evolution-thesis-plan.md` §9 makes P0 the first milestone:

> `harness_genome.py` spec + guard tests; evidence-folder writer; baseline +
> oracle-condition runs (minimal/detailed already exist as seeds).

The measurements P1–P4 depend on are already in this repo (MC-15…MC-23, MC-30,
MC-36, MC-44), but they were produced by **hand-typed CLI invocations**. There is
no object that names "the harness", so three of the four research questions are
currently unreachable:

- **RQ2** cannot mutate or recombine anything — `--tools` and `--system-prompt`
  are flags, so a crossover (elicitation from candidate A × tools from candidate
  B) has no representation.
- **RQ3** cannot state what "this harness" transfers, because there is no single
  artifact to transfer.
- **RQ4**'s strongest invariant ("a mutation touching the scorer disqualifies the
  lineage", §3.1) has **nothing to disqualify** — there is no mutation, so the
  honesty claim is currently a promise rather than a check.

## What Changes

- New `code_benchmark/harness_genome.py` — stdlib-only:
  - `Genome`: a frozen, typed, hash-addressed representation of the 8 gene
    groups in thesis-plan §4, with `from_dict` / `to_dict` / `genome_id`.
  - `validate()`: fail-fast on an unknown gene group, an out-of-enum value, a
    `tools` list that is not a subset of the pre-written reviewed menu (§7), a
    `fewshot.k` inconsistent with its elicitation, `"none"` mixed with real
    tools, a missing `shuffle_seed` for `seed_shuffle`, and any string value that
    looks like a path or a code fragment (the smuggling route around the closed
    grammar).
  - The frozen-surface guard: `TEMPLATE_IDS` is a **closed registry** of
    byte-frozen prompt builders, per-template **token ceilings**, and
    `frozen_fingerprints()` — sha256 over the source of `build_prompt`,
    `extract_answer` and `_validate_call`, so a candidate that edited the parser
    is *detectable* instead of merely forbidden.
  - `required_declarations()`: the card text a condition MUST declare because the
    genome makes it a different kind of measurement (guided fallback = a third
    elicitation condition, `temperature > 0` = non-deterministic, `samples_per_item
    > 1` = a vote, not an answer).
  - `collect_evidence()`: writes the per-candidate evidence bundle of §3.4
    (genome + fingerprint + results + ledger + budget + reproduce command).
- Seeds: `baseline_genome()` and `minimal_genome()` so P1 can start from named,
  hashed genomes instead of from a shell history.
- Tests in `code_benchmark/test_suite.py` — the guard is enforced by CI running
  the suite, which is what "CI-enforceable" (§3) means here.

## Capabilities

### New Capabilities
- `harness-genome`: the closed genome grammar, the frozen-surface guard, the
  declaration requirements, and the evidence-bundle contract.

## Impact

- New: `code_benchmark/harness_genome.py`, `TestHarnessGenome` in
  `code_benchmark/test_suite.py`, this change's specs.
- Untouched: every runner, every frozen contract, every existing card. The genome
  is a **declarative front end** — nothing it describes is executed by it, so no
  existing measurement can move.
- Known gap carried into P1 (recorded, not fixed here): the thesis plan's
  `Qwen3.8-27B-Q4_K_M_gguf` is not the model the endpoint serves today
  (`Qwen3.5-9B-65K`), and the plan's "minimal/detailed already exist as seeds"
  is true only for the V-Bench runner on 28K — hence this change ships
  `minimal_genome()` as a seed to be *run*, not as a run to be reused.

## Non-goals

- No grid search, no evolution loop, no meta-agent (P1–P2).
- No live inference in this change; the seed runs need their own card.
- No sandbox, no codegen tools (§7 defers both).