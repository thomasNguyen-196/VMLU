# Luồng hành động của harness: sáu ô (Qwen, MiMo × DSHF, OMPF, OMPS)

Ngày 2026-11-21. **Phân tích khám phá, không đăng ký trước.** Báo cáo này nối tiếp báo cáo Pha 1b (`docs/research/legal-agent-flows-2026-11-20.md`, bốn ô), thêm hai ô OMPS của MC-117. Không có request nào được gửi.

**Lý do của báo cáo.** Chủ dự án yêu cầu: "quan trọng là ta phải quan sát flow log của harness… vì harness nào cũng call api tới model, cái quan trọng là actions nó thực hiện". Ba harness ở đây gọi cùng một API model. Thứ làm chúng khác nhau là những gì xảy ra quanh các lần gọi đó.

**Dữ liệu và công cụ.**
- **Ba nhánh, cùng 646 câu, lượt 1–2.**
  - DSHF: dsh 0.2.2-rc.1.
  - OMPF: omp 18.0.0 với prompt mặc định.
  - OMPS: omp 18.0.0 với prompt của dsh.
- **Nguồn:** Qwen lấy từ MC-112 đến MC-114 và MC-117; MiMo từ MC-116 và MC-117.
- **Cách dựng dòng thời gian:** `code_benchmark/harness_flow.py` (7 test) ghép luồng sự kiện của harness (`events.jsonl`) với log của proxy (`proxy_log.jsonl`) thành một dòng thời gian cho mỗi lượt.
- **Báo cáo:** `code_benchmark/analyze_harness_flows_mc117.py` (1 test) ghi `all_res/diagnostic_legal_agent_omp_prompt/flows/flow_report.json`, SHA-256 `56788384…`. Module này dùng lại phần mô tả từng ô của `analyze_harness_flows.py`. File đó được đăng ký bằng SHA-256 cùng MC-117 nên được giữ nguyên, và vẫn tái lập đúng từng byte báo cáo bốn ô của Pha 1b (`0344d454…`).
- **Prompt:** nguyên văn ba system prompt ở `docs/research/system-prompts-2026-11-21/`.

**Ký hiệu hành động:**

| Ký hiệu | Nghĩa |
|---|---|
| `G+` / `G0` / `Gx` | grep có kết quả / rỗng / lỗi |
| `F+` / `F0` | glob có kết quả / rỗng |
| `Rm` | đọc một khoảng do **model tự chọn** (`offset`/`limit`) |
| `Rh` | đọc một trang do **harness tự cắt** |
| `Re` | đọc mà omp **bỏ phần giữa** file |
| `R` | đọc cả file (dsh) |
| `Rx` | đọc lỗi |
| `C` | harness tự nén ngữ cảnh (compaction) |
| `A` | trả lời |

## 1. Hành động của model

| Trắc nghiệm (246 câu × 2) | Qwen DSHF | Qwen OMPF | Qwen OMPS | MiMo DSHF | MiMo OMPF | MiMo OMPS |
|---|---:|---:|---:|---:|---:|---:|
| Điểm (bộ chấm đăng ký) | 77,4 | 68,5 | 72,8 | 85,6 | 91,3 | 88,4 |
| Lệnh công cụ / lượt | 5,13 | 3,62 | **5,95** | 8,17 | 7,43 | 7,96 |
| grep / lượt | 2,50 | 1,93 | 2,66 | 5,10 | 5,23 | 5,36 |
| read / lượt | 1,88 | 1,09 | **2,30** | 1,86 | 1,43 | 1,54 |
| Lần đọc do model chọn khoảng | 77,8% | 63,5% | **84,3%** | 98,6% | 94,3% | 96,6% |
| Lần đọc do harness cắt trang | 0% | **32,4%** | 13,4% | 0% | 2,8% | 1,3% |
| Suy nghĩ ẩn (ký tự / lượt) | 0 | 0 | 0 | 4.546 | 7.668 | 9.051 |

