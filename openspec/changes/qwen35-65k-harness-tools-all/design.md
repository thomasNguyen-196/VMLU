## Context

See `proposal.md` — Why. The constraints that shape the approach, all measured on
2026-09-30 against `https://llmapi.iec-uit.com/v1` (Qwen3.5-9B-65K):

- Backend is a llama.cpp-class server behind an nginx gateway: error messages name
  a context size of `65,024` tokens, responses carry `timings` counters and a
  build fingerprint `b11243-fc07d781e`; admin surfaces (`/props`, `/docs`,
  `/openapi.json`) answer 403/502, so host detail beyond this is not obtainable
  through the public API.
- Throughput: prefill ≈ 3.2–3.6k tok/s and decode ≈ 105 tok/s. Off-prompt
  identical prompts reuse the KV prefix (a serial repeat showed `cache_n 4752`),
  but a mixed load of 16 varying suffixes at 8-way concurrency showed `cache_n 0`
  for every request — plan with **no prefix-cache benefit**.
- The captured condition request (clean scaffold, neutral system prompt, omp
  default tool menu) is **14,177 prompt tokens**: 11 tools, 50,348 chars of tool
  schemas, a 690-char system message, a 282-char user turn. API round trip for
  that item: 4.4–4.7 s (prefill-bound).
- A 32-way concurrency sweep (96 queued ~4k-token prompts) coincided with the
  gateway going silent for ~6 minutes (TCP accepted, no HTTP), then recovering.
  Small cached prompts peaked at ~14.5 req/s at 8-way; uncached prefill showed no
  aggregate gain from 4→8 workers.

Scale implication: arm B over 6,319 items at ~14–15k prompt tokens/item ≈ 90M
prompt tokens ≈ 8–10 h of server time, of which `vbench_mc` (4,141 items) is
about two thirds. Arm A is cheap (~5M tokens).

## Goals / Non-Goals

**Goals:**

- Ship the `--tools all` sentinel with byte-identical behavior for the two
  existing forms, plus tests.
- Run and register the Qwen3.5-9B-65K ladder (arm A + clean scaffold × default-all
  tools) with per-dataset checkpoints that survive an outage.
- Put the server-reality evidence (limits, rates, request inventory, incident)
  into the measurement card, not into code.

**Non-Goals:**

- No change to any frozen contract: `build_prompt`, `extract_answer`, reading
  prompt, scorers, review columns.
- No omp-persona arm, no skill/rules-enabled arm, no high-concurrency tuning of
  the shared gateway.
- No MiMo M7 run gated by this change (follow-on phase only).

## Decisions

- **`all` = omit the flag, not a literal value.** omp documents `--tools`
  default as "all", and the capture proves the default menu in this flag context
  is 11 tools. Passing the string `all` risks fuzzy-match surprises; omitting the
  flag is exactly the documented default. Alternatives: a literal `--tools all`
  (rejected: undocumented), a repo-side enumeration of omp's full menu (rejected:
  drifts with omp upgrades).
- **Condition label carries the menu provenance.** The run's condition string
  records `tools=all (omp default)`, so a later omp upgrade that changes the
  default menu shows up as a condition difference, not a silent data change.
- **Workers: 4 (hard cap 6).** Aggregate prefill does not scale with concurrency,
  and the blackout happened at 32-way. 4 matches every prior card and the speed
  probe, keeping cost readings comparable. Long runs are launched per dataset
  with `--resume`.
- **System prompt stays the neutral line.** The tool gene is measured inside the
  clean scaffold family (H5/M6), so a default-persona cell can be added later
  without re-labeling this one. Alternative: omp persona (H8-style) — rejected
  here because it changes two genes at once versus the MiMo M6 comparison.
- **Pinning stays via `capture_scaffold.py`.** Qwen3.5 is non-reasoning; the pin
  set is `temperature=0` only. The proxy is also the audit surface for the
  request inventory.
- **Run order = cost order.** arm A first (baseline + legal parity gate against
  the stored arm-A prompts), then arm B: legal_mc (146) → legal_nli (150) →
  reading400 (400) → bidlqa_val (482) → vbench_agentic (1,000) → vbench_mc
  (4,141) last, since `vbench_mc` is only agreement-with-arm-A and carries two
  thirds of the budget.
- **Slugs.** Arm A: `Qwen3_5-9B-65K`. Arm B: `ompT65_Qwen3_5-9B-65K` (short id
  `T65`). MiMo's later twin: `ompM6all_mimo-v2.5` (short id `M6all`, explicitly
  labeled as a second tool condition for MiMo, separate from M6; model id taken
  verbatim from the gateway listing at run time).
- **Server evidence lives in the card.** The probe is a one-off measurement
  reproduced from documented commands; no new tracked probe tool is added. If it
  is needed regularly later, it becomes its own change.
- **Dashboard registry is extended, not mutated.** New `ARM_MODEL`/`ARM_DATASETS`
  entries for the 65K slugs; the 28K rows stay byte-identical. The insight table
  gains a 65K comparison row only when both arms exist for a dataset.

## Risks / Trade-offs

- [Estimate superseded by the first observed run] → the 8–10 h figure assumed no
  prefix reuse; the measured arm shows ~13.9k cached tokens/item, so the
  non-agentic datasets run ~1.4 items/s. The real tail is `vbench_agentic`, where
  the default-all menu makes the model **actually call tools** (mean 3.56 calls,
  24/25 failures = 180 s aborts in the first 150 items) — record it, do not
  change the condition mid-run.
- [Gateway blackouts during the arm] → dataset-scoped runs, `--resume`
  after every stall, preflight per run, workers ≤ 6; never probe at high
  concurrency again.
- [The capture proxy is a single localhop for all arm-B traffic] → it already
  passes SSE in 4 KiB chunks and runs threaded; if it dies, restart and resume
  (checkpoints are per 25-ish items).
- [`vbench_mc` budget dwarfs the rest and its metric is agreement-only] → it is
  last and independently skippable; the change is still complete for the five
  other datasets if it is deferred.
- [65K and 28K could be conflated by a reader] → every artifact and dashboard row
  carries the model tag; the proposal's non-goal repeats the rule.
- [omp upgrade silently enlarges the default menu mid-project] → the captured
  inventory (11 tools, 50,348 chars) is recorded with the card; a later run
  re-captures rather than assuming.

## Migration Plan

Additive only: revert = drop the sentinel and delete the new arm artifacts; 28K
results are untouched. No data migration, no schema/blob rewrite beyond the
dashboard builder's registry.

## Open Questions

- Whether the 28K node returns while this runs: if it does, whether to also add a
  28K default-all cell is a future card decision, not a blocker here.
