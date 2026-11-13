## Context

See proposal.md for the motivation. These parts already exist, and all of them are offline and uncommitted:

- **Corpus folder.** `python -m code_benchmark.diagnostic_legal_agent folder --out <dir>` writes `<dir>/docs/` and `folder_manifest.json`. The folder `all_res/diagnostic_legal_agent/corpus_v1` has 310 files and 44,487,455 characters, and none is truncated. Its folder SHA-256 is `5f3240a216be2eb48c88fb7873d03076071ff7462a37bb627317b0ca70b4f3f3`, the hash of the sorted `sha256  file` listing.
  - **Fail-closed checks:**
    - every MC-101 article of a page is in its file whole, with its heading on a line of its own;
    - no hethongphapluat.com `model_prompt` text and no off-site UI text is left;
    - MC-101's leak check passes, so no question stem and no answer-key line is in the folder;
    - every stored page and off-site file matches its fetch-log SHA-256.
- **Provisions.** `... provisions --folder <dir>` writes `data/diagnostic_legal_agent/item_provisions_v1.jsonl`. It refuses a folder whose files differ from their manifest hashes, and fails when an anchor is not a whole line of its file.
  - **Record keys:** `dataset_id`, `item_id`, `support`, `label_source`, `located_by`, `provisions[{file, doc_id, locator, anchor_line}]`. There is no gold letter.
  - **Owner check.** The owner's spot-check on 2026-11-12 used the 14 items first in SHA-256 order of `legal-agent-review|<id>`. All 14 agreed with the agents. Its record is `all_res/diagnostic_legal_agent/audit/review_labels.json`, which holds the gold, and the reviewer was nttung245.
- **dsh probe** (2026-11-11, `~/tools/dsh-probe/`, fake loopback server, no model).
  - **Install.** dsh 0.2.2-rc.1 runs headless under `bwrap --unshare-net` with node v24.20.0. The install in `~/tools/dsh-0.2.2-rc.1-patched` has npm-audit fixes, and its lockfile SHA-256 is `ef8381ac…`. Its requests equal those of the unpatched install.
  - **The request.** Chat Completions, streaming, `max_tokens` 4096, no temperature and no seed.
  - **The messages.** An English system prompt ("You are an AI agent powered by DeepSeek Harness. / You are a coding agent powered by the Qwen3.5-9B-65K model." plus three lines of tool guidance). The task follows as a user message, then a second user message with the runtime context: cwd, read-only policy and approvals.
  - **The tools.** Schemas for `glob`, `grep` and `read`.
  - **The output.** `--json` writes events on stdout: `session`, `status` (turn and step boundaries with usage), `tool_call`, `tool_result`, `text` and `final`.
- **dsh internals read from its source.**
  - **Temperature.** dsh sends a temperature only when a plugin sets it in the `agent/request` waterfall. No profile key does.
  - **Tool limits.** `read` returns at most 50 KiB and 2,000 characters per line. `grep` returns at most 250 matches. `glob` returns at most 100 paths.
  - **Compaction.** It starts at 0.8 of the context window and makes its own model request.
  - **No step limit.** The loop has none and ends when the model answers without a tool call.
- **MC-111's reference.**
  - **Arms.** B: 268 attempts, 86.57. O: 106 attempts on 53 items, 83.02.
  - **Score file.** `round1/scores.jsonl`, SHA-256 `4e7556716f761c7a55baeb3bd6ed83939136fc9e073452a53f89b8c7aa0f52f0`.
  - **Drift between cards.** MC-101's B on the same 134 items was 84.33. B differs on 25 items, and the mean gap is 2.24 points.

## Goals / Non-Goals

**Goals:**
- **Behaviour.** Whether Qwen, given a complete local legal folder and three file tools, searches, finds and reads the provision that governs a question, unprompted (DSH) and when told to (DSHF).
- **Answers.** Whether either arm beats closed-book B, and whether requiring search helps over allowing it.
- **Mechanism.** Accuracy when the governing provision was read and when it was not.

