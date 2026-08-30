---
name: max-effort-code-audit
description: Proactive, max-effort, multi-angle bug and error audit of a codebase. Produces a ranked report at the repo root. Use when the user asks to "find all bugs," "audit this codebase," "max-effort review," or wants a deep code review report before a release.
---

# Max Effort Code Audit

A proactive, whole-codebase bug and error audit. The workflow behind `code-review-report-2026-06-30.md`.

## Inputs

| Input | Default | Description |
|---|---|---|
| `scope` | `main...dev` (git) or working tree | Git diff range or directory to scan. |
| `output_path` | `code-review-report-YYYY-MM-DD.md` | Where to write the report. |
| `max_findings` | `50` | Hard cap on findings in the report. |
| `verify_budget` | `1` | Number of verify passes per candidate. |

## Workflow

### Step 0 — Load this skill

Load ALL section files AND ALL 10 angle files from `angles/` in a single batch before Step 1 begins. Read all 10 angle files (`01-authn-authz.md` through `10-process-conventions.md`) upfront so the orchestrator has the full checklist + seed list for every angle in memory when Step 2 launches the sub-agents.

**Why this matters:** the sub-agent prompts in Step 2 quote each angle's checklist and seeds. If you read angles one at a time you will be tempted to spawn each sub-agent as soon as you finish reading its angle, turning Step 2 into a sequential pipeline. Read everything in Step 0, then launch all 10 sub-agents together in Step 2.

### Step 1 — Scope lock

Read `sections/scope-lock.md`. Resolve the scope to a file list with line counts. Print summary.

### Step 2 — 10 parallel sub-agents

Launch ALL 10 sub-agents in a SINGLE response block. Do NOT issue them in 10 sequential round-trips — that is the most common failure mode for this skill and turns Step 2 from ~1× (the slowest angle) into ~10× wall time.

**Required pattern:**
1. Compose all 10 sub-agent invocations (one per angle file) with the file list from Step 1, the angle's checklist + seeds, and the sub-agent contract below.
2. Send all 10 invocations in ONE response / tool-call block and fire them together.
3. Wait for all 10 to return.
4. Proceed to Step 3 only after every angle has a result.

If the host platform does not support parallel sub-agent calls, fall back to a single sub-agent that processes all 10 angles in one shot and returns a combined candidate list. Do NOT process angles one-by-one as separate round-trips.

Each sub-agent:
- Receives the file list from Step 1 and the angle's checklist + seeds
- Returns candidates in the sub-agent contract format (see Sub-Agent Contract below)
- Does NOT verify — only finds candidates

Do NOT proceed to merge until ALL 10 sub-agents have returned.

### Step 3 — Merge + dedup

Read `sections/merge-dedup.md`. Combine the 10 candidate lists, dedup by `file:line`, merge cross-angle findings on the same site.

### Step 4 — 1-vote verify

Read `sections/verify.md`. For each candidate, open the file at the cited line, read 30 lines of context, confirm or drop. Cap at 1 verify per finding.

### Step 5 — Gap sweep

Read `sections/gap-sweep.md`. For each confirmed finding, ask "what did I miss in adjacent code?" and add follow-ups.

### Step 6 — Severity rank

Read `sections/severity-rank.md`. Apply severity rubric. Sort descending. Cap at `max_findings`.

### Step 7 — Write report

Read `sections/report-render.md`. Render the report at `output_path`. Update `.gitignore`.

## Sub-agent contract

Each angle sub-agent returns a JSON block:

```json
{
  "angle": "authn-authz-bypass",
  "candidates": [
    {
      "title": "Short finding title",
      "file": "path/relative/to/repo/root",
      "line": 64,
      "summary": "One-sentence description of what is wrong.",
      "failure_scenario": "Concrete steps an attacker or user takes to trigger this.",
      "confidence": 0.7
    }
  ]
}
```

`confidence` is 0.0–1.0, the sub-agent's self-rated confidence that the finding is real **before** verification. The verify phase adjusts this.

## Severity rubric

| Level | Definition |
|---|---|
| **CRITICAL** | Exploitable now against production data/users (auth bypass, injection, fail-open security, hardcoded credentials reachable in prod). |
| **HIGH** | Data corruption, privilege leak, duplicate state, wrong analytics surfaced to users, race that corrupts writes. |
| **MEDIUM** | DX failure (forced logout, double-charge credits), non-corrupting race, performance regression, code health smell. |

When on the boundary: "If a customer saw this, would they file a support ticket?" Yes → HIGH. No → MEDIUM. "Could an attacker use this to log in as someone else?" Yes → CRITICAL. Drop LOW findings.

## What is out of scope

- Performance / load testing
- Dependency CVE scanning (use `cso` or a dedicated SCA tool)
- Accessibility, i18n completeness
- Style / formatter / lint issues (use the language's standard linter)
- Generating fixes — produce findings, not patches

## Risk mitigations

- **Sub-agent hallucination** — the verify phase opens the file at the cited line and reads context. Hallucinated candidates are dropped.
- **Angle blindness** — the gap-sweep phase asks "what did I miss in adjacent code?" per confirmed finding.
- **Time blowup** — sub-agents can stream findings; merge has a hard cap per angle; `max_findings` caps the final report.

## After the report

Hand the report to the user or feed it into a follow-up skill:
- `to-issues` to create trackable issues per finding
- `openspec-propose` to design fixes for critical findings
- `cso` for a deeper security-only pass on any CRITICAL findings
