# BẢNG ĐÓNG BĂNG (FROZEN SSOT): TỔNG HỢP CÁC VÙNG TRŨNG CỦA MÔ HÌNH CHẠY TRẦN (`Qwen3-8-27B Q4_K_M`) TRÊN VMLU & V-BENCH

- **Trạng thái**: 🔒 **BYTE-FROZEN SINGLE SOURCE OF TRUTH (SSOT)**
- **Mô hình đánh giá**: `Qwen3-8-27B` (Lượng tử hóa `Q4_K_M`, chạy cục bộ qua OpenAI-compatible API)
- **Điều kiện đo đóng băng (`MC-1`, `MC-2`, `MC-3`)**: Pure Zero-Shot Naked — `temperature = 0`, `seed = 42`, **Không Chain-of-Thought (No-CoT)**, **Không Few-shot**, **Không Công cụ (No-Tool / No-Harness)**, prompt tối giản (`minimal` / `open-book`).
- **Nguồn trích xuất tuyệt đối (SSOT)**:
  1. [`report_vmlu.pdf`](file:///Users/nguyentung/VMLU/report_vmlu.pdf) — *Báo cáo sơ bộ kết quả thực nghiệm trên bộ dữ liệu VMLU* (Ngày 03/09/2026).
  2. [`report_vbench.pdf`](file:///Users/nguyentung/VMLU/report_vbench.pdf) — *Evaluation Report: Qwen3-8-27B (Q4_K_M) on V-Bench* (Ngày 04/09/2026).
  *(Bổ trợ phân rã chi tiết cụm Vi-DROP từ [`vidrop-cluster-breakdown.md`](file:///Users/nguyentung/VMLU/vmlu_docs/agents/vidrop-cluster-breakdown.md) & [`reading-results-table.md`](file:///Users/nguyentung/VMLU/vmlu_docs/agents/reading-results-table.md)).*

---

## 📊 Bảng Tổng Hợp Duy Nhất: Toàn Bộ Các Vùng Trũng Trên V-Bench & VMLU

| STT | Bộ Dataset & Phân hệ | Vùng trũng (Domain / Nhóm ngành / Môn / Cụm bài) | Dạng câu hỏi (MC hay Tự luận?) | Điểm số / Tỉ lệ đúng (Số câu đúng / Tổng) | Mốc đối chiếu (Overall / Ngẫu nhiên) | Nguyên nhân gốc rễ & Kiểu lỗi đặc trưng (Theo SSOT PDF) | Nguồn SSOT |
| :-: | :--- | :--- | :--- | :---: | :---: | :--- | :---: |
| **1** | **V-Bench**<br>*(Public Test)* | **`mathematics`**<br>*(Toán học — Đáy sâu #1 V-Bench)* | **MC**<br>*(Trắc nghiệm)* | **19,20%**<br>*(24 / 125 câu)* | **< 25,0%**<br>*(Thấp hơn đoán mò 4 lựa chọn)* | Lỗi hệ thống do không có bước tính toán trung gian (`no-CoT`, `max_tokens=4`): mô hình sinh câu trả lời rất tự tin nhưng sai (*confident but wrong answers*). | `report_vbench.pdf`<br>*(Table 1, p.2)* |
| **2** | **V-Bench**<br>*(Public Test)* | **`logics`**<br>*(Suy luận Logic — Đáy sâu #2 V-Bench)* | **MC**<br>*(Trắc nghiệm)* | **24,00%**<br>*(54 / 225 câu)* | **≈ 25,0%**<br>*(Ngang đoán mò ngẫu nhiên)* | Sụp đổ trước các bài toán suy luận chuỗi (*chained inference*), tiền đề ẩn và ràng buộc logic đa bước khi không có nháp hay bộ giải CSP. | `report_vbench.pdf`<br>*(Table 1, p.2)* |
| **3** | **V-Bench**<br>*(Public Test)* | **`physics`**<br>*(Vật lý — Đáy sâu #3 V-Bench)* | **MC**<br>*(Trắc nghiệm)* | **29,93%**<br>*(44 / 147 câu)* | Thấp hơn Macro V-Bench (`44,97%`) **-15,04%** | Đòi hỏi biến đổi công thức vật lý và tính toán số học qua nhiều bước trung gian; tính nhẩm trực tiếp gây sai số hàng loạt. | `report_vbench.pdf`<br>*(Table 1, p.2)* |
| **4** | **V-Bench**<br>*(Public Test)* | **`medicine`**<br>*(Y học & Dược lý — Đáy #4 V-Bench)* | **MC**<br>*(Trắc nghiệm)* | **38,78%**<br>*(190 / 490 câu)* | Thấp hơn Macro V-Bench (`44,97%`) **-6,19%** | Thiếu hụt tri thức chuyên sâu về chẩn đoán lâm sàng, bệnh học và dược lý bằng tiếng Việt. | `report_vbench.pdf`<br>*(Table 1, p.2)* |
| **5** | **V-Bench**<br>*(Agentic Track)* | **`agentic`**<br>*(Function Calling — Đáy #5 V-Bench)* | **Tự luận cấu trúc**<br>*(Sinh JSON `[{"fn":{args}}]`)* | **39,10%**<br>*(391 / 1.000 câu)*<br>*(39,7% trên 985 câu hợp lệ)* | **60,3% (594/985)** câu đúng cú pháp nhưng **sai ngữ nghĩa** | • **Nút thắt là Ngữ nghĩa, không phải Cú pháp**: 985/1.000 câu hợp lệ JSON nhưng **594 câu chọn sai hàm hoặc điền sai tham số**.<br>• **15 câu bị bác (Classes A–F)**: Tràn 512 token [4 câu]; lệch chính tả/gạch dưới `enum` [5 câu]; lặp đuôi hash tên hàm [2 câu]; thiếu/bịa tham số [2 câu]; lỗi schema đề bài [1 câu]; từ chối gọi hàm [1 câu]. | `report_vbench.pdf`<br>*(Table 1–2, p.1–3)* |
| **6** | **V-Bench**<br>*(Public Test)* | **`chemistry`**<br>*(Hóa học — Đáy #6 V-Bench)* | **MC**<br>*(Trắc nghiệm)* | **40,12%**<br>*(134 / 334 câu)* | Thấp hơn Macro V-Bench (`44,97%`) **-4,85%** | Sai số khi tính nhẩm các bài toán cân bằng phản ứng, bảo toàn mol và hóa học định lượng. | `report_vbench.pdf`<br>*(Table 1, p.2)* |
| **7** | **V-Bench**<br>*(Public Test)* | **`literature`**<br>*(Văn học — Đáy #7 V-Bench)* | **MC**<br>*(Trắc nghiệm)* | **40,77%**<br>*(245 / 601 câu)* | Thấp hơn Macro V-Bench (`44,97%`) **-4,20%** | Điểm mù về tác phẩm, tác giả, ngữ liệu và điển tích văn học Việt Nam trong tập pre-train đa ngữ. | `report_vbench.pdf`<br>*(Table 1, p.2)* |
| **8** | **V-Bench**<br>*(Public Test)* | **`culture`**<br>*(Văn hóa Việt Nam — Dưới TB)* | **MC**<br>*(Trắc nghiệm)* | **47,47%**<br>*(103 / 217 câu)* | Dưới ngưỡng **50,0%** | Hạn chế về tri thức văn hóa, phong tục, lịch sử và đời sống bản địa Việt Nam. | `report_vbench.pdf`<br>*(Table 1, p.2)* |
| **9** | **V-Bench**<br>*(Public Test)* | **`psychology`**<br>*(Tâm lý học — Dưới TB, quy mô lớn nhất)* | **MC**<br>*(Trắc nghiệm)* | **49,75%**<br>*(397 / 798 câu)* | Dưới ngưỡng **50,0%** *(Chiếm 798/5.141 câu)* | Domain có số lượng câu hỏi lớn nhất toàn bộ V-Bench, giữ điểm micro toàn cục xoay quanh mức ~45,46%. | `report_vbench.pdf`<br>*(Table 1, p.2)* |
| **10** | **VMLU-MQA**<br>*(Cấp Nhóm ngành)* | **Nhóm ngành `Khác` (`Other`)**<br>*(Đáy thấp nhất trong 4 nhóm ngành VMLU)* | **MC**<br>*(Trắc nghiệm)* | **63,46%**<br>*(99 / 156 câu)* | Thấp hơn STEM (`79,37%`) **-15,91%** · Overall `73,35%` | Hội tụ các môn nghiệp vụ chuyên ngành hẹp của Việt Nam (kế toán, thuế, công chức, sư phạm mầm non). | `report_vmlu.pdf`<br>*(Bảng 1, p.1)* |
| **11** | **VMLU-MQA**<br>*(Cấp Nhóm ngành)* | **Nhóm ngành `Nhân văn` (`Humanities`)**<br>*(Thấp thứ 2 trong 4 nhóm ngành VMLU)* | **MC**<br>*(Trắc nghiệm)* | **68,21%**<br>*(221 / 324 câu)* | Thấp hơn STEM (`79,37%`) **-11,16%** · Overall `73,35%` | Bị kéo xuống bởi các môn Luật thực định, Văn học và Lịch sử/Văn hóa đặc thù Việt Nam. | `report_vmlu.pdf`<br>*(Bảng 1, p.1)* |
| **12** | **VMLU-MQA**<br>*(Cấp Môn học)* | **Môn `Luật Hành chính`**<br>*(Đáy sâu nhất cấp môn học VMLU)* | **MC**<br>*(Trắc nghiệm)* | **30,00%**<br>*(Đã loại 20 câu thiếu gold gốc)* | Thấp hơn Overall VMLU (`73,35%`) **-43,35%** | Điểm mù nghiêm trọng về quy định pháp luật hành chính và thẩm quyền cơ quan nhà nước Việt Nam. | `report_vmlu.pdf`<br>*(Mục 2, p.1)* |
| **13** | **VMLU-MQA**<br>*(Cấp Môn học)* | **Môn `Giáo dục mầm non`**<br>*(Đáy sâu nhất cấp môn học VMLU)* | **MC**<br>*(Trắc nghiệm)* | **30,00%** | Thấp hơn Overall VMLU (`73,35%`) **-43,35%** | Hổng kiến thức chuyên môn hẹp về quy chuẩn chăm sóc, giáo dục trẻ mầm non tại Việt Nam. | `report_vmlu.pdf`<br>*(Mục 2, p.1)* |
| **14** | **VMLU-MQA**<br>*(Cấp Môn học)* | **Nhóm môn `Công chức`**<br>*(Civil Servant / Quản lý nhà nước & Thuế)* | **MC**<br>*(Trắc nghiệm)* | **33,00% – 50,00%** | Thấp hơn Overall VMLU (`73,35%`) **-23% đến -40%** | Nhầm lẫn các quy định thi tuyển công chức, luật cán bộ công chức và nghiệp vụ hành chính/thuế. | `report_vmlu.pdf`<br>*(Mục 2, p.1)* |
| **15** | **VMLU-MQA**<br>*(Cấp Môn học)* | **Môn `Toán tiểu học`**<br>*(Elementary Mathematics)* | **MC**<br>*(Trắc nghiệm)* | **40,00%** | Thấp hơn nhóm STEM (`79,37%`) **-39,37%** | Sẩy chân ở các bài toán đố lời văn đòi hỏi lập luận số học nhiều bước mà không có CoT — tín hiệu nhất quán với đáy `mathematics` (19,2%) của V-Bench. | `report_vmlu.pdf`<br>*(Mục 2, p.1)* |
| **16** | **VMLU Reading**<br>*(400 câu Pre-reg)* | **`Vi-DROP` (Tổng thể 200 câu)**<br>*(Đọc hiểu suy luận bán cấu trúc & số học)* | **Tự luận ngắn**<br>*(Free-text QA, 48 tokens)* | **63,00%** Chấp nhận / EM<br>*(126 / 200 câu · Bác bỏ **74 câu**)*<br>*(char-F1: `74,49%`)* | Thấp hơn `Vi-SQuAD` (`97,50%`) **-34,50%**<br>*(Chiếm **74/79** ca sai toàn bài đọc)* | Trong khi đọc hiểu trích xuất thuần túy (`Vi-SQuAD`) đạt 97,5% (195/200) và nhóm `selection` trong Vi-DROP đạt 92,68% EM, mô hình gãy nặng khi phải tính toán số học trên văn bản. | `report_vmlu.pdf`<br>*(Bảng 2, p.2)* |
| **17** | **VMLU Reading**<br>*(Phân rã Vi-DROP)* | **Cụm 1 Vi-DROP: `Cộng/trừ hai thành phần` (`add_sub`)** | **Tự luận ngắn**<br>*(Free-text QA)* | **58,18% EM** · `77,28%` F1<br>*(Đúng 32/55 · **Bác bỏ 23 câu = 41,8%**)* | Cụm đóng góp **nhiều câu sai nhất** (23/74 câu) | Mô hình trích xuất đúng các con số trong đoạn văn nhưng **chọn nhầm đối tượng/nhóm thực thể** để đưa vào phép cộng/trừ. | `report_vmlu.pdf`<br>*(Mục 3, p.2)* |
| **18** | **VMLU Reading**<br>*(Phân rã Vi-DROP)* | **Cụm 2 Vi-DROP: `So sánh` (`comparison`)** | **Tự luận ngắn**<br>*(Free-text QA)* | **61,40% EM** · `72,02%` F1<br>*(Đúng 35/57 · **Bác bỏ 22 câu = 38,6%**)* | Cụm đóng góp **nhiều câu sai thứ 2** (22/74 câu) | Lỗi điển hình là **đảo chiều so sánh** (trả lời *"ít hơn"* khi đáp án là *"nhiều hơn"*) hoặc so sánh nhầm cặp đối tượng. | `report_vmlu.pdf`<br>*(Mục 3, p.2)* |
| **19** | **VMLU Reading**<br>*(Phân rã Vi-DROP)* | **Cụm 3 Vi-DROP: `Đếm thực thể` (`count`)** | **Tự luận ngắn**<br>*(Free-text QA)* | **47,50% EM** · `56,28%` F1<br>*(Đúng 19/40 · **Bác bỏ 21 câu = 52,5%**)* | Cụm có **tỉ lệ sai cao nhất** (**52,5%** bị bác bỏ) | Khi liệt kê và đếm nhẩm thực thể trong đoạn văn mà không có công cụ lập trình hỗ trợ, mô hình liên tục đếm thiếu hoặc thừa đúng $\pm 1$ đơn vị. | `report_vmlu.pdf`<br>*(Mục 3, p.2)* |

---

## 📌 Ghi Chú Kiểm Chứng Đối Chứng (Các Phân Vùng KHÔNG Phải Vùng Trũng)

Để đảm bảo tính trung thực khoa học tuyệt đối theo 2 file PDF SSOT, các phân vùng dưới đây đạt kết quả **Tốt / Khá** ở lần đo trần và được dùng làm **nhóm đối chứng (Control / High-Performing Baselines)** chứ không được gọi là vùng trũng:

1. **Trên V-Bench (`report_vbench.pdf` — Nhóm Declarative & Language-heavy đạt `60% – 70%`)**:
   - `computer_science` (MC): **70,21%** *(132 / 188 câu — Top 1 V-Bench)*.
   - `philosophy` (MC): **64,64%** *(170 / 263 câu — Top 2 V-Bench)*.
   - `laws` (MC): **60,73%** *(116 / 191 câu — Top 3 V-Bench)*.
   - `dialect` (MC): **59,96%** *(337 / 562 câu — Top 4 V-Bench)*.
2. **Trên VMLU-MQA (`report_vmlu.pdf`)**:
   - Nhóm ngành **Khoa học tự nhiên (STEM phổ thông/cơ sở)**: **79,37%** *(304 / 383 câu — Khoa học tiểu học 100%, Vật lý 10 95%, Hóa học & Sinh học các cấp ~90%)*.
   - Nhóm ngành **Khoa học xã hội**: **78,26%** *(144 / 184 câu)*.
3. **Trên VMLU Reading (`report_vmlu.pdf`)**:
   - **`Vi-SQuAD` (Đọc hiểu trích mẫu văn bản)**: **97,50% EM** / **98,61% char-F1** *(195 / 200 câu được chấp nhận, chỉ bác bỏ 5 câu)*.
   - **`Vi-DROP — Phân tầng chọn thông tin có sẵn (`selection`)`**: **92,68% EM** / **94,35% char-F1** *(38 / 41 câu đúng, chỉ bác bỏ 3 câu)*.
