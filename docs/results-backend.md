# Results backend (Mongo local) + DB-backed frontend

Điều kiện đo: hạ tầng, regime-agnostic (không đổi điều kiện đo, chỉ lưu + phục vụ
số đã đo). Mỗi model một `_id` chuẩn, mỗi dataset một `_id` riêng, mọi run/item
mang đủ cả hai (denormalize trên item để query không cần join).

## Mongo local

- Container `vmlu-mongo` tại `mongodb://127.0.0.1:27017/`, db `vmlu` — local-only,
  không Atlas/remote, không auth/multi-user. Web đọc qua `VMLU_MONGO_URI` /
  `VMLU_MONGO_DB` (mặc định đúng hai giá trị trên).
- Collections: `models`, `datasets`, `runs` (`_id` = `{model_id}__{dataset_id}__{card_id}`),
  `mc_items` / `reading_items` / `vbench_items` (unique index `(run_id, item_id)`),
  `summaries` (một/run, precomputed — frontend không recompute lúc đọc).
- CSVs gitignored vẫn là source of truth; blob `web/public/benchmark-data.json`
  giữ nguyên đến khi 2 drift KNOWN dưới được vá trong blob.

## Registries

- `model_id = lower(NFD-strip(sanitize_model(model)))`, `[^a-z0-9]+ → '-'`
  (design D1): `Qwen3.5-9B-28K → qwen3-5-9b-28k`, `qwen38-nothink → qwen38-nothink`,
  `Qwen3_8-27B-Q4_K_M_gguf → qwen3-8-27b-q4-k-m-gguf`. Bảng `models` giữ
  `dir_slugs[]` (mọi cách viết thư mục CSV từng thấy) + `endpoint_ids[]` nên tên
  file cũ luôn resolve về đúng một id.
- `dataset_id` là từ vựng cố định (design D2): `vmlu-mqa-valid` (744),
  `vmlu-mqa-dev` (303), `vmlu-mqa-all-gold` (1047), `vmlu-mqa-test` (9833, withheld),
  `vbench-public-test` (5141 chấm được: mc 4141 + agentic 1000; source file 9141 dòng
  gồm safety rows bị skip), `reading-400`, `legal-mc-146`, `legal-nli-150`,
  `bidlqa-val` (482), `bidlqa-test` (603). Rerun = card mới = run document mới,
  không bao giờ ghi đè run cũ.

## Migration

- `code_benchmark/seed_registries.py` — seed 2 registries (upsert, idempotent).
- `code_benchmark/migrate_results_to_mongo.py [--uri ...] [--db vmlu] [--drop] [--only <model_id>]`
  — seed → đọc finals CSV (MC/reading/V-Bench) → upsert runs/items/summaries →
  verify row-count từng file + mọi doc đủ `model_id`/`dataset_id` (lệch là abort,
  nêu tên file/count, không đánh dấu partial). Chạy lại sau khi sửa accuracy lookup
  cho `qwen38-nothink` (`accuracy_<slug>.csv` không infix): 12 runs, 24.536 items,
  0 partial.
- `code_benchmark/verify_results_db.py` — diff row-for-row DB vs CSV gốc vs blob;
  exit 0 khi chỉ còn 2 drift KNOWN đã ghi nhận (xem dưới).

## API (chỉ đọc, `Cache-Control: no-store`, không chạm blob)

- `GET /api/results/models` → `{models}` (registry, sort `_id`).
- `GET /api/results/datasets` → `{datasets}` (registry + sha256 + gold_kind).
- `GET /api/results/runs?model=&dataset=` → `{runs}` (lọc theo một/chưa hai id).
- `GET /api/results/summary?run=` → `{summary}` (400 khi thiếu `run`, 404 khi lạ).
- `GET /api/results/items?run=&item=` → `{collection, item}` (400/404 tương tự).
- Deep module duy nhất: `web/lib/db.ts`
  (`getModels/getDatasets/getRuns/getSummary/getItem`, một shared client sau seam,
  `__setDbForTest` cho tests). Contract tests: `web/lib/results-api.test.ts`
  (`cd web && bun test lib/results-api.test.ts`, fake adapter, không cần Mongo).

## Frontend

- Route mới `/results` (`web/app/results/page.tsx` + `web/components/ResultsExplorer.tsx`):
  model selector (từ `models`) → dataset selector (lọc theo datasets model đó đã chạy)
  → summary panel (từ `summaries`) → per-item lookup. Compare mode render 2 runs
  side-by-side cùng `dataset_id` (đã verify Qwen3.5 MC-10 128/146=87,67 vs
  qwen38-nothink MC-6 121/146=82,88 trên `legal-mc-146`). Không import blob.
- Cutover 4.1: `/benchmark` (blob) giữ nguyên làm render mặc định; `/results` (DB) là
  counterpart song song — cả hai 200, không đường đọc chung, không regression tab cũ.
  Header hai chiều: review `/` ↔ `/benchmark` ↔ `/results` (ghi chú cutover in ngay
  dưới header `/results`).

## Cutover evidence (verify 2026-09-20)

`.venv/bin/python code_benchmark/verify_results_db.py` → exit 0,
0 blocking diffs, 14 known blob-drifts (DB đã đúng, blob là snapshot cũ):

- KNOWN-1 (MC-9 categories): blob `.vmlu.categories` Humanity 221/68,21 + Other 99/63,46
  vs CSV+DB Humanity 222/68,52 + Other 98/62,82 — 7 đáp án bị ghi đè sau snapshot
  (overall vẫn 768/1047 cả hai phía; spot-check `54-0002` C/sai ở cả CSV+DB).
- KNOWN-2 (MC-8 vbench): blob `.vbench` là snapshot thời MC-2 (macro 44,97, micro 45,46
  = 2337/5141, model Qwen3_8) trong khi CSV+DB mang điểm server chấm lại cho Qwen3.5
  (micro 45,61 = 2345/5141; xem `docs/vbench-server-qwen35.md`).
- Xanh toàn phần: legal/nli overall + baseline recompute (A=91/62,33% và A=75/50%),
  reading-400 EM 79,75/F1 86,49, BidLQA val 32,78/74,16 + test 33,17/73,21,
  vbench `server_rows == csv` 13/13 domains, card hash hiện tại trên mọi run mới.

## Gates

- `.venv/bin/python -m unittest code_benchmark.test_suite` (88 tests, gồm
  `TestResultsIdentity`: id rules + migration gates trên fake adapter) — OK.
- `.venv/bin/python code_benchmark/test_parsing.py` (17 cases) — OK.
- `ruff check code_benchmark/` — OK; `bandit -r code_benchmark -c .bandit.yml -q` — OK.
- `cd web && bunx tsc --noEmit` — OK (test file loại khỏi tsconfig qua `bun-types`).
- `cd web && bun test lib/results-api.test.ts` — 2 pass.
- `next dev 127.0.0.1:3000`: `/`, `/benchmark`, `/results`, mọi `/api/results/*` 200.
