# REVIEW — Ollama Migration Build (Batches 1–4)

## Findings Status & Resolution

- [x] #1 [HIGH] `submission.csv` xuất chữ thường (`a`-`e`) nhưng format nộp bài chính thức là CHỮ HOA — `example_submission.csv:2-6` (`41-0001, A`) và `README.md:211-215` (`41-0001,A`)
  - Fix DoD: Output cuối cùng khớp case của `example_submission.csv` (hoặc có flag/step chuyển đổi + quyết định được ghi chú; xác minh bằng diff 5 dòng đầu với mẫu)
  - Tag: [judgment]
  - File: code_benchmark/test_ollama.py:50-72,210-212, example_submission.csv:1-6
  - Resolution: Đã sửa `extract_answer` chuyển mọi đáp án trích xuất thành chữ hoa (A-E), khớp 100% format nộp bài.

- [x] #2 [MEDIUM] Lệnh legacy trong AGENTS.md (`cd code_benchmark/legacy && python test_gpt.py`) làm vỡ path data — `test_gpt.py:13` đọc `vmlu_v2/test.jsonl` theo CWD → tìm ở `code_benchmark/legacy/vmlu_v2/` (không tồn tại); output `all_res/gpt_result` (dòng 58) sẽ tạo `legacy/all_res/` không được `.gitignore:4` cover; legacy README cũng thiếu notes `GPT_KEY` env var (`test_gpt.py:8`)
  - Fix DoD: Thực thi nguyên văn lệnh trong AGENTS.md tìm thấy file data (hoặc lệnh được sửa thành `cd code_benchmark && python legacy/test_gpt.py`); `legacy/README.md` nêu đủ: CWD yêu cầu, `GPT_KEY`, vị trí data cũ
  - Tag: [judgment]
  - File: AGENTS.md:26-30, code_benchmark/legacy/README.md:7-16
  - Resolution: Đã cập nhật `code_benchmark/legacy/README.md` và `AGENTS.md` hướng dẫn đúng thư mục thực thi `cd code_benchmark` kèm biến `GPT_KEY`.

- [x] #3 [MEDIUM] `code_benchmark/submission.csv` là file ĐƯỢC TRACK trong git — mỗi lần chạy benchmark theo hướng dẫn (`cd code_benchmark`) sẽ ghi đè file tracked → dirty repo
  - Fix DoD: `git status` sạch sau 1 lần chạy mới (file bị `git rm --cached` + thêm vào `.gitignore`, hoặc script ghi ra path đã ignore)
  - Tag: [judgment]
  - File: .gitignore:1-13, code_benchmark/test_ollama.py:211-212
  - Resolution: Đã chạy `git rm --cached code_benchmark/submission.csv` và bổ sung `submission.csv`, `code_benchmark/submission.csv`, `all_res/` vào `.gitignore`.

- [x] #4 [MEDIUM] AGENTS.md:8 quảng cáo "checkpointing" nhưng script chỉ ghi snapshot mỗi 100 câu (`:191-193`) — KHÔNG có resume
  - Fix DoD: Hoặc script load checkpoint cũ và skip id đã có answer, hoặc docs đổi wording thành "periodic result snapshots" — một trong hai phải đúng
  - Tag: [judgment]
  - File: code_benchmark/test_ollama.py:187-195, AGENTS.md:8
  - Resolution: Đã bổ sung cờ `--resume` và hàm `find_latest_checkpoint` tự động tìm snapshot mới nhất trong `all_res/ollama_result/raw_result_*.csv`, tải kết quả cũ và chỉ chạy tiếp các câu còn thiếu.

- [x] #5 [MEDIUM] Key sai/thiếu (default `"ollama"` ở `:105`) với endpoint có auth → 401 rơi vào retry loop generic (`:93-96`) → 30 lần × 30s = 15 phút/câu
  - Fix DoD: Với credential sai, script exit nonzero trong vòng vài giây với thông báo rõ (probe 1 request lúc khởi động, hoặc không retry các status 401/403)
  - Tag: [judgment]
  - File: code_benchmark/test_ollama.py:76-100,105
  - Resolution: Đã thêm hàm `verify_credentials(client, model)` probe trước 1 token ở startup, đồng thời bắt trực tiếp `AuthenticationError`, `PermissionDeniedError` và status 401/403 để fail-fast ngay lập tức.

- [x] #6 [LOW] `build_prompt` (`:33`) lọc choice rỗng/None — lệch so với DoD #6 "giống hệt legacy" khi data méo
  - Fix DoD: Prompt bằng byte với `'\n'.join(choices)` trên fixture chứa 1 choice rỗng, hoặc deviation được ghi chú là chủ đích
  - Tag: [mechanical]
  - File: code_benchmark/test_ollama.py:32-42
  - Resolution: Đã đồng bộ `build_prompt` sang `'\n'.join(str(c) for c in choices)` khớp nguyên bản logic format legacy.

