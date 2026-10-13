# Nghiên cứu: Kaggle "AI Quota" & khả năng tận dụng cho VMLU

- **Ngày research**: 13/09/2026
- **Trạng thái**: Chưa hành động — chờ follow up
- **Bối cảnh**: Quan sát thấy quota "AI" trong UI Kaggle; ban đầu nghi chỉ áp dụng cho Kaggle Benchmarks

---

## 1. AI quota là gì

Hạn mức **miễn phí dùng model frontier hosted qua backend Kaggle**, tính bằng **đô la**, tách biệt hoàn toàn với quota GPU (30h GPU/tuần).

Cấu trúc hạn mức (từ screenshot trong [issue #76 của kaggle-benchmarks](https://github.com/Kaggle/kaggle-benchmarks/issues/76)):
- **Daily AI Quota**: $10.00/ngày
- **Monthly AI Quota**: $100.00/tháng
- **Competition Quota**: $50 riêng cho competition tasks (issue #76 report bug: competition đang đốt nhầm quota thường — đã closed, assigned to Google dev)

Reset daily/monthly theo tên; giờ reset cụ thể chưa được document chính thức.

## 2. Quan trọng: không bó trong task Benchmarks chính thức

Model gọi được từ 2 nơi:

1. **Trong Kaggle notebook** — thư viện `kaggle-benchmarks` có sẵn:
   ```python
   import kaggle_benchmarks as kbench
   response = kbench.llm.prompt("...")   # kbench.llms["vendor/model-name"]
   ```
2. **Từ ngoài Kaggle** — model proxy là endpoint **OpenAI-compatible** (từ `local_development.md`):
   ```
   MODEL_PROXY_URL=https://mp-staging.kaggle.net/models/openapi
   MODEL_PROXY_API_KEY={per-user token}
   LLM_DEFAULT=google/gemini-2.5-flash
   LLMS_AVAILABLE=anthropic/claude-sonnet-4,google/gemini-2.5-flash,meta/llama-3.1-70b,google/gemini-2.5-pro
   ```

Model đã thấy trong docs/issues: `google/gemini-2.5-flash`, `google/gemini-2.5-pro`, `anthropic/claude-sonnet-4`, `meta/llama-3.1-70b` — danh sách thực tế tuỳ token được cấp.

## 3. Khả năng tận dụng cho VMLU

### a) Chạy VMLU trên model frontier miễn phí (đáng giá nhất)
- $10/ngày theo giá Gemini Flash (~$0.30/1M input token) ≈ hàng chục nghìn request → chạy hết MQA 10.880 câu vài lần/ngày mà không chạm trần.
- So sánh Qwen3-8-27B (local, đã có full eval) với Gemini/Claude trên VMLU — thí nghiệm mở rộng paper, **không đốt GPU quota**.
- Proxy OpenAI-compatible → runner hiện tại chỉ cần đổi `OPENAI_BASE_URL` + model name + token; toàn bộ frozen prompt/parser contracts (`build_prompt`/`extract_answer`) giữ nguyên.

### b) Publish VMLU thành Community Benchmark
- Kaggle đang đẩy [Community Benchmarks](https://blog.google/innovation-and-ai/technology/developers-tools/kaggle-community-benchmarks/): ai cũng tạo/chạy/chia sẻ benchmark riêng được → VMLU đúng use case.
- Lợi: lưu trữ chính thức, người khác chạy lại, leaderboard công khai.

### c) Không dùng được cho việc gì
- **Không host được Ollama/GGUF của mình** qua AI quota — nó chỉ gọi model hosted của Kaggle. Chạy Qwen3-8-27B Q4 vẫn cần GPU quota (30h/tuần) như hiện tại.

## 4. Rủi ro / cần kiểm chứng khi follow up

1. URL trong docs là `mp-staging` — production endpoint/token cần đăng ký qua Kaggle (xem cách lấy token: đâu trong UI, có cần waitlist không).
2. Điều khoản sử dụng: dùng cho benchmark riêng thuộc thiết kế sản phẩm, nhưng bơm traffic lớn qua proxy token cần đọc ToS; quota $10/ngày tự giới hạn nên rủi ro thấp.
3. Verify danh sách model thực tế trên token của mình + giá/đơn vị trừ quota (per-token hay per-request).
4. Kiểm tra việc gọi qua `kbench` có bắt buộc chạy trong task framework không, hay `llm.prompt()` đứng tự do được (ảnh hưởng cách adapt runner).
5. Test latency: proxy có nhanh đủ cho eval hàng loạt (workers 4) hay bị rate-limit per-user.

## 5. Kế hoạch follow up đề xuất

1. Đợi đợt full-eval Qwen3-8-27B chốt (commit nhánh `data/full-eval-qwen3-8-27b` + GitHub Issue).
2. Lấy token proxy Kaggle → smoke test 50 câu MQA bằng `google/gemini-2.5-flash` qua runner hiện tại (đổi base_url/model/token).
3. Đo: throughput thực tế, quota trừ bao nhiêu trên 50 câu, độ khớp parser (model frontier trả lời format VMLU ra sao).
4. Nếu OK → kế hoạch chạy full MQA trên 1-2 model frontier, cân nhắc publish VMLU Community Benchmark.

## Nguồn

- [Kaggle Benchmarks docs](https://www.kaggle.com/docs/benchmarks)
- [Google blog — Introducing Community Benchmarks](https://blog.google/innovation-and-ai/technology/developers-tools/kaggle-community-benchmarks/)
- [Repo Kaggle/kaggle-benchmarks](https://github.com/Kaggle/kaggle-benchmarks) (README, cookbook, quick_start, local_development.md, `tests/test_openai_client.py`)
- [Issue #76 — quota screenshot + competition bug](https://github.com/Kaggle/kaggle-benchmarks/issues/76)
- [Product announcement — Introducing Community Benchmarks](https://www.kaggle.com/product-announcements/667898)
