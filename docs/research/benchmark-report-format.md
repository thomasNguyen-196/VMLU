# Format báo cáo benchmark · reporting schema v1

Mỗi nhóm run trình bày theo thứ tự **Condition → Benchmark → Comment → Note**.
Nguồn điều kiện là `run.json` khi có, rồi measurement card của đúng run; không kế thừa
metadata chung của một snapshot chứa nhiều model. Đây là projection của artifact đã có,
không thay prompt, gold, parser hoặc phép chấm lịch sử.

Condition ghi model/card/ngày, harness + version + mode, API/route, temperature gửi và
hiệu lực theo policy, thinking và effort, seed gửi, tools, prompt, context/history,
output cap, workers/batch, timeout, retry, gold/scorer, quantization và nguồn bằng chứng.
Thông tin không xác minh được phải ghi “chưa ghi nhận”; no-CoT không có nghĩa native
thinking đã bị tắt. Level `auto` không được đổi thành low/medium/high.

Benchmark giữ riêng Accuracy, Server accuracy, Server macro, EM, Token-F1, Char-F1, Agreement và
Schema validity. Pilot synthetic giữ label Function + arguments exact theo phép chấm gốc.
CI lower/upper có cột riêng; CI cho delta không nằm ở cột CI của score.
Server grade với withheld gold không được dùng để suy correct count hoặc CI từ phần trăm
đã làm tròn. Subject/category không có mẫu số thì để trống.

Comment lấy số từ đúng dataset/category, metric và nhóm điều kiện. Ranking chỉ có khi
manifest, prompt, harness, tools, thinking, temperature hiệu lực, seed policy, output
budget, workers/session/retry tương đương theo metadata. API/provider vẫn được nêu rõ;
điều kiện danh nghĩa không chứng minh reasoning bên trong tương đương. Ablation arm A/B
chỉ diễn giải trong cùng model và cùng mẫu; điều kiện thay nhiều yếu tố không tự tạo
claim nhân quả của riêng harness hay tools.

Note ghi giới hạn của lexical metrics, bias gold reviewed, truncation/budget, config
leaks, pilot/repeat, missing provenance, so sánh khác điều kiện và server-score source.
MC kết hợp hiểu câu hỏi với kiến thức và reasoning; EM/F1 phản ánh khớp gold, chưa phải
human semantic correctness hay chất lượng hội thoại.

Sinh báo cáo từ root:

```bash
.venv/bin/python code_benchmark/build_benchmark_reports.py
```

Outputs: `web/data/benchmark-reports.json`, `docs/research/benchmark-condition-reports.md`,
`docs/research/benchmark-condition-reports.csv`, và bản CSV download ở `web/public/`.
Frontend hiện tại: `/table` là model × dataset, có bảng Accuracy, EM, Token-F1 và
CI95 riêng cho từng metric; mỗi bảng có nhận xét ngắn dựa trên điểm nổi bật.
Panel trái tách condition. Phạm vi hiện tại là OMP 18/no tools/temp 1/auto/no seed;
VMLU dùng cohort V2, reading/Legal dùng ba Go model V1 có cùng cấu hình. Qwen V1
temp 0/thinking off không được dùng để điền các ô Qwen chưa chạy trong condition này.
API trực tiếp chỉ hiển thị khi có ít nhất hai model cùng các control đã xác minh và
cùng mẫu/output budget; thinking chưa rõ hoặc cap khác nhau phải bỏ qua.

`/table/v2` chuyển về `/table`; báo cáo lịch sử đầy đủ vẫn được lưu trong artifact
và `/table/history`, không thuộc panel so sánh hiện tại. Các điểm cũ không bị sửa.
