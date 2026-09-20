## Why

Kết quả benchmark đang nằm rải rác trong CSV gitignored theo từng model + một blob JSON đơn-model (`web/public/benchmark-data.json`); không có kho truy vấn được, không so sánh đa model, frontend không đọc được lịch sử chạy. Mongo local (`vmlu-mongo`, `mongodb://127.0.0.1:27017/`) đã chạy và ping OK — đã đến lúc chốt backend + frontend DB-backed, với **identity đàng hoàng: mỗi model một id chuẩn, mỗi dataset một id riêng, mọi run/item gắn cả hai**.

## What Changes

- **Registry `models`** (collection riêng, `_id` = canonical model id, stable, lowercase, URL-safe): mỗi model một document — `display_name`, `dir_slugs[]` (thư mục CSV hiện có), `endpoint_ids[]` (id endpoint từng dùng), quantization/params/endpoint/notes. Dataset của model nào chạy thì run/item của nó mang đúng `model_id` đó (denormalize trên item để query không cần join).
- **Registry `datasets`** (collection riêng, `_id` = dataset id ổn định): mỗi dataset một document — `benchmark`, `split`, `n`, `source_file`, `source_sha256`, `gold_kind` (withheld/local/file/reviewed), `manifest_path`.
- **Mongo store `vmlu`**: collections `runs` (`_id` = `{model_id}__{dataset_id}__{card_id}`, mang `model_id` + `dataset_id` + card/condition/config/`measurement_card_hash`), `mc_items` / `reading_items` / `vbench_items` (mỗi item mang `run_id` + `model_id` + `dataset_id`, unique index `(run_id, item_id)`), `summaries` (một/run, precomputed, mang hash), theo đúng contract Phase 5 đã duyệt (ragged shapes giữ nguyên).
- **Migration script một lần** (`code_benchmark/migrate_results_to_mongo.py`): seed 2 registries trước, import mọi CSV hiện có (Qwen3.5-9B-28K chính + qwen38-nothink / Qwen3_8-27B-Q4_K_M_gguf đối chiếu), verify row-count từng file, summaries mang `measurement_card_hash`; idempotent upsert, refuse partial.
- **API routes trong `web/`** (`/api/results/*`): `models`, `datasets`, `runs?model=&dataset=`, `summary?run=`, `items?run=&item=` — đọc từ Mongo, không recompute aggregate lúc đọc.
- **Dashboard DB-backed**: route/view mới với **model selector → dataset selector** (đọc từ 2 registries), so sánh đa model (Qwen3.5 vs qwen38-nothink tối thiểu), verify row-for-row với blob file trước khi thay đường đọc cũ; đường đọc blob cũ giữ xanh đến lúc cutover.
- **Provenance**: mọi document mang `measurement_card_hash` + card id (MC-7..MC-13); số hiển thị phải recompute-clean từ items CSV gốc.

## Capabilities

### New Capabilities

- `results-backend`: model/dataset registries + Mongo store, ingest migration có verify, API routes chỉ đọc, DB client trong `web/lib/` only.
- `results-dashboard`: view DB-backed (model selector → dataset selector, đa model compare, per-item lookup), kiểm row-for-row với blob trước cutover.

### Modified Capabilities

(none — additive; prompt/parser/scoring/review contracts giữ byte-frozen)

## Impact

- Code mới: `code_benchmark/migrate_results_to_mongo.py` + `web/lib/db.ts` (+ `mongodb` dep trong `web/` only) + `web/app/api/results/*` + route/view DB-backed mới; runners/scorers/builders không sửa (chỉ đọc CSV qua CLI hiện có).
- Deps: Python migration cần `pymongo` (cài qua `uv pip`, không chạm `requirements.txt` legacy); web thêm `mongodb` driver; CI gate không đổi (ruff F,B,E9 + bandit + parity + unittest).
- Systems: Mongo local `vmlu-mongo:27017`, db `vmlu`; CSVs vẫn là source of truth đến khi migration row-count pass; blob `benchmark-data.json` giữ nguyên đến khi DB view verify xong.
- Docs: `measurement_card.md` không thêm card mới (infra, không phải run); record registries + migration + API + cutover trong `docs/`.

## Non-goals

- Không chạy thêm inference mới, không regime B/C, không quantization/reasoning-budget.
- Không đụng `build_prompt` / `extract_answer` / `REVIEW_COLS` / `slug()` / `SCHEMA_VERSION`.
- Không seatau telecom, không dialog pipeline, không syllogism judge, không train-split eval.
- Không auth/multi-user, không Mongo Atlas/remote — local container only.

## Evaluation regime touched

Regime **A** (official template, temperature 0, seed 42). Backend là infra regime-agnostic (không đổi điều kiện đo, chỉ lưu + phục vụ số đã đo).
