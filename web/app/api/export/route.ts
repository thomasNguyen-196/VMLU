import { NextRequest, NextResponse } from "next/server";
import { bucketWithBlob, ident } from "@/lib/api-helpers.ts";
import { makeExportCsv } from "@/lib/export-csv.ts";
import { slug } from "@/lib/slug.ts";

export const dynamic = "force-dynamic";

/** The 9-column review CSV, generated server-side from the disk bucket —
 *  byte-compatible with `export_annotation_workbooks.py review`. The BOM that
 *  makeExportCsv prepends rides in the bytes so spreadsheets open Vietnamese. */
export async function GET(request: NextRequest) {
  const id = ident(request);
  if (!id) return NextResponse.json({ error: "cần tham số r (reviewer) và m (model)" }, { status: 400 });
  const joined = await bucketWithBlob(id.r, id.m);
  if (!joined.ok) return NextResponse.json({ error: joined.error }, { status: joined.status });
  const bytes = new TextEncoder().encode(makeExportCsv(joined.blob, joined.envelope));
  const name = `review_${slug(joined.envelope.annotator)}_${slug(joined.envelope.model)}.csv`;
  return new NextResponse(bytes, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${name}"`,
      "Cache-Control": "no-store",
    },
  });
}
