## Context

See proposal.md for the motivation. Already built, offline and uncommitted (2026-11-14):

- **Coverage audit of the 112 VMLU law items.** Four gold-aware agents wrote `all_res/diagnostic_legal_agent_v2/audit/located_batch_{1..4}.json`.
  - **Labels:** 86 `supports_gold`, 4 `unclear`, 1 `contradicts_gold` (42-0014: Luật Giáo dục 2005 gives THPT three years, the gold says four), and 21 `no_provision`. `no_provision` is a new label: no legal text decides the item, as in textbook theory.
  - **Quotes.** Every in-folder quote was checked by code against its file. Every web quote was checked against the stored page body.
  - **Coverage.** 59 items had a provision in corpus_v1. The other 32 needed 23 pages, which are fetched and stored with their SHA-256 in `all_res/diagnostic_legal_agent_v2/sources/fetch_log.jsonl`.
  - **Spot-check.** The owner's sheet is `audit/review_sheet.md`. Its sample is the first 10 provision items and the first 4 `no_provision` items in SHA-256 order of `legal-agent-v2-review|<id>`.
- **ViBidLQA mapping.**
  - **The decree half is unusable.** Contexts headed "Nghị định hướng dẫn Luật Đấu thầu số 22" do not match the issued Nghị định 24/2024: article numbers are off by one or more and the wording differs, so they likely follow a draft.
  - **The law half matches.** Contexts headed "Luật Đấu thầu số 22/2023/QH15 Điều N. <title> khoản K ." match the official text.
  - **Usable items.** An item is usable when its question appears once across train, val and test, the named article exists with the same title, and the answer is verbatim in it (NFC, whitespace squashed). That gives 926 items (train 595, val 148, test 183) over 90 of the law's 96 articles.
  - **Ids.** Items keep the project's existing ids: `BIDLQA-TR-NNNN` in `bidlqa-train`, and the manifest ids of `bidlqa-val` and `vi-multimodel-v1-bidlqa-test`.
- **corpus_v2.** Built by `python -m code_benchmark.diagnostic_legal_agent_v2 folder --out all_res/diagnostic_legal_agent_v2/corpus_v2`.
  - **Contents.** 335 files and 46,710,851 characters, none truncated. Folder SHA-256 `2b40c1c75650a9af9203922f0f6d7a7c9ff4a27203910f5c95133b9bd2897987`.
  - **Fail-closed checks:**
    - every corpus_v1 file is byte-identical to MC-112's;
    - every MC-101 article is whole;
    - no site text is left;
    - MC-101's leak check passes on the 134 Legal MC items and the VMLU items. One VMLU item is exempt, and the exemption is recorded in the folder manifest: 37-0003's 31-character stem is the heading of Điều 22 of Pháp lệnh xử lý vi phạm hành chính 2002.
  - **ViBidLQA stems.** One stem is verbatim in the folder. It is reported, not failed, because the stems are written from the law.
- **Provisions dry run.** All 174 VMLU provisions and all 926 ViBidLQA anchors resolve to whole lines of corpus_v2. `item_provisions_v2.jsonl` is written once the owner's spot-check labels exist.
- **Reference scores.** Read by SHA-256.
  - MC-112: score file `01084c90…`.
  - MC-113: score file `303902b7…`.
  - MC-111's B and O: score file `4e755671…`.
  - MC-96's K2: context only.
- **Power basis.**
  - **Part M.** Per-item SDs of the two-draw differences on the 134 items are 37 (forcing) and 36.5 (harness).
  - **Part S.** On ViBidLQA, earlier cards give paired token-F1 SDs of 23–38 points.

## Goals / Non-Goals

**Goals:**
- **Forcing and harness.** Settle both with enough items. Forcing is DSHF against DSH; the harness is OMPF against DSHF.
- **Two kinds of answer.** Do it on a multiple-choice task (pooled with Legal MC) and on a span task where finding the article decides the score.
- **Mechanism.** Measure retrieval (seen, read and opened) on new items, and the score when the governing provision was read against when it was not.

