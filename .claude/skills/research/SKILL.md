---
name: research
description: Research technical solutions, analyze architectures, gather requirements thoroughly. Use for technology evaluation, best practices research, solution design, scalability/security/maintainability analysis.
---

# Research

> Ported from `hipod/.claude/skills/research` (MIT). Skill renamed
> `ck:research` → `research`. Adapted: search backend is the native
> `websearch`/`webfetch` tools (no `gemini` CLI, no `.ck.json` toggle);
> doc lookup delegates to the local `docs-seeker` skill; reports default
> to chat output per repo file-creation rules.

## Research Methodology

Always honoring **YAGNI**, **KISS**, and **DRY** principles.
**Be honest, be brutal, straight to the point, and be concise.**

### Phase 1: Scope Definition

Clearly define the research scope by:
- Identifying key terms and concepts to investigate
- Determining recency requirements (how current must information be)
- Establishing evaluation criteria for sources
- Setting boundaries for research depth
- If the topic is ambiguous, ask the user one round of clarifying
  questions (via the `question` tool) before spending search budget

### Phase 2: Systematic Information Gathering

Multi-source research strategy:

1. **Search strategy** (native `websearch` tool):
   - Run searches in parallel where independent
   - Craft precise queries with keywords like "best practices", current
     year, "latest", "security", "performance"
   - Target official documentation, GitHub repositories, authoritative blogs
   - Prioritize recognized authorities (official docs, major tech
     companies, respected developers)
   - **IMPORTANT:** at most **5 research tool calls** per task unless the
     user explicitly asks for more. Think before each call; respect a
     smaller budget if the user requests it.

2. **Deep content analysis**:
   - For a promising GitHub repo or library docs, delegate to the
     `docs-seeker` skill (llms.txt-first lookup)
   - Focus on official documentation, API references, technical specs
   - Analyze READMEs of popular repos; review changelogs/release notes
     for version-specific information
   - Fetch full pages with `webfetch`; never cite a URL you have not
     fetched or that search did not return (no invented URLs)

3. **Cross-reference validation**:
   - Verify information across multiple independent sources
   - Check publication dates to ensure currency
   - Identify consensus vs. controversial approaches
   - Note conflicting information or community debates

### Phase 3: Analysis and Synthesis

- Identify common patterns and best practices
- Evaluate pros and cons of different approaches
- Assess maturity and stability of technologies
- Recognize security implications and performance considerations
- Determine compatibility and integration requirements
- For this repo: always map findings back to the measurement contract
  (`measurement_card.md`) — a solution that cannot be measured under a
  locked card is not a recommendation, it is a hypothesis

### Phase 4: Report

Default: present the report **in chat**. Save to a file only when the
user asks or the report must be durable/shared — then use
`docs/research/<topic-slug>.md` (create the dir if needed).

```markdown
# Research Report: [Topic]

## Executive Summary
[2-3 paragraph overview of key findings and recommendations]

## Research Methodology
- Sources consulted: [number]
- Date range of materials: [earliest to most recent]
- Key search terms used: [list]

## Key Findings

### 1. Technology Overview
[Comprehensive description of the technology/topic]

### 2. Current State & Trends
[Latest developments, version information, adoption trends]

### 3. Best Practices
[Recommended practices with explanations]

### 4. Security Considerations
[Security implications, vulnerabilities, mitigations]

### 5. Performance Insights
[Performance characteristics, optimization techniques, benchmarks]

## Comparative Analysis
[If applicable: comparison of solutions/approaches]

## Implementation Recommendations

### Quick Start Guide
[Step-by-step getting started]

### Code Examples
[Relevant snippets with explanations]

### Common Pitfalls
[Mistakes to avoid and their solutions]

## Resources & References

### Official Documentation
- [Linked list of official docs]

### Recommended Tutorials
- [Curated list with descriptions]

### Community Resources
- [Forums, Stack Overflow tags]

### Further Reading
- [Advanced topics]

## Appendices (only if needed)

### A. Glossary
[Technical terms and definitions]

### B. Version Compatibility Matrix
[If applicable]

## Unresolved Questions
[List anything left open]
```

## Quality Standards

- **Accuracy**: verified across multiple sources
- **Currency**: prioritize the last 12 months unless historical context is needed
- **Completeness**: cover all aspects the user requested — no more
- **Actionability**: practical, implementable recommendations
- **Clarity**: clear language, defined terms, examples
- **Attribution**: always cite sources with links for verification

## Special Considerations

- Security topics: check recent CVEs and advisories
- Performance topics: look for benchmarks and real-world case studies
- New technologies: assess community adoption and support levels
- API docs: verify endpoint availability and auth requirements
- Always note deprecation warnings and migration paths

## Output Requirements

1. Timestamp of when the research was conducted
2. Table of contents for longer reports
3. Code blocks with appropriate syntax highlighting
4. Diagrams where helpful (mermaid or ASCII art)
5. Specific, actionable next steps at the end
6. Unresolved questions listed explicitly

**IMPORTANT:** Sacrifice grammar for the sake of concision when writing reports.

**Remember:** not just collecting information, but strategic technical
intelligence for informed decisions. Anticipate follow-up questions,
stay focused and practical.
