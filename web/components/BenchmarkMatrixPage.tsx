import Link from "next/link";
import SiteNav from "@/components/SiteNav.tsx";
import BenchmarkModelObservations from "@/components/BenchmarkModelObservations.tsx";
import type { BenchmarkMatrixView, MatrixGroup, MetricMatrix } from "@/lib/benchmark-matrix.ts";
import { columnMaximum, selectMatrixGroup } from "@/lib/benchmark-matrix.ts";
import type { BenchmarkRunSummary } from "@/lib/benchmark-reports.ts";
import { fmtInt, fmtNum, fmtPct } from "@/lib/format.ts";

function directModelDetail(group: MatrixGroup, modelId: string): string {
  const controls = group.conditions.find((condition) => condition.controls?.profile_id === modelId)?.controls;
  const reasoning = controls?.thinking ?? (group.id === "direct-default" ? "mặc định / chưa ghim effort" : "chưa ghi nhận");
  return `Temperature ${controls?.temperature_effective ?? controls?.temperature_requested ?? "chưa ghi nhận"} · reasoning ${reasoning}`;
}

function MetricTable({ group, matrix, confidence = false }: { group: MatrixGroup; matrix: MetricMatrix; confidence?: boolean }) {
  const id = `${confidence ? "ci-" : ""}${matrix.metric}`;
  const title = confidence ? `CI95 · ${matrix.title}` : matrix.title;
  return <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-5">
    <div className="mb-3 flex items-end justify-between gap-3"><div><h2 id={`${id}-title`} className="font-disp text-[20px] font-semibold">{title}</h2><p className="mt-0.5 text-[11.5px] text-ink-3">{confidence ? "Khoảng ước lượng 95% · đơn vị %" : "Model theo hàng · dataset theo cột · đơn vị %"}</p></div>{confidence ? null : <span className="text-[11px] text-ink-3">Điểm lớn nhất mỗi dataset được in đậm; đồng hạng cùng được in đậm</span>}</div>
    <div className="overflow-x-auto rounded-xl border border-hair bg-card">
      <table data-metric={id} className="w-full border-collapse text-[12px]" style={{ minWidth: 210 + matrix.columns.length * 140 }}>
        <caption className="sr-only">{title} · {group.label} · các model trên từng dataset</caption>
        <thead><tr className="border-b border-hair bg-paper text-ink-2"><th scope="col" className="sticky left-0 z-10 min-w-52 border-r border-hair bg-paper px-4 py-3 text-left font-semibold">Model</th>{matrix.columns.map((column) => <th key={column.id} scope="col" className="min-w-32 px-3 py-3 text-right font-semibold"><span className="block text-ink">{column.label}</span><span className="mt-1 block text-[10px] font-normal text-ink-3">{fmtInt(column.n)} câu · {column.gold === "withheld" ? "server" : "local gold"}</span><span className="block text-[10px] font-normal text-ink-3">{column.sourceLabel}</span></th>)}</tr></thead>
        <tbody>{group.models.map((model) => <tr key={model.id} className="border-b border-hair/70 last:border-0"><th scope="row" className="sticky left-0 z-10 border-r border-hair bg-card px-4 py-3 text-left font-medium"><span className="block">{model.name}</span><span className="mt-1 block text-[10px] font-normal text-ink-3">{group.kind === "direct" ? directModelDetail(group, model.id) : model.provider}</span></th>{matrix.columns.map((column) => {
          const cell = column.cells[model.id];
          const bounds = cell && cell.score.ci_low !== null && cell.score.ci_high !== null;
          const maximum = columnMaximum(column);
          const missing = !cell || (confidence && !bounds);
          const tooltip = !cell ? "Chưa có kết quả trong condition này" : confidence && !bounds ? "Nguồn chưa công bố CI95" : `${cell.condition.card} · ${column.sourceLabel} · n=${cell.score.n ?? "chưa công bố"}${cell.score.correct !== null ? ` · đúng ${cell.score.correct}` : ""}${group.kind === "direct" ? ` · budget ${cell.condition.fields.output_cap}` : ""}`;
          return <td key={column.id} title={tooltip} data-missing={missing ? "true" : undefined} className={`whitespace-nowrap px-3 py-3 text-right font-mono tabular-nums ${missing ? "text-ink-3" : !confidence && cell.score.score === maximum ? "font-semibold text-ink" : "text-ink-2"}`}>
            {!cell ? "—" : confidence ? bounds ? `${fmtNum(cell.score.ci_low)}–${fmtNum(cell.score.ci_high)}` : "—" : fmtPct(cell.score.score)}
          </td>;
        })}</tr>)}</tbody>
      </table>
    </div>
    <p data-table-comment={id} className="mt-3 max-w-5xl text-[13px] leading-7 text-ink-2">{confidence ? matrix.ciComment : matrix.comment}</p>
  </section>;
}

