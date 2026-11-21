# Vì sao prompt của dsh trong omp giúp Qwen mà hại MiMo (phân tích khám phá sau MC-117)

Ngày 2026-11-21. **Đây là phân tích khám phá, không đăng ký trước.** Nó được viết sau khi đã đọc báo cáo đăng ký của MC-117 (`bfd544bd…`). Không có request nào được gửi.

- **Kết quả đăng ký không đổi.** Các số P1–P3 trong báo cáo đăng ký vẫn đứng nguyên. Tài liệu này chỉ đi tìm cơ chế đằng sau chúng.
- **Dữ liệu.** OMPS lấy từ MC-117. OMPF và DSHF lấy từ MC-112 đến MC-114 (Qwen) và MC-116 (MiMo). Tất cả ở lượt 1–2, trên cùng 646 câu.
- **Module.** `code_benchmark/explore_legal_agent_omp_prompt.py` (4 test). Báo cáo `all_res/diagnostic_legal_agent_omp_prompt/explore/omp_prompt_followup.json`, SHA-256 `5e9c7111…`.
- **Prompt.** Nguyên văn sáu system prompt (omp mặc định, dsh, OMPS; mỗi model một bản) và bảng so sánh theo thành phần nằm ở `docs/research/system-prompts-2026-11-21/`.
- **Luồng hành động.** Báo cáo luồng của sáu ô nằm ở `docs/research/legal-agent-flows-mc117-2026-11-21.md`.
- **Một mục còn thiếu.** Protocol của MC-117 có liệt kê "step split" (tỉ lệ đọc được điều luật, điểm khi đọc và khi không đọc) trong phần báo cáo bên cạnh. Báo cáo đăng ký lại không tính mục này. Tài liệu này tính nó ở dạng hậu kiểm.

## Hai loại điểm

- **Trắc nghiệm: điểm là accuracy, nhưng chữ cái do máy trích.** Câu lệnh ghi *"Chỉ đưa ra chữ cái đứng trước câu trả lời đúng (A, B, C, D hoặc E)…"*. Model trả lời bằng văn bản tự do. Bộ trích V1 đã đóng băng lấy chữ cái đứng riêng đầu tiên trong văn bản rồi so với đáp án. Nó không đòi câu trả lời chỉ gồm một chữ cái.
- **ViBidLQA: điểm là token-F1, không phải accuracy.** Câu lệnh ghi *"Trả lời câu hỏi sau bằng một cụm từ hoặc số ngắn gọn."* Token-F1 đo mức trùng từ với đáp án chuẩn. Nó gộp recall (bao nhiêu phần đáp án chuẩn có trong câu trả lời) và precision (bao nhiêu phần câu trả lời thuộc đáp án chuẩn). Viết thừa chữ thì precision giảm, kéo F1 xuống.
  - Ví dụ: đáp án chuẩn là *"lập kế hoạch lựa chọn nhà thầu"*. MiMo (OMPS) trả lời *"**Nguyên tắc lập kế hoạch lựa chọn nhà thầu** (Điều 37 gồm 5 khoản)."*
  - Kết quả: recall 100%, precision khoảng 50%, F1 66,7%, EM 0.

## Kết luận ngắn

Thay prompt mặc định của omp bằng prompt của dsh làm thay đổi hai thứ cùng một lúc.

1. **Cách Qwen đọc tài liệu.** Đây là thay đổi về nội dung.
   - Prompt dsh dặn dùng offset và limit để **đọc tiếp** file lớn. Prompt omp cũng nhắc offset và limit, nhưng theo hướng **đọc hẹp, tránh phần không cần**, và chỉ là một dòng giữa khoảng 150 dòng quy ước lập trình (xem phần so sánh prompt).
   - Với prompt dsh, Qwen đọc được điều luật chi phối nhiều gấp đôi: trắc nghiệm từ 21% lên 42%, ViBidLQA từ 21% lên 35%.
   - Recall trên ViBidLQA tăng 8,3.
2. **Mức tuân thủ yêu cầu định dạng câu trả lời, ở cả hai model.**
   - Chỉ prompt omp có chỉ dẫn về định dạng: *"Format MUST match ask; prose brief"*, *"Evidence-first terse engineer"*, *"no … summaries, filler"*.
   - Không có những câu đó, cả hai model viết dài hơn, có giải thích và markdown, dù câu lệnh đòi một chữ cái hoặc một cụm từ ngắn.
   - Cả hai bộ chấm đã khóa đều tính kiểu trả lời này là mất điểm: token-F1 qua precision, bộ trích chữ cái qua việc bắt nhầm chữ trong lời giải thích.