| ViBidLQA (400 câu × 2) | Qwen DSHF | Qwen OMPF | Qwen OMPS | MiMo DSHF | MiMo OMPF | MiMo OMPS |
|---|---:|---:|---:|---:|---:|---:|
| Điểm (token-F1) | 32,6 | 28,3 | 34,1 | 51,3 | 58,6 | 49,6 |
| Lệnh công cụ / lượt | 4,56 | 3,50 | 4,38 | 4,63 | 4,09 | 4,42 |
| read / lượt | 1,22 | 1,11 | **1,76** | 1,12 | 0,94 | 1,01 |
| Lần đọc do model chọn khoảng | 79,6% | 57,8% | **79,9%** | 100% | 98,5% | 99,5% |
| Lần đọc do harness cắt trang | 0% | **41,8%** | 20,1% | 0% | 1,5% | 0,4% |
| grep rỗng (% số grep) | 47,4% | 38,7% | 34,3% | 12,7% | 10,5% | 12,4% |

- **Với prompt dsh, Qwen trong omp hành động gần như trong dsh.**
  - Ở trắc nghiệm, số lần đọc tăng hơn gấp đôi (1,09 lên 2,30), và tỉ lệ khoảng đọc do model tự chọn tăng từ 63,5% lên 84,3%.
  - Tỉ lệ trang do harness cắt giảm một nửa, nhưng vẫn chưa về 0 như ở dsh. Lý do: omp vẫn phân trang khi model đọc mà không đặt offset/limit, còn dsh thì không.
- **MiMo gần như không đổi:** vẫn tự chọn khoảng đọc ở 97–100% số lần đọc. Riêng phần suy nghĩ ẩn dài thêm khoảng 18% ở trắc nghiệm.
- **grep rỗng của Qwen ở ViBidLQA cao ở mọi nhánh** (34–47%). Nguyên nhân là câu hỏi ViBidLQA gốc không ở dạng NFC, và Qwen chép nguyên byte vào mẫu grep (`docs/research/legal-agent-interaction-2026-11-20.md`).

## 2. Những gì harness trả lại cho model

| | Qwen DSHF | Qwen OMPF | Qwen OMPS | MiMo DSHF | MiMo OMPF | MiMo OMPS |
|---|---:|---:|---:|---:|---:|---:|
| Trắc nghiệm: kết quả read (trung vị, ký tự) | 6.171 | **15.249** | 7.214 | 4.670 | 3.759 | 3.631 |
| Trắc nghiệm: lần đọc bị bỏ phần giữa | 0% | 16,1% | 9,2% | 0% | 0,9% | 0,3% |
| Trắc nghiệm: kết quả grep (trung vị, ký tự) | 2.476 | 3.570 | 3.562 | 1.061 | 2.985 | 3.140 |
| Trắc nghiệm: kết quả bị cắt / lượt | 0,06 | 1,35 | 1,84 | 0,63 | 2,60 | 2,95 |
| ViBidLQA: kết quả read (trung vị, ký tự) | 6.132 | **21.410** | 14.446 | 4.788 | 3.745 | 3.952 |
| ViBidLQA: lần đọc bị bỏ phần giữa | 0% | **40,0%** | 24,5% | 0% | 0,7% | 1,0% |

- **Khi model không tự đặt khoảng đọc, omp trả về một trang dài.** Với file lớn, omp còn bỏ phần giữa. Ở OMPF, kết quả đọc của Qwen dài gấp 2,5–3,5 lần ở dsh. Ở ViBidLQA, 40% số lần đọc bị bỏ phần giữa, nơi điều luật cần tìm thường nằm.
- **Prompt dsh giảm được nhưng không xóa hết hiện tượng này.** Ở OMPS, kết quả đọc của Qwen ngắn lại một nửa ở trắc nghiệm, nhưng vẫn 24,5% số lần đọc ViBidLQA bị bỏ phần giữa.
- **grep của omp trả về dài hơn dsh** (kèm dòng ngữ cảnh), ở mọi model và mọi prompt.

## 3. Những việc harness tự làm

