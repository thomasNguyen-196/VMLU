# Chuẩn Hóa Phương Pháp Đo Lường Tài Nguyên Thực Tế (Ground-Truth Resource Consumption Specification)

- **Trạng thái**: Đã đóng băng hợp đồng đo lường (Frozen Measurement Contract)
- **Tài liệu lưu trữ**: `vmlu_docs/03_systems_and_infra/GROUND_TRUTH_RESOURCE_MEASUREMENT_SPEC.md`
- **Ngày hoàn tất kiểm chứng**: 05/10/2026
- **Đối tượng áp dụng**: Mọi kịch bản đánh giá mô hình tiếng Việt (VMLU, V-Bench, Reading-400), đối sánh giữa Closed Model (Gemini 3.8 Flash) và Open-Weight Models (Qwen) kết hợp Agentic Harness.

---

## 1. Tuyên Bố Nguyên Tắc: Tách Rời Đo Đạc Kỹ Thuật & Mô Hình Định Giá

Nguyên tắc cốt tử của nghiên cứu là **phân định rạch ròi giữa 2 giai đoạn**:
1. **Giai đoạn đo đạc (Technical Measurement)**: Thu thập 100% dữ liệu thực nghiệm khách quan từ hệ thống (Tokens thực tế, Thời gian thực tế, Lượt gọi công cụ thực tế). **Tuyệt đối không dùng công thức ước tính lý thuyết** khi đã có thể đo đạc trực tiếp.
2. **Giai đoạn định giá (Economic Mapping)**: Sau khi đã có bộ dữ liệu tài nguyên bất biến ở Giai đoạn 1, bất kỳ bảng giá nào (Gói sinh viên \$5/tháng, bảng giá CommandCode, bảng giá Google AI Studio Standard, hay DeepInfra Serverless) đều có thể được áp vào sau bằng các phép tính số học thuần túy mà không làm thay đổi bản chất kỹ thuật của thí nghiệm.

---

## 2. Ba Trục Metric Hiệu Năng Đóng Băng (Frozen 3-Axis Metric Contract)

Mỗi bài toán hoặc lượt giải quyết câu hỏi trong benchmark bắt buộc phải ghi nhận đủ 3 trục độc lập sau:

```
                            BỘ 3 TRỤC TÀI NGUYÊN (GROUND TRUTH)
                                            │
        ┌───────────────────────────────────┼───────────────────────────────────┐
        ▼                                   ▼                                   ▼
 [TRỤC 1: TOKEN CONSUMPTION]     [TRỤC 2: COMPLETION TIME]         [TRỤC 3: TOOL INVOCATIONS]
  - Fresh Input Tokens            - Wall-Clock Latency (giây)       - Python REPL count
  - Cached Read Tokens            - Tự động bao hàm:                - CSP Solver count
  - Output Tokens                   * LLM inference time            - Schema Verifier count
  - Thinking / Reasoning Tokens     * Tool execution time           - Statutory Search count
  - Total Token Footprint           * Retry & Network I/O
```

### Chi tiết định nghĩa từng trục:

### 🔹 Trục 1: Tiêu Thụ Token (Token Consumption Breakdown)
Được trích xuất trực tiếp từ metadata phản hồi của API ở mỗi lượt tương tác:
* **Fresh Input Tokens ($T_{\text{in\_fresh}}$)**: Lượng token đầu vào mới chưa có trong cache.
  $$T_{\text{in\_fresh}} = \text{prompt\_tokens} - \text{cached\_tokens}$$
* **Cached Read Tokens ($T_{\text{cached}}$)**: Lượng token được đọc lại từ tiền tố ngữ cảnh đã lưu trong bộ đệm.
  $$T_{\text{cached}} = \text{usage.prompt\_tokens\_details.cached\_tokens}$$
* **Output Completion Tokens ($T_{\text{out}}$)**: Lượng token nội dung phản hồi do mô hình sinh ra.
  $$T_{\text{out}} = \text{usage.completion\_tokens}$$
* **Thinking / Reasoning Tokens ($T_{\text{think}}$)**: Lượng token suy luận nội tâm ẩn của mô hình (đặc biệt quan trọng với `gemini-3.8-flash-high` và các dòng reasoning model).
  $$T_{\text{think}} = \text{usage.completion\_tokens\_details.reasoning\_tokens}$$
* **Tổng Không Gian Token ($T_{\text{total}}$)**:
  $$T_{\text{total}} = \sum (\text{Fresh Input} + \text{Cached Input} + \text{Output} + \text{Thinking})$$

