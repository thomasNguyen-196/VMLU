# Kế hoạch benchmark tiếng Việt với nhiều model

Cập nhật: 2026-10-06. Trạng thái: protocol v1 và runner đã được chuẩn bị; cần xác minh endpoint/rate trước pilot, rồi chốt ngân sách chính từ pilot.

## Mục lục

- [Mục tiêu và quyết định đã chốt](#mục-tiêu-và-quyết-định-đã-chốt)
- [Bộ đo đề xuất](#bộ-đo-đề-xuất)
- [Protocol và thước đo](#protocol-và-thước-đo)
- [Các bước thực hiện](#các-bước-thực-hiện)
- [Vận hành runner](#vận-hành-runner)
- [Bảng đầu ra](#bảng-đầu-ra)
- [Việc cần xác minh khi triển khai](#việc-cần-xác-minh-khi-triển-khai)
- [Nguồn](#nguồn)

## Mục tiêu và quyết định đã chốt

Mục tiêu nghiên cứu là thu thập bằng chứng về khả năng trả lời đúng, đọc hiểu và suy luận trên các nhóm bài tiếng Việt được công bố. Kết luận trong luận văn phải gắn với bộ dữ liệu, gold, metric và điều kiện suy luận đã dùng. Kiến thức trắc nghiệm, đọc theo đoạn văn và suy luận số học cung cấp các loại bằng chứng khác nhau.

| Quyết định | Trạng thái |
| --- | --- |
| Các cột chính là nhóm bài/lĩnh vực | Đã chốt ở Q1 |
| Bảng phục vụ luận văn/báo cáo nghiên cứu | Đã chốt ở Q2 |
| Chạy pilot 100–200 câu/model trước khi chốt chi phí chạy chính | Đã chốt ở Q3 |
| Bốn model đợt đầu | Muse Spark 1.3 Contributor, MiMo V2.6 Flash, MiMo V2.5, Qwen3.5-9B-65K; kiểm tra quyền truy cập trước khi chạy |
| Bộ gold đọc hiểu | Người dùng xác nhận đã chấm toàn bộ 400 câu; dùng bộ đã hiệu đính hiện có |
| Đường gọi | OMP một lượt/item, không tools, system prompt tối giản; cùng wrapper cho mọi model |
| Cách chấm chính | EM giữ dấu + token-F1; lưu điểm scorer cũ để đối chiếu |
| Chính sách reasoning | Cho phép reasoning; chốt budget theo nhóm bài sau pilot; chấm câu trả lời cuối |

Thuật ngữ được ghi tại [CONTEXT.md](../../CONTEXT.md).

## Bộ đo đề xuất

Các số dưới đây là kiểm kê dữ liệu trong repo, chưa phải kết quả cho model mới.

| Nhóm bài | Cột của bảng chính | Mẫu chính đề xuất | Nguồn đáp án hiện có | Metric đề xuất |
| --- | --- | ---: | --- | --- |
| Kiến thức đa lĩnh vực | VMLU valid | 744 | Gold chữ cái | Accuracy |
| Đọc hiểu theo đoạn văn | Vi-SQuAD | 200 | Gold đã được người dùng chấm đủ, có nguồn gốc hiệu đính từ output cũ | EM giữ dấu / token-F1 |
| Suy luận theo đoạn văn | Vi-DROP | 200 | Cùng bộ gold400 đã được chấm | EM giữ dấu / token-F1; kiểm tra số và đơn vị |
| Kiến thức pháp luật | Legal MC | 146 | Gold chữ cái | Accuracy |
| Quan hệ suy diễn pháp luật | Legal NLI | 150 | Gold nhị phân, 75/75 | Accuracy |
| Đọc hiểu nghiệp vụ đấu thầu | ViBidLQA test | 603 | Gold nguồn | EM / token-F1 |

Phương án này có **2.043 item/model** cho đợt chính. Với bốn model đã chọn, có **8.172 lượt trả lời** trước retry hoặc các condition bổ sung. Đây là quy mô dự kiến, còn ngân sách được tính từ pilot.

Phân chia pilot và đánh giá chính:

- VMLU: lấy pilot từ dev303, loại câu hỏi trùng với valid744. Có ba chuỗi câu hỏi trùng giữa hai split, nên chỉ dựa vào ID là chưa đủ.
- ViBidLQA: lấy pilot từ val482 hoặc train1928, loại cả câu hỏi và đoạn văn trùng với test603. Repo có 240 hàng val đáp ứng điều kiện tách này.
- Vi-SQuAD/Vi-DROP: giữ đủ 400 câu cho đánh giá chính. Pilot tích hợp đọc hiểu ban đầu dùng ViBidLQA-val với gold nguồn và cùng dạng prompt đọc theo đoạn văn, tránh dùng 400 câu để tinh chỉnh. Chỉ thêm pilot ngoài manifest400 nếu cần khảo sát riêng các dạng suy luận và có gold cho những câu mới đó.
- Legal MC/NLI: không có dev độc lập trong dữ liệu local. Dùng VMLU-dev để kiểm tra API và định dạng trắc nghiệm; giữ toàn bộ 146/150 câu cho đánh giá cuối, không tinh chỉnh prompt trên chúng.
- Lưu pilot trong manifest riêng. Giữ nguyên các item đã đăng ký của reading400 và tạo phiên bản gold mới song song với reference lịch sử.

V-Bench là nhánh mở rộng sau khi hoàn thành bảng cốt lõi. Có 4.141 MC và 1.000 agentic được server chấm; 9.141 là số hàng nguồn, gồm 4.000 hàng không có gold. VM14K cũng là mở rộng, cần xử lý chất lượng dữ liệu và số lựa chọn trước khi dùng.

## Protocol và thước đo

### Tham chiếu đã được hiệu đính

Người dùng xác nhận đã chấm đủ 400 câu. Kiểm kê repo cũng ghi nhận gold có đủ 400 hàng: 321 câu chấp nhận và 79 câu hiệu đính từ output của model cũ. Vì vậy kế hoạch dùng bộ gold đã có, không yêu cầu chấm lại toàn bộ.

Nguồn gốc này vẫn cần ghi trong measurement card. Một đáp án đúng được chấp nhận theo cách diễn đạt của model cũ có thể làm EM nhạy với cách diễn đạt khi model mới trả lời. Pilot kiểm tra quy tắc đáp án cuối, các đáp án tương đương và đơn vị số; việc này kiểm tra cách chấm, không phủ nhận 400 lượt review đã hoàn thành.

Giữ nguyên item set, gold và lịch sử chấm hiện tại. Nếu phát hiện lỗi gold hoặc cần bổ sung đáp án tương đương được xác minh từ đoạn văn, lưu phiên bản mới trước khi đóng băng đợt chính. Không âm thầm thay reference sau khi xem bảng xếp hạng. Gold gốc không có trong source local, nên không mặc định tồn tại một nguồn độc lập để thay thế.

### Metric

- Trắc nghiệm: accuracy = số câu đúng / toàn bộ mẫu đăng ký. Output trống hoặc không trích được đáp án tính sai; lỗi hạ tầng chưa hoàn tất phải công bố coverage và xử lý trước khi coi ô là kết quả đầy đủ.
- EM mới: chuẩn hóa Unicode, khoảng trắng và dấu câu được chỉ định; giữ dấu tiếng Việt. Quy tắc số, phần trăm và đơn vị phải được kiểm tra với gold, không tự coi các đơn vị khác nhau là tương đương.
- F1 mới: dùng token theo khoảng trắng sau chuẩn hóa Unicode và khoảng trắng, giữ dấu; công bố rõ tokenization tiếng Việt này. Không gọi đây là word-F1 dựa trên tách từ.
- Vi-DROP: kiểm tra số, đơn vị và kiểu đáp án trong bộ gold đã chấm; không đoán cách tách nhiều span từ dấu phẩy của một reference. Đối chiếu metric tham khảo DROP trong các trường hợp thực sự có gold cấu trúc phù hợp. Bản thích ứng tiếng Việt có phiên bản riêng.
- Chấm scorer cũ trên cùng đáp án cuối đã trích để đối chiếu ảnh hưởng của metric, ghi rõ condition “legacy scorer / extracted final”. Điểm lịch sử chấm nguyên văn được giữ với condition cũ. Scorer hiện tại bỏ dấu cho EM, chấp nhận một số alias số/phần trăm và tính overlap đa tập ký tự cho F1.
- Output được lưu nguyên văn, đồng thời lưu câu trả lời cuối do parser đã chốt trích ra. Đo lỗi định dạng riêng để tránh đọc một khác biệt về độ dài câu trả lời thành khác biệt năng lực.
- Không lấy trung bình chung giữa accuracy, EM và F1. Mỗi cột giữ ý nghĩa của nhóm bài mình đo.

F1 là mức khớp bề mặt, nên bổ sung một mẫu kiểm tra đúng/sai do người chấm với tên model được ẩn. Mẫu này dùng để đánh giá sai lệch của metric, đặc biệt các trường hợp EM=0 nhưng nội dung có thể đúng hoặc F1 cao dù sai số/sai quan hệ.

### Điều kiện suy luận

Thiết kế ban đầu Q6 là API trực tiếp. Sau đó người dùng chọn chạy qua omp để dùng OpenCode Go. Protocol hiện tại vì vậy là một tiến trình omp cho mỗi item, không tools, không session cũ, không extensions/skills/rules/LSP và system prompt tối giản `Answer the user's question.` User prompt và thứ tự lựa chọn vẫn byte-identical giữa các model. Kết quả này được gắn condition omp; không gộp với điểm API thuần hoặc harness tool-menu lịch sử.

Các chi tiết cần chốt sau khi biết danh sách và API thực tế:

- Zero-shot chung cho tất cả model; hướng dẫn cùng định dạng đáp án cuối.
- Đã chốt Q8: cho phép reasoning, lấy ngân sách theo nhóm bài từ pilot, chấm đáp án cuối. Ghi cấu hình reasoning thực tế của từng provider. Các runner cũ dùng 4 token MC và 48 token reading; mức này có thể làm model có hidden reasoning hết ngân sách trước khi trả lời.
- Temperature/seed chỉ ghi là được ghim khi provider thực sự hỗ trợ và request/response xác nhận. Không dùng cùng nhãn reasoning effort để suy ra cùng lượng tính toán giữa các provider.
- Một ô trỏ đến một run/condition đã chọn trước; không lấy best-of nhiều prompt hoặc lần chạy để điền ô.
- Baseline có thể truy cập phải được chạy cùng protocol mới. Những output lịch sử có budget, prompt hoặc reasoning khác cần được gắn điều kiện riêng.
- Định danh run gồm protocol, model, provider/tier, condition và hashes; checkpoint không được resume sang condition khác của cùng model.

Muse Spark 1.3 Contributor, MiMo V2.6 Flash và MiMo V2.5 được gọi qua OpenCode Go bằng model refs `zen-go/...`; Qwen3.5-9B-65K giữ endpoint IEC nội bộ vì không có trong catalog Go. OpenCode Go liệt kê Go API endpoint, model IDs, giá usage-equivalent và quota riêng theo model. Pilot dùng cap $1 quota-equivalent/model, thấp hơn quota tháng công bố; đây là mức dùng subscription, không phải khoản pay-as-you-go cộng thêm. OMP cần `x-opencode-session` ổn định cho từng item, nên runner tạo ID xác định từ run key và ghi model ref/provider trong metadata. [OpenCode Go API, models, limits and privacy](https://opencode.ai/docs/go/).

OpenCode Go ghi Contributor prompts/completions được dùng để huấn luyện Meta và không có zero data retention; vùng khả dụng bị giới hạn. Người dùng đã chọn model Contributor trước khi chuyển transport. Go cũng định hướng traffic cho coding agents; condition này dùng OMP nhưng prompts là benchmark QA, nên cần công bố đúng condition khi diễn giải. [OpenCode Go privacy and use guidance](https://opencode.ai/docs/go/).

MiMo thinking bật mặc định; trong thinking mode temperature hiệu lực là 1.0 và completion cap gồm reasoning tokens. Profile gửi thinking enabled, bỏ temperature/seed và dùng `max_completion_tokens`. Go quota rates cho MiMo V2.6 Flash/V2.5 là $0.14 input / $0.28 output mỗi triệu token (cache read $0.0028); Muse Contributor là $0.10/$0.20 (cache read $0.002). Dùng cache-miss price cho dự toán trần. [OpenCode Go](https://opencode.ai/docs/go/), [MiMo model hyperparameters](https://mimo.mi.com/docs/en-US/api/guidance/model-hyperparameters).

### Độ tin cậy

- Mỗi ô chi tiết có số đúng/tổng số, coverage, số output trống/không parse được và CI95%.
- Các so sánh giữa model ghép trên cùng item. Với đọc hiểu, tính khoảng tin cậy theo cụm đoạn văn để tính đến nhiều câu cùng một đoạn.
- Chọn trước các cặp so sánh chính; xử lý việc kiểm định nhiều cặp nếu thực hiện kiểm định thống kê.
- VMLU có phân tích phụ theo bốn nhóm lớn và macro theo môn; số gold mỗi môn ít, nên tránh kết luận thứ hạng ở từng môn từ chênh lệch nhỏ.
- Legal MC có baseline majority 62,33%; NLI cân bằng có baseline 50%. Ghi các mốc này khi diễn giải accuracy.

## Các bước thực hiện

1. **Chốt thiết kế:** danh sách model, gold, metrics, reasoning/output policy, mẫu chính và các so sánh cần báo cáo; ghi measurement card/protocol trước khi đo.
2. **Chuẩn bị dữ liệu:** audit ID/câu hỏi/đoạn văn trùng, chia pilot tách khỏi mẫu cuối, kiểm tra bộ gold400 đã được chấm và ghi nguồn gốc/phiên bản.
3. **Chuẩn bị runner:** tái sử dụng transport và kernel hiện có; thêm metadata/provider handling và định danh condition cần thiết cho đợt mới. Dừng khi auth/params không đúng hoặc nguồn dữ liệu lệch.
4. **Pilot 100–200 câu/model:** kiểm tra output cuối, finish reason, truncation, token dùng cho reasoning, rate limit, độ trễ và metric qua mẫu human audit. Xuất dự toán token/chi phí/thời gian cho 2.043 item/model.
5. **Đóng băng và chạy chính:** giữ nguyên manifest, prompts, gold/scorer versions và settings; lưu raw output + per-item score + provenance, checkpoint riêng cho từng run.
6. **Tổng hợp và công bố:** tính CI/paired deltas, human audit đã định trước; đưa các ô đủ điều kiện vào cùng ma trận và xuất CSV, Markdown/LaTeX cùng dữ liệu chi tiết.

Runner dữ liệu tái sử dụng: `run_mc_eval.py`, `run_reading_eval.py`, `run_legal_arm_a.py`, `run_bidlqa_eval.py`; mỗi item được gọi qua omp với cùng user prompt.

Phương án pilot cụ thể: chọn 100 câu VMLU-dev + 80 câu ViBidLQA-val sau khi kiểm tra không trùng final, thêm 20 lượt lặp để đo dao động. Tổng 200 request/model, 800 request cho bốn model trước retry. Scorer tính accuracy/EM/F1 pilot trên 180 câu duy nhất; 20 lượt lặp có replicate identity riêng và chỉ dùng báo mức nhất quán, không cộng vào mẫu số điểm. Pilot này kiểm tra đường trắc nghiệm và đường đọc theo đoạn văn; điểm pilot không được dùng làm bảng xếp hạng chính. Nếu cần thêm probe suy luận số, dùng câu phát triển có đáp án xác minh riêng, trước khi mở mẫu cuối.

Kiểm tra offline trước khi đo: scorer mới với các trường hợp khác dấu, sai số/đơn vị, khoảng trắng, output rỗng, đáp án cuối và nhiều reference; hồi quy scorer/prompt/parser cũ; kiểm tra run identity, resume và lựa chọn ô matrix. Dùng các công cụ test của repo. Không gọi endpoint model trong CI.

Web hiện dùng Mongo registry và summaries theo một model. Ma trận mới tái sử dụng đường đọc summaries nhưng chọn explicit protocol/run IDs; không chọn ngầm run cuối của một dataset khi nhiều condition tồn tại. Model mới và MiMo V2.5 cũng cần được bổ sung vào registry/import plan trước khi hiển thị.

Hoàn thành khi mọi ô chính cùng phiên bản bộ đo, truy được về per-item output, công bố mẫu số và coverage, và sử dụng gold đã được xác nhận với nguồn gốc cùng giới hạn diễn giải công bố rõ.

## Vận hành runner

Manifest nằm tại `data/vi_multimodel_v1/{pilot,main}_v1.json`. Runner mặc định chỉ preflight, chưa gọi model. Pilot lưu raw output, checkpoint, token usage và thời gian tại `all_res/vi_multimodel_v1/pilot/<profile>/`; scorer ghi `scores.jsonl` và `summary.json` cạnh đó.

```bash
# Chỉ cần khi khởi tạo manifest pilot lần đầu.
.venv/bin/python code_benchmark/make_vi_multimodel_manifest.py --phase pilot

# Preflight đã đóng băng manifest; lặp lại cho từng profile.
.venv/bin/python code_benchmark/run_vi_multimodel_eval.py --phase pilot --profile muse-spark-1-3-contributor

# OpenCode Go lấy key từ auth.json hiện có hoặc OPENCODE_GO_API_KEY; run cap là quota-equivalent.
.venv/bin/python code_benchmark/run_vi_multimodel_eval.py --phase pilot \
  --profile muse-spark-1-3-contributor --execute --max-cost-usd 1
.venv/bin/python code_benchmark/score_vi_multimodel.py --phase pilot \
  --profile muse-spark-1-3-contributor
```

Runner đọc Go key từ `~/.local/share/opencode/auth.json` provider `opencode-go` hoặc `OPENCODE_GO_API_KEY`; base URL mặc định là `https://opencode.ai/zen/go/v1`. Qwen đọc `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`. `--max-cost-usd` là trần quota-equivalent cộng dồn cho probe, request và retry bằng `--resume`; resume phải dùng cùng cap và setting ban đầu. Mỗi run ghi usage-equivalent theo token, reserved upper bound dùng cache-miss rate và billing mode; OpenCode Go không bị ghi thành một khoản pay-as-you-go.

Sau pilot, chốt completion cap riêng cho MC và đọc hiểu, điền các card MC-53–MC-56, cập nhật `data/vi_multimodel_protocol_v1.json`, rồi tạo lại **chỉ manifest main** bằng `make_vi_multimodel_manifest.py --phase main --overwrite` trước bất kỳ request main nào. Runner từ chối cap còn trống; manifest builder từ chối ghi đè khi đã có output cho phase đó. Chấm đủ dataset main rồi import từng profile vào Mongo bằng `migrate_vi_multimodel_to_mongo.py --phase main --profile <profile>`. Trang `/multimodel` chỉ đọc các run main có protocol đúng và chỉ hiện điểm khi mẫu số đủ.

## Bảng đầu ra

Ví dụ bố cục, chưa có điểm đo. Bốn hàng model đã được chọn; khả năng truy cập endpoint được kiểm tra trước pilot.

| Model | VMLU<br>Accuracy | Vi-SQuAD<br>EM / F1 | Vi-DROP<br>EM / F1 | Legal MC<br>Accuracy | Legal NLI<br>Accuracy | ViBidLQA<br>EM / F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | — | — / — | — / — | — | — | — / — |
| MiMo V2.6 Flash | — | — / — | — / — | — | — | — / — |
| MiMo V2.5 | — | — / — | — / — | — | — | — / — |
| Qwen3.5-9B · 65K | — | — / — | — / — | — | — | — / — |

- Score hiển thị phần trăm, hai chữ số thập phân; header công bố n và metric version.
- UI giữ một bảng, hàng model và cột đầu cố định khi cuộn. Bấm ô để xem CI, số đúng/tổng, lỗi, settings và nguồn run.
- Ô chưa đo ghi “chưa chạy”; thiếu gold ghi “chờ gold”; điểm server chưa có ghi “chờ server”. Không điền bằng 0.
- Không có thứ hạng tổng mặc định; mỗi metric giữ thang so sánh riêng.

## Việc cần xác minh khi triển khai

| Thời điểm | Việc cần xác minh | Kết quả cần có |
| --- | --- | --- |
| Trước pilot | Provider/gateway và quyền truy cập bốn model | Model ID thực, tier, thông tin revision khi có, rate limit và tham số được hỗ trợ |
| Trước pilot | Ngân sách đợt pilot | Mức trần chi phí được khai báo cho 800 request dự kiến |
| Sau pilot | Reasoning/output budget theo nhóm bài | Profile được công bố, không chọn theo điểm cao nhất của từng model |
| Sau pilot | Chi phí/thời gian đợt chính | Dự toán 8.172 request, phần retry và giới hạn ngân sách |

Các quyết định phương pháp được giữ trong kế hoạch này; quyết định phiên bản metric được ghi tại [ADR-0001](../adr/0001-version-vietnamese-reading-metrics.md). Các giá trị phụ thuộc provider và đo thực tế được điền trong measurement card trước khi chạy chính.

## Nguồn

- [VMLU, ACL 2025](https://aclanthology.org/2025.acl-long.563/): phân biệt các nhóm năng lực; các điểm đọc hiểu trong bài dùng LLM judge, nên không so trực tiếp với EM/F1 local mới.
- [Official DROP evaluator](https://github.com/allenai/allennlp-reading-comprehension/blob/master/allennlp_rc/eval/drop_eval.py): đáp án số, ngày, nhiều span và quy tắc F1/EM tham khảo.
- [Meta Model API models](https://dev.meta.ai/docs/models): ID/tier Muse Spark và giới hạn reasoning max.
- [Meta Model API reasoning](https://dev.meta.ai/docs/reasoning): nguồn để đối chiếu chính sách reasoning khi chuẩn bị runner.
- [Xiaomi: MiMo V2.6 checkpoint update](https://mimo.xiaomi.com/blog/mimo-v2-6-tool-call-repetition): alias API giữ nguyên sau cập nhật checkpoint.
- [Measurement card](../../measurement_card.md): mẫu, baseline và các khác biệt điều kiện đo lịch sử.
- [Reading reference provenance](../agents/reading-results-table.md): hạn chế gold hiệu đính từ output model.
- [Reading scorer](../../code_benchmark/score_reading_eval.py): EM/char-F1 hiện hành.
- [Canonical scoring spec](../../openspec/specs/eval-scoring/spec.md).
- [Results backend contract](../../openspec/specs/results-backend/spec.md).
