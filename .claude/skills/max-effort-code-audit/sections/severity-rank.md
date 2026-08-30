# Section — Severity rank (Step 6)

## Purpose

Apply the severity rubric, sort findings, and cap at `max_findings`.

## Rubric

```
CRITICAL — Exploitable now against production data/users.
  - Auth bypass, SQL injection, command injection, fail-open security.
  - Hardcoded credentials reachable in production.
  - JWT forgery.
  - Calling this finding "low priority" would be irresponsible.

HIGH — Data corruption, privilege leak, duplicate state.
  - Wrong analytics surfaced to campaign dashboards.
  - Viewing another user's data via a missing ownership check.
  - Race condition that corrupts database writes.
  - Duplicate charge, duplicate post, duplicate member row.

MEDIUM — DX failure, non-corrupting race, performance.
  - Forced logout when an unrelated API fails.
  - Double-charge credits (non-catastrophic).
  - Read-then-write race that loses an update (no corruption).
  - Missing cleanup on failure.
```

When on a boundary, ask:
- "If a customer saw this, would they file a support ticket?" Yes → HIGH. No → MEDIUM.
- "Could an attacker use this to log in as someone else or steal data?" Yes → CRITICAL.

## How to run

1. For each confirmed finding, assign CRITICAL / HIGH / MEDIUM.
2. If `confidence < 0.4`, demote one level (a low-confidence CRITICAL becomes HIGH; a low-confidence HIGH becomes MEDIUM). If confidence < 0.3 and MEDIUM, drop the finding — not reliable enough for the report.
3. Sort: CRITICAL first (descending confidence), then HIGH (descending confidence), then MEDIUM (descending confidence).
4. Cap at `max_findings` — truncate from the bottom (lowest MEDIUM findings are dropped first). If there are more CRITICAL + HIGH findings than `max_findings`, truncate the lowest-confidence CRITICALs.
5. Count: CRITICAL count, HIGH count, MEDIUM count.

## Output

The ranked finding list plus the count summary table.
