## Why

MC-112 let Qwen3.5-9B search for itself, inside DeepSeek Harness (`dsh`), over a complete local folder of the Vietnamese legal texts that govern the 134 Legal MC items:

- **DSHF (search required)** scored 85.07 against closed-book B's 86.57 (MC-111). That is no clear difference.
- **DSH (search allowed)** searched in 9.7% of attempts and scored 79.10, worse than B (Holm p .043).
- **Retrieval.** DSHF read the governing provision in 53.7% of attempts. Its accuracy was about the same whether it read the provision or not.

On 2026-11-13 the owner asked whether the same had been measured with `omp`, the coding-agent harness of the earlier harness cards. It has not:

- **MC-15 to MC-29** ran Qwen3.5-9B-28K through `omp` on Legal MC. The working folder held only the prompt, so there was nothing to search. MC-22 and MC-29 later found that those runs had loaded stray instructions and sent no temperature.
- **MC-71** ran Muse Spark 1.3 through `omp` with web search on Legal MC. It searched, but it is a different model.
- **MC-88** ran Qwen3.5-9B-65K through `omp` with the full tool menu. Legal MC was excluded, and Qwen made 3 tool calls in 12,033 items.

So the open question is whether MC-112's result belongs to the model or to dsh. With the same model, items, folder, instruction and analysis, does Qwen search, find and read better or worse inside `omp`? And does that change its answers?

The owner chose the forced-search arm. MC-112's optional arm almost never searched, and MC-88 suggests that Qwen in `omp` would do the same.

## What Changes

- **Items.** MC-112's 134 Legal MC items, two draws each.
- **One arm: OMPF (search required in `omp`).** It has 268 attempts.
  - **Task.** Each task is MC-112's DSHF task for the same item, byte for byte: MC-112's DSHF instruction, a blank line, then the frozen main-v1 MC prompt.
  - **Harness.** `omp` 18.0.0, the binary MC-88 used, pinned by its SHA-256.
- **Reused from MC-112, unchanged and checked by hash:**
  - the corpus folder `corpus_v1` (310 files, folder SHA-256 `5f3240a2…`);
  - the provisions file and the hit rules `seen`, `read` and `opened`;
  - the sandbox design: no network, a fresh home, an empty environment and the folder mounted read-only at `/work/van-ban-phap-luat`;
  - the loopback proxy, which adds `temperature: 1.0`, swaps the key and records every request;
  - the request cap of 30 and the 300 s timeout per request;
  - the attempt statuses.
- **References.** These are not re-run.
  - **DSHF.** From MC-112's score file, by SHA-256.
  - **B and O.** From MC-111's score file, by SHA-256.
- **`omp` settings.**
  - **Tools.** Only `read`, `grep` and `glob` (`--tools read,grep,glob`).
  - **Switched off:** omp's own request retries (enforced by the proxy, because omp still retries a 5xx), the update check, memory, titles, extensions, skills, rules and LSP. omp's session stays in the attempt's fresh home, so that its spill read-back works.
  - **Kept as shipped:** omp's coding-agent system prompt, its read window and summarisation, its grep context lines and paging, its output spill, and its compaction. They are part of the package being compared.
- **Proxy checks added for `omp`.** These are new. Each refuses a request, or pauses the run, when `omp`'s request differs from the registered shape:
  - the request's keys;
  - the 4,096-token answer cap;
  - the system prompt's hash;
  - the task text.
- **Trajectory parser for `omp`'s tool results.** MC-112's hit rules are unchanged. The tool-result formats were recorded offline on 2026-11-13 with a scripted local server and no model.
- **Smoke test before registration.** MC-112's three smoke questions, run with the OMPF instruction, plus one long-answer request. It checks that the gateway honours omp's `max_completion_tokens`. It needs the VPN, so the owner is asked first.
- **Analysis.** It is fixed before data and run once.
  - **Two Holm-adjusted questions:**
    1. OMPF against MC-112's DSHF (the harness);
    2. OMPF against MC-111's B.

    Both cross cards, so both also need the difference to exceed 2.24 points, the gap between MC-101's and MC-111's B.
  - **Description:** search behaviour, retrieval hits beside DSHF's on the same items, accuracy with and without the provision read, and cost.
