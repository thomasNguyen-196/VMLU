# Tương tác model × harness ở legal agent: kết quả phân tích theo bước (Pha 1)

Ngày 2026-11-20. Đây là **phân tích khám phá, không đăng ký trước**. Kế hoạch (`docs/research/legal-agent-interaction-plan-2026-11-20.md`, SHA-256 `641ef1aa…`) được viết và băm lúc 13:42 +07, trước khi xem các số theo bước của MiMo. Module chạy là `code_benchmark/analyze_legal_agent_interaction.py`, kèm 6 test. Báo cáo nằm ở `all_res/diagnostic_legal_agent_mimo/interaction/interaction_report.json`, SHA-256 `b5f33252d7159a247689efc233af881734907ed0f976e551c8eef7ad77cab9bf`. Phân tích không gửi request nào. Mức tương tác trên toàn bộ câu khớp với báo cáo đăng ký của MC-116: +14,63 ở trắc nghiệm, +11,64 ở ViBidLQA.

## Tóm tắt

- **Tương tác không nằm ở chỗ agent có đọc tới điều luật hay không, mà ở bước trả lời.** Trên các câu xác định được điều luật:
  - **Trắc nghiệm:** mức tương tác 14,44 [8,89; 20,22]. Phần do tỉ lệ đọc chỉ có 0,93 [−2,37; 4,11]; phần trong cùng trạng thái đọc là 13,51 [6,97; 20,18], tức **93,5%**.
  - **ViBidLQA:** phần trong cùng trạng thái là 6,80 [2,75; 10,84], tức **58,4%**. Phần do tỉ lệ đọc là 4,84 [3,20; 6,62], cũng khác 0.
  - Theo quy tắc đọc đã viết trước, cả hai nhóm đều được xếp là "tương tác nằm ở bước trả lời khi cùng trạng thái đọc".
- **omp làm cả hai model ít đọc tới điều luật hơn**, nhưng chỉ Qwen bị thiệt.

  | Tỉ lệ đọc tới điều luật | DSHF | OMPF |
  |---|---:|---:|
  | Qwen, trắc nghiệm | 56,7% | 21,3% |
  | MiMo, trắc nghiệm | 88,0% | 68,2% |
  | Qwen, ViBidLQA | 41,9% | 20,8% |
  | MiMo, ViBidLQA | 83,1% | 68,8% |

  Ở omp, bước mà agent dừng lại thường gặp nhất là "thấy tên tệp trong kết quả grep nhưng không mở". Ở trắc nghiệm, Qwen dừng ở bước này 47,6% số lượt, MiMo 25,1%.
- **Khi cả hai harness đều đã đọc điều luật của cùng một câu, kết quả trái chiều nhau:**
  - **Qwen:** OMPF − DSHF = −16,15 ở trắc nghiệm (65 câu; OMPF tốt hơn 4 câu, DSHF tốt hơn 17; p dấu 0,007) và −6,94 ở ViBidLQA (p 0,066).
  - **MiMo:** +6,32 ở trắc nghiệm (182 câu; OMPF tốt hơn 21 câu, DSHF tốt hơn 2; p 0,0001) và +8,59 ở ViBidLQA (OMPF tốt hơn 194 câu, DSHF tốt hơn 87).
- **Không phải do các lượt dừng không có đáp án.** Bỏ các lượt `answer_cap`, `request_cap` và `harness_end` đi thì mức tương tác vẫn gần như nguyên: 14,04 [8,51; 19,36] ở trắc nghiệm và 12,15 ở ViBidLQA. Lý do là DSHF của Qwen cũng có lượt dừng (3,25%). Con số +2,75 ghi trong kế hoạch là khoảng cách của riêng MiMo, chưa phải mức tương tác.

## Bảng theo ô (trắc nghiệm, 246 câu; 225 câu có điều luật)

| | Qwen DSHF | Qwen OMPF | MiMo DSHF | MiMo OMPF |
|---|---:|---:|---:|---:|
| Điểm | 77,44 | 68,50 | 85,57 | 91,26 |
| Dừng không có đáp án (%) | 3,25 | 0,20 | 5,69 | 1,02 |
| Đọc tới điều luật (%) | 56,7 | 21,3 | 88,0 | 68,2 |
| Thấy tệp nhưng không mở (%) | 18,9 | 47,6 | 6,2 | 25,1 |
| Điểm khi đã đọc | 79,2 | 66,7 | 87,4 | 93,2 |
| Điểm khi chưa đọc | 78,5 | 69,8 | 90,7 | 90,9 |
| Số lệnh / lượt | 5,1 | 3,6 | 8,2 | 7,4 |
| Đọc theo trang của omp / lượt | 0 | 0,82 | 0 | 1,29 |
| Grep ra rỗng (% số grep) | 26,8 | 32,8 | 26,3 | 25,0 |
| Token / lượt | 97.145 | 74.478 | 93.910 | 120.553 |

