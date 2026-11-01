## Context

See `proposal.md` for the motivation.

- **Router v3** (`code_benchmark/diagnostic_calibration.py`, procedure `data/diagnostic_router_v3/procedure_v3.json`) chooses a policy per dataset from 60 calibration items and writes it as a rule of the closed grammar of `code_benchmark/diagnostic_router.py`.
- **The grammar** knows the deployable arms B, S, K and KS. Its probe is arm B answered twice. It refuses arm O.
- **The campaign engine** (`run_diagnostic_prospective.py`) runs any manifest of the arms B, S, O, K and KS, with the registered limits. The scorer `diagnostic_prospective.score_arm_rows` scores B, O and K on the raw response, and S and KS from the last final-answer label.
- **Corpus v0** (`code_benchmark/diagnostic_retrieval.py`) holds the tokenizer and BM25 used by arm K in MC-93.

ViBidLQA has 1,928 train, 482 val and 603 test rows over 863 unique passages (NFC, case-folded, whitespace-collapsed). 1,848 train questions appear once across the three splits. MC-95 used 360 of them, so 1,488 remain.

## Goals / Non-Goals

**Goals:**
- Measure, on questions asked without their passage, what two BM25 passages recover against no passage and against the question's own passage.
- Test whether a frozen 60-item calibration can choose among no retrieval, retrieval, retrieval with reasoning and a cascade between the last two. That choice is the deployable part of an adaptive router.

**Non-Goals:**
- Tuning the retriever, which was chosen in K2.1.
- A router over every dataset at once.
- Any change to the v1, v2 or v3 artifacts.

## Decisions

1. **Task variant and items.**
   - Dataset id `bidlqa-train-retrieval`.
   - The items are the ViBidLQA train questions that appear once across the splits (the pool of `diagnostic_heldout_v3.load_bidlqa_train`), minus the 360 used by MC-95: 1,488 items.
   - Item ids stay `BIDLQA-TR-nnnn`. Gold is the source answer.
   - The sample is the 360 items with the lowest sha256(42, dataset:item). The 60 lowest-ranked are the calibration items. There are no strata.

2. **Corpus and retrieval (`data/diagnostic_k2/retrieval_k2.json`).**
   - **Corpus:** the unique passages of the pinned train, val and test sources. A passage's id is the SHA-256 of its normalized text. The corpus is in id order. A passage's text is its first raw form in the order train, val, test.
   - **Query:** the question as asked.
   - **Scoring:** the corpus v0 tokenizer with bigrams and its BM25 (k1 1.2, b 0.75, Lucene idf, distinct query tokens). Ties keep corpus order.
   - **Kept:** the top 2 passages.
   - **Record:** the manifest records each item's two passage ids and scores, and whether its own passage is among them. The configuration and the corpus hash are registered.

3. **Arms and prompts (two draws each, 360 × 4 × 2 = 2,880 attempts).**

   | Arm | Prompt | Scored on |
   | --- | --- | --- |
   | B (closed book) | `Trả lời câu hỏi sau bằng một cụm từ hoặc số ngắn gọn.\n\nCâu hỏi: <question>\nTrả lời: ` (registered in the protocol) | raw response |
   | K | `build_reading_prompt(<passage 1>\n\n<passage 2>, question)` | raw response |
   | KS | the frozen S reading prompt (`s_reading_head`) on the same two passages | final segment |
   | O | `build_reading_prompt(<own passage>, question)`, the ViBidLQA prompt of MC-95 | raw response |

   K and O differ only in the text in the passage slot, so the gap between them is the retrieval loss. O also repeats MC-95's ViBidLQA B condition on new items, which can reveal endpoint drift.