- **Card.** MC-113, registered and committed before the first benchmark-item request.

## Capabilities

### New Capabilities
- `diagnostic-legal-agent-omp`: the pinned `omp` binary and its configuration, the `omp` sandbox, the proxy's request-shape checks, the OMPF manifest built from MC-112's DSHF tasks, the `omp` status mapping, the `omp` trajectory parser, and the registered analysis.

### Modified Capabilities
- None. These are reused unchanged:
  - MC-112's frozen inputs and modules (`diagnostic_legal_agent.py`, `dsh_proxy.py`, `dsh_relay.py`, `run_legal_agent.py`, `analyze_legal_agent.py`), which are imported, not edited;
  - the frozen main-v1 MC prompt, the extractor and the scorer;
  - the campaign engine;
  - MC-111's and MC-112's outputs, which are read only.

## Evaluation regime

Regime B-style only, as MC-90 to MC-112: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint. Regimes A and C are not touched.

## Non-goals

- **No optional-search arm.** The owner chose the forced arm. It can be added before registration if the owner wants it (design, open choices).
- **No arm that takes `omp` apart.** There is no `omp` without tools, no `omp` with an empty folder and no `omp` with dsh's system prompt. The owner rejected such controls for MC-112.
- **No re-run of DSHF, B or O.**
- **No web access** and no tool other than `read`, `grep` and `glob`.
- **No tuning to an outcome.** The instruction, the configuration, the caps and the folder are not changed after seeing an outcome. The smoke test sets only the budget, the response model id and the system-prompt hash.
- **No second model,** and no other harness (`pi`, `opencode`), in this card.
- **No change** to MC-112's frozen files or modules.
- **No training or fine-tuning.**

## Impact

- **New code**, which imports MC-112's modules without editing them:
  - `code_benchmark/omp_trajectory.py`: the `omp` tool-result parser. It yields MC-112's observation shape, so `provision_hits` is reused as is.
  - `code_benchmark/run_legal_agent_omp.py`: the runner, the `omp` sandbox, the proxy subclass with the request-shape checks, the status mapping and the smoke test.
  - `code_benchmark/analyze_legal_agent_omp.py`: the analysis.
  - Offline tests for each.
- **New data** in `data/diagnostic_legal_agent_omp/`: `protocol.json`, `omp_config_v1.json` (the `config.yml` and `models.yml` written into each attempt's home), `smoke_questions_v1.json`, `manifest_v1.json` and `registration.json`.
- **Outputs** go to `all_res/diagnostic_legal_agent_omp/` (gitignored). The offline probe's evidence is already in `probe_20261113/` there.
- **Requests.**
  - **Volume.** 268 attempts of several requests each, so about 1,500 to 3,000 requests.
  - **Tokens.** Probably 30 to 60 million, most of them re-sent context. omp's system prompt and its grep output are larger than dsh's. The smoke test sets the budget.
  - **Time.** About one to three hours with four attempts in flight. The run needs the VPN.
- **Comparison limits** (written into the card):
  - **Several harness differences at once.** omp and dsh differ in more than one way at the same time: the system prompt, the read window, the grep output and compaction. A difference between OMPF and DSHF belongs to the package as a whole.
  - **Between-card comparisons.** DSHF and B come from earlier cards, so endpoint drift is possible. Hence the 2.24-point margin.
  - **The folder.** It is gold-aware and complete, so it is an upper bound for real search.
  - **The pool** is not held out.
  - **The benchmark's rules.** VLSP 2025 LegalSLM forbids external access at inference.