**Non-Goals:**
- Taking either harness apart into components.
- Real-world retrieval: the folder is gold-aware and complete.
- Any change to MC-112's or MC-113's frozen inputs or modules.

## Decisions

### 1. Items
- **Part M.** The 112 VMLU law items (`vmlu-mqa-dev` 33, `vi-multimodel-v1-vmlu-valid` 79). Each uses its frozen main-v1 MC prompt (`build_prompt`) and its gold.
- **Part S.** 400 ViBidLQA items: the first 400 of the 926 usable items in SHA-256 order of `legal-agent-v2-bidlqa|<dataset_id>:<item_id>`. The sample, its per-split counts and its SHA-256 are frozen in the manifest. (Open choice: all 926.)

### 2. Arms (two draws each)
| Arm | Part M | Part S | Path |
|---|---|---|---|
| DSH | instruction (search allowed) + MC prompt | instruction + closed-book prompt | dsh 0.2.2-rc.1, MC-112's install, profile, sandbox and proxy |
| DSHF | instruction (search required) + MC prompt | instruction + closed-book prompt | as DSH |
| OMPF | DSHF's task, byte for byte | DSHF's task, byte for byte | omp 18.0.0, MC-113's binary, config, sandbox and proxy checks |
| B | frozen MC prompt | — | campaign request |
| C | — | closed-book prompt alone | campaign request |
| O | — | frozen reading prompt with ViBidLQA's own passage | campaign request |

- **Campaign request.** The request of MC-90 to MC-111: Responses API, system `Answer the user's question.`, temperature 1.0, `max_output_tokens` 4096 and the token-saver header.
- **Attempt counts.** 3,072 agent attempts and 1,824 direct requests.
- **Order.** Item-major. Part M comes first, then Part S. Each item lists its arms for draw 1, then for draw 2, so that endpoint drift touches all arms alike.
- **Run identity.** `dataset:item:<ARM>-r<k>`. New arm id: C. DSH, DSHF, OMPF, B and O already exist in `diagnostic_prospective.ARMS`.

### 3. Corpus and provisions are frozen inputs
- **Hashes in the registration:**
  - corpus_v2's folder SHA-256 and folder manifest;
  - `added_documents_v2.json` and the MC-112 inputs it builds on;
  - `item_provisions_v2.jsonl`;
  - the audit batches;
  - the owner's review labels.
- **Before any request,** the runner rebuilds corpus_v2 in a fresh directory, refuses a different folder hash, and runs the provision check.
- **Mount.** Each attempt mounts the folder read-only at `/work/van-ban-phap-luat`, as in MC-112/113.
- **Provisions reach the analysis only.** No prompt carries a gold, a provision, a label or an audit note.

### 4. Prompts, version `diagnostic-legal-agent-prompts-v2`
`data/diagnostic_legal_agent_v2/agent_prompts_v2.json` holds:

- **The instructions.** MC-112's DSH and DSHF instructions, unchanged. OMPF uses DSHF's.
- **The closed-book question prompt: MC-96's,** byte for byte. MC-96 registered it in `data/diagnostic_k2/protocol.json` (`prompts.closed_book`), and its B arm sent it. It is checked by that file's SHA-256:
  > `Trả lời câu hỏi sau bằng một cụm từ hoặc số ngắn gọn.\n\nCâu hỏi: {question}\nTrả lời: `

  Reusing it makes C comparable with MC-96's B, which scored 14.0 token-F1 over 720 attempts on 360 train items.
- **Task layout.** An agent task is the instruction, a blank line, then the item prompt: the MC prompt for Part M, the closed-book prompt for Part S. C sends the closed-book prompt alone; O sends `build_reading_prompt(context, question)` as main-v1 does.

