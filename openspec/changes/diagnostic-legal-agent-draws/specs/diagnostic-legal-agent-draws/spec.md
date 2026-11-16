## Purpose

Reduce the draw-to-draw noise of MC-112/113/114's agent comparisons by running two more draws of DSHF, OMPF and each part's no-tool baseline on the same 646 items in their original conditions, and test the harness and each agent against the direct call on 4-draw item means. The registration is fixed before the first request.

## ADDED Requirements

### Requirement: Condition parity with the earlier draws
Every MC-115 attempt SHALL send the exact task bytes of its arm's draw-1 attempt on the same item, through the same harness pins, sandbox, proxy and limits as that attempt. Agent attempts on `vi-multimodel-v1-legal-mc-146` SHALL run on corpus_v1, and agent attempts on every other dataset SHALL run on corpus_v2. The runner SHALL refuse to run when either folder's listing SHA-256 differs from the registration, and SHALL rebuild corpus_v2 in a fresh directory and refuse to run when its hash differs.

#### Scenario: A Legal MC attempt
- **WHEN** the runner starts an agent attempt on a Legal MC item
- **THEN** the sandbox mounts corpus_v1's docs at `/work/van-ban-phap-luat` and the task equals MC-112's DSHF task for that item byte for byte

#### Scenario: A folder changed
- **WHEN** corpus_v1's or corpus_v2's listing hash differs from the registered one
- **THEN** the preflight gate fails and no request is sent

### Requirement: Manifest copied from the frozen manifests
The manifest SHALL be built by rebuilding MC-112's, MC-113's and MC-114's manifests, each of which SHALL equal its frozen file, and by copying each needed draw-1 item to replicate ids `-r3` and `-r4` with no other change. B on the Legal MC items SHALL use the frozen MC prompt whose SHA-256 equals MC-111's B prompt for that item. The manifest SHALL hold 246 Part M items with arms DSHF, OMPF and B, and 400 Part S items with arms DSHF, OMPF and C, at draws 3 and 4 only.

#### Scenario: An earlier manifest drifted
- **WHEN** a rebuilt MC-112, MC-113 or MC-114 manifest differs from its frozen file
- **THEN** the build fails and no manifest is written

#### Scenario: Counts
- **WHEN** the manifest is built
- **THEN** it has 2,584 agent attempts, 492 B attempts and 800 C attempts, and no run key repeats

### Requirement: Smoke test before registration
Before registration, and only with the owner's go, the runner SHALL run MC-112's `smoke-2` on corpus_v1 and MC-114's `smoke-s2` on corpus_v2, each once with DSHF and once with OMPF, and record status, requests, tokens, response model ids and omp's system-prompt hash. No benchmark item SHALL be sent and no score SHALL be computed. A smoke attempt that cannot complete SHALL block registration.

#### Scenario: omp's system prompt changed on this machine
- **WHEN** an omp smoke attempt's first request carries a system prompt other than MC-113's registered one
- **THEN** the smoke report records the mismatch and registration is blocked

### Requirement: Registered four-draw analysis
The analysis SHALL run once after every MC-115 attempt is final. It SHALL read every earlier score file by its registered SHA-256 and SHALL fail when an item lacks any of the 4 draws of a compared arm. The item score SHALL be the mean over draws 1–4. It SHALL test M1 (OMPF vs DSHF), M2 (DSHF vs B) and M3 (OMPF vs B) on the 246 Part M items with Holm over the three, and S1 (OMPF vs DSHF), S2 (DSHF vs C) and S3 (OMPF vs C) on the 400 Part S items with Holm over the three, each with the mean per-item difference, a 95% percentile bootstrap (2,000 resamples, seed 7) and a two-sided paired sign-flip p-value (20,000 resamples, seed 7). The reading rule SHALL use a 2.24-point margin on M1–M3 and none on S1–S3. The same comparisons on draws 3–4 alone and each arm's drift between rounds SHALL be reported beside, without tests.

#### Scenario: A missing draw
- **WHEN** an item lacks DSHF's draw 2 in the earlier score file
- **THEN** the analysis fails and writes no report

#### Scenario: Reading rule
- **WHEN** M2's mean difference is +3.0 points with a Holm-adjusted p of 0.01
- **THEN** the report says DSHF is better than B

### Requirement: Registration
MC-115 SHALL be registered before the first benchmark-item request by a commit titled `pre-register MC-115` that adds the root block in `measurement_card.md`, the detail card and `registration.json` with every frozen input's SHA-256. The runner's gates SHALL refuse to run when any registered hash is missing or changed.

#### Scenario: Unregistered run
- **WHEN** `--execute` is given and the measurement card has no MC-115 heading
- **THEN** the gates fail and no request is sent
