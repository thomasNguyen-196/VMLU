# MC-81 — Muse Spark 1.3 Contributor / remaining VMLU Dev and Test

Registered 2026-10-13 (+07) before dataset inference. Starts only after MC-80 completes.

| Field | Condition |
| --- | --- |
| Model/transport | `ocg/muse-spark-1.3-contributor`; direct 9Router Chat Completions; same endpoint as MC-80; credentials read from `.env` and never persisted |
| Scope | Dev 303 + Test 9,833 = 10,136; frozen `data/vi_multimodel_v2/vmlu_v2.json` parent; Valid 744 excluded after identity and byte-level prompt parity against MC-80 |
| Controls | Same MC-80 request controls: temperature sent 1.0; seed/effort omitted; default reasoning with unknown effective tier; no tool definitions supplied; system `Answer the user's question.`; `x-9router-token-saver: off` |
| Execution | Four fixed contiguous shards × three lanes = 12 workers; 4,096-token MC cap; 300-second request timeout; SDK retries zero |
| Recovery | Sequential campaign permits up to three passes, skipping completed items and retaining every technical failure. Stop on configuration/auth/quota errors. Every executed runner version is archived and hashed. |
| Scoring | Frozen expansion-V2 parser/scorer: Dev local accuracy only with complete coverage; Test gold withheld, so parser validity and submission answers only; no fabricated Test accuracy |
| Outputs | `all_res/muse13_direct_mc81/vmlu/muse-spark-1-3-contributor-ocg/`; full 10,880-item convenience artifact combines MC-80 Valid with MC-81 Dev/Test using per-row card provenance; Test CSV emitted only when Test coverage is complete |
| Provenance | Derived manifest and parent/source hashes, MC-80 condition/predictions hashes, returned model IDs, finish reasons, raw outputs, usage, timing, worker assignments, all attempts |
| Billing | 9Router tariff unknown; preserve provider-reported usage; no external submission/upload |

The campaign recovers only unfinished MC-80/MC-81 requests. It never reruns a completed answer based on correctness. V-Bench remains outside the campaign.
