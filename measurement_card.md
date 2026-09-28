# Measurement Card — điều kiện đo

Mọi báo cáo, bảng điểm và kết luận rút ra trong repo này **phải trích dẫn file này**.
Một con số không có measurement card đi kèm thì không được đem so sánh với con số khác.

> **Quy tắc:** mỗi lần chạy = một khối bên dưới. Chạy mới thì **thêm khối mới**, không sửa khối cũ.
> Hash của file này (`measurement_card_hash`) phải được ghi vào output của mỗi lần chạy.

> ⚠️ **Đọc MC-15 → MC-21 cùng MC-22.** Các khối đó đo `omp` **trên máy này**, nên vô tình kéo cả
> `~/.omp/agent/APPEND_SYSTEM.md` (luật trả lời "verdict → why → the test → the rule") vào điều
> kiện; MC-22 đo lại dưới scaffold sạch và quy lại nhân quả. Số điểm cũ vẫn đúng cho điều kiện đã
> ghi, **nhưng đừng quy chúng cho riêng `omp`**.

---

## MC-1 — VMLU-MQA (đã chạy)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-1` |
| `ngay_chay` | 2026-08-31 (báo cáo 2026-09-03) |
| `benchmark` | VMLU-MQA, `vmlu_mqa_v1.5/all_gold.jsonl` (dev 303 + valid 744 = 1.047) |
| `model_id` | `Qwen3.8-27B-Q4_K_M.gguf` |
| `quantization` | Q4_K_M |
| `endpoint` | `https://llmapi.iec-uit.com/v1` (OpenAI-compatible) |
| `temperature` | 0.0 |
| `seed` | 42 |
| `max_tokens` | 4 |
| `workers` | 4 |
| `prompt_style` | `build_prompt` — zero-shot, no-CoT, trả lời bằng chữ cái |
| `prompt_template` | "Chỉ đưa ra chữ cái đứng trước câu trả lời đúng (A, B, C, D hoặc E)…" |
| `cot` | không |
| `scoring` | `extract_answer` (contract đóng băng), so khớp chữ cái, case-insensitive |
| `ket_qua` | overall **73,35%** (768/1.047) |
| `trang_thai` | ⚠️ **KHÔNG TÁI LẬP ĐƯỢC** — model đã rời endpoint (xem phần cuối) |

---

## MC-2 — V-Bench public test (đã chạy)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-2` |
| `ngay_chay` | 2026-09-04 |
| `benchmark` | V-Bench public test `v2026.03.28`, 5.141 câu chấm được |
| `model_id` | `Qwen3.8-27B-Q4_K_M.gguf` |
| `quantization` | Q4_K_M |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` | 0.0 |
| `seed` | 42 |
| `max_tokens` | 512 |
| `workers` | 4 |
| `prompt_style` | **`minimal`** ("điều kiện trung thực": chỉ câu hỏi + schema của chính dòng đó + một dòng format) |
| `cot` | không |
| `scoring` | server-side (vbench.ai), macro trung bình 13 domain |
| `ket_qua` | macro **44,97** ; micro **45,46%** (2.337/5.141) |
| `trang_thai` | ⚠️ **KHÔNG TÁI LẬP ĐƯỢC** — model đã rời endpoint |

### MC-2b — ablation `detailed` (cùng model, cùng seed)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-2b` |
| `dieu_kien` | prompt style = **`detailed`** (vai trò + luật + ví dụ format, biến thể không CoT) |
| `muc_dich` | đo phần điểm **"thuê" từ prompt engineering** |
| `phat_hien` | **42,2%** câu agentic (415/983) đổi đáp án giữa hai điều kiện; **213** câu đổi hẳn hàm được chọn |
| `so_loai_bi_bac` | minimal bác 15 · detailed bác 4 |

> **Cấm gộp `MC-2` với `MC-2b`.** Hai điều kiện này là hai phép đo khác nhau. Không có cột "best of".
> Mỗi điều kiện là một hàng điểm riêng trong mọi bảng.

---

## MC-3 — Reading eval 400 câu (đã chạy, vừa chấm)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-3` |
| `ngay_chay` | 2026-09 (ngày chấm lại: 2026-09-12) |
| `benchmark` | `eval_set_manifest.csv` — 400 câu pre-registered (200 Vi-SQuAD + 200 Vi-DROP, seed 42) |
| `model_id` | `Qwen3.8-27B-Q4_K_M.gguf` |
| `quantization` | Q4_K_M |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | **48** |
| `prompt_style` | **open-book** (`build_reading_prompt`) — context đưa sẵn trong prompt |
| `cot` | không |
| `scoring` | EM + char-F1 trên `review_gold_agreed.csv` (`code_benchmark/score_reading_eval.py`) |
| `ket_qua` | EM **80,25%** · char-F1 **86,55%** |
| `trang_thai` | ⚠️ **KHÔNG TÁI LẬP ĐƯỢC** — model đã rời endpoint |

---

## MC-3b — Reading eval 400 câu (Qwen3.5-9B-28K, cùng điều kiện MC-3, ghi nhận bổ sung)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-3b` |
| `ngay_chay` | 2026-09-20 (12:54–12:58 +07; khối ghi nhận bổ sung 2026-09-22) |
| `benchmark` | `eval_set_manifest.csv` — 400 câu pre-registered (200 Vi-SQuAD + 200 Vi-DROP, seed 42) |
| `model_id` | `Qwen3.5-9B-28K` (như MC-7; non-thinking) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 48 (như MC-3) |
| `workers` | 4 |
| `prompt_style` | **open-book** (`build_reading_prompt`) — context đưa sẵn trong prompt |
| `cot` | không |
| `scoring` | EM + char-F1 trên gold đã hiệu đính (`code_benchmark/score_reading_eval.py`) |
| `ket_qua` | ALL EM **79,75%** (319/400) · char-F1 **86,49**; Vi-SQuAD EM **96,50%** (193/200) · F1 **98,63**; Vi-DROP EM **63,00%** (126/200) · F1 **74,35**; 0 empty raw |
| `trang_thai` | ✅ xong; output `reading_answers_Qwen3_5-9B-28K.csv` + `reading_scores_Qwen3_5-9B-28K.csv` + `reading_summary_Qwen3_5-9B-28K.csv`; card hash ghi trong summary lúc chạy: `de01b926…` (bản card trước khi thêm khối này) |

> **Ghi nhận bổ sung (2026-09-22):** run đã chạy và được DB `/results` phục vụ từ trước nhưng chưa có khối riêng trong card — thêm theo lệ "mỗi lần chạy một khối"; hash trong output thuộc bản card lúc chạy, không phải bản hiện tại.
> Cấm so ngang MC-1/MC-2/MC-2b (model khác). So với MC-3 (Qwen3.8-27B): EM 79,75 vs 80,25 · DROP EM **y hệt 63,00** — xem `docs/model-insights.md` §1.1.

---

## MC-4 — trạng thái endpoint hiện tại (2026-09-12)

⚠️ **Endpoint đã thay model. Đây là sự kiện, không phải lỗi cấu hình.**

Kiểm tra ngày 2026-09-12:

| Model | Trạng thái |
| --- | --- |
| `Qwen3.8-27B-Q4_K_M.gguf` | ❌ chết — `Error connecting to backend LLM server: All connection attempts failed` |
| `Qwen3.5-9B-28K` | ✅ chạy; backend thật là `Qwen3.5-9B-Q6_K.gguf` |
| `Qwen3.5-9B-125K` | ✅ chạy |

`GET /v1/models` chỉ còn 2 model, cả hai đều là Qwen3.5-9B.

**Hệ quả:**

1. Mọi kết quả `MC-1`, `MC-2`, `MC-2b`, `MC-3` **không tái lập được nguyên trạng** trên endpoint này nữa.
2. Bất kỳ lần chạy mới nào cũng là **model khác** → **không được so ngang** với các con số trên.
3. Nếu muốn so sánh xuyên model một cách hợp lệ, phải chạy **cả hai** model trên cùng bộ câu hỏi.

---

## MC-5 — SEATauBench l2_domain telecom VI (pre-register, chưa chạy)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-5` |
| `ngay_chay` | 2026-09-19 |
| `benchmark` | SEATauBench `312f3e6` (SEACrowd/SEATauBench), scenario `l2_domain`, domain `telecom`, `lang_id=vi` |
| `manifest` | `seatau_bench/manifest_l2_domain_vi_telecom_test.json` — n=40 (toàn bộ telecom `test`), seed 42, sha256 `644737e8…c5cee4d627` |
| `agent_model` | `qwen38-nothink` (FROM `qwen3.8:27b-q4_K_M`, `PARAMETER think false`) qua `https://porridge-livable-umbrella.ngrok-free.dev/v1` |
| `user_sim` | `Qwen3.5-9B-28K` qua `https://llmapi.iec-uit.com/v1` (paper dùng Qwen3-235B cả 2 vai — khác điều kiện) |
| `temperature` / `seed` | 0.0 / 42 |
| `trials` | q=1 trước, q=3 khi cần `ρ³` |
| `scoring` | `correct` = `reward_info.reward` (telecom `ENV_ASSERTION`, không LLM judge); `valid` ≠ `correct` (gate 1.3, 2 file riêng) |
| `ket_qua` | 2/40 sim xong (reward 1.0, 1.0) rồi kill — **ABORTED**, không phải kết quả |
| `trang_thai` | ⛔ **ABORTED 2026-09-19**: IEC 502 giữa sim 3 (user-sim Qwen3.5), tau2 retry treo >27 phút; đã kill. 2 sim dở dang không công bố |

> Cấm so ngang MC-1..MC-3 (model/endpoint khác). Không suy năng lực từ single-run.
---

