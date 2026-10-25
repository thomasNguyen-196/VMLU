import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import SiteNav from "@/components/SiteNav.tsx";
import type { VerifiedContrast } from "@/lib/diagnostic-review.ts";
import DiagnosticReviewApp, { type PilotRow } from "@/components/DiagnosticReviewApp.tsx";

export const dynamic = "force-dynamic";

const ROOT = path.resolve(process.cwd(), "..");
const PILOT_DIR = path.join(ROOT, "all_res", "diagnostic_v1", "pilot-review-v4");

async function loadPilot() {
  const [selectionBytes, pilotBytes, protocolBytes] = await Promise.all([
    readFile(path.join(PILOT_DIR, "selection.json")),
    readFile(path.join(PILOT_DIR, "pilot.jsonl")),
    readFile(path.join(ROOT, "data", "diagnostic_v1", "protocol.json")),
  ]);
  const selection = JSON.parse(selectionBytes.toString("utf8")) as Record<string, unknown>;
  const pilotSha = createHash("sha256").update(pilotBytes).digest("hex");
  const protocolSha = createHash("sha256").update(protocolBytes).digest("hex");
  if (selection.pilot_file_sha256 !== pilotSha) throw new Error("pilot.jsonl không khớp selection.json; hãy dựng lại pilot.");
  if (selection.protocol_sha256 !== protocolSha) throw new Error("Pilot được tạo theo protocol khác; hãy dựng lại pilot.");
  if (selection.review_schema_version !== "diagnostic-review-v4" || selection.annotation_revision !== 4) throw new Error("Pilot cần annotation revision 4.");
  const rows = pilotBytes.toString("utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as PilotRow);
  const secondKeys = selection.second_review_keys;
  if (rows.length !== 60 || new Set(rows.map((row) => row.observation_key)).size !== 60) throw new Error(`Pilot cần đúng 60 observation duy nhất; tìm thấy ${rows.length}.`);
  if (!Array.isArray(secondKeys) || secondKeys.length !== 15 || secondKeys.some((key) => !rows.some((row) => row.observation_key === key))) throw new Error("Danh sách review độc lập phải gồm đúng 15 observation thuộc pilot.");
  if (rows.some((row) => row.protocol_sha256 !== protocolSha || row.exposure !== "development-audit")) throw new Error("Protocol hoặc exposure của pilot không đồng nhất.");
  const previousRevisions = Array.isArray(selection.previous_revisions) ? selection.previous_revisions.map((value) => value as { annotation_revision: number; pilot_content_sha256: string; protocol_sha256: string }).filter((value) => [1, 2, 3].includes(value.annotation_revision)).map((value) => ({ revision: value.annotation_revision as 1 | 2 | 3, pilotSha: value.pilot_content_sha256, protocolSha: value.protocol_sha256 })) : [];
  const registry = JSON.parse("[]") as Array<Record<string, unknown>>;
  const contrastFile = (await readFile(path.join(PILOT_DIR, "contrasts.jsonl"))).toString("utf8");
  for (const line of contrastFile.split(/\r?\n/).filter(Boolean)) registry.push(JSON.parse(line));
  const verifiedContrasts: VerifiedContrast[] = [];
  for (const contrast of registry) {
    const artifact = path.resolve(PILOT_DIR, String(contrast.evidence_artifact ?? ""));
    const bytes = await readFile(artifact);
    if (!contrast.contrast_id || verifiedContrasts.some((value) => value.contrast_id === contrast.contrast_id)
      || contrast.pilot_content_sha256 !== selection.pilot_content_sha256
      || contrast.verified !== true || contrast.other_conditions_controlled !== true || contrast.supports_hypothesis !== true
      || !contrast.reviewer_id || !contrast.rationale || !contrast.baseline_condition_id || !contrast.intervention_condition_id
      || contrast.baseline_condition_id === contrast.intervention_condition_id
      || !["controlled_model_contrast", "deterministic_replay"].includes(String(contrast.kind))
      || !rows.some((row) => row.observation_key === contrast.observation_key)
      || createHash("sha256").update(bytes).digest("hex") !== contrast.evidence_artifact_sha256) throw new Error("Contrast registry chưa được xác minh hoặc hash không khớp.");
    verifiedContrasts.push({ contrast_id: String(contrast.contrast_id), observation_key: String(contrast.observation_key), label: String(contrast.label), kind: contrast.kind as VerifiedContrast["kind"] });
  }
  return { rows, verifiedContrasts, pilotSha: String(selection.pilot_content_sha256), protocolSha, selection, previousRevisions };
}

export default async function DiagnosticPage() {
  let pilot: Awaited<ReturnType<typeof loadPilot>> | null = null;
  let errorMessage = "";
  try {
    pilot = await loadPilot();
  } catch (error) {
    errorMessage = error instanceof Error ? error.message : String(error);
  }
  if (!pilot) return <><SiteNav /><main className="mx-auto max-w-3xl px-5 py-16"><p className="font-mono text-[11px] uppercase tracking-[.12em] text-flag">Diagnostic pilot chưa sẵn sàng</p><h1 className="mt-2 font-disp text-3xl font-semibold">Không tải được bộ review</h1><p className="mt-3 text-sm leading-6 text-ink-2">{errorMessage}</p><p className="mt-5 text-sm text-ink-2">Từ thư mục gốc repository, tạo revision review mới từ pilot đã khóa:</p><pre className="mt-3 overflow-auto rounded-xl border border-hair bg-card p-4 text-xs text-ink">{`.venv/bin/python code_benchmark/diagnostic.py revise-pilot-review --source-dir all_res/diagnostic_v1/pilot-review-v3 --output-dir all_res/diagnostic_v1/pilot-review-v4`}</pre></main></>;
  return <><SiteNav /><DiagnosticReviewApp {...pilot} /></>;
}
