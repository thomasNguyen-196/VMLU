# Insight từ kết quả model — chẩn đoán khoảng trống tri thức tiếng Việt

> **Nguồn số:** `measurement_card.md` (MC-1…MC-14b), finals trong `all_res/ollama_result/`,
> blob `/benchmark` (snapshot Qwen3.8), `docs/vbench-server-qwen35.md`, `docs/agents/reading-results-table.md`,
> `docs/agents/vidrop-cluster-breakdown.md`. Đối chiếu DB: `verify_results_db.py`.
>
> **Tính chất:** đây là **đọc chủ quan có căn cứ số** (theo yêu cầu "định hướng hành động"),
> không phải kết luận nhân quả. Mỗi mục ghi rõ điều **không được suy diễn**.
> Insight hiển thị trên web: `/results` (module `web/lib/insights.ts`).

---

## 0. Bảng tổng hợp model × bộ

| Bộ (n) | Qwen3.5-9B-28K | Qwen3.8-27B-Q4_K_M | qwen38-nothink (27B) |
| --- | --- | --- | --- |
| VMLU dev+valid (1.047) | **73,35%** (768) | **73,35%** (768) | — |
| VMLU test 9.833 (leaderboard) | **67,87%** | — | — |
| V-Bench 5.141 (server) | macro **45,22** · micro **45,61** | macro **44,97** · micro **45,46** | — |
| Reading-400 | EM **79,75** · F1 **86,49** | EM **80,25** · F1 **86,55** | — |
| Legal MC-146 | **87,67%** (baseline 62,33) | — | **82,88%** (21 blank) |
| Legal NLI-150 | **90,00%** (baseline 50) | — | — |
| BidLQA val-482 | EM **32,78** · F1 **74,16** | — | — |
| BidLQA test-603 | EM **33,17** · F1 **73,21** | — | — |

---

## 1. Ba phát hiện xuyên suốt

### 1.1. Capacity KHÔNG phải nút thắt trên các bộ hiện có

| Bằng chứng | 9B | 27B | Chênh |
| --- | --- | --- | --- |
| VMLU dev+valid | 768/1.047 | 768/1.047 | 0 |
| VMLU theo môn | — | — | **54/58 môn trùng khớp tuyệt đối**; chỉ 4 môn lệch: Toán THCS 45↔55, Kế toán 44,4↔50, Đo lường 64↔57, Luật giáo dục 76↔71 |
| V-Bench macro / micro | 45,22 / 45,61 | 44,97 / 45,46 | −0,25 / −0,15 |
| V-Bench từng miền | — | — | **lệch ≤2,1 điểm** (cao nhất: laws 62,83 vs 60,73); philosophy trùng 64,64 |
| Reading-400 EM | 79,75 | 80,25 | +0,50 |
| Reading-400 DROP EM | 63,00 | 63,00 | **0** |

→ Gấp ~3 lần tham số (9B → 27B) không tạo khác biệt có ý nghĩa. **Nút thắt nằm ở loại tri thức / phương pháp suy luận / định dạng, không ở quy mô.**
Hệ quả cho đề cương: giai đoạn C nên dồn ngân sách vào grounding/định tuyến/ngân sách suy luận, không phải model lớn hơn.

### 1.2. Cùng model — hai bộ "cùng miền" cho kết luận trái ngược

| Miền | VMLU (recall kiến thức) | V-Bench (vận dụng) | Chênh |
| --- | --- | --- | --- |
| Toán | Toán tiểu học 40% (n=20) · Toán THCS 45% (n=9–11) | mathematics **20,0%** (n=125) | ~20 điểm |
| Vật lý | Lý THCS 90% · Lý THPT 95% (n=20) | physics **28,57%** (n=147) | ~66 điểm |
| Hóa | Hóa THCS 90% (n=20) | chemistry **38,92%** (n=334) | ~51 điểm |
| Y | Nội cơ sở 78% (n=18) | medicine **38,57%** (n=490) | ~39 điểm |

