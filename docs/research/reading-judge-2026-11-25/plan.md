# Reading-400: model-as-judge check of the automatic reading metrics (plan)

Written and hashed on 2026-11-25, before any answer was judged. It is exploratory, not a registered card. No endpoint is called; the judge is Claude Opus 5.5 inside the working session.

## Question

On the 400 human-labelled Reading-400 items (200 viSQuAD and 200 Vi-DROP), how often does each automatic metric agree with a reading of the answer that checks whether it gives the gold answer in meaning? Does each metric's error differ between Qwen and MiMo? Only an error that differs between models or harnesses biases a paired harness comparison or an interaction.

## Answers judged

The two existing omp answer sets on exactly these 400 items. Their gold equals the manifest's gold on 400/400:
- **Qwen3.5-9B-65K in omp, full tools (MC-88):** `all_res/qwen_omp_mc88/main/qwen3-5-9b-65k-omp-full-tools-mc88/scores.jsonl`;
- **MiMo-V2.6-Flash in omp, full tools (MC-89):** `all_res/mimo26_omp_mc89/final/main/mimo-v2-6-flash-omp-full-tools-mc89/scores.jsonl`.

That makes 800 answers.

## Blind judging

- **Units.** One unit is one item: the passage, the question, the gold and the two answers. The two answers appear in a random order (seed 7) as answer 1 and answer 2. Model names, runs and scores are never shown.
- **Order and shards.** The 400 items are shuffled (seed 7) into 4 shards of 100.
- **Second judge.** Each shard also carries the first 15 items of the next shard. These 60 items (120 answers) are judged by two independent instances.
- **Judges.** One fresh Claude Opus 5.5 instance per shard. Each knows only the rubric below and its shard file. Each judges by reading, not with code.

## Rubric (the label is against the gold, in meaning)

Judge the answer's **final answer**: what the response finally states as its answer. Ignore working shown before it, unless the working contradicts or replaces the final statement.

**CORRECT (1)** when the final answer gives the same answer as the gold. Accepted differences:
- **Wording:** paraphrase or synonyms ("Mỹ" = "Hoa Kỳ"), or an abbreviation that unambiguously names the same entity.
- **Numbers:** a different spelling of the same value ("3" = "ba" = "3,0"; "1.000" = "1000"; "30%" = "30 phần trăm").
- **Units, head words and dates:**
  - a unit added or omitted when the value is unambiguous ("0,61" = "0,61 người");
  - a generic head word added or omitted ("năm 1916" = "1916"; "thành phố Huế" = "Huế");
  - a fuller or shorter form of the same date.
- **Extra words:** an explanation, or a restatement of the question, provided nothing in it contradicts the gold or offers a competing answer.

When the gold has several parts (a list, a range, "A và B"), every part is required.

**WRONG (0)** in these cases:
- a different answer, or a different numeric value, even a close one;
- hedging between candidates without committing to one;
- naming the gold but stating something else as the answer;
- negating the gold;
- saying the passage does not answer the question when the gold gives an answer;
- an empty, cut-off or missing answer;
- a partial answer that drops a word that identifies the referent ("New England Sports" for "New England Sports Ventures"), or that drops one part of a multi-part gold.

**Unanswerable gold** ("không có câu trả lời", "no answer"): CORRECT only when the answer says that the passage does not answer the question.

**Flags,** recorded beside the label and not changing it:
- `hedge` = 1 when the answer offers more than one candidate;
- `gold_suspect` = 1 when, from the passage, the gold looks wrong, or the answer looks right while differing from the gold.

## Automatic metrics (each computed on the vi-reading-v3 prediction: the line after the last final-answer label, `*` and backticks deleted)

| Metric | Positive when |
|---|---|
| EM-v3 | vi-reading-v3 exact match = 1 (NFC, casefold, whitespace, edge punctuation) |
| EM-lenient | `score_reading_eval.score_pair` EM: also diacritic-insensitive and numeric equivalence |
| F1 ≥ 0.5 | vi-reading-v3 token-F1 ≥ 0.5 |
| R = 1 | gold-token recall (thesis (3.11), `run_legal_agent_v2.token_recall`) = 1 |
| R ≥ 0.5 | gold-token recall ≥ 0.5 (secondary) |

## Analysis

The judge's label is the reference. A metric is positive when it calls the answer correct.
- **TP:** the metric says correct and the judge says correct.
- **FP:** the metric says correct and the judge says wrong.
- **FN:** the metric says wrong and the judge says correct.
- **TN:** both say wrong.

Reported per metric, overall, per model and per dataset:
- the counts;
- agreement, precision TP/(TP+FP), sensitivity TP/(TP+FN), specificity TN/(TN+FP) and Cohen's κ;
- the metric's mean score minus the judge's accuracy. This is the metric's bias in points. The interaction-relevant number is the difference of this bias between Qwen and MiMo.

Also reported:
- mean token-F1 and mean R against the judge's accuracy per model;
- the judges' agreement and κ on the 120 doubly judged answers;
- the `hedge` and `gold_suspect` lists;
- every FP and FN of R = 1 and of EM-v3, as a file for reading.

Primary labels come from the shard that owns the item. Second-judge labels are used only for the agreement figure.
