"use client";

/** Tab "Tổng hợp nhận xét" — bản tĩnh cho một mô hình tham chiếu.
 *
 *  Nguồn số: Qwen3.5-9B-28K, measurement_card MC-7…MC-14b,
 *  các tệp kết quả trong `all_res/ollama_result/Qwen3_5-9B-28K/`
 *  (full_evaluation_*.csv, reading_scores_*.csv, vbench_server_scores_*.csv).
 *  CI, ma trận nhầm lẫn và nhóm char-F1 cao được tính ngoại tuyến bằng script
 *  phân tích (Wilson 95%, gold×dự đoán, ngưỡng char-F1), không phải số trực tiếp từ Mongo.
 *  Điều kiện đo: một lần chạy duy nhất, temperature 0, seed 42.
 *
 *  Nội dung này KHÔNG tự đổi theo mô hình đang chọn. Giao diện phải cảnh báo
 *  rõ khi người dùng đang xem một mô hình khác để tránh gán nhầm nhận xét.
 */

function GlossaryRow({ term, plain, example, pitfall }: { term: string; plain: string; example: string; pitfall: string }) {
  return (
    <tr className="border-t border-slate-100">
      <td className="py-2 px-3 font-bold text-slate-900 align-top">{term}</td>
      <td className="py-2 px-3 text-slate-700 align-top">{plain}</td>
      <td className="py-2 px-3 font-mono text-[11px] text-slate-600 align-top">{example}</td>
      <td className="py-2 px-3 text-rose-700 align-top">{pitfall}</td>
    </tr>
  );
}

