---
name: vmlu-results-data
description: Score completed VMLU runs or refresh local result data and dashboard blocks for web display.
---

# VMLU Result Data

Use this workflow for scoring completed outputs, patching `web/public/benchmark-data.json`, or generating other web-consumed result data.

## Workflow

1. Identify the exact evaluation arm, model/condition, score artifact, and dashboard block requested. Read the matching scorer or `build_dashboard_*.py` entry point and its CLI before running it.
2. Follow the arm's canonical metric definition and denominator. Do not transfer metric names or normalization rules between MC, Reading-400, V-Bench, Harness, or experimental arms.
3. Run only the matching local scorer or builder. Dashboard builders patch a named result block; preserve every unrelated block and use the builder's fail-fast checks.
4. Inspect the resulting diff and validate the changed data against the corresponding `web/lib/` contract. Keep generated outputs local unless the user separately asks to commit, push, or upload them.

For Reading-400, consult `openspec/specs/eval-scoring/spec.md` and the current scorer before describing reported metrics. V-Bench has no local gold score. For newly added result pages or benchmark arms, follow that arm's versioned protocol and `web/lib/` validator rather than mapping it onto an older dashboard schema.

Finish by naming the score/result files changed, the selected model and condition, the reported metric and coverage, and whether unrelated dashboard blocks remained untouched.
