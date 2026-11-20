## Context

See `proposal.md` for the motivation. MC-117 reuses MC-115's items, folders and tasks, MC-115's Qwen route and MC-116's MiMo route, and MC-113's omp pin. The only change is to omp's argument list.

| What | OMPF (MC-113 to MC-116) | OMPS (MC-117) |
|---|---|---|
| Harness | omp 18.0.0, MC-113's configuration (MC-116's for MiMo) | the same |
| Argument list | MC-113's | MC-113's + `--system-prompt <dsh's system prompt for the model>` |
| First system message | 8,641 chars (Qwen, `3d04a885…`), 8,644 (MiMo, `616bebaf…`) | 1,104 chars (Qwen, `b868301f…`), 1,108 (MiMo, `32a43405…`), offline |
| Tools, sandbox, proxy limits, context window, cap | MC-113's (Qwen), MC-116's (MiMo) | the same |
| Task bytes, user-turn `<system-reminder>` | the same | the same |
| Draws | 1–2 (MC-113/114 for Qwen, MC-116 for MiMo) | 1–2, new |

Facts checked before this design, all on 2026-11-20:
- **What `--system-prompt` replaces.** An offline capture ran omp 18.0.0 in the registered sandbox against a scripted local server (`all_res/diagnostic_legal_agent_mimo/omp_prompt_capture/`).
  - With the default prompt, the first system message hashed as MC-113's and MC-116's registered pins (`3d04a885…`, `616bebaf…`), so the capture matches the runs.
  - With `--system-prompt <text>`, the message is the given text, followed by omp's `<workstation>` block (host and model id) and its `<critical>` block (three action mandates). Gone are the RFC 2119 conventions, the `<system-conventions>` block and the rest of the default prompt body.
  - Roles, tools (`read`, `grep`, `glob`) and the user turn are unchanged.
- **dsh's system prompt,** from recorded DSHF requests:
  - Qwen: 441 chars, SHA-256 `d6bd65aa82408826439600dabebac6df2cc89635d5f97c25809870a218f80402`.
  - MiMo: 442 chars, `54d89951230a8b4a14f8b9b231a480ddfca31cf1929169074b141bc165d62d6c`.

  Each names "DeepSeek Harness" and the model id, and tells the model to use `read` with offset and limit, `glob` and `grep`. All three tools exist in omp under the same names.
