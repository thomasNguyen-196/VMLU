# MC-80 — Muse Spark 1.3 Contributor, direct 9Router API, default reasoning

Registered before dataset inference on 2026-10-13 (Asia/Ho_Chi_Minh).

| Field | Condition |
| --- | --- |
| Model | Exact request route `ocg/muse-spark-1.3-contributor` |
| Transport | Direct OpenAI-compatible Chat Completions; endpoint/key loaded from `9ROUTER_BASE_URL` / `9ROUTER_API_KEY` in `.env`; credentials never persisted |
| Inputs | Frozen `data/vi_multimodel_v1/main_v1.json`: VMLU Valid 744, Vi-SQuAD 200, Vi-DROP 200, Legal MC 146, Legal NLI 150, ViBidLQA 603; total 2,043 unique items; no V-Bench |
| Prompts | Byte-identical frozen user prompts; system message `Answer the user's question.`; no tools; independent request per item |
| Sampling | Temperature explicitly sent as 1.0; seed omitted; reasoning effort omitted. Provider/model default; actual upstream temperature and reasoning effort unknown. Explicit `auto` probes returned HTTP 400. Router settings API denied read access, so provider thinking overrides remain unverified. |
| Router transformations | Send `x-9router-token-saver: off`, the documented opt-out header. Actual forwarded payload is not exposed by the inference endpoint. |
| Concurrency | Four fixed contiguous manifest shards, three dedicated worker lanes per shard; 12 concurrent requests total; no task stealing; one locked output directory and central attempt writer |
| Limits | MC 4,096 tokens; reading 2,048 tokens; reasoning and visible output share the cap; request timeout 300 seconds; SDK retries zero |
| Errors/resume | Save every attempt. Stop scheduling on HTTP 400/401/402/403/404/429. Explicit resume retries missing or technically failed items only. Completed empty/unparsed/length outputs stay in scoring denominators. |
| Scoring | Existing `score_vi_multimodel.score_rows`; accuracy for MC and strict EM/token F1 (`vi-reading-v2`) for reading; frozen legacy diagnostics retained. Headline metrics withheld for incomplete datasets. |
| Provenance | Persist parent manifest, condition, card and runner hashes, raw prompts/responses, returned model ID, finish reason, request ID, usage, latency, shard/lane, and all attempts |
| Cost | 9Router tariff unknown; no dollar estimate inferred. Preserve reported token usage. |
| Output | `all_res/muse13_direct_mc80/main/muse-spark-1-3-contributor-ocg/` |

Existing MC-53 OMP outputs and the current diagnostic pilot are independent historical artifacts. This direct condition changes transport, request model route, concurrency, and reasoning control recording; a difference in score is not a transport-only causal estimate.
