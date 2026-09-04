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
- `lib/` — pure logic (`review-logic.ts`), the zustand session store, and the
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
