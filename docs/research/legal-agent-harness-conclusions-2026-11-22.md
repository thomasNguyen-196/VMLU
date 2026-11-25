# Tổng hợp kết luận từ các card agent luật (MC-112 đến MC-117)

Ngày 2026-11-22. Tài liệu này gom các kết luận rút ra từ các lượt thử harness: dsh 0.2.2-rc.1 và omp 18.0.0, với hai model là Qwen3.5-9B-65K (IEC) và MiMo-V2.6-Flash (OpenCode Go).

**Phạm vi.** Cùng 646 câu: 246 câu trắc nghiệm luật (Legal MC và luật VMLU) và 400 câu ViBidLQA hỏi không kèm đoạn văn. Mỗi lượt tra một thư mục văn bản luật cục bộ, không có web.

**Ba mức độ chắc chắn:**
- **A, đã đăng ký trước:** phép kiểm định được khóa trước khi có dữ liệu, có hiệu chỉnh Holm.
- **B, thăm dò:** viết sau khi đã thấy dữ liệu, chỉ mô tả, không có phép kiểm định.
- **C, hệ quả cho phương pháp đo.**

Mỗi con số đều dẫn về file nguồn ở cuối tài liệu.

## A. Kết luận đã đăng ký trước

| # | Kết luận | Số liệu | Nguồn |
|---|---|---|---|
| A1 | **Agent chỉ có ích khi bị ép tra cứu.** Nếu để model tự quyết, nó hầu như không tra (Qwen tra ở 1,8–17% số lượt). | DSHF − DSH: +8,1 điểm trắc nghiệm (Holm p 0,0014), +18,4 F1 ViBidLQA (Holm p 0,0002) | MC-114 |
| A2 | **Ở trắc nghiệm, agent tốt nhất chưa hơn hỏi thẳng.** | DSHF − B: Qwen +3,5 [−0,3; 7,5], bốn lượt, Holm p 0,091; MiMo +4,1 [−0,4; 8,7], Holm p 0,109 | MC-115, MC-116 |
| A3 | **Ở ViBidLQA, agent hơn hỏi không kèm đoạn văn rất xa,** nhưng còn xa mức có sẵn đoạn văn đúng (O 67,1 với Qwen). | DSHF − C: Qwen +17,4, MiMo +26,5 (Holm p 0,0002) | MC-114, MC-115, MC-116 |
| A4 | **Với Qwen, omp kém dsh,** và kết quả này vững qua bốn lượt. | OMPF − DSHF: −7,42 [−10,9; −3,8] điểm (Holm p 0,0003); −2,62 [−4,7; −0,4] F1 (Holm p 0,023) | MC-115 |
| A5 | **Với MiMo, omp hơn dsh.** Harness nào tốt hơn phụ thuộc vào model. | OMPF − DSHF: +5,69 [3,0; 8,5] (Holm p 0,0002); +7,36 [4,9; 9,7] F1 (Holm p 0,0001). Tương tác (báo bên cạnh, không kiểm định): +14,63 và +11,64 | MC-116 |
| A6 | **System prompt mặc định của omp mang một phần tương tác.** Thay riêng prompt này bằng prompt của dsh kéo hai model theo hai chiều ngược nhau. | P3: −7,11 [−12,4; −1,6] trắc nghiệm (Holm p 0,035); −14,74 [−18,5; −11,1] ViBidLQA (Holm p 0,0002). Tương tác còn lại: ViBidLQA −3,10 [−7,1; 0,9], không khác 0; trắc nghiệm +7,52 [1,8; 13,4], tức khoảng 49% đã được giải thích | MC-117 |

## B. Cơ chế (thăm dò, viết sau khi đã thấy dữ liệu)