| | Qwen DSHF | Qwen OMPF | Qwen OMPS | MiMo DSHF | MiMo OMPF | MiMo OMPS |
|---|---:|---:|---:|---:|---:|---:|
| Trắc nghiệm: lượt bị nén ngữ cảnh | 0% | 4,9% | **11,8%** | 0% | 14,0% | 15,4% |
| Trắc nghiệm: trả lời sau khi bị nén | 0% | 4,1% | **10,0%** | 0% | 12,0% | 12,8% |
| Trắc nghiệm: điểm khi trả lời sau khi bị nén | – | 55,0 | **32,7** | – | 71,2 | 73,0 |
| Ngôn ngữ của bản tóm tắt khi nén | – | vi 24 | vi 57, en 1 | – | vi 69 | vi 76 |
| Trắc nghiệm: request bàn giao / lượt | 0 | 0,11 | 0,23 | 0 | 0,29 | 0,34 |
| Trắc nghiệm: lượt có thông báo cắt bớt ngữ cảnh | 0% | 0,2% | 0,6% | 0% | 2,2% | 2,2% |
| Trắc nghiệm: lượt harness kết thúc không có đáp án (`error`) | 3 | 0 | **13** | 1 | 5 | 7 |
| ViBidLQA: lượt bị nén ngữ cảnh | 0% | 0,9% | 2,6% | 0% | 1,5% | 1,9% |
| ViBidLQA: điểm khi trả lời sau khi bị nén | – | 7,6 | 18,4 | – | 37,5 | 10,9 |

- **Nén ngữ cảnh chỉ có ở omp, và nó luôn có hại.** Khi ngữ cảnh chạm khoảng 56.000 token, omp gửi một request bàn giao (`tool_choice: none`) để model tự tóm tắt. Sau đó nó thay toàn bộ ngữ cảnh bằng bản tóm tắt ("Context replaced…"). Câu trả lời sau khi bị nén kém hơn rõ: Qwen 33–55 điểm, MiMo 71–73 điểm ở trắc nghiệm.
- **Đọc nhiều hơn thì bị nén nhiều hơn.** Ở OMPS, Qwen bị nén gấp hơn hai lần (4,9% lên 11,8%), và những lượt đó chỉ đạt 32,7 điểm. Một phần lợi của việc đọc kỹ hơn bị mất ở đây. Cũng vì gọi nhiều lệnh hơn, 13 lượt Qwen ở trắc nghiệm chạm trần 30 request; proxy từ chối các request tiếp theo, nên các lượt đó không có đáp án. Ở MiMo, các lượt `error` gồm lượt chạm trần request và lượt omp tự dừng (`harness_end`).
- **dsh không có hành động tự khởi xướng nào trong các lượt này.** Không nén, không bàn giao. Lượt dsh kết thúc bất thường chủ yếu vì câu trả lời chạm trần token đầu ra (`max-tokens`, tức `answer_cap`: Qwen 13 lượt, MiMo 27 lượt ở trắc nghiệm).

## 4. Câu trả lời đến từ đâu

Nguồn của câu trả lời là kết quả công cụ cuối cùng trước khi model trả lời. Bảng ghi tỉ lệ số lượt, kèm điểm trong ngoặc.

| Trắc nghiệm | Sau read | Sau grep | Không có đáp án |
|---|---|---|---|
| Qwen DSHF | 81,3% (81,3) | 12,8% (76,2) | 3,3% |
| Qwen OMPF | 48,4% (61,8) | **51,0%** (74,9) | 0,2% |
| Qwen OMPS | 65,2% (73,5) | 31,7% (76,9) | 2,6% |
| MiMo DSHF | 71,3% (92,9) | 22,2% (83,5) | 5,7% |
| MiMo OMPF | 67,1% (93,9) | 30,1% (88,5) | 1,0% |
| MiMo OMPS | 63,8% (95,9) | 32,9% (80,9) | 1,4% |

- **Ở OMPF, Qwen trả lời ngay sau grep ở một nửa số lượt.** Khi nó có đọc, điểm lại thấp (61,8), vì kết quả đọc là trang dài do omp cắt. Ở OMPS, tỉ lệ trả lời ngay sau grep giảm còn 31,7%, và điểm khi đã đọc tăng lên 73,5.
- **Với MiMo, nguồn của câu trả lời gần như không đổi giữa ba nhánh.** Khác biệt về điểm của MiMo nằm ở cách viết câu trả lời (phân tích sau MC-117), không ở việc nó đọc gì.

