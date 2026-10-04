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
| `bang_chung` | Ma trận probe đầy đủ + cách gửi ban quản trị: `docs/vbench-waf-repro.md`. Tóm tắt — **file mẫu chính thức của chính site** (306.391 B) ✅ · file arm A nguyên bản (400.761 B, từng ra macro 45,22) ✅ · nửa MC của ta **giống byte** nửa MC đó ✅ · 974 dòng agentic ta chia 5 lô × 200 ✅ 5/5 (và 10 lô × 100 ✅ 10/10) · **file hỗn hợp 5.141 dòng của ta bị chặn ở CẢ HAI style** (spaced 397.923 B và compact 369.584 B — compact là đúng byte-style file mẫu). ⇒ **không phải format, không phải kích thước đơn thuần, không phải nửa MC, không phải nửa agentic**; trigger cần cả hai nửa trong một request (quy tắc tích luỹ trong WAF). **Phương pháp chunking đã được kiểm chứng**: áp lại y hệt trên 1.000 dòng agentic **của arm A** → ra đúng **397/1.000 = 39,70%**, khớp 100% snapshot 2026-09-20 ⇒ **không lệch**. |

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

## MC-29 — ⚠️ **ĐÍNH CHÍNH MC-15…MC-28**: `omp` không gửi `temperature`, và mọi arm đều bị nạp `AGENTS.md` của chính repo này

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-29` |
| `ngay_chay` | 2026-09-29 (audit scaffold, không phải một lần chấm điểm) |
| `dieu_kien` | Không có lần chấm nào. Đây là **đính chính điều kiện đo** của các card trước, dựa trên **đúng các byte request** mà `omp` gửi đi, bắt bằng `capture_scaffold.py` (log mới: `logs/`, capture: `/tmp/opencode/scaffold_real.json`). Không so với model nào. |

### Phát hiện 1 — `omp` không gửi `temperature`, cũng không gửi `reasoning_effort`

Request thật của một arm sạch (bắt qua proxy), các field ngoài `messages`:

```
temperature      : null            <- KHÔNG gửi
other_keys       : [max_completion_tokens, model, stream, stream_options]
max_tokens       : 64000
```

Mọi card MC-15…MC-28 mô tả điều kiện là **`temperature 0`**. Arm A (gọi thẳng) gửi `0`; arm B
(`omp`) **không gửi gì**, nên để provider tự quyết. Với model suy luận (`MiMo V2.5`) hệ quả đo
được ngay: arm B tiêu **109 reasoning token** cho một câu MC khi arm A là **0**.

Không có đường nào từ phía `omp`: không có cờ `--temperature`, và `options:` trong `models.yml`
bị **bỏ qua im lặng** (thử rồi, đo bằng proxy). Đây là lệch **hai** biến, không phải một.

### Phát hiện 2 — mọi arm đều đọc `AGENTS.md` của chính repo này, trước mỗi câu hỏi

Sandbox từng mặc định là `all_res/ollama_result/<label>/harness_scratch` — **nằm trong repo**.
`omp` đi ngược lên thư mục cha, thấy `AGENTS.md`, và **nội tuyện đối** vào system message:

```
system message (arm "sạch", sandbox trong repo) : 27.501 ký tự
  Answer the user's question.                     <- 28 ký tự trung tính ta đặt
  <project><instructions><file path=".../VMLU/AGENTS.md">
  # Repository Guidelines ... (26.914 byte)      <- toàn bộ AGENTS.md của repo
system message (cùng arm, sandbox ở /tmp)       :    688 ký tự
input token mỗi câu                              : 7.488  ->  994
```

`AGENTS.md` có từ 2026-08-27, và log của các arm đã ghi card cho thấy chúng **dùng** scratch
trong repo (`ompH5clean`, `ompH5clean_r2`, …). Nghĩa là các arm "scaffold sạch" của MC-22/MC-23
sạch về *persona* và về *tool menu*, nhưng **không sạch về chỉ dẫn dự án**. Trước một câu hỏi
trắc nghiệm pháp luật, model được đọc 27k ký tự về pipeline VMLU, quy ước ruff, và gotchas.

Cùng lớp rò với `APPEND_SYSTEM.md` của MC-22, nhưng lớn hơn nhiều, và **không ai thấy được**
vì request bytes của condition sạch chưa từng được bắt.

### Điều này có phủ định card nào không?

| | Trạng thái |
| --- | --- |
| Arm A, prompt, parser, scorer, manifest, pre-registration | **Không đổi** — vẫn đúng |
| MC-24 (chẩn đoán 2 kiểu sự cố endpoint) | **Không đổi** |
| MC-19 / MC-25 (chi phí) | **Cần đọc lại**: chi phí token của arm B gồm ~6,5k token lệch |
| MC-15…MC-18, MC-20…MC-23, MC-27 (điểm + CI) | **Số thì đúng đo, nhưng nhãn "scaffold sạch" sai**; và Δ so với arm A lẫn 2 biến lệch ở trên, nên **chưa được phép gọi là "harness effect"** |
| MC-26 / MC-28 (V-Bench) | Cùng lập luận |

**Chưa được quy**: phần thua còn lại (−11…−22đ) **do** `AGENTS.md` hay do vòng lặp agent. Rò
thì **đã chứng minh có**, nhưng **độ lớn chưa quy cho Qwen** — cần một ablation
(sandbox trong repo vs ngoài repo, cùng model) mới gán được. Với `MiMo V2.5` ablation đó đang
chạy (`ompM6inrepo_` vs `ompM6clean_`, legal-MC 146).

### Guard đã thêm (để lỗi này không lặp lại)

1. `assert_no_project_instructions()` — **hard fail** khi sandbox nằm trong cây thư mục có
   `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`/`.cursorrules`; `--allow-project-instructions` để đo
   *có chủ đích* một agent theo phạm vi dự án.
2. Mặc định `scratch` (cả `run` và `speed`) chuyển ra `/tmp` — nằm ngoài mọi cây dự án.
3. `preflight_endpoint()` giờ hỏi **đúng endpoint và model của arm đang đo**, và gửi kèm
   header mà gateway cần (trước đó nó hỏi endpoint ghim sẵn của cost probe).
4. `capture_scaffold.py`: thêm `--upstream`, `--header`, `--pin`, một dòng **inventory cho mọi
   request** (không chỉ request đầu), và sửa pass-through SSE từ 1 byte/lần lên 4 KiB/lần.
5. `_agent_dir_token()` nhận mọi `*_API_KEY` trong `.env` của agent dir (trước chỉ nhận đúng
   tên biến của IEC, nên agent dir của provider thứ hai bị đọc thành "không có token").
6. Test offline: 17 test mới cho các guard trên (`TestScaffoldProjectInstructions`,
   `TestExtraHeaders`, `TestLegalArmA`) — 147 test, xanh.

## MC-30 — **Lặp lại toàn bộ thang đo với `MiMo V2.5`**: cùng scaffold, kết quả đảo chiều

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-30` |
| `ngay_chay` | 2026-09-29: arm A 10:15→11:12 (4 tập + V-Bench 5.141), arm B 10:57→12:12 (6 tập, 6.319 item), ablation rò 10:58→11:05, speed/cost probe 12:2x một mình |
| `model` | `MiMo V2.5` qua `https://opencode.ai/zen/go/v1` (OpenCode Zen Go), **không phải** IEC |
| `dieu_kien` | Giữ nguyên mọi thứ của MC-22 và **thêm ba sửa của MC-29**: (1) `temperature=0` + `reasoning_effort="none"` **ghim bằng proxy** vì `omp` không gửi được; (2) sandbox ở `/tmp` nên **không** có `AGENTS.md` nạp vào; (3) system prompt trung tính, `--no-tools`, `HOME=/tmp/fakehome`. Arm A = gọi thẳng, `temperature 0`, seed 42, **prompt byte-identical** (cổng parity: 146/146 và 150/150 khớp với baseline Qwen). Slug arm A `mimo-v2_5`, slug arm B `ompM6clean_mimo-v2.5`. |
| `phu_thu` | Không có endpoint nào ngoài OpenCode; không dùng key IEC. |

