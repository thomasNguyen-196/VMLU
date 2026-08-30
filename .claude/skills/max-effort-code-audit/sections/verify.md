# Section — 1-vote verify (Step 4)

## Purpose

For each merged candidate, read the code at the cited location and confirm the finding is real.

## How to run

For each candidate (in descending confidence order):

1. **Open the file** at the cited line. Read at least 30 lines of context (15 before, 15 after).
2. **Check the finding is real:**
   - Is the vulnerability/issue actually reachable?
   - Is there a guard or check earlier that prevents it?
   - Is the cited line part of dead code or a test file?
3. **Write a failure scenario**: one concrete paragraph describing exactly what an attacker or user does to trigger the issue and what happens.
4. **Adjust confidence**:
   - Confirmed with real failure scenario: keep confidence as-is.
   - Confirmed but hard to reach: reduce to `max(0.3, confidence - 0.3)`.
   - False positive: drop the candidate.
5. **Cap**: at most 1 verify pass per finding (do not re-verify).

## Edge cases

- **Already fixed**: if the finding was already addressed in a later commit, note it in verification notes. Do not count it as a finding.
- **Out of scope**: if the finding is a style/lint/test issue, note it in "Out of scope" section. Do not count it.
- **Dupe of higher-confidence finding**: if this candidate is genuinely the same bug as a higher-confidence one, merge them (keep the higher confidence, keep both failure scenarios).
- **File doesn't exist or line is wrong**: drop candidate, note hallucination.

## Output

The confirmed finding list (original candidates minus dropped ones, with adjusted confidence where applicable).
