import { NextResponse } from "next/server";
import { getDatasets } from "@/lib/db.ts";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const datasets = await getDatasets();
    const res = NextResponse.json({ datasets });
    res.headers.set("Cache-Control", "no-store");
    return res;
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
