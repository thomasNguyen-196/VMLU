# VMLU benchmark

Ngôn ngữ chung cho bảng đối chiếu năng lực tiếng Việt đang được thiết kế trong dự án VMLU.

## Language

**Nhóm bài/lĩnh vực**:
Trục năng lực được đo trong bảng chính, như kiến thức, đọc hiểu, suy luận hoặc pháp luật.
_Avoid_: Ngữ cảnh nếu chưa nói rõ đó là lĩnh vực câu hỏi hay điều kiện đầu vào.

**Bảng so sánh model**:
Một ma trận có các model theo hàng và các nhóm bài cùng thước đo đã công bố theo cột.
_Avoid_: Bảng vuông theo nghĩa số hàng bắt buộc bằng số cột.

**Pilot benchmark**:
Đợt đo nhỏ trước thí nghiệm chính, dùng để xác định tính khả thi, chất lượng chấm và ngân sách cần thiết.
_Avoid_: Kết quả benchmark chính, bảng xếp hạng cuối cùng.

**Gold đã hiệu đính**:
Bộ đáp án tham chiếu được người chấm kiểm tra và sửa khi cần. Trong đợt benchmark này, bộ đọc 400 câu đã được người dùng chấm đủ và tiếp tục được dùng làm tham chiếu.
_Avoid_: Gold còn thiếu, gold chưa được chấm.

**OMP một lượt, không tools**:
Điều kiện đo trong đó mỗi item chạy qua một tiến trình omp riêng, giữ nguyên user prompt, tắt tools/session/skills/rules và dùng cùng system prompt tối giản.
_Avoid_: Gọi đây là API thuần; system prompt và client wrapper thuộc condition đo.

**EM tiếng Việt giữ dấu**:
Tỷ lệ câu trả lời cuối khớp đáp án tham chiếu sau các chuẩn hóa được công bố, trong đó dấu tiếng Việt được giữ nguyên.
_Avoid_: EM chung khi trộn với phiên bản EM bỏ dấu lịch sử.

**Token-F1 tiếng Việt**:
Mức khớp giữa các token theo khoảng trắng của câu trả lời cuối và đáp án tham chiếu, giữ dấu tiếng Việt.
_Avoid_: Char-F1, word-F1 dựa trên tách từ.

**Ngân sách suy luận**:
Giới hạn tài nguyên dành cho một câu trả lời trong nhóm bài, bao gồm phần reasoning theo khả năng cung cấp của provider. Đợt benchmark này cho phép reasoning và chốt ngân sách từ pilot.
_Avoid_: Coi cùng nhãn reasoning effort là cùng lượng tính toán ở mọi model.
