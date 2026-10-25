# MC-80 persistent incomplete replies: diagnosis

Investigated 2026-10-13T22:20:09.700120+07:00.

## Findings

1. Confirmed upstream output-budget exhaustion: native Responses streams report `response.incomplete`, `status=incomplete`, `incomplete_details.reason=max_output_tokens`, and output usage equal to the configured cap. Reasoning consumes nearly all of that budget before a visible answer.
2. Confirmed installed 9Router 0.5.99 aggregation defect: the SSE-to-JSON parser in compiled module 81626 (`8895.js`) handles `response.completed`/`response.done` and `response.failed`, but ignores `response.incomplete`. Its initial `status=in_progress` and zero usage survive into the returned response. The client therefore sees an empty Chat Completion with misleading status and metering.
3. The MC-80 adapter classified those replies as technical request errors and retried them. That classification is incorrect for confirmed output-budget truncations; repeating an identical request can succeed when the model uses fewer reasoning tokens, but does not remove the budget limitation. Completed-after-retry results are not a clean single-attempt baseline.

## Diagnostic probes

| Item | API probe | Cap | Terminal state | Output tokens | Reasoning tokens | Incomplete reason | Evidence |
| --- | --- | ---: | --- | ---: | ---: | --- | --- |
| 7048 | chat-json | 2048 | in_progress | 0 | None | not surfaced | [7048-chat-json-2048-1791904361864101566.json](../../all_res/muse13_direct_mc80/diagnosis/7048-chat-json-2048-1791904361864101566.json) |
| 7048 | responses-stream | 2048 | incomplete | 2048 | 2045 | max_output_tokens | [7048-responses-stream-2048-1791904411977327683.json](../../all_res/muse13_direct_mc80/diagnosis/7048-responses-stream-2048-1791904411977327683.json) |
| 7048 | responses-stream | 8192 | completed | 5430 | 5409 |  | [7048-responses-stream-8192-1791904537332667259.json](../../all_res/muse13_direct_mc80/diagnosis/7048-responses-stream-8192-1791904537332667259.json) |
| 898 | responses-stream | 2048 | incomplete | 2048 | 2045 | max_output_tokens | [898-responses-stream-2048-1791904498861327362.json](../../all_res/muse13_direct_mc80/diagnosis/898-responses-stream-2048-1791904498861327362.json) |
| BIDLQA-T-0125 | responses-stream | 2048 | completed | 1225 | 1202 |  | [BIDLQA-T-0125-responses-stream-2048-1791904485331246580.json](../../all_res/muse13_direct_mc80/diagnosis/BIDLQA-T-0125-responses-stream-2048-1791904485331246580.json) |
| BIDLQA-T-0404 | responses-stream | 2048 | completed | 1666 | 1586 |  | [BIDLQA-T-0404-responses-stream-2048-1791904508455121486.json](../../all_res/muse13_direct_mc80/diagnosis/BIDLQA-T-0404-responses-stream-2048-1791904508455121486.json) |
| BIDLQA-T-0513 | responses-stream | 2048 | incomplete | 2048 | 2045 | max_output_tokens | [BIDLQA-T-0513-responses-stream-2048-1791904517053976042.json](../../all_res/muse13_direct_mc80/diagnosis/BIDLQA-T-0513-responses-stream-2048-1791904517053976042.json) |
| LG-0056 | responses-stream | 4096 | incomplete | 4096 | 4093 | max_output_tokens | [LG-0056-responses-stream-4096-1791904505399369577.json](../../all_res/muse13_direct_mc80/diagnosis/LG-0056-responses-stream-4096-1791904505399369577.json) |
| LG-0082 | responses-stream | 4096 | completed | 3521 | 3510 |  | [LG-0082-responses-stream-4096-1791904502640155448.json](../../all_res/muse13_direct_mc80/diagnosis/LG-0082-responses-stream-4096-1791904502640155448.json) |

At the original caps, direct incomplete terminal evidence was captured for Vi-DROP 7048, Vi-SQuAD 898, Legal MC LG-0056, and ViBidLQA BIDLQA-T-0513. Three other persistent items completed on fresh native streaming probes at their existing caps. Their earlier terminal frames were not saved, so budget exhaustion on each historical attempt is an inference, not individually proven.

The isolated larger-cap probe for 7048 completed with cap 8192, using 5430 output tokens including 5409 reasoning tokens. This is a diagnostic condition only; its answer is not inserted into MC-80.

## Reproduction

Live original-condition symptom: `.venv/bin/python .codex/debug_mc80_response.py --item 7048 --cap 2048` returned HTTP 200, empty content, `finish_reason=in_progress`, zero usage, and exit code 1.

Offline replay: `node .codex/test_9router_incomplete_repro.cjs` executes the installed parser against the sanitized captured terminal event. Its completed control passes; its incomplete assertion fails with actual `in_progress`/0 output tokens versus expected `incomplete`/2048. No model calls are needed for that regression.

## Required correction and benchmark implications

Handle `response.incomplete` as a terminal outcome, preserve `incomplete_details` and all usage details, and map `max_output_tokens` to a truncation (`finish_reason=length`) for scoring. Empty/unparsed outputs must stay in the denominator. The experiment should not wait indefinitely for nonempty answers under a cap that the model already exhausted.

For a condition with larger budgets, preregister a distinct card/condition and retain provenance. Do not silently replace original-cap outputs with the 8192-token diagnostic answer or describe those as the original condition.

Audit the original attempt ledger before drawing strict one-attempt comparisons: recovery selected completed generations after earlier failures. The existing frozen scorers themselves are unchanged.

This investigation changed neither the installed router nor benchmark predictions/scores/caps. Diagnostic scripts and sanitized traces are retained separately. MC-81 remains behind the existing completion gate pending a correction to outcome handling.
