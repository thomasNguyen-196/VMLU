## Context

See `proposal.md` for the motivation. MC-118 moves the legal-agent design from legal texts to general reading. Changing domains brings three changes:
- the folder holds articles instead of laws;
- the items are Reading-400 instead of ViBidLQA;
- the instruction names articles instead of legal provisions.

Everything else follows MC-115 (Qwen), MC-116 (MiMo) and MC-117 (OMPS):
- the harness installs, profiles, sandbox, relay and proxy;
- the routes, caps, request cap and context window.

Facts checked before this design (2026-11-25):

| Fact | Value |
|---|---|
| Reading-400 golds | 400/400 filled; 321 are model answers the owner accepted (`review_records/review_nttung245_qwen3_8_27b_q4_k_m_gguf.csv`) |
| Gold verbatim in its passage | viSQuAD 186/200; Vi-DROP 110/200 (add_sub 6/55) |
| Passage length | viSQuAD median 239 words (max 761); Vi-DROP 128 (max 346) |
| Source pools | viSQuAD 3,310 questions and 1,633 distinct passages; Vi-DROP 3,309 and 1,186. After deduplicating both on normalised text: 2,284 passages, 2.41M chars, 1 non-NFC passage. All 400 items map to one passage, and no question is non-NFC |
| MC-96 closed-book prompt | `Trả lời câu hỏi sau bằng một cụm từ hoặc số ngắn gọn.\n\nCâu hỏi: {q}\nTrả lời: ` (`a8c5d481…`) |
| Legal DSHF instruction | `data/diagnostic_legal_agent/agent_prompts_v1.json` (`3f760fd1…`), worded for legal texts |
| omp paging | omp pages a read that has no offset/limit, and elides the middle of long files; dsh returns the file (MC-117 flows). In 300 MC-117 omp logs, omp still paged files under 400 lines 491 times, so the cut is not by line count alone |
| Judge check | token-F1 bias Qwen −4.75 / MiMo −25.0; R ≥ 0.5 −2.25 / −2.25; mean R −3.6 / −3.35 points |

## Goals / Non-Goals

**Goals:**
- Test, per model, whether omp and dsh differ on general reading when the agent must find the passage.
- Test whether the legal interaction recurs: MiMo gains more from omp than Qwen.
- Test whether omp's default system prompt carries that interaction (OMPS), as MC-117 found on legal texts.
- Score with a measure the judge found model-neutral, and check its neutrality across harnesses on a sample.

**Non-Goals:** see `proposal.md`.

## Decisions

### 1. Corpus `reading_corpus_v1` (long files)

- **Passages.** Every distinct context of `vmlu_squad_v1/vi_squad_benchmark_question_only.json` and `vmlu_drop_v1/vi_drop_benchmark_3309_question_only.json`, deduplicated on NFC-normalised text. The text bytes are kept as in the source. The build reports the share of non-NFC passages and questions.
- **Order.** By the SHA-256 of each passage's normalised text, so viSQuAD and Vi-DROP passages mix.
- **Layout.**
  - Files of 50 passages: `bai-viet-01.txt` … `bai-viet-46.txt`, the last one shorter.
  - Each passage is preceded by `## Đoạn NNNN` (4 digits, global numbering) and followed by a blank line. The headings play the role of a law's article headings. They carry no information about any question.
  - **One sentence per line** (`wrap`): the whitespace after `.`, `!`, `?` or `…` becomes a line break, and a sentence longer than 600 characters breaks at its last space before that. Only whitespace changes, and 0 of 2,284 passages change under `normalized_key`.
  - The result: 2.41M characters in all; per file, a median of 500 lines (minimum 352); line length median 111 and p99 391, none above 768. The legal corpus has median 78, p99 596, 0.3% above 768.
