## 1. Protocol and research rubric

- [x] 1.1 Add versioned `data/diagnostic_v1/protocol.json`, taxonomy/schema definitions and examples; verify stdlib schema checks reject unknown versions, invalid evidence/action labels and unsupported input modes.
- [x] 1.2 Write the protocol guide and Vietnamese annotation rubric, including future B/S/K/KS definitions, historical Regime A caveats, offline/runtime separation and unresolved inference controls; verify each diagnostic label has evidence criteria and examples that allow unknown/mixed attribution.
- [x] 1.3 Implement readiness reporting for preparation, audit and future inference; verify a valid offline protocol with unresolved endpoint/corpus/budget controls reports preparation ready but inference not ready with reasons.

## 2. Source adapters and immutable ledger

- [x] 2.1 Add explicit source-registry entries and V1/MC-72 adapters for manifest/run/prediction/score/summary provenance; verify real artifact inventory and negative fixtures for duplicate keys, extra items, prompt drift, wrong manifest identity, conflicting gold/output and unsupported scorers.
- [x] 2.2 Add complete observation projection with execution/missingness/resource statuses and metadata allowlist; verify correct/incorrect/failed/missing rows are all retained and unknown cost remains null while credentials/headers/credential-source paths are absent.
- [x] 2.3 Add source-specific frozen extraction/scoring and summary parity checks; verify MC parse failures remain incorrect in the original denominator, reading EM/token-F1/legacy metrics reproduce source fields and rounded aggregate mismatch fails publication.
- [x] 2.4 Add offline ledger CLI outputs (`ledger.jsonl`, `failures.jsonl`, provenance, coverage and parity reports); verify atomic/idempotent publication, differing-hash namespace rejection and rejection of source/output directory overlap.

## 3. Pilot selection and reviewer packets

- [x] 3.1 Implement the 60-item, 12-per-dataset selection policy with declared anchors, sorted seeded sampling, correctness quotas, EM/F1-disagreement priority and shortage fallbacks; verify deterministic manifest/hash, unique item count, reported fallback allocations and fatal insufficient-dataset coverage.
- [x] 3.2 Resolve question/context/choices through verified source loaders and preserve task-specific passage/document groups and exposure; verify joined content matches source prompt provenance without raw-prompt slicing, and reports identify this as development audit rather than held-out/population sampling.
- [x] 3.3 Export independent blank A/B diagnostic CSVs plus readable Markdown packets and the deterministic 15-item second-review subset; verify schema/version hashes, identical immutable source content, no other-reviewer judgments and no changes to existing `REVIEW_COLS` or review-state schemas.

## 4. Review import and adjudication

- [x] 4.1 Implement strict diagnostic review import and evidence validation; verify unknown/duplicate keys, edited source columns, bad hashes/labels and unsupported evidence levels fail while blank fields remain unreviewed.
- [x] 4.2 Implement append-only adjudication and suspected-gold annotations; verify independent reviews are retained, original gold/scores stay byte-identical, and unresolved/deferred decisions retain explicit reasons and supervision eligibility.
- [x] 4.3 Export audit reports with coverage, paired semantic/per-label agreement, denominators, adjudication backlog and readiness; verify empty reviews and single-rater fixtures do not invent IAA or mark the independent-review gate complete.

## 5. Offline integration and repository checks

- [x] 5.1 Add focused stdlib unittest fixtures/tests covering protocol gates, adapters, score parity, deterministic selection, review tampering and non-mutation; verify `.venv/bin/python -m unittest code_benchmark.test_diagnostic` passes offline and blocks accidental network use.
- [x] 5.2 Generate and inspect the local MC-72 ledger/pilot/blank packets with the new CLI: source model Qwen3.5-9B-65K, original endpoint `http://llmapi.iec/v1`, MC-72 artifacts only, **no endpoint calls**; verify 1,299 source observations, 60 unique pilot anchors, 15 independent-review items, parity and pre/post source-file hashes.
- [x] 5.3 Exercise an additional declared V1 main source (MiMo V2.6 Flash, original OpenCode Go provider/endpoint as recorded in that run, **offline import only**); verify its 2,043-observation inventory and that condition/model metadata is not inherited from MC-72 or silently pooled.
- [ ] 5.4 Run repository-required Ruff/Bandit, standalone parsing parity and root unittest suite using the documented toolchain, plus `git diff --check`; verify exit codes and ensure no unrelated dirty files are staged or edited by this change.
- [x] 5.5 Deliver a Vietnamese operating guide with root-run examples and the generated preparation/readiness report; verify the guide clearly distinguishes completed tooling from pending human audit and future inference.
- [x] 5.6 Add local `/diagnostic` server route and client review workspace, wire shared navigation, and verify the page clearly reports absent/corrupt pilot artifacts without exposing unrelated review data.
- [x] 5.7 Implement reviewer/scope-specific browser draft persistence, primary/independent-15 navigation, accessible judgments, progress and exact-schema CSV export; verify drafts remain isolated by reviewer/scope and exported columns/import identity match `diagnostic-review-v2`.
- [x] 5.8 Run the app locally with the generated pilot, review representative items in both scopes, export/import fixture-only CSVs, visually inspect desktop/mobile states and verify browser storage contains no other reviewer's labels in the rendered session.

## 6. Manual research deliverables — remain pending until real reviews exist

- [ ] 6.1 Have the primary human reviewer complete all 60 anchor observations' semantic/gold/evidence judgments and diagnostic hypotheses; verify imported signed/identified reviews, rationales, references and complete anchor coverage (do not substitute test fixtures or AI-generated labels).
- [ ] 6.2 Have a distinct human reviewer independently complete the fixed 15-item subset; verify reviewer independence, source hashes and real paired coverage before reporting agreement.
- [ ] 6.3 Resolve or explicitly defer flagged gold/semantic conflicts and produce the final pilot audit report; verify adjudication provenance, unchanged benchmark gold, explicit unavailable-supervision cases and truthful audit gate status. If reviewers are unavailable, keep these manual tasks unchecked and deliver the pending-review report.

