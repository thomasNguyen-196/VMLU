# Self-Evolving Evaluation Harness for Vietnamese LLM Benchmarks

**Thesis plan — kickoff document.** Working title: *"How much benchmark score can a fixed
quantized Vietnamese LLM rent from its harness — and can that rental be evolved
automatically, honestly?"*

Owner: nttung245 (undergrad thesis). Compute: institutional OpenAI-compatible endpoint
(`Qwen3.8-27B-Q4_K_M.gguf`), laptop for orchestration. All pipeline code lives in this
repo; this document is the design contract for the evolution layer.

---

## 1. Research questions

- **RQ1 (decomposition).** How much of a measured benchmark score is model capability
  vs. harness engineering? Pilot evidence in hand: minimal vs detailed prompt changes
  42.2% of agentic answers (415/983, 213 with a different function chosen) — same
  model, same seed, temperature 0.
- **RQ2 (evolution).** Can an automated search over a *closed harness genome*
  (elicitation strategy, few-shot/CoT, RAG mechanism, tool menu, resource budget)
  outperform both the human-tuned baseline and a flat grid search, under a fixed
  compute budget?
- **RQ3 (transfer & limits).** Does a harness evolved on VMLU-MQA gold dev transfer to
  held-out domains and to V-Bench (different task formats), or is harness knowledge
  benchmark-specific?
- **RQ4 (honesty protocol).** Can a frozen-scorer + immutable-answer design keep the
  evolutionary loop from reward-hacking, and what fraction of naive-score gains survive
  auditing? (Expected failure mode from our own history: parser relaxation and format
  repair masquerading as capability.)

Primary headline result either way: *the first quantified harness-capability
decomposition for Vietnamese benchmarks, produced by an auditable self-improvement
loop.* Negative results (e.g., "evolution adds ≤2 points after 150 generations") are
stated as findings, not failures.

## 2. What this is, relative to prior art