**Non-Goals:**
- **Explaining dsh's scaffold apart from the tools.** The owner rejected the no-tool and empty-folder arms. If an arm loses to B, the result is that "the dsh package lost", and the trajectory shows whether the right provision was found.
- **Choosing anything from an outcome.** This covers the prompts, the caps and the folder.
- **Real-world retrieval.** The folder is complete and gold-aware.

## Decisions

### 1. Items and arms
- **Items.** The 134 items of MC-101's pool (`vi-multimodel-v1-legal-mc-146`), not held out.
- **Arms.** DSH and DSHF, two draws each: 536 attempts.
- **Manifest.** Item-major. Each item lists DSH-r1, DSHF-r1, DSH-r2 and DSHF-r2 in that order, so that endpoint drift during the run touches both arms alike. The run identity is `dataset:item:<ARM>-r<k>`.
- **Reference.** B and O come from MC-111 and are not re-run.

### 2. Corpus folder and provisions are frozen inputs
- **Hashes in the registration:** the folder SHA-256, the folder manifest, `added_documents_v1.json`, `offsite_documents_v1.json`, `item_provisions_v1.jsonl`, MC-101's source list and corpus units, and MC-100's oracle evidence.
- **Before any request:**
  - the runner rebuilds the folder into a fresh directory, and refuses to run if the folder hash differs;
  - it runs `check_provisions` against that folder.
- **Where the folder sits.** Each attempt mounts the folder read-only at `/work/van-ban-phap-luat`, the attempt's working directory. The path the model sees in the runtime context is therefore the same for every attempt.
- **Who reads the provisions.** Only the analysis. No prompt carries the gold, a provision, a support label or an audit note.

### 3. Harness: dsh 0.2.2-rc.1, pinned
- **Pinned files:**
  - install `~/tools/dsh-0.2.2-rc.1-patched`;
  - `package-lock.json` SHA-256 `ef8381acc897799d7a4544e640be118420bd325802b17c749d9fb7cdb70140ea`;
  - node v24.20.0.
  The registration records the lockfile hash, the dsh version and the node version, and the runner checks all three.
- **Profile.** The headless profile with the patch `data/diagnostic_legal_agent/dsh_profile_v1.yml`. It is the probe's `cordis.patch.yml` with only the route's `baseURL` changed, to the relay inside the sandbox.
  - **Route.** `openai-completions`, `maxRetries 0`, `max_tokens` as the token field, `store` dropped. The model `Qwen3.5-9B-65K` has a context of 65,024 and a cap of 4,096 tokens per response.
  - **Tools.** Only `glob`, `grep` and `read`.
  - **Off:** bash, jobs, sub-agents, workflows, todo, goal, plan mode, MCP, web, DeepSeek routes, AGENTS.md loading and session titles.
  - **Kept as shipped:** compaction, the repeated-tool reminder and the persona, because they are part of the package being measured.
- **Invocation:** `dsh --profile headless --json "<task>"`, with `DSH_TELEMETRY_DISABLED=1` and `DSH_PERMISSION_MODE=read-only`.

### 4. Sandbox, one per attempt
- **Namespaces.** `bwrap --unshare-all --die-with-parent --new-session`. The attempt has no network but its own loopback.
- **What is visible** (tightened while building, 2026-11-12). Unlike the probe, the host root is not bound. The sandbox sees only:
  - `/usr`, with the usual `/bin`, `/lib`, `/lib64` and `/sbin` links, and six files of `/etc` (`ld.so.cache`, `passwd`, `group`, `nsswitch.conf`, `localtime`, `hosts`);
  - node at `/opt/node` and the dsh install at `/opt/dsh`, both read-only;
  - the relay script, read-only;
  - the proxy's socket directory at `/run/proxy`;
  - the attempt's own home at `/home/agent`;
  - the folder, read-only, at `/work/van-ban-phap-luat`;
  - fresh tmpfs mounts on `/tmp`, `/work` and `/run`.

  Nothing of the repository, the datasets or the user's home is reachable. An offline check confirmed that `read` of the repository's `.env` fails with "not found" and that `grep` over `/home` finds nothing.
