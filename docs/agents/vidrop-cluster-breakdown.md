# Vi-DROP — phân rã 79 câu bị bác

> Nguồn: `review_records/review_nttung245_qwen3_8_27b_q4_k_m_gguf.csv` (400 dòng, 1 người duyệt)
> và `all_res/ollama_result/reading_scores_Qwen3_8-27B-Q4_K_M_gguf.csv` (vừa chấm EM/F1).
> Bộc lộ: **79 câu bị bác trong tổng 400**, riêng Vi-DROP chiếm **74**.

Yêu cầu của thầy: bẻ 74 câu Vi-DROP bị bác thành **đúng 3 cụm**, không gộp chung là "reasoning".

> **Đơn vị:** cột `Bị bác` và `n` là **số nguyên** (đếm câu). Cột `EM` / `char-F1` là **tỉ lệ phần trăm
> trên cả cụm** — EM vẫn chỉ tính 0/1 cho mỗi câu, phần thập phân (`58,18`) đến từ phép chia
> `32/55`. Ví dụ cụm A: EM `58,18` ⇔ **32/55 câu đúng**, không phải "trung bình 0,58 điểm/câu".

---

## Ba cụm chính

| Cụm | n | Bị bác | Tỉ lệ bác | EM | char-F1 |
| --- | --- | --- | --- | --- | --- |
| **A. Cộng/trừ hai thành phần** (`add_sub`) | 55 | **23** | 41,8% | 58,18 | 77,28 |
| **B. So sánh** (`comparison`) | 57 | **22** | 38,6% | 61,40 | 72,02 |
| **C. Đếm** (`count`) | 40 | **21** | 52,5% | 47,50 | 56,28 |
| **Cộng 3 cụm** | **152** | **66** | 43,4% | 56,6 | 69,8 |

**66/74** câu bị bác nằm trong 3 cụm này. Còn **8 câu** nằm ngoài — xem phần cuối.

---

## Ví dụ từng cụm

### A. Cộng/trừ hai thành phần — 23 câu

Lỗi điển hình: **cộng sai đối tượng**, lấy tổng của một nhóm khác với câu hỏi.

| Item | Model trả lời | Gold |
| --- | --- | --- |
| 193 | `1.427.000` | `477.000 người` |
| 444 | `311.755` | `≈234.987` |

→ Không phải lỗi đọc hiểu: model **đọc đúng số** nhưng chọn sai **hai thành phần** để cộng/trừ.

### B. So sánh — 22 câu

Lỗi điển hình: **đảo chiều so sánh** hoặc chọn nhầm đối tượng đem so.

| Item | Model trả lời | Gold |
| --- | --- | --- |
| 174 | `15,00%` | `11,60% (nhóm từ 18 đến 24)` |
| 316 | `ít hơn` | `nhiều hơn` |

→ Item 316 là ca rõ nhất: trả lời **ngược hoàn toàn**. Đây là dạng mà EM phạt 0 nhưng char-F1 vẫn
cho điểm cao (hai chuỗi gần giống nhau về ký tự) — **một lý do phải báo cáo cả hai chỉ số**.

### C. Đếm — 21 câu

Lỗi điển hình: **đếm thiếu/đếm thừa đúng 1 đơn vị**.

| Item | Model trả lời | Gold |
| --- | --- | --- |
| 30 | `12` | `13` |
| 939 | `8` | `9` |

→ Sai lệch biên độ 1 hầu như luôn là **bỏ sót một mục** hoặc **đếm trùng một mục**.

---

## 8 câu nằm ngoài 3 cụm

Thầy yêu cầu đúng 3 cụm, nhưng dữ liệu có 5 phân tầng. 8 câu còn lại:

| Phân tầng | n bị bác | Ví dụ |
| --- | --- | --- |
| `selection` | 3 | item 3394: model `16945` → gold `31.381` |
| `other` | 5 | item 4531: model `Thấp hơn` → gold `cao hơn` |

**Đề xuất xử lý** (cần thầy xác nhận): giữ 3 cụm chính đúng như yêu cầu, và ghi 8 câu này
thành một dòng riêng *"ngoài 3 cụm"* trong bảng — **không** gộp chúng vào cụm nào,
vì `selection` (chọn thông tin có sẵn) là dạng **dễ nhất** (chỉ 3/41 bị bác) và trộn vào
sẽ làm sai lệch bức tranh về điểm yếu thật sự.

---

## Điều bảng này cho thấy

**Thứ tự yếu → mạnh đảo ngược hoàn toàn so với hình dung ban đầu.**

Nếu chỉ nói "Vi-DROP yếu vì reasoning" thì ta bỏ mất thông tin quan trọng:

- **Đếm** (`count`) là yếu nhất: 47,5% EM, hơn một nửa số câu bị bác (52,5%).
- **So sánh** (`comparison`) yếu thứ hai: hay đảo chiều.
- **Cộng/trừ** (`add_sub`) thực ra khá hơn hai cụm kia về EM, nhưng char-F1 cao (77,28) —
  tức trả lời **gần đúng số nhưng sai đối tượng**, một dạng sai mà EM phát hiện còn char-F1 thì không.
- **Chọn thông tin** (`selection`) là dạng **dễ nhất**: 92,68% EM, chỉ 3/41 câu bị bác.

Nói cách khác: model **không yếu ở "suy luận" nói chung**. Nó yếu ở **số học nhiều bước**
(đếm, cộng trừ đúng đối tượng) và **đảo chiều so sánh** — hai dạng rất khác nhau,
cần hai cách xử lý khác nhau. Gộp chung thành "reasoning" sẽ che mất cả hai.

---

## Cảnh báo kèm theo

1. **Một người duyệt, chưa có IAA.** Mọi con số trong bảng này là đánh giá của **một người**
   (mục 0.4 của kế hoạch chưa làm).
2. **Gold kế thừa từ output của model.** 321/400 câu accept có đáp án tham chiếu **chính là**
   câu trả lời của model → thiên lệch thuận. Chỉ 79 câu bị bác có đáp án do người viết.
3. **Một lần chạy, một model.** Không có lần chạy lặp nào để đo dao động.
