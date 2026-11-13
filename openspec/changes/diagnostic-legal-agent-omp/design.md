## Context

See proposal.md for the motivation. These parts already exist:

- **MC-112, done and committed** (`b894881` pre-registration, `86cf8f4` run record).
  - **Folder.** `all_res/diagnostic_legal_agent/corpus_v1`, folder SHA-256 `5f3240a216be2eb48c88fb7873d03076071ff7462a37bb627317b0ca70b4f3f3`. Its builder, its provisions file `data/diagnostic_legal_agent/item_provisions_v1.jsonl` (SHA-256 `472e131c…`) and its checks are in `diagnostic_legal_agent.py`.
  - **Prompts.** `data/diagnostic_legal_agent/agent_prompts_v1.json` (SHA-256 `3f760fd1…`), and the frozen manifest `manifest_v1.json` (self-hash `6e760d34…`, file SHA-256 `ca4560d6…`). Each DSHF task there is the DSHF instruction, a blank line, then the frozen B prompt.
  - **Proxy, relay and sandbox.** The proxy is `dsh_proxy.AttemptProxy`. The relay is `dsh_relay.py`. The runner `run_legal_agent.py` holds the sandbox, the engine wiring and the gates.
  - **Scores.** `all_res/diagnostic_legal_agent/run/qwen3-5-9b-65k-dsh/scores.jsonl`, SHA-256 `01084c90f1cc3230892e6ee6ac3de12792183455200c6e3da79dd6210a2abe69`, 536 rows. DSHF scored 85.07 there.
- **MC-111's reference.**
  - **Score file.** `round1/scores.jsonl`, SHA-256 `4e7556716f761c7a55baeb3bd6ed83939136fc9e073452a53f89b8c7aa0f52f0`.
  - **Arms.** B: 86.57. O: 83.02 on 53 items.
- **`omp` install.**
  - **Binary.** `~/.local/bin/omp`, a single ELF binary, `omp/18.0.0` (the version MC-86 to MC-89 ran). SHA-256 `69065aefe916fe28a09a4a1396446f16a776b5b56af0867cb4db0f452d842851`.
  - **Earlier use.** MC-88's runner (`run_qwen_omp_mc88.py`) holds the IEC provider template that this change copies.
- **Offline probe**, 2026-11-13. Its evidence is in `all_res/diagnostic_legal_agent_omp/probe_20261113/`.
  - **Setup.** A scripted local server (`fake_chat_upstream`), then MC-112's proxy on a Unix socket, then the relay inside `bwrap --unshare-all`, then `omp`. There was no model and no network. The probe ran once on a three-line file and once on `corpus_v1`.
  - **The request.** Chat Completions, streaming. Its keys are exactly `model`, `messages`, `stream`, `stream_options`, `tools`, `max_completion_tokens` (4096), `preserve_thinking` (true) and `chat_template_kwargs` (`{"preserve_thinking": true}`). There is **no temperature**, no seed and no reasoning field.
  - **The messages.** The system message is omp's English coding-agent prompt, 8,641 characters, SHA-256 `3d04a885…`. It was the same in both runs. It includes a `<workstation>` block (OS, CPU and GPU of the host, and the model ref). The user message has two text parts:
    - a `<system-reminder>` with today's date and the working directory;
    - the task, unchanged.
  - **The tools.** `--tools read,grep,glob` gives exactly three schemas: `read(path, i)`, `grep(pattern, path, case, gitignore, skip, i)` and `glob(path, hidden, gitignore, limit, i)`. `i` is a short "intent" string that every call must carry.
  - **The output.** `--mode json` writes events on stdout: `session`, `agent_start`, `turn_start`, `message_start`, `message_update`, `message_end`, `turn_end` (with `toolResults`) and `agent_end` (with all messages and `isTerminal`). Assistant messages carry `stopReason` and `usage`.
  - **The tool results** that reached the model are recorded in decision 9.
- **`omp` defaults read from `omp config list`** in a fresh profile:
  - `retry.enabled` true, with up to 10 retries and backoff up to 300 s;
  - `startup.checkUpdate` true;
  - `read.defaultLimit` 300 lines, and `read.summarize.enabled` true;
  - `grep.contextBefore` 1 and `grep.contextAfter` 3;
  - `tools.outputMaxColumns` 768, and output spill to `artifact://` for large results;
  - `compaction.enabled` true, with the method order remote, snapcompact, handoff, shake and soft;
  - `memories.enabled` false.

