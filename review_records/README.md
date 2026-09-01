# review_records — sổ phân công review (giữa 2 người)

Mỗi file ở đây là **kết quả đã chốt của một người review × một model**, đúng
9-cột contract mà `export_annotation_workbooks.py review --a --b` tiêu thụ:

    review_<reviewer-slug>_<model-slug>.csv   (UTF-8 BOM, CRLF)

luồng làm việc (split 400 câu):

1. `npm run dev` → mở http://127.0.0.1:3000
2. Đầu phiên, app tự đọc mọi CSV ở đây: câu nào người kia đã chốt (accept/reject)
   sẽ bị **khóa chỉ-đọc** + gạch chéo trên filmstrip — bạn không thể làm trùng.
3. Review các câu còn trống.
4. Bấm **Export CSV** → app tải file về *và* công bố (ghi đè) file của bạn vào
   thư mục này.
5. `git add review_records && git commit && git push` → người kia pull là thấy
   ngay phần việc còn lại.

Quy tắc:

- **Đừng sửa tay** các file CSV này (hợp nhất qua UI, hỏng header là app bỏ qua).
- `d` (decision) để trống = câu chưa chốt (kể cả flag chỉ có ghi chú) → vẫn mở
  cho người khác làm. Chỉ accept/reject mới khóa.
- State làm việc riêng vẫn ở `review_state/` (gitignored) — thứ đưa vào git là
  CSV đã export, không bao giờ là bucket JSON.
- File từng người ghi đè lên chính nó khi export lại; hai người không bao giờ
  đụng file nhau vì tên đã gắn reviewer slug.
