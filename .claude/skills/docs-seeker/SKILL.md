---
name: docs-seeker
description: Search library/framework documentation via llms.txt (context7.com). Use for API docs, GitHub repository analysis, technical documentation lookup, latest library features.
---

# Documentation Discovery via Scripts

**Script-first** documentation discovery using the llms.txt standard.
Execute scripts to handle the whole workflow — no manual URL construction.

> Ported from `hipod/.claude/skills/docs-seeker` (MIT). Skill renamed
> `ck:docs-seeker` → `docs-seeker`; scripts/workflows/references copied
> verbatim. Tool names adapted to this environment (see mapping below).

## Tool mapping (hipod → here)

| Hipod skill text says | Use here |
|---|---|
| `WebFetch` | `webfetch` tool |
| `WebSearch` | `websearch` tool |
| `Explorer agents` / `Researcher agents` | `subagent` tool (`explore` / `general`) |
| `Bash: ...` | `shell` tool |
| `Read: ...` | `read` tool |

## Primary Workflow

Run from the repo root. **ALWAYS execute scripts in this order:**

```bash
# 1. DETECT query type (topic-specific vs general)
node .claude/skills/docs-seeker/scripts/detect-topic.js "<user query>"

# 2. FETCH documentation using script output
node .claude/skills/docs-seeker/scripts/fetch-docs.js "<user query>"

# 3. ANALYZE results (if multiple URLs returned)
node .claude/skills/docs-seeker/scripts/analyze-llms-txt.js llms.txt
```

Scripts handle URL construction, fallback chains, and error handling automatically.

## Scripts

**`detect-topic.js`** — classify query type
- Identifies topic-specific vs general queries
- Extracts library name + topic keyword
- Returns JSON: `{topic, library, isTopicSpecific}`
- Zero-token execution (pure regex, no network)

**`fetch-docs.js`** — retrieve documentation
- Constructs context7.com URLs automatically
- Handles fallback: topic → general → error
- Outputs llms.txt content or error message
- Needs network; `CONTEXT7_API_KEY` env is optional (rate limits only)

**`analyze-llms-txt.js`** — process llms.txt
- Categorizes URLs (critical/important/supplementary)
- Recommends parallel-read strategy (1 reader, 3–5 readers, phased)
- Returns JSON with strategy
- Accepts a file path or `-` for stdin

Self-test (offline, no network):

```bash
node .claude/skills/docs-seeker/scripts/tests/run-tests.js
```

## Workflow References

**[Topic-Specific Search](./workflows/topic-search.md)** — fastest path (10–15s)

**[General Library Search](./workflows/library-search.md)** — comprehensive coverage (30–60s)

**[Repository Analysis](./workflows/repo-analysis.md)** — fallback strategy
(no llms.txt: clone to `/tmp/opencode` — NOT `/tmp/docs-analysis` —
and read directly; `repomix` only if installed)

## References

**[context7-patterns.md](./references/context7-patterns.md)** — URL patterns, known repositories

**[errors.md](./references/errors.md)** — error handling, fallback strategies
(note: timeout guidance there mentions WebFetch 60s — use `webfetch` `timeout` ≤ 120s here)

**[advanced.md](./references/advanced.md)** — edge cases, versioning, multi-language

## Execution Principles

1. **Scripts first** — execute scripts instead of manual URL construction
2. **Zero-token overhead** — detect/analyze run without context loading
3. **Automatic fallback** — scripts handle topic → general → error chains
4. **Progressive disclosure** — load workflows/references only when needed
5. **Verify before citing** — NEVER invent doc URLs; only cite URLs returned
   by the scripts, `webfetch`, or `websearch`. Unverified URLs are banned
   by repo convention.
6. **Prefer local evidence last** — for API behavior questions, official docs
   beat speculation; but repo code beats docs when they disagree.

## Quick Start

**Topic query:** "How do I use date picker in shadcn?"
```bash
node .claude/skills/docs-seeker/scripts/detect-topic.js "How do I use date picker in shadcn?"
# → {topic, library, isTopicSpecific}
node .claude/skills/docs-seeker/scripts/fetch-docs.js "How do I use date picker in shadcn?"
# → 2-3 URLs
# Read URLs with webfetch
```

**General query:** "Documentation for Next.js"
```bash
node .claude/skills/docs-seeker/scripts/detect-topic.js "Documentation for Next.js"
# → {isTopicSpecific: false}
node .claude/skills/docs-seeker/scripts/fetch-docs.js "Documentation for Next.js"
# → 8+ URLs
node .claude/skills/docs-seeker/scripts/analyze-llms-txt.js llms.txt
# → {totalUrls, distribution}
# Read critical URLs first, parallelize the rest via subagent
```

## Environment

Scripts read env in this order: `process.env` > skill `/.env` > repo `.env`.
No `.env` needed by default; set `CONTEXT7_API_KEY` only if rate-limited,
and `DEBUG=true` for troubleshooting. Never commit keys.
