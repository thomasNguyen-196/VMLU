# Kế hoạch thực nghiệm: Full-scale Benchmark Qwen3-8-27B (Q4_K_M) & Data Safe Fallback

- **Mô hình**: `Qwen3-8-27B` (lượng tử hoá `Q4_K_M`)
- **Endpoint**: Ollama qua ngrok (`https://porridge-livable-umbrella.ngrok-free.dev/v1`)
- **Nhánh lưu trữ**: `data/full-eval-qwen3-8-27b` (tuyệt đối không mở PR, không merge vào `main`)
- **Mục tiêu**: Phủ 100% dữ liệu toàn bộ benchmark VMLU (kể cả phần không có gold) để làm bản sao lưu an toàn (data safe fallback), lưu vết kết quả và phân tích tính nhất quán đối chiếu 2 báo cáo PDF:
  1. `report_vmlu.pdf` (03/09/2026)
  2. `report_vbench.pdf` (04/09/2026)

---

## 1. Phạm vi dữ liệu thực thi

### A. VMLU-MQA (Trắc nghiệm 58 môn - 10.880 câu)
- `vmlu_datasets/vmlu_mqa_v1.5/valid.jsonl` (744 câu, có gold): Đo độ chính xác trực tiếp đối soát với mốc 72,58% trong báo cáo VMLU.
- `vmlu_datasets/vmlu_mqa_v1.5/dev.jsonl` (303 câu, có gold): Đo độ chính xác baseline.
- `vmlu_datasets/vmlu_mqa_v1.5/test.jsonl` (9.833 câu, un-gold): Chạy toàn diện sinh đáp án trắc nghiệm phục vụ submission và lưu trữ dữ liệu an toàn.

### B. VMLU Reading Comprehension (Đọc hiểu - 7.029 câu)
- **Tập tiền đăng ký 400 câu (`eval_set_manifest.csv`)**: 200 Vi-SQuAD + 200 Vi-DROP (chấm điểm EM và char-F1 đối soát với mốc 80,25% accept-rate và 86,55% char-F1).
- **Vi-SQuAD Full (3.310 câu)**: Sinh đáp án văn bản đầy đủ.
- **Vi-DROP Full (3.309 câu)**: Sinh đáp án suy luận/tính toán số học đầy đủ.
- **Vi-Dialog Full (210 đoạn hội thoại)**: Sinh phản hồi hội thoại đa lượt đầy đủ.

### C. V-Bench Public Test (Nếu có sẵn dữ liệu)
- 4.141 câu Multiple-Choice + 1.000 câu Agentic Function Calling (Minimal prompt condition).

---

## 2. Quy trình thực hiện & An toàn dữ liệu

1. **Tạo nhánh chuyên biệt**: `git checkout -b data/full-eval-qwen3-8-27b`
2. **Thực thi pipeline tuần tự**:
   - Chạy với checkpointing theo từng batch, lưu log chi tiết.
   - Thử lại 30×30s khi gặp ngắt kết nối mạng qua ngrok.
3. **Commit & Push**:
   - Lưu trữ toàn bộ kết quả thô, checkpoint, file submission CSV/JSONL vào nhánh `data/full-eval-qwen3-8-27b`.
   - Push lên remote GitHub `origin/data/full-eval-qwen3-8-27b`.
4. **Mở GitHub Issue**:
   - Thống kê toàn bộ số lượng câu hỏi và tỷ lệ hoàn thành 100%.
   - Lập bảng phân tích tính nhất quán (Consistency Check) đối soát chi tiết với số liệu từ 2 báo cáo `report_vmlu.pdf` và `report_vbench.pdf`.
