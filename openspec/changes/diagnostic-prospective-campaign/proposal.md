## Why

`diagnostic-protocol-ledger-pilot` froze the 60-anchor audit set and left every intervention arm as a definition: there is no runner, prompt set, manifest, evidence contract or arm-aware scoring rule, so `inference_ready` can never open. A 2026-10-22 probe of the IEC endpoint changed the planning assumptions: inference is cheap (about 5 s and 250 output tokens per attempt; 24 requests finished in 42 s) and the served model is a non-thinking `Qwen3.5-9B-Q4_K_M.gguf` on llama.cpp. The binding constraints are therefore human audit effort and corpus scope, not compute. Legal MC-146 spans many legal areas (traffic and administrative penalties, enterprise and investment, land, labour and insurance, tax, criminal, civil) and only 24 of its 146 questions name a numbered document, so a retrieval corpus for the whole set cannot be frozen before the 2026-10-31 milestone, while evidence-first contrasts on the audited Legal MC anchors can.

## What Changes

- Add a versioned arm contract `data/diagnostic_prospective_v1/` (protocol, prompt templates, evidence schema) for five arms: **B** (frozen prompt), **S** (visible stepwise decomposition, same input), **O** (oracle evidence taken from the audit, frozen prompt), **K** (retrieved evidence, frozen prompt) and **KS** (retrieved evidence plus S wording).
- Define two phases: **core** (the 60 audit anchors, three replicates; O, K and KS only on the Legal MC anchors whose audited input lacks the needed provisions and whose gold is valid) and **wide** (the 1,239 non-anchor items of the same five datasets, arms B and S, one replicate), so that effect sizes come from automatic scoring and a held-out split exists without extra human labels.
- Add `code_benchmark/diagnostic_prospective.py` (contract, prompt builders, manifests, scoring wrapper, evidence validator) and `code_benchmark/run_diagnostic_prospective.py` (driver on the MC-82/83 direct-API engine). The default mode is an offline preflight with `endpoint_calls=0`; `--execute` fails closed without a pre-registered measurement card and, for `core`, without `inference_ready`.
- Score arm B and the direct-answer arms with the frozen scorers unchanged; score the reasoning arms (S, KS) from a pre-registered final-answer segment and report format compliance as its own metric instead of folding it silently into accuracy.
- Add offline analysis code (paired rescue, regression and net gain; exact McNemar; Wilson and passage-cluster bootstrap intervals; Holm correction; noise-floor oracle-routing ceiling; two-direction discordant-pair export) with synthetic-data tests, written before any prospective data exist.
- Add a rule-based router that picks one of the deployable arms B, S, K and KS per item from features known at request time (dataset, prompt length, question cue words). Amended 2026-10-26: the rule is designed on wide, frozen by hash before the first core request and evaluated once on core against fixed arms, the deployable ceiling and the B-replicate null.
- Ship the pre-registration package as a draft inside this change. Copying values into `data/diagnostic_v1/protocol.json` is deferred until the audit report is final, because the SHA-256 of that file binds the review page, review import, adjudication and the draft keys of the reviewer.

## Capabilities

### New Capabilities
- `diagnostic-prospective-run`: arm-aware frozen manifests, preflight-first runner, fail-closed execution gates, frozen condition, resume, process-local endpoint resolution and usage accounting.
- `diagnostic-arm-scoring`: per-arm answer extraction and scoring, format-compliance reporting, paired outcome definitions, discordant-pair export and the noise-floor routing ceiling.
- `diagnostic-evidence-contract`: oracle and retrieved-evidence artifacts, eligibility, corpus provenance, retrieval trace and the frozen evidence block.
- `diagnostic-router`: rule grammar over runtime features, freeze before the core run, one evaluation on core.

### Modified Capabilities

<!-- None. The diagnostic specs of diagnostic-protocol-ledger-pilot are not yet in openspec/specs/, and the frozen eval-scoring behavior is intentionally unchanged. -->

## Regime

Touches Regime A prompts and protocol (capability under the gateway's default chat template) but on Q4_K_M quantized weights, which PROPOSAL.md classes as Regime B-style; this is recorded as a threat to validity rather than hidden. Regime C (reasoning-token budgets) is not touched: arm S is visible decomposition under one fixed output cap, not a budget sweep.

## Non-goals

- Learned router, RL or harness learning, runtime verifier, transfer to a second model, matched-language variants.
- A retrieval corpus for all of Legal MC-146 or any open-domain corpus; K stays a pilot on the audited Legal MC anchors.
- Changing frozen prompts, frozen scorers, historical runs, `data/eval_set_manifest.csv`, the pilot packet or `data/diagnostic_v1/protocol.json` while the human review is in progress.
- Tooling for human review of campaign outputs (a separate change once results exist), automatic semantic judging, VMLU test or other withheld-gold sets, leaderboard uploads.

## Impact

- New: `data/diagnostic_prospective_v1/`, `code_benchmark/diagnostic_prospective.py`, `code_benchmark/run_diagnostic_prospective.py`, `code_benchmark/test_diagnostic_prospective.py`, an oracle-evidence builder, an analysis module, a router module and their tests, four specs, and a draft pair of measurement cards (ids assigned at registration).
- Read-only dependencies: `vi_multimodel.py` (main-v1 manifest, `EvalItem`, frozen extractors), `score_vi_multimodel.py`, the `run_muse13_direct_*` engine, the `diagnostic.py` readiness report and `all_res/diagnostic_v1/pilot-review-v4/` (anchor selection).
- Model and endpoint for any later run: Qwen3.5-9B-65K, self-reported `/home/llm/llama.cpp/models/Qwen3.5-9B-Q4_K_M.gguf`, `http://llmapi.iec/v1` over the IEC VPN (OpenVPN 3 profile `member-shared-tcp`).
- No change to CI gates and no web change.
