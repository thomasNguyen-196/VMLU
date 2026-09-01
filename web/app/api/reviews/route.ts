import { NextResponse } from "next/server";
import { listBuckets } from "@/lib/state.ts";
import { loadBlob } from "@/lib/blob.ts";

export const dynamic = "force-dynamic";

/** All (reviewer, model) buckets on disk with decided counts, so the pickers
 *  and the "đĩa" panel can show what exists without opening another profile.
 *  `total` comes from the active blob when it loads. */
export async function GET() {
  const buckets = await listBuckets();
  const total = await loadBlob().then((b) => b.items.length).catch(() => null);
  return NextResponse.json({ total, buckets });
}