Hai nhóm con của trắc nghiệm cho cùng một hướng:
- **Legal MC:** mức tương tác 11,57; phần trong cùng trạng thái chiếm 86%.
- **Luật VMLU:** mức tương tác 18,30. Phần trong cùng trạng thái là 20,34; phần tỉ lệ đọc −1,66, tức đi ngược chiều.

Bảng đầy đủ của cả bốn nhóm nằm trong báo cáo JSON (in ra bằng tùy chọn `--markdown`).

## Sửa một kết luận trước đó: lỗi Unicode nằm trong dữ liệu ViBidLQA, không do Qwen sinh ra

Phần dò grep trước đó (`all_res/diagnostic_legal_agent_mimo/analysis_vi/`) viết rằng "Qwen sinh ra chữ Việt bị tách dấu". **Điều đó sai.**
- **Lỗi nằm trong dữ liệu gốc.** Các file ViBidLQA gốc (`v_legal_slsp/bidlqa/*.jsonl`) không ở dạng NFC: khoảng 22% ký tự là dấu tách rời, và có cả chuỗi hỏng như `nưo` + U+031B U+0301 thay cho `nước`. Toàn bộ 400 prompt ViBidLQA mang lỗi này. Prompt Legal MC và VMLU thì không. Kho văn bản luật ở dạng NFC.
- **Qwen chỉ chép lại byte.** 188/229 pattern lỗi của Qwen (82%) chứa một từ bị tách dấu được chép nguyên văn từ câu hỏi. Mã byte khác kho văn bản, nên grep trả về rỗng.
- **MiMo thì không.** MiMo luôn viết lại ở dạng NFC: 0 pattern lỗi.
- **Ý nghĩa.** Đây vẫn là một cơ chế riêng của tiếng Việt: dấu xếp chồng nên dạng NFC và NFD khác nhau. Nhưng nó là tương tác giữa **dữ liệu và model**, không phải lỗi sinh chữ của Qwen. Nó làm Qwen ít tìm thấy điều luật hơn ở ViBidLQA trên **cả hai** harness (7,6% grep lỗi ở DSHF, 5,6% ở OMPF). Vì vậy nó góp vào mức điểm của Qwen hơn là vào mức tương tác giữa harness.
- **Không ảnh hưởng đến điểm.** Bộ chấm chuẩn hóa NFC trước khi so sánh. Nhưng ở mọi card có ViBidLQA, model đều đọc câu hỏi ở dạng tách dấu.

## Diễn giải và giới hạn

- **Đây là liên hệ, không phải nhân quả.** Việc đọc tới điều luật không được ngẫu nhiên hóa.
- **Bước trả lời là nơi hai harness khác nhau nhiều nhất.** Đó là ngữ cảnh mà model nhìn thấy khi trả lời. omp có system prompt dài 8.641 ký tự với quy ước của agent lập trình, đọc theo trang, kết quả grep kèm dòng ngữ cảnh và cắt ở 768 ký tự. dsh có system prompt ngắn (441 ký tự) và hiện số dòng.

  Phân tích này không tách được thành phần nào của omp gây ra chênh lệch, cũng không tách được đặc tính nào của MiMo có lợi. MiMo có thinking, mạnh hơn và chạy qua route khác.
- **Chỉ có hai lượt mỗi ô.** Lượt 3–4 của Qwen (MC-115) chưa được dùng để kiểm tra độ vững.

## Bước tiếp theo đề xuất

1. **Pha 2 (MC-117, đăng ký trước).** Chạy Qwen bật thinking và tắt thinking trên cả hai harness, với cùng trọng số và cùng route. Nếu Qwen có thinking trả lời tốt hơn khi ở trong omp, giống MiMo, thì thinking là đặc tính quyết định bước trả lời. Cần thử trước xem IEC có cho bật thinking không.
2. **Bỏ từng thành phần của omp.** Ứng viên đầu tiên là system prompt: chạy omp với prompt ngắn (`--system-prompt minimal` đã có trong `run_harness_eval`) trên cả hai model.
3. **ViBidLQA ở dạng NFC so với nguyên trạng.** Đây là một thí nghiệm rẻ và riêng của tiếng Việt: chạy nhánh hỏi thẳng (C) và một nhánh agent, đăng ký trước, cho cả hai model.
