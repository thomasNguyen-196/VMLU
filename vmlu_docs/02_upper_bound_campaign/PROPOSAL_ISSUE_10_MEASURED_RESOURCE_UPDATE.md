# PROPOSAL: Cập nhật Issue #10 với Số liệu Tài nguyên Thực đo (Measured Ground-Truth Resource Ledger)

- **Trạng thái**: Chờ duyệt (Pending User Review — đọc lại Issue #10 rồi chỉ điểm cập nhật)
- **Tài liệu lưu trữ**: `vmlu_docs/02_upper_bound_campaign/PROPOSAL_ISSUE_10_MEASURED_RESOURCE_UPDATE.md`
- **Ngày soạn**: 05/10/2026
- **Đích áp dụng**: `vmlu_docs/02_upper_bound_campaign/GITHUB_ISSUE_UPPER_BOUND_18_BATCHES.md` + comment trên GitHub Issue #10
- **Nguồn số liệu**: `all_res/antigravity_resource_ledger/` (trích từ telemetry local Antigravity, đã xác minh độc lập)

---

## 1. Bối cảnh & Mục tiêu

Thầy hướng dẫn Issue #10 hiện tại: investigate sâu hơn số liệu của lần chạy Gemini trên nền Antigravity 2.0 để establish được một baseline để từ đó build một harness tối ưu cho các bộ dataset benchmark tiếng Việt sử dụng (các) model open-weight tầm trung. 

Ban đầu, **số liệu token là ước tính lý thuyết** (~80–100M tokens, tỷ lệ đòn bẩy ~1:500) không truy vết được — không đạt đủ tính chân thực để làm báo cáo.

Crucial finding: phát hiện Antigravity lưu **nguyên bản usage metadata từng lượt gọi LLM** ngay trên máy local (`~/.gemini/antigravity/conversations/*.db`, 85 file SQLite, protobuf `CortexStepGeneratorMetadata`). Toàn bộ chiến dịch 18 batches giờ có bộ 3 trục tài nguyên **đo thật** (Tokens / Latency / Tool calls), trích xuất bằng script kiểm chứng được:

```bash
python3 tools/antigravity_ledger/extract.py     # stdlib-only, deterministic, 1 lệnh
```

Mục tiêu của bản cập nhật: **thay toàn bộ con số ước tính trong phần usage của Issue #10 bằng số đo thực nghiệm**, kèm chuỗi provenance đầy đủ (ai muốn kiểm tra thì chạy lại 1 lệnh).

## 2. Tóm tắt số liệu thực đo (campaign-filtered: 78 phiên / 4.461 lượt gọi LLM)

| Chỉ số                                | Giá trị đo được                                                                                                                                  |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Fresh Input Tokens                    | **54.425.971**                                                                                                                                   |
| Cached Read Tokens                    | **347.642.207**                                                                                                                                  |
| Output Tokens                         | **4.640.797** (thinking 2.689.299 = 57,9% + response text 1.951.498)                                                                             |
| **Net Tokens (fresh + output)**       | **59.066.768**                                                                                                                                   |
| — Solving / Orchestration             | 41.694.408 (70,6%) / 17.372.247 (29,4%) — tách chi tiết ở §3 Edit 2                                                                              |
| **Net tokens/câu**                    | **42,5K total · 30,0K solving-only**                                                                                                             |
| Gross Tokens (fresh + cache + output) | 406.708.975                                                                                                                                      |
| Cache Hit toàn cục                    | **86,46%**                                                                                                                                       |
| Số phiên / lượt gọi LLM               | 78 phiên / 4.461 lượt (trung bình 3,21 lượt/câu hỏi)                                                                                             |
| **Leverage (raw response)**           | **~1 : 30** total · ~1 : 21 solving — chi phí campaign / toàn bộ văn bản model viết ra (đối chiếu ước tính cũ ~1:500)                            |
| **Distilled answers — đo tokenizer**  | **10.989 tokens** cho 1.389 đáp án; leverage trên mẫu số này (1 : 5.375) chỉ mang ý nghĩa giới hạn — xem ghi chú ở §3 Edit 2                      |

Phạm vi số liệu: 78 phiên thuộc cửa sổ chiến dịch 15–20/09 (danh sách phiên: `sessions.csv`).

## 3. Bản vá đề xuất theo vị trí (Edit Map)

### Edit 1 — §1 (Rationale), câu nói về ước tính

**Hiện tại**: *"số liệu token của Issue #10 phải dựa trên mô hình ước tính lý thuyết (~80M–100M tokens với tỷ lệ đòn bẩy 1:500)"*

**Đề xuất thay**:

> *"số liệu token của Issue #10 ban đầu dựa trên ước tính lý thuyết (~80–100M tokens, đòn bẩy ~1:500); kể từ 05/10/2026 đã được thay thế bằng **số liệu thực đo nguyên bản** từ telemetry local của Antigravity — 59,07M net tokens (30,0K net/câu cho phần solving), đòn bẩy thực đo ~1:30 trên raw response — trích xuất và tái lập bằng `tools/antigravity_ledger/extract.py` (xem §4.4)."*

### Edit 2 — §4.3 (Phân Rã Chi Phí & Tỷ Lệ Đòn Bẩy), thay bảng 3 dòng

**Bảng cũ (ước tính)**: Distilled ~195,6K / Exploration Quota ~80M–100M / Leverage ~1:500

**Bảng mới (thực đo)**:

| Chỉ số Phân rã                                          | Giá trị thực đo                                                                                                                    | Nguồn  |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Distilled Answer Tokens — đo tokenizer thật              | **10.989 tokens** cho 1.389 đáp án (979 câu trắc nghiệm = 1 chữ cái/đáp án) — thay thế ước tính ~195,6K theo quy ước k              | ledger |
| **Agentic Exploration — NET thực đo (campaign-wide)**   | **59.066.768 tokens** (fresh 54,43M + output 4,64M)                                                                                | ledger |
| — trong đó: **Solving** (12 domain giải bài, 1.389 câu) | 41.694.408 tokens (70,6%) ≈ **30,0K net/câu**                                                                                      | ledger |
| — trong đó: **Orchestration** (4 phiên, 884 lượt)       | 17.372.247 tokens (29,4%) — điều phối, kiểm tra tiến độ, tổng hợp report; không trực tiếp giải câu hỏi, tách riêng khỏi per-domain | ledger |
| — Gross (kèm cache-read 347,64M)                        | 406.708.975 tokens                                                                                                                 | ledger |
| — Cache hit                                             | **86,46%**                                                                                                                         | ledger |
| — Cấu trúc                                              | 78 phiên · 4.461 lượt gọi · 3,21 lượt/câu · fresh 12,2K + cached 77,9K tokens/lượt                                                  | ledger |
| — Thinking (reasoning ẩn)                               | 2.689.299 tokens = 57,9% output                                                                                                    | ledger |
| **Tỷ lệ đòn bẩy thực đo (raw response)**                | **~1 : 30** (total) · ~1 : 21 (solving-only) — mẫu số 1.951.498 tokens văn bản model viết ra                                        | ledger |
| Tỷ lệ trên distilled (giới hạn ý nghĩa)                 | 1 : 5.375 (total) — xem ghi chú mẫu số dưới đây                                                                                     | ledger |

**Ghi chú mẫu số leverage — ba đại lượng đo thật, không còn quy ước**:

- Raw response (**1.951.498** tokens — đo thật, field 10) là toàn bộ văn bản model viết ở lượt cuối, gồm cả phần đáp án được distill vào 69 CSV. Leverage trên mẫu số này: **~1 : 30** total / ~1 : 21 solving — đối chiếu trực tiếp ước tính cũ ~1:500 của Issue #10 (cùng intent, mẫu số cùng bản chất).
- Distilled (**10.989** tokens — đo bằng tokenizer Gemini thật trên **từng đáp án**, `answer_tokens.csv`): bảng k quy ước 1,30–1,45 của §4.1 chính thức bị thay thế. Chi tiết: 979/1.389 câu trắc nghiệm có đáp án 1 chữ cái (1 token); Vi-DROP 2,16 tokens/từ (chữ số bị tách riêng: "24,10%" = 6 tokens); Vi-SQuAD 1,41; Agentic 74,9 tokens/đáp án (JSON).
- Leverage trên distilled = **1 : 5.375** (total) — đúng số học nhưng **chỉ mang ý nghĩa giới hạn**: mẫu số gồm những chữ cái 1 token nên ratio tự nổ. Đây là hệ quả của không gian đáp án đóng, không phải lãng phí: với tác vụ phức tạp, chi phí nằm ở **đa bước suy luận và kiểm chứng** (thinking 2,69M = 58% output), không nằm ở độ dài đáp án. Trình bày như một measured fact kèm bảng k_true (§4.5), không dùng làm headline.
- Phạm vi: distilled leverage chỉ định nghĩa được trên dataset có đáp án đóng có gold (toàn bộ 1.389 câu của campaign này được chọn theo tiêu chí đó). Task tự luận (generation tự do, vd. hatespeech/politics của V-Bench) không có mẫu số distilled — với task đó, metric đo được là net tokens/câu và leverage raw response; chất lượng phải chấm bằng rubric/LLM-judge (một trục chi phí riêng, ngoài phạm vi Issue #10).

**Khối công thức `Context_session = K·C₀ + K(K−1)/2·Δ`**: giữ lại nhưng thêm chú thích *"mô hình xấp xỉ thời ước tính; từ 05/10/2026 thay bằng dãy usage per-call nguyên bản trong `llm_calls.csv` (4.461 dòng)"* — không xóa (giữ lịch sử phương pháp).

### Edit 3 — Thêm §4.4 "Measured Ground-Truth Ledger (Provenance)" mới

```markdown
### 4.4. Sổ Cái Tài Nguyên Thực đo (Measured Ground-Truth Ledger — Provenance)

Kể từ 05/10/2026, toàn bộ số liệu tài nguyên của chiến dịch này được trích xuất trực tiếp từ telemetry local của Antigravity (usage metadata nguyên bản từng lượt gọi LLM, do chính hệ thống ghi lại thời điểm chạy):

- **Trích xuất**: `tools/antigravity_ledger/extract.py` — stdlib-only, deterministic, 1 lệnh: `python3 tools/antigravity_ledger/extract.py`
- **Ledger**: `all_res/antigravity_resource_ledger/`
  - `llm_calls.csv` — 4.461 lượt gọi, đủ 3 thành phần token per-call (fresh/cache/output/thinking) + wall-clock per-session
  - `sessions.csv` — 78 phiên campaign + aggregates
  - `batches.csv` — 40 (domain, batch), ghép n_questions với 69 CSV kết quả Issue #10
  - `domains.csv` — 14 domain rollup (bảng per-domain dưới đây)
  - `answer_tokens.csv` — 1.389 đáp án đo bằng tokenizer Gemini thật (thay quy ước k)
  - `excluded_sessions.csv` — nhật ký các phiên ngoài phạm vi đo
- **Phương pháp**: tách bạch đo đạc (telemetry nguyên bản) và định giá (mapping giá sau); orchestration (4 phiên điều phối, 884 lượt) tách riêng khỏi per-domain; attribution per-batch (per-item khả thi khi cần bằng so khớp câu hỏi trong step_payload).
```

### Edit 4 — Bảng per-domain chèn vào cuối §4 (số liệu mới, chưa có trong Issue)

| Domain | n câu | Phiên | Lượt gọi | Fresh/câu | Cache/câu | Out/câu | **Net/câu** | Cache hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| agentic | 110 | 7 | 449 | 48.707 | 318.350 | 3.760 | **52.468** | 86,73% |
| chemistry | 60 | 3 | 148 | 27.181 | 139.186 | 3.402 | **30.583** | 83,66% |
| cs | 20 | 1 | 34 | 15.403 | 68.415 | 2.186 | **17.589** | 81,62% |
| dialect | 100 | 5 | 89 | 10.050 | 33.853 | 1.374 | **11.424** | 77,11% |
| drop | 200 | 10 | 256 | 12.467 | 55.807 | 1.783 | **14.250** | 81,74% |
| laws | 100 | 5 | 343 | 36.788 | 367.421 | 2.500 | **39.288** | 90,90% |
| logics | 225 | 12 | 812 | 39.389 | 270.325 | 4.084 | **43.473** | 87,28% |
| math | 125 | 8 | 491 | 38.609 | 266.636 | 5.006 | **43.614** | 87,35% |
| medicine | 40 | 2 | 63 | 14.809 | 60.915 | 2.111 | **16.920** | 80,44% |
| physics | 147 | 7 | 513 | 34.413 | 314.546 | 3.668 | **38.081** | 90,14% |
| squad | 100 | 6 | 174 | 18.518 | 91.130 | 1.684 | **20.202** | 83,11% |
| vmlu_legal | 50 | 2 | 109 | 18.928 | 158.456 | 2.163 | **21.091** | 89,33% |
| vmlu_other | 112 | 6 | 96 | 9.500 | 27.777 | 1.503 | **11.003** | 74,52% |
| *(orchestration — tách riêng)* | — | 4 | 884 | — | — | — | — | — |

Nhận định kèm bảng (đề xuất thêm 1 câu): *"Chi phí net/câu dao động ~11K–52,5K tokens (≈ 4,7×) giữa domain rẻ nhất (vmlu_other — trích xuất kiến thức nhanh) và đắt nhất (agentic — kiểm định schema nhiều lượt)."*

### Edit 5 — Thêm §4.5 "Bảng k_true — đo tokenizer thật trên từng đáp án" (thay quy ước k của §4.1)

| Loại đáp án | n câu | Σ tokens thật | tokens/đáp án | tokens/từ | k quy ước cũ (§4.1) |
|---|---:|---:|---:|---:|---:|
| Trắc nghiệm 1 chữ cái (10 domain MC: math, logics, physics, chemistry, medicine, cs, laws, dialect, vmlu_other, vmlu_legal) | 979 | 979 | 1,0 | 1,00 | 1,30–1,45 |
| Vi-DROP (số/cụm ngắn, chữ số tách riêng) | 200 | 895 | 4,5 | 2,16 | 1,30 |
| Vi-SQuAD (cụm danh từ tiếng Việt) | 100 | 878 | 8,8 | 1,41 | 1,30 |
| Agentic (JSON function call) | 110 | 8.237 | 74,9 | — (JSON không đếm từ được) | 1,45 |
| **TỔNG** | **1.389** | **10.989** | 7,9 | — | — |

Ghi chú kèm bảng: *"Ước lượng ~195,6K tokens ở §4.1 (từ × k) thực chất phản ánh độ dài văn bản đầy đủ (raw_response) chứ không phải cột đáp án distilled; số đo tokenizer thật cho mẫu số distilled là 10.989 tokens. Kể từ đây mọi phát biểu về token đáp án dùng số đo thật từ `answer_tokens.csv` (script: `calibrate_k.py`)."*

## 4. Các quyết định chờ duyệt (trước khi apply)

1. **Phiên "Upper Bound Probe Progress"** (92 lượt gọi, modified 22/09 — sau cửa sổ campaign 2 ngày): hiện bị loại. Tính là campaign → mở rộng cửa sổ trong extract.py và chạy lại (chỉ thêm ~92 calls vào orchestration)? Hay giữ loại?
2. ~~**Cách phát biểu leverage**~~ — ĐÃ CHỐT: cặp raw-response (~1:30 total / ~1:21 solving) làm chính; distilled 1:5.375 kèm caveat (§3 Edit 2).
3. **Khối công thức K·C₀/Δ ở §4.3**: xóa hẳn hay giữ + chú thích lịch sử? *(khuyến nghị: giữ + chú thích)*
4. **Điểm phân phối**: cập nhật thẳng vào file md local + edit GitHub issue, hay giữ file local làm chuẩn và chỉ post comment tổng kết lên GitHub?

## 5. DoD khi apply

- [ ] §1 đã thay câu ước tính bằng câu measured + ref §4.4
- [ ] §4.3 bảng ước tính → bảng measured (đúng số trong §2 của proposal này)
- [ ] §4.4 Provenance đã thêm với đủ refs (gồm `answer_tokens.csv`)
- [ ] §4.5 bảng k_true đã thêm; bảng k quy ước §4.1 được đánh dấu superseded
- [ ] Bảng per-domain đã chèn, số khớp byte-for-byte với `domains.csv`
- [ ] Chạy lại `python3 tools/antigravity_ledger/extract.py` — số in ra khớp số trong issue
- [ ] Không còn bất kỳ con số "~80M–100M" hoặc "1:500" nào present ở dạng ước tính không nhãn

## 6. Caveats trung thực (đi kèm bản cập nhật)

- Phạm vi số liệu: 78 phiên thuộc cửa sổ campaign 15–20/09 (`sessions.csv`).
- Ranh giới Solving/Orchestration: phân loại theo persona của phiên (expert/subagent giải bài → solving; điều phối, tiến độ, report → orchestration). Tỷ trọng orchestration 29,4% là chi phí thật của harness dạng IDE tổng quát — số liệu nền cho luận điểm "harness chuyên dụng cần nén chi phí điều phối".
- Mẫu số distilled (10.989 tokens) là đo tokenizer thật trên từng đáp án (`answer_tokens.csv`) — quy ước k 1,30–1,45 của §4.1 đã superseded.
- Leverage trên distilled (1:5.375) mang ý nghĩa giới hạn do mẫu số là đáp án 1 token (trắc nghiệm); chi phí thật của tác vụ nằm ở đa bước suy luận (thinking = 57,9% output), không ở độ dài đáp án.
- Phạm vi áp dụng: toàn bộ metric accuracy + distilled leverage chỉ có trên dataset đáp án đóng có gold. Task tự luận (generation tự do) nằm ngoài phạm vi Issue #10; với task đó chỉ đo được net tokens/câu + leverage raw response, chất lượng cần rubric/LLM-judge.
- `aux_f1`/`aux_f6` trong telemetry là hằng số config (1.318 / {0,24}), không phải usage — đã loại khỏi mọi phép tính.
- Wall-clock: ĐÃ TRÍCH — tổng 6,92h cho 1.389 câu (~18s/câu), per-domain trong §4.4 (span = mtime DB − epoch step-start, đã verify). Per-call duration KHÔNG có từ telemetry (trường f12.2 không xác định danh tính → aux_f12, loại khỏi claims).
- Attribution dừng ở per-batch; per-item khả thi sau bằng so khớp câu hỏi trong `step_payload`.

## 7. Tài liệu tham chiếu

- `tools/antigravity_ledger/extract.py` — script trích xuất (T1 reproducibility)
- `tools/antigravity_ledger/calibrate_k.py` — đo tokenizer thật trên từng đáp án (thay quy ước k)
- `tools/antigravity_ledger/README.md` — provenance chain + bản đồ field protobuf
- `all_res/antigravity_resource_ledger/*.csv` — 6 ledger files (gồm `answer_tokens.csv`)
- `vmlu_docs/03_systems_and_infra/GROUND_TRUTH_RESOURCE_MEASUREMENT_SPEC.md` — hợp đồng 3 trục
- `vmlu_docs/02_upper_bound_campaign/GITHUB_ISSUE_UPPER_BOUND_18_BATCHES.md` — đích cập nhật
