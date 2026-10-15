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

## Factorial persona × tools trên **65K** (MC-46/47)

Mỗi ô so với **cùng arm A3** của chính model này — cùng cơ sở, nên dấu của Δ đọc được thẳng. Các contrast **gene** (giữ một ô cố định) ở bảng dưới, có CI ghép đôi.

| ô | tools | system prompt | arm B | Δ vs A3 | CI 95% | p |
|---|---|---|---:|---:|---|---:|
| `ompF5clean_Qwen3_5-9B-65K` | none | minimal (--system-prompt minimal) | 87.67 | **-1.37** | [-5.48, 2.74] | 0.754 |
| `ompF7clean_Qwen3_5-9B-65K` | none | gốc của omp | 79.45 | **-9.59** | [-15.07, -4.11] | 0.001 |
| `ompF8clean_Qwen3_5-9B-65K` | all | gốc của omp | 73.29 | **-15.75** | [-22.60, -8.90] | 3.4e-05 |
| `ompT65r2_Qwen3_5-9B-65K` | all | minimal (--system-prompt minimal) | 76.03 | **-13.01** | [-19.86, -6.16] | 3.1e-04 |

| contrast gene (paired) | giữ cố định | Δ | CI 95% | p | đọc |
|---|---|---:|---|---:|---|
| thêm tool menu | persona = minimal | **-11.64** | [-17.81, -5.48] | 4.9e-04 | **làm hỏng** |
| thêm tool menu | persona = gốc omp | **-6.16** | [-10.96, -1.37] | 0.022 | **làm hỏng** |
| system prompt của omp | tools = none | **-8.22** | [-13.01, -3.42] | 0.002 | **làm hỏng** |
| system prompt của omp | tools = all | **-2.74** | [-6.16, 0.00] | 0.219 | không đọc được |
| tools × persona | hiệu ứng tools có nhân với persona không | **5.48** | [-5.48, 16.44] | — | không đọc được |

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
| ompT65 | 146 | 2 | 74.66 | 76.03 | **1.37** |

## Calibration (đặc tính của điểm số, không phải một gene)

| dataset | n | accuracy | conf TB | ECE | over-conf | card |
|---|---:|---:|---:|---:|---:|---|
| legal_mc | 146 | 90.41 | 83.02 | 8.41 | -7.39 | MC-44 |
| vmlu_mqa_all_gold | 1047 | 71.73 | 78.31 | 6.51 | +6.58 | MC-44 |

## Đọc tổng hợp

1. **Gene nào quan trọng thì phụ thuộc model.** Ở 65K, ô scaffold tối giảu (không tool, system prompt trung tính) gần như **miễn phí** (−1,37; CI chạm 0) — cái tốn điểm là **những gì thêm vào nó**: tool menu (−11,64 / −6,16) và system prompt của omp (−8,22 khi không tool). Ở 28K thì **ngược lại**: hai gene đó CI chạm 0 còn scaffold mất 15–18 điểm. Cùng một cấu hình, hai kết luận khác nhau.
2. **Dấu của scaffold phụ thuộc model**: Qwen3.5-9B-65K mất hàng chục điểm, MiMo V2.5 *được* điểm (+2,74). Không có một "cái giá của harness" nếu chưa nói rõ model nào.
3. **Option order sạch** trên MC ⇒ biến động không đến từ vị trí lựa chọn (MC-36).
4. **Calibration đổi chiều theo độ khó** ⇒ một điểm số không kèm độ tin cậy thì không diễn giải được (MC-44).
5. **Tương tác tools × persona không đọc được** (CI rộng) ⇒ chưa được quy là hai gene nhân lên nhau; cần thêm lặp để thu hẹp.

## Không được quy

- **Model khác không phải là một contrast.** MiMo nằm trong bảng scaffold như một hàng riêng của *model pair* khác; so Qwen với MiMo không phải là so harness.
- **Metric khác nhau không xếp hạng được.** `accuracy`, `EM`, `agreement_with_arm_A`, `valid_rate` là bốn thứ khác nhau; bảng nêu tên từng metric thay vì gộp.
- **Noise floor: 28K có nhiều lần hơn 65K.** 5 cell, 2–3 lần chạy mỗi cell. Ở 65K mới có **2** lặp cùng shape ⇒ sàn 65K yếu hơn hẳn; một contrast 65K nhỏ hơn sàn đó thì chưa đọc được. Ngoài ra MC-44 đo trực tiếp một cặp arm A ở 65K (130 → 132/146) — đó là nhiễu của **đường gọi thẳng**, khác đường harness.
- **n=100 ở các ô factorial** → CI rộng hơn ô n=146; đừng đọc độ lớn điểm khác nhau giữa hai bảng là khác nhau về hiệu ứng.
- **Scaffold của `omp` có lịch sử rò** (MC-22): `APPEND_SYSTEM.md` của máy. Các ô ở đây là scaffold **sạch** (HOME override) hoặc arm A; đừng trộn arm H2/H3 (có rò) vào đây.