→ "STEM mạnh 79%" trên VMLU **không** có nghĩa model làm được bài toán/lý/hóa ứng dụng. VMLU đo kiến thức phổ thông dạng nhớ; V-Bench đo vận dụng. **Không được gộp hai loại số này thành một "năng lực STEM".**

### 1.3. "Valid ≠ correct" và lỗi gần đúng (near-miss) chiếm phần lớn

| Bằng chứng | Số |
| --- | --- |
| V-Bench agentic | **1.000/1.000 valid** (sau guided; 986/1.000 ở minimal thuần) nhưng chỉ **397/1.000 khớp tham chiếu** |
| BidLQA val | **105/482 (21,8%)** câu có F1≥0,8 mà EM=0; chỉ 2 câu F1=0 |
| BidLQA test | **120/603 (19,9%)** tương tự |
| Legal MC (qwen38-nothink) | 21/146 blank (14,4%) dù đã nâng max_tokens 512 |

→ Phần lớn "sai" không phải vì không biết/không tìm thấy, mà vì **ngữ nghĩa gọi hàm** và **định dạng câu trả lời**. Đây là loại lỗi sửa được bằng can thiệp suy luận (kiểm chứng tham số, chuẩn hoá span), không cần đổi model.

---

## 2. Chẩn đoán theo model

### 2.1. Qwen3.5-9B-28K (model chính — MC-7…MC-13)

| Bộ | Kết quả chính | Chẩn đoán | Nguyên nhân khả nghi |
| --- | --- | --- | --- |
| VMLU dev+valid | 73,35%; STEM 79,37 · SocSci 78,26 · Humanity 68,52 · Other 62,82; **8/58 môn <50%** | Phân hóa theo **loại tri thức**, không theo ngôn ngữ | Thiếu tri thức quy chuẩn + tham số bản địa |
| VMLU test | 67,87% (STEM 65,65 · SocSci 74,97 · Humanity 68,61 · Other 63,67) | Thấp hơn dev+valid ~5,5 điểm | Phân bố test khó hơn / khác dạng |
| V-Bench | MC 47,04% vs agentic 39,70%; yếu: toán 20,0 · logic 24,89 · lý 28,57 · hóa 38,92 · y 38,57; mạnh: CS 71,28 · triết 64,64 · luật 62,83 | Nút thắt ở **suy luận** và **ngữ nghĩa tool-calling** | Hạn chế suy luận; kiểm chứng tham số yếu |
| Legal MC-146 | 87,67% vs baseline 62,33 (+25,3); 0 blank | Mảng luật dạng MCQ **không yếu** | (Xung đột với VMLU luật 30% — xem §3.4) |
| Legal NLI-150 | 90,00% vs baseline 50 (+40); gold B 100% / gold A 80% | Đúng cao nhưng **thiên lệch "Không"** | Thiên lệch đáp án (calibration) |
| BidLQA val/test | EM 32,78/33,17 · F1 74,16/73,21; near-miss ~20% | Lỗi **định dạng/diễn đạt**, ổn định qua split | Định dạng câu trả lời tự do |
| Reading-400 | EM 79,75 · F1 86,49; SQuAD 96,5 vs DROP 63,0 | Trích xuất gần trần; **suy luận số là điểm nghẽn** | Hạn chế suy luận (cộng/trừ, so sánh, đếm) |

**Tóm tắt 9B:** mạnh đọc-hiểu-trích xuất và kiến thức phổ thông; yếu (1) suy luận số/logic, (2) tri thức quy chuẩn bản địa, (3) ngữ nghĩa gọi hàm, (4) định dạng trả lời tự do; có thiên lệch đáp án NLI.

### 2.2. Qwen3.8-27B-Q4_K_M (đối chứng — MC-1/MC-2/MC-2b/MC-3)

