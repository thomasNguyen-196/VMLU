## Purpose

Define the measurement contract of the `omp` harness arm: how a tool condition is
selected and recorded, which scaffold-isolation guards every measured arm must
pass, how model identity bounds comparability, and what capacity evidence a long
arm needs before it may spend items.

## ADDED Requirements

### Requirement: Three-valued tool condition

The harness runner SHALL accept exactly three tool-condition forms — `none`, an
explicit comma-separated menu, and `all` — and SHALL map them to omp's argv as
follows: `none` → `--no-tools`; an explicit menu → `--tools <menu>`; `all` → the
`--tools` flag is omitted entirely, so omp's own default menu is the condition.
The resolved condition SHALL be recorded with the run's artifacts so that a
consumer can tell which of the three produced a number.

#### Scenario: Default-all resolves to an omitted flag

- **WHEN** a run is launched with `--tools all`
- **THEN** the constructed omp argv contains neither `--tools` nor `--no-tools`,
  and the run's recorded condition reads `all`

#### Scenario: Explicit menu and none keep their old argv

- **WHEN** a run is launched with `--tools read,bash` or `--tools none`
- **THEN** the argv is byte-identical to the pre-change behavior for that form

#### Scenario: Conditions never mix in one cell

- **WHEN** results for the same model and dataset exist under a different tool
  condition
- **THEN** the new run writes to its own condition-tagged artifacts and never
  merges with, or resumes from, the other condition's checkpoints

### Requirement: Model tag identity bounds comparability

Every harness artifact (checkpoint, ledger, comparison, projected answers) SHALL
carry the served model tag it was produced under, and results from different
model tags SHALL NOT be pooled, resumed into, or reported as a single delta. A
model tag change is a new condition requiring its own card.

#### Scenario: New tag, fresh slug

- **WHEN** the same scaffold is run against a newly served model tag
- **THEN** checkpoints and reports are written under slugs derived from that tag,
  and existing checkpoints of the previous tag are neither read nor overwritten

#### Scenario: Cross-tag delta refused

- **WHEN** a comparison is requested between arms whose recorded model tags
  differ
- **THEN** no delta is produced without an explicit new condition and card

### Requirement: Clean-scaffold guards on measured arms

A measured harness arm SHALL run with the scaffold leaks closed and the sampling
knobs pinned: the agent home is overridden so no machine-level append prompt is
injected, the per-item sandbox lies outside every project tree (a sandbox inside
one aborts the run unless explicitly allowed), and provider fields the client
cannot send itself (temperature, and reasoning effort for reasoning models) are
forced by the localhost capture proxy, with every forced field recorded in the
capture file.

#### Scenario: Project instructions in the sandbox abort the run

- **WHEN** a run's sandbox directory sits inside a tree containing
  `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`/`.cursorrules`
- **THEN** the run aborts before the first item unless
  `--allow-project-instructions` is passed

#### Scenario: Pinned fields are auditable

- **WHEN** a measured arm runs through the capture proxy with pinned fields
- **THEN** the capture file records the forced value of each pin and the request
  the arm actually sent

### Requirement: Capacity evidence before long arms

Before an arm whose item count or per-item prompt size makes it long-running
starts spending items, its measurement card SHALL record a live capacity reading
of the endpoint it will use: at least the model's served context limit, prefill
throughput, and decode throughput, plus the request inventory (prompt tokens and
tool-schema size) for the condition being measured. The runner's preflight call
SHALL ask the arm's own endpoint and model, and SHALL abort with a diagnosis that
distinguishes an unanswered endpoint from an HTTP error.

#### Scenario: Long arm without a capacity reading

- **WHEN** a long arm is about to run and its card carries no capacity reading
- **THEN** the run does not start until the reading is taken and recorded

#### Scenario: Preflight failure is named

- **WHEN** the preflight call times out or returns an error status
- **THEN** the run aborts before any item, and the diagnosis says which of the
  two failure classes was observed
