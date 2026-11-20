# Luồng hành động của hai harness với hai model (Pha 1b, khám phá)

Ngày 2026-11-20. **Đây là phân tích khám phá, không đăng ký trước.** Phân tích không gửi request nào.

- **Mục đích.** Chủ dự án nêu yêu cầu: "quan trọng là ta phải quan sát flow log của harness… vì harness nào cũng call api tới model, cái quan trọng là actions nó thực hiện". Tài liệu này mô tả, cho từng model và từng harness, những gì diễn ra xung quanh các lần gọi model.
- **Nguồn dữ liệu.** Mỗi lượt có hai log: luồng sự kiện của chính harness (`events.jsonl`) và log của proxy (`proxy_log.jsonl`). `code_benchmark/harness_flow.py` (7 test) ghép hai log này thành một dòng thời gian.
- **Bốn ô.** Qwen3.5-9B lấy từ MC-112, MC-113 và MC-114; MiMo-V2.6-Flash lấy từ MC-116. Lượt 1–2, cùng 646 câu.
- **Báo cáo.** `all_res/diagnostic_legal_agent_mimo/flows/flow_report.json`, SHA-256 `0344d454…`. Module tạo báo cáo là `code_benchmark/analyze_harness_flows.py`.

**Ký hiệu hành động:**
- `G+` / `G0`: grep có kết quả / grep rỗng.
- `F`: glob.
- `Rm`: đọc một khoảng mà **model tự chọn** (`offset`/`limit`).
- `Rh`: đọc một trang mà **harness tự cắt**.
- `Re`: đọc mà omp **bỏ phần giữa** file.
- `C`: harness tự nén ngữ cảnh.
- `A`: trả lời.

## Phát hiện chính: ai điều khiển cửa sổ đọc

| Trắc nghiệm (246 câu) | Qwen dsh | Qwen omp | MiMo dsh | MiMo omp |
|---|---:|---:|---:|---:|
| Điểm | 77,4 | 68,5 | 85,6 | 91,3 |
| Lần đọc có khoảng do model chọn | 77,8% | 63,5% | 98,6% | 94,3% |
| Lần đọc bị harness tự cắt trang | 0% | **32,4%** | 0% | 2,8% |
| Lần đọc bị bỏ phần giữa file | 0% | **16,1%** | 0% | 0,9% |
| Độ dài kết quả read (trung vị, ký tự) | 6.171 | **15.249** | 4.670 | 3.759 |
| Trả lời ngay sau grep, không đọc | 12,8% | **51,0%** | 22,2% | 30,1% |
| Điểm khi câu trả lời theo sau một lần read | **81,3** | **61,8** | 92,9 | 93,9 |
| Điểm khi câu trả lời theo sau một lần grep | 76,2 | 74,9 | 83,5 | 88,5 |
| Lượt bị harness nén ngữ cảnh | 0% | 4,9% | 0% | **14,0%** |
| Điểm khi trả lời sau khi bị nén | – | 55,0 | – | 71,2 |

ViBidLQA (400 câu) cho cùng hướng, và rõ hơn:
- **Qwen trong omp:** 41,8% số lần đọc bị harness cắt trang, 40% bị bỏ phần giữa. Kết quả read dài 21.410 ký tự (trung vị). Điểm khi trả lời sau một lần read là 26,4, so với 40,5 ở dsh.
- **MiMo trong omp:** gần như mọi lần đọc là khoảng do model chọn (98,5%). Điểm khi trả lời sau một lần read là 59,9, so với 52,6 ở dsh.

**Diễn giải (khám phá, chưa kiểm chứng nhân quả):**

1. **MiMo tự điều khiển cửa sổ đọc, Qwen phó mặc cho harness.**
   - Khi model gọi `read` mà không nêu khoảng, omp tự cắt một trang và đôi khi bỏ phần giữa của file dài. Qwen rơi vào trường hợp này ở một phần ba đến hai phần năm số lần đọc trong omp. Model nhận về những trang rất dài nhưng thiếu đoạn, và trả lời kém hơn khi đã đọc so với ở dsh: 61,8 so với 81,3.
   - MiMo hầu như luôn tự nêu khoảng dòng, nên cơ chế phân trang và bỏ phần giữa của omp gần như không chạm tới nó.
   - Đây là cơ chế cụ thể đứng sau con số "phần trong cùng trạng thái đọc" của Pha 1. Hai model cùng "đã đọc tới điều luật", nhưng nhận về hai thứ khác nhau.
2. **grep của omp trả về kèm dòng ngữ cảnh, nên dễ thành lối tắt.**
   - Trong omp, Qwen trả lời ngay sau grep ở 51% số lượt (so với 13% ở dsh). Chuỗi hay gặp nhất của Qwen là `G+ A` (27%).
   - MiMo dùng grep để định vị rồi đọc đúng khoảng: các chuỗi phổ biến `G+x2 Rm A` và `F+ G+ Rm A` đạt 97–100 điểm.
3. **Nén ngữ cảnh là hành động harness tự làm, và nó gây hại chứ không có lợi.**
   - omp nén ngữ cảnh ở 14% số lượt trắc nghiệm của MiMo, vì MiMo gọi nhiều công cụ và suy nghĩ dài, và ở 4,9% của Qwen.
   - Trả lời sau khi bị nén thì điểm thấp hơn ở cả hai model (MiMo 71,2, Qwen 55,0).
   - Vậy nén ngữ cảnh không giải thích vì sao MiMo thắng trong omp. Nếu có tác động thì nó còn kéo MiMo xuống.
4. **Luồng hành động tách nhau ngay từ bước đầu.**
   - Chỉ 4–7% số cặp (cùng câu, cùng lượt) có chuỗi hành động giống hệt nhau giữa hai harness, và chỗ rẽ nhánh đầu tiên nằm ở bước 0–1.
   - Với Qwen ở trắc nghiệm, 13% số cặp rẽ nhánh đúng tại chỗ: dsh đọc (`Rm`) còn omp trả lời luôn (`A`).

## Hệ quả cho MC-117

- **Prompt của dsh nói đúng hành động bị thiếu.** Nó có câu "Use the read tool … Use offset and limit to continue reading large files". Nếu thay prompt mặc định của omp bằng prompt này mà Qwen bắt đầu tự chọn khoảng đọc (tỉ lệ `Rh` và `Re` giảm) thì P1 sẽ dương.
- **Luồng hành động là chỉ số cơ chế.** Trong MC-117, hai số theo dõi chính là tỉ lệ lần đọc có khoảng do model chọn và tỉ lệ trả lời ngay sau grep, đo trên OMPS so với OMPF cho từng model.
- **Thí nghiệm tiếp theo.** Nếu prompt không làm Qwen tự chọn khoảng, ứng viên kế tiếp là chính cách omp đọc mặc định (cỡ trang, bỏ phần giữa).

## Giới hạn

- **Không phải nhân quả.** Model tự chọn hành động, nên nhóm "trả lời sau read" và nhóm "trả lời sau grep" là hai nhóm câu khác nhau.
- **Thẻ ngôn ngữ của bản tóm tắt chỉ là ước lượng thô.** Bản tóm tắt gắn nhãn `vi` khi ít nhất 3% chữ cái có dấu tiếng Việt. Những bản có tiêu đề tiếng Anh nhưng trích câu hỏi tiếng Việt vẫn được gắn `vi`.
- **Chỉ hai lượt mỗi ô, hai model.**
