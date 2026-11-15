# Vì sao omp kém dsh khi tự tra luật (MC-112, MC-113, MC-114): phân tích cơ chế

Ngày 2026-11-15. **Phân tích thăm dò, không đăng ký trước.** Kết quả đăng ký nằm trong report của MC-113 và MC-114. Tài liệu này chỉ giải thích các kết quả đó và không thay đổi kết luận nào. Phân tích không gửi request mới. Nó đọc lại các file điểm đã đóng băng và nội dung request mà proxy đã ghi.

- Lệnh chạy: `.venv/bin/python -m code_benchmark.analyze_legal_agent_mechanism --markdown`. Kiểm thử: `code_benchmark/test_analyze_legal_agent_mechanism.py`, 20 test.
- Report: `all_res/diagnostic_legal_agent_v2/mechanism/mechanism_report.json`, sha256 `a37ee816…`. Thư mục này gitignored và tách khỏi thư mục report đăng ký.
- Kiểm tra đầu vào: điểm MC-114 khớp sha `793723d7…` trong report đăng ký. Điểm MC-112 (`01084c90…`), MC-113 (`303902b7…`) và B của MC-111 (`4e755671…`) khớp sha ghi trong protocol.

## Cách đo

Chỉ xét những câu đã xác định được điều luật chi phối: 225 câu trắc nghiệm (134 Legal MC và 91 câu luật VMLU) và 400 câu ViBidLQA. Mỗi lượt chạy được xếp vào đúng một bước trong chuỗi tìm → mở → đọc:

| Bước | Nghĩa |
|---|---|
| not_found | Không kết quả công cụ hay tham số nào nhắc tới file chứa điều luật |
| found_not_opened | Tên file đã xuất hiện trong kết quả tìm hoặc tham số, nhưng file không được đọc |
| opened_not_read | File đã được đọc, nhưng không lần đọc nào hiện dòng tiêu đề của điều luật |
| read | Một lần đọc đã hiện dòng tiêu đề của điều luật (`read` của MC-112) |

Với các lượt opened_not_read, lý do được xác định từ khoảng dòng mà kết quả đọc đã hiện:
- `after_shown`: điều luật nằm sau trang đã hiện;
- `before_shown`: điều luật nằm trước trang đã hiện;
- `elided_middle`: điều luật rơi vào đoạn giữa mà omp đã bỏ bớt.

Để trừ ảnh hưởng của độ khó, mỗi câu có một mốc không dùng công cụ, lấy trung bình 2 lần chạy trên đúng câu đó:
- B cho trắc nghiệm, lấy từ MC-111 cho Legal MC và từ MC-114 cho VMLU;
- C (closed-book) cho ViBidLQA.

Chỉ số **lift** là điểm của lượt chạy trừ đi mốc này.

Khoảng cách DSHF − OMPF được tách theo cách Oaxaca hai phần:
- **phần tỉ lệ đọc**: do hai arm đọc tới điều luật với tỉ lệ khác nhau;
- **phần trong cùng trạng thái**: do điểm khác nhau khi hai arm ở cùng trạng thái đọc hoặc chưa đọc.

Phép tách được làm hai lần: trên điểm thô và trên lift. Khoảng tin cậy 95% lấy bằng bootstrap theo câu: 2.000 lần lấy mẫu, seed 7. Trạng thái "đã đọc" không được gán ngẫu nhiên, nên phép tách chỉ cho thấy sự liên quan, không chứng minh nhân quả.

## Hành vi

