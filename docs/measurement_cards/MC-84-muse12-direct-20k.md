# MC-84 — Muse Spark 1.2 Contributor, API Direct, 20,000 output tokens

Registered 2026-10-14 (+07), before benchmark-item requests, at user request to use the same direct condition as Muse 1.3 and Qwen MC-83.

| Field | Condition |
| --- | --- |
| Model | Muse Spark 1.2 Contributor; pin exact route `ocg/muse-spark-1.2-contributor` for every request. No automatic route substitution |
| Transport | API Direct; native Responses streaming; same API root and request/terminal adapter as MC-82 |
| Sampling | Temperature 1.0 sent; reasoning effort omitted (provider default, effective tier unknown); seed omitted; no tools supplied |
| Prompt | `Answer the user's question.`; frozen V1 main and V2 VMLU user prompts. Gold never sent |
| Budget | `max_output_tokens=20000` on all MC and reading items, including reasoning where metered |
| Scope/order | V1 main 2,043: Valid 744, Legal MC 146, Legal NLI 150, Vi-SQuAD 200, Vi-DROP 200, ViBidLQA Test 603. Then V2 Dev 303 + Test 9,833 = 10,136. Total 12,179, Valid runs once; no V-Bench or synthetic pilot |
| Workers | Four fixed shards × three lanes = 12; no work stealing |
| Recovery | Timeout 300 seconds/request, SDK retries zero; maximum 3 passes per phase. Transient failures saved; per-lane backoff 5 seconds, 503 30 seconds, 429 60 seconds, doubled on consecutive errors up to 300 seconds. 60 seconds between recovery passes |
| Terminal outcomes | Completed/truncated answers never rerun. Empty/unparsed answers remain in denominator. Recognized permanent auth/config/billing errors and tool violations stop execution |
| Scoring | Frozen V1 and V2 scorers; Test gold withheld and submission exported for server scoring |
| Provenance | Separate MC-84 artifacts, condition/source hashes, runner snapshots, attempt ledger, returned model identity and token usage. Earlier Muse 1.2 mixed-route OMP results remain unchanged |
| Comparison | Nominal controls match MC-83 across all datasets and MC-82 Dev/Test. Earlier Muse 1.3 Valid/Legal/reading used smaller/mixed budgets; preserve those labels. Unknown effort tiers and effective upstream sampling are not asserted identical |
| Billing | API tariff unknown; usage retained, no billing inferred |

Outputs `all_res/muse12_direct_mc84/`; log `logs/muse12_direct_mc84.log`. No external upload.
