## Why

Arm K has not yet helped. In the core run (MC-93), BM25 put the cited article among its three for 7 of the 8 Legal MC evidence anchors, yet K was right on 4 of them against B's 6, while O (the cited article alone) was right on all 8. The extra articles pulled the model off the answer. K2 asks two questions on a task where the right evidence is known exactly:

- Does a small amount of retrieved text, two passages, recover what the passage gives?
- Can the calibration procedure of router v3 decide whether to retrieve and how much to reason?

That second question is the question of Adaptive-RAG, answered by a 60-item calibration instead of a trained classifier.

ViBidLQA fits. Every answer is a span of its passage, and the 863 unique passages of the train, val and test splits form a closed corpus. The exploratory offline bake-off (K2.1, no model call, 1,928 train questions) compared four retrievers by how often the question's own passage was found:

| Retriever | Passage at rank 1 | Passage in the top 3 |
| --- | --- | --- |
| BM25 v0 | 64.7% | 84.3% |
| BGE-M3 dense | 49.2% | 68.5% |
| Hybrid of the two (RRF) | 60.8% | 78.5% |
| Reranker over the hybrid top 20 (500 questions) | 67.4% | 86.6% |

- BM25 v0 is the corpus v0 tokenizer and BM25 over ViBidLQA passages.
- On the same 500 questions BM25 scored 64.2% and 83.2%, so the reranker added about 3 points at about 24 s per question on CPU.
- BM25 v0 ranks the passage first or second for 78.1% of questions. The answer string is in one of its two passages for 88.2%.

The project owner chose BM25 v0 with the top two passages, without a dense retriever or a reranker.

Router v3 (MC-95) also showed a weakness. On VM14K its 60 calibration items tied always-B with the v2 cascade, the tie went to the cheaper always-B, and the test items lost 7.3 points. The owner chose that in K2 a tie goes to the more thorough candidate.

## What Changes

- **A new task variant.** ViBidLQA train questions are asked without their passage, as dataset `bidlqa-train-retrieval`. There are 360 items that MC-95 did not use: 60 calibration items and 300 test items.
- **A frozen corpus and retriever.**
  - The corpus is the 863 unique passages of the pinned ViBidLQA splits.
  - The retriever is BM25 v0: NFC, lower case, syllables plus adjacent pairs, k1 1.2, b 0.75.
  - The query is the question, and the two best passages are kept.
  - The manifest records each item's ranking.
- **Four arms, two draws each, 2,880 attempts:**
  - **B**, closed book: a new registered prompt that asks the question alone.
  - **K**: the frozen reading prompt with the two retrieved passages in the place of the passage.
  - **KS**: the frozen S reading prompt with the same two passages.
  - **O**: the frozen reading prompt with the question's own passage, which is the ViBidLQA prompt of MC-95. O is a ceiling and is not deployable.
- **The K2 calibration procedure.**
  - It has four candidates, from least to most thorough: always-B, always-K, the K cascade, always-KS.
  - The K cascade answers with K twice; when the two answers differ, the item goes to KS.
  - Candidates are scored by mean token-F1 on 60 calibration items.
  - A tie goes to the more thorough candidate.
  - The choice is written as a rule of the closed router grammar.
- **The router grammar's probe may be arm K.** Every other part of the grammar and every existing rule stays as it is.
- **A single evaluation (MC-96).**
  - In each rotation, the calibration items choose the policy and the emitted rule routes the test items.
  - The primary test uses rotation 1: the router against always-K and against always-KS on token-F1, with paired sign-flip tests and Holm.
  - The closed-book arm, the O ceiling, exact match, tokens and retrieval hit rates are reported as description.

## Capabilities

### New Capabilities
- `diagnostic-k2-retrieval`: the closed-book task variant, the frozen passage corpus and BM25 top-2 retrieval, the prompts of the four arms, and the MC-96 set and its run gates.
- `diagnostic-k2-router`: the K2 calibration procedure (candidates, score, tie toward the more thorough candidate), the K probe in the router grammar, the rule emission, and the single evaluation.

### Modified Capabilities
None. The rules, procedures, protocols, manifests and cards of MC-90 to MC-95 stay as registered. Rules with a B probe validate and route as before.

## Non-goals

- No dense retriever, hybrid or reranker.
- No corpus beyond the ViBidLQA passages, and no new run of arm K on Legal MC.
- No combined router over every dataset and arm yet. That is the next step once MC-96 is read.
- No claim of a pristine held-out set:
  - ViBidLQA train items share passages with each other and with the val and test splits.
  - The K2.1 bake-off chose the retriever on all train questions, including the MC-96 items. It measured retrieval only, never an answer.

## Evaluation regime

Regime B-style only, as MC-90 to MC-95: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint. Regimes A and C are not touched.

## Impact

- **Code:**
  - a K2 module for the corpus, retrieval, items, prompts, manifest and procedure;
  - a probe-arm extension in `code_benchmark/diagnostic_router.py`;
  - a runner on the campaign engine;
  - a `k2` evaluation in `code_benchmark/analyze_diagnostic_router.py`;
  - tests for all of these.
- **Data:** `data/diagnostic_k2/` holds the protocol, retrieval configuration, procedure, manifest and registration.
- **Cards:** MC-96 in `measurement_card.md` and `docs/measurement_cards/`.
- **Endpoint use:** about 2,880 attempts and 3 million reported tokens over the IEC VPN.