| Mỗi lượt chạy | DSHF · trắc nghiệm | OMPF · trắc nghiệm | DSHF · ViBidLQA | OMPF · ViBidLQA |
|---|---|---|---|---|
| Số lần gọi công cụ | 5,13 | 3,62 | 4,56 | 3,51 |
| Trả lời ngay sau 1 lần gọi (%) | 3,1 | 28,1 | 13,8 | 20,5 |
| Không đọc file luật nào (%) | 9,6 | 46,5 | 32,4 | 33,4 |
| Số lần đọc file luật | 1,84 | 1,04 | 1,15 | 1,08 |
| Lần đọc lỗi do đoán sai tên file (% số lần đọc) | 6,0 | 16,8 | 3,9 | 17,4 |
| Có grep theo "Điều N" (%) | 14,0 | 6,9 | 28,9 | 17,3 |
| Token của request đầu, trung vị | 1.080 | 4.178 | 1.031 | 4.129 |
| Token lớn nhất trong lượt, trung vị | 18.453 | 15.989 | 14.695 | 17.722 |

Câu lệnh của cả hai arm giống nhau từng byte: "Trước khi trả lời, bạn phải dùng công cụ grep để tìm và công cụ read để đọc… Chỉ trả lời sau khi đã đọc quy định đó". Dù vậy, gần một nửa lượt trắc nghiệm của OMPF trả lời mà không đọc file luật nào.

omp khác dsh ở những điểm sau.
- **System prompt:** 8.641 ký tự, gồm quy ước RFC 2119 và các chỉ dẫn của agent lập trình. Ví dụ, khối `<critical>` có câu "Each response MUST advance the task" và "run the specific test". System prompt của dsh chỉ có 441 ký tự.
- **Lượt user:** omp chèn một `<system-reminder>` vào trước lượt user.
- **Tham số request:** omp gửi `chat_template_kwargs: {preserve_thinking: true}`. Cả hai harness đều chạy ở temperature 1.0.
- **Lệnh read:** read của omp hiện một trang rồi ghi chú `[Showing lines a-b of N. Use :N to continue]` (0,6–0,9 lần mỗi lượt). Đôi khi nó bỏ bớt đoạn giữa file (0,2–0,4 lần mỗi lượt).
- **Lệnh grep:** grep của omp kèm dòng ngữ cảnh và cắt dòng dài ở 768 ký tự.

Việc cắt dòng không che được điều luật, vì dòng tiêu đề điều luật dài nhất chỉ 312 ký tự.

## ViBidLQA (400 câu): khoảng cách nằm ở việc đọc tới đúng điều luật

| Bước (% lượt chạy; điểm F1; lift so với C) | DSHF | OMPF |
|---|---|---|
| not_found | 22,3; 10,6; −4,0 | 11,8; 11,0; −1,1 |
| found_not_opened | 14,0; 33,9; +20,0 | 26,0; 38,4; +23,2 |
| opened_not_read | 21,3; 28,5; +15,1 | 41,5; 20,6; +7,3 |
| read | 41,9; 46,4; +33,0 | 20,8; 41,0; +26,6 |
| Mở file, tính trên các lượt đã tìm thấy file (%) | 81,9 | 70,5 |
| Đọc tới điều luật, tính trên các lượt đã mở file (%) | 66,3 | 33,3 |

Kết quả tách khoảng cách 4,28 F1 [1,37; 7,34]:
- **Phần tỉ lệ đọc:** 3,38 [1,93; 5,14], tức **79%**. Tính trên lift thì là 3,24, tức 76%.
- **Phần trong cùng trạng thái:** 0,90 [−2,46; 4,16], khoảng tin cậy chứa 0.

Như vậy, khi đã đọc tới điều luật, hai harness cho điểm như nhau.

OMPF mở đúng file gần bằng DSHF nhưng thường không tới được điều luật. Có 332 lượt OMPF mở file mà không thấy điều luật:
- 271 lượt (82%): điều luật nằm **sau trang omp đã hiện**, và model không đi tiếp theo ghi chú "Use :N to continue";
- 42 lượt: điều luật nằm trước trang đã hiện;
- 14 lượt: điều luật nằm trong đoạn giữa bị bỏ bớt;
- 5 lượt: không xác định.

DSHF hay tìm thẳng tới điều luật bằng cách grep "Điều N" (28,9% so với 17,3%). Nó cũng tự chọn vị trí đọc (offset/limit). Trong 170 lượt mở file mà không thấy điều luật, DSHF đọc quá ngắn 101 lần và đọc nhầm đoạn phía sau 69 lần.

