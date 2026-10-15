# Tasks: revamp-review-ui (rev 2 — Next.js stack)

Status carried over from rev 1: the redesigned static template (design system, filmstrip, dock,
Backend seam, static parity) and its blob/store/export unit coverage are DONE and stay valid — the
template becomes the *fallback*. Rev 1's `review_server.py` + its HTTP tests are superseded and removed.

## 1. Python: blob emitter + rev-1 backend removal

- [x] 1.1 (rev 1, kept) `build_review_ui.py` loaders stay import-side-effect-free; template rebuilt with the design system, filmstrip and dock (`build` path unchanged, offline `file://` capable).
- [x] 1.2 Add `export-blob` to `build_review_ui.py`: reuse the exact join+coverage validation from `build`, write the blob to `web/data/review-blob.json` (mkdir -p), print counts; verify `.venv/bin/python code_benchmark/build_review_ui.py export-blob` produces a file whose `schema_version/items/passages/models` load via `json.load`.
- [x] 1.3 Remove `code_benchmark/review_server.py`, the `serve` subcommand, and the `TestReviewServer` HTTP tests it fed; verify: `grep -rn review_server code_benchmark CLAUDE.md` is empty and `.venv/bin/python -m unittest code_benchmark.test_suite` passes.
- [x] 1.4 Add a `TestExportBlob` unittest: fixture workbook + answers CSV → `export-blob` writes the expected blob; a coverage-drift case exits non-zero and leaves the prior file untouched (mtime/content).

## 2. Next app scaffold & contracts (`web/`)

- [x] 2.1 (done) Scaffold Next 16 + React 19 + TS + Tailwind v4 in `web/`.
- [x] 2.2 `web/lib/`: `types.ts` (Blob/Item/Envelope/Decision types mirroring schema_version 1), `slug.ts` (port of the template JS slug — NFD strip diacritics, non-alnum → `_`), `state.ts` (bucket path + read/atomic write + envelope validation), `export-csv.ts` (9-column CSV builder with csvCell quoting + BOM decision). Verify: `npx tsc --noEmit` clean.
- [x] 2.3 API routes: `GET /api/blob` (serve `web/data/review-blob.json`, no-store; 500 + command hint when missing), `GET|POST /api/state` (query `r`/`m` slugged; POST validates schema_version + body-vs-query identity → 409 stale-tab; corrupt file → 409 never-empty), `GET /api/reviews` (bucket list with decided/total/saved_at), `GET /api/export` (workbook-order CSV + BOM + Content-Disposition). Verify: curl each against `npm run dev` and check the documented scenarios from the review-server spec.
- [x] 2.4 Root layout: `next/font/google` (Fraunces, Be Vietnam Pro subsets latin+vietnamese, JetBrains Mono) as CSS variables; `globals.css` `@theme` block carrying the exam-instrument tokens (paper/ink/accept/reject/flag/null + dark variants); Vietnamese-first `lang="vi"`, `<title>`. Verify: dev server renders with fonts self-hosted (no fonts.googleapis request in the network panel).

## 3. Review UI components

- [x] 3.1 `components/review-app.tsx` (client island) state core: annotator gate (localStorage + cookie for return visits), model select, active bucket load/save, debounced autosave (450 ms) + save-status pill, decision/correction/note mutations, per-item key `dataset:item_id`. Verify: reload restores decisions; a save failure shows the fallback banner and keeps localStorage copy.
- [x] 3.2 Item view: passage-grouped position line (đoạn X · câu i/n), dataset + stratum + item tags, question, collapsible context (default open desktop / collapsed narrow), model answer panel in mono with n/a state, reject-without-correction error state. Verify against review-ui spec scenarios.
- [x] 3.3 Decision panel: Accept/Reject/Bỏ trống radio group (`role=radiogroup`, `aria-checked`), correction textarea (disabled unless reject, `.bad` outline when empty+reject), note textarea, stratum/dataset progress table, Export CSV / Export state / Import state / + answers CSV controls. Verify: import of a rev-1 `state_*.json` restores all decisions.
- [x] 3.4 `components/filmstrip.tsx`: passage-grouped flex ruler (grow = item count, ink divider per passage, dataset gap label), states unreviewed/accept/reject/flag, 20 px grow transition, click-to-jump, current-caret, horizontal scroll on narrow viewports, `aria-label` per passage group. Verify: deciding updates the cell live; clicking jumps; 375 px viewport scrolls without page overflow.
- [x] 3.5 `components/nav-dock.tsx`: fixed bottom dock — Prev (disabled at 0), item n/N counter, Next (primary), next-unreviewed; plus header cluster (brand, accept %, reviewed n/N, reject count, model select, reviewer, save pill, help). Verify: boundary disable behavior + keyboard parity with 3.6.
- [x] 3.6 Keyboard protocol + shortcuts overlay: `j/k/↑/↓`, `a`/`space`, `r`, `u`, `e`, `n`, `t`, `Home/End`, `?`/`Esc`, inert while typing; `prefers-reduced-motion` disables transitions/smooth scroll. Verify: manual run of the full review loop without touching the mouse.

## 4. Tests, equivalence, CI, docs

- [x] 4.1 `TestNextContracts` in `code_benchmark/test_suite.py` (skipUnless node/bun): slug parity — evaluate `web/lib/slug.ts` (type-stripped) against the template's JS reference outputs; and mode equivalence — run `web/lib/export-csv.ts` and the template's `buildCsv()` over the SAME blob + decisions, feed both through `read_review()`, assert identical meta + row maps.
- [x] 4.2 Run every gate locally: `uvx ruff@0.16.1 check .`, `uvx --from bandit bandit -r code_benchmark -c .bandit.yml -q`, `test_parsing.py`, `python -m unittest code_benchmark.test_suite`, plus `npm run lint` and `npm run build` in `web/`; fix anything red.
- [x] 4.3 Docs & hygiene: `.gitignore` += `web/data/` (and keep `review_state/`); rewrite the CLAUDE.md §4 commands for `export-blob` → `cd web && npm run dev` (primary) and `build` (fallback), note Node 24 requirement; `web/README.md` or CLAUDE.md pointer for the annotator workflow; regenerate `review_ui.html`; check the change with `openspec validate revamp-review-ui`.
- [x] 4.4 Manual acceptance pass against both spec files end-to-end (server mode: 5 decisions incl. a flag, export → `export_annotation_workbooks.py review` self-merge prints sane stats; static mode: same in Chrome `file://`), then screenshot-review the UI and remove one accessory if it shouts.
