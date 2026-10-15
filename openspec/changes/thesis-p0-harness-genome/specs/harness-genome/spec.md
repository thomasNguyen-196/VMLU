## Purpose

Defines the harness genome: the closed, hash-addressed set of genes that makes a
benchmark condition a value rather than a hand-typed command line, together with
the guard that keeps an evolutionary loop from escaping the frozen surface.

## Requirements

### Requirement: A genome is a closed, typed, hash-addressed object
The genome SHALL cover exactly the eight gene groups of the thesis plan's §4 —
`elicitation`, `fewshot`, `option_order`, `answer_format`, `rag`, `tools`,
`resources`, `agentic_extra` — SHALL reject any unknown group, and SHALL expose a
`genome_id` derived from a canonical JSON serialization so that two candidates
differing anywhere receive different identities.

#### Scenario: Valid minimal genome
- **WHEN** a genome declares `elicitation=zero_shot_minimal`, `fewshot.k=0`,
  `option_order=as_is`, a registered `template_id`, `rag.mode=off`,
  `tools=["none"]`, `temperature=0` and `samples_per_item=1`
- **THEN** it validates and its `genome_id` is stable across serialization
  round-trips.

#### Scenario: Unknown gene group
- **WHEN** a genome carries a ninth group
- **THEN** validation fails fast — an unreviewed gene is an escape hatch, not a
  default.

#### Scenario: Value outside the closed enum
- **WHEN** `elicitation` is `chain_of_thought_v2`
- **THEN** validation fails fast rather than coercing it.

### Requirement: The prompt builder is a closed registry, never a name in a string
`template_id` SHALL resolve to an entry in a closed registry that names the
byte-frozen builder, and each entry SHALL declare the token ceiling measured from
the runner that owns it. A genome SHALL NOT be able to raise the token budget past
that ceiling, and a genome SHALL be rejected if any string value looks like a
filesystem path or a code fragment.

#### Scenario: MC token ceiling
- **WHEN** a genome uses the MC template with `max_tokens=4` (the frozen letter
  budget)
- **THEN** it validates; with `max_tokens=64` it fails fast, because a longer
  budget lets the model write a rationale whose last letter the byte-frozen
  parser could read — score up, capability flat.

#### Scenario: Smuggled code
- **WHEN** a genome's `template_id` is `"/etc/passwd"` or a value contains
  `import `
- **THEN** validation fails fast.

### Requirement: The tool menu is pre-written and reviewed
`tools` SHALL be a subset of the plan's §7 pre-written menu, and the sentinel
`none` SHALL be the only entry when present.

#### Scenario: Contradictory tool list
- **WHEN** `tools` is `["none", "calculator"]`
- **THEN** validation fails fast instead of silently dropping one.

### Requirement: The frozen surface is fingerprinted, not just promised
Every evidence bundle SHALL record a sha256 fingerprint of the byte-frozen
`build_prompt`, `extract_answer` and the agentic validator, so that a candidate
which edited the parser is detectable from its own artifacts.

#### Scenario: Same scorer across a lineage
- **WHEN** two candidates share one fingerprint
- **THEN** their scores are comparable, and the bundle is the evidence for that.

#### Scenario: Parser edited mid-lineage
- **WHEN** a candidate's fingerprint differs from its parent's
- **THEN** the bundle shows the divergence and the lineage is not comparable.

### Requirement: Conditions that change what is measured must declare it
A genome SHALL surface, as required pre-registration text, every condition that
makes a run a different kind of measurement: a guided fallback (a third
elicitation condition), non-zero temperature (non-deterministic), multiple samples
per item (a vote, not an answer), and a shuffled option order (whose seed must be
recorded).

#### Scenario: Guided fallback seed
- **WHEN** `agentic_extra.guided_fallback` is true
- **THEN** `required_declarations()` states that the arm is a third elicitation
  condition and must not be pooled with the other two.

#### Scenario: Shuffled options without a seed
- **WHEN** `option_order` is `seed_shuffle` and no `shuffle_seed` is given
- **THEN** validation fails fast.

### Requirement: Every candidate ships an evidence bundle
`collect_evidence()` SHALL write a bundle containing the canonical genome, the
frozen fingerprints, the harness diff, the budget, a manifest naming the result
and ledger CSVs **by path** (never copies them), and a reproduce command.

#### Scenario: Config-only candidate
- **WHEN** a mutation changes only genome values
- **THEN** the bundle's diff is empty and `code_changed` is `false` — an honest
  empty, since most mutations should be config-only.

#### Scenario: Two conditions with identical genes but different scaffolds
- **WHEN** a direct call and a scaffolded run carry the same gene values
- **THEN** their bundles are named `<container>__<genome_id>` and differ, because
  the gene grammar cannot express "is the prompt scaffolded at all" — the largest
  measured variance source — and one folder per identity must not be shared by two
  conditions.

#### Scenario: Missing artifacts
- **WHEN** a named results CSV does not exist
- **THEN** the bundle write fails fast rather than recording a bundle that points
  at nothing.