# PLAN: Chuẩn hóa VMLU Benchmark sang Ollama & Cấu trúc lại Repository

## Batch 1 — Security & repo hygiene

- [x] #1 Thêm `.env` vào `.gitignore` (block `.env`, `.env.*`, giữ `.env.example`)
  - DoD: `git check-ignore .env` trả về path; `git status` không thấy `.env` là untracked
  - Tag: [judgment]
  - File: .gitignore
- [x] #2 Ignore thư mục data chuẩn hóa `vmlu/` (unanchored, match mọi độ sâu) trong cả `.gitignore` và `.ignore`
  - DoD: `git check-ignore vmlu/test.jsonl` và `code_benchmark/vmlu/test.jsonl` đều khớp
  - Tag: [mechanical]
  - File: .gitignore, .ignore
- [x] #3 Thêm comment hướng dẫn vào `.env.example` (giải thích `OPENAI_BASE_URL` phải trỏ endpoint `/v1` của Ollama, `OPENAI_API_KEY` là key của server trường)
  - DoD: file có đủ 3 biến + comment; không chứa key thật
  - Tag: [mechanical]
  - File: .env.example

## Batch 2 — `test_ollama.py` phần lõi

> Source context: prompt format kế thừa `code_benchmark/test_gpt.py:22-27`; retry logic kế thừa dòng 32-43.

- [x] #4 Scaffold script: argparse (`--folder ./vmlu`, `--temperature 0`, `--seed 42`, `--max-tokens 4`, `--workers 4`, `--limit`), `load_dotenv()`, client `OpenAI()` đọc `OPENAI_BASE_URL`/`OPENAI_API_KEY`, model từ `OPENAI_MODEL`
  - DoD: `python test_ollama.py --help` chạy được; thiếu env var thì báo lỗi rõ ràng và exit nonzero (không crash với traceback mơ hồ)
  - Tag: [judgment]
  - File: code_benchmark/test_ollama.py
- [x] #5 Load `test.jsonl` từ `--folder`, xử lý choices 4-5 phần tử, thiếu thì `''`
  - DoD: số row DataFrame == số dòng JSONL khi test với file giả 3 câu (2 câu 4 lựa chọn, 1 câu 5 lựa chọn)
  - Tag: [mechanical]
  - File: code_benchmark/test_ollama.py
- [x] #6 Prompt builder: giữ nguyên preamble + cấu trúc prompt như `test_gpt.py:22-27`
  - DoD: prompt sinh ra cho 1 câu mẫu giống hệt chuỗi prompt của legacy (so sánh string)
  - Tag: [mechanical]
  - File: code_benchmark/test_ollama.py
- [x] #7 Gọi API: `chat.completions.create` với `temperature`, `seed`, `max_tokens` từ CLI; retry tối đa 30 lần × sleep 30s khi exception
  - DoD: khi mock exception liên tục, vòng lặp dừng sau đúng 30 lần và ghi answer rỗng, script không chết giữa chừng
  - Tag: [judgment]
  - File: code_benchmark/test_ollama.py

## Batch 3 — Parsing, concurrency, output

- [x] #8 Parse answer: `re.search(r'[ABCDEabcde]', response)` — trích xuất A-E thông minh, trả về CHỮ HOA (A-E) khớp submission format
  - DoD: test với các response kiểu `"Đáp án đúng là B."`, `"A"`, `""` → ra `B`, `A`, `""`
  - Tag: [mechanical]
  - File: code_benchmark/test_ollama.py
- [x] #9 Chạy song song bằng `ThreadPoolExecutor` với `--workers`, tqdm hiển thị tiến độ
  - DoD: chạy `--limit 20 --workers 4` hoàn tất không lỗi race; kết quả đúng thứ tự id gốc
  - Tag: [judgment]
  - File: code_benchmark/test_ollama.py
- [x] #10 Checkpoint mỗi 100 kết quả (thread-safe, dùng lock) vào `all_res/ollama_result/raw_result_N.csv` + hỗ trợ resume `--resume`
  - DoD: checkpoint logic ghi đúng số dòng đã xử lý; resume đọc lại checkpoint và chỉ đánh giá các câu còn lại
  - Tag: [judgment]
  - File: code_benchmark/test_ollama.py
- [x] #11 Xuất `submission.csv` cuối (`id,answer`) + in runtime tổng
  - DoD: CSV chỉ 2 cột `id,answer`; mọi answer ∈ {A,B,C,D,E,''} ; in ra tổng thời gian
  - Tag: [mechanical]
  - File: code_benchmark/test_ollama.py

## Batch 4 — Legacy migration, deps, docs

- [x] #12 `git mv test_gpt.py test_prompt.py` → `code_benchmark/legacy/`; tạo `legacy/README.md` ghi chú: chạy legacy cần venv riêng pin `openai==0.28.0` + đường dẫn data cũ của từng script
  - DoD: `git status` hiện rename (không phải delete+add); nội dung 2 script byte-identical với trước khi move
  - Tag: [judgment]
  - File: code_benchmark/legacy/
- [x] #13 `requirements.txt`: đổi `openai==0.28.0` → `openai>=1.0.0`, thêm `python-dotenv>=1.0.0`
  - DoD: `pip install -r requirements.txt` sạch; `python -c "import openai; print(openai.__version__)"` ≥ 1.0
  - Tag: [mechanical]
  - File: requirements.txt
- [x] #14 Cập nhật README.md mục "How to Evaluate" (hỗ trợ cả POSIX và PowerShell): hướng dẫn setup `.env` + lệnh chạy mới `cd code_benchmark && python test_ollama.py`
  - DoD: README không còn trỏ tới `test_gpt.py` ở vị trí chạy được; có ví dụ `.env`
  - Tag: [mechanical]
  - File: README.md
- [x] #15 Cập nhật AGENTS.md phần Commands: thay lệnh benchmark cũ bằng `test_ollama.py`, ghi chú legacy
  - DoD: AGENTS.md phản ánh đúng cấu trúc thư mục mới sau khi move
  - Tag: [mechanical]
  - File: AGENTS.md

## Global Definition of Done

- Batch 1 -> Batch 2, 3 -> Batch 4.
- Smoke test script `test_ollama.py` với dummy test data và unit test suite (`code_benchmark/test_suite.py`, `code_benchmark/test_parsing.py`).
- Không để lộ `.env` chứa secret vào git (`git check-ignore` & `git ls-files` verified).