## MC-6 — VLSP2025-LegalSLM multichoice (pre-register, đang chạy)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-6` |
| `ngay_chay` | 2026-09-19 |
| `benchmark` | VLSP2025-LegalSLM public-test, split `multichoice`, n=146 |
| `manifest` | `data/legal_slm_multichoice_manifest.json` — LG-0001..LG-0146, seed 42 (gold local, closed-book, không RAG) |
| `model_id` | `qwen38-nothink` (FROM `qwen3.8:27b-q4_K_M`, `PARAMETER think false`) qua `https://porridge-livable-umbrella.ngrok-free.dev/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 512 (budget nhỏ ra rỗng do thinking ẩn — đã đo: 256 rỗng, 512 ra đáp án) |
| `prompt` / `scoring` | frozen `build_prompt` / `extract_answer` (byte-frozen, không sửa); chấm accuracy chữ cái |
| `baseline` | majority-class A=91/146 (**62,3%**) — mọi accuracy phải báo kèm baseline này |
| `ket_qua` | accuracy **82,88%** (121/146); baseline majority-class A 62,33% (91/146) → **+20,5đ** trên baseline; valid (parse được) 125/146 (85,6%), sai trong số parse được chỉ 4; confusion: gold-A 83/91, gold-B 29/39, gold-C 9/16; 21 blank (raw rỗng, tính sai — reprobe LG-0025: prompt 1019 chars vẫn `length` ở 512, không tương quan độ dài prompt; nguyên nhân chưa rõ, cấm tự ý cộng điểm bù) |
| `trang_thai` | ✅ xong 2026-09-19 ~18:26 (+07); output `all_res/ollama_result/full_evaluation_qwen38-nothink.csv` + `accuracy_qwen38-nothink.csv` + `/tmp/legal_run/submission.csv`; pre-register commit `027d714` 17:15 sớm hơn infer đầu |

> Cấm so ngang VMLU 73% (suite khác dạng). Model >4B trong khi suite giới hạn ≤4B — ghi rõ khi công bố.
---


## MC-7 — VMLU-MQA test 9.833 câu (Qwen3.5-9B-28K, pre-register)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-7` |
| `ngay_chay` | 2026-09-19 |
| `benchmark` | VMLU-MQA `vmlu_mqa_v1.5/test.jsonl`, n=9.833, **không gold local** (chấm duy nhất qua submit `vmlu.ai/submit`) |
| `model_id` | `Qwen3.5-9B-28K` (backend `Qwen3.5-9B-Q6_K.gguf` theo MC-4; non-thinking, đã probe `max_tokens=4` → `A`) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 4 |
| `workers` | 4 |
| `prompt_style` | frozen `build_prompt` — zero-shot, no-CoT, trả lời bằng chữ cái |
| `scoring` | không chấm local (no gold); output `full_evaluation_Qwen3_5-9B-28K.csv` + submission `data/submission_vmlu_test_Qwen3_5-9B-28K.csv` (9.833 dòng, id khớp 1:1, unique) để upload |
| `ket_qua` | infer xong 2026-09-20 00:06 (+07), 39,4 phút, exit 0; valid (parse được) 9.833/9.833 (0 blank); phân phối đoán A1980/B2192/C2583/D3041/E37 — không collapse; leaderboard **vmlu.ai 2026-09-20: total 67,87%** (STEM 65,65 / SocSci 74,97 / Humanity 68,61 / Other 63,67) |
| `trang_thai` | ✅ xong — đã có điểm leaderboard (xem `docs/vmlu-leaderboard-qwen35.md`); pre-register commit `363faa6` 23:26 sớm hơn infer đầu |

> Cấm so ngang MC-1 (model khác, tập khác: 1.047 gold vs 9.833 no-gold).

---

## MC-8 — V-Bench public test (Qwen3.5-9B-28K, pre-register)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-8` |
| `ngay_chay` | 2026-09-19 |
| `benchmark` | V-Bench public test `v2026.03.28` (`v_bench/public-test.jsonl`), 5.141 câu chấm được (mc + agentic; safety skip) |
| `model_id` | `Qwen3.5-9B-28K` (như MC-7) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 512 |
| `workers` | 4 |
| `prompt_style` | **`minimal`** (một điều kiện duy nhất cho slug này — cấm trộn `detailed`) |
| `scoring` | server-side (vbench.ai); local chỉ `valid` (parser frozen + clamp) → `vbench_valid_summary_*.csv` mang hash; `correct` chỉ qua `--record-server-scores` |
| `ket_qua` | infer 2026-09-20 01:14 (+07) exit 0: valid 5.127/5.141 — mc 4.141/4.141 (100%), agentic 986/1.000 (98,6%), 14 invalid logged `vbench_failures_*`; `--retry-unparsed` 13:58 (96s, 14 re-asked): vẫn 986/1.000 cùng 14 ids (lỗi model thật, không phải parser drift); `--guided` 14:01 (173s): agentic **1.000/1.000**, failures file đã xóa; submission rebuild **5.141 dòng** (`submission_vbench_Qwen3_5-9B-28K.jsonl`, shape `{"id":int,"answer"}` khớp official sample); server **vbench.ai 2026-09-20: macro 45,22 · micro 45,61% (2.345/5.141)** — mc 1.948/4.141=47,04%, agentic 397/1.000=39,70% (gồm 14 guided rows, condition thứ 3) |
| `trang_thai` | ✅ xong — đã có điểm server (xem `docs/vbench-server-qwen35.md`, snapshot `vbench_server_scores_Qwen3_5-9B-28K.csv`); 14 guided rows là condition thứ 3 (transcript `Q[function]` trong raw_response, không gộp silent vào minimal) |

> Cấm so ngang MC-2/MC-2b (model khác). Không gộp `minimal` với điều kiện khác.
---

## MC-9 — VMLU-MQA gold local (Qwen3.5-9B-28K, 3 sets)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-9` |
| `ngay_chay` | 2026-09-20 |
| `benchmark` | VMLU-MQA `vmlu_mqa_v1.5/{valid,dev,all_gold}.jsonl` (744 / 303 / 1.047, có gold local) |
| `model_id` | `Qwen3.5-9B-28K` (như MC-7) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 4 |
| `workers` | 4 |
| `prompt_style` | frozen `build_prompt` — zero-shot, no-CoT, trả lời bằng chữ cái |
| `scoring` | `extract_answer` (contract đóng băng), chữ cái case-insensitive; unparseable = sai nhưng giữ mẫu số |
| `ket_qua` | valid **540/744 = 72,58%**; dev **229/303 = 75,58%**; all_gold **768/1.047 = 73,35%** (recompute từ checkpoint khớp 0 mismatch) |
| `trang_thai` | ✅ xong — local probe, KHÔNG phải điểm leaderboard (gold test withheld, chỉ có sau `vmlu.ai/submit`) |

> Cấm so ngang MC-1 (model khác). Local gold accuracy ≠ leaderboard.

---

## MC-10 — VLSP2025-LegalSLM multichoice (Qwen3.5-9B-28K)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-10` |
| `ngay_chay` | 2026-09-20 |
| `benchmark` | VLSP2025-LegalSLM public-test, split `multichoice`, n=146 |
| `manifest` | `data/legal_slm_multichoice_manifest.json` — LG-0001..LG-0146, seed 42, sha256 `7b7d7f15…` khớp source (gold local, closed-book, không RAG) |
| `adapter` | `/tmp/legal_q35_input/legal_multichoice_146.jsonl` — LG ids theo thứ tự source + choices prefix `A. ` (khớp shape MC-6) + gold letter; runner **không sửa** |
| `model_id` | `Qwen3.5-9B-28K` (như MC-7; non-thinking, probe `max_tokens=4` → đáp án) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 4 (khác MC-6=512: Qwen3.5 không thinking ẩn, không cần budget phình) |
| `workers` | 4 |
| `prompt` / `scoring` | frozen `build_prompt` / `extract_answer` (byte-frozen, không sửa); chấm accuracy chữ cái |
| `baseline` | majority-class A=91/146 (**62,33%**) — recompute từ manifest, không hardcode |
| `ket_qua` | accuracy **87,67%** (128/146); baseline 62,33% → **+25,0đ**; valid 146/146 (0 blank); by-gold A 82/91=90,11%, B 34/39=87,18%, C 12/16=75,00%; 18 sai trong số parse được |
| `trang_thai` | ✅ xong 2026-09-20 ~14:15 (+07), 176s, exit 0; output `full_evaluation_legal_*` + `accuracy_legal_*` + `submission_legal_mc_*` (giữ tên legal- để không đè MC-9 all_gold đã restore từ `raw_result_1047`) |

> Cấm so ngang MC-6 (model + max_tokens khác). Model >4B trong khi suite giới hạn ≤4B — ghi rõ khi công bố.
---

## MC-13 — VLSP2025-LegalSLM NLI-150 (Qwen3.5-9B-28K, binary qua MC runner)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-13` |
| `ngay_chay` | 2026-09-20 |
| `benchmark` | VLSP2025-LegalSLM public-test, split `nli`, n=150 |
| `manifest` | `data/legal_nli_manifest.json` — LG-NLI-0001..LG-NLI-0150, seed 42, sha256 `43ffd837…` khớp source (gold local: answer 0→A/Có, 1→B/Không; balanced 75/75) |
| `adapter` | `/tmp/legal_nli_input/legal_nli_150.jsonl` — verbatim string: `question = legal_document.strip() + "\n\n" + specific_question.strip() + "\n" + question.strip()`; choices `["A. Có","B. Không"]`; gold Có→A / Không→B; ids theo thứ tự source; runner **không sửa** |
| `model_id` | `Qwen3.5-9B-28K` (như MC-7; non-thinking, probe `max_tokens=4` → đáp án) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 4 (như MC-10: Qwen3.5 không thinking ẩn) |
| `workers` | 4 |
| `prompt` / `scoring` | frozen `build_prompt` / `extract_answer` (byte-frozen, không sửa); chấm accuracy chữ cái |
| `baseline` | majority-class A=75/150 (**50,00%**) — recompute từ manifest, không hardcode |
| `ket_qua` | accuracy **90,00%** (135/150); baseline 50,00% → **+40,0đ**; valid 150/150 (0 blank, 0 raw rỗng); by-gold A 60/75=80,00%, B 75/75=100,00% (model thiên B: đoán B 90/A 60; 15 sai toàn là gold-A đoán B) |
| `trang_thai` | ✅ xong 2026-09-20 ~17:08 (+07), 145s, exit 0; output `full_evaluation_nli_*` + `accuracy_nli_*` + `submission_nli_*` (giữ tên nli- để không đè MC-9/MC-10; finals MC-9 `full_evaluation_*`/`accuracy_*` đã restore từ backup `/tmp/*mc9*`, 768/1047 nguyên vẹn) |