- **Why one sentence per line (owner's choice, 2026-11-25, "Mỗi câu một dòng").** The first paging check used one line per passage, and it failed:
  - omp cuts every line at 768 characters, and 19% of those lines were longer;
  - dsh cuts lines at 2,000 characters;
  - the files had about 200 lines, under omp's 300-line page.

  omp would therefore have hidden the tail of one passage in five, which never happens on the legal corpus. With one sentence per line, the self-test reads `bai-viet-01.txt` without offset or limit, and both harnesses page as they did on laws:
  - omp: `[Showing lines 1-300 of 523. Use :301 to continue]`;
  - dsh: `(Output capped. Showing lines 1-398. Use offset=399 to continue.)`.
- **Folder.**
  - Work directory `/work/bai-viet`; folder SHA-256 `cc9b461c…` and index `corpus_index_v1.json`.
  - MC-112's and MC-113's runners mount the folder at their module constant `WORKDIR`. `run_reading_agent.set_workdir` sets that constant in this card's process (`run_legal_agent.WORKDIR`, `run_legal_agent_omp.WORKDIR`, and `diagnostic_legal_agent.WORKDIR`, the base of its path normalisation), and omp's `--cwd` is replaced in the argument list. No registered file is edited.
  - The self-test showed that the work directory does not enter any system message. dsh, OMPF and OMPS send, byte for byte, the legal cards' messages:
    - Qwen: `d6bd65aa…`, `3d04a885…`, `b868301f…`;
    - MiMo: `54d89951…`, `616bebaf…`, `32a43405…`.
- **Passage index** (`data/diagnostic_reading_agent/corpus_index_v1.json`): for every passage, its number, file, first and last line, source set, and SHA-256. It also maps every Reading-400 item to its passage.
- **Paging check (before registration).** The self-test reads one corpus file without offset/limit in each harness. It records whether omp cuts or elides the page, and whether dsh caps its output. If omp shows a whole file, the smoke test refuses to run until the owner decides. Otherwise the layout would not reproduce the legal mechanics. The check passed for both models after the line layout above.

### 2. Items and prompts

- **Items.** The 400 Reading-400 items, in manifest order, with the reviewed golds (`GOLD_REVIEW_DEFAULT`). None is excluded.
- **Agent task.** DSHF's instruction, MC-112's separator (a blank line), then MC-96's closed-book prompt on the item's question, byte for byte. OMPF and OMPS send DSHF's task.
- **The DSHF instruction** (new; MC-112's sentence structure with legal terms replaced):

  > Thư mục làm việc hiện tại chứa các bài viết tiếng Việt, mỗi file `.txt` gồm nhiều đoạn văn. Trước khi trả lời, bạn phải dùng công cụ grep để tìm và công cụ read để đọc đoạn văn dùng để trả lời câu hỏi dưới đây. Chỉ trả lời sau khi đã đọc đoạn văn đó.

- **C** sends MC-96's closed-book prompt alone.
- **O** sends the frozen reading prompt (`vi_multimodel.build_reading_prompt`) with the item's own passage.
- **Retrievability (descriptive, before data).** BM25 over the 2,284 passages with each question gives the rank of the gold passage. Strata: top-1, top-5, beyond. No item is dropped.

### 3. Arms, draws and order

| Arm | Harness / call | System message |
|---|---|---|
| DSHF | dsh 0.2.2-rc.1, the model's registered profile, forced task | dsh's own |
| OMPF | omp 18.0.0, the model's registered configuration | omp's default |
| OMPS | as OMPF, plus `--system-prompt <file>` | dsh's system prompt for the model, as in MC-117 |
| C | direct request, no tools | none |
| O | direct request, no tools | none |

- **Draws.** Two per arm (`<arm>-r1`, `<arm>-r2`).
- **Order.** Item-major. Per item and draw, the five arms come in an order permuted by seed 7, so the arms share the time window.
- **OMPS's prompt files.** MC-117's `data/diagnostic_legal_agent_omp_prompt/dsh_system_prompt_{qwen,mimo}.txt`, read by SHA-256. The smoke test records dsh's first system message in the new work directory:
  - if it equals the file, OMPS uses the file;
  - if it differs (for example, by a work-directory line), OMPS uses the smoke's message, saved as a new file and hashed. The card states which.

### 4. Routes and runner

- **Routes:**
  - Qwen: MC-115's route, IEC `Qwen3.5-9B-65K` over the VPN with the in-tunnel resolver, cap 4,096. **C and O use chat completions on the same endpoint** (protocol `models.qwen.direct`). MC-115's direct route, IEC's Responses API, answered HTTP 500 to all 16 smoke requests on 2026-11-25, and the owner chose the switch.
  - MiMo: MC-116's route, OpenCode Go `mimo-v2.6-flash`, one session per try, cap 16,000.
  - Both: temperature 1.0, request cap 30, context 65,024, and a response-model pin.
- **Runner.** `run_reading_agent.py --model qwen|mimo` wraps the existing dsh and omp paths and the campaign request for C and O. It adds:
  - the corpus folder;
  - OMPS's `--system-prompt` overlay (MC-117's code);
  - MC-117's stall rule (a stream that ends with no model chunk is technical) and halted-row identity;
  - the budget-amendment hook.
- **Operation.** At most 4 attempts in flight per run; stop after 4 timeouts. One `systemd-run --user` unit per model, plus a relauncher that resumes only after budget, breaker or technical stops. Qwen's VPN stays open for its run.

### 5. Smoke test (before registration; owner's go; no benchmark item)

- **Questions.** Two viSQuAD and two Vi-DROP questions that are not among the 400 but whose passages are in the corpus, fixed by seed 7. Each runs once per arm and model: 4 × 5 × 2 = 40 attempts.
- **Recorded:** statuses, body keys, response models, first system messages and their hashes, the paging check, and tokens.
- **Budgets.** Smoke tokens per attempt per arm × attempts × 1.5. MC-117's amendment hook stays, because one smoke attempt underestimated MC-117's budget.

### 6. Scoring

- **Prediction.** vi-reading-v3: the line after the last final-answer label, with `*` and backticks deleted.
- **R** (thesis (3.11), `run_legal_agent_v2.token_recall`): the share of the gold's tokens present in the prediction. It is the registered score.
- **Token-F1 v3:** the continuity score.
- **EM-v3:** beside only.
- **Item score:** the mean over the item's two draws in each arm (thesis (3.5)).

### 7. Analysis (fixed before data, run once after both runs are final)

`analyze_reading_agent`, plan `diagnostic-reading-agent`.

- **Tests,** two families, each with Holm over four:
  - **Primary family:** R.
  - **Continuity family:** token-F1 v3.

  | Test | Definition |
  |---|---|
  | H1 | Qwen: OMPF − DSHF |
  | H2 | MiMo: OMPF − DSHF |
  | H3 | ι = H2 − H1, per item |
  | H4 | P3 = (OMPS − OMPF)_MiMo − (OMPS − OMPF)_Qwen, per item |

- **Statistics,** as in MC-112 to MC-117: the mean per-item difference in points; a 95% percentile bootstrap over items (2,000 resamples, seed 7); a two-sided paired sign-flip p-value (20,000 resamples, seed 7). No margin, as on MC-117's Part S.
- **Reading rules:**
  - **H1, H2:** "OMPF better/worse than DSHF" with a Holm-adjusted p below 0.05; otherwise "no clear difference", with the interval.
  - **H3:** "the legal interaction recurs on general reading" when ι > 0 with Holm p < 0.05; "reversed" when ι < 0 with Holm p < 0.05; otherwise "not detected".
  - **H4:** "omp's default prompt carries part of the interaction on general reading" when P3 < 0 with Holm p < 0.05. When H3 is "not detected", H4 is reported but not read as carrying an interaction.
- **Beside, not tested:**
  - **Model and harness effects:**
    - P1 and P2 (each model's OMPS − OMPF), and the remaining interaction ρ = ι + P3;
    - DSHF − C (the value of search) and O − DSHF (the gap to the ceiling), per model;
    - splits by source set (viSQuAD and Vi-DROP), by Vi-DROP category and by BM25 retrievability;
    - a sensitivity run without the 7 golds flagged on 2026-11-25.
  - **Reading behaviour:**
    - **Gold passage read:** a read output contains the passage's first 80 normalised characters.
    - **Answer seen:** a read or grep output contains the gold string. This applies only to the 296 items whose gold is verbatim in the passage.
    - The score given the same read state (Phase 1).
    - Action flows with `harness_flow.py` and the six-cell module: model-chosen windows, harness-cut and elided pages, compaction, and answering straight after a grep.
  - **Format and cost:**
    - format compliance: answers of at most 8 tokens, and answers equal to their prediction;
    - outcomes, requests, tool calls and tokens.

### 8. Judge sample (fixed before data)

- **Sample.** 100 items drawn by seed 7, 50 viSQuAD and 50 Vi-DROP, stratified by Vi-DROP category. For each item, the draw-1 answers of DSHF, OMPF and OMPS for both models: 600 answers.
- **Judges.**
  - Blind shards: passage, question, gold, and the six answers in a random order, with no arm, model or score.
  - The rubric of `docs/research/reading-judge-2026-11-25/plan.md` (sha256 `ac99f17e…`), unchanged.
  - Four fresh Claude Opus 5.5 instances; each shard repeats 15 items of the next shard.
- **Reported:**
  - judge accuracy, R's bias, and TP/FP/FN/TN per cell;
  - the bias difference between arms within each model (OMPF − DSHF, OMPS − OMPF);
  - H1–H4 by judge labels on the 100 items, without tests;
  - the agreement between judges.
- **Reading rule.** When R's bias differs between two arms of one model by more than 5 points, the report flags every R-based test that uses those arms as possibly driven by scoring.

### 9. Registration (MC-118)

The registration consists of:
- a root block in `measurement_card.md`;
- the detail card `docs/measurement_cards/MC-118-diagnostic-reading-agent.md`;
- `data/diagnostic_reading_agent/registration.json`, with every frozen input hashed: protocol, prompts, corpus index and folder, item manifest, smoke reports, judge rubric, runner and analysis code.

The commit is titled `pre-register MC-118` and comes before the first benchmark-item request of either model.

## Risks / Trade-offs

- **Questions written beside their passage.** Some may be ambiguous without it ("Ai ghi bàn đầu tiên?") or match several passages. The BM25 strata show how many, and the analysis reports scores by stratum. No item is dropped, so the tests stay on the reviewed set.
- **Long files are artificial.** Unrelated passages are grouped, unlike a law. Search behaviour is comparable, but topical coherence is not. The paging check confirms that omp's paging is in play.
- **Gold leaning.** 80% of golds are one Qwen model's accepted answers. Within-model harness differences cancel most of this; R reduces the rest. The judge sample measures it.
- **Two draws.** With 400 items, H1 and H2 detect about 3–4 points; ι and P3 about 5–6.
- **Thinking and route stay confounded with the model,** as in MC-116 and MC-117.
- **Time.** The midterm report is due 28/11 and Chapter 5 v1 on 06/12. The build is about 2 days, registration about 29/11, the runs about 30/11, and the analysis about 01/12. A slip moves the card to Chapter 5's second version.