### 5. Harnesses, sandboxes and proxies: reused, not edited
- **dsh attempts** call MC-112's `run_legal_agent` functions: sandbox command, home preparation, relay and the `dsh_proxy` configuration. Settings are as registered for MC-112.
- **omp attempts** call MC-113's `run_legal_agent_omp` functions: binary check, config, sandbox and the proxy subclass with its request-shape checks. The task-text check now compares against this card's manifest.
- **Unchanged limits:**
  - 30 requests per attempt;
  - 300 s per request;
  - temperature 1.0 added by the proxy;
  - a pause on a response-model change;
  - the 3-hour wall clock.

### 6. Attempt statuses
As MC-112/113: `complete`, the terminal statuses (`request_cap`, `upstream_4xx`, `harness_end`, `answer_cap`) and technical ones. Terminal statuses score 0 and stay in the denominator. Only technical failures are re-run, by `--resume`. A direct arm's incomplete response follows the campaign's rules.

### 7. Scoring
- **Part M.** The frozen MC extractor and scorer on the agent's final text (dsh `final.text`, omp's last assistant text) and on B's response.
- **Part S.** vi-reading-v3 on the same texts. It strips `*` and backticks, reads the line after the last final-answer label (else the whole text), and gives token-F1 and EM.
  - **Primary metric:** token-F1, in points.
  - **Descriptive only:** EM and gold-token recall.
  - **Long answers** lose precision. That is part of the package being measured.

### 8. Trajectory and hit rules
MC-112's rules (`seen`, `read`, `opened`) over the proxy-recorded `tool` messages, with MC-112's dsh parser and MC-113's omp parser, against `item_provisions_v2.jsonl`.
- **Part S.** The provision is the named article of `luat-dau-thau-2023.txt`.
- **Part M `no_provision` items** have no hit. They are scored but left out of the retrieval rates.

### 9. Engine and limits
- **Engine.** The campaign engine, at most four attempts in flight across both harnesses and the direct arms.
- **Breaker.** As in MC-112.
- **Budget guard.** It totals the tokens reported by the proxy and by direct responses. The cap is 1.5 times the smoke-based projection and is written into the protocol before registration.
- **Response model ids.** One expected id per path, taken from MC-112's and MC-113's registrations and checked by the smoke test.

### 10. Smoke test before registration
- **Questions.** Three questions written for the smoke and drawn from no benchmark:
  - two span questions on Luật Đấu thầu articles that no ViBidLQA item uses;
  - one MC question on an added document's article that no VMLU item uses.
- **Runs.** Each runs once with DSHF and once with OMPF on corpus_v2.
- **What it checks:**
  - corpus_v2 is mounted;
  - both harnesses run end to end;
  - the span answers are scored;
  - the cost per span attempt.
- **Use.** No score is computed from it; it sets only the budget.
- **Gate.** It needs the VPN, so the owner is asked first.

### 11. Analysis, plan `diagnostic-legal-agent-v2`, fixed before data and run once
- **Item score.**
  - **Part M:** mean correctness over two draws.
  - **Part S:** mean token-F1 v3 over two draws, in points.
