# Giải thích Issue #3: VMLU baseline + proposal đọc hiểu

> Ghi chú cá nhân, ghi lại tường thuật đã trao đổi với agent.
> Nguồn: issue #3 trên GitHub, `PROPOSAL.md`, code FE đã merge.

## Bức tranh lớn trước

Nhớ lại đề tài đang làm (theo `PROPOSAL.md`): đánh giá các model nhỏ ≤8B trên tiếng Việt, vừa đo năng lực vừa đo chi phí. Trong đó cần đo được kỹ năng **đọc hiểu**. Issue #3 sinh ra từ đúng chỗ này — nó làm 2 việc trong một: **báo cáo kết quả vừa xong** (phần 1) và **xin duyệt một kế hoạch làm tiếp** (phần 2).

## Phần 1: Báo cáo — "harness chấm điểm đã xong, đây là con số đầu tiên"

Trước đây, chạy benchmark xong chỉ ra file dự đoán, phải chấm tay. Phần này báo: `test_ollama.py` giờ **tự chấm** khi bộ dữ liệu có đáp án sẵn (`valid.jsonl`, `dev.jsonl` có cột `answer`): tự thêm cột `gold_answer`/`correct`, xuất bảng accuracy theo tổng thể / 4 nhóm môn / 58 môn. Input không có đáp án (`test.jsonl` — dùng cho leaderboard) thì giữ nguyên hành vi cũ, không phá flow cũ.

Sau đó chạy **baseline** — tức chạy 1 model (Qwen3-8B 27B-class GGUF) làm con số gốc để các model sau so sánh. Kết quả trên 744 câu:

| Nhóm | Accuracy |
|---|---|
| **Overall** | **72.58%** |
| STEM | 78.68% |
| Social Science | 75.57% |
| Humanity | 68.56% |
| Other (nghề nghiệp) | 62.50% |

Hai phát hiện được nêu ra "dùng được cho bài":
- **Gradient STEM → Other** khớp nhận định của paper VMLU gốc: kiến thức nghề nghiệp bản địa Việt Nam là điểm mù của pretrain (model học từ web quốc tế, ít gặp "cách làm mắm", "nghề thủ công địa phương"...).
- **Position bias**: model chọn D (234 lần) nhiều hơn hẳn A (139 lần) — tức là có phần trả lời theo *vị trí đáp án* chứ không thuần túy theo nội dung. Đây là kiểu bias thường phải ghi nhận trong báo cáo.

Chi tiết nhỏ: "chi phí thực sự nằm ở regime C" — theo `PROPOSAL.md`, regime C là chế độ đo **reasoning budget** (model thinking như Qwen3, bật chế độ suy luận sinh hàng trăm/nghìn token). Chạy trắc nghiệm này rẻ vì output chỉ ~1 token; đắt là đắt ở regime C.

Cuối phần là "còn nợ": `dev.jsonl` 303 câu chưa chạy (chạy 30-60s là xong, để đủ 1.047 câu có đáp án nội bộ), còn `test.jsonl` 9.833 câu chờ harness ổn định rồi submit 1 lượt.

## Phần 2: Đề xuất — "muốn đo đọc hiểu thì phải tự làm bộ đáp án"

Đây mới là phần "truyền tải" chính. Logic nó như sau:

**Vì sao cần:** benchmark Vi-MQA là trắc nghiệm *closed-book* — khoảng 98,6% câu **không có đoạn văn cho trước**, model trả lời bằng kiến thức nhớ được, không phải đọc gì cả. Nên Vi-MQA **không đo được kỹ năng đọc hiểu**. Muốn đo thì phải dùng dataset đọc hiểu thật (Vi-SQuAD, Vi-DROP: cho model đọc một đoạn văn rồi trả lời câu hỏi tự do). Vi-MQA chỉ giữ vai trò **negative control** — nghĩa là: một phép đo mà ta *kỳ vọng không đổi* sau khi áp dụng cải thiện, dùng để đối chiếu.