## Trắc nghiệm (225 câu có điều luật): khoảng cách không nằm ở việc đọc

| Bước (% lượt chạy; lift so với B) | DSHF · Legal MC | OMPF · Legal MC | DSHF · luật VMLU | OMPF · luật VMLU |
|---|---|---|---|---|
| not_found | 10,8; −3,4 | 20,1; −12,0 | 12,6; +23,9 | 19,2; 0,0 |
| found_not_opened | 19,8; −1,0 | 44,8; −2,1 | 17,6; +9,4 | 51,6; −4,3 |
| opened_not_read | 15,3; 0,0 | 11,9; −14,1 | 8,8; +25,0 | 10,4; +15,8 |
| read | 53,7; −1,0 | 23,1; −12,1 | 61,0; +16,7 | 18,7; +14,7 |

Tỉ lệ đọc chênh lệch lớn: 56,7% so với 21,3%. Bước hụt lớn nhất của OMPF là đã thấy tên file đúng nhưng không mở. Tỉ lệ mở trên các lượt đã tìm thấy file là 40,7%, so với 78,6% của DSHF.

Dù vậy, tỉ lệ đọc giải thích **rất ít** khoảng cách điểm. Kết quả tách khoảng cách 9,78 [4,67; 15,11] trên 225 câu:

| | Phần tỉ lệ đọc | Phần trong cùng trạng thái |
|---|---|---|
| Điểm thô | −1,10 [−4,79; 2,68] | 10,88 [4,57; 17,07] |
| Lift | 0,53 [−2,88; 4,15] | 9,25 [3,16; 15,14] |

Tách riêng từng tập:
- **Legal MC:** OMPF thấp hơn B trên cùng câu khoảng 12 điểm, dù đã đọc hay chưa. Điều này đúng cả khi omp đã hiện trọn điều luật, vì trong 90,6% lượt "read" của OMPF trọn điều luật đã được hiện. DSHF xấp xỉ B ở mọi bước.
- **Luật VMLU:** đọc tới điều luật giúp cả hai harness (lift +15 đến +17). Tính trên lift, phần tỉ lệ đọc chiếm khoảng **44%** khoảng cách: 6,51 [0,03; 14,31].

Khi xét theo B, có hai kiểu thay đổi. **Cứu** là trả lời đúng ở câu mà B sai cả 2 lần. **Làm hỏng** là trả lời sai ở câu mà B đúng cả 2 lần.

| | Cứu (82 lượt) | Làm hỏng (302 lượt) |
|---|---|---|
| DSHF | 45,1% | 10,6% |
| OMPF | 24,4% | 14,6% |
| DSH | 26,8% | 11,9% |

Tỉ lệ cứu của OMPF ngang DSH, vốn gần như không tìm kiếm. Như vậy, việc dùng công cụ trong omp gần như không giúp thêm câu nào.

Cách viết câu trả lời cuối cũng khác. Tỉ lệ chỉ ghi đúng một chữ cái là 67,5% ở OMPF, 46,5% ở DSHF và 99,6% ở DSH. DSHF hay trích điều luật rồi mới chọn đáp án. Nhưng riêng cách viết không giải thích được Legal MC: các lượt OMPF có viết lời giải thích vẫn thấp hơn B 7,1 điểm.

Một quan sát liên quan: DSH, tức dsh khi gần như không tìm kiếm, cũng thấp hơn B 7,7 điểm trên Legal MC (MC-112 đã ghi DSH kém B). Vậy chỉ riêng việc đặt câu hỏi vào một harness agent đã làm giảm điểm Legal MC. DSHF bù lại được nhờ đọc, còn OMPF thì không.

## Đọc tới điều luật rồi vẫn sai: có phải do model "quên"?

Phần này chỉ xét các lượt trắc nghiệm đã đọc tới điều luật. Trước hết cần lưu ý cỡ mẫu. Kết quả "đọc rồi vẫn kém B" chỉ có trên Legal MC và dựa trên ít lượt chạy:

