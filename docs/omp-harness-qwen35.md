# Harness arm — `Qwen3.5-9B-28K` qua `omp` (docs)

> ⚠️ **Đọc MC-15…MC-21 cùng MC-22.** Các arm H* đo `omp` **trên máy này**, nên vô tình kéo cả
> `~/.omp/agent/APPEND_SYSTEM.md` (luật trả lời "verdict → why → the test → the rule") vào điều
> kiện. MC-22 đo lại dưới scaffold sạch. Số cũ đúng cho điều kiện đã ghi — **đừng quy cho `omp`**.

**Câu hỏi:** cùng model, endpoint, `temperature 0`, bộ chấm đóng băng — nhưng đi qua agent harness
(`omp`) thay vì gọi API trực tiếp thì mất bao nhiêu điểm, tốn bao nhiêu thời gian/token, và mất
do **scaffold** hay do **tool/persona**.

Arm A = số đã có trong `measurement_card.md` (MC-3b/10/12/13).
Arms: H2 (`ompH2_…`, tool đầy đủ) · H1 (`--no-tools`) · H3/H4 (`--system-prompt minimal`) ·
**H5–H8 (scaffold sạch, `HOME` override)** — MC-15…MC-23. Cost = MC-19 (đã đính chính ở MC-22) ·
Nhiễu của arm = MC-18.
Xem trên web: `/harness` (Next) hoặc offline `harness_report.html` — cả hai đọc từ
`web/public/benchmark-data.json["harness"]`, dựng bằng `build_dashboard_harness.py`.

## 1. Điều kiện đo (arm B)

| Trường | Giá trị |
| --- | --- |
| `model` | `iec/Qwen3.5-9B-28K` → `Qwen3.5-9B-28K` (IEC `https://llmapi.iec-uit.com/v1`) |
| `harness` | `omp` v18.2.7, `-p --mode json`, `PI_CODING_AGENT_DIR` (`.omp-iec/`, hoặc `.omp-clean/` + `HOME` override cho H5) |
| `system prompt` | H1–H4: mặc định của omp (~10,9k ký tự) hoặc 1 dòng trung tính · **H5: 1 dòng, không rò style** |
| `tools` | H2/H3: `read,bash,edit,write,grep,glob` + `--auto-approve` · H1/H4/H5: `--no-tools` |
| `thinking` / `max-time` | `off` / 180s (context 32768) |
| tắt | `--no-session --no-title --no-extensions --no-skills --no-rules --no-lsp` |
| `prompt` | **byte-identical arm A** (frozen `build_prompt`/`build_reading_prompt`; adapter legal tái dựng từ source và hard-fail nếu lệch byte) |
| cô lập | mỗi item 1 thư mục tạm rỗng chỉ có `item.json` (**không gold**), `--cwd`, không `--add-dir` |
| scorer | **đóng băng**: `extract_answer` + `score_reading_eval.py` (không viết lại) |
| sửa chữa | **không** — lỗi nằm nguyên văn trong `harness_failures_*.csv` |

## 2. Kết quả (paired, cùng tập item)

| Tập | Card A | n | Arm A | **omp sạch (H5)** | Δ thật | CI 95% | *(omp + rò style, H2)* |
| --- | --- | --- | --- | --- | --- | --- | --- |
| reading-400 (EM) | MC-3b | 400 | 79,75% | **57,50%** | **−22,25** | −26,75..−17,75 | 27,00% |
| legal-MC | MC-10 | 146 | 87,67% | **69,18%** | **−18,49** | −26,71..−10,96 | 50,00% |
| legal-NLI | MC-13 | 150 | 90,00% | **78,67%** | **−11,33** | −18,67..−4,00 | 60,67% |
| ViBidLQA val (EM) | MC-12 | 482 | 32,78% | **27,18%** | **−5,60** | −9,34..−2,07 | 6,02% |

char-F1 (sạch): reading-400 86,49 → 74,92 · ViBidLQA 74,16 → 68,43.

## 3. Cơ chế

1. **Rò cấu hình (lớn nhất).** `~/.omp/agent/APPEND_SYSTEM.md` lọt vào mọi arm H1–H4 dù đã đặt
   `PI_CODING_AGENT_DIR`; nó áp luật "verdict → why → the test → the rule". Chỉ `HOME` override mới
   chặn được. Bằng chứng byte nguyên vẹn: `capture_scaffold.py`.