## 7. Annotation revision 2 — explicit outcomes

- [x] 7.1 Revise OpenSpec design/specs and archive v1 definitions; version annotation schema/rubric with explicit outcomes and conditional cause labels.
- [x] 7.2 Update importer and audit/adjudication reporting; verify no-issue successes, unknown causes, unresolved deferrals, measurement issues and agreement denominators.
- [x] 7.3 Update frontend completion/CSV and preserve prior reviewer/scope drafts with downloadable backups; verify outcome choices and missing-field explanations.
- [x] 7.4 Publish a revision-2 pilot without resampling and verify identical source rows, ordered anchors, independent subset and unchanged old snapshot bytes.
- [x] 7.5 Run focused Python/Bun/export-import/version-negative checks, typecheck/lint and browser QA; retain pending human review gates.

Verification on 2026-10-12 for annotation revision 2: focused diagnostic unittest 21/21; Bun review tests 11/11; UTF-8-BOM export/import fixture 60 rows, 4 complete and 56 unreviewed; typecheck, scoped ESLint, scoped Ruff/Bandit, OpenSpec validation and diff checks pass. Old snapshot/source checksums, 60 ordered anchors and 15 independent keys are unchanged. Task 5.4 remains pending: full-repo Ruff has 6 pre-existing unused-symbol findings in expansion/migration/MC70 files; Bandit has 4 campaign-runner findings; root suite has 1 failure and 1 error in TestHarnessDashboard. Human tasks 6.1–6.3 remain pending; fixtures were not imported into the real pilot.

## 8. AI-assisted first pass with human final review

- [x] 8.1 Archive review-v2 definitions; version review schema/protocol v3 with explicit assistance mode and separate human attestations.
- [x] 8.2 Create a source-linked assistant suggestion sidecar for all locked observations; validate exact coverage/hashes and keep it out of ledger/annotation imports.
- [x] 8.3 Display suggestions only in primary-60 and seed blank reviewer-specific draft rows without changing existing reviewer data or setting human status/signature.
- [x] 8.4 Record ai_assisted on primary exports and hide suggestions in independent-15; preserve old reviewer/scope drafts for download.
- [x] 8.5 Generate a new review-v3 snapshot from the same item order/subset; verify suggestion coverage/provenance and keep human-review gates pending.

Revision 3 was generated locally from the fixed revision-2 packet. Assistant suggestions are source-linked proposals; no suggestion sets reviewer status/attestation and the current audit still has zero human-reviewed rows.

## 9. Methodology revision 4 — claim-specific evidence

- [x] 9.1 Archive revision 3; define scoped audit evidence, observed issues, per-hypothesis support and prospective experiment controls.
- [x] 9.2 Implement strict revision-4 import and evidence-linked attribution; fix label-specific eligibility and blind review reporting/gates.
- [x] 9.3 Update frontend/Zustand/export to revision 4, preserve old reviewer drafts and refresh 60 provisional proposals without human signoff.
- [x] 9.4 Rebind the same 60 anchors/15 subset; verify old snapshots/source bytes unchanged.
- [x] 9.5 Update Notion roadmap and local methodology guide; clarify language scope, baseline, budget, verification and stage gates.
- [x] 9.6 Run focused contract/negative tests, TypeScript/lint and browser checks; keep real human reviews and future inference pending.

Revision-4 verification on 2026-10-14: focused Python 31/31, Bun 13/13, parsing 17/17 and prompt parity; TypeScript, targeted ESLint, scoped Ruff/Bandit and strict OpenSpec validation pass. Export/import was exercised only in a temporary pilot copy (60 rows, 4 synthetic complete judgments); the real pilot has zero imported human reviews. Same ordered 60 anchors, fixed 15 subset and source values are preserved; 34 archived snapshot files are unchanged. Browser shows item 2 with input-span audit evidence, no causal tier and unsigned status, with a downloadable v3 backup; Independent-15 is blank and suggestion-free, and a primary-exposed reviewer is blocked. Notion roadmap was updated and refetched. Task 5.4 remains pending: full-repo Ruff reports 15 unrelated findings, Bandit reports 4 unrelated low-severity findings, and the root suite has 1 failure plus 1 error in TestHarnessDashboard (286 tests). Human tasks 6.1–6.3 and prospective inference remain pending.


## 10. Reviewer progress backend and human-edit tracking

- [x] 10.1 Separate AI proposals from human work in progress counts, filters, item editor metadata and completed/deferred validation; preserve old review values and collapse historical rubric backups.
- [x] 10.2 Add MongoDB-backed reviewer/pilot/scope progress API with structural/scope validation, atomic revision checks, persistent AI-exposure markers and Zustand caching of unsynced edits.
- [x] 10.3 Verify resume across independent browser storage and service restarts, reviewer isolation, stale-write rejection, focused tests and type/lint checks. Preserve all real judgments and keep human audit/import tasks pending.

Verification on 2026-10-15: 23 Bun tests / 73 assertions pass, including actual Mongo adapter CAS calls through an offline fake; live API returns 409 for a stale revision. With a dedicated smoke reviewer, the UI showed 1 human-edited item and 59 unstarted despite 60 AI proposals. After removing only that test reviewer's browser cache, the same values/counts restored from MongoDB. Exact progress survived restarting both MongoDB and web containers. Existing results API still returns 200. TypeScript, targeted ESLint, diff checks and strict OpenSpec validation pass. Smoke data is separate from all human audit records and is removed after verification; no human review, attestation or audit import is fabricated.
