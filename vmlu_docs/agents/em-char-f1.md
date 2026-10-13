# Cách tính EM và char-F1

Tài liệu công thức cho hai chỉ số chấm điểm bài đọc hiểu 400 câu.
Nguồn duy nhất: `code_benchmark/score_reading_eval.py`. Mọi công thức dưới đây chép từ code đang chạy.

> Bối cảnh vận hành (chạy lệnh nào, đọc file nào, kết quả ra sao) nằm ở
> `docs/agents/score-reading-eval.md`. File này chỉ nói **toán**.

---

## 0.0 Đọc đơn vị trước khi đọc công thức

Cùng một tên `em` mang **hai nghĩa khác nhau** tuỳ tầng. Đây là chỗ dễ nhầm nhất của cả pipeline:

| Tầng | Field | Đơn vị | Miền giá trị | Ví dụ |
| --- | --- | --- | --- | --- |
| **Từng câu** | `em` trong `reading_scores_*.csv` | 0 hoặc 1 | `{0, 1}` | `1` |
| **Tổng hợp** | `em_count` trong `reading_summary_*.csv` | **số câu đúng** (số nguyên) | `0 … n` | `321` |
| **Tổng hợp** | `em` trong `reading_summary_*.csv` | **phần trăm** | `0 … 100` | `80.25` |

> ⚠️ **EM là nhị phân ở tầng từng câu.** Không tồn tại câu nào được 0,5 điểm EM.
> Nếu thấy một giá trị `em` lẻ ở tầng per-item → đó là **bug**, không phải thiết kế.

Con số thập phân (`80.25`) **không phải điểm của một câu** — nó là **tỉ lệ câu đúng**:

$$80{,}25\% = \frac{321}{400} \times 100$$

Tử số `321` vẫn là tổng của các số nguyên 0/1. Việc $321/400$ không chia hết chỉ làm
**thương** có phần thập phân, không làm điểm từng câu mất tính nhị phân.

### Ba chỉ số trông giống nhau nhưng khác bản chất

| Chỉ số | Cách tính | Bản chất |
| --- | --- | --- |
| **EM** = 80,25 | $321/400 \times 100$ | **tỉ lệ câu đúng tuyệt đối** — mỗi câu 0 hoặc 1 rồi lấy tỉ lệ |
| **char-F1** = 86,55 | $\frac{1}{400}\sum \mathrm{F1}_i$ | **trung bình của điểm bộ phận** — mỗi câu có thể được 0,53… |
| **accept-rate** = 80,25 | $321/400 \times 100$ | **tỉ lệ người duyệt bấm accept** — trùng số với EM do gold sinh từ chính câu accept |

EM và char-F1 **cùng in ra dạng phần trăm** nên nhìn giống nhau, nhưng EM không bao giờ
cho điểm từng phần còn char-F1 thì luôn cho. Đây chính là lý do phải báo cả hai (xem §4).

---

## 0. Tiền xử lý: `normalize_answer()`

Cả EM lẫn char-F1 đều so sánh trên dạng đã chuẩn hoá:

```python
s = unicodedata.normalize("NFC", s or "").strip().casefold()
s = re.sub(r"\s+", " ", s)                     # gộp mọi khoảng trắng thành 1 space
s = s.strip(" \t\n\r.,;:!?\"'()[]{}")          # cắt dấu câu ở HAI ĐẦU
```

Lưu ý: chỉ cắt dấu câu ở hai đầu chuỗi. Dấu câu **bên trong** (`"a, b"`, `"Kim Jong-nam"`)
sống sót và tham gia vào so khớp.

---

## 1. EM (Exact Match)

### 1.1 Công thức

$$\text{per-item:}\quad \mathrm{EM}_i \in \{0, 1\}$$

$$P = \text{canonical\_variants}(\text{pred}),\quad G = \text{canonical\_variants}(\text{gold})$$

$$\mathrm{EM}_i = \begin{cases} 1 & P \cap G \neq \emptyset \\ 0 & \text{ngược lại} \end{cases}$$

