## 1. Judge tool upgrades (offline)

- [x] 1.1 `judge_faithfulness.py`: reasoning-fallback parser (last explicit
  `"verdict"`), `judge_once` re-ask on parse failure only, `--exclude` on
  `sheet`, and the v2 defaults (`--judge-reasoning-effort ""` = omit,
  `--judge-max-tokens 1500`, `--judge-retries 2`).
  - **Bằng chứng:** parser fallback + `judge_once` + `--exclude` implemented;
    `run_reading_eval.py`/`score_reading_eval.py` untouched.
- [x] 1.2 Tests: reasoning-fallback takes the last verdict, `judge_once` re-asks
  only on parse failure and gives up after the budget, exclusion keeps the
  sample disjoint. Suite + ruff green.
  - **Bằng chứng:** 4 test mới; suite **230 OK**, ruff sạch.

## 2. Pre-register MC-39 (before ANY judge call on the test set)

- [ ] 2.1 Write MC-39: judge `kimi-k3` @ Zen Go, prompt = MC-38 v2 bytes, no
  reasoning pin, `max_tokens=1500`, retries 2, temp 0/seed 42; dev = MC-38
  labels, test = fresh seed 43 excluding dev; gate ≥0,80 and κ≥0,60; **no
  iteration**; stop rules. Commit. Verify the card precedes any test judge CSV.

## 3. Fresh test sample + human labels

- [ ] 3.1 Generate the fresh 60 (`--seed 43 --exclude <dev labels>`), commit the
  scaffold `data/faithfulness_labels_<label>_test.csv`, run the local labeler
  (autosave). Human labels committed BEFORE any judge verdict on the test set.

## 4. Gate on the fresh test

- [ ] 4.1 Preflight Zen Go; judge the fresh 60 with the v2 instrument; `validate`
  → agreement + κ. Record the decision in MC-40 (part 1).

## 5. Outcome

- [x] 5.1 Pass → full 400-item judge pass (same config); MC-40: compliance,
  EM/char-F1, verbatim rate, supported rate, `correct ∧ supported`, cross-tab,
  test-κ caveat; `docs/model-insights.md` §1.5 rewritten from "chưa đo được" to
  the result; optional `/results` seed.
  - **Không thực hiện** — cổng test fail (κ 0,4809), đúng luật một-phát.
- [x] 5.2 Fail → 2.2 closed permanently; MC-40 records the second instrument
  failure (κ numbers) as the final negative result; no faithfulness score.
  - **Bằng chứng:** MC-40 ghi test κ=0,4809 (n=59, 1 ô trống bỏ rõ) vs dev
    κ=0,666 (lạc quan); 2.2 đóng vĩnh viễn; §1.5 cập nhật; không chấm full 400.
