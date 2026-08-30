# Angle 9 — Idempotency / retry

## What to look for

- Operations that double-execute on retry (e.g., publish post on retry creates a duplicate)
- Missing unique constraints on columns that should prevent duplicates
- "Lock or create" patterns where the race between check and insert is not atomic
- Functions called `add_member`, `add_user`, `add_*`, `create_*` that can be called twice with the same args and produce duplicate rows
- Missing idempotency keys on POST endpoints that do side-effectful operations
- Retry logic that replays the full side effect instead of replaying only the non-side-effect part

## Grep seeds

```
UniqueConstraint
ON CONFLICT
add_member
add_user
add_token
lock_or_create
create_or_
upsert
Idempotency-Key
idempotency
max_retries
retry
```

## Checklist

1. Find all `add_member`, `add_user`, `add_*`, `create_*` functions — is there a unique constraint preventing duplicate rows?
2. Check POST endpoints that create or modify state — do they support `Idempotency-Key`?
3. Check River worker retry logic — when a job retries, does it re-execute the full side effect (publish post, send message) or does it check whether the effect already happened?
4. Check "lock or create" patterns: a SELECT to check existence, then an INSERT. Is there a race window where two callers both see "not found" and both insert?

## Known pattern from 2026-06-30 report

- #13: `campaign.py:334` — missing unique constraint on `(campaign_id, user_id)` allows duplicate member rows on concurrent calls.

## Output

Return each non-idempotent operation. Include file, line, what duplicate execution produces, and whether the existing guard (unique constraint, idempotency key) is missing.
