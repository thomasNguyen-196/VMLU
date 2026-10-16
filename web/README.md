# VMLU Reading Review — `web/`

The primary review tool for the pre-registered 400-question Vietnamese
reading-comprehension eval (issue #3): a local Next.js app where two
researchers mark the model's free-text answers **accept** (becomes gold) or
**reject** (+ correction). State autosaves to disk buckets under
`../review_state/`; exporting the CSV publishes it to the tracked
`../review_records/` folder — the split-the-400 handoff log.

## Quick start

```bash
# 1. From the repo ROOT, regenerate the input blob (the validated
#    workbook × answers join — see code_benchmark/build_review_ui.py):
.venv/bin/python code_benchmark/build_review_ui.py export-blob

# 2. Then here:
npm install
npm run dev          # http://localhost:3000 (loopback-only bind)
```

No API keys and no network at runtime: the app reads `data/review-blob.json`
(tracked, so every reviewer serves the identical eval) and writes only local
JSON/CSV files. The offline fallback for reviewers without Node is the
self-contained `../review_ui.html` (same 9-column CSV contract).

## Layout

- `app/` — server component entry (`page.tsx` reads the blob from disk) + the
  five disk-backed API routes (`/api/blob`, `/api/state`, `/api/export`,
  `/api/reviews`, `/api/records`).
- `components/` — client UI: `ReviewApp` orchestrates; leaf components are
  memoized. Keyboard protocol lives in `hooks/use-keyboard`.
- `lib/` — pure logic (`review-logic.ts`), the Zustand session and diagnostic
  draft stores, and the
  server-only disk helpers (`state.ts`, `records.ts`, `blob.ts` — they import
  `fs`; client code may only `import type` from them).

`lib/slug.ts` and `lib/export-csv.ts` are executed by the Python contract
tests (`code_benchmark/test_suite.py :: TestNextContracts`): their **paths**
and their review-CSV byte output are pinned — never rename or re-layout them.

## Checks

```bash
npx tsc --noEmit   # CI does not build web/ — typecheck locally
npm run lint
```

Full pipeline tests: run `python -m unittest code_benchmark.test_suite` from
the repo root (needs bun or node ≥ 22 for the cross-language contract tests).


### Diagnostic reviewer progress (review v4)

`/diagnostic` keeps one current progress record per normalized reviewer name, pilot hash, protocol hash and scope. Zustand/localStorage is the browser cache and holds unsynced changes; the authoritative synchronized state is in MongoDB `diagnostic_progress` in `VMLU_MONGO_DB` (default `vmlu`). It uses the existing `VMLU_MONGO_URI`. The `/api/diagnostic-progress` GET/POST endpoint checks the locked pilot identity, item scope and editor identity. Atomic revision checks reject stale/concurrent writers instead of silently overwriting progress. A failed save retains the local cache and exposes retry/download recovery. Names are self-declared identities, not authenticated accounts.

Human edit metadata is separate from the judgment schema: editor name and last edit time are recorded per item. AI-only prefilled proposals count as **Chưa làm**; an actual form change counts as **Đã chỉnh · chưa xác nhận**; **Đã hoàn tất** and **Tạm hoãn** still require the original complete judgment and human attestation. No automatic human completion, audit import or causal upgrade is performed. Existing v4 browser caches are preserved; prior differences from the frozen AI proposals can be recovered without inventing a historical timestamp. Old v1/v2/v3 backups remain downloadable under a collapsed rubric-history section.

`diagnostic_reviewer_exposure` records primary AI exposure by normalized reviewer identity, so a new browser cannot reuse that identity for Independent-15. Reviewer isolation is for this local research app; it is not an authorization boundary.

Docker runtime: `vmlu-web` and `vmlu-mongo` share the `vmlu-local` network; the web container uses `mongodb://vmlu-mongo:27017/`. Mongo data remains in `vmlu-mongo-data`. Host ports 3000 and 27017 bind to 127.0.0.1; both services use restart policy `unless-stopped`.

Focused checks: `bun test lib/diagnostic-review.test.ts lib/diagnostic-store.test.ts lib/diagnostic-progress.test.ts lib/diagnostic-progress-server.test.ts`.
