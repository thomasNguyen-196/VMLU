import type { RouterCell, RouterExperiment, RouterExplainer, RouterMethod, RouterResults, RouterRole, RouterStatus, RouterTable, RouterTest } from "@/lib/router-results.ts";
import { namedTest, overviewCell } from "@/lib/router-results.ts";
import { fmtDelta, fmtInt, fmtNum } from "@/lib/format.ts";

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

/** Colour only a registered (primary) comparison whose p is under alpha: green when the tried way is ahead. */
function tone(test: RouterTest, alpha: number): string {
  if (!test.primary || test.p === null || test.p >= alpha) return "";
  return test.diff !== null && test.diff < 0 ? "font-semibold text-reject" : "font-semibold text-accept";
}

/** Difference and p of a comparison as the card reports them; the interval only when there is no p (a
 *  non-inferiority check), since the full list under each card keeps every interval. */
function figures(test: RouterTest): string {
  return [test.diff !== null ? fmtDelta(test.diff, 1) : null,
    test.ci && test.p === null ? `CI95 ${fmtNum(test.ci[0], 1)} … ${fmtNum(test.ci[1], 1)}` : null,
    test.p !== null ? fmtP(test.p) : null].filter(Boolean).join(" · ");
}

function Score({ cell, strong = false }: { cell: RouterCell | null; strong?: boolean }) {
  return cell
    ? <span className={strong ? "font-semibold text-ink" : "text-ink-2"}>{fmtNum(cell.score, 1)}</span>
    : <span className="text-ink-3" aria-label="Không đo trên tập câu này">—</span>;
}

/** Bảng 1: the before / after of one experiment whose cells share items and prompts with /table, one row group
 *  per model. The figure under a score is the registered paired difference, read from the card's test. */
