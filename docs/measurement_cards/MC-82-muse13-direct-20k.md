# MC-82 — Muse Spark 1.3 Contributor, direct API, 20,000 output tokens

Registered 2026-10-13 (+07) before larger-budget benchmark requests.

| Field | Condition |
| --- | --- |
| Model | Exact route `ocg/muse-spark-1.3-contributor`, same 9Router endpoint as MC-80 |
| Budget | `max_output_tokens=20000` for every new recovery and VMLU request; includes reasoning plus visible output |
| Other controls | Temperature sent 1.0; effort and seed omitted; default reasoning with unknown named tier; no tools supplied; same frozen prompts and minimal system message |
| Wire protocol | Native Responses streaming to capture `response.completed`, `response.incomplete`, and `response.failed` correctly; budget and wire format both differ from MC-80 |
| Scope/order | Seven unfinished MC-80 items first, then VMLU Dev 303 + Test 9,833. Freeze the selected recovery keys before calls; skip every completed item on resume |
| Workers | Four fixed shards × three lanes = 12 workers for the large phase; small recovery phase has only seven distinct tasks |
| Timeout/retries | 300 seconds/request, SDK retries zero; up to three passes for genuine technical failures; completed and budget-truncated outcomes never retried |
| Terminal limits | `response.incomplete` with reason `max_output_tokens` is a terminal truncation, mapped to `finish_reason=length`; empty/unparsed answers remain in scoring denominators; actual usage retained |
| Scoring | Frozen V1 scorer for recovery and combined descriptive views; frozen V2 scorer for Dev/Test; Test gold withheld and no local Test accuracy claimed |
| Combined artifacts | Preserve original MC-80 outputs. Recovery answers live in MC-82; combined views explicitly mark mixed output budgets and retain per-row measurement-card provenance. Full VMLU includes original-cap Valid 744 plus 20k Dev/Test |
| Outputs | `all_res/muse13_direct_mc82/`; recovery and vmlu phase directories; condition/manifest hashes, runner sources, all attempts, visible responses, usage and terminal reasons |
| Billing | 9Router tariff unknown; larger budget is an upper limit, not tokens necessarily consumed; preserve reported token usage; no external uploads |
