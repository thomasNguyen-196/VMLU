## Context

See `proposal.md` for the motivation.

**Reused pieces:**
- The frozen main-v1 Legal MC items: `vi_multimodel.rebuild_items("main")`, dataset `vi-multimodel-v1-legal-mc-146`.
- The wide B draws:
  - MC-90 `scores.jsonl`, B-r1;
  - MC-91 `scores.jsonl`, B-r2.
- The campaign protocol, engine and scorer:
  - `diagnostic_prospective.load_protocol`;
  - `run_diagnostic_prospective` (`configure_engine`, `base.execute`);
  - `diagnostic_prospective.score_arm_rows`.
- The evidence block of `data/diagnostic_prospective_v1/prompt_templates_v1.json` and `build_arm_prompt(item, "O", …)`. MC-93's arm O used the same block.
- The article parser and fetcher of `diagnostic_retrieval`. Corpus v0 was built with them from hethongphapluat.com.

## Goals / Non-Goals

**Goals:**
- Measure, on Legal MC, what the governing provision does to Qwen's answers:
  - how many wrong answers it fixes;
  - how many right answers it breaks.
- Decide by a registered rule whether a retrieval study on Legal MC is worth building.

**Non-Goals:**
- Any retriever. The oracle replaces retrieval on purpose.
- Legal NLI. Its task is to judge whether a given text answers a question, so adding documents would change the task.
- Changing any registered campaign artefact.

## Decisions

### 1. Items
- **Pool.** The 134 Legal MC items of the wide phase. The 12 core anchors are not in it.
- **Stratum `wrong`.** Every pool item that B answered wrongly on at least one of the two draws: 28 items, 12 of them on both draws.
- **Stratum `right`.** 28 of the 106 items B answered correctly on both draws: the first 28 in ascending SHA-256 of `legal-oracle-v1|<item_id>`.
- The protocol records the selection rule and the paths of its two sources. The manifest records the SHA-256 of both sources.
- Selecting on earlier draws invites regression to the mean: some `wrong` items will be right on a fresh B draw. So O is compared with **fresh** B draws on the same items, never with the draws that selected them.

### 2. Oracle evidence
- **Who locates it.** Four Claude agents, 14 items each, sorted by item id and blind to the stratum. Each agent sees the exact prompt (question and lettered options) and the gold letter, and returns locations only: page URL, document number and title, article number, and clause numbers when an article exceeds 6,000 characters.
- **Source.** hethongphapluat.com, the source site of corpus v0, so that one parser applies. Each page is stored once with its SHA-256 and retrieval time under `all_res/diagnostic_legal_oracle/sources/`.
- **Provision text.** The text is extracted by code, never written by an agent:
  - the whole article (`Điều N`), verbatim from the stored page;
  - when the article exceeds 6,000 characters, its heading line and the named clauses, verbatim and in page order. Clauses named for a shorter article are ignored, and an over-long article without named clauses fails the build.
  - An item has at most two provisions.
  - Articles are read as corpus v0 reads them, with two exceptions:
    - A page that breaks off inside its last article element keeps the articles closed before it. The stored page of NĐ 99/2022 never closes Điều 11; its Điều 3 and Điều 4 are unaffected.
    - A document attached to the page (a Quy chế issued by a Quyết định) whose articles carry no article element is read from the page text after its heading line (for example `QUY CHẾ`), from the article's heading line up to the next article, chapter, section or annex heading. Its locator reads `Quy chế kèm theo, Điều N`. The location names the heading line in an optional `part` field.
- **Support label against the gold:**
  - `supports_gold`: the provision, read plainly, makes the gold option correct and the others wrong;
  - `contradicts_gold`: it makes another option correct;
  - `unclear`: relevant, but it does not decide;
  - `not_found`: no governing provision on the site.
- **Owner review.**
  - **Sample.** 14 items, the first 14 in ascending SHA-256 of `legal-oracle-review|<item_id>` among items that have a provision.
  - **What the owner sees.** The question, the options, the gold, the provision text, and the agent's label with its rationale.
  - **Verdict.** The owner's label replaces the agent's on reviewed items.
  - **Owner's option.** The owner also writes, per reviewed item, the option the provision makes correct. Added after the owner noticed, while reviewing, that several golds look doubtful. These options mostly equal the gold, so the review file stays in `all_res/` and only its SHA-256 is registered.
  - **Report.** Agent–owner agreement on the sample. The review is AI-assisted, since the sheet shows the agents' labels, so agreement bounds rather than measures their accuracy.
