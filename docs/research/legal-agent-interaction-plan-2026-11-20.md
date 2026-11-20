# Tương tác model × harness ở legal agent: kế hoạch phân tích (viết trước khi xem số liệu theo bước của MiMo)

Ngày 2026-11-20. Đây là **phân tích khám phá**, không đăng ký trước như một measurement card. Kế hoạch này được viết và băm SHA-256 trước khi chạy phân tích theo bước trên dữ liệu MC-116, để không chọn cách đo sau khi đã thấy kết quả. Phân tích không gửi request nào và không thay đổi kết luận đã đăng ký của MC-112 đến MC-116.

## Câu hỏi

Với cùng thư mục văn bản luật, cùng 646 câu và cùng task, omp kém dsh khi model là Qwen3.5-9B: −8,94 điểm trắc nghiệm và −4,28 token-F1 ViBidLQA (lượt 1–2). Nhưng omp lại tốt hơn dsh khi model là MiMo-V2.6-Flash: +5,69 và +7,36 (MC-116). **Tương tác này sinh ra ở bước nào của vòng agent?**

## Đã biết trước khi viết kế hoạch

- Điểm tổng của bốn ô và mức tương tác. Báo cáo đăng ký của MC-116 (`b6f8a7cb…`) cho +14,63 ở trắc nghiệm và +11,64 ở ViBidLQA.
- Kết quả khám phá: DSHF của MiMo có 27 lượt `answer_cap` ở phần trắc nghiệm, còn OMPF không có lượt nào. Bỏ các lượt dừng không có đáp án đi thì khoảng cách OMPF − DSHF của MiMo là +2,75 ở trắc nghiệm và +7,48 ở ViBidLQA.
- Dò lỗi tiếng Việt khi grep (`all_res/diagnostic_legal_agent_mimo/analysis_vi/`). Qwen viết pattern bị tách dấu (NFD) hoặc chồng dấu hỏng ở 4,4% số lệnh grep; MiMo không có lệnh nào như vậy.
- **Chưa xem:** phân bố theo bước (tìm, mở, đọc tới điều luật) và phần tách của MiMo.

## Dữ liệu

| Ô | Nguồn | Lượt |
|---|---|---|
| Qwen DSHF, Qwen OMPF | MC-112 và MC-113 (134 câu Legal MC), MC-114 (112 câu luật VMLU, 400 câu ViBidLQA) | 1–2 |
| MiMo DSHF, MiMo OMPF | MC-116 (cùng 646 câu, cùng thư mục) | 1–2 |

- Mỗi file điểm đều được đọc kèm kiểm tra SHA-256 đã ghi.
- **Mốc độ khó của câu** được tính theo từng model: B của chính model đó ở trắc nghiệm (với Qwen ở Legal MC là B của MC-111), và C ở ViBidLQA.
- **Điều luật chi phối** dùng đúng tệp của MC-112 và MC-114 (`provisions`). Câu nào không xác định được điều luật thì không vào phần chia bước.
- **Nhóm phân tích:**
  - trắc nghiệm, tách riêng Legal MC và luật VMLU;
  - ViBidLQA.

## Cách đo

1. **Điểm từng ô và mức tương tác.** Với mỗi câu, lấy trung bình hai lượt. Mức tương tác của câu = (OMPF − DSHF của MiMo) − (OMPF − DSHF của Qwen). Báo cáo trung bình và khoảng 95% bootstrap theo câu (2.000 lần, seed 7). Trên toàn bộ câu, con số này phải khớp báo cáo đăng ký (+14,63 và +11,64). Nếu không khớp thì phân tích dừng.
2. **Các bước** lấy đúng định nghĩa của module MC-114 (`analyze_legal_agent_mechanism`):
   - `no_tool`: không gọi công cụ nào;
   - `not_found`: không tìm thấy tệp điều luật;
   - `found_not_opened`: thấy tên tệp nhưng không mở;
   - `opened_not_read`: mở tệp nhưng không thấy dòng mở đầu điều luật;
   - `read`: đã thấy dòng mở đầu điều luật.
3. **Tách mức tương tác.** Với mỗi model, khoảng cách OMPF − DSHF trên các câu có điều luật được tách làm hai phần (Oaxaca hai phần, theo phần thưởng đọc của DSHF):
   - **phần tỉ lệ đọc** = (tỉ lệ đọc của OMPF − của DSHF) × (điểm khi đọc − điểm khi không đọc, của DSHF);
   - **phần trong cùng trạng thái** = chênh điểm giữa hai harness khi cùng đã đọc hoặc cùng chưa đọc.

   Phần tách của mức tương tác là hiệu của từng phần giữa MiMo và Qwen. Khoảng tin cậy lấy bằng bootstrap theo câu: mỗi lần lấy mẫu dùng chung bộ câu cho cả hai model. Kèm theo một bản đo trên điểm trừ mốc độ khó (lift).
4. **Dừng không có đáp án** (`answer_cap`, `request_cap`, `harness_end`, `upstream_4xx`). Báo tỉ lệ từng ô, và tính lại mức tương tác khi bỏ các lượt này (trung bình các lượt còn lại của câu; câu nào thiếu một harness ở một model thì bỏ).
5. **Hành vi từng ô.** Gồm:
   - số lệnh, số lần đọc, số lần omp phân trang;
   - tỉ lệ grep ra rỗng, tỉ lệ pattern có Unicode lỗi;
   - token (gồm cả token suy nghĩ).
6. **Trả lời khi cả hai harness đều đọc.** Với mỗi model, trên các câu mà cả hai harness đều đọc tới điều luật ở ít nhất một lượt: chênh điểm OMPF − DSHF và phép thử dấu.

## Quy tắc đọc (cố định trước khi chạy)

Trong mỗi nhóm:
- **"Tương tác nằm ở việc đọc tới điều luật"**: phần tỉ lệ đọc của mức tương tác có khoảng tin cậy không chứa 0 và chiếm ít nhất 50% mức tương tác trên các câu có điều luật.
- **"Tương tác nằm ở bước trả lời"**: phần trong cùng trạng thái có khoảng tin cậy không chứa 0 và chiếm ít nhất 50%.
- **"Một phần do dừng không có đáp án"**: bỏ các lượt dừng làm mức tương tác giảm ít nhất 50%.
- Các nhận định trên có thể đúng cùng lúc, và cả ba đều được báo cáo. Nếu không nhận định nào đúng thì ghi "chưa xác định".

## Giới hạn đã biết

- **Không phải nhân quả.** Việc đọc tới điều luật không được ngẫu nhiên hóa, nên phần tách chỉ là liên hệ, không phải hiệu ứng.
- **Hai model khác nhau ở nhiều thứ:** thinking, độ mạnh, route, lượng tử hóa. Phân tích này chỉ trả lời "ở bước nào", không trả lời "vì đặc tính nào" (đó là việc của Pha 2 và Pha 3).
- **Chỉ hai lượt** mỗi ô, để hai model đối xứng. Lượt 3–4 của Qwen (MC-115) có thể dùng để kiểm tra độ vững, và sẽ ghi rõ là kiểm tra thêm.