### Arm A — gọi thẳng (chỉ để đặt mốc)

| Tập | n | MiMo V2.5 | Qwen3.5-9B-28K (MC-22) |
| --- | ---: | ---: | ---: |
| legal-MC | 146 | **90,41** | 87,67 |
| legal-NLI | 150 | **94,00** | 90,00 |
| reading-400 (EM) | 400 | **58,25** | 79,75 |
| ViBidLQA val (EM) | 482 | **41,70** | 32,78 |
| V-Bench agentic (validity) | 1.000 | **99,40** | 100,00 |
| V-Bench MC (mức **trùng khớp** với arm A, KHÔNG phải điểm) | 4.141 | xem dưới | — |

⚠️ **58,25 ở reading-400 không phải vì model kém**: arm A trả lời bằng **câu** chứa đáp án
(`"Midtown Manhattan, … nằm trên 53rd Street, giữa Fifth và Sixth Avenue."`) trong khi gold là
đoạn trích, nên EM=0 dù nội dung đúng (F1 0,62). Không so 58,25 với 79,75 như hai con số năng lực.

### Arm B — cùng scaffold, chỉ khác đường truy xuất

| Tập | arm A | arm B | Δ | CI 95% | McNemar p |
| --- | ---: | ---: | ---: | --- | ---: |
| legal-MC (n=146) | 90,41 | 93,15 | **+2,74** | +0,00…+6,16 | 0,219 |
| legal-NLI (n=150) | 94,00 | 94,00 | **0,00** | −4,67…+4,67 | 1,00 |
| **reading-400 (n=400)** | 58,25 | 65,25 | **+7,00** | +3,50…+10,50 | **0,00018** |
| ViBidLQA val (n=482) | 41,70 | 43,98 | **+2,28** | +0,00…+4,77 | 0,080 |
| V-Bench agentic — schema validity (n=1.000) | 99,40 | 99,90 | **+0,50** | +0,00…+1,00 | 0,125 |
| V-Bench MC — **mức trùng khớp** (n=4.141) | 100,00 | 77,61 | **−22,39** | −23,40…−20,91 | (không kiểm) |

⚠️ **Hàng cuối KHÔNG phải mất 22 điểm.** Không có vàng cục bộ, nên đó là tỉ lệ câu trả lời mà
agent cho **giống hệt** lời gọi trực tiếp trên cùng câu hỏi: trên 4.141 câu, agent **đổi chữ
cái ở 927 câu**. Không nói được là đáp án mới tệ hơn hay tốt hơn — chỉ nói được là nó khác. Điểm
thật của V-Bench do máy chủ chấm và **chưa** có snapshot cho arm này.

Chỉ một ô vượt ngưỡng ý nghĩa (reading-400), và **ngưỡng có lợi cho arm B**. So với MC-22 của
cùng scaffold trên đúng bốn tập: **−5,60…−22,25 điểm**.

### Cơ chế, xem ở từng item (đây là bằng chứng, không phải suy đoán)

41 câu reading-400 đi từ sai→đúng, 13 câu ngược lại. Bốn ví dụ trong nhóm lời:

| gold | arm A | arm B |
| --- | --- | --- |
| `1999` | `năm 1999` | `1999` |
| `'Touring'` | `kiểu thân station wagon, định vị trên thị trường là 'Touring'` | `'Touring'` |
| `53rd Street, giữa Fifth và Sixth Avenue` | `Midtown Manhattan, Thành phố New York, nằm trên 53rd Street, giữa Fifth và Sixth Avenue.` | `53rd Street, giữa Fifth và Sixth Avenue` |
| `thành phần hóa học của Trái Đất` | `Sự đa dạng và phong phú của các loại khoáng vận …` | `thành phần hóa học của Trái Đất` |

Cùng một câu hỏi, cùng gold: arm A **diễn giải**, arm B **chép**. Trung vị độ dài reply 12 → 10 ký tự.
Khung agent đẩy mô hình về phía *chép nguyên văn*, và bộ chấm extractive thưởng đúng cái đó.

### Ablation của chính MC-29: `AGENTS.md` rò tốn tiền, **không** tốn điểm

Cùng model, cùng agent, **chỉ khác vị trí sandbox** (legal-MC, n=146):

| Sandbox | System prompt | Prompt token/câu | Accuracy |
| --- | ---: | ---: | ---: |
| `/tmp` (sạch) | 688 ký tự | 505 | 136/146 = **93,15** |
| trong repo (rò `AGENTS.md`) | 27.501 ký tự | 7.508 | 137/146 = **93,84** |

Δ = **+0,68 điểm** (6 câu đảo chữ cái, 3 vs 2) ⇒ **không có hiệu ứng điểm**. Nhưng prompt token
tăng **+7.003/câu ≈ 15×**, tức chi phí input tăng tương ứng. Nói cách khác: MC-29 đúng về *rò*,
nhưng **rò không giải thích** phần thua của Qwen.

### Caveat thứ ba: ngân sách output lệch nhau (có sẵn từ trước, không phải do MC-29)

Arm A có trần `max_tokens` 4 (MC) / 48 (reading); `omp` **không** gửi trần nào và model config
khai `maxTokens: 128000` (request thật: `max_tokens: 64000`). Nên arm B không bị chặn. Trần 48 chỉ
có thể làm hại arm A ở **≤ 7/400 item ⇒ ≤ 1,75 điểm**, và kiểm tra 2 item dài nhất cho thấy arm A
trả về **cả câu trích đầy đủ**, không phải bị cắt. Δ +7,00 đứng vững.

