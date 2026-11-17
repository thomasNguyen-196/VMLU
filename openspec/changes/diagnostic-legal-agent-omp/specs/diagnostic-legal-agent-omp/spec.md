## Purpose

Measure whether Qwen3.5-9B, running inside `omp` 18.0.0 with only `read`, `grep` and `glob` over MC-112's complete local folder of Vietnamese legal texts and required to search, finds and reads the provision that governs a Legal MC item more or less often than inside dsh (MC-112's DSHF), and whether its answers differ from DSHF's and from closed-book B's. The registration is fixed before the first request.

## ADDED Requirements

### Requirement: Inputs reused from MC-112
The run SHALL use MC-112's corpus folder, provisions file, prompts file, added and off-site document lists, MC-101 sources and corpus units, MC-100 oracle evidence and MC-111 score file. It SHALL check each of these against its SHA-256 in MC-112's registration. Before any request, the runner SHALL rebuild the folder in a fresh directory, SHALL refuse to run when the folder hash differs, and SHALL run MC-112's provision check against it. The provisions SHALL be read only by the analysis and SHALL never reach a prompt.

#### Scenario: A reused input changed
- **WHEN** any reused input's SHA-256 differs from MC-112's registration
- **THEN** the runner refuses to start and no request is sent

### Requirement: Pinned omp binary and configuration
Each attempt SHALL run the `omp` binary whose SHA-256 is registered, and the binary SHALL report `omp/18.0.0`. Each attempt SHALL run with `-p --mode json --tools read,grep,glob --auto-approve --thinking off --no-title --no-extensions --no-skills --no-rules --no-lsp`, with its session kept in the attempt's fresh home. The registered `config.yml` and `models.yml` SHALL be the only files in its agent directory. The configuration SHALL switch off omp's request retries and its update check. It SHALL pin the IEC provider with model `Qwen3.5-9B-65K`, a context of 65,024 and an answer cap of 4,096 tokens. omp's system prompt, read window, grep output, output spill and compaction SHALL be left as shipped.

#### Scenario: Binary drift
- **WHEN** the binary's SHA-256 or its reported version differs from the registration
- **THEN** the runner refuses to start

### Requirement: Isolated attempt sandbox
Each attempt SHALL run in a sandbox with no network of its own and a fresh home. It SHALL hold the registered agent files and nothing else, and its environment SHALL be empty apart from the registered variables. The sandbox SHALL see only:
- system directories;
- the `omp` binary;
- the relay;
- the proxy's socket;
- its own home;
- the folder, mounted read-only at `/work/van-ban-phap-luat`, which SHALL be the working directory.

No `AGENTS.md`, `APPEND_SYSTEM.md` or rule file SHALL be reachable. The repository, the datasets and the user's home SHALL NOT be visible.

#### Scenario: A second attempt starts
- **WHEN** an attempt starts after another one has finished
- **THEN** it sees none of the earlier attempt's session, configuration, artifacts or files

### Requirement: Proxy with request-shape checks
The proxy SHALL behave as MC-112's proxy: it adds `"temperature": 1.0`, swaps the dummy key, adds the gateway header, records every request and response, applies a 300 s timeout per request and a cap of 30 requests per attempt, and pauses the run on a change of response model id. In addition, it SHALL refuse a request, and pause the run, when:
- the body has a key outside the registered set;
- `max_completion_tokens` exceeds 4096, or differs from 4096 on a request that offers tools;
- on an attempt's first request, the system message's SHA-256 differs from the registered hash;
- on an attempt's first request, the user message's last text part differs from the manifest task.

Once a request of an attempt has failed with a connection error, a timeout or a 5xx, the proxy SHALL refuse every later request of that attempt with 503 and SHALL forward none of them.

#### Scenario: omp retries a gateway failure
- **WHEN** a request gets a 503 and omp sends the same request again
- **THEN** the proxy refuses the retry without forwarding it, and the attempt ends as a technical failure

#### Scenario: Compaction request
- **WHEN** omp's handoff request adds `tool_choice: none`, or its summary request has no tools and a cap of 512
- **THEN** the proxy forwards it, and it counts toward the request cap

