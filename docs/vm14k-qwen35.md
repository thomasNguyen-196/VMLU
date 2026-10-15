# Qwen3.5 VM14K public-12.488 (card MC-14b)

Điều kiện đo: `MC-14b` (VM14K public release, shuffled0), measurement_card.md.
Model `Qwen3.5-9B-28K` qua `https://llmapi.iec-uit.com/v1`
(temp 0, seed 42, 4 token, workers 8, frozen `build_prompt`/`extract_answer`).
Cấm so ngang model khác (MC-1/MC-2/MC-6 là model khác) và cấm trừ phần trăm
với V-Bench medicine (khác dạng câu — chỉ nói cùng/khác hướng).

## Kết quả

| Track | Card | n | Metric | Kết quả | Baseline |
| --- | --- | --- | --- | --- | --- |
| VM14K public-shuffled0 | MC-14b | 12.488 | accuracy (chữ cái) | **64,79%** (8.091/12.488) | luôn-A 3.915/12.488 = **31,35%** → **+33,4đ** |

Parse **100%** (valid 12.488/12.488), 0 blank, 0 empty raw.
Recompute từ per-item CSV khớp accuracy file (0 mismatch);
key-set 2 chiều khớp `data/vm14k_manifest.json`; gold full ↔ manifest 0 lệch.

Theo độ khó tự khai báo (đơn điệu, thang khó của bộ có tín hiệu):
Easy **67,19%** (2.763/4.112) → Medium **64,01%** (4.540/7.093) →
Challenging **61,78%** (737/1.193) → Hard **56,67%** (51/90).

Theo số lựa chọn: 4 → **64,16%** (7.129/11.111) · 2 (Đúng/Sai) →
**69,84%** (866/1.240) · 3 → 67,33% · 7 → 57,89% (11/19) ·
1 → 100% (15/15) · 5 → 100% (2/2).
Câu Đúng/Sai kéo điểm tổng lên — báo 4-lựa-chọn làm số chính.

Theo gold: D **75,06%** · C 64,69% · A 62,78% · B 58,62% · E 100% (1/1).

Theo nhóm chuyên khoa (taxonomy tiền đăng ký `code_benchmark/vm14k_taxonomy.py`,
nhóm = tag đầu tiên của `medical_topic`):

| Nhóm | n | Accuracy |
| --- | --- | --- |
| Ung bướu & Chăm sóc giảm nhẹ | 280 | **71,43%** |
| Y tế công cộng & Dự phòng | 228 | **70,61%** |
| Khoa học cơ sở | 381 | 67,19% |
| Nội khoa | 6.299 | 65,88% |
| Dược – Độc – Điều trị | 567 | 64,73% |
| Chuyên khoa khác | 493 | 64,10% |
| Sản – Nhi | 2.589 | 62,84% |
| Cận lâm sàng & Chẩn đoán | 408 | 61,52% |
| Ngoại – Gây mê – Hồi sức – Cấp cứu | 1.236 | 61,49% |
| unknown (tag rác) | 7 | 42,86% |

Nội khoa chiếm một nửa bộ (50,4%) nên quyết định điểm tổng; nhóm mạnh nhất là
Ung bướu, trũng nhất là Ngoại — đọc như điểm trũng theo miền (xem caveat cỡ
mẫu: YTCC chỉ n=228).

## Nhận xét chéo (cùng model, khác suite — mô tả, không xếp hạng)

- **VM14K 64,79% vs V-Bench medicine 38,57% (MC-8, 189/490): khác hướng mạnh.**
  Hai bộ đo hai thứ khác nhau (VM14K lẫn 1.240 câu Đúng/Sai + 15 câu 1 lựa
  chọn, độ khó tự khai báo; V-Bench medicine là vận dụng) — không trừ hai
  phần trăm cho nhau (đúng luật mục 3.2 của roadmap).
- **VM14K vs Legal MC-146 87,67% (MC-10):** cùng runner frozen, cùng
  closed-book — mảng Y-khoa đại chúng (VM14K) thấp hơn mảng luật phổ thông
  ~23 điểm. Đọc như điểm trũng theo miền, chưa phải kết luận nhân quả
  (xem caveat dữ liệu dưới).
- **Thang độ khó có tín hiệu:** gradient đơn điệu Easy→Hard hiếm gặp ở các
  bộ khác (VMLU theo môn n=10–20 nhiễu hơn) — đủ cơ sở để báo cáo bẻ theo
  difficulty trong giai đoạn C.

## Outputs (gitignored) + manifests (tracked)

- `all_res/ollama_result/Qwen3_5-9B-28K/full_evaluation_vm14k_Qwen3_5-9B-28K.csv`
  + `accuracy_vm14k_Qwen3_5-9B-28K.csv` + `submission_vm14k_Qwen3_5-9B-28K.csv`
  (12.488 dòng; checkpoint VM14K park riêng `vm14k_checkpoints/`, 125 file).
- `data/vm14k_manifest.json` (sha `68821834…1e05aef4` khớp source, seed 42;
  mỗi item thêm `primary_topic` + `category` từ taxonomy tiền đăng ký
  `code_benchmark/vm14k_taxonomy.py` — id/gold/n_choices/difficulty giữ nguyên).
- Blob `web/public/benchmark-data.json`: `.vm14k` (overall + baseline +
  by_gold + by_difficulty + by_n_choices) — các key cũ byte-identical.
- Live `/benchmark`: tab VM14K từ Mongo
  (`qwen3-5-9b-28k__vm14k-public-12488__MC-14b`, 12.488 items).

## Caveat dữ liệu (bắt buộc khi công bố)

1. Bản phát hành lệch paper (12.488 dòng/file vs paper 4k+10k+2k; private
   2k không có ở đây) + **không license** — research-use, trích dẫn paper + HF.
2. 1.377/12.488 dòng ≠ 4 lựa chọn; 34 dòng placeholder `optionE/F/G`;
   2 dòng question rỗng; 19 dòng 7 lựa chọn có thể elicits F/G (parser
   frozen A–E → tính sai).
3. ~6% trùng lặp nội dung giữ nguyên (không dedupe) — quyết định lọc phải
   là card mới, không sửa bộ raw.
4. Model 9B vượt giới hạn ≤4B của suite — ghi rõ khi công bố.

## Không làm trong change này

- **Shuffled1/shuffled2 DEFER:** cùng 12.488 id với options permuted
  (pass@k/ensemble theo paper) — để change riêng, card riêng.
- **Dedup/filtered split DEFER:** mọi bản lọc phải pre-register manifest
  mới, không tự ý sửa input đã chạy MC-14b.
