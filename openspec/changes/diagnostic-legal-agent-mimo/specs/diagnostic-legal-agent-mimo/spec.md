## Purpose

Test whether the harness gap that MC-112 to MC-115 found with Qwen3.5-9B (omp below dsh, same model, folder and task) holds with a second model, MiMo-V2.6-Flash, by running MC-115's forced-search agent arms and no-tool baselines on the same 646 items and folders, two draws, with only the model route changed. The registration is fixed before the first request.

## ADDED Requirements

### Requirement: Same tasks as MC-115
Every MC-116 attempt SHALL send the task of its arm's draw-1 item as MC-115 copied it, with replicate id `-r1` or `-r2` and no other change. The build SHALL fail when any attempt's task, input, gold or task kind differs from MC-115's manifest for the same item and arm, or when an MC-115 item and arm is missing.

#### Scenario: A task drifted
- **WHEN** a rebuilt attempt's prompt SHA-256 differs from MC-115's for the same item and arm
- **THEN** the manifest build fails and no manifest is written

#### Scenario: Counts
- **WHEN** the manifest is built
- **THEN** it holds 646 items and 3,876 attempts: DSHF 1,292, OMPF 1,292, B 492, C 800, at draws 1 and 2

### Requirement: Same folders as MC-115
Agent attempts on `vi-multimodel-v1-legal-mc-146` SHALL run on corpus_v1 and every other agent attempt on corpus_v2. The runner SHALL refuse to run when either folder's listing SHA-256 differs from the registration.

#### Scenario: A folder changed
- **WHEN** corpus_v1's or corpus_v2's listing hash differs from the registered one
- **THEN** the preflight gate fails and no request is sent

### Requirement: Harness specifications differ only in the model route
The dsh and omp specifications SHALL be MC-112's and MC-113's protocols, each read by its registered SHA-256, with only the model route replaced: MC-116's dsh profile and omp configuration (each read by its registered SHA-256), omp's model argument, a per-response cap of 16,000 tokens, omp's request shape and system-prompt hash, and the proxy's timeout and response-model pin.

#### Scenario: A changed profile
- **WHEN** the dsh profile or the omp configuration does not hash as registered
- **THEN** the harness specification fails to load and no request is sent

#### Scenario: omp sends another shape
- **WHEN** an omp request carries a key outside the registered set, a cap other than 16,000 with tools, or a first system prompt with another SHA-256
- **THEN** the proxy refuses it before forwarding and the run pauses

### Requirement: Context window and routing session
The context window declared to both harnesses SHALL stay 65,024 tokens. The proxy SHALL forward to OpenCode Go with the registered headers and one `x-opencode-session` per try of an attempt; a direct attempt SHALL use one session.

#### Scenario: A re-run attempt
- **WHEN** `--resume` re-runs an agent attempt as its second try
- **THEN** its requests carry a session id different from the first try's

### Requirement: Provider errors read for OpenCode Go
An attempt that ends on an HTTP 429, 401, 402, 403 or 404 from the provider SHALL be technical and SHALL halt the launch. An HTTP 400 whose error names no content policy SHALL be technical; more than 20 attempts with one SHALL halt the run. An HTTP 400 naming a content policy SHALL be terminal and scored 0.

#### Scenario: Usage limit
- **WHEN** a request of an agent attempt gets HTTP 429 from OpenCode Go and the attempt ends without an answer
- **THEN** the attempt is recorded as a technical failure, the launch halts, and the attempt is not scored

#### Scenario: Policy refusal
- **WHEN** a direct request gets HTTP 400 with the code `content_policy_violation`
- **THEN** the attempt is complete with outcome `upstream_4xx` and scores 0

### Requirement: Smoke test before registration
Before registration, and only with the owner's go, the runner SHALL run MC-112's `smoke-2` on corpus_v1 and MC-114's `smoke-s2` on corpus_v2, each once with DSHF, OMPF and its direct arm, and record statuses, body keys, response model ids, omp's system-prompt hash and tokens. No benchmark item SHALL be sent.

#### Scenario: omp's system prompt differs
- **WHEN** an omp smoke attempt's first request carries a system prompt other than the registered one
- **THEN** the report records the mismatch and the `smoke_passed` gate fails

### Requirement: Pins and budget come from the smoke test
A smoke attempt that does not complete SHALL block registration. The response-model pins of dsh, omp and the direct arms and the budget guard SHALL be set from the smoke report before registration.

#### Scenario: A pin is unset
- **WHEN** `--execute` is given and any response-model pin is null
- **THEN** the `pins_set` gate fails and no request is sent

### Requirement: Registered two-draw tests
The analysis SHALL run once after every attempt is final and SHALL fail when an item lacks a draw of a compared arm. The item score SHALL be the mean over draws 1–2. It SHALL test M1 (OMPF vs DSHF) and M2 (DSHF vs B) on 246 Part M items, Holm over the two, margin 2.24 points; and S1 (OMPF vs DSHF) and S2 (DSHF vs C) on 400 Part S items, Holm over the two, no margin.

#### Scenario: Reading rule
- **WHEN** M1's mean difference is −6.0 points with a Holm-adjusted p of 0.004
- **THEN** the report says OMPF is worse than DSHF

### Requirement: Statistics and the Qwen comparison
Each test SHALL report the mean per-item difference, a 95% percentile bootstrap (2,000 resamples, seed 7) and a two-sided paired sign-flip p-value (20,000 resamples, seed 7). Qwen's same comparisons on the same items, read from the registered score files by SHA-256, and the per-item model difference in the harness gap SHALL be reported beside, without tests.

#### Scenario: A Qwen score file changed
- **WHEN** a registered Qwen score file no longer hashes as registered
- **THEN** the analysis fails and writes no report

### Requirement: Registration
MC-116 SHALL be registered before the first benchmark-item request by a commit titled `pre-register MC-116` that adds the root block in `measurement_card.md`, the detail card and `registration.json` with every frozen input's SHA-256. The runner's gates SHALL refuse to run when the card is missing or a registered hash differs.

#### Scenario: Unregistered run
- **WHEN** `--execute` is given and the measurement card has no MC-116 heading
- **THEN** the gates fail and no request is sent
