## Why

MC-112 (dsh) and MC-113 (omp) let Qwen3.5-9B search a complete local folder of Vietnamese legal texts before answering the 134 Legal MC items, two draws each. Two of their questions ended with gaps of about 6 points and no clear answer:

- **Forcing search** (DSHF against DSH, MC-112): +5.97, Holm p .165.
- **The harness** (OMPF against DSHF, MC-113): −6.34, Holm p .061.

A power check on the per-item scores (2026-11-14) showed why. With 134 items × 2 draws, the smallest gap these tests detect with 80% power is about 9 points for both questions. More draws on the same items cannot fix it: the floor from 134 items alone is about 6.2 points for forcing and 4.5 for the harness. The Legal MC pool is exhausted, because VLSP 2025 LegalSLM has only 146 multiple-choice items (134 wide, 12 core).

The owner chose to add new items from datasets already on disk (2026-11-14: "Thêm câu mới", then "dùng các dataset có sẵn đi", then "Cả hai"):

- **VMLU law subjects:** the 112 gold items of subjects 37–42 and 45 (dev 33, valid 79). They are multiple choice like Legal MC, so they pool with it. Qwen's closed-book accuracy on them is about 56% over earlier cards, against 86.6% on Legal MC, which leaves room for search to help.
- **ViBidLQA, closed-book:** the question without its passage, to be answered by searching the folder. Each item names the article of Luật Đấu thầu 2023 that holds its answer, so whether the agent read that article is checked automatically. In MC-96, Qwen scored about 14 token-F1 closed-book and about 59 with BM25's top-2 articles. Finding the article therefore decides most of the score, and a difference in search between the harnesses should show clearly.

## What Changes

- **Corpus folder `corpus_v2`** (built, offline, uncommitted). It is MC-112's `corpus_v1` (310 files, byte for byte) plus 25 pages from hethongphapluat.com:
  - the 23 documents a gold-aware coverage audit of the 112 VMLU items needed (2026-11-14, four agents, every quote checked by code);
  - Luật Đấu thầu 2023 and its Nghị định 24/2024.

  That gives 335 files, 46.7M characters, none truncated, folder SHA-256 `2b40c1c7…`.
- **Item provisions** (`item_provisions_v2.jsonl`, MC-112's keys).
  - **VMLU items.** From the audit: 86 `supports_gold`, 4 `unclear`, 1 `contradicts_gold`, and 21 `no_provision` (textbook theory that no legal text decides). The owner's spot-check of 14 items replaces the agents' labels on those items.
  - **ViBidLQA items.** The heading line of the article each context names.
- **Two parts, each with its own registered tests:**
  - **Part M (multiple choice).** The 112 VMLU law items. Arms DSH, DSHF and OMPF (MC-112's and MC-113's harnesses, unchanged), and B, all at two draws. The tests pool these items with MC-112/113's 134 Legal MC items, so they cover 246 items.
  - **Part S (span).** 400 ViBidLQA items, the first 400 in a fixed hash order of the 926 usable ones. Arms DSH, DSHF and OMPF on MC-96's closed-book prompt, C (that prompt alone, without tools) and O (the frozen reading prompt with ViBidLQA's own passage, as a ceiling), all at two draws. Scored with vi-reading-v3 token-F1.
- **Prompts v2.** Part M tasks are MC-112's, byte for byte: the arm's instruction, a blank line, then the frozen MC prompt. Part S tasks use the same instructions, then MC-96's registered closed-book question prompt, byte for byte, which C also sends.
- **One runner for both harnesses**, `run_legal_agent_v2.py`. It imports MC-112's and MC-113's sandbox, proxy and parser code without editing them. Its direct arms (B, C and O) use the campaign request of MC-90 to MC-111.
- **Smoke test** on corpus_v2 with questions written for it, run through both harnesses. It sets the budget and needs the VPN, so the owner is asked first.
- **Analysis.** Fixed before data and run once.
  - **Part M:** harness and forcing on the pooled 246 items, Holm over 2.
  - **Part S:** harness, forcing, and DSHF against closed-book C, Holm over 3.
  - **Description:** search behaviour, retrieval hits, scores when the provision was read and when it was not, and cost.
