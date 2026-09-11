# Mở rộng bench — bản dễ đọc

> **Nguồn số liệu:** VMLU-MQA + V-Bench, model Qwen3-8-27B Q4_K_M chạy local.
> **Cách làm:** tuần tự từ trên xuống. Mục sau chỉ được mở khi mục trước đã đạt dòng "**Xong khi**".
> **Trạng thái:** chưa làm (Not started).
>
> *Ghi chú: đây là bản diễn đạt lại cho dễ đọc. Nội dung yêu cầu giữ nguyên, không thêm không bớt.*

---

## Đọc trước: cả tài liệu này để làm gì?

Hiện tại ta có vài con số đang bị **trình bày như thể là kết quả năng lực của model**, nhưng thật ra chúng chỉ là **kết quả của cách ta đo**:

| Con số đang có | Thật ra nó là gì |
| --- | --- |
| "Độ chính xác đọc hiểu 80,25%" | Tỷ lệ **một người duyệt** bấm nút "chấp nhận" câu trả lời của model. Không phải độ chính xác. |
| "74 câu Vi-DROP sai" | **Đánh giá chủ quan của một người**, chưa có người thứ hai kiểm lại. |
| Điểm V-Bench 44,97 | Chỉ đúng với **một cách hỏi cụ thể**. Đổi cách hỏi, 42,2% câu đổi đáp án. |

Vì vậy tài liệu chia làm 5 mục, đi theo thứ tự:

```
Mục 0  Dọn lại mấy con số đang hiểu sai ở bộ dữ liệu CŨ (VMLU)
  │      → Xong mục 0 mới được đi tiếp
  ▼
Mục 1  Viết ra một "phiếu điều kiện đo" dùng chung cho mọi lần chạy sau
  │      → Xong mục 1 mới được chạy cái mới
  ▼
Mục 2  Thêm ĐÚNG MỘT bộ dữ liệu mới, có hình dạng khác  ← CẦN CHỌN A HOẶC B
  │      → Xong mục 2 mới được mở mục 3
  ▼
Mục 3  Đo hai mảng yếu đã lộ ra: Luật và Y
  │
  ▼
Mục 4  Bốn thứ ta CHƯA đo — ghi rõ là chưa đo, đừng gọi là năng lực chung
```

**Ba nguyên tắc xuyên suốt:**

1. **Tách "đo được" khỏi "tin được".** Con số do 1 người duyệt, hoặc do một cách hỏi cụ thể, thì phải ghi rõ nó phụ thuộc vào đâu.
2. **Chốt trước, nhìn sau.** Với mọi bộ dữ liệu mới: chốt danh sách câu hỏi + seed và commit **trước khi** xem đáp án hoặc xem bảng xếp hạng.
3. **Không ngoại suy.** Không cộng điểm giữa hai bộ khác dạng. Không lấy 10–20 câu làm đại diện cho cả một môn. Chỗ nào chưa đo được thì **ghi là chưa đo**, không điền số ước lượng.

---

## Bảng thuật ngữ

| Từ | Nghĩa |
| --- | --- |
| **accept-rate** | Tỷ lệ người duyệt chấp nhận câu trả lời của model (bấm "accept") |
| **single-rater** | Chỉ có **một** người duyệt, chưa có người thứ hai kiểm chéo |
| **EM** (Exact Match) | Trả lời **trùng khít** đáp án mẫu thì được 1 điểm, khác một chữ cũng 0 |
| **char-F1** | Điểm F1 tính theo ký tự — trả lời đúng một phần vẫn có điểm |
| **IAA** | Mức đồng thuận giữa hai người duyệt độc lập. Không có người thứ hai thì không có IAA |
| **pre-register** | Chốt trước: ghi danh sách câu hỏi + seed và commit **trước khi** nhìn đáp án |
| **manifest** | File danh sách câu hỏi đã chốt, kèm seed |
| **measurement card** | "Phiếu điều kiện đo" — ghi model, cách chạy, tham số, ngày chạy |
| **prompt style** | Cách hỏi model: `minimal` (hỏi tối giản) hay `detailed` (có kèm luật + ví dụ) |
| **valid / correct** | `valid` = gọi tool **đúng cú pháp**; `correct` = trả lời **đúng nội dung**. Hai chuyện khác nhau |
| **macro / micro** | macro = mỗi nhóm 1 phiếu rồi lấy trung bình; micro = tính theo số câu |
| **breakdown** | Bẻ nhỏ kết quả theo từng nhóm thay vì gộp lại một mối |
| **scope** | Phạm vi — cái gì nằm trong bài đo, cái gì nằm ngoài |
| **suite** | Một bộ dữ liệu kiểm tra hoàn chỉnh |

