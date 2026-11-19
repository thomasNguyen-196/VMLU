## Why

MC-112 to MC-115 measured the legal agent on one model only, Qwen3.5-9B. Their clearest result is that the harness is a variable of the measurement: with the same model, folder and task, omp scores below dsh (MC-115, 4 draws: −7.4 points on 246 multiple-choice items, Holm p 0.0003; −2.6 token-F1 on 400 ViBidLQA items, Holm p 0.023). The exploratory mechanism analysis of MC-114 put the ViBidLQA gap on omp's paged reads, which Qwen does not page through, and the multiple-choice gap on the answering step. Both could be properties of the small model rather than of the harness.

A second model answers this. The owner chose MiMo-V2.6-Flash (2026-11-19: "vậy chạy tiếp cho MiMo V2.6 Flash đi"), already used in MC-103 to MC-110, over GLM-5.3-Flash, which has no other result in the thesis. The owner approved the design on 2026-11-19 ("duyệt"): thinking at the provider's default (it cannot be set on this route), a 16,000-token cap per response, MC-112's 65,024-token context window kept, and the whole of MC-115's design in one card.

## What Changes

- **MC-115's arms, items and folders with MiMo.** DSHF (dsh) and OMPF (omp), forced search, plus each part's no-tool baseline (B on Part M, C on Part S), on MC-115's 646 items, two draws each: 3,876 attempts.
  - **Part M, 246 items:** MC-112/113's 134 Legal MC items on corpus_v1 and MC-114's 112 VMLU law items on corpus_v2.
  - **Part S, 400 items:** MC-114's ViBidLQA items, closed-book, on corpus_v2.
- **Same tasks.** Each attempt is the frozen draw-1 item of its arm, as MC-115 copied it, with replicate ids `-r1` and `-r2`. The build checks every task, input and gold hash against MC-115's manifest.
- **Only the model route changes in the harnesses.** MC-112's dsh profile and MC-113's omp configuration with the provider, the model id, the token field and the per-response cap replaced. Tools, sandbox, relay, proxy, limits, context window and leak guards stay. The proxy forwards to OpenCode Go with the provider's headers and one routing session per try.
- **Direct arms** send MiMo's direct request of MC-103 to MC-110 (chat completions, system prompt "Answer the user's question.", no streaming) with this card's cap and temperature 1.0, the values every arm sends.
- **Provider errors** are read for OpenCode Go: a 429 (rate or usage limit) halts the launch and its attempt is re-run later; a 400 that names no content policy is technical.
- **Smoke test** on the two registered smoke questions (DSHF, OMPF and the direct arm each), with the owner's go. It sets the response-model pins and the budget.
- **Analysis,** fixed before data and run once: M1 OMPF vs DSHF and M2 DSHF vs B (Holm over two); S1 OMPF vs DSHF and S2 DSHF vs C (Holm over two). Qwen's numbers on the same items are reported beside, with the model difference in the harness gap, without tests.
- **Card MC-116,** registered and committed before the first benchmark-item request.

## Capabilities

### New Capabilities
- `diagnostic-legal-agent-mimo`: MC-115's agent arms and baselines on a second model, the MiMo route through the unchanged harnesses, OpenCode Go's error handling, and the registered two-draw analysis with the Qwen comparison beside.

### Modified Capabilities
- None. Reused and not edited: MC-112's to MC-115's modules, frozen inputs, manifests and score files; the frozen MC and reading prompts and scorers; the campaign engine; MiMo's model registry entry.

## Evaluation regime

MiMo-V2.6-Flash through OpenCode Go (`opencode.ai`, chat completions), thinking at the provider's default. This is a diagnostic condition with external tools, outside VLSP 2025's rules, as MC-112 to MC-115.

## Non-goals

- **No new items, arms or folders.** DSH and O are not run.
- **No thinking setting.** The route does not honour one (probe 2026-11-19); the card records this rather than working around it.
- **No change to the earlier cards.** Their registered results stand; Qwen's numbers appear only beside.

## Impact

- **New code** (offline, tested): `code_benchmark/diagnostic_legal_agent_mimo.py` (protocol, harness overlays, manifest), `code_benchmark/run_legal_agent_mimo.py` (runner, self-test, smoke test), `code_benchmark/analyze_legal_agent_mimo.py` (analysis), and a test module for each.
- **New data** in `data/diagnostic_legal_agent_mimo/`: `protocol.json`, `dsh_profile_mimo_v1.yml`, `omp_config_mimo_v1.json`, `manifest_v1.json`, `registration.json`.
- **Outputs** in `all_res/diagnostic_legal_agent_mimo/` (gitignored).
- **Requests:** 2,584 agent attempts (Part M 984, Part S 1,600) and 1,292 direct requests (492 B, 800 C); no VPN.
- **Tokens and money:** about 190M reported tokens if MiMo costs what Qwen did per attempt; the smoke test sets the budget guard. At OpenCode Go's listed MiMo prices (USD 0.14 per million input, 0.0028 cached, 0.28 output) that is roughly USD 7 with most input cached and USD 27 with none, against the plan's USD 60 monthly limit shared by every model.