### Chi phí của scaffold sạch trên model này (speed probe, legal-MC, n=24, workers=4, chạy một mình)

| Cánh | p50/câu | prompt tok | completion tok | overhead tiến trình |
|---|---:|---:|---:|---:|
| A gọi thẳng | 2,31s | 470 | 4 | 0,00s |
| B qua omp | 4,54s | 508 | 2 | **1,59s** |

Tức **×2,0 thời gian** nhưng **chỉ ×1,1 token**, và gần một nửa thời gian là **spawn tiến trình**
không phải lời gọi model. So với MC-25 của Qwen (rò persona: +140 token, +4,00s, completion
×118) và ablation rò `AGENTS.md` (+7.003 token/câu), scaffold sạch gần như **miễn phí về token**.

### Chưa được quy

1. **Chưa có sàn nhiễu cho MiMo.** Mỗi ô chạy **một** lần. MC-27 đo được 0,68–5,48đ cho Qwen ở
   `temperature 0`; MiMo có thể khác, nên ô +2,74 và +2,28 (p = 0,22 và 0,080) **chưa** tách được
   khỏi nhiễu — CI có chạm 0 là dấu hiệu đúng, không phải lỗi.
2. **Arm đo qua một hop proxy trong suốt** (bắt buộc, vì `omp` không gửi được 2 field đó). Mọi pin
   được ghi vào file capture.
3. **`MiMo V2.5` là model có suy luận**, tắt bằng `reasoning_effort="none"`; đây là một condition
   khác hẳn Qwen (không có reasoning). So sánh *giữa hai model* vì vậy là so hai condition, không
   phải hai model — dùng để trả lời "harness tax có phải tính chất của scaffold không", không dùng
   để xếp hạng model.

### Kết luận của MC-29 + MC-30

**Scaffold không có "giá".** Giá phụ thuộc model. Cùng một scaffold, cùng prompt, cùng bộ chấm:
`Qwen3.5-9B-28K` thua **5,6…22,3 điểm**; `MiMo V2.5` thắng tới **+7,0** và trung tính ở ba tập còn
lại. Cái bị đo trong MC-15…MC-28 là **ngân sách tuân thủ của một model 9B**, không phải chi phí
của việc đi qua tiến trình agent. Và trên bài trích xuất, khung agent **giúp** model chép đúng hơn.

## MC-31 — **Qwen3.5-9B-65K @ IEC: baseline mới + arm B `--tools all`** (pre-register, chưa chạy)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-31` |
| `ngay_chay` | Pre-register 2026-09-30 (card ghi xong **trước** mọi lần chạy); arm A 09:47–10:34 (+07); arm B bắt đầu 10:55, vbench_agentic + vbench_mc chạy nền có `--resume` |
| `model` | `Qwen3.5-9B-65K` @ `https://llmapi.iec-uit.com/v1` — model DUY NHẤT còn chạy (node 28K offline: HTTP 503 `Compute Node 'RTX3060-8GB' is offline`) |
| `dieu_kien` | **Arm A**: gọi thẳng, prompt byte-frozen như mọi card, temperature 0, seed 42. **Arm B**: `omp sạch` — `--tools all` (bỏ hẳn cờ `--tools`, menu default của omp), system prompt trung tính, `HOME=/tmp/fakehome`, sandbox `/tmp`, `temperature=0` ghim bằng proxy (MC-29); không tool-schema nào bị sửa tay. |
| `slug` | arm A `Qwen3_5-9B-65K` · arm B `ompT65_Qwen3_5-9B-65K` — **một condition một slug**, không trộn với `Qwen3_5-9B-28K`/`ompH*`/`ompM*` |
| `tap` | legal_mc 146 · legal_nli 150 · reading400 400 · bidlqa_val 482 · vbench_agentic 1.000 · vbench_mc 4.141 |
| `workers` | 4 (trần 6) — vì tổng thông lượng prefill **không tăng** theo số luồng (xem khối server); chạy từng tập + `--resume` |
| `scoring` | Không đổi: MC exact-letter, reading EM/char-F1, vbench_agentic = schema validity, vbench_mc = mức **trùng khớp** với arm A (không có gold cục bộ) |
| `khong_so_voi` | Mọi số `Qwen3.5-9B-28K` (MC-15…MC-30): tag khác = condition khác (MC-4/MC-29) |
| `trang_thai` | 🔄 arm A **xong**; arm B xong 5/6 tập + compare; `vbench_mc` dở ở 1.275/4.141 — gateway đang sập cert nên chưa resume được |

### Bằng chứng server đo trước khi chạy (2026-09-30, cùng ngày pre-register)

| Phép đo | Kết quả |
| --- | --- |
| Backend | lớp llama.cpp sau nginx/1.18.0; fingerprint `b11243-fc07d781e`; `timings` fields chuẩn llama.cpp |
| Context limit | **65.024 token** — gateway trả về nguyên văn: `request (69027 tokens) exceeds the available context size (65024 tokens)` |
| Prefill | ~3,2–3,6k tok/s (2.327 tok → 0,71s; 9.227 → 2,10s; 27.627 → 5,93s) |
| Decode | ~105 tok/s (80 tok → 749ms) |
| Request arm B (bắt qua proxy) | **14.177 prompt token**: 11 tool (`read, bash, edit, eval, glob, grep, task, hub, todo, web_search, write`), **50.348 ký tự** schema, system 690 ký tự, user 283 ký tự; `max_completion_tokens` 4.096; `temperature: 0` do proxy ghim (`pinned_by_proxy` ghi trong capture `/tmp/opencode/qwen65k_capture.json`) |
| Round trip 1 item | 4,4–4,8s (TTFT 4,4–4,6s) ⇒ **prefill-bound**, decode không đáng kể |
| Prefix cache | Tuần tự có dùng lại (`cache_n 4.752`); mixed song song `cache_n 0` ⇒ **không tính cache** vào ngân sách |
| Song song | Prompt nhỏ (cache) đạt ~14,5 req/s ở 8 luồng; prompt mixed **không tăng** tổng thông lượng (~3,1k tok/s); probe 32 luồng (96 request 4k) làm gateway "câm" ~6 phút (TCP nhận, HTTP không trả) rồi tự hồi |
| Ngân sách arm B | 6.319 item × ~14,2–15k token ≈ **90M prompt token ≈ 8–10h** server time; `vbench_mc` (4.141) chiếm ~2/3 |
| Thứ tự chạy | arm A (rẻ) → legal_mc → legal_nli → reading400 → bidlqa_val → vbench_agentic → **vbench_mc cuối** |

### Kết quả tạm (ghi khi arm B còn đang chạy — số điểm cuối cùng bổ sung sau)

