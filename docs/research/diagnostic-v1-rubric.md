# Diagnostic annotation rubric v3 · review revision 4

Audit đáp án dùng evidence kind/reference; giả thuyết nguyên nhân dùng support riêng. Observation/Supported không còn là dropdown chung.

## Biểu hiện quan sát
- `answer_mismatch`: Đáp án không phù hợp câu hỏi/nguồn
- `factual_conflict`: Claim mâu thuẫn nguồn
- `calculation_error`: Kết quả tính toán sai
- `wrong_entity_relation`: Sai thực thể/quan hệ/phạm vi
- `instruction_violation`: Vi phạm yêu cầu/định dạng
- `missing_input_evidence`: Input thiếu dữ kiện cần thiết
- `retrieval_miss`: Trace retrieval không lấy được evidence
- `context_assembly_issue`: Evidence bị mất khi ghép context
- `parser_mismatch`: Raw output khác prediction đã parse
- `output_truncation`: Output bị cắt
- `gold_metric_issue`: Vấn đề gold/metric
- `run_variation`: Kết quả biến động giữa lần chạy
- `other`: Vấn đề khác được mô tả

## Giả thuyết nguyên nhân
### external_evidence_gap
Input lacks necessary information; this does not assert missing parametric knowledge.
**Contrast support requires:** Contrast or reviewed deterministic evidence-sufficiency replay establishes input deficiency; input may be insufficient.
Human signoff and confidence do not establish controlled attribution.

### parametric_knowledge_gap
The tested model fails a controlled parametric-knowledge probe.
**Contrast support requires:** Closed-book/evidence controls distinguish contextual deficiency and reading/reasoning alternatives; recovery alone is insufficient.
Human signoff and confidence do not establish controlled attribution.

### parametric_knowledge_error
A persistent factual conflict is hypothesized in parametric knowledge.
**Contrast support requires:** Verified dated source plus controlled probes; a wrong output alone establishes a factual error, not its internal origin.
Human signoff and confidence do not establish controlled attribution.

### reasoning_gap
Necessary premises are present but combining/calculation fails.
**Contrast support requires:** Verified premises and a matched reasoning/tool contrast; calculator effects remain distinct from prompt effects.
Human signoff and confidence do not establish controlled attribution.

### reading_representation_gap
Interpretation of entity, relation, scope or negation is hypothesized to fail.
**Contrast support requires:** Matched representation/reading contrast with unchanged required facts.
Human signoff and confidence do not establish controlled attribution.

### instruction_gap
An explicit output/task constraint is violated.
**Contrast support requires:** Matched instruction contrast; raw violation is descriptive evidence only.
Human signoff and confidence do not establish controlled attribution.

### retrieval_gap
A versioned corpus contains relevant evidence but the retriever misses it.
**Contrast support requires:** Corpus evidence availability, retrieval trace and reviewed matched/oracle contrast.
Human signoff and confidence do not establish controlled attribution.

### context_assembly_gap
Relevant retrieved evidence is lost, truncated or misplaced during assembly.
**Contrast support requires:** Retrieval-to-input trace and controlled assembly contrast or deterministic replay.
Human signoff and confidence do not establish controlled attribution.

### generator_evidence_use_gap
Supplied relevant evidence is not used correctly by the generator.
**Contrast support requires:** Matched context-use contrast; do not classify as a retriever failure.
Human signoff and confidence do not establish controlled attribution.

### harness_gap
Scaffold, tool interface or cap changes the response.
**Contrast support requires:** Same-model/item matched harness contrast with explicit controls.
Human signoff and confidence do not establish controlled attribution.

### parser_gap
Raw output and parsed prediction differ in a way that changes scoring.
**Contrast support requires:** Hash-linked deterministic parser replay or matched parser contrast; do not alter frozen source scores.
Human signoff and confidence do not establish controlled attribution.

### measurement_gap
Gold or metric representation causes a misleading correctness measurement.
**Contrast support requires:** Reviewed references and hash-linked deterministic scoring/gold comparison; source scores remain intact.
Human signoff and confidence do not establish controlled attribution.

### run_instability
Repeated same-condition outputs produce inconsistent outcomes.
**Contrast support requires:** Registered same-condition repetitions and declared stability criterion; one output is insufficient.
Human signoff and confidence do not establish controlled attribution.

## Hướng dẫn quyết định

- No observed issue: correct, gold valid, bằng chứng audit cụ thể; issue/cause/support rỗng. Không suy model không có latent gaps.
- Issue observed: ít nhất một biểu hiện; có thể chưa có giả thuyết nguyên nhân. Mỗi giả thuyết có reference riêng, mặc định hypothesis.
- Unresolved: deferred, giải thích bằng chứng thiếu/xung đột, không ép nhãn.
- Input sufficiency và corpus availability khác nhau; corpus present/absent cần tham chiếu corpus riêng.
- contrast_supported cần matching registered contrast, reviewed controls và hash artifact, không suy từ human signoff hoặc độ tự tin AI.
- Reference nên ghi chính xác đoạn/câu hoặc phép tính; không xem prediction/gold match đơn thuần là causal evidence.
