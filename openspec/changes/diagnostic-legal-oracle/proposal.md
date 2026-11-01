## Why

The routers so far choose only among ways of prompting: B, Q and S. On 2026-10-29 the project owner proposed that they underperform because they do not detect what a question needs and do not pull in the documents needed to answer it.

The evidence so far splits by task.

**Reading items.** In the 60-anchor audit, the passage was sufficient for 35 of the 36 reading anchors (Vi-SQuAD, Vi-DROP, ViBidLQA). Their failures were labelled reading or representation (8) and reasoning (2).

**Legal items.** The input lacked the needed law for 10 of the 12 Legal MC anchors. Legal MC gives only a question and four options, so the model answers from memory.

**Retrieval quality.** The K2.1 bake-off already compared retrievers on ViBidLQA. BM25 ranked the question's own passage first for 64.7% of questions, against 49.2% for BGE-M3 dense retrieval; a reranker added about 3 points. So retrieval method alone is not the open question.

**The open question.** Would the right document help at all? On Legal MC, Qwen3.5-9B already answers 86.6% correctly with B (MC-90). Over the two B draws (MC-90 B-r1 and MC-91 B-r2) it missed 28 of the 134 wide items at least once, and 12 on both draws. Before building a legal corpus for all 146 questions, this change measures the ceiling of retrieval: hand Qwen the provision that governs each question (arm O) and see whether it fixes what B gets wrong, and whether it breaks what B gets right.

The owner chose this order on 2026-10-29: the oracle test first, the question-based corpus only if the oracle helps.

## What Changes

- **Items.** The 134 Legal MC items of the wide phase, in two strata:
  - `wrong`: every item B missed on at least one of its two draws (28);
  - `right`: 28 items B answered correctly on both draws, in a fixed hash order.
- **Oracle evidence.** For each item, AI agents locate the provision that governs the question on hethongphapluat.com, the source site of corpus v0. They work from the question, the options and the gold letter, without knowing the stratum.
  - The provision text is copied verbatim from the stored page by article number.
  - Each item gets a support label against the gold.
  - The project owner reviews a fixed random sample of 14 items.
  - The evidence file is frozen before registration.
- **Arms.**
  - B: the frozen main-v1 MC prompt.
  - O: the campaign evidence block (`prompt_templates_v1.json`) with the item's provisions, then the same frozen prompt.
  - Two draws each, on the campaign's engine and route: Qwen3.5-9B-65K on the IEC gateway.
- **Analysis.** It is fixed before data and run once. Per stratum it reports O against fresh B, and a registered reading rule decides whether a retrieval study on Legal MC (step 2b) is worth building.
- **Card.** MC-100, registered before the first request.

## Capabilities

### New Capabilities
- `diagnostic-legal-oracle`: the item selection, oracle-evidence procedure, frozen manifest, runner gates and registered analysis of the Legal MC oracle test.

### Modified Capabilities
- None. The campaign's engine, templates and scorer are reused unchanged.

## Impact

- New code:
  - `code_benchmark/diagnostic_legal_oracle.py` (selection, evidence, manifest);
  - `code_benchmark/run_legal_oracle.py` (runner);
  - `code_benchmark/analyze_legal_oracle.py` (analysis);
  - `code_benchmark/test_diagnostic_legal_oracle.py` (offline tests).
- New data in `data/diagnostic_legal_oracle/`:
  - `protocol.json`;
  - the frozen evidence file and manifest;
  - `registration.json`.
- Outputs go to `all_res/diagnostic_legal_oracle/`, which is gitignored: stored source pages, the review sheet, the run.
- About 224 requests to Qwen3.5-9B: 56 items × 2 arms × 2 draws. Items without evidence run B only. The run needs the VPN.
- Comparison limits:
  - The oracle is tailored to each question and located with the gold answer known. It measures what perfect retrieval could give, not what a retriever gives.
  - VLSP 2025 LegalSLM forbids external access at inference, so arm O is a diagnostic condition outside the benchmark's rules.
