# Kết quả VMLU expansion v2

Bản tổng hợp lưu ngày 2026-10-09. Protocol `vi-multimodel-expansion-v2` version 2.

Condition đầy đủ, benchmark, comment theo category và note từng run: [báo cáo chung](benchmark-condition-reports.md) · [CSV](benchmark-condition-reports.csv) · frontend `/table/v2`.

Cả bốn model đều hoàn tất VMLU: **10.880/10.880 item/model, 0 request error**. Qwen dùng condition riêng MC-70 (`temperature=1`, `thinking=auto`, seed omitted); không gộp với condition Qwen MC-65 trước đó.

## Bảng benchmark

| Model | VMLU Dev accuracy (n=303) | Dev CI95 lower | Dev CI95 upper | VMLU Valid accuracy (n=744) | Valid CI95 lower | Valid CI95 upper | Dev + Valid accuracy (n=1,047) | Pooled CI95 lower | Pooled CI95 upper | VMLU Test server accuracy (n=9,833) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | 91.09% (276/303) | 87.35% | 93.80% | 91.13% (678/744) | 88.87% | 92.97% | 91.12% (954/1,047) | 89.24% | 92.69% | 87.04% (VMLU server) |
| MiMo V2.6 Flash | 83.17% (252/303) | 78.55% | 86.96% | 80.24% (597/744) | 77.23% | 82.94% | 81.09% (849/1,047) | 78.60% | 83.35% | 76.20% (VMLU server) |
| MiMo V2.5 | 82.18% (249/303) | 77.47% | 86.08% | 78.23% (582/744) | 75.12% | 81.04% | 79.37% (831/1,047) | 76.81% | 81.71% | 75.62% (VMLU server) |
| Qwen3.5-9B-65K (MC-70) | 71.29% (216/303) | 65.95% | 76.09% | 69.62% (518/744) | 66.23% | 72.82% | 70.11% (734/1,047) | 67.26% | 72.80% | 63.86% (VMLU server) |

## Các lượt chưa có điểm local

- **V-Bench MC:** deferred theo yêu cầu người dùng, 0/4.141 item đã chạy.
- **V-Bench agentic:** deferred theo yêu cầu người dùng, 0/1.000 item đã chạy.
- Qwen VMLU Test inference hoàn tất 9.833/9.833 câu; một đáp án không parse được được xuất thành ô trống. Gold vẫn withheld, nên không tính local Test correct count/CI. Server accuracy 63.86% và category/subject breakdown do người dùng cung cấp; CSV giữ parser-validity riêng như diagnostic.
- Server scores/category totals cho cả bốn profile được lưu riêng khỏi local-gold scores. Per-subject denominator/correct count không có trong JSON nên không tự suy ra.

### VMLU Test v2 server grade by category

| Model | Overall | STEM | Social Science | Humanity | Other |
| --- | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | 87.04% | 88.98% | 87.42% | 86.45% | 83.30% |
| MiMo V2.6 Flash | 76.20% | 81.22% | 80.21% | 72.05% | 68.32% |
| MiMo V2.5 | 75.62% | 79.63% | 79.02% | 72.94% | 67.84% |
| Qwen3.5-9B-65K | 63.86% | 61.76% | 72.13% | 64.15% | 58.97% |

Subject-level details are in the accompanying CSV; no per-subject denominators were supplied.

### Historical VMLU Test server score — separate condition

| Model | Card | Test items | Official server accuracy | Date |
| --- | --- | ---: | ---: | --- |
| Qwen3.5-9B-28K | MC-7 | 9,833 | 67.87% | 2026-09-20 |

This historical grade is for a different model and condition; the MC-70 result is separately recorded above. See the [MC-7 server record](../vmlu-leaderboard-qwen35.md).

Accuracy local dùng Wilson CI95; đáp án không parse được vẫn nằm trong mẫu số và tính là sai. Dev + Valid là accuracy gộp theo số lượng câu của hai split, không phải trung bình cộng hai tỷ lệ.

CSV đi kèm có các dòng benchmark-level cho từng split/phase, breakdown local theo 58 subject/stratum của Dev và Valid, cùng category và 58 subject server breakdown cho Test.

## Artifacts

- Bảng benchmark: `docs/research/vi-multimodel-expansion-v2-results.md`
- CSV tổng hợp: `docs/research/vi-multimodel-expansion-v2-results.csv`
- Dashboard snapshot: `web/data/vi-multimodel-expansion-v2-results.json`
- Summary gốc: `all_res/vi_multimodel_v2/vmlu/<profile>/summary.json`
- Qwen MC-70 Test submission CSV: `submissions/vi_multimodel_v2/qwen3-5-9b-65k/submission_vmlu_test.csv`
