import Link from "next/link";
import SiteNav from "@/components/SiteNav.tsx";
import { BenchmarkReport } from "@/components/BenchmarkReport.tsx";
import { loadBenchmarkReports, type ReportSurface } from "@/lib/benchmark-reports.ts";

const TITLES: Record<ReportSurface, string> = { v1: "Benchmark tiếng Việt · V1", v2: "VMLU V2 và full harness", history: "Lịch sử benchmark và điều kiện đo" };
export async function BenchmarkReportsPage({ surface }: { surface: ReportSurface }) {
  const data = await loadBenchmarkReports();
  const reports = data.reports.filter((report) => report.surface === surface);
  return <><SiteNav /><main className="mx-auto max-w-[1500px] px-5 py-8 sm:px-8"><header className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="font-disp text-[26px] font-semibold">{TITLES[surface]}</h1><p className="mt-1 max-w-4xl text-[12.5px] leading-relaxed text-ink-2">Condition → Benchmark → Comment → Note. Mỗi điểm đi cùng model, card, cấu hình và nguồn gold; nhận xét giữ đúng metric và phạm vi so sánh.</p></div></header>
    <nav aria-label="Các nhóm báo cáo" className="mt-4 flex flex-wrap gap-2 text-[12px]">{(["v1", "v2", "history"] as const).map((entry) => <Link key={entry} href={entry === "v1" ? "/table" : `/table/${entry}`} aria-current={entry === surface ? "page" : undefined} className={`rounded-lg border border-hair px-3 py-2 ${entry === surface ? "bg-card font-semibold" : "text-ink-2"}`}>{TITLES[entry]}</Link>)}<a href="/benchmark-condition-reports.csv" download className="rounded-lg border border-hair px-3 py-2 text-ink-2">CSV gồm cấu hình + điểm + nhận xét</a></nav>
    <p className="mt-3 text-[11px] text-ink-3">Báo cáo từ artifact đã lưu · cập nhật {new Date(data.generated_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}. Hạng chỉ hiện trong nhóm cấu hình danh nghĩa khớp; gap chưa phải ý nghĩa thống kê.</p>
    <nav aria-label="Mục lục condition" className="mt-4 flex flex-wrap gap-2 text-[11.5px]">{reports.map((report) => <a key={report.id} href={`#${report.id}`} className="rounded border border-hair px-2 py-1 text-ink-2">{report.title}</a>)}</nav>
    <div className="mt-6 space-y-8">{reports.map((report) => surface === "history" ? <details key={report.id} className="rounded-xl border border-hair bg-card p-4" open={report.id.startsWith("history-direct")}><summary className="cursor-pointer text-[14px] font-semibold">{report.title}</summary><BenchmarkReport report={report} data={data} /></details> : <BenchmarkReport key={report.id} report={report} data={data} />)}</div>
  </main></>;
}
