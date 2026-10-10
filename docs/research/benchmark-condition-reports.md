# Báo cáo điều kiện và benchmark

Nguồn: measurement_card.md và artifact từng run. Projection reporting v1; giữ metric/denominator lịch sử.

## Main V1 · sáu dataset tiếng Việt

So sánh theo cấu hình danh nghĩa; API và cách provider diễn giải auto vẫn khác. Nhóm suy luận/sampling khác có condition riêng.

### Condition

**Muse Spark 1.3 Contributor · MC-53**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-06T12:04:19.482260+00:00 → 2026-10-06T13:38:18.855745+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-responses · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; provider default; omitted on Responses API |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model |
| History / session / sandbox | one process per item; no persisted session; stable x-opencode-session per item |
| Giới hạn output | multiple_choice: 4096 token; reading: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts resume cùng cấu hình |
| Gold / cách chấm | V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold |
| Model / quantization | zen-go/muse-spark-1.3-contributor; quantization không công bố trong metadata |

**MiMo V2.6 Flash · MC-54**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-06T13:38:42.528186+00:00 → 2026-10-06T16:33:22.875762+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-completions · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; thinking mode provider default; custom temperature ignored |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model |
| History / session / sandbox | one process per item; no persisted session; stable x-opencode-session per item |
| Giới hạn output | multiple_choice: 4096 token; reading: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts resume cùng cấu hình |
| Gold / cách chấm | V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold |
| Model / quantization | zen-go/mimo-v2.6-flash; quantization không công bố trong metadata |

**MiMo V2.5 · MC-55**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-06T14:02:14.411046+00:00 → 2026-10-06T16:44:12.594499+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-completions · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; thinking mode provider default; custom temperature ignored |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model |
| History / session / sandbox | one process per item; no persisted session; stable x-opencode-session per item |
| Giới hạn output | multiple_choice: 4096 token; reading: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts resume cùng cấu hình |
| Gold / cách chấm | V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold |
| Model / quantization | zen-go/mimo-v2.5; quantization không công bố trong metadata |

**Qwen3.5-9B-65K · MC-56**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-06T11:46:17.908628+00:00 → 2026-10-07T02:16:01.328946+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | IEC internal endpoint · openai-completions · llmapi.iec |
| Temperature gửi / hiệu lực | gửi 0.0; hiệu lực theo metadata 0.0; profile/model config |
| Thinking / reasoning level | off; reasoning tắt; effort không ghim mức low/medium/high |
| Seed | gửi 42 |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model |
| History / session / sandbox | one process per item; no persisted session; stable x-opencode-session per item |
| Giới hạn output | multiple_choice: 4096 token; reading: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts resume cùng cấu hình |
| Gold / cách chấm | V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold |
| Model / quantization | iec/Qwen3.5-9B-65K; quantization không công bố trong metadata |

**Qwen3.5-9B-65K · MC-72**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-10T07:26:55.637344+00:00 → 2026-10-10T07:51:18.852650+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | IEC internal endpoint · openai-completions · llmapi.iec |
| Temperature gửi / hiệu lực | gửi 1.0; hiệu lực theo metadata 1.0; explicit 1.0; nominally matched to OpenCode Go |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model |
| History / session / sandbox | one process per item; no persisted session; stable x-opencode-session per item |
| Giới hạn output | multiple_choice: 4096 token; reading: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts resume cùng cấu hình |
| Gold / cách chấm | V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold |
| Model / quantization | iec/Qwen3.5-9B-65K; quantization không công bố trong metadata |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor / MC-53 | VMLU valid | Accuracy | 744 | 678 | 91.13 | 88.87 | 92.97 | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | Vi-SQuAD | EM | 200 | — | 74.50 | 68.37 | 80.90 | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | Vi-SQuAD | Token-F1 | 200 | — | 89.01 | 85.39 | 92.50 | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | Vi-DROP | EM | 200 | — | 58.50 | 51.87 | 64.82 | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | Vi-DROP | Token-F1 | 200 | — | 73.86 | 68.81 | 78.75 | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | Legal MC | Accuracy | 146 | 136 | 93.15 | 87.85 | 96.24 | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | Legal NLI | Accuracy | 150 | 120 | 80.00 | 72.89 | 85.62 | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | ViBidLQA test | EM | 603 | — | 50.25 | 46.14 | 54.30 | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | ViBidLQA test | Token-F1 | 603 | — | 76.89 | 74.11 | 79.56 | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | VMLU valid / Humanity | Accuracy | 229 | 201 | 87.77 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | VMLU valid / Other | Accuracy | 112 | 101 | 90.18 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | VMLU valid / STEM | Accuracy | 272 | 258 | 94.85 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-53 | VMLU valid / Social Science | Accuracy | 131 | 118 | 90.08 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-54 | VMLU valid | Accuracy | 744 | 596 | 80.11 | 77.09 | 82.82 | — | — | — |
| MiMo V2.6 Flash / MC-54 | Vi-SQuAD | EM | 200 | — | 67.00 | 60.70 | 73.58 | — | — | — |
| MiMo V2.6 Flash / MC-54 | Vi-SQuAD | Token-F1 | 200 | — | 86.45 | 82.94 | 90.03 | — | — | — |
| MiMo V2.6 Flash / MC-54 | Vi-DROP | EM | 200 | — | 24.00 | 18.13 | 29.90 | — | — | — |
| MiMo V2.6 Flash / MC-54 | Vi-DROP | Token-F1 | 200 | — | 50.00 | 45.04 | 54.86 | — | — | — |
| MiMo V2.6 Flash / MC-54 | Legal MC | Accuracy | 146 | 119 | 81.51 | 74.43 | 86.97 | — | — | — |
| MiMo V2.6 Flash / MC-54 | Legal NLI | Accuracy | 150 | 130 | 86.67 | 80.30 | 91.20 | — | — | — |
| MiMo V2.6 Flash / MC-54 | ViBidLQA test | EM | 603 | — | 38.97 | 34.80 | 42.93 | — | — | — |
| MiMo V2.6 Flash / MC-54 | ViBidLQA test | Token-F1 | 603 | — | 74.30 | 71.75 | 76.87 | — | — | — |
| MiMo V2.6 Flash / MC-54 | VMLU valid / Humanity | Accuracy | 229 | 167 | 72.93 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-54 | VMLU valid / Other | Accuracy | 112 | 71 | 63.39 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-54 | VMLU valid / STEM | Accuracy | 272 | 250 | 91.91 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-54 | VMLU valid / Social Science | Accuracy | 131 | 108 | 82.44 | — | — | — | — | — |
| MiMo V2.5 / MC-55 | VMLU valid | Accuracy | 744 | 570 | 76.61 | 73.44 | 79.51 | — | — | — |
| MiMo V2.5 / MC-55 | Vi-SQuAD | EM | 200 | — | 58.00 | 51.26 | 64.97 | — | — | — |
| MiMo V2.5 / MC-55 | Vi-SQuAD | Token-F1 | 200 | — | 78.32 | 73.74 | 82.87 | — | — | — |
| MiMo V2.5 / MC-55 | Vi-DROP | EM | 200 | — | 25.50 | 19.21 | 31.61 | — | — | — |
| MiMo V2.5 / MC-55 | Vi-DROP | Token-F1 | 200 | — | 43.30 | 37.69 | 48.89 | — | — | — |
| MiMo V2.5 / MC-55 | Legal MC | Accuracy | 146 | 121 | 82.88 | 75.94 | 88.12 | — | — | — |
| MiMo V2.5 / MC-55 | Legal NLI | Accuracy | 150 | 129 | 86.00 | 79.54 | 90.66 | — | — | — |
| MiMo V2.5 / MC-55 | ViBidLQA test | EM | 603 | — | 29.35 | 25.62 | 33.05 | — | — | — |
| MiMo V2.5 / MC-55 | ViBidLQA test | Token-F1 | 603 | — | 66.05 | 63.27 | 68.69 | — | — | — |
| MiMo V2.5 / MC-55 | VMLU valid / Humanity | Accuracy | 229 | 163 | 71.18 | — | — | — | — | — |
| MiMo V2.5 / MC-55 | VMLU valid / Other | Accuracy | 112 | 69 | 61.61 | — | — | — | — | — |
| MiMo V2.5 / MC-55 | VMLU valid / STEM | Accuracy | 272 | 240 | 88.24 | — | — | — | — | — |
| MiMo V2.5 / MC-55 | VMLU valid / Social Science | Accuracy | 131 | 98 | 74.81 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-56 | VMLU valid | Accuracy | 744 | 499 | 67.07 | 63.61 | 70.35 | — | — | — |
| Qwen3.5-9B-65K / MC-56 | Vi-SQuAD | EM | 200 | — | 80.00 | 74.60 | 85.50 | — | — | — |
| Qwen3.5-9B-65K / MC-56 | Vi-SQuAD | Token-F1 | 200 | — | 91.85 | 88.88 | 94.80 | — | — | — |
| Qwen3.5-9B-65K / MC-56 | Vi-DROP | EM | 200 | — | 50.50 | 43.88 | 57.29 | — | — | — |
| Qwen3.5-9B-65K / MC-56 | Vi-DROP | Token-F1 | 200 | — | 59.82 | 53.70 | 65.90 | — | — | — |
| Qwen3.5-9B-65K / MC-56 | Legal MC | Accuracy | 146 | 125 | 85.62 | 79.01 | 90.40 | — | — | — |
| Qwen3.5-9B-65K / MC-56 | Legal NLI | Accuracy | 150 | 139 | 92.67 | 87.35 | 95.86 | — | — | — |
| Qwen3.5-9B-65K / MC-56 | ViBidLQA test | EM | 603 | — | 25.21 | 21.74 | 28.96 | — | — | — |
| Qwen3.5-9B-65K / MC-56 | ViBidLQA test | Token-F1 | 603 | — | 63.80 | 61.01 | 66.72 | — | — | — |
| Qwen3.5-9B-65K / MC-56 | VMLU valid / Humanity | Accuracy | 229 | 140 | 61.14 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-56 | VMLU valid / Other | Accuracy | 112 | 70 | 62.50 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-56 | VMLU valid / STEM | Accuracy | 272 | 198 | 72.79 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-56 | VMLU valid / Social Science | Accuracy | 131 | 91 | 69.47 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-72 | Vi-SQuAD | EM | 200 | — | 74.50 | 68.14 | 81.00 | — | — | — |
| Qwen3.5-9B-65K / MC-72 | Vi-SQuAD | Token-F1 | 200 | — | 89.08 | 85.69 | 92.37 | — | — | — |
| Qwen3.5-9B-65K / MC-72 | Vi-DROP | EM | 200 | — | 47.50 | 40.39 | 54.64 | — | — | — |
| Qwen3.5-9B-65K / MC-72 | Vi-DROP | Token-F1 | 200 | — | 56.40 | 49.93 | 62.88 | — | — | — |
| Qwen3.5-9B-65K / MC-72 | Legal MC | Accuracy | 146 | 123 | 84.25 | 77.47 | 89.27 | — | — | — |
| Qwen3.5-9B-65K / MC-72 | Legal NLI | Accuracy | 150 | 136 | 90.67 | 84.94 | 94.36 | — | — | — |
| Qwen3.5-9B-65K / MC-72 | ViBidLQA test | EM | 603 | — | 25.54 | 22.19 | 28.96 | — | — | — |
| Qwen3.5-9B-65K / MC-72 | ViBidLQA test | Token-F1 | 603 | — | 64.85 | 62.10 | 67.67 | — | — | — |

### Comment

