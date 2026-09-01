import type { NextRequest } from "next/server";
import { loadBlob } from "./blob.ts";
import { loadBucket } from "./state.ts";
import type { ReviewBlob, StateEnvelope } from "./types.ts";

/** Parse ?r=&m= — the identity every state/export route keys on. */
export function ident(request: NextRequest): { r: string; m: string } | null {
  const p = new URL(request.url).searchParams;
  const r = p.get("r");
  const m = p.get("m");
  return r && m ? { r, m } : null;
}

export type Joined =
  | { ok: true; blob: ReviewBlob; envelope: StateEnvelope }
  | { ok: false; status: number; error: string };

/** The saved bucket joined against the ACTIVE blob — the shape /api/export
 *  needs, and the same join the static exporter does client-side (spec:
 *  Mode equivalence). Fail statuses mirror the spec: 409 corrupt / wrong
 *  model, 404 no bucket, 500 missing blob. */
export async function bucketWithBlob(reviewer: string, model: string): Promise<Joined> {
  const blob = await loadBlob().catch(() => null);
  if (!blob) return { ok: false, status: 500, error: "blob missing — chạy `build_review_ui.py export-blob` trước" };
  const { envelope, error } = await loadBucket(reviewer, model);
  if (error) return { ok: false, status: 409, error };
  if (!envelope) return { ok: false, status: 404, error: `chưa có state đã lưu cho reviewer '${reviewer}' model '${model}'` };
  if (!blob.models.includes(envelope.model)) {
    return { ok: false, status: 409, error: `model '${envelope.model}' không có trong answers hiện tại (${blob.models.join(", ")})` };
  }
  return { ok: true, blob, envelope };
}