### 🔹 Trục 2: Thời Gian Hoàn Thành (Wall-Clock Completion Time)
Đo bằng đồng hồ chính xác cao `time.perf_counter()` từ thời điểm bắt đầu khởi tạo phiên xử lý câu hỏi đến khi ghi nhận kết quả cuối cùng:
$$\Delta t = t_{\text{end}} - t_{\text{start}}\quad (\text{đơn vị: giây, làm tròn } 3 \text{ chữ số thập phân})$$
* Metric này phản ánh trung thực toàn bộ độ trễ thực tế: Thời gian suy luận của LLM + Thời gian môi trường Python REPL chạy mã / giải hệ CSP + Thời gian sửa lỗi cú pháp (retry) + Độ trễ truyền tải mạng (I/O).

### 🔹 Trục 3: Tần Suất Kích Hoạt Công Cụ (Tool Invocations)
Ghi nhận số lần từng công cụ ngoại vi được kích hoạt để giải quyết bài toán:
* `tools.python_repl`: Số lần chạy môi trường tính toán số học, giải tích, modulo, ma trận.
* `tools.csp_solver`: Số lần giải hệ ràng buộc logic vị từ và lập bảng chân trị.
* `tools.schema_verifier`: Số lần kiểm tra và sửa lỗi cú pháp JSON / Arguments.
* `tools.statutory_grounding`: Số lần tra cứu đối soát điều khoản văn bản quy phạm pháp luật.

---

## 3. Môi Trường Thực Nghiệm & Cấu Hình Provider (Empirical Provider Setup)

* **Nhà cung cấp Gateway / Proxy**: `commandcode.ai`
* **Giao thức kết nối**: Chuẩn OpenAI-Compatible REST API
* **Base URL**: `https://api.commandcode.ai/provider/v1`
* **Mô hình định danh**: `google/gemini-3.8-flash`
* **Cấu hình Reasoning**: Mặc định hoạt động ở mức suy luận sâu (`Dynamic / High Reasoning Effort`).
* **Thư viện thực thi**: `openai` Python SDK (v1.x).

---

## 4. Các Phát Hiện Thực Nghiệm Cốt Lõi (Key Empirical Findings)

Qua quá trình chạy probe thực tế trên hệ thống của CommandCode, nhóm nghiên cứu đã xác minh được các đặc tính kỹ thuật mang tính bước ngoặt:

### 4.1. Bóc Tách Thành Công Thinking Tokens
Khác với các proxy thông thường hay nuốt mất metadata suy luận, `commandcode.ai` **forward nguyên vẹn 100% trường `reasoning_tokens`** từ Google về:
```json
"completion_tokens_details": {
  "reasoning_tokens": 213,   // Ghi nhận chính xác số token suy luận ẩn
  "accepted_prediction_tokens": null
}
```
* Kết quả thực nghiệm ghi nhận dao động từ **213 tokens đến 2.910 tokens thinking** tùy theo độ phức tạp của bài toán logic/toán học, chứng minh mô hình thực sự kích hoạt cơ chế suy luận chuyên sâu.

### 4.2. Khám Phá Hai Điều Kiện Kích Hoạt Caching Qua CommandCode
Trong thử nghiệm ban đầu với prompt ngắn (95 tokens và 2.368 tokens), `cached_tokens` luôn trả về bằng `0`. Sau khi đối chiếu tài liệu nội bộ và kiểm chứng thực nghiệm, hệ thống xác nhận **2 điều kiện bắt buộc để kích hoạt Cache Hit**:

1. **Ngưỡng độ dài ngữ cảnh tối thiểu (Context Length Threshold)**:
   * Google Gemini 3.8 Flash áp đặt quy tắc cứng: **Prompt phải đạt tối thiểu $\ge 4.096$ tokens** thì hệ thống mới nạp vào bộ đệm TPU. Dưới ngưỡng này, 100% request sẽ là Fresh Input.
2. **Cấu trúc vòng lặp tác tử (Agent Loop Multi-Turn Continuity)**:
   * Caching chỉ được ghi nhận khi các lượt gọi nằm trong một chuỗi hội thoại tiếp nối, giữ nguyên toàn bộ lịch sử (System Context + Turn 1 User + Turn 1 Assistant Response + Turn 2 User).

### 4.3. Bằng Chứng Thực Nghiệm Đã Được Kiểm Chứng (Proof of Concept)
Thực nghiệm kiểm chứng tại `tools/probe_token_usage/test_cache_probe.py` với văn bản luật 9.709 tokens đã cho kết quả thực tế không thể chối cãi:

