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
- [ ] 2.4 Rebuild test submission: `--submission-only`-tương đương cho MC (rebuild `submissions/Qwen3_5-9B-28K/submission_vmlu_test_*.csv` từ checkpoint mới nhất, schema `id,answer` chữ hoa) — sẵn sàng upload vmlu.ai
- [ ] 2.5 Ghi kết quả 3 sets vào dashboard `.vmlu` (mở rộng blob hoặc ghi chú multi-file cho Phase 5 dùng)

## Phase 3 — V-Bench retry 14 rows lỗi (986/1000 agentic)

- [ ] 3.1 Direct retry: `run_vbench_eval.py --resume --retry-unparsed --model Qwen3.5-9B-28K` (chỉ re-call rows unparsed dưới parser hiện tại; đáp án đúng của model không bao giờ bị chạm) → đếm failures còn lại
- [ ] 3.2 Guided retry cho rows còn lỗi: `--resume --guided` (phỏng vấn đánh số; transcript nằm trong `raw_response`; `load_checkpoint` KHÔNG re-derive guided rows) → target `vbench_failures_*` rỗng/bị xóa
- [ ] 3.3 Rebuild + verify: `--submission-only` → jsonl mới; `vbench_valid_summary_*` đạt 1000/1000 agentic (hoặc liệt kê rows bất trị + diagnosis); label guided là condition thứ 3 trong mọi báo cáo
- [ ] 3.4 Upload `submissions/Qwen3_5-9B-28K/submission_vbench_*.jsonl` lên vbench.ai, record server scores nếu có (`--record-server-scores`)

## Phase 4 — LegalSLM matrix trên Qwen3.5

- [ ] 4.1 Format probe: đọc 1 dòng mỗi file `v_legal_slsp/legal_slm/{nli,syllogism}.jsonl` + `v_legal_slsp/bidlqa/ViBidLQA_test.jsonl`, liệt kê keys; quyết định adapter-vs-defer cho từng file (runner MC giữ nguyên, chỉ nhận `{id, question, choices[], answer}`)
- [ ] 4.2 Multichoice-146: chạy MC runner với manifest `data/legal_slm_multichoice_manifest.json` → cross-check manifest-gold như `build_dashboard_legal.py` (recompute accuracy vs `accuracy_*`, majority baseline recompute không hardcode) → patch `.legal` cho Qwen3.5
- [ ] 4.3 Các file còn lại theo kết quả probe: viết adapter nhỏ (không sửa runner) hoặc ghi explicit defer + lý do
- [ ] 4.4 Report: accuracy multichoice + baseline so sánh (MC-6 trước đó trên `qwen38-nothink`: 121/146 = 82.88% vs baseline 62.33%)

## Phase 5 — Backend MongoDB + multi-model dashboard

- [ ] 5.1 Schema: collections `runs` (model, dataset, condition, config, measurement_card_hash, n, created_at) / `mc_items` / `reading_items` / `vbench_items` (run_id, item_id, answer, gold, correct/score, raw_response; index `(run_id, item_id)`) / `summaries` (số tính sẵn cho frontend) / `models` (params, quantization, endpoint) — xem design D6
- [ ] 5.2 Migration script: import toàn bộ CSV hiện có (`all_res/**/`, `data/gold/`) + verify row-counts khớp nguồn; summaries mang `measurement_card_hash`
- [ ] 5.3 API routes: `web/app/api/results/*` (runs list/detail, summaries, per-item query) + DB client trong `web/lib/` (mongo driver thêm vào `web/` only, Python deps không đổi)
- [ ] 5.4 Dashboard cutover: blob `benchmark-data.json` thành view đọc từ DB + multi-model compare (Qwen3.5 vs qwen38-nothink tối thiểu); old blob path giữ xanh đến khi verify row-for-row
- [ ] 5.5 Tests: unit cho migration row-counts + API shape (offline, tempdirs/mock như suite hiện tại); CI gate không đổi (ruff F,B,E9 + bandit + parity + unittest)

## Phase 6 — Submit

- [ ] 6.1 Upload `submission_vmlu_test_Qwen3_5-9B-28K.csv` lên vmlu.ai (UTF-8, `id,answer` chữ hoa), record leaderboard score về docs
- [ ] 6.2 Upload `submission_vbench_Qwen3_5-9B-28K.jsonl` lên vbench.ai, record server-side scores (`--record-server-scores`)
- [ ] 6.3 Reading/Legal gold nội bộ — không submit, chỉ hiển thị dashboard; đóng change (archive openspec)
