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

- [x] 3.1 Add `code_benchmark/run_shuffled_mc.py` wrapper (park-free variant of
  design D4): pre-run fail-fast on leftover MC-prefix files, subprocess
  `run_mc_eval.py` without `--resume`, rename outputs to shuffled names, move
  `raw_result_146_*` to gitignored `shuffled_checkpoints/`. Verify offline:
  unit-test the rename/park logic on tempdirs with fake CSVs (no network).
  - **Bằng chứng:** `TestRunShuffledMcWrapper` 6 tests xanh (argv frozen,
    không `--resume`; conflicts bắt đúng namespace count-only, bỏ qua
    dataset-scoped; rename/park; refuse overwrite).
- [x] 3.2 Add `code_benchmark/compare_position_bias.py`: join orig
  (`full_evaluation_legal_Qwen3_5-9B-65K.csv`) + shuffled on id; emit per-item
  compare CSV + summary (acc both sides, Δ + paired-bootstrap CI seed 42 +
  McNemar p, flip 2×2, accuracy-by-gold-position, answer-position histograms,
  blanks each side). Verify offline on synthetic CSVs with a known Δ
  (e.g. 5 planted flips → Δ and flip counts exact).
  - **Bằng chứng:** `TestPositionBiasCompare` 6 tests xanh (planted 2×2=8/2/5/5
    → Δ +15,00 và p == `_mcnemar_p(2,5)`; baseline gate; id/multiset/gold-text
    fail-fasts; breakdown partition). Affixes parse từ chính probe
    `build_prompt` — contract drift sẽ fail loud.
- [x] 3.3 Full offline gate: `python -m unittest code_benchmark.test_suite`
  + `python code_benchmark/test_parsing.py` + `ruff check .` green, and
  `git diff --stat -- code_benchmark/run_mc_eval.py` empty (runner frozen).
  - **Bằng chứng:** suite **201 tests OK**; test_parsing OK; ruff sạch;
    `git status --short code_benchmark/run_mc_eval.py` rỗng.

## 4. Live run (needs VPN + IEC gateway)

- [x] 4.1 Preflight endpoint/model (1-token call); record OK in run log. If
  down → stop, no partial files presented as results (pending, per MC-24 rule).
  - **Bằng chứng:** VPN `openvpn3` session `iec-tcp` (proto tcp, `tun0`
    172.16.30.7/24); DNS shim `/tmp/opencode/pyshim` (map `llmapi.iec` →
    172.16.50.172); probe 1-token `'A'` OK 2026-10-04 10:2x.
- [x] 4.2 Run wrapper (146 items, ~minutes). Verify ledger/final row-count 146,
  0 blank `raw_response` unexplained, shuffled accuracy file present, orig
  arm-A files untouched (`git status` on `all_res/` shows only new shuffled
  names).
  - **Bằng chứng:** 146/146, 149,53s, **0 blank**; 8 retry thoáng qua tự hồi;
    `full_evaluation_shuffled_s1234_*` + `accuracy_shuffled_s1234_*` +
    2 checkpoint park; `full_evaluation_legal_*` (arm A) nguyên vẹn.
- [x] 4.3 Run compare; verify per-item choice-set equality check passes
  (shuffled set == orig set for all 146) and acc_orig recompute = 130/146.
  - **Bằng chứng:** compare pass toàn bộ fail-fast (id set, multiset,
    gold-text, baseline gate); stdout: Δ +0,00, CI −5,48..+5,48, p=1,
    stability same_text 126 / letter_anchored 4 / neither 16.

## 5. Record

- [x] 5.1 Write MC-36 (results block): acc_orig/acc_shuffled/Δ/CI/p, flip
  table, accuracy-by-gold-position, answer histograms, blanks, cost (wall +
  tokens from log), `measurement_card_hash` in outputs. Verify numbers
  recompute from the committed compare CSV (second pair of eyes: rerun compare
  → identical stdout).
  - **Bằng chứng:** MC-36 trong `measurement_card.md`; compare chạy lại 2 lần
    (lần 2 sau khi thêm cột stability) ra cùng số; hash `2669c665…` ghi trong
    summary CSV. **Bổ sung so với plan:** cột stability theo text
    (same_text/letter_anchored/neither) — thêm vào compare + spec + design
    ngày 2026-10-04 vì flip-count thuần không tách được nội dung khỏi vị trí.
- [x] 5.2 Append the one-paragraph verdict to `docs/model-insights.md`
  (position-bias section): exploit-A vs position-sensitivity reading + whether
  the VMLU-1047-shuffle and harness-shuffle follow-ups are opened or closed.
  Dashboard: no change (non-goal, proposal).
  - **Bằng chứng:** §1.4 "Position bias" + cập nhật taxonomy §5; mốc dừng ghi
    trong MC-36: cả hai follow-up **ĐÓNG**.

## 6. UI — nhận xét lên `/results` + `/benchmark` (yêu cầu bổ sung 2026-10-04)

- [x] 6.1 Register `qwen3-5-9b-65k` in `seed_registries.MODELS` + migrate its
  arm-A runs (legal-mc-146, legal-nli-150, reading-400, bidlqa-val / MC-31) so
  the model is visible on `/results` + `/benchmark`. V-Bench 65K waits for a
  track-aware plan (split 4141+1000 files; not merged silently).
- [x] 6.2 `web/lib/insights.ts`: curated seed `legal-mc-146` ×
  `qwen3-5-9b-65k` carrying the MC-36 verdict (89,04%; Δ +0,00; same-text
  126/146; caveat "không suy sang bộ khác"); `insights.test.ts` +1 test.
- [x] 6.3 Migration support: `runner_config()` dataset-scoped keys (MC-31
  spans 4-token legal + 48-token reading), `accuracy_summary_rows()` derives
  the aggregate from the committed final when an arm-A run wrote none
  (`run_legal_arm_a.py` prints instead of writing) — same `build_accuracy_rows`,
  never a second scorer; 2 new Python tests.
  - **Bằng chứng:** suite 204 OK, ruff sạch; `bun test lib/insights.test.ts`
    14 pass; `tsc` sạch; Mongo: seed 4 models + migrate 17 runs / 38.202 items,
    verify 0 blocking diffs; `/api/results/models` lists `qwen3-5-9b-65k`;
    summary API trả 130/146 = 89.04; `buildInsight` end-to-end với summary thật
    → curated, verdict mang kết quả position bias; `/benchmark?model=qwen3-5-9b-65k`
    render "LegalSLM (146 câu) 89.04%".
