# Draft measurement card: diagnostic prospective wide (B / S on 1,239 non-anchor items)

SUPERSEDED: registered on 2026-10-22 as MC-90 (`measurement_card.md` and `docs/measurement_cards/MC-90-diagnostic-prospective-wide.md` are authoritative; where they differ from this draft, they win). Original draft note follows. DRAFT, not registered. At registration (task 6.4) assign the next free card id, fill the dates and hashes, copy the first block into `measurement_card.md` as a new `## MC-NN` section and the second block into `docs/measurement_cards/MC-NN-diagnostic-prospective-wide.md`, and commit with the title `pre-register MC-NN`. This card does not require `inference_ready`: it touches no audit anchor, so it may run as soon as it is registered and its prompts are frozen.

## Root block (for measurement_card.md)

## MC-NN — Qwen3.5-9B-65K (IEC) / diagnostic prospective wide / B and S on the 1,239 non-anchor items

| Field | Condition |
| --- | --- |
| `card_id` | `MC-NN` |
| `status` | DRAFT; to be preregistered YYYY-MM-DD (+07), before benchmark-item requests |
| `scope` | The 1,239 items of the five non-VMLU datasets of the MC-72 scope that are not audit anchors (134 Legal MC, 138 Legal NLI, 188 Vi-SQuAD, 188 Vi-DROP, 591 ViBidLQA); arms B and S; 1 replicate; 2,478 attempts |
| `harness / tools` | Direct API, no harness, no tools; OpenAI Responses API, streaming |
| `model / route` | Qwen3.5-9B-65K via the IEC internal gateway `http://llmapi.iec/v1` through the openvpn3 `member-shared-tcp` tunnel; self-reported `/home/llm/llama.cpp/models/Qwen3.5-9B-Q4_K_M.gguf` |
| `sampling / limits` | Temperature 1.0 requested; effective value unverified; seed and reasoning field omitted; `max_output_tokens=4096` for both arms; 300 s timeout; no SDK retries; campaign cap 5,000,000 reported tokens shared with the core card |
| `workers / scheduler` | 12 workers (4 shards x 3 lanes); items ordered item-major so B and S of one item run adjacently |
| `details` | `docs/measurement_cards/MC-NN-diagnostic-prospective-wide.md` |
| `outputs` | `all_res/diagnostic_prospective/wide/qwen3-5-9b-65k-prospective/`; no upload |

## Detail card (for docs/measurement_cards)

# MC-NN — Qwen3.5-9B-65K (IEC), diagnostic prospective wide: B and S on the 1,239 non-anchor items

Registered YYYY-MM-DD (+07) before benchmark-item requests. Companion of the core card; the design is `openspec/changes/diagnostic-prospective-campaign`.

| Field | Condition |
| --- | --- |
| Model / route | Same endpoint, model identity, transport, sampling, caps and connectivity as the core card; self-reported `Qwen3.5-9B-Q4_K_M.gguf` on llama.cpp (Q4_K_M, not BF16). |
| Role | Effect-size and held-out set: arms B and S are scored automatically, so no human label limits n. It is held-out only with respect to rule design (the rule-based router is tuned on the core anchors and evaluated once here); every item was evaluated by earlier runs, so none is pristine. |
| Scope | The non-anchor items of the five datasets of the MC-72 scope, derived from the frozen main-v1 manifest minus the 60 locked anchors: 134 Legal MC, 138 Legal NLI, 188 Vi-SQuAD, 188 Vi-DROP, 591 ViBidLQA (1,239 items). VMLU and V-Bench are excluded. One replicate per arm: 2,478 attempts. |
| Arms and prompts | B is the frozen main-v1 prompt, byte-identical (hash-checked for every item); S is the stepwise wording of the core card with the same template SHA-256 `<set at registration>`. No evidence arms. |
| Inputs and manifest | Run identity `dataset:item:<ARM>-r1`; manifest SHA-256 `<set at registration>`; send no gold. |
| Token, time, retries, workers | As in the core card (4,096 output tokens, 300 s, no SDK retries, 12 workers, item-major order, resume only under an identical frozen condition). |
| Scoring | As in the core card: frozen scorers for B, final-segment rule for S, unparsed answers kept in denominators, format compliance reported separately. |
| Gates | This card heading in `measurement_card.md`, the registration record with matching hashes, endpoint host and model equal to this card. `inference_ready` is not required because no audit anchor is touched. |
| Analysis | As in the core card, on single attempts: paired rescue and regression, exact McNemar with Holm correction, Wilson intervals, passage-cluster bootstrap. No oracle-routing ceiling is read as headroom: one draw per arm gives no noise floor. |
| Provenance and outputs | `condition.json` with all hashes, per-attempt usage and response model id, outputs under `all_res/diagnostic_prospective/wide/qwen3-5-9b-65k-prospective/`. |
| Comparison limits | Q4_K_M weights on a non-thinking endpoint; one temperature-1.0 draw per item and arm; shared infrastructure that may drift; exact-match reading scores are depressed by units and formatting equally in both arms; historical MC-72 results used a different harness and are not a comparison arm. |
