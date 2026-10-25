import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { DIAGNOSTIC_LABELS, OBSERVED_ISSUES } from "@/lib/diagnostic-taxonomy.ts";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const ROOT = path.resolve(process.cwd(), "..");
const PILOT_DIR = path.join(ROOT, "all_res", "diagnostic_v1", "pilot-review-v4");

/** Serve provisional suggestions only after the primary reviewer explicitly enters that scope. */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const expectedPilot = url.searchParams.get("pilot_sha");
  const expectedProtocol = url.searchParams.get("protocol_sha");
  if (!expectedPilot || !expectedProtocol) return NextResponse.json({ error: "Missing pilot identity." }, { status: 400 });
  try {
    const [selectionBytes, pilotBytes, protocolBytes, suggestionBytes, manifestBytes] = await Promise.all([
      readFile(path.join(PILOT_DIR, "selection.json")),
      readFile(path.join(PILOT_DIR, "pilot.jsonl")),
      readFile(path.join(ROOT, "data", "diagnostic_v1", "protocol.json")),
      readFile(path.join(PILOT_DIR, "assistant_suggestions.jsonl")),
      readFile(path.join(PILOT_DIR, "assistant-suggestions.json")),
    ]);
    const selection = JSON.parse(selectionBytes.toString("utf8")) as Record<string, unknown>;
    const manifest = JSON.parse(manifestBytes.toString("utf8")) as Record<string, unknown>;
    const pilotSha = String(selection.pilot_content_sha256 ?? "");
    const protocolSha = createHash("sha256").update(protocolBytes).digest("hex");
    if (expectedPilot !== pilotSha || expectedProtocol !== protocolSha || selection.review_schema_version !== "diagnostic-review-v4") {
      return NextResponse.json({ error: "Pilot revision does not match." }, { status: 409 });
    }
    if (selection.pilot_file_sha256 !== createHash("sha256").update(pilotBytes).digest("hex")) {
      return NextResponse.json({ error: "Pilot file identity check failed." }, { status: 409 });
    }
    if (manifest.schema_version !== "diagnostic-assistant-suggestion-v2" || manifest.status !== "complete"
      || manifest.pilot_content_sha256 !== pilotSha || manifest.protocol_sha256 !== protocolSha
      || manifest.file_sha256 !== createHash("sha256").update(suggestionBytes).digest("hex")) {
      return NextResponse.json({ error: "Assistant suggestion provenance check failed." }, { status: 409 });
    }
    const pilotRows = pilotBytes.toString("utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as { observation_key: string });
    const suggestions = suggestionBytes.toString("utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as { observation_key: string; proposal?: Record<string, unknown>; basis?: string; confidence?: string });
    const pilotKeys = new Set(pilotRows.map((row) => row.observation_key));
    if (pilotRows.length !== 60 || suggestions.length !== 60 || new Set(suggestions.map((row) => row.observation_key)).size !== 60
      || suggestions.some((row) => !pilotKeys.has(row.observation_key) || !row.proposal || !row.basis || !row.confidence)) {
      return NextResponse.json({ error: "Assistant suggestions do not cover the locked pilot." }, { status: 409 });
    }
    if (suggestions.some(({proposal: p}) => !p || ["reviewer_attestation", "blind_review_attestation", "review_status", "review_scope"].some((key) => key in p)
      || "evidence_level" in p || !Array.isArray(p.observed_issues) || !Array.isArray(p.diagnostic_labels) || !Array.isArray(p.diagnostic_support)
      || p.observed_issues.some((value) => !OBSERVED_ISSUES.some(([id]) => id === value))
      || p.diagnostic_labels.some((value) => !DIAGNOSTIC_LABELS.some(([id]) => id === value))
      || p.diagnostic_support.some((value) => !value || typeof value !== "object" || (value as {status?: string}).status !== "hypothesis"))) {
      return NextResponse.json({ error: "Provisional proposals must use the scoped revision-4 schema, without human signoff or controlled attribution." }, { status: 409 });
    }
    return NextResponse.json({ suggestions }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "Local diagnostic suggestions are not ready." }, { status: 503 });
  }
}
