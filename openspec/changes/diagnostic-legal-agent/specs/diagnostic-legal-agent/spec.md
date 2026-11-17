## Purpose

Measure whether Qwen3.5-9B, running inside DeepSeek Harness (dsh) with only `glob`, `grep` and `read` over a complete local folder of Vietnamese legal texts, searches for, finds and reads the provision that governs a Legal MC item, and whether its answers then beat closed-book B. The registration is fixed before the first request.

## ADDED Requirements

### Requirement: Frozen corpus folder
The corpus folder SHALL hold one plain-text file per document, with the whole text of the document's stored source. It SHALL hold no site instruction to AI readers, no site interface text, no question stem and no answer-key line. Every MC-101 article of a page SHALL appear in its file whole, with its heading as a line of its own. The folder SHA-256 SHALL be the SHA-256 of the sorted `sha256  file` listing, and it SHALL be registered. Before any request, the runner SHALL rebuild the folder from its registered inputs and SHALL refuse to run when the hash differs.

#### Scenario: A stored page changed
- **WHEN** a stored page or off-site file differs from its fetch-log SHA-256
- **THEN** the folder build fails and no request is sent

#### Scenario: Site instruction left in a file
- **WHEN** a built file still contains `hethongphapluat` or `model_prompt`
- **THEN** the folder build fails

### Requirement: Frozen provisions with anchor lines
For each of the 134 items, the provisions file SHALL list the provisions that govern it. Each provision SHALL be given as a file of the folder and an anchor line that is a whole line of that file. The file SHALL carry no gold letter, no option and no audit note. The owner's review labels SHALL replace the agent's labels on the reviewed items. The provisions SHALL be used only by the analysis and SHALL never reach a prompt.

#### Scenario: Anchor not in the folder
- **WHEN** a provision's anchor line is not a whole line of its file in the rebuilt folder
- **THEN** the provision check fails and no request is sent

### Requirement: Pinned harness and profile
Each attempt SHALL run dsh 0.2.2-rc.1 from the install whose lockfile SHA-256 is registered, on the registered node version, in headless mode with `--json`, under the registered profile patch. The profile SHALL expose only the `glob`, `grep` and `read` tools. It SHALL disable web access, bash, sub-agents, AGENTS.md loading and session titles.

#### Scenario: Install drift
- **WHEN** the install's lockfile hash, the dsh version or the node version differs from the registration
- **THEN** the runner refuses to start

### Requirement: Isolated attempt sandbox
Each attempt SHALL run in a sandbox with no network of its own, with fresh HOME and DSH_HOME directories and an empty environment apart from the registered variables. The sandbox SHALL see only system directories, node, the dsh install, the relay, the proxy's socket, its own home and the folder. The folder SHALL be mounted read-only at `/work/van-ban-phap-luat`, which SHALL be the working directory. The repository, the datasets and the user's home SHALL NOT be visible. The only connection out of the sandbox SHALL be the proxy. dsh SHALL never be started with the repository as its working directory.

#### Scenario: A second attempt starts
- **WHEN** an attempt starts after another one has finished
- **THEN** it sees none of the earlier attempt's session, configuration or files

### Requirement: Proxy changes only the temperature and key
The proxy SHALL forward only `POST /v1/chat/completions` with the registered model id. It SHALL add `"temperature": 1.0` to the request body and SHALL make no other change to the body. On the headers it SHALL:
- replace the dummy credential with the endpoint's key;
- add the campaign's gateway header;
- ask for an uncompressed stream;
- forward dsh's other headers unchanged.

It SHALL return the response stream unchanged and SHALL record every request and response.

It SHALL apply these limits:
- a 300 s timeout per request;
- a cap of 30 model requests per attempt;
- a pause of the run when the response model id differs from the registered one.

#### Scenario: dsh sends a temperature
- **WHEN** a request body already carries a `temperature` field
- **THEN** the proxy refuses it and the attempt fails without a score

#### Scenario: Request cap
- **WHEN** an attempt sends its 31st model request
- **THEN** the proxy refuses it, the attempt ends as `request_cap`, and it counts as wrong

### Requirement: Arm prompts
The task of each attempt SHALL be the arm's registered instruction, a blank line, then the item's frozen main-v1 MC prompt, byte for byte as B sends it:
- DSH SHALL say that the folder holds the full texts of Vietnamese legal documents, one per file, and that the tools may be used if useful.
- DSHF SHALL also require finding the governing provision with `grep` and reading it with `read` before answering.

Neither instruction SHALL name a document, an article or a search term.

#### Scenario: Prompt rebuild
- **WHEN** the runner rebuilds an attempt's task and it differs from the manifest's prompt hash
- **THEN** the run is refused

### Requirement: Attempt statuses and scoring
An attempt SHALL be `complete` when dsh emits `final` with reason `completed`. Its answer SHALL be `final.text`, read by the frozen V1 MC extractor and scored by the frozen scorer. The following attempts SHALL be terminal without an answer, SHALL count as wrong, and SHALL never be retried:
- `request_cap`;
- `upstream_4xx`;
- `harness_end`: dsh exited without `final` and the proxy saw no upstream failure;
- `answer_cap`.

Connection errors, timeouts, gateway 5xx and the 3-hour wall clock SHALL be technical failures. Only these SHALL be re-run, from scratch, on `--resume`.

#### Scenario: dsh exits without an answer
- **WHEN** dsh exits without a `final` event and the proxy recorded no upstream failure
- **THEN** the attempt is `harness_end`, it is scored wrong, and resume does not repeat it

#### Scenario: Gateway failure
- **WHEN** a model request fails with a connection error or a 5xx
- **THEN** the attempt is a technical failure and resume repeats it in a fresh sandbox

### Requirement: Trajectory hit rules
Hits SHALL be read from the tool results that reached the model: the `tool` messages of the request bodies the proxy recorded, not dsh's event previews. For each attempt and each provision of its item, the analysis SHALL compute three hits:
- **`seen`:** a `grep` or `read` result from the provision's file contains the anchor line;
- **`read`:** a `read` result from the provision's file contains the anchor line;
- **`opened`:** a `read` of the provision's file happened.

Line-number prefixes SHALL be stripped before matching. An item-level hit SHALL be any provision's hit.

#### Scenario: Heading found by grep only
- **WHEN** a `grep` result lists the anchor line of a provision's file, and no `read` of that file follows
- **THEN** the attempt is `seen` but not `read` for that provision

### Requirement: Registered analysis
The analysis SHALL run once, after every attempt is final. It SHALL score items by mean correctness over two draws, and SHALL take MC-111's B and O item scores from MC-111's round-1 score file, by registered SHA-256.

It SHALL test three questions on the 134 items, Holm-adjusted at α = 0.05:
1. DSHF against DSH;
2. DSH against MC-111's B;
3. DSHF against MC-111's B.

For each question it SHALL report the mean per-item difference, a 95% percentile bootstrap (2,000 resamples, seed 7) and a two-sided paired sign-flip p-value (20,000 resamples, seed 7).

For questions 2 and 3, an arm SHALL be read as beating B only when its mean exceeds B's by more than 2.24 points and its adjusted p is below α. It SHALL be read as worse only when it trails by more than 2.24 points and its adjusted p is below α.

#### Scenario: Small gain over B
- **WHEN** DSHF exceeds MC-111's B by 1.5 points with an adjusted p of 0.01
- **THEN** the reading is "no clear difference" and B stays the Legal MC route
