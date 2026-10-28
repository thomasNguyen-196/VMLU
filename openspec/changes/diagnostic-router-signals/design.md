## Context

See `proposal.md` for the motivation.

**Reused pieces:**

- **The menu set.** `diagnostic_menu.design_items()` returns the 967 wide reading items in manifest order:

  | Dataset | Items |
  | --- | --- |
  | ViBidLQA test | 591 |
  | Vi-DROP | 188 |
  | Vi-SQuAD | 188 |

  Each item's frozen main-v1 prompt hashes to its MC-90 B prompt.
- **The cells.** `analyze_menu_q.load_cells` returns per item the B, Q and S draws, each twice:
  - B-r1 and S-r1 from MC-90;
  - B-r2 from MC-91;
  - S-r2 from MC-92;
  - Q-r1 and Q-r2 from MC-97.
- **The MC-98 artefacts.** The six groups, their keyword comparator and the cross-draw mapping are in `data/diagnostic_llm_router/router_v1.json` and `diagnostic_llm_router.py`. The Muse labels are in `all_res/diagnostic_llm_router/labels/muse-spark-1-3-contributor/labels.jsonl`.
- **The VMLU sources.**
  - MC-94 and MC-95 hold B and S twice on 660 VMLU items: 300 in MC-94 and 360 in MC-95.
  - MC-43/44 hold, for all 1,047 VMLU dev and valid items, the temperature-0 B answer, its correctness and its first-token letter probabilities.

## Goals / Non-Goals

**Goals:**
- Measure what each signal source can capture of the per-item benefit, on the same footing, and decide by a registered rule which policies earn a held-out card.

**Non-Goals:**
- Any new student-model request.
- Any held-out evaluation.
- Any model training other than the fixed ridge rule of Decision 5.

## Decisions

### 1. Requests

- **Pre-hoc (J1).** One request per item. The state is `{"passage", "question"}`, taken from the item's frozen reading prompt (`parse_frozen_prompt`).
- **Post-hoc (J2).** Two requests per item, one per B draw. The state is `{"passage", "question", "proposed_answer"}`. The proposed answer is the scored `prediction` of B-r1 (MC-90 scores) or B-r2 (MC-91 scores), exactly the string the frozen scorer graded.
- **Questions.** Instructions and option descriptions are in English, because Jev's documentation gives English as its primary training language. The passage, question and answer stay in Vietnamese.
- **J1 group question.** A Choice over the six MC-98 group ids, with the MC-98 definitions translated. Muse was told that an earlier group wins a tie; Jev returns probabilities, and the analysis takes their argmax.
- **J1 yes/no questions (Noul).** Seven, each returning the probability that the statement is true:
  - `asks_designation`;
  - `needs_computation`;
  - `asks_whole_list`;
  - `asks_one_part`;
  - `asks_condition`;
  - `verbatim_short`;
  - `passage_insufficient`. This one was added at the owner's question about per-group techniques, so that a later router has a signal for when outside evidence is needed.
- **J2 yes/no questions (Noul).** Four:
  - `answer_correct`;
  - `answer_complete`;
  - `answer_extra`;
  - `answer_verbatim`.
- 967 + 2 × 967 = **2,901 requests**.

### 2. Route

- **Endpoint.** Host `opencode.ai`, path `/inference/systemone/v1/systemone`, model `jev-1.13-free`.
- **Credential.** The OpenCode key in the local auth store, read in the runner process and never written out.
- **Headers.**
  - `x-opencode-session`, derived from the run key;
  - a stable user agent.
- **Limits.**
  - 2 requests in flight;
  - a 120 s timeout;
  - the run halts after 4 consecutive network failures.
- **Retries.** A 429 or 5xx response is re-sent after the `Retry-After` wait, or 30 s without one, at most 5 times; every retry is recorded.
- **Other halts.**
  - non-free billing: `usage.cost` above 0, or `billing_source` other than `free`;
  - a different response model;
  - a 401 or 403 response.

### 3. Manifest

- One row per request, with:
  - the run key `dataset:item:<kind>` (`jev-pre`, `jev-post-B1`, `jev-post-B2`);
  - the SHA-256 of the canonical request body without the model field;
  - the SHA-256 of the state;
  - for post-hoc rows, the answer source.
- The header records:
  - the configuration SHA-256;
  - the menu manifest's self-hash;
  - the SHA-256 of the MC-90 and MC-91 scores files.
- The manifest is self-hashed and frozen as `jev_signals_manifest_v1.json`. The runner rebuilds it and refuses any difference.

### 4. Scores and baseline

- **Scores.** Token-F1 on reading, accuracy on VMLU. Student-model tokens are the `total_tokens` of the scored rows.
- **The best fixed per-dataset policy** is the baseline of the reading rule:
  - Per dataset, it takes the arm with the best mean on one draw (B, Q and S on reading; B and S on VMLU) and scores it on the other draw, both ways, averaged.
  - Ties go to the more thorough arm (B < Q < S), as in MC-98.