## Goals / Non-Goals

**Goals:**
- **Harness.** Whether Qwen, required to search, finds and reads the governing provision more often or less often in `omp` than in dsh, with the same folder, items and instruction.
- **Answers.** Whether OMPF's answers differ from DSHF's, and whether OMPF beats closed-book B.
- **Mechanism.** OMPF's accuracy when the governing provision was read and when it was not, beside DSHF's.

**Non-Goals:**
- **Attributing a difference to one part of `omp`.** The system prompt, the read window, the grep output and compaction all differ from dsh at once. The comparison is package against package.
- **Choosing anything from an outcome.**
- **Real-world retrieval.** The folder is complete and gold-aware.

## Decisions

### 1. Items and arm
- **Items.** MC-112's 134 items (pool `vi-multimodel-v1-legal-mc-146`).
- **Arm.** OMPF only, two draws: 268 attempts.
- **Manifest.** Item-major: each item lists OMPF-r1 then OMPF-r2. The run identity is `dataset:item:OMPF-r<k>`.
- **References.** These are not re-run.
  - **DSHF** from MC-112's score file.
  - **B and O** from MC-111's score file.

### 2. Frozen inputs reused from MC-112
- **What is reused.** Everything that MC-112's registration hashes, except its dsh profile and its manifest. That covers the folder and its manifest, the added and off-site documents, the provisions, the prompts, MC-101's sources and corpus units, MC-100's oracle evidence and MC-111's scores.
- **How it is checked.** This card's registration repeats those hashes and adds MC-112's manifest and score file.
- **Before any request:**
  - the runner rebuilds the folder in a fresh directory, and refuses to run if the folder hash differs;
  - it runs MC-112's `check_provisions` against that folder.
- **Who reads the provisions.** Only the analysis.

### 3. Harness: `omp` 18.0.0, pinned
- **Binary.** `~/.local/bin/omp`, SHA-256 `69065aef…`, and `omp --version` = `omp/18.0.0`. The runner checks both.
- **Configuration.** `data/diagnostic_legal_agent_omp/omp_config_v1.json` holds the two files written into each attempt's fresh home at `~/.omp/agent/`.
  - **`config.yml`:**
    - every model role set to `iec/Qwen3.5-9B-65K`;
    - `memory.backend: off`;
    - `retry.enabled: false`, so that a failed request is a technical failure re-run from scratch, as dsh's `maxRetries 0` made it in MC-112. omp honours the setting (`omp config list` shows it), but it does not stop omp's retry of a 5xx, so the proxy enforces the rule (decision 5);
    - `startup.checkUpdate: false`.
  - **`models.yml`:** provider `iec` with:
    - `baseUrl` set to the relay, `http://127.0.0.1:18080/v1`;
    - `apiKey` taken from `IEC_API_KEY`, which holds the dummy key;
    - `api: openai-completions`, `authHeader: true` and `disableStrictTools: true`;
    - one model, `Qwen3.5-9B-65K`, with `reasoning: false`, `input: [text]`, `contextWindow: 65024` and `maxTokens: 4096`.

    These are MC-88's values, except that `maxTokens` is MC-112's 4,096.
- **Invocation:** `omp -p --model iec/Qwen3.5-9B-65K --mode json --tools read,grep,glob --auto-approve --thinking off --max-time 10800 --no-title --no-extensions --no-skills --no-rules --no-lsp --cwd /work/van-ban-phap-luat "<task>"`.
  - **Change while building (2026-11-13): `--no-session` dropped.** With `--no-session`, omp still tells the model "Read artifact://0 for full output" after a long read, but that read returns "No session - artifacts unavailable". With a session, the read-back returns the spilled output, and the request is otherwise unchanged: same keys, same system prompt hash. The session lives in the attempt's fresh home, so nothing carries over between attempts. This keeps the output spill "as shipped", as approved, and matches MC-112, where dsh kept its session files.
- **Kept as shipped.** These are part of the package being compared:
  - the system prompt;
  - the date and working-directory reminder;
  - read summarisation and the 300-line default window;
  - grep context and paging;
  - output spill;
  - compaction.
