# Kế Hoạch Tái Lập & Triển Khai Khung Tác Tử Đo Lường Tài Nguyên Thực Tế
(Harness Replication & Empirical Rollout Plan)

- **Trạng thái**: Chờ duyệt (Pending User Review & Compact)
- **Tài liệu lưu trữ**: `vmlu_docs/03_systems_and_infra/HARNESS_REPLICATION_AND_ROLLOUT_PLAN.md`
- **Mục tiêu**: Tái lập mức trần năng lực (Upper Bound Ceiling) của Issue #10 thông qua Harness tự động độc lập, đo đạc chuẩn chỉ 100% bộ 3 trục tài nguyên thực tế (*Tokens, Latency, Tool Calls*).

---

## 1. Rationale: Tại Sao Bắt Buộc Phải Code Một Khung Harness Tự Động Độc Lập?

Trong chiến dịch **Issue #10**, việc khảo sát mức trần năng lực 100% được thực hiện qua giao diện tương tác bán thủ công của Antigravity (điều phối qua sub-agents `invoke_subagent`). Mặc dù kết quả về độ chính xác và bài giải đạt 100%, phương thức này tồn tại hai hạn chế phương pháp luận:

1. **Thiếu vắng dữ liệu tài nguyên phân giải cao (High-Resolution Resource Metadata)**:
   - Giao diện chat và gói AI Pro chỉ hiển thị thanh phần trăm quota theo tuần, không trả về metadata per-request.
   - Do đó, số liệu token của Issue #10 phải dựa trên mô hình ước tính lý thuyết ($\sim 80\text{M} - 100\text{M}$ tokens với tỷ lệ đòn bẩy $1 : 500$).
2. **Yêu cầu về tính khách quan và khả năng tái lập (Reproducibility)**:
   - Để phục vụ luận văn và phản biện của Thầy hướng dẫn, toàn bộ quá trình đo đạc phải được **tự động hóa bằng mã nguồn có thể kiểm chứng (auditable code)**.
   - Khi có một script runner độc lập (Agentic Harness Runner), bất kỳ ai cũng có thể chạy lại lệnh và thu được kết quả giống hệt.

> 🎯 **Giải pháp**: Xây dựng script Python `code_benchmark/run_agentic_harness.py` đóng vai trò là "Vòng lặp tác tử độc lập", kết nối qua gateway `commandcode.ai` để trích xuất trực tiếp `usage` metadata chính chủ từ Google.

---

## 2. Phạm Vi Dữ Liệu Đối Soát (Target Scope)

Harness sẽ chạy trên đúng tập mẫu đã được nghiệm thu trong **Issue #10**:

| Nhóm bài toán / Domain | Nguồn dữ liệu | Số lượng (N) | Công cụ trọng tâm (Primary Tool) |
|---|---|:---:|---|
| **V-Bench Mathematics** | `v_bench/public-test.jsonl` | 125 câu | `python_repl` (Đại số, giải tích, modulo, ma trận) |
| **V-Bench Logics** | `v_bench/public-test.jsonl` | 225 câu | `csp_solver` / `python_repl` (Mô hình hóa ràng buộc) |
| **V-Bench Physics** | `v_bench/public-test.jsonl` | 147 câu | `python_repl` (Mô phỏng động học & nhiệt học) |
| **V-Bench Agentic (FC)** | `v_bench/public-test.jsonl` | 110 câu | `validate_schema` (Kiểm định cú pháp & enum JSON) |
| **VMLU Vi-DROP (Reading)** | `data/eval_set_manifest.csv` | 200 câu | `python_repl` (Tính toán số học & đếm thực thể) |
| **VMLU Vi-SQuAD (Reading)**| `data/eval_set_manifest.csv` | 100 câu | Suy luận tham số / Trích xuất nguyên văn |
| **VMLU Valid Other & Legal**| `vmlu_mqa_v1.5/` | 162 câu | Đối soát căn cứ luật & nghiệp vụ chuyên môn |
| **V-Bench Laws & Dialect** | `v_bench/public-test.jsonl` | 200 câu | Căn cứ luật định & ngữ cảnh phương ngữ 3 miền |
| **Các môn khoa học khác** | CS, Chemistry, Medicine | 120 câu | Thuật toán, bảo toàn mol, cơ chế dược lý |
| **TỔNG CỘNG** | **18 Batches** | **1.389 câu** | **Quét sạch 100% phạm vi Issue #10** |

---

## 3. Lộ Trình Triển Khai 2 Giai Đoạn (Two-Phase Rollout Plan)

Nhằm tối ưu hóa thời gian thực thi và kiểm soát quota an toàn, dự án áp dụng chiến lược 2 giai đoạn:

```
┌────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 1: PILOT STRATIFIED VALIDATION (80 CÂU)      │
│  - 20 câu Math (test REPL)                             │
│  - 20 câu Logic (test CSP)                             │
│  - 20 câu Vi-DROP (test Đọc hiểu số học)               │
│  - 20 câu Agentic FC (test Schema Validator)           │
│                                                        │
│ 🎯 Mục tiêu: Kiểm chứng 3 trục đo lường & Tỷ lệ Cache  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼ (Khi Pilot đạt 100% tiêu chí)
┌────────────────────────────────────────────────────────┐
│ GIAI ĐOẠN 2: FULL REPLICATION SWEEP (1.389 CÂU)        │
│  - Chạy quét sạch 18 Batches dưới chế độ chạy nền      │
│  - Checkpoint tự động sau mỗi batch                    │
│  - Xuất 69 CSV Ledgers có đầy đủ 3 trục tài nguyên     │
│                                                        │
│ 🎯 Mục tiêu: Bộ số liệu Ground-Truth chính thức cho LV  │
└────────────────────────────────────────────────────────┘
```

