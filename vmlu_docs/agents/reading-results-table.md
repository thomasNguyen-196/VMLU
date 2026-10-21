# Bảng kết quả đọc hiểu — 400 câu pre-registered

> **Điều kiện đo:** `MC-3`, xem [`measurement_card.md`](../../measurement_card.md)
> **Ít nhất một lần chạy, một model.** Không có lần lặp để đo dao động.
> Model: `Qwen3.8-27B-Q4_K_M.gguf` · seed 42 · temperature 0 · ngân sách 48 token · open-book · no-CoT
> `measurement_card_hash`: `56743eb19d1764d07832af7cb250a1601fe7f74b83937e678a3fe06e63cf633e`

---

## Bảng chính

> **Đơn vị của hai cột điểm:** cả EM và char-F1 đều là **tỉ lệ phần trăm trên cả nhóm**, không phải
> điểm của một câu. **EM ở tầng từng câu chỉ có 0 hoặc 1**; phần thập phân của `97,50` sinh ra từ
> phép chia `195/200`, không phải từ điểm bộ phận. Cột `n trả lời đúng nguyên văn` mới là **số đếm thô**
> (số nguyên) — dùng nó để kiểm tra tay. Công thức đầy đủ: [`em-char-f1.md`](em-char-f1.md) §0.0.

| Nguồn | n | EM | char-F1 | n trả lời đúng nguyên văn |
| --- | --- | --- | --- | --- |
| Vi-SQuAD | 200 | **97,50%** | **98,61%** | 195 |
| Vi-DROP | 200 | **63,00%** | **74,49%** | 126 |
| **Tổng** | **400** | **80,25%** | **86,55%** | **321** |

`n trả lời đúng nguyên văn` = số câu model phát ra **đúng chuỗi** đáp án tham chiếu (đã chuẩn hoá).
Con số này **trùng khít** với số câu được người duyệt bấm "chấp nhận" (321).

**Kiểm tra tay được với EM, không kiểm tra tay được với char-F1:**

```
EM  = 321 / 400 * 100 = 80,25      ← tử số là số nguyên đếm được
F1  = trung bình của 400 số thực   ← phải chạy máy mới có
```

---

## Đọc bảng này thế nào

**Con số 80,25% không phải "độ chính xác đọc hiểu" theo nghĩa thông thường.**

Đáp án tham chiếu của 400 câu được **xây dựng trong lúc duyệt**: câu nào người duyệt
chấp nhận thì **câu trả lời của model trở thành đáp án tham chiếu**. Hệ quả:

- 321 câu accept → đáp án tham chiếu **chính là output của model**.
- 79 câu bị bác → đáp án tham chiếu do người duyệt viết.
- Lỗi tinh vi mà người duyệt bỏ sót **được tính là đúng**.

Vì vậy đây là ước lượng **cận trên, thiên lệch thuận** (optimistic upper bound), không phải
điểm năng lực. Nhưng khác với "accept-rate" ở chỗ: đây là **EM/char-F1 đo trên một tập tham chiếu
đã cố định**, nên **so sánh được giữa các lần chạy** — miễn là giữ nguyên tập gold này.

**Điều kiện để con số này có nghĩa:** gold phải đứng yên. Từ nay `data/gold/review_gold_agreed.csv`
là tập tham chiếu đóng băng. Chạy lại model khác thì chấm trên **đúng file này**.

---

## Phân rã theo dạng câu hỏi

### Vi-SQuAD — trả lời trích xuất từ đoạn văn

| Phân tầng | n | EM | char-F1 |
| --- | --- | --- | --- |
| direct (trả lời có sẵn trong bài) | 185 | 97,30 | 98,50 |
| infer (phải suy ra) | 15 | 100,00 | 100,00 |

### Vi-DROP — suy luận số học

| Phân tầng | n | EM | char-F1 |
| --- | --- | --- | --- |
| chọn thông tin (`selection`) | 41 | 92,68 | 94,35 |
| cộng/trừ (`add_sub`) | 55 | 58,18 | 77,28 |
| so sánh (`comparison`) | 57 | 61,40 | 72,02 |
| đếm (`count`) | 40 | 47,50 | 56,28 |
| khác (`other`) | 7 | 28,57 | 60,48 |

