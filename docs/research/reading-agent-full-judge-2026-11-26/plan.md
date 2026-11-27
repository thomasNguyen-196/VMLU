# MC-118, exploratory: a blind judge on all 4,800 agent answers (plan)

Written and hashed on 2026-11-26, before any of these answers was judged. This is **not part of MC-118's registration.** The registered analysis (report `9c376d4c…`) and the registered judge sample (report `dd8219cb…`) stand. This pass is exploratory and is reported beside them.

## Why

The registered judge sample covered 600 draw-1 answers on 100 items. It flagged R's bias on OMPS − OMPF for both models:
- Qwen −5.51 points;
- MiMo +5.60 points.

On those 100 items, the judge put Qwen's OMPS 9 points above OMPF, where R showed +2.8. The owner asked on 2026-11-26 for Opus to read all 4,800 agent answers ("cho Opus quét qua 4800 câu đi").

## Answers

Every DSHF, OMPF and OMPS answer of both models on all 400 items, both draws: 2 × 3 × 2 × 400 = 4,800. C and O are not judged.

## Blind judging

- **Units.** One unit per item: the passage, the question, the gold, and the item's 12 agent answers in an order permuted by seed 7. Model, arm, draw and score are never shown.
- **Shards and judges.** Items are shuffled by seed 7 into 14 shards of 28–29 items. Each shard goes to one fresh Claude Opus 5.5 instance.
- **Rubric.** The rubric of `docs/research/reading-judge-2026-11-25/plan.md` (`ac99f17e…`), unchanged, with answer slots 1–12.
- **Reliability.** The 600 answers judged in the registered sample are judged again here by different instances. The agreement between the two passes is the reliability figure.

## Analysis (exploratory)

The judge label (1/0) is the score. The item score is the mean over the two draws.

- **H1–H4 on judge labels,** defined as in MC-118: H1 Qwen OMPF − DSHF; H2 MiMo OMPF − DSHF; H3 ι; H4 P3. Statistics as registered: 95% percentile bootstrap (2,000 resamples, seed 7), two-sided paired sign-flip p (20,000 resamples, seed 7), Holm over the four. **These are exploratory, not registered tests.**
- **Beside:**
  - P1, P2 and the remaining interaction;
  - judge accuracy per arm and model;
  - R's bias per cell, with TP/FP/FN/TN for R ≥ 0.5 and R = 1;
  - splits by source set;
  - agreement with the registered sample's labels;
  - the `gold_suspect` and `hedge` counts.