- **Differences from dsh in MC-112** (all recorded in the card):

  | | dsh (MC-112) | `omp` (this card) |
  |---|---|---|
  | System prompt | short English persona and tool guidance | 8,641-character coding-agent prompt, which tells the model to use tools and not to stop early |
  | `read` window | up to 2,000 lines or 50 KiB | 300 lines by default. A whole-file read elides the middle of the window. `file:N-M` reads a range |
  | `grep` output | matching lines only, up to 250 | 1 line of context before and 3 after each match, 20 files per page with `skip` for more, lines cut at 512 characters |
  | Answer cap field | `max_tokens` | `max_completion_tokens` |
  | Extra body fields | none | `preserve_thinking`, `chat_template_kwargs` |
  | Retries | none | none (switched off) |

### 4. Sandbox, one per attempt
MC-112's sandbox (`bwrap --unshare-all --die-with-parent --new-session --clearenv`), with `omp` in place of node and dsh:
- **What is visible:**
  - `/usr` with its links, and the same six `/etc` files;
  - the `omp` binary read-only at `/opt/omp`;
  - the relay script read-only;
  - the proxy's socket directory at `/run/proxy`;
  - the attempt's fresh home at `/home/agent`, holding only `~/.omp/agent/config.yml` and `models.yml`;
  - the folder read-only at `/work/van-ban-phap-luat`, which is the working directory;
  - fresh tmpfs mounts on `/tmp`, `/work` and `/run`.
- **Environment.** Only `PATH`, `HOME`, `PI_CODING_AGENT_DIR=/home/agent/.omp/agent`, `IEC_API_KEY` (the dummy key), `LANG=C.UTF-8` and `TMPDIR=/tmp`.
- **Instruction files.** There is no `AGENTS.md`, `APPEND_SYSTEM.md` or rule file anywhere `omp` looks.
- **The only way out.** The proxy's Unix socket, through the relay. `omp`'s update check, its error reporting and its URL reads have no network, so they fail closed. A URL read reaches the model as a tool error.
- **What is kept.** omp's stdout events, its stderr, its home (with its session) and the proxy log, in the attempt's directory.
- **What is deleted.** omp unpacks about 300 MB of native libraries from the pinned binary into `~/.omp/natives` at every start. They are the same each time, so the runner deletes them after the attempt.
- **Safety net.** `--max-time 10800`, plus a runner kill at 10,860 s. Either one is a technical failure. When omp's own limit fires, it exits 0 with a last assistant message whose stop reason is `aborted` ("Deadline exceeded").

### 5. Proxy: MC-112's, with request-shape checks
- **Unchanged from MC-112:**
  - only `POST /v1/chat/completions` with model `Qwen3.5-9B-65K`;
  - `temperature: 1.0` added, and a body that already has one is refused;
  - the dummy key swapped for the IEC key;
  - the gateway header `x-9router-token-saver: off`, and `Accept-Encoding: identity`;
  - the stream passed through unchanged, and every request and response recorded;
  - a 300 s timeout per request, and a cap of 30 requests per attempt (the 31st gets 429);
  - a pause of the run when the response model id changes.
- **Added for `omp`.** A subclass in `run_legal_agent_omp.py`; `dsh_proxy.py` is not edited. Each check refuses before anything is sent, and the run pauses (fatal):
  - **Keys.** The body's keys must be a subset of the registered nine: the eight the probe recorded, plus `tool_choice`, which omp's compaction request adds (decision 9).
  - **Answer cap.** `max_completion_tokens` must be at most 4096, and exactly 4096 when the request offers tools. omp's compaction requests fit this rule: the handoff request keeps 4096 and adds `tool_choice: none`, and the short-summary fallback has no tools and a cap of 512. (Changed while building, 2026-11-13. The first rule, "exactly 4096", would have refused every compaction request.)
  - **System prompt.** On an attempt's first request, the system message's SHA-256 must equal the registered one. The smoke test records it on the endpoint path, and it must equal the probe's `3d04a885…`.
  - **Task.** On an attempt's first request, the user message's last text part must equal the manifest task byte for byte.

  These checks stop a change in omp's behaviour, or a different host whose `<workstation>` block changes the prompt, from passing silently.
- **No request after a technical failure** (added while building, 2026-11-13).
  - **Why.** omp 18.0.0 retries a 5xx by itself even with `retry.enabled: false`: offline, it made four retries of a 503 within about 10 s, then answered from the fifth request. It also retries the 429 of the request cap.
  - **What the proxy does.** Once a request of the attempt has failed technically (connection error, timeout or 5xx), the proxy refuses every later request of that attempt with 503 (`refused_after_failure`) and forwards nothing.
  - **Result.** The attempt ends as a technical failure, and `--resume` re-runs it from scratch, as approved ("omp's retries switched off") and as dsh's attempts did in MC-112.

