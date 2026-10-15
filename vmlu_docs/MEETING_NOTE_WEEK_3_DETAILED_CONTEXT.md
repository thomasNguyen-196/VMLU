# Biên Bản Chi Tiết & Ngữ Cảnh Mở Rộng Cuộc Họp Tuần 3 (Elaborated Meeting Context — Week 3)

- **Ngày họp**: 22/09/2026
- **Thành phần tham dự**: Thầy hướng dẫn, Quang Tùng, Thanh Tùng
- **Chủ đề chính**: Đánh giá thực nghiệm mô hình tiếng Việt (VMLU, V-Bench), phân tích mức trần năng lực (Upper Bound Ceiling) và định hướng nghiên cứu cho Luận văn tốt nghiệp.
- **Tài liệu đối chiếu gốc**: [`vmlu_docs/GITHUB_ISSUE_UPPER_BOUND_18_BATCHES.md`](file:///Users/nguyentung/VMLU/vmlu_docs/GITHUB_ISSUE_UPPER_BOUND_18_BATCHES.md), [`report_vmlu.pdf`](file:///Users/nguyentung/VMLU/report_vmlu.pdf), [`report_vbench.pdf`](file:///Users/nguyentung/VMLU/report_vbench.pdf).

---

## 1. Bối cảnh Thực nghiệm Trước Cuộc Họp

Trước khi bước vào buổi họp tuần 3, nhóm nghiên cứu đã tích lũy hai nguồn dữ liệu thực nghiệm đối lập:

1. **Hiệu năng chạy trần (Naked Baseline) của Open-Weight Model (`Qwen3-8-27B Q4_K_M`)**:
   > 📌 **SSOT (Single Source of Truth)**: Toàn bộ số liệu và nhận định của mô hình chạy trần lấy chuẩn tuyệt đối từ 2 báo cáo chính thức [`report_vmlu.pdf`](file:///Users/nguyentung/VMLU/report_vmlu.pdf) (03/09/2026) và [`report_vbench.pdf`](file:///Users/nguyentung/VMLU/report_vbench.pdf) (04/09/2026).
   - **VMLU-MQA** (`report_vmlu.pdf`): Đạt **73,35%** trên 1.047 câu có gold (768/1.047; kiểm định chéo tập `valid` 744 câu đạt **72,58%**). Theo nhóm ngành: **STEM 79,37%** (304/383), **KHXH 78,26%** (144/184), **Nhân văn 68,21%** (221/324), và thấp nhất là **Khác (`Other`) 63,46%** (99/156). Các môn chạm đáy vùng trũng: **Luật Hành chính 30%**, **Giáo dục mầm non 30%**, **Nhóm Công chức 33–50%**, **Toán tiểu học 40%**.
   - **VMLU Reading 400 câu tiền đăng ký** (`report_vmlu.pdf`): Tổng tỉ lệ chấp nhận đạt **80,25%** (321/400), trong đó **Vi-SQuAD** (trích mẫu văn bản) đạt **97,5%** (195/200, chỉ bác 5 câu), còn **Vi-DROP** (suy luận số học) rơi xuống vùng trũng **63,0%** (126/200, bác bỏ **74 câu**). Lỗi hội tụ ở 3 dạng suy luận số học: **cộng/trừ 2 thành phần (23 câu)**, **so sánh (22 câu)** và **đếm (21 câu)**.
   - **V-Bench Public Test** (`report_vbench.pdf`): Đạt **44,97%** macro trên 13 domain (micro **45,46%** — 2.337/5.141 câu). Điểm số phân tầng rõ theo loại tri thức:
     - *Nhóm ngôn ngữ / tri thức khai báo (Declarative / Language-heavy)* đạt **60–70%**: `computer_science` **70,21%** (132/188), `philosophy` **64,64%** (170/263), `laws` **60,73%** (116/191), `dialect` **59,96%** (337/562).
     - *Nhóm trung bình thấp (<50%)*: `psychology` **49,75%** (397/798), `culture` **47,47%** (103/217), `literature` **40,77%** (245/601), `chemistry` **40,12%** (134/334), `medicine` **38,78%** (190/490).
     - *Nhóm chạm đáy tính toán & suy luận chuỗi (Bottom — Computation / Chained Inference)*: `physics` **29,93%** (44/147), `logics` **24,00%** (54/225), và thấp nhất là `mathematics` **19,20%** (24/125 — thấp hơn cả đoán mò ngẫu nhiên 25%).
     - *Track Agentic Function Calling*: Đạt **39,10%** (391/1.000). Trong đó **985/1.000 câu hợp lệ cú pháp JSON**, nhưng **60,3% (594/985) chọn sai hàm hoặc điền sai tham số** (chứng tỏ điểm nghẽn nằm ở quyết định ngữ nghĩa chứ không phải cú pháp); 15 câu bị loại chia làm 6 lớp lỗi A–F.

> ⚠️ **Lưu ý Kỹ thuật về Cấu hình LLM & Phân định với Issue #8**:  
> Toàn bộ các chỉ số của Naked Baseline nêu trên đều được đo ở điều kiện **Pure Zero-Shot Naked: Hoàn toàn KHÔNG Chain-of-Thought (No-CoT), KHÔNG Few-shot, KHÔNG Tool/Harness**, với ngân sách token tối giản (4 token cho trắc nghiệm, 48 token cho đọc hiểu, 512 token cho V-Bench).  
> **Cần phân định rạch ròi**: Các biến thể mở rộng `--strategy cot` (CoT prompt, 512 tokens) và `--strategy fewshot` thuộc phạm vi của **Issue #8** / `code_benchmark/test_generative.py` sau này trên tập quy mô lớn (full split). Con số Naked Baseline đem ra làm mốc đối sánh với Upper Bound Ceiling 100% trong cuộc họp là **phiên bản chạy trần 0-shot không CoT nguyên bản**.

2. **Mức trần năng lực (Upper Bound Ceiling) của Gemini-3.8-flash-high + Antigravity 2.0 Harness**:
   - Hoàn tất **18 batches** với **1.389 câu hỏi** khảo sát trên toàn bộ các domain khó nhất của V-Bench và VMLU.
   - Khi được trang bị hệ thống công cụ ngoại vi (Python REPL tính toán, CSP solver giải logic, Tra cứu căn cứ pháp lý, Schema validator kiểm soát cú pháp), Gemini đạt **100.0% độ chính xác đối soát** trên toàn bộ các tập có nhãn đối chứng.

---

## 2. Diễn Biến Thảo Luận Chi Tiết Trong Cuộc Họp

### 2.1. Câu hỏi Gợi Mở Chiến Lược của Thầy Hướng Dẫn
Sau khi nghe nhóm trình bày báo cáo về điểm yếu của Qwen và con số 100% của Gemini + Antigravity, Thầy đã đặt ra câu hỏi định hướng cốt lõi:

> *"Bây giờ chúng ta đã biết rõ Qwen yếu ở những điểm nào (tính toán số học, suy luận logic phức tạp, tra cứu văn bản luật), và chúng ta cũng thấy Gemini kết hợp với agentic harness có thể lấp kín hoàn toàn những khoảng trống đó để đạt 100%.*  
> *Vậy hướng đi tiếp theo của chúng ta là gì? Từ sự chênh lệch này, chúng ta có thể rút ra kết luận khoa học gì sâu sắc hơn cho luận văn ngoài việc đơn thuần ghi nhận điểm số?"*

### 2.2. Câu Trả Lời & Đóng Góp Sắc Bén của Quang Tùng
Tại thời điểm đó, Quang Tùng đã đưa ra luận điểm dựa trên phát hiện định lượng trong quá trình thực nghiệm Issue #10:

* **Bản chất của con số 100%**: Điểm số tuyệt đối không tự nhiên sinh ra từ một lượt prompt thông thường. Để đổi lấy 100% độ chính xác, hệ thống phải kích hoạt vòng lặp tác tử đa lượt (multi-turn agentic exploration loop), tự sinh mã Python để giải tích, mô hình hóa ràng buộc CSP và kiểm chứng phản hồi.
* **Tỷ lệ chuyển đổi / Tỷ lệ đòn bẩy token (Leverage Ratio ~ 1 : 500)**:
  * Lượng token đầu ra tinh gọn (distilled answer tokens) ghi vào file benchmark cuối cùng chỉ trung bình **~141 tokens/câu** (~195,6K tokens cho 1.389 câu).
  * Nhưng chi phí token thực tế tiêu tốn trong không gian tìm kiếm tác tử (prompt context, tool schemas, stdout/logs thực thi code, tự sửa lỗi) lên tới **~80M – 100M tokens**.
  * Nghĩa là: **Để sinh ra đúng 1 token đáp án chuẩn xác tuyệt đối (Gold token), hệ thống phải "đốt" tới ~500 token suy luận và vận hành công cụ trong hậu trường.**

### 2.3. Đánh Giá của Thầy & Gợi Ý Mở Rộng Hướng Nghiên Cứu
Thầy đánh giá rất cao góc nhìn này. Thầy nhận định đây là **một lát cắt học thuật đắt giá (novel research angle)**: *Định lượng cái giá tính toán để đổi lấy sự chính xác của tác tử (The Compute Cost of Agentic Precision)*.

Thầy yêu cầu **Quang Tùng** tập trung phát triển sâu và rộng hơn nữa theo trục này:
* Không chỉ dừng lại ở việc đếm tổng số token, mà phải mổ xẻ cấu trúc chi phí (token breakdown), độ trễ (completion time), cơ cấu tool set và chi phí tài chính (USD) thực tế.
* Xây dựng cơ sở lý thuyết so sánh giữa các phương thức suy luận khác nhau.

### 2.4. Vấn Đề Thứ Hai: Giả Thuyết Bão Hòa Benchmark (The Benchmark Saturation Hypothesis)
Ngay sau đó, Thầy đưa ra một nghi vấn phản biện khoa học mà cả hai bạn sinh viên chưa từng nghĩ tới:

> *"Nếu Gemini + Antigravity có thể dễ dàng quét sạch 100% trên cả VMLU và V-Bench, liệu có phải các benchmark tiếng Việt hiện nay (đã có tuổi đời 1–2 năm) đang dần bị bão hòa, quá yếu và không còn đủ 'sức cản' (resistance) để phân loại các hệ thống AI hiện đại nữa hay không?"*

Để kiểm chứng giả thuyết này một cách khách quan và nghiêm cẩn, Thầy giao nhiệm vụ cho **Thanh Tùng**:
* Đem chính bộ harness tác tử này (hoặc phiên bản tương đương) áp dụng cho mô hình mã nguồn mở kích thước trung bình (**Qwen 3.5 / Qwen 27B**).
* Mục tiêu: Đánh giá xem harness có thể nâng tầm (*advance*) năng lực AI ở cả mô hình thương mại đóng (Gemini) lẫn mô hình mã nguồn mở mở (Qwen) hay không.

---

## 3. Bản Đồ Kế Hoạch Nghiên Cứu Tiếp Theo (Detailed Action Roadmap)

Hai bài toán được giao cho Quang Tùng và Thanh Tùng thực chất là **hai mặt của cùng một thể thống nhất**, cùng trả lời cho câu hỏi lớn của đề tài: *Năng lực giải quyết vấn đề đến từ Mô hình nền (Model), từ Hệ thống công cụ (Harness), hay do Bài toán (Benchmark) chưa đủ độ khó?*

```
                               CÂU HỎI LỚN CỦA THẦY
           "Benchmark tiếng Việt đã bão hòa hay do Harness quá mạnh?"
                                     │
         ┌───────────────────────────┴───────────────────────────┐
         ▼                                                       ▼
   [NHÁNH QUANG TÙNG]                                      [NHÁNH THANH TÙNG]
Khảo sát Chi phí & Hiệu năng Harness                   Kiểm chứng trên Open-weight Model
(Gemini Flash High + Antigravity)                          (Qwen 3.5 + Harness)
         │                                                       │
         ├─ Token Amplification Factor                           ├─ Qwen + Tool có đạt 100%?
         ├─ Cost & Latency per Accuracy Gain                     ├─ Xác định điểm nghẽn Agentic
         └─ Tool Efficiency & Overhead                           └─ Phân định: Model vs Benchmark
```

---

### Phân Nhánh 1: Nhiệm Vụ Của Quang Tùng
**Mục tiêu cốt lõi**: Tiến hành nghiên cứu / khảo sát thực nghiệm toàn diện (*conduct an empirical survey / study*) trên dữ liệu của `Gemini-3.8-flash-high` khi vận hành trong Antigravity Harness. Trọng tâm là bóc tách và định lượng hóa dữ liệu để trả lời câu hỏi về chi phí và hiệu năng của harness trên benchmark tiếng Việt, phục vụ mục tiêu đánh giá khoa học (không sa vào xây dựng giải pháp tối ưu kỹ thuật ở giai đoạn này).

1. **Token Amplification Factor (Hệ số khuếch đại Token)**:
   - Không phải câu nào cũng tốn 500 token. Có câu chỉ tốn $1 : 1$ (suy luận trực tiếp không cần tool), nhưng có câu toán/logic hoặc đa bước (Vi-DROP, Logic) tốn tới $1 : 1.500$ hoặc $1 : 2.000$ qua nhiều lượt gọi Python REPL/CSP.
   - Phân rã hệ số khuếch đại $R = \frac{\text{Exploration Tokens}}{\text{Final Answer Tokens}}$ theo từng **Domain** (Toán, Lý, Logic, Luật, Đọc hiểu) và từng **Tool** (Code execution vs CSP vs Evidence retrieval).
   - Đo đạc tỷ lệ khuếch đại thực tế trên 18 batches để vẽ nên bức tranh phân phối chi phí token chân thực giữa các dạng bài.

2. **Cost & Latency per Accuracy Gain (Biên chi phí để đổi điểm số theo Khung Iso-Throughput)**:
   - Áp dụng khung phương pháp luận **Iso-Throughput** (chi tiết và trích dẫn chuẩn mực xem tại [`vmlu_docs/RESEARCH_ISO_THROUGHPUT_COST_ANALYSIS.md`](file:///Users/nguyentung/VMLU/vmlu_docs/RESEARCH_ISO_THROUGHPUT_COST_ANALYSIS.md)) để giải quyết triệt để sự bất đối xứng phần cứng (2x T4 15 TPS vs Google TPU ~300 TPS).
   - Chuyển hóa số token ra thời gian trễ (**Completion Time / Latency per question**) và chi phí tài chính thực tế (**USD / 1.000 câu hỏi**) theo biểu giá chuẩn đã kiểm chứng của `gemini-3.8-flash` (\$3.75 Standard / \$1.875 Batch-Flex trên 1M output tokens).
   - Đối sánh kinh tế sòng phẳng ở cùng đẳng cấp thông lượng: Chi phí đơn luồng của mô hình tự host trên GPU H100 ($\approx \$5.95\text{ / 1M output tokens}$) so với API thương mại của Gemini 3.8 Flash ($\approx \$1.875 - \$3.75$) và Serverless API trên DeepInfra ($\approx \$0.28\text{ / 1M output tokens}$).
   - Xác lập đường cong đánh đổi thực nghiệm giữa Chi phí (Compute/Time/USD) và Độ chính xác (Accuracy Gain): Đo đạc mức chi phí bùng nổ theo hàm mũ (*exponential*) khi muốn nâng từ $70\%$ lên $85\%$ và từ $85\%$ lên $100\%$.

3. **Tool Efficiency & Overhead (Độ hữu dụng và chi phí phụ trội của từng công cụ)**:
   - Đánh giá tỷ lệ "lãng phí" và hữu dụng trong tổng lượng compute:
     - Bao nhiêu token là dành cho system instruction/schema cố định (*context overhead*)?
     - Bao nhiêu token là cho việc thử sai, chạy lại code, parse lỗi (*trial-and-error overhead*)?
     - Bao nhiêu token thực sự biến thành reasoning hữu ích đi thẳng vào kết quả cuối cùng?
   - Thống kê tần suất và hiệu quả trên từng loại công cụ (532 lượt Python REPL, 225 lượt CSP Solver, ~190 lượt tra cứu luật, 110 lượt Schema verifier).

---

### Phân Nhánh 2: Nhiệm Vụ Của Thanh Tùng
**Mục tiêu**: Tích hợp harness cho mô hình open-weight (Qwen 3.5 / Qwen 27B) để đối chiếu trực tiếp với Gemini, làm sáng tỏ nghi vấn về độ khó của benchmark.

1. **Hai Kịch Bản Khoa Học Có Thể Xảy Ra**:
   - **Kịch bản 1: Benchmark thực sự bão hòa (Saturation)**:
     - *Hiện tượng*: Khi được cấp Python REPL và công cụ tương tự, Qwen cũng nhảy vọt từ 40–70% lên sát 95–100%.
     - *Ý nghĩa học thuật*: Chứng minh các câu hỏi VMLU/V-Bench không đủ sức cản; bài toán tưởng chừng khó đối với LLM thực ra chỉ là do hạn chế về tính toán nhẩm (mental arithmetic). Khi có "giấy nháp" (code), benchmark bị giải mã hoàn toàn.
   - **Kịch bản 2: Năng lực mô hình nền vẫn là nút thắt cốt tử (Model Bottleneck)**:
     - *Hiện tượng*: Dù được cấp tool, Qwen vẫn không đạt được điểm số cao vì gặp các lỗi agentic đặc trưng: không nhận diện được khi nào cần gọi tool, viết code giải thuật sai, hallucinate tham số hoặc không biết diễn giải kết quả từ stdout của Python.
     - *Ý nghĩa học thuật*: Bác bỏ giả thuyết benchmark quá yếu; khẳng định 100% của Gemini là sự cộng hưởng giữa **Harness mạnh** và **Mô hình nền có khả năng reasoning bậc cao**.

---

## 4. Định Hướng Bài Báo & Luận Văn Tốt Nghiệp

Sự kết hợp giữa hai nhánh việc của Quang Tùng và Thanh Tùng sẽ nâng tầm đề tài từ một bài báo cáo thử nghiệm thông thường thành một **công trình nghiên cứu có tính lý luận sâu sắc**:

1. **Định đề 1 (Decomposition)**: Bóc tách rạch ròi bao nhiêu phần trăm điểm số benchmark đến từ *Năng lực nội tại của Mô hình (Model Capability)*, bao nhiêu phần trăm được "vay mượn" từ *Kỹ thuật Hệ thống (Harness Engineering)*.
2. **Định đề 2 (Economics of AI Agents)**: Đưa ra bức tranh định lượng rõ ràng đầu tiên trên dữ liệu tiếng Việt về cái giá phải trả (Token, Latency, USD) để đạt được độ chính xác tuyệt đối trong môi trường tác tử.
3. **Định đề 3 (Benchmark Auditing)**: Đánh giá độc lập về độ bền vững và sức cản thực tế của các bộ benchmark tiếng Việt hiện hành trong kỷ nguyên Agentic AI.

---

## 5. Phụ Lục: Hướng Mở Rộng Tiềm Năng Trong Tương Lai (Future Potential Exploration)

* **Adaptive Epistemic Routing (AER)**:  
  *Ghi chú định hướng tương lai*: Nếu kết quả khảo sát định lượng ở trên chỉ ra rằng chi phí suy luận bùng nổ ở các câu hỏi khó trong khi các câu hỏi dễ chỉ cần bộ nhớ tham số (parametric memory), một hướng phát triển ứng dụng tiềm năng sau khi hoàn tất công trình khảo sát benchmark này là thiết kế cơ chế định tuyến thông minh (AER) để cân bằng biên hiệu quả Pareto giữa độ chính xác và chi phí.  
  *Lưu ý phương pháp luận*: Trọng tâm hàng đầu hiện nay của dự án VMLU là **thực hiện khảo sát / nghiên cứu thực nghiệm (conduct a survey / study)** để kiểm chứng và đánh giá benchmark, không đặt mục tiêu xây dựng giải pháp tối ưu hóa kỹ thuật trong giai đoạn này.
