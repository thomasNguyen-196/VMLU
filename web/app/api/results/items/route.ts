import { NextResponse, type NextRequest } from "next/server";
import { getItem } from "@/lib/db.ts";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const p = new URL(request.url).searchParams;
  const run = p.get("run");
  const item = p.get("item");
  if (!run || !item)
    return NextResponse.json({ error: "missing ?run=<run_id>&item=<item_id>" }, { status: 400 });
  try {
    const found = await getItem(run, item);
    if (!found) return NextResponse.json({ error: `no item '${item}' in run '${run}'` }, { status: 404 });
    const res = NextResponse.json({ collection: found.collection, item: found.doc });
    res.headers.set("Cache-Control", "no-store");
    return res;
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
