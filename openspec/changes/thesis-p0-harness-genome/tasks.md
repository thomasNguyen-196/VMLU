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

## 4. Chạy seed (CẦN CARD RIÊNG — chưa làm ở đây)

- [ ] 4.1 Pre-register MC-46: chạy `minimal_genome()` trên `legal_mc` ở
  `Qwen3.5-9B-65K` để có **cặp seed** minimal/detailed mà §6 cần (cặp hiện có
  chỉ ở runner V-Bench trên 28K). Cần VPN + endpoint ⇒ không thuộc change này.
- [ ] 4.2 Bảng gene → CLI flag (P1): ánh xạ mỗi gene sang flag thật của
  `run_harness_eval.py` / `run_vbench_eval.py`, để genome không thành cách viết
  thứ hai cho cùng một phép đo.

## 5. Ngoài phạm vi

- Grid search, evolution loop, meta-agent (P1–P2).
- Sandbox + codegen tools (P4, §7).
- Sửa tiền đề model `Qwen3.8-27B` trong plan → `Qwen3.5-9B-65K` (ghi ở
  proposal, thực hiện khi chốt P1).