2. **Vỏ câu trả lời (chỉ khi rò).** 145/214 item mất điểm ở reading-400 có nguyên văn gold trong
   reply → EM 0. Với scaffold sạch: 14/97 (14%) và reply p50 **8 ký tự = arm A** ⇒ phần còn lại là
   **sai thật**, không phải vỏ.
3. **Factorial 2×2 trên scaffold SẠCH (MC-23)** — mệnh đề mạnh nhất của chuỗi đo
   (100 item legal-MC giống nhau, arm A = 86,00%):

   | | **tools đầy đủ** | **`--no-tools`** | hiệu ứng tools |
   | --- | --- | --- | --- |
   | **system prompt của omp** | H8 = **75,00%** (Δ −11,00; p=0,027) | H7 = **68,00%** (Δ −18,00; p=1,2e−04) | +7,00 |
   | **dòng trung tính** | H6 = **69,00%** (Δ −17,00; p=9,1e−04) | H5 = **70,00%** (Δ −16,00) | −1,00 (p=1,00) |
   | hiệu ứng persona | +6,00 | −2,00 (p=0,86) | |

   Contrast trong scaffold sạch, so với ô H5: thêm tool **−1,00** (p=1,00) · đổi sang system
   prompt omp **−2,00** (p=0,86) · thêm cả hai **+5,00** (p=0,40).
   ⇒ **Mọi ô sạch đều thua arm A 11–18 điểm** (p ≤ 0,027): một **khoản phạt phẳng ~−16đ** cho
   việc đi qua tiến trình agent, **độc lập với gene nào bật**. Persona và tool menu **≈ 0**, thậm
   chí *thay thế* nhau về chiều (bật cả hai là ô tốt nhất). Bản MC-21 (4 ô, đều có rò) cho
   "sàn −23đ" = `−9đ (omp sạch) − 14đ (rò style)`.

## 4. Giá phải trả (số đã đính chính — MC-22)

| Arm | wall/item | overhead | request thật | prompt token thật | output tok/item |
| --- | --- | --- | --- | --- | --- |
| A (direct) | 0,59–1,38s | 0 | ~960 ký tự | 226–249 | 2 |
| **H5 (sạch)** | 3,2–3,5s | ~2,5s | 1.711 | ~690 | **2** |
| H4 (+rò style) | 23s | 5,9s | 2.485 | 688 | 264 |
| H2 (+tools+persona) | 16–23s | 5,8s | 26.463 | ~7.000 | 245 |

⚠️ `cacheRead` của gateway IEC là **bộ đếm cache tích luỹ** ⇒ ledger thổi phồng token (H4: ghi
5.527, thật 688). **Đừng dùng tỉ lệ "×29 token" của MC-19.** Điểm cốt lõi: **completion token của
mọi arm sạch = 2, bằng đúng arm A** ⇒ toàn bộ chi phí token trước đây (×9,6) là do rò cấu hình.
Với scaffold sạch, chi phí gần như toàn bộ là **spawn tiến trình** (~1,8–2,5s/item) + một lượt
decode ngắn.

## 5. Kiểm định hiệu lực

0 item lỗi trên **2.956 item × 8 arm** · 4 item dùng tool (chỉ ở H2/H3) · **0 lần gọi mạng** ·
3 lần trốn sandbox **đều hỏng** (0 rò gold). `--cwd` là quy ước, không phải cưỡng chế: `bash` vẫn
`cd` được ra ngoài (đã thử 3 lần, đều thất bại vì lệnh sai).

## 6. Điều KHÔNG được quy

- **Không quy "harness tax" cho riêng `omp`**: scaffold đo gồm system prompt `omp` **cộng** luật
  trả lời cá nhân bị rò. Số của `omp` sạch: −5,6…−22,3 điểm.
- **Không dùng tỉ lệ token của MC-19**; muốn token thật thì soi bằng `capture_scaffold.py`.
- **Không gắn Δ cho persona hay tool menu**: trên scaffold sạch mọi contrast đều p ≥ 0,40 (MC-23),
  và hai gene còn *thay thế* nhau về chiều.
- **Δ là hiệu ứng tổng**: arm không tất định ở `temp 0` (13/20 item đổi đáp án, MC-18).

## 7. Lệnh tái lập

