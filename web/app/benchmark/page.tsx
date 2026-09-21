/** Merged /benchmark shell (change results-into-benchmark).
 *
 * Server component: loads the assembled view-model for ?model= (default
 * qwen3-5-9b-28k) and hands it to the client dashboard, which renders the
 * benchmark look with live Mongo numbers. Replaces the frozen
 * public/benchmark-data.json read path; /results redirects here.
 */
import { getBenchmarkView } from "@/lib/benchmark-view.ts";
import { BenchmarkShell } from "@/components/BenchmarkShell.tsx";

export const dynamic = "force-dynamic";

export default async function BenchmarkPage({
  searchParams,
}: {
  searchParams?: Promise<{ model?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const view = await getBenchmarkView(
    typeof params.model === "string" ? params.model : undefined,
  );
  return <BenchmarkShell view={view} />;
}