### 6. Prompt
- **Task.** The task of each attempt is MC-112's DSHF task for the same item: the DSHF instruction of `agent_prompts_v1.json`, a blank line, then the frozen main-v1 MC prompt.
- **Manifest check.** The manifest builder checks that each task's SHA-256 equals the DSHF task hash in MC-112's manifest for that item.
- **What the instruction names.** It names `grep` and `read`, which `omp` has under the same names. It names no document, article or search term.
- **How `omp` sends it.** `omp` puts the task in a user message after its date and working-directory reminder. The proxy's task check (decision 5) confirms that the task arrives unchanged.

### 7. Attempt statuses
The same statuses as MC-112, mapped from omp's events. The mapping is fixed in offline tests against the scripted server.
- **`complete`.** `omp` exited 0, and the last assistant message in `agent_end` has `stopReason` `stop` and a text part. The answer is that text, read by the frozen V1 MC extractor and scored by the frozen scorer. An unparsed answer is wrong and stays in the denominator.
- **Terminal without an answer.** These count as wrong, are reported by status, and are never retried:
  - `request_cap`: the proxy refused the 31st request;
  - `upstream_4xx`: the endpoint answered 4xx, for example a context overflow that omp did not compact away;
  - `answer_cap`: the last assistant message stopped at the 4,096-token cap;
  - `harness_end`: `omp` ended without an answer, and the proxy saw no upstream failure.
- **Technical, resumable.** A connection error, a timeout, a 5xx, or the wall clock: the runner's kill, or omp's `--max-time`, which ends with stop reason `aborted`. `--resume` re-runs such an attempt from scratch. Four consecutive technical failures trip the breaker.
- **Offline check** (`--selftest`, scripted server, 2026-11-13). All six cases give the expected status:
  - a normal answer is `complete`, with every hit;
  - the cap is `request_cap`;
  - a 503 is technical, with the next request refused;
  - a 400 is `upstream_4xx`;
  - a stop at the cap is `answer_cap`;
  - a wrong system-prompt hash is fatal.

  `--max-time` gave `aborted`, which is technical.
- **Fatal.** These pause the run: a proxy refusal of decision 5, a change of response model id, or a sandbox start failure.

### 8. Engine and limits
- **As MC-112.** The campaign engine, at most 4 attempts in flight, and the breaker.
- **Budget guard.** Total reported tokens. The cap is set from the smoke test as 1.5 times the projected total.
- **Smoke-set fields.** The budget, `expected_response_model` and the system-prompt hash are `null` in the protocol until the smoke test. The runner's gates refuse to run while any of them is unset.
- **Arm id.** `OMPF` is added to `diagnostic_prospective.ARMS`.

### 9. Trajectory and hit rules (plan part of `diagnostic-legal-agent-omp-v1`)
- **Source of the trajectory.** As in MC-112, hits are read from the `tool` messages of the request bodies the proxy recorded. They are collected over all requests of the attempt, so a result counts once it was sent, even if compaction later dropped it. Each tool message is paired with its call by `tool_call_id`.
- **Formats recorded by the probe:**
  - **`read`.** The result is the file's text lines with no line numbers. A closing note in square brackets follows when the output is partial: `[Showing lines 39-63 of 20630. Use :64 to continue]`, or for a whole-file read, `[Showing lines 1-81 and 221-300 of 300; 139 middle lines (23.8KB) elided. … Read artifact://0 for full output. …]`.
    - **Which file.** The result names no file, so the file comes from the call's `path` argument: its base name, after removing a selector suffix such as `:40-60`, `:64` or `:raw`. The folder is flat, so a base name identifies a file.
    - **What counts.** Only the shown lines count; elided lines do not. The bracketed note is not content.
  - **`grep`.** File blocks headed `# <file>`, with lines `*<n>|<text>` for a match and ` <n>|<text>` for context. A paging note follows (`Showing files 1-20 of 293. Use skip=20 …`), and lines are cut at 512 characters. A result shows a line once it appears in a block, as a match or as context. A grep of a single file has no header, so its lines belong to the call's `path`.
  - **`glob`.** Paths only, so it shows no line of any file.
  - **Spilled output.** A note `Read artifact://<k> for full output` names a spilled result. A later `read` of `artifact://<k>`, or of the session file `<k>.<tool>.log` that the read-back's note names, counts as a result of the call that spilled it:
    - a read of file F if that call was a read of F;
    - grep output, counting for `seen` only, if that call was a grep.
  - **Paths outside the folder.** Directory listings, URLs, `omp://` documents and paths outside the folder count for no provision.
  - **Errors.** For example `Path '<p>' not found`, `URL: … Method: failed` (no network), or a regex that does not compile ("No matches found"). These show no line.