$$\text{tổng hợp:}\quad \mathrm{EM}_{\text{tập}} = \frac{1}{N}\sum_{i=1}^{N}\mathrm{EM}_i \times 100 \;(\%)$$

Không phải "trùng khít tuyệt đối". Gold là **văn bản tự do**
(`"Bằng nhau, mỗi quân đoàn có 3 sư đoàn"`), không phải span trích xuất, nên EM được
chấm bằng **giao hai tập biến thể tương đương**. Xem §0.0 về đơn vị: $\mathrm{EM}_i$ nhị phân,
còn con số báo cáo là tỉ lệ phần trăm.

### 1.2 `canonical_variants(s)` — tập biến thể

Gồm tối đa **3 nhánh**, hợp lại thành một set:

| # | Nhánh | Phép biến đổi | Ví dụ |
| --- | --- | --- | --- |
| 1 | Chuỗi chuẩn hoá | `normalize_answer(s)` | `"Bằng nhau"` → `"bằng nhau"` |
| 2 | Bỏ dấu | NFD rồi xoá combining marks (`strip_diacritics`) | `"bằng nhau"` → `"bang nhau"` |
| 3 | Số học | `to_number()` rồi in lại `f"{num:g}"` | `"30,40%"` → `"30.4"` |

Nhánh 3 chỉ sinh ra khi chuỗi **là một con số** (khớp `_PCT_RE`, `_NUM_RE`, hoặc `_GROUPED_RE`).

### 1.3 `to_number()` — parse số kiểu Việt Nam

Vì `,` và `.` đều có thể là dấu thập phân *hoặc* phân cách nghìn:

- **Cả hai cùng xuất hiện** → dấu **cuối cùng** là dấu thập phân, dấu còn lại là phân cách nghìn.
  - `"1.234,5"` → `1234.5`
  - `"1,234.5"` → `1234.5`
- **Chỉ một loại dấu** → đếm chữ số sau dấu:
  - Đúng **3 chữ số** và phần nguyên **không phải `"0"`** và không bắt đầu bằng `0` → hiểu là phân cách nghìn.
    - `"32.100"` → `32100`
    - `"1.000"` → `1000`
  - Ngược lại → dấu thập phân.
    - `"30.4"` → `30.4`
    - `"0.400"` → `0.4` (ngoại lệ có chủ ý: phần nguyên `"0"` thì chỉ có thể là thập phân)
- Dấu `%` bị cắt trước khi parse: `"30,40%"` → `"30,40"` → `30.4`

Nhờ vậy `30,4%`, `30.40%`, `30.4 %`, `30.4` cùng sinh ra form `"30.4"` → **EM bằng nhau**.

### 1.4 Ví dụ EM (chạy thật từ scorer)

| pred | gold | EM | `exact_raw` | Nhánh cứu điểm |
| --- | --- | --- | --- | --- |
| `473` | `473` | ✅ | ✅ | 1 (khớp nguyên văn) |
| ` 473 ` | `473` | ✅ | ✅ | 1 (whitespace bị nuốt ở normalize) |
| `30.40%` | `30,4%` | ✅ | ❌ | 3 (số: `30.4 == 30.4`) |
| `1000` | `1.000` | ✅ | ❌ | 3 (số: dấu chấm = phân cách nghìn) |
| `5` | `5,0` | ✅ | ❌ | 3 (số: `5.0 == 5.0`) |
| `bang nhau` | `bằng nhau` | ✅ | ❌ | 2 (bỏ dấu) |
| `Khong co cau tra loi` | `Không có câu trả lời` | ✅ | ❌ | 2 (bỏ dấu) |
| `Kim Jong-nam` | `Kim Jong Nam` | ❌ | ❌ | — gạch nối không được bỏ |
| `Bằng nhau, mỗi quân đoàn có 3 sư đoàn` | `bằng nhau mỗi quân đoàn có 3 sư đoàn` | ❌ | ❌ | — khác đúng **1 dấu phẩy**, vẫn 0 điểm |
| `Năm 1999` | `1999` | ❌ | ❌ | — có tiền tố, không phải số trần |
| `32.200` | `32.100` | ❌ | ❌ | — hai số khác nhau |
| `ít hơn` | `nhiều hơn` | ❌ | ❌ | — đảo chiều hoàn toàn |