```text
📡 [LẦN 1] Gửi ngữ cảnh văn bản luật (>5.000 tokens):
✅ Lần 1 hoàn tất trong 7.36s: prompt_tokens = 9.709 | cached_tokens = 0

📡 [LẦN 2] Gửi tiếp câu hỏi trong Agent Loop giữ nguyên ngữ cảnh:
✅ Lần 2 hoàn tất trong 28.24s: prompt_tokens = 9.775 | cached_tokens = 4.075 🎯
```
* **Kết luận thực nghiệm**: Hệ thống đã tái sử dụng thành công **4.075 cached tokens**, chứng minh khả năng đo đạc chính xác chi phí Cache Read trong các vòng lặp tác tử đa lượt (multi-turn harness).

---

## 5. Phương Pháp Code Kỹ Thuật Chuẩn Hóa (Standardized Measurement Code)

Để áp dụng đồng bộ vào mọi pipeline runner (`run_mc_eval.py`, `run_vbench_eval.py`, `run_reading_eval.py`), đoạn code kỹ thuật chuẩn sau đây được đóng băng:

```python
import time
from openai import OpenAI

def execute_measured_agent_step(client: OpenAI, model: str, messages: list[dict], tool_tracker: dict) -> dict:
    """
    Thực thi một bước gọi mô hình và thu thập đầy đủ 3 trục tài nguyên.
    """
    t_start = time.perf_counter()
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    
    wall_time_s = round(time.perf_counter() - t_start, 3)
    usage = response.usage
    
    # ── TRỤC 1: BÓC TÁCH TOKEN NGUYÊN BẢN ───────────────────────────
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    
    # Cache details
    p_details = getattr(usage, "prompt_tokens_details", None)
    cached_tokens = getattr(p_details, "cached_tokens", 0) or 0 if p_details else 0
    fresh_input_tokens = max(0, prompt_tokens - cached_tokens)
    
    # Thinking details
    c_details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = getattr(c_details, "reasoning_tokens", 0) or 0 if c_details else 0
    
    total_tokens = prompt_tokens + completion_tokens
    
    # ── ĐÓNG GÓI LEDGER ROW ─────────────────────────────────────────
    return {
        "wall_time_s": wall_time_s,
        "fresh_input_tokens": fresh_input_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "raw_response": response.choices[0].message.content,
        "tool_invocations": dict(tool_tracker),
    }
```

---

## 6. Phụ Lục: Tổng Quan Cơ Chế Caching Của Google Gemini (Tham Khảo Thêm)

Phần này ghi chú chi tiết kỹ thuật từ tài liệu chính thức của Google Gemini API nhằm phục vụ công tác đối chiếu học thuật:

### A. Implicit Caching (Bộ đệm ẩn / Tự động)
* **Nguyên lý**: Được bật mặc định cho toàn bộ các dòng mô hình từ Gemini 2.5 trở lên. Hệ thống tự động nhận diện các tiền tố (prefix) trùng khớp trong request để chuyển sang tính giá đọc cache mà lập trình viên không cần cấu hình thêm.
* **Ngưỡng kích hoạt tối thiểu (Min Token Limits)**:
  * `Gemini 3.8 Flash`: **4.096 tokens**
  * `Gemini 3.7 Flash`: **4.096 tokens**
  * `Gemini 3.6 / 3.5 Flash`: **4.096 tokens**
  * `Gemini 2.5 Flash / Pro`: **2.048 tokens**
* **Đặc tính phục vụ**: Mang tính cơ hội (*opportunistic*). Bộ đệm được lưu trữ trực tiếp trên bộ nhớ HBM/SRAM của cụm TPU; nếu cụm quá tải hoặc hết hạn thời gian nhàn rỗi, bộ đệm có thể bị thu hồi (evict).

### B. Explicit Caching (Bộ đệm tường minh / Chủ động)
* **Nguyên lý**: Chỉ hỗ trợ trên giao thức `GenerateContent API` của Google (không hỗ trợ trên Interactions API). Người dùng chủ động gửi một tài liệu lớn (sách, video, văn bản luật) qua `client.caches.create()` và nhận về một `cache_id`.
* **Chi phí**: 
  * Chi phí đọc cache: Giảm 90% so với giá input thông thường (\$0.075 / 1M tokens đối với Gemini 3.8 Flash).
  * Chi phí lưu trữ bộ đệm (Storage TTL): Bị tính phí duy trì theo thời gian (\$0.50 / 1.000.000 tokens mỗi giờ).
* **Mức độ tương thích với Aggregator**: Các proxy đa nhà cung cấp (như CommandCode, 9router, OpenRouter) hiện tại **chỉ hỗ trợ Implicit Caching** thông qua cơ chế tự động khớp tiền tố của Agent Loop, không hỗ trợ quản lý vòng đời Explicit Cache ID độc lập.