- **Compaction, observed offline** (scripted server reporting large prompt usage, 2026-11-13):
  - **Threshold.** It fires once the reported context passes about 56,800 tokens (between 56,000 and 57,000), about 87% of 65,024.
  - **First method: handoff.** A model request with the same system prompt and tools plus `tool_choice: none` asks the model to "write a handoff document". The run then continues from that document.
  - **Fallback: short summary.** If the handoff fails, omp sends a short-summary request, with no tools, another system prompt and a cap of 512.
  - **Elided results.** "Dead-end recovery" and shaking replace heavy tool results with a stub such as `[shaken ~127 tokens — recover: artifact://0 (region 2)]`. If a fresh read result is replaced before any request carries it, the model never sees it. The attempt is then `opened` for that file but not `read`. A later read of the named artifact counts as above.
  - **Counting.** Compaction requests count toward the cap, and their bodies are scanned like any other.
  - **Line cuts.** Anchor lines are at most 406 bytes, under both the 512- and the 768-character cut, so matching is exact.
- **Hits.** The new parser yields MC-112's observation shape (`tool`, `read_file`, `lines`). MC-112's `provision_hits` is then reused unchanged, with the same definitions:
  - **`seen`.** A `grep` or `read` result from the provision's file contains the anchor line.
  - **`read`.** A `read` result from the provision's file contains the anchor line.
  - **`opened`.** A `read` of the provision's file happened at all.

  An item-level hit means any of the item's provisions meets the rule.
- **Other counts per attempt:** tool calls by tool, read selectors used, grep pages requested, model requests, compactions, reported tokens and wall time.

### 10. Smoke test before registration
- **Questions.** `data/diagnostic_legal_agent_omp/smoke_questions_v1.json` names MC-112's three smoke questions by the SHA-256 of MC-112's file. They were written for the smoke, on a three-file synthetic folder and on articles that no Legal MC item uses. Each runs once with the DSHF instruction through the full path: sandbox, relay, proxy and IEC.
- **smoke-4.** One request on the synthetic folder asks for a long numbered list. It checks that the gateway honours `max_completion_tokens`: the response should stop with finish reason `length` at no more than 4,096 completion tokens.
- **What it records:**
  - whether tool calls parse;
  - the request bodies as sent;
  - the system-prompt hash;
  - the response model id;
  - the read format;
  - steps, requests, tokens and time.
- **Owner gate.** It needs the VPN, so the owner is asked first.
- **Use of its outputs.** No score is computed. The smoke sets the budget guard, `expected_response_model` and the system-prompt hash.
- **When to stop and report to the owner:** tool calls fail on IEC, the system prompt differs from the probe's, or the cap is not honoured.

### 11. Analysis, plan `diagnostic-legal-agent-omp-v1`, fixed before data and run once
- **Item score.** The mean correctness over two draws (0, 0.5 or 1).
  - **DSHF's** item scores come from MC-112's score file.
  - **B's and O's** come from MC-111's round-1 score file.

  Both are read by registered SHA-256.
- **Registered questions,** on the 134 items, Holm over the two p-values at α = 0.05:
  1. **Harness.** OMPF against MC-112's DSHF.
  2. **Against closed book.** OMPF against MC-111's B.
- **Statistics for each question.** The mean per-item difference, a 95% percentile bootstrap (2,000 resamples, seed 7) and a two-sided paired sign-flip p-value (20,000 resamples, seed 7).
- **Reading rule (both questions).** Both cross cards, so both use the 2.24-point margin, the gap between MC-101's and MC-111's B on the same items.
  - **Better.** OMPF beats the reference when its mean exceeds the reference's by more than 2.24 points and its adjusted p is below α.
  - **Worse.** OMPF is worse when it trails by more than 2.24 points with an adjusted p below α.
  - **Otherwise** there is no clear difference.
  - **The route.** B stays the Legal MC route unless OMPF beats B.
