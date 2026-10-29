## Why

MC-100 measured the ceiling of retrieval on Legal MC. Handed the provision that governs each question (arm O), Qwen3.5-9B fixed most of the items it had missed and kept the ones it got right:

- items B had missed: 37.0% with fresh B against 82.6% with O (+45.7 points, p 0.0004);
- items B had answered correctly: 94.0% against 96.0%.

The registered reading rule was met, so a retrieval study on Legal MC is worth building. But O's provisions were located by agents who knew the gold, so MC-100 says nothing about whether a retriever finds them. In MC-93, BM25 over corpus v0 put the cited article among its top three for 7 of the 8 Legal MC evidence anchors, yet arm K, given those three articles, lost points while O gained.

This change asks the deployable question. With a corpus built from the questions alone and the campaign's BM25, does arm K beat arm B on Legal MC as a whole, and how much of O's gain does it keep?

On 2026-10-29 the project owner chose a question-based corpus ("kho theo câu hỏi"): agents read the questions without the answers, choose the laws and decrees that govern them, and add older versions and distractor documents. It is faster than a broad corpus. Retrieval will be easier than in practice, and the card says so.

## What Changes

- **Items.** All 134 Legal MC items of the wide phase, the MC-100 pool. The MC-100 strata (`wrong`, `right`) and its frozen oracle evidence are reused for the mechanism analysis.
- **Corpus `vi-legal-corpus-lmc-v1`.**
  - Four agents read the question stems only (no options, no gold, no MC-100 file) and list the documents that govern each question, their predecessors and a few distractors. All documents come from hethongphapluat.com.
  - Each page is stored with its SHA-256.
  - Code extracts the articles verbatim. An article over 6,000 characters is split into parts at line boundaries.
  - A leak check runs, and the corpus is frozen before any retrieval query.
- **Retrieval.**
  - BM25 with the settings of corpus v0 (`bm25-article-v0`), untuned.
  - The query is the question and options exactly as the B prompt carries them.
  - The top 2 units are kept: the same evidence budget as O, which has at most two provisions.
  - Every item's ranking is frozen in the K evidence file before registration.
- **Arms.** Two draws each, 642 attempts, on the campaign's engine and route.
  - B: the frozen main-v1 MC prompt.
  - K: the campaign evidence block with the two retrieved units, then the same prompt.
  - O: MC-100's frozen oracle evidence, then the same prompt, on the 53 items that have it.
- **Analysis.** It is fixed before data and run once.
  - Primary: always-K against always-B on the 134 items. A reading rule decides whether K becomes the Legal MC arm of the router.
  - Descriptive: per MC-100 stratum, K against B and K against O; retrieval hits against the MC-100 oracle articles; the gold check; tokens.
- **Card.** MC-101, registered before the first request.

## Capabilities

### New Capabilities
- `diagnostic-legal-retrieval`: the question-based legal corpus, its retrieval, the frozen K evidence and manifest, the runner gates and the registered analysis of the Legal MC retrieval test.

### Modified Capabilities
- None. The campaign's engine, templates and scorer, and the frozen files of MC-100, are reused unchanged.

## Evaluation regime

Regime B-style only, as MC-90 to MC-100: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint. Regimes A and C are not touched.

## Non-goals

- No dense, hybrid or reranking retriever. In the K2.1 bake-off BM25 led on ViBidLQA; another retriever is considered only if the hit rates here are low.
- No broad corpus (Bộ pháp điển); the owner declined it for time.
- No router change. This step decides whether K should be the Legal MC route; building that route is a later change.
- No Legal NLI, and none of the 12 core Legal MC anchors (MC-93 already ran K on them with corpus v0).
- No tuning of BM25, k or the unit size on any outcome.
- No change to the frozen files of MC-100.

## Impact

- New code:
  - `code_benchmark/diagnostic_legal_retrieval.py`: worklist, sources, corpus reader, retrieval, K evidence, manifest;
  - `code_benchmark/run_legal_retrieval.py`: runner;
  - `code_benchmark/analyze_legal_retrieval.py`: analysis;
  - `code_benchmark/test_diagnostic_legal_retrieval.py`: offline tests.
- New data in `data/diagnostic_legal_retrieval/`:
  - `protocol.json`, `corpus_sources_v1.json` and `retrieval_v1.json`;
  - the frozen K evidence file and manifest;
  - `registration.json`.
- Outputs go to `all_res/diagnostic_legal_retrieval/`, which is gitignored: stored pages, the built corpus, the run.
- About 642 requests to Qwen3.5-9B: 268 B, 268 K and 106 O. That is roughly 0.7 million tokens, and the run needs the VPN.
- Comparison limits:
  - A corpus built from the evaluation questions makes retrieval easier than a corpus built without them.
  - VLSP 2025 LegalSLM forbids external access at inference, so K and O are diagnostic conditions outside the benchmark's rules.
