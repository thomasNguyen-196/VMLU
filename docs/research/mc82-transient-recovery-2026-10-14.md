# MC-82 transient provider failure recovery

On 14 October 2026 the user authorized probing Muse again and continuing the campaign without repeatedly halting for individual transient failures.

The exact prior failure item `26-0147` completed in an isolated probe, as did the health check. Sanitized wire and terminal evidence is saved under `all_res/muse13_direct_mc82/diagnosis/20261014T040245Z/`. These diagnostic answers are excluded from benchmark outputs.

The runner previously marked every failed terminal response fatal, so one failed item stopped all 12 workers. Regression tests exercise the real response adapter and scheduler: a failed item must not prevent the next item from completing, and a resumed pass must retry the failed item while skipping the completed item.

The operational repair retains transient failures in the attempt ledger and lets other items continue. Each failing lane waits 5 seconds for generic transient failures, 30 seconds for HTTP 503, or 60 seconds for HTTP 429; consecutive failures double that delay up to 300 seconds. Successful requests reset the consecutive-failure counter. Waiting is interruptible by the shared stop event. Incomplete phases proceed to the already registered maximum of three passes, with 60 seconds between recovery passes. Persistent failures after those passes still require attention. Explicit HTTP authentication/configuration/billing failures, recognized permanent provider error codes, and tool-call violations remain fatal.

Output-budget truncations remain terminal outcomes and are never retried. Temperature, model route, system/user prompts, output budget, seed/effort omission, scorer, and manifests are unchanged. The current runner and shared scheduler sources are archived and hashed on execution. The new code records the provider error code without error-message text and clears stale pause metadata on resume.

Validation: five offline recovery tests pass; targeted Ruff and Bandit pass; standalone parsing parity passes. The broader suite ran 291 tests with two failures in existing dashboard tests (`TestHarnessDashboard.test_insight_never_mixes_agreement_into_the_score_range` and `test_render_html_escapes_labels_and_shows_the_leak_banner`), outside the modified runner paths. No dashboard files were changed in this repair.
