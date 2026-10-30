import type { Metadata } from "next";
import { BenchmarkMatrixPage, ROUTER_VIEW } from "@/components/BenchmarkMatrixPage.tsx";
import { buildBenchmarkMatrix } from "@/lib/benchmark-matrix.ts";
import { loadBenchmarkReports } from "@/lib/benchmark-reports.ts";
import { loadRouterResults, type RouterResults } from "@/lib/router-results.ts";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Bảng benchmark · model × dataset",
  description: "Bảng Accuracy, EM, F1 và CI95 riêng, theo condition OMP/no tools/temp 1/auto; API trực tiếp chỉ ghép khi cấu hình tương đương. Kèm các thí nghiệm router và chẩn đoán MC-90 – MC-103.",
};

/** The router view reads its own blob; a missing or invalid one shows the error in that view and leaves the others up. */
async function routerData(): Promise<{ results: RouterResults | null; error: string | null }> {
  try {
    return { results: await loadRouterResults(), error: null };
  } catch (error) {
    return { results: null, error: error instanceof Error ? error.message : String(error) };
  }
}

export default async function TablePage({ searchParams }: { searchParams?: Promise<{ condition?: string | string[] }> }) {
  const params = searchParams ? await searchParams : {};
  const requested = typeof params.condition === "string" ? params.condition : undefined;
  const view = buildBenchmarkMatrix(await loadBenchmarkReports());
  const router = requested === ROUTER_VIEW ? await routerData() : undefined;
  return <BenchmarkMatrixPage view={view} requested={requested} router={router} />;
}
