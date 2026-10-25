# MC-78 — Muse Spark 1.3 CMC / four-worker V-Bench continuation

| Field | Value |
| --- | --- |
| `card_id` | `MC-78` |
| registration | 2026-10-11 (+07), before four-worker inference; user explicitly requested four fixed parts |
| model / route | `cmc/meta/muse-spark-1.3-contributor` through 9ROUTER, same CMC route as MC-77 |
| retained results | {"MC-76": 468, "MC-77": 383}; all completed answers preserved, including empty/invalid responses; incomplete requests remain pending |
| new scope | 4290 remaining V-Bench items; four dedicated fixed parts of sizes [1073, 1073, 1072, 1072]; no task stealing |
| manifest | Frozen parent e44d5642fe5726f7265917917cbf35e2d4e2e199ccbdcd3e95e81b650f9f0b12; derived 5f10ed5ffe8e0a2e99a75fc9cc20dbe88c76e0446ec819444cc5cd74d0b0261f; source ledger hashes in condition manifest |
| inference | OMP 18.0.0 JSON, tools none, temperature 1.0 enforced on outgoing relay, thinking auto, seed omitted; system prompt Answer the user's question.; one isolated process/item with temporary HOME/absolute agent/scratch paths, no history |
| caps / timeout | MC 4096; function-call 2048; 300 seconds/item plus 60 process slack; connectivity probe 256; SDK retries 0 |
| scoring / output | Frozen V2 diagnostics for continuation scope; combined 5141-item artifact records route and source condition per item. Withheld gold requires server grading; no upload. Output all_res/muse13_cmc_vbench_mc78 |
| budget | No tariff supplied; zero equivalent is not a monetary estimate; frozen item counts/caps/timeouts and four-worker bound |
