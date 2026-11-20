## Purpose

Test whether omp's default system prompt carries the model × harness interaction found by MC-112 to MC-116 (omp below dsh with Qwen3.5-9B, above dsh with MiMo-V2.6-Flash). Each model runs an omp arm whose only change is dsh's system prompt in place of omp's default prompt body, on MC-115's 646 items, two draws. The result is compared with the registered OMPF and DSHF score files. The registration is fixed before the first request.

## ADDED Requirements

### Requirement: Same tasks as MC-115's OMPF
Every MC-117 attempt SHALL send the task of MC-115's OMPF draw-1 item for the same item, with replicate id `OMPS-r1` or `OMPS-r2` and no other change. The build SHALL fail when any attempt's task, input, gold or task kind differs from MC-115's manifest, or when an item is missing.

#### Scenario: Counts
- **WHEN** the manifest is built
- **THEN** it holds 646 items and, per model, 1,292 OMPS attempts at draws 1 and 2

### Requirement: OMPS differs from OMPF only in the system prompt
For each model, OMPS SHALL run that model's registered OMPF specification (MC-113's for Qwen, MC-116's for MiMo) with `--system-prompt` set to dsh's system prompt for that model, read from a file by its registered SHA-256. Nothing else in the specification SHALL change.

#### Scenario: A changed prompt file
- **WHEN** a prompt file does not hash as registered
- **THEN** the specification fails to load and no request is sent

#### Scenario: omp sends another system message
- **WHEN** an attempt's first request carries a system message whose SHA-256 differs from the model's pin set by the smoke test
- **THEN** the proxy refuses it before forwarding and the run pauses

### Requirement: Routes as in MC-115 and MC-116
Qwen attempts SHALL use MC-115's route: IEC `Qwen3.5-9B-65K` through the VPN, cap 4,096. MiMo attempts SHALL use MC-116's route: OpenCode Go `mimo-v2.6-flash`, one session per try, cap 16,000. Both SHALL use temperature 1.0, a request cap of 30, a 65,024-token context window and a response-model pin.

#### Scenario: Another model answers
- **WHEN** a response names a model other than the pin
- **THEN** the attempt is fatal and the run halts

### Requirement: Halted rows keep their identity
A row written without a request (`halted_before_send`, `budget_cap`, `endpoint_unresponsive`) SHALL carry its run key, shard, lane, model id, protocol id, profile id and card id. A halt SHALL pause the run without an exception, and `--resume` SHALL load the row.

#### Scenario: A halt with attempts in flight
- **WHEN** a fatal attempt halts the run while other attempts are in flight
- **THEN** every in-flight attempt's row is written to the ledger and the run ends paused

### Requirement: A stalled stream is technical
A proxied stream that ends with no chunk naming a model SHALL be recorded as `network` with error type `stream_stalled`, not as `model_drift`. An attempt that ends without an answer after such a request SHALL be technical and re-run by `--resume`.

#### Scenario: A stall that the harness recovers from
- **WHEN** a request stalls and omp re-sends it and reaches a final answer
- **THEN** the attempt is complete and scored, and the stall is counted in the run record

### Requirement: Smoke test before registration
Before registration, and only with the owner's go, the runner SHALL run MC-112's `smoke-2` and MC-114's `smoke-s2` once with OMPS per model. It SHALL record statuses, body keys, response models, the first system message's SHA-256 and tokens. No benchmark item SHALL be sent.

#### Scenario: A smoke attempt fails
- **WHEN** a smoke attempt does not complete
- **THEN** registration is blocked until the owner decides

### Requirement: Registered tests
The analysis SHALL run once, after both runs are final. The item score SHALL be the mean over draws 1–2. Per part it SHALL test P1 (Qwen OMPS − OMPF), P2 (MiMo OMPS − OMPF) and P3 (per item, MiMo's OMPS − OMPF minus Qwen's), with Holm over the three, margin 2.24 on Part M and none on Part S.

#### Scenario: Reading P3
- **WHEN** P3 on Part S is −6.0 points with a Holm-adjusted p of 0.003
- **THEN** the report says omp's default prompt carries part of the interaction on Part S

### Requirement: Comparators by hash
OMPF and DSHF scores SHALL be read from MC-112's, MC-113's, MC-114's and MC-116's score files at their registered SHA-256. The analysis SHALL fail when a file differs or an item lacks a draw.

#### Scenario: A comparator changed
- **WHEN** MC-116's score file no longer hashes as registered
- **THEN** the analysis fails and writes no report

### Requirement: Action flows are kept and summarised
Every attempt SHALL keep the harness's event stream and the proxy's request records. `harness_flow.py`, registered by SHA-256, SHALL turn both into one timeline per attempt, separating model actions, what the harness showed back, and actions the harness took on its own. The report SHALL summarise them per model and arm, without tests.

#### Scenario: A compaction before the answer
- **WHEN** omp compacts the context and the model answers after the compaction
- **THEN** the attempt's flow records the compaction, its summary's size and language, and that the answer followed it

### Requirement: Registration
MC-117 SHALL be registered by a commit titled `pre-register MC-117` before the first benchmark-item request of either model. The commit SHALL add the root block, the detail card and `registration.json` with every frozen input's SHA-256. The runner's gates SHALL refuse to run without them.

#### Scenario: Unregistered run
- **WHEN** `--execute` is given and `measurement_card.md` has no MC-117 heading
- **THEN** the gates fail and no request is sent
