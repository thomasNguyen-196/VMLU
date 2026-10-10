import type { BenchmarkReports, EvaluationReport, ReportScore } from "@/lib/benchmark-reports.ts";
import { ranksForScores } from "@/lib/benchmark-reports.ts";
import { fmtInt, fmtNum, fmtPct } from "@/lib/format.ts";

function ScoreTable({ report, rows, labels }: { report: EvaluationReport; rows: ReportScore[]; labels: BenchmarkReports["metric_labels"] }) {
  const conditions = new Map(report.conditions.map((condition) => [condition.id, condition]));
  const ranks = ranksForScores(report);
  const deltas = rows.some((score) => score.delta !== null);
  const sorted = [...rows].sort((a, b) => `${a.dataset_id}:${a.category}:${a.metric}`.localeCompare(`${b.dataset_id}:${b.category}:${b.metric}`));
  return <div className="overflow-x-auto rounded-xl border border-hair bg-card"><table className="w-full min-w-[1080px] border-collapse text-[11.5px]">
    <caption className="sr-only">{report.title}: điểm, mẫu số và confidence interval ở cột riêng.</caption>
    <thead className="bg-paper text-ink-2"><tr className="border-b border-hair">{["Dataset / category", "Model / card", "Metric", "n", "Correct", "Score", "CI95 lower", "CI95 upper", "Hạng cùng condition", "Truncation", ...(deltas ? ["Δ vs A (pp)", "Δ CI lower", "Δ CI upper"] : [])].map((label, index) => <th key={label} scope="col" className={`px-3 py-2.5 font-semibold ${index < 3 ? "text-left" : "text-right"}`}>{label}</th>)}</tr></thead>
    <tbody>{sorted.map((score) => {
      const condition = conditions.get(score.condition_id)!;
      return <tr key={JSON.stringify([score.condition_id, score.dataset_id, score.level, score.category, score.metric])} className="border-b border-hair/70 last:border-0">
        <th scope="row" className="px-3 py-2 text-left font-medium">{score.dataset}{score.category ? <span className="block font-normal text-ink-2">{score.category}</span> : null}</th>
        <td className="px-3 py-2">{condition.model}<span className="block text-[10px] text-ink-3">{condition.card}</span></td>
        <td className="px-3 py-2 text-ink-2">{labels[score.metric]}<span className="block text-[10px] text-ink-3">{score.gold === "withheld" ? "server · gold withheld" : score.gold === "none" ? "diagnostic" : score.gold}</span></td>
        <td className="px-3 py-2 text-right font-mono tabular-nums">{fmtInt(score.n)}</td><td className="px-3 py-2 text-right font-mono tabular-nums">{fmtInt(score.correct)}</td>
        <td className="px-3 py-2 text-right font-mono font-semibold tabular-nums">{fmtPct(score.score)}</td><td className="px-3 py-2 text-right font-mono tabular-nums">{fmtPct(score.ci_low)}</td><td className="px-3 py-2 text-right font-mono tabular-nums">{fmtPct(score.ci_high)}</td>
        <td className="px-3 py-2 text-right font-mono tabular-nums">{ranks.has(score) ? `#${ranks.get(score)}` : "—"}</td><td className="px-3 py-2 text-right font-mono tabular-nums">{fmtInt(score.truncated)}</td>
        {deltas ? <><td className="px-3 py-2 text-right font-mono tabular-nums">{fmtNum(score.delta)}</td><td className="px-3 py-2 text-right font-mono tabular-nums">{fmtNum(score.delta_ci_low)}</td><td className="px-3 py-2 text-right font-mono tabular-nums">{fmtNum(score.delta_ci_high)}</td></> : null}
      </tr>;
    })}</tbody>
  </table></div>;
}