---

## Mục 0 — Dọn nợ của bộ dữ liệu cũ (VMLU) trước khi thêm bộ mới

**Lý do cả mục:** mấy con số đang có trong báo cáo hiện tại chưa phân biệt rõ đâu là *cách đo* và đâu là *năng lực model*. Phải sửa cách gọi tên trước, nếu không mọi báo cáo sau đều sai theo.

### 0.1 — Tách "80,25%" ra khỏi mọi chỗ gọi là "độ chính xác đọc hiểu"

- **Vấn đề:** 80,25% là **tỷ lệ một người duyệt bấm accept**, không phải độ chính xác của model.
- **Làm gì:** Trong bảng biểu và phần tóm tắt (abstract), chỉ được gọi nó là **accept-rate**, và phải ghi rõ nó là *tạm tính, do một người duyệt*. Muốn nói "độ chính xác" thì phải dùng **EM hoặc char-F1**.
- **Xong khi:** Không còn câu nào trong báo cáo chính đánh đồng accept-rate với độ chính xác đọc hiểu.
- [x] Đã làm
  - **Bằng chứng:** Báo cáo VMLU: abstract + Bảng 2 đã gọi đúng là **accept-rate**; thêm **Bảng 2b** cho EM/char-F1.

### 0.2 — Chấm lại 400 câu đã chốt bằng EM và char-F1

- **Vấn đề:** 400 câu này chưa có điểm EM/F1. Có gold thì mới chấm được.
- **Làm gì:** Dùng gold độc lập (đáp án đã hiệu đính, cộng với gold gốc nếu còn giữ) để chấm EM và char-F1. Tách riêng kết quả Vi-SQuAD và Vi-DROP.
- **Xong khi:** Có bảng đọc hiểu (RC) với đủ 3 cột: EM, char-F1, và số câu n — tách theo từng nguồn.
- [x] Đã làm
  - **Bằng chứng:** `code_benchmark/score_reading_eval.py` — EM **80,25%** / char-F1 **86,55%** (Vi-SQuAD 200 + Vi-DROP 200).

### 0.3 — Bẻ 74 câu Vi-DROP bị bác thành đúng 3 cụm

- **Vấn đề:** 74 câu này đang bị gọi chung chung là "reasoning", không nói được model yếu ở khâu nào.
- **Làm gì:** Chia thành đúng 3 cụm: **(a) cộng/trừ hai thành phần**, **(b) so sánh**, **(c) đếm**. Mỗi cụm phải có số lượng và ví dụ cụ thể.
- **Lưu ý:** 3 cụm này chỉ phủ 66/74 câu. 8 câu còn lại (`selection` 3, `other` 5) chưa biết xếp vào đâu — cần chốt cách xử lý.
- **Xong khi:** Có 3 con số đếm + ví dụ minh hoạ, không còn nhãn "reasoning" chung chung.
- [x] Đã làm
  - **Bằng chứng:** `docs/agents/vidrop-cluster-breakdown.md` — `add_sub 23 · comparison 22 · count 21` (66/74) + 8 câu ngoài cụm.

### 0.4 — Nhờ người thứ hai duyệt lại