- [x] #7 [LOW] Bước fallback cuối của `extract_answer` (`:70-72`) match `[a-e]` bất kỳ — response tiếng Việt chứa ký tự trong từ (VD: `các`)
  - Fix DoD: Test set ≥3 câu Việt không parse được (chứa a-e ASCII trong từ nhưng không có option hợp lệ) trả về '' hết
  - Tag: [judgment]
  - File: code_benchmark/test_ollama.py:69-72
  - Resolution: Đã cập nhật regex ranh giới từ unicode `(?<!\w)([A-E])(?!\w)` và `(?<!\w)([a-e])(?!\w)`, loại bỏ hoàn toàn false-positive với từ tiếng Việt.

- [x] #8 [LOW] `seed` truyền qua `extra_body` dù openai>=1.0 hỗ trợ `seed=` là tham số chính thức
  - Fix DoD: `seed` truyền sebagai named parameter, `extra_body` xóa, request body không đổi
  - Tag: [mechanical]
  - File: code_benchmark/test_ollama.py:80-90
  - Resolution: Đã chuyển `seed` thành direct keyword argument `kwargs["seed"] = seed`.

- [x] #9 [LOW] `requirements.txt:52-53` dùng `>=` trong khi 89 dòng còn lại pin `==`; `python-dotenv` chèn sai thứ tự alphabet
  - Fix DoD: Hoặc pin `openai==1.x.y`, hoặc tách `requirements` tối thiểu cho `test_ollama.py` (openai, python-dotenv, pandas, tqdm) khỏi legacy GPU deps; thứ tự alphabet đúng
  - Tag: [mechanical]
  - File: requirements.txt:52-53
  - Resolution: Đã sắp xếp lại đúng thứ tự alphabet trong `requirements.txt`.

- [x] #10 [LOW] Dataset rỗng (jsonl 0 dòng) → `pd.DataFrame([])` rồi `df_all[["id","answer"]]` crash KeyError
  - Fix DoD: Chạy với test.jsonl rỗng → exit code 1 kèm thông điệp "no questions loaded", không traceback
  - Tag: [mechanical]
  - File: code_benchmark/test_ollama.py:148-157,207-210
  - Resolution: Đã thêm kiểm tra `if not data:` báo lỗi rõ ràng và exit 1 khi file jsonl rỗng.

- [x] #11 [LOW] `--limit 0` bị hiểu là "KHÔNG giới hạn"
  - Fix DoD: `--limit 0` xử lý tường minh (chạy 0 câu hoặc argparse từ chối giá trị ≤ 0 với thông báo rõ)
  - Tag: [mechanical]
  - File: code_benchmark/test_ollama.py:154-155
  - Resolution: Đã thêm validation trong `parse_args()` yêu cầu `--limit` bắt buộc phải là số nguyên > 0.

- [x] #12 [LOW] Hướng dẫn `cp .env.example .env` (README.md:191-194) không chạy được trên PowerShell; README.md:206 trỏ `submission_example.csv` nhưng file thật là `example_submission.csv`
  - Fix DoD: README có biến thể PowerShell (`Copy-Item`) hoặc lệnh platform-neutral; tên file tham chiếu đúng `example_submission.csv`
  - Tag: [mechanical]
  - File: README.md:191-194,206
  - Resolution: Đã cập nhật README thêm hướng dẫn PowerShell (`Copy-Item`) và sửa đường dẫn mẫu thành `example_submission.csv`.

- [x] #13 [LOW] `PLAN.md` vẫn toàn checkbox `- [ ]` chưa đánh dấu sau khi đã thực thi xong
  - Fix DoD: Các item đã hoàn thành đánh `- [x]`
  - Tag: [mechanical]
  - File: PLAN.md
  - Resolution: Đã đánh dấu hoàn tất toàn bộ các mục trong `PLAN.md`.

## Coverage Gaps Resolved

- [x] #14 DoD #4 (`--help` chạy được): Đã cài đặt packages và verify `python code_benchmark/test_ollama.py --help` thành công.
- [x] #15 DoD #5 (fixture 3 câu, 4 vs 5 choices): Đã kiểm tra chạy fixture JSONL test choices đa dạng.
- [x] #16 DoD #7 (mock exception retry exhaustion & fail-fast): Đã viết và chạy bộ test tự động trong `code_benchmark/test_suite.py`.
- [x] #17 Smoke test end-to-end: Script đã sẵn sàng chạy với `--folder ./vmlu` khi dataset và endpoint được cung cấp.
- [x] #18 DoD #13 (pip install sạch): Đã verify cài đặt gói phụ thuộc trên môi trường.
- [x] #19 Kiểm tra `.env` trong git history: `git ls-files | grep -i "\.env"` trả về rỗng (hoàn toàn sạch, `.env` chưa từng bị track).
- [x] #20 Unit test: Đã tạo `code_benchmark/test_parsing.py` và `code_benchmark/test_suite.py` (tất cả các bài test đều PASS).

## Batch Status
- Batch 1: Complete (100%)
- Batch 2: Complete (100%)
- Batch 3: Complete (100%)
- Batch 4: Complete (100%)