### 5. Policies (fixed before data)

**Reading, pre-hoc (B, Q and S unless stated):**

- **P1. The baseline.**
- **P2. Keyword groups**, by the MC-98 comparator. The cross-draw mapping is applied per dataset:
  - each group's arm is chosen on one draw and scored on the other;
  - a group has at least 20 items;
  - smaller groups take the dataset's fixed arm of the same draw.
- **P3. Muse groups** (MC-98 labels) on ViBidLQA, with the other datasets taking P1. This is descriptive.
- **P4. Jev groups:** the argmax of `group`, mapped as P2.
- **P5. Jev groups gated by confidence:** the group counts only when Jev's choice confidence is at least 0.5; otherwise the item takes the dataset's fixed arm.
- **P6. Ridge rule, B or S.**
  - Features: the 7 J1 yes/no probabilities, the 6 group probabilities and a dataset one-hot.
  - Target: the S − B token-F1 of the fitting draw.
  - Fit: ridge with λ = 1 on features standardised within the training folds.
  - Folds: 5, by passage (SHA-256 of the passage id, mod 5).
  - Each held-out fold takes S when the prediction is positive, and is scored on the other draw. Both directions are averaged.

**Reading, post-hoc (B, then S if escalated, on the same draw k):**

- **P7. Agreement.** Accept B_k when the normalised B-r1 and B-r2 predictions agree, else S_k. Cost: both B calls plus S_k when escalated.
- **P8. Jev check.** Accept B_k when P(`answer_correct` | B_k) ≥ 0.5.
- **P9. Jev check with a cross-fitted threshold.** The threshold τ is chosen on the other draw from 0.05, 0.10, …, 0.95 to maximise mean token-F1. Ties go to the lower τ, which escalates less.
- **P10. Jev combined check.** Accept when P(`answer_correct`) × P(`answer_complete`) × (1 − P(`answer_extra`)) ≥ 0.5.
- Cost for P8 to P10: B_k, plus S_k when escalated.
- **References:**
  - the same-draw oracle, the better of B_k and S_k by outcome;
  - the cross-draw per-item bound.

**VMLU (J3, 660 items, B and S):**

- **M1.** Always-B at temperature 0 (the MC-43/44 answer).
- **M2.** Always-S (S_k).
- **M3.** Agreement of B-r1 and B-r2, else S_k.
- **M4.** Logprob cascade: accept the temperature-0 B answer when its first-token confidence is at least τ, else S_k. τ is chosen on the other draw from 0.50, 0.51, …, 0.99. Ties go to the lower τ.

At run time, one temperature-0 B call with logprobs gives both the answer and the confidence, so M4 needs no probe call. Its B tokens are taken from the campaign B row of the same item.

One of the 660 MC-43/44 rows has no letter confidence. That row counts as confidence 0, so M4 always escalates it, and the report gives the count. This was found by counting empty fields, before any outcome was computed.

### 6. Ceiling block

For each dataset and arm pair with two draws of both arms, the block reports:

- the correlation of per-item differences between draws;
- the number of items each arm wins on both draws;
- the cross-draw per-item gain over the better fixed arm;
- the distribution-free cap (m + √(m² + τ²))/2 − max(m, 0), with τ² = cov(d1, d2);
- the normal-model estimate.

The arm pairs are:

- reading: S − B, Q − B, Q − S;
- VMLU: S − B;
- MC-96: K − B, KS − K, O − K.

This block was first computed exploratorily on 2026-10-28, before this design, from scripts in the session scratchpad. The registered analysis recomputes it with the frozen plan.

### 7. Statistics

For each policy against P1 (reading) and against M2 (VMLU), the analysis reports the per-item difference:

- its mean;
- a percentile bootstrap interval, 2,000 resamples, seed 7;
- a two-sided sign-flip p-value, 20,000 resamples, seed 7.

These are descriptive: the items are design data.

### 8. Reading rule

A policy is promising if either holds against P1, or M2 on VMLU:

- **Quality:** its pooled score is at least 1.0 point higher.
- **Cost:** its score is at most 0.5 points lower, at no more than 60% of the student-model tokens.

Promising policies go to a held-out card. The others stop here.

## Risks / Trade-offs

- **Language.** Jev's accuracy on Vietnamese is unknown and documented as lower than on English. A weak result may reflect the language, not the method. The analysis reports how spread Jev's probabilities are, so a flat signal is visible.
- **Free tier.** Jev's free tier is limited in time and may rate-limit. The runner retries a limited number of times, `--resume` continues, and non-free billing halts the run.
- **Design data reused.** All 967 items served earlier designs. Every result here is design-stage.
- **J3 conditions.** The MC-43/44 answers come from a temperature-0 run at another time. The S draws come from MC-94 and MC-95 at temperature 1.0.

## Migration Plan

New files only. Nothing registered is rewritten.