MiMo giảm điểm chủ yếu vì điểm thứ hai, không phải vì đọc kém đi: tỉ lệ đọc được điều luật và recall của MiMo đều còn tăng nhẹ.

**Hệ quả cho tương tác model × harness:**
- **Trắc nghiệm.** Chấm theo đúng yêu cầu của đề (chỉ tính đúng khi câu trả lời là một chữ cái), omp tốt hơn dsh với cả hai model, và không còn tương tác.
- **ViBidLQA.** Đo theo recall, tương tác gốc nhỏ đi một nửa. Sau khi thay prompt, phần còn lại bằng 0.

## Bảng 1: trạng thái đọc và câu trả lời (lượt 1–2)

| | Qwen OMPS | Qwen OMPF | Qwen DSHF | MiMo OMPS | MiMo OMPF | MiMo DSHF |
|---|---:|---:|---:|---:|---:|---:|
| **Trắc nghiệm:** điểm đăng ký | 72,8 | 68,5 | 77,4 | 88,4 | 91,3 | 85,6 |
| Đọc được điều luật chi phối | **41,8%** | 21,3% | 56,7% | 73,1% | 68,2% | 88,0% |
| Câu trả lời chỉ gồm một chữ cái | 42,3% | **65,7%** | 42,1% | 78,0% | **88,8%** | 75,0% |
| Số từ trong câu trả lời (trung bình) | 111 | 60 | 93 | 28 | 12 | 33 |
| Câu trả lời có markdown | 50% | 30% | 41% | 16% | 6% | 17% |
| **ViBidLQA:** token-F1 đăng ký | 34,1 | 28,3 | 32,6 | 49,6 | 58,6 | 51,3 |
| Đọc được điều luật chi phối | **34,6%** | 20,8% | 41,9% | 73,8% | 68,8% | 83,1% |
| Gold-token recall | **50,4** | 42,1 | 50,6 | 88,8 | 86,4 | 89,0 |
| Precision (suy ra từ F1 và recall) | 36,9 | 29,6 | 32,5 | **42,5** | **53,5** | 45,2 |
| Số từ được chấm | 36 | 33 | 36 | **36** | **28** | 35 |
| Câu trả lời có markdown | 33% | 33% | 23% | 54% | 25% | 66% |

## Bảng 2: trắc nghiệm chấm theo đúng yêu cầu của đề

"Chấm chặt" nghĩa là một lượt chỉ được tính đúng khi câu trả lời là đúng một chữ cái A–E và trùng đáp án. Cho phép markdown, ngoặc và dấu chấm, ví dụ `B`, `**B**`, `B.`, `(B)`.

Câu trả lời dạng "Đáp án: B" bị tính là không tuân thủ, vì đề đòi chỉ chữ cái. Dạng này rất ít: từ 0 đến 23 trên 492 lượt mỗi ô, nên không đổi kết luận.

| | DSHF | OMPF | OMPS |
|---|---:|---:|---:|
| Qwen: tỉ lệ trả một chữ cái | 42,1% | 65,7% | 42,3% |
| Qwen: accuracy khi trả một chữ cái / khi trả dài (bộ trích đăng ký) | 78,7 / 76,5 | 69,7 / 66,3 | 77,4 / 69,4 |
| Qwen: accuracy chấm chặt | 33,1 | **45,7** | 32,7 |
| MiMo: tỉ lệ trả một chữ cái | 75,0% | 88,8% | 78,0% |
| MiMo: accuracy khi trả một chữ cái / khi trả dài (bộ trích đăng ký) | 98,1 / **48,0** | 94,5 / 65,5 | 94,3 / 67,6 |
| MiMo: accuracy chấm chặt | 73,6 | **83,9** | 73,6 |

