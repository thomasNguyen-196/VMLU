# Section — Merge + dedup (Step 3)

## Purpose

Combine the 10 candidate lists from the angle sub-agents into a single deduplicated list.

## How to run

1. Collect all 10 sub-agent results. Each is a JSON block (see Sub-Agent Contract in SKILL.md).
2. If any sub-agent failed or returned empty, note it in the report's "Verification notes" section. Do not block merging on a missing angle — proceed with what you have.
3. Dedup by `file:line`. When two candidates have the same `file:line`:
   - Merge their titles with "/" separator
   - Sum their confidence: `confidence = min(1.0, c1 + c2 + ...)` — multiple angles finding the same issue makes it more likely to be real.
   - Keep both summaries, separated by "; "
   - Keep the shorter failure scenario
4. Sort merged candidates by descending confidence.
5. Apply the max per-angle cap: no single angle should contribute > 30% of candidates. If one angle dominates, drop bottom-confidence candidates from that angle.
6. Output the merged list.

## Output

A list of candidates with `file`, `line`, `title`, `summary`, `failure_scenario`, `confidence`.

## Edge cases

- File path from angle does not exist: drop candidate, note in verification notes.
- Line number exceeds file length: drop candidate.
- Same finding from 3 angles: merge into one finding with combined confidence.