- **Environment.** `--clearenv`, then only PATH, HOME, DSH_HOME, `LANG`, the two dsh variables and a dummy API key.
- **Home.** HOME (and DSH_HOME inside it) is a fresh directory in the attempt's output, holding only the profile patch. No session, config or credential carries over between attempts, and dsh's session files stay with the attempt.
- **Working directory.** The folder at `/work/van-ban-phap-luat` is the cwd. dsh never starts with the repository as its working directory, because headless dsh reads `<cwd>/.env`.
- **The only way out.** The proxy's Unix socket. A stdlib relay inside the sandbox (`python3 -I`) listens on `127.0.0.1:18080` and copies bytes to that socket. dsh starts only after the relay has written its ready file.
- **What is kept.** dsh's stdout events, its stderr, its home (with its session files) and the proxy log, in the attempt's directory.
- **Safety net.** A 3-hour wall clock per attempt. Hitting it is a technical failure.

### 5. Proxy (`dsh_proxy`), outside the sandbox
- **What it accepts.** Only `POST /v1/chat/completions` whose `model` is `Qwen3.5-9B-65K`.
- **The one body change.** It adds `"temperature": 1.0`. A body that already carries a temperature fails the attempt, so a change of dsh's behaviour cannot pass silently.
- **Headers.**
  - It replaces the dummy key with the IEC key from the repo `.env`, so dsh never holds the real key.
  - It adds the campaign's gateway header `x-9router-token-saver: off`, which MC-90 to MC-111 sent with every request.
  - It asks for an uncompressed stream (`Accept-Encoding: identity`).
  - It forwards dsh's other headers unchanged.
- **Forwarding.** It sends the request to the registered endpoint and streams the response back unchanged.
- **What it records.** For every request: the body as received, the body as sent, the status, the assembled response (content, reasoning text if any, tool calls, finish reason, usage, response model id) and timings.
- **Limits.**
  - A 300 s timeout per request, as MC-111.
  - A cap of 30 model requests per attempt. The 31st request gets an error, and the attempt ends as `request_cap`. Compaction requests count toward the cap.
- **Model id.** It checks the response model id against the registered id, and pauses the run on a change.

### 6. Prompts, version `diagnostic-legal-agent-prompts-v1`
Template file `data/diagnostic_legal_agent/agent_prompts_v1.json`. The task is the arm's instruction, a blank line, then the item's frozen main-v1 MC prompt, byte for byte as B sends it.

- **DSH:** *"Thư mục làm việc hiện tại chứa toàn văn các văn bản pháp luật Việt Nam, mỗi file `.txt` là một văn bản. Bạn có thể dùng các công cụ glob, grep và read để tra cứu các văn bản này nếu thấy cần."*
- **DSHF:** *"Thư mục làm việc hiện tại chứa toàn văn các văn bản pháp luật Việt Nam, mỗi file `.txt` là một văn bản. Trước khi trả lời, bạn phải dùng công cụ grep để tìm và công cụ read để đọc quy định pháp luật dùng để trả lời câu hỏi dưới đây. Chỉ trả lời sau khi đã đọc quy định đó."*

Neither instruction names a document, an article or a search term.

### 7. Attempt statuses
- **`complete`.** dsh emitted `final` with reason `completed`. The answer is `final.text`, read by the frozen V1 MC extractor and scored by the frozen scorer. An unparsed answer is wrong and stays in the denominator.
- **Terminal without an answer.** These count as wrong, are reported by status, and are never retried:
  - `request_cap`: the proxy refused the 31st request;
  - `upstream_4xx`: the endpoint answered 4xx, for example a context overflow that dsh did not compact away;
  - `harness_end`: dsh exited without `final`, and the proxy saw no upstream failure;
  - `answer_cap`: the final step hit the 4,096-token cap without a final text.