> Cấm so ngang MC-6 (suite + model khác). Model >4B trong khi suite giới hạn ≤4B — ghi rõ khi công bố.
---

## MC-12 — ViBidLQA val 482 (Qwen3.5-9B-28K, MC-3 condition)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-12` |
| `ngay_chay` | 2026-09-20 |
| `benchmark` | ViBidLQA val (`v_legal_slsp/bidlqa/ViBidLQA_val.jsonl`), n=482 |
| `manifest` | `data/bidlqa_val_manifest.json` — BIDLQA-V-0001..BIDLQA-V-0482, source order, sha256 `4cafca9d…` khớp source (gold file-native trong cột `gold_answer`, không review) |
| `runner` | `code_benchmark/run_bidlqa_eval.py --split val` — frozen `build_reading_prompt` import từ `run_reading_eval` (không copy); `run_reading_eval.py` byte-frozen |
| `model_id` | `Qwen3.5-9B-28K` (như MC-7) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 48 (như MC-3) |
| `workers` | 4 |
| `prompt` / `scoring` | open-book (`build_reading_prompt`), no-CoT; EM + char-F1 trên file gold (`score_reading_eval.py --gold manifest`, scoring math không chạm) |
| `ket_qua` | EM **32,78%** (158/482) · char-F1 **74,16%** (recompute từ per-item scores khớp summary, 0 mismatch; key-set 2 chiều khớp manifest); 0 empty raw |
| `trang_thai` | ✅ xong 2026-09-20 ~17:40 (+07), 1098s, exit 0; output `reading_answers_bidlqa_val_*` + `reading_scores_bidlqa_val_*` + `reading_summary_bidlqa_val_*` (infix `bidlqa_val` — file MC-3 400 câu nguyên vẹn) |

> Gold file-native (không review) — báo là file-gold EM như MC-10 manifest gold, không phải reviewed-gold. Cấm so ngang model khác.
---

## MC-11 — ViBidLQA test 603 (Qwen3.5-9B-28K, MC-3 condition)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-11` |
| `ngay_chay` | 2026-09-20 |
| `benchmark` | ViBidLQA test (`v_legal_slsp/bidlqa/ViBidLQA_test.jsonl`), n=603 |
| `manifest` | `data/bidlqa_test_manifest.json` — BIDLQA-T-0001..BIDLQA-T-0603, source order, sha256 `b99b9484…` khớp source (gold file-native trong cột `gold_answer`, không review) |
| `runner` | `code_benchmark/run_bidlqa_eval.py --split test` — frozen `build_reading_prompt` import từ `run_reading_eval` (không copy); `run_reading_eval.py` byte-frozen |
| `model_id` | `Qwen3.5-9B-28K` (như MC-7) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 48 (như MC-3) |
| `workers` | 4 |
| `prompt` / `scoring` | open-book (`build_reading_prompt`), no-CoT; EM + char-F1 trên file gold (`score_reading_eval.py --gold manifest`, scoring math không chạm) |
| `ket_qua` | EM **33,17%** (200/603) · char-F1 **73,21%** (recompute từ per-item scores khớp summary, 0 mismatch; key-set 2 chiều khớp manifest); 0 empty raw |
| `trang_thai` | ✅ xong 2026-09-20 ~18:04 (+07), 1359s, exit 0; output `reading_answers_bidlqa_test_*` + `reading_scores_bidlqa_test_*` + `reading_summary_bidlqa_test_*` (infix `bidlqa_test` — file MC-3/val nguyên vẹn) |

> Gold file-native (không review) — báo là file-gold EM như MC-10 manifest gold, không phải reviewed-gold. Cấm so ngang model khác. Val (MC-12) EM 32,78 / test (MC-11) EM 33,17 — cùng điều kiện, chênh 0,4đ.

---

## MC-14 — VM14K public release 12.488 câu (Qwen3.5-9B-28K, pre-register, chưa chạy)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-14` |
| `ngay_chay` | 2026-09-21 (pre-register; infer chưa chạy) |
| `benchmark` | VM14K public release — `v_med_vm14k/data-processed-shuffled0.jsonl` (HF `venera-ai/VietnameseMedBench`, tải 2026-09-21), n=12.488 |
| `manifest` | `data/vm14k_manifest.json` — sha256 `68821834…1e05aef4` khớp source, seed 42; items = id gốc (hex) + gold + n_choices + difficulty_level |
| `adapter` | `code_benchmark/make_vm14k_input.py` → `v_med_vm14k/vm14k_input.jsonl` (choices prefix `A. `, gold letter); `run_mc_eval.py` **byte-frozen**, không sửa |
| `model_id` | `Qwen3.5-9B-28K` (như MC-7; non-thinking, probe `max_tokens=4`) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 4 (như MC-10/MC-13: Qwen3.5 không thinking ẩn) |
| `workers` | 4 |
| `prompt` / `scoring` | frozen `build_prompt` / `extract_answer` (byte-frozen, không sửa); chấm accuracy chữ cái |
| `baseline` | majority-class A = 3915/12488 (**31,35%**) — recompute từ manifest, không hardcode |
| `ket_qua` | ⛔ **ABORTED — không có kết quả** (dừng ở 568/12.488 sau 12,5 phút vì đổi điều kiện concurrency; theo lệ MC-5, không công bố) |
| `trang_thai` | ⛔ **ABORTED 2026-09-21** trước khi hoàn thành → chuyển sang **MC-14b** (workers 8). Manifest/điều kiện đo không đổi; không có kết quả nào bị trộn điều kiện |

> **Caveat bắt buộc khi công bố:** (1) bản phát hành HF lệch paper (12.488 vs "4k sample + 10k full + 2k private") và dataset card **không có license**;
> (2) 1.377/12.488 dòng không phải 4 lựa chọn (2→1.240 · 3→101 · 1→15 · 5→2 · 7→19); 34 dòng có option placeholder `optionE/F/G`; 2 dòng question rỗng;
> (3) ~6% nội dung trùng lặp (716 nhóm / 785 dòng thừa) — giữ nguyên theo quyết định "raw", không dedupe;
> (4) suite công bố giới hạn ≤4B trong khi model 9B vượt — ghi rõ;
> (5) chỉ được đối chiếu V-Bench medicine 38,78% theo hướng "cùng/khác", **không trừ hai phần trăm cho nhau**.

---

## MC-14b — VM14K public release 12.488 câu (Qwen3.5-9B-28K, workers 8, pre-register, đang chạy)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-14b` |
| `ngay_chay` | 2026-09-21 |
| `benchmark` | VM14K public release — `v_med_vm14k/data-processed-shuffled0.jsonl` (HF `venera-ai/VietnameseMedBench`), n=12.488 |
| `manifest` | `data/vm14k_manifest.json` — sha256 `68821834…1e05aef4` khớp source, seed 42 (commit `97982e3`) |
| `adapter` | `code_benchmark/make_vm14k_input.py` → `v_med_vm14k/vm14k_input.jsonl`; `run_mc_eval.py` **byte-frozen** |
| `model_id` | `Qwen3.5-9B-28K` (như MC-7; non-thinking) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 |
| `max_tokens` | 4 |
| `workers` | **8** — đo tải 2026-09-21 (probe cùng lúc với run cũ): 1 request 0,26 req/s · 4 song song 0,72 req/s · 8 song song **1,55 req/s**; các điều kiện khác giữ nguyên MC-14 |
| `prompt` / `scoring` | frozen `build_prompt` / `extract_answer` (byte-frozen, không sửa); chấm accuracy chữ cái |
| `baseline` | majority-class A = 3915/12488 (**31,35%**) — recompute từ manifest, không hardcode |
| `ket_qua` | accuracy **64,79%** (8.091/12.488); parse **12.488/12.488 (100%, 0 blank)**; baseline majority A 31,35% → **+33,4đ**; theo difficulty: Easy **67,19%** (2.763/4.112) · Medium **64,01%** (4.540/7.093) · Challenging **61,78%** (737/1.193) · Hard **56,67%** (51/90); theo số lựa chọn: 4→64,16% (7.129/11.111) · 2→69,84% (866/1.240) · 3→67,33% (68/101) · 7→57,89% (11/19) |
| `trang_thai` | ✅ xong 2026-09-22 ~00:38 (+07), exit 0; output `full_evaluation_vm14k_*` + `accuracy_vm14k_*` + `submission_vm14k_*` (12.488 dòng); MC-9 finals restore nguyên vẹn (sha khớp); checkpoint VM14K park riêng `vm14k_checkpoints/` (**125 file**, park theo nội dung — tránh nhiễm `find_latest_checkpoint`); DB: run `qwen3-5-9b-28k__vm14k-public-12488__MC-14b` |

> Cùng **caveat bắt buộc** như MC-14: (1) bản phát hành lệch paper + không license; (2) 1.377/12.488 dòng ≠ 4 lựa chọn, 34 dòng option placeholder, 2 dòng question rỗng; (3) ~6% trùng lặp (giữ nguyên, không dedupe); (4) suite ≤4B vs model 9B; (5) chỉ so hướng với V-Bench medicine 38,78%.
> **Lưu ý kỹ thuật:** `workers` là tham số hạ tầng — `temperature 0` + `seed 42` + prompt/parser không đổi; MC-14 chưa từng cho ra kết quả nên hai điều kiện không bị trộn.

