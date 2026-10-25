# Tổng hợp kết quả benchmark tiếng Việt đa model

Ngày tổng hợp: 2026-10-09. CSV gồm dataset-level, phase summary và group/subject breakdown từ các summary đã chấm.

Bản trình bày đầy đủ **Condition → Benchmark → Comment → Note**, gồm run cũ từ MC-1, nằm ở [báo cáo theo điều kiện](benchmark-condition-reports.md), [CSV có cấu hình và nhận xét](benchmark-condition-reports.csv) và frontend `/table`, `/table/v2`, `/table/history`.

**Không gộp điểm giữa các protocol.** Main v1, các pilot và expansion v2 là các điều kiện/mẫu riêng.

## Main benchmark v1

Bốn profile hoàn tất 2.043 item/profile, coverage 100%, không còn request error. Vi-SQuAD, Vi-DROP và ViBidLQA dùng EM + token-F1; MC dùng accuracy.

| Model | VMLU valid accuracy (n=744) | VMLU CI95 lower | VMLU CI95 upper | Vi-SQuAD (n=200) | Vi-DROP (n=200) | ViBidLQA test (n=603) | Legal MC accuracy (n=146) | Legal MC CI95 lower | Legal MC CI95 upper | Legal NLI accuracy (n=150) | Legal NLI CI95 lower | Legal NLI CI95 upper | Truncation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | 91.13% (678/744) | 88.87% | 92.97% | EM 74.50% / F1 89.01% | EM 58.50% / F1 73.86% | EM 50.25% / F1 76.89% | 93.15% (136/146) | 87.85% | 96.24% | 80.00% (120/150) | 72.89% | 85.62% | 11 |
| MiMo V2.6 Flash | 80.11% (596/744) | 77.09% | 82.82% | EM 67.00% / F1 86.45% | EM 24.00% / F1 50.00% | EM 38.97% / F1 74.30% | 81.51% (119/146) | 74.43% | 86.97% | 86.67% (130/150) | 80.30% | 91.20% | 34 |
| MiMo V2.5 | 76.61% (570/744) | 73.44% | 79.51% | EM 58.00% / F1 78.32% | EM 25.50% / F1 43.30% | EM 29.35% / F1 66.05% | 82.88% (121/146) | 75.94% | 88.12% | 86.00% (129/150) | 79.54% | 90.66% | 32 |
| Qwen3.5-9B-65K | 67.07% (499/744) | 63.61% | 70.35% | EM 80.00% / F1 91.85% | EM 50.50% / F1 59.82% | EM 25.21% / F1 63.80% | 85.62% (125/146) | 79.01% | 90.40% | 92.67% (139/150) | 87.35% | 95.86% | 0 |

Unparsed answer vẫn nằm trong mẫu số. CI95, latency và detailed VMLU subject/group breakdown nằm trong CSV.

## Pilot v1 — diagnostics, không phải leaderboard

Mỗi profile có 100 VMLU-dev + 80 ViBidLQA-val unique items và 20 repeat requests. Qwen dùng kết quả hoàn chỉnh của `pilot_omp`; bản pilot ban đầu chưa hoàn tất.

| Model | VMLU-dev (n=100) | ViBidLQA-val EM / F1 (n=80) | Repeat agreement MC / reading | MC truncation | Ghi chú |
| --- | ---: | ---: | ---: | ---: | --- |
| Muse Spark 1.3 Contributor | 90/100 (90.0%) | 45.0% / 77.43% | 9/10 (90%) / 8/10 (80%) | 2 |  |
| MiMo V2.6 Flash | 83/100 (83.0%) | 42.5% / 75.33% | 9/10 (90%) / 7/10 (70%) | 9 |  |
| MiMo V2.5 | 79/100 (79.0%) | 32.5% / 64.91% | 9/10 (90%) / 3/10 (30%) | 4 |  |
| Qwen3.5-9B-65K | 76/100 (76.0%) | 25.0% / 66.97% | 9/10 (90%) / 5/10 (50%) | 0 | Completed OMP rerun; initial Qwen pilot was incomplete. |

## Pilot v2 — diagnostics, không phải V-Bench chính thức

| Model | VMLU-dev (n=100) | Synthetic agentic (n=80) | Repeat agreement VMLU / agentic |
| --- | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | 93/100 (93.0%) | 70/80 (87.5%) | 100% / 100% |
| MiMo V2.6 Flash | 90/100 (90.0%) | 62/80 (77.5%) | 80% / 90% |
| MiMo V2.5 | 87/100 (87.0%) | 60/80 (75.0%) | 80% / 100% |

