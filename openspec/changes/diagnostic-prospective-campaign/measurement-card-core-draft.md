# Draft measurement card: diagnostic prospective core (B / S / O on the 60 audit anchors)

DRAFT, not registered. At registration (task 6.4) assign the next free card id, fill the dates and hashes, copy the first block into `measurement_card.md` as a new `## MC-NN` section and the second block into `docs/measurement_cards/MC-NN-diagnostic-prospective-core.md`, and commit with the title `pre-register MC-NN`. Old blocks are never edited and conditions are never merged.

## Root block (for measurement_card.md)

## MC-NN — Qwen3.5-9B-65K (IEC) / diagnostic prospective core / B, S, O on the 60 audit anchors

| Field | Condition |
| --- | --- |
| `card_id` | `MC-NN` |
| `status` | DRAFT; to be preregistered YYYY-MM-DD (+07), after `audit-report.json` is final and before benchmark-item requests |
| `scope` | The 60 audit anchors of the locked pilot (12 each: Legal MC, Legal NLI, Vi-SQuAD, Vi-DROP, ViBidLQA); arms B and S on all 60, arm O on the Legal MC anchors with reviewer-cited provisions; 3 replicates; 396 attempts when 12 oracle records exist. Arms K and KS are not part of this card |
| `harness / tools` | Direct API, no harness, no tools; OpenAI Responses API, streaming |
| `model / route` | Qwen3.5-9B-65K via the IEC internal gateway `http://llmapi.iec/v1` through the openvpn3 `member-shared-tcp` tunnel; self-reported `/home/llm/llama.cpp/models/Qwen3.5-9B-Q4_K_M.gguf` |
| `sampling / limits` | Temperature 1.0 requested; effective value unverified; seed and reasoning field omitted; `max_output_tokens=4096` for every arm; 300 s timeout; no SDK retries; campaign cap 5,000,000 reported tokens |
| `workers / scheduler` | 12 workers (4 shards x 3 lanes); items ordered item-major so the arms and replicates of one item run adjacently |
| `details` | `docs/measurement_cards/MC-NN-diagnostic-prospective-core.md` |
| `outputs` | `all_res/diagnostic_prospective/core/qwen3-5-9b-65k-prospective/`; no upload |

## Detail card (for docs/measurement_cards)

# MC-NN — Qwen3.5-9B-65K (IEC), diagnostic prospective core: B / S / O on the 60 audit anchors

Registered YYYY-MM-DD (+07) before benchmark-item requests. Successor of the offline work in `diagnostic-protocol-ledger-pilot`; the design is `openspec/changes/diagnostic-prospective-campaign`.

| Field | Condition |
| --- | --- |
| Model / route | Qwen3.5-9B-65K served by the IEC internal gateway (`http://llmapi.iec/v1`, plain HTTP inside the IEC VPN tunnel), direct API, OpenAI Responses API with streaming. The endpoint self-reports `/home/llm/llama.cpp/models/Qwen3.5-9B-Q4_K_M.gguf` (llama.cpp, Q4_K_M quantization), observed 2026-10-22 on 168 requests; weights are therefore Regime B-style, not BF16. Keep MC-56, MC-70, MC-72, MC-83 and MC-88 separate: they used different transports, harnesses or budgets. |
| Connectivity | IEC VPN via `openvpn3` (`member-shared-tcp`). `llmapi.iec` resolves only through the tunnel DNS (172.16.30.1 to 172.16.50.172); the runner maps it inside its own process and leaves the `Host` header, system resolver and hosts file untouched. |
| Scope | The 60 ordered anchors of the locked pilot (pilot content SHA-256 `<set at registration>`): 12 each of Legal MC, Legal NLI, Vi-SQuAD, Vi-DROP and ViBidLQA, drawn from MC-72 with seed 42 and exposed as `development-audit`. Arms B and S run on all 60; arm O runs only on Legal MC anchors that have validated reviewer-cited provisions. Three replicates per arm and item. |
| Arms and prompts | B is the frozen main-v1 prompt, byte-identical (hash-checked for every item). S replaces the answer-only instruction by a stepwise-decomposition instruction with a pinned final line and drops the completion cue; question, options and passage are untouched. O prepends one frozen evidence block of verbatim provisions to the B prompt. Template SHA-256 `<set at registration>`; wording developed only on synthetic prompts (`synthetic-dev-results.md`: 72/72 final-label compliance, wording unchanged since the first draft). |
| Inputs and manifest | Run identity `dataset:item:<ARM>-r<k>`; manifest SHA-256 `<set at registration>`; evidence SHA-256 `<set at registration>`; parent main-v1 manifest SHA-256 recorded in the manifest. Send no gold. |
| Sampling | Temperature 1.0 requested; effective value not observable; seed omitted; reasoning field omitted (the endpoint reports no reasoning tokens); system prompt `Answer the user's question.`; header `x-9router-token-saver: off`. |
| Token and time limits | `max_output_tokens=4096` for every arm; request timeout 300 s; no SDK retries. Campaign cap 5,000,000 reported tokens: the runner pauses without further requests when reached. Attempts with unreported usage are not counted (unknown, not zero). |
| Workers and scheduling | 12 workers (4 contiguous shards x 3 lanes) from the MC-80/82/83 engine; item-major order. |
| Retries | No in-run retry of a failed item; `--resume` re-attempts only items without a completed response under an identical frozen condition. Completed responses, including truncated or unparsed ones, are terminal. Authentication, permission, model-identity and budget errors pause the run. |
| Scoring | B and O: frozen V1 scorers on the raw response. S: score from the text after the last final-answer label (`diagnostic-final-segment-v1`); a multiple-choice response without the label is unparsed and the first-match parser is not applied to the whole response; reading uses the frozen last-label extraction. Unparsed answers stay in denominators; format compliance is reported separately. Reading correctness is exact match; token-F1 >= 0.8 with exact match 0 is a semantic-audit candidate only. |
| Gates | Execution requires this card heading in `measurement_card.md`, the registration record with matching hashes, endpoint host and model equal to this card, and `inference_ready` from the diagnostic readiness report (audit complete and every control registered). |
| Analysis | Fixed before data: strict-majority item outcome, rescue and regression, exact two-sided McNemar per arm versus B inside the multiple-choice and reading families with Holm correction, Wilson intervals for recovery and regression, passage-cluster bootstrap (2,000 resamples, seed 42) for net gain, oracle-routing ceiling always next to the ceiling over B replicates, discordant pairs exported in both directions. Per-dataset results are descriptive only. |
| Provenance and outputs | Record manifest, template, protocol, evidence, runner, wrapper and scorer hashes in `condition.json`, per-attempt usage and response model id, and all outputs under `all_res/diagnostic_prospective/core/qwen3-5-9b-65k-prospective/`. |
| Comparison limits | Q4_K_M weights on a non-thinking endpoint; temperature 1.0 makes single draws noisy; the endpoint is shared infrastructure and may drift (the runner pauses on a model-id change); n = 60 development items, descriptive only, not an estimate of benchmark-wide rates; items were evaluated by earlier runs, so none is pristine held-out; the O arm covers only the audited Legal MC anchors (about six B-incorrect items). |