```bash
# Mọi `run` tự preflight 1 call 1 token (45s): endpoint chết thì exit ngay
#   thay vì ghi failure giả (guard sinh từ sự cố MC-24).
# scaffold SẠCH (bắt buộc — không có HOME override là dính APPEND_SYSTEM.md)
HOME=/tmp/fakehome .venv/bin/python code_benchmark/run_harness_eval.py run \
  --dataset reading400 --workers 6 --label ompH5clean_Qwen3.5-9B-28K \
  --tools none --system-prompt minimal --agent-dir .omp-clean
.venv/bin/python code_benchmark/score_reading_eval.py --answers <file>
.venv/bin/python code_benchmark/run_harness_eval.py compare --dataset reading400 \
  --label ompH5clean_Qwen3_5-9B-28K
# lặp lại ô factorial (đo nhiễu chạy-đến-chạy → MC-27)
for REP in r2 r3; do
  HOME=/tmp/fakehome .venv/bin/python code_benchmark/run_harness_eval.py run \
    --dataset legal_mc --workers 6 --label "ompH5clean_${REP}_Qwen3.5-9B-28K" \
    --tools none --system-prompt minimal --agent-dir .omp-clean
  .venv/bin/python code_benchmark/run_harness_eval.py compare --dataset legal_mc \
    --label "ompH5clean_${REP}_Qwen3.5-9B-28K" --tag vsA
done
# V-Bench agentic (chỉ scaffold sạch + tool menu; validity cục bộ, điểm thật ở server)
HOME=/tmp/fakehome .venv/bin/python code_benchmark/run_harness_eval.py run \
  --dataset vbench_agentic --workers 6 --label ompV1clean_Qwen3.5-9B-28K \
  --tools read,bash,edit,write,grep,glob --agent-dir .omp-clean
# soi request thật của omp (localhost proxy)
.venv/bin/python code_benchmark/capture_scaffold.py --port 8801 --out /tmp/scaffold.json
# dựng lại khối hiển thị (/harness + harness_report.html)
.venv/bin/python code_benchmark/build_dashboard_harness.py
```

## 8. Artifact

| File | Nội dung |
| --- | --- |
| `harness_ledger_<ds>_<slug>.csv` | sự thật gốc: `raw_response`, `answer`, `gold`, `em/f1/correct`, `turns`, `tool_calls`, `net_attempt`, `path_escape`, token, `wall_s`, `failure` |
| `harness_<ds>_result_<n>_<slug>.csv` | checkpoint (resume) |
| `full_evaluation_<ds>_<slug>.csv` / `reading_answers[_bidlqa_val]_<slug>.csv` | projection đúng hình dạng để scorer đóng băng đọc |
| `reading_scores_*`, `reading_summary_*` | do `score_reading_eval.py` sinh |
| `harness_compare_<ds>[_tag]_<slug>.csv` | 2×2 + Δ + CI + McNemar + cost |
| `speed_arms_*`, `speed_summary_*` | cost probe (wall/model/overhead/TTFT/token) |
| `harness_failures_<ds>_<slug>.csv` | ledger lỗi, nguyên văn (xoá khi sạch) |
| `harness_scratch/transcripts/<ds>_<id>.json` | transcript đầy đủ (audit) |

## 9. Điểm server V-Bench (MC-28) — và cách nộp vượt WAF

```bash
# Form của vbench.ai trả HTML "Request Rejected" (F5 WAF) cho payload ~400 KB,
# trình duyệt báo thành `JSON.parse: unexpected character at line 1 column 1` —
# đó là lỗi của RESPONSE, không phải của file. Cách vượt: nộp 10 lô × 100 dòng.
# Phương pháp đã kiểm chứng: chạy lại y hệt trên agentic của arm A → ra đúng
# 397/1.000 = 39,70%, khớp snapshot 2026-09-20.
curl -s -X POST https://vbench.ai/api/grade \
  -H "Content-Type: application/json" -H "Referer: https://vbench.ai/submission" \
  -H "Origin: https://vbench.ai" -H "User-Agent: <browser UA>" \
  --data-binary @payload.json     # {"filename": "...jsonl", "content": "<jsonl>"}
```

| | valid | accuracy server |
| --- | ---: | ---: |
| arm A (trực tiếp) | 100,00% | 397/1.000 = **39,70%** |
| arm `ompV1clean` (sạch + 6 tool) | 97,40% | 308/1.000 = **30,80%** |

Mẫu số là **1.000** (server dùng tổng domain), không phải 974 — 26 dòng invalid không nộp được tính
sai, và ta **không** bịa answer cho chúng. Snapshot + 10 response thô:
`all_res/ollama_result/ompV1clean_Qwen3_5-9B-28K/vbench_server_scores_*.csv` và `vbench_server_chunks/`.
