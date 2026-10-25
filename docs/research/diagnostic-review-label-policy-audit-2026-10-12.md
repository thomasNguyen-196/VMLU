# Đối chiếu chính sách nhãn diagnostic với bài báo và OpenSpec

Ngày kiểm tra: 2026-10-12. Phạm vi: yêu cầu mỗi review hoàn tất phải có ít nhất một nhãn lỗi trong `diagnostic-protocol-ledger-pilot`. Đây là bản audit trước triển khai; các số dòng ở mục 2 mô tả trạng thái lúc phát hiện vấn đề. Sau audit, annotation revision 2 đã được triển khai theo OpenSpec: xem `diagnostic-v1-rubric.md`, `diagnostic-v1-protocol.md` và `all_res/diagnostic_v1/pilot-review-v2/migration-verification.json`. Nhãn người duyệt thực tế vẫn chưa được tạo.

## Kết luận

Không có cơ sở trong ba công trình chính của kế hoạch để buộc mọi observation, kể cả đáp án đúng và không có vấn đề được quan sát, phải mang một nhãn lỗi. Quy tắc này xuất phát từ thiết kế annotation của OpenSpec và được triển khai nhất quán xuống rubric, Python importer, điều kiện hoàn tất UI và CSV exporter. Vì vậy, đây là thiếu sót trong thiết kế domain/schema, không chỉ là lỗi frontend.

Không nên thay quy tắc đó bằng `semantic_correctness == correct` thì tự động kết luận không có vấn đề. Đáp án đúng vẫn có thể đi cùng vấn đề gold/scorer hoặc vấn đề thành phần đã có trace. Cần tách kết quả ngữ nghĩa, vấn đề được quan sát, nguyên nhân lỗi và hành động can thiệp.

## 1. Đúng các nguồn đã dùng trong kế hoạch