| System | What evolves | Fitness | We take |
|---|---|---|---|
| **DGM** ([jennyzzt/dgm](https://github.com/jennyzzt/dgm), [arXiv:2505.22954](https://arxiv.org/abs/2505.22954)) | the agent's own **code**, open-ended | SWE-bench / Polyglot per-instance gold tests | archive of diverse agents; per-candidate evidence folders; outer-loop mechanics; lineage visualization; the discipline "every self-modification must pass external empirical validation" |
| **ADAS** (Hu et al. 2024, arXiv:2408.08435) | agent **design in code**, meta-programming | fixed benchmarks | search-over-designs framing with a *fixed target model* — exactly our setting |
| **Promptbreeder / APE / OPRO** | prompts only | benchmark score | mutation operators for prompt genes; honest compute accounting |
| **This plan** | a **closed genome** of harness genes around a frozen model | per-item gold on a frozen internal dev split; V-Bench = final exam only | — |

Key structural difference from DGM we must state in the thesis: in DGM the evolving
system *is* the coder (frontier API models self-modify arbitrary code). Here the
benchmark model (quantized local 8B) is **not** the optimizer — it is the thing being
scaffolded. So our loop is ADAS-style search *with* DGM-style evidence/archive
discipline, and the meta-agent is an external, disclosed API model.

## 3. Invariants (design axioms — CI-enforceable, non-negotiable)

1. **The scorer is frozen.** Gold answers, the agentic validator (`_validate_call`),
   the MC parser (`extract_answer`, byte-frozen contract), and the dev/test splits are
   outside the genome. A mutation touching them disqualifies the lineage.
   (Repo precedent: fail-fast + byte-frozen contracts + `test_parsing.py` parity suite.)
2. **Answers are never repaired.** The harness may re-ask, re-frame, retrieve, use a
   tool — the final submitted artifact must be traceable to a model decision.
   `raw_response` remains the single source of truth; the failure ledger stays
   verbatim. (User's rule, already encoded since the first V-Bench run.)
3. **One condition per checkpoint namespace.** Evolution runs reuse the repo's
   per-model slug isolation (`--model harness<gen>_<id>`), so generations never mix.
4. **Every candidate ships an evidence folder** (DGM pattern): genome JSON + git diff of
   the harness code, dev-set results CSV, per-item ledger, run log, token/wall budget.
   One command must reproduce the score.
5. **Disclosure by construction.** Final tables always report: minimal-baseline,
   best-single (oracle), evolved, and grid-search arms at matched compute, plus the
   condition table (the paper-grade artifact our V-Bench runs already established).

## 4. Harness genome (closed grammar, v0)

```jsonc
{
  "elicitation":  "zero_shot_minimal | zero_shot_detailed | cot | fewshot_k",
  "fewshot":      {"k": 0, "selection": "random | same_domain | hardest_wrong"},
  "option_order": "as_is | seed_shuffle",              // known MC variance source
  "answer_format": {"template_id": "...", "retries": 0, "repair_syntax_only": true},
  "rag":          {"off | bm25 | dense | hybrid", "corpus": "viwiki | vbpl | mixed",
                  "top_k": 3, "merge": "none | concat | auto"},
  "tools":        ["none" | "calculator" | "date_arith" | "enum_verbatim_lookup"],
  "resources":    {"max_tokens": 512, "temperature": 0, "samples_per_item": 1},
  "agentic_extra": {"guided_fallback": false}           // third-condition per V-Bench docs
}
```

- Tool genes are **pre-written and reviewed** (menu, not synthesis) in P0–P3; the
  calculator and `enum_verbatim_lookup` are motivated by measured error clusters:
  Vi-DROP arithmetic dominates the 79 rejected 400-set items, and near-miss enums
  dominate agentic rejections. Allowing synthesis (DGM-style free codegen) is P4/
  future-work and then requires the sandbox (see §7).
- Genome → runner mapping: `prepare_prompt(item, style)` and `process_item` are already
  parameterized hooks; evolution wraps the existing runners, no fork.

## 5. Fitness data & budget

- **Dev (fitness):** 1,047 VMLU-MQA gold items + 400 reviewed reading items (EM/F1 once
  gold merge lands). Stratified 300-item dev slice per generation (reuse
  `make_eval_sample.py` machinery), full 1,447 every 10th generation to catch
  slice-overfitting.
- **Test (frozen, once):** held-out VMLU gold slice + full V-Bench submission — the
  graduation exam for the evolved harness, scored offline (VMLU items) then submitted
  once (V-Bench). V-Bench itself is **never** a fitness signal (no per-item gold,
  aggregate-only feedback; see the discussion in the failure-mode log of Sep 4).
- **Compute:** ≈3–5 min per 300-item MC eval at workers=4; ≈50 min for 1,000 agentic.
  Population 8 × 15 generations ≈ 120 evals ≈ 2–3 days of shared endpoint. Grid
  baseline (30–50 points) and temp-ensemble control included.

## 6. Loop (ADAS/DGM outer, thin)

1. Seed: hand-encode current repo state as baseline genome + 8 hand-designed mutants.
2. Evaluate each genome on dev slice (existing runners), write evidence folder.
3. Meta-agent (disclosed API model) receives archive summaries + failure-ledger
   aggregates → proposes N mutations/crossovers; **hypothesis required per mutation**
   ("add calculator: 74/79 rejected items are arithmetic" — it must cite the ledger).
4. Guard pass (§3 invariants) → evaluate → insert into archive (quality-diversity:
   keep best-per-domain, not just global best — DGM archive rationale).
5. Every 10th gen: full-dev + drift report. End: freeze best lineage's final harness,
   run Test, write disclosure tables.

## 7. Explicitly NOT inherited from DGM (scope control)

- **Arbitrary self-modification of agent code** — replaced by the closed genome (the
  thesis claim survives without it; a semester does not survive with it).
- **Docker sandbox for untrusted generated code** — not needed while tools are a fixed
  menu; becomes mandatory the day we allow codegen tools. DGM's own safety warning is
  the citation for why we defer this.
- **Frontier-model coder as the improving subject** — our meta-agent only proposes
  genome edits (≤10 lines of config/template), keeping its capability ceiling out of
  the headline claim.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Reward hacking the scorer | invariants §3 + evidence folders + human adjudication queue reusing the **review UI** for flagged mutations |
| Grid ≈ evolution (search space saturated at format genes) | honest pre-registered comparison; the *decomposition* (RQ1) is publishable regardless |
| Meta-model confound | disclose; ablate meta-agent (random mutation vs LLM-guided mutation) — that itself is a chapter |
| Endpoint contention / cost | checkpoints+resume already handle restarts; budget matched-compute in tables |
| V-Bench release drift (`VB_SCORED_EXPECTED` warning) | final submission pinned to v2026.03.28 checksum |

## 9. Milestones

- **P0 (wk 1–2):** `harness_genome.py` spec + guard tests; evidence-folder writer;
  baseline + oracle-condition runs (minimal/detailed already exist as seeds).
- **P1 (wk 3–4):** grid search (30–50 points) incl. calculator & option-shuffle genes;
  variance decomposition tables (RQ1) + confidence intervals via bootstrap.
- **P2 (wk 5–7):** evolution loop (8×15); archive plots; mutation-hypothesis ledger.
- **P3 (wk 8–9):** frozen final harness → Test + V-Bench single submission; transfer
  report (RQ3); honesty audit (RQ4): score gains before/after adjudication.
- **P4 (stretch):** one DGM-style free-codegen experiment inside a container
  (opt-in, clearly capped) — "what the grammar denied us, codegen finds", sandboxed.

## 10. Reading list (validated)

- DGM repo: <https://github.com/jennyzzt/dgm> — read `DGM_outer.py`,
  `coding_agent.py`, `analysis/visualize_archive.py`, one `initial/logs/...` evidence
  folder as the template for our per-candidate artifacts.
- DGM paper: <https://arxiv.org/abs/2505.22954> · Sakana blog: <https://sakana.ai/dgm/>
- ADAS: arXiv:2408.08435 · Promptbreeder: arXiv:2309.16797 · Self-consistency:
  arXiv:2203.11171 · MMLU reliability/"Are we done": SWE-bench-style contamination
  survey found via 2026 search: arXiv:2502.17521
- Vietnamese context: VMLU (ACL 2025, in-repo PDF) · V-Bench v2026.03.28 spec ·
  VialectBench arXiv:2608.10414 (dialect robustness — the neighboring result we must
  cite and differentiate from: we study harness variance, not dialect variance)

---

*Companion artifacts in this repo:* `AGENTS.md` §V-Bench (conditions & invariants),
`code_benchmark/run_vbench_eval.py` (`--prompt-style`, `--guided`, ledger),
`report/2026-09-04/report_vbench.{html,pdf}` (the pilot measurement), failure ledgers
and `vbench_result_*` checkpoints (raw evidence per §3.4 precedent).