- **Vấn đề:** Hiện chỉ có một người duyệt. Không ai kiểm chéo được.
- **Làm gì:** Nhờ một người thứ hai duyệt lại **toàn bộ 79 câu bị bác**, cộng thêm **một mẫu của các câu được chấp nhận**. Ghi lại mức đồng thuận (IAA).
- **Nếu không tìm được người thứ hai:** thì trong phần hạn chế của báo cáo phải ghi rõ dòng *"single-rater, chưa có IAA"*.
- **Xong khi:** Có hệ số IAA, **hoặc** có dòng ghi chú "single-rater, chưa IAA" trong phần limitations.
- [x] Đã làm
  - **Bằng chứng:** **Nhánh dự phòng:** chưa có người duyệt thứ hai. Đã ghi "single-rater, chưa có IAA" (`docs/agents/measurement-gaps.md` mục 6 + mục 4 báo cáo VMLU).

### 0.5 — Chạy nốt Vi-Dialog

- **Làm gì:** Chạy bộ Vi-Dialog cùng model, cùng cách phục vụ (serving), cùng seed như các lần trước.
- **Nếu không chạy:** thì phải ghi rõ một mục *"out of scope / chưa chạy"* trong báo cáo. Không được để trống.
- **Xong khi:** Có điểm Vi-Dialog, **hoặc** có mục ghi rõ "chưa chạy".
- [x] Đã làm
  - **Bằng chứng:** **Nhánh dự phòng:** chưa chạy. Đã ghi mục "chưa chạy" (`docs/agents/measurement-gaps.md` mục 5).

### 0.6 — Gom cả mục 0 thành một bảng đọc hiểu sạch

- **Làm gì:** Gom lại thành một bảng duy nhất, có EM/F1 + số câu n + số đếm thô. Con số accept-rate bị đẩy xuống phụ lục.
- **Xong khi:** Bảng chính có đủ EM/F1 + n + raw count; accept-rate chỉ còn trong phụ lục.
- [x] Đã làm
  - **Bằng chứng:** `docs/agents/reading-results-table.md` — bảng chính có EM/F1 + n + exact-raw; accept-rate xuống Phụ lục A.

---

## Mục 1 — Đóng băng điều kiện đo

**Lý do cả mục:** các lần chạy trước khác nhau ở nhiều thứ (cách hỏi, ngân sách token, ngày). Không có một phiếu chung thì không so sánh được, và người đọc không biết con số đến từ đâu.

### 1.1 — Viết file `measurement_card.md`

- **Làm gì:** Một file ghi đủ các thông tin sau cho mỗi lần chạy: model id, mức lượng tử hoá (Q4_K_M), endpoint, temperature (0), seed (42), ngân sách token, cách hỏi (`minimal` hay `detailed`), có dùng CoT hay không, và ngày chạy.
- **Xong khi:** File có trong repo, và **mọi báo cáo viết sau đó đều trích dẫn file này**.
- [x] Đã làm
  - **Bằng chứng:** `measurement_card.md` — card MC-1…MC-4 + quy tắc dùng. Có ghi cả sự kiện model rời endpoint.

### 1.2 — Cấm gộp điểm `minimal` với điểm `detailed`

- **Vì sao:** Thực nghiệm cho thấy đổi cách hỏi làm **42,2% câu đổi đáp án**. Gộp hai điều kiện lại là trộn hai phép đo khác nhau.
- **Làm gì:** Mỗi điều kiện là một hàng điểm riêng. Không được có cột kiểu "best of" (lấy điểm cao nhất trong hai).
- **Xong khi:** Mỗi điều kiện một hàng, không có cột "best of".
- [x] Đã làm
  - **Bằng chứng:** Quy tắc chốt trong `measurement_card.md` ("Cấm gộp MC-2 với MC-2b"); không bảng nào có cột "best of".

### 1.3 — Tách "gọi tool đúng cú pháp" khỏi "trả lời đúng nội dung"

- **Vấn đề:** `valid` (đúng cú pháp) không có nghĩa là `correct` (đúng nội dung).
- **Làm gì:** Làm thành hai bước riêng biệt, ghi ra hai file log riêng.
- **Xong khi:** Log tách riêng; bảng agentic ghi cả **tỷ lệ valid** và **tỷ lệ đúng nội dung**.
- [ ] Chưa làm

### 1.4 — Mọi lần chạy mới phải dán hash của measurement card