- Trong nhóm cấu hình khớp, số metric dataset đứng đầu: Muse Spark 1.3 Contributor: 7/9; Qwen3.5-9B-65K: 2/9. Kết quả phân biệt khả năng trả lời khớp reference ở đọc hiểu và làm MC/NLI; không tạo điểm tổng hợp ngôn ngữ.
- Các cột đọc hiểu cho biết model tái hiện được nội dung tham chiếu từ context đến mức nào. EM thấp nhưng F1 cao có thể là diễn đạt khác hoặc trả lời dài; muốn phân biệt với sai nội dung cần semantic/human judging. Legal MC và NLI cần đọc riêng vì đo dạng suy luận khác nhau.
- VMLU valid · Accuracy: Muse Spark 1.3 Contributor 91.13%, MiMo V2.6 Flash 80.11% (chênh 11.02 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- Vi-SQuAD · EM: Muse Spark 1.3 Contributor 74.50%, Qwen3.5-9B-65K 74.50% (chênh 0.00 pp); đây là khớp gold, trong nhóm cấu hình danh nghĩa khớp.
- Vi-SQuAD · Token-F1: Qwen3.5-9B-65K 89.08%, Muse Spark 1.3 Contributor 89.01% (chênh 0.07 pp); đây là khớp gold, trong nhóm cấu hình danh nghĩa khớp.
- Vi-DROP · EM: Muse Spark 1.3 Contributor 58.50%, Qwen3.5-9B-65K 47.50% (chênh 11.00 pp); đây là khớp gold, trong nhóm cấu hình danh nghĩa khớp.
- Vi-DROP · Token-F1: Muse Spark 1.3 Contributor 73.86%, Qwen3.5-9B-65K 56.40% (chênh 17.46 pp); đây là khớp gold, trong nhóm cấu hình danh nghĩa khớp.
- Legal MC · Accuracy: Muse Spark 1.3 Contributor 93.15%, Qwen3.5-9B-65K 84.25% (chênh 8.90 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- Legal NLI · Accuracy: Qwen3.5-9B-65K 90.67%, MiMo V2.6 Flash 86.67% (chênh 4.00 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- ViBidLQA test · EM: Muse Spark 1.3 Contributor 50.25%, MiMo V2.6 Flash 38.97% (chênh 11.28 pp); đây là khớp gold, trong nhóm cấu hình danh nghĩa khớp.
- ViBidLQA test · Token-F1: Muse Spark 1.3 Contributor 76.89%, MiMo V2.6 Flash 74.30% (chênh 2.59 pp); đây là khớp gold, trong nhóm cấu hình danh nghĩa khớp.
- VMLU valid / Humanity · Accuracy: Muse Spark 1.3 Contributor 87.77%, MiMo V2.6 Flash 72.93% (chênh 14.84 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU valid / Other · Accuracy: Muse Spark 1.3 Contributor 90.18%, MiMo V2.6 Flash 63.39% (chênh 26.79 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU valid / STEM · Accuracy: Muse Spark 1.3 Contributor 94.85%, MiMo V2.6 Flash 91.91% (chênh 2.94 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU valid / Social Science · Accuracy: Muse Spark 1.3 Contributor 90.08%, MiMo V2.6 Flash 82.44% (chênh 7.64 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.

### Note

- CI95 lower và upper nằm ở cột riêng. Khoảng cách điểm chưa phải kết quả kiểm định ghép đôi.
- Truncation: phản hồi kết thúc do length; cap do benchmark đặt. Mẫu số giữ các câu không parse được.
- Reading-400 có gold user-reviewed, trong đó có đáp án kế thừa từ output model; EM/Token-F1 là lexical metrics, cần human/semantic-judge evaluation để kết luận mức đúng về nghĩa.
- Qwen MC-56 dùng temp 0 / thinking off / seed 42; không cùng nhóm ranking với ba OpenCode Go temp hiệu lực 1 / auto / không seed. Điểm Qwen vẫn là kết quả hợp lệ của condition riêng.
- Qwen MC-72 hoàn tất 1.299 câu ở năm dataset ngoài VMLU: temp 1 / auto / không seed. Prompt hashes đã đối chiếu với từng run Go; giữ MC-56 riêng, không trộn điểm giữa hai condition.
- Muse Spark 1.3 Contributor · request complete: 2043; request expected: 2043; request errors cuối: 0; truncation tổng: 11. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- MiMo V2.6 Flash · request complete: 2043; request expected: 2043; request errors cuối: 0; truncation tổng: 34. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- MiMo V2.5 · request complete: 2043; request expected: 2043; request errors cuối: 0; truncation tổng: 32. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- Qwen3.5-9B-65K · request complete: 2043; request expected: 2043; request errors cuối: 0; truncation tổng: 0. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.

## Pilot V1 · diagnostics

So sánh theo cấu hình danh nghĩa; API và cách provider diễn giải auto vẫn khác. Nhóm suy luận/sampling khác có condition riêng.

### Condition

**Muse Spark 1.3 Contributor · MC-49**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-06T10:41:16.666385+00:00 → 2026-10-06T10:48:35.583395+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-responses · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; provider default; omitted on Responses API |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high (pilot: theo card/profile) |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model |
| History / session / sandbox | one process per item; no persisted session; stable x-opencode-session per item |
| Giới hạn output | multiple_choice: 2048 token; reading: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts resume cùng cấu hình |
| Gold / cách chấm | V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold |
| Model / quantization | zen-go/muse-spark-1.3-contributor; quantization không công bố trong metadata |

**MiMo V2.6 Flash · MC-50**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-06T10:14:08.009425+00:00 → 2026-10-06T10:40:58.189106+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-completions · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; thinking mode provider default; custom temperature ignored |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high (pilot: theo card/profile) |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model |
| History / session / sandbox | one process per item; no persisted session; stable x-opencode-session per item |
| Giới hạn output | multiple_choice: 2048 token; reading: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts resume cùng cấu hình |
| Gold / cách chấm | V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold |
| Model / quantization | zen-go/mimo-v2.6-flash; quantization không công bố trong metadata |

**MiMo V2.5 · MC-51**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-06T10:01:06.310631+00:00 → 2026-10-06T10:13:17.158169+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-completions · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; thinking mode provider default; custom temperature ignored |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high (pilot: theo card/profile) |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model |
| History / session / sandbox | one process per item; no persisted session; stable x-opencode-session per item |
| Giới hạn output | multiple_choice: 2048 token; reading: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts resume cùng cấu hình |
| Gold / cách chấm | V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold |
| Model / quantization | zen-go/mimo-v2.5; quantization không công bố trong metadata |

**Qwen3.5-9B-65K · MC-57**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-06T11:12:03.634259+00:00 → 2026-10-06T11:34:54.806623+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | IEC internal endpoint · openai-completions · llmapi.iec |
| Temperature gửi / hiệu lực | gửi 0.0; hiệu lực theo metadata 0.0; profile/model config |
| Thinking / reasoning level | off; reasoning tắt; effort không ghim mức low/medium/high |
| Seed | gửi 42 |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model |
| History / session / sandbox | one process per item; no persisted session; stable x-opencode-session per item |
| Giới hạn output | multiple_choice: 2048 token; reading: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts resume cùng cấu hình |
| Gold / cách chấm | V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold |
| Model / quantization | iec/Qwen3.5-9B-65K; quantization không công bố trong metadata |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor / MC-49 | VMLU-dev pilot | Accuracy | 100 | 90 | 90.00 | 82.56 | 94.48 | — | — | — |
| Muse Spark 1.3 Contributor / MC-49 | ViBidLQA-val pilot | EM | 80 | — | 45.00 | 33.77 | 56.25 | — | — | — |
| Muse Spark 1.3 Contributor / MC-49 | ViBidLQA-val pilot | Token-F1 | 80 | — | 77.43 | 70.76 | 83.59 | — | — | — |
| Muse Spark 1.3 Contributor / MC-49 | VMLU-dev pilot / Humanity | Accuracy | 31 | 26 | 83.87 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-49 | VMLU-dev pilot / Other | Accuracy | 14 | 13 | 92.86 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-49 | VMLU-dev pilot / STEM | Accuracy | 37 | 34 | 91.89 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-49 | VMLU-dev pilot / Social Science | Accuracy | 18 | 17 | 94.44 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-50 | VMLU-dev pilot | Accuracy | 100 | 83 | 83.00 | 74.45 | 89.11 | — | — | — |
| MiMo V2.6 Flash / MC-50 | ViBidLQA-val pilot | EM | 80 | — | 42.50 | 31.17 | 53.57 | — | — | — |
| MiMo V2.6 Flash / MC-50 | ViBidLQA-val pilot | Token-F1 | 80 | — | 75.33 | 68.32 | 81.86 | — | — | — |
| MiMo V2.6 Flash / MC-50 | VMLU-dev pilot / Humanity | Accuracy | 31 | 25 | 80.65 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-50 | VMLU-dev pilot / Other | Accuracy | 14 | 10 | 71.43 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-50 | VMLU-dev pilot / STEM | Accuracy | 37 | 32 | 86.49 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-50 | VMLU-dev pilot / Social Science | Accuracy | 18 | 16 | 88.89 | — | — | — | — | — |
| MiMo V2.5 / MC-51 | VMLU-dev pilot | Accuracy | 100 | 79 | 79.00 | 70.02 | 85.83 | — | — | — |
| MiMo V2.5 / MC-51 | ViBidLQA-val pilot | EM | 80 | — | 32.50 | 22.22 | 43.04 | — | — | — |
| MiMo V2.5 / MC-51 | ViBidLQA-val pilot | Token-F1 | 80 | — | 64.91 | 57.19 | 72.11 | — | — | — |
| MiMo V2.5 / MC-51 | VMLU-dev pilot / Humanity | Accuracy | 31 | 21 | 67.74 | — | — | — | — | — |
| MiMo V2.5 / MC-51 | VMLU-dev pilot / Other | Accuracy | 14 | 10 | 71.43 | — | — | — | — | — |
| MiMo V2.5 / MC-51 | VMLU-dev pilot / STEM | Accuracy | 37 | 33 | 89.19 | — | — | — | — | — |
| MiMo V2.5 / MC-51 | VMLU-dev pilot / Social Science | Accuracy | 18 | 15 | 83.33 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-57 | VMLU-dev pilot | Accuracy | 100 | 76 | 76.00 | 66.77 | 83.31 | — | — | — |
| Qwen3.5-9B-65K / MC-57 | ViBidLQA-val pilot | EM | 80 | — | 25.00 | 15.38 | 35.37 | — | — | — |
| Qwen3.5-9B-65K / MC-57 | ViBidLQA-val pilot | Token-F1 | 80 | — | 66.97 | 59.76 | 73.96 | — | — | — |
| Qwen3.5-9B-65K / MC-57 | VMLU-dev pilot / Humanity | Accuracy | 31 | 20 | 64.52 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-57 | VMLU-dev pilot / Other | Accuracy | 14 | 9 | 64.29 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-57 | VMLU-dev pilot / STEM | Accuracy | 37 | 33 | 89.19 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-57 | VMLU-dev pilot / Social Science | Accuracy | 18 | 14 | 77.78 | — | — | — | — | — |

### Comment

- VMLU-dev pilot · Accuracy: Muse Spark 1.3 Contributor 90.00%, MiMo V2.6 Flash 83.00% (chênh 7.00 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- ViBidLQA-val pilot · EM: Muse Spark 1.3 Contributor 45.00%, MiMo V2.6 Flash 42.50% (chênh 2.50 pp); đây là khớp gold, trong nhóm cấu hình danh nghĩa khớp.
- ViBidLQA-val pilot · Token-F1: Muse Spark 1.3 Contributor 77.43%, MiMo V2.6 Flash 75.33% (chênh 2.10 pp); đây là khớp gold, trong nhóm cấu hình danh nghĩa khớp.
- VMLU-dev pilot / Humanity · Accuracy: Muse Spark 1.3 Contributor 83.87%, MiMo V2.6 Flash 80.65% (chênh 3.22 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU-dev pilot / Other · Accuracy: Muse Spark 1.3 Contributor 92.86%, MiMo V2.6 Flash 71.43% (chênh 21.43 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU-dev pilot / STEM · Accuracy: Muse Spark 1.3 Contributor 91.89%, MiMo V2.5 89.19% (chênh 2.70 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU-dev pilot / Social Science · Accuracy: Muse Spark 1.3 Contributor 94.44%, MiMo V2.6 Flash 88.89% (chênh 5.55 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.

### Note

- CI95 lower và upper nằm ở cột riêng. Khoảng cách điểm chưa phải kết quả kiểm định ghép đôi.
- Truncation: phản hồi kết thúc do length; cap do benchmark đặt. Mẫu số giữ các câu không parse được.
- Reading-400 có gold user-reviewed, trong đó có đáp án kế thừa từ output model; EM/Token-F1 là lexical metrics, cần human/semantic-judge evaluation để kết luận mức đúng về nghĩa.
- Pilot là diagnostics, số câu nhỏ và có repeat requests riêng; các lượt lặp không thuộc mẫu số accuracy/EM. Không dùng làm leaderboard hoặc so trực tiếp với main.
- Muse Spark 1.3 Contributor · request complete: 200; request expected: 200; request errors cuối: 0; truncation tổng: 2. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- MiMo V2.6 Flash · request complete: 200; request expected: 200; request errors cuối: 0; truncation tổng: 9. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- MiMo V2.5 · request complete: 200; request expected: 200; request errors cuối: 0; truncation tổng: 4. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- Qwen3.5-9B-65K · request complete: 200; request expected: 200; request errors cuối: 0; truncation tổng: 0. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.

## VMLU V2 · Dev / Valid / Test server

So sánh theo cấu hình danh nghĩa; API và cách provider diễn giải auto vẫn khác. Nhóm suy luận/sampling khác có condition riêng.

### Condition

**Muse Spark 1.3 Contributor · MC-62**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-07T05:51:30.215886+00:00 → 2026-10-07T13:18:31.645456+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-responses · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; provider default; omitted on Responses API |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | VMLU: câu hỏi + lựa chọn; gold không gửi cho model |
| History / session / sandbox | one isolated process per item; no persisted session; stable request session ID |
| Giới hạn output | multiple_choice: 4096 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts 3 |
| Gold / cách chấm | Dev/Valid: local gold; Test: withheld, server grade do người dùng cung cấp; pilot synthetic có gold |
| Model / quantization | zen-go/muse-spark-1.3-contributor; quantization không công bố trong metadata |

**MiMo V2.6 Flash · MC-63**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-07T05:51:30.194003+00:00 → 2026-10-08T09:42:47.003397+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-completions · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; thinking mode provider default; custom temperature ignored |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | VMLU: câu hỏi + lựa chọn; gold không gửi cho model |
| History / session / sandbox | one isolated process per item; no persisted session; stable request session ID |
| Giới hạn output | multiple_choice: 4096 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts 3 |
| Gold / cách chấm | Dev/Valid: local gold; Test: withheld, server grade do người dùng cung cấp; pilot synthetic có gold |
| Model / quantization | zen-go/mimo-v2.6-flash; quantization không công bố trong metadata |

**MiMo V2.5 · MC-64**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-07T13:18:42.309245+00:00 → 2026-10-08T14:43:15.947409+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-completions · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; thinking mode provider default; custom temperature ignored |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | VMLU: câu hỏi + lựa chọn; gold không gửi cho model |
| History / session / sandbox | one isolated process per item; no persisted session; stable request session ID |
| Giới hạn output | multiple_choice: 4096 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts 3 |
| Gold / cách chấm | Dev/Valid: local gold; Test: withheld, server grade do người dùng cung cấp; pilot synthetic có gold |
| Model / quantization | zen-go/mimo-v2.5; quantization không công bố trong metadata |

**Qwen3.5-9B-65K · MC-70**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-09T05:56:56.797747+00:00 → 2026-10-09T07:38:27.837216+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | IEC internal endpoint · openai-completions · llmapi.iec |
| Temperature gửi / hiệu lực | gửi 1.0; hiệu lực theo metadata 1.0; explicit 1.0; matched to V2 Go provider effective temperature |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | VMLU: câu hỏi + lựa chọn; gold không gửi cho model |
| History / session / sandbox | one isolated process per item; no persisted session; stable request session ID |
| Giới hạn output | multiple_choice: 4096 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts 3 |
| Gold / cách chấm | Dev/Valid: local gold; Test: withheld, server grade do người dùng cung cấp; pilot synthetic có gold |
| Model / quantization | iec/Qwen3.5-9B-65K; quantization không công bố trong metadata |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor / MC-62 | VMLU Dev v2 | Accuracy | 303 | 276 | 91.09 | 87.35 | 93.80 | — | — | — |
| Muse Spark 1.3 Contributor / MC-62 | VMLU Test v2 | Server accuracy | 9833 | — | 87.04 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-62 | VMLU Valid v2 | Accuracy | 744 | 678 | 91.13 | 88.87 | 92.97 | — | — | — |
| Muse Spark 1.3 Contributor / MC-62 | VMLU Dev + Valid local-gold aggregate | Accuracy | 1047 | 954 | 91.12 | 89.24 | 92.69 | — | — | — |
| MiMo V2.6 Flash / MC-63 | VMLU Dev v2 | Accuracy | 303 | 252 | 83.17 | 78.55 | 86.96 | — | — | — |
| MiMo V2.6 Flash / MC-63 | VMLU Test v2 | Server accuracy | 9833 | — | 76.20 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-63 | VMLU Valid v2 | Accuracy | 744 | 597 | 80.24 | 77.23 | 82.94 | — | — | — |
| MiMo V2.6 Flash / MC-63 | VMLU Dev + Valid local-gold aggregate | Accuracy | 1047 | 849 | 81.09 | 78.60 | 83.35 | — | — | — |
| MiMo V2.5 / MC-64 | VMLU Dev v2 | Accuracy | 303 | 249 | 82.18 | 77.47 | 86.08 | — | — | — |
| MiMo V2.5 / MC-64 | VMLU Test v2 | Server accuracy | 9833 | — | 75.62 | — | — | — | — | — |
| MiMo V2.5 / MC-64 | VMLU Valid v2 | Accuracy | 744 | 582 | 78.23 | 75.12 | 81.04 | — | — | — |
| MiMo V2.5 / MC-64 | VMLU Dev + Valid local-gold aggregate | Accuracy | 1047 | 831 | 79.37 | 76.81 | 81.71 | — | — | — |
| Qwen3.5-9B-65K / MC-70 | VMLU Dev v2 | Accuracy | 303 | 216 | 71.29 | 65.95 | 76.09 | — | — | — |
| Qwen3.5-9B-65K / MC-70 | VMLU Test v2 | Server accuracy | 9833 | — | 63.86 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-70 | VMLU Valid v2 | Accuracy | 744 | 518 | 69.62 | 66.23 | 72.82 | — | — | — |
| Qwen3.5-9B-65K / MC-70 | VMLU Dev + Valid local-gold aggregate | Accuracy | 1047 | 734 | 70.11 | 67.26 | 72.80 | — | — | — |
| Muse Spark 1.3 Contributor / MC-62 | VMLU Test v2 server breakdown / Other | Server accuracy | — | — | 83.30 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-62 | VMLU Test v2 server breakdown / Social Science | Server accuracy | — | — | 87.42 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-62 | VMLU Test v2 server breakdown / STEM | Server accuracy | — | — | 88.98 | — | — | — | — | — |
| Muse Spark 1.3 Contributor / MC-62 | VMLU Test v2 server breakdown / Humanity | Server accuracy | — | — | 86.45 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-63 | VMLU Test v2 server breakdown / Social Science | Server accuracy | — | — | 80.21 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-63 | VMLU Test v2 server breakdown / STEM | Server accuracy | — | — | 81.22 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-63 | VMLU Test v2 server breakdown / Other | Server accuracy | — | — | 68.32 | — | — | — | — | — |
| MiMo V2.6 Flash / MC-63 | VMLU Test v2 server breakdown / Humanity | Server accuracy | — | — | 72.05 | — | — | — | — | — |
| MiMo V2.5 / MC-64 | VMLU Test v2 server breakdown / STEM | Server accuracy | — | — | 79.63 | — | — | — | — | — |
| MiMo V2.5 / MC-64 | VMLU Test v2 server breakdown / Social Science | Server accuracy | — | — | 79.02 | — | — | — | — | — |
| MiMo V2.5 / MC-64 | VMLU Test v2 server breakdown / Other | Server accuracy | — | — | 67.84 | — | — | — | — | — |
| MiMo V2.5 / MC-64 | VMLU Test v2 server breakdown / Humanity | Server accuracy | — | — | 72.94 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-70 | VMLU Test v2 server breakdown / Social Science | Server accuracy | — | — | 72.13 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-70 | VMLU Test v2 server breakdown / STEM | Server accuracy | — | — | 61.76 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-70 | VMLU Test v2 server breakdown / Other | Server accuracy | — | — | 58.97 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-70 | VMLU Test v2 server breakdown / Humanity | Server accuracy | — | — | 64.15 | — | — | — | — | — |

### Comment

- Category VMLU mô tả việc trả lời câu hỏi tiếng Việt gắn với kiến thức STEM, xã hội, nhân văn và nghiệp vụ. Ưu thế trải trên nhiều category hỗ trợ nhận định model làm tốt nhiều dạng MC trong condition này; phép đo chưa tách riêng hiểu ngôn ngữ, kiến thức nhớ được và reasoning.
- VMLU Dev v2 · Accuracy: Muse Spark 1.3 Contributor 91.09%, MiMo V2.6 Flash 83.17% (chênh 7.92 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU Test v2 · Server accuracy: Muse Spark 1.3 Contributor 87.04%, MiMo V2.6 Flash 76.20% (chênh 10.84 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU Valid v2 · Accuracy: Muse Spark 1.3 Contributor 91.13%, MiMo V2.6 Flash 80.24% (chênh 10.89 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU Dev + Valid local-gold aggregate · Accuracy: Muse Spark 1.3 Contributor 91.12%, MiMo V2.6 Flash 81.09% (chênh 10.03 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU Test v2 server breakdown / Other · Server accuracy: Muse Spark 1.3 Contributor 83.30%, MiMo V2.6 Flash 68.32% (chênh 14.98 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU Test v2 server breakdown / Social Science · Server accuracy: Muse Spark 1.3 Contributor 87.42%, MiMo V2.6 Flash 80.21% (chênh 7.21 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU Test v2 server breakdown / STEM · Server accuracy: Muse Spark 1.3 Contributor 88.98%, MiMo V2.6 Flash 81.22% (chênh 7.76 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU Test v2 server breakdown / Humanity · Server accuracy: Muse Spark 1.3 Contributor 86.45%, MiMo V2.5 72.94% (chênh 13.51 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- Profile Muse Spark 1.3 Contributor: STEM 88.98% cao nhất, Other 83.30% thấp nhất trong bốn nhóm Test. Đây là mô tả domain của run; độ khó/số câu giữa category chưa được kiểm soát như nhau.
- Profile MiMo V2.6 Flash: STEM 81.22% cao nhất, Other 68.32% thấp nhất trong bốn nhóm Test. Đây là mô tả domain của run; độ khó/số câu giữa category chưa được kiểm soát như nhau.
- Profile MiMo V2.5: STEM 79.63% cao nhất, Other 67.84% thấp nhất trong bốn nhóm Test. Đây là mô tả domain của run; độ khó/số câu giữa category chưa được kiểm soát như nhau.
- Profile Qwen3.5-9B-65K: Social Science 72.13% cao nhất, Other 58.97% thấp nhất trong bốn nhóm Test. Đây là mô tả domain của run; độ khó/số câu giữa category chưa được kiểm soát như nhau.
- MiMo V2.6 Flash so với MiMo V2.5 ở Test: Other +0.48 pp; Social Science +1.19 pp; STEM +1.59 pp; Humanity -0.89 pp. Chênh lệch nhỏ cần repeat/paired analysis trước khi kết luận khác biệt ổn định.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.

### Note

- CI95 lower và upper nằm ở cột riêng. Khoảng cách điểm chưa phải kết quả kiểm định ghép đôi.
- Truncation: phản hồi kết thúc do length; cap do benchmark đặt. Mẫu số giữ các câu không parse được.
- VMLU Test server grade do người dùng cung cấp; Test không có local gold. Không suy correct count/CI từ tỷ lệ đã làm tròn; category/subject chưa có mẫu số riêng.
- MC-70 dùng temp 1 / auto / không seed; MC-65 đã bị hủy và không được trộn vào bảng. V-Bench vẫn deferred theo yêu cầu người dùng.
- Muse Spark 1.3 Contributor · request complete: 10880; request expected: 10880; request errors cuối: 0; truncation tổng: 126. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- MiMo V2.6 Flash · request complete: 10880; request expected: 10880; request errors cuối: 0; truncation tổng: 538. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- MiMo V2.5 · request complete: 10880; request expected: 10880; request errors cuối: 0; truncation tổng: 441. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- Qwen3.5-9B-65K · Test có 1 output không parse được/blank. Đây là diagnostic của output; server grade đã được ghi riêng.
- Qwen3.5-9B-65K · request complete: 10880; request expected: 10880; request errors cuối: 0; truncation tổng: 0. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.

## Pilot V2 · VMLU + synthetic agentic

So sánh theo cấu hình danh nghĩa; API và cách provider diễn giải auto vẫn khác. Nhóm suy luận/sampling khác có condition riêng.

### Condition

**Muse Spark 1.3 Contributor · MC-58**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-07T05:32:43.416505+00:00 → 2026-10-07T05:41:39.882386+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-responses · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; provider default; omitted on Responses API |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | VMLU: câu hỏi + lựa chọn; synthetic agentic: schema; gold không gửi cho model |
| History / session / sandbox | one isolated process per item; no persisted session; stable request session ID |
| Giới hạn output | multiple_choice: 4096 token; function_call: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts 3 |
| Gold / cách chấm | Dev/Valid: local gold; Test: withheld, server grade do người dùng cung cấp; pilot synthetic có gold |
| Model / quantization | zen-go/muse-spark-1.3-contributor; quantization không công bố trong metadata |

**MiMo V2.6 Flash · MC-59**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-07T05:32:43.430519+00:00 → 2026-10-07T05:46:12.466990+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-completions · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; thinking mode provider default; custom temperature ignored |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | VMLU: câu hỏi + lựa chọn; synthetic agentic: schema; gold không gửi cho model |
| History / session / sandbox | one isolated process per item; no persisted session; stable request session ID |
| Giới hạn output | multiple_choice: 4096 token; function_call: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts 3 |
| Gold / cách chấm | Dev/Valid: local gold; Test: withheld, server grade do người dùng cung cấp; pilot synthetic có gold |
| Model / quantization | zen-go/mimo-v2.6-flash; quantization không công bố trong metadata |

**MiMo V2.5 · MC-60**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-07T05:42:11.416522+00:00 → 2026-10-07T05:50:24.541304+00:00 |
| Harness / phiên bản / mode | omp · omp/18.0.0 · mode json |
| Provider / API / route | OpenCode Go · openai-completions · opencode.ai |
| Temperature gửi / hiệu lực | gửi không gửi; hiệu lực theo metadata 1.0; thinking mode provider default; custom temperature ignored |
| Thinking / reasoning level | auto; reasoning bật; effort không ghim mức low/medium/high |
| Seed | không gửi; seed sample và seed inference là hai cấu hình riêng |
| Tools | none |
| System / user prompt | System: Answer the user's question.; user prompt đóng băng theo manifest |
| Ngữ cảnh / dữ liệu đầu vào | VMLU: câu hỏi + lựa chọn; synthetic agentic: schema; gold không gửi cho model |
| History / session / sandbox | one isolated process per item; no persisted session; stable request session ID |
| Giới hạn output | multiple_choice: 4096 token; function_call: 2048 token; cap do benchmark đặt, có thể bao gồm reasoning |
| Workers / batch | 4 worker; queue chia sẻ |
| Timeout | 300 giây/item |
| Retry / recovery | SDK 0; technical attempts 3 |
| Gold / cách chấm | Dev/Valid: local gold; Test: withheld, server grade do người dùng cung cấp; pilot synthetic có gold |
| Model / quantization | zen-go/mimo-v2.5; quantization không công bố trong metadata |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor / MC-58 | Synthetic agentic pilot | Function + arguments exact | 80 | 70 | 87.50 | 78.50 | 93.07 | — | — | — |
| Muse Spark 1.3 Contributor / MC-58 | VMLU-dev v2 pilot | Accuracy | 100 | 93 | 93.00 | 86.25 | 96.57 | — | — | — |
| MiMo V2.6 Flash / MC-59 | Synthetic agentic pilot | Function + arguments exact | 80 | 62 | 77.50 | 67.21 | 85.27 | — | — | — |
| MiMo V2.6 Flash / MC-59 | VMLU-dev v2 pilot | Accuracy | 100 | 90 | 90.00 | 82.56 | 94.48 | — | — | — |
| MiMo V2.5 / MC-60 | Synthetic agentic pilot | Function + arguments exact | 80 | 60 | 75.00 | 64.52 | 83.19 | — | — | — |
| MiMo V2.5 / MC-60 | VMLU-dev v2 pilot | Accuracy | 100 | 87 | 87.00 | 79.02 | 92.24 | — | — | — |

### Comment

- Synthetic agentic pilot · Function + arguments exact: Muse Spark 1.3 Contributor 87.50%, MiMo V2.6 Flash 77.50% (chênh 10.00 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- VMLU-dev v2 pilot · Accuracy: Muse Spark 1.3 Contributor 93.00%, MiMo V2.6 Flash 90.00% (chênh 3.00 pp); đây là điểm trên mẫu này, trong nhóm cấu hình danh nghĩa khớp.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.

### Note

- CI95 lower và upper nằm ở cột riêng. Khoảng cách điểm chưa phải kết quả kiểm định ghép đôi.
- Truncation: phản hồi kết thúc do length; cap do benchmark đặt. Mẫu số giữ các câu không parse được.
- VMLU Test server grade do người dùng cung cấp; Test không có local gold. Không suy correct count/CI từ tỷ lệ đã làm tròn; category/subject chưa có mẫu số riêng.
- MC-70 dùng temp 1 / auto / không seed; MC-65 đã bị hủy và không được trộn vào bảng. V-Bench vẫn deferred theo yêu cầu người dùng.
- Pilot là diagnostics, số câu nhỏ và có repeat requests riêng; các lượt lặp không thuộc mẫu số accuracy/EM. Không dùng làm leaderboard hoặc so trực tiếp với main.
- Muse Spark 1.3 Contributor · request complete: 200; request expected: 200; request errors cuối: 0; truncation tổng: 0. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- MiMo V2.6 Flash · request complete: 200; request expected: 200; request errors cuối: 0; truncation tổng: 1. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.
- MiMo V2.5 · request complete: 200; request expected: 200; request errors cuối: 0; truncation tổng: 1. Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.

## Muse · full OMP tools · legal-MC (MC-71)

Một model trong condition tools all + OMP system prompt + auto. Các run tools-none hoặc temp 0 không thuộc cùng bảng ranking.

### Condition

**Muse Spark 1.3 Contributor · MC-71**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | Hoàn tất 2026-10-09 14:39 (+07); 146/146 item, 0 lỗi; preregistration được ghi trước mọi dataset item |
| Harness / phiên bản / mode | OMP 18.0.0, JSON mode, --fixed-shards; label muse-spark-1-3-contributor-h2-legal-mc-full-tools-auto; isolated agent dir .omp-muse-spark-full |
| Provider / API / route | Muse Spark 1.3 Contributor · zen-go/muse-spark-1.3-contributor · OpenCode Go Responses |
| Temperature gửi / hiệu lực | không gửi; hiệu lực theo provider default 1.0 |
| Thinking / reasoning level | auto; reasoning level không ghim low/medium/high |
| Seed | không gửi |
| Tools | --tools all (bỏ cờ để dùng full default menu của OMP); giữ system prompt coding-agent mặc định; --auto-approve bật theo runner; không session/title/extensions/skills/rules/LSP |
| System / user prompt | OMP coding-agent system prompt mặc định; user prompt/parser legal-MC đóng băng |
| Ngữ cảnh / dữ liệu đầu vào | legal_mc, 146 item, manifest data/legal_slm_multichoice_manifest.json, gold cục bộ đã review; giữ prompt/parser đã đóng băng |
| History / session / sandbox | process/scratch riêng mỗi item; không history/repo instructions |
| Giới hạn output | Model maxTokens=4096; --max-time 180 giây/item |
| Workers / batch | 4 fixed shard 37/37/36/36 theo thứ tự manifest; một worker giữ một shard và xử lý tuần tự, barrier để cả 4 worker cùng bắt đầu; một tiến trình + scratch sandbox riêng/item, scratch ở /tmp, không có repo instructions |
| Timeout | 180 giây/item |
| Retry / recovery | Lỗi ghi trong ledger; 0 failure trên lượt này |
| Gold / cách chấm | Accuracy trên gold cục bộ; lượt này là score riêng của Muse qua harness, không tính delta với direct arm của model khác |
| Model / quantization | zen-go/muse-spark-1.3-contributor; quantization không công bố |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor / MC-71 | Legal MC | Accuracy | 146 | 136 | 93.15 | — | — | — | — | — |

### Comment

- Muse trả đúng 136/146 (93.15%) câu Legal MC trong full harness. Điểm phản ánh cả model và công cụ được phép; chưa có model thứ hai trong cùng condition để kết luận ưu thế model.
- 36 item có tool call, 39 calls gồm 37 web_search và 2 read (audit MC-71). Quyền có tool và việc thực sự gọi tool được ghi riêng.

### Note

- 4 shard cố định 37/37/36/36 chạy đồng thời; timeout/output cap do benchmark đặt.
- 0 failure, 0 blank, 1 network-attempt audit; chưa có repeat run hoặc paired significance test.

## Lịch sử · Qwen3.5-9B-28K · API trực tiếp

Các condition và bộ câu cũ; không xếp hạng chéo với V1/V2 hoặc model khác khi budget/thinking/gold khác.

### Condition

**Qwen3.5-9B-28K · MC-9**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-20 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | frozen build_prompt — zero-shot, no-CoT, trả lời bằng chữ cái |
| Ngữ cảnh / dữ liệu đầu vào | VMLU-MQA vmlu_mqa_v1.5/{valid,dev,all_gold}.jsonl (744 / 303 / 1.047, có gold local) |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 4 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | extract_answer (contract đóng băng), chữ cái case-insensitive; unparseable = sai nhưng giữ mẫu số |
| Model / quantization | Qwen3.5-9B-28K · 9B · quantization Q6_K |
| recorded:workers | 4 |

**Qwen3.5-9B-28K · MC-7**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-19 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | frozen build_prompt — zero-shot, no-CoT, trả lời bằng chữ cái |
| Ngữ cảnh / dữ liệu đầu vào | VMLU-MQA vmlu_mqa_v1.5/test.jsonl, n=9.833, không gold local (chấm duy nhất qua submit vmlu.ai/submit) |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 4 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | không chấm local (no gold); output full_evaluation_Qwen3_5-9B-28K.csv + submission data/submission_vmlu_test_Qwen3_5-9B-28K.csv (9.833 dòng, id khớp 1:1, unique) để upload |
| Model / quantization | Qwen3.5-9B-28K · 9B · quantization Q6_K |
| recorded:workers | 4 |

**Qwen3.5-9B-28K · MC-8**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-19 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | minimal (một điều kiện duy nhất cho slug này — cấm trộn detailed) |
| Ngữ cảnh / dữ liệu đầu vào | V-Bench public test v2026.03.28 (v_bench/public-test.jsonl), 5.141 câu chấm được (mc + agentic; safety skip) |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 512 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | server-side (vbench.ai); local chỉ valid (parser frozen + clamp) → vbench_valid_summary_*.csv mang hash; correct chỉ qua --record-server-scores |
| Model / quantization | Qwen3.5-9B-28K · 9B · quantization Q6_K |
| recorded:workers | 4 |

**Qwen3.5-9B-28K · MC-3b**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-20 (12:54–12:58 +07; khối ghi nhận bổ sung 2026-09-22) |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | open-book (build_reading_prompt) — context đưa sẵn trong prompt |
| Ngữ cảnh / dữ liệu đầu vào | eval_set_manifest.csv — 400 câu pre-registered (200 Vi-SQuAD + 200 Vi-DROP, seed 42) |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 48 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | EM + char-F1 trên gold đã hiệu đính (code_benchmark/score_reading_eval.py) |
| Model / quantization | Qwen3.5-9B-28K · 9B · quantization Q6_K |
| recorded:workers | 4 |

**Qwen3.5-9B-28K · MC-10**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-20 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | frozen build_prompt / extract_answer (byte-frozen, không sửa); chấm accuracy chữ cái |
| Ngữ cảnh / dữ liệu đầu vào | VLSP2025-LegalSLM public-test, split multichoice, n=146 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 4 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | frozen build_prompt / extract_answer (byte-frozen, không sửa); chấm accuracy chữ cái |
| Model / quantization | Qwen3.5-9B-28K · 9B · quantization Q6_K |
| recorded:workers | 4 |

**Qwen3.5-9B-28K · MC-13**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-20 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | frozen build_prompt / extract_answer (byte-frozen, không sửa); chấm accuracy chữ cái |
| Ngữ cảnh / dữ liệu đầu vào | VLSP2025-LegalSLM public-test, split nli, n=150 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 4 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | frozen build_prompt / extract_answer (byte-frozen, không sửa); chấm accuracy chữ cái |
| Model / quantization | Qwen3.5-9B-28K · 9B · quantization Q6_K |
| recorded:workers | 4 |

**Qwen3.5-9B-28K · MC-12**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-20 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | open-book (build_reading_prompt), no-CoT; EM + char-F1 trên file gold (score_reading_eval.py --gold manifest, scoring math không chạm) |
| Ngữ cảnh / dữ liệu đầu vào | ViBidLQA val (v_legal_slsp/bidlqa/ViBidLQA_val.jsonl), n=482 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 48 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | open-book (build_reading_prompt), no-CoT; EM + char-F1 trên file gold (score_reading_eval.py --gold manifest, scoring math không chạm) |
| Model / quantization | Qwen3.5-9B-28K · 9B · quantization Q6_K |
| recorded:workers | 4 |

**Qwen3.5-9B-28K · MC-11**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-20 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | open-book (build_reading_prompt), no-CoT; EM + char-F1 trên file gold (score_reading_eval.py --gold manifest, scoring math không chạm) |
| Ngữ cảnh / dữ liệu đầu vào | ViBidLQA test (v_legal_slsp/bidlqa/ViBidLQA_test.jsonl), n=603 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 48 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | open-book (build_reading_prompt), no-CoT; EM + char-F1 trên file gold (score_reading_eval.py --gold manifest, scoring math không chạm) |
| Model / quantization | Qwen3.5-9B-28K · 9B · quantization Q6_K |
| recorded:workers | 4 |

**Qwen3.5-9B-28K · MC-14b**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-21 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | frozen build_prompt / extract_answer (byte-frozen, không sửa); chấm accuracy chữ cái |
| Ngữ cảnh / dữ liệu đầu vào | VM14K public release — v_med_vm14k/data-processed-shuffled0.jsonl (HF venera-ai/VietnameseMedBench), n=12.488 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 4 token do runner đặt |
| Workers / batch | 8 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | frozen build_prompt / extract_answer (byte-frozen, không sửa); chấm accuracy chữ cái |
| Model / quantization | Qwen3.5-9B-28K · 9B · quantization Q6_K |
| recorded:workers | 8 — đo tải 2026-09-21 (probe cùng lúc với run cũ): 1 request 0,26 req/s · 4 song song 0,72 req/s · 8 song song 1,55 req/s; các điều kiện khác giữ nguyên MC-14 |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-9 | vmlu-mqa-all-gold | Accuracy | 1047 | 768 | 73.35 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-9 | vmlu-mqa-all-gold / STEM | Accuracy | 383 | 304 | 79.37 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-9 | vmlu-mqa-all-gold / Social Science | Accuracy | 184 | 144 | 78.26 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-9 | vmlu-mqa-all-gold / Humanity | Accuracy | 324 | 222 | 68.52 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-9 | vmlu-mqa-all-gold / Other | Accuracy | 156 | 98 | 62.82 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-7 | VMLU Test cũ | Server accuracy | 9833 | — | 67.87 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-7 | VMLU Test cũ / STEM | Server accuracy | — | — | 65.65 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-7 | VMLU Test cũ / Social Science | Server accuracy | — | — | 74.97 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-7 | VMLU Test cũ / Humanity | Server accuracy | — | — | 68.61 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-7 | VMLU Test cũ / Other | Server accuracy | — | — | 63.67 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench · micro | Server accuracy | 5141 | 2345 | 45.61 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench · macro | Server macro (domain mean) | — | — | 45.22 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / function calling / agentic | Server accuracy | 1000 | 397 | 39.70 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / chemistry | Server accuracy | 334 | 130 | 38.92 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / computer_science | Server accuracy | 188 | 134 | 71.28 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / culture | Server accuracy | 217 | 104 | 47.93 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / dialect | Server accuracy | 562 | 338 | 60.14 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / laws | Server accuracy | 191 | 120 | 62.83 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / literature | Server accuracy | 601 | 247 | 41.10 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / logics | Server accuracy | 225 | 56 | 24.89 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / mathematics | Server accuracy | 125 | 25 | 20.00 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / medicine | Server accuracy | 490 | 189 | 38.57 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / philosophy | Server accuracy | 263 | 170 | 64.64 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / physics | Server accuracy | 147 | 42 | 28.57 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-8 | V-Bench domain / multiple-choice / psychology | Server accuracy | 798 | 393 | 49.25 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-3b | reading-400 / squad | EM | 200 | — | 96.50 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-3b | reading-400 / squad | Char-F1 | 200 | — | 98.63 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-3b | reading-400 / drop | EM | 200 | — | 63.00 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-3b | reading-400 / drop | Char-F1 | 200 | — | 74.35 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-3b | reading-400 | EM | 400 | — | 79.75 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-3b | reading-400 | Char-F1 | 400 | — | 86.49 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-10 | legal-mc-146 | Accuracy | 146 | 128 | 87.67 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-10 | legal-mc-146 / unknown | Accuracy | 146 | 128 | 87.67 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-13 | legal-nli-150 | Accuracy | 150 | 135 | 90.00 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-13 | legal-nli-150 / unknown | Accuracy | 150 | 135 | 90.00 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-12 | bidlqa-val | EM | 482 | — | 32.78 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-12 | bidlqa-val | Char-F1 | 482 | — | 74.16 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-11 | bidlqa-test | EM | 603 | — | 33.17 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-11 | bidlqa-test | Char-F1 | 603 | — | 73.21 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-14b | vm14k-public-12488 | Accuracy | 12488 | 8091 | 64.79 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-14b | vm14k-public-12488 / unknown | Accuracy | 12488 | 8091 | 64.79 | — | — | — | — | — |

### Comment

- Trong Qwen3.5-9B-28K / vm14k-public-12488, unknown đạt 64.79%, unknown đạt 64.79%. Đây là mô tả category của cùng run; bộ câu và kích thước category khác nhau.
- Trong Qwen3.5-9B-28K / legal-nli-150, unknown đạt 90.00%, unknown đạt 90.00%. Đây là mô tả category của cùng run; bộ câu và kích thước category khác nhau.
- Trong Qwen3.5-9B-28K / legal-mc-146, unknown đạt 87.67%, unknown đạt 87.67%. Đây là mô tả category của cùng run; bộ câu và kích thước category khác nhau.
- Trong Qwen3.5-9B-28K / vmlu-mqa-all-gold, STEM đạt 79.37%, Other đạt 62.82%. Đây là mô tả category của cùng run; bộ câu và kích thước category khác nhau.
- Đây là kết quả của condition riêng. Dữ liệu hiện có chưa tạo thành bảng xếp hạng các model dưới cùng cấu hình đầy đủ.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.

### Note

- Metadata thiếu được hiển thị rõ; ngày và condition lấy theo từng card, không lấy model_info chung của snapshot cũ.
- V-Bench MC-8 submission gồm 14 agentic rows gọi lại bằng guided prompt. Grade này có treatment khác ở 14 rows; không gộp thành baseline minimal đồng nhất.
- V-Bench macro là trung bình domain; micro là tỷ lệ đúng theo item. Cột Correct/n thuộc micro/domain, không phải numerator của macro.
- Reading-400: gold có đáp án kế thừa từ model được người duyệt chấp nhận; các lexical score cần đọc cùng thiên lệch reference. ViBidLQA dùng file-gold upstream, chưa review lại tại repo.

## Lịch sử · Qwen3_8-27B-Q4_K_M_gguf · API trực tiếp

Các condition và bộ câu cũ; không xếp hạng chéo với V1/V2 hoặc model khác khi budget/thinking/gold khác.

### Condition

**Qwen3_8-27B-Q4_K_M_gguf · MC-1**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-08-31 (báo cáo 2026-09-03) |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 (OpenAI-compatible) |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | User prompt không yêu cầu CoT; native thinking/effort chưa ghi nhận |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | build_prompt — zero-shot, no-CoT, trả lời bằng chữ cái |
| Ngữ cảnh / dữ liệu đầu vào | VMLU-MQA, vmlu_mqa_v1.5/all_gold.jsonl (dev 303 + valid 744 = 1.047) |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 4 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | extract_answer (contract đóng băng), so khớp chữ cái, case-insensitive |
| Model / quantization | Qwen3_8-27B-Q4_K_M_gguf · 27B · quantization Q4_K_M |
| recorded:workers | 4 |

**Qwen3_8-27B-Q4_K_M_gguf · MC-2**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-04 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | User prompt không yêu cầu CoT; native thinking/effort chưa ghi nhận |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | minimal ("điều kiện trung thực": chỉ câu hỏi + schema của chính dòng đó + một dòng format) |
| Ngữ cảnh / dữ liệu đầu vào | V-Bench public test v2026.03.28, 5.141 câu chấm được |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 512 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | server-side (vbench.ai), macro trung bình 13 domain |
| Model / quantization | Qwen3_8-27B-Q4_K_M_gguf · 27B · quantization Q4_K_M |
| recorded:workers | 4 |

**Qwen3_8-27B-Q4_K_M_gguf · MC-3**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09 (ngày chấm lại: 2026-09-12) |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | User prompt không yêu cầu CoT; native thinking/effort chưa ghi nhận |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | open-book (build_reading_prompt) — context đưa sẵn trong prompt |
| Ngữ cảnh / dữ liệu đầu vào | eval_set_manifest.csv — 400 câu pre-registered (200 Vi-SQuAD + 200 Vi-DROP, seed 42) |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 48 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | EM + char-F1 trên review_gold_agreed.csv (code_benchmark/score_reading_eval.py) |
| Model / quantization | Qwen3_8-27B-Q4_K_M_gguf · 27B · quantization Q4_K_M |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3_8-27B-Q4_K_M_gguf / MC-1 | vmlu-mqa-all-gold | Accuracy | 1047 | 768 | 73.35 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-1 | vmlu-mqa-all-gold / STEM | Accuracy | 383 | 304 | 79.37 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-1 | vmlu-mqa-all-gold / Social Science | Accuracy | 184 | 144 | 78.26 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-1 | vmlu-mqa-all-gold / Humanity | Accuracy | 324 | 221 | 68.21 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-1 | vmlu-mqa-all-gold / Other | Accuracy | 156 | 99 | 63.46 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench · micro | Server accuracy | 5141 | 2337 | 45.46 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench · macro | Server macro (domain mean) | — | — | 44.97 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / computer_science | Server accuracy | 188 | 132 | 70.21 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / philosophy | Server accuracy | 263 | 170 | 64.64 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / laws | Server accuracy | 191 | 116 | 60.73 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / dialect | Server accuracy | 562 | 337 | 59.96 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / psychology | Server accuracy | 798 | 397 | 49.75 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / culture | Server accuracy | 217 | 103 | 47.47 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / literature | Server accuracy | 601 | 245 | 40.77 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / chemistry | Server accuracy | 334 | 134 | 40.12 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / function-calling / agentic | Server accuracy | 1000 | 391 | 39.10 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / medicine | Server accuracy | 490 | 190 | 38.78 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / physics | Server accuracy | 147 | 44 | 29.93 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / logics | Server accuracy | 225 | 54 | 24.00 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-2 | V-Bench domain / multiple-choice / mathematics | Server accuracy | 125 | 24 | 19.20 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-3 | reading-400 / squad | EM | 200 | — | 97.50 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-3 | reading-400 / squad | Char-F1 | 200 | — | 98.61 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-3 | reading-400 / drop | EM | 200 | — | 63.00 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-3 | reading-400 / drop | Char-F1 | 200 | — | 74.49 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-3 | reading-400 | EM | 400 | — | 80.25 | — | — | — | — | — |
| Qwen3_8-27B-Q4_K_M_gguf / MC-3 | reading-400 | Char-F1 | 400 | — | 86.55 | — | — | — | — | — |

### Comment

- Trong Qwen3_8-27B-Q4_K_M_gguf / vmlu-mqa-all-gold, STEM đạt 79.37%, Other đạt 63.46%. Đây là mô tả category của cùng run; bộ câu và kích thước category khác nhau.
- Đây là kết quả của condition riêng. Dữ liệu hiện có chưa tạo thành bảng xếp hạng các model dưới cùng cấu hình đầy đủ.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.

### Note

- Metadata thiếu được hiển thị rõ; ngày và condition lấy theo từng card, không lấy model_info chung của snapshot cũ.
- MC-2 V-Bench lấy từ snapshot công bố và card MC-2; không gán model_info chung cho các block khác. Macro và micro giữ metric riêng.
- Reading-400: gold có đáp án kế thừa từ model được người duyệt chấp nhận; các lexical score cần đọc cùng thiên lệch reference. ViBidLQA dùng file-gold upstream, chưa review lại tại repo.

## Lịch sử · qwen38-nothink · API trực tiếp

Các condition và bộ câu cũ; không xếp hạng chéo với V1/V2 hoặc model khác khi budget/thinking/gold khác.

### Condition

**qwen38-nothink · MC-6**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-19 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | qwen38-nothink (FROM qwen3.8:27b-q4_K_M, PARAMETER think false) qua https://porridge-livable-umbrella.ngrok-free.dev/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | Ollama Modelfile think false theo registry/MC-6; user prompt no-CoT |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | frozen build_prompt / extract_answer (byte-frozen, không sửa); chấm accuracy chữ cái |
| Ngữ cảnh / dữ liệu đầu vào | VLSP2025-LegalSLM public-test, split multichoice, n=146 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 512 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | frozen build_prompt / extract_answer (byte-frozen, không sửa); chấm accuracy chữ cái |
| Model / quantization | qwen38-nothink · 27B · quantization Q4_K_M |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| qwen38-nothink / MC-6 | legal-mc-146 | Accuracy | 146 | 121 | 82.88 | — | — | — | — | — |
| qwen38-nothink / MC-6 | legal-mc-146 / unknown | Accuracy | 146 | 121 | 82.88 | — | — | — | — | — |

### Comment

- Trong qwen38-nothink / legal-mc-146, unknown đạt 82.88%, unknown đạt 82.88%. Đây là mô tả category của cùng run; bộ câu và kích thước category khác nhau.
- Đây là kết quả của condition riêng. Dữ liệu hiện có chưa tạo thành bảng xếp hạng các model dưới cùng cấu hình đầy đủ.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.

### Note

- Metadata thiếu được hiển thị rõ; ngày và condition lấy theo từng card, không lấy model_info chung của snapshot cũ.

## Lịch sử · Qwen3.5-9B-65K · API trực tiếp

Các condition và bộ câu cũ; không xếp hạng chéo với V1/V2 hoặc model khác khi budget/thinking/gold khác.

### Condition

**Qwen3.5-9B-65K · MC-31**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | Pre-register 2026-09-30 (card ghi xong trước mọi lần chạy); arm A 09:47–10:34 (+07); arm B bắt đầu 10:55, vbench_agentic + vbench_mc chạy nền có --resume |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | Qwen3.5-9B-65K @ https://llmapi.iec-uit.com/v1 — model DUY NHẤT còn chạy (node 28K offline: HTTP 503 Compute Node 'RTX3060-8GB' is offline) |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | Chưa ghi nhận trong artifact/card |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | Chưa ghi nhận trong artifact/card |
| Ngữ cảnh / dữ liệu đầu vào | legal_mc 146 · legal_nli 150 · reading400 400 · bidlqa_val 482 · vbench_agentic 1.000 · vbench_mc 4.141 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 4 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Không đổi: MC exact-letter, reading EM/char-F1, vbench_agentic = schema validity, vbench_mc = mức trùng khớp với arm A (không có gold cục bộ) |
| Model / quantization | Qwen3.5-9B-65K · 9B · quantization không công bố |
| recorded:dieu_kien | Arm A: gọi thẳng, prompt byte-frozen như mọi card, temperature 0, seed 42. Arm B: omp sạch — --tools all (bỏ hẳn cờ --tools, menu default của omp), system prompt trung tính, HOME=/tmp/fakehome, sandbox /tmp, temperature=0 ghim bằng proxy (MC-29); không tool-schema nào bị sửa tay. |
| recorded:workers | 4 (trần 6) — vì tổng thông lượng prefill không tăng theo số luồng (xem khối server); chạy từng tập + --resume |

**Qwen3.5-9B-65K · MC-31**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | Pre-register 2026-09-30 (card ghi xong trước mọi lần chạy); arm A 09:47–10:34 (+07); arm B bắt đầu 10:55, vbench_agentic + vbench_mc chạy nền có --resume |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | Qwen3.5-9B-65K @ https://llmapi.iec-uit.com/v1 — model DUY NHẤT còn chạy (node 28K offline: HTTP 503 Compute Node 'RTX3060-8GB' is offline) |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | Chưa ghi nhận trong artifact/card |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | Chưa ghi nhận trong artifact/card |
| Ngữ cảnh / dữ liệu đầu vào | legal_mc 146 · legal_nli 150 · reading400 400 · bidlqa_val 482 · vbench_agentic 1.000 · vbench_mc 4.141 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 4 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Không đổi: MC exact-letter, reading EM/char-F1, vbench_agentic = schema validity, vbench_mc = mức trùng khớp với arm A (không có gold cục bộ) |
| Model / quantization | Qwen3.5-9B-65K · 9B · quantization không công bố |
| recorded:dieu_kien | Arm A: gọi thẳng, prompt byte-frozen như mọi card, temperature 0, seed 42. Arm B: omp sạch — --tools all (bỏ hẳn cờ --tools, menu default của omp), system prompt trung tính, HOME=/tmp/fakehome, sandbox /tmp, temperature=0 ghim bằng proxy (MC-29); không tool-schema nào bị sửa tay. |
| recorded:workers | 4 (trần 6) — vì tổng thông lượng prefill không tăng theo số luồng (xem khối server); chạy từng tập + --resume |

**Qwen3.5-9B-65K · MC-31**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | Pre-register 2026-09-30 (card ghi xong trước mọi lần chạy); arm A 09:47–10:34 (+07); arm B bắt đầu 10:55, vbench_agentic + vbench_mc chạy nền có --resume |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | Qwen3.5-9B-65K @ https://llmapi.iec-uit.com/v1 — model DUY NHẤT còn chạy (node 28K offline: HTTP 503 Compute Node 'RTX3060-8GB' is offline) |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | Chưa ghi nhận trong artifact/card |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | Chưa ghi nhận trong artifact/card |
| Ngữ cảnh / dữ liệu đầu vào | legal_mc 146 · legal_nli 150 · reading400 400 · bidlqa_val 482 · vbench_agentic 1.000 · vbench_mc 4.141 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 48 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Không đổi: MC exact-letter, reading EM/char-F1, vbench_agentic = schema validity, vbench_mc = mức trùng khớp với arm A (không có gold cục bộ) |
| Model / quantization | Qwen3.5-9B-65K · 9B · quantization không công bố |
| recorded:dieu_kien | Arm A: gọi thẳng, prompt byte-frozen như mọi card, temperature 0, seed 42. Arm B: omp sạch — --tools all (bỏ hẳn cờ --tools, menu default của omp), system prompt trung tính, HOME=/tmp/fakehome, sandbox /tmp, temperature=0 ghim bằng proxy (MC-29); không tool-schema nào bị sửa tay. |
| recorded:workers | 4 (trần 6) — vì tổng thông lượng prefill không tăng theo số luồng (xem khối server); chạy từng tập + --resume |

**Qwen3.5-9B-65K · MC-31**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | Pre-register 2026-09-30 (card ghi xong trước mọi lần chạy); arm A 09:47–10:34 (+07); arm B bắt đầu 10:55, vbench_agentic + vbench_mc chạy nền có --resume |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | Qwen3.5-9B-65K @ https://llmapi.iec-uit.com/v1 — model DUY NHẤT còn chạy (node 28K offline: HTTP 503 Compute Node 'RTX3060-8GB' is offline) |
| Temperature gửi / hiệu lực | 0.0 gửi theo runner; không khẳng định endpoint deterministic |
| Thinking / reasoning level | Chưa ghi nhận trong artifact/card |
| Seed | 42 theo runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | Chưa ghi nhận trong artifact/card |
| Ngữ cảnh / dữ liệu đầu vào | legal_mc 146 · legal_nli 150 · reading400 400 · bidlqa_val 482 · vbench_agentic 1.000 · vbench_mc 4.141 |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | 48 token do runner đặt |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Không đổi: MC exact-letter, reading EM/char-F1, vbench_agentic = schema validity, vbench_mc = mức trùng khớp với arm A (không có gold cục bộ) |
| Model / quantization | Qwen3.5-9B-65K · 9B · quantization không công bố |
| recorded:dieu_kien | Arm A: gọi thẳng, prompt byte-frozen như mọi card, temperature 0, seed 42. Arm B: omp sạch — --tools all (bỏ hẳn cờ --tools, menu default của omp), system prompt trung tính, HOME=/tmp/fakehome, sandbox /tmp, temperature=0 ghim bằng proxy (MC-29); không tool-schema nào bị sửa tay. |
| recorded:workers | 4 (trần 6) — vì tổng thông lượng prefill không tăng theo số luồng (xem khối server); chạy từng tập + --resume |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-65K / MC-31 | legal-mc-146 | Accuracy | 146 | 130 | 89.04 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | legal-nli-150 | Accuracy | 150 | 138 | 92.00 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | reading-400 / squad | EM | 200 | — | 87.00 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | reading-400 / squad | Char-F1 | 200 | — | 96.15 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | reading-400 / drop | EM | 200 | — | 57.50 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | reading-400 / drop | Char-F1 | 200 | — | 70.75 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | reading-400 | EM | 400 | — | 72.25 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | reading-400 | Char-F1 | 400 | — | 83.45 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | bidlqa-val | EM | 482 | — | 29.25 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | bidlqa-val | Char-F1 | 482 | — | 73.49 | — | — | — | — | — |

### Comment

- Đây là kết quả của condition riêng. Dữ liệu hiện có chưa tạo thành bảng xếp hạng các model dưới cùng cấu hình đầy đủ.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.

### Note

- Metadata thiếu được hiển thị rõ; ngày và condition lấy theo từng card, không lấy model_info chung của snapshot cũ.
- Reading-400: gold có đáp án kế thừa từ model được người duyệt chấp nhận; các lexical score cần đọc cùng thiên lệch reference. ViBidLQA dùng file-gold upstream, chưa review lại tại repo.

## Qwen3.5-9B-28K · A · Gọi API trực tiếp (không harness)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-10, MC-12, MC-13, MC-3b, MC-8**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-20 |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 gửi theo card/runner; hiệu lực tùy API |
| Thinking / reasoning level | non-thinking backend theo MC-4; no-CoT trong user prompt |
| Seed | 42 gửi theo card/runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | Gọi API trực tiếp (không harness); build_prompt / build_reading_prompt / V-Bench minimal theo từng dataset |
| Ngữ cảnh / dữ liệu đầu vào | MC closed-book; reading có context trong prompt; V-Bench có schema ở từng item |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | MC: 4 token; reading: 48 token; V-Bench theo card riêng, không tự suy cap cho mọi track |
| Workers / batch | 4 |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | frozen build_prompt / extract_answer (byte-frozen, không sửa); chấm accuracy chữ cái |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |
| recorded:workers | 4 |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-10, MC-12, MC-13, MC-3b, MC-8 | reading-400 (EM) | EM | 400 | — | 79.75 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-10, MC-12, MC-13, MC-3b, MC-8 | reading-400 (EM) | Char-F1 | 400 | — | 86.49 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-10, MC-12, MC-13, MC-3b, MC-8 | legal-MC (accuracy) | Accuracy | 146 | — | 87.67 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-10, MC-12, MC-13, MC-3b, MC-8 | legal-NLI (accuracy) | Accuracy | 150 | — | 90.00 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-10, MC-12, MC-13, MC-3b, MC-8 | ViBidLQA val (EM) | EM | 482 | — | 32.78 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-10, MC-12, MC-13, MC-3b, MC-8 | ViBidLQA val (EM) | Char-F1 | 482 | — | 74.16 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-10, MC-12, MC-13, MC-3b, MC-8 | V-Bench agentic — schema validity, không có gold cục bộ | Schema validity | 1000 | — | 100.00 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-10, MC-12, MC-13, MC-3b, MC-8 | V-Bench agentic — schema validity, không có gold cục bộ | Server accuracy | 1000 | 397 | 39.70 | — | — | — | — | — |

### Comment

- Đây là kết quả của condition riêng. Dữ liệu hiện có chưa tạo thành bảng xếp hạng các model dưới cùng cấu hình đầy đủ.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.
- EM thay đổi ở arm harness còn chịu ảnh hưởng độ dài/cách trình bày câu trả lời và output budget. Không suy trực tiếp rằng hiểu nội dung giảm/tăng chỉ từ mức khớp chuỗi này.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-28K · H2 · omp: tool đầy đủ + system prompt của omp (có rò style)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-15, MC-16, MC-17**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-26 |
| Harness / phiên bản / mode | omp v18.2.7 · -p --mode json · PI_CODING_AGENT_DIR=.omp-iec (config + provider cô lập, mọi modelRoles ghim về 1 model) |
| Provider / API / route | https://llmapi.iec-uit.com/v1 |
| Temperature gửi / hiệu lực | 0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29) |
| Thinking / reasoning level | --thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | read,bash,edit,write,grep,glob; không tự suy là có search |
| System / user prompt | omp: tool đầy đủ + system prompt của omp (có rò style) |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | 6 |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | scorer đóng băng, không viết lại: score_reading_eval.py (EM + char-F1) trên projection ANSWER_COLS; MC không có, parser extract_answer nguyên vẹn |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | arm B của phép so sánh harness: cùng model/prompt/parser như MC-3b, chỉ thay đường elicitation — chạy trong agent omp (Oh My Pi). Mục đích: đo harness effect (delta do scaffold, không do model) |
| recorded:prompt | byte-identical MC-3b (build_reading_prompt); cô lập: mỗi item 1 thư mục tạm rỗng chỉ có item.json (không gold), --cwd vào đó, không --add-dir |
| recorded:system_prompt | mặc định của omp (coding-agent) — đo được ~11,5k token/lượt |
| recorded:max_time | 180s/item (--max-time); max_tokens + context do omp quản lý (context 32768) |
| recorded:workers | 6 |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-15, MC-16, MC-17 | reading-400 (EM) | EM | 400 | — | 27.00 | — | — | -52.75 | -57.75 | -48.00 |
| Qwen3.5-9B-28K / MC-15, MC-16, MC-17 | reading-400 (EM) | Char-F1 | 400 | — | 43.14 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-15, MC-16, MC-17 | legal-MC (accuracy) | Accuracy | 146 | — | 50.00 | — | — | -37.67 | -46.58 | -28.77 |
| Qwen3.5-9B-28K / MC-15, MC-16, MC-17 | legal-NLI (accuracy) | Accuracy | 150 | — | 60.67 | — | — | -29.33 | -37.33 | -22.00 |
| Qwen3.5-9B-28K / MC-15, MC-16, MC-17 | ViBidLQA val (EM) | EM | 482 | — | 6.02 | — | — | -26.76 | -30.91 | -22.61 |
| Qwen3.5-9B-28K / MC-15, MC-16, MC-17 | ViBidLQA val (EM) | Char-F1 | 482 | — | 36.74 | — | — | — | — | — |

### Comment

- reading-400 (EM): 27.00% ở arm H2, 79.75% ở arm A cùng model; Δ -52.75 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- legal-MC (accuracy): 50.00% ở arm H2, 87.67% ở arm A cùng model; Δ -37.67 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- legal-NLI (accuracy): 60.67% ở arm H2, 90.00% ở arm A cùng model; Δ -29.33 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- ViBidLQA val (EM): 6.02% ở arm H2, 32.78% ở arm A cùng model; Δ -26.76 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- EM thay đổi ở arm harness còn chịu ảnh hưởng độ dài/cách trình bày câu trả lời và output budget. Không suy trực tiếp rằng hiểu nội dung giảm/tăng chỉ từ mức khớp chuỗi này.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.
- MC-22 phát hiện APPEND_SYSTEM.md lọt vào các run này. Kết quả đo cả cấu hình máy; không quy nguyên nhân chỉ cho OMP.

## Qwen3.5-9B-28K · H1 · omp: không tool + system prompt của omp (có rò style)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-20**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-26 |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29) |
| Thinking / reasoning level | --thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | none |
| System / user prompt | omp: không tool + system prompt của omp (có rò style) |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | 6 (chạy) · 4 (cost probe) |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | MC-16 không tool: cùng model / endpoint / prompt byte-identical / scorer, chạy omp với --no-tools (thay vì tool menu read,bash,edit,write,grep,glob), --limit 100 (tiền tố 100 item của legal-MC, trùng đúng tập H2 đã chạy) |
| recorded:workers | 6 (chạy) · 4 (cost probe) |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-20 | legal-MC (accuracy) | Accuracy | 100 | — | 64.00 | — | — | -22.00 | -32.00 | -12.00 |

### Comment

- legal-MC (accuracy): 64.00% ở arm H1, 86.00% ở arm A cùng model; Δ -22.00 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.
- MC-22 phát hiện APPEND_SYSTEM.md lọt vào các run này. Kết quả đo cả cấu hình máy; không quy nguyên nhân chỉ cho OMP.

## Qwen3.5-9B-28K · H3 · omp: tool đầy đủ + system prompt trung tính (có rò style)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-21**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-26 |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29) |
| Thinking / reasoning level | --thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | read,bash,edit,write,grep,glob; không tự suy là có search |
| System / user prompt | omp: tool đầy đủ + system prompt trung tính (có rò style) |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | 6 (chạy) · 4 (cost probe) |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Bốn arm qua omp, cùng 100 item legal-MC đầu, cùng model/endpoint/prompt byte-identical/scorer; chỉ khác 2 nhịp: system_prompt ∈ {mặc định của omp, dòng trung tính Answer the user's question.} × tools ∈ {menu đầy đủ, --no-tools}. Slug: ompH1_ (persona×no-tools) · ompH2_ (persona×tools) · ompH3_ (min-sys×tools) · ompH4_ (min-sys×no-tools) |
| recorded:workers | 6 (chạy) · 4 (cost probe) |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-21 | legal-MC (accuracy) | Accuracy | 100 | — | 65.00 | — | — | -21.00 | -30.00 | -13.00 |

### Comment

- legal-MC (accuracy): 65.00% ở arm H3, 86.00% ở arm A cùng model; Δ -21.00 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.
- MC-22 phát hiện APPEND_SYSTEM.md lọt vào các run này. Kết quả đo cả cấu hình máy; không quy nguyên nhân chỉ cho OMP.

## Qwen3.5-9B-28K · H4 · omp: không tool + system prompt trung tính (có rò style)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-21**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-26 |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29) |
| Thinking / reasoning level | --thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | none |
| System / user prompt | omp: không tool + system prompt trung tính (có rò style) |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | 6 (chạy) · 4 (cost probe) |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Bốn arm qua omp, cùng 100 item legal-MC đầu, cùng model/endpoint/prompt byte-identical/scorer; chỉ khác 2 nhịp: system_prompt ∈ {mặc định của omp, dòng trung tính Answer the user's question.} × tools ∈ {menu đầy đủ, --no-tools}. Slug: ompH1_ (persona×no-tools) · ompH2_ (persona×tools) · ompH3_ (min-sys×tools) · ompH4_ (min-sys×no-tools) |
| recorded:workers | 6 (chạy) · 4 (cost probe) |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-21 | legal-MC (accuracy) | Accuracy | 100 | — | 63.00 | — | — | -23.00 | -35.00 | -12.00 |

### Comment

- legal-MC (accuracy): 63.00% ở arm H4, 86.00% ở arm A cùng model; Δ -23.00 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.
- MC-22 phát hiện APPEND_SYSTEM.md lọt vào các run này. Kết quả đo cả cấu hình máy; không quy nguyên nhân chỉ cho OMP.

## Qwen3.5-9B-28K · H5 · omp sạch: không tool + system prompt trung tính, HOME override

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-22**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-26 (sau MC-15…MC-21, cùng ngày) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29) |
| Thinking / reasoning level | --thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | none |
| System / user prompt | omp sạch: không tool + system prompt trung tính, HOME override |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-22 | reading-400 (EM) | EM | 400 | — | 57.50 | — | — | -22.25 | -26.75 | -17.75 |
| Qwen3.5-9B-28K / MC-22 | reading-400 (EM) | Char-F1 | 400 | — | 74.92 | — | — | — | — | — |
| Qwen3.5-9B-28K / MC-22 | legal-MC (accuracy) | Accuracy | 146 | — | 69.18 | — | — | -18.49 | -26.71 | -10.96 |
| Qwen3.5-9B-28K / MC-22 | legal-NLI (accuracy) | Accuracy | 150 | — | 78.67 | — | — | -11.33 | -18.67 | -4.00 |
| Qwen3.5-9B-28K / MC-22 | ViBidLQA val (EM) | EM | 482 | — | 27.18 | — | — | -5.60 | -9.34 | -2.07 |
| Qwen3.5-9B-28K / MC-22 | ViBidLQA val (EM) | Char-F1 | 482 | — | 68.43 | — | — | — | — | — |

### Comment

- reading-400 (EM): 57.50% ở arm H5, 79.75% ở arm A cùng model; Δ -22.25 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- legal-MC (accuracy): 69.18% ở arm H5, 87.67% ở arm A cùng model; Δ -18.49 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- legal-NLI (accuracy): 78.67% ở arm H5, 90.00% ở arm A cùng model; Δ -11.33 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- ViBidLQA val (EM): 27.18% ở arm H5, 32.78% ở arm A cùng model; Δ -5.60 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- EM thay đổi ở arm harness còn chịu ảnh hưởng độ dài/cách trình bày câu trả lời và output budget. Không suy trực tiếp rằng hiểu nội dung giảm/tăng chỉ từ mức khớp chuỗi này.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-28K · H6 · omp sạch + tool menu đầy đủ

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-23**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-26 (sau MC-22) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29) |
| Thinking / reasoning level | --thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | read,bash,edit,write,grep,glob; không tự suy là có search |
| System / user prompt | omp sạch + tool menu đầy đủ |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | 6 (chạy) · 4 (cost probe) |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Bốn arm qua omp, cùng 100 item legal-MC, cùng model/endpoint/prompt byte-identical/scorer, HOME override nên không dính APPEND_SYSTEM.md, PI_CODING_AGENT_DIR=.omp-clean/, --tools none hoặc menu đầy đủ, system prompt của omp hoặc dòng trung tính. Slug: ompH5clean_ (trung tính×no-tool) · ompH6clean_ (trung tính×tools) · ompH7clean_ (omp-sys×no-tool) · ompH8clean_ (omp-sys×tools) |
| recorded:workers | 6 (chạy) · 4 (cost probe) |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-23 | legal-MC (accuracy) | Accuracy | 100 | — | 69.00 | — | — | -17.00 | -26.00 | -8.00 |

### Comment

- legal-MC (accuracy): 69.00% ở arm H6, 86.00% ở arm A cùng model; Δ -17.00 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-28K · H7 · omp sạch + system prompt của omp, không tool

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-23**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-26 (sau MC-22) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29) |
| Thinking / reasoning level | --thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | none |
| System / user prompt | omp sạch + system prompt của omp, không tool |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | 6 (chạy) · 4 (cost probe) |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Bốn arm qua omp, cùng 100 item legal-MC, cùng model/endpoint/prompt byte-identical/scorer, HOME override nên không dính APPEND_SYSTEM.md, PI_CODING_AGENT_DIR=.omp-clean/, --tools none hoặc menu đầy đủ, system prompt của omp hoặc dòng trung tính. Slug: ompH5clean_ (trung tính×no-tool) · ompH6clean_ (trung tính×tools) · ompH7clean_ (omp-sys×no-tool) · ompH8clean_ (omp-sys×tools) |
| recorded:workers | 6 (chạy) · 4 (cost probe) |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-23 | legal-MC (accuracy) | Accuracy | 100 | — | 68.00 | — | — | -18.00 | -27.00 | -10.00 |

### Comment

- legal-MC (accuracy): 68.00% ở arm H7, 86.00% ở arm A cùng model; Δ -18.00 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-28K · H8 · omp sạch + tool menu + system prompt của omp

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-23**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-26 (sau MC-22) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29) |
| Thinking / reasoning level | --thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | read,bash,edit,write,grep,glob; không tự suy là có search |
| System / user prompt | omp sạch + tool menu + system prompt của omp |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | 6 (chạy) · 4 (cost probe) |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Bốn arm qua omp, cùng 100 item legal-MC, cùng model/endpoint/prompt byte-identical/scorer, HOME override nên không dính APPEND_SYSTEM.md, PI_CODING_AGENT_DIR=.omp-clean/, --tools none hoặc menu đầy đủ, system prompt của omp hoặc dòng trung tính. Slug: ompH5clean_ (trung tính×no-tool) · ompH6clean_ (trung tính×tools) · ompH7clean_ (omp-sys×no-tool) · ompH8clean_ (omp-sys×tools) |
| recorded:workers | 6 (chạy) · 4 (cost probe) |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-23 | legal-MC (accuracy) | Accuracy | 100 | — | 75.00 | — | — | -11.00 | -20.00 | -3.00 |

### Comment

- legal-MC (accuracy): 75.00% ở arm H8, 86.00% ở arm A cùng model; Δ -11.00 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-28K · V1 · omp sạch + tool menu đầy đủ, trên V-Bench function-calling (nơi scaffold *có thể* thắng)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-28K · MC-26**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-27 14:28→15:26 (sau khi endpoint hồi sinh lúc 13:55) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29) |
| Thinking / reasoning level | --thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | read,bash,edit,write,grep,glob; không tự suy là có search |
| System / user prompt | omp sạch + tool menu đầy đủ, trên V-Bench function-calling (nơi scaffold *có thể* thắng) |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Schema validity — có/không có lời gọi hàm hợp lệ theo schema của chính row đó. KHÔNG có gold: điểm chính xác chỉ có ở server (vbench.ai), đã ghi file upload submissions/ompV1clean_Qwen3_5-9B-28K/submission_vbench_*.jsonl (1.000 dòng, 26 dòng rỗng = invalid, không đoán bừa). |
| Model / quantization | Qwen3.5-9B-28K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Arm ompV1clean: scaffold sạch (HOME override ⇒ không rò APPEND_SYSTEM.md) + tool menu đầy đủ 6 tool, qua omp. Prompt = đóng băng từ run_vbench_eval.build_agentic_prompt(style="minimal") — byte-identical với arm A. Tập: 1.000 row track=agentic của vbench.ai release v2026.03.28. Scorer: validator đóng băng _validate_call (enum verbatim, required present, field bịa bị loại). |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-28K / MC-26 | V-Bench agentic — schema validity, không có gold cục bộ | Schema validity | 1000 | — | 97.40 | — | — | -2.60 | -3.60 | -1.70 |
| Qwen3.5-9B-28K / MC-26 | V-Bench agentic — schema validity, không có gold cục bộ | Server accuracy | 1000 | 308 | 30.80 | — | — | — | — | — |

### Comment

- Đây là kết quả của condition riêng. Dữ liệu hiện có chưa tạo thành bảng xếp hạng các model dưới cùng cấu hình đầy đủ.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## MiMo V2.5 · A2 · MiMo V2.5: gọi API trực tiếp (không harness)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**MiMo V2.5 · MC-30**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-29: arm A 10:15→11:12 (4 tập + V-Bench 5.141), arm B 10:57→12:12 (6 tập, 6.319 item), ablation rò 10:58→11:05, speed/cost probe 12:2x một mình |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | MiMo V2.5 qua https://opencode.ai/zen/go/v1 (OpenCode Zen Go), không phải IEC |
| Temperature gửi / hiệu lực | 0.0 gửi theo card/runner; hiệu lực tùy API |
| Thinking / reasoning level | Chưa ghi nhận trong artifact/card |
| Seed | 42 gửi theo card/runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | MiMo V2.5: gọi API trực tiếp (không harness); build_prompt / build_reading_prompt / V-Bench minimal theo từng dataset |
| Ngữ cảnh / dữ liệu đầu vào | MC closed-book; reading có context trong prompt; V-Bench có schema ở từng item |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | MC: 4 token; reading: 48 token; V-Bench theo card riêng, không tự suy cap cho mọi track |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | MiMo V2.5; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Giữ nguyên mọi thứ của MC-22 và thêm ba sửa của MC-29: (1) temperature=0 + reasoning_effort="none" ghim bằng proxy vì omp không gửi được; (2) sandbox ở /tmp nên không có AGENTS.md nạp vào; (3) system prompt trung tính, --no-tools, HOME=/tmp/fakehome. Arm A = gọi thẳng, temperature 0, seed 42, prompt byte-identical (cổng parity: 146/146 và 150/150 khớp với baseline Qwen). Slug arm A mimo-v2_5, slug arm B ompM6clean_mimo-v2.5. |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MiMo V2.5 / MC-30 | reading-400 (EM) | EM | 400 | — | 58.25 | — | — | — | — | — |
| MiMo V2.5 / MC-30 | reading-400 (EM) | Char-F1 | 400 | — | 77.64 | — | — | — | — | — |
| MiMo V2.5 / MC-30 | legal-MC (accuracy) | Accuracy | 146 | — | 90.41 | — | — | — | — | — |
| MiMo V2.5 / MC-30 | legal-NLI (accuracy) | Accuracy | 150 | — | 94.00 | — | — | — | — | — |
| MiMo V2.5 / MC-30 | ViBidLQA val (EM) | EM | 482 | — | 41.70 | — | — | — | — | — |
| MiMo V2.5 / MC-30 | ViBidLQA val (EM) | Char-F1 | 482 | — | 80.54 | — | — | — | — | — |
| MiMo V2.5 / MC-30 | V-Bench agentic — schema validity, không có gold cục bộ | Schema validity | 1000 | — | 99.40 | — | — | — | — | — |
| MiMo V2.5 / MC-30 | V-Bench MC 12 domain — trùng khớp arm A, không có gold cục bộ | Agreement với arm A | 4141 | — | 100.00 | — | — | — | — | — |

### Comment

- Đây là kết quả của condition riêng. Dữ liệu hiện có chưa tạo thành bảng xếp hạng các model dưới cùng cấu hình đầy đủ.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.
- EM thay đổi ở arm harness còn chịu ảnh hưởng độ dài/cách trình bày câu trả lời và output budget. Không suy trực tiếp rằng hiểu nội dung giảm/tăng chỉ từ mức khớp chuỗi này.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## MiMo V2.5 · M6 · MiMo V2.5: omp sạch, không công cụ, prompt trung tính, sandbox ngoài repo; proxy ghim temperature 0 và tắt reasoning

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**MiMo V2.5 · MC-30**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-29: arm A 10:15→11:12 (4 tập + V-Bench 5.141), arm B 10:57→12:12 (6 tập, 6.319 item), ablation rò 10:58→11:05, speed/cost probe 12:2x một mình |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | MiMo V2.5 qua https://opencode.ai/zen/go/v1 (OpenCode Zen Go), không phải IEC |
| Temperature gửi / hiệu lực | 0.0 ghim proxy (MC-29+) |
| Thinking / reasoning level | reasoning_effort="none" ghim bằng proxy (MC-29/30) |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | none |
| System / user prompt | MiMo V2.5: omp sạch, không công cụ, prompt trung tính, sandbox ngoài repo; proxy ghim temperature 0 và tắt reasoning |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | MiMo V2.5; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Giữ nguyên mọi thứ của MC-22 và thêm ba sửa của MC-29: (1) temperature=0 + reasoning_effort="none" ghim bằng proxy vì omp không gửi được; (2) sandbox ở /tmp nên không có AGENTS.md nạp vào; (3) system prompt trung tính, --no-tools, HOME=/tmp/fakehome. Arm A = gọi thẳng, temperature 0, seed 42, prompt byte-identical (cổng parity: 146/146 và 150/150 khớp với baseline Qwen). Slug arm A mimo-v2_5, slug arm B ompM6clean_mimo-v2.5. |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MiMo V2.5 / MC-30 | reading-400 (EM) | EM | 400 | — | 65.25 | — | — | 7.00 | 3.50 | 10.50 |
| MiMo V2.5 / MC-30 | reading-400 (EM) | Char-F1 | 400 | — | 81.63 | — | — | — | — | — |
| MiMo V2.5 / MC-30 | legal-MC (accuracy) | Accuracy | 146 | — | 93.15 | — | — | 2.74 | 0.00 | 6.16 |
| MiMo V2.5 / MC-30 | legal-NLI (accuracy) | Accuracy | 150 | — | 94.00 | — | — | 0.00 | -4.67 | 4.67 |
| MiMo V2.5 / MC-30 | ViBidLQA val (EM) | EM | 482 | — | 43.98 | — | — | 2.28 | 0.00 | 4.77 |
| MiMo V2.5 / MC-30 | ViBidLQA val (EM) | Char-F1 | 482 | — | 79.78 | — | — | — | — | — |
| MiMo V2.5 / MC-30 | V-Bench agentic — schema validity, không có gold cục bộ | Schema validity | 1000 | — | 99.90 | — | — | 0.50 | 0.00 | 1.00 |
| MiMo V2.5 / MC-30 | V-Bench MC 12 domain — trùng khớp arm A, không có gold cục bộ | Agreement với arm A | 4141 | — | 77.61 | — | — | -22.39 | -23.62 | -21.13 |

### Comment

- reading-400 (EM): 65.25% ở arm M6, 58.25% ở arm A cùng model; Δ +7.00 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- legal-MC (accuracy): 93.15% ở arm M6, 90.41% ở arm A cùng model; Δ +2.74 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- legal-NLI (accuracy): 94.00% ở arm M6, 94.00% ở arm A cùng model; Δ +0.00 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- ViBidLQA val (EM): 43.98% ở arm M6, 41.70% ở arm A cùng model; Δ +2.28 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- EM thay đổi ở arm harness còn chịu ảnh hưởng độ dài/cách trình bày câu trả lời và output budget. Không suy trực tiếp rằng hiểu nội dung giảm/tăng chỉ từ mức khớp chuỗi này.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## MiMo V2.5 · M6L · MiMo V2.5: cùng arm M6 nhưng sandbox trong repo, nên AGENTS.md được nạp vào mọi item; ablation MC-29

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**MiMo V2.5 · MC-30**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-09-29: arm A 10:15→11:12 (4 tập + V-Bench 5.141), arm B 10:57→12:12 (6 tập, 6.319 item), ablation rò 10:58→11:05, speed/cost probe 12:2x một mình |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | MiMo V2.5 qua https://opencode.ai/zen/go/v1 (OpenCode Zen Go), không phải IEC |
| Temperature gửi / hiệu lực | 0.0 ghim proxy (MC-29+) |
| Thinking / reasoning level | reasoning_effort="none" ghim bằng proxy (MC-29/30) |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | none |
| System / user prompt | MiMo V2.5: cùng arm M6 nhưng sandbox trong repo, nên AGENTS.md được nạp vào mọi item; ablation MC-29 |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | MiMo V2.5; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Giữ nguyên mọi thứ của MC-22 và thêm ba sửa của MC-29: (1) temperature=0 + reasoning_effort="none" ghim bằng proxy vì omp không gửi được; (2) sandbox ở /tmp nên không có AGENTS.md nạp vào; (3) system prompt trung tính, --no-tools, HOME=/tmp/fakehome. Arm A = gọi thẳng, temperature 0, seed 42, prompt byte-identical (cổng parity: 146/146 và 150/150 khớp với baseline Qwen). Slug arm A mimo-v2_5, slug arm B ompM6clean_mimo-v2.5. |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MiMo V2.5 / MC-30 | legal-MC (accuracy) | Accuracy | 146 | — | 93.84 | — | — | 3.42 | -0.68 | 7.53 |

### Comment

- legal-MC (accuracy): 93.84% ở arm M6L, 90.41% ở arm A cùng model; Δ +3.42 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.
- Sandbox trong repo nạp AGENTS.md; đây là điều kiện khác M6 clean.

## Qwen3.5-9B-65K · A3 · Qwen3.5-9B-65K: gọi API trực tiếp (không harness)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-65K · MC-31**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | Pre-register 2026-09-30 (card ghi xong trước mọi lần chạy); arm A 09:47–10:34 (+07); arm B bắt đầu 10:55, vbench_agentic + vbench_mc chạy nền có --resume |
| Harness / phiên bản / mode | OpenAI-compatible API trực tiếp; không qua agent harness |
| Provider / API / route | Qwen3.5-9B-65K @ https://llmapi.iec-uit.com/v1 — model DUY NHẤT còn chạy (node 28K offline: HTTP 503 Compute Node 'RTX3060-8GB' is offline) |
| Temperature gửi / hiệu lực | 0.0 gửi theo card/runner; hiệu lực tùy API |
| Thinking / reasoning level | Chưa ghi nhận trong artifact/card |
| Seed | 42 gửi theo card/runner |
| Tools | none (gọi API trực tiếp) |
| System / user prompt | Qwen3.5-9B-65K: gọi API trực tiếp (không harness); build_prompt / build_reading_prompt / V-Bench minimal theo từng dataset |
| Ngữ cảnh / dữ liệu đầu vào | MC closed-book; reading có context trong prompt; V-Bench có schema ở từng item |
| History / session / sandbox | Mỗi câu một request; chưa ghi model history ngoài request |
| Giới hạn output | MC: 4 token; reading: 48 token; V-Bench theo card riêng, không tự suy cap cho mọi track |
| Workers / batch | 4 (trần 6) — vì tổng thông lượng prefill không tăng theo số luồng (xem khối server); chạy từng tập + --resume |
| Timeout | Chưa ghi nhận trong artifact/card |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Không đổi: MC exact-letter, reading EM/char-F1, vbench_agentic = schema validity, vbench_mc = mức trùng khớp với arm A (không có gold cục bộ) |
| Model / quantization | Qwen3.5-9B-65K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Arm A: gọi thẳng, prompt byte-frozen như mọi card, temperature 0, seed 42. Arm B: omp sạch — --tools all (bỏ hẳn cờ --tools, menu default của omp), system prompt trung tính, HOME=/tmp/fakehome, sandbox /tmp, temperature=0 ghim bằng proxy (MC-29); không tool-schema nào bị sửa tay. |
| recorded:workers | 4 (trần 6) — vì tổng thông lượng prefill không tăng theo số luồng (xem khối server); chạy từng tập + --resume |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-65K / MC-31 | reading-400 (EM) | EM | 400 | — | 72.25 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | reading-400 (EM) | Char-F1 | 400 | — | 83.45 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | legal-MC (accuracy) | Accuracy | 146 | — | 89.04 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | legal-NLI (accuracy) | Accuracy | 150 | — | 92.00 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | ViBidLQA val (EM) | EM | 482 | — | 29.25 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | ViBidLQA val (EM) | Char-F1 | 482 | — | 73.49 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | V-Bench agentic — schema validity, không có gold cục bộ | Schema validity | 1000 | — | 98.60 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31 | V-Bench MC 12 domain — trùng khớp arm A, không có gold cục bộ | Agreement với arm A | 4141 | — | 100.00 | — | — | — | — | — |

### Comment

- Đây là kết quả của condition riêng. Dữ liệu hiện có chưa tạo thành bảng xếp hạng các model dưới cùng cấu hình đầy đủ.
- Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.
- EM thay đổi ở arm harness còn chịu ảnh hưởng độ dài/cách trình bày câu trả lời và output budget. Không suy trực tiếp rằng hiểu nội dung giảm/tăng chỉ từ mức khớp chuỗi này.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-65K · T65 · Qwen3.5-9B-65K: omp sạch + tool menu đầy đủ, temperature 0 ghim bằng proxy

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-65K · MC-31, MC-32**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | Pre-register 2026-09-30 (card ghi xong trước mọi lần chạy); arm A 09:47–10:34 (+07); arm B bắt đầu 10:55, vbench_agentic + vbench_mc chạy nền có --resume |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Qwen3.5-9B-65K @ https://llmapi.iec-uit.com/v1 — model DUY NHẤT còn chạy (node 28K offline: HTTP 503 Compute Node 'RTX3060-8GB' is offline) |
| Temperature gửi / hiệu lực | 0.0 ghim proxy (MC-29+) |
| Thinking / reasoning level | Level thinking chính xác chưa ghi lại trong artifact; reasoning native không ghim (xem card) |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | all / OMP default menu |
| System / user prompt | Qwen3.5-9B-65K: omp sạch + tool menu đầy đủ, temperature 0 ghim bằng proxy |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | 4 (trần 6) — vì tổng thông lượng prefill không tăng theo số luồng (xem khối server); chạy từng tập + --resume |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Không đổi: MC exact-letter, reading EM/char-F1, vbench_agentic = schema validity, vbench_mc = mức trùng khớp với arm A (không có gold cục bộ) |
| Model / quantization | Qwen3.5-9B-65K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Arm A: gọi thẳng, prompt byte-frozen như mọi card, temperature 0, seed 42. Arm B: omp sạch — --tools all (bỏ hẳn cờ --tools, menu default của omp), system prompt trung tính, HOME=/tmp/fakehome, sandbox /tmp, temperature=0 ghim bằng proxy (MC-29); không tool-schema nào bị sửa tay. |
| recorded:workers | 4 (trần 6) — vì tổng thông lượng prefill không tăng theo số luồng (xem khối server); chạy từng tập + --resume |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-65K / MC-31, MC-32 | reading-400 (EM) | EM | 400 | — | 57.75 | — | — | -14.50 | -19.25 | -10.00 |
| Qwen3.5-9B-65K / MC-31, MC-32 | reading-400 (EM) | Char-F1 | 400 | — | 76.43 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31, MC-32 | legal-MC (accuracy) | Accuracy | 146 | — | 73.97 | — | — | -15.07 | -21.92 | -8.90 |
| Qwen3.5-9B-65K / MC-31, MC-32 | legal-NLI (accuracy) | Accuracy | 150 | — | 88.00 | — | — | -4.00 | -8.00 | 0.00 |
| Qwen3.5-9B-65K / MC-31, MC-32 | ViBidLQA val (EM) | EM | 482 | — | 23.24 | — | — | -6.02 | -9.54 | -2.70 |
| Qwen3.5-9B-65K / MC-31, MC-32 | ViBidLQA val (EM) | Char-F1 | 482 | — | 68.61 | — | — | — | — | — |
| Qwen3.5-9B-65K / MC-31, MC-32 | V-Bench agentic — schema validity, không có gold cục bộ | Schema validity | 1000 | — | 48.50 | — | — | -50.10 | -53.30 | -47.00 |
| Qwen3.5-9B-65K / MC-31, MC-32 | V-Bench MC 12 domain — trùng khớp arm A, không có gold cục bộ | Agreement với arm A | 4141 | — | 63.37 | — | — | -36.63 | -38.13 | -35.16 |

### Comment

- reading-400 (EM): 57.75% ở arm T65, 72.25% ở arm A cùng model; Δ -14.50 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- legal-MC (accuracy): 73.97% ở arm T65, 89.04% ở arm A cùng model; Δ -15.07 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- legal-NLI (accuracy): 88.00% ở arm T65, 92.00% ở arm A cùng model; Δ -4.00 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- ViBidLQA val (EM): 23.24% ở arm T65, 29.25% ở arm A cùng model; Δ -6.02 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.
- EM thay đổi ở arm harness còn chịu ảnh hưởng độ dài/cách trình bày câu trả lời và output budget. Không suy trực tiếp rằng hiểu nội dung giảm/tăng chỉ từ mức khớp chuỗi này.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-65K · F5 · 65K: omp sạch, không công cụ, prompt trung tính — scaffold tối giản

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-65K · MC-46, MC-47**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-05 (pre-register, trước mọi lần chạy) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 ghim proxy (MC-29+) |
| Thinking / reasoning level | Level thinking chính xác chưa ghi lại trong artifact; reasoning native không ghim (xem card) |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | none |
| System / user prompt | 65K: omp sạch, không công cụ, prompt trung tính — scaffold tối giản |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-65K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Model Qwen3.5-9B-65K @ IEC. omp sạch: HOME=/tmp/fakehome, sandbox /tmp, --agent-dir .omp-qwen65k-pinned (temperature 0 ghim qua proxy 127.0.0.1:8799 → llmapi.iec, --pin temperature=0), --arm-a-slug Qwen3_5-9B-65K để so với arm A3 của chính model này, dataset legal_mc (146), workers 4 |
| recorded:4_o | F5 --tools none --system-prompt minimal · F7 --tools none (giữ system prompt của omp) · F8 --tools all (giữ system prompt của omp) · T65‑r2 lặp lại y hệt T65 |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-65K / MC-46, MC-47 | legal-MC (accuracy) | Accuracy | 146 | — | 87.67 | — | — | -1.37 | -5.48 | 2.74 |

### Comment

- legal-MC (accuracy): 87.67% ở arm F5, 89.04% ở arm A cùng model; Δ -1.37 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-65K · F7 · 65K: omp sạch, không công cụ, prompt gốc của omp

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-65K · MC-46, MC-47**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-05 (pre-register, trước mọi lần chạy) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 ghim proxy (MC-29+) |
| Thinking / reasoning level | Level thinking chính xác chưa ghi lại trong artifact; reasoning native không ghim (xem card) |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | none |
| System / user prompt | 65K: omp sạch, không công cụ, prompt gốc của omp |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-65K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Model Qwen3.5-9B-65K @ IEC. omp sạch: HOME=/tmp/fakehome, sandbox /tmp, --agent-dir .omp-qwen65k-pinned (temperature 0 ghim qua proxy 127.0.0.1:8799 → llmapi.iec, --pin temperature=0), --arm-a-slug Qwen3_5-9B-65K để so với arm A3 của chính model này, dataset legal_mc (146), workers 4 |
| recorded:4_o | F5 --tools none --system-prompt minimal · F7 --tools none (giữ system prompt của omp) · F8 --tools all (giữ system prompt của omp) · T65‑r2 lặp lại y hệt T65 |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-65K / MC-46, MC-47 | legal-MC (accuracy) | Accuracy | 146 | — | 79.45 | — | — | -9.59 | -15.07 | -4.11 |

### Comment

- legal-MC (accuracy): 79.45% ở arm F7, 89.04% ở arm A cùng model; Δ -9.59 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-65K · F8 · 65K: omp sạch + tool menu đầy đủ, system prompt gốc của omp

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-65K · MC-46, MC-47**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-05 (pre-register, trước mọi lần chạy) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 ghim proxy (MC-29+) |
| Thinking / reasoning level | Level thinking chính xác chưa ghi lại trong artifact; reasoning native không ghim (xem card) |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | all / OMP default menu |
| System / user prompt | 65K: omp sạch + tool menu đầy đủ, system prompt gốc của omp |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-65K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Model Qwen3.5-9B-65K @ IEC. omp sạch: HOME=/tmp/fakehome, sandbox /tmp, --agent-dir .omp-qwen65k-pinned (temperature 0 ghim qua proxy 127.0.0.1:8799 → llmapi.iec, --pin temperature=0), --arm-a-slug Qwen3_5-9B-65K để so với arm A3 của chính model này, dataset legal_mc (146), workers 4 |
| recorded:4_o | F5 --tools none --system-prompt minimal · F7 --tools none (giữ system prompt của omp) · F8 --tools all (giữ system prompt của omp) · T65‑r2 lặp lại y hệt T65 |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-65K / MC-46, MC-47 | legal-MC (accuracy) | Accuracy | 146 | — | 73.29 | — | — | -15.75 | -22.60 | -8.90 |

### Comment

- legal-MC (accuracy): 73.29% ở arm F8, 89.04% ở arm A cùng model; Δ -15.75 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-65K · T65r2 · 65K: lặp 2 của ô tool đầy đủ + prompt trung tính (sàn nhiễu)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-65K · MC-47**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-05 (sau MC-46) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 ghim proxy (MC-29+) |
| Thinking / reasoning level | Level thinking chính xác chưa ghi lại trong artifact; reasoning native không ghim (xem card) |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | all / OMP default menu |
| System / user prompt | 65K: lặp 2 của ô tool đầy đủ + prompt trung tính (sàn nhiễu) |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-65K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Y hệt MC-46. Tất cả 5 arm sạch: 146/146 item, 0 failure, 0 tool call, 0 net attempt |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-65K / MC-47 | legal-MC (accuracy) | Accuracy | 146 | — | 76.03 | — | — | -13.01 | -19.86 | -6.16 |

### Comment

- legal-MC (accuracy): 76.03% ở arm T65r2, 89.04% ở arm A cùng model; Δ -13.01 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.

## Qwen3.5-9B-65K · T65r3 · 65K: lặp 3 của ô tool đầy đủ + prompt trung tính (sàn nhiễu)

Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.

### Condition

**Qwen3.5-9B-65K · MC-47**

| Trường | Giá trị |
| --- | --- |
| Thời gian chạy | 2026-10-05 (sau MC-46) |
| Harness / phiên bản / mode | OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ |
| Provider / API / route | Chưa ghi nhận trong artifact/card |
| Temperature gửi / hiệu lực | 0.0 ghim proxy (MC-29+) |
| Thinking / reasoning level | Level thinking chính xác chưa ghi lại trong artifact; reasoning native không ghim (xem card) |
| Seed | OMP không gửi seed; seed 42 trong card không đảm bảo được truyền |
| Tools | all / OMP default menu |
| System / user prompt | 65K: lặp 3 của ô tool đầy đủ + prompt trung tính (sàn nhiễu) |
| Ngữ cảnh / dữ liệu đầu vào | User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book |
| History / session / sandbox | scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp |
| Giới hạn output | OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại |
| Workers / batch | Chưa ghi nhận trong artifact/card |
| Timeout | 180 giây/item theo card harness |
| Retry / recovery | Chưa ghi nhận trong artifact/card |
| Gold / cách chấm | Chưa ghi nhận trong artifact/card |
| Model / quantization | Qwen3.5-9B-65K; Chưa ghi nhận trong artifact/card |
| recorded:dieu_kien | Y hệt MC-46. Tất cả 5 arm sạch: 146/146 item, 0 failure, 0 tool call, 0 net attempt |

### Benchmark

| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-9B-65K / MC-47 | legal-MC (accuracy) | Accuracy | 146 | — | 74.66 | — | — | -14.38 | -21.23 | -7.53 |

### Comment

- legal-MC (accuracy): 74.66% ở arm T65r3, 89.04% ở arm A cùng model; Δ -14.38 pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.

### Note

- CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.
- Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng.
