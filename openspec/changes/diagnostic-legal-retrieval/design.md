## Context

See proposal.md for the motivation. Most of the needed machinery already exists:

- **Corpus v0** (MC-93): 19 audit-cited documents and 2,375 articles from hethongphapluat.com, read as top-level article elements by `diagnostic_retrieval.parse_articles`, with BM25 settings `bm25-article-v0` and a leak check (`leak_report`).
- **MC-100's reader** (`diagnostic_legal_oracle`) adds two exceptions: a page that breaks off inside its last article keeps the articles closed before it, and a Quy chế attached to a Quyết định is read from the page text after its heading line (`part`).
- **The campaign engine, templates and MC scorer** run arm K unchanged, as they did in MC-93. Arm K's prompt is the evidence block of `prompt_templates_v1.json` followed by the frozen MC prompt, the same template as O.
- **MC-100's frozen files:** the strata, the oracle evidence (53 items with provisions) and the owner's review, each with a registered SHA-256.

## Goals / Non-Goals

**Goals:**
- The deployable estimate: always-K against always-B on the whole Legal MC pool.
- The mechanism, on the same run: K against O on the MC-100 items, retrieval hits against the oracle articles, and K's accuracy when retrieval hits and when it misses.

**Non-Goals:**
- Choosing k, the unit size or BM25 parameters from any outcome.
- Building the router route itself.
- Repairing a missed document by hand.

## Decisions

### 1. Items: the 134-item pool, not the 56 MC-100 items
- **Deployment question.** The question that matters for the router is the per-dataset choice: should Legal MC go to K or stay on B? Adaptive-RAG found that choice hard to beat.
- **Why the 56 items can't answer it.** They oversample B's misses: all 28 misses, but only 28 of the 106 items B got right. An average over them overweights the items where retrieval can help. Reweighting would leave 28 items to stand for 106. On the 134 items, the estimate needs no weights.
- **Mechanism.** The MC-100 items, their strata and their oracle evidence stay inside the run, so the mechanism analysis is within-run.
- **Fresh baseline.** B runs fresh, two draws. The MC-90 and MC-91 draws selected the strata and are not the baseline.
- **Alternatives rejected:**
  - The 56 items alone: a cheaper corpus, but it answers only the mechanism question.
  - Adding the 12 core anchors: they were audited, and MC-93 already ran K on them over corpus v0.

### 2. Corpus: chosen from the question stems, with three roles
- **Who chooses, and from what.** Four agents, about 34 items each, in item-id order. Each sees only the question stem: the question text without the instruction and without the options. Agents never see:
  - the options, which can reveal the answer to an agent that knows the law;
  - the gold or the strata;
  - any file of MC-100.
- **What they list.**
  - **`topical`:** per item, up to 3 documents that govern the question's subject (law, decree, circular, decision or consolidated text), preferring the version in force.
  - **`predecessor`:** for each topical document, the instrument it replaced or amends, when the site carries it.
  - **`distractor`:** per batch, up to 5 documents from the same fields that govern other matters.
  - **`part`:** the heading line, for a document with an attached Quy chế.
- **Merge and freeze.**
  - The lists are merged by URL, one entry per page. On a clash, `topical` wins over `predecessor`, which wins over `distractor`.
  - The list is frozen as `corpus_sources_v1.json` before the corpus is built and before any retrieval query.
- **Fetching.** Pages are fetched by code: https only, hethongphapluat.com only, 2 s apart. Each is stored with its SHA-256 and time under `all_res/diagnostic_legal_retrieval/corpus/raw/`, with a fetch log.
- **Expected size.** 80 to 150 documents. The owner's earlier estimate of 50 to 100 was for fewer questions.
- **Alternative rejected: MC-100's 45 oracle documents as the corpus.** They were chosen with the gold in view, which would make K a near-oracle. Their overlap with the new corpus is reported instead.

### 3. Reader and units
- **Reading articles.** MC-100's reader, with two more rules:
  - a heading with a footnote marker, as in the consolidated texts (`Điều 15[15].`), is the heading of Điều 15;
  - for a document with a `part`, every article of the attached text is read: each runs from its heading line to the next article, chapter, section or annex heading, or to a signature or `Nơi nhận` line.
- **Unit.** An article, except that an article over 6,000 characters is split into consecutive parts at line boundaries.
  - Each part is at most 6,000 characters where its lines allow.
  - Every part after the first opens with the article's heading line.
  - Unit ids are `<doc_id>#dieu-<n>` or `<doc_id>#dieu-<n>-p<i>`. Locators are `Điều N` or `Điều N (phần i/k)`.
- **Why split.** K then gets O's evidence budget: at most two units of about 6,000 characters. Whole amending articles reach 48,000 characters (TT 96/2015 Điều 4), which would bury the provision.
- **Alternatives rejected:**
  - Whole articles, as in corpus v0: prompts are unbounded, and MC-93 saw dilution.
  - Clause-level units: amending articles repeat clause numbers, so clause parsing fails on them.
