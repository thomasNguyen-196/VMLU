# Antigravity Resource Ledger (Arm A — Ground Truth)

Bộ ledger tài nguyên **thực đo** cho chiến dịch Upper Bound Ceiling (Issue #10),
trích trực tiếp từ telemetry local của Antigravity — thay thế con số ước tính
~80–100M tokens bị phê là "lạc đề" bằng dữ liệu nguyên bản từng lượt gọi LLM.

## Chuỗi tái lập (Extraction Reproducibility — tầng T1)

```
~/.gemini/antigravity/conversations/*.db   (85 file SQLite, raw telemetry)
            │  python3 tools/antigravity_ledger/extract.py   ← 1 lệnh, stdlib-only
            ▼
all_res/antigravity_resource_ledger/{llm_calls,sessions,batches,domains,excluded_sessions}.csv
```

- **Deterministic**: cùng DB đầu vào → byte-identical CSV.
- **Không tái thực thi**: script KHÔNG chạy lại campaign (T2) và không mô phỏng
  agent (T3) — nó chỉ đọc lại sự kiện đã được Antigravity ghi nguyên bản.
- Re-run protocol gốc của campaign: xem `vmlu_docs/02_upper_bound_campaign/`.

## Bản đồ trường protobuf (gen_metadata → field 1 = ChatModelMetadata)

| Đường | Ý nghĩa | Ghi chú |
|---|---|---|
| `f1.f4.{2,5,3,9,10}` | fresh_input / cache_read / output / thinking / response_out | usage nguyên bản từ Gemini API; field 5 vắng mặt khi = 0 (proto3) |
| `f1.f12.2` | **unidentified** (`aux_f12`) | KHÔNG dùng làm thời gian — vi phạm consistency với wall span (phiên 2,2 phút nhưng Σf12.2-as-µs = 42,5 phút) |
| `f1.f19` | model id (`gemini-3.8-flash`) | |
| `f1.f4.{1,6}` | **unidentified** (`aux_f1`, `aux_f6`) | KHÔNG dùng trong bất kỳ claim nào |
| `steps.metadata.f1.1` | epoch giây bắt đầu mỗi bước | ĐÃ VERIFY: khớp mtime DB; dùng làm wall start |
| `steps.metadata.f1.2` | **unidentified** | KHÔNG dùng (giá trị ~4×10⁸, không phải epoch/thời lượng) |
| `steps` + `executor_metadata` | đếm bước / lần thực thi công cụ | Trục 3 (proxy count) |
| **Trục 2 (wall-clock)** | wall_span = **mtime DB − epoch step đầu** | mtime ≈ lúc đóng phiên (verify trên phiên ngắn); per-call duration KHÔNG có từ telemetry |

## Luật attribution (lọc nhiễm — minh bạch, không im lặng)

- **Giữ**: persona expert/subagent khớp pattern (Anh + Việt), cửa sổ
  2026-09-14..21, workspace VMLU (hoặc rỗng = sub-conversation kế thừa).
- **Loại**: ghi đầy đủ vào `excluded_sessions.csv` kèm lý do
  (`outside_window` / `workspace_not_vmlu` / `no_campaign_persona`).
- `reading_mixed` (persona "Reading Comprehension" không hé DROP/SQuAD):
  phân loại tự định bằng cách đếm câu hỏi manifest (45 ký tự đầu) xuất hiện
  trong `step_payload` — đa số thắng, hòa → giữ nhãn mixed (trung thực).
- `orchestration`: phiên điều phối/tiến độ/report — là chi phí thật của
  campaign, tách riêng khỏi các domain giải bài, không trộn vào per-question.

## Kết quả chốt (campaign-filtered, 78 phiên / 4.461 lượt gọi)

- Fresh 54.426.971 · Cache 347.642.207 · Output 4.640.797 → **Net 59.066.768 tokens**
- Cache hit toàn cục **86,46%** (per-domain 74,5–90,9%)
- **Trục 2 (wall-clock)**: tổng **6,92 giờ** / 1.389 câu (~18s/câu); lịch 15/09 13:41 → 20/09 07:35 (4,7 ngày); phiên median 5,5 phút (mốc: epoch step đầu + mtime DB — per-call duration không có từ telemetry)
- ⚠️ Tổng trên TOÀN BỘ 85 file (chưa lọc) là 67,15M fresh / 391,9M cache —
  lệch ~18% so với số sạch; mọi trích dẫn trong luận văn dùng số đã lọc.

## Các điểm đã hồi giải (đã xác minh, không còn mở)

- **`aux_f1` / `aux_f6` KHÔNG phải usage**: aux_f1 = hằng số 1.318 trên cả
  4.461 records (config); aux_f6 ∈ {0, 24} (nghi vấn: số tool declarations
  mỗi request). Zero variance ⇒ zero thông tin tiêu thụ — loại khỏi mọi claim.
- **Reconcile 4.461 vs 4.908**: 4.908 = tổng blob gen_metadata của 85 file;
  **447 blob thuộc đúng 7 phiên bị loại** (FaceGate Aug, các phiên 22/09–05/10
  ngoài cửa sổ campaign) → ledger campaign = 4.461 calls, hoàn chỉnh 100%.
  (Bug parse ngưỡng field-id đã sửa trong extract.py.)
- **Lệch đếm 4.883 vs 4.908**: cách đếm của báo cáo thủ công; ledger dùng
  4.461 (campaign-filtered) làm số chính thức.

## Việc còn mở

- Attribution per-ITEM (1.389 câu): khả thi bằng so khớp văn bản câu hỏi
  trong `step_payload` với manifest/CSV — hiện ledger dừng ở per-batch (đủ
  cho bảng luận văn). Cần thêm khi muốn phân bố per-question.
- Phiên "Upper Bound Probe Progress" (92 blobs, modified 22/09 — sau cửa sổ
  campaign) đang bị loại; nếu xem là phần campaign thì mở rộng cửa sổ 1 dòng
  trong extract.py và chạy lại.
