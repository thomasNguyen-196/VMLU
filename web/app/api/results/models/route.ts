import { NextResponse } from "next/server";
import { getModels } from "@/lib/db.ts";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const models = await getModels();
    const res = NextResponse.json({ models });
    res.headers.set("Cache-Control", "no-store");
    return res;
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