- **Drift between rounds** (MC-115's report, Qwen, draws 1–2 to 3–4): OMPF −0.41 [−5.08, 4.27] on multiple choice and +0.36 [−2.18, 2.93] on ViBidLQA. DSHF moved more: −3.46 and −2.97.
- **Qwen's thinking cannot be switched on** at the IEC gateway. Probe: 20 synthetic requests; `enable_thinking` and `/think` were ignored, and `Qwen3.5-9B-75K` returned 503.

## Goals / Non-Goals

**Goals:**
- Test, per model, whether replacing omp's default prompt body changes omp's score.
- Test whether that change differs between the models, which would mean the prompt carries part of the model × harness interaction.
- Report how much of the interaction remains with the prompt replaced.

**Non-Goals:**
- Removing `<critical>` or `<workstation>`. omp's CLI cannot remove them.
- Changing paging, grep formatting, compaction or thinking.
- Re-running OMPF or DSHF.

## Decisions

### 1. The replacement text is dsh's own prompt, verbatim

- **Why not a neutral short prompt.** That would introduce a third prompt. dsh's prompt is the one under which each model's DSHF answers were measured, so OMPS asks: omp with dsh's instructions.
- **What the text says.** It names "DeepSeek Harness", which is now inaccurate inside omp. It is kept byte for byte so the instruction text equals DSHF's. The card states this.
- **Hashes.** Each model's text is stored in `data/diagnostic_legal_agent_omp_prompt/` and read by its SHA-256.

### 2. Items, arm and draws

MC-115's 646 items:
- **Part M:** 246 items, the 134 Legal MC items on corpus_v1 and the 112 VMLU law items on corpus_v2.
- **Part S:** 400 ViBidLQA items, closed-book, on corpus_v2.

OMPS runs at draws 1 and 2 for each model: 1,292 attempts per model. Each attempt sends the task of MC-115's OMPF item with replicate id `OMPS-r1` or `OMPS-r2`. The build fails if any task, input or gold hash differs from MC-115's manifest for the OMPF arm of that item.

### 3. Routes, unchanged

- **Qwen.** MC-115's route: IEC's `Qwen3.5-9B-65K` over the openvpn3 `member-shared-tcp` tunnel, the in-tunnel resolver shim, MC-113's omp configuration, cap 4,096 (`max_completion_tokens`) and context window 65,024. The response-model pin is `Qwen3.5-9B-65K`.
- **MiMo.** MC-116's route: OpenCode Go `mimo-v2.6-flash`, one `x-opencode-session` per try, cap 16,000 and context window 65,024. The pin is `mimo-v2.6-flash`.
- **Both.** Temperature 1.0 added by the proxy, a request cap of 30, a 3-hour wall clock per attempt, and the request timeout of each route's card.

### 4. Runner

`run_legal_agent_omp_prompt.py --model qwen|mimo` wraps MC-115's (Qwen) or MC-116's (MiMo) runner functions without editing them. The omp protocol is overlaid with:
- the extra arguments;
- the system-prompt pin, set from the smoke test;
- the arm id OMPS.

It also has its own engine, budget guard, outage guard, statuses and `--resume`. Two fixes apply to MC-117 only:
- **Identity on halted rows.** A row returned without a request (`halted_before_send`, `budget_cap`, `endpoint_unresponsive`) carries `shard`, `lane`, `model_id`, `protocol_id`, `profile_id` and `measurement_card_id`. A halt then neither crashes the loop nor blocks `--resume`.
- **Stalls.** A proxied stream that ends with no chunk naming a model is recorded as `network` (`stream_stalled`), not `model_drift`. Under the registered status rules it is technical, and `--resume` re-runs it, unless the harness itself went on to a final answer. A response that names another model still halts the run.

### 5. Smoke test (before registration, no benchmark item; owner's go)

MC-112's `smoke-2` (corpus_v1) and MC-114's `smoke-s2` (corpus_v2), each once with OMPS per model: 4 attempts. Qwen's 2 run over the VPN. The test records:
- status and HTTP statuses;
- body keys;
- response model ids;
- the first system message's SHA-256, which must equal the offline capture's (`b868301f…`, `32a43405…`) unless the host changed;
- tokens and the largest completion.

From it come the system-prompt pins and the budgets: MC-115's and MC-116's real OMPF tokens per attempt, scaled by the smoke ratio and multiplied by 1.5.

### 6. Operation

- At most 4 attempts in flight per run; stop after 4 timeouts.
- Each run is a `systemd-run --user` unit.
- Qwen's unit opens the VPN at start and closes it when it ends (MC-115's practice).
- The two runs may overlap.

### 7. Analysis (fixed before data, run once after both runs are final)

`analyze_legal_agent_omp_prompt`, plan `diagnostic-legal-agent-omp-prompt`.
- **Item score:** the mean over draws 1–2. Part M uses correctness; Part S uses vi-reading-v3 token-F1, in points. Comparators come from the registered score files by SHA-256: MC-112/113/114 for Qwen (OMPF, DSHF) and MC-116 for MiMo (OMPF, DSHF).
- **Per part, Holm over three tests:**
  - **P1:** Qwen's OMPS − OMPF.
  - **P2:** MiMo's OMPS − OMPF.
  - **P3:** per item, MiMo's (OMPS − OMPF) − Qwen's (OMPS − OMPF).

  The margin is 2.24 points on Part M (as MC-115 and MC-116) and none on Part S.
- **Statistics,** as MC-112 to MC-116:
  - the mean per-item difference;
  - a 95% percentile bootstrap over items (2,000 resamples, seed 7);
  - a two-sided paired sign-flip p-value (20,000 resamples, seed 7).
