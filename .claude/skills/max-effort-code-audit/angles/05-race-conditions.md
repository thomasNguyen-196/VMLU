# Angle 5 — Race conditions on shared mutable state

## What to look for

- Read-then-write patterns without a lock or transaction isolation
- Missing `SELECT ... FOR UPDATE` / `SELECT FOR UPDATE` on critical reads
- In-memory maps or sets used as mutual-exclusion guards (not backed by DB transactions)
- Closure-captured boolean flags checked before `await` but without atomicity
- Missing unique constraints on tables that enforce business invariants

## Grep seeds

```
FOR UPDATE
with_for_update
isStreaming
is_authorized
locked_by
pending_
if\s*.+\s*&&\s*!
if\s*\w+\s*&&\s*
catch.*\bfalse\b
UniqueConstraint
```

## Checklist

1. Find patterns where code reads a value, then conditionally writes — is the read+write in a single transaction with `FOR UPDATE`?
2. Check in-memory maps used as locks: `extension_connections_map`, `_reply_results`, `_processing` — are there two concurrent goroutines/requests that could race?
3. Check closure-captured flags like `isStreaming`, `is_publishing`, `is_authorized` — can two callers both pass the guard?
4. Check for missing `UniqueConstraint` on columns that should be unique per business rule (e.g., `(campaign_id, user_id)`).

## Known pattern from 2026-06-30 report

- #10: `content_reviews.py:537` — review lock without `SELECT ... FOR UPDATE` — two admins can both claim the same review.
- #12: `use-chat.ts:559` — `isStreaming` closure allows duplicate concurrent chat sends.
- #13: `campaign.py:334` — missing unique constraint on `(campaign_id, user_id)` allows duplicate member rows.

## Output

Return each race. Include file, line, the shared state, and the interleaving that breaks it.
