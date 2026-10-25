## Context

See `proposal.md` for motivation and scope. Current V1 runs expose `run.json`, `predictions.jsonl`, `scores.jsonl`, and `summary.json`; predictions carry raw prompts, responses, request/replicate IDs, usage and finish reasons. Scores carry gold, parsed predictions, passage IDs and source-specific metrics. `vi_multimodel.py` and `score_vi_multimodel.py` provide frozen scoring functions. Qwen MC-72 contains 1,299 observations under a derived manifest; V1 main peers contain 2,043 under the parent manifest. Existing annotation exports use a nine-column `REVIEW_COLS` contract and can apply gold changes, so diagnostic reviews must not flow through that mutation path.

The working tree contains unrelated ongoing evaluation/web changes. Implementation is additive; planning and implementation must not stage those changes. Historical card text can remain preregistered after a run completes, so artifact state and card provenance are separate evidence rather than silently reconciled fields.

## Goals / Non-Goals

**Goals:** Offline preparation, strict source reconciliation, score parity, deterministic sampling, usable human packets, an accessible local review surface, and honest readiness reporting using existing repository/runtime dependencies.

**Non-Goals:** Intervention execution, endpoint probes, corpus construction, automatic semantic judging, causal classification, legacy CSV adapters, and modifying the existing 400-item review UI or gold. Actual human reviews cannot be manufactured as implementation fixtures.

## Decisions

### 1. Independent modules and file-based interface

Add `code_benchmark/diagnostic.py` for schema validation/projection and `code_benchmark/build_diagnostic_ledger.py` / `prepare_diagnostic_pilot.py` for offline commands. Add `review_diagnostic_pilot.py` for import, adjudication and reports. Keep `common.py` unchanged; reuse its checked/atomic I/O where suitable. Alternative: extend the existing acceptance-review exporter; rejected because it couples diagnostic labels to gold mutation and a frozen schema.

Tracked definitions: `data/diagnostic_v1/protocol.json`, `taxonomy.json`, `source_registry.json`, schema descriptions/examples, and `docs/research/diagnostic-v1-protocol.md` / `diagnostic-v1-rubric.md`. Generated snapshots: `all_res/diagnostic_v1/<label>/` (already within ignored output space). Source registry entries declare adapter version, run directory, source manifest/protocol, dataset allowlist, scorer version and card identity. No output directory can overlap a source directory.

### 2. Readiness distinguishes preparation from full preregistration

The protocol has a stable ID and immutable revision hash. Stage 1 locks offline identities, taxonomy, selection and metric definitions. Future B/S/K/KS and oracle/harness arms are definitions, with unresolved model/corpus/budget controls explicitly listed. `preparation_ready` requires valid offline inputs, `audit_complete` requires completed human review/adjudication plus an independent-review subset, and `inference_ready` additionally requires verified future controls and budget. This change cannot produce inference readiness by guessing settings.

The independent subset is fixed at 15 of the 60 anchors, 3 per dataset, selected deterministically and blind to reviewer results. These numbers are pilot design choices, not statistical sufficiency claims. If human availability is insufficient, tooling deliverables can complete while the research gate remains pending.

### 3. One observation per source-run/item/replicate

Use the exact tuple `(source_run_id, dataset_id, item_id, replicate_id)` as observation identity and the existing `dataset:item_id` convention as item key. Store source/run/control fields separately from measurements, execution, provenance and annotations. No cross-run overwrite by profile ID, no condition inheritance from a model name, no guessed historical-to-modern ID aliases.

`provenance.json` records protocol/registry/schema versions, input byte hashes and observation-to-line references. `ledger.jsonl` includes every expected manifest observation, `failures.jsonl` is a derived view, and `coverage.json` / `parity-report.json` explain missingness and parity. Validate manifest hashes with the declared adapter's original canonicalization; also retain actual file-byte SHA256. Never compare a semantic manifest hash with an unrelated raw-file checksum.

