# Synthetic prompt-development results (task 5)

Recorded 2026-10-22. These are calibration checks on **self-generated synthetic prompts with known answers**; no benchmark item text was used or sent, and none of the synthetic prompts equals a frozen main-v1 prompt (checked by SHA-256 against all 2,041 distinct frozen prompts). They are not results of the study.

## Setup

- Harness: `code_benchmark/run_diagnostic_prompt_dev.py` (generator, arm builders, the campaign runner's own `request`, the arm scoring wrapper). Reproduce with `--seed 101 --run` and `--seed 202 --run`.
- Model and endpoint: Qwen3.5-9B-65K, self-reported `/home/llm/llama.cpp/models/Qwen3.5-9B-Q4_K_M.gguf`, `http://llmapi.iec/v1` over the IEC VPN (OpenVPN 3 profile `member-shared-tcp`), resolver shim via `172.16.30.1`.
- Request shape: OpenAI Responses API, streaming, `temperature=1.0`, no seed or reasoning field, system prompt "Answer the user's question.", `x-9router-token-saver: off`, output cap 4096, 6 workers.
- Item sets: seed 101 and seed 202, each 36 items (18 multiple choice from six generators, 18 reading from three passage generators), each sent as arm B and arm S = 72 requests per seed.
- Frozen at the time of the runs: `data/diagnostic_prospective_v1/prompt_templates_v1.json` SHA-256 `9bcada89b93a1e011f32379278dae1a8c829cecc2b1c2be4a5740a7ef7df9481`, `protocol.json` SHA-256 `9284c5fdc25ad95ddf1d264bb78a00962f6baa1a99c6e2aaeb68f5e287cdc914` (afterwards extended with the `analysis.metrics` name list only, no request-affecting field; now `edd7acf2749094c893418184d4e14c338cd5e9dae7f7c56b1063e5f61a55eea6`). The S wording is the first draft; it was not changed after seeing any output.

## Acceptance rule and outcome

Rule (design Decision 4): final-label compliance of arm S at least 95% on at least 36 prompts.

| Seed | Requests | Request errors | S final-label compliance | Markdown on reading final line | Truncated |
|---|---|---|---|---|---|
| 101 | 72 | 0 | 36/36 (MC 18/18, reading 18/18) | 0 | 0 |
| 202 | 72 | 0 | 36/36 (MC 18/18, reading 18/18) | 0 | 0 |
| Combined | 144 | 0 | 72/72 = 100% (Wilson 95% lower bound about 94.9%) | 0 | 0 |

Outcome: the rule is met on both sets, so the draft S wording stands unchanged and is ready to be frozen at registration (its hash goes into `registration.json`, not before).

## Sanity observations (not evidence)

| Arm | Seed | MC correct | Reading EM (token-F1) | Completion tokens mean / max | Mean latency |
|---|---|---|---|---|---|
| B | 101 | 3/18 | 6/18 (0.58) | 3 / 7 | 5.3 s |
| S | 101 | 15/18 | 11/18 (0.76) | 363 / 1551 | 9.6 s |
| B | 202 | 6/18 | 6/18 (0.57) | 3 / 8 | 5.3 s |
| S | 202 | 15/18 | 9/18 (0.69) | 363 / 1031 | 9.6 s |

- The synthetic multiple-choice items are deliberately multi-step (discount chains, rates, orderings, recurrences, date arithmetic); a non-thinking model answering with one letter is near or below chance on them, while the stepwise prompt recovers most. This shows the pipeline can register a rescue; it says nothing about the benchmark items.
- Reading EM is depressed by units ("7 ngày" against gold "7"), a property of the frozen exact-match scorer shared by both arms.
- The largest S output was 1,551 tokens, well under the 4,096 cap; no attempt was truncated.
- All 144 responses carried the expected self-reported model id (the runner pauses on a change).
