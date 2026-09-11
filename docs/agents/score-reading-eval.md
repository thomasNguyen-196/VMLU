# Runner mới: `score_reading_eval.py`

Chấm điểm bài đọc hiểu 400 câu bằng **EM** và **char-F1** trên gold đã chốt trong
`review_gold_agreed.csv`. Thay thế cách nói "tỉ lệ chấp nhận" trong báo cáo.

## Vì sao cần

Giao diện duyệt trả về **accept-rate**: tỉ lệ câu trả lời của model được người duyệt
xác nhận là đáp án tham chiếu. Đó **không phải độ chính xác**:

- Đáp án tham chiếu được **kế thừa từ chính câu trả lời của model** → thiên lệch thuận.
- Lỗi tinh vi mà người duyệt bỏ sót được tính là **đúng**.
- Chỉ có **một người duyệt**, chưa có IAA.

EM / char-F1 đo trên tập tham chiếu **đã cố định** là con số đem báo cáo.
Accept-rate chuyển xuống phụ lục.

## Chạy

```bash
# tự tìm reading_answers_*.csv mới nhất
.venv/bin/python code_benchmark/score_reading_eval.py

# chỉ định rõ file
.venv/bin/python code_benchmark/score_reading_eval.py \
    --answers all_res/ollama_result/reading_answers_<model>.csv \
    --gold review_gold_agreed.csv
```

## Vào / ra

| | |
| --- | --- |
| Vào | `all_res/ollama_result/reading_answers_<model>.csv` + `review_gold_agreed.csv` |
| Ra | `reading_scores_<model>.csv` (từng câu) · `reading_summary_<model>.csv` (tổng hợp) |
| Bắt buộc | `measurement_card.md` phải tồn tại — thiếu thì script dừng |

Mọi dòng trong file tổng hợp đều mang `measurement_card_hash` (sha256 của card)
để truy vết về đúng điều kiện đo.

### Tái tạo gold nếu chưa có

`review_gold_agreed.csv` **không được commit** (khớp quy ước `/review_*.csv` trong `.gitignore`).
Nó là file dẫn xuất từ `review_records/` — bản ghi đã được track. Sinh lại bằng:

```bash
.venv/bin/python code_benchmark/export_annotation_workbooks.py merge-split review_records/*.csv
```

Lệnh này **không** ghi vào `eval_set_manifest.csv` (không có `--apply`), chỉ tạo hai file
`review_gold_agreed.csv` và `review_adjudication.csv` ở gốc repo. Muốn chấm điểm thì chỉ cần
file thứ nhất.

## Kết quả (model Qwen3.8-27B-Q4_K_M, card `MC-3`)

| Nguồn | n | EM | char-F1 | exact-raw |
| --- | --- | --- | --- | --- |
| Vi-SQuAD | 200 | 97,50 | 98,61 | 195 |
| Vi-DROP | 200 | 63,00 | 74,49 | 126 |
| **Tổng** | **400** | **80,25** | **86,55** | **321** |

Theo từng phân tầng:

| Nguồn | Phân tầng | n | EM | char-F1 |
| --- | --- | --- | --- | --- |
| Vi-SQuAD | short-direct | 92 | 95,65 | 97,24 |
| Vi-SQuAD | mid-direct | 47 | 100,00 | 100,00 |
| Vi-SQuAD | long-direct | 46 | 97,83 | 99,48 |
| Vi-SQuAD | short/mid/long-infer | 5+5+5 | 100,00 | 100,00 |
| Vi-DROP | selection | 41 | 92,68 | 94,35 |
| Vi-DROP | comparison | 57 | 61,40 | 72,02 |
| Vi-DROP | add_sub | 55 | 58,18 | 77,28 |
| Vi-DROP | count | 40 | 47,50 | 56,28 |
| Vi-DROP | other | 7 | 28,57 | 60,48 |

## Ghi chú kỹ thuật

**Vì sao EM ở đây không phải EM "trùng khít tuyệt đối".** Gold là văn bản tự do
(`"Bằng nhau, mỗi quân đoàn có 3 sư đoàn"`), không phải span trích xuất. Nên EM
được tính bằng *tập biến thể tương đương*: khớp chuỗi đã chuẩn hoá, khớp bỏ dấu,
hoặc khớp số khi cả hai vế đều là số.

Kiểm chứng: trong 400 câu, **không có câu nào** mà chuẩn hoá "cứu" được điểm
(`em != exact_raw` = 0 trường hợp). Nghĩa là chấm chặt hay chấm nới cho **cùng kết quả**
trên tập này — con số không phụ thuộc vào quy tắc chuẩn hoá.

**`exact_raw`** = số câu model trả lời **nguyên văn** đáp án tham chiếu (sau chuẩn hoá).
Bằng đúng số `accept` (321) → xác nhận gold được kế thừa từ chính output của model,
đúng như cảnh báo về thiên lệch thuận.

**`f1 == 0`**: 22 câu (toàn bộ thuộc Vi-DROP), tức không trùng một ký tự nào với gold.

**Số học dài** (Vi-DROP cần tính toán nhiều bước) là điểm yếu nhất: `count` 47,5%,
`add_sub` 58,18%. Ngược lại `selection` đạt 92,68% — chọn thông tin có sẵn trong
đoạn văn thì model làm tốt.
