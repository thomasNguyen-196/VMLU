## Purpose

Defines how the prospective B/S/O/K/KS diagnostic campaign is constructed, gated and executed so that every attempt traces to a frozen manifest, a frozen prompt set and a pre-registered measurement card.

## ADDED Requirements

### Requirement: Arm-aware frozen manifests
The campaign SHALL derive two manifests from the frozen main-v1 manifest: `core`, the 60 audit anchors bound to the locked pilot content hash, and `wide`, the remaining items of the five non-VMLU datasets. Every attempt SHALL have the identity `dataset_id:item_id:replicate_id` with `replicate_id` of the form `<ARM>-r<k>`. Each manifest row SHALL carry the SHA-256 of the arm-specific prompt, and rows SHALL be ordered item-major so that the arms and replicates of one item are scheduled adjacently.

#### Scenario: Core and wide partition the MC-72 scope
- **WHEN** both manifests are built from main-v1 and the locked pilot packet
- **THEN** no item appears in both and together they contain exactly 1,299 distinct items across five datasets

#### Scenario: Baseline arm reuses the frozen prompt
- **WHEN** the B-arm prompt of any item is built
- **THEN** its SHA-256 equals the prompt hash recorded for that item in main-v1

#### Scenario: Unexpected prompt skeleton fails closed
- **WHEN** a frozen prompt lacks the expected multiple-choice or reading head or tail
- **THEN** arm-prompt construction exits with an error naming the item and no manifest is produced

### Requirement: Preflight by default
The runner SHALL send no request unless `--execute` is passed. Without it the runner SHALL validate inputs, hashes and counts and report `endpoint_calls=0`.

#### Scenario: Preflight sends nothing
- **WHEN** the runner is started without `--execute`
- **THEN** it prints the item, arm and attempt counts, reports `endpoint_calls=0` and performs no network access

### Requirement: Fail-closed execution gates
With `--execute` the runner SHALL refuse to start unless all of these hold: the campaign's measurement-card heading exists in `measurement_card.md` and its detail card file exists; the configured endpoint root host and model id equal those named by the card; the manifest, prompt-template and evidence hashes equal the frozen values; and, for the `core` phase, the diagnostic readiness report states `inference_ready` true and the router rule file exists with the SHA-256 recorded in the core registration entry.

#### Scenario: Unregistered campaign cannot run
- **WHEN** `--execute` is passed and the card heading is absent from `measurement_card.md`
- **THEN** the runner exits before any request and states which gate failed

#### Scenario: Core waits for the audit
- **WHEN** `--execute` is passed for `core` while `inference_ready` is false
- **THEN** the runner exits before any request and lists the readiness blockers

#### Scenario: Core waits for a frozen router rule
- **WHEN** `--execute` is passed for `core` and the router rule file is missing or its SHA-256 differs from the core registration entry
- **THEN** the runner exits before any request and states which gate failed

### Requirement: Frozen condition and resumable runs
The runner SHALL write a `condition.json` before the first request containing model, endpoint host, transport, sampling, caps, prompt-template, manifest, evidence, scorer and runner hashes. A resumed run SHALL proceed only when every inference setting is unchanged. Completed attempts, including truncated or unparsed ones, SHALL NOT be retried automatically.

#### Scenario: Changed setting blocks resume
- **WHEN** `--resume` is passed and the output cap differs from the frozen condition
- **THEN** the runner exits without sending a request

### Requirement: Process-local endpoint resolution
When the endpoint host does not resolve through the system resolver, the runner SHALL support resolving it through a named in-tunnel DNS server for its own process only, and SHALL NOT modify the system resolver, the hosts file or the network configuration.

#### Scenario: Shim changes nothing outside the process
- **WHEN** the resolver shim is enabled
- **THEN** only name lookups for the configured endpoint host inside the runner process are redirected and the HTTP `Host` header remains the configured host

### Requirement: Usage accounting and budget guard
Each attempt row SHALL record the usage the endpoint reports, and absent fields SHALL be recorded as unknown rather than zero. Every request SHALL use the registered per-attempt output cap, and the runner SHALL pause without sending further requests when cumulative reported tokens exceed the registered campaign cap.

#### Scenario: Missing usage is unknown
- **WHEN** an endpoint response lacks a reasoning-token count
- **THEN** the attempt row stores null for it and summaries count it as not reported

#### Scenario: Campaign cap pauses the run
- **WHEN** cumulative reported tokens exceed the campaign cap
- **THEN** the runner records a budget pause, sends no further request and keeps completed attempts intact

### Requirement: Opt-in operational guards
The runner SHALL offer two operational options that are off by default so the registered condition is what runs unless an operator asks otherwise: a cap on simultaneous requests below the registered lane count, and a circuit breaker that pauses the run after a configured number of consecutive network-level failures. Every launch SHALL append a record of the options used, the lane count and the runner hash to an operator event file next to the run outputs, and neither option SHALL change the frozen condition or the content of any request.

#### Scenario: Registered path unchanged
- **WHEN** the runner is launched without the options
- **THEN** every registered lane sends requests as before and a series of timeouts never stops the run by itself

#### Scenario: Breaker pauses an unresponsive endpoint
- **WHEN** the configured number of consecutive requests fail with timeouts or connection errors and no request succeeds in between
- **THEN** the next request is recorded as a fatal endpoint-unresponsive row without being sent, the engine pauses and every incomplete item stays resumable

#### Scenario: Cap bounds simultaneous requests
- **WHEN** a cap of three is set with twelve lanes active
- **THEN** no more than three requests are in flight at any time and waiting for a free slot is not counted in the recorded latency

#### Scenario: Launch is recorded
- **WHEN** a run is launched or resumed with or without the options
- **THEN** one line is appended to the operator event file and earlier lines are never rewritten

### Requirement: Registered supplements
A supplement SHALL re-run arms of an already registered phase under further replicate numbers without changing the campaign protocol, the prompt templates or any registered manifest. It SHALL have its own entry in the registration record (base phase, arms, replicate numbers, card, manifest hash, registered operational limits), its own measurement card and its own output directory; it SHALL add no arm, evidence or item and SHALL NOT reuse a replicate number registered for its base phase. The operational limits it registers SHALL be part of its frozen condition.

#### Scenario: Supplement manifest reuses frozen prompts
- **WHEN** a supplement re-runs arm B of the wide phase as replicate 2
- **THEN** every row carries the prompt, input and gold hashes of replicate 1 of that arm under a different replicate id, and the manifest of the registered phase is unchanged

#### Scenario: Colliding replicate numbers are refused
- **WHEN** a supplement names a replicate number already registered for its base phase
- **THEN** the manifest cannot be built and the error names the supplement

#### Scenario: Registered limits cannot be loosened
- **WHEN** a supplement registers a cap of four simultaneous requests and a launch asks for another value, or a resume would change the registered limits
- **THEN** the launch or the resume is refused
