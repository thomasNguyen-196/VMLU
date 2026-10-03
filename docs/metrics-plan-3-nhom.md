# Plan metric bổ sung — 3 nhóm (MC-32/33 follow-up)

**Trạng thái (2026-10-03): nhóm 1 XONG (card MC-34).** Nhóm 2–3 chưa bắt đầu.
Chi tiết xem MC-34 trong `measurement_card.md`.

Ngày lập: 2026-10-03. Ngữ cảnh: bảng `/harness` đã đủ 3 model (MC-32, đính chính MC-33).
Câu hỏi gốc: metric hiện tại có đủ phản ánh hành vi model không?
Trả lời: đủ cho các claim hiện tại; thiếu cho hành vi chi tiết. Plan dưới đây lấp chỗ thiếu.

**Nguyên tắc xuyên suốt: không nhóm nào bắt buộc chạy thêm harness `omp`.**
Mọi nhóm đều đo hành vi model từ arm A và ledger cũ. Harness chỉ cần nếu mở RQ mới
("đi qua scaffold thì metric mới đổi ra sao") — là mở rộng, không phải điều kiện.

## Nhóm 1 — Suy từ artifact sẵn có (2–3 ngày, 0 lần gọi model mới)

| Task | Input sẵn có | Output | Tiêu chí xong |
|---|---|---|---|
| 1.1 Tỉ lệ unparseable/empty riêng cho arm A | `raw_result_*`, `reading_answers_*` | Cột `unparseable_rate` cạnh accuracy/EM trong dashboard | Số tách khỏi điểm, không đổi điểm cũ |
| 1.2 Δ harness theo domain/subject | Cột `stratum` trong mọi ledger | Bảng Δ × domain (58 subject VMLU, 12 domain V-Bench) | Mỗi ô đủ n mới hiện; ô thiếu ghi "n nhỏ", không gộp bừa |
| 1.3 Partial credit V-Bench | `vbench_failures_*` (đã phân loại lỗi) | Metric "tham số đúng/tổng tham số" cạnh validity 0/1 | Định nghĩa cố định trước khi tính, áp như nhau mọi arm |

Harness cần không: **Không.** Chỉ đọc ledger/checkpoint cũ. Test: unit test + snapshot số trên 1 arm mẫu.

## Nhóm 2 — Chạy mới, không cần gold mới (1–2 tuần)

| Task | Cách làm | Harness cần không? |
|---|---|---|
| 2.1 Position bias MC | Chạy lại `run_mc_eval.py` với `choices` shuffle (seed cố định), so accuracy gốc vs shuffle | **Không** (đo model). Muốn biết scaffold có khuếch đại bias không thì chạy thêm arm B (~2h máy) — quyết sau |
| 2.2 Faithfulness reading | Model trả lời **kèm trích dẫn** passage; chấm EM như cũ + thêm "câu trả lời có được passage entail không" bằng LLM-as-judge qua chính endpoint IEC | **Không.** Judge là gọi API trực tiếp |

Điểm dừng trung thực cho 2.2: validate judge trên 50–100 câu mẫu thủ công trước;
không đạt thì số faithfulness vô nghĩa, dừng.

## Nhóm 3 — Đắt, cần hạ tầng/gold mới (ngoài scope release, ghi hướng phát triển)

| Task | Điều kiện tiên quyết | Harness cần không? |
|---|---|---|
| 3.1 Calibration | Probe xem gateway có trả `logprobs` không — nếu không, dừng, không cố | Không |
| 3.2 Safety benchmark | 4.000 safety rows đang skip: cần rubric + gold riêng, duyệt hội đồng | Không (đo model gọi thẳng) |

## Thứ tự làm và mốc dừng

1. **Tuần 1**: 1.1 → 1.2 → 1.3, mỗi task kèm test + 1 khối card. Dừng kiểm tra: nếu 1.2 cho
   thấy Δ tập trung ở 1–2 domain thì đó đã là phát hiện đáng viết, không cần vội sang nhóm 2.
2. **Tuần 2–3**: 2.1 trước (rẻ, tự động hoàn toàn), rồi 2.2 (đắt ở khâu validate judge).
3. Nhóm 3: chỉ khởi động khi luận văn chốt cần claim về calibration/safety.

Tổng chi phí gọi model mới ≈ 1 run MC shuffle (~1h) + judge faithfulness (~400 câu) —
nhỏ hơn nhiều so với ~90M token đã dùng cho harness.