## 5. Chuỗi hành động thường gặp

Mỗi ô có năm chuỗi hành động hay gặp nhất, kèm tỉ lệ số lượt và điểm.

| Trắc nghiệm | Chuỗi thường gặp |
|---|---|
| Qwen DSHF | `G+ Rm A` 20,5% (77,2); `G+ R A` 6,9% (94,1); `G+ Rmx2 A` 4,5%; `G0 G+ Rm A` 3,9%; `G+x2 Rm A` 3,3% |
| Qwen OMPF | **`G+ A` 27,0%** (74,4); `G+ Rm A` 8,1% (62,5); `G0 G+ A` 4,1%; `G+x2 A` 3,7%; `G+ Rh A` 2,8% (64,3) |
| Qwen OMPS | **`G+ Rm A` 15,2%** (78,7); `G+ A` 13,8% (77,9); `G0 G+ Rm A` 3,5%; `G+ Rmx2 A` 3,0%; `G+ Rh A` 1,8% |
| MiMo DSHF | `G+ F+ Rm A` 7,9% (97,4); `G+ F+ Rmx2 A` 6,7%; `G+x2 Rm A` 5,5%; `G+x2 Rmx2 A` 3,9%; `G+ F+ G+ Rm A` 3,3% |
| MiMo OMPF | `G+x2 Rm A` 13,6% (97,0); `F+ G+ Rm A` 7,1% (100); `G+x2 Rmx2 A` 5,5%; `G+x2 A` 3,7%; `F+ G+x2 Rm A` 3,3% |
| MiMo OMPS | `F+ G+ Rm A` 10,2% (98,0); `G+x2 Rm A` 7,7% (97,4); `G+x2 Rmx2 A` 5,5%; `F+ G+ Rmx2 A` 3,3%; `F+ G+x2 Rm A` 3,0% |

| ViBidLQA | Chuỗi thường gặp |
|---|---|
| Qwen DSHF | `G+ Rm A` 9,9%; `G0 G+ Rm A` 9,1%; `G0 A` 7,8% (12,8); `G+ A` 5,6%; `G0 G+ A` 2,0% |
| Qwen OMPF | `G+ A` 17,4%; `G+ Rm A` 7,5%; **`G+ Re A` 5,6%** (25,8); `G0 G+ A` 3,1%; `G0 F+ Re A` 3,0% |
| Qwen OMPS | `G+ A` 17,0%; `G+ Rm A` 8,4%; `G0 G+ A` 3,4%; `G+ Re A` 3,2% (18,1); `G0 G+ Rm A` 3,1% |
| MiMo DSHF | `G+ F+ Rm A` 13,4%; `G+x2 Rm A` 11,9%; `F0 G+ Rm A` 7,9%; `G+ F0 Rm A` 7,0%; `F+ G+ Rm A` 5,0% |
| MiMo OMPF | `G+x2 Rm A` 24,6% (57,5); `F+ G+x2 Rm A` 13,6% (66,0); `F+ G+ Rm A` 8,5%; `G+x3 Rm A` 4,1%; `F+ G+x2 A` 3,1% |
| MiMo OMPS | `F+ G+x2 Rm A` 21,2% (53,6); `F+ G+ Rm A` 15,4%; `G+x2 Rm A` 15,2%; `F+ G+x2 A` 3,5%; `F+ G+x3 Rm A` 2,5% |

- **Chuỗi phổ biến nhất của Qwen trong omp đổi theo prompt.** Với prompt omp, đó là `G+ A` (tìm rồi trả lời luôn). Với prompt dsh, đó là `G+ Rm A` (tìm, tự chọn khoảng đọc, rồi trả lời).
- **MiMo giữ cùng kiểu chuỗi ở cả ba nhánh:** vài lần grep hoặc glob, rồi đọc một khoảng tự chọn. Ở OMPS, MiMo mở đầu bằng glob (`F+`) nhiều hơn.

## 6. Hai nhánh tách nhau ở bước nào (cùng câu, cùng lượt)

