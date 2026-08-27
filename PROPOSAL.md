# Nghiên cứu: Đánh giá Năng lực & Hiệu quả Triển khai của các Mô hình Ngôn ngữ Nhỏ (≤8B) cho Tiếng Việt
**Title**: *Small Open-Weight Language Models for Vietnamese: A Capability–Efficiency Benchmark*

---

## 1. Đặt vấn đề & Câu hỏi nghiên cứu (Research Question)

Thay vì chỉ xây dựng một bảng xếp hạng (leaderboard) thông thường xem mô hình nào đạt điểm cao nhất, nghiên cứu này tập trung vào bài toán đánh giá toàn diện về tính khả thi thực tế và sự đánh đổi giữa **Chất lượng (Quality)** và **Hiệu quả triển khai (Efficiency)** của các mô hình mã nguồn mở cỡ nhỏ (≤8B) trên tiếng Việt.

### Câu hỏi nghiên cứu trọng tâm (Core RQ)
> **"How effective are small open-weight LLMs (≤8B) for Vietnamese language understanding, reasoning, cultural knowledge, and agentic tasks under realistic compute constraints?"**

### Đóng góp cốt lõi
$$\boxed{\text{Vietnam-specific capability} + \text{Dialect robustness} + \text{Tokenization efficiency} + \text{Inference cost}}$$

Nghiên cứu này cũng đóng vai trò là **Stage 0 (Baseline & Gap Analysis)**: xác lập rõ ràng các điểm nghẽn và hạn chế của các mô hình nhỏ hiện tại trước khi tiến hành tối ưu hóa tokenizer hoặc tiếp tục pretraining mô hình tiếng Việt chuyên biệt.

---

## 2. Danh mục Mô hình Đánh giá (Model Matrix)

### 2.1. Phân nhóm mô hình

| Nhóm | Mô hình | Mục tiêu & Lý do lựa chọn |
| :--- | :--- | :--- |
| **Qwen scaling** | Qwen3 (0.6B, 1.7B, 4B, 8B) | Nghiên cứu scaling có kiểm soát cùng họ mô hình; hỗ trợ đa ngôn ngữ (100+ ngôn ngữ). |
| **Google** | Gemma-3 (1B, 4B) | Đại diện đa ngôn ngữ mạnh; kiểm chứng bước nhảy năng lực giữa 1B và 4B. |
| **Meta** | Llama-3.2 (1B, 3B) | Baseline phổ biến cho các mô hình kích thước nhỏ / edge. |
| **Microsoft** | Phi-4-mini (3.8B) | Baseline suy luận logic mạnh (200K vocab), không chính thức hỗ trợ tiếng Việt -> Đo lường cross-lingual transfer. |
| **Mistral** | Ministral-3 (3B, 8B) | Mô hình thế hệ mới tối ưu cho môi trường edge. |
| **Vietnamese / SEA Adapted** | BloomVN (0.5B, 8B), SeaLLM-7B, Vistral-7B | Nhóm đối chứng được tinh chỉnh / pretrained chuyên sâu cho tiếng Việt & Đông Nam Á. |

### 2.2. Tập thử nghiệm tối thiểu (Minimal 10-Model Experiment)
Tối ưu hóa để có thể chạy kiểm nghiệm toàn diện trên cấu hình phần cứng khả thi (1 GPU phân khúc RTX 5090 / A100):
1. **Qwen3-0.6B**
2. **Qwen3-1.7B**
3. **Qwen3-4B**
4. **Qwen3-8B**
5. **Gemma-3-1B**
6. **Gemma-3-4B**
7. **Llama-3.2-1B**
8. **Llama-3.2-3B**
9. **Phi-4-mini-3.8B**
10. **BloomVN-8B**

---

## 3. Các Tầng Benchmark (Evaluation Layers)

| Tầng | Benchmark | Mục đích đo lường |
| :--- | :--- | :--- |
| **Core** | **VMLU** | Năng lực hiểu biết kiến thức đa ngành (58 môn học) & suy luận logic tiếng Việt. |
| **Vietnam-specific** | **V-Bench** | Văn hóa bản địa, y tế, kiến thức đặc thù Việt Nam, an toàn & tác vụ agentic (function calling). |
| **Linguistic Robustness** | **VialectBench** | Độ bền vững của mô hình trước các phương ngữ, biến thể vùng miền tiếng Việt. |
| **General NLU** | **ViGLUE** | Khả năng đọc hiểu và xử lý ngôn ngữ tự nhiên tổng quát. |
| **Intrinsic (Tùy chọn)** | **ViWiki / PPL** | Perplexity trên văn bản tiếng Việt chuẩn (đo lường mô hình hóa ngôn ngữ gốc). |

