# VMLU leaderboard — Qwen3.5-9B-28K (test 9.833, card MC-7)

Điều kiện đo: `MC-7`, measurement_card.md. Chấm server-side duy nhất qua `vmlu.ai/submit`
(test gold withheld — không gold local). Ngày có điểm: 2026-09-20.

File upload: `submissions/Qwen3_5-9B-28K/submission_vmlu_test_Qwen3_5-9B-28K.csv`
(9.833 rows, `id,answer` chữ hoa, 0 blank — byte-identical với `raw_result_9833`).

## Overall: 67,87%

| Category | Score |
| --- | --- |
| STEM | 65,65 |
| Social Science | 74,97 |
| Humanity | 68,61 |
| Other | 63,67 |

## STEM (21 môn)

| Môn | Score |
| --- | --- |
| applied_informatics | 78,33 |
| computer_architecture | 67,22 |
| computer_network | 70,95 |
| discrete_mathematics | 67,27 |
| electrical_engineering | 53,41 |
| elementary_mathematics | 71,11 |
| elementary_science | 92,78 |
| high_school_biology | 63,33 |
| high_school_chemistry | 59,44 |
| high_school_mathematics | 62,16 |
| high_school_physics | 58,33 |
| introduction_to_chemistry | 66,48 |
| introduction_to_physics | 56,07 |
| introduction_to_programming | 69,83 |
| metrology_engineer | 60,99 |
| middle_school_biology | 78,24 |
| middle_school_chemistry | 72,22 |
| middle_school_mathematics | 51,85 |
| middle_school_physics | 66,67 |
| operating_system | 66,67 |
| statistics_and_probability | 45,40 |

## Social Science (10 môn)

| Môn | Score |
| --- | --- |
| business_administration | 63,79 |
| high_school_civil_education | 82,78 |
| high_school_geography | 65,43 |
| ho_chi_minh_ideology | 70,95 |
| macroeconomics | 68,89 |
| microeconomics | 75,00 |
| middle_school_civil_education | 89,89 |
| middle_school_geography | 78,23 |
| principles_of_marxism_and_leninism | 75,56 |
| sociology | 79,21 |

## Humanity (18 môn)

| Môn | Score |
| --- | --- |
| administrative_law | 58,89 |
| business_law | 67,60 |
| civil_law | 80,56 |
| criminal_law | 74,85 |
| economic_law | 62,11 |
| education_law | 60,84 |
| elementary_history | 75,71 |
| high_school_history | 68,33 |
| high_school_literature | 60,00 |
| history_of_world_civilization | 78,89 |
| idealogical_and_moral_cultivation | 88,89 |
| introduction_to_laws | 78,57 |
| introduction_to_vietnam_culture | 68,33 |
| logic | 50,57 |
| middle_school_history | 74,44 |
| middle_school_literature | 70,69 |
| revolutionary_policy_of_the_vietnamese_commununist_part | 59,44 |
| vietnamese_language_and_literature | 56,32 |

## Other (9 môn)

| Môn | Score |
| --- | --- |
| accountant | 66,07 |
| civil_servant | 61,40 |
| clinical_pharmacology | 72,78 |
| driving_license_certificate | 81,87 |
| environmental_engineering | 54,97 |
| internal_basic_medicine | 70,18 |
| preschool_pedagogy | 64,71 |
| tax_accountant | 42,53 |
| tax_civil_servant | 58,48 |

## Nhận xét (so với local gold MC-9, cùng model)

- Leaderboard test (67,87%) thấp hơn local all_gold (73,35%) — tập khác, cấm suy "giảm điểm".
- SocSci vẫn mạnh nhất ở cả hai (74,97 vs 78,26); Other yếu nhất ở cả hai (63,67 vs 62,82).
- Cấm so ngang MC-1 (model khác).
