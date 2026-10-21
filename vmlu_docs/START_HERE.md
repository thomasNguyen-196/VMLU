# 🧭 Start Here: VMLU Research & Thesis Vault Navigation Hub

> **Chào mừng bạn đến với Obsidian Vault của Dự án Nghiên cứu VMLU & Harness Engineering!**  
> Tệp này đóng vai trò là **Bản đồ Điều hướng Trung tâm (Map of Content — MOC)** giúp bạn nhanh chóng tra cứu, theo dõi tiến độ và nắm bắt toàn bộ mạng lưới tri thức trong vault.

---

## 🎯 Luận Điểm Trung Tâm Của Vault (Core Research Thesis)

Nghiên cứu tập trung bóc tách mối quan hệ tay ba giữa:
1. **Năng lực nội tại của Mô hình (Model Capability)**: Khảo sát các điểm mù ngôn ngữ, tính toán nhẩm và suy luận logic của các dòng mô hình (Qwen 3.5, Gemini 3.8 Flash).
2. **Kỹ thuật Hệ thống Tác tử (Harness Engineering)**: Đo lường mức độ nâng tầm điểm số khi cung cấp công cụ ngoại vi (Python REPL, CSP solver, Tra cứu văn bản luật).
3. **Độ khó & Sức cản của Benchmark (Benchmark Resistance & Saturation)**: Kiểm chứng xem các benchmark tiếng Việt hiện nay (VMLU, V-Bench) còn đủ sức cản phân loại hay đã bão hòa khi gặp agentic harness.

---

## 🚀 Lộ Trình Đọc Nhanh Đề Xuất (Recommended Reading Path)

Nếu cần nắm bắt nhanh toàn bộ mạch nghiên cứu từ đầu đến thời điểm hiện tại:

```
[1. PROPOSAL] ──► [2. findings] ──► [3. MEETING_W3] ──► [4. ISO_THROUGHPUT] ──► [5. UPPER_BOUND] ──► [6. MEETING_W5] ──► [7. CONTEXT_INSIGHTS]
  (Đề cương)      (Literature)       (Bối cảnh họp 1)     (Phương pháp kinh tế)    (Sổ cái thực đo)     (Họp tuần 5)        (Nhiệm vụ Quang Tùng)
```

1. [[PROPOSAL]] — Đề cương nghiên cứu xuất phát điểm về các mô hình ngôn ngữ nhỏ (≤8B) cho tiếng Việt.
2. [[findings]] — Tổng quan nghiên cứu liên quan (Literature Review) & khoảng trống học thuật về Adaptive-RAG và xung đột trí nhớ tham số.
3. [[MEETING_NOTE_WEEK_3_DETAILED_CONTEXT]] — **Biên bản cuộc họp Tuần 3 (22/09/2026)**: Tỉ lệ đòn bẩy token, nghi vấn bão hòa benchmark của Thầy và phân công ban đầu.
4. [[RESEARCH_ISO_THROUGHPUT_COST_ANALYSIS]] — **Khung phương pháp luận Iso-Throughput**: Phân tích băng thông, TPS và mô hình chi phí đối soát.
5. [[GITHUB_ISSUE_UPPER_BOUND_18_BATCHES]] — Báo cáo thực nghiệm 18 batches (1.389 câu, sổ cái tài nguyên thực đo 59,07M net tokens trong `all_res/antigravity_resource_ledger/`).
6. [[01_thesis_and_proposals/MEETING_NOTE_WEEK_5_06_10_2026|MEETING_NOTE_WEEK_5_06_10_2026.md]] — **Biên bản cuộc họp Tuần 5 (06/10/2026)**: Kết quả Qwen 3.5 9B vs. MIMO V2.5 Flash trên `oh-my-pi` (Qwen tụt điểm khi dùng harness), và **phân công nhiệm vụ trọng tâm cho Quang Tùng**.
7. [[SESSION_HANDOFF_RESOURCE_BENCHMARK]] — **Kim chỉ nam phiên làm việc của Nguyễn Quang Tùng**: Tập trung 100% vào phân tích ngữ cảnh dataset & trích xuất insight tài nguyên, không re-run hay code harness mới.

---

## 📂 Danh Mục Chuyên Đề Chi Tiết (Thematic Clusters)