function BenchmarkTable({ results }: { results: RouterResults }) {
  const { benchmark } = results;
  const experiment = results.experiments.find((entry) => entry.id === benchmark.experiment)!;
  const columns = experiment.tables[benchmark.groups[0].table].columns;
  return <section aria-labelledby="router-benchmark" className="mt-6">
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
      <h3 id="router-benchmark" className="font-disp text-[17px] font-semibold">Bảng 1 · {benchmark.title}</h3>
      <p className="flex items-center gap-2"><a href={`#router-${experiment.id}`} className="font-mono text-[11px] text-ink-2 underline underline-offset-2">{experiment.cards}</a><StatusBadge status={experiment.status} /></p>
    </div>
    <p className="mt-1 max-w-4xl text-[12px] leading-relaxed text-ink-2">{experiment.verdict}</p>
    <div className="mt-3 overflow-x-auto rounded-xl border border-hair bg-card">
      <table className="w-full border-collapse text-[12px]" style={{ minWidth: 210 + columns.length * 104 }}>
        <caption className="sr-only">{benchmark.title}</caption>
        <thead><tr className="border-b border-hair bg-paper text-ink-2">
          <th scope="col" className="px-4 py-2.5 text-left font-semibold">Model · cách hỏi</th>
          {columns.map((column) => <th key={column.id} scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-semibold"><span className="block text-ink">{column.label}</span><span className="mt-0.5 block text-[10px] font-normal text-ink-3">{column.metric} · {fmtInt(column.n)} câu</span></th>)}
        </tr></thead>
        {benchmark.groups.map((group) => {
          const table = experiment.tables[group.table];
          return <tbody key={group.label} className="border-b border-hair last:border-0">
            <tr className="bg-paper/60"><th scope="rowgroup" colSpan={columns.length + 1} className="px-4 py-1.5 text-left text-[11.5px] font-semibold text-ink">{group.label}</th></tr>
            {group.rows.map((ref) => {
              const row = table.rows.find((entry) => entry.id === ref.row)!;
              return <tr key={ref.row} className={`border-t border-hair/70 ${row.role === "candidate" ? "bg-paper/40" : ""}`}>
                <th scope="row" className={`px-4 py-2 text-left font-normal ${ROLE[row.role]}`}>{ref.label}</th>
                {columns.map((column) => {
                  const change = ref.changes[column.id] ? namedTest(experiment, ref.changes[column.id]) : null;
                  return <td key={column.id} className="whitespace-nowrap px-3 py-2 text-right align-top font-mono tabular-nums">
                    <Score cell={row.cells[column.id] ?? null} strong={row.role === "candidate"} />
                    {change ? <span className={`block text-[10px] ${tone(change, results.alpha) || "text-ink-3"}`}>{figures(change)}</span> : null}
                  </td>;
                })}
              </tr>;
            })}
          </tbody>;
        })}
      </table>
    </div>
    <p className="mt-2 max-w-5xl text-[11px] leading-relaxed text-ink-3">{benchmark.note}</p>
    <MethodSteps method={benchmark.method} />
  </section>;
}

/** The rules of Bảng 1's tried row, so "Sau" reads without opening its card: the rounds in order, then what the
 *  three rows share and what the loop costs. */
function MethodSteps({ method }: { method: RouterMethod }) {
  return <div className="mt-3 rounded-xl border border-hair bg-paper/60 px-4 py-3">
    <h4 className="text-[12.5px] font-semibold text-ink">{method.title}</h4>
    <ol className="mt-2 grid gap-x-6 gap-y-2.5 md:grid-cols-3">
      {method.steps.map((step, index) => <li key={step.title} className="flex gap-2.5">
        <span aria-hidden="true" className="mt-px flex size-5 shrink-0 items-center justify-center rounded-full border border-hair bg-card font-mono text-[10.5px] text-ink-2">{index + 1}</span>
        <span>
          <span className="block text-[12px] font-semibold text-ink">{step.title}</span>
          <span className="mt-0.5 block text-[11.5px] leading-relaxed text-ink-2">{step.text}</span>
        </span>
      </li>)}
    </ol>
    <p className="mt-2.5 text-[11px] leading-relaxed text-ink-3">{method.note}</p>
  </div>;
}

/** Bảng 2: every other experiment in a few lines. A line reads one column of one of its tables, so the numbers
 *  on a line share their items; two lines never do, and the caption says so. */
function OverviewTable({ results }: { results: RouterResults }) {
  const experiments = results.experiments.filter((experiment) => experiment.overview.length);
  const span = `${experiments[0].cards.split(", ")[0]} – ${experiments.at(-1)!.cards.split(", ").at(-1)}`;
  const cell = "px-3 py-2 align-top";
  const number = `${cell} whitespace-nowrap text-right font-mono tabular-nums`;
  return <section aria-labelledby="router-overview" className="mt-9">
    <h3 id="router-overview" className="font-disp text-[17px] font-semibold">Bảng 2 · Từng thí nghiệm ({span})</h3>
    <p className="mt-1 max-w-4xl text-[12px] leading-relaxed text-ink-2">Mỗi dòng đo trên một tập câu riêng: chỉ so các số trong cùng một dòng, không so giữa hai dòng. Model là Qwen3.5-9B, trừ dòng ghi tên model khác. Cột phép so sánh là phép thử đã đăng ký của thẻ đo; chữ mờ là so sánh phụ hoặc mô tả. Bấm mã thẻ đo để mở chi tiết.</p>
    <div className="mt-3 overflow-x-auto rounded-xl border border-hair bg-card">
      <table className="w-full min-w-[960px] border-collapse text-[12px]">
        <caption className="sr-only">Tóm tắt các thí nghiệm {span}, mỗi dòng một tập câu</caption>
        <thead><tr className="border-b border-hair bg-paper text-ink-2">
          <th scope="col" className="px-3 py-2.5 text-left font-semibold">Thẻ đo</th>
          <th scope="col" className="px-3 py-2.5 text-left font-semibold">Cách thử và tập câu</th>
          <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-semibold">Điểm</th>
          <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-semibold">Luôn B</th>
          <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-semibold">Luôn S</th>
          <th scope="col" className="px-3 py-2.5 text-left font-semibold">Mốc khác, cùng câu</th>
          <th scope="col" className="px-3 py-2.5 text-left font-semibold">Phép so sánh</th>
          <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-left font-semibold">Trạng thái</th>
        </tr></thead>
        {experiments.map((experiment) => <tbody key={experiment.id} className="border-b border-hair last:border-0">
          {experiment.overview.map((line, index) => {
            const table: RouterTable = experiment.tables[line.table];
            const column = table.columns.find((entry) => entry.id === line.column)!;
            const at = (row: string | null) => row === null ? null : overviewCell(experiment, line, row);
            return <tr key={`${line.table}:${line.column}:${line.tried.row}`} className={index ? "border-t border-hair/50" : ""}>
              {index === 0 ? <th scope="rowgroup" rowSpan={experiment.overview.length} className={`${cell} w-20 text-left font-mono text-[11px] font-normal`}><a href={`#router-${experiment.id}`} className="text-ink-2 underline underline-offset-2">{experiment.cards}</a></th> : null}
              <td className={`${cell} min-w-60`}>
                <span className="block font-medium text-ink">{line.tried.label}</span>
                <span className="mt-0.5 block text-[11px] leading-snug text-ink-3">{line.label} · {column.metric} · {fmtInt(column.n)} câu</span>
              </td>
              <td className={number}><Score cell={at(line.tried.row)} strong /></td>
              <td className={number}><Score cell={at(line.always_b)} /></td>
              <td className={number}><Score cell={at(line.always_s)} /></td>
              <td className={`${cell} text-[11px]`}>{line.others.length ? line.others.map((ref) => {
                const role = table.rows.find((entry) => entry.id === ref.row)!.role;
                return <span key={ref.row} className="block whitespace-nowrap"><span className={role === "ceiling" ? "italic text-ink-3" : "text-ink-3"}>{ref.label}</span> <span className="font-mono tabular-nums text-ink-2">{fmtNum(at(ref.row)!.score, 1)}</span></span>;
              }) : <span className="text-ink-3">—</span>}</td>
              <td className={`${cell} min-w-52 text-[11px]`}>{line.tests.length ? line.tests.map((ref) => {
                const test = namedTest(experiment, ref.test);
                return <span key={ref.test} className={`block ${test.primary ? "text-ink-2" : "text-ink-3"}`}>{ref.label}: <span className={`whitespace-nowrap font-mono tabular-nums ${tone(test, results.alpha)}`}>{figures(test)}</span></span>;
              }) : <span className="text-ink-3" aria-label="Không có phép thử trên dòng này">—</span>}</td>
              {index === 0 ? <td rowSpan={experiment.overview.length} className={cell}><StatusBadge status={experiment.status} /></td> : null}
            </tr>;
          })}
        </tbody>)}
      </table>
    </div>
  </section>;
}

function ResultTable({ table }: { table: RouterTable }) {
  return <figure className="mt-4">
    <figcaption className="mb-2 text-[12.5px] font-semibold text-ink-2">{table.title}</figcaption>
    <div className="overflow-x-auto rounded-xl border border-hair bg-card">
      <table className="w-full border-collapse text-[12px]" style={{ minWidth: 240 + table.columns.length * 112 }}>
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
                {cell.vs_b !== null ? <VersusB delta={cell.vs_b} /> : null}
                {cell.ci ? <span className="block text-[10px] text-ink-3">{fmtNum(cell.ci[0], 1)}–{fmtNum(cell.ci[1], 1)}</span> : null}
                {cell.tokens !== null ? <span className="block text-[10px] text-ink-3">{fmtInt(cell.tokens)} token</span> : null}
              </> : <span className="text-ink-3" aria-label="Không đo trong thí nghiệm này">—</span>}
            </td>;
          })}
        </tr>)}</tbody>
      </table>
    </div>
    {table.note ? <p className="mt-2 text-[11px] text-ink-3">{table.note}</p> : null}
    {table.rows.some((row) => Object.values(row.cells).some((cell) => cell.vs_b !== null))
      ? <p className="mt-1 text-[11px] text-ink-3">Số <span className="text-accept">xanh</span> / <span className="text-reject">đỏ</span> dưới điểm: hơn / kém dòng B của cùng model bao nhiêu điểm, trên cùng các câu. Đây là chênh lệch mô tả; phép thử nằm ở mục Phép so sánh.</p>
      : null}
  </figure>;
}

