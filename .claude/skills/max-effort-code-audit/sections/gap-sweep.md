# Section — Gap sweep (Step 5)

## Purpose

For each confirmed finding, ask "what did I miss in adjacent code?" and add follow-up findings.

## How to run

For each confirmed finding:

1. **Read adjacent code** — open the file and read 20 lines above and 20 lines below the finding line.
2. **Ask three questions:**
   a. Is there the same pattern in the same function (e.g., same type of injection on another variable)?
   b. Is there the same pattern in the same file (e.g., another endpoint with the same missing auth)?
   c. Is there the same pattern in similarly-named files (e.g., another `*_handler.py` or `*_service.py` with the same bug class)?
3. If yes to any of the above, add a new finding:
   - Title: `"<same pattern> in <adjacent function/file>"`
   - File/line: the other location
   - Summary: same as the original finding
   - Failure scenario: same as original (or adapted)
   - Confidence: `original_confidence - 0.2` (the adjacent spot is inferred, not directly observed)
4. Mark the new findings as "gap-swept" (they get one verify pass in step 4, which they just passed).

## Notes

- Do not invent findings that are purely speculative ("maybe there is a bug in a file I haven't opened"). Only add follow-ups when you have read the adjacent code and confirmed the pattern is there.
- If the adjacent code is clean (no same pattern), do not add any follow-up.
- Gap-swept findings that fail the verify pass in step 4 are dropped, which is expected.

## Output

The augmented finding list — original findings plus gap-swept follow-ups discovered while reading adjacent code.
