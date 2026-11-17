# Khả năng tiếng Việt của model qua các lượt hỏi thẳng và hỏi từng bước

Báo cáo ngày 2026-11-08. Đây là **phân tích sau (post hoc), chỉ để khám phá**: không có request mới, không thay kết luận đã đăng ký của thẻ đo nào. Số liệu lấy từ các lượt đã chấm:

- **VMLU test:** điểm theo từng môn do vmlu.ai chấm. Qwen3.5-9B có cả hai bản: hỏi thẳng và vòng tự sửa (MC-109). MiMo V2.6 Flash có bản hỏi thẳng (MC-85).
- **Các bộ của `/table`:** từng câu, cả hỏi thẳng (B) lẫn hỏi từng bước (S), cho cả hai model (MC-105).
- **Câu trắc nghiệm mới:** VMLU dev và VM14K (MC-104).
- **Thí nghiệm đưa văn bản cho model:** MC-100 (đưa đúng điều luật) và MC-96 (tự tìm văn bản).

Mọi bảng ở mục [Bảng số liệu](#bảng-số-liệu) do script sinh ra rồi chép nguyên vào đây.

Báo cáo trả lời bốn câu hỏi:

1. Nếu kết quả cũ (chỉ hỏi thẳng) thấp hơn, thì thấp vì đâu?
2. Khả năng tiếng Việt thật của model tới đâu?
3. Điều gì giúp model trả lời tiếng Việt tốt hơn?
4. Thước chấm đã đủ khách quan chưa? Bắt model suy nghĩ chi tiết có làm nó đọc hiểu tốt hơn theo tỷ lệ không?

Hai từ dùng xuyên suốt:
- **B** là hỏi thẳng: model trả lời ngay, không trình bày lời giải.
- **S** là hỏi từng bước: prompt bảo model chia bài thành các bước nhỏ, kiểm tra từng bước rồi kết luận ở dòng cuối `Đáp án: …`.

## Tóm tắt

- **Kết quả cũ thấp vì ba lý do khác nhau, và S chỉ sửa được hai.**
  - *Thiếu bước tính toán.* Đây là lý do của Qwen. Trên VMLU test, 13 môn tính toán tăng từ 61,1 lên 84,1 (+23,0), và môn nào cũng tăng quá 2 điểm. Ở Vi-DROP, các câu cộng trừ, so sánh và đếm tăng 26–31 điểm.
  - *Định dạng câu trả lời làm điểm thấp oan.* Đây là lý do của MiMo ở đọc hiểu. Khi hỏi thẳng Vi-DROP, MiMo trả lời đúng số rồi viết thêm lời giải thích, nên token-F1 chỉ còn 54,0 dù 78,0% câu trả lời có chứa đúng đáp án. Xét riêng các câu có đáp án là một con số, số đầu tiên MiMo viết ra đúng 80,3% khi hỏi thẳng và 86,8% khi hỏi từng bước. Vậy trong mức tăng +23,6 F1 của S, phần thật chỉ khoảng 6,5 điểm; phần còn lại là do dòng `Đáp án:` ngắn gọn.
  - *Thiếu kiến thức.* S không sửa được lý do này. 21 môn kiến thức đặc thù Việt Nam (luật, sử, địa, văn, giáo dục công dân, tư tưởng) chỉ tăng từ 69,6 lên 74,0, và 7 môn tăng không quá 2 điểm. Môn "Tiếng Việt và văn học" đứng yên (55,8 → 55,2). Môn "Luật hành chính" cũng vậy (55,6 → 55,6).
- **Khả năng đọc hiểu tiếng Việt của cả hai model đã cao; chỗ yếu là kiến thức về Việt Nam.**
  - Ở Vi-SQuAD (tìm thông tin có sẵn trong đoạn văn), cả hai model đạt 89–91 token-F1 với cả B lẫn S.
  - Khi được đưa đúng điều luật, Qwen trả lời đúng 82,6% số câu Legal MC mà trước đó nó từng sai. Không có điều luật, con số này là 37,0% (MC-100).
  - Khi tự tìm trúng đoạn văn, Qwen đạt token-F1 ngang với khi được đưa đúng đoạn (67,9 so với 67,9); khi không có văn bản thì chỉ 14,4 (MC-96).
  - Kiến thức đặc thù Việt Nam dừng quanh 74–75% cho cả Qwen (sau vòng lặp) lẫn MiMo, dù MiMo là model có thinking.
- **Thứ giúp nhiều nhất là đưa đúng văn bản, sau đó mới tới suy nghĩ từng bước, rồi bỏ phiếu.**
  - Đưa đúng văn bản: +45,6 điểm trên các câu luật model từng sai.
  - S: chỉ giúp phần tính toán, và chỉ ở model không có thinking.
  - Bỏ phiếu ba lần S: thêm không quá 2 điểm mỗi bộ ([báo cáo Pareto](../router-before-after/pareto.md)).
- **Thước chấm trắc nghiệm đủ khách quan để so các điều kiện với nhau; thước chấm đọc hiểu thì chưa.**
  - Token-F1 và EM chấm lẫn nội dung với định dạng: cùng một câu trả lời đúng, viết dài hơn là bị trừ điểm.
  - Ở MC-94, 34 trên 50 câu trả lời thua về EM thực ra đúng về nghĩa. Theo EM, router hơn hỏi thẳng 24 câu và kém 4 câu; xét theo nghĩa, nó chỉ hơn 7 câu và không kém câu nào.
- **Suy nghĩ chi tiết không tỷ lệ thuận với khả năng đọc hiểu.**
  - S gần như không đổi điểm Vi-SQuAD (+0,1 với Qwen, +1,7 với MiMo).
  - Trong mọi bộ, lời giải càng dài thì tỷ lệ đúng càng thấp. Ví dụ, Qwen ở VMLU valid đúng 95,2% với một phần tư lời giải ngắn nhất, nhưng chỉ 57,5% với một phần tư dài nhất.
  - S giúp khi model chưa chắc: nếu độ tự tin của lần hỏi thẳng dưới 0,8, S tăng khoảng 15 điểm. Nhưng S làm hại khi model khá chắc: ở độ tự tin 0,8–0,9, S giảm 7,9 điểm.
  - Ở luật, Qwen bị S làm sai 30 câu vốn đúng, trong khi chỉ được sửa đúng 7 câu.

## 1. Kết quả cũ thấp vì đâu

Mỗi câu được hỏi cả B lẫn S, nên ta so được B và S trên cùng câu. Ba lý do dưới đây tách được khỏi nhau.

**Thiếu bước tính toán (Qwen).** Trên VMLU test, nhóm vmlu.ai gọi là STEM tăng từ 65,2 lên 82,1, trong khi ba nhóm còn lại chỉ tăng 5–6 điểm. Mình chia lại 58 môn thành ba nhóm (danh sách ở mục [Cách chia môn](#cách-chia-môn)). Nhóm tính toán có 13 môn, gồm toán, lý, hóa, thống kê, kiến trúc máy tính và kỹ thuật điện:
- Trước khi hỏi từng bước, Qwen làm nhóm này **kém hơn** nhóm kiến thức Việt Nam (61,1 so với 69,6).
- Sau khi hỏi từng bước, nhóm này lại **hơn hẳn** (84,1 so với 74,0).

Vậy điểm cũ của Qwen ở toán, lý, hóa thấp vì nó phải đoán chữ cái mà không được tính, không phải vì nó đọc đề tiếng Việt kém.

Vi-DROP cho cùng kết luận. Các câu cần cộng trừ, so sánh hay đếm tăng 26–31 điểm. Riêng loại "selection" (chọn một đoạn có sẵn trong bài) gần như không đổi: −4,2 với Qwen, +5,0 với MiMo.

**Định dạng câu trả lời làm điểm thấp oan (MiMo, đọc hiểu).** Bảng "đọc hiểu, thước chấm chính và hai cách chấm nới lỏng" so ba cách chấm:
- token-F1 và EM: thước chấm đã đăng ký;
- "chứa đáp án": đáp án chuẩn, sau khi chuẩn hóa, xuất hiện nguyên cụm trong câu trả lời;
- "số đầu tiên": chỉ dùng cho các câu Vi-DROP có đáp án là một con số; kiểm tra xem số đầu tiên model viết ra có đúng không.

Kết quả với MiMo:
- Ở Vi-DROP, MiMo hỏi thẳng có token-F1 54,0, nhưng 78,0% câu trả lời chứa đáp án và 80,3% có số đầu tiên đúng. Câu trả lời dài trung bình 57 ký tự, trong khi đáp án chuẩn chỉ là một con số.
- Với S, F1 lên 77,6, nhưng tỷ lệ "chứa đáp án" vẫn 76,5% và tỷ lệ "số đầu tiên" là 86,8%.

Nên phần lớn mức tăng F1 của MiMo đến từ việc S bắt model kết thúc bằng một dòng `Đáp án:` ngắn, không phải từ việc model hiểu bài hơn. ViBidLQA cũng vậy: B của MiMo "chứa đáp án" nhiều hơn S (79,8 so với 75,5), nhưng F1 thấp hơn vì viết dài hơn (105 so với 77 ký tự).

Qwen thì khác. Khi hỏi thẳng, nó trả lời Vi-DROP rất ngắn (9 ký tự), nên mức tăng của nó là thật: tỷ lệ "số đầu tiên" tăng từ 44,7 lên 78,9.

**Thiếu kiến thức (cả hai model).** Nhóm 21 môn kiến thức đặc thù Việt Nam chỉ tăng 4,4 điểm với Qwen. 7 trong 21 môn tăng không quá 2 điểm. Các môn tăng ít nhất là "Tiếng Việt và văn học" (−0,6), "Luật hành chính" (0,0), "Luật dân sự" (+0,6), "Địa lý THPT" (+0,6) và "Pháp luật đại cương" (+1,6).

MiMo hỏi thẳng, dù có thinking, cũng chỉ đạt 75,1 ở nhóm này, gần như bằng Qwen sau vòng lặp (74,0). Suy nghĩ thêm không tạo ra được kiến thức mà model không có.

## 2. Khả năng tiếng Việt thật tới đâu

Muốn tách "hiểu tiếng Việt" khỏi "biết kiến thức", ta cần những phép đo đưa sẵn thông tin cho model. Có ba phép đo như vậy:

- **Tìm thông tin trong đoạn văn tiếng Việt: tốt.** Ở Vi-SQuAD, cả hai model đạt 89–91 token-F1, và S gần như không đổi gì. Model đã đọc và tìm đúng chỗ trong văn bản tiếng Việt ngay khi hỏi thẳng.
- **Đọc văn bản luật tiếng Việt khi có văn bản: tốt.**
  - Ở MC-100, trên 23 câu Legal MC mà Qwen từng sai, đưa đúng điều luật vào prompt nâng tỷ lệ đúng từ 37,0% lên 82,6% (p = 0,0004). Trên 25 câu nó vốn đúng, tỷ lệ đúng gần như không đổi (94,0 → 96,0).
  - Ở MC-96 (ViBidLQA, Qwen), khi bộ tìm kiếm lấy trúng đoạn văn của câu hỏi, điểm bằng hẳn điểm khi được đưa đúng đoạn (67,9 so với 67,9). Khi tìm trượt, điểm tụt xuống 32,0, so với 62,1 nếu có đúng đoạn.
  - Nút thắt ở đây là có văn bản hay không, không phải đọc văn bản.
- **Kiến thức về Việt Nam: trần chung khoảng 74–75%.** Cả Qwen sau vòng lặp lẫn MiMo đều dừng ở mức này trong nhóm kiến thức đặc thù Việt Nam.
  - "Tiếng Việt và văn học" nằm trong nhóm thấp nhất của cả hai model. Với Qwen sau vòng lặp, đây là môn thấp nhất (55,2, ngang "Kế toán thuế"). Với MiMo, nó đứng thứ năm từ dưới lên (62,6). Đây lại là môn gần với "ngôn ngữ" nhất. Có thể hiểu là: đọc hiểu câu chữ tiếng Việt thông thường thì tốt, nhưng kiến thức về chính tiếng Việt (ngữ pháp, tu từ, phân tích văn học) và kiến thức hành chính – pháp luật Việt Nam thì yếu.
  - "Luật hành chính" của MiMo chỉ 50,0.

Gộp lại, hai model đọc hiểu tiếng Việt thông thường tốt. Chúng yếu ở hai chỗ:
- kiến thức đặc thù Việt Nam, kể cả kiến thức về tiếng Việt;
- với Qwen, các phép tính nhiều bước khi không được trình bày lời giải.

Báo cáo này chưa tách được hẳn "ngôn ngữ" khỏi "kiến thức", vì ta chưa đo cùng câu hỏi bằng tiếng Anh.

## 3. Điều gì giúp model trả lời tiếng Việt tốt hơn

Xếp theo độ lớn của bằng chứng đã có:

1. **Đưa đúng văn bản.** Đây là đòn bẩy mạnh nhất: +45,6 điểm trên các câu luật mà model từng sai (MC-100). Nhưng muốn có lợi thì phải tìm trúng văn bản. Khi tìm trượt, Qwen chỉ giữ được khoảng một phần ba lợi ích: từ 14,8 lên 32,0, trong khi có đúng đoạn thì được 62,1 (MC-96). Ở Legal MC, cách tự tìm của MC-101 chỉ giữ được 38% lợi ích của việc đưa đúng điều luật.
2. **Hỏi từng bước, cho phần tính toán và cho model không có thinking.** Lợi ích tập trung ở môn tính toán (+23,0 trên VMLU test) và ở câu Vi-DROP cần phép tính. Với kiến thức, S tăng ít; với luật, S có hại cho Qwen. MiMo vốn đã suy nghĩ ẩn trước khi trả lời, nên S chỉ thêm 0–4,5 điểm ở trắc nghiệm.
3. **Ép một dòng đáp án ngắn.** Đòn bẩy này không làm model giỏi hơn, nhưng làm điểm đo đúng hơn khả năng thật, nhất là với model hay viết dài như MiMo.
4. **Bỏ phiếu nhiều lần.** Lợi ích nhỏ: không quá 2 điểm mỗi bộ, và không ô nào có ý nghĩa sau Holm. Nhưng mức đồng thuận giữa các lần là tín hiệu tốt để biết câu nào model không chắc. Ba lần S giống nhau thì S-r1 đúng 84–98% tùy bộ. Chỉ hai lần giống nhau thì S-r1 đúng 36–55%.

Những hướng chưa đo nên chưa kết luận được: fine-tune trên dữ liệu tiếng Việt; viết prompt bằng tiếng Anh cho câu hỏi tiếng Việt; model lớn hơn cùng họ; dịch câu hỏi sang tiếng Anh rồi trả lời. Thí nghiệm ViNumQA (MC-106, MC-107) chưa có kết quả để dùng ở đây.

## 4. Thước chấm có đủ khách quan không

| Thước chấm | Điểm mạnh | Điểm yếu đã thấy | Nên dùng thế nào |
|---|---|---|---|
| Trắc nghiệm, chấm theo chữ cái (VMLU, VM14K, Legal MC, NLI) | Khách quan. VMLU test chấm mù trên vmlu.ai. Không bị thổi bởi vị trí đáp án: đảo thứ tự lựa chọn ở Legal MC không đổi điểm, 89,04% trước và sau (MC-35/36, xem `docs/model-insights.md` mục 1.4). | Câu không đọc được chữ cái bị tính sai: ở VMLU valid có 10 trên 744 câu S của Qwen như vậy, cả 10 câu đều dùng hết trần 4.096 token trước khi viết dòng đáp án. Không đo được việc model đã thấy đề khi huấn luyện, vì VMLU là bộ công khai. Mỗi điều kiện chỉ chạy một lần, và mỗi môn trên VMLU test chỉ có khoảng 170 câu, nên khoảng tin cậy 95% của điểm một môn là khoảng ±7 điểm. | Dùng để so các điều kiện, và so theo nhóm nhiều môn (mỗi nhóm khoảng ±2 điểm). Không kết luận từ chênh lệch dưới khoảng 7 điểm ở một môn. |
| Đọc hiểu, token-F1 và EM | Tự động, chạy lại được, có sẵn đáp án chuẩn. | Chấm lẫn nội dung với định dạng. MiMo ở Vi-DROP: F1 54,0 nhưng 78,0% câu trả lời chứa đáp án. EM thấp hơn F1 từ 9 đến 39 điểm tùy bộ. MC-94: 34 trên 50 câu thua về EM vẫn đúng về nghĩa. MC-103: dấu `**` của Markdown làm tụt điểm ViBidLQA của MiMo; bộ chấm v3 đã sửa lỗi này. Đáp án chuẩn của Vi-SQuAD và Vi-DROP (bộ Reading-400, `reading-400-reviewed-v1`) có phần lấy lại từ câu trả lời của model rồi người duyệt. | Báo cáo F1 kèm ít nhất một cách chấm theo nghĩa. Khi so B với S, xem thêm độ dài câu trả lời. |
| Hai cách chấm nới lỏng trong báo cáo này | Tách được định dạng khỏi nội dung. | "Chứa đáp án" có lợi cho câu trả lời dài, vì câu dài dễ tình cờ chứa đáp án; nên đây là cận trên. "Số đầu tiên" chặt hơn, nhưng chỉ dùng được cho 76 câu Vi-DROP có đáp án là một con số. | Chỉ dùng để chẩn đoán, không thay thước chấm đã đăng ký. |
| Chấm bằng LLM | Có thể chấm theo nghĩa. | Dụng cụ judge của MC-37/38 đã trượt cổng kiểm định (`docs/model-insights.md` mục 1.5). | Chỉ dùng sau khi qua kiểm định với nhãn người chấm. |

Tóm lại, các con số trắc nghiệm đủ khách quan để nói "điều kiện A hơn điều kiện B". Con số đọc hiểu thì đo cả việc *trả lời đúng khuôn* lẫn việc *hiểu bài*. Muốn nói về "khả năng đọc hiểu", cần thêm một phép chấm theo nghĩa.

## 5. Suy nghĩ chi tiết có tỷ lệ thuận với đọc hiểu không

Không. Có bốn dấu hiệu:

- **Đọc hiểu tìm thông tin không đổi.** S gần như không đổi điểm Vi-SQuAD (+0,1 với Qwen, +1,7 với MiMo). S chỉ giúp khi câu hỏi cần một phép xử lý thêm sau khi đã đọc, như đếm, cộng trừ hay so sánh.
- **Lời giải dài đi kèm câu khó, không đi kèm câu đúng.**
  - Trong mọi bộ, một phần tư lời giải S dài nhất có tỷ lệ đúng thấp nhất. Ví dụ VMLU valid: Qwen 95,2% với nhóm ngắn nhất và 57,5% với nhóm dài nhất; MiMo 93,5% và 61,8%.
  - Phần suy nghĩ ẩn của MiMo khi hỏi thẳng cũng vậy. Ở Vi-DROP, MiMo đúng 71,3% khi suy nghĩ ngắn nhất, nhưng chỉ 23,4% khi suy nghĩ dài nhất.
  - Đây là tương quan, không phải nhân quả: model nghĩ lâu hơn ở câu nó thấy khó, và câu khó thì hay sai hơn. Nghĩ dài hơn không làm câu trả lời đúng hơn.
- **S giúp khi model chưa chắc, hại khi model khá chắc.**
  - Độ tự tin của Qwen ở đây là xác suất của chữ cái nó chọn khi hỏi thẳng. Dưới 0,8, S tăng khoảng 15 điểm. Từ 0,8 đến 0,9, S giảm 7,9 điểm. Từ 0,9 trở lên, gần như không đổi (−1,0).
  - Ở Legal MC và Legal NLI, S của Qwen làm sai 30 câu vốn đúng mà chỉ sửa đúng 7 câu: suy luận dài đã kéo model khỏi đáp án đúng ban đầu.
  - Đây cũng là lý do vòng tự sửa giữ đáp án hỏi thẳng khi model đã chắc.
- **Model có thinking được ít hơn từ S.** MiMo vốn đã suy nghĩ ẩn trước khi trả lời. S chỉ thêm 4,5 điểm ở VMLU valid, so với 10,5 điểm ở Qwen, và không đổi gì ở luật.

Vậy suy nghĩ chi tiết là một công cụ cho **tính toán** và cho **câu model chưa chắc**. Đọc hiểu là một kỹ năng riêng mà cả hai model đã có ở mức cao.

## 6. Hệ quả cho khóa luận

- **Cách phát biểu kết quả.**
  - "Hỏi từng bước nâng điểm VMLU của Qwen chủ yếu ở các môn tính toán. Kiến thức đặc thù Việt Nam là trần chung của hai model, và suy nghĩ thêm không vượt qua được trần này."
  - Không nên viết "S làm model hiểu tiếng Việt tốt hơn".
- **Đọc hiểu.** Khi báo cáo mức tăng của S ở đọc hiểu, nên kèm hai cách chấm nới lỏng hoặc một mẫu chấm theo nghĩa. Mức tăng Vi-DROP của MiMo nên ghi rõ là phần lớn do định dạng.
- **Các bước có thể làm tiếp, không cần request mới:**
  - chấm theo nghĩa một mẫu các cặp B/S lệch nhau ở Vi-DROP và ViBidLQA, theo cách của MC-94;
  - khi có điểm vmlu.ai của MC-110, so mẫu hình theo môn của MiMo với bảng ở đây.
- **Bước cần request mới, phải đăng ký trước:** tìm văn bản cho các môn kiến thức đặc thù Việt Nam (luật, sử, văn), vì đưa đúng văn bản là đòn bẩy mạnh nhất đã thấy.

## Giới hạn

- **Chọn sau khi đã xem kết quả.** Các cách chia nhóm và các phép so ở đây được chọn sau khi xem dữ liệu. Chúng là giả thuyết, cần kiểm chứng trên câu mới.
- **Cách chia môn là của nhóm nghiên cứu, không phải của vmlu.ai.** Danh sách đầy đủ ở dưới. Đổi vài môn giữa các nhóm có thể đổi các con số trung bình vài điểm.
- **MiMo trên VMLU test là MC-85,** chạy theo route khác MC-109 (Responses API, temperature 1). So với Qwen chỉ nên xem như mốc tham khảo. Bản hỏi thẳng và vòng lặp của MiMo theo đúng điều kiện MC-110 đang chạy.
- **Hai model, mỗi điều kiện một lượt chạy.** Những nhận xét về "model có thinking" mới dựa trên một model.
- **Không có bản tiếng Anh của cùng câu hỏi,** nên chưa tách hẳn được ngôn ngữ khỏi kiến thức.
- **Tương quan độ dài – đúng sai không phải nhân quả.**

## Bảng số liệu

Các bảng dưới đây do script sinh ra và được chép nguyên vào đây. Trắc nghiệm tính tỷ lệ đúng (%); đọc hiểu tính token-F1 theo bộ chấm v3. "Sai → đúng" và "Đúng → sai" đếm số câu mà S sửa đúng hoặc làm sai so với B; với đọc hiểu, một câu được đếm khi token-F1 thay đổi từ 0,5 trở lên.

### VMLU test (vmlu.ai): Qwen trước và sau vòng lặp (MC-109), MiMo hỏi thẳng (MC-85)

| Nhóm | Số môn | Qwen hỏi thẳng | Qwen vòng lặp | Tăng | MiMo hỏi thẳng | Số môn tăng ≤ 2 điểm |
|---|---|---:|---:|---:|---:|---:|
| Tính toán | 13 | 61,1 | 84,1 | 23,0 | 83,1 | 0 |
| Kiến thức đặc thù Việt Nam | 21 | 69,6 | 74,0 | 4,4 | 75,1 | 7 |
| Còn lại | 24 | 68,1 | 74,9 | 6,8 | 77,0 | 5 |


| Nhóm của vmlu.ai | Qwen hỏi thẳng | Qwen vòng lặp | MiMo hỏi thẳng |
|---|---|---:|---:|
| Nhân văn | 67,1 | 72,1 | 73,6 |
| Khác | 63,4 | 69,7 | 71,8 |
| Khoa học xã hội | 74,4 | 79,4 | 80,4 |
| STEM | 65,2 | 82,1 | 82,4 |
| Tổng | 67,1 | 76,6 | 77,7 |

Tám môn thấp nhất sau vòng lặp:


| Môn | Qwen hỏi thẳng | Qwen vòng lặp | MiMo hỏi thẳng |
|---|---|---:|---:|
| vietnamese_language_and_literature | 55,8 | 55,2 | 62,6 |
| tax_accountant | 44,2 | 55,2 | 58,0 |
| administrative_law | 55,6 | 55,6 | 50,0 |
| environmental_engineering | 55,6 | 57,9 | 59,1 |
| logic | 48,3 | 59,2 | 62,6 |
| preschool_pedagogy | 62,8 | 60,8 | 62,8 |
| education_law | 60,2 | 62,0 | 65,7 |
| business_administration | 67,8 | 63,2 | 71,3 |

### Qwen3.5-9B: hỏi thẳng (B-r1) và từng bước (S-r1) trên cùng câu

| Bộ | Nhóm | Số câu | B | S | S − B | Sai → đúng | Đúng → sai |
|---|---|---:|---:|---:|---:|---:|---:|
| VMLU valid | cả bộ | 744 | 69,9 | 80,4 | 10,5 | 114 | 36 |
| VMLU valid | Humanity | 229 | 67,2 | 71,6 | 4,4 | 23 | 13 |
| VMLU valid | Other | 112 | 60,7 | 71,4 | 10,7 | 23 | 11 |
| VMLU valid | STEM | 272 | 74,6 | 90,1 | 15,5 | 51 | 9 |
| VMLU valid | Social Science | 131 | 72,5 | 83,2 | 10,7 | 17 | 3 |
| Legal MC | cả bộ | 146 | 91,1 | 82,9 | -8,2 | 3 | 15 |
| Legal NLI | cả bộ | 150 | 90,7 | 83,3 | -7,4 | 4 | 15 |
| Vi-SQuAD | cả bộ | 200 | 89,7 | 89,8 | 0,1 | 11 | 9 |
| Vi-DROP | cả bộ | 200 | 54,3 | 75,4 | 21,1 | 52 | 9 |
| Vi-DROP | add_sub | 55 | 39,4 | 67,2 | 27,8 | 18 | 2 |
| Vi-DROP | comparison | 57 | 55,0 | 85,9 | 30,9 | 16 | 0 |
| Vi-DROP | count | 40 | 38,9 | 65,4 | 26,5 | 14 | 4 |
| Vi-DROP | other | 7 | 47,1 | 54,3 | 7,2 | 1 | 0 |
| Vi-DROP | selection | 41 | 89,4 | 85,2 | -4,2 | 3 | 3 |
| ViBidLQA test | cả bộ | 603 | 65,0 | 67,6 | 2,6 | 45 | 31 |
| VMLU dev (MC-104) | cả bộ | 303 | 73,6 | 79,5 | 5,9 | 36 | 18 |
| VM14K (MC-104) | cả bộ | 300 | 64,3 | 68,3 | 4,0 | 38 | 26 |

### Qwen3.5-9B: đọc hiểu, thước chấm chính và hai cách chấm nới lỏng

| Bộ | Số câu | B F1 | B EM | B chứa đáp án | B số đầu tiên (Vi-DROP) | S F1 | S EM | S chứa đáp án | S số đầu tiên (Vi-DROP) | Độ dài B (ký tự) | Độ dài S (ký tự) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Vi-SQuAD | 200 | 89,7 | 76,0 | 90,5 | – | 89,8 | 73,0 | 84,5 | – | 29 | 29 |
| Vi-DROP | 200 | 54,3 | 45,0 | 50,5 | 44,7 | 75,4 | 65,0 | 68,5 | 78,9 | 9 | 72 |
| ViBidLQA test | 603 | 65,0 | 26,0 | 50,1 | – | 67,6 | 29,0 | 57,2 | – | 84 | 91 |

### Qwen3.5-9B: điểm của S-r1 theo độ dài lời giải (tứ phân vị token sinh ra trong mỗi bộ)

| Bộ | Ngắn nhất | Thứ 2 | Thứ 3 | Dài nhất |
|---|---|---:|---:|---:|
| VMLU valid | 95,2 (435 token) | 86,6 (575 token) | 82,3 (725 token) | 57,5 (1.181 token) |
| Legal MC | 94,4 (614 token) | 97,2 (727 token) | 86,1 (857 token) | 55,3 (1.239 token) |
| Legal NLI | 97,3 (348 token) | 91,9 (429 token) | 78,4 (481 token) | 66,7 (732 token) |
| Vi-SQuAD | 90,2 (119 token) | 87,1 (162 token) | 91,7 (200 token) | 90,2 (266 token) |
| Vi-DROP | 83,7 (153 token) | 73,7 (209 token) | 77,0 (280 token) | 67,3 (397 token) |
| ViBidLQA test | 75,2 (161 token) | 71,3 (226 token) | 68,7 (306 token) | 55,6 (484 token) |
| VMLU dev (MC-104) | 92,0 (431 token) | 93,3 (573 token) | 76,0 (726 token) | 57,7 (1.133 token) |
| VM14K (MC-104) | 84,0 (484 token) | 81,3 (617 token) | 60,0 (807 token) | 48,0 (1.447 token) |

### Qwen3.5-9B: trắc nghiệm, theo độ tự tin của lần hỏi thẳng

| Độ tự tin của B | Số câu | B | S | S − B |
|---|---|---:|---:|---:|
| < 0,5 | 248 | 35,5 | 50,8 | 15,3 |
| 0,5–0,8 | 452 | 53,8 | 68,6 | 14,8 |
| 0,8–0,9 | 177 | 76,8 | 68,9 | -7,9 |
| ≥ 0,9 | 762 | 96,7 | 95,7 | -1,0 |

### Qwen3.5-9B: trắc nghiệm, ba lần S có trả lời giống nhau không

| Bộ | 3/3 giống: tỷ lệ câu | 3/3: S-r1 đúng | 2/3 giống: tỷ lệ câu | 2/3: S-r1 đúng |
|---|---|---:|---:|---:|
| VMLU valid | 78% | 90,9 | 19% | 45,7 |
| Legal MC | 77% | 95,5 | 20% | 41,4 |
| Legal NLI | 86% | 89,1 | 14% | 47,6 |
| VMLU dev (MC-104) | 79% | 91,6 | 19% | 37,3 |
| VM14K (MC-104) | 64% | 85,9 | 31% | 40,9 |

### MiMo V2.6 Flash: hỏi thẳng (B-r1) và từng bước (S-r1) trên cùng câu

| Bộ | Nhóm | Số câu | B | S | S − B | Sai → đúng | Đúng → sai |
|---|---|---:|---:|---:|---:|---:|---:|
| VMLU valid | cả bộ | 743 | 77,9 | 82,4 | 4,5 | 74 | 41 |
| VMLU valid | Humanity | 229 | 69,4 | 74,7 | 5,3 | 27 | 15 |
| VMLU valid | Other | 112 | 69,6 | 71,4 | 1,8 | 12 | 10 |
| VMLU valid | STEM | 271 | 89,3 | 93,4 | 4,1 | 21 | 10 |
| VMLU valid | Social Science | 131 | 76,3 | 82,4 | 6,1 | 14 | 6 |
| Legal MC | cả bộ | 146 | 91,8 | 91,8 | 0,0 | 4 | 4 |
| Legal NLI | cả bộ | 150 | 89,3 | 89,3 | 0,0 | 5 | 5 |
| Vi-SQuAD | cả bộ | 200 | 88,9 | 90,6 | 1,7 | 5 | 3 |
| Vi-DROP | cả bộ | 200 | 54,0 | 77,6 | 23,6 | 58 | 6 |
| Vi-DROP | add_sub | 55 | 48,9 | 68,5 | 19,6 | 12 | 0 |
| Vi-DROP | comparison | 57 | 54,9 | 83,5 | 28,6 | 19 | 1 |
| Vi-DROP | count | 40 | 36,9 | 74,4 | 37,5 | 19 | 3 |
| Vi-DROP | other | 7 | 21,6 | 66,7 | 45,1 | 4 | 0 |
| Vi-DROP | selection | 41 | 81,7 | 86,7 | 5,0 | 4 | 2 |
| ViBidLQA test | cả bộ | 603 | 72,9 | 76,6 | 3,7 | 29 | 20 |
| VMLU dev (MC-104) | cả bộ | 303 | 81,8 | 83,8 | 2,0 | 25 | 19 |
| VM14K (MC-104) | cả bộ | 300 | 70,7 | 73,7 | 3,0 | 30 | 21 |

### MiMo V2.6 Flash: đọc hiểu, thước chấm chính và hai cách chấm nới lỏng

| Bộ | Số câu | B F1 | B EM | B chứa đáp án | B số đầu tiên (Vi-DROP) | S F1 | S EM | S chứa đáp án | S số đầu tiên (Vi-DROP) | Độ dài B (ký tự) | Độ dài S (ký tự) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Vi-SQuAD | 200 | 88,9 | 73,0 | 89,0 | – | 90,6 | 72,5 | 87,5 | – | 36 | 31 |
| Vi-DROP | 200 | 54,0 | 33,5 | 78,0 | 80,3 | 77,6 | 64,0 | 76,5 | 86,8 | 57 | 10 |
| ViBidLQA test | 603 | 72,9 | 39,6 | 79,8 | – | 76,6 | 47,4 | 75,5 | – | 105 | 77 |

### MiMo V2.6 Flash: điểm của S-r1 theo độ dài lời giải (tứ phân vị token sinh ra trong mỗi bộ)

| Bộ | Ngắn nhất | Thứ 2 | Thứ 3 | Dài nhất |
|---|---|---:|---:|---:|
| VMLU valid | 93,5 (337 token) | 90,9 (464 token) | 83,3 (610 token) | 61,8 (1.139 token) |
| Legal MC | 94,4 (506 token) | 100,0 (645 token) | 100,0 (752 token) | 73,7 (1.419 token) |
| Legal NLI | 100,0 (391 token) | 86,5 (463 token) | 97,3 (530 token) | 74,4 (757 token) |
| Vi-SQuAD | 93,7 (144 token) | 95,0 (193 token) | 91,4 (243 token) | 82,1 (352 token) |
| Vi-DROP | 88,7 (169 token) | 79,9 (253 token) | 69,1 (347 token) | 72,7 (718 token) |
| ViBidLQA test | 84,8 (219 token) | 81,8 (284 token) | 78,2 (365 token) | 61,9 (521 token) |
| VMLU dev (MC-104) | 93,3 (316 token) | 88,0 (433 token) | 85,3 (578 token) | 69,2 (901 token) |
| VM14K (MC-104) | 81,3 (413 token) | 82,7 (597 token) | 74,7 (809 token) | 56,0 (1.663 token) |

### MiMo V2.6 Flash: điểm của B-r1 theo độ dài phần suy nghĩ ẩn (reasoning token)

| Bộ | Ngắn nhất | Thứ 2 | Thứ 3 | Dài nhất |
|---|---|---:|---:|---:|
| VMLU valid | 83,8 (27 token) | 85,9 (65 token) | 79,5 (123 token) | 62,8 (386 token) |
| Legal MC | 100,0 (68 token) | 94,4 (100 token) | 91,7 (157 token) | 81,6 (341 token) |
| Legal NLI | 100,0 (85 token) | 91,9 (107 token) | 89,2 (136 token) | 76,9 (214 token) |
| Vi-SQuAD | 95,0 (9 token) | 92,8 (26 token) | 93,0 (44 token) | 75,0 (69 token) |
| Vi-DROP | 71,3 (24 token) | 68,0 (51 token) | 53,3 (83 token) | 23,4 (235 token) |
| ViBidLQA test | 76,5 (22 token) | 81,3 (50 token) | 73,2 (71 token) | 60,9 (111 token) |
| VMLU dev (MC-104) | 89,3 (29 token) | 82,7 (61 token) | 86,7 (124 token) | 69,2 (344 token) |
| VM14K (MC-104) | 80,0 (51 token) | 80,0 (106 token) | 70,7 (217 token) | 52,0 (580 token) |

### MiMo V2.6 Flash: trắc nghiệm, ba lần S có trả lời giống nhau không

| Bộ | 3/3 giống: tỷ lệ câu | 3/3: S-r1 đúng | 2/3 giống: tỷ lệ câu | 2/3: S-r1 đúng |
|---|---|---:|---:|---:|
| VMLU valid | 82% | 90,0 | 17% | 49,2 |
| Legal MC | 88% | 98,4 | 10% | 35,7 |
| Legal NLI | 93% | 92,1 | 7% | 54,5 |
| VMLU dev (MC-104) | 78% | 93,7 | 20% | 52,5 |
| VM14K (MC-104) | 75% | 83,6 | 21% | 46,9 |

### Khi được đưa đúng văn bản (Qwen)

| Thí nghiệm | Nhóm câu | Số câu | Không có văn bản | Có văn bản đúng |
|---|---|---:|---:|---:|
| MC-100 Legal MC | B từng sai | 23 | 37,0 | 82,6 |
| MC-100 Legal MC | B luôn đúng | 25 | 94,0 | 96,0 |


| MC-96 ViBidLQA (token-F1) | Số câu | Không văn bản (B) | Văn bản tự tìm (K) | Văn bản đúng (O) |
|---|---|---:|---:|---:|
| tìm trúng đoạn của câu | 231 | 14,4 | 67,9 | 67,9 |
| tìm trượt | 69 | 14,8 | 32,0 | 62,1 |

## Cách chia môn

Cách chia này do nhóm nghiên cứu đặt ra để phân tích, không phải nhóm môn của vmlu.ai. Mỗi nhóm lấy trung bình không trọng số của điểm các môn trong nhóm.

- **Tính toán (13 môn):** `elementary_mathematics`, `middle_school_mathematics`, `high_school_mathematics`, `discrete_mathematics`, `statistics_and_probability`, `introduction_to_physics`, `middle_school_physics`, `high_school_physics`, `introduction_to_chemistry`, `middle_school_chemistry`, `high_school_chemistry`, `computer_architecture`, `electrical_engineering`.
- **Kiến thức đặc thù Việt Nam (21 môn):** `vietnamese_language_and_literature`, `high_school_literature`, `middle_school_literature`, `administrative_law`, `business_law`, `civil_law`, `criminal_law`, `economic_law`, `education_law`, `introduction_to_laws`, `elementary_history`, `middle_school_history`, `high_school_history`, `introduction_to_vietnam_culture`, `ho_chi_minh_ideology`, `revolutionary_policy_of_the_vietnamese_commununist_part`, `high_school_geography`, `middle_school_geography`, `middle_school_civil_education`, `high_school_civil_education`, `idealogical_and_moral_cultivation`.
- **Còn lại (24 môn):** các môn khác, ví dụ kế toán, y dược, tin học ứng dụng, sinh học, kinh tế học, xã hội học, logic, lịch sử văn minh thế giới.

## Nguồn số liệu

- **Script:** `code_benchmark/analyze_model_capability.py`. Chạy lại bằng `.venv/bin/python -m code_benchmark.analyze_model_capability --markdown <file>`; không có `--markdown` thì in báo cáo JSON.
- **Điểm vmlu.ai:** `docs/research/qwen-vmlu-test-server-grade-mc109-{before,loop}-2026-11-07.json` và `docs/research/mimo26-vmlu-test-server-grade-mc85-2026-10-15.json`.
- **Từng lượt hỏi:**
  - MC-105: `all_res/diagnostic_router_loop/table_loop/<model>/scores.jsonl`.
  - MC-104: `all_res/diagnostic_router_loop/self_loop/<model>/scores.jsonl`, chỉ lấy VMLU dev và VM14K.
- **Đưa văn bản cho model:**
  - MC-100: `all_res/diagnostic_legal_oracle/run/<model>/analysis/legal_oracle_report.json`.
  - MC-96: `all_res/diagnostic_k2/heldout/<model>/analysis/k2_report.json`, lượt luân phiên 1.
- **Số liệu trích từ tài liệu khác:**
  - MC-94: commit `97db8d7`.
  - MC-35/36 và MC-37/38: `docs/model-insights.md`.
  - MC-101: thẻ MC-101.
  - Bỏ phiếu: `docs/router-before-after/pareto.md`.