Completed rows verify prompt hash, raw-response/parsed/gold agreement between prediction/score artifacts, frozen scorer parity, and supplied summary aggregates at the source rounding precision. Missing and failed expected observations remain execution records; scores stay null unless source scoring explicitly recorded them. Default pilot creation requires complete verified anchor sources; an inventory mode can report incomplete sources without issuing a successful scorable ledger. Unsupported versions fail with an actionable message.

Allowlist run/control fields; do not serialize credentials, headers, complete run blobs or credential-source paths. Preserve raw prompt/response locally, expose only required packet content, and document that generated files are local research artifacts. Deterministic output content excludes volatile timestamps from its content identity. Build into a temporary directory and publish after validation; same-content rebuild is idempotent, differing content requires a new label.

### 4. A declared 60-item sampling algorithm

Default anchor is MC-72 for the five eligible datasets, validated against its own manifest. Anchor substitution is explicit in the registry and changes selection provenance. Default allocation is 12 items per dataset. For MC/NLI target 6 completed correct + 6 completed incorrect. For reading target 6 EM=1 + 6 EM=0, prioritizing up to 3 of the EM=0 quota with token-F1 >= 0.8. This priority identifies lexical disagreement candidates, not semantic near-correctness.

Sort candidates by exact item ID before seeded selection (seed 42 is a sampling seed, not an inference seed). If a correctness stratum is short, deterministically fill from the other completed local-gold stratum within that dataset and report actual allocation and fallback reasons; fewer than 12 eligible unique items for a dataset is fatal. Seeded rank selection chooses the independent 3-per-dataset subset from the resulting manifest. Expected minimum correct/incorrect coverage is validated whenever both strata have eligible candidates.

Store passage group hashes for reading and available document/related-item group provenance for legal items; missing grouping is explicit. Import contexts/questions from verified manifests/dataset loaders, not brittle raw-prompt splitting. MC `passage_id` can denote subject rather than a passage, so grouping depends on task/source semantics. Original item IDs and prompts remain unchanged. The pilot is exposure-marked `development-audit`; no clean-test claim or population error estimate.

### 5. Human annotations are append-only diagnostic evidence

Export `review_A.csv` and `review_B.csv` plus a readable Markdown packet with source question, context/choices where available, raw/final response, original gold and lexical metrics. Model/source observations are visibly included: this is diagnostic acceptance audit, not a blind gold-construction study. Reviewer judgments are independent of each other, and immutable source columns/checksums bind imports to the snapshot.

Use CSV for scalar judgments and semicolon-separated controlled label IDs, with a companion JSONL evidence/adjudication log for references and provenance. Semantic correctness: `correct|incorrect|uncertain`; gold validity: `valid|suspect|unassessable`; evidence sufficiency: `sufficient|insufficient|unassessable`. An entirely blank judgment row means unreviewed. Review schema v2 adds an explicit diagnostic_outcome: no_observed_issue, issue_observed, or unresolved. Empty diagnostic labels are valid for no_observed_issue and unresolved. References can identify context offsets, source documents, or declared contrasts; proposed gold corrections are diagnostic notes only. Label sets permit multiple hypotheses or `unknown`/`mixed`; action labels remain null. Stage 2 often supports observations rather than causal attribution.

A completed anchor review requires the three judgments, explicit diagnostic outcome, evidence level/reference/rationale, self-attestation and review status. no_observed_issue requires correct semantics, validated gold, observation/supported evidence, reviewed status and no labels. issue_observed requires one or more labels; unknown is exclusive and cannot claim supported attribution. unresolved requires empty labels, unresolved evidence and deferred status. Outcomes are explicitly chosen, never inferred from correctness or lexical scores. Correct answers may still have measurement or component issues when evidence supports them. Second reviews cover the 15-item subset. Preserve reviewer files; adjudication writes new decisions rather than overwriting them. Report paired denominators, raw semantic agreement and per-label agreement; no invented kappa or classifier quality. Suspicious gold and uncertain semantic judgments must be resolved or explicitly deferred with reasons. Deferred items remain unsuitable for later intervention supervision until resolved, even if the audit process is marked complete.