### 🏛️ I. Đề Cương, Họp Định Kỳ & Lộ Trình Luận Văn (`01_thesis_and_proposals/`)
* [[01_thesis_and_proposals/MEETING_NOTE_WEEK_5_06_10_2026|MEETING_NOTE_WEEK_5_06_10_2026.md]] — *(Mới nhất)* Cuộc họp 06/10/2026: Hiện tượng sụt giảm của Qwen trên harness và giao nhiệm vụ khai thác insight ngữ cảnh cho Quang Tùng.
* [[MEETING_NOTE_WEEK_3_DETAILED_CONTEXT]] — Bối cảnh mở rộng cuộc họp tuần 3 với Thầy hướng dẫn: Đào sâu tỉ lệ đòn bẩy token, kiểm chứng bão hòa benchmark.
* [[SESSION_HANDOFF_RESOURCE_BENCHMARK]] — Tài liệu bàn giao & steering chuyên biệt cho phiên làm việc của Nguyễn Quang Tùng.
* [[01_thesis_and_proposals/harness-evolution-thesis-plan|harness-evolution-thesis-plan.md]] — Kế hoạch tổng thể luận văn tốt nghiệp: Thiết kế vòng lặp tiến hóa harness tự trị (Self-Evolving Evaluation Harness) quanh mô hình cố định (RQ1 – RQ4).
* [[01_thesis_and_proposals/PROPOSAL|PROPOSAL.md]] — Đề cương nghiên cứu Small Open-Weight LLMs (≤8B) cho tiếng Việt theo 3 chế độ (Regime A/B/C).
* [[01_thesis_and_proposals/findings|findings.md]] — Tổng hợp tài liệu tham khảo: Adaptive-RAG, Parametric vs. Non-parametric Memory conflict.
* [[01_thesis_and_proposals/ISSUE_3_EXPLAINED|ISSUE_3_EXPLAINED.md]] — Ghi chú diễn giải chi tiết về Issue #3 (Harness tự chấm điểm, phân tầng 400 câu Vi-SQuAD / Vi-DROP).
* [[01_thesis_and_proposals/todo_mo_rong_bench_notion|todo_mo_rong_bench_notion.md]] — Danh sách công việc mở rộng benchmark theo các lỗ hổng đo lường đã nhận diện.

---

### ⚡ II. Phương Pháp Luận Hệ Thống, Hạ Tầng & Chi Phí (`03_systems_and_infra/`)
* [[RESEARCH_ISO_THROUGHPUT_COST_ANALYSIS]] — *(Root)* **Tài liệu phương pháp luận trọng tâm**:
  * Giải mã trần băng thông 320 GB/s của NVIDIA T4 khiến TPS kịch trần ở mức $\approx 15\text{ TPS}$.
  * Yêu cầu phần cứng HBM ($\ge 2.000\text{ GB/s}$) của A100/H100 để đạt cùng tốc độ với Gemini Flash.
  * Phân tích hiện tượng *Single-Stream Memory Penalty* của máy chủ chuyên dụng (\$5.95 / 1M output) so với Frontier API (\$3.75 Standard / \$1.875 Flex) và Serverless Open-Weight API (\$0.28 / 1M).
* [[03_systems_and_infra/measurement_card|measurement_card.md]] — Thẻ điều kiện đo lường chuẩn hóa bắt buộc trích dẫn (MC-1, MC-2... gắn liền với hash sha256).
* [[NAKED_BASELINE_TROUGHS_SSOT]] — **Bảng đóng băng duy nhất (Frozen Table)** tổng hợp toàn bộ 19 vùng trũng của mô hình chạy trần (`Qwen3-8-27B Q4_K_M`) trích xuất trực tiếp từ 2 file gốc **`report_vmlu.pdf`** (03/09/2026) và **`report_vbench.pdf`** (04/09/2026).
* [[03_systems_and_infra/RESEARCH_KAGGLE_AI_QUOTA|RESEARCH_KAGGLE_AI_QUOTA.md]] — Hướng dẫn tối ưu hóa hạn ngạch tài nguyên GPU Kaggle (30h/tuần) khi chạy đánh giá benchmark quy mô lớn.

---

