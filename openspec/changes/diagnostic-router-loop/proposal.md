## Why

Every router tested so far (rules v1–v3, the K2 cascade, the Muse LLM router of MC-98) decided *before* the student answered. None beat a fixed strategy per dataset by a measurable margin, and Adaptive-RAG reports the same. Per-item "winning" strategies repeat only about 56% of the time across draws (MC-97), so guessing from the question alone is mostly guessing noise.

On 2026-10-30 the project owner asked for a different router:

- it looks at the student's answer;
- it reasons, with retrieved evidence and what earlier experiments learned, about whether and why the answer is weak;
- it applies an enhancement (prompt, evidence, tools, the `omp` harness, …) and asks again, up to n rounds;
- it works for several student models, not only Qwen3.5-9B. The owner sees this as the complete router.

Two results make this worth trying.

**A simple loop already helps.** On the MC-101 data (exploratory, no new request), the loop "ask B twice; if the answers differ, ask with the law (K)" scores 87.3% on Legal MC, against 84.3% for always-B and 84.7% for always-K. It calls K on 16% of items. A detector that always knew a wrong first answer would reach 91.4%. Asking twice flags 30 of 42 wrong first answers.

**Evidence fixes failures that the question alone cannot predict.** In MC-100, the governing provision lifted the items Qwen had missed from 37% to 83%.

The owner also set the fallback: if an LLM router cannot do this, a learned router (deep learning) comes next.

## What Changes

A phased plan; each phase that sends benchmark requests gets its own pre-registered card.

- **Phase 0, scope and access.**
  - Choose the router model and 2–3 student models, with the API quota and budget of each.
  - Update the thesis scope (Notion) with the owner's agreement.
- **Phase 1, offline foundations (no new requests).**
  - The *rule loop* baseline, simulated on existing Qwen data for every dataset.
  - An *experience store* of past (item, model, enhancement, outcome) cases.
  - The *enhancement menu* v1: S, Q, K at clause level, a calculator tool, multi-sample voting, the `omp` harness with tools, and escalation to a stronger model.
  - A first look at MC-80–MC-89 (direct API against `omp` full tools for four models).
- **Phase 2, a weakness map per model.** A small calibration run per student model: B twice and each enhancement once on about 60 fresh items per dataset.
- **Phase 3, router-critic.**
  - An LLM reads the question, the passage if any, the student's answers, retrieved evidence, similar past cases and the model's weakness map.
  - It returns a closed-format verdict (likely wrong or not), a cause and a prescription (which enhancement, with which evidence).
  - It is checked on calibration data against a reading rule written before data.
- **Phase 4, held-out evaluation** on fresh items, per student model, with n ≤ 3 rounds. The loop with the router-critic is compared with:
  - always-B;
  - the best fixed enhancement per dataset;
  - the rule loop;
  - the router answering by itself.

  Every token of every round and of the router is counted.
- **Phase 5, fallback.** If the router-critic fails its rules, train a learned router to predict which enhancement rescues an answer, on the outcome data of all runs. It is reported as exploratory unless it is tested on held-out items.

## Capabilities

### New Capabilities
- `diagnostic-router-loop`: the closed-loop router protocol — gold-free runtime inputs, the enhancement menu, the stop rule, per-model calibration, cost accounting and the evaluation contract.

### Modified Capabilities
- None. Existing arms, templates, scorers and frozen runs are reused unchanged.

## Evaluation regime

Regime B-style for Qwen3.5-9B (Q4_K_M GGUF on the IEC endpoint), as MC-90 to MC-101. The other student models and the router are API models whose serving precision is not observable; their conditions are recorded per card. Regimes A and C are not touched.

## Non-goals

- No training of the student models (no fine-tuning, no RL).
- No change to the frozen benchmark prompts, parsers or scorers; enhancements are new arms with their own cards.
- The router never sees the gold. It must not hand the student an answer: prescriptions carry evidence, procedure or tools, never an option letter or an answer phrase.
- Not every available model: two or three students within the thesis, the rest future work.
- No headline claim on Legal MC: all 146 items have been used, so Legal MC results stay exploratory.

## Impact

- **New code:**
  - an experience store and its builder;
  - enhancement wrappers (clause-level retrieval, calculator, voting, harness, escalation);
  - a router-critic client with a closed output grammar;
  - a loop runner on the campaign engine;
  - calibration and evaluation analyses.
- **Data:** per-model weakness maps and loop manifests in `data/diagnostic_router_loop/`; runs in `all_res/diagnostic_router_loop/` (gitignored).
- **Requests:** calibration and evaluation for 2–3 students plus router calls. These are estimated per card before registration; the router is called only where the plan says.
- **Timeline:** the 50% gate on 2026-11-23 needs chapters 1–3 and the analysis skeleton. Phases 0–2 fit before it, and Phases 3–4 run in late November. Phase 5 is December or future work.
