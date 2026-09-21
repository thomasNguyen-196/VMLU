# Design: revamp-review-ui (rev 2 — Next.js stack per user direction)

## Context

See proposal.md – Why. Rev 1 of this design chose a stdlib `http.server` backend; the user then approved moving to **Next.js + Tailwind** (localhost, single researcher) while keeping Python as the data layer. Current state: `build_review_ui.py` (loaders + join + embed) renders `review_ui_template.html`; reviewer state lives in `localStorage` (`schema_version: 1`, `{items:{key:{d,c,n}}}`); CSV export is client-side JS; downstream consumer is `export_annotation_workbooks.py review` (`read_review()` validates the 9-column header).

## Goals / Non-Goals

**Goals:**
- Next.js app (`web/`) is the primary review tool: React components + Tailwind v4 tokens + API routes; dev/prod parity via `next dev` / `next build && next start` on localhost.
- Python remains the **validator and emitter** (`export-blob` → `web/data/review-blob.json`), preserving the single-source-of-truth for the workbook × answers join (the fail-fast column/dup/coverage checks stay in the repo's Python culture, next to the pipeline that produces the inputs).
- One shared on-disk state contract across every mode: file layout `review_state/<slug(r)>__<slug(m)>.json`, envelope `{schema_version:1, annotator, model, saved_at, items:{key:{d,c,n}}}`, slug rules — Next API routes write these, the static localStorage export imports them, and both are the input of the old UI's `state_*.json` continuity guarantee.
- Keep `review_ui.html` (self-contained, zero external requests) as the offline fallback artifact for reviewers without a dev environment.
- Export contract byte-compatible with `read_review()` no matter which mode produced the CSV — enforced by a cross-mode equivalence test, not by faith.

**Non-Goals:**
- No auth beyond the reviewer-name gate (localhost single user, decided with the user); no multi-tab conflict merging (last atomic write wins); no SSR of reviewer state (client-only after boot gate).
- No deletion of the Python static template path; no migration of historical localStorage exports is required — same schema.

## Decisions

### D1: Three surfaces, one data contract
```
CSVs (gitignored inputs)
  └─ build_review_ui.py ── export-blob ─▶ web/data/review-blob.json ─▶ Next app (web/)
                       └── build ────────▶ review_ui.html (static fallback, localStorage)
                                                    Next API routes ⇄ review_state/*.json ⇄ (import/export bridge)
```
Python validates the join ONCE (same code `build` already uses) and the app refuses to boot without a blob (clear error with the exact command to run). The previously planned `review_server.py` (stdlib http backend) is removed in favor of Next route handlers — two backends with the same behavior would drift, which is what this change exists to prevent. Rev-1's stdlib code and its 8 unit tests are deleted; the durable parts of their contract coverage move to TS-facing tests (D5).
*Alternative*: keep the stdlib server behind Next as a data API — rejected: the user chose Next for logic separation; two servers double the surface and the port story.

### D2: Next.js 16 App Router, TypeScript, Tailwind v4 — no extra runtime deps
State/export routes: `app/api/blob` (reads `web/data/review-blob.json`, no-store), `app/api/state` GET/POST (validate + atomic write via `fs.writeFile(tmp)` + `rename`, 409 on unreadable file — the "never serve corrupt as empty" rule from rev 1), `app/api/export` (CSV, BOM, `Content-Disposition`). Client: `app/page.tsx` (RSC shell) + `components/review-app.tsx` (client island holding all logic; blob passed as props via RSC fs-read, state fetched client-side). Pure logic lives in `lib/` (`slug.ts`, `state.ts`, `export-csv.ts`, `types.ts`) so it is testable without React (D5).
*Alternative considered*: Vite+React with a separate Express — rejected: Next gives app + API in one process (localhost), and the user named Next explicitly.

### D3: Fonts via `next/font/google`, design tokens via Tailwind v4 `@theme`
`Fraunces` (display) + `Be Vietnam Pro` (body, `subsets: ["vietnamese","latin"]` — diacritics are the dataset's core) + `JetBrains Mono` (model output). `next/font` downloads and **self-hosts at build time** — dev machine has network now; the app never ships a runtime font request. Tokens (D5 of rev 1, unchanged): paper `#F5F3EE`, ink `#1A1D23`, accept `#1E7A46`, reject `#C2372C`, flag `#B4700E`, null `#C8C4BA`, dark-mode variants; **color is only decision state** — all chrome graphite-on-warm-paper, deliberately not the cream-serif or acid-dark defaults. Signature filmstrip ruler (400 passage-grouped cells, grow-on-decide, click-to-jump, dataset boundary gap) + fixed bottom dock (Prev / item n/N / Next / next-unreviewed / save pill) carried over from rev 1 unchanged.

### D4: State slug + envelope are shared contracts, enforced by tests
`slug()` (NFD strip-diacritics → `_`-join) is the bucket identity used by: the template JS, the Next `lib/slug.ts`, and (historically) Python. With rev 1's Python server gone, Python's only remaining consumer is the docs/tests — the parity test now runs the **TS** source through Node 24 type-stripping (or bun) and compares against the JS in the template. The envelope's TS type lives in `lib/types.ts`; `POST /api/state` rejects schema_version ≠ 1 and body/query identity mismatch (stale-tab guard).

### D5: Contract tests move to a Node-executed layer
`test_suite.py` gains `TestNextContracts` (skipUnless a TS runner is found: `node --experimental-strip-types` or `bun`): (a) slug parity vs the template's JS reference outputs; (b) `makeExportCsv(blob, envelope)` from `lib/export-csv.ts` over a fixture decisions set → bytes must feed `read_review()` and equal the static template's client-side `buildCsv()` output row-for-row (the same equivalence assertion rev 1 made, now static-vs-Next). Python-side, `export-blob` gets an end-to-end CLI fixture test. `npm run build` typecheck is part of local verification.
*Alternative*: full vitest in web/ — deferred: adds a JS test stack; the contracts that actually matter (slug, CSV shape, envelope) are covered from the existing CI (unittest) without new CI jobs. Can be added later without changing behavior.

### D6: Offline static fallback stays honest
`build_review_ui.py build` keeps working unchanged (its 449-line proven template — now the rev-1 redesigned one: hand-written CSS, zero CDN, server code paths inert under `file://`). `review_ui.html` remains the email-to-reviewer-B artifact; its Export CSV/JSON + Import JSON bridge the localStorage world to the disk buckets.

## Risks / Trade-offs

- **Node toolchain on the review machine** — required for the primary mode; mitigated: the static fallback covers any machine, and `npm ci` is one command.
- **Blob staleness** (CSVs changed after `export-blob`) — the blob carries `created` date; the app displays it and the README workflow (`export-blob → npm run dev`) makes refresh the first step of every session. (A future `watch` mode was considered and skipped.)
- **API route fs semantics differ from Python's** (atomicity, corrupt handling) — ported deliberately and asserted by curl-level route tests in the Next run (manual checklist, mirrored from specs) + the D5 equivalence tests for the CSV path specifically.
- **Tailwind v4 + custom tokens**: `@theme` tokens keep the design system honest; utility soup is contained by component boundaries.
- **CI grows a JS surface** — untouched jobs still gate Python; web/ gets its own `npm run lint/build` step locally before merge; adding a CI node job is a follow-up.

## Migration / Rollout

1. `export-blob` + `web/` app land; `review_server.py` deleted (its capability spec is retargeted at the Next backend, not dropped — file layout and CSV contract identical).
2. `.gitignore` += `web/data/` (derived, contains dataset text). `review_state/` stays ignored.
3. CLAUDE.md workflow section updated to: `export-blob` → `cd web && npm run dev` (primary); `build` (fallback); `export_annotation_workbooks.py review --a --b` unchanged.

## Open Questions

None blocking.
