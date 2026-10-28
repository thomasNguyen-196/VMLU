## 1. Requests, manifest and runner (offline until registered)

- [x] 1.1 Write `data/diagnostic_router_signals/jev_signals_v1.json` and `code_benchmark/diagnostic_router_signals.py`:
  - the J1 and J2 questions;
  - the request builders;
  - the B answer sources.

  Freeze `jev_signals_manifest_v1.json`. Verify:
  - 2,901 rows: 967 pre-hoc and 1,934 post-hoc;
  - no state carries a gold answer;
  - every post-hoc state carries the scored prediction of its B draw;
  - the manifest rebuilds identically.

  (2026-10-28: configuration sha256 5804fcb6…, manifest self-hash a9647395…: 967 pre-hoc and 1,934 post-hoc rows, every B prediction non-empty.)
- [x] 1.2 Implement `code_benchmark/run_router_signals.py`:
  - the gates: card heading, detail card, frozen hashes, route identity;
  - the halts of the spec;
  - resume.

  Verify with a fake transport that:
  - a non-free response halts the run;
  - a changed model id halts it;
  - a 401 halts it;
  - a 429 is retried within the registered count;
  - the offline preflight prints `endpoint_calls=0`.

  (2026-10-28: a halting response now stops further sends from the worker itself, not only after the main thread reads it. A first test caught this: six fake sends went out after a non-free response.)
- [x] 1.3 Implement `code_benchmark/analyze_router_signals.py` (plan `diagnostic-router-signals-v1`): the ceiling block, policies P1–P10 and M1–M4, and the reading rule. Verify on synthetic data that:
  - cross-fitting never scores a choice on the outcomes it was fitted on;
  - post-hoc cost adds S only when escalated;
  - the reading rule marks the registered cases.

  (2026-10-28: 15 tests in `test_diagnostic_router_signals.py`. Inputs were loaded by count only: 967 reading items, 660 VMLU items, of which 1 has no MC-43/44 letter confidence and counts as 0, and 591 Muse labels. No policy outcome was computed before registration.)

## 2. Registration and run (MC-99)

- [x] 2.1 Register MC-99:
  - the root block;
  - the detail card `docs/measurement_cards/MC-99-diagnostic-router-signals.md`;
  - `data/diagnostic_router_signals/registration.json` with the configuration and manifest hashes.

  Commit as `pre-register MC-99`. Verify that the offline preflight passes every gate.

  (2026-10-28: all four gates pass, and the preflight prints `endpoint_calls=0`.)
- [ ] 2.2 Run MC-99 with `--execute`. Verify:
  - 2,901 complete calls;
  - a constant response model;
  - zero reported cost throughout.

  Append the run record to the detail card.
- [ ] 2.3 Run the analysis once and apply the reading rule. Report it here, and say which policies, if any, go to a held-out card.
