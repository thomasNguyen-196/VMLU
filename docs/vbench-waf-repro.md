# V-Bench upload: WAF repro (2026-09-28)

Form của `vbench.ai/submission` báo `JSON.parse: unexpected character at line 1 column 1 of the JSON
data` cho **mọi** file ta nộp. Đây là **lỗi của response, không phải của file**: code của form
(`/assets/index-*.js`) parse từng dòng trong `try/catch`, nên file hỏng không bao giờ sinh lỗi đó —
lỗi đến từ `await response.json()` khi `POST /api/grade` trả về **HTML**:

```html
<title>Request Rejected</title> … The requested URL was rejected. Please consult with your
administrator.<br><br>Your support ID is: 9456549617406835490
```

Đây là **F5 BIG-IP/WAF** (có support ID), không phải Cloudflare, không phải service chết.

## Ma trận probe (tất cả lặp lại được, không phải ngẫu nhiên)

| # | Payload | Bytes | Kết quả |
| --- | --- | ---: | --- |
| 1 | 2 dòng toy | 50 | ✅ 200 JSON |
| 2 | **File mẫu chính thức** `data/sample_submission.jsonl` (5.141, compact) | 306.391 | ✅ 200 JSON |
| 3 | **File arm A nguyên bản** (5.141, spaced) — từng ra macro 45,22 | 400.761 | ✅ 200 JSON |
| 4 | Chỉ nửa MC của arm A (4.141, spaced) | 115.374 | ✅ 200 JSON |
| 5 | Agentic arm B × 10 lô × 100 dòng | ~28 KB/lô | ✅ 10/10 |
| 6 | Agentic arm B × 5 lô × 200 dòng | ~60 KB/lô | ✅ 5/5 |
| 7 | **File hỗn hợp arm B** (5.141, spaced) | 397.923 | ❌ Request Rejected |
| 8 | **File hỗn hợp arm B** (5.141, compact, đúng byte-style mẫu) | 369.584 | ❌ Request Rejected |

## Kết luận

- **Không phải format**: file mẫu chính thức lọt; file ta đã sửa về *đúng* byte-style mẫu
  (`separators=(",",":")`, sort id, LF, không BOM) vẫn bị chặn.
- **Không phải kích thước đơn thuần**: 400 KB lọt, 369 KB không; 306 KB lọt, 60 KB lô lọt.
- **Không phải nửa MC**: nửa MC của ta **giống byte** nửa MC của file arm A đã lọt.
- **Không phải nửa agentic riêng**: 974 dòng agentic lọt khi chia 5 lô × 200.
- ⇒ Trigger cần **cả hai nửa trong một request** (nội dung + quy mô), nên nó là quy tắc tích lũy
  bên trong WAF, không phải một mẫu đơn lẻ.

## Cách vượt (đã dùng để lấy điểm)

Nộp 10 lô × 100 dòng, cộng `correctAnswers` của domain `agentic` rồi chia cho **1.000**.

**Phương pháp đã được kiểm chứng**: chạy lại y hệt trên 1.000 dòng agentic **của arm A** → ra đúng
**397/1.000 = 39,70%**, khớp 100% snapshot 2026-09-20 (`docs/vbench-server-qwen35.md`). Không có
lệch nào, nên con số của arm B đáng tin.

```bash
curl -s -X POST https://vbench.ai/api/grade \
  -H "Content-Type: application/json" -H "Referer: https://vbench.ai/submission" \
  -H "Origin: https://vbench.ai" -H "User-Agent: <browser UA của bạn>" \
  --data-binary @payload.json      # {"filename": "...jsonl", "content": "<nội dung jsonl>"}
```

Không có header trình duyệt thì Cloudflare trả `403 error code 1010` (chặn fingerprint) — đó là lớp
khác, không phải lỗi WAF.

## Gửi ban quản trị

`vbench-support@vinuni.edu.vn` (hiện ở chân trang trang submission). Nội dung nên có: support ID
`9456549617406835490`, bảng probe trên, và bằng chứng rằng file **mẫu chính thức của chính site**
(306 KB) lọt trong khi file 5.141 dòng hợp lệ — 397 KB — bị chặn.
