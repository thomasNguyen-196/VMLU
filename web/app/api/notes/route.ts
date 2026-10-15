import { NextRequest, NextResponse } from "next/server";
import { deleteModelNote, listModelNotes, saveModelNote } from "@/lib/db.ts";

export const dynamic = "force-dynamic";

// GET /api/notes?model=<id>&dataset=<id> — note của ĐÚNG dataset đó
// (không còn phạm vi chung; dataset rỗng trả []).
export async function GET(request: NextRequest) {
  try {
    const p = request.nextUrl.searchParams;
    const model = (p.get("model") ?? "").trim();
    if (!model) return NextResponse.json({ error: "cần tham số model" }, { status: 400 });
    const dataset = (p.get("dataset") ?? "").trim();
    const notes = await listModelNotes(model, dataset);
    const res = NextResponse.json({ notes });
    res.headers.set("Cache-Control", "no-store");
    return res;
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}

// PUT /api/notes {model, dataset, compare?, body, author} — thêm MỚI một note
// (một dataset có nhiều note; dataset bắt buộc non-empty).
export async function PUT(request: NextRequest) {
  try {
    const b = (await request.json()) as Record<string, unknown>;
    const model = typeof b.model === "string" ? b.model.trim() : "";
    const dataset = typeof b.dataset === "string" ? b.dataset.trim() : "";
    const compare = typeof b.compare === "string" ? b.compare.trim() : "";
    const body = typeof b.body === "string" ? b.body : "";
    const author = typeof b.author === "string" ? b.author.trim() : "";
    if (!model) return NextResponse.json({ error: "cần field model" }, { status: 400 });
    if (!dataset) return NextResponse.json({ error: "cần field dataset (không còn note chung)" }, { status: 400 });
    if (!body.trim()) return NextResponse.json({ error: "body rỗng" }, { status: 400 });
    if (!author) return NextResponse.json({ error: "cần field author (tên reviewer)" }, { status: 400 });
    const note = await saveModelNote(model, compare, dataset, body, author);
    const res = NextResponse.json({ note });
    res.headers.set("Cache-Control", "no-store");
    return res;
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}

// DELETE /api/notes?id=<note_id>&model=<id> — xóa một note của đúng model chủ.
export async function DELETE(request: NextRequest) {
  try {
    const p = request.nextUrl.searchParams;
    const id = (p.get("id") ?? "").trim();
    const model = (p.get("model") ?? "").trim();
    if (!id) return NextResponse.json({ error: "cần tham số id" }, { status: 400 });
    if (!model) return NextResponse.json({ error: "cần tham số model" }, { status: 400 });
    const deleted = await deleteModelNote(model, id);
    if (!deleted) return NextResponse.json({ error: "không tìm thấy note của model này" }, { status: 404 });
    const res = NextResponse.json({ deleted });
    res.headers.set("Cache-Control", "no-store");
    return res;
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