function ConditionDetails({ group, runSummaries }: { group: MatrixGroup; runSummaries: BenchmarkRunSummary[] }) {
  const fieldLabels = group.kind === "direct"
    ? [["Model", "identity"], ["Temperature", "temperature"], ["Reasoning", "thinking"], ["Output budget", "output_cap"], ["Seed", "seed"], ["Tools", "tools"], ["Workers", "workers"], ["Cách chấm", "gold"]]
    : [["Harness", "harness"], ["Provider / API", "provider"], ["Temperature", "temperature"], ["Thinking", "thinking"], ["Seed", "seed"], ["Tools", "tools"], ["Prompt", "prompt"], ["Context", "context"], ["History / session", "session"], ["Output cap", "output_cap"], ["Workers / timeout", "workers"], ["Timeout", "timeout"], ["Retry", "retry"], ["Gold", "gold"], ["Ngày chạy", "date"]];
  return <details className="mt-4 rounded-xl border border-hair bg-card px-4 py-3 text-[12px]">
    <summary className="cursor-pointer font-medium">Condition đầy đủ và nguồn từng run · {group.conditions.length} run</summary>
    <div className="mt-3 grid gap-3 xl:grid-cols-2">
      {group.conditions.map((condition) => {
        const summary = runSummaries.find((entry) => entry.id === condition.id);
        const serverDataset = summary?.datasets.find((dataset) => dataset.server_breakdown.length > 0);
        return <article key={condition.id} className="rounded-lg border border-hair p-3">
          <h3 className="font-semibold">{condition.model} · {condition.card}</h3>
          <dl className="mt-2 space-y-2 text-[11px] leading-relaxed">{fieldLabels.map(([label, key]) => <div key={key}><dt className="font-medium text-ink-2">{label}</dt><dd className="break-words text-ink-3">{condition.fields[key]}</dd></div>)}</dl>
          {serverDataset ? <details className="mt-3 rounded border border-hair px-2 py-1.5">
            <summary className="cursor-pointer font-medium">VMLU Test server breakdown · {serverDataset.server_breakdown.length} dòng</summary>
            <p className="mt-2 text-[10px] text-ink-3">Nguồn: {serverDataset.server_grade_source}. Server không cung cấp số câu đúng hoặc CI95.</p>
            <div className="mt-2 max-h-[360px] overflow-auto">
              <table className="w-full border-collapse text-[10.5px]">
                <thead className="sticky top-0 bg-paper"><tr><th scope="col" className="px-2 py-1 text-left">Category</th><th scope="col" className="px-2 py-1 text-left">Subject</th><th scope="col" className="px-2 py-1 text-right">Score</th></tr></thead>
                <tbody>{serverDataset.server_breakdown.map((grade) => <tr key={`${grade.category}:${grade.subject ?? "total"}`} className={`border-t border-hair/70 ${grade.subject === null ? "bg-paper font-semibold" : ""}`}>
                  <th scope="row" className="px-2 py-1 text-left">{grade.category}</th>
                  <td className="px-2 py-1">{grade.subject === null ? "Tổng nhóm" : grade.subject.split("_").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ")}</td>
                  <td className="px-2 py-1 text-right font-mono tabular-nums">{fmtPct(grade.score)}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </details> : null}
        </article>;
      })}
    </div>
  </details>;
}

export function BenchmarkMatrixPage({ view, requested }: { view: BenchmarkMatrixView; requested?: string }) {
  const group = selectMatrixGroup(view, requested);
  const observationGroup = group?.kind === "omp-no-tools" ? group : undefined;
  return <><SiteNav /><main className="mx-auto max-w-[1600px] px-4 py-7 sm:px-7"><header className="mb-6 flex flex-wrap items-start justify-between gap-3"><div><p className="font-mono text-[10.5px] text-ink-3">BENCHMARK TIẾNG VIỆT</p><h1 className="mt-1 font-disp text-[27px] font-semibold">So sánh model theo điều kiện đo</h1><p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">Mỗi metric có một bảng riêng. Chọn condition ở panel bên trái để đối chiếu cùng thiết lập.</p></div></header>
    {observationGroup ? <BenchmarkModelObservations group={observationGroup} /> : null}
    <div className="grid items-start gap-7 lg:grid-cols-[225px_minmax(0,1fr)]">
      <aside aria-label="Condition panel" className="rounded-xl border border-hair bg-paper p-3 lg:sticky lg:top-5"><h2 className="px-2 py-1 text-[12px] font-semibold">Điều kiện đo</h2><nav className="mt-2 space-y-2">{view.groups.map((entry) => <Link key={entry.id} href={`/table?condition=${entry.id}`} scroll={false} aria-current={group?.id === entry.id ? "page" : undefined} className={`block rounded-lg border px-3 py-3 ${group?.id === entry.id ? "border-hair bg-card text-ink" : "border-transparent text-ink-2 hover:bg-card"}`}><span className="block text-[12.5px] font-semibold">{entry.label}</span><span className="mt-1 block text-[10.5px] leading-relaxed text-ink-3">{entry.detail}</span></Link>)}</nav>
        {view.directReason ? <div data-direct-skipped className="mt-3 border-t border-hair px-2 pt-3"><p className="text-[12px] font-medium text-ink-2">API trực tiếp · tạm bỏ qua</p><p className="mt-1 text-[10.5px] leading-relaxed text-ink-3">Chưa xác minh được nhóm model có cùng thinking và output budget.</p></div> : null}
        {group ? <nav aria-label="Các bảng metric" className="mt-4 flex flex-wrap border-t border-hair pt-3 text-[11.5px] lg:block"><p className="mb-1 basis-full px-2 text-[10.5px] text-ink-3">BẢNG TRONG CONDITION</p>{group.matrices.map((matrix) => <a key={matrix.metric} href={`#${matrix.metric}`} className="inline-flex rounded px-2 py-1.5 text-ink-2 hover:bg-card lg:flex">{matrix.title}</a>)}<a href="#confidence" className="inline-flex rounded px-2 py-1.5 text-ink-2 hover:bg-card lg:flex">CI95</a><a href="#notes" className="inline-flex rounded px-2 py-1.5 text-ink-2 hover:bg-card lg:flex">Note & nguồn</a></nav> : null}
      </aside>
      <div className="min-w-0">{group ? <><section className="mb-7"><div className="flex flex-wrap items-center gap-2"><h2 className="font-disp text-[19px] font-semibold">{group.label}</h2><span className="rounded-full border border-hair bg-card px-2.5 py-1 text-[10.5px] text-ink-2">{group.detail}</span></div><p className="mt-2 text-[12px] leading-relaxed text-ink-3">{group.models.length} model · {group.matrices.length} metric · ô trống là chưa có kết quả trong condition này.</p><ConditionDetails group={group} runSummaries={view.runSummaries} /></section>
        <div className="space-y-9">{group.matrices.map((matrix) => <MetricTable key={matrix.metric} group={group} matrix={matrix} />)}</div>
        <section id="confidence" className="mt-10 scroll-mt-5 border-t border-hair pt-6"><p className="mb-5 text-[12px] leading-relaxed text-ink-3">CI95 được trình bày riêng cho từng metric. MC dùng Wilson; các bài đọc dùng bootstrap theo passage. CI95 của VMLU Test chưa được server công bố.</p><div className="space-y-9">{group.matrices.map((matrix) => <MetricTable key={matrix.metric} group={group} matrix={matrix} confidence />)}</div></section>
        <section id="notes" className="mt-10 scroll-mt-5 border-t border-hair pt-5"><h2 className="text-[16px] font-semibold">Note</h2><ul className="mt-2 list-disc space-y-2 pl-5 text-[12px] leading-relaxed text-ink-3">{group.notes.map((note) => <li key={note}>{note}</li>)}{view.directReason ? <li>{view.directReason}</li> : null}</ul><p className="mt-4 text-[10.5px] text-ink-3">Cập nhật từ artifact: {new Date(view.generatedAt).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}. <a href="/benchmark-condition-reports.csv" className="underline">CSV nguồn của toàn bộ run</a>.</p></section>
      </> : <p className="rounded-xl border border-hair bg-card p-5 text-[13px] text-ink-2">Chưa có nhóm ít nhất hai model được xác minh cùng condition.</p>}</div>
    </div>
  </main></>;
}