- **Technical, resumable.** A connection error, a timeout, a 5xx from the gateway, or the 3-hour wall clock. `--resume` re-runs such an attempt from scratch in a fresh sandbox. Four consecutive technical failures trip the engine's breaker.

### 8. Engine and limits
- **Engine.** The campaign engine of MC-91 to MC-111, with 12 lanes (4 shards × 3 lanes). At most 4 attempts are in flight. An attempt's requests are sequential, so at most 4 requests are in flight.
- **Breaker.** As registered for MC-111.
- **Budget guard.** Total reported tokens over all proxy-recorded requests. The run halts when the total reaches the cap. The cap is set from the smoke test (decision 10) as 1.5 times the projected total, and written into the protocol and card before registration.
- **Response model id.** The proxy checks it against `expected_response_model`. That id is taken from the smoke test, because llama.cpp's Chat Completions endpoint may name the model differently from the Responses API's self-reported path. The protocol holds `null` for both fields until then, and the runner's gates refuse to run while either is unset.
- **Arm ids.** DSH and DSHF are added to `diagnostic_prospective.ARMS`, as MC-111 added K10, PICK and SEL. They are scored as frozen MC answers on dsh's final text.

### 9. Trajectory and hit rules (plan part of `diagnostic-legal-agent-v1`)
- **Source of the trajectory: what reached the model.** The offline fake-server run showed that dsh's `--json` `tool_result` events carry only a preview of about 6 KB, while the model receives the whole result, up to about 50 KB. Hits are therefore read from the `tool` messages of the request bodies the proxy recorded. These are collected over all requests of the attempt, so a result counts once it was sent, even if compaction later removed it. dsh's events are kept for the final answer and for description.
- **Parsing.** The formats were recorded from dsh 0.2.2-rc.1 in the sandbox and are fixed in the parser's tests.
  - A `grep` result is `Found …`, then file blocks: a path line (`./<file>` or `<file>`), followed by `Line <n>: <text>` lines.
  - A `read` result is `<path>…</path>`, `<type>file</type>`, then `<content>` with `<n>: <text>` lines and a closing note. Its path comes from the `<path>` tag. A path that does not resolve to a file of the folder counts for no provision.
  - A grep result too large for the context is spilled to a file under `/tmp`. If the model reads that file back, its lines are parsed as grep output, and they count for `seen` only.
  - Anchor lines are at most 406 bytes, far below the tools' 2,000-character line cut, so matching is exact.
- **Per attempt and per provision of the item:**
  - **`seen`.** A `grep` or `read` result from the provision's file contains the anchor line.
  - **`read`.** A `read` result from the provision's file contains the anchor line.
  - **`opened`.** A `read` of the provision's file happened at all.
- **Per attempt overall.** `searched` means at least one tool call. An item-level hit means any of the item's provisions meets the rule.
- **Other counts per attempt:** tool calls by tool, model requests, compaction requests, steps, reported tokens and wall time.

### 10. Smoke test before registration
- **Questions.** Three questions written for the smoke, not drawn from any benchmark. One runs on a three-file synthetic folder; two run on `corpus_v1` and ask about articles that no Legal MC item uses. Each question runs once through the full path: sandbox, relay, proxy and IEC.
- **What it checks:**
  - the endpoint returns parseable tool calls through Chat Completions;
  - the proxy's temperature and key handling work;
  - the record of a `read` result is as expected;
  - the cost per step and per attempt.
- **Owner gate.** It needs the VPN, so the owner is asked before it runs.
- **Use of its outputs.** No score is computed. Its outputs stay in `all_res/diagnostic_legal_agent/smoke/` and are described in the card. It sets only the budget guard.
- **If tool calls do not work on IEC,** the card is not registered, and the owner is told.

