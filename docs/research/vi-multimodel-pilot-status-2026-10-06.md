# Pilot benchmark tiếng Việt đa model — trạng thái 2026-10-06

Trạng thái: **đủ bốn profile, 200/200 request mỗi profile**. Đây là pilot diagnostics, không phải leaderboard chính.

Main benchmark sau đó đã hoàn tất cho cả bốn profile, 2.043/2.043 câu mỗi model. Xem [bảng kết quả main ngày 2026-10-07](vi-multimodel-main-results-2026-10-07.md).

## Điều kiện đo

- Mỗi profile chạy 100 câu VMLU-dev + 80 câu ViBidLQA-val duy nhất + 20 lượt lặp; accuracy, EM và token-F1 chỉ dùng 180 câu duy nhất.
- OMP 18.0.0; một tiến trình/item; user prompt giữ nguyên byte; system prompt `Answer the user's question.`; tools và session history tắt; bốn workers; không tự retry.
- Completion cap pilot là 2.048 token cho MC và đọc hiểu. Câu trả lời đọc hiểu được chấm bằng EM giữ dấu và token-F1.
- Muse và MiMo bật reasoning theo cấu hình provider; Qwen MC-57 dùng `--thinking off` theo adapter IEC đã đăng ký. Reasoning giữa provider không tương đương, nên bảng là so sánh theo điều kiện đã khai báo.
- Lượt lặp báo agreement riêng, không đưa vào điểm chính. Các attempt MC-52 lỗi và probe MC-57 lỗi trước khi tunnel lên không nằm trong mẫu chấm.

## Điểm pilot

| Chỉ số | Muse Spark 1.3 Contributor | MiMo V2.6 Flash | MiMo V2.5 | Qwen3.5-9B-65K |
| --- | ---: | ---: | ---: | ---: |
| VMLU-dev accuracy (n=100) | 90/100 (90.0%) | 83/100 (83.0%) | 79/100 (79.0%) | 76/100 (76.0%) |
| ViBidLQA-val EM (n=80) | 36/80 (45.0%) | 34/80 (42.5%) | 26/80 (32.5%) | 20/80 (25.0%) |
| ViBidLQA-val token-F1 | 77.43% | 75.33% | 64.91% | 66.97% |
| Repeat agreement, MC / reading | 9/10 (90%) / 8/10 (80%) | 9/10 (90%) / 7/10 (70%) | 9/10 (90%) / 3/10 (30%) | 9/10 (90%) / 5/10 (50%) |
| MC truncation (n=100) | 2 | 9 | 4 | 0 |
| Usage-equivalent thực tế | $0.029479 | $0.017914 | $0.014896 | Chưa định giá hạ tầng IEC |

Khoảng tin cậy 95% của accuracy MC lần lượt là Muse 82.6–94.5%, MiMo V2.6 74.5–89.1%, MiMo V2.5 70.0–85.8%, Qwen 66.8–83.3%. Khoảng tin cậy EM đọc hiểu là Muse 33.8–56.3%, MiMo V2.6 31.2–53.6%, MiMo V2.5 22.2–43.0%, Qwen 15.4–35.4%. Token-F1 intervals và breakdown theo nhóm nằm trong từng `summary.json` dưới `all_res/vi_multimodel_v1/`.

Usage-equivalent thực tế của ba profile OpenCode Go cộng lại là $0.062289; đây là mức quy đổi theo token usage cho quota subscription, không phải pay-as-you-go charge. Cache-miss reserve pilot lần lượt là Muse $0.104461 và mỗi MiMo $0.146246. Qwen không có tariff token được khai báo; chi phí hạ tầng IEC không tính.

Completion token p90 theo thứ tự MC / đọc hiểu: Muse 750 / 777; MiMo V2.6 394 / 117; MiMo V2.5 369 / 172; Qwen 2 / 43. Reading không có truncation trong 320 câu chính. Ở MC, các profile Go có 15 truncation trên 300 câu chính với cap 2.048; Qwen có 0/100.

## Qwen MC-57

Pilot Qwen hoàn tất qua OMP sau khi kết nối IEC VPN bằng profile TCP và cấu hình split DNS cho `.iec`. Run có 200/200 response hợp lệ; 180 câu chính và 20 lượt lặp. Điểm MC-52 lỗi trước đó vẫn được giữ riêng và không tính vào kết quả. Nội dung MC-57 trong card hiện tại giống snapshot preregister dùng lúc chạy; run ghi `measurement_card_hash=2f67984afd0bb35136551b253202e239c90d59ee6e7e147e67b58943871a0287`.

## Ngân sách dự kiến trước main

- Main manifest có 2.043 câu/profile: 1.040 MC và 1.003 đọc hiểu, tổng 8.172 request dữ liệu cho bốn model, chưa kể probe.
- Đề xuất cap **4.096 token cho MC** và **2.048 token cho đọc hiểu**. Cap MC cao hơn pilot để giảm truncation; cap reading giữ nguyên vì không có truncation ở pilot.
- Theo cache-miss worst-case bound với các cap trên, usage-equivalent ước tính là Muse $1.531043, mỗi MiMo $2.143460, tổng ba profile Go $5.817962; Qwen nội bộ là $0 theo tariff khai báo, không gồm chi phí hạ tầng.
- Các con số trên là ước tính trước khi chạy. Main đã được đóng băng trong MC-53–56 và hoàn tất; chi tiết cap cùng mức quota-equivalent thực tế nằm trong báo cáo kết quả main.

## Giới hạn và xử lý dữ liệu

OpenCode Go ghi rõ Muse Spark Contributor có thể dùng prompt/completion để huấn luyện Meta, không có zero data retention và chỉ khả dụng ở một số region. Các câu benchmark được gửi qua Go theo lựa chọn đã xác nhận. [OpenCode Go usage limits, models, and privacy](https://opencode.ai/docs/go/).

OpenCode Go hướng tới traffic coding-agent; pilot này dùng OMP nhưng là QA benchmark không-code với tools tắt. Pilot chỉ đo VMLU-dev và ViBidLQA-val, chưa kết luận về pháp luật, Vi-SQuAD, Vi-DROP hay thứ hạng tổng.
