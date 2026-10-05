## 1. Genome + guard (offline first)

- [x] 1.1 `code_benchmark/harness_genome.py` (stdlib-only): frozen `Genome`
  dataclass over the §4 gene groups, `from_dict`/`to_dict`/`canonical_json`/
  `genome_id`, closed enums with fail-fast `validate()`.
  - **Bằng chứng:** module; `Genome` là frozen dataclass, 8 nhóm gene khớp §4.
- [x] 1.2 Frozen-surface guard: `TEMPLATE_IDS` closed registry, per-template
  token ceilings cited to their runner line, `MAX_TOKENS_HARD_CAP`,
  `frozen_fingerprints()`, deny-keys + value-shape check.
  - **Bằng chứng:** `TEMPLATE_IDS` với 5 entry, ngưỡng 4/48/64/512 trích dẫn
    `run_mc_eval`/`run_reading_eval`/`run_vbench_eval`; `frozen_fingerprints()`
    trả sha256 cho 3 hàm đóng băng.
- [x] 1.3 `required_declarations()` + `baseline_genome()` / `minimal_genome()`.
  - **Bằng chứng:** 4 nhóm khai báo (guided / temperature / samples / shuffle).

## 2. Evidence bundles (§3.4)

- [x] 2.1 `collect_evidence()`: bundle gồm genome.json, frozen_fingerprints.json,
  harness.diff, budget.json, manifest.json, README.md — **tham chiếu** CSV kết quả
  theo đường dẫn, không copy; fail-fast nếu artifact không tồn tại.
  - **Bằng chứng:** hàm + test: bundle ghi `code_changed=false` cho mutation
    chỉ đổi config; thiếu CSV ⇒ `SystemExit`.

## 3. Guard tests (CI enforcement)

- [x] 3.1 Offline tests: genome hợp lệ (round-trip id ổn định), group lạ, enum
  lạ, `fewshot.k` lệch với elicitation, `tools` chứa "none" lẫn tool thật,
  shuffle không seed, vượt trần token MC, giá trị có dấu `/` hoặc `import `,
  khai báo bắt buộc, breakdown theo category/subject.
  - **Bằng chứng:** `TestHarnessGenome`; suite **OK**, ruff sạch.

## 4. Gene → CLI flag (P1 bước 1) — xong

- [x] 4.1 ~~Pre-register MC-46: chạy `minimal_genome()` để có cặp seed~~ — **đã
  hủy, và lý do mới**: arm **A3 đã chính là `minimal_genome()`** (gọi thẳng, prompt
  đóng băng, temp 0, seed 42), đã đo trên 6 tập ở MC-31/32. Chạy lại là đo trùng.
  Cặp seed mà §6 cần thật ra đã có, chỉ là dưới dạng **arm** chứ không phải genome —
  nên MC-46 chuyển sang đo factorial persona × tools trên 65K (xem MC-46/47).
  - **Bằng chứng:** MC-47 xác nhận 4 ô + noise floor; `docs/rq1-decomposition.md`.
- [x] 4.2 Bảng gene → CLI flag: `code_benchmark/genome_to_cli.py` với
  `support_matrix()` + `plan()` fail-fast.
  - **Bằng chứng:** ma trận 22 dòng — **8 implemented, 2 routed, 1 external,
    1 separate-pipeline, 10 unsupported**; `plan()` chặn 5 nhóm gene chưa có runner.

## 5. Những gì bảng gene phơi ra (ghi để không quên)

| phát hiện | nghĩa là gì |
|---|---|
| **10/22 gene chưa chạy được** | `cot`, `fewshot_k`, toàn bộ `rag`, `samples_per_item>1`, và 3 tool có tên. Lưới P1 **không thể** quét chúng cho tới khi có runner |
| **3 tool có tên không tồn tại** | menu thật của omp là 11 tool (`read, bash, edit, eval, glob, grep, task, hub, todo, web_search, write`). `calculator`/`date_arith`/`enum_verbatim_lookup` chỉ có trong kế hoạch |
| **`elicitation` chỉ có 2 giá trị thật** | `minimal` và `detailed`, mà `detailed` chỉ chạy được ở runner V-Bench. Muốn đổi prompt MC/reading là **việc mới**, không phải đổi cờ |
| **harness không có `--temperature`** | temp 0 được ghim bằng proxy ⇒ **proxy là một phần của điều kiện**. MC-47 đã đo cái giá khi proxy chết: 25 item `exit 1`, chậm 60×, preflight không thấy |
| **`baseline_genome()` đã sửa** | bản đầu mã hoá RAG + tool có tên ⇒ mô tả một lần chạy **không tồn tại**. Nay mã hoá đúng arm T65 đã đo: `tools=all`, không RAG, temp 0, 1 mẫu |

## 6. Ngoài phạm vi

- Grid search, evolution loop, meta-agent (P1–P2).
- Sandbox + codegen tools (P4, §7).
- Sửa tiền đề model `Qwen3.8-27B` trong plan → `Qwen3.5-9B-65K` (ghi ở
  proposal, thực hiện khi chốt P1).