Chi tiết phân rã 79 câu bị bác: [`vidrop-cluster-breakdown.md`](vidrop-cluster-breakdown.md).

---

## Ba điểm rút ra

**1. Khoảng cách giữa hai nguồn là thật, không phải nhiễu.**
Vi-SQuAD 97,50% vs Vi-DROP 63,00% — chênh **34,5 điểm**. Cả hai đều 200 câu, cùng model,
cùng điều kiện. Khác biệt duy nhất là **dạng câu hỏi**: trích xuất văn bản vs tính toán nhiều bước.

**2. char-F1 cao hơn EM ở Vi-DROP gần 11,5 điểm — và đó là thông tin, không phải lỗi.**
Vi-DROP 63,00 → 74,49. Nghĩa là có những câu trả lời **gần đúng về hình thức nhưng sai nội dung**.
Ví dụ rõ nhất: item 316 trả lời `ít hơn` trong khi đáp án là `nhiều hơn` — đảo chiều hoàn toàn
nhưng hai chuỗi rất giống nhau về ký tự. **Báo cáo chỉ EM sẽ mất thông tin; chỉ báo cáo char-F1
sẽ tô hồng kết quả.** Phải báo cả hai.

**3. "Reasoning" là nhãn quá rộng để hữu ích.**
Trong Vi-DROP, `selection` đạt 92,68% còn `count` chỉ 47,50%. Gộp chung thành "model yếu về
suy luận" là sai — model **mạnh ở chọn lọc thông tin**, **yếu ở đếm và số học nhiều bước**.

---

## Phụ lục A — accept-rate (không dùng để so sánh)

> Đây là con số **cũ**, giữ lại chỉ để đối chiếu lịch sử. Không được dùng trong phần kết quả.

| Nguồn | n | chấp nhận | bác bỏ | tỉ lệ chấp nhận |
| --- | --- | --- | --- | --- |
| Vi-SQuAD | 200 | 195 | 5 | 97,50% |
| Vi-DROP | 200 | 126 | 74 | 63,00% |
| Tổng | 400 | 321 | 79 | 80,25% |

**Vì sao phải tách khỏi bảng chính:** accept-rate và EM **trùng số** trên tập này (321/400)
không phải vì hai phép đo giống nhau, mà vì gold được sinh ra **từ chính** những câu được accept.
Đây là **vòng lặp tự xác nhận**, không phải một phép đo độc lập.

---

## Phụ lục B — hạn chế

1. **Một người duyệt, chưa có IAA.** Mục 0.4 của kế hoạch chưa làm.
2. **Gold thiên lệch thuận** như đã nói ở trên — 321/400 câu gold = output của model.
3. **Một lần chạy duy nhất.** Không có lần lặp để đo dao động giữa các lần chạy cùng điều kiện.
4. **Model không còn tái lập được.** `Qwen3.8-27B-Q4_K_M.gguf` đã rời endpoint
   (xem `MC-4` trong measurement card). Chạy lại cho cùng kết quả là **không thể** với
   hạ tầng hiện tại.
5. **Chưa so sánh với công bố nào.** Paper VMLU có bảng Vi-SQuAD/Vi-DROP, nhưng dùng
   **LLM-as-judge** chứ không phải EM/char-F1 → **không so trực tiếp được**.

---

## Nguồn số liệu

```
all_res/ollama_result/Qwen3_8-27B-Q4_K_M_gguf/reading_answers_Qwen3_8-27B-Q4_K_M_gguf.csv   # câu trả lời thô
all_res/ollama_result/Qwen3_8-27B-Q4_K_M_gguf/reading_scores_Qwen3_8-27B-Q4_K_M_gguf.csv    # điểm từng câu (script sinh)
all_res/ollama_result/Qwen3_8-27B-Q4_K_M_gguf/reading_summary_Qwen3_8-27B-Q4_K_M_gguf.csv   # bảng tổng hợp
review_records/review_nttung245_qwen3_8_27b_q4_k_m_gguf.csv         # quyết định duyệt
data/gold/review_gold_agreed.csv                                    # gold đóng băng (400 câu)
```

Sinh lại bằng:

```bash
.venv/bin/python code_benchmark/score_reading_eval.py
```