### 1.5 `exact_raw` — cột chẩn đoán

```python
exact_raw = normalize_answer(pred) == normalize_answer(gold)   # chỉ nhánh 1
```

`exact_raw` = model trả lời **nguyên văn** đáp án tham chiếu. Cột này rẻ hơn EM
(không dùng tập biến thể) và dùng để kiểm tra gold có bị kế thừa từ output của model hay không.

Trên tập 400 câu của repo: `em != exact_raw` = **0 trường hợp** → chấm chặt hay chấm nới
cho **cùng kết quả**; con số không phụ thuộc vào quy tắc chuẩn hoá.

---

## 2. char-F1

### 2.1 Công thức

Chuẩn hoá hai vế trước, rồi so **đa tập ký tự** (multiset — không quan tâm thứ tự):

$$O = \sum_{c} \min\big(\text{count}_P(c),\ \text{count}_G(c)\big)$$

$$\text{Precision} = \frac{O}{|P|}, \qquad \text{Recall} = \frac{O}{|G|}, \qquad \text{F1} = \frac{2PR}{P+R}$$

trong đó $|P|$ là số ký tự của pred (sau chuẩn hoá), $|G|$ của gold.

Trong code là `Counter(p) & Counter(g)` — giao đa tập — rồi `sum(common.values())`.

### 2.2 Trường hợp biên

| Điều kiện | Kết quả | Ghi chú |
| --- | --- | --- |
| `p == ""` và `g == ""` | `1.0` | quy ước: hai bên cùng rỗng coi như khớp |
| một bên rỗng | `0.0` | |
| `overlap == 0` | `0.0` | short-circuit, tránh chia 0 |
| `p == g` | `1.0` | |

### 2.3 Ví dụ char-F1 (chạy thật từ scorer)

| pred | gold | char-F1 | Diễn giải |
| --- | --- | --- | --- |
| `473` | `473` | 1.0000 | khớp tuyệt đối |
| `ab` | `ba` | 1.0000 | ⚠️ đa tập giống hệt → **không phạt đảo thứ tự** |
| `Bằng nhau, mỗi quân đoàn có 3 sư đoàn` | `bằng nhau mỗi quân đoàn có 3 sư đoàn` | 0.9863 | thiếu 1 dấu phẩy |
| `Kim Jong-nam` | `Kim Jong Nam` | 0.9167 | khác 1 ký tự (`-` vs space) |
| `1000` | `1.000` | 0.8889 | EM cho 1 điểm nhưng F1 chỉ 0.89 (chuỗi khác) |
| `32.200` | `32.100` | 0.8333 | sai 2 ký tự, F1 vẫn cao |
| `Khong co cau tra loi` | `Không có câu trả lời` | 0.7500 | bỏ dấu làm F1 tụt dù EM = 1 |
| `30.40%` | `30,4%` | 0.7273 | EM = 1 nhưng F1 thấp |
| `Năm 1999` | `1999` | 0.6667 | tiền tố "Năm " ăn vào precision |
| `ít hơn` | `nhiều hơn` | 0.5333 | ⚠️ **đảo chiều hoàn toàn mà vẫn hơn 0.5** |
| `5` | `5,0` | 0.5000 | |
| `abc` | `xyz` | 0.0000 | |
| `` | `473` | 0.0000 | |

### 2.4 Hệ quả của thiết kế multiset

- **Cộng điểm oan**: đảo thứ tự từ/câu (item 316: `ít hơn` vs `nhiều hơn` — ngữ nghĩa
  ngược hoàn toàn, F1 = 0.53). Đây **không phải bug** — đó là lý do phải báo Song song EM và F1.
