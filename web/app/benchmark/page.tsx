/** Merged /benchmark shell (change results-into-benchmark).
 *
 * Server component: loads the assembled view-model for ?model= (default
 * qwen3-5-9b-28k) and hands it to the client dashboard, which renders the
 * benchmark look with live Mongo numbers. Replaces the frozen
 * public/benchmark-data.json read path; /results redirects here.
 */
import { promises as fs } from "fs";
import path from "path";
import { getBenchmarkView } from "@/lib/benchmark-view.ts";
import { readHarnessBlock } from "@/lib/harness-block.ts";
import { indexHarnessContrasts, type HarnessContrastMap } from "@/lib/harness-contrast.ts";
import { BenchmarkShell } from "@/components/BenchmarkShell.tsx";

export const dynamic = "force-dynamic";

/** The frozen harness block, read here so each dataset tab can cross-link into
 *  it. FAIL-OPEN on purpose: a missing or invalid `.harness` block must not take
 *  /benchmark down with it — the tabs then render "chưa có arm omp cho cell
 *  này", which is true. /harness itself still fails loud on the same blob. */
async function loadHarnessContrasts(): Promise<HarnessContrastMap> {
  try {
    const file = path.join(process.cwd(), "public", "benchmark-data.json");
    const raw = await fs.readFile(file, "utf-8");
    return indexHarnessContrasts(readHarnessBlock(JSON.parse(raw)));
  } catch {
    return {};
  }
}

export default async function BenchmarkPage({
  searchParams,
}: {
  searchParams?: Promise<{ model?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const view = await getBenchmarkView(
    typeof params.model === "string" ? params.model : undefined,
  );
  const harness = await loadHarnessContrasts();
  return <BenchmarkShell view={view} harness={harness} />;
}
