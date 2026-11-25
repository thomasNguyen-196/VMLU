# Reading-400: model-as-judge check of the automatic reading metrics (results)

Run on 2026-11-25 under `plan.md` (sha256 `ac99f17e…`, written before judging; `analyze` checks it is unchanged). Exploratory.

## Setup

- **Code and outputs.**
  - Code: `code_benchmark/judge_reading400.py`; tests in `test_judge_reading400.py`.
  - Outputs (gitignored) under `all_res/reading_judge_20261125/`: `report.json` (sha256 `4a4728fe…`), `judged.csv` and `disagreements.csv`.
- **Answers.** 800 in all: Qwen3.5-9B-65K in omp (MC-88) and MiMo-V2.6-Flash in omp (MC-89), on the 400 Reading-400 items.
- **Judges.** Four fresh Claude Opus 5.5 instances, each holding one blind shard: no model names and no scores. Each judged by reading, against the gold in meaning, with the pre-written rubric.
- **Judge reliability.** 60 items (120 answers) were judged twice by different instances. They agreed on 119/120 answers (99.2%), κ 0.97. This measures consistency between instances, not validity against a human.

## Judge accuracy against the metric means (points)

| | Judge accuracy | Mean token-F1 | Mean recall R |
|---|---|---|---|
| Qwen, all | 75.75 | 68.49 | 72.16 |
| MiMo, all | 94.25 | 67.78 | 90.90 |
| Qwen, viSQuAD | 91.5 | 82.99 | 86.94 |
| Qwen, Vi-DROP | 60.0 | 53.98 | 57.38 |
| MiMo, viSQuAD | 97.5 | 83.23 | 95.28 |
| MiMo, Vi-DROP | 91.0 | 52.33 | 86.52 |

Token-F1 puts the two models level (68.5 against 67.8). The judge puts MiMo 18.5 points ahead. Qwen's wrong answers are mostly on Vi-DROP (80 of 200).

## Each metric against the judge (800 answers; positive = the metric calls the answer correct)

| Metric | TP | FP | FN | TN | Agreement | κ | Bias Qwen | Bias MiMo | MiMo − Qwen |
|---|---|---|---|---|---|---|---|---|---|
| EM-v3 | 384 | 0 | 296 | 120 | 63.0% | 0.28 | −23.00 | −51.00 | −28.00 |
| EM-lenient | 391 | 0 | 289 | 120 | 63.9% | 0.29 | −22.25 | −50.00 | −27.75 |
| token-F1 ≥ 0.5 | 549 | 12 | 131 | 108 | 82.1% | 0.50 | −4.75 | −25.00 | −20.25 |
| R = 1 | 593 | 4 | 87 | 116 | 88.6% | 0.65 | −11.75 | −9.00 | +2.75 |
| R ≥ 0.5 | 645 | 17 | 35 | 103 | 93.5% | 0.76 | −2.25 | −2.25 | 0.00 |

The bias is the metric's rate minus the judge's accuracy, in points.

## Readings

1. **Every metric errs mostly by FN.** It marks correct answers wrong; false positives are rare.
2. **EM and token-F1 are not model-neutral.** MiMo writes fuller answers ("8 ghế" for the gold "8"). EM and F1 penalise this, so they understate MiMo by 20–28 points more than Qwen. A between-model comparison or interaction scored with them carries this bias, unless the bias is the same under both harnesses. This check measured only omp answers.
3. **Recall treats the two models alike.**
   - R ≥ 0.5 is closest to the judge: −2.25 points for both models, κ 0.76.
   - R = 1 misses more correct answers, but by a similar amount for each model (bias difference +2.75).
4. **Why R = 1 misses correct answers (87 FN).**
   - Golds that are longer than the answer needs: "3 định luật" or "8 đề cử Oscar" against "3" or "8".
   - Number words against digits: "ba" against "3", "thứ tư" against "4".
   - Paraphrase or a function word: "tại Paris, Pháp" against "Paris, Pháp".
   - Tokenisation slips: "Clubở", superscript exponents.
5. **Why R = 1 passes wrong answers (4 FP).** The answer contains the gold but adds a wrong competing item (General Atomics as a user force; Bletchley Park beside the gold place), or states a different count while mentioning the gold's.
6. **Gold check.** The judges flagged 7 golds (1.75%):
   - viSQuAD 316, 2370 and 2435 (2435 gives a range 633–656 for "which year");
   - Vi-DROP 1723, 2216 (an ambiguous question), 2741 (the passage gives 15, the gold 17) and 7048.

## Limits

- **The judge is a model, not a human.** Agreement between instances is high, but agreement with a human reader is not measured. A human audit of a sample of the 296 EM false negatives and of the R disagreements would establish it.
- **One harness only.** The answers come from omp, so the dependence of each metric's bias on the harness is not measured here.
