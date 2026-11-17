## Why

MC-101 retrieved two units by BM25 for each Legal MC item (arm K) and compared them with the provisions MC-100 located with the gold (arm O). On the 40 items whose top two held an oracle article, Qwen3.5-9B scored 76.3% with K against 83.8% with O. On the 13 misses it scored 50.0% against 88.5%.

On 2026-11-08 the project owner considered a web-search step. A post hoc check on MC-101's frozen data, with no requests, showed where the loss sits:

- **Missing documents are not the problem.** The corpus agents had found the governing document on the web for 52 of the 53 oracle items. Of the 13 misses:
  - 1 lacks its document, and every arm already answers that item correctly;
  - 3 hold the right document but rank another of its articles first;
  - 9 hold the right document, but BM25 ranks articles of other documents above it.
- **A web search would barely help.** Restricting BM25 to the oracle documents, as if a search had found exactly the right law, would raise hit@2 from 40 to 45 of 53. On those 5 items K scores 50% and O 90%, so the best case is about two more correct answers out of 53.
- **The losses come from evidence the model cannot filter:**
  - on hits, the right article arrives together with a second unit, and K still trails O by 7.5 points;
  - on misses, the right article usually sits just below the cut: BM25's top 10 holds an oracle article for 47 of the 53 items, against 40 for the top 2.

The owner chose to test this instead ("đổi bước 3 thành thí nghiệm 'chọn rồi trả lời'"). Can the small model filter retrieved evidence itself? Given BM25's top 10 units, does it pick the article that governs the question, and does answering from its own pick beat answering from the top two, from all ten, or closed-book?

## What Changes

- **Items.** The 134 Legal MC items of MC-101, with MC-100's strata and oracle evidence for the mechanism analysis. They are not fresh: MC-101's results motivated this test, and the card says so.
- **Candidates.** The top 10 units of MC-101's frozen BM25 ranking (same corpus, configuration and query), frozen in a candidate file before registration. Their first two must equal MC-101's K evidence.
- **Arms.** Two draws each, 1,446 attempts, on the campaign engine and the IEC route of MC-101:
  - **B:** the frozen main-v1 MC prompt.
  - **K:** MC-101's top-2 evidence block, then the frozen prompt.
  - **K10:** the same block with all 10 candidates, then the frozen prompt. This control separates "more evidence" from "selection".
  - **SEL**, in two requests per draw:
    - Step 1: a new selection prompt shows the 10 candidates and the question with its options. It asks for at most two candidate numbers, or `Không có`.
    - Step 2: the K template carrying only the selected units, then the frozen prompt. If nothing was selected, step 2 is the B prompt.
  - **O:** MC-100's oracle evidence, then the frozen prompt, on the 53 items that have it.
- **Analysis.** Fixed before data and run once. Two registered questions, Holm-adjusted:
  1. **Filter.** On the 53 oracle items, how often SEL's step-1 selection holds an oracle article, against BM25's top two.
  2. **Route.** Always-SEL against always-B on the 134 items. This uses MC-101's reading rule for the Legal MC route.

  Everything else is description: SEL against K, K10 and O per stratum; the share of O's gain kept; selection behaviour; tokens.
- **Card.** MC-111, registered before the first request.

## Capabilities

### New Capabilities
- `diagnostic-legal-select`: the frozen top-10 candidate file, the selection prompt and parser, the two-step SEL arm, the manifest and runner gates, and the registered analysis.

### Modified Capabilities
- None. The following are reused unchanged:
  - MC-101's corpus, retrieval configuration and K evidence;
  - MC-100's frozen files;
  - the campaign engine, templates and MC scorer.

## Evaluation regime

Regime B-style only, as MC-90 to MC-101: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint. Regimes A and C are not touched.

## Non-goals

- **No web search.** The pre-check above bounds its gain at about two items.
- **No new retriever, reranker model or embedding model.** The selector is the answering model itself.
- **No tuning on any outcome** of k, the candidate order, the selection prompt or the fallback.
- **No training or fine-tuning.** The đề cương puts it out of scope.
- **No second model.** MiMo can follow in a later card if the filter question is answered here.
- **No change to the frozen files** of MC-100 or MC-101.

## Impact

- **New code:**
  - `code_benchmark/diagnostic_legal_select.py`: candidates, selection prompt and parser, manifests;
  - `code_benchmark/run_legal_select.py`: runner with two rounds;
  - `code_benchmark/analyze_legal_select.py`: analysis;
  - `code_benchmark/analyze_legal_retrieval_misses.py`: the pre-check, moved from the scratchpad;
  - `code_benchmark/test_diagnostic_legal_select.py`: offline tests.
- **New data** in `data/diagnostic_legal_select/`:
  - `protocol.json` and `select_template_v1.json`;
  - the frozen candidate file and the round-1 manifest;
  - `registration.json`.
- **Outputs** go to `all_res/diagnostic_legal_select/` (gitignored).
- **Requests:** about 1,446 to Qwen3.5-9B: B, K, K10, SEL step 1 and SEL step 2 at 268 each, plus 106 for O. That is roughly 5.5 million tokens, most of them in the 10-candidate prompts (about 8,000 tokens each on average, at most about 16,000). The run needs the VPN.
- **Comparison limits:**
  - **Not a held-out test.** The items and corpus are those whose results motivated the test.
  - **Easier retrieval than in practice.** The question-based corpus is easier than a general one, as in MC-101.
  - **Outside the benchmark's rules.** VLSP 2025 LegalSLM forbids external access at inference, so K, K10, SEL and O are diagnostic conditions.