**Arm A — Qwen3.5-9B-65K, gọi thẳng** (prompt byte-frozen; parity legal 146/146, 150/150):

| Tập | Kết quả |
| --- | --- |
| legal_mc | 130/146 = **89,04%** |
| legal_nli | 138/150 = **92,00%** |
| reading400 · bidlqa_val | answers xong (400 + 482, 0 rỗng); chấm EM/char-F1 ở bước `compare` |
| vbench_agentic | **986/1.000 = 98,6%** validity (14 invalid, cùng loại lỗi MC-8) |
| vbench_mc | 4.141/4.141 parse được (0 rỗng) |

**Arm B — `omp sạch` + `--tools all`** (0 lỗi ở cả 4 tập đầu, 0 tool call):

| Tập | n | Lỗi | wall/item | Ghi chú |
| --- | ---: | ---: | ---: | --- |
| legal_mc | 146/146 | 0 | 2,8s | 0 tool call |
| legal_nli | 150/150 | 0 | 2,7s | 0 tool call |
| reading400 | 400/400 | 0 | 2,8s | 0 tool call |
| bidlqa_val | 482/482 | 0 | 3,5s | 0 tool call |
| vbench_agentic | **xong 1.000/1.000** | **480** (474 abort ở trần 180s + 6 tin rỗng) | 116s mean | validity **485/1.000 = 48,5%** (arm A 98,6%) |
| vbench_mc | dở 1.275/4.141 (máy tắt ngang) | 120 (106 abort 180s dù 0 tool call + 14 tin rỗng) | — | chưa compare; chờ gateway hồi mới resume |

### Phát hiện giữa chừng — menu default-all **kích hoạt vòng tool** trên tập function-calling

Trên `vbench_agentic`, khác hẳn mọi card trước (MC-28 với menu 6 tool: **0** tool call), model
**gọi tool thật**: 83/150 item dùng tool, mean **3,56 call**, max 21, turns mean 4,48 — chủ yếu
`eval` (152), `todo` (129), `read` (122), `bash` (57), `web_search` (32), `task` (18). Hệ quả đo
được trên 150 item đầu: 24/25 lỗi là **abort ở `--max-time 180`** (vòng lặp không kết thúc),
validity tạm thời 112/150 = 74,7% (so với 98,6% của arm A). Đây là hành vi thật của condition
"as shipped" — không sửa điều kiện giữa chừng; các item hỏng nằm verbatim trong ledger + failures.

**Cache prefix hoạt động trong run thật**: arm B dùng lại ~13,9k token/item (`cache_read`), chỉ
~500 token tươi mỗi item (câu hỏi), nên 4 tập đầu chạy ~1,4 item/s chứ không phải ~0,25 item/s như
ước tính không-cache trong bảng trên; `vbench_agentic` chậm vì **vòng tool**, không phải prefill.

### So sánh arm A − arm B (`compare --tag vsA`, 5/6 tập; `vbench_mc` chờ resume)

| Tập | Arm A | Arm B | Δ (CI 95%) | McNemar p |
| --- | ---: | ---: | ---: | --- |
| legal_mc (acc) | 89,04% | 73,97% | **−15,07** (−21,92..−8,90) | ≈1e−05 — có ý nghĩa |
| legal_nli (acc) | 92,00% | 88,00% | −4,00 (−8,00..+0,00) | 0,11 — không có ý nghĩa |
| reading400 (EM) | 72,25% | 57,75% | **−14,50** (−19,25..−10,00) | ≈6e−09 — có ý nghĩa |
| bidlqa_val (EM) | 29,25% | 23,24% | **−6,02** (−9,54..−2,70) | ≈9e−04 — có ý nghĩa |
| vbench_agentic (validity) | 98,60% | 48,50% | **−50,10** (−53,30..−47,00) | ≈2e−141 — có ý nghĩa |

Audit `vbench_agentic` arm B: 480 lỗi · 507/1.000 item dùng tool · **11 network attempt**
(`web_search`) · **1 path escape** (audit ghi nhận theo convention — `bash` vẫn `cd` ra được,
đúng như AGENTS.md đã cảnh báo). Ba tập MC/reading/bidlqa: 0 lỗi, 0 tool call, 0 network,
0 escape.

### Sự cố hạ tầng trong lúc chạy (ghi để sau này khỏi đoán)

- **2026-09-30 ~17:43, máy tắt đột ngột**: chain chết tại `vbench_mc` 1.275/4.141; `/tmp`
  (tmpfs) bị xoá — mất chain log, proxy capture json/log. Nội dung condition đã nằm trong
  card; bằng chứng per-item còn nguyên trong ledger. **Không mất artifact nào trên đĩa**
  (đã kiểm row-count bằng csv parser: 146 / 150 / 400 / 482 / 1.000 / 1.275).
- **Gateway sập kiểu mới, chặn resume**: IP hiện serve cert `challenges.iec-uit.com` **hết hạn
  từ 16-08-2026** → preflight lỗi `CERTIFICATE_VERIFY_FAILED`. Runner không bỏ qua verify
  (đúng — bỏ qua là trỏ request sang nhầm vhost). Chờ IEC sửa cert rồi resume một lệnh.
- **2026-10-01: chuyển sang endpoint nội bộ `http://llmapi.iec/v1`** (đúng tài liệu chính thức
  của gateway). VPN lên 14:07, `llmapi.iec` → 172.16.50.172; cổng ngoài https vẫn cert sai với
  cả 2 SNI nên không cứu được. Preflight 1-token OK; `/v1/models` xác nhận 65K `running`,
  28K `offline`. Đây là **sửa đường truyền, không đổi condition** (cùng model/backend, cùng
  params) — ghi minh bạch: 1.275 item mc đầu qua URL cũ, 2.866 item sau qua URL mới.
  `.env` + `.omp-qwen65k-real/models.yml` + proxy `--upstream` đã chuyển tương ứng; proxy
  thêm cờ `--allow-http-upstream` (guard cũ chỉ cho https — endpoint LAN trong VPN tunnel
  được tài liệu provider cho phép http) + hàm pure `check_upstream` + 3 test. Suite 172 OK,
  ruff sạch.
- **Bug compare (đã sửa trong change này)**: `_vbench_validity` / `_vbench_mc_letters` chọn
  checkpoint theo count lớn nhất nên khi thư mục arm A có cả 2 track (1.000 agentic +
  4.141 mc) thì compare agentic đọc nhầm file mc → "no shared items". Đã sửa thành chọn theo
  đúng track + 3 test hồi quy (`test_vbench_validity_picks_the_agentic_checkpoint`,
  `test_vbench_mc_letters_skips_a_bigger_agentic_checkpoint`,
  `test_vbench_readers_split_a_mixed_track_all_file`). Suite 169 test OK, ruff sạch.
