# Kế hoạch mở rộng benchmark tiếng Việt đa model

Cập nhật: 2026-10-07, múi giờ Asia/Ho_Chi_Minh.

Trạng thái: **kế hoạch triển khai**. Tài liệu được lập từ kiểm kê dữ liệu, kết quả và lịch sử submission trong repo. Các dự toán quota bên dưới được tính offline; chưa phát sinh inference hoặc submission mới từ việc lập kế hoạch.

Mục tiêu là hoàn tất phạm vi VMLU cho bốn model hiện tại, thực hiện một lượt V-Bench có điều kiện công bố rõ, lấy điểm chính thức qua hệ thống đã từng submit và lưu kết quả vào `/table`. Những phép đo mới về đặc trưng ngôn ngữ tiếng Việt là phần mở rộng sau đợt cốt lõi.

## Mục lục

1. [Điểm xuất phát và các kết quả đã có](#1-điểm-xuất-phát-và-các-kết-quả-đã-có)
2. [Phạm vi và thứ tự ưu tiên](#2-phạm-vi-và-thứ-tự-ưu-tiên)
3. [Model và protocol suy luận](#3-model-và-protocol-suy-luận)
4. [Dữ liệu, manifest và tái sử dụng](#4-dữ-liệu-manifest-và-tái-sử-dụng)
5. [Công việc triển khai runner và scorer](#5-công-việc-triển-khai-runner-và-scorer)
6. [Pilot và đóng băng main](#6-pilot-và-đóng-băng-main)
7. [Ngân sách, quota và lịch chạy](#7-ngân-sách-quota-và-lịch-chạy)
8. [Lỗi, checkpoint và phục hồi](#8-lỗi-checkpoint-và-phục-hồi)
9. [Metrics và giới hạn diễn giải](#9-metrics-và-giới-hạn-diễn-giải)
10. [Submission và lưu điểm server](#10-submission-và-lưu-điểm-server)
11. [Artifacts và UI](#11-artifacts-và-ui)
12. [Các mốc thực hiện và tiêu chí hoàn thành](#12-các-mốc-thực-hiện-và-tiêu-chí-hoàn-thành)
13. [Mở rộng thêm và các điểm chưa chốt](#13-mở-rộng-thêm-và-các-điểm-chưa-chốt)
14. [Nguồn dữ liệu và tài liệu tham khảo](#14-nguồn-dữ-liệu-và-tài-liệu-tham-khảo)

## 1. Điểm xuất phát và các kết quả đã có

### Main v1

Main v1 đã hoàn tất 2.043 item/model, tổng 8.172 item-model, với 100% request coverage và 0 `request_error` trong checkpoint cuối. Mỗi model đã chạy 744 VMLU valid, 200 Vi-SQuAD, 200 Vi-DROP, 146 Legal MC, 150 Legal NLI và 603 ViBidLQA test. Kết quả được ghi tại [báo cáo main](vi-multimodel-main-results-2026-10-07.md), các card MC-53–56 và `web/data/vi-multimodel-main-results.json`.

V1 là một bộ mẫu nghiên cứu đã hoàn thành. Các kết quả VMLU valid trong đó chỉ bao phủ split 744 câu; V-Bench thuộc nhánh đo riêng.

### Submission và phép đo lịch sử

| Artifact đã có | Phạm vi và điều kiện | Vai trò trong kế hoạch mới |
| --- | --- | --- |
| VMLU MC-7, Qwen3.5-9B-28K | Test 9.833; đã submit và có điểm server 67,87% ngày 2026-09-20 | Tái sử dụng workflow, schema CSV và cách lưu kết quả; model 28K là hàng lịch sử |
| V-Bench MC-8, Qwen3.5-9B-28K | 5.141 câu chấm được; macro 45,22 và micro 45,61%; gồm 14 câu agentic dùng guided | Tái sử dụng schema upload và snapshot; khai rõ điều kiện guided khi trích điểm |
| V-Bench MC-30–33, MC-48 | MiMo V2.5 và Qwen 65K, các arm API/harness; đã có điểm server cho MC 12 domain | Đối chiếu prompt, điều kiện, parser và server response; không tự chuyển thành lượt v2 |
| Calibration MC-43–44 | Qwen 65K trên VMLU all_gold 1.047, logprobs token đầu; accuracy 71,73%, ECE 6,51 pp | Bằng chứng calibration đã có, thuộc condition riêng; không nói rằng cả bốn model đã có calibration |
| Faithfulness MC-37–40 | Các cổng validation judge đã thất bại; nhánh tự động đã đóng | Các scores judge thất bại không đủ điều kiện công bố grounding |
| Safety MC-45 | Nhánh 4.000 hàng safety/open đã đóng vì thiếu gold/rubric phù hợp | Mọi mở rộng safety cần thiết kế và nhãn mới |

Hồ sơ thành công đã nằm tại [báo cáo VMLU](../vmlu-leaderboard-qwen35.md), [báo cáo V-Bench](../vbench-server-qwen35.md), [hồ sơ WAF](../vbench-waf-repro.md), `submissions/` và `measurement_card.md`. Kế hoạch tiếp tục dùng những cấu trúc này.

### Kiểm kê nguồn ngày 2026-10-07

| Nguồn | Số item | Gold local | Trạng thái với bốn model main |
| --- | ---: | --- | --- |
| VMLU valid | 744 | Có | V1 đã chạy đủ |
| VMLU dev | 303 | Có | Pilot v1 đã dùng một tập con; chưa có lượt dev đầy đủ trong condition main của cả bốn model |
| VMLU test | 9.833 | Không; cả 9.833 dòng đều không có answer | Cần inference mới và điểm server |
| VMLU all_gold | 1.047 | Có | Chính xác là hợp của dev và valid, cùng nội dung theo ID |
| V-Bench MC | 4.141 | Không | Có một số lượt lịch sử; Muse/MiMo 2.6 chưa có artifact tương ứng |
| V-Bench agentic | 1.000 | Không có gold correctness local | Có schema, có lượt lịch sử; các submission cũ của MiMo V2.5/Qwen 65K còn invalid |
| V-Bench safety/open | 4.000 | Không | Runner release hiện tại bỏ qua; MC-45 ghi nhận chưa đo |

Tổng VMLU có ID duy nhất là **10.880 = 744 + 303 + 9.833**. `all_gold` là một cách đóng gói lại dev và valid, nên không cộng thêm 1.047 vào tổng.

Kiểm kê cũng phát hiện trùng nội dung giữa split dù ID tách biệt. Theo NFC/casefold/khoảng trắng, dev–valid có 3 fingerprint câu hỏi chung, dev–test có 8 và valid–test có 18. Theo cả câu hỏi và thứ tự choices, dev–test có 1 fingerprint chung. Giữ nguyên các tập chính thức để submit đủ ID; loại các nội dung trùng held-out khỏi tập phát triển dùng để chọn cap/format, đồng thời ghi giới hạn này trong báo cáo.

## 2. Phạm vi và thứ tự ưu tiên

### Phạm vi cốt lõi

| Hạng mục | Mục đích | Số item/model | Đầu ra chính |
| --- | --- | ---: | --- |
| VMLU test | So sánh chính thức trên 58 môn và lấy điểm server | 9.833 | Prediction CSV và accuracy do VMLU trả về |
| VMLU dev | Diagnostics trên đủ dữ liệu có gold; kiểm tra dụng cụ | 303 | Local accuracy và breakdown, ghi rõ vai trò development |
| VMLU valid | Chạy lại dưới condition v2 thống nhất với các split khác | 744 | Điểm local v2; giữ V1 làm score lịch sử |
| V-Bench MC | Kiến thức, văn hóa, phương ngữ, y tế theo domain | 4.141 | Accuracy server, macro/micro theo domain |
| V-Bench agentic | Chọn hàm và tham số theo function schema | 1.000 | Function-call correctness server và schema validity local |

Ưu tiên inference VMLU test, rồi V-Bench MC/agentic. Dữ liệu dev phục vụ diagnostics và lựa chọn kỹ thuật trước main. Các cột Vi-SQuAD, Vi-DROP, Legal MC/NLI và ViBidLQA test đã hoàn tất tiếp tục là bằng chứng đọc hiểu/pháp luật của v1.

**10.880 câu VMLU là mục tiêu coverage dữ liệu**, không tự động trở thành một tập held-out có điểm accuracy chung. Dev đã được dùng cho pilot, còn test không có gold local. Báo cáo phải giữ vai trò và metric theo split; chỉ tính một aggregate toàn bộ khi server cung cấp numerator/denominator và quy tắc averaging tương thích, đồng thời ghi rõ dev thuộc development.

### Safety/open của V-Bench

File nguồn có 9.141 dòng, trong đó runner v2026.03.28 xử lý 5.141 MC/agentic và skip 4.000 safety/open. Cần lưu bản scoring spec đang có hiệu lực của portal để xác nhận phạm vi được server chấm. Website leaderboard giới thiệu nhóm safety, nên không suy từ behavior của loader local rằng toàn bộ V-Bench đã được đo.

Nhánh safety/open chưa nằm trong tổng call cốt lõi. Hatespeech 2.000 dòng cần rubric phản hồi/từ chối; politics_easy và politics_advanced tổng 2.000 dòng cần gold/rubric nội dung theo từng câu. Đây là các nhiệm vụ khác nhau. MC-45 đã ghi nhận việc thiếu gold và giới hạn nhãn tay, nên nhánh này chỉ tiến tới inference khi có thiết kế chấm và khả năng hiệu đính phù hợp.

### Số lượt gọi dự kiến

| Phương án | VMLU mới | V-Bench mới | Tổng main mới |
| --- | ---: | ---: | ---: |
| Condition v2 thống nhất: rerun toàn bộ VMLU + fresh V-Bench cho 4 model | 43.520 | 20.564 | **64.084** |
| Tham khảo: reuse valid v1 nếu profile/wire condition trùng tuyệt đối | 40.544 | 20.564 | **61.108** |
| Chỉ official VMLU test và V-Bench MC/agentic; dev chưa chạy đủ | 39.332 | 20.564 | **59.896** |

Pilot dự kiến thêm 800 request. Probe và technical retry/resume được ghi riêng. Nếu safety/open đủ điều kiện chấm và chạy cả bốn model, phát sinh thêm tối đa 16.000 item-model; số đó chưa nằm trong ngân sách cốt lõi.

## 3. Model và protocol suy luận

### Roster giữ từ main v1

| Profile | Model ref | Provider/API | Reasoning đang dùng | Temperature hiệu lực / seed |
| --- | --- | --- | --- | --- |
| `muse-spark-1-3-contributor` | `zen-go/muse-spark-1.3-contributor` | OpenCode Go Responses | `auto` | Provider default 1,0; không gửi seed |
| `mimo-v2-6-flash` | `zen-go/mimo-v2.6-flash` | OpenCode Go Chat Completions | Thinking bật, `auto` | Provider default 1,0; không gửi seed |
| `mimo-v2-5` | `zen-go/mimo-v2.5` | OpenCode Go Chat Completions | Thinking bật, `auto` | Provider default 1,0; không gửi seed |
| `qwen3-5-9b-65k` | `iec/Qwen3.5-9B-65K` | IEC internal Chat Completions | `off` | 0,0; seed 42 |

Đây là provider-native profiles đã đo trong v1. Không giả định temperature, seed và effort có hiệu lực giống nhau ở mọi API. Ghi request model ID, response model ID và revision/fingerprint nếu provider trả về; ghi rõ trường nào không được cung cấp.

### Wrapper và settings chung đề xuất

- Dùng OMP với version v1 `omp/18.0.0` khi còn khả dụng; một subprocess độc lập/item, mode JSON, tools `none`, không persisted session.
- Isolate config, HOME và scratch directory; kiểm tra không nạp `AGENTS.md`, append-system, extensions, rules, memory hoặc tool menu ngoài protocol.
- System prompt `Answer the user's question.`. Prompt VMLU dùng frozen `build_prompt`; V-Bench dùng builders/parser hiện có, style `minimal`.
- Model gọi endpoint của OpenCode Go hoặc IEC qua adapter đúng API. Muse dùng Responses, hai MiMo/Qwen dùng Chat Completions; không ép Muse vào chat-only runner.
- Bốn worker/profile, timeout 300 giây/item. SDK retries tắt; mọi recovery attempt được ghi riêng theo quy tắc ở mục 8.
- Cap dự kiến trước pilot: MC 4.096 token; agentic 2.048 token. Cap reasoning/output được ghi theo tham số thực tế của provider.
- V-Bench agentic ở đây đo model sinh mô tả lời gọi hàm từ schema. Không có tool thực được thực thi bởi OMP trong condition này.
- Chỉ chấm response chính/đáp án cuối đã trích theo parser đóng băng. Không lấy best-of, chọn giữa nhiều output hoặc majority vote cho headline.

Cap agentic là giả thuyết cần kiểm tra trước main. Prompt agentic local có độ dài trung bình khoảng 10.346 byte và tối đa 21.921 byte. Pilot phải bao phủ schema dài, nhiều hàm, enum, required/optional và kiểu dữ liệu để kiểm tra context và output budget.

### Measurement cards

Tạo protocol `vi-multimodel-v2` và card mới cho mỗi profile/benchmark/condition. Card IDs lấy từ số chưa dùng tiếp theo khi triển khai; MC-58 trở đi là dải dự kiến, chưa được preregister bởi tài liệu này.

Ghi tất cả card của một phase trước request đầu tiên, chụp snapshot và hash toàn bộ `measurement_card.md`. Giữ snapshot cố định trong phase vì config/resume hiện dùng hash toàn file. Trạng thái hoàn thành và điểm hậu nghiệm ghi tại `run.json` cùng báo cáo kết quả, thay vì sửa nội dung card đang được hash.

Đổi prompt, decoding, cap main, tool menu, model/backend hay scorer tạo condition/card mới. Đổi budget guard cho recovery chỉ được thực hiện trong hạn mức đã công bố, có audit trail và giữ nguyên các điều kiện inference.

## 4. Dữ liệu, manifest và tái sử dụng

### Manifest v2

Manifest chứa protocol/profile version, source hashes, ID/split/task, prompt hash, choices/function-schema hash, stratum và trạng thái gold. Phân biệt ít nhất:

- `gold_status=local`: VMLU dev/valid và pilot synthetic.
- `gold_status=withheld`: VMLU test, V-Bench MC/agentic.
- `gold_status=unavailable`: nhánh safety/open chưa có protocol chấm.

Gold có thể dùng để chấm local; không đi vào prompt model. Item thiếu gold khi split yêu cầu gold phải fail-fast. Split withheld được chấp nhận theo contract tường minh, không dựa trên suy đoán từ chuỗi rỗng.

Manifest giữ đủ ID chính thức cho test/submission. Không dedupe câu hỏi của benchmark rồi giảm mẫu số. `all_gold` chỉ là union đã xác minh, không phải một split độc lập. Lưu audit ID/content overlap trước khi chọn pilot.

### Valid 744: giữ v1 riêng, chạy lại trong v2

Runner v2 dùng `User-Agent: vmlu-benchmark/2.0` và card snapshot mới; V1 dùng headers/card hash cũ. Vì vậy main v2 **chạy lại valid 744**, cùng với dev303 và test9833. Không nhập raw output v1 vào headline v2.

Kết quả V1 vẫn được giữ ở bảng lịch sử. Nếu sau này có phép đo nào định reuse giữa version, trước khi dùng phải so sánh source/item ID, input/prompt hash, model ref/revision, API adapter, system prompt, tools/session, reasoning, sampling, token cap, timeout, OMP version và request headers. Card/run gốc phải được giữ trên từng item; không đổi metadata cũ để mang nhãn v2.

Nếu API không có revision/fingerprint, lưu mức xác minh thực tế. Re-run v2 tạo **một condition và một card hash cho đủ 10.880 VMLU item/profile**. So với reuse valid744, lựa chọn này thêm 2.976 calls cho bốn model.

### Reuse kết quả V-Bench lịch sử

MC-30, MC-31/32 và MC-48 có đường gọi/settings khác main v1; Qwen 28K cũng là model khác. Mặc định fresh V-Bench cho bốn profile hiện tại để có protocol v2 nhất quán. Giữ các scores lịch sử ở hàng điều kiện riêng.

Không coi các dòng guided là một phần của condition minimal. Nếu cần một condition guided để nghiên cứu độ nhạy format, phải preregister và đánh giá riêng; không dùng để vá riêng các câu model làm sai trong main.

## 5. Công việc triển khai runner và scorer

### 5.1. Contracts và item adapters

- [ ] Tạo protocol/profile files v2; giữ config v1 và manifest v1 có thể đọc/resume như trước.
- [ ] Parameterize đường protocol/manifest/output theo suite version, giữ thay đổi ở seam hẹp; không sửa kernel frozen hoặc `legacy/`.
- [ ] Thêm VMLU test adapter cho nguồn không có answer; hiện `_load_vmlu` chỉ xử lý dev/valid và yêu cầu gold.
- [ ] Thêm V-Bench MC/agentic adapters; import `build_prompt`, MC clamp và function parser/schema validator hiện có.
- [ ] Ghi task `function_call`, source domain và schema identity cho agentic; bảo toàn item identity `dataset:item_id` với replicate/run identity riêng.
- [ ] Giữ V1 valid744 làm baseline; chạy lại valid744 cho v2 để full VMLU có một condition/hash/profile.

### 5.2. Transport và checkpoint

- [ ] Tái sử dụng đường OMP/profile của `run_vi_multimodel_eval.py`, gồm Responses cho Muse và probe tối thiểu 16 token đã sửa.
- [ ] Thêm per-task cap MC/agentic và lưu actual API controls; phản hồi unsupported parameter phải được xử lý trước khi freeze main.
- [ ] Ghi append-only attempt ledger, request/session IDs, finish reason, usage telemetry và liveness/heartbeat; result checkpoint vẫn atomic.
- [ ] Giữ một writer/process cho mỗi run; khóa để ngăn hai process resume cùng run. Thêm sharding chỉ khi manifest shards disjoint và ledger/budget được quản lý chung.
- [ ] Dừng dispatch khi auth fail hoặc endpoint probe fail sau chuỗi lỗi transport; giữ các item chưa có output là pending.

### 5.3. Scoring và export

- [ ] Local scorer chỉ tính accuracy khi gold local hiện hữu. VMLU test/V-Bench hiển thị coverage/validity và trạng thái `awaiting_server` trước khi có grade.
- [ ] Lưu parser output, source raw answer và parse failure; response complete nhưng model không sinh đáp án hợp lệ vẫn ở mẫu số.
- [ ] Xuất VMLU CSV và V-Bench JSONL bằng format đã dùng thành công; thêm metadata/checksums và mapping omitted/invalid IDs.
- [ ] Import grade server cùng raw response, release/date, received/matched/total, card và checksum file đã nộp.
- [ ] Tạo exporter aggregate cho `/table`; version/condition selection tường minh, thiếu score không hiển thị thành 0.

### 5.4. Các kiểm tra offline trước inference

Ưu tiên các test có thể phát hiện sai điểm hoặc sai mẫu số: missing/withheld gold, drift source/prompt, duplicate/unknown ID, all_gold union, reuse khác condition, offered-choice clamp, function schema validity khác correctness, technical errors khác model parse failures, resume idempotence, cumulative quota, trùng writer và server denominator.

Chạy các kiểm tra phù hợp của repo: `unittest`, parity parser, ruff và bandit cho thay đổi Python; typecheck/bun tests liên quan cho UI. Test dùng dữ liệu nhỏ/fakes, không gọi endpoint model trong CI. Tài liệu kế hoạch này không tự thêm tests hoặc chạy inference.

## 6. Pilot và đóng băng main

### Pilot đề xuất: 200 request/profile, tổng 800

| Thành phần | Request/profile | Vai trò |
| --- | ---: | --- |
| VMLU dev | 100 | MC format/throughput/usage; chọn seed 42 và loại fingerprint trùng valid/test |
| Agentic synthetic | 80 | Tác vụ tiếng Việt có gold hàm/tham số tự xây, bao phủ schema/enum/required/optional và prompt dài |
| Lặp | 20 | Lặp 10 câu MC và 10 synthetic agentic, replicate IDs riêng để đo agreement |

Pilot synthetic không dùng câu hỏi chính thức của V-Bench để tinh chỉnh prompt. Gold synthetic cần được xác minh trước inference. Lượt lặp không góp vào mẫu số accuracy của 180 câu duy nhất và không dùng chọn output tốt nhất.

Cổng kỹ thuật trước main: auth/API adapter hoạt động, source và run identities đúng, tools được gọi bằng 0, parser đã qua fixtures, raw output/usage/cost ghi được và recovery giữ nguyên điều kiện. Model sai câu hoặc sinh JSON invalid là kết quả cần báo, không phải lý do tự tinh chỉnh prompt tới khi có score tốt.

Kiểm tra truncation/output budget và context trên pilot. Nếu cần đổi cap, thay trước main cho condition đã công bố và tính lại preflight. Không chọn cap theo điểm server của test. Ước tính wall time từ tổng thời gian pilot dưới concurrency đã định; ghi khoảng dự kiến thay vì cam kết ETA.

Sau pilot, đóng băng prompt/style, profile/API settings, cap, timeout, workers, recovery policy, scorer versions, manifests, card snapshots và budget guard. Main không chọn hyperparameter từ kết quả leaderboard.

## 7. Ngân sách, quota và lịch chạy

### Dự toán offline tại thời điểm lập kế hoạch

Ngày 2026-10-07, [OpenCode Go](https://opencode.ai/docs/go/) liệt kê rates sau, đơn vị mỗi triệu token. Giá quy đổi này dùng để tính quota subscription.

| Model | Input | Output | Cached read | Go monthly/model |
| --- | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | $0,10 | $0,20 | $0,002 | $60 |
| MiMo V2.6 Flash | $0,14 | $0,28 | $0,0028 | $60 |
| MiMo V2.5 | $0,14 | $0,28 | $0,0028 | $60 |

Go còn có cửa sổ 5 giờ bằng 20% và tuần bằng 50% monthly limit, tương ứng $12 và $30/model với Go thông thường. Phải đọc usage còn lại của tài khoản trước chạy; không suy từ $60 monthly rằng mọi phase có thể chạy liền trong một cửa sổ. Tài khoản Go Plus có hạn mức khác. Giữ lựa chọn của người dùng: dùng Go, không chuyển sang pay-as-you-go.

Công thức preflight dựa trên runner v1:

```text
reserve/item = ((UTF-8 prompt bytes + 256) × input rate
                + completion cap × output rate) / 1.000.000
```

Đây là bound theo giả định token/framing của runner, không phải tokenizer chính xác hoặc invoice. Không trừ cache hit; bảng dưới chưa cộng probe, pilot và retry. Với builders nguồn hiện tại, MC cap 4.096 và agentic cap 2.048:

| Profile | VMLU test 9.833 | VMLU dev 303 | VMLU mới 10.136 | VMLU rerun 10.880 | V-Bench MC | V-Bench agentic | V-Bench 5.141 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse | $8,760147 | $0,268602 | $9,028749 | $9,689538 | $3,800537 | $1,469758 | $5,270295 |
| Mỗi MiMo | $12,264206 | $0,376043 | $12,640249 | $13,565354 | $5,320752 | $2,057661 | $7,378413 |
| Qwen IEC | Chưa định giá | Chưa định giá | Chưa định giá | Chưa định giá | Chưa định giá | Chưa định giá | Chưa định giá |

Tổng bound cốt lõi cho ba Go profile theo lựa chọn rerun toàn VMLU là khoảng **$56,847367 quota-equivalent**; đây là tổng trên ba model, không phải giới hạn của một model. Guard preregistered cho main là VMLU Muse $10/mỗi MiMo $14; V-Bench Muse $6/mỗi MiMo $8,50. Tổng guard main ba Go profile là $61, chưa gồm pilot. Giới hạn Go theo rolling window cũng được theo dõi; guard $14 của MiMo VMLU là upper bound qua cả run, nên nếu endpoint rate-limit thì checkpoint resume đợi cửa sổ quota thay vì dispatch tiếp.

Rates, model availability và allowance phải được kiểm tra lại ngay trước khi freeze. Retry có usage thiếu được reserve bảo thủ; giá trị token được báo là 0 không chứng minh request chưa được provider xử lý. Qwen không có tariff hạ tầng: guard USD với rate 0 không giới hạn được chi phí thật, nên cần guard số item, token, concurrency và wall time.

### Lịch chạy

1. Preflight cả bốn profile và lưu budget report; pilot theo roster đã chốt.
2. Ưu tiên ba Go profile: chạy VMLU test trước, dev diagnostics và V-Bench sau theo quota còn lại.
3. Giữ 4 worker/profile; mặc định tối đa hai Go profile đồng thời, tối đa 8 OMP requests đang xử lý. Model tiếp theo vào slot khi một model xong.
4. Chạy Qwen sau phần Go như thứ tự người dùng đã chọn; kết nối IEC VPN, xác minh split DNS/endpoint và giữ 4 worker.
5. Khi allowance hết hoặc endpoint lỗi, checkpoint được giữ; tiếp tục khi cửa sổ/quyền truy cập hồi phục. Dừng dispatch khi có budget breach thay vì chuyển provider.

Đây là batch của các câu độc lập. Có thể chia hàng đợi thành shard công việc, nhưng mỗi request vẫn chỉ có một câu và không dùng chung context. Thay số worker trong run đang đo là thay điều kiện cần được preregister riêng.

UI/Mongo nếu cần start/restart phải dùng Docker theo lựa chọn vận hành của người dùng. Result/checkpoint nằm trên thư mục hoặc volume persistent; không dùng `/tmp` để giữ kết quả qua mất điện. Scratch của OMP có thể nằm trong `/tmp`.

## 8. Lỗi, checkpoint và phục hồi

| Tình huống | Cách xử lý | Tác động tới điểm |
| --- | --- | --- |
| DNS/VPN/socket/timeout trước khi có response hoàn tất | Ghi technical error và attempt metadata; resume trong policy/budget cố định | Item pending; headline chưa được coi là đủ khi request coverage còn thiếu |
| Response complete nhưng không trích được chữ cái/hàm, rỗng hoặc refusal | Ghi output gốc, `unparsed`/`empty`/`invalid`; không gọi lại để tìm đáp án đúng | Vẫn thuộc mẫu số accuracy/correctness |
| Finish reason `length` | Ghi truncation, chấm output hoàn tất theo parser cố định | Không được xóa khỏi denominator hoặc rerun với cap lớn hơn chỉ cho câu đó |
| Auth/model/unsupported params | Dừng profile và sửa adapter trước main; thay điều kiện main cần card/run mới | Không tạo điểm 0 giả cho toàn bộ dataset |
| Model/tools/protocol drift | Dừng, lưu sự kiện, tạo condition mới khi cần | Không gộp vào score cùng condition |
| Power loss/process chết | Xác minh lock/liveness và hash checkpoint, phục hồi VPN khi cần, resume pending | Dòng complete chỉ tính một lần; attempt chưa có kết quả giữ trong audit log |

SDK retries giữ bằng 0. Recovery chỉ áp dụng lỗi kỹ thuật theo policy đã đóng băng; đề xuất tối đa 3 attempt kỹ thuật trong mỗi recovery pass, có backoff và endpoint probe trước khi dispatch lại. Nếu endpoint tiếp tục hỏng, run giữ trạng thái incomplete để chờ phục hồi. Không dùng `--retry-unparsed` hoặc `--guided` của runner lịch sử để vá model failures của main v2.

Checkpoint ghi atomic sau completion, có attempt ledger và heartbeat. Sau mất điện, request đã được server xử lý nhưng chưa kịp lưu có thể bị gọi lại; không cam kết exactly-once billing. Ghi attempt ambiguous và reserve còn lại, giữ nguyên completed rows và ID duy nhất.

Không dùng tên `run.status=running` như bằng chứng process còn sống. Supervisor kiểm tra PID/lock/heartbeat và output mới. Một process resume sở hữu một run; export và scoring đọc snapshot đã hoàn tất.

## 9. Metrics và giới hạn diễn giải

| Khối | Metrics chính | Metrics bổ sung |
| --- | --- | --- |
| VMLU dev/valid có gold | Accuracy theo split, 58 môn và category | Correct/total, offered-choice validity, CI95 Wilson, breakdown, latency/token/truncation |
| VMLU test | Điểm server chính thức theo quy tắc averaging của VMLU | Source split, coverage, parse-invalid, lịch sử submit; CI chỉ khi numerator/denominator có thật |
| V-Bench MC | Correct/total server, micro và macro 12 domain | Local parse-validity, coverage, CI theo counts được server cấp |
| V-Bench agentic | Function-call correctness server trên mẫu số 1.000 | Schema validity, required-slot fill, argument/schema diagnostics, latency/token/truncation |
| Reading v1 | EM giữ dấu, token-F1 và CI đã lưu | Legacy scorer, counts và các giới hạn reference; không đổi score gốc |

Coverage request = số item có response hoàn tất / số item đăng ký. Parse validity là tỷ lệ response theo đúng schema; correctness cần gold local hoặc grade server. Báo riêng số technical error, model invalid và omitted submission.

V-Bench micro = tổng correct / tổng total của các domain được đưa vào cùng phạm vi. Macro = trung bình score của domain đã chốt; MC macro 12 domain và all-scored macro 13 domain phải có nhãn riêng. Không lấy aggregate response khi chỉ nộp MC mà mặc định nó là điểm cho toàn bộ MC + agentic.

Với server withheld-gold, không tự dựng per-item correctness từ việc hai model trùng đáp án. Không có nhãn per item thì không chạy McNemar/paired correctness bootstrap; chỉ công bố được metrics mà server thực sự cấp. Score làm tròn không đủ để khôi phục chính xác số câu đúng nếu server không cấp counts.

CI95 cho local MC dùng Wilson. Reading v1 đã dùng bootstrap theo passage, 2.000 lần. CI thể hiện biến thiên theo mẫu, không thay thế phép đo nhiễu giữa các lần gọi API; nhiệt độ 0 và seed có thể vẫn không đảm bảo endpoint tất định.

Headline giữ metric theo benchmark/split/condition. “Đã chạy 10.880 câu” là coverage; việc dev được dùng phát triển và các đoạn nguồn lặp giữa split phải được ghi khi diễn giải khả năng tổng quát hóa.

## 10. Submission và lưu điểm server

### VMLU

Tạo UTF-8 CSV `id,answer` cho **test 9.833 ID**, sort theo thứ tự source hoặc quy tắc đã đăng ký. Check exact ID-set, unique ID, option hợp lệ, dấu phẩy/header/encoding và SHA-256. Dev/valid có output riêng để tránh upload nhầm vào test.

Dùng [cổng VMLU submit](https://vmlu.ai/submit) và workflow đã thành công ở MC-7. Website nêu kết quả upload mặc định riêng tư; public leaderboard cần yêu cầu xác minh. Cổng cũng giới hạn số record và số lần nộp/ngày, nên kiểm tra account state trước lượt mới. Ghi receipt, thời gian, file hash và score JSON/screenshots được trả về. Không xóa record cũ để tạo slot mà chưa xác định chúng cần được giữ.

### V-Bench

Tạo JSONL `{"id":int,"answer":...}` từ parser đã đóng băng, dùng cách serialize chính thức đã kiểm chứng và source-ID mapping. File MC, agentic và combined mang cùng condition; không ghép một track API với track harness khác.

Response complete nhưng model invalid giữ trong omission ledger. Exporter hiện có bỏ invalid rows: xác minh portal chấp nhận omission/blank theo spec và server vẫn dùng full domain denominator. Không đoán chữ cái/hàm để lấp dòng hoặc loại câu sai khỏi mẫu số. Nếu spec không chấp nhận output của condition đó, công bố hạn chế định dạng hoặc thiết kế condition format mới trước main.

Gửi qua [V-Bench submission](https://vbench.ai/submission), hoặc endpoint grading đã được xác nhận trong workflow hiện có. Lưu nguyên response và response headers/status cần thiết; phân biệt đã được grade với đã xuất hiện công khai trên [leaderboard](https://vbench.ai/leaderboard).

Repo đã ghi nhận WAF trả HTML cho một số combined payload và có phương pháp grading agentic theo chunk đã đối chiếu với full submission ở MC-28. Tái sử dụng cách này chỉ sau kiểm tra scoring spec và equivalence hiện tại: shards phải có ID disjoint, cộng counts `correct` của domain, chia cho tổng domain 1.000 một lần; không cộng `totalQuestions=1.000` từ mọi response hoặc lấy trung bình các score chunk. Khi phép đối chiếu không còn khớp, ghi lỗi submission và giữ `awaiting_server`.

Một file main/profile/condition chỉ có một kết quả chính thức được lựa chọn theo rule đã chốt; không chọn lần nộp có điểm cao nhất. Prompt/guided changes không được quyết định từ grade của test.

### Cổng trước upload/công bố

Hoàn tất bản file upload, checksum, source-ID audit, model/condition manifest, coverage/invalid counts và báo cáo đủ để xem lại trước khi gửi kết quả mới. Việc lập tài liệu này chưa phải lệnh upload; không liên hệ ban tổ chức hoặc công bố từ bước planning. Khi người dùng yêu cầu submit, tiếp tục workflow có sẵn trong phạm vi đó; public listing/communication cần đúng chỉ dẫn của người dùng và portal.

## 11. Artifacts và UI

Cấu trúc đề xuất khi triển khai, chưa phải các file đã được tạo:

```text
data/vi_multimodel_protocol_v2.json
data/vi_multimodel_profiles_v2.json
data/vi_multimodel_v2/
  source_inventory.json
  pilot_v2.json
  vmlu_dev_v2.json
  vmlu_test_v2.json
  vbench_mc_v2.json
  vbench_agentic_v2.json
  source_inventory.json
all_res/vi_multimodel_v2/<phase>/<profile>/<condition>/
  run.json
  predictions.jsonl
  attempts.jsonl
  scores.jsonl                 # chỉ các item có gold local
  summary.json
  source_card_snapshot.md
submissions/vi_multimodel_v2/<profile>/<condition>/
  submission_vmlu_test.csv
  submission_vbench_mc.jsonl
  submission_vbench_agentic.jsonl
  submission_vbench_all.jsonl
  omitted_items.csv
  submission_manifest.json
  server_snapshots/
web/data/vi-multimodel-expanded-results.json
docs/research/vi-multimodel-v2-results.md
```

Giữ kết quả local dưới thư mục persistent. `all_res/` và `submissions/` đang gitignored, nên có file local không đồng nghĩa đã được giữ trong lịch sử Git hoặc backup ngoài máy. Tạo archive raw outputs/submissions và checksum index; lưu aggregate JSON, manifests không chứa gold withheld, báo cáo và provenance có thể review trong repo. Không đưa credentials vào archive/public export.

`/table` bổ sung lựa chọn protocol/split hoặc bảng “VMLU/V-Bench mở rộng”. Bảng mẫu:

| Model | VMLU test 9.833 · server | VMLU valid 744 · local | V-Bench MC 4.141 · server | V-Bench agentic 1.000 · server | Request coverage / parse validity |
| --- | ---: | ---: | ---: | ---: | ---: |
| Muse Spark 1.3 Contributor | chờ đo | V1 hoặc v2 có provenance | chờ đo | chờ đo | chờ đo |
| MiMo V2.6 Flash | chờ đo | V1 hoặc v2 có provenance | chờ đo | chờ đo | chờ đo |
| MiMo V2.5 | chờ đo | V1 hoặc v2 có provenance | chờ đo | chờ đo | chờ đo |
| Qwen3.5-9B-65K | chờ đo | V1 hoặc v2 có provenance | chờ đo | chờ đo | chờ đo |

Dev diagnostics hiển thị riêng, có nhãn đã dùng phát triển. Mỗi ô có counts, scorer/server release, card, date, actual reasoning/sampling, tools/session, cap và trạng thái grade. Thiếu gold/grade/coverage hiển thị đúng trạng thái, không dùng 0 làm placeholder. Người xem có thể tìm kết quả lịch sử 28K/API/harness ở các condition riêng.

## 12. Các mốc thực hiện và tiêu chí hoàn thành

| Mốc | Công việc và artifacts | Cổng chuyển tiếp |
| --- | --- | --- |
| P0 — Audit | Source inventory/hash, split overlap, historical-submission mapping, portal scoring scope và model access metadata | Đếm đúng VMLU 10.880 ID và V-Bench 5.141 scorable; biết vai trò dev/gold withheld |
| P1 — Chuẩn bị v2 | Adapters, manifests, profiles, runner/scorer/exporter và offline checks | V1 contracts/parsers không drift; withheld gold, resume, denominator và schema được xử lý đúng |
| P2 — Pilot | Preregister pilot cards/snapshot, chạy 800 request, usage/latency/truncation/adapter report | Adapter hoạt động, budget main và caps chốt theo rule; không tuning từ leaderboard test |
| P3 — Freeze main | Cards mới, source/config snapshots, fixed manifests và quota guards | Đủ thông tin điều kiện cho cả bốn profile; không mutation hashed card trong phase |
| P4 — VMLU | Chạy lại valid, dev và test theo cùng card v2; checkpoints và local diagnostics | Mỗi profile đủ 10.880 response; test 9.833 hàng sẵn sàng cho portal |
| P5 — V-Bench | Fresh MC/agentic cùng v2 condition, checkpoint, parse/omission report | Mỗi profile đủ 5.141 response outcomes; technical errors phục hồi, model-invalid giữ trong denominator |
| P6 — Grade/submit | File upload reviewable, receipt/raw server outputs, count/averaging audit | Từng ô có score chính thức hoặc trạng thái awaiting_server; thiếu score không bị coi là hoàn tất grading |
| P7 — Báo cáo/UI | Aggregate JSON, kết quả v2, `/table`, archive/checksum index | Mọi ô truy được về source/run/card/submission/grade; giới hạn suy luận và provenance được công bố |

**Hoàn tất inference** khi mỗi item main có một outcome complete được xác định, technical failures chưa xử lý bằng 0 và không có duplicate identity. Parse invalid có thể tồn tại, được báo cáo và tính sai theo scorer/server contract.

**Hoàn tất benchmark có điểm** khi các ô server-required đã có grade đúng file/condition, mẫu số và cách averaging đã kiểm tra. **Hoàn tất công bố public** là trạng thái riêng, có receipt hoặc xác minh của ban tổ chức; nó không được suy từ sự tồn tại của file submission hay một response từ API grade.

Thời gian dự kiến chỉ được điền sau pilot và quota check. Dự toán theo throughput dưới concurrency thật, tách thời gian inference, chờ cửa sổ quota, chờ grade và chờ public verification.

## 13. Mở rộng thêm và các điểm chưa chốt

### Nhánh nghiên cứu sau phạm vi cốt lõi

1. **Vi-DROP scorer bổ sung:** chấm lại 200 output đã lưu nếu gold cho phép xác định số/đơn vị/span. Metric mới có version riêng; giữ EM/token-F1 v1. Không suy cấu trúc multi-span từ dấu phẩy mà chưa hiệu đính.
2. **Contrast set tiếng Việt:** đề xuất 300 cặp, 50 cặp cho mỗi nhóm phủ định, quy chiếu đại từ, diễn đạt/trật tự, dấu có ý nghĩa, số/ngày/đơn vị và phương ngữ/register. Gold từng biến thể phải được người chấm xác minh. Accuracy từng biến thể và tỷ lệ đúng cả cặp là metrics riêng. Với bốn model là 2.400 calls, chưa trong ngân sách cốt lõi. Biến thể bỏ dấu chỉ được coi invariant khi người chấm xác nhận không làm đổi hoặc mơ hồ nghĩa.
3. **Semantic accuracy/evidence:** dùng nhãn người ẩn tên model trên mẫu đã preregister. Nhánh faithfulness judge MC-37–40 đã thất bại, nên không dùng scores đó như dụng cụ đạt chuẩn. Muốn công bố metric grounding mới cần rubric, nhãn và cổng validation mới.
4. **Calibration đa model:** lưu kết quả Qwen MC-43–44 như condition riêng; mở rộng chỉ khi API cung cấp xác suất phù hợp. Không trộn first-token logprobs với confidence do model tự khai mà gọi cùng phép đo.
5. **Bộ reading lớn hơn/ViBidLQA val/VM14K:** audit gold, trùng split, license và chất lượng trước khi chọn. Gold reading đã được người dùng chấm đủ 400 câu không đồng nghĩa toàn bộ corpus question-only có gold. Không tự đưa các nhánh này vào call budget đã tính.

### Các điểm phải giải quyết khi triển khai

| Điểm chưa chốt | Mặc định đề xuất | Bằng chứng cần có |
| --- | --- | --- |
| Reuse valid v1 | Reuse khi condition/input khớp; giữ provenance v1 | Comparison report, model/response ID và revision khả dụng; nếu drift thì rerun |
| Phạm vi safety của server V-Bench | Cốt lõi MC/agentic 5.141; safety chưa có điểm | Current scoring spec, denominator theo track, rubric/gold nếu cần mở safety |
| Agentic output cap | 2.048 trước pilot | Truncation/context report; thay đổi trước freeze và tính lại budget |
| Quota/account | Go subscription hiện có, không pay-as-you-go | Remaining allowance 5h/tuần/tháng, rates và models còn truy cập được |
| Public leaderboard | Chuẩn bị đủ artifacts; submit theo lệnh tiếp theo của người dùng | Portal receipt; VMLU public verification; V-Bench public state được xác nhận |
| Nhãn người cho metric mới | Chưa giả định có nguồn lực ngoài gold400 | Mẫu, rubric, số labels và người hiệu đính được xác định trước inference/chấm |

Khi người dùng yêu cầu triển khai kế hoạch, bước đầu là P0/P1 và preflight. Những điểm kỹ thuật có thể giải quyết từ repo và endpoint metadata được xử lý trong scope đã cho; chỉ hỏi thêm khi thiếu quyết định về ngân sách mới, nguồn lực nhãn hoặc hành động công bố ngoài hệ thống.

## 14. Nguồn dữ liệu và tài liệu tham khảo

### Hash nguồn kiểm kê ngày 2026-10-07

| File | SHA-256 |
| --- | --- |
| `vmlu_mqa_v1.5/dev.jsonl` | `e4eb5a51a75639bdcc080c96556b09fcfb875033aec867844c15d308ed3c1f0b` |
| `vmlu_mqa_v1.5/valid.jsonl` | `02082d081e8e57b5a1c4c91b11e3caefea2f0f92937d649f5cc61b065bae5e8c` |
| `vmlu_mqa_v1.5/test.jsonl` | `f625e503b6e6713759d8f9ae259724a0b0ce2261fb1e0e0428724d52e184aa3e` |
| `vmlu_mqa_v1.5/all_gold.jsonl` | `6504499974f433c167ed21c4337c5d8328fa1419d6523b53b852ae70323596be` |
| `v_bench/public-test.jsonl` | `5526c4394113ead003dde43331c2fc0e0da32d1ba82ad6326d24ff54417be5ef` |

### Trong repo

- [Kế hoạch v1](vietnamese-multimodel-benchmark-plan.md), [kết quả main v1](vi-multimodel-main-results-2026-10-07.md), [trạng thái pilot](vi-multimodel-pilot-status-2026-10-06.md).
- [Measurement cards](../../measurement_card.md): MC-7/8, MC-30–33, MC-37–45, MC-48–57.
- [VMLU server record](../vmlu-leaderboard-qwen35.md), [V-Bench server record](../vbench-server-qwen35.md), [WAF record](../vbench-waf-repro.md).
- [Versioned items](../../code_benchmark/vi_multimodel.py), [OMP runner](../../code_benchmark/run_vi_multimodel_eval.py), [multi-model scorer](../../code_benchmark/score_vi_multimodel.py).
- [Frozen MC runner/prompt](../../code_benchmark/run_mc_eval.py), [V-Bench prompt/parser/submission](../../code_benchmark/run_vbench_eval.py).
- [Canonical scoring spec](../../openspec/specs/eval-scoring/spec.md), [reading metric ADR](../adr/0001-version-vietnamese-reading-metrics.md).
- [Profiles v1](../../data/vi_multimodel_profiles.json), [protocol v1](../../data/vi_multimodel_protocol_v1.json).

### Nguồn chính thức đã đối chiếu

- [VMLU submission](https://vmlu.ai/submit): CSV, private result và quy trình public verification.
- [VMLU official repository](https://github.com/ZaloAI-Jaist/VMLU): benchmark và submission format.
- [V-Bench submission](https://vbench.ai/submission) và [leaderboard](https://vbench.ai/leaderboard): điểm chấm ngoài repo; cần lưu current scoring spec trước lượt mới.
- [OpenCode Go](https://opencode.ai/docs/go/): rates, model/API availability và cửa sổ quota; đối chiếu ngày 2026-10-07, kiểm tra lại trước freeze.