- **Checks.** `validate_provisions(…, verbatim_source=True)` (shape, text hash, answer-key lines), and no record key from `FORBIDDEN_EVIDENCE_KEYS`.
- **Gold.** The gold is used only to locate and label evidence, never in a request. The evidence file is frozen, and its SHA-256 registered, before the first request.

### 3. Arms and prompts
- **B:** the item's frozen main-v1 prompt, byte for byte.
- **O:** the campaign evidence block, then the same frozen prompt: `build_arm_prompt(item, "O", templates, provisions)`. The header reads "Căn cứ tham khảo (có thể chưa đầy đủ):", and each provision is listed as `[i] <title> — <locator>` followed by its text.
- **Draws.** Two per arm: B-r1, B-r2, O-r1, O-r2.
- **Coverage.** Every selected item runs B. O runs on every item that has at least one provision, whatever its support label.
- **Manifest.** Item-major (item, draw, arm), self-hashed, frozen as `manifest_v1.json`. The runner rebuilds it and refuses any difference.

### 4. Route, engine and scoring
- **Route and engine.** The campaign protocol's model and transport, unchanged: Qwen3.5-9B-65K on the IEC gateway, the registered temperature and output cap, and the campaign budget guard. The same engine runs as in MC-93 to MC-97.
- **Limits.** 4 requests in flight; the run stops after 4 consecutive network failures. Other values are refused.
- **Scoring.** The frozen MC extractor and `score_arm_rows`, exactly as for B and O in MC-93. An unparseable answer counts as wrong.

### 5. Analysis (plan `diagnostic-legal-oracle-v1`, fixed before data, run once)
- **Item score.** The mean correctness of an arm over its two draws: 0, 0.5 or 1.
- **Primary set.** Items whose final support label is `supports_gold`. This is the owner's label on reviewed items and the agent's elsewhere.
- **For each stratum, O against B on the primary set:**
  - the mean per-item difference, with a percentile bootstrap interval (2,000 resamples, seed 7) and a two-sided sign-flip p-value (20,000 resamples, seed 7);
  - clear rescues (O right on both draws, B wrong on both) and clear regressions (the reverse).
- **Descriptive:**
  - stratum `wrong` split into items missed on both earlier draws and items missed on one;
  - the items labelled `contradicts_gold` or `unclear`;
  - the share of answers that are A, per arm (the gold is 62.3% A);
  - mean prompt and completion tokens per arm;
  - evidence length;
  - agent–owner agreement on the review sample.
- **Gold check (descriptive).** On the reviewed items, the owner's option against the gold. On the `contradicts_gold` items, each arm's answers that pick the gold's option, the owner's option or another. This asks whether the provision moves Qwen away from a gold the law does not support, so that a lost point there is not read as a reading failure.
- **Reading rule.** A retrieval study on Legal MC (step 2b, the question-based corpus) is worth building when, on the primary set, both hold:
  - in stratum `wrong`, O's mean is at least **20 points** above fresh B's;
  - in stratum `right`, O's mean is at most **10 points** below fresh B's.

  Otherwise the step stops. Missing documents are then not the main cause of Qwen's Legal MC errors, and Legal NLI's detector (step 1) or the thesis writing comes next.

### 6. Registration (MC-100)
- The root block in `measurement_card.md`.
- The detail card `docs/measurement_cards/MC-100-diagnostic-legal-oracle.md`.
- `data/diagnostic_legal_oracle/registration.json`, with the SHA-256 of:
  - the protocol;
  - the evidence file;
  - the templates;
  - the campaign protocol;
  - the manifest;
  - the owner's review file, read by the analysis only when its hash matches;

  and the report's top-level keys, which the analysis checks.

All are committed as `pre-register MC-100` before the first request.

## Risks / Trade-offs

- **Tailored oracle.** The provision is located knowing the question and the gold, so O is an upper bound on what retrieval could give. A null result is therefore informative: if even the right article does not fix the errors, a retriever will not. A positive result is only a ceiling.
- **AI-located evidence.** An agent may pick a provision that echoes the gold option without governing the question. The owner's sample review measures this, and the support labels keep `contradicts_gold` and `unclear` items out of the primary set.
- **Law versions.** The questions ask about the law "hiện hành" around 2025, and the source site may show an original text later amended. Agents note version issues; such items can land in `unclear` or `contradicts_gold`.
- **Small strata.** 28 items each, fewer after labelling. The thresholds are large on purpose, about 5–6 items net in `wrong`.
- **Answer skew.** 62.3% of gold answers are A. A shift in the share of A answers can move accuracy without any reading of the evidence, so the share is reported per arm.
- **Benchmark rules.** VLSP 2025 LegalSLM is closed-book. Arm O is a diagnostic condition, not a leaderboard entry.

## Migration Plan

New files only. Nothing registered is rewritten.
