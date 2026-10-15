## 1. Calibration runner (offline first)

- [x] 1.1 Add `code_benchmark/run_mc_calibration_eval.py` (`run`|`report`):
  frozen `build_prompt`/`extract_answer`/gold reuse; `logprobs=true,
  top_logprobs=20`; `letter_probs` (bare A–E, renormalized), `ECE`/reliability,
  Brier (confidence + multiclass); per-item + summary + reliability CSVs.
  - **Bằng chứng:** module + `run`/`report`; `build_prompt`/`extract_answer`
    không đổi byte.
- [x] 1.2 Offline tests: letter distribution (letters only, absent→0, empty),
  ECE hand-computed, summary math (accuracy/mean_conf/Brier/overconfidence,
  unusable item excluded from calibration but in the denominator). Suite + ruff.
  - **Bằng chứng:** `TestMcCalibration` 4 tests; suite **236 OK**, ruff sạch.

## 2. Pre-register MC-41 (before the calibration run)

- [x] 2.1 Write MC-41: probe result (logprobs available, structure), model,
  dataset, flags, D2/D3 rules, outputs, scope. Commit before the run. Verify
  the card commit precedes any `mc_calibration_*` artifact.
  - **Bằng chứng:** MC-41 commit cùng code (sha `6959d5ef…`) trước khi chạy;
    probe: logprobs YES, token đầu = chữ cái trần, top@0 đủ A–E.

## 3. Live calibration + report

- [x] 3.1 Preflight IEC; run the logprobs capture on legal_mc-146; verify 146
  rows, `n_letters_found` distribution, accuracy vs MC-31 note.
  - **Bằng chứng:** 146/146, `n_letters_found=5` mọi câu; accuracy
    **130/146 = 89,04%** — tái lập khít MC-31 arm A.
- [x] 3.2 `report` → ECE/Brier/reliability; write MC-42; update
  `docs/model-insights.md` (a calibration paragraph) and the plan doc.
  - **Bằng chứng:** ECE 7,39pp · Brier 0,0701 · over −6,66pp; MC-42 + §1.6 +
    plan doc cập nhật.

## 4. VMLU-1047 extension (MC-43/44)

- [x] 4.1 Fix the letter-set rule first: `offered_letters` reads the prompt's own
  option block; `off_options_mass` reports what falls outside it. (MC-42 was
  wrong: legal_mc is 4-choice yet E carried up to 9.4% mass.)
  - **Bằng chứng:** `offered_letters` + tests (3/4/5-choice, gapped block fails
    fast); MC-43 pre-register commit `5784bb2`.
- [x] 4.2 Re-run `legal_mc-146` and add `vmlu_mqa_all_gold` (1,047 / 58 subjects)
  with the same model and flags; per-category + per-subject breakdown.
  - **Bằng chứng:** legal 132/146 = 90,41%; VMLU **751/1047 = 71,73%**, 1046/1047
    usable, breakdown CSV 58 môn.
- [x] 4.3 Record MC-44 and update insights + plan doc.
  - **Bằng chứng:** MC-44 (kết quả + nhiễu backend + hạn chế), §1.6, plan doc.

## 5. Not done (out of scope)

- Safety (group 3.2) — needs its own rubric + gold; no measurement attempted.
- A second model for the calibration contrast — `Qwen3.5-9B-28K` is offline
  (503), so no cross-model claim is made.