## MC-15 — Reading eval 400 câu qua **omp harness** (H2, Qwen3.5-9B-28K)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-15` |
| `ngay_chay` | 2026-09-26 |
| `dieu_kien` | **arm B của phép so sánh harness**: cùng model/prompt/parser như MC-3b, chỉ thay đường elicitation — chạy trong agent `omp` (Oh My Pi). Mục đích: đo **harness effect** (delta do scaffold, không do model) |
| `benchmark` | reading-400 (`data/eval_set_manifest.csv` 200 squad + 200 drop; gold reviewed `data/gold/review_gold_agreed.csv`) |
| `model_id` | `iec/Qwen3.5-9B-28K` (provider trong `.omp-iec/models.yml`; **cùng backend** với MC-7/MC-3b) |
| `endpoint` | `https://llmapi.iec-uit.com/v1` |
| `temperature` / `seed` | 0.0 / 42 (temperature ép qua `--thinking off`; omp không truyền `seed`) |
| `harness` | `omp` v18.2.7 · `-p --mode json` · `PI_CODING_AGENT_DIR=.omp-iec` (config + provider cô lập, **mọi `modelRoles` ghim** về 1 model) |
| `system_prompt` | **mặc định của omp** (coding-agent) — đo được ~11,5k token/lượt |
| `tools` | `read,bash,edit,write,grep,glob` + `--auto-approve` |
| `max_time` | 180s/item (`--max-time`); `max_tokens` + context do omp quản lý (context 32768) |
| `tat` | `--no-session --no-title --no-extensions --no-skills --no-rules --no-lsp` |
| `prompt` | **byte-identical MC-3b** (`build_reading_prompt`); cô lập: mỗi item 1 thư mục tạm rỗng chỉ có `item.json` (**không gold**), `--cwd` vào đó, không `--add-dir` |
| `scoring` | **scorer đóng băng, không viết lại**: `score_reading_eval.py` (EM + char-F1) trên projection `ANSWER_COLS`; MC không có, parser `extract_answer` nguyên vẹn |
| `workers` | 6 |
| `slug` | `ompH2_Qwen3_5-9B-28K` (điều kiện riêng, không trộn với `Qwen3_5-9B-28K`) |
| `ket_qua` | **EM 27,00%** (108/400) · char-F1 **43,14** — squad EM 38,50 / F1 59,52 · drop EM 15,50 / F1 26,76 |
| `so_voi_arm_A` | MC-3b EM 79,75 / F1 86,49 → **Δ = −52,75đ** (paired bootstrap 95% CI −57,75..−48,00; McNemar exact p≈1,6e−59); 2×2: both 105 · A-only 214 · B-only 3 · neither 78 |
| `gia_phi` | 14,0 s/item · 1,00 lượt · 581 input tok/item · 75 output tok/item (arm A: ~150 input, 1–4 output) |
| `audit` | 0 item lỗi · 0 tool call · **0 lần gọi mạng** · 0 lần trốn sandbox |
| `trang_thai` | ✅ xong 2026-09-26 17:08 (+07); ledger `harness_ledger_reading400_ompH2_Qwen3_5-9B-28K.csv`; `measurement_card_hash` của output = `bc4d7c28…4f7bf04` (hash file **trước khi** thêm khối này) |

> **Cơ chế (đo trên per-item, không phải suy đoán):** 145/214 item "A-only" có **nguyên văn chuỗi gold** trong câu trả lời của harness → mất điểm vì bị bọc markdown + giải thích, không phải vì sai. Chấm riêng dòng đầu cũng chỉ cứu được squad 39,50% (arm A 96,50%) → prose xen kẽ, không phải một dòng bọc ngoài.

## MC-16 — VLSP2025-LegalSLM MC-146 + NLI-150 qua **omp harness** (H2)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-16` |
| `ngay_chay` | 2026-09-26 |
| `dieu_kien` | như MC-15 (cùng harness H2, cùng model, cùng prompt byte-identical) |
| `benchmark` | multichoice 146 (`v_legal_slsp/legal_slm/multichoice.jsonl`, gold `data/legal_slm_multichoice_manifest.json`) + nli 150 (`…/nli.jsonl`, gold `data/legal_nli_manifest.json`) |
| `model_id` / `endpoint` | `iec/Qwen3.5-9B-28K` @ `https://llmapi.iec-uit.com/v1` |
| `temperature` | 0.0 (`--thinking off`) |
| `prompt` | frozen `build_prompt`; adapter **tái dựng từ source rồi hard-fail nếu lệch byte** so với prompt arm A đã lưu (phát hiện đúng 1 lỗi thật: choices phải gán chữ cái `A. B. C. D.`) |
| `scoring` | frozen `extract_answer` + `score_row` (accuracy chữ cái); recompute độc lập từ per-item CSV khớp **0 sai lệch** |
| `workers` | 6 · `slug` `ompH2_Qwen3_5-9B-28K` |
| `ket_qua` | multichoice **50,00%** (73/146) · nli **60,67%** (91/150) |
| `so_voi_arm_A` | MC-10 87,67% → **Δ = −37,67đ** (CI −46,58..−28,77; p≈4,9e−13; both 68 · A-only 60 · B-only 5 · neither 13) · MC-13 90,00% → **Δ = −29,33đ** (CI −37,33..−22,00; p≈1,3e−12; both 90 · A-only 45 · B-only 1 · neither 14) |
| `gia_phi` | MC 23,0 s/item · NLI 19,5 s/item · reply dài trung vị 791 / 573 ký tự (arm A: **1 ký tự**) |
| `audit` | 0 item lỗi · 2 item dùng tool · 0 gọi mạng · **1 lần trốn sandbox thất bại** (xem MC-18) |
| `trang_thai` | ✅ xong 2026-09-26 17:27 (+07) |

> **Cơ chế:** 0/296 item lỗi parse, nhưng 44/60 item MC mất điểm **vẫn nhắc chữ cái gold** (73%)
> → không phải parser bắt nhầm, mà model tự lập luận rồi đổi ý (kèm trích dẫn luật bịa:
> "Nghị định 59/2024", "Luật Giao thông 2024"). Ở NLI chỉ còn 33% nhắc gold → phần lớn là
> đổi đáp án thật.

## MC-17 — ViBidLQA val 482 qua **omp harness** (H2)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-17` |
| `ngay_chay` | 2026-09-26 |
| `dieu_kien` | như MC-15 (cùng harness H2; MC-3 open-book prompt) |
| `benchmark` | ViBidLQA val 482 (`data/bidlqa_val_manifest.csv`, gold cùng file; sha256 source `4cafca9d…3e800`) |
| `model_id` / `endpoint` | `iec/Qwen3.5-9B-28K` @ `https://llmapi.iec-uit.com/v1` · temperature 0.0 |
| `scoring` | `score_reading_eval.py` (đóng băng) với `--gold data/bidlqa_val_manifest.csv` |
| `workers` | 6 · `slug` `ompH2_Qwen3_5-9B-28K` |
| `ket_qua` | **EM 6,02%** (29/482) · char-F1 **36,74** |
| `so_voi_arm_A` | MC-12 EM 32,78% / F1 74,16 → **Δ = −26,76đ** (CI −30,91..−22,61; p≈7,4e−33; both 23 · A-only 135 · B-only 6 · neither 318) |
| `gia_phi` | 17,1 s/item · 1,00 lượt · 874 input tok/item · 138 output tok/item |
| `audit` | 0 item lỗi · 1 item dùng tool (`read` chính item.json bằng đường dẫn đoán mò → `Path not found`) · 0 gọi mạng |
| `trang_thai` | ✅ xong 2026-09-26 17:55 (+07) |

## MC-18 — Nhiễu lặp lại của chính arm H2 (legal-MC 20 item, slug thứ hai)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-18` |
| `ngay_chay` | 2026-09-26 |
| `dieu_kien` | **y hệt MC-16** nhưng `--label ompH2rep2_Qwen3.5-9B-28K`, `--limit 20` — chạy lại để đo nhiễu của arm, **không phải điều kiện mới** |
| `ket_qua` | chữ cái parse **giống lần 1: 7/20**; đúng/sai giống: 12/20; accuracy 11/20 = 55% (lần 1: 11/20 = 55%); 1 item lỗi ở lần 2 (`LG-0011`: model dùng `write` lưu `answer.txt` rồi trả lời *"Đáp án đã được lưu vào file"* → unparsed) |
| `trang_thai` | ✅ xong 2026-09-26 17:55 (+07) |

> **Kết luận bắt buộc cho mọi lần đọc số H2:** arm này **không tất định ở `temperature 0`**
> (~65% item đổi đáp án giữa hai lần chạy, trong khi điểm tổng gần như không đổi). Δ phải
> được đọc như **hiệu ứng tổng**; không suy ra thuộc tính từng item, và mọi so sánh điểm về
> sau cần ≥2 lần lặp (hoặc CI rộng).

## MC-19 — **Chi phí** của harness: thời gian + token (cost probe, cùng item, cùng workers)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-19` |
| `ngay_chay` | 2026-09-26 |
| `dieu_kien` | **đo chi phí, không đo điểm**: `run_harness_eval.py speed` gọi **cả hai arm trên cùng một tập item**, cùng `workers`, cùng prompt byte-identical. Arm A gọi API trực tiếp (`max_tokens` theo card: MC 4 / reading 48, temp 0, seed 42); arm B chạy harness H2 như MC-15/16/17 |
| `model` / `endpoint` | `Qwen3.5-9B-28K` @ `https://llmapi.iec-uit.com/v1` (token đọc từ `.omp-iec/.env`, **không** hardcode, **không** đọc `OPENAI_MODEL` từ `.env` — file đó trỏ model đã chết) |
| `workers` | 4 (thêm sweep 1 và 8 trên legal_mc) |
| `output` | `speed_arms_<ds>[_tag]_<slug>.csv` (per-item) + `speed_summary_<ds>[_tag]_<slug>.csv` (tổng hợp) — **tách riêng**, không lẫn vào file kết quả chính |

### Kết quả/item (workers=4)

| Tập | n | A wall | B wall | **×wall** | A token | B token | **×token** | B prompt (fresh+cache) | B completion | overhead B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| legal-MC | 40 | 1,33s | 15,51s | **11,7×** | 228 | 12.543 | **55,0×** | 322 fresh + 12.006 cache | 216 (**108×** A) | 6,19s |
| legal-NLI | 24 | 1,53s | 23,04s | **15,1×** | 318 | 12.779 | **40,2×** | ~330 + 12.006 | 359 (**179×** A) | 5,92s |
| reading-400 | 40 | 2,13s | 10,05s | **4,7×** | 373 | 12.814 | **34,4×** | 459 + 12.318 | 38 (**4,8×** A) | 7,56s |
| ViBidLQA val | 24 | 3,44s | 13,39s | **3,9×** | 599 | 12.815 | **21,4×** | 670 + 12.006 | 139 (**5,1×** A) | 6,31s |

