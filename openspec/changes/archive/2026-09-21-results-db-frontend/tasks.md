## 1. Registries + migration backend

- [x] 1.1 Seed `models` + `datasets` registries vào Mongo local (`vmlu-mongo:27017`, db `vmlu`) và verify mỗi model một `_id` chuẩn + mỗi dataset một `_id` riêng (mongosh count + spot-check `qwen3-5-9b-28k__bidlqa-val__mc-12` mang đủ `model_id`/`dataset_id`)
- [x] 1.2 Implement `code_benchmark/migrate_results_to_mongo.py` (seed registries → readers MC/reading/V-Bench → upsert runs/items/summaries → verify row-count + identity) và verify import Qwen3.5 finals (MC-7..MC-13) row-count khớp CSV, 0 partial
- [x] 1.3 Import đối chiếu `qwen38-nothink` + `Qwen3_8-27B-Q4_K_M_gguf` và verify mỗi run/item mang đúng `model_id` của model đó (không lẫn), unique index `(run_id, item_id)` xanh
- [x] 1.4 Unit tests cho quy tắc `model_id`/`dataset_id`/`run_id` + migration gates (fake client, tempdirs) và verify `python -m unittest code_benchmark.test_suite` + `ruff check` + `bandit` xanh

## 2. Web DB module + API chỉ đọc

- [x] 2.1 Thêm `mongodb` dep cho `web/` + viết deep module `web/lib/db.ts` (`getModels/getDatasets/getRuns/getSummary/getItem`, read-only, shared client) và verify `bunx tsc --noEmit` xanh
- [x] 2.2 Viết routes `web/app/api/results/{models,datasets,runs,summary,items}` (validate params, `no-store`, không chạm blob) và verify GET từng route trả JSON đúng shape trên db đã migrate
- [x] 2.3 Viết unit/contract tests cho API (mock db module, 400 khi thiếu `run`/`item`) và verify suite + tsc xanh

## 3. Frontend DB-backed (model → dataset → run → item)

- [x] 3.1 Viết route/view kết quả mới (model selector từ `models` → dataset selector lọc theo datasets model đó đã chạy → summary panel → per-item lookup) và verify smoke `next dev 127.0.0.1:3000` hiển thị đủ 3 tầng + item drill-down
- [x] 3.2 Thêm compare đa model (Qwen3.5 vs qwen38-nothink tối thiểu, cùng `dataset_id` side-by-side) và verify render đúng số cả hai runs
- [x] 3.3 Verify row-for-row DB view vs `benchmark-data.json` + CSV gốc (overall, per-category/subject, EM/F1, baseline, card hash) — diff rỗng mới pass, đường blob cũ giữ nguyên

## 4. Cutover + docs + đóng change

- [x] 4.1 Cutover đường đọc cũ sang API sau khi 3.3 pass (giữ fallback blob một commit) và verify `/benchmark` + view mới đều 200, không regression tab cũ
- [x] 4.2 Ghi `docs/results-backend.md` (registries, run_id scheme, API, cutover evidence, local-only `vmlu-mongo`) + full gates xanh (`test_suite` + `test_parsing.py` + `ruff` + `bandit` + `tsc`) rồi archive change