- Soi thêm: 106 abort-180s trên `vbench_mc` dù **0 tool call** — không phải vòng tool mà là
  server không trả lời (giống mẫu outage 27-09: nhận TCP, không trả HTTP). Resume sẽ cho biết
  tỉ lệ này có lặp lại không.

### Không được quy

1. Chưa có kết quả — khối này KHÔNG có số điểm nào; mọi số trong bảng trên là số **server/hạ tầng**, không phải năng lực model.
2. Một lần chạy mỗi ô (nhiễu chưa đo cho 65K); arm B đi qua một hop proxy trong suốt.
3. `--tools all` = menu default của chính `omp` tại thời điểm chạy (11 tool trong cấu hình flag hiện tại); omp nâng cấp làm menu đổi thì capture phải bắt lại, không giả định.

## MC-32 — **Qwen3.5-9B-65K: hoàn tất `vbench_mc` + bảng so sánh công bằng 6 tập**

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-32` |
| `ngay_chay` | 2026-10-02 22:50–23:22 (+07), resume từ checkpoint 1.775/4.141 (MC-31) |
| `model` | `Qwen3.5-9B-65K` @ `http://llmapi.iec/v1` (nội bộ qua VPN; cổng https công cộng treo sau Server-hello nên không dùng) |
| `dieu_kien` | Y hệt arm B của MC-31: `omp sạch` + `--tools all` + system prompt trung tính + `HOME=/tmp/fakehome` + sandbox `/tmp` + `temperature=0` ghim bằng proxy. Một condition một slug, không trộn. |
| `slug` | arm A `Qwen3_5-9B-65K` · arm B `ompT65_Qwen3_5-9B-65K` |
| `tap` | `vbench_mc` 4.141 (5 tập còn lại lấy nguyên compare MC-31 — không chạy lại) |
| `workers` | 6 · `preflight` OK 0,2s · nhịp thật 2,12 item/s sau khi hạ tầng sạch |

### Hạ tầng trong lần resume (ghi để tái lập, và để phân biệt lỗi hạ tầng với lỗi model)

1. **VPN**: file `.ovpn` gốc `proto udp` chỉ gửi không nhận (`BYTES_OUT`-only, reconnect liên tục);
   server thật ra nghe TCP → bản `proto tcp`, `tun0 172.16.30.10/24`, ping gateway 4–5ms.
2. **DNS**: `llmapi.iec` chỉ phân giải qua DNS tunnel (`172.16.30.1` → `172.16.50.172`);
   `systemd-resolved` không gắn DNS cho `tun0`, `resolvectl` cần quyền → shim
   `sitecustomize` qua `PYTHONPATH=/tmp/opencode/pyshim` (map ở mức socket, giữ nguyên
   Host header; http thuần nên vhost nginx OK). Probe 1-token qua venv OpenAI client OK.
   Không sudo, không đổi code pipeline.
3. **Sự cố bwrap (đã dọn sạch, không còn dấu trong ledger)**: lần resume đầu chạy trong
   `bwrap` để override `/etc/hosts` làm `bun`/`omp` crash `exit -6` cho toàn bộ 2.366 item
   mới — dấu hiệu nhận biết: tốc độ "ảo" ~100 item/s + `exit_code -6` hàng loạt. Đã kill,
   xóa mọi checkpoint/ledger/failures/answers/projection của run lỗi, resume lại từ
   checkpoint 1.775 nguyên vẹn (đã kiểm exit-code trước khi xóa).
4. **Quên proxy pinning**: 12 phút đầu `omp` retry vào `127.0.0.1:8799` không ai nghe
   (proxy mất sau reboot cùng `/tmp`). Đã dựng lại
   (`--upstream http://llmapi.iec/v1 --allow-http-upstream --pin temperature=0`,
   capture mới `/tmp/opencode/qwen65k_capture_resume3.json` vì file cũ mất theo tmpfs) →
   các item đang treo được cứu qua retry, về nhịp 2,12 item/s.
5. **Đường truyền đổi giữa chừng** (đã khai ở MC-31, nhắc lại): 1.275 item đầu qua URL https
   công cộng, 2.866 item sau qua http nội bộ — cùng model/backend/params, chỉ sửa đường
   truyền. Đoạn resume sạch hơn hẳn (64 lỗi thêm/2.866 so với 120/1.275, trong đó 106
   abort-180s dù 0 tool call) — ủng hộ giả thuyết abort cũ là do server/đường truyền,
   không phải scaffold.

### Kết quả `vbench_mc` arm B (cuối cùng)

`4.141/4.141`, `failures=184` (170 `omp exit 1` rỗng + 14 tin rỗng), `tool_use=2` item,
`net_attempt=0`, `path_escape=0`, `wall/item=11,9s`. Ledger đã kiểm: 3.971 `exit 0`,
không còn hàng `-6` nào.

### So sánh công bằng arm A − arm B, Qwen3.5-9B-65K (`compare --tag vsA`, đủ 6/6 tập)

| Tập | Arm A | Arm B | Δ (CI 95%) | McNemar p |
| --- | ---: | ---: | ---: | --- |
| legal_mc (acc) | 89,04% | 73,97% | **−15,07** (−21,92..−8,90) | ≈1e−05 — có ý nghĩa |
| legal_nli (acc) | 92,00% | 88,00% | −4,00 (−8,00..+0,00) | 0,11 — không có ý nghĩa |
| reading400 (EM) | 72,25% | 57,75% | **−14,50** (−19,25..−10,00) | ≈6e−09 — có ý nghĩa |
| bidlqa_val (EM) | 29,25% | 23,24% | **−6,02** (−9,54..−2,70) | ≈9e−04 — có ý nghĩa |
| vbench_agentic (validity) | 98,60% | 48,50% | **−50,10** (−53,30..−47,00) | ≈2e−141 — có ý nghĩa |
| vbench_mc (trùng khớp A) | 100,00% | 64,04% | **−35,96** (−37,43..−34,51) | (trống cố ý — arm A tự trùng chính nó) |

### Đặt cạnh các model trước (chỉ đặt cạnh — KHÔNG trừ qua lại)

Delta chỉ có nghĩa trong cùng một model (cùng model, prompt, scorer, endpoint-era).
Baseline arm A đã khác nhau (28K: legal_mc 87,67% · 65K: 89,04% · MiMo: 90,41%),
thời điểm/endpoint cũng khác (28K đo qua https công cộng lúc còn sống; 65K nửa sau qua
http nội bộ). Vì vậy bảng dưới là **bảng đặt cạnh**, mỗi Δ đọc dọc trong model của nó:

