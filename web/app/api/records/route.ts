import { NextRequest, NextResponse } from "next/server";
import { bucketWithBlob, ident } from "@/lib/api-helpers.ts";
import { makeExportCsv } from "@/lib/export-csv.ts";
import { loadPeerDecisions, publishRecord } from "@/lib/records.ts";

export const dynamic = "force-dynamic";

/** Peer-review sync (the split-400 workflow).
 *  GET  ?r=&m=  -> { peers: {itemKey: {reviewer, decision}}, files: [...] } —
 *         every decision OTHER reviewers published in review_records/*.csv for
 *         this model, so the app can lock and mark those items at startup.
 *  POST ?r=&m=  -> publish the caller's saved bucket as its CSV into the shared
 *         folder (the same bytes /api/export returns). Commit + push the folder
 *         to hand work to the next reviewer. */
export async function GET(request: NextRequest) {
  const id = ident(request);
  if (!id) return NextResponse.json({ error: "cần tham số r (reviewer) và m (model)" }, { status: 400 });
  const { peers, files } = await loadPeerDecisions(id.m, id.r);
  return NextResponse.json({ peers, files }, { headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: NextRequest) {
  const id = ident(request);
  if (!id) return NextResponse.json({ error: "cần tham số r (reviewer) và m (model)" }, { status: 400 });
  const joined = await bucketWithBlob(id.r, id.m);
  if (!joined.ok) return NextResponse.json({ error: joined.error }, { status: joined.status });
  try {
    const file = await publishRecord(joined.envelope.annotator, joined.envelope.model, makeExportCsv(joined.blob, joined.envelope));
    return NextResponse.json({ ok: true, file, decided: Object.values(joined.envelope.items).filter((v) => v?.d).length });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
