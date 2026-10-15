# TÀI LIỆU BÀN GIAO NGỮ CẢNH & ĐỊNH HƯỚNG PHIÊN LÀM VIỆC (QUANG TÙNG)
(Context Handoff & Steering Guide — Quang Tùng's Focus)

- **Cập nhật lần cuối**: 12/10/2026 (sau cuộc họp ngày 06/10/2026)
- **Kho lưu trữ (Repository)**: `thomasNguyen-196/VMLU`
- **Nhánh làm việc (Branch)**: `research/upper-bound-ceiling`
- **Chủ sở hữu phiên làm việc**: **Nguyễn Quang Tùng** (Luận văn tốt nghiệp)
- **Độc giả mục tiêu**: Mọi AI Agent tiếp quản phiên làm việc cùng Nguyễn Quang Tùng.

---

## ⚠️ CHỈ DẪN QUAN TRỌNG ĐỂ KHÔNG BỊ "LÚ" ĐỊNH HƯỚNG (CRITICAL STEERING)

1. **Tuyệt đối KHÔNG viết script chạy lại (re-run / replication harness) hay code runner mới**:
   - Dữ liệu tài nguyên thực tế (**Ground Truth**) của Gemini-3.8-flash trên nền Antigravity **ĐÃ ĐẦY ĐỦ 100%** trong thư mục [`all_res/antigravity_resource_ledger/`](file:///Users/nguyentung/VMLU/all_res/antigravity_resource_ledger/).
   - 4.461 lượt gọi LLM, 1.389 câu hỏi, 18 batches, 14 domain rollup đã được trích xuất trực tiếp và xác thực từ telemetry local SQLite (`tools/antigravity_ledger/extract.py`).
2. **Tuyệt đối KHÔNG nhầm sang phần việc của bạn Nguyễn Thanh Tùng**:
   - Thanh Tùng phụ trách: Chạy benchmark đa mô hình tiếng Việt (MIMO V2.5 Flash, Qwen 3.5 9B 65K...) trên nhiều ngữ cảnh.
3. **ĐÂY LÀ PHẦN VIỆC DUY NHẤT CỦA BẠN (NGUYỄN QUANG TÙNG)**:
   - **Phân tích các ngữ cảnh dataset và quan sát dữ liệu tiêu thụ tài nguyên (từ Ground Truth Ledger) để trích xuất các INSIGHTS khoa học cho Luận văn tốt nghiệp.**

---

## 1. Bối Cảnh Từ Cuộc Họp Mới Nhất (06/10/2026)

Xem chi tiết tại: [`vmlu_docs/01_thesis_and_proposals/MEETING_NOTE_WEEK_5_06_10_2026.md`](file:///Users/nguyentung/VMLU/vmlu_docs/01_thesis_and_proposals/MEETING_NOTE_WEEK_5_06_10_2026.md).

* **Phát hiện thực nghiệm với Harness (`oh-my-pi`)**:
  - MIMO V2.5 Flash vượt trội hơn Qwen 3.5 9B trên mọi benchmark tiếng Việt.
  - Khi cắm thêm harness: MIMO cải thiện kết quả khả quan hơn, nhưng **Qwen 3.5 9B lại có kết quả tệ hơn ban đầu** (bị "thuế nhận thức" / cognitive overload bởi tool loop và prompt dài).
* **Kết luận của Thầy hướng dẫn**:
  - Nhóm đã có dữ liệu đo đạc tài nguyên (token + thời gian) của Gemini trên Antigravity.
  - Nhưng hiện tại **CHƯA CÓ INSIGHT trong các ngữ cảnh dataset khác nhau**.
  - Yêu cầu Quang Tùng: Đào sâu vào kho dữ liệu này để rút ra các quy luật, sự đánh đổi và kết luận học thuật.

---

## 2. Nguồn Chân Lý Duy Nhất (Single Source of Truth — SSOT)

Để tránh mọi sai lệch hoặc tam sao thất bản từ các ghi chú nháp `.md`, mọi phân tích bắt buộc tuân thủ 2 nguồn SSOT đóng băng sau:

### 2.1. SSOT cho Mô hình Chạy Trần (Naked Baseline — `Qwen3-8-27B Q4_K_M`)
> 📌 **Bảng tổng hợp đóng băng (1 Table duy nhất)**: Xem trực tiếp tại **[`vmlu_docs/NAKED_BASELINE_TROUGHS_SSOT.md`](file:///Users/nguyentung/VMLU/vmlu_docs/NAKED_BASELINE_TROUGHS_SSOT.md)**.

Hai tệp báo cáo PDF gốc ở thư mục root là **SSOT tuyệt đối** cho điểm số và vùng trũng của mô hình trần (Zero-shot, No-CoT, No-Tool, $T=0$, seed 42):
1. **[`report_vmlu.pdf`](file:///Users/nguyentung/VMLU/report_vmlu.pdf) (Báo cáo ngày 03/09/2026)**:
   - **VMLU-MQA (1.047 câu có đáp án tham chiếu; loại trừ 20 câu Luật Hành chính thiếu đáp án gốc)**:
     - Tổng thể: **73,35%** (768/1.047) | Kiểm định chéo tập `valid` (744 câu): **72,58%**.
     - Theo nhóm ngành: **STEM 79,37%** (304/383) · **KH Xã hội 78,26%** (144/184) · **Nhân văn 68,21%** (221/324) · **Khác (`Other`) 63,46%** (99/156 — *thấp nhất*).
     - **Vùng trũng cấp môn học**: **Luật Hành chính 30%**, **Giáo dục mầm non 30%**, **Nhóm Công chức 33–50%**, **Toán tiểu học 40%**.
   - **VMLU Reading 400 câu tiền đăng ký (`max_tokens=48`, open-book)**:
     - Tổng tỉ lệ chấp nhận: **80,25%** (321/400) — khi chấm EM/char-F1 trên gold chuẩn đạt **80,25% EM / 86,55% char-F1**.
     - **Vi-SQuAD (200 câu trích mẫu)**: **97,5%** (195/200 chấp nhận, chỉ bác 5 câu).
     - **Vi-DROP (200 câu suy luận số học — VÙNG TRŨNG)**: **63,0%** (126/200 chấp nhận, **bác bỏ 74 câu**). Lỗi hội tụ ở 3 cụm số học: **Cộng/trừ 2 thành phần (23 câu)**, **So sánh (22 câu)**, và **Đếm (21 câu)**.

2. **[`report_vbench.pdf`](file:///Users/nguyentung/VMLU/report_vbench.pdf) (Báo cáo ngày 04/09/2026 — V-Bench public test `v2026.03.28`, `minimal` prompt)**:
   - **Tổng thể (5.141 câu chấm điểm / 13 domains)**: Macro-average = **44,97%** | Micro-accuracy = **45,46%** (2.337/5.141).
   - **Bảng điểm đầy đủ 13 domains (từ thấp nhất đến cao nhất)**:
     1. 🔴 `mathematics` (MC): **19,20%** (24/125) — *Thấp hơn đoán mò ngẫu nhiên 25% do thiếu tính toán trung gian (no-CoT)*.
     2. 🔴 `logics` (MC): **24,00%** (54/225) — *Ngang mức đoán mò ngẫu nhiên*.
     3. 🔴 `physics` (MC): **29,93%** (44/147) — *Thấp thứ 3 toàn giải*.
     4. 🟠 `medicine` (MC): **38,78%** (190/490)
     5. 🟠 `agentic` (Function Calling): **39,10%** (391/1.000) — *985/1.000 câu hợp lệ cú pháp JSON nhưng **60,3% (594/985) chọn sai hàm hoặc sai tham số**; 15 câu bị bác thuộc 6 lớp lỗi A–F (tràn 512 token [4], lệch chính tả/gạch dưới `enum` [5], lặp đuôi hash tên hàm [2], thiếu/bịa tham số [2], lỗi schema đề bài [1], từ chối gọi hàm [1])*.
     6. 🟠 `chemistry` (MC): **40,12%** (134/334)
     7. 🟠 `literature` (MC): **40,77%** (245/601)
     8. 🟡 `culture` (MC): **47,47%** (103/217)
     9. 🟡 `psychology` (MC): **49,75%** (397/798)
     10. 🟢 `dialect` (MC): **59,96%** (337/562) — *(Lưu ý: thuộc nhóm khá 60–70%, không phải đáy!)*
     11. 🟢 `laws` (MC): **60,73%** (116/191) — *(Lưu ý: đứng Top 3 V-Bench, không phải đáy!)*
     12. 🟢 `philosophy` (MC): **64,64%** (170/263)
     13. 🟢 `computer_science` (MC): **70,21%** (132/188)

### 2.2. SSOT cho Dữ liệu Tài nguyên Thực đo (`Gemini 3.8 Flash High + Antigravity 2.0`)
Toàn bộ dữ liệu nằm tại [`all_res/antigravity_resource_ledger/`](file:///Users/nguyentung/VMLU/all_res/antigravity_resource_ledger/):
- `llm_calls.csv`: 4.461 dòng — ghi nhận từng lượt gọi với đầy đủ:
  - `fresh_input_tokens`, `cached_tokens`, `output_tokens`, `thinking_tokens`
  - `wall_start`, `wall_span`, Domain, session id, persona
- `domains.csv`: Thống kê tổng hợp 14 domain/ngữ cảnh (13 domain giải bài = 1.389 câu + 1 nhóm `orchestration`).
- `batches.csv`: Thống kê theo 40 batch cụ thể.
- `answer_tokens.csv`: Đo chính xác tokenizer của từng đáp án (1.389 câu).
- `sessions.csv`: 78 phiên làm việc được lọc sạch.

---

## 3. Các Trục Insight Trọng Tâm Cần Phân Tích & Báo Cáo

Báo cáo cần trả lời 4 nhóm câu hỏi lớn cho luận văn:

### Trục 1: Dấu chân tài nguyên theo ngữ cảnh bài toán (Contextual Footprint)
- **Nhóm tính toán / suy luận đa bước (Math, Logic, Physics, Agentic FC)**:
  - Vì sao tiêu tốn **38K – 52,5K net tokens/câu**?
  - Tỷ lệ thinking tokens (Gemini 3.8 Flash High suy luận ngầm) chiếm bao nhiêu %?
  - Số turn trung bình và số lần gọi tool (Python REPL, CSP solver, schema verifier) là bao nhiêu?
- **Nhóm đọc hiểu (Vi-DROP số học vs. Vi-SQuAD trích xuất)**:
  - So sánh đối chiếu trực tiếp: Tại sao Vi-DROP tốn nhiều lượt thử sai số học hơn, còn Vi-SQuAD chủ yếu là trích xuất ngữ cảnh?
- **Nhóm tri thức luật & chuyên môn (Laws, VMLU Legal)**:
  - Dấu chân context lớn (đọc văn bản luật) nhưng tỷ lệ cache hit cực cao (>90%).
- **Nhóm ngôn ngữ / phương ngữ (Dialect, VMLU Other)**:
  - Tiêu thụ ít nhất (**~11K net tokens/câu**), phản ánh việc chủ yếu dựa vào trí nhớ tham số (parametric memory).

### Trục 2: Cơ chế Cache Hit & Hiệu quả kinh tế theo ngữ cảnh
- Cache hit toàn cục đạt **86,46%**, nhưng biến thiên mạnh:
  - Laws: **90,90%** cache hit
  - Physics: **90,14%** cache hit
  - Dialect: chỉ **77,11%** cache hit
  - VMLU Other: chỉ **74,52%** cache hit
- *Insight*: Dạng bài nào có tính lặp ngữ cảnh cao thì cache hit cứu vãn chi phí; dạng bài câu hỏi ngắn, tản mạn thì cache hit giảm mạnh.

### Trục 3: Chi phí phụ trội của Điều phối (Orchestration Overhead)
- **17.372.247 tokens (29,4% tổng net tokens)** là chi phí Orchestration (điều phối tiến độ, đọc format, tổng hợp report), KHÔNG trực tiếp giải câu hỏi.
- *Insight kết nối với phát hiện họp 06/10*: Giải thích vì sao mô hình mã nguồn mở như Qwen 3.5 9B khi gánh harness `oh-my-pi` lại bị tụt điểm — việc phải "cõng" 30% overhead điều phối làm tràn bộ nhớ làm việc (working memory) của mô hình nhỏ.

### Trục 4: Tỷ lệ đòn bẩy thực tế (True Leverage Ratio)
- Phân tích sự đối lập giữa:
  - Đòn bẩy trên raw response: **~1 : 30** (tổng) và **~1 : 21** (solving-only).
  - Đòn bẩy trên distilled answer (đáp án 1 ký tự): **1 : 5.375**.
  - Ý nghĩa đối với thiết kế benchmark: Không gian đáp án đóng làm bùng nổ tỷ lệ đòn bẩy, giá trị thật sự nằm ở quá trình kiểm chứng (verification).

---

## 4. Kế Hoạch Thực Hiện Cụ Thể (Action Plan)

1. **Khai thác dữ liệu (Data Mining Script)**:
   - Viết script Python (ví dụ: `tools/antigravity_ledger/analyze_context_insights.py`) đọc các file CSV trong `all_res/antigravity_resource_ledger/` để tính toán ma trận tương quan, phân phối phân vị (p50, p90, p99), tỷ trọng thinking tokens và overhead per-context.
2. **Biên soạn Báo Cáo Insight Khoa Học**:
   - Xuất tài liệu: `vmlu_docs/03_systems_and_infra/DATASET_CONTEXT_RESOURCE_INSIGHTS.md`.
   - Có đầy đủ bảng biểu so sánh, biểu đồ Markdown/ASCII, nhận xét học thuật và trích dẫn chuẩn chỉ phục vụ chương thực nghiệm của Luận văn.