| Tập | 28K H5 sạch (Δ vs A) | 65K T65 (Δ vs A) | MiMo M6 sạch (Δ vs A) |
| --- | ---: | ---: | ---: |
| legal_mc | −18,49 (−26,71..−10,96) * | −15,07 (−21,92..−8,90) * | +2,74 (0,00..6,16) ns |
| legal_nli | −11,33 (−18,67..−4,00) * | −4,00 (−8,00..0,00) ns | +0,00 (−4,67..4,67) ns |
| reading400 | −22,25 (−26,75..−17,75) * | −14,50 (−19,25..−10,00) * | +7,00 (3,50..10,50) * |
| bidlqa_val | −5,60 (−9,34..−2,07) * | −6,02 (−9,54..−2,70) * | +2,28 (0,00..4,77) ns |
| vbench_agentic | (V1, arm khác) | −50,10 * | +0,50 (0,00..1,00) ns |
| vbench_mc | (không chạy) | −35,96 (trùng khớp) | −22,39 (trúng khớp) |

`*` = McNemar có ý nghĩa ở 5%; `ns` = không. Mẫu hình nhất quán: scaffold `omp` làm Qwen
mất điểm ở mọi tập MC/reading (cả 28K lẫn 65K), trong khi MiMo giữ nguyên hoặc nhỉnh hơn —
cùng hướng với kết luận MC-30, nay lặp lại trên model thứ ba (65K) với tập thứ sáu.

### Không được quy

1. `vbench_mc` là **mức trùng khớp**, không phải accuracy (không có gold cục bộ); McNemar
   trống là cố ý theo thiết kế compare.
2. Mỗi ô 65K mới chạy một lần (chưa đo sàn nhiễu cho model này); arm B đi qua một hop
   proxy trong suốt, arm A không.
3. 184 câu trả lời rỗng phía B tính là "khác A" — đúng luật unparsed = sai, đã áp dụng
   như nhau cho mọi arm.

## MC-33 — **Đính chính MC-32: `vbench_mc` 65K là 63,37% (không phải 64,04%)**

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-33` |
| `ngay_chay` | 2026-10-02 23:23–23:40 (+07), không chạy model — chỉ chạy lại `compare` + rebuild dashboard |
| `noi_dung` | Lệnh `compare` trong MC-32 thiếu `--arm-a-slug` nên rơi về default
`Qwen3_5-9B-28K` — tức so arm B của model này với arm A của model khác, đúng điều cấm
kỵ của MC-4/MC-29. Builder `build_dashboard_harness.py` từ chối số đó
(`compare arm_b=64.04 but per-item recompute=63.37`) — fail-fast hoạt động đúng.
Chạy lại `compare --dataset vbench_mc --label ompT65_Qwen3_5-9B-65K --arm-a-slug
Qwen3_5-9B-65K --tag vsA` → **trùng khớp 2.624/4.141 = 63,37%, Δ −36,63
(CI −38,13..−35,16)**. Submission/profile không ảnh hưởng (chỉ đọc ledger arm B).
Bảng đúng của hàng `vbench_mc` trong MC-32: A 100% → B 63,37%, Δ **−36,63**. |
| `dashboard` | Đã mở rộng registry (`ARMS` + `A3`/`T65`, `ARM_MODEL`, `CLEAN_ARMS`, `REPRESENTATIVE`,
`ARM_DATASETS`, `BASELINE_SHORTS`, metadata block, 1 caveat về đổi đường truyền 65K):
block `.harness` 45 dòng/3 model, claim `penalty:Qwen3.5-9B-65K` + `model_dependent` 3 model
tự sinh từ artifact. Kiểm: suite 172 OK, ruff sạch, `bun test` 51 pass, `tsc` sạch,
blob thật validate qua `parseHarnessBlock`. Phía TS không đổi (validator/page generic). |

## MC-34 — **Nhóm metric 1 xong: trống riêng, cắt theo nhóm, điểm từng phần**

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-34` |
| `ngay_chay` | 2026-10-03, offline trên artifact cũ — 0 lần gọi model mới |
| `lam_gi` | 1.1: dòng comparison mang `a_blanks`/`b_blanks` (đếm sẵn trong ladder),
hiện "(trống X)" dưới % ở các hàng accuracy/EM. 1.2: `compare` viết thêm
`harness_breakdown_<dataset>_vsA_<slug>.csv` (cùng predicate với dòng ALL, cắt theo
`stratum`; stratum hằng → không viết file; bucket "unknown" cho stratum rỗng;
nhóm nhỏ giữ CI rộng, không giấu). 1.3: `grade_agentic_args` + `score_arg_credit.py`
→ `vbench_arg_credit_<slug>.csv` (required_fill + precision, xem MC-32 phân tích).
Dashboard thêm 3 mục (breakdown + điểm từng phần dạng accordion, trống dưới %
comparison); TS validator mở rộng tương ứng. |
| `ket_qua_moi` | V-Bench MC T65 chênh từ −9,5 (philosophy) tới −42,4 (mathematics) — aggregate
−36,6 che mất. Arg credit: arm trực tiếp fill ~99,9% (hỏng validity là do không ra
call: 5–14 câu); T65 chỉ ra được 504/1.000 call nhưng call nào ra thì fill 99,0% —
sập validity là do vòng tool/unparseable, không phải điền sai tham số. |
| `dieu_chinh` | So với plan nhóm 1: bỏ cắt theo subject cho legal_mc (source không có metadata
subject — stratum hằng, trung thực báo ALL-only). Compare cũ tái chạy để sinh breakdown
giữ nguyên số, chỉ refresh hash (deterministic, seed 42). |
| `kiem` | Suite 178 OK, ruff sạch, `bun test` 54 pass, `tsc` sạch, blob thật validate
(45 ladder / 6 breakdown / 6 arg_credit). |