#### Scenario: omp sends a new field
- **WHEN** a request body carries a key that the probe and the smoke test did not record
- **THEN** the proxy refuses it before forwarding, the attempt fails without a score, and the run pauses

#### Scenario: Different host
- **WHEN** the system prompt's `<workstation>` block differs from the registered one, so that its hash differs
- **THEN** the first request is refused and the run pauses

### Requirement: Task equals MC-112's DSHF task
The task of each attempt SHALL be MC-112's DSHF task for the same item: the DSHF instruction, a blank line, then the item's frozen main-v1 MC prompt. The manifest SHALL list 268 attempts, item-major, with OMPF-r1 then OMPF-r2 for each item. Each task's SHA-256 SHALL equal the DSHF task hash in MC-112's manifest for that item.

#### Scenario: Prompt rebuild
- **WHEN** a rebuilt task's SHA-256 differs from MC-112's DSHF task hash for its item
- **THEN** the manifest build fails and no request is sent

### Requirement: Attempt statuses and scoring
An attempt SHALL be `complete` when `omp` exits 0 and the last assistant message has stop reason `stop` and a text part. Its answer SHALL be that text, read by the frozen V1 MC extractor and scored by the frozen scorer. These attempts SHALL be terminal without an answer, SHALL count as wrong, and SHALL never be retried:
- `request_cap`;
- `upstream_4xx`;
- `answer_cap`: the last assistant message stopped at the token cap;
- `harness_end`: `omp` ended without an answer, and the proxy saw no upstream failure.

Connection errors, timeouts, gateway 5xx and the wall clock (the runner's kill, or omp's `--max-time`, which ends with stop reason `aborted`) SHALL be technical failures. Only these SHALL be re-run, from scratch, on `--resume`.

#### Scenario: omp stops at the cap
- **WHEN** the last assistant message has stop reason `length`
- **THEN** the attempt is `answer_cap`, it is scored wrong, and resume does not repeat it

### Requirement: Trajectory hit rules for omp results
Hits SHALL be read from the `tool` messages of the request bodies the proxy recorded, each paired with its call by `tool_call_id`.
- **`read` results.** The file SHALL be the base name of the call's `path` without a selector suffix, and only the shown lines SHALL count.
- **`grep` results.** Lines under a `# <file>` header SHALL count, as matches or as context, once their `*<n>|` or ` <n>|` prefix is stripped.
- **Spilled results.** A `read` of `artifact://<k>` SHALL count as a result of the call that spilled it. It counts as a read only if that call was a read.
- **Other paths.** Directory listings, URLs, internal documents and paths outside the folder SHALL count for no provision.

The `seen`, `read` and `opened` rules SHALL be MC-112's, unchanged.

#### Scenario: Elided middle of a whole-file read
- **WHEN** a whole-file `read` shows the head and tail of its window, and the anchor line lies in the elided middle
- **THEN** the attempt is `opened` but not `read` for that provision

#### Scenario: Anchor shown as grep context
- **WHEN** a `grep` result shows the anchor line as a context line of another match
- **THEN** the attempt is `seen` for that provision

### Requirement: Registered analysis
The analysis SHALL run once, after every attempt is final. It SHALL score items by mean correctness over two draws. It SHALL take DSHF's item scores from MC-112's score file, and B's and O's from MC-111's round-1 score file, each by registered SHA-256. It SHALL test two questions on the 134 items, Holm-adjusted at α = 0.05:
1. OMPF against MC-112's DSHF;
2. OMPF against MC-111's B.

For each question it SHALL report the mean per-item difference, a 95% percentile bootstrap (2,000 resamples, seed 7) and a two-sided paired sign-flip p-value (20,000 resamples, seed 7). OMPF SHALL be read as better than the reference only when its mean exceeds the reference's by more than 2.24 points and its adjusted p is below α. It SHALL be read as worse only when it trails by more than 2.24 points with an adjusted p below α.

#### Scenario: Small harness gain
- **WHEN** OMPF exceeds DSHF by 2.0 points with an adjusted p of 0.01
- **THEN** the reading is "no clear difference"