### Cả run 1.178 item (arm B đo thật; arm A = tỉ lệ đo được × n)

| Đại lượng | Arm A | Arm B | Tỉ lệ |
| --- | --- | --- | --- |
| token **chưa cache** (trả tiền thật) | ~502.117 prompt + 16.765 completion | 761.620 fresh + 161.611 completion | **×1,8** |
| token **kể cả cache read** | 518.883 | **15.050.640** | **×29,0** |
| trong đó cache read | ~0 | 14.084.141 (**94,9%** prompt token của H2 là cache hit** của tiền tố system prompt ~12k token**) | — |
| completion token (việc decode thật trên GPU) | 16.765 | 161.611 | **×9,6** |
| tổng latency của item (workers=4) | 48,8 phút | 269,9 phút | **×5,5** |
| latency mỗi item | 1,3–3,4s | 10,1–23,0s | ×3,9–15,1 |

### Phân rã thời gian của arm B (legal-MC, workers=4)

`15,51s/item = 6,19s overhead tiến trình (spawn bun + nạp config/provider + teardown) + 9,32s gọi model (trong đó TTFT 3,36s)`

### Throughput theo số worker (legal-MC)

| workers | Arm A items/phút | Arm B items/phút | wall/item A | wall/item B |
| --- | --- | --- | --- | --- |
| 1 | 146,3 | 5,6 | 0,41s | 10,76s |
| 4 | 181,1 | 15,5 | 1,33s | 15,51s |
| 8 | 272,8 | 17,0 | 1,76s | 28,32s |

> **Đọc đúng các con số này:** (1) phần lớn prompt token của H2 là **cache read** — nếu gateway tính cache read rẻ/như miễn phí thì hóa đơn token chỉ **×1,8**, con số **×29** chỉ mô tả lưu lượng qua wire; (2) khoản đắt thật là **completion token ×9,6** (verbosity — cùng thứ làm hỏng EM) + **overhead ~6s/item CPU**; (3) arm B **không scale** theo worker (5,6 → 15,5 → 17,0 items/phút) trong khi arm A scale tốt (146 → 273) ⇒ nút thắt là decode + spawn, không phải endpoint.

## MC-20 — **Ablation H1 `--no-tools`**: tách scaffolding khỏi tool menu (legal-MC 100 item)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-20` |
| `ngay_chay` | 2026-09-26 |
| `dieu_kien` | **MC-16 không tool**: cùng model / endpoint / prompt byte-identical / scorer, chạy `omp` với `--no-tools` (thay vì tool menu `read,bash,edit,write,grep,glob`), `--limit 100` (tiền tố 100 item của legal-MC, trùng đúng tập H2 đã chạy) |
| `slug` | `ompH1_Qwen3_5-9B-28K` (điều kiện riêng; `compare` đọc được vì cả hai arm dùng tên `full_evaluation_<dataset>_<slug>.csv`) |
| `workers` | 6 (chạy) · 4 (cost probe) |
| `muc_dich` | **phân rã Δ của MC-16**: Δ là của persona (system prompt) hay của tool menu? |

### Kết quả trên CÙNG 100 item

| Arm | accuracy | Δ so với arm A | CI 95% (paired) | McNemar p | A-only | B-only |
| --- | --- | --- | --- | --- | --- | --- |
| **A** — gọi API trực tiếp (MC-10) | **86,00%** | — | — | — | — | — |
| **H1** — omp, **không tool** | **64,00%** | **−22,00** | −32,00..−12,00 | 5,9e−05 | 26 | 4 |
| **H2** — omp, tool menu đầy đủ (MC-16) | **54,00%** | **−32,00** | −43,00..−21,00 | 1,9e−07 | 36 | 4 |
| H1 vs H2 (bỏ tool menu) | — | **+10,00** | −4,00..+24,00 | **0,20 (không đáng kể)** | 20 | 30 |

⇒ **69% sức hủy của H2 đến từ scaffolding một mình** (system prompt của omp). Phần dư do tool
menu (−10đ) **không phân giải được** ở n=100 (CI ±14đ) — đúng vùng mà nhiễu của chính arm đã
đo ở MC-18 lấn át. Muốn kết luận về tool cần ≥2 lần lặp mỗi arm hoặc n≥300.

### Cơ chế: verbosity đến từ system prompt, KHÔNG phải từ tool

| Arm | reply p50 | reply p90 | completion tok/item | có `**` | có list | có "vì sao/why" |
| --- | --- | --- | --- | --- | --- | --- |
| A | **1 ký tự** | 1 | 2 | 0% | 0% | 0% |
| H1 (không tool) | **804 ký tự** | 1.372 | 257 | 93% | 92% | 48% |
| H2 (có tool) | 779 ký tự | 1.262 | 245 | 96% | 93% | 41% |

H1 không tool **vẫn verbose y hệt** ⇒ định dạng trả lời là hệ quả của system prompt, không phải
 của tool menu. (Cơ chế này giải thích toàn bộ phần "EM đúng nội dung nhưng 0 điểm" ở MC-15.)

### Chi phí (cost probe, cùng item, workers=4)

| Arm | wall/item | overhead | prompt tok/item | completion tok/item | tổng token |
| --- | --- | --- | --- | --- | --- |
| A (direct) | 0,73s | 0 | 226 | 2 | 228 |
| **H1** (không tool) | 17,48s | 5,87s | **7.503** | 274 | 7.777 |
| H2 (có tool) | 15,51s | 6,19s | **12.328** (322 fresh + 12.006 cache) | 216 | 12.543 |

⇒ **tool schema tốn ~4.825 token prompt/item nhưng gần như không tốn thời gian** (vì model
gần như không gọi tool: turns 1,00; 0/1.178 item có tool call ở H2). Và arm H1 **vẫn đắt hơn arm
A ~24× về thời gian, ~34× về token** — scaffolding tốn phần lớn chi phí.

### Audit

0 item lỗi · 0 tool call (đúng thiết kế) · 0 gọi mạng · 0 trốn sandbox — trên 100 item.

> **Còn chưa tách được:** system prompt của omp gộp *cả ba* thứ — persona coding, kỷ luật
> "trả lời + giải thích", và định dạng markdown. Muốn tách tiếp phải có arm H3 (system prompt
> tối giản 1 dòng); kết quả H1 ở đây **không** cho phép quy Δ cho persona nói riêng.

## MC-21 — **Factorial 2×2 của harness**: persona × tool menu (legal-MC, 100 item giống nhau)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-21` |
| `ngay_chay` | 2026-09-26 |
| `dieu_kien` | Bốn arm qua `omp`, **cùng 100 item legal-MC đầu**, cùng model/endpoint/prompt byte-identical/scorer; chỉ khác 2 nhịp: `system_prompt` ∈ {mặc định của omp, dòng trung tính `Answer the user's question.`} × `tools` ∈ {menu đầy đủ, `--no-tools`}. Slug: `ompH1_` (persona×no-tools) · `ompH2_` (persona×tools) · `ompH3_` (min-sys×tools) · `ompH4_` (min-sys×no-tools) |
| `workers` | 6 (chạy) · 4 (cost probe) |
| `muc_dich` | Đóng ngoặc "Δ đến từ cái gì": trước MC-20 mới chỉ tách được 1 tầng |

### Kết quả (n = 100 item **giống nhau** ở cả 5 arm, arm A = 86,00%)

| | **tool menu đầy đủ** | **`--no-tools`** | hiệu ứng chính của tools |
| --- | --- | --- | --- |
| **system prompt của omp** | **H2 = 54,00%** (Δ −32,00; p=1,9e−07) | **H1 = 64,00%** (Δ −22,00; p=6,0e−05) | **−10,00** (p=0,20) |
| **dòng trung tính** | **H3 = 65,00%** (Δ −21,00; p=5,7e−06) | **H4 = 63,00%** (Δ −23,00; p=2,9e−04) | +2,00 (p=0,87) |
| hiệu ứng chính của persona | **−11,00** (p=0,14) | +1,00 (p=1) | trung bình **−5,0** |

### Đọc kết quả (đây là kết luận của chuỗi đo)

| Mệnh đề | Số | Độ tin cậy |
| --- | --- | --- |
| **Sàn của scaffold**: `omp` với system prompt trung tính + không tool vẫn mất **−23,00đ** so với gọi API trực tiếp với **cùng prompt** | −23,00 | **CI −35..−12, p=0,00029 — mạnh** |
| Persona (coding-agent) thêm | −5,0 (trung bình) | không phân giải được: −11 khi bật tool (p=0,14), +1 khi tắt tool (p=1) |
| Tool menu thêm | −4,0 (trung bình) | không phân giải được: −10 khi bật persona (p=0,20), +2 khi tắt persona (p=0,87) |
| Hai gene cùng bật thêm so với sàn | −9,00 | CI −23..+5, p=0,27 — **không phân giải được** |
| Tương tác (H2−H3−H1+H4) | **−12,0** | hai gene **thay thế nhau**, không cộng dồn: chỉ một gene cũng chỉ bằng sàn |

⇒ **Kết luận trung thực:** phần lớn sức hủy (**~23/32 điểm ≈ 72%**) đến từ **scaffold của chính `omp`**, không phải persona, không phải tool menu. Hai gene "persona" và "tools" **không cộng dồn** mà thay thế nhau, và mỗi cái riêng lẻ đều không vượt nổi nhiễu của arm (MC-18). Muốn gắn phần ~9 điểm còn lại cho gene nào thì phải tăng n (≥300/arm) hoặc lặp ≥2 lần mỗi arm.

### Cơ chế: verbosity là thuộc tính của scaffold, không thuộc về gene nào

| Arm | reply p50 | completion tok/item | có `**` | có list | có "vì sao/why" | prompt tok/item | tool calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A (direct) | 1 ký tự | 2 | 0% | 0% | 0% | 226 | 0 |
| H4 (min-sys, no tools) | 812 ký tự | 264 | 96% | 90% | 45% | 5.527 | 0 |
| H1 (omp sys, no tools) | 804 ký tự | 257 | 93% | 92% | 48% | 7.497 | 0 |
| H3 (min-sys, tools) | 889 ký tự | 253 | 98% | 89% | 46% | 10.368 | 1 |
| H2 (omp sys, tools) | 779 ký tự | 245 | 96% | 93% | 41% | 12.448 | 1 |