## VMLU expansion v2

Bốn profile hoàn tất 10.880/10.880 item, 0 request error. Đây là protocol v2 riêng, không ghép với main v1. Qwen chạy theo condition MC-70 (`temperature=1`, `thinking=auto`, seed omitted); Test gold vẫn withheld và server grade 63.86% do người dùng cung cấp.

| Model | Dev accuracy (n=303) | Dev CI95 lower | Dev CI95 upper | Valid accuracy (n=744) | Valid CI95 lower | Valid CI95 upper | Dev + Valid accuracy (n=1,047) | Pooled CI95 lower | Pooled CI95 upper | Test server accuracy (n=9,833) | V-Bench MC | V-Bench agentic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | 91.09% (276/303) | 87.35% | 93.80% | 91.13% (678/744) | 88.87% | 92.97% | 91.12% (954/1,047) | 89.24% | 92.69% | 87.04% (VMLU server) | deferred 0/4,141 | deferred 0/1,000 |
| MiMo V2.6 Flash | 83.17% (252/303) | 78.55% | 86.96% | 80.24% (597/744) | 77.23% | 82.94% | 81.09% (849/1,047) | 78.60% | 83.35% | 76.20% (VMLU server) | deferred 0/4,141 | deferred 0/1,000 |
| MiMo V2.5 | 82.18% (249/303) | 77.47% | 86.08% | 78.23% (582/744) | 75.12% | 81.04% | 79.37% (831/1,047) | 76.81% | 81.71% | 75.62% (VMLU server) | deferred 0/4,141 | deferred 0/1,000 |
| Qwen3.5-9B-65K | 71.29% (216/303) | 65.95% | 76.09% | 69.62% (518/744) | 66.23% | 72.82% | 70.11% (734/1,047) | 67.26% | 72.80% | 63.86% (VMLU server) | deferred 0/4,141 | deferred 0/1,000 |

VMLU Test inference đã hoàn tất cho cả bốn model (9.833 câu mỗi model). Server score/category/subject breakdown cho Qwen được người dùng cung cấp trong turn hiện tại; local gold vẫn withheld nên không suy ra correct count hay CI từ tỷ lệ server. Một đáp án Qwen không parse được được xuất thành ô trống và vẫn thuộc mẫu số; CSV giữ parser-validity riêng như diagnostic, không dùng thay server grade. V-Bench vẫn được tạm hoãn: 0 request đã chạy ở cả MC và agentic.

### VMLU Test v2 server grade by category

| Model | Overall | STEM | Social Science | Humanity | Other |
| --- | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | 87.04% | 88.98% | 87.42% | 86.45% | 83.30% |
| MiMo V2.6 Flash | 76.20% | 81.22% | 80.21% | 72.05% | 68.32% |
| MiMo V2.5 | 75.62% | 79.63% | 79.02% | 72.94% | 67.84% |
| Qwen3.5-9B-65K | 63.86% | 61.76% | 72.13% | 64.15% | 58.97% |

Toàn bộ 58 subject-level server scores cho mỗi model được lưu trong CSV; denominator/correct count từng môn không có trong JSON đầu vào nên không tự suy ra.

### Historical VMLU Test server score — separate condition

| Model | Card | Test items | Official server accuracy | Date |
| --- | --- | ---: | ---: | --- |
| Qwen3.5-9B-28K | MC-7 | 9,833 | 67.87% | 2026-09-20 |

This historical grade is for a different model and condition and is kept separate from the MC-70 result. See the [MC-7 server record](../vmlu-leaderboard-qwen35.md).

Accuracy Dev + Valid là tỷ lệ gộp theo số lượng câu, không phải trung bình cộng hai accuracy. Các pilot dùng mẫu nhỏ và được giữ riêng khỏi main benchmark.

## Files

- Bảng tổng hợp: `docs/research/vi-multimodel-all-results-2026-10-09.md`
- CSV tổng hợp duy nhất: `docs/research/vi-multimodel-all-results-2026-10-09.csv`
- Main v1 report nguồn: `docs/research/vi-multimodel-main-results-2026-10-07.md`
- Pilot report nguồn: `docs/research/vi-multimodel-pilot-status-2026-10-06.md`
- V2-specific report vẫn được giữ tại `docs/research/vi-multimodel-expansion-v2-results.md`
- Qwen MC-70 VMLU Test submission CSV: `submissions/vi_multimodel_v2/qwen3-5-9b-65k/submission_vmlu_test.csv`