- **Description.**
  - **Behaviour.** Tool calls by tool. Read selectors and grep pages. Requests, compactions and tokens per attempt. Statuses. The share answering A. All of these sit beside MC-112's DSHF.
  - **Retrieval.** `seen`, `read` and `opened` hit rates over the 134 items and over MC-100's 53 oracle items. Each is given beside DSHF's, with the per-item paired difference and its bootstrap interval. This is descriptive and not tested.
  - **Accuracy by retrieval.** On the 126 `supports_gold` items, accuracy when the provision was read and when it was not, for OMPF and DSHF.
  - **Against O.** On the 53 oracle items, OMPF against MC-111's O.
  - **Gold check.** Answers on the 2 `contradicts_gold` and 6 `unclear` items.
  - **Context.** MC-112's DSH and DSHF, and MC-111's round-1 B, K and K10, and O on its items.

  The report's top-level keys are recorded in the registration and checked.

### 12. Registration (MC-113)
- **Files:**
  - a root block in `measurement_card.md`, with only that hunk staged;
  - the detail card `docs/measurement_cards/MC-113-diagnostic-legal-agent-omp.md`;
  - `data/diagnostic_legal_agent_omp/registration.json`.
- **What the registration holds.** The SHA-256 of every input:
  - MC-112's reused inputs;
  - MC-112's manifest and score file;
  - MC-111's score file;
  - the `omp` binary;
  - `omp_config_v1.json`, the protocol and the manifest;
  - the system-prompt hash;
  - the runner, the parser and the analysis.
- **The commit.** It is titled `pre-register MC-113` and comes before the first benchmark-item request.

### Open choices for the owner
These are the defaults above. Any can change before registration.
1. **Forced arm only.** An optional-search arm (MC-112's DSH instruction in `omp`) would add 268 attempts. It would be cheap if Qwen rarely searches. It is not included, because the owner chose the forced arm.
2. **omp's request retries switched off,** as dsh's were in MC-112.
3. **omp's read window, read summarisation, grep context and compaction left as shipped,** rather than set to dsh's limits.
4. **The 2.24-point margin on the harness question** as well as on the B question.
5. **smoke-4,** the check of the answer cap.

## Risks / Trade-offs

- **Package against package.**
  - **The cause.** omp's prompt pushes tool use and persistence. Its read window is smaller, and its grep output is wider.
  - **What it means.** A difference, or no difference, cannot be assigned to one of these. The card says so.
- **Power.**
  - **The size.** With 134 items and two draws, MC-112's 95% intervals for paired differences were about ±6.5 points.
  - **What it means.** A harness effect much smaller than that, or within the 2.24-point margin, reads as "no clear difference". Retrieval rates are compared descriptively.
- **Comparisons between cards.** DSHF ran on 2026-11-13 and B on 2026-11-09. The endpoint is shared, so drift is possible. Both questions carry the margin.
- **The request differs from dsh's and from B's.**
  - **The shape.** The user content comes in parts, and `preserve_thinking` and `chat_template_kwargs` are sent. The answer cap goes in `max_completion_tokens`.
  - **Checks.** The smoke test checks that no reasoning text returns and that the cap holds.
  - **If the gateway ignores the cap,** answers are bounded only by the context and the 300 s timeout. The owner is told before registration.
- **Prompt content that depends on the host or the date.**
  - **Host.** The `<workstation>` block names the host's hardware, and the system-prompt hash check pins it. The run must use the machine the smoke ran on.
  - **Date.** The reminder carries the date, so a run that crosses midnight sends two dates. That is recorded.
- **Compaction can hide what was read.**
  - **What was seen offline** (decision 9). omp compacts at about 56,800 reported tokens. A read that pushes the context past that point can be replaced by a stub before the model sees it.
  - **Consequence.** Long whole-file reads of large texts may count as `opened` without `read` more often than in dsh, whose 0.8 threshold left more room.
  - **What is done.** Compactions are counted per attempt. Their requests count toward the cap. A context overflow that remains is `upstream_4xx`. The real model may write handoffs differently from the scripted server.
- **Cost.**
  - **Why it is higher.** omp's grep returns context lines and up to 20 files per page, and the system prompt is larger, so each request re-sends more than dsh's.
  - **Bounds.** The request cap, the timeout and the budget guard.
- **`omp` changes fast.** The binary is pinned by hash. Results describe 18.0.0 only.
- **The folder is gold-aware,** as in MC-112. Retrieval is an upper bound for search in a general collection.
