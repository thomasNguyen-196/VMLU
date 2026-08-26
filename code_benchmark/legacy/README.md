# Legacy Benchmark Scripts

Thư mục này lưu trữ các benchmark scripts cũ nhằm mục đích lưu trữ và đối chiếu.

## Danh sách scripts

1. **`test_gpt.py`**:
   - Sử dụng OpenAI Python SDK cũ (`openai==0.28.0`).
   - Cần cấu hình biến môi trường `GPT_KEY="<YOUR_KEY>"`.
   - Đọc dữ liệu từ đường dẫn `vmlu_v2/test.jsonl` (tính từ thư mục `code_benchmark/`).
   - Gọi `openai.ChatCompletion.create`.
   - Cách chạy:
     ```bash
     cd code_benchmark
     GPT_KEY="<YOUR_KEY>" python legacy/test_gpt.py
     ```

2. **`test_prompt.py`**:
   - Chạy inference mô hình HuggingFace cục bộ bằng PyTorch và `transformers`.
   - Đọc dữ liệu từ `./vmlu_v1.5/test.jsonl` (mặc định theo `--folder`).
   - Cần cấu hình GPU / VRAM phù hợp với model cần đánh giá.
   - Cách chạy:
     ```bash
     cd code_benchmark
     python legacy/test_prompt.py --llm "bigscience/bloom-1b7" --folder "./vmlu_v1.5/" --device "cuda"
     ```

> **Khuyến nghị**: Sử dụng `code_benchmark/test_ollama.py` cho các lượt đánh giá mới với chuẩn hóa endpoint Ollama / OpenAI-compatible và dữ liệu `./vmlu/test.jsonl`.
