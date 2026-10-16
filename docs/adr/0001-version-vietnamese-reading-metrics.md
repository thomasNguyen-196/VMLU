---
status: accepted
date: 2026-10-06
---

# Đặt phiên bản riêng cho EM giữ dấu và token-F1

Scorer lịch sử dùng EM có bỏ dấu/alias số và char-F1, nên các điểm có thể che khác biệt dấu tiếng Việt hoặc không phân biệt đúng số, đơn vị và kiểu diễn đạt. Người dùng đã chọn EM giữ dấu cùng token-F1 cho bảng nghiên cứu mới, đồng thời giữ scorer cũ để đối chiếu; lựa chọn này tăng khả năng diễn giải nhưng tạo một điều kiện chấm khác cần ghi phiên bản.

Giữ nguyên bộ đọc 400 câu mà người dùng đã chấm, các prompt/parser/scorer đóng băng và điểm lịch sử. Scorer mới chấm đáp án cuối, giữ dấu và công bố tokenization theo khoảng trắng; kết quả scorer cũ trên cùng đáp án cuối mang nhãn riêng để không bị nhầm với điểm nguyên văn lịch sử. Mỗi run và ô bảng phải ghi phiên bản protocol, gold, scorer và cách trích đáp án.
