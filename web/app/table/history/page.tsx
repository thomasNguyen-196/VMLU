import type { Metadata } from "next";
import { BenchmarkReportsPage } from "@/components/BenchmarkReportsPage.tsx";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Lịch sử benchmark · đầy đủ điều kiện", description: "Các run từ ngày đầu và harness ablations, kèm condition, điểm, nhận xét và caveat từng card." };
export default function HistoryPage() { return <BenchmarkReportsPage surface="history" />; }