- **Checks.**
  - The leak check of corpus v0: a question stem copied verbatim, or an answer-key line, fails the build; options copied verbatim are counted only.
  - Every unit's text hash, and unique unit ids.
  - Omitted documents are listed with their reason.
- **Freeze.** The corpus (`corpus.jsonl` and its manifest with `corpus_sha256`) stays in `all_res/`. The sources list and the reader settings are tracked in `data/`. Their hashes are registered.

### 4. Retrieval
- **Settings.** BM25 exactly as `bm25-article-v0`, untuned:
  - NFC, lower case;
  - word-character tokens plus adjacent pairs;
  - k1 1.2, b 0.75, Lucene idf;
  - distinct query terms counted once;
  - ties broken by corpus order.
- **Query.** The item's question and options as the frozen B prompt carries them (`mc_query`).
- **Top 2 units.** This is O's evidence budget. MC-93's top 3 diluted the cited article, and MC-96 also used the top 2.
- **Alternatives.** Top 1 has fewer distractions and more misses; top 3 is MC-93's setting. Neither runs, so K stays a single preset arm. Hit@1, hit@2 and hit@3 are reported as description.
- **K evidence file.** Each record holds:
  - the two units as provisions;
  - the ranking (unit id, score, text hash);
  - the query hash, the corpus hash and the configuration hash.

  The file is frozen before registration.

### 5. Arms and manifest
- **Arms.**
  - B: the frozen prompt.
  - K: evidence block with the K evidence, then the frozen prompt.
  - O: evidence block with MC-100's oracle provisions, then the frozen prompt.

  K and O share one template, so they differ only in which provisions they carry.
- **Manifest.** Item-major (item, draw, arm), self-hashed, 642 attempts: B 268, K 268, O 106.
- **Rebuild.** The runner rebuilds the manifest and refuses any difference.
- **Engine.** As MC-100: route, temperature, output cap, at most 4 requests in flight, a breaker after 4 network failures, and a budget guard of 5,000,000 tokens.

### 6. Analysis (plan `diagnostic-legal-retrieval-v1`, fixed before data, run once)
- **Item score.** The mean correctness over the two draws.
- **Primary.** Always-K against always-B on the 134 items:
  - the mean per-item difference;
  - a percentile bootstrap interval (2,000 resamples, seed 7);
  - a two-sided sign-flip p-value (20,000 resamples, seed 7).
- **Reading rule.** K becomes the Legal MC arm of the router when its mean exceeds B's and p < 0.05; otherwise always-B stays. One confirmatory test, no multiplicity. Its cost is tokens only: K's prompts are several times B's, which is reported.
- **Description:**
  - On the MC-100 strata, for items labelled `supports_gold`: K against B, K against O, and, in stratum `wrong`, the share of O's gain that K keeps, (K − B)/(O − B).
  - The 78 items outside MC-100: K against B.
  - Retrieval hits against the MC-100 oracle articles on its 53 items: hit@1, hit@2 and hit@3, by document number (case, spaces and Đ/D folded) and article number, any part counting. Also K's and O's accuracy on hit and miss items, and the overlap between the corpus documents and MC-100's oracle documents.
  - Gold check: each arm's choices on the `contradicts_gold` items (gold, the owner's option, other). It reads MC-100's owner review by its registered hash.
  - Clear rescues and regressions on the pool; the share answering A; mean tokens per arm; evidence length.
- **Report keys.** Recorded in the registration and checked.
- **If K fails overall but helps the `wrong` stratum.** A selective route becomes the candidate for a later change: send to K only the items the B-twice signal marks as uncertain. It is not tested here.

### 7. Registration (MC-101)
- The root block in `measurement_card.md`, and the detail card `docs/measurement_cards/MC-101-diagnostic-legal-retrieval.md`.
- `data/diagnostic_legal_retrieval/registration.json`, with the SHA-256 of:
  - the protocol;
  - the sources list;
  - the corpus;
  - the retrieval configuration;
  - the K evidence;
  - MC-100's oracle evidence and owner review;
  - the templates;
  - the campaign protocol;
  - the manifest.

  It also records the report keys.
- All of it is committed as `pre-register MC-101` before the first request.

## Risks / Trade-offs

- [A corpus built from the evaluation questions makes retrieval easier than a general corpus] → Agents see stems only. Predecessors and distractors are added, the overlap with the oracle documents is reported, and the card states the limit.
- [An agent misses the governing document] → It is a real failure of the procedure, not repaired by hand. The hit report and K's accuracy on misses show its cost.
- [Pages that do not parse] → They are listed as omitted with their reason, and their count is reported.
- [Splitting cuts an article mid-topic] → Every part keeps the heading line, and a hit to any part counts.
- [Some golds follow superseded law] → Predecessors are in the corpus and the gold check stays descriptive. The card notes the limit.
- [The MC-100 items were already studied] → No setting is chosen from MC-100's outcomes, and B is drawn fresh.
- [The endpoint drifts] → The model-id check pauses the run. B and O repeat MC-100's conditions on the same items.
- [Many numbers in one report] → One primary test; every other number is description.