| Hiệu theo từng câu, CI 95% bootstrap | Bộ trích đăng ký | Chấm chặt |
|---|---|---|
| Qwen: OMPF − DSHF | −8,94 [−14,0; −3,9] | **+12,60 [6,7; 18,3]** |
| MiMo: OMPF − DSHF | +5,69 [2,8; 8,5] | **+10,37 [6,1; 14,4]** |
| Tương tác gốc (MiMo − Qwen) | +14,63 [8,9; 20,5] | **−2,24 [−9,8; 5,1]** |
| Qwen: OMPS − OMPF | +4,27 [−0,6; 8,9] | −13,01 [−18,1; −7,9] |
| MiMo: OMPS − OMPF | −2,85 [−5,5; −0,6] | −10,37 [−14,6; −6,1] |
| Tương tác còn lại | +7,52 [1,6; 13,2] | +0,41 [−6,9; 7,3] |

**Vì sao hai cách chấm cho kết quả ngược nhau.** Hai model viết câu trả lời dài theo hai kiểu khác nhau:
- **Qwen** thường ghi chữ cái ở đầu rồi mới giải thích, nên bộ trích lấy đúng. Ở DSHF, câu trả lời dài của Qwen vẫn đạt 76,5%.
- **MiMo** giải thích trước, chữ cái ở dòng cuối, nên bộ trích hay bắt nhầm một chữ cái trong phần giải thích. Ở DSHF, câu trả lời dài của MiMo chỉ đạt 48,0%, so với 98,1% khi nó trả một chữ cái.
  - Ví dụ câu 39-0018, đáp án C. MiMo viết *"… → Nhận định **B sai** … Vậy cả A và B đều sai. / C"*. Bộ trích lấy "B".

Như vậy, dưới bộ trích dễ dãi, Qwen được tính điểm cho câu trả lời dài mà MiMo thì không. Phần lớn tương tác +14,6 trên trắc nghiệm đến từ việc bố cục câu trả lời của từng model gặp một bộ chấm dễ dãi.

## Bảng 3: OMPS − OMPF trên cùng câu, cùng lượt (CI 95% bootstrap theo câu)

| | Qwen | MiMo |
|---|---|---|
| Trắc nghiệm, khi cả hai lượt đều đọc được điều luật | +23,7 [10,2; 37,3] (59 cặp) | −3,9 [−6,5; −1,5] (260 cặp) |
| ViBidLQA, khi cả hai lượt đều đọc được điều luật | −3,6 [−11,3; 4,3] (110 cặp) | **−9,1 [−11,9; −6,2]** (487 cặp) |
| ViBidLQA, recall | +8,3 [4,6; 11,7] | +2,4 [1,0; 3,8] |
| ViBidLQA, precision | +7,3 [4,2; 10,2] | **−11,0 [−13,5; −8,5]** |
| ViBidLQA, số từ được chấm | +3,5 [−3,1; 11,1] | **+8,4 [6,8; 10,0]** |
| Trắc nghiệm, số từ | +51 [37; 67] | +16 [10; 23] |

Ở ViBidLQA, MiMo mất 9 điểm ngay cả khi cả hai lượt đều đã đọc điều luật. Precision giảm 11 trong khi recall tăng 2,4. MiMo vẫn đưa đúng nội dung vào câu trả lời, chỉ là không giữ được yêu cầu "cụm từ ngắn gọn".

## Bảng 4: các cách đọc ít phụ thuộc định dạng hơn (hậu kiểm, không thay số đăng ký)

Ba cách đọc được dùng ở đây:
- **Trắc nghiệm, chữ cái ở dòng cuối** (`stated_letter`): lấy dòng cuối nếu nó chỉ có một chữ cái; nếu không, lấy cụm "Đáp án (đúng) (là) X" cuối cùng; nếu vẫn không có, giữ chữ cái của bộ trích đã khóa. Quy tắc này được viết sau khi xem 22 lượt MiMo đúng ở OMPF mà sai ở OMPS. Trong 22 lượt đó, 14 lượt có dòng cuối đúng chữ cái gold, 5 lượt sai thật và 3 lượt không có đáp án.
- **Trắc nghiệm, chấm chặt:** như Bảng 2.
- **ViBidLQA:** gold-token recall thay cho token-F1. Bộ chấm vi-reading-v3 vốn đã ghi recall như một chỉ số mô tả.