- **Bắt điểm oan**: `Khong co cau tra loi` vs `Không có câu trả lời` — EM đúng nhưng F1 chỉ 0.75,
  vì bỏ dấu làm mất ký tự. F1 **không** dùng nhánh bỏ dấu; chỉ EM mới có nhánh đó.
- Không có tokenization → không cần tách từ tiếng Việt; bù lại không phân biệt được
  "sai một từ" với "sai một ký tự".

---

## 3. Tổng hợp thành chỉ số toàn tập

Cả hai tính **trung bình theo câu** (macro over items), không phải gộp chung mọi ký tự:

$$\mathrm{EM}_{\text{tập}} = \frac{1}{N}\sum_{i=1}^{N} \mathrm{EM}_i \qquad\qquad \mathrm{charF1}_{\text{tập}} = \frac{1}{N}\sum_{i=1}^{N} \mathrm{F1}_i$$

Nên một câu trả lời dài không "nặng ký" hơn một câu trả lời ngắn.

**Cùng một công thức, hai kết quả khác bản chất:**

| | $\mathrm{EM}_i$ | $\mathrm{F1}_i$ |
| --- | --- | --- |
| Miền giá trị mỗi câu | $\{0, 1\}$ | $[0, 1]$ liên tục |
| Trung bình ra | **bội số của $1/N$** → phần thập phân chỉ đến từ phép chia | số thực bất kỳ |
| Kiểm tra tay | đếm số câu đúng rồi chia | không đếm được, phải chạy máy |

Với $N = 400$: EM chỉ có thể nhận các giá trị chia hết cho $0{,}25$ **sau khi nhân 100**
(bước nhảy nhỏ nhất của tỉ lệ là $1/400 = 0{,}25\%$). Riêng tập con lẻ (ví dụ phân tầng
$n = 41$) thì phần thập phân lẻ hơn — vẫn là hệ quả của phép chia, không phải điểm bộ phận.

Bảng tổng hợp còn xuất `em_count` và `exact_raw_count` (số đếm thô, **số nguyên**) để
kiểm tra lại bằng tay.

Tỉ lệ trong báo cáo nhân 100: EM **80,25%** · char-F1 **86,55%** trên 400 câu
(Vi-SQuAD 97,50 / 98,61 · Vi-DROP 63,00 / 74,49).

**Ví dụ kiểm tra tay** (làm được với EM, không làm được với char-F1):

```
reading_summary_*.csv   →  ALL, n=400, em_count=321
321 / 400 * 100         =  80.25            ✔ khớp cột `em`
```

---

## 4. Vì sao báo cả hai chỉ số

Khoảng cách EM→char-F1 là **thông tin**, không phải nhiễu:

| Chỉ báo EM | Chỉ báo char-F1 |
| --- | --- |
| Mất điểm oan cho câu đúng nội dung nhưng lệch hình thức (`Bằng nhau, ...` thiếu dấu phẩy) | Tô hồng câu sai nội dung nhưng giống hình thức (`ít hơn` vs `nhiều hơn`, F1 0.53) |
| Không đo được mức độ gần đúng | Đo được mức độ gần đúng |

Vi-DROP: EM 63,00 → char-F1 74,49 (**+11,5 điểm**). Chênh lệch đó gom đúng nhóm ít ỏi
"gần đúng vẻ ngoài, sai nội dung" — nhóm mà EM phát hiện còn F1 thì không.
Báo chỉ EM sẽ mất thông tin; báo chỉ F1 sẽ thổi phồng kết quả.

---

## 5. Cảnh báo khi so sánh với bên ngoài

- Paper VMLU gốc dùng **LLM-as-judge**, không dùng EM/char-F1 → **không so trực tiếp được**.
- Gold hiện tại của 321/400 câu **kế thừa từ chính output của model** (người duyệt bấm accept)
  → EM/char-F1 ở đây là **cận trên, thiên lệch thuận**, không phải điểm năng lực.
  Khác accept-rate ở chỗ: tham chiếu đã **cố định**, nên **so sánh được giữa các lần chạy**
  miễn là giữ nguyên tập gold này.
