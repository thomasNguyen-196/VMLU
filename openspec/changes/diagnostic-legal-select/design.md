## Context

See proposal.md for the motivation. Everything except the selection step already exists:

- **MC-101's corpus and retrieval:**
  - corpus `vi-legal-corpus-lmc-v1`: 24,265 units, SHA-256 `66e4a349…`;
  - BM25 `bm25-article-v1`;
  - the frozen K evidence: top 2 per item, SHA-256 `97d058b2…`.

  `diagnostic_retrieval.rank` reproduces the full ranking deterministically.
- **MC-100's frozen files:** the strata, the support labels, the oracle evidence (53 items with provisions) and the owner's review.
- **The campaign engine, templates and MC scorer.** `build_arm_prompt(item, "K", templates, provisions)` renders any list of units as the evidence block followed by the frozen prompt.
- **Two-round scheduling.** MC-104 to MC-110 schedule later requests from earlier answers. A simpler scheme is enough here, because step 2 depends only on step 1 of the same draw.

## Goals / Non-Goals

**Goals:**
- **Filter.** Measure whether Qwen picks the governing article out of BM25's top 10 better than BM25's own top 2.
- **Route.** The deployable estimate of answering from the model's own selection, against closed-book B on the whole pool.
- **Mechanism.** Same-run description: SEL against K, K10 and O.

**Non-Goals:**
- Choosing k, the order, the prompt or the fallback from any outcome.
- Reranking with another model, or web search.
- Building the router route.

## Decisions

### 1. Items: MC-101's 134-item pool, not held out
- **Why the same pool.** MC-101's pool, strata and oracle evidence are the only Legal MC items with located provisions. The 12 core anchors are excluded as in MC-101.
- **The cost.** The test is not held out: MC-101's results suggested it. The card states this, and the two registered questions are the only confirmatory claims.
- **Fresh draws for every arm.** B, K and O run again in the same run rather than reusing MC-101's draws. Every comparison is then within-run, and MC-101's numbers serve only as a descriptive replication check.

### 2. Candidates: BM25's top 10, in rank order
- **How they are built.** MC-101's index ranks the units for each item's query, the question and options exactly as the B prompt carries them. The top 10 units are frozen in `candidates_v1.jsonl`. Each record holds:
  - the unit ids, locators, titles and verbatim texts with their hashes;
  - the scores;
  - the query, corpus and configuration hashes.
- **Consistency gate.** Each record's first two units must equal MC-101's K evidence; otherwise the build fails.
- **Why 10.** Coverage of an oracle article on the 53 items by depth:

  | Depth | Items covered |
  |---|---|
  | top 2 | 40 |
  | top 5 | 42 |
  | top 10 | 47 |
  | top 15 | 48 |
  | top 20 | 50 |

  Ten units are about 28,700 characters on average, at most 58,200, roughly 8,000 and 16,000 tokens. That fits the 65K context with room for the answer. Depth 20 would double the prompt for 3 more items.
- **Why rank order.** It is what a deployed pipeline would show, and it gives the model BM25's prior. Position bias is the risk: a model that always picks [1] and [2] reproduces K. The positions chosen are reported. A shuffled order would isolate reading from the prior, but it does not run.
- **Alternatives rejected:**
  - top 5 (only 2 more items in reach);
  - top 20 (prompt length);
  - a shuffled order (not deployable; can be a later card).

### 3. Selection prompt (step 1), version `diagnostic-legal-select-prompts-v1`
- **Where it lives.** `data/diagnostic_legal_select/select_template_v1.json`, frozen and hashed. The campaign templates file is not edited.
- **Text:**

  > Dưới đây là một câu hỏi trắc nghiệm về pháp luật và {n} đoạn văn bản pháp luật, đánh số từ [1] đến [{n}]. Không cần trả lời câu hỏi. Hãy chọn tối đa hai đoạn có quy định dùng để trả lời câu hỏi. Nếu không đoạn nào có quy định đó, chọn "Không có". Dòng cuối cùng phải đúng một dòng có dạng `Đoạn liên quan: 3`, `Đoạn liên quan: 3, 7` hoặc `Đoạn liên quan: Không có`, không thêm ký tự hay định dạng nào khác.
  >
  > Các đoạn văn bản:
  >
  > {candidates}
  >
  > Câu hỏi:
  > {question and options}

- **Candidate format.** Each candidate is rendered with the campaign's `evidence_item` format, `[{index}] {doc_title} — {locator}\n{text}`, joined by `evidence_separator`. The question block is `mc_query(item)`, the same text the retriever used.
- **At most two.** That is O's and K's evidence budget, so step 2 carries no more evidence than K. `Không có` is allowed: a selector that can say "nothing here" is part of what filtering means.

### 4. Parser and fallback
- **Normalization.** The response is NFC-normalized; backticks and `*` are stripped from it.
- **Which line counts.** The last line whose text starts with `Đoạn liên quan:` (case-insensitive).
- **Reading the line.**
  - The integers in it are read in the order written. Only those from 1 to n are kept, duplicates are dropped, and the first two remain.
  - If no valid integer remains and the line contains `không có` (case-insensitive), the selection is empty.
  - If there is no such line, or it holds neither a valid integer nor `không có`, the selection is `unparsed`.
- **Fallback for `unparsed`.** Step 2 uses the BM25 top 2, which is K's evidence. That is what a deployed pipeline would do when its selector fails. Unparsed draws are counted. For the filter question they count as **misses**, so BM25's ordering never earns the model credit.
- **A completed but unparsed step 1 is final.** It is not re-asked. Technical failures (no response) are re-sent as usual.

