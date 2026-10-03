## 1. Shuffle adapter (offline, no model calls)

- [x] 1.1 Add `code_benchmark/make_shuffled_mc_input.py` (stdlib + sha check
  only): per-item RNG `random.Random(f"{SHUFFLE_SEED}:{item_id}")`
  (`SHUFFLE_SEED=1234` constant), source sha256 verified against
  `data/legal_slm_multichoice_manifest.json`, uniqueness + gold-preservation
  fail-fasts, outputs shuffled JSONL + shuffle manifest
  (`data/legal_slm_multichoice_shuffled_s1234_manifest.json`) with
  `input_sha256`. Verify: regenerate twice → byte-identical; `--help` documents
  the seed.
  - **Bằng chứng:** module + dry-run trên source thật ra `/tmp` (chưa commit):
    146 dòng, gold_old A91/B39/C16 → gold_new A33/B45/C36/D32, gold-text
    preservation 146/146, scorable shape OK.
- [x] 1.2 Add offline unit tests in `code_benchmark/test_suite.py`
  (`TestShuffledMcInput`): determinism (same seed+id → same perm),
  subset-stability (prefix run reproduces full-run per-item output),
  gold-remap correctness on hand-made items, duplicate-choices
  hard-fail, different seeds differ. Verify `python -m unittest
  code_benchmark.test_suite` green + `ruff check .` clean.
  - **Bằng chứng:** 9 tests (`TestShuffledMcInput`) xanh; full suite 189
    tests OK; `test_parsing.py` OK; ruff sạch. Design/spec đính chính kèm:
    subset-stable thay vì order-independent (id là positional).

## 2. Pre-register (before ANY shuffled infer)

- [ ] 2.1 Generate the shuffled input + manifest, commit manifest (and input
  JSONL if tracked — see design D3) on this branch. Verify `sha256sum` of the
  committed manifest matches the value to be quoted in MC-35.
- [ ] 2.2 Write MC-35 (pre-register block) into `measurement_card.md`: model
  `Qwen3.5-9B-65K` @ IEC internal endpoint, inference flags = MC-31 arm A
  (temp 0, seed 42, max_tokens 4, workers 4), `SHUFFLE_SEED=1234`, manifest +
  input shas, wrapper/output names, no post-hoc numbers. Commit. Verify card
  commit timestamp precedes any shuffled checkpoint file mtime.

## 3. Wrapper + compare (offline code, no model calls)

- [ ] 3.1 Add `code_benchmark/run_shuffled_mc.py` wrapper (park-free variant of
  design D4): pre-run fail-fast on leftover MC-prefix files, subprocess
  `run_mc_eval.py` without `--resume`, rename outputs to shuffled names, move
  `raw_result_146_*` to gitignored `shuffled_checkpoints/`. Verify offline:
  unit-test the rename/park logic on tempdirs with fake CSVs (no network).
- [ ] 3.2 Add `code_benchmark/compare_position_bias.py`: join orig
  (`full_evaluation_legal_Qwen3_5-9B-65K.csv`) + shuffled on id; emit per-item
  compare CSV + summary (acc both sides, Δ + paired-bootstrap CI seed 42 +
  McNemar p, flip 2×2, accuracy-by-gold-position, answer-position histograms,
  blanks each side). Verify offline on synthetic CSVs with a known Δ
  (e.g. 5 planted flips → Δ and flip counts exact).
- [ ] 3.3 Full offline gate: `python -m unittest code_benchmark.test_suite`
  + `python code_benchmark/test_parsing.py` + `ruff check .` green, and
  `git diff --stat -- code_benchmark/run_mc_eval.py` empty (runner frozen).

## 4. Live run (needs VPN + IEC gateway)

- [ ] 4.1 Preflight endpoint/model (1-token call); record OK in run log. If
  down → stop, no partial files presented as results (pending, per MC-24 rule).
- [ ] 4.2 Run wrapper (146 items, ~minutes). Verify ledger/final row-count 146,
  0 blank `raw_response` unexplained, shuffled accuracy file present, orig
  arm-A files untouched (`git status` on `all_res/` shows only new shuffled
  names).
- [ ] 4.3 Run compare; verify per-item choice-set equality check passes
  (shuffled set == orig set for all 146) and acc_orig recompute = 130/146.

## 5. Record

- [ ] 5.1 Write MC-36 (results block): acc_orig/acc_shuffled/Δ/CI/p, flip
  table, accuracy-by-gold-position, answer histograms, blanks, cost (wall +
  tokens from log), `measurement_card_hash` in outputs. Verify numbers
  recompute from the committed compare CSV (second pair of eyes: rerun compare
  → identical stdout).
- [ ] 5.2 Append the one-paragraph verdict to `docs/model-insights.md`
  (position-bias section): exploit-A vs position-sensitivity reading + whether
  the VMLU-1047-shuffle and harness-shuffle follow-ups are opened or closed.
  Dashboard: no change (non-goal, proposal).
