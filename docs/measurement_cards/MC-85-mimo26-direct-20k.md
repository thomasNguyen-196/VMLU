# MC-85 — MiMo V2.6 Flash, API Direct, 20,000 output tokens

Registered 2026-10-15 (+07), before benchmark-item requests, at user request for `ocg/mimo-v2.6-flash` under the existing direct condition.

| Field | Condition |
| --- | --- |
| Model | MiMo V2.6 Flash; exact route `ocg/mimo-v2.6-flash` pinned throughout; no route or model substitution |
| Transport | API Direct; native Responses streaming through the same API root and adapter as MC-82/MC-84 |
| Sampling | Temperature 1.0 sent; reasoning effort and seed omitted; provider-default reasoning, effective tier and temperature unknown; no extra thinking override |
| Tools | None supplied |
| Budget | `max_output_tokens=20000` for both MC and reading; reasoning included where reported by provider |
| Prompt | System `Answer the user's question.` and frozen V1/V2 user prompts; gold not sent |
| Scope/order | Main 2,043: Valid 744, Legal MC 146, Legal NLI 150, Vi-SQuAD 200, Vi-DROP 200, ViBidLQA Test 603. Then Dev 303 + Test 9,833 = 10,136. Total 12,179; Valid runs once; no V-Bench or synthetic pilot |
| Workers | Four fixed shards × three lanes = 12, no work stealing |
| Timeout/recovery | Timeout 300 seconds/request, SDK retries zero; maximum 3 passes/phase. Transient failures saved, backoff 5 seconds, HTTP 503 30 seconds, HTTP 429 60 seconds; consecutive errors double up to 300 seconds per lane; 60 seconds between recovery passes |
| Terminal outcomes | Completed/truncated outcomes are not retried. Empty/unparsed answers remain in scoring denominator. Recognized permanent auth/config/billing failures and tool violations stop execution |
| Scoring | Frozen V1/V2 scorers and Vietnamese normalization; VMLU Test withheld, export id,answer for server grading |
| Provenance | Separate MC-85 output, condition/manifest hashes, source snapshots, attempt ledger, returned model identity and usage. Do not overwrite earlier MiMo OMP runs |
| Comparison | Same nominal request controls as Qwen MC-83 and Muse 1.2 MC-84, and Muse 1.3 MC-82 Dev/Test. Preserve smaller/mixed budgets for Muse 1.3's older main outputs; default reasoning tiers are not claimed equal across models |
| Billing | API tariff unknown; reported token usage retained, no cost inferred |

Outputs `all_res/mimo26_direct_mc85/`; log `logs/mimo26_direct_mc85.log`. No external uploads.
