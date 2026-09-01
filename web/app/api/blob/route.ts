import { NextResponse } from "next/server";
import { loadBlob } from "@/lib/blob.ts";

// The blob is file-backed and must reflect a re-run of `export-blob` without a
// server restart.
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(await loadBlob());
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