/** A detail cell's difference from its row's B: green ahead, red behind, grey when it rounds to zero. */
function VersusB({ delta }: { delta: number }) {
  const shown = fmtDelta(delta, 1);
  const zero = /^[-+]?0,0$/.test(shown);
  return <span className={`block text-[10.5px] ${zero ? "text-ink-3" : delta > 0 ? "text-accept" : "text-reject"}`}>
    {zero ? "0,0" : shown}<span className="sr-only"> điểm so với B</span>
  </span>;
}

/** One collapsed section: the mechanism in prose, then a student's counted funnel and worked examples. Native
 *  <details> keeps it keyboard- and screen-reader-accessible with no JavaScript, and starts closed. */
function Explainer({ explainer }: { explainer: RouterExplainer }) {
  return <details className="group mt-4 rounded-xl border border-hair bg-paper/60">
    <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-3 py-2.5 text-[12.5px] font-semibold text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
      <span aria-hidden="true" className="inline-block text-ink-3 transition-transform group-open:rotate-90">▸</span>
      {explainer.title}
    </summary>
    <div className="border-t border-hair/70 px-3 pb-3 pt-2.5">
      {explainer.paragraphs.map((paragraph) => <p key={paragraph} className="mt-1 text-[12px] leading-relaxed text-ink-2">{paragraph}</p>)}
      {explainer.groups.map((group) => <div key={group.title} className="mt-3.5">
        <h5 className="text-[12px] font-semibold text-ink">{group.title}</h5>
        <div className="mt-1.5 space-y-1">{group.facts.map((fact) => <div key={fact.label} className="flex items-baseline justify-between gap-4 text-[11.5px]">
          <span className="text-ink-3">{fact.label}</span>
          <span className="whitespace-nowrap font-mono tabular-nums text-ink-2">{fact.value}</span>
        </div>)}</div>
        {group.examples.map((example) => <figure key={example.item} className="mt-3 rounded-lg border border-hair bg-card px-3 py-2">
          <figcaption className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <span className="text-[11.5px] font-semibold text-ink">{example.verdict}</span>
            <span className="font-mono text-[10px] text-ink-3">{example.item}</span>
          </figcaption>
          <p className="mt-1 whitespace-pre-line text-[11.5px] leading-relaxed text-ink-2">{example.question}</p>
          <p className="mt-2 flex flex-wrap items-center gap-1.5">
            {example.answers.map((answer, index) => <span key={`${example.item}-${index}`}
              className={`rounded border px-1.5 py-0.5 font-mono text-[10.5px] ${answer === example.gold
                ? "border-accept/40 bg-accept-soft text-accept" : "border-hair bg-paper text-ink-2"}`}>
              S-r{index + 1} {answer}
            </span>)}
            <span aria-hidden="true" className="text-ink-3">→</span>
            <span className={`rounded border px-1.5 py-0.5 font-mono text-[10.5px] ${example.final === example.gold
              ? "border-accept/40 bg-accept-soft text-accept" : "border-reject/40 bg-reject-soft text-reject"}`}>
              chốt {example.final}
            </span>
            <span className="text-[10.5px] text-ink-3">đáp án đúng {example.gold}</span>
          </p>
          <p className="mt-1.5 font-mono text-[10px] text-ink-3">token ba lần: {example.tokens.join(" · ")}</p>
        </figure>)}
      </div>)}
      <p className="mt-3 text-[10.5px] leading-relaxed text-ink-3">{explainer.note}</p>
    </div>
  </details>;
}