| # | Kết luận | Số liệu | Nguồn |
|---|---|---|---|
| B1 | **Harness khác nhau ở hành động quanh lần gọi model, không ở chính lần gọi đó.** Có ba khác biệt: ai chọn khoảng đọc, harness trả lại bao nhiêu, và harness tự làm gì. | omp tự cắt trang và bỏ phần giữa file khi model không chỉ định khoảng đọc; trang đọc của omp dài gấp 2,5–3,5 lần dsh; chỉ omp tự nén ngữ cảnh, và câu trả lời sau khi bị nén chỉ đạt 33–73 điểm trắc nghiệm | Luồng 4 ô và 6 ô |
| B2 | **Qwen làm theo chỉ dẫn từng chữ, MiMo tự quyết cách đọc.** | Qwen trong OMPF: 32–42% số lần đọc là trang do harness cắt, và 51% số lượt trắc nghiệm trả lời ngay sau grep. Với prompt dsh (OMPS): tự chọn khoảng đọc 82%, số lần đọc 1,09 lên 2,30, đọc tới điều luật 21% lên 42%. MiMo tự chọn khoảng đọc 94–100% ở mọi nhánh | Luồng 6 ô; thăm dò sau MC-117 |
| B3 | **Đọc kỹ hơn thì tốn hơn, và bị nén ngữ cảnh nhiều hơn.** | Token mỗi lượt của Qwen trong OMPS gấp 1,37 lần OMPF (1,76 lần ở những câu chạy đầu; phải nâng trần token bằng amendment 1). Lượt bị nén: 4,9% lên 11,8%; điểm sau khi bị nén 32,7 | MC-117; luồng 6 ô |
| B4 | **Chỉ prompt omp có chỉ dẫn định dạng câu trả lời.** Cả hai prompt đều nhắc offset/limit: dsh dặn đọc tiếp file lớn; omp dặn đọc hẹp, trong một dòng giữa khoảng 150 dòng quy ước lập trình. | Câu định dạng của omp: *"Format MUST match ask; prose brief"*, *"Evidence-first terse engineer"*. Tỉ lệ câu trả lời trắc nghiệm chỉ gồm một chữ cái (OMPF / DSHF / OMPS): Qwen 65,7 / 42,1 / 42,3%; MiMo 88,8 / 75,0 / 78,0% | `system-prompts-2026-11-21/`; thăm dò sau MC-117 |
| B5 | **Phần lớn tương tác trên trắc nghiệm đến từ bộ chấm.** Chấm theo đúng yêu cầu "chỉ đưa ra chữ cái" thì omp hơn dsh với cả hai model. Bộ trích V1 dễ dãi: nó đọc đúng kiểu viết của Qwen (chữ cái trước) nhưng bắt nhầm kiểu viết của MiMo (chữ cái ở cuối). | Chấm chặt, OMPF − DSHF: Qwen +12,6 [6,7; 18,3], MiMo +10,4 [6,1; 14,4]; tương tác −2,2 [−9,8; 5,1], so với +14,6 theo bộ trích. Accuracy của câu trả lời dài ở DSHF: Qwen 76,5%; MiMo 48,0% (98,1% khi trả một chữ cái) | Thăm dò sau MC-117 |
| B6 | **Ở ViBidLQA, lợi thế của omp với MiMo chủ yếu là sự ngắn gọn.** | Recall của MiMo: 86–89 ở cả ba nhánh. Precision OMPS − OMPF: −11,0. Theo recall: tương tác gốc 5,9 [2,0; 10,1], còn lại 0,0 [−4,2; 4,5]; MiMo OMPS − OMPF +2,4 | Thăm dò sau MC-117 |
| B7 | **Ở trắc nghiệm, tương tác nằm ở bước trả lời, không ở việc có đọc tới điều luật hay không.** | Phần trong cùng trạng thái đọc chiếm 93,5% (trắc nghiệm) và 58% (ViBidLQA). Khi cả hai harness đều đã đọc điều luật: Qwen −16,2, MiMo +6,3 | Phân tích theo bước (kế hoạch băm trước, `641ef1aa…`) |
| B8 | **Phát hiện riêng của tiếng Việt: dữ liệu ViBidLQA gốc không ở dạng NFC.** Qwen chép nguyên byte vào mẫu grep nên tìm không ra; MiMo tự viết lại ở dạng NFC. Lỗi này hạ điểm của Qwen ở cả hai harness, không phải nguồn của tương tác. | Khoảng 22% ký tự là dấu tách rời; 82% số mẫu grep lỗi của Qwen chứa từ tách dấu lấy từ câu hỏi | Phân tích theo bước |

## C. Hệ quả cho phương pháp đo

1. **"Harness nào tốt hơn" không có câu trả lời chung.** Đáp án phụ thuộc vào model (A4, A5) và vào thước đo (B5). Một kết quả agent phải ghi rõ harness, phiên bản, system prompt và bộ chấm. Kết luận rút ra trên một model không chuyển được sang model khác.
2. **Bộ chấm là một phần của phép đo agent.** System prompt quyết định model có giữ đúng định dạng mà đề yêu cầu hay không, và bộ chấm phản ứng với điều đó. Card sau nên đăng ký trước:
   - ba chỉ số cho trắc nghiệm: tỉ lệ trả đúng một chữ cái, accuracy chấm chặt, accuracy theo bộ trích V1;
   - recall cạnh F1 cho câu trả lời ngắn.

   Lần đổi bộ chấm ViBidLQA từ v2 sang v3 đã có tiền lệ như vậy.
