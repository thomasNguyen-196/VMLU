# Biên Bản Cuộc Họp Tuần 5 (06/10/2026) — Thực Nghiệm Harness & Phân Công Nhiệm Vụ Luận Văn

- **Thời gian họp**: 06/10/2026
- **Thành phần tham dự**: Thầy hướng dẫn, Nguyễn Quang Tùng, Nguyễn Thanh Tùng
- **Chủ đề chính**: Đánh giá kết quả thực nghiệm mô hình tiếng Việt với Harness (`oh-my-pi`), hiện trạng số liệu tài nguyên Gemini/Antigravity và phân công nhiệm vụ nghiên cứu tiếp theo cho Luận văn tốt nghiệp.
- **Tài liệu liên quan**:
  - [[MEETING_NOTE_WEEK_3_DETAILED_CONTEXT]] (Cuộc họp tuần 3)
  - [[vmlu_docs/02_upper_bound_campaign/GITHUB_ISSUE_UPPER_BOUND_18_BATCHES|GITHUB_ISSUE_UPPER_BOUND_18_BATCHES.md]] (Issue #10)
  - `all_res/antigravity_resource_ledger/` (Sổ cái tài nguyên thực đo)

---

## 1. Nội Dung Thảo Luận & Phát Hiện Thực Nghiệm Cốt Lõi

### 1.1. Thực nghiệm so sánh: Qwen 3.5 9B 65K vs. MIMO V2.5 Flash
Nhóm đã tiến hành đo đạc đối sánh giữa hai mô hình trên các benchmark tiếng Việt (VMLU, V-Bench) ở hai điều kiện: **Chạy trần (Naked)** và **Chạy kèm Harness (`oh-my-pi`)**.

* **Kết quả Baseline (Naked)**:
  - Ở mọi benchmark tiếng Việt được khảo sát, **MIMO V2.5 Flash** đều thể hiện kết quả vượt trội hơn so với **Qwen 3.5 9B 65K**.
* **Hiện tượng khi tích hợp Harness (`oh-my-pi`)**:
  - Khi được trang bị harness, cả hai mô hình đều thay đổi đáng kể tập đáp án sinh ra.
  - Tuy nhiên, xu hướng dịch chuyển hoàn toàn trái ngược:
    - **MIMO V2.5 Flash**: Kết quả **khả quan hơn ban đầu** (tận dụng được scaffolding/tool để nâng cao độ chính xác).
    - **Qwen 3.5 9B 65K**: Kết quả **tệ hơn ban đầu** (điểm số bị sụt giảm so với khi chạy trần không tool).

> 🎓 **Ý nghĩa Khoa học cho Luận văn**:
> Harness không phải chiếc đũa thần vạn năng đem lại hiệu ứng tích cực đồng đều cho mọi mô hình. Đối với mô hình kích thước nhỏ / open-weight như Qwen 3.5 9B, việc bị nhồi thêm system prompt phức tạp, tool schema và vòng lặp phản hồi tạo ra một **"khoản thuế nhận thức / gánh nặng phụ trội (cognitive tax / orchestration overhead)"** khiến mô hình bị lạc đề hoặc hallucinate cú pháp, dẫn tới suy giảm hiệu năng. Trong khi đó, các mô hình có khả năng tuân thủ chỉ dẫn (instruction-following) mạnh mẽ như MIMO mới hấp thụ được sức mạnh của harness.

---

### 1.2. Hiện trạng Dữ liệu Tài nguyên Gemini + Antigravity
* Nhóm đã khai thác thành công và sở hữu trọn vẹn bộ dữ liệu tài nguyên thực đo (**Ground Truth Ledger**) từ telemetry local của Antigravity (`all_res/antigravity_resource_ledger/`):
  - 4.461 lượt gọi LLM, 78 phiên làm việc thuộc 18 Batches chiến dịch Upper Bound Ceiling (Issue #10).
  - Đầy đủ 3 trục độc lập: **Tokens** (Fresh, Cached, Output, Thinking), **Wall-clock latency** và **Tool calls**.
* **Khoảng trống cần giải quyết ngay**:
  - Dữ liệu tài nguyên hiện mới dừng ở mức con số tổng thể và thống kê cơ bản theo domain.
  - **Chưa có phân tích chuyên sâu (insights) về hành vi tiêu thụ tài nguyên trong các ngữ cảnh dataset khác nhau** (Toán/Lý tính toán vs. Logic ràng buộc vs. Đọc hiểu trích xuất vs. Đọc hiểu số học vs. Tra cứu pháp lý vs. Ngữ cảnh phương ngữ).

---

## 2. Phân Công Nhiệm Vụ Tiếp Theo (Next Steps)

Thầy hướng dẫn đã chốt phân công hai nhánh việc độc lập nhưng bổ trợ cho nhau:

### 👤 Nhánh 1: Nguyễn Thanh Tùng
* **Nhiệm vụ**: Xây dựng **Bảng benchmark tiếng Việt với nhiều model dựa trên nhiều ngữ cảnh**.
* Khảo sát diện rộng trên các dòng mô hình khác nhau (kích thước, kiến trúc, nguồn gốc) dưới các điều kiện ngữ cảnh benchmark để đối chiếu năng lực nội tại.

### 👤 Nhánh 2: Nguyễn Quang Tùng (Trọng tâm phiên làm việc này)
* **Nhiệm vụ**: **Phân tích các ngữ cảnh dataset và quan sát dữ liệu tiêu thụ tài nguyên để cho ra được các INSIGHTS khoa học.**
* **Mục tiêu cụ thể**:
  1. **Bóc tách theo ngữ cảnh đề bài (Dataset Context Breakdown)**:
     - Đo lường và so sánh mức độ ngốn tài nguyên giữa các ngữ cảnh: *Computation-heavy (Math, Physics)* vs. *Constraint Satisfaction (Logics)* vs. *Reading Comprehension (Vi-DROP số học vs. Vi-SQuAD trích xuất)* vs. *Domain Knowledge / Statutory (Laws, Legal)* vs. *Linguistic/Dialect*.
  2. **Giải mã cơ cấu tài nguyên (Resource Anatomy)**:
     - Tỷ trọng Thinking tokens (Gemini Flash High dành ~58% output cho suy luận ngầm).
     - Hiệu suất Context Caching theo ngữ cảnh (tại sao Laws đạt cache hit 90,9% trong khi Dialect chỉ 77,1%?).
     - Mức độ phụ trội của điều phối (Orchestration Overhead chiếm tới 29,4% tổng token net).
  3. **Kết nối phát hiện thực nghiệm**:
     - Dùng các insight về chi phí điều phối và tải trọng prompt để lý giải hiện tượng tại sao Qwen 3.5 9B lại bị suy giảm điểm số khi dùng harness `oh-my-pi`.
  4. **Sản phẩm đầu ra**:
     - Báo cáo phân tích chuyên sâu: `vmlu_docs/03_systems_and_infra/DATASET_CONTEXT_RESOURCE_INSIGHTS.md`.
     - Script khai thác dữ liệu tự động phục vụ trích xuất bảng biểu / đồ thị cho luận văn.
