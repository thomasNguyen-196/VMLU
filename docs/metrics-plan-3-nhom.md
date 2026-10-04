# Plan metric bổ sung — 3 nhóm (MC-32/33 follow-up)

**Trạng thái (2026-10-04): nhóm 1 XONG (MC-34); nhóm 2 XONG — 2.1 (MC-35/36) và
2.2 (MC-37/38, kết quả âm: dụng cụ judge trượt cổng). Nhóm 3 chưa bắt đầu.**
Chi tiết xem MC-34/36/38 trong `measurement_card.md`.

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

**Kết quả nhóm 2 (2026-10-04):**

- **2.1 XONG — MC-35/36.** legal_mc-146 shuffle s1234: gốc 130/146 → shuffle 130/146, **Δ +0,00**
  (CI −5,48..+5,48; p=1); stability theo text **same_text 126/146** vs letter-anchored 4 ⇒ model bám
  nội dung, không bám vị trí. Follow-up VMLU-1047 shuffle + harness shuffle **ĐÓNG** (CI chứa 0).
- **2.2 XONG theo nhánh dừng — MC-37/38.** Điều kiện cite 400 câu (compliance 100%, EM 65,00) nhưng
  **judge trượt cổng validation**: MiMo V2.5 đạt agreement 0,8167/**κ 0,1872** (v1), sau một lần siết
  prompt vẫn **κ 0,2941** (v2) < 0,60 ⇒ **dừng, không công bố điểm grounding** (đúng mốc dừng của plan).
  Hướng mở: judge bật reasoning hoặc model mạnh hơn — phải pre-register riêng (MC-39).

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
