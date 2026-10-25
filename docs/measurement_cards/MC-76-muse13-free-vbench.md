# MC-76 — Muse Spark 1.3 Contributor Free / V-Bench

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-76` |
| `trạng_thái` | Preregistered 2026-10-11 (+07), before dataset inference |
| `model / API` | Exact request model `oc/muse-spark-1.3-contributor-free`, OMP provider `router9`, 9ROUTER Chat Completions; `9ROUTER_BASE_URL` and `9ROUTER_API_KEY` resolved at execution; secrets never stored |
| `dataset` | V-Bench v2026.03.28: MC 4,141 plus agentic 1,000 = 5,141; 4,000 safety/open rows excluded by existing frozen protocol |
| `partition` | Two stable contiguous manifest parts: worker 1 = 2,571 items, worker 2 = 2,570 items; one dedicated thread per part; no task stealing |
| `manifest` | Frozen parent `e44d5642fe5726f7265917917cbf35e2d4e2e199ccbdcd3e95e81b650f9f0b12`; derived `e1316a9760be864f33545944af4a3c566c5cdfaaa134e677089feaecf11d8671`; all parent item/prompt/schema rows byte-preserved |
| `harness` | OMP 18.0.0 JSON; no tools; system prompt `Answer the user's question.`; thinking auto; one isolated process/item; temporary HOME, absolute per-item agent dir, no persisted session |
| `sampling` | Temperature 1.0 enforced on outgoing requests by loopback relay; no seed. Upstream effective sampling/reasoning not exposed. Same inference condition as previous Muse runs, but 2 workers instead of 4 as explicitly requested |
| `caps / timeouts` | MC 4096 tokens; function-call 2048; 300 seconds/item plus 60 process slack; connectivity probe 256, outside dataset; SDK retries 0; existing bounded recovery only for technical failures |
| `scoring` | Frozen V2 parser/schema diagnostics. Correctness gold withheld: server grading required, no fabricated accuracy. Invalid model answers remain in denominator; no selective retries |
| `cost` | No 9ROUTER tariff supplied; zero bookkeeping rate is not a monetary estimate. Fixed coverage/caps/timeouts/concurrency |
| `outputs` | `all_res/muse13_free_vbench_mc76/vbench/muse-spark-1-3-contributor-free/`; automatic offline scoring on complete coverage; no external upload |
