## Phase 0 — Chốt gold vào manifest (5 phút, làm trước)

- [x] 0.1 Fill `gold_answer` từ agreed gold: `export_annotation_workbooks.py merge-split review_records/review_nttung245_qwen3_8_27b_q4_k_m_gguf.csv --apply` — commit `3e35462` (model Qwen3_8-27B-Q4_K_M_gguf @ IEC endpoint; 321 accept + 79 reject, adjudication rỗng; dry-run diff byte-identical với gold đã commit)
- [x] 0.2 Verify: 400/400 `gold_answer` non-empty, key-set `(dataset,item_id)` vẫn bằng `review_gold_agreed.csv` (0 mismatch), diff chỉ chạm cột `gold_answer` (400+/400-); pre-phase0 backup tại `/tmp/eval_set_manifest.pre-phase0.csv` — commit riêng `3e35462` (audit trail của pre-registration)

## Phase 1 — Reading 400q full trên Qwen3.5 (gold đã chấm)

- [x] 1.1 Run full: `.venv/bin/python code_benchmark/run_reading_eval.py --model Qwen3.5-9B-28K --workers 4` (dot form — endpoint id; KHÔNG `--limit`); xong exit 0, 232s, 400 answers, 0 empty; checkpoints `reading_result_{100,200,300,400}_Qwen3_5-9B-28K.csv`; gián đoạn thì `--resume`
- [x] 1.2 Verify answers: `reading_answers_Qwen3_5-9B-28K.csv` đủ 400 rows (200 squad + 200 drop), 0 empty, key-set khớp manifest 2 chiều (0 mismatch)
- [x] 1.3 Score: `.venv/bin/python code_benchmark/score_reading_eval.py --answers all_res/ollama_result/Qwen3_5-9B-28K/reading_answers_Qwen3_5-9B-28K.csv` (phải chỉ rõ --answers: default newest theo sort sẽ vớ nhầm model cũ) → squad EM 96.50 / F1 98.63, drop EM 63.00 / F1 74.35, ALL EM 79.75 (319/400) / F1 86.49. BUG FIX: `score_reading_eval.py` thiếu dòng ghi `reading_scores_*` (chỉ log "Wrote" nhưng không write) — đã thêm `write_csv_atomic(scores_path, rows, SCORE_COLS)`
- [x] 1.4 Patch dashboard: `build_dashboard_reading.py --answers ...Qwen3_5... --review-record review_records/review_nttung245_qwen3_8_27b_q4_k_m_gguf.csv` (flag mới, user duyệt) → blob `.reading` = Qwen3.5 (ALL EM 79.75/F1 86.49); blob parse OK, các key khác nguyên vẹn. Code fix: thêm `--review-record` (record là thuộc tính của gold đóng băng, không của model)
- [x] 1.5 Report: EM = em_count/400 (số + %), char-F1 %, breakdown squad/drop; KHÔNG dùng accept-rate làm accuracy

## Phase 2 — VMLU MC full + chấm trên gold

- [x] 2.1 `valid.jsonl` (744, có gold): chạy xong exit 0, 220s → **540/744 = 72.58%** (STEM 78.31 / SocSci 76.34 / Humanity 68.56 / Other 62.50); recompute từ `full_evaluation_*` khớp 0 mismatch
- [x] 2.2 `dev.jsonl` (303, có gold): chạy xong exit 0, 91s → **229/303 = 75.58%** (STEM 81.08 / SocSci 84.91 / Humanity 67.37 / Other 68.18); recompute khớp. LƯU Ý: runner ghi đè `full_evaluation_*` + `accuracy_*` theo tên model (không theo file input) — file cuối cùng trên đĩa là của all_gold; số valid/dev đã record ở đây
- [x] 2.3 `all_gold.jsonl` (1047, có gold): chạy xong exit 0, 309s → **768/1047 = 73.35%** (STEM 79.37 / SocSci 78.26 / Humanity 68.52 / Other 62.82); 0 mismatch
- [x] 2.4 Rebuild test submission: verified `submissions/Qwen3_5-9B-28K/submission_vmlu_test_Qwen3_5-9B-28K.csv` byte-identical với rebuild từ `raw_result_9833_Qwen3_5-9B-28K.csv` (sha256 `1dc68aa3…`, 9.833 rows, 0 empty, header `id,answer`, đáp án A–E hoa) — sẵn sàng upload vmlu.ai
- [x] 2.5 Ghi kết quả 3 sets vào dashboard `.vmlu` (commit `6006fae`): card MC-9 mới + hash `87f63017…`; `gold_sets={valid 540/744=72.58%, dev 229/303=75.58%, all_gold 768/1047=73.35%}` recompute từ source+checkpoint (0 mismatch); all_gold giữ primary explorer block; blob parse OK (tsc + node), các key khác nguyên vẹn

## Phase 3 — V-Bench retry 14 rows lỗi (986/1000 agentic)

