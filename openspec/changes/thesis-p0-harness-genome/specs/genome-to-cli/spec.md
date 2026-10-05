## Purpose

Defines the mapping from a genome to a runnable command, and the support matrix that
says which genes a runner can actually express today.

## Requirements

### Requirement: A gene with no runner is an error, not a dropped flag
`plan()` SHALL fail fast when the genome asks for a gene the chosen runner cannot
express, naming the gene and stating that the run must not be labelled with a
condition it did not apply. It SHALL NOT silently omit the gene.

#### Scenario: Genome asks for chain-of-thought
- **WHEN** a genome declares `elicitation=cot`
- **THEN** planning fails and names `elicitation=cot` as unsupported.

#### Scenario: Genome asks for a named tool
- **WHEN** a genome declares `tools=["calculator"]` and the runner is the harness
- **THEN** planning fails, and the message lists the menu that **does** exist, so the
  reader can see what is available instead.

#### Scenario: Runnable genome
- **WHEN** a genome uses only implemented or routed genes
- **THEN** planning succeeds and emits the flags that produce the condition.

### Requirement: An external mechanism is a precondition, not a blocker
A gene that requires a mechanism outside the runner — such as the harness having no
`--temperature` flag, so determinism is pinned by a localhost proxy — SHALL be
reported as an external precondition and SHALL NOT block planning. It SHALL be
surfaced in the command output as something the caller must set up and disclose.

#### Scenario: Harness and temperature 0
- **WHEN** a genome with `temperature=0` is planned for the harness
- **THEN** the status is `external`, the mechanism names the pinning proxy, the emitted
  command contains no `--temperature`, and the output lists the proxy as a
  precondition.

#### Scenario: Direct runner and temperature 0
- **WHEN** the same genome is planned for the MC runner
- **THEN** the status is `implemented` and the command contains `--temperature`.

### Requirement: The support matrix reports the whole grammar
`support_matrix()` SHALL cover every gene group and every value in the grammar,
assigning each a status from a closed vocabulary, and SHALL work both for a specific
genome and for the whole grammar.

#### Scenario: A planned tool that does not exist
- **WHEN** the whole grammar is printed
- **THEN** `calculator`, `date_arith` and `enum_verbatim_lookup` are reported
  `unsupported`, while `none` and `all` are `implemented`.

#### Scenario: A gene in the grammar with no flag anywhere
- **WHEN** the matrix is printed for the whole grammar
- **THEN** `cot`, `fewshot_k`, every non-`off` retrieval mode and
  `samples_per_item > 1` are reported `unsupported` — that is the finding, not a
  defect of the table.

### Requirement: The seeds must be executable
Both named seed genomes SHALL plan successfully against the harness runner. A seed
that validates but cannot be executed reintroduces the failure the genome exists to
remove, and the baseline seed SHALL encode a **measured** arm rather than a
speculative one.

#### Scenario: Baseline seed
- **WHEN** the baseline seed is inspected
- **THEN** it carries the tool menu that was actually measured, no retrieval, one
  sample and temperature zero — a configuration that exists in this repo's artifacts.