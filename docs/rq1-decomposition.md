# RQ1 — Phân rã biến động (sinh tự động, đừng sửa tay)

Sinh bởi `code_benchmark/build_rq1_decomposition.py` từ artifact của các card.
**Không con số nào được gõ tay**; thiếu artifact thì script dừng, không bỏ dòng.

Câu hỏi: *trong một điểm benchmark, bao nhiêu là năng lực model và bao nhiêu là kỹ thuật harness?* Mỗi dòng là một **gene** đổi một thứ, giữ model cố định.

## Scaffold gene (điểm chính)

Cùng model, cùng item, cùng scorer — chỉ khác là có đưa prompt qua agent `omp` hay không.

| model | dataset | metric | n | gọi thẳng | qua omp | Δ | CI 95% | p | card |
|---|---|---|---:|---:|---:|---:|---|---:|---|
| Qwen3.5-9B-65K | legal_mc | accuracy | 146 | 89.04 | 73.97 | **-15.07** | [-21.92, -8.90] | 1.0e-05 | MC-31/32 |
| Qwen3.5-9B-65K | legal_nli | accuracy | 150 | 92.00 | 88.00 | **-4.00** | [-8.00, 0.00] | 0.109 | MC-31/32 |
| Qwen3.5-9B-65K | reading400 | EM | 400 | 72.25 | 57.75 | **-14.50** | [-19.25, -10.00] | 6.4e-09 | MC-31/32 |
| Qwen3.5-9B-65K | bidlqa_val | EM | 482 | 29.25 | 23.24 | **-6.02** | [-9.54, -2.70] | 9.1e-04 | MC-31/32 |
| Qwen3.5-9B-65K | vbench_mc | agreement_with_arm_A | 4141 | 100.00 | 63.37 | **-36.63** | [-38.13, -35.16] | — | MC-31/32 |
| Qwen3.5-9B-65K | vbench_agentic | valid_rate | 1000 | 98.60 | 48.50 | **-50.10** | [-53.30, -47.00] | 1.9e-141 | MC-31/32 |
| Qwen3.5-9B-28K | legal_mc | accuracy | 146 | 87.67 | 69.18 | **-18.49** | [-26.71, -10.96] | 1.4e-05 | MC-23 |
| Qwen3.5-9B-28K | legal_mc | accuracy | 146 | 87.67 | 70.55 | **-17.12** | [-24.66, -10.27] | 1.1e-05 | MC-23 (lặp) |
| Qwen3.5-9B-28K | legal_mc | accuracy | 146 | 87.67 | 72.60 | **-15.07** | [-21.92, -8.22] | 5.9e-05 | MC-23 (lặp) |
| MiMo V2.5 | legal_mc | accuracy | 146 | 90.41 | 93.15 | **2.74** | [0.00, 6.16] | 0.219 | MC-30 |

## Persona × tools (trên scaffold sạch, model 28K)

Câu hỏi tiếp: phần mất điểm là do **cái scaffold**, hay do những thứ ta thêm vào nó?

| gene | n | đối chiếu | Δ | CI 95% | đọc |
|---|---:|---|---:|---|---|
| tools (danh mục tool) | 100 | thêm tool menu, giữ persona tối giản | **-1.00** | [-11.00, 10.00] | CI chạm 0 → **thêm tool không giúp** |
| persona (system prompt) | 100 | đổi sang system prompt của omp, giữ không tool | **-2.00** | [-13.00, 9.00] | CI chạm 0 → **đổi persona không giúp** |
| tools × persona | 100 | cả tool menu lẫn persona của omp | **5.00** | [-4.00, 14.00] | CI chạm 0 → **cả hai cùng lúc vẫn không giúp** |

## Option order (gene thứ ba)

| dataset | metric | n | giữ nguyên | đảo (seed 1234) | Δ | CI 95% | p | card |
|---|---|---:|---:|---:|---:|---|---:|---|
| legal_mc | accuracy | 146 | 89.04 | 89.04 | **0.00** | [-5.48, 5.48] | 1 | MC-36 |

⇒ Thứ tự lựa chọn **không** phải nguồn biến động ở model này (MC-36: 126/146 trả lời theo nội dung, chỉ 4 neo chữ cái).

## Nhiễu lặp lại (noise floor) — mọi contrast phải lớn hơn mức này

Cùng một điều kiện, chạy lại, cùng `n`. Không lặp lại thì không thu nhỏ được CI lấy mẫu, nhưng nó tách **nhiễu chạy** khỏi **sai số lấy mẫu** — một contrast nhỏ hơn độ trải này không phải kết quả.

| cell | n | số lần chạy | min | max | độ trải |
|---|---:|---:|---:|---:|---:|
| ompH5clean | 146 | 3 | 69.18 | 72.60 | **3.42** |
| ompH6clean | 146 | 2 | 67.81 | 73.29 | **5.48** |
| ompH7clean | 146 | 2 | 70.55 | 71.23 | **0.68** |
| ompH8clean | 146 | 2 | 73.97 | 74.66 | **0.69** |

## Calibration (đặc tính của điểm số, không phải một gene)

| dataset | n | accuracy | conf TB | ECE | over-conf | card |
|---|---:|---:|---:|---:|---:|---|
| legal_mc | 146 | 90.41 | 83.02 | 8.41 | -7.39 | MC-44 |
| vmlu_mqa_all_gold | 1047 | 71.73 | 78.31 | 6.51 | +6.58 | MC-44 |

## Đọc tổng hợp

1. **Scaffold là gene duy nhất có hiệu ứng lớn** — và dấu của nó **phụ thuộc model**: Qwen3.5-9B-65K mất hàng chục điểm, MiMo V2.5 *được* điểm. Không có một "cái giá của harness" nếu chưa nói rõ model nào.
2. **Persona và tool menu gần như vô hiệu** (CI chạm 0) ⇒ phần mất điểm không phải do những gì ta thêm vào, mà do **chính cái scaffold**.
3. **Option order sạch** trên MC ⇒ biến động không đến từ vị trí lựa chọn.
4. **Calibration đổi chiều theo độ khó** ⇒ một điểm số không kèm độ tin cậy thì không diễn giải được (MC-44).

## Không được quy

- **Model khác không phải là một contrast.** MiMo nằm trong bảng scaffold như một hàng riêng của *model pair* khác; so Qwen với MiMo không phải là so harness.
- **Metric khác nhau không xếp hạng được.** `accuracy`, `EM`, `agreement_with_arm_A`, `valid_rate` là bốn thứ khác nhau; bảng nêu tên từng metric thay vì gộp.
- **Noise floor chỉ có cho model 28K** (4 cell × 2–3 lần chạy, n=146). Ở 65K mới chỉ có một cặp đo gián tiếp (130 → 132/146, MC-44) — đủ để biết có nhiễu, **không đủ** để đặt ngưỡng. Các contrast 65K rộng hơn nhiều lần nên không bị nhiễu này nuốt, nhưng một contrast 65K nhỏ thì chưa có sàn.
- **n=100 ở các ô factorial** → CI rộng hơn ô n=146; đừng đọc độ lớn điểm khác nhau giữa hai bảng là khác nhau về hiệu ứng.
- **Scaffold của `omp` có lịch sử rò** (MC-22): `APPEND_SYSTEM.md` của máy. Các ô ở đây là scaffold **sạch** (HOME override) hoặc arm A; đừng trộn arm H2/H3 (có rò) vào đây.
