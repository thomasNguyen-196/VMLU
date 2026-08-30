# Angle 6 — Signature / call-site drift

## What to look for

- A function's signature changed but one or more callers still pass the old arguments
- A method/function was overloaded or had a parameter added, but some callers were missed
- Renamed/moved functions where old import paths still exist
- Wrapper functions that don't forward all arguments
- Call sites that pass positional args that became keyword-only

## Grep seeds

Not pattern-based. Instead, the agent must:

1. Gather all `def` / `func` / `function` definitions that appear in the diff or in recently modified files.
2. For each function that changed its signature (new/dropped/renamed params), search for all callers.
3. Check each caller against the current signature.
4. Also check: did any function have a parameter type changed (str → UUID, str → int, list → set)?

## Checklist

1. Find all `def function_name(` in the diff scope.
2. For each function where the diff shows a signature change, grep for `function_name(` across the affected codebase.
3. Compare the call-site args to the new signature — mismatched count or type is a finding.
4. Check for renamed functions where the old-name references still exist.
5. Check for commonly misused functions: `add_token(self, jti: str)` that some callers pass 2 args to.

## Known pattern from 2026-06-30 report

- #3: `mcp_servers.py:465` — calls `token_blacklist.add_token(instance.mcp_token_jti, exp_ts)` but `add_token` only accepts `jti: str`. One call site was fixed in commit `76250a9` but this one was missed.

## Output

Return each mismatched call site. Include file, line, the function name, the old signature, the new signature, and whether the mismatch causes a TypeError or silent wrong behavior.