- **Reading rules:**
  - P1 and P2: "OMPS better/worse than OMPF" when the difference exceeds the margin with a Holm-adjusted p below 0.05; otherwise "no clear difference".
  - P3: "omp's default prompt carries part of the interaction" when P3 is below −margin with a Holm-adjusted p below 0.05, which is the direction opposite to the original interaction. "Carries none detectable" when P3's interval lies within ±margin (Part M) or contains 0 (Part S). Otherwise "not determined".
- **Beside, not tested:**
  - the remaining interaction, (OMPS − DSHF) of MiMo minus that of Qwen, against the original +14.63 and +11.64, with the share removed (−P3 ÷ original);
  - P1 with Qwen's OMPF draws 1–4 (MC-115 added);
  - the step split of `analyze_legal_agent_interaction` for OMPS (read rate, score when read and when not read);
  - outcomes, requests, tool calls and tokens per model.

### 8. Action flows (owner, 2026-11-20: "quan trọng là ta phải quan sát flow log của harness… cái quan trọng là actions nó thực hiện")

Every harness calls the same model API. What sets a harness apart is the actions around those calls: which tools it lets the model call and how it executes them, what it shows back, and what it does on its own. So the card measures actions, not only scores.

- **Source.** Each attempt keeps the harness's own event stream (`events.jsonl`) and the proxy's request records (`proxy_log.jsonl`). `code_benchmark/harness_flow.py` joins the two into one timeline per attempt, with one vocabulary for both harnesses:
  - **Model actions:** thinking (size), a tool call (tool, pattern or path, offset and limit, omp's `intent`) and the answer.
  - **What the harness showed back:** size, empty, the paging note ("Showing lines a–b of N"), truncated lines and the files named.
  - **Actions the harness took on its own:** auto-compaction (reason, action, and the summary's size and language), notices and elisions (blocks and tokens removed), re-sends after a failure or stall, the hand-off request, cancelled requests, step limits and the end reason.
  - **API calls:** tokens, latency and outcome.
- **What is reported** per model and arm (OMPS, OMPF, DSHF):
  - actions per attempt by kind;
  - the share of attempts with each harness-initiated action;
  - transitions between action kinds;
  - the most frequent action sequences;
  - for each item and draw, the first step at which OMPS and OMPF (and OMPF and DSHF) diverge;
  - what the model had in front of it when it answered: the raw tool output of the governing article, a compaction summary (and its language), or neither.
- **Fixed before data, not tested.** The module and its metrics are written and tested on MC-112 to MC-116 (Phase 1b), and their SHA-256 is registered with the card. The flow layer explains the registered tests; it is not one of them.

### 9. Registration (MC-117)

- A root block in `measurement_card.md`;
- the detail card `docs/measurement_cards/MC-117-diagnostic-legal-agent-omp-prompt.md`;
- `data/diagnostic_legal_agent_omp_prompt/registration.json`, with every frozen input hashed (protocol, prompt texts, manifest, reference score files, the runner and analysis code).

The commit is titled `pre-register MC-117` and comes before the first benchmark-item request of either model.

## Risks / Trade-offs

- **Old comparators.** OMPF and DSHF are not re-run, so OMPS is compared with rounds measured 2026-11-13 to 2026-11-19. Qwen's OMPF moved by under 0.5 points between rounds (CIs about ±5). MiMo has one round, so its drift cannot be estimated. P1 and P2 therefore carry this caveat. P3, which differences two models' changes, does not remove it.
- **What stays.** `<critical>` ("run the specific test"), `<workstation>`, paging, grep formatting and omp's message assembly all stay. A null P3 says the prompt body is not the carrier; it does not clear omp's other components.
- **The prompt names DeepSeek Harness.** It is kept verbatim for equality with DSHF's instructions. A model could react to the mismatch. The card records it.
- **Two draws.** P1 and P2 are detectable at about ±5 points per part. The original interaction was 11–15 points, so a prompt that carries half of it should show in P3.
- **Thinking stays confounded** with the model. MC-117 tests a harness component, not a model property.
