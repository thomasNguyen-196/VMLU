"use client";

import { useState } from "react";
import type { BenchmarkComparison, ComparisonMode } from "@/lib/benchmark-comparison.ts";
import { fmtInt, fmtNum, fmtPct } from "@/lib/format.ts";

const COLORS: Record<ComparisonMode, string> = {
  "omp-no-tools": "var(--ink-2)",
  "omp-full-tools": "var(--squad)",
  "direct-default": "var(--drop)",
};
const deltaText = (value: number | null | undefined) => value == null ? "—" : `${value > 0 ? "+" : ""}${fmtNum(value)}`;

export default function BenchmarkComparisonSection({ comparison }: { comparison: BenchmarkComparison }) {
  const [datasetId, setDatasetId] = useState("vmlu-test");
  const [metric, setMetric] = useState("accuracy");
  const datasets = [...new Map(comparison.slices.map((slice) => [slice.datasetId, slice.dataset])).entries()];
  const activeDataset = datasets.some(([id]) => id === datasetId) ? datasetId : datasets[0]?.[0];
  const metrics = comparison.slices.filter((slice) => slice.datasetId === activeDataset);
  const slice = metrics.find((slice) => slice.metric === metric) ?? metrics[0];
  if (!slice) return null;

  return <section id="comparison" aria-labelledby="comparison-title" className="mb-9 scroll-mt-5 rounded-xl border border-hair bg-card p-4 sm:p-5">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-2xl">
        <h2 id="comparison-title" className="font-disp text-[21px] font-semibold">Tổng kết 3 chế độ chạy</h2>
        <p className="mt-1 text-[12px] leading-relaxed text-ink-2">Đặt điểm của cùng model cạnh nhau trên từng dataset. Chọn metric để xem biểu đồ và chênh lệch giữa ba bảng.</p>
      </div>
      <a href="#comparison-scores" className="rounded px-1 py-1 text-[11.5px] text-ink-2 underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2">Xem điểm & nguồn</a>
    </div>

    <div className="mt-5 flex flex-wrap gap-3">
      <label className="min-w-40 flex-1 text-[11px] text-ink-3 sm:flex-none" htmlFor="comparison-dataset">Dataset
        <select id="comparison-dataset" value={activeDataset} onChange={(event) => setDatasetId(event.target.value)} className="mt-1 block w-full rounded-lg border border-hair bg-paper px-3 py-2 text-[12px] text-ink focus-visible:outline-2 focus-visible:outline-offset-2">
          {datasets.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
      </label>
      <label className="min-w-40 flex-1 text-[11px] text-ink-3 sm:flex-none" htmlFor="comparison-metric">Metric
        <select id="comparison-metric" value={slice.metric} onChange={(event) => setMetric(event.target.value)} className="mt-1 block w-full rounded-lg border border-hair bg-paper px-3 py-2 text-[12px] text-ink focus-visible:outline-2 focus-visible:outline-offset-2">
          {metrics.map((entry) => <option key={entry.metric} value={entry.metric}>{entry.metricLabel}</option>)}
        </select>
      </label>
    </div>

    <p id="comparison-caveat" className="mt-4 border-l-2 border-hair pl-3 text-[11.5px] leading-relaxed text-ink-2">
      So sánh mô tả: route, system prompt, budget và timeout/recovery khác nhau. Chênh lệch chưa chứng minh tác động riêng của tools hoặc ý nghĩa thống kê. Không tính điểm trung bình gộp dataset.
    </p>

    <figure aria-labelledby="comparison-chart-title" aria-describedby="comparison-caveat" className="mt-6" aria-live="polite">
      <figcaption id="comparison-chart-title" className="text-[13px] font-semibold">{slice.dataset} · {slice.metricLabel} (%)</figcaption>
      <ul aria-label="Chú giải chế độ chạy" className="mt-2 flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-ink-2">
        {comparison.series.map((series) => <li key={series.id} className="flex items-center gap-1.5"><span aria-hidden="true" className="h-2 w-3 rounded-sm" style={{ backgroundColor: COLORS[series.id] }} />{series.label}</li>)}
      </ul>
      <div className="mb-1 mt-5 ml-[116px] mr-14 flex justify-between text-[10px] tabular-nums text-ink-3 sm:ml-[154px]" aria-hidden="true"><span>0</span><span>25</span><span>50</span><span>75</span><span>100%</span></div>
      <div className="divide-y divide-hair">
        {slice.rows.map((row) => <div key={row.id} className="py-3" data-comparison-model={row.id}>
          <h3 className="mb-2 text-[12px] font-semibold">{row.name}</h3>
          <div className="space-y-1.5">
            {comparison.series.map((series) => {
              const cell = row.cells[series.id];
              return <div key={series.id} className="grid grid-cols-[108px_minmax(0,1fr)_48px] items-center gap-2 sm:grid-cols-[146px_minmax(0,1fr)_48px]" title={cell ? `${cell.model} · ${cell.card} · n=${cell.n ?? "—"} · ${cell.provider}` : "Chưa có kết quả trong bảng này"}>
                <span className="text-[10px] text-ink-2 sm:text-[11px]">{series.label}</span>
                <div aria-hidden="true" className="relative h-3.5 overflow-hidden rounded-sm bg-paper" style={{ backgroundImage: "linear-gradient(to right, var(--hair) 1px, transparent 1px)", backgroundSize: "25% 100%" }}>
                  {cell ? <div className="relative h-full rounded-sm" style={{ width: `${cell.score}%`, backgroundColor: COLORS[series.id] }} /> : null}
                </div>
                <span className="text-right font-mono text-[11px] tabular-nums text-ink-2">{cell ? fmtPct(cell.score) : <span aria-label="Chưa có kết quả">—</span>}</span>
              </div>;
            })}
          </div>
        </div>)}
      </div>
    </figure>

    <div id="comparison-scores" className="mt-5 scroll-mt-5">
      <h3 className="text-[13px] font-semibold">Điểm, chênh lệch & nguồn</h3>
      <p className="mt-1 text-[11px] leading-relaxed text-ink-3">Δ = điểm của chế độ đó − OMP không tools, đơn vị điểm phần trăm (pp). Chỉ tính khi cùng dataset, metric, số câu và loại gold; đây chưa phải một phép so có kiểm soát.</p>
      <div className="mt-3 overflow-x-auto rounded-lg border border-hair">
        <table className="w-full min-w-[760px] border-collapse text-[11.5px]" data-comparison-scores>
          <caption className="sr-only">{slice.dataset} · {slice.metricLabel}: điểm và chênh lệch so với OMP không tools</caption>
          <thead className="bg-paper text-ink-2"><tr className="border-b border-hair">
            <th scope="col" className="sticky left-0 z-10 bg-paper px-3 py-3 text-left">Model</th>
            {comparison.series.map((series) => <th key={series.id} scope="col" className="px-3 py-3 text-right">{series.label}</th>)}
            <th scope="col" className="px-3 py-3 text-right">Δ full tools<br /><span className="text-[10px] font-normal">so với không tools</span></th>
            <th scope="col" className="px-3 py-3 text-right">Δ API trực tiếp<br /><span className="text-[10px] font-normal">so với không tools</span></th>
          </tr></thead>
          <tbody>{slice.rows.map((row) => <tr key={row.id} className="border-b border-hair last:border-0" data-comparison-row={row.id}>
            <th scope="row" className="sticky left-0 z-10 bg-card px-3 py-3 text-left font-medium">{row.name}</th>
            {comparison.series.map((series) => {
              const cell = row.cells[series.id];
              return <td key={series.id} className="px-3 py-3 text-right" title={cell ? `${cell.model} · ${cell.provider}\nNguồn: ${cell.source}` : "Chưa có kết quả trong bảng này"}>
                {cell ? <><span className="block font-mono tabular-nums">{fmtPct(cell.score)}</span><a href={`/table?condition=${series.id}#${slice.metric}`} className="mt-1 block text-[10px] text-ink-3 underline underline-offset-2">{cell.card}</a><span className="mt-0.5 block text-[10px] text-ink-3">n={fmtInt(cell.n)} · {cell.gold === "withheld" ? "server" : "local gold"}</span></> : <span className="text-ink-3" aria-label="Chưa có kết quả">—</span>}
              </td>;
            })}
            <td className="px-3 py-3 text-right font-mono tabular-nums">{deltaText(row.cells["omp-full-tools"]?.delta)}</td>
            <td className="px-3 py-3 text-right font-mono tabular-nums">{deltaText(row.cells["direct-default"]?.delta)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-ink-3">Dấu “—” là chưa có điểm hoặc chưa đủ dữ liệu tính Δ, không phải điểm 0. Legal MC full tools chưa có trong bảng hiện tại; MC-71 là lượt riêng. Qwen API trực tiếp ghi Q4_K_M; biến thể và route được giữ trong nguồn từng ô. VMLU Test dùng server grade, chưa có CI95 hoặc số câu đúng để suy ra từ điểm làm tròn.</p>
    </div>
  </section>;
}