- **Statistics.** For each question: mean per-item difference, 95% percentile bootstrap (2,000 resamples, seed 7) and a two-sided paired sign-flip p (20,000 resamples, seed 7).
- **Part M: pooled 246 items, Holm over 2 at α = 0.05.**
  - **Pooled scores.** The 134 Legal MC items use MC-112's DSH and DSHF and MC-113's OMPF, by score-file SHA-256. The 112 VMLU items use this card's arms.
  - **M1, harness.** OMPF against DSHF. Most of the pool crosses cards, so a difference also needs to exceed 2.24 points (MC-113's margin).
  - **M2, forcing.** DSHF against DSH. Each item's two arms come from one card, so there is no margin.
- **Part S: 400 items, Holm over 3 at α = 0.05, all within this card, no margin.**
  - **S1, harness.** OMPF against DSHF.
  - **S2, forcing.** DSHF against DSH.
  - **S3, search against closed book.** DSHF against C.
- **Reading rule.** An arm is better when its mean is higher and its adjusted p is below α (and, for M1, the gap exceeds the margin). It is worse in the mirror case. Otherwise there is no clear difference.
- **Description:**
  - **Part M, new items alone.** M1 and M2 on the 112 VMLU items, and on the 134 for reference.
  - **Part M, against B.** Each agent arm against this card's B on the 112 items. Accuracy by support label (`supports_gold`, `no_provision`, other) and on items whose gold follows superseded law.
  - **Part S, against O.** Each arm against O, the ceiling. C beside MC-96's closed-book B, and DSHF and OMPF beside MC-96's K (BM25 top-2) on overlapping train items.
  - **Both parts:**
    - behaviour: searched share, tool calls by tool, requests, compactions, tokens and statuses;
    - retrieval: `seen`, `read` and `opened`;
    - score by retrieval: when the provision was read and when it was not.
- **Report keys.** The report's top-level keys are recorded in the registration and checked.

### 12. Registration (MC-114)
- **Files.** A root block in `measurement_card.md`, the detail card `docs/measurement_cards/MC-114-diagnostic-legal-agent-v2.md` and `data/diagnostic_legal_agent_v2/registration.json`.
- **Registered hashes.** Every frozen input:
  - the folder;
  - the added documents and stored pages;
  - provisions, audit and review labels;
  - prompts v2, protocol and manifest;
  - MC-111's, MC-112's and MC-113's score files;
  - the dsh lockfile and the omp binary;
  - the runner, the proxies and the analysis.
- **The commit.** It is titled `pre-register MC-114` and comes before the first benchmark-item request. The runner's gates refuse to run on any missing or changed hash.

### Open choices for the owner (defaults are the recommendation)
1. **Part S size.** 400 items (default; MDE about 4 F1 points at an SD of 28) or all 926 (about 2.6 points, about 2.3 times the cost of Part S).
2. **Part M primary.** Pooled 246 (default; MDE about 6.5 points) or the 112 new items only (MDE about 10 points, too weak to settle a 6-point gap).
3. **M1 margin.** 2.24 points (default, as MC-113) or none.
4. **Part S family.** Holm over S1–S3 (default), or over S1 and S2 only.
5. **DSH in Part S** (default yes). It is cheap, because it rarely searches, and it is needed for S2.

## Risks / Trade-offs

- **Pooled tests mix cards and folders.** Old items ran on corpus_v1 a day or two earlier; new items run on corpus_v2. Recording the pooled tests before the new data exist bounds, but does not remove, the choice made after seeing MC-112/113's p-values. The card states it, and the new-items-only results are reported beside.
- **VMLU's stale golds.** The folder keeps superseded and current texts, as corpus_v1 does. An agent that reads the current law can contradict a gold that follows the old law. The stale subset is reported separately.
- **`no_provision` items** (21 of 112). Search cannot help on them. They stay in the accuracy tests, as on a real exam, and are left out of retrieval rates.
- **Agent labels.** 98 of the 112 VMLU labels come from agents; 14 come from the spot-check. At the owner's request Claude proposed those 14 labels with reasons, and the owner approved them unchanged. All 14 agree with the agents, which were also Claude, so the spot-check is not independent of them.
- **The ViBidLQA question text.** Its stems were generated from the law text; 30% name the article number and one is verbatim in the folder. Search is therefore easier than for a user's question. Some items were seen in earlier cards, but no setting here was chosen from them.
- **Cost and time.** About 190M tokens and 10 hours over the VPN, guarded by the per-attempt cap, the budget guard and resumable launches.
- **The closed-book prompt** is MC-96's, which has run only on train items before. C and the agents get the same question text, so the comparisons within Part S are fair; against O, the prompt differs by the passage.