4. **The K2 procedure (`data/diagnostic_k2/procedure_k2.json`).**
   - **Candidates,** from least to most thorough: `always_B`, `always_K`, `k_cascade`, `always_KS`.
   - **One rotation:** the answering K draw, the second K draw as the probe, the KS draw, and the B draw.
   - **What each candidate returns:**
     - always-B returns B.
     - always-K returns K.
     - always-KS returns KS.
     - The K cascade returns K when the two K answers agree under `normalized-answer-v1`, otherwise KS. Its tokens include both K answers.
   - **Score:** mean token-F1 on the 60 calibration items.
   - **Tie:** the more thorough candidate, that is the later one in the list. Scores within 1e-12 count as equal. The owner chose this after MC-95, where a tie that went to the cheaper policy cost 7.3 points.
   - The file has a closed set of keys, as the v3 procedure does.

5. **Probe arm K in the grammar.**
   - A rule's probe may name arm B or arm K. The other probe checks stay.
   - The semantics are unchanged: the probe answers twice. When the decision is the probe's arm, the first probe answer stands, and a condition with `probe: disagree` escalates.
   - Existing rules validate and route identically.

6. **Rule emission.**
   - always-B, always-K and always-KS each become one condition on the dataset. K and KS name the labels they address.
   - The K cascade becomes two conditions: the dataset with `probe: disagree` goes to KS, then the dataset alone goes to K.
   - The probe `{arm K, 2, normalized-answer-v1}` is declared only for the cascade. The default is B.
   - The router reads the closed-book request: the dataset, the length of the B prompt and the question. It never reads a passage.

7. **The single evaluation (`analyze_diagnostic_router k2`, plan `diagnostic-k2-heldout-v1`).**
   - **Rotations.** Rotation 1 uses draw 1 to answer, draw 2 for the probe, and draw 1 of KS, B and O. Rotation 2 swaps the draws. In each rotation the calibration items choose and the emitted rule routes the 300 test items.
   - **Primary (rotation 1).** The router against always-K and against always-KS on per-item token-F1:
     - a two-sided paired sign-flip test, 20,000 Monte Carlo resamples, seed 7;
     - Holm over the two tests.
   - **Per policy** (the router, always-B, always-K, the K cascade, always-KS and O):
     - mean token-F1 with a percentile bootstrap interval (2,000 resamples, seed 7);
     - exact match with a Wilson interval;
     - mean reported tokens per item, the probe included.
   - **Description:**
     - the calibration scores, choice and cost per rotation;
     - the best candidate on the test items in hindsight and the regret;
     - retrieval hits: the own passage at rank 1 or in the top 2;
     - K, KS and O token-F1 on hits and on misses;
     - the items whose exact match differs between the router and a fixed retrieval policy.
   - The report's top-level keys are registered and checked.

8. **Runner and registration.**
   - `run_k2_heldout.py` follows the v3 runner: the campaign engine, the scorer, the operational limits (4 in flight, breaker after 4 network failures) and the 5,000,000-token guard.
   - Gates:
     - the MC-96 heading and the detail card;
     - the K2 protocol, campaign protocol, templates, retrieval configuration and manifest hashes;
     - the endpoint identity;
     - the procedure hash.
   - Outputs go to `all_res/diagnostic_k2/heldout/<profile>/`.

## Risks / Trade-offs

- **Closed book near zero.** Closed-book B will score near zero, so always-B is unlikely to be chosen. It is the no-retrieval baseline, and the gap measures what retrieval gives.
- **Exact ties are rare under token-F1.** A tie needs two candidates that return equal scores, for example a cascade whose K answers all agree. The tie rule therefore matters less than it did for accuracy in MC-95.
- **The cascade is expensive on reading.** The two B answers disagreed on about 58% of ViBidLQA items in the wide phase. The K cascade will often cost more than always-KS, and the tokens are reported.
- **Not a pristine held-out set.**
  - Calibration and test items can share passages.
  - The bake-off saw the MC-96 questions, though only for retrieval.
  - These limits are stated on the card.
- **One model.** One quantized model at temperature 1.0, so single draws are noisy. Rotation 2 bounds this.

## Migration Plan

New files only, plus the probe-arm extension, which keeps existing rules valid. Nothing registered is rewritten.