| Lượt đã đọc tới điều luật | Số lượt (số câu); số lượt sai | Lift so với B [CI 95% theo câu] |
|---|---|---|
| OMPF · Legal MC | 62 (48); 17 | −12,1 [−21,6; −2,4] |
| DSHF · Legal MC | 144 (93); 21 | −1,0 [−7,8; 5,4] |
| OMPF · luật VMLU | 34 (27); 15 | +14,7 [2,8; 28,8] |
| DSHF · luật VMLU | 111 (71); 32 | +16,7 [5,4; 27,4] |
| OMPF · gộp | 96 (75); 32 | −2,6 [−10,8; 5,7] |

So trên cùng câu mà cả hai harness đều đã đọc tới điều luật, DSHF hơn OMPF ở 17 câu, kém ở 4 câu và hòa ở 44 câu (kiểm định dấu p = 0,007). Riêng Legal MC là 11, 1 và 29 câu (p = 0,006). Riêng luật VMLU là 6, 3 và 15 câu (p = 0,51).

"Quên" ở LLM không phải mất trí nhớ. Có hai cơ chế cụ thể:
- harness xóa bớt ngữ cảnh (compaction);
- sự chú ý loãng đi khi bằng chứng nằm sâu trong một ngữ cảnh dài ("lạc giữa ngữ cảnh").

Ngoài ra còn ba khả năng khác cần kiểm. Tất cả đều được kiểm trên request đã sinh ra câu trả lời cuối:

| Giả thuyết | Số liệu (OMPF; DSHF) | Kết luận |
|---|---|---|
| Harness xóa điều luật khỏi ngữ cảnh | Điều luật vẫn còn trong request cuối ở 100% lượt OMPF và 99,2% lượt DSHF | Loại |
| Điều luật nằm quá xa câu trả lời | Lệnh đọc điều luật thường là lệnh cuối cùng (trung vị 0 lệnh sau đó). Trung vị khoảng cách tới cuối ngữ cảnh: 6.435 ký tự (OMPF), 6.555 (DSHF). Request cuối dài khoảng 57.000 ký tự, tức khoảng 16k token, còn xa giới hạn 65k | Loại |
| Bị nhiễu bởi phiên bản khác của cùng văn bản | Có phiên bản khác trong ngữ cảnh: 22,9% (OMPF), 34,9% (DSHF). Riêng các lượt sai của OMPF: 25,0% | Loại |
| Bỏ qua bằng chứng, quay về hiểu biết sẵn có | Trên Legal MC, chỉ 1/17 câu OMPF trả lời sai trùng một câu trả lời của B. Ở 8/17 câu, B đúng cả 2 lần | Loại. Model rời xa cả bằng chứng lẫn hiểu biết sẵn có |
| Quên nhãn A–D vì phương án nằm ở đầu ngữ cảnh | Tỉ lệ chọn D (khi gold không phải D) của OMPF theo độ dài ngữ cảnh: 14,6% (2–10k token), 10,4% (10–25k), 12,8% (25k+). Không tăng theo độ dài | Loại |

Riêng trên Legal MC, đáp án đúng không bao giờ là D. OMPF chọn D ở 9,0% số lượt, so với B 3,4%, DSHF 4,5% và DSH 6,7%. D chiếm 42% số lượt OMPF trả lời sai. Đây là quan sát riêng của Legal MC. Trên luật VMLU, B cũng chọn D ở 20,5% số lượt khi gold không phải D, còn OMPF ở 16,5%.

**Kiểm tra bộ chấm.** Bộ trích đáp án đã khóa đôi khi đọc nhầm chữ cái trong câu trả lời có lời giải thích. Ví dụ, ở LG-0107 model viết "đáp án đúng là: A", nhưng bộ chấm lấy "C" từ "Phụ lục C". Để đo mức ảnh hưởng, mình đọc lại theo chữ cái model tự nêu. Chỉ tính khi mọi tín hiệu trong câu trả lời thống nhất ("đáp án là X", một dòng chỉ có chữ cái).