### 6. Reuse scores, do not backfill history

Alternative: trust score JSON without recomputation; rejected because stale joins or changed parsers would be invisible. Use only source-declared frozen extraction/scoring to verify parity, never invoking live runners. Semantic audit has its own fields and does not replace lexical/MC scores. Future source families or scorers need explicit new adapters and fixtures.

### 7. Local-only review surface

Add `web/app/diagnostic/page.tsx` as a dynamic server page that reads the generated pilot and selection from the repository root, verifies the declared protocol/file/selection identities and exact item counts, then passes only pilot review fields to a client component. If artifacts are missing or fail validation, render a clear setup message and the command to prepare them. Do not check in the pilot, model responses or source gold as `web/data`.

The client uses a versioned Zustand `persist` store in `localStorage` (`vmlu.diagnostic.v3.zustand`). Its `drafts` map is keyed by protocol revision, pilot content hash, normalized reviewer ID, and scope (`primary-60` or `independent-15`); reviewer IDs and scopes are collected before review items appear, and only the active bucket is selected. On first use, a matching legacy per-reviewer revision-3 localStorage envelope is copied into the Zustand store without changing judgments. Display source data as read-only and expose only versioned review fields, with keyboard navigation, dataset/item progress and a clear save indicator. Browser storage is local draft persistence, not a verified identity service or shared server database.

CSV export SHALL include every row in the active scope with the exact `REVIEW_COLUMNS` order from `diagnostic.py`, including untouched items with blank judgment fields; the reviewer ID is filled for that packet and the attestation text is included only after the reviewer explicitly checks it. Download locally; no upload or backend write. Keep the app's existing site navigation and paper/ink design tokens. Scope selection limits the independent reviewer to the predeclared 15 items. A human reviewer must still import and adjudicate exported files through the offline CLI.

Risks: stale browser drafts → key drafts by immutable pilot hash and show the identity; pilot file absent in another checkout/container → explain that the local generated artifact must be present; localStorage is not authenticated → describe reviewer identity as self-attested and retain explicit CSV import identity; second reviewer may select the wrong scope → require an explicit independent-15 mode before entering the review screen.

## Risks / Trade-offs

- [Reviewer availability] → Produce packets and an accurate pending-human-review report; keep manual tasks unchecked until real evidence arrives.
- [Taxonomy over-attribution] → Require evidence levels, unknown/mixed outcomes, and separate action labels; support does not claim direct observation of internal knowledge.
- [Pilot selection bias] → Declare quotas/fallbacks/exposure and prohibit population/held-out claims.
- [Source drift] → Validate original recorded hashes where available, freeze ingestion checksums and reject rebuilt namespaces with different provenance; do not hash today's mutable measurement card and rewrite history.
- [Missing historical control/scorer provenance] → Mark unknown, reject unsupported scoring, and do not claim matched compute across providers.
- [CSV edits and accidental gold mutation] → Separate schemas, source-column validation, append-only adjudication, read-only source permissions in tests, and pre/post input hashes.

## Migration Plan

Add definitions, docs, offline commands and unittest fixtures. Run schema validation and fixture-based parity/negative tests first, then generate a local MC-72 snapshot and pilot without API/network access. Review real outputs for provenance, counts and blank review fields. Run required repo gates. Rollback consists of removing only additive diagnostic code/definitions and local generated snapshots; historical artifacts require no migration.

## Open Questions

Later inference work must select a live verified endpoint, corpus/version, hard budget and detailed augmentation controls. Actual human reviewer identities and availability are supplied when reviews are performed; the 15-item independent-review gate remains pending until then. These do not change the offline design or authorize endpoint execution.

### Annotation revision 2

