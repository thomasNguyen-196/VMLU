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

## Quy tắc dùng card

1. **Mỗi lần chạy một khối.** Không sửa khối cũ; chạy lại thì thêm khối mới có `card_id` mới.
2. **Không gộp điều kiện khác nhau** (đặc biệt `minimal` vs `detailed`, có CoT vs không CoT) vào một cột điểm.
3. **Ghi hash.** Output của mỗi lần chạy mang field `measurement_card_hash`.

   ```bash
   sha256sum measurement_card.md
   ```
4. **Trích dẫn.** Mỗi báo cáo mở đầu bằng: *"Điều kiện đo: `MC-<n>`, measurement_card.md"*.
5. **Model đổi thì card đổi.** Không có ngoại lệ.