3. **Cần quan sát luồng hành động, không chỉ nhìn điểm.** Log luồng (sự kiện của harness ghép với log proxy) đã cho thấy cơ chế mà điểm số không lộ ra: ai chọn khoảng đọc, nén ngữ cảnh, tuân thủ định dạng.

## Những điều chưa kết luận được

- **Câu nào trong prompt omp có tác dụng.** Có thể là các câu về định dạng, có thể là câu về đọc file. Cần một card thay từng phần của prompt.
- **Đặc tính nào của model quyết định.** MiMo vừa có suy nghĩ ẩn ở mức mặc định không đổi được, vừa chạy route khác, vừa có giới hạn đầu ra khác Qwen. Phía IEC lại không bật được chế độ suy nghĩ cho Qwen (thử ngày 2026-11-20).
- **Độ dao động của MiMo giữa các lần chạy.** OMPF của MiMo mới đo một vòng, nên P2 có thể lẫn cả độ dao động này. Với Qwen, OMPF dao động dưới 0,5 điểm giữa hai vòng.
- **Mức khái quát.** Mới có hai model và một miền (luật).
- **Tính chất hậu kiểm của B5 và B6.** Các cách chấm thay thế được chọn sau khi thấy dữ liệu. Chúng là mô tả mạnh, nhưng cần một card đăng ký trước mới thành kết luận chính thức.

## Tóm một câu

Với model nhỏ, harness ảnh hưởng tới điểm qua hai kênh mà model khó tự chủ:
- **cách đọc tài liệu:** harness hay model chọn khoảng đọc;
- **việc giữ đúng định dạng câu trả lời.**

Kênh thứ hai bị bộ chấm khuếch đại, nên một phần lớn "tương tác model × harness" là chuyện đo lường, không phải năng lực luật.

## Bước tiếp theo đề xuất (chưa đăng ký)

- **Một card thay từng phần prompt:** prompt dsh cộng thêm câu định dạng của omp (*"Format MUST match ask; prose brief"*), cho cả hai model.
- **Chấm bằng ba chỉ số trắc nghiệm ở mục C2, đăng ký trước.**
- **Kỳ vọng:** cả hai model lấy lại mức tuân thủ định dạng, còn Qwen giữ được phần lợi về đọc. Nếu đúng vậy, cơ chế hai kênh được xác nhận; nếu không, nó bị bác bỏ.

## Nguồn

| Nội dung | File | SHA-256 |
|---|---|---|
| MC-114 (A1, A3) | `docs/measurement_cards/MC-114-diagnostic-legal-agent-v2.md`; báo cáo `all_res/diagnostic_legal_agent_v2/run/…/analysis/legal_agent_v2_report.json` | `6c063d47…` |
| MC-115 (A2–A4) | `docs/measurement_cards/MC-115-diagnostic-legal-agent-draws.md`; `…/legal_agent_draws_report.json` | `45ed6b6c…` |
| MC-116 (A2, A3, A5) | `docs/measurement_cards/MC-116-diagnostic-legal-agent-mimo.md`; `…/legal_agent_mimo_report.json` | `b6f8a7cb…` |
| MC-117 (A6, B3) | `docs/measurement_cards/MC-117-diagnostic-legal-agent-omp-prompt.md` (gồm amendment 1 và run record); `all_res/diagnostic_legal_agent_omp_prompt/analysis/legal_agent_omp_prompt_report.json` | `bfd544bd…` |
| Phân tích theo bước (B7, B8) | `docs/research/legal-agent-interaction-2026-11-20.md`; `all_res/diagnostic_legal_agent_mimo/interaction/interaction_report.json` | `b5f33252…` |
| Luồng hành động 4 ô (B1, B2) | `docs/research/legal-agent-flows-2026-11-20.md`; `all_res/diagnostic_legal_agent_mimo/flows/flow_report.json` | `0344d454…` |
| Luồng hành động 6 ô (B1–B3) | `docs/research/legal-agent-flows-mc117-2026-11-21.md`; `all_res/diagnostic_legal_agent_omp_prompt/flows/flow_report.json` | `56788384…` |
| Thăm dò sau MC-117 (B2, B4–B6) | `docs/research/legal-agent-omp-prompt-followup-2026-11-21.md`; `all_res/diagnostic_legal_agent_omp_prompt/explore/omp_prompt_followup.json` | `5e9c7111…` |
| Nguyên văn system prompt (B4) | `docs/research/system-prompts-2026-11-21/` (sáu file kèm README so sánh) | khớp pin đã đăng ký |