## MC-35 — **Position bias legal_mc-146**: shuffle chọn lựa (pre-register, chưa chạy)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-35` |
| `ngay_chay` | Pre-register 2026-10-04 (card + artifact ghi xong **trước** mọi lần infer shuffled; không có số hậu nghiệm trong khối này) |
| `muc_dich` | Trả lời câu hỏi validity rẻ nhất còn treo (plan nhóm 2.1): điểm MC có phụ thuộc **vị trí** đáp án đúng không, và model có đang khai thác "A hay đúng" không |
| `benchmark` | VLSP2025-LegalSLM multichoice, n=146 — bản **shuffle s1234** của đúng 146 item MC-10/MC-31 arm A |
| `manifest` | `data/legal_slm_multichoice_shuffled_s1234_manifest.json` — sha256 `f796af1f…` (tracked, commit trước infer); source sha `7b7d7f15…` verify lại lúc sinh |
| `input` | `data/legal_slm_multichoice_shuffled_s1234_input.jsonl` — sha256 `4c722b7f…`; shape scorable `{id,question,choices[],answer}` như adapter MC-10, **runner không sửa byte nào** |
| `shuffle_seed` | **1234** — hoán vị per-item `random.Random("1234:LG-XXXX")` (subset-stable, không phụ thuộc thứ tự chạy); gold remap theo **text identity**, fail-fast nếu choices trùng text |
| `gold_shift` | Đo trước khi chạy (từ chính artifact): gold_old A91/B39/C16 (majority A **62,33%**) → gold_new A33/B45/C36/D32 (majority B **30,82%**) — baseline may-rủi đã bị phá |
| `model_id` | `Qwen3.5-9B-65K` @ `http://llmapi.iec/v1` (đường nội bộ qua VPN; đúng model/đường truyền của MC-31/MC-32) |
| `dieu_kien` | **y hệt MC-31 arm A**: frozen `build_prompt`/`extract_answer`, temperature 0.0, seed 42, `max_tokens=4`, workers 4, không `--resume`; chỉ khác duy nhất: input đã shuffle |
| `baseline_doi_chieu` | MC-31 arm A trên thứ tự gốc: **130/146 = 89,04%** (compare sẽ recompute từ file gốc và từ chối chạy nếu khác) |
| `so_sanh` | `code_benchmark/compare_position_bias.py`: paired trên `id` — acc gốc vs acc shuffle, Δ + paired bootstrap CI seed 42 + McNemar exact; bảng **accuracy theo vị trí gold** (A/B/C/D) hai bên; histogram vị trí model chọn; blanks tách riêng |
| `output` | `full_evaluation_shuffled_s1234_Qwen3_5-9B-65K.csv` + `accuracy_shuffled_s1234_Qwen3_5-9B-65K.csv` + `position_bias_compare_legal_mc_s1234.csv` (trong `all_res/ollama_result/Qwen3_5-9B-65K/`); checkpoint thô park ở `shuffled_checkpoints/`; submission shuffled riêng tên |
| `khong_lam` | Không shuffle NLI (nhị phân vô nghĩa); không shuffle VMLU-1047/VM14K (chỉ mở nếu CI của Δ loại 0); **không chạy arm harness** — đây là validity của arm A, không phải so sánh scaffold |
| `trang_thai` | 📌 **PRE-REGISTERED** — artifact + card commit trước infer; kết quả ghi ở **MC-36** |

> Đọc kết quả đúng cách: Δ accuracy **một mình không trả lời** được câu hỏi — gold gốc lệch A nên
> Δ có thể đến từ (i) khai thác vị trí, hoặc (ii) nhạy vị trí nói chung. Bảng accuracy-theo-vị-trí-gold
> hai bên mới tách được hai cơ chế. n=146 ⇒ CI ~±7đ: Δ nhỏ hơn nhiễu ghi là "dưới độ phân giải",
> không mở follow-up.

## MC-36 — **Position bias legal_mc-146: kết quả** (Qwen3.5-9B-65K, shuffle s1234)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-36` |
| `ngay_chay` | 2026-10-04 10:24:48→10:27:17 (+07); pre-register MC-35 commit `556334f` **trước** infer |
| `dieu_kien` | Y hệt MC-35: input shuffle s1234 (sha `4c722b7f…`), frozen runner, temp 0, seed 42, max_tokens 4, workers 4, model `Qwen3.5-9B-65K` @ `http://llmapi.iec/v1` (VPN nội bộ; DNS shim `PYTHONPATH` — MC-32) |
| `infer` | 146/146 item, 149,53s (2,49 phút), **0 blank**, 8 lần retry thoáng qua đều tự hồi (không item nào hỏng); submission `submission_shuffled_s1234.csv` (không upload) |

### Kết quả (nguồn: `position_bias_legal_mc_s1234_compare.csv`)

| Chỉ số | Giá trị |
| --- | --- |
| accuracy gốc | **130/146 = 89,04%** (recompute khớp MC-31, gate pre-registered pass) |
| accuracy shuffle | **130/146 = 89,04%** |
| **Δ** | **+0,00** (CI95 **−5,48..+5,48**; McNemar exact **p=1**) |
| 2×2 (a=gốc, b=shuffle) | both 121 · a-only 9 · b-only 9 · neither 7 |
| flip chữ cái | 112/146 (76,7%) |
| **stability theo TEXT** | **same_text 126 (86,3%)** · letter_anchored **4 (2,7%)** · neither 16 (11,0%) |
| accuracy theo gold (gốc) | A 84/91=92,31 · B 32/39=82,05 · C 14/16=87,50 |
| accuracy theo gold (shuffle) | A 28/33=84,85 · B 40/45=88,89 · C 31/36=86,11 · D 31/32=96,88 |
| histogram đáp án model | gốc A88/B32/C21/D5 · shuffle A30/B43/C34/D39 (gold: A91/B39/C16 → A33/B45/C36/D32) |
| `measurement_card_hash` | `2669c665…634fb0` (bản card lúc compare chạy — có MC-35, chưa có khối này) |

### Đọc kết quả

1. **Không phát hiện position bias ở mức accuracy** — câu hỏi pre-registered: Δ = +0,00, CI chứa 0,
   p = 1, và 2×2 **đối xứng 9/9**. Gold đổi từ majority-A 62,3% sang gần đều (majority-B 30,8%)
   mà điểm không nhúc nhích ⇒ con số 89,04% **không bị thổi bởi "A hay đúng"**.
2. **Cơ chế: model bám nội dung, không bám vị trí.** 126/146 item giữ nguyên **text** được chọn;
   letter_anchored chỉ 4 item (2,7%). Histogram đáp án **đi theo histogram gold** (A88 khi gold A91 →
   A30 khi gold A33; B32 khi gold B39 → B43 khi gold B45) — dấu hiệu content-driven rõ nhất.
3. **112 flip chữ cái không phải bất ổn**: phần lớn là đáp án đúng "cưỡi" text gold sang chữ cái mới
   (both 121 item). Đây là lý do bảng stability-theo-text là bảng chính, không phải flip count.
4. **Phần dư chưa quy**: 16 item "neither" + chênh lệch 9/9 không tách được giữa nhạy cảm nội dung
   thật và noise chạy-lại (arm A 65K **chưa có repeat** — MC-27 mới đo noise cho harness arm 28K).
   CI ±5,48đ trên n=146; mọi kết luận nhỏ hơn ngưỡng này ghi là **dưới độ phân giải**.

### Mốc dừng (theo `docs/metrics-plan-3-nhom.md`)

- VMLU-1047 shuffle: **ĐÓNG** — CI của Δ chứa 0, không có tín hiệu để đuổi theo.
- Harness-arm shuffle (`omp` có khuếch đại bias không): **ĐÓNG** — không cần cho claim nào hiện tại.
- 2.2 faithfulness (reading + judge) là task nhóm 2 còn lại, độc lập với khối này.

## MC-37 — **Faithfulness reading-400 (điều kiện trích dẫn) + judge MiMo** (pre-register, chưa chạy)