### 🏆 III. Chiến Dịch Nghiên Cứu Mức Trần Năng Lực (Upper Bound Ceiling — `02_upper_bound_campaign/`)
* [[02_upper_bound_campaign/GITHUB_ISSUE_UPPER_BOUND_18_BATCHES|GITHUB_ISSUE_UPPER_BOUND_18_BATCHES.md]] — Báo cáo nghiệm thu hoàn tất 100% kế hoạch dài hạn (18 batches, 1.389 câu hỏi, 69 file CSV tại `all_res/antigravity_gemini/`). *(Lưu ý: Các con số cột Naked Baseline trong bảng đối sánh phải quy chiếu theo SSOT `report_vmlu.pdf` và `report_vbench.pdf`).*
* [[02_upper_bound_campaign/GITHUB_ISSUE_UPPER_BOUND_12_BATCHES|GITHUB_ISSUE_UPPER_BOUND_12_BATCHES.md]] — Báo cáo sơ kết cột mốc 12 batches đầu tiên (920 câu hỏi).
* [[02_upper_bound_campaign/LONG_TERM_PLAN_STATISTICAL_ROLLOUT|LONG_TERM_PLAN_STATISTICAL_ROLLOUT.md]] — Cơ sở toán học xác định cỡ mẫu phân tầng và tiêu chí dừng thống kê ($E \le \pm 5\%$).
* [[02_upper_bound_campaign/SESSION_HANDOFF_UPPER_BOUND|SESSION_HANDOFF_UPPER_BOUND.md]] — Tài liệu bàn giao phiên làm việc: Hướng dẫn lệnh kiểm chứng 1 giây và các nguyên tắc vận hành sub-agent.
* [[02_upper_bound_campaign/PROBE_UPPER_BOUND_PILOT_1|PROBE_UPPER_BOUND_PILOT_1.md]] — Thử nghiệm thăm dò pilot đợt 1 về tiềm năng vượt ngưỡng của mô hình kèm công cụ.
* [[02_upper_bound_campaign/PROPOSAL_FULL_EVAL_QWEN3_8_27B|PROPOSAL_FULL_EVAL_QWEN3_8_27B.md]] — Kế hoạch thực nghiệm full-scale benchmark Qwen 27B để tạo bản sao lưu dữ liệu an toàn (Data Safe Fallback).

---

### 🔬 IV. Ghi Chú Kỹ Thuật Chuyên Sâu (`agents/`)
Thư mục con `agents/` chứa các tài liệu phân tích kỹ thuật chi tiết:
* [[agents/domain|agents/domain.md]] — Định nghĩa và phân loại chi tiết các môn học VMLU & domain V-Bench.
* [[agents/em-char-f1|agents/em-char-f1.md]] — Công thức toán học và quy tắc chuẩn hóa văn bản tiếng Việt khi chấm Exact Match (EM) và Character F1.
* [[agents/vidrop-cluster-breakdown|agents/vidrop-cluster-breakdown.md]] — Phân tích chi tiết 3 cụm lỗi số học của Vi-DROP: Phép cộng/trừ 2 thành phần (23 ca), so sánh (22 ca) và đếm (21 ca).
* [[agents/score-reading-eval|agents/score-reading-eval.md]] — Quy trình và hướng dẫn sử dụng công cụ chấm điểm đọc hiểu độc lập.
* [[agents/reading-results-table|agents/reading-results-table.md]] — Bảng tổng hợp kết quả đọc hiểu chính thức.
* [[agents/measurement-gaps|agents/measurement-gaps.md]] — Phân tích các khoảng trống đo lường còn tồn đọng.
* [[agents/triage-labels|agents/triage-labels.md]] — Hệ thống nhãn phân loại lỗi và tiến độ.
* [[agents/issue-tracker|agents/issue-tracker.md]] — Bảng theo dõi các issue kỹ thuật.

---

## 🏷️ Hệ Thống Tags Gợi Ý Cho Obsidian

Khi ghi chú thêm hoặc tạo liên kết mới trong Obsidian, bạn có thể tận dụng các thẻ tag sau để lọc đồ thị (Graph Filter):
* `#thesis` — Các tài liệu liên quan trực tiếp đến đề cương và nội dung luận văn.
* `#meeting` — Các biên bản thảo luận và trao đổi với Thầy hướng dẫn.
* `#methodology` — Các phương pháp luận đo đạc, chuẩn hóa và kiểm chứng khoa học.
* `#systems-economics` — Phân tích chi phí tính toán, phần cứng, latency, TPS và kinh tế học AI.
* `#upper-bound` — Dữ liệu và phân tích liên quan đến chiến dịch Upper Bound Ceiling 100%.
* `#benchmark` — Các vấn đề xoay quanh VMLU, V-Bench và bộ dữ liệu tiếng Việt.

---

*Vault được khởi tạo và đồng bộ tự động. Chúc bạn có những trải nghiệm nghiên cứu và quản lý tri thức thật mượt mà trên Obsidian!*
