import type { MatrixGroup, MatrixMetric } from "@/lib/benchmark-matrix.ts";
import { fmtPct } from "@/lib/format.ts";

/** Editorial hypotheses are separate from the scores read from the benchmark matrix. */
export default function BenchmarkModelObservations({ group }: { group: MatrixGroup }) {
  const score = (model: string, dataset: string, metric: MatrixMetric = "accuracy") =>
    fmtPct(group.matrices.find((matrix) => matrix.metric === metric)?.columns.find((column) => column.id === dataset)?.cells[model]?.score.score);
  const observations: Record<string, { observed: string; hypothesis: string }> = {
    "muse-spark-1-3-contributor": {
      observed: `Khá cân bằng: VMLU Test ${score("muse-spark-1-3-contributor", "vmlu-test")}, Legal MC ${score("muse-spark-1-3-contributor", "legal-mc")}; nổi bật ở Vi-DROP và ViBidLQA. Legal NLI thấp hơn, đạt ${score("muse-spark-1-3-contributor", "legal-nli")}.`,
      hypothesis: "Có thể mạnh về kiến thức và tổng hợp bài đọc, nhưng kém hơn ở phân biệt quan hệ suy ra / mâu thuẫn / trung lập. Cách hiểu nhãn hoặc dữ liệu huấn luyện có thể ảnh hưởng; reasoning dài hơn chưa chắc khắc phục được.",
    },
    "muse12-vmlu-mc74-mc79": {
      observed: `Trắc nghiệm mạnh: VMLU Test ${score("muse12-vmlu-mc74-mc79", "vmlu-test")}, Legal MC ${score("muse12-vmlu-mc74-mc79", "legal-mc")}. Theo bộ chấm v2, bài đọc thấp rõ rệt (Vi-DROP EM ${score("muse12-vmlu-mc74-mc79", "vi-drop", "em")} / token F1 ${score("muse12-vmlu-mc74-mc79", "vi-drop", "token_f1")}), phần lớn vì câu trả lời in đậm. Theo v3, token F1 Vi-SQuAD ${score("muse12-vmlu-mc74-mc79", "vi-squad", "token_f1_v3")} và ViBidLQA ${score("muse12-vmlu-mc74-mc79", "bidlqa-test", "token_f1_v3")} nằm trong khoảng của các model khác; chỉ Vi-DROP còn thấp rõ (${score("muse12-vmlu-mc74-mc79", "vi-drop", "token_f1_v3")}).`,
      hypothesis: "Kiến thức tốt; điểm đọc v2 bị kéo thấp chủ yếu vì định dạng (in đậm bằng **), không phải vì đọc kém. Vi-DROP vẫn thấp sau khi bỏ in đậm, nên tính toán nhiều bước hoặc câu trả lời dài vẫn có thể là điểm yếu thật; cần xem response thô.",
    },
    "mimo-v2-6-flash": {
      observed: `VMLU Test ${score("mimo-v2-6-flash", "vmlu-test")}, Legal NLI ${score("mimo-v2-6-flash", "legal-nli")}. Vi-SQuAD và ViBidLQA cao hơn MiMo 2.5; Vi-DROP EM còn ${score("mimo-v2-6-flash", "vi-drop", "em")}.`,
      hypothesis: "Có thể cải thiện làm theo chỉ dẫn và trích xuất so với 2.5, trong khi suy luận số học nhiều bước còn hạn chế. Thinking auto và giới hạn output của provider có thể ảnh hưởng kết quả.",
    },
    "mimo-v2-5": {
      observed: `VMLU Test ${score("mimo-v2-5", "vmlu-test")}, Legal NLI ${score("mimo-v2-5", "legal-nli")}. Điểm đọc thường thấp hơn 2.6, nhưng Legal MC và Vi-DROP EM nhỉnh hơn.`,
      hypothesis: "Có thể giữ nền kiến thức và suy luận nhãn khá ổn, nhưng trích xuất hoặc khớp cách diễn đạt tham chiếu yếu hơn. Các chênh lệch nhỏ chưa đủ chứng minh một phiên bản tốt hơn trên mọi tác vụ.",
    },
    "qwen3-5-9b-65k": {
      observed: `VMLU Test ${score("qwen3-5-9b-65k", "vmlu-test")}; Legal NLI ${score("qwen3-5-9b-65k", "legal-nli")} cao nhất nhóm. Vi-SQuAD EM ${score("qwen3-5-9b-65k", "vi-squad", "em")} đồng hạng cao nhất, token F1 ${score("qwen3-5-9b-65k", "vi-squad", "token_f1")} cao nhất.`,
      hypothesis: "Quy mô 9B có thể hạn chế độ phủ kiến thức, nhưng model làm tốt khi ngữ cảnh đã cung cấp đáp án hoặc cần phân loại quan hệ. Context 65K tự nó chưa đảm bảo kiến thức hoặc suy luận tốt hơn.",
    },
  };
  return <section id="model-observations" aria-labelledby="model-observations-title" className="mb-8 rounded-xl border border-hair bg-card p-4 sm:p-5">
    <h2 id="model-observations-title" className="font-disp text-[20px] font-semibold">Nhận xét năng lực model & giả thiết ảnh hưởng</h2>
    <p className="mt-1 text-[12px] leading-relaxed text-ink-3">Phạm vi: nhóm OMP · không tools · Temperature 1,0 · thinking auto · seed không gửi. Điểm bên dưới lấy từ bảng; các giải thích là giả thiết, chưa phải kết luận nhân quả.</p>
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[760px] border-collapse text-left text-[12px] leading-6">
        <caption className="sr-only">Quan sát kết quả và giả thiết cho từng model trong nhóm OMP không tools</caption>
        <thead><tr className="border-b border-hair text-ink-2"><th scope="col" className="w-[16%] px-3 py-2 font-semibold">Model</th><th scope="col" className="w-[39%] px-3 py-2 font-semibold">Quan sát từ benchmark</th><th scope="col" className="px-3 py-2 font-semibold">Giả thiết cần kiểm chứng</th></tr></thead>
        <tbody>{group.models.filter((model) => observations[model.id]).map((model) => <tr key={model.id} className="border-b border-hair/70 last:border-0">
          <th scope="row" className="px-3 py-3 align-top font-semibold text-ink">{model.name}</th>
          <td className="px-3 py-3 align-top text-ink-2">{observations[model.id].observed}</td>
          <td className="px-3 py-3 align-top text-ink-3">{observations[model.id].hypothesis}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <details className="mt-4 border-t border-hair pt-3 text-[12px] leading-6 text-ink-3" open>
      <summary className="cursor-pointer font-semibold text-ink-2">Các yếu tố cần cân nhắc khi so sánh</summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li><strong>Reasoning & tham số:</strong> thinking auto không cố định cùng mức reasoning giữa các provider; chưa đủ metadata về số tham số và quantization của các model khác để quy thứ hạng cho quy mô model.</li>
        <li><strong>Metric & parser:</strong> EM/F1 phụ thuộc cách diễn đạt, trích xuất và đáp án tham chiếu; mức khớp từ vựng chưa xác nhận đúng về ngữ nghĩa. Bộ chấm v2 còn trừ điểm câu trả lời in đậm; bảng v3 bỏ dấu in đậm rồi chấm lại.</li>
        <li><strong>Harness & sampling:</strong> chưa tách được tác động riêng của OMP. Baseline API trực tiếp khác temperature, seed và metadata thinking; không thể suy ra chênh lệch chỉ do harness.</li>
        <li><strong>Provider & workers:</strong> workers chủ yếu ảnh hưởng throughput. VMLU Test Muse 1.2 ghép route CMC/OCG; chênh {score("muse12-vmlu-mc74-mc79", "vmlu-test")} so với {score("muse-spark-1-3-contributor", "vmlu-test")} chưa đủ kết luận 1.2 tốt hơn 1.3.</li>
      </ul>
    </details>
  </section>;
}