- [x] 3.1 Direct retry: `run_vbench_eval.py --resume --retry-unparsed --model Qwen3.5-9B-28K` (14 re-asked, 5.127 kept verbatim; 96s, exit 0) → vẫn 986/1000 agentic, cùng 14 ids (2 hallucinated_arg + 1 no_call_shape + 5 off_enum + 4 truncated + 2 unknown_fn) — lỗi model thật, không phải parser drift
- [x] 3.2 Guided retry: `--resume --guided` (phỏng vấn đánh số, 173s, exit 0) → agentic **1000/1000**, `vbench_failures_*` đã xóa (không còn file); 14 guided rows giữ transcript trong `raw_response`, answer JSON hợp lệ, 0 empty
- [x] 3.3 Rebuild + verify: `vbench_valid_summary_*` đạt **5141/5141** (hash `87f63017…` = MC-9); `submission_vbench_Qwen3_5-9B-28K.jsonl` 5.141 dòng đã rebuild; guided là condition thứ 3 (transcript `Q[function]` trong raw_response)
- [ ] 3.4 Upload `submissions/Qwen3_5-9B-28K/submission_vbench_*.jsonl` lên vbench.ai, record server scores nếu có (`--record-server-scores`)

## Phase 4 — LegalSLM matrix trên Qwen3.5

- [x] 4.1 Format probe: multichoice `{question, choices[4, bare không prefix A-D], answer:int, answer_choice_letter}` — sha256 khớp manifest, order 1:1, letter↔index khớp 146/146; nli 150 `{legal_document, specific_question, question≡1 câu duy nhất, choices=[Có,Không], answer:0/1}` — KHÔNG phải MC A–E (binary entailment, cần prompt/scoring riêng); syllogism 144 `{question, answer:free-text 551–1819 chars}` — luận chứng sinh thành, không chấm chữ cái được; ViBidLQA_test 603 `{context, question, answer:free-text ngắn}` + không id — dạng reading, không phải MC. Quyết định: multichoice → MC runner qua adapter input (không sửa runner); 3 file còn lại DEFER (ghi lý do ở 4.3).
- [x] 4.2 Multichoice-146: adapter `/tmp/legal_q35_input/legal_multichoice_146.jsonl` (LG ids + choices prefix `A. ` + gold letter, sha source khớp manifest) → MC runner frozen (`--max-tokens 4`, Qwen3.5 non-thinking) 176s exit 0 → cross-check manifest-gold 146/146 + recompute khớp `accuracy_legal_*` → patch `.legal` = Qwen3.5/MC-10 (commit `21f869a`); outputs giữ tên `*_legal_*` để không đè MC-9 (all_gold restore từ `raw_result_1047`, 768/1047 nguyên vẹn)
- [x] 4.3 Các file còn lại: **DEFER cả ba, không adapter** — nli là binary entailment Có/Không (cần prompt/scoring riêng, ép vào runner A–E là sai phép đo); syllogism là luận chứng sinh thành 551–1819 chars (không chấm chữ cái được); ViBidLQA_test là reading có context + không id (thuộc pipeline `run_reading_eval`, không phải MC). Code fix: `build_dashboard_legal.py` thêm `--card/--max-tokens/--model-id` + caveat blank-aware (không còn hardcode MC-6/512/21-blank)
- [x] 4.4 Report: Qwen3.5 multichoice **128/146 = 87,67%** vs baseline luôn-A 91/146 = 62,33% (**+25,0đ**); valid 146/146 (0 blank — khác MC-6 21 blank do max_tokens 4 đủ cho non-thinking); by-gold A 82/91=90,11%, B 34/39=87,18%, C 12/16=75,00%. Cấm so ngang MC-6 (model + max_tokens khác).

## Phase 5 — Backend MongoDB + multi-model dashboard — ⏸️ DEFERRED (user 2026-09-20)

> Lý do: không có MongoDB server local (chỉ docker images mongo:7/8 chưa chạy), uploads Phase 6 cần user thao tác web thủ công — ưu tiên đóng submits trước, backend thành follow-up change riêng. Spec `results-backend/spec.md` giữ nguyên cho change sau.

- [ ] 5.1 Schema: collections `runs` (model, dataset, condition, config, measurement_card_hash, n, created_at) / `mc_items` / `reading_items` / `vbench_items` (run_id, item_id, answer, gold, correct/score, raw_response; index `(run_id, item_id)`) / `summaries` (số tính sẵn cho frontend) / `models` (params, quantization, endpoint) — xem design D6
- [ ] 5.2 Migration script: import toàn bộ CSV hiện có (`all_res/**/`, `data/gold/`) + verify row-counts khớp nguồn; summaries mang `measurement_card_hash`
- [ ] 5.3 API routes: `web/app/api/results/*` (runs list/detail, summaries, per-item query) + DB client trong `web/lib/` (mongo driver thêm vào `web/` only, Python deps không đổi)
- [ ] 5.4 Dashboard cutover: blob `benchmark-data.json` thành view đọc từ DB + multi-model compare (Qwen3.5 vs qwen38-nothink tối thiểu); old blob path giữ xanh đến khi verify row-for-row
- [ ] 5.5 Tests: unit cho migration row-counts + API shape (offline, tempdirs/mock như suite hiện tại); CI gate không đổi (ruff F,B,E9 + bandit + parity + unittest)

## Phase 6 — Submit

- [ ] 6.1 Upload `submission_vmlu_test_Qwen3_5-9B-28K.csv` lên vmlu.ai (UTF-8, `id,answer` chữ hoa), record leaderboard score về docs
- [ ] 6.2 Upload `submission_vbench_Qwen3_5-9B-28K.jsonl` lên vbench.ai, record server-side scores (`--record-server-scores`)
- [ ] 6.3 Reading/Legal gold nội bộ — không submit, chỉ hiển thị dashboard; đóng change (archive openspec)
