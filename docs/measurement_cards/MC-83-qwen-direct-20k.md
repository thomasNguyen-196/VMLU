# MC-83 — Qwen3.5-9B-65K, API Direct, 20,000 output tokens

Registered 2026-10-14 (+07) before benchmark-item requests. User requested Qwen under the Muse direct condition.

| Field | Condition |
| --- | --- |
| Model | Exact served ID `Qwen3.5-9B-65K`; validated via models API. IEC endpoint from OPENAI_BASE_URL, retained privately in configuration/provenance |
| Transport | API Direct; native Responses streaming, same request shape and terminal handling as MC-82 |
| Sampling | Temperature 1.0 sent; reasoning/effort omitted (provider default, effective tier unknown); seed omitted; no tools supplied |
| System and input | `Answer the user's question.`; frozen V1 main and V2 VMLU user prompts, gold never sent |
| Budget | `max_output_tokens=20000` for every new MC and reading request, including reasoning and visible answer where the provider meters reasoning |
| Scope | First V1 main: Valid 744, Legal MC 146, Legal NLI 150, Vi-SQuAD 200, Vi-DROP 200, ViBidLQA Test 603 = 2,043. Then V2 Dev 303 + Test 9,833 = 10,136. Total 12,179; Valid runs once. No V-Bench or synthetic pilot |
| Workers | Four fixed shards × three lanes = 12; no work stealing |
| Timeout/recovery | 300 seconds/request, SDK retries zero; at most 3 passes per phase. Transient errors retained; lane backoff 5 seconds, HTTP 503 30 seconds, HTTP 429 60 seconds, doubled for consecutive errors up to 300 seconds; 60 seconds between recovery passes |
| Terminal outcomes | Budget truncation is terminal and remains in the denominator. Completed answers never rerun. Recognized permanent authentication/configuration/billing errors and tool violations stop execution |
| Scoring | Frozen V1 and V2 scorers; EM/token-F1 retain Vietnamese accents. Test has withheld gold; export id,answer CSV when complete for server grading |
| Provenance | Separate MC-83 outputs, source hashes, snapshots and attempt ledger. Preserve all historical Qwen and Muse artifacts. Default reasoning tiers and upstream effective temperature are not asserted equivalent |
| Connectivity | Existing IEC VPN; current internal DNS verified; process-local hosts overlay only, no system hosts changes |
| Comparison | Dev/Test match nominal MC-82 controls. Muse Valid and original Legal/reading retain smaller or mixed budgets, so those comparisons must retain per-dataset budget labels |
| Billing | No per-token tariff supplied; do not infer provider billing from token counts |

Outputs: `all_res/qwen_direct_mc83/`, logs `logs/qwen_direct_mc83.log`. No external uploads.
