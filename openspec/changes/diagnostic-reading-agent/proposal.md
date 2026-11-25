## Why

The legal-agent cards (MC-112 to MC-117) found three things, all on Vietnamese legal texts:
- **The harness gap reverses between models.** Qwen3.5-9B does worse in omp than in dsh. MiMo-V2.6-Flash does better.
- **omp's default system prompt carries much of that interaction.** MC-117, Part S: P3 −14.74, Holm p 0.0002.
- **Mechanics differ by model.** Qwen leaves read windows to the harness and omp cuts and elides pages. MiMo sets offset/limit itself.

Every one of these comes from one domain. The owner asked on 2026-11-25 for the same experiment on another field ("lên plan cho phần thực nghiệm với harness giống phần luật đi (bao gồm đổi system prompt của omp thành dsh luôn)"). The test bed is general-domain reading: Reading-400, whose 400 golds were reviewed by the owner.

A model-as-judge check run the same day (`docs/research/reading-judge-2026-11-25/results.md`) changes the scoring:
- **Token-F1 is not model-neutral on these items.** It understates MiMo by about 20 points more than Qwen. The judge puts MiMo 18.5 points ahead in omp; token-F1 puts the two level.
- **Gold-token recall R treats both models alike** (bias −2.25 points for each at R ≥ 0.5).

The owner chose on 2026-11-25:
- **Layout:** long files, as in the legal corpus ("File dài, giống luật").
- **Scoring:** R as the registered score, token-F1 beside it, and a blind judge on a sample ("R chính + giám khảo trên mẫu").

## What Changes

- **Corpus `reading_corpus_v1`.**
  - **Content.** Every distinct passage of the two source files Reading-400 was drawn from: viSQuAD 1,633 and Vi-DROP 1,186, deduplicated on normalised text into 2,284 passages and about 2.41M characters.
  - **Files.** Passages go in a fixed hash order into 46 files of 50 (median 52k characters), each passage under a heading line `## Đoạn NNNN`, one sentence per line, as a law has one clause per line. As with a law, the agent greps, then reads a small window of a long file. That keeps omp's paging and elision in play.
- **Items.** The 400 Reading-400 items (viSQuAD 200, Vi-DROP 200), with the owner-reviewed golds. The agent gets the question without its passage, so it must find the passage in the folder.
- **Arms, for each model (Qwen3.5-9B-65K and MiMo-V2.6-Flash), two draws each:**
  - **DSHF:** dsh 0.2.2-rc.1 with forced search. The instruction is MC-112's DSHF instruction reworded from legal texts to articles.
  - **OMPF:** omp 18.0.0 with its default system prompt and DSHF's task.
  - **OMPS:** OMPF with `--system-prompt` set to dsh's system prompt for the model, as in MC-117.
  - **C:** MC-96's closed-book prompt alone, without tools.
  - **O:** the frozen reading prompt with the item's own passage. This is the ceiling.
- **Counts.** 400 × 2 draws × 5 arms = 4,000 attempts per model, 2,400 of them agent attempts, so 8,000 in all.
- **Routes.**
  - Qwen: MC-115's route, IEC over the VPN.
  - MiMo: MC-116's route, OpenCode Go.
- **Runner** in new code, wrapping MC-115's, MC-116's and MC-117's runner functions without editing them. It keeps MC-117's stall rule, halted-row identity and budget-amendment hook.
- **Analysis,** fixed before data and run once.
  - **Primary family (R) and continuity family (token-F1),** each with Holm over the same four tests:
    - H1: Qwen's OMPF − DSHF;
    - H2: MiMo's OMPF − DSHF;
    - H3: the interaction ι = H2 − H1;
    - H4: the share of the interaction carried by omp's prompt, P3 = (OMPS − OMPF)_MiMo − (OMPS − OMPF)_Qwen.
  - **Beside, without tests:**
    - P1, P2 and the remaining interaction;
    - the value of search (DSHF − C) and the gap to the ceiling (O − DSHF);
    - gold-passage reading and answer-seen rates;
    - action flows, format compliance and cost.
- **Judge sample.** 100 items × 6 agent cells = 600 draw-1 answers, judged blind by Claude Opus 5.5 under the 2026-11-25 rubric. It measures whether R's bias differs between harnesses.
- **Card MC-118,** registered and committed before the first benchmark-item request. The id was named by the dropped dsh-with-omp-prompt draft, which was never registered.

## Capabilities

### New Capabilities
- `diagnostic-reading-agent`: the reading corpus, the agent and direct arms for Qwen and MiMo on Reading-400, and the registered analysis of the harness gap, the model × harness interaction and the prompt swap, scored by gold-token recall with a judge sample.

### Modified Capabilities
- None. Reused, not edited:
  - MC-112's to MC-117's modules, frozen inputs, dsh and omp installs, profiles, proxies and score files;
  - the frozen reading prompt, MC-96's closed-book prompt, and the vi-reading-v3 scorer;
  - the Reading-400 manifest and golds;
  - the campaign engine.

## Evaluation regime

A diagnostic condition with external tools at inference, as in MC-112 to MC-117. Regime B-style for Qwen (Q4_K_M GGUF on llama.cpp behind IEC). MiMo is a provider model, as in MC-116. Regimes A and C are not touched.

## Non-goals

- **No new harness and no change to dsh's or omp's tools, tool schemas or profiles.**
- **No DSHO arm** (dsh with omp's prompt). The owner dropped it on 2026-11-25.
- **No second layout** (one passage per file). That is future work.
- **No third model.** Muse was declined for content-filter risk.
- **No tuning to an outcome.** The corpus, prompts, caps, sample and analysis are fixed before any benchmark request.
- **No re-scoring of the legal cards here.** A judge pass on MC-115/116's ViBidLQA answers is a separate follow-up.

## Impact

- **New code** (offline, tested):
  - `code_benchmark/diagnostic_reading_agent.py`: corpus, items, passage locations, manifest and BM25 pre-check;
  - `code_benchmark/run_reading_agent.py`: runner, self-test and smoke test;
  - `code_benchmark/analyze_reading_agent.py`: the registered analysis and the judge sample;
  - their tests.
- **Changed:** nothing. `diagnostic_prospective.ARMS` already holds every arm id used here (DSHF, OMPF, OMPS, C and O).
- **New data** in `data/diagnostic_reading_agent/`: the protocol, the agent prompts, the corpus manifest, the item manifest and the registration. The corpus itself stays under `all_res/` (gitignored), because the source sets are not redistributed.
- **Requests:** about 4,000 per model plus smoke.
  - Qwen runs over the VPN.
  - MiMo costs about USD 12–15 by MC-117's realised rate.
- **Time:** about 2 days to build. The runs take about 10 hours per model and overlap, because the routes are separate.