### 5. Arms, rounds and manifests
- **Arms.** All arms run two draws.

  | Arm | Prompt | Items |
  |---|---|---|
  | B | frozen prompt | 134 |
  | K | `build_arm_prompt(K, MC-101 top 2)` | 134 |
  | K10 | `build_arm_prompt(K, top 10)` | 134 |
  | SEL step 1 | selection prompt | 134 |
  | SEL step 2 | `build_arm_prompt(K, selected units)`, or the frozen prompt when the selection is empty | 134 |
  | O | `build_arm_prompt(O, MC-100 provisions)` | 53 |

  K, K10, SEL step 2 and O share one template, so they differ only in which units they carry.
- **Round 1.** B, K, K10, O and SEL step 1: 1,178 attempts. Its manifest is item-major, self-hashed and frozen before registration. The runner rebuilds it and refuses any difference.
- **Round 2.** SEL step 2: 268 attempts.
  - It starts only after every step-1 attempt is complete.
  - Its manifest is built from the round-1 ledger by the registered rule (§4): draw r's step 2 uses draw r's step-1 selection.
  - It is self-hashed and written to the run record.
  - On resume, the runner rebuilds it from the same ledger and refuses any difference.
- **Engine.** As MC-101:
  - the IEC route, Responses API, streaming, temperature 1.0, 4,096 output tokens, the campaign system prompt;
  - at most 4 requests in flight, a breaker after 4 network failures, a 300 s timeout;
  - the model-id check.

  The budget guard rises from MC-101's 5,000,000 tokens to 8,000,000, because the K10 and step-1 prompts are long.

### 6. Analysis (plan `diagnostic-legal-select-v1`, fixed before data, run once)
- **Item score.** The mean over the two draws: correctness for an answer, selection hit for a step 1.
- **Selection hit.** The step-1 selection holds an oracle article. Matching is by document number (NFC, case, spaces and Đ/D folded) and article number, any part counting, the matching of MC-101's hit report. An empty or unparsed selection is a miss.
- **Question 1, filter.** On the 53 oracle items:
  - the mean per-item difference between SEL's selection hit and BM25's top-2 hit, which is 0 or 1 per item and 40 of 53 overall;
  - a percentile bootstrap interval (2,000 resamples, seed 7);
  - a two-sided sign-flip p-value (20,000 resamples, seed 7).
- **Question 2, route.** Always-SEL (step-2 correctness) against always-B on the 134 items, with the same statistics.
- **Rule.** Holm over the two p-values at α = 0.05.
  - Q1 is met when SEL's mean exceeds BM25's and its adjusted p is below α. The report then says Qwen filters retrieved evidence better than BM25's order.
  - Q2 is met when SEL's mean exceeds B's and its adjusted p is below α. The report then says SEL should be the Legal MC route. Otherwise always-B stays.
- **Description:**
  - **Per stratum** (supports_gold items of `wrong` and `right`, and the 78 items outside MC-100): B, K, K10, SEL and O, and the differences SEL−K, SEL−K10, K10−K and SEL−O. In `wrong`, the share of O's gain kept, (arm − B)/(O − B), for K, K10 and SEL.
  - **Selection behaviour:**
    - how often 0, 1 or 2 units are selected, and how many draws are unparsed;
    - the positions chosen, including the share of selections that are exactly [1] and [2];
    - precision: the share of selected units that are oracle articles;
    - recall within reach: hits on the 47 items whose top 10 holds an oracle article;
    - `Không có` on the 6 items whose top 10 holds none.
  - **Accuracy by selection outcome:** SEL's step-2 accuracy when its selection hits and when it misses.
  - **Gold check:** each arm's choices on the `contradicts_gold` items, read from MC-100's owner review by its registered hash.
  - **Pool counts:** clear rescues and regressions; the share answering A.
  - **Tokens:** mean tokens per arm, with SEL counting both steps.
  - **Replication check:** this run's B, K and O against MC-101's.
- **Report keys.** Recorded in the registration and checked.

### 7. Registration (MC-111)
- **Cards.** The root block in `measurement_card.md`, and the detail card `docs/measurement_cards/MC-111-diagnostic-legal-select.md`.
- **`data/diagnostic_legal_select/registration.json`,** with the report keys and the SHA-256 of:
  - the protocol;
  - the selection template;
  - the candidate file;
  - MC-101's corpus, retrieval configuration and K evidence;
  - MC-100's oracle evidence and owner review;
  - the campaign templates and protocol;
  - the round-1 manifest.
- **Commit.** All of it is committed as `pre-register MC-111` before the first request.
- **MC-110 is unaffected.** It may still be running. Adding a block to the root card changes `measurement_card_hash`, which MC-110's resume treats as an implementation field.

## Risks / Trade-offs

- **[Position bias: Qwen picks [1] and [2]]** → SEL then equals K. The positions chosen are reported, and K10 and K bound the outcome. A shuffled-order card is the follow-up if this happens.
- **[Ten long units overwhelm a 9B model]** → K10 measures the effect of length itself. Step 1 asks only for numbers, so its output stays short.
- **[Format failures in step 1]** → They fall back to K and count as filter misses. A high unparsed share is itself a finding about the model, reported as such.
- **[Not held out, small n (53 oracle items; 23 in stratum `wrong`)]** → There are only two confirmatory questions, with Holm. Everything else is description, and the card states the limit.
- **[Endpoint drift since MC-101]** → The model-id check pauses the run. B, K and O are re-run, and their agreement with MC-101 is reported.
- **[Some golds follow superseded law]** → Predecessors are in the corpus. The gold check stays descriptive, as in MC-101.