- **Card.** MC-114, registered and committed before the first benchmark-item request.

## Capabilities

### New Capabilities
- `diagnostic-legal-agent-v2`: corpus_v2, the new items and their provisions, prompts v2, the two-harness runner with its direct arms, span scoring, and the registered two-part analysis.

### Modified Capabilities
- None. These are reused and not edited:
  - MC-112's modules and frozen inputs (`diagnostic_legal_agent.py`, `dsh_proxy.py`, `dsh_relay.py`, `run_legal_agent.py`, the dsh install and profile);
  - MC-113's modules and frozen inputs (`run_legal_agent_omp.py`, `omp_trajectory.py`, the `omp` binary and configuration);
  - the frozen MC prompt, extractor and scorer;
  - the frozen reading prompt and the vi-reading-v3 scorer;
  - the campaign engine;
  - MC-111's, MC-112's and MC-113's outputs, which are read only.

## Evaluation regime

Regime B-style only, as MC-90 to MC-113: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint. Regimes A and C are not touched.

## Non-goals

- **No more draws on the 134 Legal MC items,** and no re-run of MC-112's or MC-113's arms. Their score files enter the pooled tests by SHA-256.
- **No gated or newly downloaded dataset** (ALQAC was dropped by the owner).
- **No ViBidLQA decree items.** Their contexts follow a draft whose article numbers and wording differ from the issued Nghị định 24/2024. The decree file stays in the folder as a topical companion.
- **No scaffold-taking-apart arms** (no harness without tools, no empty folder), as the owner ruled for MC-112.
- **No tuning to an outcome.** The prompts, caps, folder and sample are fixed before any benchmark request.
- **No second model, no web access, no tool besides `read`, `grep` and `glob`.**

## Impact

- **New code** (offline, tested):
  - `code_benchmark/diagnostic_legal_agent_v2.py` (written): corpus_v2, items and provisions.
  - `code_benchmark/run_legal_agent_v2.py`: manifest, the two harness paths, the direct arms, statuses, scoring and the smoke test.
  - `code_benchmark/analyze_legal_agent_v2.py`: the analysis.
  - Tests for each.
- **New data** in `data/diagnostic_legal_agent_v2/`:
  - `added_documents_v2.json` (written);
  - `item_provisions_v2.jsonl`;
  - `agent_prompts_v2.json`;
  - `protocol.json`;
  - `smoke_questions_v2.json`;
  - `manifest_v1.json`;
  - `registration.json`.
- **Outputs** go to `all_res/diagnostic_legal_agent_v2/` (gitignored).
- **Requests:**
  - **Agent attempts:** 3,072. Part M has 672 (112 × 2 × 3); Part S has 2,400 (400 × 2 × 3).
  - **Direct requests:** 1,824 (224 B, 800 C and 800 O).
  - **Tokens:** roughly 190M, mostly context re-sent by the agents, going by MC-112/113's 96K tokens per DSHF attempt and 82K per OMPF attempt. The smoke test sets the budget.
  - **Time:** about 10 hours at four attempts in flight, over the VPN, as `systemd-run` units with a VPN watcher and `--resume`.
- **Comparison limits** (written into the card):
  - **Mixed cards in Part M.** The pooled tests mix cards. The 134 Legal MC items come from MC-112/113 on corpus_v1; the 112 VMLU items come from this card on corpus_v2, a superset. Adding items was decided after seeing those cards' p-values, although the pooled tests are fixed before the new data exist.
  - **Stale golds.** Many VMLU golds follow superseded law (13 items follow Luật Giáo dục 2005). The folder holds both versions, so an agent that reads the current law can answer "wrong".
  - **The folder.** It is gold-aware and complete, so it is an upper bound for real search.
  - **Earlier use.** ViBidLQA items appeared in earlier cards (test as reading, train in MC-96 and the self-loop). Nothing here was chosen from their outcomes.
  - **Span scoring.** It punishes long answers. A verbose agent answer loses token-F1 precision; that is part of the package being measured.