Cả 4 ô đều verbose như nhau ⇒ **định dạng "trả lời + giải thích markdown" do scaffold áp đặt**, không
phải persona, không phải tool. Đây là cơ chế giải thích toàn bộ phần "đúng nội dung nhưng 0 điểm"
ở MC-15 (reading EM 79,75% → 27,00%).

### Chi phí theo ô (cost probe, cùng item, workers=4)

| Arm | wall/item | overhead | prompt tok/item | tổng token/item |
| --- | --- | --- | --- | --- |
| A (direct) | 0,59–1,38s | 0 | 226 | 228 |
| H4 (min-sys, no tools) | 15,20s | 5,81s | 5.527 | 5.763 |
| H2 (omp sys, tools) | 16,43s | 5,76s | 10.264 | 10.517 |

Chi phí **tăng đơn điệu theo prompt** (226 → 5.5k → 10.3k) nhưng **thời gian gần như không đổi**
(15,2s vs 16,4s) ⇒ thời gian bị chi phối bởi **spawn tiến trình + 1 lượt decode dài**, không phải
bởi kích thước prompt. Persona chỉ chiếm ~2.080 token prompt; tool schema thêm ~2.871 token.

### Audit

0 item lỗi ở cả 4 arm · 0 gọi mạng · 0 trốn sandbox thành công (2 lần trốn ở H2/H3 đều hỏng).

> **Giới hạn:** (1) n=100/arm → CI ±10–14 điểm, nên chỉ "sàn −23" là kết luận chắc; (2) arm H2
> không tất định ở temp 0 (MC-18) nên các contrast nhỏ nằm trong nhiễu; (3) "dòng trung tính" là
> một lựa chọn vận hành, không phải "không có system prompt" — `omp` vẫn chèn ~5.3k token
> lệnh nội bộ của nó (đo được ở H4), và chính phần đó đã đủ để mất 23 điểm.

## MC-22 — ⚠️ **ĐÍNH CHÍNH MC-15…MC-19**: scaffold bị rò từ `APPEND_SYSTEM.md` + sweep dưới scaffold sạch

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-22` |
| `ngay_chay` | 2026-09-26 (sau MC-15…MC-21, cùng ngày) |
| `ly_do` | Bắt được bằng công cụ mới `code_benchmark/capture_scaffold.py` (proxy ghi log localhost, đọc request thật mà `omp` gửi). **Hai lỗi trong cách diễn giải MC-15…MC-21, không phải trong số đo.** Số đo vẫn đúng cho *điều kiện đã ghi*; nhưng điều kiện đó **không phải "omp" — nó là "omp + cấu hình trả lời cá nhân của máy"** |

### Lỗi 1 — rò cấu hình: `PI_CODING_AGENT_DIR` KHÔNG cô lập được scaffold

`omp` đọc thêm `~/.omp/agent/APPEND_SYSTEM.md` (774 ký tự) từ **agent dir mặc định**, ngay cả khi
`PI_CODING_AGENT_DIR` trỏ sang thư mục khác. Nội dung file đó là luật trả lời "plain-answers":
**verdict first → why → the test → the rule**. Bằng chứng (system prompt bắt được, byte nguyên vẹn):

```
"Answer the user's question.\n# Global reply style (all projects)\nWhen replying to the user as the
root-level agent, use the plain-answers skill: inverted pyramid, verdict first …"
```

- Tạo `APPEND_SYSTEM.md` **rỗng** trong agent dir riêng → **không** che được (vẫn 1.519 ký tự).
- Chỉ ghi đè `HOME` mới sạch: system prompt còn **745 ký tự**, mất hẳn "Global reply style".
- ⇒ Runner nay in cảnh báo `SCAFFOLD LEAK` (guard `warn_about_scaffold_leaks`) mỗi lần chạy.

### Lỗi 2 — số token trong MC-19/MC-21 bị thổi phồng

Ledger ghi `input + cacheRead`; `cacheRead` của gateway IEC là **bộ đếm prefix cache tích luỹ**, không
phải số token của request đó. Đối chiếu bằng request thật:

| Arm | request thật (client) | ledger ghi | endpoint xác nhận (replay) |
| --- | --- | --- | --- |
| H4 (min-sys, no tools) | system 1.519 + user 966 = **2.485 ký tự** | 5.527 tok/item | **688 prompt tokens** |
| H2 (tools + persona) | system 10.859 + tools 15.602 + user = **26.463 ký tự** | 12.448 tok/item | ~7.000 prompt tokens (ước lượng 3,5–4 ký tự/token) |

⇒ Các tỉ lệ "×29 token" (MC-19) **sai**; số đúng tính ở MC-23 dưới.

### Lỗi 3 — hệ quả: phần lớn "harness tax" là cấu hình, không phải harness

Sweep lại **toàn bộ 1.178 item** dưới scaffold sạch (`HOME` override, `--tools none`,
`--system-prompt minimal`, cùng prompt byte-identical), slug `ompH5clean_Qwen3_5-9B-28K`:

| Tập | Card A | n | Arm A | **omp + rò style (H2)** | **omp sạch (H5)** | Δ thật của harness | p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| reading-400 (EM) | MC-3b | 400 | 79,75% | 27,00% | **57,50%** | **−22,25** (CI −26,75..−17,75) | 1,5e−20 |
| legal-MC | MC-10 | 146 | 87,67% | 50,00% | **69,18%** | **−18,49** (CI −26,71..−10,96) | 1,4e−05 |
| legal-NLI | MC-13 | 150 | 90,00% | 60,67% | **78,67%** | **−11,33** (CI −18,67..−4,00) | 0,0046 |
| ViBidLQA val (EM) | MC-12 | 482 | 32,78% | 6,02% | **27,18%** | **−5,60** (CI −9,34..−2,07) | 0,0032 |

⇒ **Chi phí thật của việc "ở trong `omp`" là −5,6 … −22,3 điểm**, không phải −26,8 … −52,8. Phần còn
lại do rò cấu hình: reading-400 hồi được **+30,50đ**, legal-NLI **+18,00đ**, bidlqa **+21,16đ**.

### Cơ chế sau khi rò bị gỡ (reading-400, cùng 400 item)

| | item A-only | trong đó có nguyên văn gold | char-F1 trung vị | reply p50 |
| --- | --- | --- | --- | --- |
| omp + rò style (H2) | 214 | **145 (68%)** | 0,24 | 100 ký tự |
| **omp sạch (H5)** | **97** | **14 (14%)** | 0,51 | **8 ký tự (= arm A)** |

Với scaffold sạch, **định dạng trả lời khớp hệt arm A** (8 ký tự p50) ⇒ phần tổn thất còn lại
**không còn là vỏ nữa** mà là **sai thật** (ví dụ gold `24,10%` → `14,10%`; gold `tăng dần` →
`có xu hướng tăng dần`). Cơ chế "đúng nội dung nhưng 0 điểm" ở MC-15 **do cấu hình, không do omp**.

### Audit sweep sạch

1.178 item · **0 lỗi** · 0 tool call (đúng `--no-tools`) · 0 gọi mạng · 0 trốn sandbox.

> **Đọc lại MC-15…MC-21 như thế nào:** các số điểm vẫn hiệu lực cho điều kiện đã ghi ("`omp` trên
> máy này, có global `APPEND_SYSTEM.md`"). **Cách quy nhân quả** thì sai: không được viết "harness
> `omp` làm mất 52 điểm" — phải viết "scaffold gồm system prompt `omp` **cộng** luật trả lời cá nhân
> bị rò vào làm mất 52 điểm; riêng `omp` sạch làm mất 22 điểm trên tập đó".

## MC-23 — **Factorial 2×2 trên scaffold SẠCH**: persona × tool menu (100 item legal-MC giống nhau)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-23` |
| `ngay_chay` | 2026-09-26 (sau MC-22) |
| `dieu_kien` | Bốn arm qua `omp`, **cùng 100 item legal-MC**, cùng model/endpoint/prompt byte-identical/scorer, **`HOME` override nên không dính `APPEND_SYSTEM.md`**, `PI_CODING_AGENT_DIR=.omp-clean/`, `--tools none` hoặc menu đầy đủ, system prompt của omp hoặc dòng trung tính. Slug: `ompH5clean_` (trung tính×no-tool) · `ompH6clean_` (trung tính×tools) · `ompH7clean_` (omp-sys×no-tool) · `ompH8clean_` (omp-sys×tools) |
| `workers` | 6 (chạy) · 4 (cost probe) |
| `muc_dich` | Lặp lại MC-21 sau khi gỡ rò cấu hình — 3/4 ô của MC-21 còn nhiễm |

### Kết quả (n = 100 item **giống nhau**, arm A = 86,00%)

| | **tool menu đầy đủ** | **`--no-tools`** | hiệu ứng tools |
| --- | --- | --- | --- |
| **system prompt của omp** | H8 = **75,00%** (Δ −11,00; p=0,027) | H7 = **68,00%** (Δ −18,00; p=1,2e−04) | +7,00 |
| **dòng trung tính** | H6 = **69,00%** (Δ −17,00; p=9,1e−04) | H5 = **70,00%** (Δ −16,00) | −1,00 (p=1,00) |
| hiệu ứng persona | +6,00 | −2,00 (p=0,86) | |

Các contrast **trong** scaffold sạch, so với ô trung tính×no-tool (H5 = 70,00%):

| Contrast | Δ | CI 95% | p |
| --- | --- | --- | --- |
| thêm tool menu (H6 − H5) | −1,00 | −11,00..+10,00 | **1,00** |
| đổi sang system prompt omp (H7 − H5) | −2,00 | −13,00..+9,00 | **0,86** |
| thêm cả hai (H8 − H5) | +5,00 | −4,00..+14,00 | **0,40** |

### Kết luận (mệnh đề mạnh nhất của cả chuỗi đo)

