# Tổng hợp Nghiên cứu Liên quan & Khoảng trống Học thuật (Literature Review & Gaps)

Tài liệu phục vụ xây dựng luận điểm và cơ sở lý thuyết (Chương 2) cho đề tài: **Adaptive Epistemic Routing & Grounded Legal Retrieval**.

---

## 1. Các nghiên cứu nền tảng liên quan

### 1.1. Adaptive-RAG (Jeong et al., NAACL 2024)
- **Tên bài báo:** *Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity*
- **Đóng góp:** Phân loại câu hỏi đầu vào theo 3 mức độ phức tạp:
  1. *Non-retrieval:* Câu hỏi đơn giản, mô hình tự trả lời từ tri thức nội tại.
  2. *Single-step retrieval:* Câu hỏi cần tra cứu dữ liệu ngoài qua 1 bước RAG thông thường.
  3. *Multi-step retrieval:* Câu hỏi phức tạp cần lập kế hoạch và tra cứu lặp nhiều bước.
- **Hạn chế đối với bài toán hiện tại:** 
  - Chỉ giải quyết bài toán nhị phân "có gọi RAG hay không" trên các mô hình truyền thống (chỉ có generation thuần).
  - Chưa xét đến cơ chế **Thinking Mode (Native Reasoning / Chain-of-Thought)** của các kiến trúc thế hệ mới (Qwen 2.5/3, o1). Không tính đến bài toán đánh đổi token giữa suy luận nội sinh và truy xuất ngoại sinh.

### 1.2. Parametric vs. Non-parametric Knowledge Conflict (Mallen et al., ACL 2023; Neeman et al., 2022)
- **Tài liệu tham khảo:** 
  - Mallen et al. (2023): *When Not to Trust Language Models: Investigating Effectiveness of Parametric and Non-parametric Memories*.
  - Neeman et al. (2022): *Disentangling Parametric and Non-parametric Knowledge*.
- **Đóng góp:**
  - Chứng minh LLM ghi nhớ và xử lý rất tốt các thực thể phổ biến (Head entities / phổ quát), nhưng rỗng tri thức và dễ bịa đặt ở các thực thể ngách/đuôi dài (Tail entities).
  - Khuyến nghị: Chỉ can thiệp truy xuất ngoại sinh khi gặp các tri thức ngoài vùng trí nhớ tham số vững để tránh lãng phí tài nguyên và tránh xung đột tri thức.
- **Áp dụng vào đề tài:**
  - Phân định rõ: Tri thức phổ quát/khoa học tự nhiên (STEM, Địa lý) là *Parametric Head*, trong khi văn bản quy phạm pháp luật bản địa (VBPL, mức phạt, điều khoản) đóng vai trò *Arbitrary Statutory Knowledge* — không thể tự sinh hay "suy luận" nếu chưa nạp.

### 1.3. Self-RAG (Asai et al., ICLR 2024)
- **Tên bài báo:** *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*
- **Đóng góp:** Huấn luyện mô hình tự đánh giá độ không chắc chắn (Uncertainty) và tự sinh các special token như `[Retrieve]`, `[IsRel]`, `[IsSup]` để chủ động gọi công cụ tra cứu khi cần.
- **Hạn chế đối với mô hình quy mô vừa lượng tử hóa:**
  - **Uncertainty Miscalibration:** Các mô hình tầm trung (như 27B Q4_K_M) có khả năng tự lượng giá (self-critique) rất kém đối với văn bản pháp luật. Mô hình thường thể hiện sự "tự tin sai" (*Confident Hallucination*), tự bịa số Điều luật rất trôi chảy mà không kích hoạt cờ cảnh báo không chắc chắn.
  - Việc yêu cầu mô hình tự suy ngẫm sinh token làm tăng đáng kể độ trễ và chi phí suy luận (Inference Overhead).

---

## 2. Khoảng trống học thuật & Đóng góp của Đề tài (Research Gaps & Novelty)

| Phương pháp | Cơ chế định tuyến | Đối tượng quyết định | Xử lý Reasoning Mode | Kiểm soát Chi phí (Pareto) |
|---|---|---|---|---|
| **Adaptive-RAG** | Classifier ngoài | RAG đơn bước vs đa bước | ❌ Bỏ qua | ⚠️ Chỉ đo độ trễ RAG |
| **Self-RAG** | Model tự sinh token `[Retrieve]` | Model tự quyết định | ❌ Bỏ qua | ❌ Tốn token tự phản tư |
| **Model Routing (Factory/Martian)** | Router phân loại task | Chọn Model nhỏ vs Model to | ❌ Bỏ qua | ⚠️ Giảm chi phí API model |
| **AER-Legal (Đề tài)** | **Epistemic Router chuyên biệt** | **Fast Path vs Deep Path vs Evidence Path** | ✅ **Bật/tắt Thinking Mode & ép trích dẫn căn cứ luật** | ✅ **Tối ưu hóa đa mục tiêu (Accuracy vs Average Tokens)** |

### 3 Luận điểm bảo vệ cốt lõi (Case Arguments):
1. **Phản biện hiện tượng Overthinking trên tri thức quy chuẩn:** Bật Thinking Mode trên câu hỏi Luật không làm tăng độ chính xác mà chỉ tạo ra *Overthinking Hallucination* và đốt token vô ích.
2. **Khắc phục Uncertainty Miscalibration:** Sử dụng Epistemic Router nhẹ độc lập phân loại bản chất tri thức từ câu hỏi thay vì để mô hình 27B tự đánh giá bản thân (tránh bẫy của Self-RAG).
3. **Cân bằng Pareto thực dụng:** Cắt giảm token ở nhóm câu hỏi mô hình đã làm chủ (Zero-shot Fast Path) để bù đắp chi phí ngữ cảnh cho nhóm pháp luật (Evidence Path).