export function OverviewTab({ modelId }: { modelId: string }) {
  const isReferenceModel = modelId === "qwen3-5-9b-28k";

  return (
    <div className="space-y-6">
      {/* HERO */}
      <div className="bg-gradient-to-r from-indigo-900 via-slate-900 to-teal-950 text-white rounded-2xl p-6 sm:p-8 shadow-sm">
        <div className="space-y-2 max-w-3xl">
          <div className="flex items-center gap-2 text-indigo-300 text-xs font-semibold uppercase tracking-wider">
            <span>Tổng hợp nhận xét · snapshot tĩnh</span> &bull; <span>Qwen3.5-9B-28K · seed 42 · temp 0 · một lần chạy</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Mô hình đạt gì — và nên đọc các con số thế nào?
          </h2>
          <p className="text-slate-300 text-sm leading-relaxed">
            Trang này tổng hợp các phép đo của một mô hình tham chiếu. Điểm số chỉ cho biết
            {" "}<em>đạt bao nhiêu</em>; phần nhận xét chỉ đưa ra các giả thuyết cần kiểm chứng,
            không coi tương quan là nguyên nhân nhân quả.
          </p>
          <p className="text-[11px] font-mono text-slate-400">
            AI soạn · chưa có người đánh giá xác nhận · nguồn số: measurement_card MC-7…MC-14b
          </p>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-6 pt-6 border-t border-white/10">
          {[
            { k: "VMLU dev+valid", v: "73,35%", s: "768/1.047 · CI [70,6; 75,9]" },
            { k: "VM14K 12.488", v: "64,79%", s: "8.091 · CI [64,0; 65,7]" },
            { k: "Reading-400", v: "EM 79,75%", s: "char-F1 86,49 · SQuAD 96,5 vs DROP 63" },
            { k: "V-Bench (máy chủ chấm)", v: "45,61%", s: "micro · macro 45,22 · CS 71 ↔ toán 20" },
          ].map((c) => (
            <div key={c.k} className="bg-white/5 rounded-xl p-3 border border-white/5">
              <div className="text-xs text-indigo-200 font-medium">{c.k}</div>
              <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">{c.v}</div>
              <div className="text-xs text-slate-400 mt-0.5 font-mono">{c.s}</div>
            </div>
          ))}
        </div>
      </div>

      <div
        className={
          isReferenceModel
            ? "rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-900"
            : "rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs leading-relaxed text-rose-900"
        }
        role="note"
      >
        {isReferenceModel ? (
          <>
            Đây là bản tổng hợp tĩnh của <b>Qwen3.5-9B-28K</b>, không tự cập nhật theo số liệu
            trực tiếp. Khi số ở thẻ khác lệch, hãy tin kết quả trực tiếp và dùng trang này làm giải thích
            tĩnh theo snapshot đã ghi.
          </>
        ) : (
          <>
            Mô hình đang chọn là <b className="font-mono">{modelId}</b>, nhưng nội dung dưới đây
            vẫn là snapshot của <b>Qwen3.5-9B-28K</b>. Không gán các nhận xét này cho mô hình đang
            chọn; hãy dùng phần nhận xét riêng trong từng thẻ bộ dữ liệu.
          </>
        )}
      </div>

      {/* 0. GLOSSARY — đọc trước để khỏi hiểu nhầm tiếng Việt chuyên ngành */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="p-5 border-b border-slate-200 bg-slate-50">
          <h3 className="font-bold text-slate-900 text-base">📖 Đọc trước: từ khó nghĩa là gì?</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Mỗi thuật ngữ có 4 cột: từ gốc → nói đơn giản → ví dụ số thật trong trang này → điều hay bị hiểu nhầm.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-100 text-slate-600 font-semibold">
              <tr>
                <th className="py-2 px-3">Thuật ngữ</th>
                <th className="py-2 px-3">Nói đơn giản</th>
                <th className="py-2 px-3">Ví dụ</th>
                <th className="py-2 px-3">Đừng hiểu nhầm thành…</th>
              </tr>
            </thead>
            <tbody className="text-slate-700">
              <GlossaryRow term="Accuracy (độ chính xác)" plain="Tỷ lệ câu được chấm đúng trên tổng số câu." example="VMLU 768/1.047 = 73,35%" pitfall="Điểm cao ở một bộ không đồng nghĩa với năng lực chung trên mọi miền." />
              <GlossaryRow term="Mốc chọn nhãn phổ biến" plain="Điểm đạt được nếu chỉ chọn nhãn phổ biến nhất, không cần đọc nội dung." example="Legal MC: chọn A luôn đạt 62,33%; mô hình đạt 87,67%." pitfall="Vượt mốc đối chứng là dữ kiện mô tả, chưa tự chứng minh mọi câu sai đều do thiếu kiến thức." />
              <GlossaryRow term="CI 95% (khoảng tin cậy)" plain="Khoảng giá trị kỳ vọng chứa tham số thực với xác suất 95% theo quy trình lấy mẫu lặp lại." example="VMLU tổng [70,6; 75,9]; môn n=10 có khoảng rất rộng." pitfall="Khoảng chồng nhau không tự động chứng minh hai môn không khác nhau; phụ thuộc phép thử và phương pháp." />
              <GlossaryRow term="Ma trận nhầm lẫn / recall / thiên lệch nhãn" plain="Đối chiếu đáp án đúng với nhãn mô hình dự đoán; recall cho biết trong nhóm vào có bao nhiêu được nhận đúng." example="VMLU: recall D 83,9%, còn A 62,5%." pitfall="Chênh recall là dấu hiệu phân bố lệch, không phải bằng chứng riêng về nguyên nhân hoặc hiệu chuẩn xác suất." />
              <GlossaryRow term="Độ chính xác cân bằng (balanced accuracy)" plain="Điểm trung bình theo các nhãn có mẫu, giúp giảm ảnh hưởng của phân bố lệch." example="Legal MC 84,1% sau khi bỏ lớp D không có mẫu." pitfall="Bỏ một nhãn không có mẫu có thể phù hợp, nhưng phải được ghi rõ và không thay thế kiểm định đầy đủ." />
              <GlossaryRow term="EM (khớp chuẩn hóa)" plain="Câu trả lời khớp gold sau khi chuẩn hóa khoảng trắng và dấu câu; luật hiện tại còn chấp nhận bỏ dấu và một số dạng số tương đương." example="Reading-400 EM 79,75% (319/400)." pitfall="Không phải so khớp từng ký tự nguyên bản và không đo trực tiếp ngữ nghĩa." />
              <GlossaryRow term="char-F1 (F1 ký tự)" plain="So sánh túi ký tự, không xét thứ tự ký tự." example="BidLQA EM ~33%, char-F1 ~74%." pitfall="Char-F1 cao chỉ chứng minh trùng nhiều ký tự, không chứng minh cùng nghĩa hoặc câu trả lời dùng được." />
              <GlossaryRow term="Gần đúng theo ký tự" plain="EM=0 nhưng char-F1 ≥ 0,8; đây là nhóm ứng viên cần kiểm tra thêm." example="BidLQA có 105/482 câu." pitfall="Không tự động gọi đây là lỗi tính toán hoặc chỉ lỗi trình bày." />
              <GlossaryRow term="Hợp lệ ≠ đúng" plain="Câu trả lời đúng cú pháp nhưng chưa chắc đúng hàm, tham số hoặc nội dung." example="V-Bench agentic hợp lệ 100% sau guided nhưng đúng nội dung thấp hơn." pitfall="Độ hợp lệ cú pháp không chứng minh chức năng gọi hàm đúng." />
              <GlossaryRow term="Macro / micro (V-Bench)" plain="Micro theo tổng câu; macro theo trung bình các miền." example="micro 45,61% · macro 45,22." pitfall="Không so trực tiếp với độ chính xác của VMLU vì thang và cấu trúc tập khác nhau." />
              <GlossaryRow term="Câu trả lời rỗng" plain="Không có nội dung sau khi xử lý; vẫn được tính là sai." example="qwen38-nothink có 21/146 câu rỗng dù đã nâng giới hạn lên 512 token." pitfall="Bản thân hiện tượng này không chỉ ra nguyên nhân là ngân sách token, mẫu hỏi, cấu hình hay tri thức." />
            </tbody>
          </table>
        </div>
      </div>

      {/* 1. MC */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="p-5 border-b border-slate-200 bg-slate-50">
          <h3 className="font-bold text-slate-900 text-base">1. Trắc nghiệm: điểm tổng + khoảng tin cậy + phân bố dự đoán</h3>
          <p className="text-xs text-slate-500 mt-0.5">CI = Wilson 95%. Độ chính xác cân bằng bỏ nhãn không có mẫu; xem ghi chú bên dưới.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-100 text-slate-700 font-semibold">
              <tr>
                <th className="py-2 px-3">Bộ</th>
                <th className="py-2 px-3 text-right">Độ chính xác</th>
                <th className="py-2 px-3 text-right">CI 95%</th>
                <th className="py-2 px-3 text-right">Chênh mốc đối chứng</th>
                <th className="py-2 px-3">Phân bố dự đoán</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              <tr>
                <td className="py-2 px-3 font-semibold">VMLU 1.047</td>
                <td className="py-2 px-3 text-right font-mono font-bold">73,35% (768)</td>
                <td className="py-2 px-3 text-right font-mono">[70,6; 75,9]</td>
                <td className="py-2 px-3 text-right font-mono">+46,8 (mốc 26,6%)</td>
                <td className="py-2 px-3">Gold gần cân bằng; mô hình dự đoán <b>D 308 / A 199</b>. Recall D 83,9%, A 62,5% — dấu hiệu phân bố dự đoán lệch, chưa giải thích nguyên nhân.</td>
              </tr>
              <tr>
                <td className="py-2 px-3 font-semibold">Legal MC 146</td>
                <td className="py-2 px-3 text-right font-mono font-bold">87,67% (128)</td>
                <td className="py-2 px-3 text-right font-mono">[81,4; 92,1]</td>
                <td className="py-2 px-3 text-right font-mono">+25,3 (mốc 62,3%)</td>
                <td className="py-2 px-3">Recall A 90 / B 87 / C 75. Mô hình chọn <b>D ở 8 câu</b> dù không có gold D — cần kiểm tra nhãn và lựa chọn ngoài phạm vi.</td>
              </tr>
              <tr>
                <td className="py-2 px-3 font-semibold">Khả năng hỗ trợ pháp lý 150</td>
                <td className="py-2 px-3 text-right font-mono font-bold">90,00% (135)</td>
                <td className="py-2 px-3 text-right font-mono">[84,2; 93,9]</td>
                <td className="py-2 px-3 text-right font-mono">+40,0 (mốc 50,0%)</td>
                <td className="py-2 px-3"><b>15/15 câu sai đều A→B</b>: dự đoán B 90 / A 60 dù gold cân bằng 75/75. Đây là bằng chứng thiên lệch nhãn, chưa phải đo hiệu chuẩn xác suất.</td>
              </tr>
              <tr>
                <td className="py-2 px-3 font-semibold">VM14K 12.488</td>
                <td className="py-2 px-3 text-right font-mono font-bold">64,79% (8.091)</td>
                <td className="py-2 px-3 text-right font-mono">[64,0; 65,7]</td>
                <td className="py-2 px-3 text-right font-mono">+33,4 (mốc 31,4%)</td>
                <td className="py-2 px-3">Recall D 75,1%, B 58,6%. Phân bố dự đoán lệch; chưa đủ để quy nguyên nhân mà không kiểm tra lại dữ liệu.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="px-5 py-3 text-[11px] text-slate-500 leading-relaxed border-t border-slate-100">
          * Độ chính xác cân bằng sau khi bỏ nhãn không có mẫu: VMLU 73,5% (xấp xỉ độ chính xác thường), Legal MC 84,1%, VM14K 65,3%.
          VMLU có 1 câu đáp án E duy nhất; Legal MC có 0 câu D trong đề nhưng mô hình chọn D ở 8 câu.
        </p>
      </div>

      {/* 2. VMLU categories + VM14K difficulty */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
          <div className="p-5 border-b border-slate-200 bg-slate-50">
            <h3 className="font-bold text-slate-900 text-sm">2a. VMLU theo nhóm (kèm CI)</h3>
          </div>
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-100 text-slate-700 font-semibold">
              <tr><th className="py-2 px-3">Nhóm</th><th className="py-2 px-3 text-right">Độ chính xác</th><th className="py-2 px-3 text-right">CI 95%</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700 font-mono">
              <tr><td className="py-2 px-3 font-sans">STEM (383)</td><td className="py-2 px-3 text-right font-bold text-emerald-700">79,37%</td><td className="py-2 px-3 text-right">[75,0; 83,1]</td></tr>
              <tr><td className="py-2 px-3 font-sans">Xã hội (184)</td><td className="py-2 px-3 text-right font-bold">78,26%</td><td className="py-2 px-3 text-right">[71,8; 83,6]</td></tr>
              <tr><td className="py-2 px-3 font-sans">Nhân văn (324)</td><td className="py-2 px-3 text-right font-bold text-amber-700">68,52%</td><td className="py-2 px-3 text-right">[63,3; 73,3]</td></tr>
              <tr><td className="py-2 px-3 font-sans">Khác (156)</td><td className="py-2 px-3 text-right font-bold text-rose-700">62,82%</td><td className="py-2 px-3 text-right">[55,0; 70,0]</td></tr>
            </tbody>
          </table>
          <p className="px-5 py-3 text-[11px] text-slate-500 leading-relaxed border-t border-slate-100">
            8 môn có điểm dưới 50% (mỗi môn chỉ n=10–20, chưa đủ đại diện cả mảng): mầm non 3/10 (30%) ·
            luật hành chính 3/10 (30%) · thuế công chức 6/18 · toán tiểu học 8/20 ·
            văn THPT 8/20 · kế toán 8/18 · toán THCS 5/11 · luật kinh tế 8/17.
          </p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
          <div className="p-5 border-b border-slate-200 bg-slate-50">
            <h3 className="font-bold text-slate-900 text-sm">2b. VM14K: điểm giảm theo nhãn độ khó</h3>
          </div>
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-100 text-slate-700 font-semibold">
              <tr><th className="py-2 px-3">Độ khó</th><th className="py-2 px-3 text-right">Độ chính xác</th><th className="py-2 px-3 text-right">CI 95%</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700 font-mono">
              <tr><td className="py-2 px-3 font-sans">Easy (4.112)</td><td className="py-2 px-3 text-right font-bold">67,19%</td><td className="py-2 px-3 text-right">[65,7; 68,6]</td></tr>
              <tr><td className="py-2 px-3 font-sans">Medium (7.093)</td><td className="py-2 px-3 text-right font-bold">64,01%</td><td className="py-2 px-3 text-right">[62,9; 65,1]</td></tr>
              <tr><td className="py-2 px-3 font-sans">Challenging (1.193)</td><td className="py-2 px-3 text-right font-bold">61,78%</td><td className="py-2 px-3 text-right">[59,0; 64,5]</td></tr>
              <tr><td className="py-2 px-3 font-sans">Hard (90)</td><td className="py-2 px-3 text-right font-bold">56,67%</td><td className="py-2 px-3 text-right">[46,4; 66,4]</td></tr>
            </tbody>
          </table>
          <p className="px-5 py-3 text-[11px] text-slate-500 leading-relaxed border-t border-slate-100">
            Theo số lựa chọn: 4 lựa chọn 64,16% (11.111 câu — lấy làm số chính) ·
            Đúng/Sai 69,84% (1.240 câu, kéo điểm tổng lên) · 7 lựa chọn 57,9% (n=19).
          </p>
        </div>
      </div>

      {/* 3. Reading */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="p-5 border-b border-slate-200 bg-slate-50">
          <h3 className="font-bold text-slate-900 text-base">3. Đọc hiểu: mức trùng lớn và khác biệt theo dạng câu</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-100 text-slate-700 font-semibold">
              <tr><th className="py-2 px-3">Dạng câu</th><th className="py-2 px-3 text-right">n</th><th className="py-2 px-3 text-right">EM</th><th className="py-2 px-3 text-right">char-F1</th><th className="py-2 px-3">Đọc thế nào</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              <tr><td className="py-2 px-3 font-semibold">DROP dạng khác (other)</td><td className="py-2 px-3 text-right font-mono">7</td><td className="py-2 px-3 text-right font-mono font-bold text-rose-600">28,6%</td><td className="py-2 px-3 text-right font-mono">60,5</td><td className="py-2 px-3">Điểm thấp nhất nhưng n=7; khoảng tin cậy rất rộng, chỉ mô tả.</td></tr>
              <tr><td className="py-2 px-3 font-semibold">DROP đếm (count)</td><td className="py-2 px-3 text-right font-mono">40</td><td className="py-2 px-3 text-right font-mono font-bold text-rose-600">47,5%</td><td className="py-2 px-3 text-right font-mono">56,0</td><td className="py-2 px-3">Thấp nhất trong nhóm đếm; cần kiểm tra lỗi đếm, cách diễn đạt gold và định dạng.</td></tr>
              <tr><td className="py-2 px-3 font-semibold">DROP cộng/trừ</td><td className="py-2 px-3 text-right font-mono">55</td><td className="py-2 px-3 text-right font-mono font-bold text-amber-700">58,2%</td><td className="py-2 px-3 text-right font-mono">75,9</td><td className="py-2 px-3">Có thể liên quan đến phép tính hoặc cách chuẩn hóa câu trả lời.</td></tr>
              <tr><td className="py-2 px-3 font-semibold">DROP so sánh</td><td className="py-2 px-3 text-right font-mono">57</td><td className="py-2 px-3 text-right font-mono font-bold text-amber-700">61,4%</td><td className="py-2 px-3 text-right font-mono">73,1</td><td className="py-2 px-3">Cần phép thử độc lập để tách lỗi so sánh khỏi lỗi diễn đạt.</td></tr>
              <tr><td className="py-2 px-3 font-semibold">DROP chọn đáp án</td><td className="py-2 px-3 text-right font-mono">41</td><td className="py-2 px-3 text-right font-mono font-bold text-emerald-600">92,7%</td><td className="py-2 px-3 text-right font-mono">94,3</td><td className="py-2 px-3">Điểm cao hơn các dạng cần phép tính; vẫn là lát cắt riêng.</td></tr>
              <tr><td className="py-2 px-3 font-semibold">SQuAD (trích xuất)</td><td className="py-2 px-3 text-right font-mono">200</td><td className="py-2 px-3 text-right font-mono font-bold text-emerald-600">96,5%</td><td className="py-2 px-3 text-right font-mono">~98–100</td><td className="py-2 px-3">Các nhóm direct khoảng 96–98; mỗi nhóm infer chỉ có n=5.</td></tr>
              <tr><td className="py-2 px-3 font-semibold">BidLQA val / test</td><td className="py-2 px-3 text-right font-mono">482 / 603</td><td className="py-2 px-3 text-right font-mono font-bold">32,8 / 33,2%</td><td className="py-2 px-3 text-right font-mono">74,2 / 73,2</td><td className="py-2 px-3">Nhiều câu có char-F1 cao nhưng EM=0; cần đánh giá ngữ nghĩa trước khi gọi là lỗi định dạng.</td></tr>
            </tbody>
          </table>
        </div>
        <p className="px-5 py-3 text-[11px] text-slate-500 leading-relaxed border-t border-slate-100">
          Câu sai ở Reading-400 ngắn hơn đáp án (trung bình 16 so với 26 ký tự), có thể liên quan đến giới hạn 48 token; cần `finish_reason` và số token để xác nhận.
          Ở BidLQA, độ dài và char-F1 chỉ mô tả khác biệt bề mặt; chưa đủ kết luận mô hình viết lại thay vì trích nguyên văn.
        </p>
      </div>

      {/* 4. V-Bench */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="p-5 border-b border-slate-200 bg-slate-50">
          <h3 className="font-bold text-slate-900 text-base">4. V-Bench: điểm miền và độ bất định</h3>
          <p className="text-xs text-slate-500 mt-0.5">CI mô tả bất định của từng tỷ lệ; không tự chứng minh khác biệt giữa các miền. Tệp cuối có 14 câu guided.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-100 text-slate-700 font-semibold">
              <tr><th className="py-2 px-3">Miền</th><th className="py-2 px-3 text-right">Điểm</th><th className="py-2 px-3 text-right">CI 95%</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700 font-mono">
              {[
                ["Toán", "20,00% (25/125)", "[13,9; 27,9]"],
                ["Logic", "24,89% (56/225)", "[19,7; 30,9]"],
                ["Vật lý", "28,57% (42/147)", "[21,9; 36,3]"],
                ["Y (V-Bench)", "38,57% (189/490)", "[34,4; 43,0]"],
                ["Hóa", "38,92% (130/334)", "[33,8; 44,2]"],
                ["Agentic (tệp cuối có guided)", "39,70% (397/1.000)", "[36,7; 42,8]"],
                ["Văn học", "41,10% (247/601)", "[37,2; 45,1]"],
                ["Văn hóa", "47,93% (104/217)", "[41,4; 54,6]"],
                ["Tâm lý", "49,25% (393/798)", "[45,8; 52,7]"],
                ["Phương ngữ", "60,14% (338/562)", "[56,0; 64,1]"],
                ["Luật (lý thuyết)", "62,83% (120/191)", "[55,8; 69,4]"],
                ["Triết", "64,64% (170/263)", "[58,7; 70,2]"],
                ["Khoa học máy tính", "71,28% (134/188)", "[64,4; 77,3]"],
              ].map(([a, b, c]) => (
                <tr key={a}>
                  <td className="py-2 px-3 font-sans font-semibold text-slate-900">{a}</td>
                  <td className="py-2 px-3 text-right font-bold">{b}</td>
                  <td className="py-2 px-3 text-right text-slate-500">{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="px-5 py-3 text-[11px] text-slate-500 leading-relaxed border-t border-slate-100">
          Điểm agentic 397/1.000 thuộc tệp cuối có 14 câu guided; không nên gọi toàn bộ là minimal thuần.
          Y ở V-Bench 38,57% và VM14K 64,79% là hai phép đo khác dạng, chỉ mô tả khác hướng; không trừ phần trăm cho nhau.
        </p>
      </div>

      {/* 5. Conclusions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[
          { t: "1. Phân bố nhãn có dấu hiệu lệch", d: "VMLU/VM14K có recall D cao hơn A/B; nhiệm vụ khả năng hỗ trợ pháp lý có 15/15 lỗi A→B. Đây là dữ kiện mô tả, cần tập độc lập và kiểm tra thiên lệch trước khi dùng cho định tuyến hoặc RAG." },
          { t: "2. Thước đo bề mặt không tự chỉ ra nguyên nhân", d: "Char-F1 cao ở BidLQA hoặc EM thấp ở Reading-400 chỉ là tín hiệu bề mặt. Cần đánh giá ngữ nghĩa, `finish_reason` và phép thử ngân sách suy luận trước khi kết luận lỗi định dạng hay suy luận." },
          { t: "3. Cỡ mẫu nhỏ không đại diện miền", d: "Mỗi môn VMLU thường chỉ có 10–20 câu. “Luật hành chính 30% (n=10)” và Legal MC 87,67% (n=146) là hai phép đo khác nhau; chưa đủ để kết luận năng lực pháp luật nói chung." },
          { t: "4. Điều kiện hỏi ảnh hưởng kết quả", d: "Prompt minimal→detailed làm 42,2% câu agentic của mô hình 27B đổi đáp án; tệp cuối của mô hình 9B còn có 14 câu guided. Mỗi phép so sánh phải khóa và báo rõ phương thức thu thập câu trả lời." },
        ].map((c) => (
          <div key={c.t} className="bg-indigo-50/50 rounded-xl p-4 border border-indigo-100">
            <h4 className="font-bold text-slate-900 text-sm">{c.t}</h4>
            <p className="text-xs text-slate-600 leading-relaxed mt-1">{c.d}</p>
          </div>
        ))}
      </div>

      {/* 6. Limits */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-2">
        <h3 className="font-bold text-amber-900 text-sm">⚠️ Giới hạn diễn giải</h3>
        <ul className="list-disc pl-5 space-y-1 text-xs text-amber-900/90 leading-relaxed">
          <li>Một lần chạy duy nhất (seed 42, temp 0) chưa đo biến động dịch vụ. So 9B với 27B còn bị đồng biến (confounded) giữa quy mô tham số và phương pháp lượng tử hóa; cần phép thử ghép cặp, lặp nhiều lần hoặc kiểm định tương đương.</li>
          <li>Không cộng/trừ điểm giữa các bộ khác thang đo. Chỉ mô tả “cùng hướng / khác hướng” và nêu rõ khác biệt dạng câu.</li>
          <li>Chưa có đối chứng song ngữ hoặc mẫu kiểm soát nội dung, nên chưa thể tách năng lực tiếng Việt khỏi tri thức môn.</li>
          <li>Mô hình 9B vượt giới hạn ≤4B của LegalSLM; cần nêu rõ khi công bố.</li>
          <li>Gold Reading-400 do một người duyệt khi nhìn thấy câu trả lời của Qwen3.8; 321/400 câu giữ nguyên văn theo trạng thái Chấp nhận (Accept). Vì vậy chưa có độ khớp giữa người đánh giá (IAA) và điểm không độc lập hoàn toàn.</li>
          <li>Char-F1 chỉ so sánh túi ký tự; không chứng minh cùng ngữ nghĩa hoặc lỗi chỉ nằm ở định dạng. Gold BidLQA cũng chưa được hai người kiểm chứng.</li>
          <li>Thang khó VM14K do bộ tự khai báo; Hard chỉ n=90, câu bảy lựa chọn chỉ n=19, và tổng hợp nhiều số lựa chọn.</li>
          <li>Đây là snapshot tĩnh của Qwen3.5-9B-28K, không phải số trực tiếp theo mô hình đang chọn.</li>
        </ul>
      </div>
    </div>
  );
}