export function BenchmarkReport({ report, data }: { report: EvaluationReport; data: BenchmarkReports }) {
  const fields = Object.keys(data.field_labels);
  const id = report.id;
  return <article id={id} className="scroll-mt-6 border-t border-hair pt-6">
    <header><h2 className="font-disp text-[20px] font-semibold">{report.title}</h2><p className="mt-1 text-[12px] leading-relaxed text-ink-2">{report.scope}</p></header>
    <section aria-labelledby={`${id}-condition`} className="mt-5"><h3 id={`${id}-condition`} className="mb-2 text-[15px] font-semibold">Condition</h3>
      <div className="overflow-x-auto rounded-xl border border-hair bg-card"><table className="w-full min-w-[760px] border-collapse text-[11.5px]">
        <caption className="sr-only">Cấu hình đầy đủ từng run của {report.title}</caption>
        <thead className="bg-paper"><tr className="border-b border-hair"><th scope="col" className="min-w-44 px-3 py-2 text-left font-semibold">Tham số</th>{report.conditions.map((condition) => <th key={condition.id} scope="col" className="min-w-64 px-3 py-2 text-left font-semibold">{condition.model}<span className="block text-[10px] font-normal text-ink-3">{condition.card}{condition.comparison_group ? " · cấu hình danh nghĩa khớp" : " · condition riêng"}</span></th>)}</tr></thead>
        <tbody>{fields.map((field) => <tr key={field} className="border-b border-hair/70 last:border-0"><th scope="row" className="px-3 py-2 text-left align-top font-medium text-ink-2">{data.field_labels[field]}</th>{report.conditions.map((condition) => <td key={condition.id} className="max-w-lg break-words px-3 py-2 align-top leading-relaxed">{condition.fields[field]}</td>)}</tr>)}</tbody>
      </table></div>
    </section>
    <section aria-labelledby={`${id}-benchmark`} className="mt-5"><h3 id={`${id}-benchmark`} className="mb-2 text-[15px] font-semibold">Benchmark</h3>
      <ScoreTable report={report} rows={report.benchmarks.filter((score) => score.level === "dataset")} labels={data.metric_labels} />
      <p className="mt-2 text-[11px] leading-relaxed text-ink-3">Truncation đếm phản hồi kết thúc do length, theo output cap ở Condition. Cap do benchmark đặt và có thể gồm reasoning token. Output cap của nhóm: {[...new Set(report.conditions.map((condition) => condition.fields.output_cap))].join(" / ")}.</p>
      {(["category", "subject"] as const).map((level) => { const rows = report.benchmarks.filter((score) => score.level === level);return rows.length ? <details key={level} className="mt-3" open={level === "category"}><summary className="cursor-pointer py-1 text-[12px] font-medium">{level === "category" ? "Category breakdown" : "Subject / stratum breakdown"} · {rows.length} dòng</summary><ScoreTable report={report} rows={rows} labels={data.metric_labels} /></details> : null; })}
    </section>
    <section aria-labelledby={`${id}-comment`} className="mt-5"><h3 id={`${id}-comment`} className="text-[15px] font-semibold">Comment</h3><ul className="mt-2 list-disc space-y-2 pl-5 text-[12px] leading-relaxed text-ink-2">{report.comments.map((comment, index) => <li key={index}>{comment}</li>)}</ul></section>
    <section aria-labelledby={`${id}-note`} className="mt-5"><h3 id={`${id}-note`} className="text-[15px] font-semibold">Note</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-[11.5px] leading-relaxed text-ink-3">{report.notes.map((note, index) => <li key={index}>{note}</li>)}</ul>
      <details className="mt-3 text-[11px] text-ink-3"><summary className="cursor-pointer">Artifact / measurement-card evidence</summary>{report.conditions.map((condition) => <div key={condition.id} className="mt-2 rounded-lg border border-hair p-3"><p className="font-medium">{condition.model} · {condition.card}</p><ul className="mt-1 space-y-1">{condition.sources.map((entry) => <li key={entry.path} className="break-all">{entry.label}: <code>{entry.path}</code></li>)}</ul>{condition.manifest_sha256 ? <p className="mt-1 break-all">Manifest SHA: <code>{condition.manifest_sha256}</code></p> : null}{Object.entries(condition.fields).filter(([key]) => key.startsWith("recorded:")).map(([key, value]) => <p key={key} className="mt-1 leading-relaxed">{key}: {value}</p>)}</div>)}</details>
    </section>
  </article>;
}
