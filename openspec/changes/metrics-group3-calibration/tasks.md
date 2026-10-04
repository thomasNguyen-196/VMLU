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

## 4. Optional follow-up (not gated)

- [ ] 4.1 If the first pass is clean: `vmlu-mqa-all-gold` (1,047) calibration
  for a per-category curve; else record the limitation and stop.
  - **Chưa làm** (tùy chọn) — lượt đầu sạch; mở rộng chờ quyết định.
