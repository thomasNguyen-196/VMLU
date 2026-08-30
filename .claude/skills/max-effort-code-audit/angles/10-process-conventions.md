# Angle 10 — Process / convention violations

## What to look for

- Commits that lack `type:` prefix (e.g., `fix:`, `feat:`, `chore:`, `docs:`)
- `git init` at the monorepo root where each sub-repo has its own `.git`
- Config changes that contradict `AGENTS.md` or `CLAUDE.md` documented rules
- Dead code: functions that are `pass` only, unreachable branches, commented-out code
- Unbounded in-memory data structures with no eviction (growing maps, lists, queues)
- Hardcoded values that should be env vars (URLs, ports, timeouts)
- Import paths that break the documented module structure

## Grep seeds

```
git log --oneline
git init
pass$
cleanup_
def _\(
# .*TODO
# .*FIXME
# .*HACK
os\.environ
os\.getenv
```

## Checklist

1. Check `git log --oneline -20` for commits without a recognized prefix prefix (`feat:`, `fix:`, `chore:`, `docs:`, `perf:`, `refactor:`, `test:`, `ci:`, `revert:`).
2. Check for `git init` in the repo history or root `.git` (violates AGENTS.md).
3. Check any cleanup functions or scheduled tasks: are they actually implemented or are they `pass`?
4. Check for in-memory caches / maps that grow indefinitely without TTL or size limit.
5. Check that undocumented hardcoded URLs and ports match the env-var-driven config.

## Known pattern from 2026-06-30 report

- Non-bug: two commits lack `type:` prefix.
- Non-bug: `root git init` evidence in commit `d1fa054`.
- Non-bug: `cleanup_expired` is `pass` in `token_blacklist.py` — unbounded in-memory growth.

## Output

Return each convention violation. Distinguish between code-level issues (dead code) and process-level issues (commit format, monorepo structure). If it is a process-level issue, note that it is a non-bug finding.