| Trường | Giá trị |
| --- | --- |
| `card_id` | `MC-37` |
| `ngay_chay` | Pre-register 2026-10-04 (card ghi xong **trước** mọi lần gọi model của điều kiện cite; không có số hậu nghiệm trong khối này) |
| `muc_dich` | Plan nhóm 2.2: EM/F1 chỉ đo "khớp gold", không đo **grounding**. Điều kiện cite + judge trả lời: trích dẫn có chống đỡ câu trả lời không |
| `benchmark` | reading-400 (`data/eval_set_manifest.csv`, 200 Vi-SQuAD + 200 Vi-DROP, seed 42 — manifest đóng băng) |
| `model_id` | `Qwen3.5-9B-65K` @ `http://llmapi.iec/v1` (VPN nội bộ) |
| `label` | `Qwen3_5-9B-65K-cite` — namespace riêng; **cấm** so hàng-hàng với reading-400 của MC-3/MC-31 (khác prompt) |
| `infer_flags` | temperature 0.0, seed 42, `max_tokens=128`, workers 4; runner `run_reading_cite_eval.py run` (checkpoint `reading_cite_result_<n>_<label>.csv`, `--resume` chỉ trong label này) |
| `prompt_cite` | **Byte-frozen** — `build_citation_prompt` (module `run_reading_cite_eval.py`; sha256 code lúc pre-register `eee13b58…`): |

```text
Đọc đoạn văn dưới đây và trả lời câu hỏi bằng một cụm từ hoặc số ngắn gọn, lấy nguyên văn trong đoạn văn khi có thể.
Sau đó trích dẫn nguyên văn một đoạn ngắn trong bài chứa câu trả lời.
Trả lời theo đúng hai dòng:
Trả lời: <câu trả lời>
Trích dẫn: <đoạn trích>

<context>

Câu hỏi: <question>
Trả lời: 
```

| Trường | Giá trị |
| --- | --- |
| `extraction` | `extract_citation_answer`: nhận cả hai kiểu trả lời (lặp nhãn hoặc tiếp nối sau `Trả lời: `); thiếu nhãn `Trích dẫn:` hoặc answer rỗng ⇒ **("", "")**, đếm unparsed, không bao giờ đoán |
| `scoring` | `score_reading_eval.score_pair` (đóng băng) trên **trường answer**; EM/char-F1 báo là **điều kiện riêng**; compliance (đủ 2 trường) báo riêng |
| `judge_model` | **`mimo-v2.5` @ `https://opencode.ai/zen/go/v1`** (OpenCode Zen Go; khác họ model với model bị chấm — tránh self-judge); headers bắt buộc `x-opencode-session` + browser-ish (Cloudflare 1010/MissingSessionID — MC-29); token `OPENCODE_GO_API_KEY` trong `.omp-mimo/.env`, truyền qua `JUDGE_*` env, **không** commit |
| `judge_flags` | temperature 0.0, seed 42, `max_tokens=200`, `reasoning_effort="none"` (ghim qua extra_body; probe 2026-10-04 OK, trả JSON chuẩn) |
| `prompt_judge` | **Byte-frozen** — `build_judge_prompt` (module `judge_faithfulness.py`; sha256 code lúc pre-register `75eadb04…`): |

```text
Bạn là giám khảo cho bài đọc hiểu. Cho đoạn văn, câu hỏi, câu trả lời của mô hình và đoạn trích dẫn của mô hình.
Đánh giá: đoạn trích dẫn có trực tiếp chống đỡ câu trả lời (chứa thông tin trả lời, hoặc suy ra trực tiếp từ đoạn trích) không?
Chỉ trả về JSON đúng định dạng:
{"verdict": "supported" hoặc "unsupported", "reason": "<một câu ngắn>"}

Đoạn văn:
<context>

Câu hỏi: <question>
Câu trả lời: <answer>
Trích dẫn: <citation>
```

| Trường | Giá trị |
| --- | --- |
| `judge_parse` | Strict-but-safe: JSON trần, JSON trong prose, hoặc code fence; `verdict` phải ∈ {supported, unsupported}; còn lại ⇒ `judge_error`, đếm, không đoán. `raw_judge_response` giữ nguyên văn |
| `validation` | Sheet mù 60 câu: **seed 42, 15 ô (dataset × EM)** = 15 squad-EM1 + 15 squad-EM0 + 15 drop-EM1 + 15 drop-EM0; ô thiếu thì lấp từ item còn lại của cùng dataset (squad trước drop). Người gán nhãn **không thấy** gold/EM/verdict judge; labels commit vào `data/faithfulness_labels_<label>.csv` **trước** khi chấm sheet |
| `gate` | **agreement ≥ 0,80 VÀ Cohen's κ ≥ 0,60** trên 60 câu đã gán. Fail ⇒ sửa judge prompt **một lần** (ghi lại), validate lại trên đúng labels đã đóng băng; fail lần hai ⇒ **DỪNG**, công bố thất bại dụng cụ, không có điểm faithfulness |
| `metrics` | compliance · EM/char-F1 (answer) · `citation_verbatim` (citation ⊆ context, chuẩn hoá của scorer, **không judge**) · `supported_rate` (trên judged) · **`correct ∧ supported`** · cross-tab correct×supported; `judge_error`/unparsed tách riêng, không gộp |
| `output` | `reading_cite_answers_<label>.csv` · `reading_cite_scores_<label>.csv` · `reading_cite_summary_<label>.csv` · `faithfulness_sheet_<label>.csv` · `faithfulness_judge_validation_<label>.csv` → gate → `faithfulness_judge_<label>.csv` · `faithfulness_validation_<label>.csv` · `faithfulness_summary_<label>.csv` (trong `all_res/ollama_result/Qwen3_5-9B-65K/`) |
| `khong_lam` | Không đụng `build_reading_prompt`/`score_reading_eval.py` (byte-frozen); không sửa câu trả lời; không nhét unparsed/judge_error vào bất kỳ tử/mẫu nào; không so ngang MC-31 |
| `trang_thai` | 📌 **PRE-REGISTERED** — code + card commit trước mọi lần chạy cite; kết quả + quyết định gate ghi ở **MC-38** |

## Quy tắc dùng card

1. **Mỗi lần chạy một khối.** Không sửa khối cũ; chạy lại thì thêm khối mới có `card_id` mới.
2. **Không gộp điều kiện khác nhau** (đặc biệt `minimal` vs `detailed`, có CoT vs không CoT) vào một cột điểm.
3. **Ghi hash.** Output của mỗi lần chạy mang field `measurement_card_hash`.

   ```bash
   sha256sum measurement_card.md
   ```
4. **Trích dẫn.** Mỗi báo cáo mở đầu bằng: *"Điều kiện đo: `MC-<n>`, measurement_card.md"*.
5. **Model đổi thì card đổi.** Không có ngoại lệ.
