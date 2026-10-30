## Context

See proposal.md for the motivation. The plan builds on these pieces:

- **The campaign engine.** It runs any arm whose prompt is frozen in a manifest, with guards, scoring and resume (MC-90 to MC-101). It already accepts a retrieval trace per K row.
- **Existing arms.**
  - B, S, Q: prompts.
  - K: BM25 over a corpus. For Legal MC this is `vi-legal-corpus-lmc-v1`, 303 documents and 24,265 units.
  - O: oracle provisions, a ceiling only.
  - The `omp` harness (`run_harness_eval.py`, frozen genomes): MC-86 to MC-89 ran four models with full tools, against direct-API runs MC-80 to MC-85.
- **The two-answer probe** of router v2. Its cascade form, "B twice, escalate when they differ", was evaluated in MC-94 (VMLU: 76.7% against 68.3% for always-B and 80.0% for always-S). It was simulated for Legal MC on MC-101 data: 87.3% against 84.3%.
- **The LLM-router client of MC-98:** Muse Spark 1.3 with a closed output grammar, about 3,100 tokens and 13 s a call.
- **Outcome data for Qwen3.5-9B:** about 18,000 scored attempts across arms and draws (MC-90 to MC-101).
- **Fresh items with gold remain** in VMLU (about 390 valid and dev items not used by any router), VM14K (thousands) and ViBidLQA train (about 1,100). None remain in Legal MC, Vi-SQuAD or Vi-DROP.

## Goals / Non-Goals

**Goals:**
- One loop procedure for every student model. Only its weakness map changes per model.
- An honest test on fresh items: whether a router that reads the answer beats the rule loop, at the cost it actually adds.
- Answers to the thesis questions for at least two student models: where each model is weak, and which enhancement repairs what.

**Non-Goals:**
- Training student models.
- Free-text coaching that could carry the answer (see Decision 3).
- Covering every available model.

## Decisions

### 1. Architecture: five parts
1. **Student models.** Qwen3.5-9B (IEC), plus one or two API models chosen in Phase 0.
2. **Knowledge stores (RAG):**
   - **Evidence store:** the item's own passage when the task has one, `vi-legal-corpus-lmc-v1` at article and clause level, corpus v0, and the ViBidLQA passages.
   - **Experience store:** past cases. Each case holds the dataset, the question, the model, the arm, whether the two B answers agreed, and the outcome. Cases are retrieved by similarity, never for the item being answered and never for an evaluation item.
3. **Router-critic:** one LLM call per consulted round, with a closed output (Decision 3).
4. **Enhancement menu:** registered arms (Decision 4).
5. **Loop controller and cost ledger:** rounds, stop rule, final answer, and every token.

The pre-answer routers failed because the question alone predicts little. The critic instead judges an answer it can see, with evidence in hand, which is how tool-based critics such as CRITIC correct outputs. The literature also warns that self-correction without new information does not help (Huang et al., 2024). That is why every prescription must bring something new: evidence, a procedure or a tool.

### 2. Detection in two stages
- **Stage 1, every item:** ask B twice. Different parsed answers raise a flag. This costs one extra student call and caught 30 of 42 wrong first answers on Legal MC.
- **Stage 2, the router-critic.** It always runs on flagged items. It runs on unflagged items only if Phase 3 shows it catches enough "confident errors" (two equal wrong answers; 12 of 42 on Legal MC) to pay for calling it on every item. That choice is registered before Phase 4.

### 3. Router-critic output: closed, and no answer injection
The critic returns one JSON object:
- `verdict`: `likely_correct`, `likely_wrong` or `unsure`;
- `cause`: one of `knowledge_or_evidence`, `reasoning`, `reading`, `format`, `instability`, `other`;
- `prescription`: one menu id, optional evidence unit ids chosen from the retrieved candidates, and an optional focus note of at most 200 characters;
- `rationale`: kept in the log and never sent to the student.

The student receives only what the menu item renders: the template, the chosen evidence units verbatim, and the focus note if it passes the leak check. The leak check rejects any note that contains an option letter in an answer pattern, an option's text, or answer phrases ("đáp án", "chọn …"). Free-form coaching is not used: it could carry the answer and could not be reproduced. Whether the focus note helps is an ablation in Phase 3.

### 4. Enhancement menu v1 (each a registered arm)
| id | Enhancement | Status |
| --- | --- | --- |
| E0 | Resample B | exists |
| E1 | S, step by step | exists |
| E2 | Q, quote then answer | exists |
| E3 | Clause-level retrieval, the top clauses rather than whole units | new; MC-101 showed whole units dilute |
| E4 | Critic-selected evidence, from the retrieved candidates | new |
| E5 | Calculator or Python tool for arithmetic (Vi-DROP style) | new, via the harness tool loop |
| E6 | `omp` harness with tools, a frozen genome | exists (MC-86 to MC-89) |
| E7 | Self-consistency vote over k samples | new, cheap |
| E8 | Escalate to a stronger model | new; must beat "router alone" on cost |

