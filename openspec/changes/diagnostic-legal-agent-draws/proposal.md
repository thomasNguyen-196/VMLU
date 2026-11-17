## Why

MC-112, MC-113 and MC-114 ran each agent arm **twice** per item. A power check on their per-item score files (2026-11-16, offline, exploratory) shows that two draws leave most of the noise in place:

- **Draw-to-draw noise dominates.** About three quarters of the variance of the per-item difference DSHF − OMPF is the agent answering the same item differently in its two draws. Only about a quarter is a real difference between items. The within-item SD of one draw is 28–40 points on multiple choice and 25–28 token-F1 points on ViBidLQA.
- **More draws therefore shrink the noise without new items.** The smallest OMPF − DSHF gap detected with 80% power at α = 0.05 (no Holm) falls from 7.1 to 5.7 points on the 246 multiple-choice items, and from 4.4 to 3.5 F1 on the 400 ViBidLQA items, when each item has 4 draws instead of 2.
- **Items cannot be added on multiple choice.** The Legal MC pool is exhausted (134 of VLSP 2025's 146 items are used; the other 12 are core items), and VMLU's law subjects have only 112 gold items, all in MC-114.
- **The question the noise blocks most** is whether the best agent beats the direct call on multiple choice: DSHF − B is +5.1 points on the 246 items, against a detectable gap of 6.8.

The owner chose two more draws per item (2026-11-16: "okay, thực hiện đi, mức 4 lượt 1 câu").

## What Changes

- **Draws 3 and 4** of DSHF and OMPF on the 646 items of MC-114's analysis, and of each part's no-tool baseline (B on Part M, C on Part S):
  - **Part M (multiple choice), 246 items:** MC-112/113's 134 Legal MC items and MC-114's 112 VMLU law items.
  - **Part S (span), 400 items:** MC-114's ViBidLQA items, closed-book.
- **Each new attempt repeats its item's earlier condition exactly:** the same task bytes as draw 1, the same harness pins, sandbox, proxy and limits, and the same corpus folder (corpus_v1 for the Legal MC items, as in MC-112/113; corpus_v2 for the other items, as in MC-114). Only the draw number and the date differ.
- **Manifest by copying.** MC-112's, MC-113's and MC-114's manifests are rebuilt and must equal their frozen files. Each new attempt is the frozen draw-1 item of its arm with only the replicate id changed (`-r3`, `-r4`). B on the Legal MC items uses the frozen MC prompt that MC-111's B sent.
- **Runner `run_legal_agent_draws.py`.** It reuses MC-114's runner functions and MC-112's and MC-113's code without editing them. It picks the folder per item.
- **Smoke test,** 4 attempts, no benchmark item: MC-112's corpus question on corpus_v1 and one of MC-114's span questions on corpus_v2, each once with DSHF and once with OMPF. It needs the VPN, so the owner is asked first.
- **Analysis,** fixed before data and run once. The item score is the mean over 4 draws. Part M asks OMPF vs DSHF, DSHF vs B and OMPF vs B; Part S asks OMPF vs DSHF, DSHF vs C and OMPF vs C; Holm over 3 within each part. Draws 3–4 alone and the drift between rounds are reported beside, not tested.
- **Card MC-115,** registered and committed before the first benchmark-item request.

## Capabilities

### New Capabilities
- `diagnostic-legal-agent-draws`: two more draws of MC-112/113/114's agent arms and baselines in their original conditions, the per-item folder, and the registered four-draw analysis.

### Modified Capabilities
- None. Reused and not edited: MC-112's, MC-113's and MC-114's modules, frozen inputs, manifests and score files; MC-111's score file; the frozen MC and reading prompts and scorers; the campaign engine.

## Evaluation regime

Regime B-style only, as MC-90 to MC-114: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint.

## Non-goals

- **No new items and no new arms.** DSH and O are not re-run; their two draws stay as they are.
- **No change to the earlier cards.** Their registered results stand. MC-115 reports its own tests.
- **No tuning.** Prompts, caps, folders and items are copied from the earlier cards.

## Impact

- **New code** (offline, tested): `code_benchmark/diagnostic_legal_agent_draws.py` (protocol and manifest), `code_benchmark/run_legal_agent_draws.py` (runner and smoke test), `code_benchmark/analyze_legal_agent_draws.py` (analysis), and a test module for each.
- **New data** in `data/diagnostic_legal_agent_draws/`: `protocol.json`, `manifest_v1.json`, `registration.json`.
- **Outputs** in `all_res/diagnostic_legal_agent_draws/` (gitignored).
- **Requests:** 2,584 agent attempts (Part M 984 = 246 × 2 × 2; Part S 1,600 = 400 × 2 × 2) and 1,292 direct requests (492 B, 800 C).
- **Tokens:** about 176M by the earlier cards' real per-attempt cost; budget guard 270M (× 1.5, rounded up).
- **Time:** about 8–9 hours at four attempts in flight, by MC-112/113/114's real time per attempt, over the VPN as a `systemd-run` unit with `--resume`.
- **Comparison limits** (written into the card): draws 1–2 were seen before this registration; draws 3–4 run 2–3 days after them on the same endpoint; for B on the Legal MC items, draws 1–2 come from MC-111, a different card.