Preserve the original protocol/taxonomy/review schema under data/diagnostic_v1/revisions/review-v1 and review-v2. Keep the offline ledger schema at v1, version the assisted annotation contract as diagnostic-review-v3 / diagnostic-rubric-v2 with annotation_revision=3 and a new protocol hash. Revise the locked pilot into a new snapshot by copying verified rows in the exact original order; only rubric/protocol/packet identities change. Preserve all 60 anchors, the 15 second-review keys, selection reasons, source bytes and old review files. Old browser drafts remain in their own keys and can be downloaded by their original reviewer/scope; do not infer new outcomes or copy old attestation. Agreement on diagnostic outcomes is separate from cause-label agreement, whose denominator includes only paired issue_observed judgments. Deferred/unresolved cases and no-issue controls are not causal-positive supervision.

### AI-assisted primary review, blinded second review

The primary 60-item UI fetches separate `diagnostic-assistant-suggestion-v1` records only after that scope is selected. Each record is provisional, source-linked, and outside the immutable pilot ledger. The UI seeds blank rows into each reviewer's own browser draft and preserves rows that already contain reviewer data; seeding never sets reviewer status or attestation. Every exported primary judgment records `review_assistance_mode=ai_assisted` and uses the explicit AI-assisted human attestation. The independent-15 scope does not receive suggestions and requires `human_only`; a reviewer who viewed primary suggestions must not claim blind independence. Suggestions are generated without endpoint calls and carry confidence, evidence reference and rationale; they are advisory, not imported as judgments.

Annotation revision 3 preserves review-v2 definitions and the locked 60-item order/15-key subset. New snapshots use review-v3 schema and an explicit suggestion-manifest hash. Old v1/v2 drafts remain downloadable only to the same reviewer and scope; no outcome is inferred during backup or import.

## Authoritative revision-4 amendment (supersedes revision-2/3 evidence sections)

Audit evidence kind/reference supports semantic/gold/outcome judgments. Observed issues describe output/measurement phenomena; diagnostic labels are separate optional hypotheses with one support object per label. Human review does not upgrade a hypothesis. contrast_supported requires a registered, hash-linked reviewed contrast/replay for this exact observation and label. Input sufficiency and corpus availability are separate; eligibility applies label-specific premises and never excludes a missing-input hypothesis merely for insufficient input. Unknown is an empty hypothesis set; mixed is derived, not a competing label. No-issue controls have no causal support field and are preserved as negative/control data.

Review-v4 and rubric-v3 preserve old definitions, pilot snapshots and Zustand keys. Rebind only protocol/rubric/packet identities, without resampling. Previous reviewer drafts are downloadable for the same reviewer/scope; new human judgments and attestations are not inferred. All 60 AI suggestions are advisory r4 proposals, never contrast_supported without registered evidence.

Imports declare primary-60 or independent-15. Independent imports require human_only and explicit blind self-attestation, the fixed subset, and a different identity from primary reviews. Reports require a primary plus blind-independent pair and distinguish AI-assisted/human-only designs; person identity remains self-attested. Conflict handling does not automatically create causal training labels.

A prospective B is rerun in the same campaign as S/K/KS. Separate isolating diagnostic contrasts from end-to-end deployment comparisons; lock content/length/position, prompt/tool/compute controls, splits, corpus, budget, stability and verifier policies before inference. Runtime routing predicts quality/cost, not proven internal causes. Scope is Vietnamese tasks; language-specific claims require separately versioned matched translations. 720 arm attempts can entail more model calls. Verification reports grounding/calculation/format scope, false accept/reject, abstention coverage and costs. Unset runtime controls remain explicit blockers.


## Reviewer progress backend amendment (2026-10-15)

Working progress now uses a MongoDB-backed backend, with Zustand as the browser cache and unsynced-edit buffer. The unique record key includes normalized reviewer identity, pilot hash, protocol hash and scope; each item has separate human-editor metadata. The record is updated in place with atomic revision checks, not duplicated per shutdown/session. Old rubric backups remain unchanged under a collapsed history control. AI seed values do not mark an item started. Final completion still requires the unchanged review-v4 judgment contract and explicit attestation; working progress never imports itself into the research audit. AI exposure is persisted separately by reviewer identity to enforce the independent scope across browsers. This supersedes the earlier browser-only persistence architecture without changing frozen pilot, gold, scores, review CSV columns or protocol hashes.