### 11. Analysis, plan `diagnostic-legal-agent-v1`, fixed before data and run once
- **Item score.** The mean correctness over the two draws (0, 0.5 or 1). MC-111's B and O item scores come from its round-1 score file, by registered SHA-256.
- **Registered questions,** on the 134 items, with Holm over the three p-values at α = 0.05:
  1. **Forcing.** DSHF against DSH.
  2. **Allowing search.** DSH against MC-111's B.
  3. **Requiring search.** DSHF against MC-111's B.
- **Statistics for each question.** The mean per-item difference, a 95% percentile bootstrap (2,000 resamples, seed 7) and a two-sided paired sign-flip p-value (20,000 resamples, seed 7).
- **Reading rule.**
  - **Question 1.** Forcing helps when DSHF's mean exceeds DSH's and its adjusted p is below α. Forcing hurts when the reverse holds with an adjusted p below α.
  - **Questions 2 and 3.** The arm beats B when its mean exceeds B's by more than 2.24 points, the gap between MC-101's and MC-111's B, and its adjusted p is below α. It is worse than B when it trails by more than 2.24 points with an adjusted p below α. Otherwise there is no clear difference, and B stays the Legal MC route.
- **Description.**
  - **Behaviour per arm.** The share of attempts that searched. Tool calls by tool. Requests, compactions and tokens per attempt. Statuses. The share answering A.
  - **Retrieval per arm.** `seen`, `read` and `opened` hit rates over the 134 items and over MC-100's 53 oracle items. The latter sit beside MC-111's BM25 top-2 hit (40 of 53) and PICK.
  - **Accuracy by retrieval.** On the 126 `supports_gold` items, each arm's accuracy when the governing provision was read and when it was not.
  - **Against O.** On the 53 oracle items, each arm against MC-111's O.
  - **Gold check.** Answers on the 2 `contradicts_gold` items and the 6 `unclear` items.
  - **Context.** MC-101's B, K and O and MC-111's K, K10 and SEL beside the two new arms.

  The report's top-level keys are recorded in the registration and checked.

### 12. Registration (MC-112)
- **Files:** a root block in `measurement_card.md`, the detail card `docs/measurement_cards/MC-112-diagnostic-legal-agent.md` and `data/diagnostic_legal_agent/registration.json`.
- **What the registration holds.** The SHA-256 of every frozen input: the folder, its manifest, the added, off-site and provision files, the prompts, the profile, the protocol, the manifest, MC-111's score file, MC-101's and MC-100's inputs, the dsh lockfile, the runner, the proxy and the analysis.
- **The commit.** It is titled `pre-register MC-112` and comes before the first benchmark-item request.
- **Runner gates.** The runner refuses to run without each of these, and when any hash differs.

## Risks / Trade-offs

- **The API and system prompt differ from MC-111's B.**
  - **The difference.** Chat Completions with dsh's English coding persona, against the Responses API with `Answer the user's question.`.
  - **Bound.** A share of any difference from B may come from this. The comparison carries the 2.24-point margin. Question 1 is within the card and free of it.
- **Cost and runaway trajectories.**
  - **The risk.** Re-sent context grows with each step.
  - **Bounds.** The request cap (30), the per-request timeout and the budget guard. Reaching the cap counts as wrong, because that is the package's behaviour.
- **Context overflow.** A long `read` (up to 50 KiB) can push the context toward 65K. dsh's own compaction handles this as shipped. What remains is recorded as `upstream_4xx`.
- **Tool calling on IEC is unverified.** The smoke test checks it before registration.
- **The folder is gold-aware.**
  - **How it was built.** Documents were added for items the audit found uncovered.
  - **Consequence.** Retrieval here is an upper bound for search in a general collection. The card says so.
- **Labels from agents.** 106 of the 134 provision rows are labelled by agents, and 28 carry the owner's label: 14 from MC-100's review and 14 from this audit's check. In this audit's check the owner agreed with the agents on 14 of 14. The Wilson 95% lower bound is about 78%.
- **dsh is a developer preview.** The install and lockfile are pinned and hashed. Results describe this version only.