Đã fetch trang [VMLU — Kế hoạch Diagnostic Track & Gap Detector](https://app.notion.com/p/3f77470dbce28103b4c6f64bdb190a4f). Trang nêu PRISM cho taxonomy/controlled diagnostics, RAGChecker cho evidence và generator, Adaptive-RAG cho supervision/routing. Kế hoạch cũng yêu cầu ledger giữ cả câu đúng và sai để đo regression. Trạng thái triển khai trên trang là trạng thái của bản kế hoạch, không dùng để xác nhận trạng thái code hiện nay.

### PRISM

Nguồn: [paper ACL 2026](https://aclanthology.org/2026.acl-long.1551.pdf), [repo tác giả](https://github.com/Kzczc/ACL2026-PRISM); đã đối chiếu bản `prism.pdf` trong repo (arXiv v2) và bản ACL chính thức. Các phiên bản có cập nhật nội dung; kết luận ở đây dựa trên nguyên tắc xây benchmark và chấm response, không dựa vào số lượng của từng subtask.

- §2 xây các tập bài kiểm tra theo chiều KE/KM/RE/IFE và kiểm soát thông tin/điều kiện để khảo sát từng chiều.
- §3.1 đánh giá kết quả của model bằng accuracy với bài có đáp án xác định và evaluator với bài mở; báo cáo hallucination rate/H-Score.
- Nhóm của một bài kiểm tra là chiều năng lực được khảo sát. Một bài thuộc reasoning không có nghĩa model đã mắc reasoning error khi trả lời đúng bài đó.

Hệ quả cho VMLU: học nguyên tắc kiểm soát phép thử và tách chiều năng lực khỏi kết quả. Không biến tên dataset hoặc task dimension thành một lỗi bắt buộc trên mọi response. PRISM cũng không cung cấp một phép gán nguyên nhân chắc chắn cho mọi output VMLU hiện có.

### RAGChecker

Nguồn: [paper, §3.2–3.3](https://arxiv.org/html/2408.08067v1), [repo tác giả](https://github.com/amazon-science/RAGChecker).

§3.2 phân biệt correct, incorrect và missing claims. §3.3.1 đo correctness/completeness qua precision/recall; §3.3.3 phân tích các nhóm claim sai, đồng thời phân tích claim đúng và cách chúng liên hệ với context. Faithfulness và correctness là hai phép đánh giá riêng.

Hệ quả cho VMLU: không bắt một response đúng phải có claim sai. Tuy nhiên, output đúng không tự chứng minh retrieval tốt hoặc tất cả nội dung đều grounded. Muốn gán một vấn đề thành phần cần đúng artifact/trace; pilot answer-only hiện nay chưa có trace retrieval để gán nhãn đó tự động.

### Adaptive-RAG

Nguồn: [paper, §3.2 Training Strategy](https://arxiv.org/html/2403.14403v2), [repo tác giả](https://github.com/starsuzi/Adaptive-RAG).

Nếu no-retrieval trả lời đúng, supervision chọn A. Nếu no-retrieval sai nhưng single-step và multi-step đều đúng, ưu tiên B vì chiến lược đơn giản hơn. Khi các chiến lược đều thất bại, bài báo có bước fallback dựa trên inductive bias của dataset.

Hệ quả cho VMLU: supervision routing biểu diễn chiến lược nào đáp ứng câu hỏi, bao gồm lựa chọn không tăng cường retrieval; đó không phải taxonomy nguyên nhân lỗi. Không sao chép fallback theo dataset để tạo nhãn nguyên nhân trong VMLU, vì proposal của VMLU cấm suy nguyên nhân chỉ từ dataset/lexical score. Một baseline đúng trên một observation cũng chưa đủ để khẳng định action `direct` là tốt nhất và ổn định dưới ngân sách; cần kết quả các arm theo thiết kế đã đăng ký.

Các kết luận ứng dụng trên là tổng hợp cho dự án, không phải một annotation schema được ba bài báo đề xuất chung.

## 2. Đối chiếu OpenSpec và code hiện tại

| Artifact | Nội dung đã kiểm tra | Nhận định |
| --- | --- | --- |
| `proposal.md`, What Changes | Ledger giữ correct, incorrect và execution failures; failure view riêng | Đúng mục tiêu và phù hợp kế hoạch |
| `specs/diagnostic-ledger/spec.md`, Complete observation accounting | Giữ mọi expected observation và trạng thái missing/error | Không được coi mọi observation là một failure |
| `specs/diagnostic-pilot-audit/spec.md`, Deterministic pilot item selection | Pilot giữ cả đúng/sai; EM/F1 disagreement chưa phải semantic error | Cần biểu diễn success được review |
| `design.md:39` | 6 correct + 6 incorrect ở MC/NLI; 6 EM + 6 non-EM ở reading | Success/control rows là thành phần chủ đích |
| `design.md:49–51` | Empty means unreviewed; review hoàn tất cần diagnostic label hoặc unresolved attribution | Thiếu trạng thái đã review nhưng không phát hiện vấn đề |
| `specs/diagnostic-protocol/spec.md`, Evidence-aware diagnostic taxonomy | Các loại gap và mixed/unknown; yêu cầu evidence | Không có no-observed-issue outcome; spec không trực tiếp bắt một nhãn trên mọi row, nhưng chưa bảo vệ trường hợp này |
| `docs/research/diagnostic-v1-rubric.md:87–108` | Unknown là chưa phân biệt được nguyên nhân; label yêu cầu một hoặc nhiều | Unknown không thay thế được no issue |
| `code_benchmark/diagnostic.py:918–920` | Review có trường được điền nhưng thiếu labels bị từ chối | Quy tắc có mặt ở importer |
| `web/lib/diagnostic-review.ts:64–65` | Completion yêu cầu `diagnostic_labels.length` | UI thực hiện cùng quy tắc |
| `web/lib/diagnostic-review.ts:80–90` | Row không complete được export với các judgments trống | Một reviewer đã chấm đúng/no issue có thể bị xuất thành unreviewed |

Điểm phát sinh chính là `design.md:51`. Frontend và importer đã triển khai quy tắc đó; sửa mỗi UI sẽ làm CSV không nhập được. OpenSpec không phải nguồn chứng minh quy tắc hợp lý: bản design cũng cần được sửa theo audit phương pháp.

## 3. Chính sách annotation đề xuất

Thêm một trường outcome riêng, tên đề xuất `diagnostic_outcome`. Đây là lựa chọn thiết kế của VMLU, không phải enum lấy nguyên từ paper.

| Outcome | Ý nghĩa | Diagnostic labels |
| --- | --- | --- |
| `no_observed_issue` | Đã review và không phát hiện vấn đề trong phạm vi artifact/phép đánh giá hiện có | `[]` hợp lệ; outcome phải được chọn rõ ràng |
| `issue_observed` | Có vấn đề cụ thể được quan sát | Một hoặc nhiều nhãn phù hợp; `unknown` nếu có vấn đề nhưng chưa phân biệt được nguyên nhân |
| `unresolved` | Chưa đủ bằng chứng để kết luận có vấn đề hay không | Không ép gán nguyên nhân; lưu rationale và phần thiếu bằng chứng |

`review_status` tiếp tục thể hiện tiến độ reviewed/deferred. Row chưa review được xác định bằng trạng thái và judgments chưa điền, không bằng việc riêng mảng labels có rỗng hay không.

### Những trường hợp cần được biểu diễn

1. Answer đúng, gold hợp lệ, không có vấn đề khác: `correct` + `no_observed_issue` + `[]`; vẫn hoàn tất review sau khi đủ các trường evidence/rationale/attestation theo rule mới.
2. Answer sai, đủ bằng chứng cho lỗi đọc hiểu: `incorrect` + `issue_observed` + `reading_representation_instruction_gap`; mức evidence phụ thuộc corroboration.
3. Answer sai nhưng chưa rõ knowledge/reasoning/harness: `incorrect` + `issue_observed` + `unknown`; ghi rõ các giả thuyết chưa phân biệt được.
4. Answer đúng về nghĩa nhưng scorer/gold có bất đồng đã được xác minh: `correct` + `issue_observed` + `measurement_reliability_gap`; không hồi tố sửa điểm gốc.
5. Gold hoặc nghĩa câu trả lời chưa xác định: `uncertain`/gold suspect + `unresolved`, deferred khi chưa đủ điều kiện giám sát cho can thiệp sau này.
6. Chưa review: judgments/outcome/status vẫn chưa điền; không tự gán `unknown` hay `no_observed_issue`.

Không tự suy outcome từ EM/F1, semantic correctness hoặc dataset. `No observed issue` chỉ là kết luận trong phạm vi review hiện tại, không chứng minh model không có latent knowledge/reasoning gap. Giữ action label chưa được gán cho tới khi có intervention evidence theo protocol.

## 4. Tác động đến mục tiêu Gap Detector

Nếu mọi row bị ép mang nhãn lỗi, các success controls không thể tạo nhóm không phát hiện vấn đề. Nếu dùng unknown để lấp chỗ trống, nhóm này trộn success với failure chưa rõ nguyên nhân. Điều đó làm méo supervision chẩn đoán và khó đánh giá false positive khi phát triển detector. Đây là hệ quả thiết kế suy ra, chưa phải một số đo trên pilot.

Pilot 60 câu vẫn là mẫu có chủ đích; có thêm no-issue outcome không biến tỷ lệ nhãn trong pilot thành prevalence toàn benchmark. Cần giữ success rows cho regression và đánh giá policy, như kế hoạch ban đầu.

## 5. Thứ tự sửa được khuyến nghị

1. Sửa design và delta specs của change: explicit no-issue outcome, unknown cause, unresolved assessment, completion và export semantics.
2. Version review schema/rubric và revision/hash protocol; sửa importer, audit/adjudication logic, UI và CSV serializer đồng bộ.
3. Chuẩn bị snapshot review mới với cùng item IDs, source outputs, scores và selection đã khóa; không lấy mẫu lại hoặc ghi đè snapshot khác hash.
4. Giữ bản draft/review cũ; chỉ migrate trường có quy tắc rõ ràng. Không suy unknown thành no issue thay người review.
5. Kiểm chứng các trường hợp ở mục 3 bằng offline Python/Bun fixtures, export→import parity, old-version/hash rejection và browser review flow. Không sử dụng fixture làm nhãn người duyệt thực tế.

MC-72 và các metric/scorer lịch sử không thuộc revision này. Source condition, raw response, gold, scores và mẫu số vẫn là baseline của phép đo. Chỉ annotation contract thay đổi.

## 6. Giới hạn và việc chưa làm

- Khi nghiên cứu: đã đối chiếu ba nguồn chính trong plan và OpenSpec. Sau đó đã triển khai revision 2; kiểm thử diagnostic Python 21/21, Bun 11/11 và export/import fixture đều pass. Các gate toàn repo còn lỗi ngoài phạm vi như ghi trong tasks.md.
- Các paper không quyết định hộ VMLU tên field/enum hoặc rule review completion; schema ở mục 3 là đề xuất cần được ghi thành revision.
- Không có dữ liệu mới về tri thức nội tại, không có model calls và không có nhãn human audit được tạo.
- Bước tiếp theo: người duyệt thực tế tiếp tục audit trên `/diagnostic` với kết luận chẩn đoán revision 2; giữ các gate human review/adjudication pending tới khi có dữ liệu thật.
