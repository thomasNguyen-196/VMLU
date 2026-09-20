# V-Bench server scores — Qwen3.5-9B-28K (public test v2026.03.28, card MC-8)

Điều kiện đo: `MC-8`, measurement_card.md. Chấm server-side duy nhất qua `vbench.ai/submission`
(không gold local). Ngày có điểm: 2026-09-20.

File upload: `submissions/Qwen3_5-9B-28K/submission_vbench_Qwen3_5-9B-28K.jsonl`
(5.141 dòng, mc 4.141 + agentic 1.000 — gồm 14 guided rows, condition thứ 3).

Snapshot: `all_res/ollama_result/Qwen3_5-9B-28K/vbench_server_scores_Qwen3_5-9B-28K.csv`
(ghi qua `--record-server-scores`; nơi DUY NHẤT chứa `correct`).

## Overall: macro 45,22 · micro 45,61% (2.345/5.141)

| Track | Correct | Total | Accuracy |
| --- | --- | --- | --- |
| multiple-choice | 1.948 | 4.141 | 47,04% |
| agentic (function calling) | 397 | 1.000 | 39,70% |

## Per-domain

| Domain | Track | Score | Correct |
| --- | --- | --- | --- |
| agentic | function calling | 39,70 | 397/1.000 |
| chemistry | multiple-choice | 38,92 | 130/334 |
| computer_science | multiple-choice | 71,28 | 134/188 |
| culture | multiple-choice | 47,93 | 104/217 |
| dialect | multiple-choice | 60,14 | 338/562 |
| laws | multiple-choice | 62,83 | 120/191 |
| literature | multiple-choice | 41,10 | 247/601 |
| logics | multiple-choice | 24,89 | 56/225 |
| mathematics | multiple-choice | 20,00 | 25/125 |
| medicine | multiple-choice | 38,57 | 189/490 |
| philosophy | multiple-choice | 64,64 | 170/263 |
| physics | multiple-choice | 28,57 | 42/147 |
| psychology | multiple-choice | 49,25 | 393/798 |

## Nhận xét

- Mạnh nhất: computer_science (71,28), philosophy (64,64), laws (62,83), dialect (60,14).
- Yếu nhất: mathematics (20,00), logics (24,89), physics (28,57) — cùng cụm STEM định lượng yếu như local gold.
- Agentic 39,70% gồm 14 guided rows (condition thứ 3) — không gộp silent vào minimal.
- Cấm so ngang MC-2/MC-2b (model khác).
