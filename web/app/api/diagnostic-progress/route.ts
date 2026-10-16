import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { loadDiagnosticProgress, saveDiagnosticProgress, ProgressError, type ProgressIdentity } from "@/lib/diagnostic-progress-server.ts";

export const dynamic = "force-dynamic";
async function context(request: Request) {
  const q = new URL(request.url).searchParams;
  const id = { reviewer: q.get("reviewer")?.trim() ?? "", scope: q.get("scope"), pilotSha: q.get("pilot_sha"), protocolSha: q.get("protocol_sha") };
  if (!id.reviewer || id.reviewer.length > 120 || !["primary-60", "independent-15"].includes(id.scope ?? "") || !/^[a-f0-9]{64}$/.test(id.pilotSha ?? "") || !/^[a-f0-9]{64}$/.test(id.protocolSha ?? "")) throw new ProgressError("Reviewer/scope/pilot không hợp lệ.", 400);
  const root = path.resolve(process.cwd(), ".."), dir = path.join(root,"all_res/diagnostic_v1/pilot-review-v4");
  const [selectionBytes, pilotBytes, protocolBytes] = await Promise.all([readFile(path.join(dir,"selection.json")),readFile(path.join(dir,"pilot.jsonl")),readFile(path.join(root,"data/diagnostic_v1/protocol.json"))]);
  const selection = JSON.parse(selectionBytes.toString());
  if (selection.review_schema_version !== "diagnostic-review-v4" || selection.pilot_content_sha256 !== id.pilotSha || selection.protocol_sha256 !== id.protocolSha || createHash("sha256").update(protocolBytes).digest("hex") !== id.protocolSha || createHash("sha256").update(pilotBytes).digest("hex") !== selection.pilot_file_sha256) throw new ProgressError("Pilot/protocol đã thay đổi; tải lại trang.");
  const rows = pilotBytes.toString().trim().split(/\r?\n/).map(line=>JSON.parse(line));
  const allowed = id.scope === "independent-15" ? selection.second_review_keys : rows.map(row=>row.observation_key);
  return { id: id as ProgressIdentity, keys: new Set<string>(allowed) };
}
function failure(error: unknown) { return NextResponse.json({error:error instanceof ProgressError ? error.message : "Không đọc/lưu được tiến độ server; bản lưu trên trình duyệt được giữ nguyên."},{status:error instanceof ProgressError ? error.status : 500}); }
export async function GET(request: Request) {
  try { const {id,keys}=await context(request); return NextResponse.json({record:await loadDiagnosticProgress(id,keys)},{headers:{"Cache-Control":"no-store"}}); }
  catch(error){return failure(error);}
}
export async function POST(request: Request) {
  // This is a loopback-only, self-identified reviewer app, not authentication.
  const origin=request.headers.get("origin");
  if (origin && origin!==new URL(request.url).origin && new URL(origin).host!==request.headers.get("host")) return NextResponse.json({error:"Origin không hợp lệ."},{status:403});
  try {
    const {id,keys}=await context(request);
    const raw=await request.text(); if(raw.length>2_000_000) throw new ProgressError("Tiến độ quá lớn.",413);
    let body;try{body=JSON.parse(raw);}catch{throw new ProgressError("JSON không hợp lệ.",400);}
    const record=await saveDiagnosticProgress(id,keys,body.draft,body.expectedRevision);
    return NextResponse.json({record},{headers:{"Cache-Control":"no-store"}});
  } catch(error){return failure(error);}
}
