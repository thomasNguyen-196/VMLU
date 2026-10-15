import { NextResponse, type NextRequest } from "next/server";
import { getRuns } from "@/lib/db.ts";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const p = new URL(request.url).searchParams;
    const runs = await getRuns(p.get("model") ?? undefined, p.get("dataset") ?? undefined);
    const res = NextResponse.json({ runs });
    res.headers.set("Cache-Control", "no-store");
    return res;
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