- Trùng 9B trên VMLU (cùng 768/1.047) và reading (80,25/86,55) và V-Bench (44,97/45,46) — xem §1.1.
- **Prompt ablation:** đổi `minimal` → `detailed` làm **42,2% câu agentic (415/983) đổi đáp án**, 213 câu đổi hẳn hàm. Prompt engineering giảm 11 lỗi cú pháp nhưng xáo trộn gần nửa số câu.
- ⚠️ Model đã rời endpoint 12/09 (MC-4) — không tái lập, không chạy thêm được.

### 2.3. qwen38-nothink (đối chứng 27B, thinking ẩn — MC-6)

- Legal MC 82,88% — **thấp hơn 9B 4,8 điểm**, trong đó **21 câu blank** (raw rỗng) dù đã nâng max_tokens lên 512; valid 85,6%; sai trong số parse được chỉ 4.
- → Vấn đề **ngân sách/định dạng** (thinking ẩn ăn hết token), không phải kiến thức. Không cộng điểm bù.

---

## 3. Chẩn đoán theo bộ (cross-model)

### 3.1. VMLU (dev+valid)
- 9B và 27B **giống hệt**: 54/58 môn khớp tuyệt đối. Trũng chung: Luật hành chính 30%, Sư phạm mầm non 30%, Thuế công chức 33,3%, Toán tiểu học 40%, Văn THPT 40%, Kế toán 44,4%, Logic 50%, Công chức 50%.
- Nhóm quy chuẩn/hành chính chiếm gần hết danh sách yếu → **khoảng trống theo loại tri thức**, đúng giả thuyết đề cương.

### 3.2. V-Bench
- Cấu trúc lỗi giống nhau ở cả hai model: toán/logic/lý <30% → y/hóa/văn ~39–41% → văn hóa/tâm lý ~47–50% → phương ngữ/luật/triết/CS 60–71%.
- **MC 47,0% vs agentic 39,1–39,7%** ở cả hai model; valid ~100% → nút thắt ngữ nghĩa.
- Prompt sensitivity 42,2% (MC-2b) → mọi so sánh phải khóa một điều kiện hỏi.

### 3.3. Reading-400
- SQuAD gần trần (EM 96,5–97,5) vs DROP 63,0 ở **cả hai model**.
- 74 câu DROP bị bác (bản cũ 1 người duyệt) tập trung: **cộng/trừ 2 thành phần 23 · so sánh 22 · đếm 21**; 8 câu ngoài cụm (`selection` 3, `other` 5).
- → Điểm nghẽn là **suy luận số**, không phải đọc hiểu.

### 3.4. Legal (MC + NLI) — có xung đột cần điều tra
- VMLU "Luật hành chính" 30% (n=10) vs **LegalSLM MC 87,67%** (n=146). Hai bộ khác nguồn/khác dạng/cỡ mẫu rất khác → **chưa thể kết luận "model yếu luật"**; cần bộ luật lớn hơn, cùng dạng, trước khi chốt.
- NLI 90% nhưng lệch B (A 80% / B 100%) → nếu dùng NLI làm bước kiểm chứng trong RAG phải hiệu chỉnh thiên lệch trước.

### 3.5. BidLQA (open-book, pháp lý đấu thầu)
- EM ~33% nhưng F1 ~73–74% và near-miss ~20% → mô hình **tìm đúng vùng thông tin**, thua ở định dạng/độ dài.
- Val/test lệch 0,4 điểm EM → ổn định; lỗi có hệ thống, không phải nhiễu.

---

## 4. Xếp hạng điểm nghẽn + hướng can thiệp (giai đoạn C của đề cương)

