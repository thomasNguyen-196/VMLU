# MC-79 — Muse Spark 1.2 OCG / VMLU remaining-only continuation

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-79` |
| `trạng_thái` | Registered before OCG inference, 2026-10-12 (+07) |
| `mục_đích` | Continue only the VMLU items not completed by MC-74 after the CMC route reached its weekly quota. MC-74 answers remain attributable to MC-74; this card defines a separate OCG route. |
| `model / API` | Exact request model `ocg/muse-spark-1.2-contributor`, OMP provider `router9`, 9ROUTER Chat Completions through `9ROUTER_BASE_URL`; key from `9ROUTER_API_KEY`, never stored |
| `nguồn / manifest` | Parent manifest SHA256 `553fbd77e318eade604911998251e3a32abf743577c28101f8698632eef6b24a`; MC-74 derived manifest SHA256 `4046145d633931454c8760f8ffb74ae5d2e267bdb6aa02878adba68f8a472655`; MC-74 attempt ledger SHA256 `903794668864e982d7d63c694401973423b3f6bd80cfadec6d0d8d5f4244a817` |
| `sample` | Parent VMLU has 10,880 items: valid 744, dev 303, test 9,833. MC-74 has 7,504 complete answers; MC-79 sends the remaining 3,376 items, all from VMLU test with withheld gold. The 22 MC-74 latest errors are included among the unfinished keys. |
| `harness / prompt` | OMP 18.0.0 JSON; same frozen V2 prompts/parsers; no tools; system prompt `Answer the user's question.`; one isolated OMP process per item; no persisted session |
| `sampling` | Temperature 1.0 enforced by the loopback sampling relay; thinking auto; seed omitted. Upstream effective sampling/reasoning settings are not exposed. |
| `workers / shards` | Four stable contiguous parts of the 3,376 remaining manifest rows (844 each); three concurrent request lanes per part; total concurrency 12; no task stealing. Each answer is recorded with its shard/lane and MC-79 identity. |
| `caps / timeout` | Multiple choice 4,096 completion tokens; 300 seconds/item plus 60 seconds process slack; SDK retries 0; technical recovery remains bounded by the V2 runner. |
| `source / output` | Source MC-74: `all_res/muse_router_matched/vmlu/muse-spark-1-2-contributor/`. MC-79: `all_res/muse12_ocg_vmlu_mc79/vmlu/muse-spark-1-2-contributor-ocg/`. A combined file may be emitted only with per-row route and condition provenance. |
| `scoring` | MC-79 contains only VMLU test items with withheld gold, so no local accuracy is claimed. Any combined CMC+OCG artifact is explicitly mixed-route and must not be reported as one homogeneous condition. No submission is uploaded. |
| `cost` | No 9ROUTER tariff supplied; zero-priced bookkeeping is not a monetary estimate. The existing run cap is 1.00 USD-equivalent. |
