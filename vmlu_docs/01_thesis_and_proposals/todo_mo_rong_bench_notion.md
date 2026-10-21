# Mở rộng bench — theo lỗ hổng

Nguồn: VMLU-MQA + V-Bench (Qwen3-8-27B Q4_K_M, local). Làm tuần tự. Item sau chỉ mở khi exit của item trước đã đạt.

Trạng thái mặc định: Not started

---

## 0 — Đóng nợ cùng suite trước khi thêm suite

- [ ] Tách 80,25% ra khỏi mọi câu “độ chính xác đọc hiểu”. Trong bảng và abstract chỉ còn nhận: accept-rate (optimistic, single-rater) ≠ EM / char-F1
	Exit: không còn câu nào trong report chính đồng nhất accept-rate với accuracy đọc hiểu
- [ ] Chấm lại 400 câu pre-register bằng EM và char-F1 trên gold độc lập (đáp án hiệu đính + gold gốc nếu còn), tách Vi-SQuAD / Vi-DROP
	Exit: có bảng RC với EM, char-F1, n theo từng nguồn
- [ ] Breakdown 74 câu Vi-DROP bị bác theo đúng 3 cụm: cộng/trừ hai thành phần, so sánh, đếm. Không gộp “reasoning”
	Exit: 3 số đếm + ví dụ, không còn nhãn chung
- [ ] Người duyệt thứ hai trên ít nhất phần bác bỏ (79 câu) + mẫu chấp nhận. Ghi IAA; nếu không có người thứ hai thì giữ nhãn single-rater
	Exit: hệ số IAA hoặc dòng “single-rater, chưa IAA” trong limitations
- [ ] Chạy nốt Vi-Dialog cùng model, cùng serving, cùng seed — hoặc ghi rõ “chưa chạy”
	Exit: điểm Vi-Dialog hoặc mục “out of scope / chưa chạy” trong report
- [ ] Gom mục 0 thành một bảng RC sạch
	Exit: EM/F1 + n + raw count; accept-rate chỉ còn appendix

---

## 1 — Đóng băng điều kiện đo

- [ ] Viết `measurement_card.md` dùng chung: model id, quant Q4_K_M, endpoint, temperature 0, seed 42, token budget, prompt style (minimal | detailed), có/không CoT, ngày chạy
	Exit: file có trong repo và được trích dẫn từ mọi report sau này
- [ ] Cấm merge điểm minimal với điểm detailed. Ablation agentic 42,2% đổi đáp án là lý do
	Exit: mỗi điều kiện một hàng điểm, không có cột “best of”
- [ ] Validator cấu trúc và scorer semantics là hai bước, hai file log. Valid ≠ correct
	Exit: log tách; bảng agentic có cả valid rate và semantic match
- [ ] Mọi run mới gắn hash của measurement card
	Exit: field `measurement_card_hash` trong output run

---

## 2 — Một suite hình dạng khác — chọn đúng một

Chọn A hoặc B, không song song.

- [ ] Quyết định A hoặc B
	A = SEA-HELM track VI (culture / linguistics / instruction following / safety)
	B = Vietnamese Function Calling Test (2.899) hoặc SEATauBench (kiểm lại semantics ≠ syntax trên schema khác V-Bench)
	Exit: một dòng quyết định + lý do bám lỗ hổng, không bám “thiếu suite”
- [ ] Pre-register manifest + seed trước khi nhìn gold / leaderboard script
	Exit: manifest đã commit, timestamp trước lần infer đầu
- [ ] Chạy đúng measurement card ở mục 1. Không sửa prompt cho gần baseline công bố
	Exit: run log khớp card
- [ ] Công bố kết quả theo task shape
	Exit: một bảng; nếu tool-calling thì có valid vs đúng. Không có cột so với VMLU 73%

---

## 3 — Domain đáy đã thấy — chỉ sau mục 2

- [ ] Luật: VietLegal hoặc VLSP 2025 LegalSLM. Không lấy 10–20 câu VMLU-MQA làm điểm domain
	Exit: n đủ lớn hơn mẫu môn VMLU; tách nhớ điều/khái niệm khỏi NLI / syllogism / citation nếu suite hỗ trợ
- [ ] Y: VM14K public split. Đối chiếu V-Bench medicine 38,78% chỉ ở mức cùng hướng / khác hướng
	Exit: điểm VM14K + câu “không trừ hai phần trăm với V-Bench”

---

## 4 — Thứ chưa đo — đừng gọi là năng lực tổng quát

- [ ] Hallucination: ViHallu, một split, cùng measurement card
	Exit: metric đúng tên suite, không nhét vào macro tiếng Việt
- [ ] Bias: ViBBQ trục Việt Nam-specific, không chỉ bản dịch BBQ
	Exit: tách trục dịch vs trục nội địa
- [ ] Safety V-Bench 4.000 item đang skip: chạy và công bố scope, hoặc giữ “out of scoring scope”
	Exit: một trong hai, không suy từ academic MCQ
- [ ] Sycophancy hội thoại tiếng Việt: ghi gap (chưa có suite tương đương ELEPHANT / BenSyc). Không tự dựng vài chục câu rồi gọi là bench
	Exit: đoạn gap trong report, không có “điểm sycophancy” tự chế