| # | Điểm nghẽn | Bằng chứng | Hướng được phép (C1/C2/C3) |
| --- | --- | --- | --- |
| 1 | **Suy luận số / so sánh / đếm** | DROP EM 63 vs SQuAD 96,5; cluster 23/22/21; V-Bench toán 20 · logic 24,9 · lý 28,6 | Ngân sách suy luận có kiểm soát (CoT/scratchpad) + grounding cho bài số học; đo token cost |
| 2 | **Tri thức quy chuẩn bản địa** | VMLU 8 môn <50 (luật HC 30, thuế 33, nghiệp vụ 50); đối chiếu V-Bench laws 62,8 | RAG văn bản quy phạm **có chọn lọc theo môn** (C3); C2 toàn phần để đo nhiễu truy xuất |
| 3 | **Ngữ nghĩa gọi hàm** | agentic 39,7% vs valid 100% | Kiểm chứng tham số trước khi gọi (đối chiếu ngữ cảnh), không chỉ đúng schema |
| 4 | **Định dạng trả lời tự do** | BidLQA near-miss 21,8%/19,9%; F1=0 chỉ 2 câu | Chuẩn hoá/ràng buộc span ngắn; hạ token budget cho câu trích xuất |
| 5 | **Thiên lệch đáp án** | NLI B 100% / A 80% | Hiệu chỉnh/counterfactual đảo nhãn trước khi dùng cho routing |
| 6 | **Nhạy điều kiện hỏi** | 42,2% câu agentic đổi đáp án khi đổi prompt; test −5,5 điểm so dev+valid | Khóa một điều kiện khi công bố; lặp lại để tách dao động hạ tầng |

**Chỉ số đối đầu gợi ý (đề cương):** accuracy tổng + theo miền · token trung bình · Pareto `E = Acc / log₁₀(T_avg)` · tỷ lệ nhiễu truy xuất (C2 vs C3).

---

## 5. Bản đồ taxonomy (theo đề cương)

| Loại khoảng trống | Bằng chứng định lượng | Mức độ |
| --- | --- | --- |
| Thiếu tri thức **tham số** | Môn phổ thông vẫn ổn (nhiều môn 90–100%) nhưng 4 môn <45% | Trung bình, cục bộ |
| Thiếu tri thức **quy chuẩn** | Luật HC 30% · Thuế 33% · Nghiệp vụ 50% · Kế toán 44% (VMLU) | Rõ, lặp ở cả 2 model |
| Hạn chế **suy luận** | DROP 63 vs SQuAD 96,5; toán 20 · logic 24,9 · lý 28,6 (V-Bench) | **Nặng nhất, lặp ở cả 2 model** |
| **Ảo giác quy chuẩn** | Chưa đo trực tiếp (ViHallu chưa có dữ liệu — xem `docs/agents/measurement-gaps.md`) | Chưa xác định |
| **Định dạng / ngân sách** | BidLQA near-miss ~20%; qwen38 21 blank | Rõ, sửa được |
| **Thiên lệch đáp án** | NLI A 80% vs B 100% | Rõ ở NLI |
| **Nhạy điều kiện** | 42,2% đổi đáp án; test −5,5 | Rõ, cần kiểm soát thực nghiệm |

---

## 6. Không được suy diễn (bắt buộc)

1. **Một lần chạy duy nhất** (seed 42, temp 0) — chưa đo dao động hạ tầng; mọi so sánh chỉ trong cùng điều kiện card.
2. **Không cộng/so điểm giữa các bộ khác dạng** (MC vs reading vs server-side); chỉ được nói "cùng hướng/khác hướng".
3. **Model 9B vượt giới hạn ≤4B** của LegalSLM/ViHallu — ghi rõ khi công bố.
4. **27B đã rời endpoint** (MC-4) — không tái lập; số 27B là snapshot lịch sử.
5. **Reading-400 single-rater, chưa IAA**; EM/F1 trên gold hiệu đính 1 người.
6. **VMLU theo môn chỉ 10–20 câu/môn** — không lấy làm đại diện cả mảng; đặc biệt "Luật hành chính 30%" (n=10) chưa đủ để kết luận mảng luật (xem §3.4).
7. **V-Bench chấm server-side** (vbench.ai), không recompute local; `valid ≠ correct`.
8. **Số neo trong tài liệu này** lấy tại 2026-09-21/22; khi finals đổi (VM14K sắp xong) phải cập nhật — bảng trong `/results` là nguồn live.
