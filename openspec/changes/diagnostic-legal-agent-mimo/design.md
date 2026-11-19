## Context

See proposal.md for the motivation. MC-116 reuses MC-115's items, folders and tasks, and MC-112's and MC-113's harness pins, with one change: the model.

| What | MC-115 (Qwen) | MC-116 (MiMo) |
|---|---|---|
| Model and route | Qwen3.5-9B-65K, Q4_K_M GGUF on llama.cpp, IEC gateway over the VPN | `mimo-v2.6-flash` through OpenCode Go (`https://opencode.ai/zen/go/v1`), no VPN |
| Thinking | off (served non-thinking) | the provider's default; cannot be set on this route |
| Cap per response | 4,096 (`max_tokens` for dsh, `max_completion_tokens` for omp) | 16,000 (`max_completion_tokens` for both) |
| Context window declared to the harness | 65,024 | 65,024 |
| Direct request | Responses API, "Answer the user's question.", temperature 1.0, 4,096 | chat completions, the same system prompt, temperature 1.0, 16,000 |
| Draws | 3 and 4 (draws 1–2 in MC-111 to MC-114) | 1 and 2 |

Facts checked before this design (2026-11-19):
- **The model is served.** OpenCode Go's model list holds `mimo-v2.6-flash` (context 1,048,576, output 131,072; USD 0.14 / 0.0028 cached / 0.28 per million tokens; monthly Go limit USD 60).
- **Thinking cannot be set.** Ten synthetic requests: `thinking: {type: disabled}` still returned 36–52 reasoning tokens on an easy question; on a harder one, `reasoning_effort` low, medium and high gave 342–505, 386–410 and 311–478 reasoning tokens, and `thinking.budget_tokens: 256` gave 264 and 585. The model list says `effort_updates: false`. The route returns `reasoning_tokens` in usage but no reasoning text.
- **The harnesses send the expected shape** (offline, scripted server, MiMo configuration). dsh: `max_completion_tokens` 16,000, system prompt "…You are a coding agent powered by the mimo-v2.6-flash model…". omp: body keys `max_completion_tokens, messages, model, store, stream, stream_options, tools` (plus `tool_choice` in compaction), cap 16,000, system prompt SHA-256 `616bebaf…`, which names the model as `zengo/mimo-v2.6-flash`. With Qwen's configuration omp sent `chat_template_kwargs` and `preserve_thinking` instead of `store`.
- **omp compacts at the same point.** With either configuration, auto-compaction fires between 56,000 and 57,000 reported tokens (scripted server), so keeping the 65,024 window keeps omp's context management as in MC-113.

## Goals / Non-Goals

**Goals:**
- Test whether the harness gap (OMPF below DSHF) holds with a second model, on both parts.
- Test whether MiMo's best agent beats its own direct call.
- Report Qwen's numbers on the same items beside, so the model difference in the gap can be read.

**Non-Goals:**
- Tuning MiMo's thinking, cap or prompts, or comparing more than two models.

## Decisions

### 1. Items, arms and draws
| Part | Items | Arms, draws 1 and 2 |
|---|---|---|
| M | 134 Legal MC (corpus_v1) + 112 VMLU law (corpus_v2) = 246 | DSHF, OMPF, B |
| S | 400 ViBidLQA (corpus_v2) | DSHF, OMPF, C |

Attempts: agents 2,584; direct 1,292 (492 B, 800 C). Two draws, as MC-112 to MC-114, because the harness gap on Qwen was detectable at two draws (M1 −8.94, Holm p 0.0008; S1 −4.28, Holm p 0.007).

### 2. The model route (approved by the owner, 2026-11-19)
- **dsh:** `data/diagnostic_legal_agent_mimo/dsh_profile_mimo_v1.yml`, MC-112's profile with the provider (`zengo`), model id, token field (`max_completion_tokens`) and cap (16,000) replaced. Every other row is MC-112's.
- **omp:** `data/diagnostic_legal_agent_mimo/omp_config_mimo_v1.json`, MC-113's configuration with the provider, model id and cap replaced; `--model zengo/mimo-v2.6-flash` in the argument list; `reasoning: false` and `--thinking off`, as MC-113 (the model thinks anyway).
- **Cap 16,000.** The thinking counts toward the cap; MC-112's 4,096 was set for a model that does not think. Whether 16,000 is enough is read from the smoke test before registration.
- **Context window 65,024**, MC-112's, so the harnesses manage context as before (§Context).
- **Proxy:** MC-112's, unchanged in code: temperature 1.0 added, request cap 30, wall clock 3 hours per attempt; the request timeout 600 s (MiMo answers slower than IEC; MC-110 saw replies past 300 s); OpenCode Go's headers (a browser user agent, referer and origin, as `.omp-mimo` needed) and `x-opencode-session`, one session per try of an attempt.
- **Direct arms:** chat completions, no streaming, system prompt "Answer the user's question.", temperature 1.0, cap 16,000, one session per attempt, timeout 600 s, no SDK retries.

