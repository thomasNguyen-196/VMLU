## Why

On 2026-10-28 the project owner set what the adaptive router is:

- **Baseline.** A reading item's input is its passage and its question. That is the baseline. A closed-book prompt fits only knowledge questions that have no passage, such as VMLU.
- **Router.** The router is an LLM. It reads the passage and the question and tells the student model how to work on that question.
- **Groups.** The groups the router uses come from experiments on the student model, so that each question gets what works best for that model.

The thesis outline says the same. Section 4(C) states that B on an open-book task uses the original passage, and that K adds outside evidence; K does not replace the passage. Section (E) asks whether choosing a strategy per question beats a fixed strategy.

MC-96 (K2) departed from this. It hid each item's passage, so its B was closed book, and it answered an open-domain question instead. Under the owner's framing its own-passage arm O is the baseline, and the K2 router (62.0 token-F1) is below O (66.6). Routers v1 to v3 and the K2 cascade read only the dataset, the prompt length, cue words in the question, or the agreement of two answers. None reads the passage.

**What a router could gain.** The wide draws (MC-90 to MC-92: B and S twice each on the 967 reading items) bound what a router choosing between B and S can gain. All scores are token-F1:

| Policy | Score |
| --- | --- |
| always-B | 68.1 |
| always-S | 72.4 |
| best fixed arm per dataset (Vi-SQuAD B; Vi-DROP and ViBidLQA S) | 73.1 |
| per question, chosen on draw 1 and scored on draw 2 | 73.7 |
| per question, chosen and scored on the same draws (luck counted) | 79.0 |

The winner of draw 1 wins again on draw 2 for 61% of ViBidLQA items (282 decided pairs), 74% of Vi-SQuAD and 95% of Vi-DROP. With B and S alone, the dataset already carries most of what a per-question choice can honestly gain. A router needs arms that differ more from question to question.

**Arm Q.** On ViBidLQA the largest loss with a visible pattern is over-long answers: answers that contain the gold and more. They are 24% to 27% of attempts and cost 10 to 12 token-F1 points. Examples are a whole list where one item is asked, or "quy định tại khoản 2 Điều 27 của Nghị định này" where "khoản 2 Điều 27" is the answer. A new arm Q targets this loss. The model first copies the part of the passage that answers, then gives the shortest phrase in it that answers what is asked.

**Owner's choices (2026-10-28):**
- the router model is a stronger model, Muse Spark 1.3;
- the router returns one group name from a closed list, and each group maps to a fixed arm;
- the menu is B, S and Q.

## What Changes

- **Arm Q.** A new reading arm: the registered Q head, then the passage and question of the frozen reading prompt, in the layout of the S reading prompt. It is scored from the text after the last final-answer label, as S is.
- **The campaign module learns Q in two places only:** replicate ids and scoring. `diagnostic_prospective` keeps its campaign arms for protocol validation and prompt building, so no campaign artifact changes.
- **Design run MC-97.** Q answers the 967 wide reading items twice (ViBidLQA test 591, Vi-DROP 188, Vi-SQuAD 188), 1,934 attempts. With MC-90 to MC-92, every design item then has two draws of B, S and Q. The analysis is descriptive.
- **Later steps of this change.** Each is registered on its own card before its first request:
  - **Router design.** The closed list of groups and the Muse Spark 1.3 router prompt (passage and question in, one group out) are written from the design draws. The router labels the design items, and a registered rule maps each group to the arm with the best design score.
  - **Single held-out evaluation.** It runs on fresh ViBidLQA items with their passages. Each item gets B, S and Q twice and one router call.
    - The router is compared with always-B, the baseline, and with always-S, using paired sign-flip tests with Holm.
    - The router's own tokens are counted in the cost.
    - always-Q and the per-dataset rule are described, not tested.

## Capabilities

### New Capabilities
- `diagnostic-quote-arm`: arm Q (prompt and scoring), the menu design set, and the MC-97 run gates.
- `diagnostic-llm-router`: the router's input and output, groups and mapping from experiments, and the held-out evaluation.

### Modified Capabilities
None. The protocols, manifests, rules, procedures and cards of MC-90 to MC-96 stay as registered. The campaign module accepts Q only in replicate ids and in scoring.

## Non-goals

- No closed-book baseline on reading items: every reading arm gets the passage.
- No free-form instruction from the router. A free-form instruction could carry the answer, and then the score would no longer measure the student model.
- No training or fine-tuning of the router or the student model; the thesis outline rules out fine-tuning the base model.
- No new B or S draws on the design items.
- MC-96 stays registered. Its result is a side result about retrieval, not a router result.

## Evaluation regime

The student model is the regime B-style condition of MC-90 to MC-96: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint. The router model, Muse Spark 1.3, is reached through a commercial route; its card will name the route.

## Impact

- **Code:**
  - `code_benchmark/diagnostic_prospective.py`: arm Q in replicate ids and scoring;
  - `code_benchmark/diagnostic_menu.py`: the Q prompt and the menu manifest;
  - `code_benchmark/run_menu_q.py`: the MC-97 runner;
  - tests for each.
- **Data:** `data/diagnostic_llm_router/` holds the protocol, the menu manifest and the registration.
- **Cards:** MC-97 now; the router cards later.
- **Endpoint use:** about 1,934 attempts and 1.6 million reported tokens over the IEC VPN for MC-97.
