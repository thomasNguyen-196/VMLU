# Trước và sau router: OMP, full tools, API trực tiếp và vòng tự sửa

Báo cáo ngày 2026-11-03, cập nhật ngày 2026-11-07 với VMLU Test của Qwen (MC-109) và ngày 2026-11-11 với VMLU Test của MiMo (MC-110c). File này đặt các điều kiện đo **trước khi có router** (OMP không tools, OMP full tools, API trực tiếp) cạnh kết quả **sau khi dùng router** (vòng tự sửa của MC-105), trên cùng các bộ dữ liệu của trang `/table`. Mọi con số được chép từ hai file mà `/table` hiển thị; báo cáo này không chấm lại gì (xem [Nguồn số liệu](#nguồn-số-liệu)).

## Tóm tắt

- **Sau router chỉ có cho Qwen3.5-9B và MiMo V2.6 Flash** (MC-105). MC-108 (Muse Spark 1.3 và 1.2) đã **dừng hẳn** ngày 2026-11-04, ở 1.639 và 2.165 lượt, vì bộ lọc nội dung của Meta liên tục từ chối prompt suy luận từng bước. Muse sẽ không có số sau (xem [Muse Spark: vì sao không có số sau](#muse-spark-vì-sao-không-có-số-sau)).
- **Vòng tự sửa tốt hơn hỏi thẳng rõ ràng ở 6/12 ô đã đăng ký**: VMLU valid, Vi-DROP và ViBidLQA test, ở cả hai model. Mức tăng lớn nhất ở Vi-DROP: Qwen +15,4 điểm, MiMo +22,0 điểm token-F1. Qwen còn tăng +12,1 điểm ở VMLU valid.
- **VMLU Test của Qwen (MC-109): 67,09% trước, 76,63% sau, tức +9,54 điểm** theo điểm vmlu.ai. Router chưa từng dùng 9.833 câu này lúc thiết kế, vì Test không có đáp án. vmlu.ai chỉ trả điểm theo môn nên không làm được phép thử theo cặp câu. Nhóm STEM tăng nhiều nhất (+16,95), nhất là các môn toán và vật lý (xem [VMLU Test của Qwen theo nhóm môn](#vmlu-test-của-qwen-theo-nhóm-môn-mc-109)).
- **VMLU Test của MiMo (MC-110c): 76,32% trước, 80,71% sau, tức +4,39 điểm** theo điểm vmlu.ai. MC-110c là MC-110 (trần 20.000 token) cộng với việc hỏi lại 538 lượt không ra câu trả lời ở trần 40.000 token; hai file của MC-110 không được nộp. MiMo hỏi thẳng đã gần bằng Qwen sau vòng tự sửa (76,32 so với 76,63), nên mức tăng chỉ bằng khoảng một nửa của Qwen (xem [VMLU Test của MiMo theo nhóm môn](#vmlu-test-của-mimo-theo-nhóm-môn-mc-110c)).
- **Vòng tự sửa không giúp ở Legal MC, Legal NLI và Vi-SQuAD.** Với Qwen ở Legal MC, sau còn thấp hơn trước 4,1 điểm (không có ý nghĩa thống kê, p = 0,55), vì suy luận từng bước (S) kém hỏi thẳng ở bộ này.
- **So với ba điều kiện của /table**, vòng tự sửa cao hơn điều kiện tốt nhất ở 15/16 ô (dưới Legal NLI của Qwen). Đây chỉ là so sánh mô tả: route, cài đặt và lượt chạy khác nhau, không có phép thử.
- **Full tools không phải là cách cải thiện.** Với Muse và MiMo, full tools gần ngang OMP không tools. Với Qwen, full tools thấp hơn hẳn (VMLU valid 58,7% so với 69,6%).
- **Chi phí:** vòng tự sửa tốn 1,9 đến 10,2 lần số token của hỏi thẳng, tuỳ ô. Ở Vi-DROP, chỉ dùng S (luôn S) còn cao hơn vòng tự sửa và rẻ hơn.
- **Trên câu mới (MC-104)**, vòng tự sửa của Qwen nâng trắc nghiệm từ 69,0% lên 76,3% (đạt). Với MiMo chỉ thêm 2,2 điểm, chưa chắc (không đạt).

## Các điều kiện so sánh

| Điều kiện | Model được hỏi qua | Cài đặt chính | Thẻ đo |
|---|---|---|---|
| **OMP · không tools** | Coding agent `omp` 18.0.0, JSON mode | Tools tắt; system prompt tối giản; mỗi câu một process, không giữ lịch sử. Temperature 1,0; thinking auto; không gửi seed. Trần output 4.096 token cho trắc nghiệm và 2.048 cho đọc hiểu; 4 workers. | VMLU: MC-62 (Muse 1.3), MC-74 + MC-79 (Muse 1.2), MC-63 (MiMo), MC-70 (Qwen). Legal và đọc hiểu: MC-53, MC-73, MC-54, MC-72 |
| **OMP · full tools** | Coding agent `omp` với đủ bộ tools (read, bash, web_search…) | System prompt mặc định của coding agent. Yêu cầu temperature 1,0, nhưng không xác minh được giá trị thực; reasoning effort không ghim. 20.000 token mỗi lượt; 12 workers. Timeout và cách chạy lại khác nhau giữa các model (300 đến 3.600 giây). **Chỉ mô tả, không dùng để xếp hạng.** Không chạy Legal MC. | MC-86 / R2 (Muse 1.3), MC-87 / R3 (Muse 1.2), MC-88 (Qwen), MC-89 (MiMo) |
| **API trực tiếp** | API của model, không qua harness (Muse qua 9Router) | Gửi temperature 1; reasoning theo mặc định của provider; trần 20.000 token output (MC-80 dùng trần nhỏ hơn); 12 workers. | MC-80 / MC-82 (Muse 1.3), MC-84 (Muse 1.2), MC-83 (Qwen), MC-85 (MiMo) |
| **Trước router** (hỏi thẳng B, cùng lượt chạy) | Qwen: IEC endpoint. MiMo: OpenCode Go | Prompt giống hệt /table. Qwen trắc nghiệm: probe với temperature 0, seed 42, 4 token, đọc log-probability. Qwen đọc hiểu: temperature 1,0. MiMo: mặc định của provider. | MC-105 (VMLU Dev: MC-104; VMLU Test: MC-109 với Qwen, MC-110c với MiMo) |
| **Sau router** (vòng tự sửa) | Như dòng trước | Xem phần dưới. Mọi câu trả lời cuối do chính model viết. | MC-105 (VMLU Dev: MC-104; VMLU Test: MC-109 với Qwen, MC-110c với MiMo) |

### Vòng tự sửa (dòng "Sau") chạy thế nào

1. **Hỏi thẳng (B).** Dùng đúng prompt của /table. Nếu model chắc chắn thì giữ đáp án và dừng.
   - Qwen làm trắc nghiệm: được coi là chắc khi xác suất của chữ cái nó chọn từ 0,80 trở lên.
   - MiMo, và cả hai model ở đọc hiểu: hỏi B hai lần, chắc khi hai lần cho cùng đáp án.
2. **Suy luận từng bước (S).** Nếu chưa chắc, hỏi S một lần. Nếu S trùng một câu trả lời B thì lấy đáp án đó và dừng.
3. **Bỏ phiếu.** Nếu vẫn lệch, hỏi S thêm hai lần và lấy đáp án nhiều phiếu nhất trong ba lần S. Hoà thì lấy lần sớm nhất; câu trả lời rỗng không được tính phiếu.

Mỗi câu được hỏi đủ mọi lượt, rồi quy tắc trên được tính lại từ các câu trả lời đã ghi. Nhờ vậy "Trước", "Sau" và "Luôn S" được so trên cùng một tập câu trả lời. Các lần hỏi độc lập với nhau: model không thấy câu trả lời trước của chính nó.

Riêng VMLU Test (MC-109 của Qwen, MC-110c của MiMo), để đỡ tốn lượt, mỗi lần hỏi chỉ được gửi khi quy tắc cần đến:
- S chỉ được hỏi khi probe chưa chắc (Qwen) hoặc khi hai lần B lệch nhau (MiMo);
- S lần 2 và 3 chỉ được hỏi khi S lệch B.

Vì các lần hỏi độc lập, đáp án cuối vẫn đúng như khi hỏi đủ rồi tính lại; phần kiểm thử đã đối chiếu điều này trên 3.000 trường hợp ngẫu nhiên. Nhưng S không được hỏi cho mọi câu, nên ô này không có dòng "Luôn S".

## Kết quả theo model

Cách đọc bảng:

- Trắc nghiệm (VMLU, Legal MC, Legal NLI) tính tỷ lệ đúng, %. Đọc hiểu (Vi-SQuAD, Vi-DROP, ViBidLQA test) tính token-F1 theo bộ chấm v3. Số câu: VMLU Test 9.833, Valid 744, Dev 303, Legal MC 146, Legal NLI 150, Vi-SQuAD 200, Vi-DROP 200, ViBidLQA test 603.
- Ô có ✓ là phép thử chính đạt: p sau hiệu chỉnh Holm trên 12 ô nhỏ hơn 0,05 và sau cao hơn trước. Trắc nghiệm dùng McNemar chính xác; đọc hiểu dùng phép thử đổi dấu trên chênh lệch F1 theo cặp câu.
- "Sau − điều kiện /table cao nhất" lấy điểm cao nhất trong ba dòng OMP không tools, OMP full tools và API trực tiếp. Dòng này chỉ để mô tả, không có phép thử.
- Cột "Thẻ đo" ghi hai thẻ khi các cột VMLU lấy từ thẻ đầu và các cột còn lại lấy từ thẻ sau.
- VMLU Test chỉ vmlu.ai chấm được. Router đã chạy trên Test cho Qwen (MC-109) và MiMo (MC-110c): chủ dự án nộp file trước và file sau lên vmlu.ai. Điểm tổng của vmlu.ai là trung bình cộng của 58 môn. vmlu.ai không trả kết quả từng câu, nên ô này không có phép thử.

### Qwen3.5-9B-65K

| Điều kiện | Thẻ đo | VMLU Test | VMLU Valid | VMLU Dev | Legal MC | Legal NLI | Vi-SQuAD | Vi-DROP | ViBidLQA test |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OMP · không tools | MC-70 / MC-72 | 63,86 | 69,62 | 71,29 | 84,25 | 90,67 | 89,08 | 56,40 | 64,85 |
| OMP · full tools | MC-88 | 53,43 | 58,74 | 55,78 | — | 78,67 | 82,99 | 53,98 | 59,65 |
| API trực tiếp | MC-83 | 62,94 | 68,55 | 69,97 | 83,56 | 91,33 | 90,00 | 54,58 | 66,01 |
| Trước router: hỏi thẳng B, cùng lượt chạy | MC-105 (Dev: MC-104, Test: MC-109) | 67,09 ⁵ | 69,89 | 73,60 | 91,10 ³ | 90,67 | 89,74 | 54,27 | 64,99 |
| **Sau router: vòng tự sửa** | MC-105 (Dev: MC-104, Test: MC-109) | **76,63** ⁵ | **81,99** | **80,53** | **86,99** | **89,33** | **90,03** | **69,66** | **69,74** |
| Sau − trước (điểm) | phép thử chính | +9,54 ⁵ | **+12,10** ✓ | +6,93 | −4,11 | −1,34 | +0,29 | **+15,39** ✓ | **+4,75** ✓ |
| p sau Holm (12 ô) | | — ⁵ | < 0,001 | — ¹ | 0,55 | 1,00 | 1,00 | < 0,001 | < 0,001 |
| Sau − điều kiện /table cao nhất (mô tả) | | +12,77 | +12,37 | +9,24 | +2,74 | −2,00 | +0,03 | +13,26 | +3,73 |
| Luôn S (tham khảo) | MC-105 | — | 80,38 | 79,54 | 82,88 | 83,33 | 89,81 | 75,41 | 67,63 |
| Token/câu: trước → sau | | 132 → 1660 | 124 → 1265 | 120 → 1032 | 223 → 1107 | 302 → 583 | 446 → 1255 | 328 → 1562 | 818 → 3211 |

### MiMo V2.6 Flash

| Điều kiện | Thẻ đo | VMLU Test | VMLU Valid | VMLU Dev | Legal MC | Legal NLI | Vi-SQuAD | Vi-DROP | ViBidLQA test |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OMP · không tools | MC-63 / MC-54 | 76,20 | 80,24 | 83,17 | 81,51 | 86,67 | 86,97 | 50,67 | 74,84 |
| OMP · full tools | MC-89 | 79,60 | — ² | 82,84 | — | 87,33 | 83,23 | 52,33 | 71,05 |
| API trực tiếp | MC-85 | 77,68 | 79,84 | 81,85 | 89,73 | 88,00 | 86,83 | 58,38 | 75,63 |
| Trước router: hỏi thẳng B, cùng lượt chạy | MC-105 (Dev: MC-104, Test: MC-110c) | 76,32 ⁶ | 77,82 | 81,85 | 91,78 | 89,33 | 88,95 | 53,99 | 72,92 |
| **Sau router: vòng tự sửa** | MC-105 (Dev: MC-104, Test: MC-110c) | **80,71** ⁶ | **83,20** | **83,83** | **92,47** | **88,67** | **91,29** | **76,02** | **78,08** |
| Sau − trước (điểm) | phép thử chính | +4,39 ⁶ | **+5,38** ✓ | +1,98 | +0,69 | −0,66 | +2,34 | **+22,03** ✓ | **+5,16** ✓ |
| p sau Holm (12 ô) | | — ⁶ | < 0,001 | — ¹ | 1,00 | 1,00 | 0,13 | < 0,001 | < 0,001 |
| Sau − điều kiện /table cao nhất (mô tả) | | +1,11 | +2,96 | +0,66 | +2,74 | +0,67 | +4,32 | +17,64 | +2,45 |
| Luôn S (tham khảo) | MC-105 | — | 82,39 | 83,83 | 91,78 | 89,33 | 90,56 | 77,61 | 76,60 |
| Token/câu: trước → sau | | 866 → 3115 | 383 → 1217 | 363 → 1021 | 453 → 1169 | 494 → 1034 | 519 → 1489 | 477 → 2234 | 389 → 1406 |

### Muse Spark 1.3

| Điều kiện | Thẻ đo | VMLU Test | VMLU Valid | VMLU Dev | Legal MC | Legal NLI | Vi-SQuAD | Vi-DROP | ViBidLQA test |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OMP · không tools | MC-62 / MC-53 | 87,04 | 91,13 | 91,09 | 93,15 | 80,00 | 89,01 | 73,86 | 76,89 |
| OMP · full tools | MC-86 / R2 | 87,53 | 90,99 | 90,76 | — | 82,00 | 89,37 | 75,00 | 77,91 |
| API trực tiếp | MC-80, MC-82 ⁴ | 88,41 | 91,40 | 92,41 | 93,15 | 80,00 | 86,11 | 76,31 | 77,17 |
| **Sau router** | MC-108 (dừng hẳn) | — | không có | không có | không có | không có | không có | không có | không có |

### Muse Spark 1.2

| Điều kiện | Thẻ đo | VMLU Test | VMLU Valid | VMLU Dev | Legal MC | Legal NLI | Vi-SQuAD | Vi-DROP | ViBidLQA test |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OMP · không tools | MC-74 + MC-79 / MC-73 | 87,41 | 90,32 | 91,09 | 95,21 | 85,33 | 82,54 | 37,98 | 70,36 |
| OMP · full tools | MC-87 / R3 | 87,94 | 91,53 | 91,75 | — | 86,67 | 82,71 | 37,75 | 69,06 |
| API trực tiếp | MC-84 | 87,49 | 90,99 | 90,76 | 95,21 | 81,33 | 83,20 | 39,31 | 71,66 |
| **Sau router** | MC-108 (dừng hẳn) | — | không có | không có | không có | không có | không có | không có | không có |

Chú thích:

1. VMLU Dev lấy từ MC-104 và không thuộc 12 ô của MC-105, nên không có phép thử riêng. Phép thử của MC-104 gộp VMLU Dev với VM14K (xem phần dưới).
2. MC-89 của MiMo có VMLU Valid 80,48% nhưng chỉ trên 743/744 câu, nên /table không hiển thị ô này.
3. Hỏi thẳng của Qwen ở trắc nghiệm trong MC-105 là probe: temperature 0, seed 42, 4 token. Vì vậy Legal MC đạt 91,10%, cao hơn hẳn 84,25% và 83,56% của OMP và API trực tiếp, vốn chạy ở temperature 1,0. Hệ quả: so với hỏi thẳng cùng lượt, vòng tự sửa kém 4,11 điểm, nhưng so với số /table lại hơn 2,74 điểm. Phép thử chính dùng mốc cùng lượt.
4. Muse 1.3 API trực tiếp: VMLU Test và Dev lấy từ MC-82, VMLU Valid từ MC-80. Các bộ Legal và đọc hiểu lấy từ MC-80, có 7 câu chạy lại trong MC-82.
5. VMLU Test của Qwen lấy từ MC-109 (chạy từ 2026-11-05 đến 2026-11-07), do vmlu.ai chấm.
   - "Trước" là probe của cùng lượt chạy (temperature 0, seed 42, 4 token, như chú thích 3). "Sau" là vòng tự sửa, hỏi theo từng vòng.
   - vmlu.ai chỉ trả điểm theo môn, không theo câu, nên không làm được McNemar; +9,54 là chênh lệch mô tả. Tính theo số câu, file trước đúng 6.623 và file sau đúng 7.565 trên 9.833 câu (+942).
   - Trong file sau có 113 câu để trống vì cả ba lần S đều bị cắt ở trần 4.096 token; các câu này tính là sai.
6. VMLU Test của MiMo lấy từ MC-110c, do vmlu.ai chấm. MC-110 chạy vòng tự sửa trên đủ 9.833 câu (2026-11-07 đến 2026-11-10) với trần 20.000 token. Có 538 lượt hỏi không ra câu trả lời: 183 lượt quá thời gian chờ ba lần, 355 lượt bị cắt ở trần. MC-110c (2026-11-10) hỏi lại các lượt đó với trần 40.000 token, cùng quy tắc, và dùng lại 17 câu trả lời của MC-110b (dừng giữa chừng) vốn đã xong dưới 20.000 token. Hai file của MC-110 không được nộp lên vmlu.ai.
   - "Trước" là B lần 1 của cùng lượt chạy, với mặc định của nhà cung cấp. "Sau" là vòng tự sửa, hỏi theo từng vòng.
   - vmlu.ai chỉ trả điểm theo môn; +4,39 là chênh lệch mô tả. Tính theo số câu, file trước đúng 7.542 và file sau đúng 7.975 trên 9.833 câu (+433).
   - File sau có 39 câu để trống: ở cả 39 câu, không lượt S nào cho ra chữ cái, và gần như mọi lượt S đó đều suy nghĩ hết trần 40.000 token. File trước có 210 câu để trống: 143 lượt nhà cung cấp trả về rỗng ngay lập tức, 57 lượt hết trần 40.000 token và 10 lượt có chữ nhưng không đọc được chữ cái. Các câu để trống tính là sai.
   - Token/câu tính trên các lượt mà đáp án cuối dùng. Cả ba lượt chạy (MC-110, MC-110b, MC-110c) đã trả 39,8 triệu token, vì các lượt bị cắt ở 20.000 token được hỏi lại.

## Bằng chứng trên câu mới (MC-104)

Các bộ của MC-105 đã được dùng để thiết kế router (MC-90 đến MC-95). MC-104 vì vậy chạy cùng vòng tự sửa trên 603 câu trắc nghiệm chưa router nào dùng: VMLU Dev 303 và VM14K 300.

| Model | Trước: hỏi thẳng | Sau: vòng tự sửa | Sau − trước | p (Holm) | Luôn S | Token/câu: trước → sau |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3.5-9B | 68,99 | 76,29 | **+7,30** ✓ | < 0,001 | 73,96 | 118 → 1334 |
| MiMo V2.6 Flash | 76,29 | 78,44 | +2,16 | 0,079 | 78,77 | 423 → 1390 |

Vòng tự sửa tốn nhiều token hơn luôn S ở cả hai model, nên không đạt điều kiện đăng ký "không kém luôn S quá 1 điểm và rẻ hơn".

## VMLU Test của Qwen theo nhóm môn (MC-109)

VMLU Test là bằng chứng thứ hai trên câu mới cho router, sau MC-104: router chưa từng dùng các câu này lúc thiết kế, vì Test không có đáp án. Điểm do vmlu.ai chấm hai file chủ dự án nộp ngày 2026-11-07. Điểm của mỗi nhóm là trung bình các môn trong nhóm.

| Nhóm môn | Số môn | Số câu | Trước: hỏi thẳng | Sau: vòng tự sửa | Sau − trước |
|---|---:|---:|---:|---:|---:|
| STEM | 21 | 3.592 | 65,17 | 82,12 | **+16,95** |
| Khoa học xã hội | 10 | 1.738 | 74,36 | 79,44 | +5,08 |
| Nhân văn | 18 | 3.024 | 67,14 | 72,11 | +4,97 |
| Khác | 9 | 1.479 | 63,38 | 69,74 | +6,36 |
| **Tổng** (trung bình 58 môn) | 58 | 9.833 | 67,09 | **76,63** | **+9,54** |

- **53/58 môn tăng.** Tăng nhiều nhất là các môn cần tính toán:
  - xác suất thống kê +42,53 (50,00 → 92,53);
  - toán THCS +33,34;
  - nhập môn vật lý +30,06;
  - vật lý THCS +26,67;
  - toán rời rạc +23,64.
- **3 môn giảm:** quản trị kinh doanh −4,60, giáo dục mầm non −1,97 và tiếng Việt và văn học −0,58. Hai môn không đổi: sinh học THPT và luật hành chính.
- **Vòng tự sửa dừng ở vòng nào:**

  | | Dừng ở vòng 1 | Dừng ở vòng 2 | Phải bỏ phiếu ở vòng 3 |
  |---|---:|---:|---:|
  | VMLU Test (MC-109) | 4.928 câu (50%) | 2.392 câu (24%) | 2.513 câu (26%) |
  | VMLU Valid (MC-105) | 54% | 24% | 22% |

  - Vòng 1: probe chắc chắn.
  - Vòng 2: S trùng B.
  - Có 2.263 đáp án cuối (23%) khác hỏi thẳng.
  - Mức tăng ở Test (+9,54) thấp hơn ở Valid (+12,10).
- **Chi phí:** 1.660 token/câu, so với 132 khi chỉ hỏi thẳng (12,6 lần). Lượt S ở Test dài hơn ở Valid (trung bình 1.316 so với 830 token output), nên tổng thời gian chạy khoảng 22 giờ ở 6 luồng.
- **So với MiMo (chỉ mô tả, khác route và cài đặt):** Qwen sau vòng tự sửa (76,63) ngang mức MiMo hỏi thẳng trên /table: 76,20 với OMP không tools và 77,68 với API trực tiếp.

## VMLU Test của MiMo theo nhóm môn (MC-110c)

Điểm do vmlu.ai chấm hai file của MC-110c mà chủ dự án nộp ngày 2026-11-11. Điểm của mỗi nhóm là trung bình các môn trong nhóm.

| Nhóm môn | Số môn | Số câu | Trước: hỏi thẳng | Sau: vòng tự sửa | Sau − trước |
|---|---:|---:|---:|---:|---:|
| STEM | 21 | 3.592 | 81,57 | 86,69 | **+5,12** |
| Khoa học xã hội | 10 | 1.738 | 79,28 | 82,39 | +3,11 |
| Nhân văn | 18 | 3.024 | 71,07 | 75,69 | +4,62 |
| Khác | 9 | 1.479 | 71,33 | 74,92 | +3,59 |
| **Tổng** (trung bình 58 môn) | 58 | 9.833 | 76,32 | **80,71** | **+4,39** |

- **52/58 môn tăng.** Tăng nhiều nhất:
  - vật lý THPT +13,34 (72,22 → 85,56);
  - giáo dục mầm non +10,79;
  - kiến trúc máy tính +8,89;
  - xác suất thống kê +8,62;
  - khoa học tiểu học +8,34.
- **3 môn giảm:** luật hành chính −3,33, kỹ thuật môi trường −0,59 và quản trị kinh doanh −0,57. Ba môn không đổi: lịch sử THPT, tư tưởng Hồ Chí Minh và địa lý THCS.
- **Vòng tự sửa dừng ở vòng nào:** vòng 1 (hai lần B trùng nhau) 7.838 câu (80%), vòng 2 (S trùng một B) 1.638 câu (17%), vòng 3 (bỏ phiếu) 357 câu (4%). Có 1.100 đáp án cuối (11%) khác B lần 1. Mức tăng ở Test (+4,39) thấp hơn ở Valid (+5,38).
- **Chi phí:** 3.115 token/câu, so với 866 khi chỉ hỏi thẳng (3,6 lần). MiMo là model thinking, nên ngay cả hỏi thẳng cũng tốn nhiều token hơn Qwen. Các câu khó nhất (nhiều ở sinh, hoá, lý THPT) suy nghĩ tới hàng chục nghìn token mỗi lượt.
- **So với Qwen (cùng câu, khác model):** MiMo hỏi thẳng (76,32) gần bằng Qwen sau vòng tự sửa (76,63). Sau vòng tự sửa MiMo cao hơn Qwen ở 51/58 môn. Ở sinh học THPT, vòng tự sửa nâng MiMo từ 72,22 lên 79,44, còn Qwen không đổi (67,78).

## Nhận xét

- **Nơi router giúp.** Vi-DROP (cần tính toán trên đoạn văn), VMLU và ViBidLQA test tăng rõ ở cả hai model. Phần lớn lợi ích đến từ suy luận từng bước (S): ở Vi-DROP, chỉ dùng S (luôn S) đã cao hơn vòng tự sửa.
- **Nơi router không giúp.** Ở Legal MC, Legal NLI và Vi-SQuAD, hỏi thẳng đã gần trần. Với Qwen, S còn kém B ở Legal (Legal MC: luôn S 82,9% so với B 91,1%), nên vòng lặp càng dùng S thì càng tụt.
- **Full tools và router là hai hướng khác nhau.** Cho model dùng tools không nâng điểm ở bộ nào một cách nhất quán, và làm Qwen tụt mạnh. Router giữ nguyên prompt và model, chỉ quyết định khi nào hỏi thêm.
- **Model mạnh hơn được lợi ít hơn.** MiMo tự suy nghĩ sẵn khi hỏi thẳng, nên S giúp MiMo ít hơn Qwen ở VMLU valid: luôn S hơn hỏi thẳng 4,6 điểm ở MiMo, so với 10,5 điểm ở Qwen. Ở VMLU Test cũng vậy: vòng tự sửa thêm 4,39 điểm cho MiMo, so với 9,54 điểm cho Qwen. MC-108 định hỏi liệu Muse, đã trên 90% ở VMLU, có còn được lợi không. Câu hỏi đó vẫn không có câu trả lời, vì MC-108 đã dừng hẳn.

## Giới hạn khi so sánh

- **Không phải câu mới, trừ VMLU Test.** Các bộ khác của /table đã dùng để thiết kế router trên Qwen. Bằng chứng trên câu mới là MC-104 và VMLU Test (MC-109 của Qwen, MC-110c của MiMo).
- **VMLU Test của MiMo là bản hỏi lại, không phải MC-110 đã đăng ký.** MC-110c giữ nguyên quy tắc của MC-110, chỉ hỏi lại các lượt không ra câu trả lời với trần 40.000 token. Hai file của MC-110 (trần 20.000 token) chưa được vmlu.ai chấm; chúng khác file của MC-110c ở 42 câu (trước) và 60 câu (sau).
- **"Trước" có hai nghĩa.** Phép thử chính so với hỏi thẳng trong cùng lượt chạy. Ba dòng OMP, full tools và API trực tiếp đo ở route, temperature, trần token, số workers và thời điểm khác. Chênh lệch giữa chúng và dòng "Sau" vì vậy không chỉ do router.
- **Full tools chỉ mô tả.** Timeout và cách chạy lại khác nhau giữa bốn model. Riêng MiMo có 46 câu không xong trong ngân sách thời gian, được ghi đáp án rỗng.
- **Bộ chấm v3 được áp dụng sau khi đã xem dữ liệu.** Đọc hiểu ở đây dùng token-F1 v3: bỏ dấu `*` và backtick rồi chấm như v2. Số đăng ký của các thẻ cũ là v2. V2 trừ điểm câu trả lời in đậm dù đúng chữ, nên làm điểm đọc hiểu của Muse Spark 1.2 và MiMo thấp đi. Muse Spark 1.3 và Qwen gần như không đổi.
- **Một lượt chạy cho mỗi cách.** Các cách được so trên cùng một tập câu trả lời đã ghi; chạy lại có thể khác.
- **Đã gặp câu hỏi trước.** Các model đã trả lời những câu này ở nhiều thẻ đo trước. Model không nhớ giữa các lần gọi, nhưng không đo được việc dữ liệu công khai đã nằm trong dữ liệu huấn luyện hay chưa.

## Muse Spark: vì sao không có số sau

MC-108 chạy đúng vòng tự sửa của MiMo trong MC-105 cho Muse Spark 1.3 và 1.2, trên 2.346 câu (7 cột ở trên, trừ VMLU Test). Mỗi câu hỏi B hai lần và S ba lần, tức 11.730 lượt mỗi model. Thẻ đã đăng ký trước khi chạy ([`docs/measurement_cards/MC-108-diagnostic-table-loop-muse.md`](../measurement_cards/MC-108-diagnostic-table-loop-muse.md)).

- Ngày 2026-11-03, bộ lọc nội dung của Meta ở gói Contributor từ chối một số prompt S với lỗi HTTP 400 `content_policy_violation`. Ví dụ là một đoạn Vi-DROP về chất tẩy xạ quân sự, trong khi prompt B của cùng câu vẫn qua. Ở VMLU không có lượt nào bị từ chối.
- Sau khoảng 4 lần bị từ chối trong 10 phút (một lần trong số đó là lần gửi lại để đọc lỗi), tài khoản OpenCode Go nhận lỗi 403 `user_blocked` ("Your access has been restricted due to repeated policy violations.") với cả hai model Muse.
- Các lần kiểm tra lúc 16:42, 16:44, 21:08 và 21:26 (+07), kể cả từ một phiên `opencode` mới, đều nhận cùng lỗi. Khoá nằm ở tài khoản, không ở phiên hay công cụ gọi.
- Ngày 2026-11-04 tài khoản được mở lại. MC-108 chạy tiếp với các câu bị từ chối được giữ lại, không gửi nữa (sửa đổi 1 đến 4 trong thẻ đo). Dù vậy, chỉ trong khoảng 35 phút đã có thêm 4 lần bị từ chối:
  - Vi-DROP 3101: thiệt hại trực thăng trong một chiến dịch.
  - Vi-DROP 5218: một vụ rơi máy bay chở khách.
  - Vi-SQuAD 1855: một đoạn về **dự báo thời tiết**, bị cả hai model từ chối. Lần thứ hai là do lỗi vận hành: câu này chưa được giữ lại trước khi chạy lại Muse 1.3.
- Mọi lần bị từ chối đều là prompt S; chưa prompt B nào bị từ chối. Riêng ngày 2026-11-04, Muse 1.2 bị từ chối 3/142 prompt S. Bộ lọc cho kết quả cố định với từng prompt, nhưng nội dung đoạn văn không cho biết trước prompt nào bị từ chối, nên không lọc trước được.
- Chủ dự án quyết định dừng Muse 1.2 sau lần từ chối thứ 3, rồi dừng hẳn MC-108 sau lần từ chối tiếp theo của Muse 1.3. Lúc dừng, Muse 1.3 đã xong 1.639 lượt và Muse 1.2 đã xong 2.165 lượt, trên 10.725 lượt còn được phép gửi mỗi model. Phân tích đã đăng ký không được chạy, nên không có điểm nào được tính.

## Nguồn số liệu

- Ba điều kiện trước router: `web/data/benchmark-reports.json` (build lúc 2026-10-30 07:14 UTC), qua cùng logic ghép bảng của `/table` (`web/lib/benchmark-matrix.ts`).
- Trước và sau router: `web/data/router-results.json` (build lúc 2026-11-11 02:23 UTC), bảng "Trước / sau" của `/table?condition=router`. File này đọc từ các báo cáo phân tích đã đăng ký:
  - `all_res/diagnostic_router_loop/table_loop/analysis/table_loop_report.json` (MC-105), SHA-256 `8b9a526b…`;
  - `all_res/diagnostic_router_loop/self_loop/analysis/self_loop_report.json` (MC-104), SHA-256 `f2138797…`.
- VMLU Test của Qwen (MC-109): điểm vmlu.ai mà chủ dự án gửi lại ngày 2026-11-07. Bản gốc lưu ở `all_res/diagnostic_router_loop/vmlu_test_loop/qwen3-5-9b-65k-prospective/vmlu_ai_scores_before.json` và `vmlu_ai_scores_loop.json`, cạnh hai file đã nộp `submission_before.csv` và `submission_loop.csv`. Bản có kèm SHA-256 của file nộp lưu ở `docs/research/qwen-vmlu-test-server-grade-mc109-{before,loop}-2026-11-07.json`, cùng mẫu với các điểm vmlu.ai trước đó. Từ ngày 2026-11-07, `/table?condition=router` hiển thị số này: cột VMLU test ở Bảng 1, một dòng ở Bảng 2 và mục chi tiết MC-109.
- VMLU Test của MiMo (MC-110c): điểm vmlu.ai mà chủ dự án gửi lại ngày 2026-11-11. Bản gốc lưu ở `all_res/diagnostic_router_loop/vmlu_test_loop/mimo-v2-6-flash-40k/vmlu_ai_scores_{before,loop}.json`, cạnh hai file đã nộp. Bản có kèm SHA-256 của file nộp lưu ở `docs/research/mimo-vmlu-test-server-grade-mc110c-{before,loop}-2026-11-11.json`. Từ ngày 2026-11-11, `/table?condition=router` hiển thị số này: cột VMLU test của MiMo ở Bảng 1, một dòng ở Bảng 2 và mục chi tiết MC-110, MC-110c.
- Thẻ đo: `measurement_card.md` và `docs/measurement_cards/` (MC-80 đến MC-89, MC-104, MC-105, MC-108, MC-109, MC-110, MC-110b, MC-110c).
- Hai file JSON trên được sinh tự động; nếu chúng được build lại, các số ở đây cần được đối chiếu lại.
