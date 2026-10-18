# Probe Token Usage & Latency

Thư mục này dùng để kiểm tra thực tế xem một proxy / aggregator (như `commandcode.ai`, 9router, OpenRouter...) có forward đầy đủ các trường đo lường token và độ trễ hay không.

## Cách sử dụng

1. Mở file `.env` trong thư mục này:
   ```env
   COMMANDCODE_BASE_URL=https://api.commandcode.ai/v1
   COMMANDCODE_API_KEY=your_actual_key_here
   COMMANDCODE_MODEL=gemini-3.8-flash
   ```

2. Chạy script kiểm thử:
   ```bash
   .venv/bin/python tools/probe_token_usage/test_probe.py
   ```

3. Script sẽ tự động:
   - Đo thời gian phản hồi (Wall-clock time).
   - In nguyên bản cấu trúc `response.usage`.
   - Phân tích chi tiết: `prompt_tokens`, `completion_tokens`, `reasoning_tokens` (thinking), `cached_tokens` (cache hit).
   - Bắn tiếp request 2 để kiểm tra cache hit rate.