/** One experiment, closed by default. The anchor sits inside the body, so following a link from Bảng 1 or 2 opens
 *  it in browsers that reveal closed <details> on fragment navigation; the named group keeps the chevron of a
 *  nested explainer from turning with this one. A page loaded with that link opens the card before React hydrates,
 *  so the browser-set `open` attribute is expected to differ from the server HTML. */
function ExperimentDetails({ experiment }: { experiment: RouterExperiment }) {
  return <details suppressHydrationWarning className="group/experiment rounded-xl border border-hair bg-card">
    <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 rounded-xl px-4 py-2.5 hover:bg-paper/60 [&::-webkit-details-marker]:hidden">
      <span aria-hidden="true" className="inline-block text-ink-3 transition-transform group-open/experiment:rotate-90">▸</span>
      <span className="font-mono text-[10.5px] text-ink-3">{experiment.cards}</span>
      <span className="font-disp text-[15px] font-semibold text-ink">{experiment.title}</span>
      <span className="ml-auto"><StatusBadge status={experiment.status} /></span>
    </summary>
    <div id={`router-${experiment.id}`} className="scroll-mt-16 border-t border-hair px-4 pb-4 pt-3 sm:px-5">
      <dl className="grid gap-x-6 gap-y-1.5 text-[12px] sm:grid-cols-[120px_minmax(0,1fr)]">
        <dt className="text-ink-3">Câu hỏi</dt><dd className="text-ink">{experiment.question}</dd>
        <dt className="text-ink-3">Model được hỏi</dt><dd className="text-ink-2">{experiment.student}</dd>
        <dt className="text-ink-3">Tập câu</dt><dd className="text-ink-2">{experiment.items}</dd>
      </dl>
      {experiment.tables.map((table) => <ResultTable key={table.title} table={table} />)}
      {experiment.explainers?.map((explainer) => <Explainer key={explainer.id} explainer={explainer} />)}
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
    </div>
  </details>;
}