1. **Mọi ô sạch đều thua arm A 11–18 điểm** (p ≤ 0,027) ⇒ có một **khoản phạt phẳng ~−16đ** cho
   việc "đi qua tiến trình agent", **độc lập với gene nào bật**.
2. **Persona và tool menu không có tác dụng đo được** (mọi p ≥ 0,40; dải CI ±10–14 điểm nuốt hết
   cả hiệu ứng). Ở sạch, chúng thậm chí **thay thế nhau** về chiều: bật persona *cùng* tools là ô
   tốt nhất (75,00%), bật tools *không* persona thì tệ nhất (69,00%).
3. ⇒ Phân rã cuối cùng của "harness tax" (−52,75đ trên reading-400 của MC-15):
   **~−23đ = sàn của tiến trình agent (~−16đ) + luật trả lời cá nhân bị rò (~−7đ ở tập này)**,
   còn persona và tool menu **≈ 0**.

### Chi phí trên scaffold sạch (cost probe, cùng item, workers=4)

| Arm | wall/item | overhead | prompt tok (theo ledger*) | completion tok/item |
| --- | --- | --- | --- | --- |
| A (direct) | 1,24s | 0 | 226 | 2 |
| H5 (trung tính, no tools) | 3,60s | 1,81s | 5.387 | **2** |
| H8 (omp-sys + tools) | 3,18s | 1,83s | 12.432 | **2** |

\* Số này vẫn mang **cảnh báo MC-22**: `cacheRead` của gateway là bộ đếm tích luỹ, nên đây là **số
báo cáo**, không phải kích thước request. Request thật đo bằng `capture_scaffold.py`: ô sạch
tối thiểu ≈ **1.711 ký tự (~400–700 token)**, ô có tools ≈ **26.463 ký tự (~7k token)**.

⇒ **Điểm quan trọng:** completion token của mọi arm sạch = **2** (bằng arm A). Toàn bộ chi phí
token trước đây (×9,6 completion) là do **rò cấu hình**, không phải harness. Phần còn lại là
overhead spawn ~1,8–2,5s/item.

### Audit

4 arm × 100 item: 0 lỗi · 0 gọi mạng · 0 trốn sandbox. (Tool menu ở H6/H8 không bị model dùng:
0 tool call.)

## MC-24 — Trạng thái endpoint IEC 2026-09-27 00:35 + guard `preflight` (chưa chạy được)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-24` |
| `ngay_chay` | 2026-09-27 ~00:35 (+07) |
| `su_kien` | Gateway IEC **nhận TCP 443 nhưng không trả lời HTTP**: `GET /v1/models` và `POST /v1/chat/completions` (call 1 token) đều timeout > 25–60s. Probe lặp 3 lần đều timeout; kết nối TCP tới host:443 mở trong 0,0s. |
| `phat_hien` | Giữa lúc chạy repeat của factorial sạch (MC-23): 6 tiến trình `omp` còn sống nhưng **không checkpoint nào** sau 10 phút. Đã dừng toàn bộ, không ghi nhầm dữ liệu. |
| `guard_moi` | `run_harness_eval.py preflight_endpoint()` — **1 call trực tiếp 1 token, timeout 45s, chạy trước mọi `run`**. Endpoint chết ⇒ `SystemExit` kèm lý do, thay vì biến N item thành N "model failure" giả (mỗi item tốn `--max-time` 180s). Không mất gì: `--resume` nối tiếp từ checkpoint mới nhất. |
| `ly_do_gi` | Arm harness **không có retry** (mỗi item là một tiến trình `omp`); arm A thì có `call_model_with_retry`. Không có preflight thì một sự cố hạ tầng sẽ trông y hệt một kết quả model tệ — đúng cái loại "measurement contamination" mà MC-22 ghi nhận. |
| `viec_cho_lai` | (1) **Repeat 2× mỗi ô factorial sạch** trên 146 item (`ompH5…H8clean_r2/r3`) — đo nhiễu chạy-đến-chạy thay vì giả định; (2) **V-Bench agentic 1.000 item** — arm `ompV1clean` (scaffold sạch + tool menu đầy đủ): đã cài xong (`load_vbench_agentic`, `_vbench_validity`, projection ghi `vbench_valid_summary_*.csv` + `submissions/<slug>/submission_vbench_<slug>.jsonl` để upload lấy điểm server). Cả hai **chưa có số**. |
| `trang_thai` | ⏸ **PENDING** — chạy lại bằng `/tmp/opencode/harness_pending.sh` khi endpoint sống lại (script tự preflight, tự dừng nếu còn chết) |

> **Điểm cần nhớ khi đọc số liệu:** mọi con số trong MC-15…MC-23 đều lấy từ các lần chạy **trước** sự cố;
> không có số nào trong đó bị ảnh hưởng. Không được suy ra gì về sức khỏe endpoint từ dữ liệu cũ.

## MC-25 — Tách **hai** cơ chế chi phí: rò cấu hình = độ trễ, tool menu = token

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-25` |
| `ngay_chay` | 2026-09-27 (số đọc lại từ `speed_summary_*.csv`, không tốn thêm lượt gọi nào) |
| `nguon` | 5 ô ablation đều `n=24`, `workers=4` ⇒ **so sánh được**. Ô H2 của cost probe là `n=40` (khác subset) nên **không dùng để so**; dòng H2 `n=24` thuộc `bidlqa_val`, không phải legal-MC. |
| `dieu_kien` | Cùng item, cùng `workers=4`, cùng model/prompt/scorer. Nguồn: `all_res/ollama_result/ompH{1,3,4,5,8}*/speed_summary_legal_mc_*.csv` |

### Kết quả (per item)

| Arm | Cấu hình | prompt tok | completion tok | wall p50 | overhead |
| --- | --- | ---: | ---: | ---: | ---: |
| H5 | **sạch** · no-tool · sys trung tính | 5.389 | **2** | **2,62s** | +1,81s |
| H4 | rò · no-tool · sys trung tính | 5.763 | **235** | 15,09s | **+5,81s** |
| H3 | rò · tool · sys trung tính | 10.517 | 216 | 15,70s | +5,76s |
| (H1) rò · no-tool · sys của omp | 7.777 | 274 | 16,87s | +5,87s |
| (H8) **sạch** · tool · sys của omp | 12.434 | 2 | 2,85s | +1,83s |

### Hai phép trừ độc lập (cùng n, cùng workers)

| Contrast | Δ prompt tok | Δ overhead | Δ điểm (MC-23) |
| --- | ---: | ---: | ---: |
| **rò `APPEND_SYSTEM.md`** (H5 → H4) | **+140** | **+4,00s** | −14,00đ (theo MC-22) |
| **tool menu** (H4 → H3) | **+4.737** | **−0,05s** | không đáng kể (p ≥ 0,40) |

### Kết luận

1. **Hai cơ chế không cùng bản chất, và trước đây đã bị gộp làm một.** Rò cấu hình gần như *miễn
   phí về input* (+140 token) nhưng cộng **+4,00 giây/item** và làm completion token nhân **117×**
   (2 → 235) — vì nó ép model viết câu trả lời bọc vỏ, mà scorer đóng băng chấm sai (metric phụ:
   `wrapper_cost` +22,25đ trên reading-400 của H2).
2. **Tool menu ngược lại**: **+4.737 token** (tool schema) gần như **0 độ trễ** (−0,05s), và
   **không cộng điểm**. Đây là cái giá cấu trúc của việc "cho agent biết nó có thể làm gì".
3. **Hệ quả cho thiết kế agent**: muốn giảm chi phí độ trễ thì cắt *văn bản* ép dài (system
   prompt/persona), **không phải** cắt tool — cắt tool chỉ đổi token, không đổi độ trễ, lại mất
   khả năng dùng công cụ.
4. **Không được quy**: ô H2 (`n=40`) không dùng để suy ra tương tác persona×tool; `input +
   cacheRead` của gateway IEC không phải kích thước request (MC-19, đã đính chính MC-22).

## MC-26 — V-Bench **agentic** (1.000 item function-calling): nơi scaffold *có thể* thắng — và không thắng chỗ nào

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-26` |
| `ngay_chay` | 2026-09-27 14:28→15:26 (sau khi endpoint hồi sinh lúc 13:55) |
| `dieu_kien` | Arm `ompV1clean`: **scaffold sạch** (`HOME` override ⇒ không rò `APPEND_SYSTEM.md`) + **tool menu đầy đủ** 6 tool, qua `omp`. Prompt = **đóng băng** từ `run_vbench_eval.build_agentic_prompt(style="minimal")` — byte-identical với arm A. Tập: 1.000 row `track=agentic` của vbench.ai release v2026.03.28. Scorer: **validator đóng băng** `_validate_call` (enum verbatim, required present, field bịa bị loại). |
| `metric` | **Schema validity** — có/không có lời gọi hàm hợp lệ theo schema của chính row đó. **KHÔNG có gold**: điểm chính xác chỉ có ở server (vbench.ai), đã ghi file upload `submissions/ompV1clean_Qwen3_5-9B-28K/submission_vbench_*.jsonl` (1.000 dòng, 26 dòng rỗng = invalid, **không đoán bừa**). |

### Kết quả

| | valid | n |
| --- | ---: | ---: |
| arm A (gọi trực tiếp) | **1.000 / 1.000 = 100,00%** | 1.000 |
| arm B (`ompV1clean`) | **974 / 1.000 = 97,40%** | 1.000 |

Δ = **−2,60** (CI 95% −3,60..−1,70; McNemar **p = 2,98e−08**). 2×2: `both 974 | chỉ-A 26 | chỉ-B 0 | không 0`.

Chi phí: `wall 20,7s/item · turns 1,00 · prompt 2.473 tok · completion 138 tok`.
Kiểm định: `0 lỗi · 0 item dùng tool · 3 lần gọi mạng (đều thất bại) · 0 lần trốn sandbox`.

### Kết luận

1. **Ở task duy nhất mà scaffold được cơ hội thắng, nó chỉ thua** — và thua *chặt*: `b_only = 0`
   nghĩa là **không có lời gọi hàm nào** mà arm A làm hỏng mà arm omp làm được. Tính hợp lệ của arm B
   là tập con thật của arm A (974 ⊂ 1.000), không phải đổi chiều.
