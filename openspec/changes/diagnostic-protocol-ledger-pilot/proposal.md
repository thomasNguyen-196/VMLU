## Why

The current `/table` identifies performance differences but cannot attribute individual failures to knowledge, reasoning, retrieval, harness, or measurement. Existing per-item artifacts make it possible to prepare a traceable diagnostic protocol and a human-audited pilot before spending on augmentation or training a Gap Detector.

## What Changes

- Define `diagnostic-v1`: separate diagnostic labels from intervention/action labels, document evidence standards, preserve unknown/mixed outcomes, and specify preregistration and audit gates.
- Build an offline, read-only adapter for modern V1 artifacts, including Qwen MC-72, with explicit source-run declarations, checked identities/hashes, coverage accounting, and score parity.
- Export a versioned ledger of all selected observations (correct, incorrect, and execution failures), plus a failure view; preserve source conditions and frozen scoring.
- Select a reproducible 60-item, five-dataset audit pilot, export separate diagnostic review packets, import reviews, and report disagreements/adjudication and readiness without changing benchmark gold.
- Add a local-only `/diagnostic` review surface for the prepared 60-item packet and 15-item independent-review subset, with reviewer-scoped browser drafts and CSV export in the existing import schema.
- Record future B/S/K/KS, oracle-evidence, and harness experiments as protocol definitions only. Unresolved runtime budget/corpus/model controls remain explicit blockers for later inference.

## Evaluation Regime

This change addresses **Regime A — Capability** questions and prepares preregistration for later **Regime C — Reasoning budget** experiments from `PROPOSAL.md`. Historical OMP/provider runs retain their recorded controls and MUST NOT be relabeled as the strict BF16/official-template Regime A configuration when those controls are unverified. It does not execute Regime C experiments or measure **Regime B — Edge deployment**. Modern model identities come from their original run metadata, including Qwen3.5-9B-65K; the historical small-model framing is not a reason to rewrite those identities.

## Non-goals

- No LLM calls, retrieval corpus/index construction, augmentation runs, learned router, or runtime verification.
- No changes to historical prompts/parsers/scorers, source gold, `data/eval_set_manifest.csv`, existing review CSV/state contracts, or dashboard scores.
- No automatic causal labels from dataset names, lexical scores, or successful interventions; no synthetic human reviews or invented agreement.
- No database, third-party packages, remote uploads, Notion updates, or Git publication.
- No claim that a deliberately sampled audit pilot estimates population failure rates or provides a pristine held-out test.

## Capabilities

### New Capabilities

- `diagnostic-protocol`: Versioned protocol, taxonomy, evidence/readiness gates, and unchanged historical measurement boundaries.
- `diagnostic-ledger`: Provenance-checked offline artifact projection, source-specific score parity, coverage and failure classification.
- `diagnostic-pilot-audit`: Deterministic pilot manifest, independent reviewer packets/imports, adjudication, and truthful audit reporting.
- `diagnostic-review-ui`: Local pilot presentation, per-reviewer/scope draft persistence, controlled annotation fields and schema-compatible download.

### Modified Capabilities

None. Existing evaluation and human-review requirements remain unchanged; diagnostic annotations use a separate namespace and schema.

## Impact

Add diagnostic modules/CLIs and offline unittest coverage under `code_benchmark/`; protocol and schemas under `data/diagnostic_v1/`; rubric and operational guide under `docs/research/`. Generated ledgers, manifests, packets, and reports live under gitignored `all_res/diagnostic_v1/`. Reuse frozen scoring functions as read-only parity checks, with adapters isolated from runners and `common.py` remaining stdlib-only.

The source set initially supports explicitly declared V1 main runs and the MC-72 derived manifest. Other artifact families require future adapters rather than guessed mappings. Actual human annotation is a separate manual deliverable; prepared packets do not imply completed audit.

## Annotation revision 2

Add explicit no-observed-issue, observed-issue and unresolved outcomes, with conditional error labels. Correct reviews can complete with zero labels; unknown cause stays distinct from success and unreviewed. Version rubric/schema, preserve old snapshots/drafts and update importer, audit reports and UI together. See docs/research/diagnostic-review-label-policy-audit-2026-10-12.md for the paper/OpenSpec audit.

- Provide provisional, source-linked first-pass suggestions in the primary review UI; preserve human final judgment and independent second-review blinding, and record AI assistance provenance.

## Methodology amendment: annotation revision 4

Separate answer-audit evidence from controlled cause attribution. Version the review contract and preserve prior packets/drafts. Fix scoped evidence eligibility, reviewer blinding gates and roadmap controls; do not execute interventions or migrate old human signoff.
