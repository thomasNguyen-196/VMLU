import type { Metadata } from "next";
import { BenchmarkMatrixPage } from "@/components/BenchmarkMatrixPage.tsx";
import { buildBenchmarkMatrix } from "@/lib/benchmark-matrix.ts";
import { loadBenchmarkReports } from "@/lib/benchmark-reports.ts";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Bảng benchmark · model × dataset",
  description: "Bảng Accuracy, EM, F1 và CI95 riêng, theo condition OMP/no tools/temp 1/auto; API trực tiếp chỉ ghép khi cấu hình tương đương.",
};
export default async function TablePage({ searchParams }: { searchParams?: Promise<{ condition?: string | string[] }> }) {
  const params = searchParams ? await searchParams : {};
  const requested = typeof params.condition === "string" ? params.condition : undefined;
  const view = buildBenchmarkMatrix(await loadBenchmarkReports());
  return <BenchmarkMatrixPage view={view} requested={requested} />;
}
