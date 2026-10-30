import type { RouterExperiment, RouterResults, RouterRole, RouterStatus, RouterTable } from "@/lib/router-results.ts";
import { fmtInt, fmtNum } from "@/lib/format.ts";

const STATUS: Record<RouterStatus, { label: string; className: string }> = {
  met: { label: "Đạt", className: "border-accept/40 bg-accept-soft text-accept" },
  partial: { label: "Đạt một phần", className: "border-flag/40 bg-flag-soft text-flag" },
  not_met: { label: "Không đạt", className: "border-reject/40 bg-reject-soft text-reject" },
  descriptive: { label: "Mô tả", className: "border-hair bg-paper text-ink-2" },
};
const ROLE: Record<RouterRole, string> = {
  candidate: "font-semibold text-ink",
  baseline: "text-ink-2",
  ceiling: "italic text-ink-3",
  reference: "text-ink-3",
};

function StatusBadge({ status }: { status: RouterStatus }) {
  return <span className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${STATUS[status].className}`}>{STATUS[status].label}</span>;
}

function fmtP(p: number): string {
  if (p >= 0.9995) return "p 1,0";
  if (p < 0.0001) return "p < 0,0001";
  return `p ${fmtNum(p, p < 0.01 ? 4 : 3)}`;
}

function ResultTable({ table }: { table: RouterTable }) {
  return <figure className="mt-4">
    <figcaption className="mb-2 text-[12.5px] font-semibold text-ink-2">{table.title}</figcaption>
    <div className="overflow-x-auto rounded-xl border border-hair bg-card">
      <table className="w-full border-collapse text-[12px]" style={{ minWidth: 260 + table.columns.length * 130 }}>
        <thead><tr className="border-b border-hair bg-paper text-ink-2">
          <th scope="col" className="min-w-60 px-4 py-2.5 text-left font-semibold">Cách chọn</th>
          {table.columns.map((column) => <th key={column.id} scope="col" className="min-w-28 px-3 py-2.5 text-right font-semibold"><span className="block text-ink">{column.label}</span><span className="mt-0.5 block text-[10px] font-normal text-ink-3">{column.metric} · {fmtInt(column.n)} câu</span></th>)}
        </tr></thead>
        <tbody>{table.rows.map((row) => <tr key={row.id} className={`border-b border-hair/70 last:border-0 ${row.role === "candidate" ? "bg-paper/60" : ""}`}>
          <th scope="row" className={`px-4 py-2.5 text-left font-normal ${ROLE[row.role]}`}>{row.label}</th>
          {table.columns.map((column) => {
            const cell = row.cells[column.id];
            return <td key={column.id} className="whitespace-nowrap px-3 py-2.5 text-right align-top font-mono tabular-nums">
              {cell ? <>
                <span className={row.role === "candidate" ? "font-semibold text-ink" : "text-ink-2"}>{fmtNum(cell.score)}</span>
                {cell.ci ? <span className="block text-[10px] text-ink-3">{fmtNum(cell.ci[0], 1)}–{fmtNum(cell.ci[1], 1)}</span> : null}
                {cell.tokens !== null ? <span className="block text-[10px] text-ink-3">{fmtInt(cell.tokens)} token</span> : null}
              </> : <span className="text-ink-3" aria-label="Không đo trong thí nghiệm này">—</span>}
            </td>;
          })}
        </tr>)}</tbody>
      </table>
    </div>
    {table.note ? <p className="mt-2 text-[11px] text-ink-3">{table.note}</p> : null}
  </figure>;
}

function ExperimentCard({ experiment }: { experiment: RouterExperiment }) {
  return <article id={`router-${experiment.id}`} className="scroll-mt-5 rounded-xl border border-hair bg-card p-4 sm:p-5">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="font-mono text-[10.5px] text-ink-3">{experiment.cards}</p><h3 className="mt-0.5 font-disp text-[18px] font-semibold">{experiment.title}</h3></div>
      <StatusBadge status={experiment.status} />
    </header>
    <dl className="mt-3 grid gap-x-6 gap-y-1.5 text-[12px] sm:grid-cols-[120px_minmax(0,1fr)]">
      <dt className="text-ink-3">Câu hỏi</dt><dd className="text-ink">{experiment.question}</dd>
      <dt className="text-ink-3">Model được hỏi</dt><dd className="text-ink-2">{experiment.student}</dd>
      <dt className="text-ink-3">Tập câu</dt><dd className="text-ink-2">{experiment.items}</dd>
    </dl>
    {experiment.tables.map((table) => <ResultTable key={table.title} table={table} />)}
    {experiment.tests.length ? <div className="mt-4">
      <h4 className="text-[12.5px] font-semibold text-ink-2">Phép so sánh</h4>
      <ul className="mt-1.5 space-y-1.5 text-[12px]">{experiment.tests.map((test) => <li key={test.label} className={test.primary ? "text-ink" : "text-ink-2"}>
        {test.primary ? <span className="mr-1.5 rounded border border-hair bg-paper px-1.5 py-0.5 text-[10px] text-ink-3">chính</span> : null}
        {test.label}:{" "}
        <span className="font-mono tabular-nums">
          {test.diff !== null ? `${test.diff > 0 ? "+" : ""}${fmtNum(test.diff)} điểm` : ""}
          {test.ci ? ` (CI95 ${fmtNum(test.ci[0], 1)} … ${fmtNum(test.ci[1], 1)})` : ""}
          {test.p !== null ? `${test.diff !== null ? "; " : ""}${fmtP(test.p)}` : ""}
        </span>
        {test.p_kind ? <span className="text-ink-3"> · {test.p_kind}</span> : null}
        {test.note ? <span className="block text-[11px] text-ink-3">{test.note}</span> : null}
      </li>)}</ul>
    </div> : null}
    <p className="mt-4 rounded-lg border border-hair bg-paper px-3 py-2.5 text-[12.5px] leading-relaxed text-ink"><b>Kết luận.</b> {experiment.verdict}</p>
    {experiment.notes.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-[11.5px] leading-relaxed text-ink-3">{experiment.notes.map((note) => <li key={note}>{note}</li>)}</ul> : null}
    <p className="mt-3 break-all text-[10px] text-ink-3">Nguồn: {experiment.sources.map((source) => `${source.path} (${source.sha256.slice(0, 12)}…)`).join(" · ")}</p>
  </article>;
}

/** The router and diagnosis experiments: one overview row each, then one card per experiment with its own tables. */
export function RouterResultsView({ results, error }: { results: RouterResults | null; error: string | null }) {
  if (!results) {
    return <p role="alert" className="rounded-xl border border-reject/40 bg-reject-soft p-4 text-[13px] text-reject">Không đọc được dữ liệu router: {error ?? "chưa có file data/router-results.json"}.</p>;
  }
  return <section aria-labelledby="router-title">
    <h2 id="router-title" className="font-disp text-[21px] font-semibold">Router và chẩn đoán (MC-90 – MC-103)</h2>
    <p className="mt-1 max-w-4xl text-[12.5px] leading-relaxed text-ink-2">Các thí nghiệm tìm cách hỏi model tốt hơn cho từng câu. Mỗi thí nghiệm chạy trên một tập câu riêng nên có bảng riêng; không so điểm giữa hai thí nghiệm khác nhau. Mọi con số lấy từ báo cáo phân tích đã đăng ký của từng thẻ đo.</p>
    <p className="mt-2 max-w-4xl text-[11.5px] leading-relaxed text-ink-3">B: hỏi thẳng · S: suy luận từng bước · Q: trích câu trong đoạn văn rồi đáp · K: kèm bằng chứng do BM25 tự tìm · O: kèm sẵn đúng bằng chứng, chỉ để đo trần. CI95 là khoảng tin cậy 95%; p dưới {fmtNum(results.alpha)} nghĩa là khác biệt khó xảy ra do may rủi. Dòng in đậm là cách đang được thử.</p>
    <div className="mt-4 overflow-x-auto rounded-xl border border-hair bg-card">
      <table className="w-full min-w-[760px] border-collapse text-[12px]">
        <caption className="sr-only">Tổng quan các thí nghiệm router và chẩn đoán</caption>
        <thead><tr className="border-b border-hair bg-paper text-ink-2">
          <th scope="col" className="px-3 py-2.5 text-left font-semibold">Thẻ đo</th>
          <th scope="col" className="px-3 py-2.5 text-left font-semibold">Hỏi gì</th>
          <th scope="col" className="px-3 py-2.5 text-left font-semibold">Kết luận</th>
          <th scope="col" className="px-3 py-2.5 text-left font-semibold">Trạng thái</th>
        </tr></thead>
        <tbody>{results.experiments.map((experiment) => <tr key={experiment.id} className="border-b border-hair/70 last:border-0">
          <th scope="row" className="whitespace-nowrap px-3 py-2.5 text-left align-top font-mono text-[11px] font-normal"><a href={`#router-${experiment.id}`} className="text-ink-2 underline underline-offset-2">{experiment.cards}</a></th>
          <td className="px-3 py-2.5 align-top text-ink">{experiment.question}</td>
          <td className="px-3 py-2.5 align-top text-ink-2">{experiment.verdict}</td>
          <td className="px-3 py-2.5 align-top"><StatusBadge status={experiment.status} /></td>
        </tr>)}</tbody>
      </table>
    </div>
    <div className="mt-8 space-y-6">{results.experiments.map((experiment) => <ExperimentCard key={experiment.id} experiment={experiment} />)}</div>
    <p className="mt-6 text-[10.5px] text-ink-3">Cập nhật từ artifact: {new Date(results.generated_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}. MC-99 (thử tín hiệu cho router ở bước thiết kế) chưa có trong trang này.</p>
  </section>;
}
