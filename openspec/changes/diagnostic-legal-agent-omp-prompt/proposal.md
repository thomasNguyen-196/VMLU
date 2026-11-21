## Why

With the same 646 items, folders and tasks, the better harness depends on the model:
- **Qwen3.5-9B:** omp scores below dsh, −8.94 points on multiple choice and −4.28 token-F1 on ViBidLQA (draws 1–2).
- **MiMo-V2.6-Flash:** omp scores above dsh, +5.69 and +7.36 (MC-116).

The exploratory split by step of the agent loop (`docs/research/legal-agent-interaction-2026-11-20.md`; plan hashed before the MiMo stage numbers) places most of that interaction in the answering step, not in reaching the governing article:
- **Multiple choice:** 93.5% of 14.44 points.
- **ViBidLQA:** 58% of 11.64.
- **Items where both harnesses read the article:** OMPF − DSHF is −16.2 for Qwen and +6.3 for MiMo.

The largest difference in what the model sees when it answers is omp's default system prompt: 8,641 characters of coding-agent conventions (RFC 2119 terms, action mandates) against dsh's 441. The owner chose to test this harness component first (2026-11-20: "okay làm 3 đi"). The alternative was the model property (thinking), which the IEC gateway cannot switch on (probe 2026-11-20).

## What Changes

- **New arm OMPS:** omp 18.0.0 exactly as OMPF, with one change. `--system-prompt` replaces omp's default prompt body with dsh's system prompt for the same model, verbatim:
  - Qwen: 441 characters, `d6bd65aa…`.
  - MiMo: 442 characters, `54d89951…`.

  omp still appends its own `<workstation>` and `<critical>` blocks (offline capture, 2026-11-20). The first system message becomes 1,104 (Qwen) or 1,108 (MiMo) characters instead of 8,641 or 8,644. Tools, sandbox, proxy, limits, task bytes and the user-turn reminder do not change.
- **Two models, two draws, the same items:** MC-115's 646 items, Part M 246 and Part S 400, with OMPS at draws 1 and 2. That is 1,292 attempts per model and 2,584 in all.
  - **Qwen3.5-9B-65K:** through IEC over the VPN, in MC-115's route and configuration.
  - **MiMo-V2.6-Flash:** through OpenCode Go, in MC-116's route and configuration.
- **Comparators are the registered score files, read by SHA-256:**
  - Qwen's OMPF and DSHF draws 1–2 (MC-112, MC-113, MC-114);
  - MiMo's OMPF and DSHF draws 1–2 (MC-116).
  No OMPF or DSHF attempt is re-run.
- **Runner fixes for this card only,** in new code; the registered runners stay unchanged:
  - A halted or blocked row carries its identity fields (MC-116's `_blocked_row` defect).
  - A stream that ends with no model-bearing chunk (a provider stall) counts as a technical failure, re-run by `--resume`. A response that names another model still halts the run.
- **Smoke test** with the owner's go: MC-112's `smoke-2` and MC-114's `smoke-s2` with OMPS, once per model, 4 attempts. It sets each model's system-prompt pin and budget.
- **Analysis,** fixed before data and run once. Per part:
  - P1: Qwen's OMPS − OMPF;
  - P2: MiMo's OMPS − OMPF;
  - P3: the model difference in that change.

  Holm over the three. The remaining interaction is reported beside, without a test: (OMPS − DSHF) of MiMo minus that of Qwen.
- **Card MC-117,** registered and committed before the first benchmark-item request.

## Capabilities

### New Capabilities
- `diagnostic-legal-agent-omp-prompt`: the OMPS arm (omp with dsh's system prompt) for Qwen and MiMo on MC-115's items, the stall and blocked-row handling, and the registered test of whether omp's default prompt carries the model × harness interaction.

### Modified Capabilities
- None. The following are reused and not edited:
  - MC-112's to MC-116's modules, frozen inputs, manifests and score files;
  - the frozen prompts and scorers;
  - the campaign engine;
  - the harness pins.

## Evaluation regime

A diagnostic condition with external tools, outside VLSP 2025's rules, as in MC-112 to MC-116:
- **Qwen:** non-thinking, served by IEC.
- **MiMo:** thinking at the provider's default, through OpenCode Go.

## Non-goals

- **No other harness component.** `<critical>`, `<workstation>`, paging, grep formatting and compaction stay as omp sends them.
- **No thinking manipulation** (not available on IEC).
- **No new items, no change to DSHF or OMPF, no re-run of earlier arms.**

## Impact

- **New code** (offline, tested):
  - `code_benchmark/diagnostic_legal_agent_omp_prompt.py`: protocol, overlays, manifest;
  - `code_benchmark/run_legal_agent_omp_prompt.py`: runner with `--model qwen|mimo`, self-test, smoke test;
  - `code_benchmark/analyze_legal_agent_omp_prompt.py`;
  - their tests.
- **Changed:** `code_benchmark/diagnostic_prospective.py` gains the arm id `OMPS` (appended to `ARMS`, scored like OMPF), as MC-112 to MC-114 added DSH, DSHF, OMPF and C.
- **New data** in `data/diagnostic_legal_agent_omp_prompt/`: the protocol, both dsh prompt texts, the manifest and the registration.
- **Requests:**
  - Qwen: 1,292 agent attempts on IEC, with the VPN open during its run.
  - MiMo: 1,292 agent attempts on OpenCode Go.
  - Smoke: 4 attempts.
- **Tokens and money:**
  - Qwen costs nothing per token. Its OMPF used 93M tokens per 1,292 attempts in MC-115.
  - MiMo's OMPF used 103.7M tokens, about USD 5. OMPS sends about 2,500 fewer system tokens per request, so about USD 4–5 is expected.
  - The smoke test sets both budget guards.
- **Time:** about 4–5 h for Qwen and about 6 h for MiMo. The two routes are separate, so the runs can overlap.