| | Điểm đăng ký → điểm theo chữ cái model tự nêu |
|---|---|
| DSHF · gộp | 77,44 → 78,46 (+7 câu, −2 câu) |
| OMPF · gộp | 68,50 → 69,11 (+4 câu, −1 câu) |

Khoảng cách M1 vì thế còn hơi bị đánh giá thấp: 8,94 điểm thành 9,35. Kết luận đăng ký không đổi.

**Kết luận của phần này.** omp không làm mất điều luật, và điều luật không nằm xa câu trả lời. Trên Legal MC, khi điều luật ngay trước mặt, model trong omp thường trả lời một chữ cái không khớp với cả điều luật lẫn hiểu biết của chính nó. Log không cho biết vì sao. Các khác biệt của bối cảnh omp vẫn là nghi phạm:
- system prompt kiểu agent lập trình;
- cờ `preserve_thinking`;
- `<system-reminder>` chèn vào lượt hỏi.

## Kết luận

1. **Với câu trả lời bằng đoạn trích (ViBidLQA):** khoảng cách giữa hai harness chủ yếu nằm ở khâu đọc, khoảng 3/4. Lệnh read của omp chỉ hiện trang đầu của file luật. Qwen 9B hiếm khi đọc tiếp theo ghi chú trang, nên 82% số lần đã mở đúng file vẫn không tới được điều luật. Khi đã đọc tới điều luật, hai harness cho điểm như nhau.
2. **Với trắc nghiệm:** OMPF đọc tới điều luật ít hơn hẳn. Nhưng khoảng cách điểm chủ yếu nằm ở cách model trả lời khi chạy trong omp, chứ không nằm ở chuyện tìm thấy điều luật. Trên Legal MC, OMPF thấp hơn B khoảng 12 điểm ngay cả khi đã thấy trọn điều luật (62 lượt). Trên cùng câu mà cả hai đều đã đọc, DSHF hơn OMPF ở 17 câu và kém ở 4 câu. Đây không phải do "quên" (xem mục trên).

   Log không đủ để tách nguyên nhân giữa các khác biệt sau:
   - system prompt agent lập trình lớn gấp 4 lần;
   - cờ `preserve_thinking`;
   - `<system-reminder>`;
   - kết quả grep nhiều nhiễu;
   - thói quen trả lời ngay sau một lần grep (28% lượt chạy).
3. **Với luận văn:** cùng một model 9B và cùng một thư mục văn bản, chỉ những chi tiết thiết kế harness đã làm điểm luật dao động 4–9 điểm. Đó là kích thước trang của lệnh read, độ dài system prompt và ngữ cảnh mà harness chèn vào. Vì vậy, khi so sánh agent, cần báo cáo harness như một biến của phép đo.

## Giới hạn

- Trạng thái đọc không được gán ngẫu nhiên. Phép tách Oaxaca có hai cách tính tham chiếu và hai cách này cho số khác nhau, nên cả hai đều được báo cáo.
- B của Legal MC lấy từ MC-111, một card khác. Chênh lệch B giữa các card đã được đăng ký là 2,24 điểm.
- Bước "found" được tính rộng: chỉ cần tên file xuất hiện trong kết quả hoặc tham số. Bước "read" dựa vào dòng tiêu đề của điều luật.
- Mỗi câu chỉ chạy 2 lần, và từng tập con khá nhỏ.

## Nếu muốn kiểm chứng (chưa làm, cần đăng ký trước)

- Chạy OMPF với system prompt tối giản trên 246 câu trắc nghiệm × 2 lần, khoảng 500 lượt. Thí nghiệm này kiểm tra giả thuyết system prompt ở phần trắc nghiệm.
- Chạy OMPF với trang read lớn hơn trên 400 câu ViBidLQA. Thí nghiệm này kiểm tra giả thuyết phân trang ở phần đoạn trích.