- **Làm gì:** Output của mỗi lần chạy có thêm field `measurement_card_hash`.
- **Xong khi:** Field `measurement_card_hash` xuất hiện trong output.
- [x] Đã làm
  - **Bằng chứng:** `measurement_card_hash` có trong mọi dòng `reading_summary_*.csv`; script thoát nếu thiếu card.

---

## Mục 2 — Thêm một bộ dữ liệu có hình dạng khác

> ⚠️ **Luật cứng: chọn A hoặc B. Không làm song song cả hai.**

**Lý do cả mục:** các bộ đang có (VMLU, V-Bench) cùng một hình dạng câu hỏi trắc nghiệm. Cần một bộ có hình dạng khác để biết model có làm được việc khác hay không.

### 2.1 — Chốt chọn A hay B

**A** = SEA-HELM track VI — gồm văn hoá, ngôn ngữ học, làm theo chỉ dẫn, an toàn.

**B** = *Vietnamese Function Calling Test* (2.899 mẫu) **hoặc** *SEATauBench* — trong đó SEATauBench kiểm tra phần **ngữ nghĩa** thay vì chỉ cú pháp, trên một schema khác với V-Bench.

- **Xong khi:** Có một dòng ghi rõ chọn gì và **lý do phải bám vào lỗ hổng cần lấp**, không phải bám vào kiểu "thấy thiếu suite nên thêm".
- [ ] Chưa làm

### 2.2 — Chốt danh sách câu hỏi + seed trước khi nhìn đáp án

- **Làm gì:** Pre-register manifest và seed, **rồi commit**, xong mới được xem gold hoặc xem script chấm điểm của ban tổ chức.
- **Xong khi:** Manifest đã commit với timestamp **sớm hơn** lần suy luận (infer) đầu tiên.
- [ ] Chưa làm

### 2.3 — Chạy đúng theo measurement card ở mục 1

- **Làm gì:** Chạy đúng điều kiện đã ghi trong card. **Không được sửa prompt** để cho ra kết quả gần với baseline đã công bố.
- **Xong khi:** Log chạy khớp với card.
- [ ] Chưa làm

### 2.4 — Công bố kết quả theo đúng hình dạng của bài đo

- **Làm gì:** Một bảng duy nhất. Nếu là bài gọi tool thì phải có cả *valid* và *đúng nội dung*.
- **Cấm:** Không được thêm cột so sánh với con số VMLU 73%.
- **Xong khi:** Có một bảng đúng yêu cầu trên.
- [ ] Chưa làm

---

## Mục 3 — Đo hai mảng đã lộ rõ là yếu

> Chỉ được mở mục này **sau khi mục 2 xong**.

### 3.1 — Mảng Luật

- **Vấn đề:** Kết luận "yếu về luật" hiện đang dựa trên 10–20 câu của một môn trong VMLU — quá ít để kết luận.
- **Làm gì:** Dùng **VietLegal** hoặc **VLSP 2025 LegalSLM**. Nếu bộ dữ liệu cho phép, tách riêng: nhớ điều luật / khái niệm, NLI, syllogism, và citation.
- **Cấm:** Không lấy 10–20 câu VMLU-MQA làm điểm đại diện cho cả mảng luật.
- **Xong khi:** Có số câu n đủ lớn hơn mẫu môn VMLU, và đã tách các dạng bài như trên (nếu suite hỗ trợ).
- [ ] Chưa làm

### 3.2 — Mảng Y

- **Làm gì:** Dùng **VM14K** public split. Đối chiếu với con số V-Bench medicine 38,78%.
- **Cách đối chiếu:** Chỉ được nói "cùng hướng" hoặc "khác hướng". **Không được trừ hai phần trăm cho nhau.**
- **Xong khi:** Có điểm VM14K, kèm một câu ghi rõ "không trừ hai phần trăm này với V-Bench".
- [ ] Chưa làm

---

## Mục 4 — Bốn thứ chưa đo: đừng gọi là năng lực tổng quát

**Lý do cả mục:** đây là những khía cạnh chưa có số. Nếu không đo thì phải nói thẳng là chưa đo, chứ không được suy diễn từ điểm trắc nghiệm.

### 4.1 — Hallucination (model bịa)

