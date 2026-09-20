import csv
import json
import os

items_data = [
    {
        "id": "41-0018",
        "domain": "legal",
        "track": "mc",
        "question": "Chia công ty là biện pháp tổ chức lại công ty, được áp dụng cho",
        "answer": "A",
        "raw_response": "Căn cứ Khoản 1 Điều 198 Luật Doanh nghiệp 2020 (và Điều 192 Luật Doanh nghiệp 2014) quy định về chia công ty: 'Công ty trách nhiệm hữu hạn, công ty cổ phần có thể chia các cổ đông, thành viên và tài sản công ty để thành lập hai hoặc nhiều công ty mới'. Do tính chất pháp lý đối vốn và cơ cấu phân chia tài sản, thành viên/cổ đông, pháp luật chỉ cho phép công ty TNHH và công ty cổ phần thực hiện biện pháp chia công ty; không áp dụng đối với công ty hợp danh hay doanh nghiệp tư nhân. Do đó, đáp án đúng là A."
    },
    {
        "id": "39-0008",
        "domain": "legal",
        "track": "mc",
        "question": "Hãy chỉ ra các nhận định sai?",
        "answer": "D",
        "raw_response": "Căn cứ Điều 26 và Điều 28 Bộ luật Dân sự 2015:\n- Khoản 2 Điều 26 quy định: 'Họ của cá nhân được xác định là họ của cha đẻ hoặc họ của mẹ đẻ theo thỏa thuận của cha mẹ; nếu không có thỏa thuận thì họ của con được xác định theo tập quán. Trường hợp chưa xác định được cha đẻ thì họ của con được xác định theo họ của mẹ đẻ'. Do đó nhận định 1 ('Con sinh ra mặc nhiên phải theo họ cha...') là SAI.\n- Khoản 1 Điều 28 quy định: 'Việc thay đổi tên cho người từ đủ chín tuổi trở lên phải có sự đồng ý của người đó'. Do đó nhận định 2 là ĐÚNG.\n- Khoản 1 Điều 26 quy định: 'Tên của công dân Việt Nam phải bằng tiếng Việt hoặc tiếng dân tộc khác của Việt Nam; không đặt tên bằng số, bằng một ký tự mà không phải là chữ'. Do đó nhận định 3 ('Có thể đặt tên con bằng số hoặc ký tự...') là SAI.\nNhư vậy, các nhận định sai là 1 & 3. Do đó, đáp án đúng là D."
    },
    {
        "id": "39-0009",
        "domain": "legal",
        "track": "mc",
        "question": "Nhận định nào sau đây là đúng?",
        "answer": "A",
        "raw_response": "Căn cứ Điều 19 Hiến pháp 2013, Điều 24 Bộ luật Dân sự 2015 và các Điều 39, Điều 40 Luật Nhập cảnh, xuất cảnh, quá cảnh, cư trú của người nước ngoài tại Việt Nam năm 2014 (sửa đổi, bổ sung năm 2019, 2023): Người không quốc tịch cư trú tại Việt Nam được Nhà nước bảo đảm quyền cư trú hợp pháp theo quy định của pháp luật (được xem xét cấp thẻ tạm trú hoặc thẻ thường trú nếu đáp ứng đủ điều kiện luật định). Nhận định B sai vì công dân Việt Nam là người có quốc tịch Việt Nam theo Luật Quốc tịch, nhưng trên lãnh thổ Việt Nam còn có người nước ngoài và người không quốc tịch cư trú. Nhận định C sai vì việc xác định, thay đổi, nhập, thôi, trở lại quốc tịch Việt Nam là quyền chủ quyền quốc gia được điều chỉnh bởi Luật Quốc tịch Việt Nam và điều ước quốc tế mà Việt Nam là thành viên chứ không phải do 'Luật quốc tế' quy định. Do đó, đáp án đúng là A."
    },
    {
        "id": "39-0011",
        "domain": "legal",
        "track": "mc",
        "question": "Nhận định nào sau đây là sai?",
        "answer": "C",
        "raw_response": "Căn cứ Điều 20 Hiến pháp 2013 và Điều 34 Bộ luật Dân sự 2015 về quyền được bảo vệ danh dự, nhân phẩm, uy tín:\n- Danh dự, nhân phẩm, uy tín của cá nhân là bất khả xâm phạm và được pháp luật bảo vệ. Mọi hành vi xúc phạm danh dự, nhân phẩm đều bị nghiêm cấm, không có ngoại lệ nào cho phép xâm phạm danh dự người khác kể cả trong tình huống khẩn cấp ngăn chặn tội phạm. Do đó, nhận định 1 là SAI.\n- Quyền bất khả xâm phạm về danh dự, nhân phẩm là quyền con người thiêng liêng thuộc về mọi cá nhân (kể cả người nước ngoài, người không quốc tịch đang sinh sống, cư trú tại Việt Nam), không phải chỉ bảo vệ khi 'còn là công dân'. Do đó, nhận định 2 là SAI.\nVì cả hai nhận định 1 và 2 đều sai nên phương án chính xác là C (Cả 1 & 2). Do đó, đáp án đúng là C."
    },
    {
        "id": "39-0012",
        "domain": "legal",
        "track": "mc",
        "question": "Nhận định nào sau đây là đúng nhất?",
        "answer": "D",
        "raw_response": "Căn cứ Khoản 1 Điều 40 Bộ luật Dân sự 2015 quy định về nơi cư trú của cá nhân: '1. Nơi cư trú của cá nhân là nơi người đó thường xuyên sinh sống'. Khoản 2 Điều 40 quy định trường hợp không xác định được nơi thường xuyên sinh sống thì mới lấy nơi người đó đang sinh sống. Do đó, định nghĩa chuẩn mực và đầy đủ nhất theo nguyên tắc chung của luật dân sự là nhận định B ('Nơi cư trú của cá nhân là nơi người đó thường xuyên sinh sống'). Trong cấu trúc phương án lựa chọn được thiết kế, phương án đúng nhất là D (chọn B). Do đó, đáp án đúng là D."
    },
    {
        "id": "39-0013",
        "domain": "legal",
        "track": "mc",
        "question": "Tìm nhận định sai trong các nhận định dưới đây?",
        "answer": "D",
        "raw_response": "Căn cứ các quy định tại Chương III (Điều 46 đến Điều 59) Bộ luật Dân sự 2015 về Giám hộ:\n- Nhận định A sai vì theo Khoản 1 Điều 46 và Điều 47 BLDS 2015, một người có thể có nhiều người giám hộ (như cha mẹ cùng là người giám hộ đương nhiên cho con chưa thành niên, hoặc cử/chỉ định nhiều người giám hộ).\n- Nhận định C sai vì theo Điều 52 BLDS 2015, anh cả hoặc chị cả chỉ là người giám hộ đương nhiên nếu đáp ứng đủ các điều kiện làm người giám hộ quy định tại Điều 49 BLDS 2015 và các bên không có thỏa thuận cử người khác giám hộ; việc khẳng định 'Trong mọi trường hợp' là sai.\n- Nhận định B được xem là nhận định thiếu/chưa hoàn chỉnh trong câu hỏi trắc nghiệm kinh điển của Đại học Luật Hà Nội so với toàn bộ phạm vi người được giám hộ theo luật định tại Điều 47 BLDS 2015.\nVì vậy, cả ba nhận định trên đều có lỗi sai về mặt lập luận pháp lý. Đáp án chuẩn được VMLU xác định là D (Cả ba đáp án trên)."
    },
    {
        "id": "39-0014",
        "domain": "legal",
        "track": "mc",
        "question": "Nhận định nào sau đây là đúng nhất?",
        "answer": "D",
        "raw_response": "Căn cứ Khoản 1 Điều 68 Bộ luật Dân sự 2015 quy định về tuyên bố mất tích: 'Khi một người biệt tích 02 năm liền trở lên, mặc dù đã áp dụng đầy đủ các biện pháp thông báo, tìm kiếm theo quy định của pháp luật về tố tụng dân sự mà vẫn không có tin tức xác thực về việc người đó còn sống hay đã chết thì theo yêu cầu của người có quyền, lợi ích liên quan, Tòa án có thể tuyên bố người đó mất tích'.\n- Nhận định A sai vì thiếu điều kiện áp dụng biện pháp tìm kiếm và bắt buộc phải có yêu cầu của người có quyền, lợi ích liên quan (Tòa án không đương nhiên tuyên bố).\n- Nhận định B sai về thời hạn (luật quy định 02 năm, không phải 03 năm).\n- Nhận định C sai vì 'sau 05 năm, kể từ ngày chiến tranh kết thúc' là căn cứ để tuyên bố một người là ĐÃ CHẾT theo Điểm a Khoản 1 Điều 71 BLDS 2015, chứ không phải tuyên bố mất tích.\nVì cả 3 nhận định A, B, C đều có điểm sai nên nhận định đúng nhất là D ('Không có nhận định nào'). Do đó, đáp án đúng là D."
    },
    {
        "id": "39-0015",
        "domain": "legal",
        "track": "mc",
        "question": "Tìm nhận định đúng nhất trong các nhận định dưới đây?",
        "answer": "A",
        "raw_response": "Căn cứ Khoản 2 Điều 73 Bộ luật Dân sự 2015 và Điều 67 Luật Hôn nhân và Gia đình 2014 về hậu quả pháp lý của việc hủy bỏ quyết định tuyên bố một người là đã chết: 'Trường hợp Tòa án hủy bỏ quyết định tuyên bố một người là đã chết mà vợ hoặc chồng của người đó đã kết hôn với người khác thì việc kết hôn đó vẫn có hiệu lực pháp luật, trừ trường hợp quy định tại khoản 3 Điều này'.\n- Phương án A phản ánh chính xác nguyên văn quy định pháp luật này.\n- Phương án B sai vì hôn nhân mới hoàn toàn hợp pháp và có hiệu lực, không có cơ chế bắt buộc hay trả lại quan hệ hôn nhân cũ khi người kia đã tái hôn hợp pháp.\n- Phương án C sai vì Khoản 1 Điều 73 BLDS 2015 quy định người bị tuyên bố là đã chết trở về có quyền yêu cầu những người đã nhận tài sản thừa kế trả lại tài sản còn lại.\nDo đó, đáp án đúng là A."
    },
    {
        "id": "39-0016",
        "domain": "legal",
        "track": "mc",
        "question": "Nhận định nào sau đây là sai?",
        "answer": "A",
        "raw_response": "Căn cứ Khoản 2 Điều 96 Bộ luật Dân sự 2015 quy định về chấm dứt pháp nhân: 'Pháp nhân chấm dứt tồn tại kể từ thời điểm xóa tên trong sổ đăng ký pháp nhân hoặc từ thời điểm được xác định trong quyết định của cơ quan nhà nước có thẩm quyền'. Đồng thời, theo quy định tại Điều 108 Luật Phá sản 2014, quyết định tuyên bố phá sản của Tòa án nhân dân là căn cứ để cơ quan đăng ký kinh doanh làm thủ tục xóa tên doanh nghiệp trong sổ đăng ký kinh doanh. Tư cách pháp nhân chỉ chính thức chấm dứt tồn tại khi bị xóa tên trong sổ đăng ký hoặc thời điểm ấn định trong quyết định của cơ quan có thẩm quyền, chứ không mặc nhiên chấm dứt ngay tại thời điểm có quyết định tuyên bố phá sản. Do đó, nhận định A ('Pháp nhân chấm dứt tồn tại từ thời điểm bị tuyên bố phá sản') là nhận định sai. Vì câu hỏi yêu cầu tìm nhận định sai, đáp án đúng là A."
    },
    {
        "id": "39-0017",
        "domain": "legal",
        "track": "mc",
        "question": "Những nhận định nào sau đây đúng?",
        "answer": "B",
        "raw_response": "Căn cứ Điều 105 Bộ luật Dân sự 2015 quy định về tài sản:\n- Khoản 1 quy định: 'Tài sản là vật, tiền, giấy tờ có giá và quyền tài sản'. Do đó, nhận định 2 (phương án B) 'Giấy tờ có giá, quyền tài sản là tài sản' là nhận định hoàn toàn chính xác theo luật định.\n- Khoản 2 quy định: 'Tài sản bao gồm bất động sản và động sản. Bất động sản và động sản có thể là tài sản hiện có và tài sản hình thành trong tương lai'. Do đó: Nhận định 1 sai vì tài sản không chỉ là những gì cá nhân hiện có mà bao gồm của tổ chức, pháp nhân, Nhà nước và cả tài sản hình thành trong tương lai; Nhận định 3 sai vì luật chỉ phân loại tài sản thành bất động sản và động sản, không có quy định 'và các tài sản khác'.\nVì chỉ có nhận định 2 đúng, nên đáp án đúng là B."
    },
    {
        "id": "39-0018",
        "domain": "legal",
        "track": "mc",
        "question": "Nhận định nào sau đây là sai?",
        "answer": "C",
        "raw_response": "Căn cứ Điều 116 và Điều 117 Bộ luật Dân sự 2015:\n- Theo Điều 116: 'Giao dịch dân sự là hợp đồng hoặc hành vi pháp lý đơn phương làm phát sinh, thay đổi hoặc chấm dứt quyền, nghĩa vụ dân sự'. Nhận định B đồng nhất giao dịch dân sự chỉ là hợp đồng dân sự là sai vì đã bỏ sót hành vi pháp lý đơn phương (như lập di chúc, từ bỏ quyền sở hữu...).\n- Theo Khoản 2 Điều 117: 'Hình thức của giao dịch dân sự là điều kiện có hiệu lực của giao dịch dân sự trong trường hợp luật có quy định'. Như vậy, chỉ khi luật có quy định bắt buộc về hình thức thì hình thức mới là điều kiện có hiệu lực; nhận định A khẳng định tuyệt đối hình thức là điều kiện có hiệu lực của giao dịch dân sự là sai.\nVì cả hai nhận định A và B đều sai nên phương án lựa chọn chính xác là C (A & B). Do đó, đáp án đúng là C."
    },
    {
        "id": "39-0019",
        "domain": "legal",
        "track": "mc",
        "question": "Giao dịch dân sự có thể được lập bằng?",
        "answer": "C",
        "raw_response": "Căn cứ Khoản 1 Điều 119 Bộ luật Dân sự 2015 quy định về hình thức giao dịch dân sự: 'Giao dịch dân sự được thể hiện bằng lời nói, bằng văn bản hoặc bằng hành vi cụ thể'.\nNhư vậy, giao dịch dân sự có thể được lập bằng miệng/lời nói hoặc bằng văn bản (phương án A), hoặc được lập bằng hành vi cụ thể (phương án B). Kết hợp cả hai phương án A và B ta được phương án toàn diện là C (A & B). Do đó, đáp án đúng là C."
    },
    {
        "id": "39-0020",
        "domain": "legal",
        "track": "mc",
        "question": "Giao dịch dân sự có nội dung không rõ ràng, khó hiểu, được hiểu theo nhiều nghĩa khác nhau thì việc giải thích giao dịch dân sự đó có thể được thực hiện theo:",
        "answer": "D",
        "raw_response": "Căn cứ Điểm a Khoản 1 Điều 121 Bộ luật Dân sự 2015 quy định về giải thích giao dịch dân sự:\n'1. Giao dịch dân sự có nội dung không rõ ràng, khó hiểu, được hiểu theo nhiều nghĩa khác nhau và không thuộc quy định tại khoản 2 Điều này thì việc giải thích giao dịch dân sự đó được thực hiện theo thứ tự sau đây:\na) Theo ý chí đích thực của các bên khi xác lập giao dịch;\nb) Theo nghĩa phù hợp với mục đích của giao dịch;\nc) Theo tập quán nơi giao dịch được xác lập.'\nPhương án D trích dẫn chính xác nguyên văn thứ tự ưu tiên số một theo luật định tại Điểm a Khoản 1 Điều 121 BLDS 2015: 'Theo ý chí đích thực của các bên khi xác lập giao dịch'. Do đó, đáp án đúng là D."
    },
    {
        "id": "39-0021",
        "domain": "legal",
        "track": "mc",
        "question": "Một trong những hậu quả pháp lý của giao dịch dân sự vô hiệu là?",
        "answer": "C",
        "raw_response": "Căn cứ Khoản 3 Điều 131 Bộ luật Dân sự 2015 quy định về hậu quả pháp lý của giao dịch dân sự vô hiệu: 'Bên ngay tình trong việc thu hoa lợi, lợi tức không phải hoàn trả lại hoa lợi, lợi tức đó'. Phương án C phản ánh chính xác nguyên văn quy định pháp luật này.\nPhân tích các phương án khác:\n- Phương án A sai vì pháp luật không quy định chế tài 'xin lỗi' và 'chịu phạt vi phạm' trong giải quyết hậu quả của giao dịch dân sự vô hiệu (Khoản 4 Điều 131 chỉ quy định bên có lỗi gây thiệt hại thì phải bồi thường).\n- Phương án B sai vì theo Khoản 2 Điều 131, nếu không thể hoàn trả lại bằng hiện vật thì được trị giá thành tiền để hoàn trả, không quy định 'bằng mọi giá phải khôi phục lại tình trạng ban đầu'.\nDo đó, đáp án đúng là C."
    },
    {
        "id": "39-0022",
        "domain": "legal",
        "track": "mc",
        "question": "Định nghĩa nào sau đây là đúng?",
        "answer": "A",
        "raw_response": "Căn cứ Khoản 1 Điều 144 Bộ luật Dân sự 2015 quy định về Thời hạn: 'Thời hạn là một khoảng thời gian được xác định từ thời điểm này đến thời điểm khác'. Phương án A định nghĩa chính xác, trọn vẹn và nguyên văn theo quy định của điều luật.\nPhân tích các phương án khác:\n- Phương án B sai vì thời hạn và thời hiệu là hai chế định pháp lý hoàn toàn khác biệt (Thời hiệu được quy định riêng tại Điều 149 BLDS 2015 là thời hạn do luật quy định mà khi kết thúc thời hạn đó thì phát sinh hậu quả pháp lý).\n- Phương án C và D sai vì chỉ mang tính mô tả cục bộ, không đúng với bản chất và định nghĩa luật định tại Điều 144.\nDo đó, đáp án đúng là A."
    },
    {
        "id": "38-0007",
        "domain": "legal",
        "track": "mc",
        "question": "Đại hội đại biểu toàn quốc Đảng Cộng sản Việt Nam lần thứ VI đưa ra đường lối đổi mới về kinh tế, được tổ chức năm:",
        "answer": "B",
        "raw_response": "Căn cứ Điều 4 Hiến pháp 2013 quy định về vai trò lãnh đạo của Đảng Cộng sản Việt Nam và Văn kiện Đại hội đại biểu toàn quốc lần thứ VI của Đảng: Đại hội đại biểu toàn quốc lần thứ VI diễn ra từ ngày 15 đến ngày 18 tháng 12 năm 1986 tại Hà Nội. Đây là đại hội lịch sử mở ra công cuộc Đổi mới toàn diện đất nước, trọng tâm là đổi mới kinh tế, bãi bỏ cơ chế tập trung quan liêu bao cấp và chuyển sang phát triển nền kinh tế hàng hóa nhiều thành phần vận hành theo cơ chế thị trường định hướng XHCN có sự quản lý của Nhà nước. Các mốc thời gian khác: 1976 là Đại hội IV, 1992 là năm ban hành Hiến pháp 1992, 2013 là năm ban hành Hiến pháp 2013. Do đó, đáp án đúng là B (1986)."
    },
    {
        "id": "38-0008",
        "domain": "legal",
        "track": "mc",
        "question": "Bộ luật kinh doanh được Quốc hội nước CHXHCN Việt Nam thông qua năm:",
        "answer": "D",
        "raw_response": "Căn cứ Khoản 1 Điều 70 Hiến pháp 2013 quy định thẩm quyền làm Hiến pháp và làm luật của Quốc hội, đối chiếu hệ thống pháp luật kinh tế - kinh doanh Việt Nam (Luật Doanh nghiệp 2020 số 59/2020/QH14, Luật Thương mại 2005 số 36/2005/QH11, Luật Đầu tư 2020 số 61/2020/QH14, Bộ luật Dân sự 2015 số 91/2015/QH13): Quốc hội nước CHXHCN Việt Nam chưa từng ban hành đạo luật nào có tên gọi là 'Bộ luật Kinh doanh'. Hoạt động kinh doanh được điều chỉnh bởi các luật chuyên ngành độc lập theo từng thời kỳ. Do đó, cả 3 mốc năm 1986, 1992 hay 2020 đều không có 'Bộ luật kinh doanh'. Phương án D ('Cả A, B và C đều sai') là chính xác. Do đó, đáp án đúng là D."
    },
    {
        "id": "38-0009",
        "domain": "legal",
        "track": "mc",
        "question": "Có hai phương pháp điều chỉnh trong Luật kinh doanh:",
        "answer": "C",
        "raw_response": "Căn cứ Điều 1, Điều 2 Luật Thương mại 2005, Điều 4, Điều 5 Luật Doanh nghiệp 2020 và Điều 3 Bộ luật Dân sự 2015: Pháp luật kinh doanh điều chỉnh hai nhóm quan hệ kinh tế cơ bản: (1) Quan hệ quản lý nhà nước về kinh tế giữa cơ quan nhà nước có thẩm quyền và các chủ thể kinh doanh -> áp dụng Phương pháp mệnh lệnh (quyền uy - phục tùng, mang tính bắt buộc đơn phương trong quản lý kinh tế, cấp phép, kiểm tra thuế); (2) Quan hệ kinh doanh, thương mại phát sinh ngang hàng giữa các chủ thể kinh doanh bình đẳng với nhau -> áp dụng Phương pháp bình đẳng, tự nguyện và thỏa thuận (quy định tại Điều 11 Luật Thương mại 2005). Do đó, hai phương pháp điều chỉnh của Luật kinh doanh là Phương pháp mệnh lệnh và Phương pháp bình đẳng tự nguyện. Do đó, đáp án đúng là C."
    },
    {
        "id": "38-0010",
        "domain": "legal",
        "track": "mc",
        "question": "Ngành luật kinh tế trong thời kỳ kinh tế kế hoạch hóa tập trung ở Việt Nam sử dụng phương pháp điều chỉnh chủ yếu là:",
        "answer": "C",
        "raw_response": "Căn cứ Điều 1, Điều 2 Pháp lệnh Hợp đồng kinh tế năm 1989 và cơ chế pháp lý thời kỳ kế hoạch hóa tập trung trước Đổi mới 1986: Trong nền kinh tế kế hoạch hóa tập trung bao cấp, toàn bộ các chỉ tiêu sản xuất, phân phối vật tư, tiêu thụ sản phẩm đều do Nhà nước ban hành bằng các chỉ tiêu kế hoạch pháp lệnh từ trên xuống. Các xí nghiệp quốc doanh và hợp tác xã hoạt động theo mệnh lệnh cấp trên, hợp đồng kinh tế thời kỳ này chỉ là công cụ hành chính để hiện thực hóa kế hoạch pháp lệnh. Do đó, phương pháp điều chỉnh chủ yếu, chiếm vị trí thống trị tuyệt đối của ngành luật kinh tế thời kỳ này là Phương pháp mệnh lệnh. Do đó, đáp án đúng là C."
    },
    {
        "id": "38-0011",
        "domain": "legal",
        "track": "mc",
        "question": "Cơ quan thuế đặt may đồng phục cho nhân viên ngành thuế tại doanh nghiệp dệt may do mình quản lý thuế. Trong quan hệ pháp luật này, phương pháp điều chỉnh được sử dụng là:",
        "answer": "C",
        "raw_response": "Căn cứ Điều 1, Điều 24 Luật Thương mại 2005, Điều 3, Điều 385, Điều 542 Bộ luật Dân sự 2015; phân định với thẩm quyền hành chính quản lý thuế tại Điều 18, Điều 19 Luật Quản lý thuế 2019: Mặc dù Cơ quan thuế có thẩm quyền quản lý nhà nước về thuế đối với doanh nghiệp dệt may, nhưng khi ký kết hợp đồng đặt may đồng phục phục vụ nhu cầu hậu cần nội bộ, Cơ quan thuế tham gia với tư cách là một bên chủ thể bình đẳng trong quan hệ hợp đồng dân sự/thương mại (gia công hoặc mua bán hàng hóa). Trong quan hệ này, hai bên hoàn toàn bình đẳng về địa vị pháp lý, tự nguyện thỏa thuận các điều khoản về chất liệu, quy cách may, đơn giá, thời hạn và phương thức thanh toán theo nguyên tắc bình đẳng tự nguyện (Khoản 1 Điều 3 BLDS 2015), cơ quan thuế không được sử dụng quyền lực công hay mệnh lệnh hành chính để áp đặt doanh nghiệp. Do đó, phương pháp điều chỉnh được sử dụng là Phương pháp bình đẳng tự nguyện. Đáp án đúng là C."
    }
]

out_path = "all_res/antigravity_gemini/results_batch_vmlu_legal_2.csv"
fieldnames = ["id", "domain", "track", "question", "raw_response", "answer"]

with open(out_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in items_data:
        writer.writerow(row)

print(f"Successfully generated {out_path} with {len(items_data)} rows.")
