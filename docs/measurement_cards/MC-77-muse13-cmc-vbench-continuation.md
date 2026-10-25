# MC-77 — V-Bench continuation through Muse Spark 1.3 CMC

| Field | Value |
| --- | --- |
| `card_id` | `MC-77` |
| registration | 2026-10-11 (+07), before remaining dataset inference |
| model / route | Exact `cmc/meta/muse-spark-1.3-contributor` through 9ROUTER, OMP provider router9; environment credentials only |
| request scope | 4673 unfinished V-Bench items; preserve 468 completed MC-76 answers including empty/invalid model answers; only unfinished requests continue |
| manifest | Parent `e44d5642fe5726f7265917917cbf35e2d4e2e199ccbdcd3e95e81b650f9f0b12`; remaining condition `86287c021f133212784a7618b6658f9cf77c187a3555b67af9c00102206171c2`; source attempt ledger `6657eba966ec55fd45509ebd6fa0c1d813af568b048d76422dc61d4ed9ef9669` |
| workers | 2 fixed contiguous parts of remaining manifest, no task stealing |
| OMP / sampling | OMP 18.0.0 JSON; no tools; thinking auto; temperature 1.0 enforced at outgoing relay; seed omitted; system prompt Answer the user's question.; process/item; isolated temporary HOME/agent/scratch; no conversation history |
| caps / timeout | MC 4096; function-call 2048; 300 seconds/item plus 60 process slack; probe cap 256 outside dataset; SDK retries 0 |
| scoring / provenance | Frozen V2 parser and withheld-gold policy. MC-77 diagnostics report only remaining-item scope. Combined 5141-item artifact explicitly labels original Free and CMC routes per item; never present as a homogeneous route/model evaluation. Server required for correctness; no upload |
| output | all_res/muse13_cmc_vbench_mc77; preserves source MC-76 artifact directory |
| tariff | Not supplied; zero bookkeeping rate is not a cost estimate |