### 3. Manifest
`diagnostic_legal_agent_mimo.build_manifest`: MC-115's path (rebuild MC-112's, MC-113's and MC-114's manifests, each equal to its frozen file; take the draw-1 items), copied to `-r1` and `-r2`. Every attempt's task, input, gold and task kind must equal MC-115's for the same item and arm, and every MC-115 item and arm must appear. The manifest records every source and reference hash, both folder hashes, the dsh profile and omp configuration hashes, and self-hashes.

### 4. Runner
`run_legal_agent_mimo.py` reuses MC-115's runner functions that carry no card identity (`check_folders`, the per-item folder, `agent_row`, the smoke tasks) and MC-114's (`finish_agent_row`, `rescore`, `summarize`), and MC-112's and MC-113's sandboxes, proxy and classifiers unchanged. It adds MiMo's route, the per-try session, the provider-error reading of §5, the direct request, reasoning and cached token counts per attempt, and a cost estimate in `summary.json`. Same engine, budget guard, outage guard, statuses and `--resume`.

### 5. Provider errors
- **429** (rate or usage limit) and **401/402/403/404:** the attempt is technical and the launch halts; `--resume` re-runs it once the cause is cleared. This keeps a usage limit from scoring attempts 0.
- **400 that names no content policy** (in its error body or code): technical, re-run by `--resume`. More than 20 attempts with such a 400 halt the run for the owner.
- **400 naming a content policy:** terminal, scored 0, as MC-112's `upstream_4xx`.
- Everything else as MC-112 to MC-115.

### 6. Smoke test (before registration, no benchmark item; owner's go)
MC-112's `smoke-2` on corpus_v1 and MC-114's `smoke-s2` on corpus_v2, each once with DSHF, once with OMPF and once with its direct arm (B, C): 6 attempts. It records status, requests, HTTP statuses, body keys, response model ids, omp's system-prompt hash, tokens (reasoning and cached included) and the largest completion. From it, before registration: the response-model pins (dsh, omp, direct), and the budget guard (the earlier cards' real cost per attempt scaled by the smoke's MiMo-to-Qwen ratio, × 1.5). A smoke attempt that cannot complete blocks registration. If a request ends at the 16,000 cap, the owner decides the cap before registration.

### 7. Operation
At most 4 attempts in flight; stop after 4 timeouts; budget guard from §6. Run as a `systemd-run --user` unit with `--resume` after a technical stop.

### 8. Analysis (fixed before data, run once)
`analyze_legal_agent_mimo`, plan `diagnostic-legal-agent-mimo`.
- **Item score:** the mean over MiMo's draws 1–2. Part M: correctness. Part S: vi-reading-v3 token-F1, in points.
- **Part M (246), Holm over two:** M1 OMPF vs DSHF; M2 DSHF vs B. Margin 2.24 points on both, as MC-115.
- **Part S (400), Holm over two:** S1 OMPF vs DSHF; S2 DSHF vs C. No margin.
- **Statistics,** as MC-112 to MC-115: the mean per-item difference; a 95% percentile bootstrap over items (2,000, seed 7); a two-sided paired sign-flip p-value (20,000, seed 7).
- **Reading rule:** the left arm is better when it leads by more than the margin with a Holm-adjusted p below 0.05, worse when it trails by more than the margin with such a p, otherwise no clear difference.
- **Beside, not tested:** Qwen's same comparisons on the same items, draws 1–2 (MC-111 to MC-114) and draws 1–4 (with MC-115), every score file read by its registered SHA-256; per item, MiMo's OMPF − DSHF minus Qwen's on draws 1–2, with a bootstrap CI; MiMo − Qwen per arm on draws 1–2; Part M by source; per arm, outcomes, requests, tool calls and tokens (reasoning included).

### 9. Registration (MC-116)
A root block in `measurement_card.md`, the detail card `docs/measurement_cards/MC-116-diagnostic-legal-agent-mimo.md` and `data/diagnostic_legal_agent_mimo/registration.json` with every frozen input hashed. The commit is titled `pre-register MC-116` and comes before the first benchmark-item request.

## Risks / Trade-offs

- **Two things change, not one.** MiMo thinks and Qwen does not, and the route differs (OpenCode Go vs IEC). The harness gap of each model is measured within its own card, so the route difference cancels within MC-116; the model difference in the gap is reported, not tested.
- **The harness names the model.** dsh's and omp's system prompts state the model id; they cannot be kept byte for byte across models.
- **Thinking inside the cap.** A long thought can end a response at 16,000 tokens with no answer (`answer_cap`, scored 0). The smoke test shows the largest completion; the registered card reports the share of capped attempts per arm.
- **Usage limit.** OpenCode Go's monthly limit is USD 60 across all models, and other limits may apply. A 429 halts the launch without scoring; resuming waits for the limit.
- **Provider drift.** A changed response-model id halts the run (pinned from the smoke test).
- **Two draws.** As MC-114, the agent-vs-direct question may stay below the detectable gap (MC-115 needed 4 draws for Qwen and still did not settle M2).
