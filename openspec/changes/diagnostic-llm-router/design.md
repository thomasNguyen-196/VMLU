## Context

See `proposal.md` for the motivation.

- **The campaign engine** (`run_diagnostic_prospective.py`) runs a manifest of replicate ids `<ARM>-r<k>` with the registered limits. It reads each row's arm through `diagnostic_prospective.arm_of_replicate`.
- **The scorer** `diagnostic_prospective.score_arm_rows` scores B, O and K on the raw response, and S and KS from the last final-answer label. On reading items, the frozen V1 reading extractor then takes the first line after the last label.
- **The campaign protocol** validates that its arms are exactly B, S, O, K and KS. `build_arm_prompt` builds those arms from an item's frozen main-v1 prompt.
- **The wide phase** (`wide_v1.json`, MC-90) holds 1,239 items. 967 of them are reading items:

  | Dataset | Items |
  | --- | --- |
  | ViBidLQA test | 591 |
  | Vi-DROP | 188 |
  | Vi-SQuAD | 188 |

  MC-91 and MC-92 added a second B and a second S draw on every wide item.
- **Two sources of the facts used here:** the per-question numbers in `proposal.md` come from those four draws, computed offline. The failure types come from token precision and recall against the gold.

## Goals / Non-Goals

**Goals:**
- Give every design item two draws of each menu arm (B, S, Q), so that the router's groups and the mapping from group to arm can be fitted to this model's measured behaviour.
- Keep the change additive: no registered artifact or campaign behaviour changes.

**Non-Goals:**
- Writing the router's groups or prompt before the Q draws exist.
- Any test of Q against B or S at this stage; MC-97 is descriptive.

## Decisions

1. **Arm Q prompt.**
   - The head is registered in `data/diagnostic_llm_router/protocol.json`.
   - The prompt is: head + the passage of the item's frozen main-v1 reading prompt + `\n\nCâu hỏi: ` + question + `\n`. This is the layout of the S reading prompt, which also has no `Trả lời: ` tail.
   - The head asks the model to copy the part of the passage that answers into a line `Trích dẫn: …`. It then asks for the shortest phrase or number from that copy that answers what is asked, without the document name, article or clause number, or an explanation unless the question asks for them. The last line must be `Trả lời: …`.
   - `Trích dẫn` is not a final-answer label of the frozen extractor (`đáp án cuối|đáp án|trả lời|final answer|answer`), so the quoted line is never scored.

2. **Arm Q in the campaign module, scoring and replicate ids only.**
   - `CAMPAIGN_ARMS` = B, S, O, K, KS keeps the protocol check and `build_arm_prompt` as they were, so `build_arm_prompt(item, "Q")` is refused.
   - `ARMS` = `CAMPAIGN_ARMS` + Q is what a replicate id may carry, which is what the engine and the scorer read.
   - `FINAL_LABEL_ARMS` = S, KS, Q are scored from the last final-answer label, with the format flags of S.
   - B, S, O, K and KS score exactly as before.

3. **Items.**
   - The menu set is the B-r1 rows of `wide_v1.json` for the three reading datasets, in manifest order.
   - Each row maps to its frozen main-v1 item `dataset:item:main-000`. That item's prompt must hash to the row's `prompt_sha256`, its MC-90 B prompt; any difference stops the build.
   - The counts are checked: 591, 188, 188.
   - Two Q draws per item, item-major. The manifest is self-hashed like the campaign manifests, and frozen as `menu_q_v1.json`.

4. **Protocol inheritance.**
   - The protocol names the campaign protocol and the wide manifest as parents, and inherits the model, transport, scoring and budget blocks. It copies none of them, and the loader refuses a copy.
   - The manifest records the campaign protocol's SHA-256, so a change there is still caught.
   - The protocol therefore holds no endpoint address.

5. **Runner and gates (`run_menu_q.py`).**
   - It follows `run_k2_heldout.py`: the campaign engine, the scorer, the operational limits (4 in flight, breaker after 4 network failures) and the campaign's 5,000,000-token guard.
   - The gates are:
     - the MC-97 heading and the detail card;
     - the registered hashes of the menu protocol, campaign protocol, wide manifest and menu manifest;
     - the campaign's endpoint and model.
   - Outputs go to `all_res/diagnostic_llm_router/menu/<profile>/`.

6. **MC-97 analysis (plan `diagnostic-menu-q-v1`).** Descriptive only, on the 967 items, with B and S from MC-90 to MC-92:
   - per dataset and arm: mean token-F1, exact match and reported tokens;
   - the per-item winner and whether it repeats on the other draw;
   - the bounds for choosing per question (choose on one draw and score the other; the same-draw bound);
   - the best fixed arm per dataset;
   - each arm's failure types.

7. **The router (registered later, before its first request).**
   - **Input:** the item's passage and question, no gold and no outcome.
   - **Output:** one group name from a closed list; anything else routes to a registered default arm.
   - **Model:** Muse Spark 1.3, the owner's choice.
   - **Groups:** a closed list with definitions, written from the MC-97 analysis and frozen before any router request.
   - **Mapping:** the router labels the design items. A registered rule then gives each group the arm with the highest mean token-F1 on the design items it labelled. Ties go to the more thorough arm (B < Q < S), as the owner chose for K2. A group with too few design items takes the overall best arm.
   - **Held-out:** 300 fresh ViBidLQA train items with their passages, from the 1,128 that MC-95 and MC-96 did not use.
     - Each item gets B, S and Q twice and one router call.
     - Primary: the router against always-B and against always-S on token-F1, with paired sign-flip tests and Holm.
     - Tokens per item include the router's, reported apart because the router is another model.

## Risks / Trade-offs

- **Q may cut answers short.** "The shortest phrase" can drop items of an answer that is itself a list, and Q may suit Vi-DROP calculations less well than S. That is the point of a menu: such questions should map to B or S.
- **Cross-run comparison.** B and S ran on 2026-10-22 and Q runs later. An endpoint drift would bias the comparison. MC-96's O showed no drift against MC-95; the card states the limit.
- **Design data reused.** The design items also served routers v1 to v3, so they are design data only.
- **Held-out set is legal only.** Vi-SQuAD and Vi-DROP have no gold-labelled items left outside the wide and core phases, so groups that mostly hold Vi-DROP questions will rarely appear in the held-out set.
- **Router cost.** A router that reads the passage costs about as much as another prompt. Its tokens are counted, and an accuracy gain has to pay for them.

## Migration Plan

New files, plus the two-constant change in `diagnostic_prospective.py`, which keeps every campaign artifact valid and every existing arm's scoring identical. Nothing registered is rewritten.