**Blocker:** cả 2 dataset public chỉ phát hành câu hỏi + đoạn văn, **không có đáp án mẫu** (đã kiểm tra schema trên đĩa và cả mirror trên HuggingFace). Không có đáp án → không chấm được.

**Giải pháp: tự annotate 400 đáp án.** Kế hoạch 6 bước, mỗi bước đều có lý do:

1. **Lấy mẫu phân tầng** (stratified sampling — chia dữ liệu thành các nhóm theo đặc tính rồi lấy đều từ từng nhóm, thay vì lấy 200 câu đầu): SQuAD phân theo độ dài đoạn × loại câu hỏi; DROP phân theo dạng suy luận, và *tăngSampling* câu "count" (đếm số lượng) lên ~20% vì đó là điểm mù nêu trong paper. Chọn **seed 42 và commit manifest** vào repo — đây là "chứng cứ" cho thấy bộ câu được chọn trước khi biết kết quả, chống nghi vấn chọn câu dễ.
2. **Tự annotate** 400 đáp án: 2 người làm, chéo kiểm 20%, đo **IAA** (inter-annotator agreement — mức hai người cùng chấm một câu có ra cùng đáp án không). Đây là phần **tốn công người nhất: ~2-3 ngày**.
3. **Chốt metric trước khi chạy**: EM (exact match — khớp chính xác sau chuẩn hoá) + **char-level F1** (so khớp một phần theo ký tự). Chọn so theo ký tự thay vì theo từ là để né bẫy tiếng Việt: tách từ tiếng Việt không ổn định, so theo từ sẽ ra con số không so sánh được với SQuAD tiếng Anh.
4. **Dev vòng nhanh trên MLQA-vi/XQuAD-vi** — hai bộ này có sẵn đáp án trên HF, cùng dạng → test hết script chấm *trước khi* bỏ 2-3 ngày annotate, giảm rủi ro làm xong mới phát hiện script lỗi.
5. **Thiết kế thí nghiệm = DiD** (difference-in-differences — sai khác của sai khác): sau khi áp "cải thiện đọc hiểu", đo model trên cả 2 bộ. Bộ đọc hiểu (treatment) kỳ vọng **tăng**; Vi-MQA (control) kỳ vọng **không đổi**. Nếu Vi-MQA cũng tăng → mức tăng đó là side-effect của prompt/temperature, **phải trừ đi** — nó không phải do cải thiện đọc hiểu. Đây là cách loại trừ "tăng giả".
6. **Báo cáo**: ≥2-3 model, mỗi con số kèm bootstrap 95% CI (khoảng tin cậy — cho biết con số dao động trong khoảng nào khi lấy mẫu lại), config inference đóng băng giữa 2 lần đo.

**Non-goals** cũng đáng chú ý: không dùng Vi-Dialog vì chấm bằng LLM judge — biến động của judge sẽ che mất biến động của model size nhỏ; không xin gold chính thức của VMLU — phòng chống contamination (model có thể đã học mặt đề trong pretrain, chấm bằng gold đó sẽ inflate kết quả).

**Risk**: annotate là critical path (mọi thứ khác đợi nó) → phải bắt đầu song song từ đầu; nếu IAA < 0.8 thì làm lại guideline, hoặc bỏ DROP chỉ giữ SQuAD (đáp án dạng "trích đoạn trong văn bản" dễ đồng thuận hơn DROP dạng suy luận).

## Tóm lại issue này muốn gì

Nó muốn người đọc hiểu: **"pipeline chấm điểm đã xong và đã có baseline 72,58%; để đo đọc hiểu, tôi đề xuất tự xây bộ 400 câu có đáp án theo 6 bước này — vui lòng duyệt kế hoạch, đặc biệt phần cần người annotate (labels: `enhancement` + `ready-for-human`)"**. Và theo 2 PR liên quan, phần tooling (sampler, runner chấm đọc hiểu, workbook annotate, UI review, exporter merge) đã được làm xong và merge vào `main` (PR #5) — phần còn lại đúng như label là **công việc của người**: ngồi annotate 400 gold.
