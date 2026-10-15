import { NextResponse, type NextRequest } from "next/server";
import { getSummary } from "@/lib/db.ts";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const run = new URL(request.url).searchParams.get("run");
  if (!run) return NextResponse.json({ error: "missing ?run=<run_id>" }, { status: 400 });
  try {
    const summary = await getSummary(run);
    if (!summary) return NextResponse.json({ error: `no summary for run '${run}'` }, { status: 404 });
    const res = NextResponse.json({ summary });
    res.headers.set("Cache-Control", "no-store");
    return res;
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
