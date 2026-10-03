# Design: 2.1 position bias on legal_mc-146

## Context

- Source: `v_legal_slsp/legal_slm/multichoice.jsonl` rows
  `{question, choices[] (raw texts, NO letters), answer (0-based index),
  answer_choice_letter}`; sha256 in
  `data/legal_slm_multichoice_manifest.json` (`7b7d7f15…`, n=146).
- Arm-A adapter (`load_legal_mc` in `run_harness_eval.py:294`): letters raw
  texts **in source order** (`A. …`, `B. …`, …) then frozen `build_prompt`.
  Gold distribution in source order: A 91 / B 39 / C 16 (MC-10).
- `run_mc_eval.py` consumes JSONL `{id, question, choices[], answer?}` and
  builds the prompt **verbatim** from `choices` (`build_prompt`, byte-frozen).
  So a shuffled input JSONL with pre-lettered, remapped choices needs **zero**
  runner changes.
- Output-collision audit (2026-10-03): `all_res/ollama_result/Qwen3_5-9B-65K/`
  holds dataset-scoped legal files (`full_evaluation_legal_*`,
  `raw_result_legal_mc_*`) but **no** MC-prefix `raw_result_146_*`,
  `full_evaluation_Qwen3_5-9B-65K.csv`, or `accuracy_Qwen3_5-9B-65K.csv`.
  A shuffled `run_mc_eval.py` run therefore writes fresh files — which the
  wrapper still renames immediately so the model dir never mixes conditions
  (park precedent: MC-14b `vm14k_checkpoints/`).

## Decisions

### D1 — Scope: legal_mc-146 only, model Qwen3.5-9B-65K
n=146 runs in minutes at workers=4 and pairs exactly with the MC-31 arm-A
baseline (89.04%). NLI is binary (shuffle = swap Có/Không — uninformative);
VMLU-1047/VM14K shuffles are follow-ups gated on the effect size here.

### D2 — Adapter-only, runner byte-frozen
New `make_shuffled_mc_input.py` + wrapper `run_shuffled_mc.py`. `run_mc_eval.py`
(including `build_prompt`/`extract_answer`/`detect_scorable`/`score_row`) is
verified `git diff`-empty at the end. Rationale: the frozen contracts are the
thing being *tested* (does position change what the same parser scores?), so
they cannot be the thing being *edited*.

### D3 — Shuffle: per-item RNG, seed 1234, fail-fast on duplicates
- `SHUFFLE_SEED = 1234` (fixed; distinct from data seed 42; recorded in shuffle
  manifest + MC-35).
- Permutation per item from `random.Random(f"{SHUFFLE_SEED}:{item_id}")` —
  deterministic and **subset-stable**: any prefix/`--limit` run reproduces the
  same per-item output (no sequential RNG stream). It is NOT invariant under
  source reordering (ids are positional: `LG-i` = i-th source row) — the
  source-sha pin is what forbids silent reordering.
- Gold remap by **text identity**: gold text = raw choices[gold index]; new gold
  = its index in the shuffled list. Adapter hard-fails if an item's choice
  texts are not unique (remap would be ambiguous) or if the gold text is lost.
- Output A: shuffled input JSONL `{id: LG-XXXX, question, choices: ["A. …",
  "B. …", …] (shuffled+lettered), answer: <new letter>}` — scorable shape, so
  the runner's own `accuracy_*` output is the shuffled accuracy with no extra
  scorer.
- Output B (tracked, committed **before** first infer): shuffle manifest with
  `{benchmark, split, n, seed: 42, shuffle_seed: 1234, source_file,
  source_sha256, input_sha256, items: [{id, gold_new, gold_old, perm}]}`.

### D4 — Output isolation without touching the runner
`run_shuffled_mc.py` (wrapper, no model call itself):
1. Fail-fast if MC-prefix `raw_result_*_Qwen3_5-9B-65K.csv`,
   `full_evaluation_Qwen3_5-9B-65K.csv`, or `accuracy_Qwen3_5-9B-65K.csv`
   already exist (a previous shuffle leaked — do not silently mix).
2. Subprocess `run_mc_eval.py --folder <shuffled_dir> --file <shuffled.jsonl>`
   with MC-31 arm-A inference flags (temp 0, seed 42, max_tokens 4, workers 4),
   **no `--resume`**, `--submission-out` pointed at a shuffled name.
3. Rename fresh outputs → `full_evaluation_shuffled_s1234_*`,
   `accuracy_shuffled_s1234_*`; move `raw_result_146_*` → gitignored
   `shuffled_checkpoints/` park dir. Restore nothing (nothing was parked —
   orig arm-A files have different names by construction, §Context).

### D5 — Comparison: paired, with the A-bias table
`compare_position_bias.py` joins orig (`full_evaluation_legal_Qwen3_5-9B-65K.csv`)
with shuffled on `id` and writes `position_bias_compare_legal_mc_s1234.csv` +
stdout summary:
1. acc_orig (expect 130/146 = 89.04%), acc_shuffled, Δ + paired-bootstrap 95%
   CI (seed 42) + McNemar exact p — same statistics family as every MC card.
2. Flip analysis: # items where the parsed letter changed; 2×2 correctness
   (right→right / right→wrong / wrong→right / wrong→wrong).
3. Accuracy **by gold position**, orig vs shuffled — the decisive table: orig
   golds are A-heavy (91/39/16); shuffled golds are ~uniform. If the model
   merely exploits "A is likely", acc_shuffled drops toward the uniform-gold
   expectation while per-position accuracies stay flat.
4. Model answer-position histogram both sides (does it over-predict A?);
   blanks/unparseable counted separately per MC-34 doctrine, never folded
   into the Δ.
- Prompt-parity gate is **inverted on purpose**: shuffled prompts MUST differ
  from arm A. Integrity check instead: per-item choice-text set equality
  (shuffled set == orig set) + gold-text-follows-gold-letter recompute.

### D6 — Cards: pre-register MC-35, results MC-36
MC-35 written and committed before any shuffled infer (manifest sha inside).
MC-36 holds the numbers. Card rule "mỗi lần chạy một khối, không sửa khối cũ"
applies; MC-35 stays untouched after the run.

## Risks

| Risk | Mitigation |
|---|---|
| Gateway down (recurring IEC outages, MC-24/MC-31) | preflight first; pending-resume, never fabricate; run is minutes, not hours |
| Shuffled run pollutes 65K dir on crash | wrapper step 1 fail-fast re-run detects leftovers; park dir keeps them out of `find_latest_checkpoint` glob reach of other runs (MC-prefix glob only matches same slug — documented, and step 1 refuses to run dirty) |
| Duplicate choice texts in an item | adapter hard-fails (D3); inspect, then decide (drop item with card note vs tie-break — no silent choice) |
| Effect smaller than noise (n=146 → CI ~±7) | report as "below resolution", gate follow-ups (VMLU-1047 shuffle, harness shuffle) on CI excluding 0 |
