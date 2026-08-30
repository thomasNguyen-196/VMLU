# Section — Write report (Step 7)

## Purpose

Render the ranked findings as a markdown report and write it to `output_path`.

## How to run

1. Determine `output_path` — use user-provided value or default to `code-review-report-YYYY-MM-DD.md` at the repo root.
2. Render the report using the template below.
3. Update `.gitignore` at the repo root to include `code-review-report-*.md` if not already present. Do this by reading `.gitignore`, checking for the pattern, and appending it if missing.
4. Print a one-line confirmation: `Report written to <path>`.

## Report template

```markdown
# Code Review Report — Max Effort (`{scope}`)

**Scope:** {file_count} files across {language_list} | **Date:** {date}

---

## Findings ({finding_count} remaining, ranked by severity)

{findings_section}

---

## Summary

| Severity | Count | Key impact |
|---|---|---|
| CRITICAL | {critical_count} | {critical_impact} |
| HIGH | {high_count} | {high_impact} |
| MEDIUM | {medium_count} | {medium_impact} |

### Notable non-bug findings (not counted in {finding_count})

{non_bug_items}

### Verification notes

{verification_notes}

### Out of scope (for follow-up)

{out_of_scope_items}
```

### Findings section format

Each finding uses this structure:

```markdown
1. **{Title}**
   - **File:** {file_path}
   - **Line:** {line_number}
   - **Severity:** {severity}
   - **Summary:** {summary}
   - **Failure scenario:** {failure_scenario}
```

Number sequentially. Rank: CRITICAL descending → HIGH descending → MEDIUM descending.

### Summary section

- `critical_impact`: one sentence naming the most damaging critical finding.
- `high_impact`: one sentence naming the most widespread high finding.
- `medium_impact`: one sentence naming the most common medium class.

### Non-bug findings

One bullet per item, each line is a short statement (10-20 words). These are findings from angle 10 (process/convention violations) and anything that is true but not a code bug.

### Verification notes

- For each finding: "Finding N: read {K} lines of context at {file}:{line}, confirmed — {specific observation}."
- For each dropped candidate: "Dropped: {title} — {reason} ({false positive, out of scope, already fixed})."
- For each hallucinated candidate: "Hallucinated: {title} — file/line does not exist or is incorrect."

### Out of scope

Items the audit noticed but intentionally did not pursue: missing test files, performance concerns, accessibility, third-party dependency version pinning, etc.

## Output

The rendered markdown file and the .gitignore update.
