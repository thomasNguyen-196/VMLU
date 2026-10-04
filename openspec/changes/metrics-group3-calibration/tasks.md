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

- [ ] 2.1 Write MC-41: probe result (logprobs available, structure), model,
  dataset, flags, D2/D3 rules, outputs, scope. Commit before the run. Verify
  the card commit precedes any `mc_calibration_*` artifact.

## 3. Live calibration + report

- [ ] 3.1 Preflight IEC; run the logprobs capture on legal_mc-146; verify 146
  rows, `n_letters_found` distribution, accuracy vs MC-31 note.
- [ ] 3.2 `report` → ECE/Brier/reliability; write MC-42; update
  `docs/model-insights.md` (a calibration paragraph) and the plan doc.

## 4. Optional follow-up (not gated)

- [ ] 4.1 If the first pass is clean: `vmlu-mqa-all-gold` (1,047) calibration
  for a per-category curve; else record the limitation and stop.