- **Làm gì:** Dùng **ViHallu**, chạy một split duy nhất, cùng measurement card ở mục 1.
- **Xong khi:** Metric gọi đúng tên của suite. **Không được nhét vào macro tiếng Việt.**
- [ ] Chưa làm

### 4.2 — Bias (định kiến)

- **Làm gì:** Dùng **ViBBQ**, nhưng phải lấy trục **đặc thù Việt Nam**, không chỉ lấy bản dịch của BBQ.
- **Xong khi:** Tách riêng trục dịch và trục nội địa.
- [ ] Chưa làm

### 4.3 — Safety: 4.000 câu V-Bench đang bị bỏ qua

- **Vấn đề:** Bộ V-Bench có 4.000 câu (hatespeech 2.000 + politics_easy 1.000 + politics_advanced 1.000) đang không được tính điểm.
- **Làm gì:** Chọn một trong hai: **(a)** chạy và công bố rõ phạm vi, hoặc **(b)** giữ nguyên trạng thái "ngoài phạm vi tính điểm" và ghi rõ như vậy.
- **Cấm:** Không được suy ra điểm an toàn từ điểm trắc nghiệm học thuật.
- **Xong khi:** Chọn một trong hai hướng trên và ghi rõ trong báo cáo.
- [ ] Chưa làm

### 4.4 — Sycophancy (model nịnh theo người hỏi)

- **Thực tế:** Tiếng Việt chưa có bộ dữ liệu tương đương ELEPHANT / BenSyc.
- **Làm gì:** Viết một đoạn ghi nhận **khoảng trống** này trong báo cáo.
- **Cấm:** Không được tự dựng vài chục câu rồi gọi đó là một benchmark.
- **Xong khi:** Có đoạn gap trong báo cáo, và **không có** mục "điểm sycophancy" tự chế.
- [x] Đã làm
  - **Bằng chứng:** `docs/agents/measurement-gaps.md` mục 1 — ghi gap, không tự chế suite.

---

## Tóm tắt thứ tự làm

```
Bước 1  Mục 0 (6 việc)  — dọn lại cách gọi tên các con số cũ
Bước 2  Mục 1 (4 việc)  — viết measurement_card.md + cấm gộp điều kiện
Bước 3  Mục 2 (4 việc)  — ★ CẦN BẠN QUYẾT: chọn A hay B
Bước 4  Mục 3 (2 việc)  — đo Luật + Y
Bước 5  Mục 4 (4 việc)  — ghi rõ 4 thứ chưa đo
```

**Tổng: 20 việc.** Trong đó **1 việc cần bạn quyết trước khi đi tiếp: mục 2.1 (chọn A hay B)**.

---

## Phụ lục — Hiện trạng repo (không thuộc tài liệu của thầy)

Đối chiếu ngày 2026-09-11:

| Mục | Trạng thái thực tế |
| --- | --- |
| 0.1 | `reading_answers_*.csv` **không có cột accept-rate** — con số 80,25% đang nằm ngoài pipeline |
| 0.2 | `eval_set_manifest.csv` có gold **0/400** → chưa chấm EM/F1 được |
| 0.3 | Số có sẵn, nhưng đang chia 5 nhóm chứ chưa gộp 3: `add_sub 23 · comparison 22 · count 21 · selection 3 · other 5` |
| 0.4 | `review_records/` chỉ có **1 annotator** (`nttung245`), 400 dòng: accept 321 / reject 79 |
| 0.5 | Vi-Dialog 210 hội thoại **chưa từng chạy** |
| 0.6 | — |
| 1.1 | `measurement_card.md` **chưa tồn tại** |
| 1.2–1.4 | Chưa có field hash trong output |
| 2.1 | Chưa quyết |
| 3.1 | **Dữ liệu đã sẵn sàng:** `v_legal_slsp/legal_slm/` — multichoice 146 + nli 150 + syllogism 144, đều có gold local |
| 4.3 | Đã xác minh: 4.000 câu đó có `choices: []` và `function: []` (rỗng), nằm ngoài `sample_submission.jsonl` |

**Số liệu đối chiếu được với thầy:** V-Bench medicine 38,78% (190/490) ✔ khớp với tài liệu.
