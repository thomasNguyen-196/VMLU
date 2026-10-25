# Kết quả main benchmark tiếng Việt đa model — 2026-10-07

Trạng thái: **hoàn tất 8.172/8.172 item-model**, 2.043 item cho mỗi model, coverage 100%, không còn request lỗi trong checkpoint cuối.

Condition đầy đủ của MC-53–56, nhóm sampling tương đương, benchmark/category comment và note: [báo cáo theo điều kiện](benchmark-condition-reports.md) · [CSV](benchmark-condition-reports.csv) · frontend `/table`.

## Bảng so sánh

| Model | VMLU valid accuracy (n=744) | Vi-SQuAD EM / token-F1 (n=200) | Vi-DROP EM / token-F1 (n=200) | ViBidLQA test EM / token-F1 (n=603) | Legal MC accuracy (n=146) | Legal NLI accuracy (n=150) | Truncation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | 91.13% (678/744) | 74.50% / 89.01% | 58.50% / 73.86% | 50.25% / 76.89% | 93.15% (136/146) | 80.00% (120/150) | 11 |
| MiMo V2.6 Flash | 80.11% (596/744) | 67.00% / 86.45% | 24.00% / 50.00% | 38.97% / 74.30% | 81.51% (119/146) | 86.67% (130/150) | 34 |
| MiMo V2.5 | 76.61% (570/744) | 58.00% / 78.32% | 25.50% / 43.30% | 29.35% / 66.05% | 82.88% (121/146) | 86.00% (129/150) | 32 |
| Qwen3.5-9B-65K | 67.07% (499/744) | 80.00% / 91.85% | 50.50% / 59.82% | 25.21% / 63.80% | 85.62% (125/146) | 92.67% (139/150) | 0 |

Các số trong cột đọc hiểu lần lượt là exact match có giữ dấu và token-F1. Accuracy, EM và token-F1 đều tính trên toàn bộ mẫu của dataset tương ứng; câu không parse được vẫn ở trong mẫu số. Khoảng tin cậy 95%, thời gian phản hồi, token usage và breakdown bổ sung được lưu trong `summary.json` của từng run.

## Điều kiện và độ phủ

- Mỗi model xử lý cùng manifest `main_v1.json`: 744 câu VMLU valid, 200 Vi-SQuAD, 200 Vi-DROP, 146 legal MC, 150 legal NLI và 603 ViBidLQA test.
- Chạy qua OMP với bốn worker, một item mỗi request, tools và session history tắt, prompt theo manifest, completion cap 4.096 token cho MC và 2.048 token cho đọc hiểu.
- Các run dùng card MC-53–56. Muse và hai MiMo dùng reasoning `auto`; Qwen dùng `thinking off` theo adapter IEC. Kết quả là phép so sánh theo điều kiện đã công bố; reasoning giữa provider không tương đương.
- Mọi checkpoint cuối có 2.043 dòng `complete`, 0 dòng `request_error`. Các request lỗi do mạng ở lần chạy trước được chạy lại từ checkpoint; chúng không được chấm như câu trả lời sai.
- Vi-SQuAD và Vi-DROP có gold trong bộ 400 câu người dùng đã chấm; ViBidLQA test có 603 gold answer trong manifest. Với các bộ đọc hiểu này, EM là exact-match accuracy theo quy tắc chuẩn hoá hiện tại; accuracy exact-match riêng sẽ lặp cùng kết quả. Accuracy MC dùng nhãn đáp án của dataset.
- Accuracy CI95 dùng Wilson; CI95 cho reading dùng bootstrap theo passage với 2.000 lần lấy mẫu. Traces cũng lưu truncation, độ trễ, token usage, empty/unparsed và breakdown theo stratum.
- Không dùng pay-as-you-go cho ba model OpenCode Go. Budget guard là Muse $1.55, MiMo V2.6 $2.15, MiMo V2.5 $2.16 và Qwen $1.00-equivalent. Cap MiMo V2.5 tăng $0.01 khi resume để bao phủ reserve bảo thủ cho request mạng lỗi không có token usage; điều kiện prompt và model không đổi.
- Quota-equivalent theo usage đã báo là Muse $0.334086, MiMo V2.6 $0.220656, MiMo V2.5 $0.209348. Một số attempt không có usage telemetry nên đây không phải đối soát usage đầy đủ. Qwen chạy qua IEC nội bộ; tariff hạ tầng không được khai báo nên chi phí không được định giá.
- Mỗi `run.json` lưu hash measurement card dùng trước khi chạy; báo cáo này là bản tổng hợp sau chạy.

## Artifacts

- Manifest: `data/vi_multimodel_v1/main_v1.json`
- Protocol: `data/vi_multimodel_protocol_v1.json`
- Scorer: `code_benchmark/score_vi_multimodel.py`
- Runs và summary cục bộ: `all_res/vi_multimodel_v1/main/<profile>/`
- Pilot: [trạng thái pilot ngày 2026-10-06](vi-multimodel-pilot-status-2026-10-06.md)