| | Chuỗi trùng hoàn toàn | Bước tách nhau (trung vị) | Cặp khác biệt phổ biến nhất ở bước tách |
|---|---:|---:|---|
| Qwen: OMPF so với DSHF (trắc nghiệm) | 5,7% | 1 | DSHF `G+` / OMPF `G0` 17,7%; `G0`/`G+` 13,6%; DSHF `Rm` / OMPF `A` 13,0% |
| Qwen: OMPS so với OMPF (trắc nghiệm) | 11,4% | 1 | OMPF `G0` / OMPS `G+` 16,5%; `G+`/`G0` 14,6%; OMPF `A` / OMPS `Rm` 8,7% |
| MiMo: OMPF so với DSHF (trắc nghiệm) | 3,7% | 0 | DSHF `F+` / OMPF `G+` 26,6%; `G+`/`F+` 15,9% |
| MiMo: OMPS so với OMPF (trắc nghiệm) | 8,9% | 0 | OMPF `G+` / OMPS `F+` 20,7%; `G+`/`G0` 13,4% |
| Qwen: OMPS so với OMPF (ViBidLQA) | 9,4% | 0 | OMPF `G0` / OMPS `G+` 18,6%; `G+`/`G0` 12,4%; OMPF `Rx` / OMPS `G+` 7,0% |
| MiMo: OMPS so với OMPF (ViBidLQA) | 19,6% | 0 | OMPF `G+` / OMPS `F+` 24,8% |

- **Phần lớn các cặp đã khác nhau ngay từ lệnh đầu tiên hoặc thứ hai,** thường chỉ ở mẫu grep, vì model lấy mẫu ở nhiệt độ 1,0. Vì vậy so sánh từng bước có nhiễu lớn.
- **Khác biệt đặc trưng của prompt nằm ở cặp "OMPF `A` / OMPS `Rm`"** (8,7% số cặp trắc nghiệm của Qwen). Ở cùng một bước, với prompt omp Qwen trả lời luôn, còn với prompt dsh nó mở file ra đọc.

## Diễn giải

1. **Harness hành động khác nhau quanh cùng một lần gọi model, theo ba cách:**
   - **ai chọn khoảng đọc:** dsh luôn để model chọn; omp tự cắt trang và bỏ phần giữa khi model không chỉ định;
   - **trả lại bao nhiêu:** trang đọc và kết quả grep của omp dài hơn;
   - **tự làm gì:** chỉ omp tự nén ngữ cảnh.
2. **Một model nhỏ làm theo chỉ dẫn từng chữ, nên nó chịu tác động của các hành động này mạnh hơn.**
   - Qwen không tự đặt offset/limit khi prompt không nói rõ, nên chịu cách phân trang của omp.
   - MiMo tự đặt offset/limit gần như mọi lần, nên cách phân trang của omp không chạm tới nó.
3. **Đổi prompt làm đổi hành động của Qwen, nhưng không đổi hành động của omp.**
   - Prompt dsh khiến Qwen đọc theo kiểu của dsh.
   - Nhưng omp vẫn cắt trang khi Qwen quên chỉ định, vẫn trả kết quả dài, và vẫn tự nén khi ngữ cảnh đầy. Việc nén còn xảy ra nhiều hơn vì Qwen đọc nhiều hơn.

   Đó là lý do tương tác trên trắc nghiệm chưa về 0 dưới bộ chấm đăng ký.
4. **Luồng hành động của MiMo gần như không đổi giữa ba nhánh.** Khác biệt điểm của MiMo nằm ở câu trả lời cuối: độ dài và việc tuân thủ định dạng mà đề yêu cầu (`docs/research/legal-agent-omp-prompt-followup-2026-11-21.md`).

## Giới hạn

- **Liên hệ, không phải nhân quả.** Hành động của model trong mỗi lượt không được ngẫu nhiên hóa. Riêng việc đổi prompt (OMPS so với OMPF) là can thiệp có đăng ký trước.
- **Chỉ có hai lượt mỗi ô,** lấy mẫu ở nhiệt độ 1,0. So sánh từng bước giữa hai lượt có nhiễu lớn.
- **Phân loại "đọc do harness cắt trang" dựa trên ghi chú phân trang của omp.** Lượt đọc mà omp không ghi chú được xếp là đọc do model chọn khoảng hoặc đọc cả file.