/** The router and diagnosis experiments: two overview tables, then every experiment collapsed with its own tables. */
export function RouterResultsView({ results, error }: { results: RouterResults | null; error: string | null }) {
  if (!results) {
    return <p role="alert" className="rounded-xl border border-reject/40 bg-reject-soft p-4 text-[13px] text-reject">Không đọc được dữ liệu router: {error ?? "chưa có file data/router-results.json"}.</p>;
  }
  return <section aria-labelledby="router-title">
    <h2 id="router-title" className="font-disp text-[21px] font-semibold">Router và chẩn đoán (MC-90 – MC-105, MC-109)</h2>
    <p className="mt-1 max-w-4xl text-[12.5px] leading-relaxed text-ink-2">Các thí nghiệm tìm cách hỏi model tốt hơn cho từng câu, gom vào hai bảng: Bảng 1 là trước / sau trên đúng các bộ của /table, Bảng 2 cho mỗi thí nghiệm vài dòng, mỗi dòng một tập câu riêng. Bảng đầy đủ, phép so sánh, ghi chú và nguồn của từng thẻ đo nằm ở mục chi tiết cuối trang. Mọi con số lấy từ báo cáo phân tích đã đăng ký của từng thẻ đo.</p>
    <p className="mt-2 max-w-4xl text-[11.5px] leading-relaxed text-ink-3">B: hỏi thẳng · S: suy luận từng bước · Q: trích câu trong đoạn văn rồi đáp · K: kèm bằng chứng do BM25 tự tìm · O: kèm sẵn đúng bằng chứng, chỉ để đo trần. CI95 là khoảng tin cậy 95%; p dưới {fmtNum(results.alpha)} nghĩa là khác biệt khó xảy ra do may rủi. Ở Bảng 1 và 2, số xanh / đỏ là phép so sánh chính có p dưới {fmtNum(results.alpha)}, cách thử hơn / kém mốc; trong bảng chi tiết, số xanh / đỏ chỉ là hơn / kém dòng B. Chữ đậm là cách đang được thử.</p>
    <BenchmarkTable results={results} />
    <OverviewTable results={results} />
    <section aria-labelledby="router-details" className="mt-10">
      <h3 id="router-details" className="font-disp text-[17px] font-semibold">Chi tiết từng thí nghiệm</h3>
      <p className="mt-1 max-w-4xl text-[12px] leading-relaxed text-ink-2">Mỗi thẻ đo một mục, mặc định đóng: câu hỏi, bảng đầy đủ kèm chênh lệch so với B, CI95 và token, phép so sánh, kết luận, ghi chú và nguồn.</p>
      <div className="mt-3 space-y-2">{results.experiments.map((experiment) => <ExperimentDetails key={experiment.id} experiment={experiment} />)}</div>
    </section>
    <p className="mt-6 text-[10.5px] text-ink-3">Cập nhật từ artifact: {new Date(results.generated_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}. MC-99 (thử tín hiệu cho router ở bước thiết kế) chưa có trong trang này.</p>
  </section>;
}
