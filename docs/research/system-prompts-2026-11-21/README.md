# System prompt của omp và dsh trong các card agent luật (MC-112 đến MC-117)

Ngày 2026-11-21. Thư mục này lưu **nguyên văn** system message đầu tiên mà model nhận được ở mỗi nhánh. Mỗi file được lấy từ `body_received` của request đầu tiên trong `proxy_log.jsonl` của một lượt chạy thật. SHA-256 bên dưới trùng với pin mà proxy kiểm tra trên mọi request đầu tiên của các card đó.

| File | Nhánh | Model | Ký tự | SHA-256 | Lấy từ |
|---|---|---|---:|---|---|
| `omp_default_qwen.txt` | OMPF (omp 18.0.0, prompt mặc định) | Qwen3.5-9B-65K | 8.641 | `3d04a885…` | MC-113, `LG-0001:OMPF-r1` |
| `omp_default_mimo.txt` | OMPF | mimo-v2.6-flash | 8.644 | `616bebaf…` | MC-116, `BIDLQA-TR-0002:OMPF-r1` |
| `dsh_qwen.txt` | DSHF (dsh 0.2.2-rc.1) | Qwen3.5-9B-65K | 441 | `d6bd65aa…` | MC-112, `LG-0001:DSHF-r1` |
| `dsh_mimo.txt` | DSHF | mimo-v2.6-flash | 442 | `54d89951…` | MC-116, `BIDLQA-TR-0002:DSHF-r1` |
| `omps_qwen.txt` | OMPS (omp với `--system-prompt` = prompt dsh) | Qwen3.5-9B-65K | 1.104 | `b868301f…` | MC-117, `BIDLQA-TR-0002:OMPS-r1` |
| `omps_mimo.txt` | OMPS | mimo-v2.6-flash | 1.108 | `32a43405…` | MC-117, `BIDLQA-TR-0002:OMPS-r1` |

**Khác biệt giữa hai model.** Hai bản omp chỉ khác nhau ở dòng `- Model:` trong khối `<workstation>`. Hai bản dsh chỉ khác nhau ở tên model trong câu thứ hai.

**Thông tin máy.** Khối `<workstation>` của omp ghi hệ điều hành, kernel, CPU và GPU của máy chạy. Không có tên người dùng, tên máy hay đường dẫn cá nhân. Khối này được giữ nguyên văn vì pin SHA-256 phụ thuộc vào nó.

**Phần lượt người dùng.** Câu lệnh của từng câu hỏi giống từng byte ở cả ba nhánh. omp chèn thêm trước câu lệnh một `<system-reminder>` gồm ngày chạy và thư mục làm việc. dsh không chèn gì.

## So sánh theo thành phần

| Thành phần | omp mặc định (OMPF) | dsh (DSHF) | OMPS |
|---|---|---|---|
| Độ dài | 8.641–8.644 ký tự, khoảng 150 dòng | 441–442 ký tự, 4 đoạn | 1.104–1.108 ký tự |
| Vai trò | *"Helpful, trusted assistant for load-bearing changes in Oh My Pi coding harness"* | *"You are an AI agent powered by DeepSeek Harness. You are a coding agent powered by the <model> model."* | Như dsh |
| Quy ước | Khối `<system-conventions>`: RFC 2119 (MUST, SHOULD, NEVER = MUST NOT…), thẻ XML là chỉ thị hệ thống | Không | Không |
| **Chỉ dẫn đọc file** | Một dòng trong mục `# Exploration`: *"NEVER open files hoping. AVOID unneeded files/sections. Use `read` offset/limit, not whole-file reads."* | *"Use the read tool — not shell commands like cat — to inspect text files. Use offset and limit to continue reading large files."* | Như dsh |
| Chỉ dẫn grep | *"Regex search/target location → `grep`, not shell `grep`, `rg`, `awk`."* | *"Use the grep tool — not shell grep or rg — to search file contents. Use read on a matched file when you need surrounding context."* | Như dsh |
| Chỉ dẫn glob | *"Structure mapping/globbing → `glob`"* | *"Use the glob tool — not shell find — to discover files by path pattern."* | Như dsh |
| Dùng công cụ nói chung | *"NEVER accept first plausible answer when another call reduces uncertainty; retry empty/partial/suspiciously narrow lookup differently."*; *"SHOULD parallelize independent calls."* | Không | Không |
| **Định dạng và độ dài câu trả lời** | `# Personality`: *"Evidence-first terse engineer"*; `# Tone`: *"no ceremony, hedging, summaries, filler, marketing"*, *"Conclusion first; evidence next"*; `<evidence-and-output>`: *"Format MUST match ask; prose brief"* | **Không có** | **Không có** |
| Quy trình lập trình | Các mục `§ Workflow` (scope, research, implement, verify, cleanup), `<contract>`, `<completeness>`, `<yielding>`, tài liệu về URL nội bộ (`skill://`, `agent://`, `pr://`…) | Không | Không |
| `<critical>` giữa prompt | *"NEVER yield while actionable work remains…"*, *"NEVER narrate/consider session limits…"*, *"NEVER re-audit applied edit…"* | Không | Không |
| `<workstation>` | Có (OS, kernel, CPU, GPU, model) | Không | Có (omp tự nối) |
| `<critical>` cuối prompt | *"Each response MUST advance the task…"*, *"MUST default to informed action…"*, *"Before yielding, MUST verify significant behavioral changes: run the specific test…"* | Không | Có (omp tự nối) |

## Ba điểm khác biệt có liên quan đến kết quả

1. **Chỉ dẫn đọc: cả hai đều nhắc offset và limit, nhưng khác hướng và khác độ nổi bật.**
   - dsh dặn dùng offset và limit **để đọc tiếp** file lớn. Câu này là một trong bốn đoạn của prompt.
   - omp dặn **đọc hẹp** ("not whole-file reads") và **tránh** phần không cần ("AVOID unneeded files/sections", "NEVER open files hoping"). Dòng này nằm giữa khoảng 150 dòng quy ước lập trình.
   - Trong OMPF, 32% (trắc nghiệm) và 42% (ViBidLQA) số lần đọc của Qwen không có offset/limit, nên omp tự cắt trang. Trong OMPS, các con số này giảm còn 13% và 20%.
2. **Định dạng câu trả lời: chỉ omp có chỉ dẫn.** *"Format MUST match ask; prose brief"* và *"terse"* khớp với yêu cầu của câu lệnh (*"Chỉ đưa ra chữ cái…"*, *"…một cụm từ hoặc số ngắn gọn"*). Prompt dsh không nói gì về định dạng. Tỉ lệ câu trả lời trắc nghiệm chỉ gồm một chữ cái:
   - Qwen: 65,7% ở OMPF, 42,1% ở DSHF, 42,3% ở OMPS.
   - MiMo: 88,8% ở OMPF, 75,0% ở DSHF, 78,0% ở OMPS.
3. **Thứ omp vẫn giữ trong OMPS.** `<workstation>` và khối `<critical>` cuối, với các chỉ thị hành động kiểu agent lập trình ("run the specific test…"), vẫn còn. Lượt người dùng vẫn có `<system-reminder>`. MC-117 không tách được ảnh hưởng của những phần này.

Các con số ở trên lấy từ `all_res/diagnostic_legal_agent_omp_prompt/explore/omp_prompt_followup.json` và `all_res/diagnostic_legal_agent_omp_prompt/flows/flow_report.json`. Diễn giải đầy đủ nằm ở `docs/research/legal-agent-omp-prompt-followup-2026-11-21.md` và `docs/research/legal-agent-flows-mc117-2026-11-21.md`.
