# Runner mới: `score_reading_eval.py`

Chấm điểm bài đọc hiểu 400 câu bằng **EM** và **char-F1** trên gold đã chốt trong
`data/review_gold_agreed.csv`. Thay thế cách nói "tỉ lệ chấp nhận" trong báo cáo.

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
    --gold data/review_gold_agreed.csv
```

## Vào / ra

| | |
| --- | --- |
| Vào | `all_res/ollama_result/reading_answers_<model>.csv` + `data/review_gold_agreed.csv` |
| Ra | `reading_scores_<model>.csv` (từng câu) · `reading_summary_<model>.csv` (tổng hợp) |
| Bắt buộc | `measurement_card.md` phải tồn tại — thiếu thì script dừng |

Mọi dòng trong file tổng hợp đều mang `measurement_card_hash` (sha256 của card)
để truy vết về đúng điều kiện đo.

### Đơn vị — đọc trước khi trích số

Tên `em` mang **hai nghĩa khác nhau** ở hai file, đây là chỗ dễ trích sai nhất:

| File | Cột | Đơn vị | Miền giá trị |
| --- | --- | --- | --- |
| `reading_scores_*.csv` (từng câu) | `em` | **0 hoặc 1** | `{0, 1}` — không có giá trị nào khác |
| `reading_scores_*.csv` (từng câu) | `f1` | điểm bộ phận | `[0, 1]` liên tục |
| `reading_summary_*.csv` | `em_count` | **số câu đúng** (số nguyên) | `0 … n` |
| `reading_summary_*.csv` | `em` | **phần trăm** | `0 … 100` |
| `reading_summary_*.csv` | `char_f1` | **phần trăm** | `0 … 100` |

> ⚠️ **EM là nhị phân ở tầng từng câu.** Giá trị `em` lẻ trong `reading_scores_*.csv` là **bug**.
> Con số `80.25` trong file tổng hợp **không phải điểm của một câu** — nó là `321/400 × 100`.
> Muốn kiểm tra tay thì dùng `em_count` (số nguyên), đừng dùng `em`.
> Với `n = 400`, bước nhảy nhỏ nhất của cột `em` là `1/400 = 0,25`; phân tầng lẻ (n = 41, 55 …)
> cho phần thập phân lẻ hơn — vẫn là hệ quả của phép chia, **không phải** điểm bộ phận.

Công thức đầy đủ và bảng ví dụ: [`em-char-f1.md`](em-char-f1.md).

### Tái tạo gold nếu chưa có

`data/review_gold_agreed.csv` **không được commit** (derived — xem `.gitignore` mục `data/`).
Nó là file dẫn xuất từ `review_records/` — bản ghi đã được track. Sinh lại bằng:

```bash
.venv/bin/python code_benchmark/export_annotation_workbooks.py merge-split review_records/*.csv
```

Lệnh này **không** ghi vào `data/eval_set_manifest.csv` (không có `--apply`), chỉ tạo hai file
`data/review_gold_agreed.csv` và `data/review_adjudication.csv`. Muốn chấm điểm thì chỉ cần
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
