# Diagnostic protocol v1 · annotation revision 4

Protocol: `vmlu-diagnostic-v1` · SHA256 `44fc2ea0f51954628e7a2d2716f3e468f7f68fcea8df9481679dd69b603aec0f` · `diagnostic-review-v4` · `diagnostic-rubric-v3`.

## Phạm vi và ba gate
Đo thiếu hụt và khả năng phục hồi trên tác vụ tiếng Việt. Không tự suy thành thiếu hụt do ngôn ngữ hoặc tri thức riêng Việt Nam. Đối chiếu ngôn ngữ cần task variant mới và bản dịch được kiểm tra.
`preparation_ready` là công cụ/packet offline; `audit_complete` là quy trình review/adjudication thật; `inference_ready` cần protocol prospective đã preregister đầy đủ. Chưa chạy inference từ module này.

## Audit đáp án và giả thuyết nguyên nhân
Bỏ trường Observation/Supported chung. Semantic correctness, gold validity và diagnostic outcome là phán đoán audit. `audit_evidence_kind` + `evidence_reference` ghi bằng chứng cho audit. `input_evidence_sufficiency` xét input model nhận; `corpus_evidence_availability` + tham chiếu riêng xét corpus được kiểm tra, không suy từ input.
`observed_issues` mô tả điều thấy trong artifact; `diagnostic_labels` là giả thuyết tùy chọn. Nguyên nhân chưa rõ có tập giả thuyết rỗng, không ép unknown; mixed được suy từ nhiều giả thuyết.
Mỗi giả thuyết có `diagnostic_support` riêng: hypothesis hoặc contrast_supported, tham chiếu và contrast_id. Human review/AI confidence không nâng cấp giả thuyết. contrast_supported chỉ được import khi contrast/replay đã đăng ký, khớp item/label và hash artifact được xác minh. Không phát hiện vấn đề có tập issue/cause rỗng, không phải chọn mức bằng chứng nguyên nhân.

## Review và provenance
Primary-60 có AI proposals trong draft riêng, không tự ký hoặc đặt trạng thái. Independent-15 không tải AI suggestions; cần human_only và blind self-attestation, reviewer khác primary. Báo cáo agreement ghi rõ AI-assisted-primary versus blind-human hay human-only-primary versus blind-human. ID browser là tự khai báo, không xác minh danh tính.
No-issue controls được giữ làm negative/control data riêng. Deferred/suspect/conflicting judgments không tạo causal supervision. Eligibility theo từng label: input thiếu không loại external_evidence_gap; reasoning cần đủ premises; retrieval cần corpus có evidence. Một adjudication 'resolved' không tự tạo nhãn huấn luyện mới.

## Prospective experiment trước khi inference
Historical B chỉ là audit anchor. Chạy B mới trong cùng campaign và model/control với S/K/KS. Tách đối chiếu cô lập nguyên nhân khỏi so sánh pipeline deployment. Khóa content/length/position controls; prompt/tool/compute controls; corpus; group splits; budget; replicate pairing; stability và verifier policy trước khi chạy.
Router dự đoán quality/cost để chọn arm; causal diagnosis là phân tích offline riêng. Đăng ký threshold, tie-break theo cost/latency và all-arm-failure/abstain; không ép action khi không arm thành công. 60*4*3 = 720 arm attempts, có thể nhiều hơn 720 model calls. Ba lần lặp chỉ là pilot; không tự chứng minh ổn định.
Verification phải nêu grounding/calculation/format scope, đánh giá false-accept/reject và coverage/abstention, tính tất cả chi phí probe/retrieval/tools/retries/verification; offline grading có thể dùng gold, runtime verifier không được dùng gold.

## Revision và vận hành
Giữ v1/v2/v3 snapshots, draft keys và human records. Revision 4 giữ 60 ordered anchors và 15 keys; không tự chuyển outcome/attestation cũ. Zustand store mới riêng v4; draft cũ của cùng reviewer/scope có thể tải để review lại.

```bash
.venv/bin/python code_benchmark/diagnostic.py revise-pilot-review --source-dir all_res/diagnostic_v1/pilot-review-v3 --output-dir all_res/diagnostic_v1/pilot-review-v4
.venv/bin/python code_benchmark/diagnostic.py import-review --pilot-dir all_res/diagnostic_v1/pilot-review-v4 --file <review-v4.csv> --annotator <reviewer-id>
```

Scorer, gold, prompt, denominators và source condition lịch sử bất biến. Corpus/endpoint/budget/splits/stability/verifier chưa chốt vẫn là blocker; không tạo con số bằng cách đoán.