2. **Model vẫn không dùng tool** dù được cấp đủ 6 tool và đây đúng là bài function-calling:
   `turns = 1,00`, `tool_use_items = 0`. Vòng lặp agent không được kích hoạt; scaffold chỉ thêm
   văn bản, không thêm hành vi.
3. **Cùng cơ chế MC-22 ở dạng nhẹ hơn**: −2,60đ (không phải −14đ) vì ở đây vỏ markdown không làm hỏng
   chấm điểm — validity chỉ hỏi "có JSON hợp lệ không". ⇒ Vỏ **luôn luôn** làm hỏng khi metric là so
   khớp văn bản (EM/accuracy), và **vô hại** khi metric là kiểm tra cấu trúc.
4. **Không được quy**: Δ này là **validity**, không phải accuracy. Muốn so sánh điểm thật phải upload
   submission lên vbench.ai; chưa có số server nào được ghi vào card này.

### Nộp lên vbench.ai — file nào, và đọc số thế nào

| File | Nộp? | Nội dung |
| --- | --- | --- |
| `submissions/ompV1clean_Qwen3_5-9B-28K/submission_vbench_Qwen3_5-9B-28K.jsonl` | ✅ **file này** | **5.141 dòng** = 4.141 MC **nguyên văn của arm A** + 1.000 agentic của arm B. Tên file giống hệt file đã từng nộp thành công. |
| `…_ompV1clean_…jsonl` (bản 1.000 dòng) | ❌ | Chỉ agentic — form từ chối với `JSON.parse: unexpected character at line 1 column 1` (2026-09-28). |

**Cơ chế kiểm chứng:** nửa MC là **đối chứng**. Nếu site trả MC = **47,04%** (đúng số arm A đã có
2026-09-20) thì đường nộp chạy đúng và **con số agentic trả về là của arm B**. Nếu MC khác 47,04%
⇒ có sai sót ở đâu đó, đừng tin số agentic. **Đây là submission hỗn hợp, không phải kết quả thuần
của arm B** — MC là của arm A, chỉ agentic là của arm B.

**Mẫu số phải dùng = 1.000 agentic**, không phải 974: client của site (`Ose`) trả `null` cho answer
rỗng rồi **xoá hẳn dòng khỏi request** ⇒ 26 dòng invalid **không được gửi**. Ta **không** bịa answer
cho chúng (26/26 đều có `raw_response` đầy đủ, `exit_code=0`; chỉ là lời gọi không vượt validator —
lỗi model thật). Nếu site báo `974/974` thì đó là **hiệu ứng thiếu phủ**, không phải model giỏi hơn.

## MC-27 — Mức sàn nhiễu: lặp 2–3× mỗi ô factorial sạch, n=146 (arm A = 87,67%)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-27` |
| `ngay_chay` | 2026-09-27 13:55→14:28 (ngay sau MC-24 hết chặn) |
| `dieu_kien` | Cùng điều kiện MC-23, **lặp lại trên toàn bộ 146 item legal-MC** (thay vì 100 item của MC-23). Slug `ompH5…H8clean_r2_` và `_r3_`; ô H5clean còn có lần gốc ở n=146 nên có **3** lặp. Mọi số đọc từ `harness_compare_legal_mc_vsA_*.csv`. |

### Kết quả — trung bình và dao động trong từng ô (n=146)

| Ô (scaffold sạch) | r1 | r2 | r3 | **TB ô** | **Spread ô** |
| --- | ---: | ---: | ---: | ---: | ---: |
| H5 trung tính × no-tool | 69,18 | 70,55 | 72,60 | **70,78** | 3,42 |
| H6 trung tính × tools | — | 67,81 | 73,29 | **70,55** | **5,48** |
| H7 omp-sys × no-tool | — | 70,55 | 71,23 | **70,89** | 0,68 |
| H8 omp-sys × tools | — | 73,97 | 74,66 | **74,31** | 0,69 |

Mỗi lặp đều có CI riêng (n=146 ⇒ CI 95% rộng ~±7đ) và p so với arm A ≤ 8,8e−04.

### Hai mệnh đề, tách bạch

| Mệnh đề | Số | Phán quyết |
| --- | --- | --- |
| **Phạt khi đi qua tiến trình agent** | Δ = −13,01…−19,86, TB ≈ **−16,3đ** | **Nằm ngoài nhiễu 2,4–3,6 lần**; 8/8 lặt đều p ≤ 8,8e−04 ⇒ **kết luận vững** |
| **Tương tác persona × tool** | H8 − H5 = 74,31 − 70,78 = **+3,53đ** | **Nhỏ hơn spread của chính một ô (5,48)** ⇒ **không phân giải được**; MC-23 dừng ở "không đủ bằng chứng", nay có lý do định lượng |

### Kết luận

1. **Nhiễu chạy-đến-chạy ở `temperature 0` là thật và đo được**: 0,68–5,48đ cho cùng một điều kiện
   trên 146 item. Mọi lần trước (n=100) có CI ±10–14đ nên chưa phân biệt được nhiễu với hiệu ứng.
2. **Lặp không thu nhỏ CI lấy item** (n vẫn 146) — nó tách *nhiễu chạy* khỏi *sai số lấy mẫu*. CI
   bootstrap trên 146 item vẫn ±7đ vì giới hạn đó là của item, không phải của lần chạy.
3. **Không được suy ra** rằng `+3,53đ` của H8 là hướng có lợi thật: nó nhỏ hơn mức mà chính cùng một ô
   biến thiên giữa hai lần chạy. Muốn tách được cần nhiều item hơn, không phải lặp thêm.

## MC-28 — Điểm **server thật** của arm `ompV1clean` + cách vượt WAF của vbench.ai

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-28` |
| `ngay_chay` | 2026-09-28 |
| `su_kien` | Form upload của vbench.ai báo `JSON.parse: unexpected character at line 1 column 1 of the JSON data` cho **mọi** file của ta — kể cả bản 5.141 dòng có nửa MC **giống byte** file từng nộp thành công. |
| `chan_dung` | **Không phải lỗi file.** `POST /api/grade` trả về **HTML** `<title>Request Rejected</title>` + "support ID" ⇒ **F5 BIG-IP/WAF** của site chặn, chứ không phải Cloudflare và không phải service chết. Trình duyệt gọi `await response.json()` trên HTML đó nên báo lỗi JSON — dấu hiệu của *response*, không phải của file. |
| `bang_chung` | (1) file arm A nguyên bản 400.761 byte (từng ra macro 45,22) → **HTTP 200 JSON**; (2) file hỗn hợp của ta 397.923 byte → **Request Rejected**; (3) 974 dòng agentic của ta chia 10 lô × 100 dòng (~28 KB) → **10/10 HTTP 200**; (4) cùng thủ tục áp cho 974…1000 dòng agentic **của arm A** → ra đúng **397/1.000 = 39,70%**, khớp 100% snapshot 2026-09-20 ⇒ **phương pháp chunking chính xác, không lệch**. |

### Điểm server (đây là accuracy thật, khác validity)

| | valid | **accuracy server** |
| --- | ---: | ---: |
| arm A (trực tiếp) | 100,00% | **397/1.000 = 39,70%** |
| arm `ompV1clean` (sạch + 6 tool) | 97,40% | **308/1.000 = 30,80%** |
| **Δ** | −2,60 | **−8,90** |

Artifact: `all_res/ollama_result/ompV1clean_Qwen3_5-9B-28K/vbench_server_scores_ompV1clean_Qwen3_5-9B-28K.csv`
(đúng `SERVER_SCORES_COLS` của repo) + `vbench_server_chunks/resp_*.json` (10 response thô làm bằng chứng kiểm toán).

### Kết luận

1. **Khoản phạt thật lớn hơn nhiều so với validity cho thấy**: −8,90đ accuracy so với −2,60đ
   validity. Tức là phần lớn lỗi của scaffold **không phải "sinh JSON sai"** mà là **gọi đúng hàm sai
   tham số** — validator chỉ bắt được lớp lỗi thứ nhất. Đây là phát hiện quan trọng nhất của MC-26.
2. **Chiều hiệu ứng không đổi, độ lớn tăng gấp 3,4**: ở MC/QA scaffold mất 5,6–22,3đ; ở
   function-calling mất 8,90đ. Nhất quán với "mọi đường elicitation ngoài HTTP trực tiếp đều tốn
   điểm" — và MC-26/28 là bằng chứng mạnh nhất vì đây là nơi scaffold *được lợi thế nhất*.
3. **So với arm A là phép so **bất lợi** cho arm B**, vì số arm A (397) gồm 14 dòng **guided** —
   condition elicitation thứ ba (MC-8). Trừ đi 14 dòng đó thì baseline còn cao hơn, Δ cửa rộng hơn.
   Nói cách khác: **−8,90 là so với trường hợp tốt nhất của arm A**.
4. **Mẫu số 1.000, không phải 974**: server dùng tổng domain đầy đủ làm mẫu số (response trả
   `totalQuestions: 1000` cho agentic dù chỉ nhận 100 dòng/lô), nên 26 dòng không nộp được tính sai.
   Ta **không** bịa answer cho chúng (26/26 có `raw_response` đầy đủ, `exit_code=0` — lỗi model thật).
5. **Không được quy**: đây là **một** lần chạy của arm B (chưa lặp), nên chưa có ước lượng nhiễu cho
   con số 30,80%. Và **không** so sánh với bất kỳ model nào khác (MC-2/MC-2b).

## Quy tắc dùng card

1. **Mỗi lần chạy một khối.** Không sửa khối cũ; chạy lại thì thêm khối mới có `card_id` mới.
2. **Không gộp điều kiện khác nhau** (đặc biệt `minimal` vs `detailed`, có CoT vs không CoT) vào một cột điểm.
3. **Ghi hash.** Output của mỗi lần chạy mang field `measurement_card_hash`.

   ```bash
   sha256sum measurement_card.md
   ```
4. **Trích dẫn.** Mỗi báo cáo mở đầu bằng: *"Điều kiện đo: `MC-<n>`, measurement_card.md"*.
5. **Model đổi thì card đổi.** Không có ngoại lệ.
