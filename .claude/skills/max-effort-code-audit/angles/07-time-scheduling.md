# Angle 7 — Time / scheduling semantics

## What to look for

- Scheduled bg jobs that publish immediately instead of at the scheduled time
- Deleting a field from an object and then reading that same field later in the same call
- `clone` / `clonedPayload` patterns where the clone is created but the original is mutated
- Missing or incorrect timezone handling (local time treated as UTC, or vice versa)
- `NOW` fallback in a scheduled job worker

## Grep seeds

```
delete .*scheduled
scheduledPublishTime
scheduled_at
execute_at
\.clone
clonedPayload
NOW
\.utc\(\)
\.local\(\)
\.format\(
timezone
```

## Checklist

1. Find all patterns where `delete obj.key` is followed by `obj.key` read. Is the read getting `undefined`/`None`?
2. Find all `scheduledPublishTime` or `scheduled_at` usages — are they correctly passed through the entire pipeline (webapp → API → bg job → worker)?
3. Check bg job worker code: when a scheduled job runs, does the worker re-read the scheduled time from the payload or does it fall back to `NOW`?
4. Check timezone handling: are user-facing schedule times converted correctly (UTC storage → local display)?
5. Check any `clone` / `spread` pattern — is the clone actually used downstream, or is the original mutated and the clone discarded?

## Known pattern from 2026-06-30 report

- #9: `multi-platform.handler.ts:753` — `delete payload.scheduledPublishTime` then reads `payload.scheduledPublishTime` later. Also: `scheduled.handler.ts:29` — same bug, clonedPayload vs payload confusion (already fixed).

## Output

Return each broken scheduling or time handling pattern. Include the file, line, what the code does, and what the actual publication behavior is versus the intended one.