### 🔹 Giai đoạn 1: Pilot Stratified Validation (80 câu — Thời gian dự kiến: 10–15 phút)
* **Quy mô**: Trích xuất ngẫu nhiên có phân tầng (Stratified Sampling) đúng 80 câu đại diện cho 4 bài toán chịu tải nặng nhất.
* **Tiêu chí nghiệm thu Giai đoạn 1**:
  1. **Độ chính xác (Accuracy)**: Phải duy trì được tỷ lệ đúng cao tương đương Issue #10 ($\ge 95\%$).
  2. **Thu thập tài nguyên đầy đủ 100%**: 0 ô trống ở các cột `fresh_input`, `cached_tokens`, `reasoning_tokens`, `output_tokens`, `wall_time_s`.
  3. **Xác nhận tỷ lệ Cache Hit**: Đo lường thực tế phần trăm context được cache từ Turn 2 trở đi trong các câu hỏi đa lượt.
  4. **Tính toán chi phí trung bình per-item**: Đưa ra con số $T_{\text{avg}}$ (tokens/câu) và $t_{\text{avg}}$ (giây/câu) để dự phóng chính xác thời gian và quota cho Giai đoạn 2.

### 🔹 Giai đoạn 2: Full Replication Sweep (1.389 câu — Thời gian dự kiến: 1.5 – 2.5 giờ)
* **Cơ chế vận hành**:
  * Chạy nền thông qua tiến trình `run_command` (hoặc background process).
  * Checkpoint độc lập theo từng batch (tự động khôi phục nếu đứt kết nối mạng).
  * Cơ chế Retry tự động (tối đa 3 lần với Exponential Backoff khi gặp mã lỗi 429 hoặc 500).
* **Đầu ra**: 
  * 69 file CSV lưu trữ tại `all_res/ground_truth_gemini_harness/`.
  * Bộ bảng tổng kết tích hợp vào dashboard so sánh trực tiếp với Open-Weight Model + Harness.

---

## 4. Kiến Trúc Kỹ Thuật Của Harness Runner (`code_benchmark/run_agentic_harness.py`)

Harness được thiết kế theo mô hình **ReAct Tool-Calling Agent Loop**:

```python
# Sơ đồ chu trình xử lý mỗi câu hỏi:
#
#  User Question + System Rules + Tool Declarations
#                         │
#                         ▼
#         ┌───► [Gọi Model Gemini 3.8 Flash]
#         │               │
#         │               ├─► Model trả về Final Answer ──► Trích xuất đáp án & Ghi Ledger ──► KẾT THÚC
#         │               │
#         │               └─► Model yêu cầu Tool Call
#         │                       │
#         │                       ▼
#         │             [Thực thi Tool cục bộ]
#         │             - Python REPL sandbox
#         │             - Schema / Enum checker
#         │                       │
#         │                       ▼
#         └──────────── [Nối Tool Result vào Messages]
#                       (Kích hoạt Cache Hit từ lượt này)
```

### Bộ công cụ cốt lõi khai báo qua OpenAI Tool Calling Schema:
1. `execute_python(code: str) -> str`:
   - Thực thi đoạn mã Python trong sub-process có giới hạn thời gian (timeout 10s).
   - Bắt toàn bộ `stdout` và `stderr` để trả về cho mô hình.
   - Thư viện hỗ trợ sẵn: `math`, `sympy`, `scipy`, `numpy`, `re`, `itertools`.
2. `validate_vbench_schema(function_call_json: str, expected_schema: dict) -> str`:
   - Đối soát đối số gọi hàm với schema gốc của câu hỏi V-Bench.
   - Báo lỗi ngay nếu thiếu required parameter, sai enum hoặc thừa tham số bịa đặt.

### Cấu trúc Schema File Ledger CSV Kết Quả:
Mỗi dòng kết quả sẽ ghi nhận 14 trường dữ liệu hoàn chỉnh:
```csv
domain,item_id,question,gold_answer,predicted_answer,is_correct,turns,wall_time_s,fresh_input_tokens,cached_tokens,reasoning_tokens,output_tokens,total_tokens,tool_invocations_json
```

---

## 5. Danh Mục Kiểm Tra Của Người Dùng (User Verification Checklist)

Trước khi tiến hành chạy Bước 1, người dùng có thể đối chiếu các điểm sau:
- [x] Đã xác định rõ lý do phải code Harness (tự động hóa, tính tái lập, trích xuất 3 trục tài nguyên).
- [x] Đã giới hạn đúng phạm vi 1.389 câu của Issue #10.
- [x] Đã phê duyệt phương án chạy thử Pilot 80 câu trước khi càn quét diện rộng.
- [x] Đã xác lập xong cơ chế lưu trữ độc lập để đối sánh song song với Issue #10 và Open-weight.