| | Bộ chấm đăng ký | Chữ cái ở dòng cuối | Chấm chặt | Recall (ViBidLQA) |
|---|---|---|---|---|
| Trắc nghiệm: Qwen OMPS − OMPF | +4,27 | +6,10 [1,6; 10,6] | −13,01 | |
| Trắc nghiệm: MiMo OMPS − OMPF | −2,85 | −1,22 [−3,3; 0,8] | −10,37 | |
| Trắc nghiệm: tương tác gốc | 14,63 | 12,20 [6,7; 17,5] | −2,24 | |
| Trắc nghiệm: tương tác còn lại | 7,52 | 4,88 [−0,2; 9,8] | 0,41 | |
| ViBidLQA: Qwen OMPS − OMPF | +5,74 | | | +8,26 [4,3; 11,9] |
| ViBidLQA: MiMo OMPS − OMPF | −9,00 | | | **+2,38 [1,0; 3,8]** |
| ViBidLQA: tương tác gốc | 11,64 | | | 5,88 [2,0; 10,1] |
| ViBidLQA: tương tác còn lại | −3,10 | | | **0,00 [−4,2; 4,5]** |

## Diễn giải

1. **Prompt mặc định của omp có hai tác dụng, và mỗi model chịu một tác dụng.**
   - **Với Qwen, nó gây hại vì làm Qwen đọc ít.** Chỉ dẫn đọc của omp hướng tới đọc hẹp và nằm lẫn giữa các quy ước lập trình. Qwen để harness cắt trang và thường trả lời ngay sau grep.
   - Prompt dsh dặn đọc tiếp file lớn, và Qwen làm theo: tự chọn khoảng đọc ở 82% số lần đọc (OMPF 60%), đọc tới điều luật nhiều gấp đôi, và cả recall lẫn precision đều tăng.
   - Cái giá là ngữ cảnh đầy nhanh hơn, nên omp tự nén ngữ cảnh nhiều hơn (báo cáo luồng hành động).
   - **Với MiMo, nó có lợi vì giữ đúng định dạng câu trả lời.** MiMo vốn đã tự chọn khoảng đọc. Thứ quyết định điểm của MiMo là có trả lời gọn như đề yêu cầu hay không.
2. **Thước đo quyết định câu trả lời cho câu hỏi "harness nào tốt hơn".**
   - Nếu tính cả việc tuân thủ yêu cầu của đề (chấm chặt), omp tốt hơn dsh với cả hai model trên trắc nghiệm.
   - Nếu chỉ tính chữ cái mà bộ trích dễ dãi lấy được, dsh tốt hơn với Qwen.
   - Cả hai cách đều hợp lệ nhưng đo hai thứ khác nhau, nên khóa luận phải nói rõ đang dùng cách nào.
3. **Phần tương tác thật sự thuộc về nội dung** là việc Qwen đọc điều luật. Trên ViBidLQA, đo theo recall, tương tác gốc là 5,9 và thay prompt xóa hết phần đó.

## Giới hạn

- **Hậu kiểm.** Ba cách đọc thay thế được chọn sau khi đã thấy dữ liệu, và quy tắc "dòng cuối" được viết sau khi xem 22 ví dụ. Không có phép kiểm định nào ở đây; các số đăng ký vẫn là kết quả chính thức.
- **Chấm chặt đo hai thứ cùng lúc,** tuân thủ định dạng và đúng sai. **Recall** không phạt câu trả lời dài. Không cách nào là thước đo "đúng hơn"; chúng tách các thành phần ra để nhìn.
- **Độ dao động của MiMo giữa các lần chạy chưa biết,** vì OMPF của MiMo mới có một vòng.
- **Chưa tách được câu nào trong prompt có tác dụng.** Prompt mặc định của omp có nhiều câu về định dạng và về đọc file. Muốn biết câu nào có tác dụng, cần một card thay từng phần của prompt.

## Gợi ý cho bước tiếp theo (chưa đăng ký)

- **Card thay từng phần prompt:** thêm vào prompt dsh câu định dạng của omp (*"Format MUST match ask; prose brief"*). Nếu cả hai model lấy lại được mức tuân thủ định dạng mà Qwen giữ được phần lợi về đọc, cơ chế hai tác dụng được xác nhận.
- **Đăng ký trước ba chỉ số trắc nghiệm cho các card sau:** tỉ lệ trả đúng một chữ cái, accuracy chấm chặt, và accuracy theo bộ trích V1. Với câu trả lời ngắn, báo recall cạnh F1. Lần đổi bộ chấm ViBidLQA từ v2 sang v3 đã có tiền lệ như vậy.
