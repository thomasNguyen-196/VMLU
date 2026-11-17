# Điểm và chi phí của vòng tự sửa: hỏi bao nhiêu lần là đủ

Báo cáo ngày 2026-11-07. Đây là **phân tích sau (post hoc), chỉ để khám phá**. Không có request mới, cũng không đăng ký điều kiện đo mới. Mọi con số được tính lại từ các lượt hỏi đã chấm của MC-105 (các bộ của `/table`, 2.043 câu) và MC-104 (603 câu trắc nghiệm mới). Script tính lại bốn chính sách đã đăng ký (hỏi thẳng, luôn S, bỏ phiếu 3 S, vòng tự sửa 3 vòng) và so với hai báo cáo cũ. Chỉ cần lệch một chữ số là script dừng. Lần chạy này khớp hết. Câu hỏi của báo cáo: với mỗi bộ dữ liệu, cần hỏi model bao nhiêu lần để được điểm cao nhất với số token hợp lý.

## Tóm tắt

- **Trắc nghiệm với Qwen: 2 vòng hiệu quả nhất.** Trên 1.040 câu trắc nghiệm của MC-105, 2 vòng đạt 82,60% với 659 token mỗi câu. Luôn S đạt 81,15% với 1.027 token, còn 3 vòng (đã đăng ký) đạt 83,75% với 1.144 token. 2 vòng giữ được khoảng 85% mức tăng của 3 vòng so với hỏi thẳng, nhưng chỉ tốn khoảng một nửa số token thêm. Trên 603 câu mới của MC-104 cũng vậy: 2 vòng 75,12% (726 token), luôn S 73,96% (1.049 token), 3 vòng 76,29% (1.334 token).
- **Trên câu mới, 2 vòng đạt điều kiện mà 3 vòng đã trượt.** MC-104 đăng ký điều kiện: vòng tự sửa không kém luôn S quá 1 điểm (cận dưới của khoảng 95% phải trên −1,0) và tốn ít token hơn. 3 vòng trượt vì tốn hơn luôn S 27%. 2 vòng hơn luôn S 1,16 điểm [−0,33; 2,65] với 69% số token. Đây là kết quả tính sau, không thay kết luận đã đăng ký. Muốn khẳng định thì cần một lượt chạy có đăng ký trước (xem [Bước tiếp theo](#bước-tiếp-theo-có-thể-làm)).
- **Đọc hiểu: luôn S vừa rẻ vừa tốt ngang hoặc hơn 2 vòng và 3 vòng.** Ở đọc hiểu, vòng 1 phải hỏi thẳng hai lần để so, nên riêng vòng 1 đã tốn gần bằng hoặc hơn một lần S. Gộp đọc hiểu của Qwen: luôn S 73,60 token-F1 với 982 token, 2 vòng 73,33 với 1.809, 3 vòng 73,77 với 2.492. Ở Vi-DROP, 2 vòng kém luôn S 6,83 điểm (Qwen, p Holm 0,014). Lý do: khi hai lần hỏi thẳng ra cùng một đáp án sai, vòng lặp dừng ngay ở vòng 1.
- **Ở nơi S gây hại, chỉ nên hỏi thẳng.** Với Qwen, S kém hỏi thẳng 8,22 điểm ở Legal MC và 7,33 điểm ở Legal NLI (p Holm 0,056 và 0,116). 2 vòng giảm thiệt hại: ở Legal NLI chỉ còn −0,67, và hơn luôn S 6,67 điểm (p Holm 0,021). Nhưng ở Legal MC, 2 vòng vẫn kém hỏi thẳng 6,16 điểm. Ở cả hai bộ, chỉ có hỏi thẳng là không bị chính sách nào khác vượt.
- **Hai lần S thêm của vòng 3 mua được rất ít.** Theo từng ô, 3 vòng hơn 2 vòng nhiều nhất 2,05 điểm (Qwen, Legal MC), có ô còn kém hơn. Không ô nào có ý nghĩa sau Holm (p Holm nhỏ nhất 0,296). Gộp trắc nghiệm của Qwen, 3 vòng hơn 2 vòng 1,15 điểm [0,29; 2,12] nhưng tốn thêm 485 token mỗi câu. Bỏ phiếu 3 S cho điểm cao nhất ở vài ô (MiMo ở VMLU valid 85,08%, cả hai model ở Vi-DROP 77–79), với khoảng 2.200–3.100 token mỗi câu.
- **Với MiMo (model có thinking), suy luận thêm giúp ít ở trắc nghiệm.** Trên câu mới, 2 vòng (78,44%) không hơn luôn S (78,77%) và đắt hơn: mỗi lần hỏi thẳng của MiMo đã tốn khoảng 420 token vì có thinking, mà vòng 1 phải hỏi hai lần. Mỗi 1.000 token thêm, 2 vòng nâng MiMo 2,8 điểm, còn với Qwen là 10,1 điểm.

## Quy tắc phân bổ rút ra (đề xuất, chưa kiểm chứng)

Từ các bảng dưới đây, có thể rút ra một quy tắc chọn cách hỏi theo loại câu và loại model. Quy tắc này được rút ra trên chính dữ liệu MC-104 và MC-105, nên chỉ là giả thuyết cho một lượt chạy mới.

| Loại câu | Model không thinking (Qwen3.5-9B) | Model có thinking (MiMo V2.6 Flash) |
|---|---|---|
| Trắc nghiệm kiến thức (VMLU, VM14K) | 2 vòng: chắc thì giữ, chưa chắc thì S | Hỏi thẳng hoặc luôn S; cổng hỏi thẳng hai lần không đáng tiền |
| Trắc nghiệm luật (Legal MC, Legal NLI) | Hỏi thẳng | Hỏi thẳng (các chính sách chênh nhau không quá 2 điểm) |
| Đọc hiểu cần tính toán (Vi-DROP) | Luôn S | Luôn S |
| Đọc hiểu trích xuất (Vi-SQuAD) | Hỏi thẳng (chênh dưới 1 điểm) | Hỏi thẳng hoặc luôn S (chênh dưới 2,4 điểm, không có ý nghĩa sau Holm) |
| Đọc hiểu luật (ViBidLQA) | Luôn S; 2 vòng hơn luôn S 1,53 điểm nhưng tốn gần gấp đôi token | Luôn S |

## Năm chính sách được so

Mỗi chính sách trả tiền cho mọi lượt hỏi mà nó phải đọc.

1. **Hỏi thẳng (B):** lấy câu trả lời B-r1.
2. **2 vòng:** vòng 1 giống hệt vòng tự sửa đã đăng ký. Với trắc nghiệm của Qwen, vòng 1 đọc xác suất của chữ cái được chọn và giữ đáp án nếu từ 0,80 trở lên. Với MiMo và với đọc hiểu, vòng 1 hỏi thẳng hai lần và giữ đáp án nếu hai lần trùng nhau. Câu chưa chắc thì lấy luôn câu trả lời S-r1, không hỏi thêm. Ngưỡng 0,80 của MC-104 vốn được chọn trên dữ liệu thiết kế theo đúng quy tắc 2 vòng này.
3. **3 vòng (đã đăng ký, MC-104 và MC-105):** như 2 vòng, nhưng nếu S-r1 không khớp câu trả lời nào ở vòng 1 thì hỏi S thêm hai lần và lấy đa số của ba lần S.
4. **Luôn S:** lấy S-r1.
5. **Bỏ phiếu 3 S:** lấy đa số của S-r1, S-r2, S-r3.

## Cách đọc bảng

- Trắc nghiệm tính tỷ lệ đúng (%). Đọc hiểu tính token-F1 theo bộ chấm v3.
- Số trong ngoặc là token trung bình mỗi câu: tổng token endpoint báo (prompt và câu trả lời, kể cả thinking của MiMo), cộng qua mọi lượt hỏi mà chính sách cần. Với trắc nghiệm của Qwen, hỏi thẳng là lần probe đọc log-probability, chỉ sinh 4 token.
- **In đậm** là chính sách nằm trên đường Pareto của ô: không có chính sách nào khác vừa điểm bằng hoặc cao hơn, vừa token bằng hoặc ít hơn, và hơn hẳn ở ít nhất một trong hai.
- "Câu chưa chắc" là tỷ lệ câu mà vòng 1 không giữ đáp án.
- Trong bảng gộp, số sau dấu "·" là số điểm tăng so với hỏi thẳng trên mỗi 1.000 token thêm: (điểm − điểm hỏi thẳng) ÷ (token − token hỏi thẳng) × 1.000.
- Chênh lệch theo cặp là trung bình chênh lệch trên từng câu, kèm khoảng 95% bootstrap và p của phép thử đổi dấu (sign-flip). Holm hiệu chỉnh riêng từng cột trong từng nguồn: 12 ô của MC-105, 4 ô của MC-104. Phép thử dùng 20.000 lần đổi dấu, nên p nhỏ nhất là 1/20.001; sau Holm, các p nhỏ nhất hiện thành 0,001. Bảng gộp không hiệu chỉnh Holm.

## Kết quả

### Gộp theo loại bài: điểm (token mỗi câu) · điểm tăng so với B trên 1.000 token thêm

| Nguồn | Model | Gộp | Số câu | Hỏi thẳng (B) | 2 vòng | 3 vòng (đã đăng ký) | Luôn S | Bỏ phiếu 3 S |
|---|---|---|---:|---:|---:|---:|---:|---:|
| MC-105 | Qwen3.5-9B | trắc nghiệm | 1.040 | **75,87 (164)** | **82,60 (659) · 13,6** | **83,75 (1.144) · 8,0** | 81,15 (1.027) · 6,1 | 82,79 (3.076) · 2,4 |
| MC-105 | Qwen3.5-9B | đọc hiểu | 1.003 | **67,79 (646)** | 73,33 (1.809) · 4,8 | **73,77 (2.492) · 3,2** | **73,60 (982) · 17,3** | **74,69 (2.960) · 3,0** |
| MC-105 | MiMo V2.6 Flash | trắc nghiệm | 1.040 | **81,44 (409)** | **85,10 (1.084) · 5,4** | **85,29 (1.184) · 5,0** | **84,71 (1.074) · 4,9** | **86,92 (3.159) · 2,0** |
| MC-105 | MiMo V2.6 Flash | đọc hiểu | 1.003 | **72,34 (432)** | **79,74 (1.230) · 9,3** | **80,30 (1.588) · 6,9** | **79,59 (733) · 24,2** | **80,34 (2.180) · 4,6** |
| MC-104 (câu mới) | Qwen3.5-9B | trắc nghiệm (VMLU dev + VM14K) | 603 | **68,99 (118)** | **75,12 (726) · 10,1** | **76,29 (1.334) · 6,0** | 73,96 (1.049) · 5,3 | **76,45 (3.135) · 2,5** |
| MC-104 (câu mới) | MiMo V2.6 Flash | trắc nghiệm (VMLU dev + VM14K) | 603 | **76,29 (423)** | 78,44 (1.205) · 2,8 | 78,44 (1.390) · 2,2 | **78,77 (1.137) · 3,5** | **80,27 (3.619) · 1,2** |

### MC-105, các bộ của /table: điểm và token mỗi câu

| Model | Bộ | Hỏi thẳng (B) | 2 vòng | 3 vòng (đã đăng ký) | Luôn S | Bỏ phiếu 3 S | Câu chưa chắc |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen3.5-9B | VMLU valid | **69,89 (124)** | **80,65 (697)** | **81,99 (1.265)** | 80,38 (1.022) | 81,99 (3.031) | 45,6% |
| Qwen3.5-9B | Legal MC | **91,10 (223)** | 84,93 (675) | 86,99 (1.107) | 82,88 (1.211) | 84,93 (3.701) | 32,2% |
| Qwen3.5-9B | Legal NLI | **90,67 (302)** | 90,00 (455) | 89,33 (583) | 83,33 (878) | 84,67 (2.693) | 15,3% |
| Qwen3.5-9B | Vi-SQuAD | **89,74 (446)** | **90,61 (1.063)** | 90,03 (1.255) | **89,81 (692)** | 89,19 (2.085) | 22,5% |
| Qwen3.5-9B | Vi-DROP | **54,27 (328)** | 68,59 (1.083) | 69,66 (1.562) | **75,41 (719)** | **77,26 (2.203)** | 53,0% |
| Qwen3.5-9B | ViBidLQA test | **64,99 (818)** | **69,16 (2.298)** | **69,74 (3.211)** | **67,63 (1.165)** | 69,03 (3.501) | 55,7% |
| MiMo V2.6 Flash | VMLU valid | **77,82 (383)** | **82,93 (1.092)** | **83,20 (1.217)** | **82,39 (1.067)** | **85,08 (3.109)** | 17,9% |
| MiMo V2.6 Flash | Legal MC | **91,78 (453)** | **92,47 (1.096)** | 92,47 (1.169) | 91,78 (1.259) | 92,47 (3.810) | 7,5% |
| MiMo V2.6 Flash | Legal NLI | **89,33 (494)** | 88,67 (1.034) | 88,67 (1.034) | 89,33 (932) | **90,67 (2.773)** | 4,7% |
| MiMo V2.6 Flash | Vi-SQuAD | **88,95 (519)** | **91,09 (1.279)** | **91,29 (1.489)** | **90,56 (753)** | 90,51 (2.249) | 29,0% |
| MiMo V2.6 Flash | Vi-DROP | **53,99 (477)** | 75,58 (1.539) | 76,02 (2.234) | **77,61 (821)** | **78,57 (2.405)** | 65,5% |
| MiMo V2.6 Flash | ViBidLQA test | **72,92 (389)** | **77,35 (1.111)** | **78,08 (1.406)** | **76,60 (696)** | 77,55 (2.083) | 43,0% |

### MC-105, các bộ của /table: chênh lệch theo cặp câu (điểm, khoảng 95%, p Holm)

| Model | Bộ | S − B | 2 vòng − B | 2 vòng − luôn S | 2 vòng − 3 vòng | Token 2 vòng / luôn S |
|---|---|---:|---:|---:|---:|---:|
| Qwen3.5-9B | VMLU valid | 10,48 [7,39; 13,44], p Holm 0,001 | 10,75 [7,93; 13,58], p Holm 0,001 | 0,27 [-0,81; 1,48], p Holm 1,000 | -1,34 [-2,42; -0,27], p Holm 0,333 | 68% |
| Qwen3.5-9B | Legal MC | -8,22 [-13,70; -3,42], p Holm 0,056 | -6,16 [-11,64; -1,37], p Holm 0,207 | 2,05 [0,00; 4,79], p Holm 1,000 | -2,05 [-5,48; 0,68], p Holm 1,000 | 56% |
| Qwen3.5-9B | Legal NLI | -7,33 [-12,67; -2,00], p Holm 0,116 | -0,67 [-4,67; 2,67], p Holm 1,000 | 6,67 [3,33; 11,33], p Holm 0,021 | 0,67 [0,00; 2,00], p Holm 1,000 | 52% |
| Qwen3.5-9B | Vi-SQuAD | 0,06 [-3,16; 3,54], p Holm 1,000 | 0,87 [-1,38; 3,08], p Holm 1,000 | 0,80 [-1,76; 3,24], p Holm 1,000 | 0,58 [0,00; 1,50], p Holm 1,000 | 154% |
| Qwen3.5-9B | Vi-DROP | 21,15 [14,95; 27,96], p Holm 0,001 | 14,32 [8,96; 19,80], p Holm 0,001 | -6,83 [-10,91; -3,00], p Holm 0,014 | -1,07 [-3,15; 0,95], p Holm 1,000 | 151% |
| Qwen3.5-9B | ViBidLQA test | 2,64 [0,27; 5,21], p Holm 0,156 | 4,18 [2,23; 6,14], p Holm 0,001 | 1,53 [0,27; 2,85], p Holm 0,192 | -0,58 [-1,13; -0,11], p Holm 0,296 | 197% |
| MiMo V2.6 Flash | VMLU valid | 4,57 [1,75; 7,66], p Holm 0,015 | 5,11 [3,09; 7,53], p Holm 0,001 | 0,54 [-1,21; 2,28], p Holm 1,000 | -0,27 [-0,81; 0,27], p Holm 1,000 | 102% |
| MiMo V2.6 Flash | Legal MC | 0,00 [-4,11; 3,42], p Holm 1,000 | 0,68 [-2,05; 3,42], p Holm 1,000 | 0,68 [-1,37; 3,42], p Holm 1,000 | 0,00 [0,00; 0,00], p Holm 1,000 | 87% |
| MiMo V2.6 Flash | Legal NLI | 0,00 [-4,00; 4,00], p Holm 1,000 | -0,67 [-2,00; 0,00], p Holm 1,000 | -0,67 [-4,67; 3,33], p Holm 1,000 | 0,00 [0,00; 0,00], p Holm 1,000 | 111% |
| MiMo V2.6 Flash | Vi-SQuAD | 1,61 [-0,85; 4,41], p Holm 0,994 | 2,15 [0,24; 4,19], p Holm 0,207 | 0,53 [-1,26; 2,27], p Holm 1,000 | -0,20 [-0,59; 0,00], p Holm 1,000 | 170% |
| MiMo V2.6 Flash | Vi-DROP | 23,62 [17,53; 29,47], p Holm 0,001 | 21,60 [16,20; 27,10], p Holm 0,001 | -2,03 [-4,37; 0,24], p Holm 0,815 | -0,43 [-2,85; 1,98], p Holm 1,000 | 187% |
| MiMo V2.6 Flash | ViBidLQA test | 3,68 [1,85; 5,54], p Holm 0,001 | 4,43 [2,96; 5,99], p Holm 0,001 | 0,75 [-0,11; 1,72], p Holm 0,861 | -0,72 [-1,42; -0,07], p Holm 0,333 | 160% |

### MC-104, câu mới (VMLU dev, VM14K): điểm và token mỗi câu

| Model | Bộ | Hỏi thẳng (B) | 2 vòng | 3 vòng (đã đăng ký) | Luôn S | Bỏ phiếu 3 S | Câu chưa chắc |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen3.5-9B | VMLU dev | **73,60 (120)** | **79,54 (592)** | **80,53 (1.032)** | 79,54 (996) | **82,51 (2.933)** | 40,9% |
| Qwen3.5-9B | VM14K | **64,33 (116)** | **70,67 (862)** | **72,00 (1.638)** | 68,33 (1.103) | 70,33 (3.339) | 57,0% |
| MiMo V2.6 Flash | VMLU dev | **81,85 (363)** | **83,83 (884)** | 83,83 (1.021) | 83,83 (944) | **86,47 (3.024)** | 13,9% |
| MiMo V2.6 Flash | VM14K | **70,67 (484)** | 73,00 (1.529) | 73,00 (1.762) | **73,67 (1.332)** | **74,00 (4.220)** | 22,7% |

### MC-104, câu mới (VMLU dev, VM14K): chênh lệch theo cặp câu (điểm, khoảng 95%, p Holm)

| Model | Bộ | S − B | 2 vòng − B | 2 vòng − luôn S | 2 vòng − 3 vòng | Token 2 vòng / luôn S |
|---|---|---:|---:|---:|---:|---:|
| Qwen3.5-9B | VMLU dev | 5,94 [1,65; 10,56], p Holm 0,076 | 5,94 [1,65; 10,23], p Holm 0,040 | 0,00 [-1,98; 1,98], p Holm 1,000 | -0,99 [-2,97; 0,99], p Holm 1,000 | 59% |
| Qwen3.5-9B | VM14K | 4,00 [-1,33; 9,00], p Holm 0,504 | 6,33 [1,67; 11,33], p Holm 0,040 | 2,33 [0,33; 4,33], p Holm 0,258 | -1,33 [-4,00; 1,00], p Holm 1,000 | 78% |
| MiMo V2.6 Flash | VMLU dev | 1,98 [-1,98; 6,27], p Holm 0,530 | 1,98 [-0,66; 4,62], p Holm 0,472 | 0,00 [-3,30; 3,30], p Holm 1,000 | 0,00 [0,00; 0,00], p Holm 1,000 | 94% |
| MiMo V2.6 Flash | VM14K | 3,00 [-1,67; 7,67], p Holm 0,530 | 2,33 [-1,33; 6,00], p Holm 0,472 | -0,67 [-3,67; 2,33], p Holm 1,000 | 0,00 [-1,00; 1,00], p Holm 1,000 | 115% |

## Giới hạn

- **Chọn sau khi đã xem kết quả.** Chính sách 2 vòng và mọi so sánh ở đây được chọn sau khi đã xem kết quả của MC-104 và MC-105. Chúng chỉ để khám phá, không thay kết luận đã đăng ký của hai thẻ đo.
- **MC-105 không phải tập mới.** Các bộ của `/table` đã được dùng để thiết kế router trước đó (MC-90 đến MC-95). MC-104 là câu mới, nhưng ngưỡng 0,80 được chọn trên dữ liệu thiết kế theo quy tắc 2 vòng.
- **Chưa có VMLU test.** VMLU test không có đáp án tại máy, chỉ vmlu.ai chấm được, nên MC-109 và MC-110 không có mặt ở đây.
- **Token không phải tiền.** Token là con số endpoint báo. Giá theo token của hai model khác nhau, và bảng không quy ra tiền.
- **Hai model, mỗi điều kiện một lượt chạy.** Kết luận về "model có thinking" và "model không thinking" mới dựa trên đúng hai model.

## Bước tiếp theo có thể làm

1. **Kiểm tra 2 vòng trên VMLU test mà không gửi request mới.** MC-109 hỏi Qwen theo từng vòng: B-r1 cho mọi câu, S-r1 cho mọi câu chưa chắc. Vì vậy có thể dựng file nộp của chính sách 2 vòng từ các lượt đã ghi. Đăng ký trước một thẻ đo cho file này, rồi chủ đề tài nộp lên vmlu.ai. vmlu.ai chấm mù, nên đây sẽ là phép kiểm tra bên ngoài cho chính sách 2 vòng. Với MiMo, làm tương tự sau khi MC-110 chạy xong.
2. **Kiểm chứng quy tắc phân bổ ở trên** trên câu mới, có đăng ký trước, so với luôn S và với 3 vòng.

## Nguồn số liệu

- Script: `code_benchmark/analyze_loop_pareto.py`. Test offline: `code_benchmark/test_analyze_loop_pareto.py`. Chạy lại bằng `.venv/bin/python -m code_benchmark.analyze_loop_pareto --markdown <file>`.
- Báo cáo JSON (gitignored): `all_res/diagnostic_router_loop/pareto/loop_pareto_report.json`, sha256 `f75f9b6d615d6d11e366fd05527b7767abfadc8cb89e0dc0359cb15473ee9109`.
- Đầu vào MC-105: báo cáo `all_res/diagnostic_router_loop/table_loop/analysis/table_loop_report.json` (sha256 bắt đầu `8b9a526b49286ca7`), `scores.jsonl` của Qwen (`586ffb01ddcdc179…`) và MiMo (`0b3f7fea9cff7927…`).
- Đầu vào MC-104: báo cáo `all_res/diagnostic_router_loop/self_loop/analysis/self_loop_report.json` (sha256 bắt đầu `f213879703b3eb31`), `scores.jsonl` của Qwen (`1f366f0237ae4ae8…`) và MiMo (`a9858124e991b1c9…`).
- Các bảng ở mục Kết quả được script sinh ra và chép nguyên vào đây.