---

## 4. Chi tiết 4 Câu hỏi Nghiên cứu (Research Questions)

### RQ1: Năng lực mở rộng theo kích thước (Capability Scaling)
$$\text{Vietnamese capability} = f(\text{model size})$$
- Kiểm chứng trên chuỗi kích thước Qwen3: $0.6\text{B} \rightarrow 1.7\text{B} \rightarrow 4\text{B} \rightarrow 8\text{B}$.
- Xác định mức độ tăng trưởng có đơn điệu (monotonic) hay không và điểm bắt đầu xuất hiện quy luật lợi suất giảm dần (diminishing returns).

### RQ2: Ảnh hưởng của kiến trúc trong cùng phân khúc 3–4B (Architecture / Family Effect)
So sánh có kiểm soát số lượng tham số (parameter count):
$$\text{Qwen3-4B} \quad \text{vs} \quad \text{Gemma-3-4B} \quad \text{vs} \quad \text{Phi-4-mini-3.8B} \quad \text{vs} \quad \text{Llama-3.2-3B} \quad \text{vs} \quad \text{Ministral-3-3B}$$

### RQ3: Mô hình đa ngôn ngữ tổng quát vs Mô hình chuyên biệt tiếng Việt
$$\text{Generic Multilingual (Qwen / Gemma / Llama)} \quad \longleftrightarrow \quad \text{Vietnamese/SEA Adapted (BloomVN / SeaLLM / Vistral)}$$
- Làm rõ liệu các mô hình nền tảng đa ngôn ngữ thế hệ mới có vượt qua hoặc thu hẹp khoảng cách với các mô hình được tiếp tục tiền huấn luyện riêng cho tiếng Việt hay không.

### RQ4: Chất lượng so với Chi phí Triển khai (Quality vs. Deployment Cost)
Đánh giá song song giữa Chất lượng $Q$ và Chi phí $C$:
$$Q = \{\text{VMLU, V-Bench, VialectBench, ViGLUE}\}$$
$$C = \{\text{Parameters, Peak VRAM, TTFT (Time to First Token), Tokens/sec, Latency, Output Tokens}\}$$

Xây dựng đường biên Pareto (Pareto Frontier) minh họa mối quan hệ giữa **Vietnamese Accuracy** và **GPU Memory / Latency**.

---

## 5. Đánh giá Hiệu quả Tokenizer (Tokenizer Efficiency)

Đo lường chi phí biểu diễn ngôn ngữ tiếng Việt của từng tokenizer:
- **Tỉ lệ Token / Từ**: $F = \frac{N_{\text{tokens}}}{N_{\text{words}}}$
- Số lượng tokens trên 1,000 ký tự tiếng Việt.
- Số ký tự trung bình trên mỗi token (characters / token).
- Tỉ lệ nén tiếng Việt so với tiếng Anh (Vietnamese vs English tokenization ratio).

---

## 6. Chế độ Đánh giá (Evaluation Regimes)

1. **Regime A — Năng lực Thuần (Capability Baseline)**:
   - Precision: BF16 / FP16.
   - Zero-shot / Few-shot chuẩn hóa theo benchmark.
   - Sử dụng Official Chat Template của mô hình.
   - Không lượng tử hóa (no quantization).

2. **Regime B — Triển khai Thực tế / Edge Deployment**:
   - Lượng tử hóa: INT4 / AWQ / GGUF.
   - Batch size = 1.
   - Cùng một serving engine (vLLM / SGLang / Ollama) và thống nhất cấu hình phần cứng.

3. **Regime C — Giới hạn Ngân sách Suy luận (Reasoning Budget)**:
   - Đối với các mô hình suy luận (thinking models như Qwen3):
     - So sánh `non-thinking` vs `thinking`.
     - Kiểm soát ngân sách reasoning token cố định: **128 / 512 / 2048 tokens**.

---

## 7. Kế hoạch Thực hiện (Action Plan)

1. **Giai đoạn 1**: Chuẩn hóa pipeline benchmark (VMLU, V-Bench, VialectBench) và công cụ đo lường tokenization / inference profiling.
2. **Giai đoạn 2**: Chạy đánh giá Regime A & Tokenizer analysis trên 10 mô hình cốt lõi.
3. **Giai đoạn 3**: Chạy đánh giá Regime B (Edge/INT4) và Regime C (Reasoning budget).
4. **Giai đoạn 4**: Tổng hợp dữ liệu, vẽ Pareto frontiers, phân tích kết quả và tổng kết tài liệu báo cáo nghiên cứu.
