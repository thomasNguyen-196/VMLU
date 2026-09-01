import { NextRequest, NextResponse } from "next/server";
import { checkEnvelope, loadBucket, saveBucket } from "@/lib/state.ts";
import { ident } from "@/lib/api-helpers.ts";
import { slug } from "@/lib/slug.ts";
import { SCHEMA_VERSION, type StateEnvelope } from "@/lib/types.ts";

export const dynamic = "force-dynamic"; // disk-backed reviewer state, never cache it

export async function GET(request: NextRequest) {
  const id = ident(request);
  if (!id) return NextResponse.json({ error: "cần tham số r (reviewer) và m (model)" }, { status: 400 });
  const { envelope, error } = await loadBucket(id.r, id.m);
  if (error) {
    // corrupt/foreign file on disk: report it — never serve it as empty truth
    return NextResponse.json({ error, reviewer: id.r, model: id.m }, { status: 409 });
  }
  if (!envelope) return NextResponse.json({ empty: true, reviewer: id.r, model: id.m });
  return NextResponse.json(envelope);
}

export async function POST(request: NextRequest) {
  const id = ident(request);
  if (!id) return NextResponse.json({ error: "cần tham số r (reviewer) và m (model)" }, { status: 400 });
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "body không phải JSON" }, { status: 400 });
  }
  const err = checkEnvelope(body);
  if (err) return NextResponse.json({ error: `envelope không hợp lệ: ${err}` }, { status: 400 });
  const env = body as StateEnvelope;
  if (env.schema_version !== SCHEMA_VERSION) {
    return NextResponse.json({ error: "schema_version sai" }, { status: 400 });
  }
  // stale-tab guard: a body whose identity differs from the query would
  // silently clobber another reviewer's/model's bucket — refuse instead.
  if (slug(env.annotator) !== slug(id.r) || slug(env.model) !== slug(id.m)) {
    return NextResponse.json(
      { error: `annotator/model trong body (${env.annotator}/${env.model}) khác r=${id.r}&m=${id.m} — tab cũ? tải lại trước khi lưu.` },
      { status: 409 },
    );
  }
  try {
    await saveBucket(env);
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
  return NextResponse.json({ ok: true, decided: Object.values(env.items).filter((v) => v?.d).length });
}