Phase 1 delivers E0–E4 and E7. E5, E6 and E8 enter once their wrappers pass offline tests.

### 5. Loop and stop rule
- **Rounds:** at most 3 after the first answer.
- **Stop** when an enhancement's answer equals the previous round's answer, or when the critic says `likely_correct`.
- **Final answer:** the answer of the last round that the critic did not reject. If it rejected every round, the most frequent answer, with ties broken in favour of B.

All three choices are registered, and Phase 3 may tighten them only on calibration data.

### 6. Weakness map per model (Phase 2)
- For each student: about 60 fresh calibration items per dataset (VMLU, VM14K, ViBidLQA), each run with B twice and every menu item once.
- The map records, per dataset and per cause group, the rescue rate and the damage rate of each enhancement, plus its cost.
- The map is frozen per model. A new model joins by running this calibration only; the loop itself does not change.

### 7. Evaluation (Phase 4)
- **Items:** about 300 fresh items per dataset per student, disjoint from calibration. Legal MC, Vi-SQuAD and Vi-DROP are reported as exploratory on their used items.
- **Conditions per student:**
  - always-B;
  - the best fixed enhancement per dataset, chosen on calibration;
  - the rule loop (B twice; on disagreement, the dataset's best enhancement);
  - the critic loop;
  - router alone (the critic model answering the item);
  - the oracle-detector ceiling, offline.
- **Primary comparison:** the critic loop against the rule loop per student, on quality at the reported cost, with Holm correction across students.
- **Reading rule:** fixed in the Phase 4 registration, before data.

### 8. Fallback: learned router (Phase 5)
- **When:** only if the critic fails its Phase 3 or Phase 4 rule.
- **Data:** every (item, model, arm, draw) outcome, with evaluation items excluded.
- **Features:**
  - question embedding (BGE-M3, already cached);
  - dataset;
  - whether the two answers agreed;
  - answer type;
  - token log-probabilities where the provider gives them.
- **Target:** whether an enhancement rescues the item.
- **Models**, in this order: logistic regression, gradient boosting, then a small MLP on frozen embeddings. All use grouped cross-validation by item.
- **Policy:** choose the enhancement with the best expected gain minus a registered cost weight.
- **Expectation, stated now:** with a few thousand cases per model and Adaptive-RAG's 54.5% classifier accuracy as precedent, this is likely exploratory or future work.

### 9. Timeline
| Dates | Phase | Output |
| --- | --- | --- |
| 30/10–1/11 | 0 | Router and student models, quota and budget, Notion scope |
| 1/11–5/11 | 1 | Rule-loop simulation on all Qwen data; experience store; E0–E4 and E7; MC-80–89 harness review |
| 5/11–10/11 | 2 | Calibration cards and weakness maps for 2–3 students |
| 10/11–17/11 | 3 | Critic design check on calibration data; go or no-go |
| 23/11 | gate | Chapters 1–3 and the analysis skeleton (MC-90–101, loop design, first maps) |
| 17/11–30/11 | 4 | Held-out evaluation card and run |
| December | 5 | Learned router if triggered; writing; submission 12–15/12 |

## Risks / Trade-offs

- [The critic is simply a better model, so the loop adds nothing over asking it] → "Router alone" is a required baseline, and cost is reported beside quality.
- [The critic leaks answers through its notes] → A closed output, evidence copied verbatim and a code leak check; rejected notes are logged and counted.
- [Enhancements damage right answers, as K did on easy Legal MC items] → Enhance only flagged or critic-rejected answers, and report damage rates per enhancement.
- [Confident errors escape both stages] → Measure the critic's recall on them in Phase 3 and report the remainder.
- [API quotas and costs: Jev's free tier stopped after about 234 requests a window] → Phase 0 checks every model, and each card carries an estimate and a budget guard.
- [Too few fresh items: none left in Legal MC, Vi-SQuAD or Vi-DROP] → Evaluate on VMLU, VM14K and ViBidLQA; report the rest as exploratory.
- [Time against writing] → Writing runs in parallel. If Phase 3 slips, the thesis reports the rule loop plus the weakness maps, and the critic becomes future work.
- [Earlier LLM routers matched cheap rules (MC-98)] → The Phase 3 go or no-go gate runs before any held-out spending.

## Decisions pending the owner (Phase 0)

1. **Router-critic model:** decided 2026-10-30: Muse Spark 1.3 for now. The owner asked for near-term results first and left the other decisions for later.
2. **Student models:** Qwen3.5-9B plus MiMo V2.6 Flash, and optionally a third, after checking quotas.
3. **Monthly API budget.**
4. **Escalation (E8):** a menu item, or only the "router alone" baseline.
