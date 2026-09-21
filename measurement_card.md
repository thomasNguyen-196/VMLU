# Measurement Card — điều kiện đo

Mọi báo cáo, bảng điểm và kết luận rút ra trong repo này **phải trích dẫn file này**.
Một con số không có measurement card đi kèm thì không được đem so sánh với con số khác.

> **Quy tắc:** mỗi lần chạy = một khối bên dưới. Chạy mới thì **thêm khối mới**, không sửa khối cũ.
> Hash của file này (`measurement_card_hash`) phải được ghi vào output của mỗi lần chạy.

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
| `ket_qua` | ⏳ đang chạy (bắt đầu 2026-09-21 ~23:0x) |
| `trang_thai` | 🕓 thay thế MC-14 (aborted trước khi có kết quả); output `full_evaluation_vm14k_*` + `accuracy_vm14k_*` + `submission_vm14k_*`; checkpoint VM14K park riêng; wrapper `code_benchmark/run_vm14k_mc14.sh` (MC-9 finals backup + restore, commit `a172027`) |

> Cùng **caveat bắt buộc** như MC-14: (1) bản phát hành lệch paper + không license; (2) 1.377/12.488 dòng ≠ 4 lựa chọn, 34 dòng option placeholder, 2 dòng question rỗng; (3) ~6% trùng lặp (giữ nguyên, không dedupe); (4) suite ≤4B vs model 9B; (5) chỉ so hướng với V-Bench medicine 38,78%.
> **Lưu ý kỹ thuật:** `workers` là tham số hạ tầng — `temperature 0` + `seed 42` + prompt/parser không đổi; MC-14 chưa từng cho ra kết quả nên hai điều kiện không bị trộn.

## Quy tắc dùng card

1. **Mỗi lần chạy một khối.** Không sửa khối cũ; chạy lại thì thêm khối mới có `card_id` mới.
2. **Không gộp điều kiện khác nhau** (đặc biệt `minimal` vs `detailed`, có CoT vs không CoT) vào một cột điểm.
3. **Ghi hash.** Output của mỗi lần chạy mang field `measurement_card_hash`.

   ```bash
   sha256sum measurement_card.md
   ```
4. **Trích dẫn.** Mỗi báo cáo mở đầu bằng: *"Điều kiện đo: `MC-<n>`, measurement_card.md"*.
5. **Model đổi thì card đổi.** Không có ngoại lệ.
