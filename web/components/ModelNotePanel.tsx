"use client";

import { useCallback, useEffect, useState } from "react";

interface Note {
  _id: string;
  model_id: string;
  dataset_id: string;
  compare_model_id: string;
  body: string;
  author: string;
  created_at: string;
  updated_at: string;
}

function NoteCard({
  note,
  onDelete,
  deleting,
}: {
  note: Note;
  onDelete: () => Promise<void>;
  deleting: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-2.5 py-2">
      <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-700">{note.body}</p>
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <p className="font-mono text-[10px] text-slate-400">
          {note.author} · sửa {note.updated_at}
        </p>
        <button
          onClick={() => void onDelete()}
          disabled={deleting}
          className="rounded-lg border border-rose-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-rose-700 disabled:opacity-40"
        >
          {deleting ? "Đang xóa…" : "Xóa"}
        </button>
      </div>
    </div>
  );
}

/** Nhận xét thủ công trong phạm vi dataset hiện tại (nhiều note/dataset).
 *  Note chỉ hiện ở đúng dataset của nó — không có phạm vi chung. */
export function ModelNotePanel({ modelId, datasetId }: { modelId: string; datasetId: string }) {
  const [models, setModels] = useState<string[]>([]);
  const [compare, setCompare] = useState("");
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [body, setBody] = useState("");
  const [author, setAuthor] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/results/models")
      .then((r) => r.json())
      .then((j: { models?: Array<{ _id: string }> }) =>
        setModels((j.models ?? []).map((m) => m._id).filter((id) => id !== modelId)),
      )
      .catch(() => {});
  }, [modelId]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(
        `/api/notes?model=${encodeURIComponent(modelId)}&dataset=${encodeURIComponent(datasetId)}`,
      );
      const j = (await r.json()) as { notes?: Note[]; error?: string };
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      setNotes(j.notes ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [modelId, datasetId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(): Promise<void> {
    if (!body.trim() || !author.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      const r = await fetch("/api/notes", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelId, dataset: datasetId, compare, body, author: author.trim() }),
      });
      const j = (await r.json()) as { note?: Note; error?: string };
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      setBody("");
      setAdding(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string): Promise<void> {
    setDeletingId(id);
    setError(null);
    try {
      const r = await fetch(`/api/notes?id=${encodeURIComponent(id)}&model=${encodeURIComponent(modelId)}`, {
        method: "DELETE",
      });
      const j = (await r.json()) as { error?: string };
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingId(null);
    }
  }

  const scoped = notes.filter((n) => n.dataset_id === datasetId && n.compare_model_id === compare);

  return (
    <div className="mt-2.5 space-y-2.5 rounded-xl border border-emerald-100 bg-emerald-50/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-emerald-900">
          📝 Nhận xét model · dataset này ({scoped.length})
        </span>
        <select
          value={compare}
          onChange={(e) => setCompare(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-mono text-[11px]"
          title="Rỗng = nhận xét riêng của model; chọn model khác = nhận xét so sánh"
        >
          <option value="">riêng {modelId}</option>
          {models.map((m) => (
            <option key={m} value={m}>
              vs {m}
            </option>
          ))}
        </select>
        {!adding && (
          <button
            onClick={() => setAdding(true)}
            className="rounded-lg border border-emerald-200 bg-white px-2 py-1 text-[11px] font-semibold text-emerald-700"
          >
            + Thêm nhận xét
          </button>
        )}
      </div>

      {loading ? (
        <p className="text-xs text-slate-500">Đang tải nhận xét…</p>
      ) : error ? (
        <p className="text-xs text-red-600">nhận xét: {error}</p>
      ) : (
        <div className="space-y-2">
          {adding && (
            <div className="space-y-2 rounded-lg border border-emerald-200 bg-white p-2.5">
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={5}
                placeholder="Nhận xét…"
                className="w-full rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs leading-relaxed"
              />
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={author}
                  onChange={(e) => setAuthor(e.target.value)}
                  placeholder="Tên reviewer (bắt buộc)"
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs"
                />
                <button
                  onClick={() => void save()}
                  disabled={!body.trim() || !author.trim() || saving}
                  className="rounded-lg bg-emerald-600 px-3 py-1 text-xs font-semibold text-white disabled:opacity-40"
                >
                  {saving ? "Đang lưu…" : "Lưu"}
                </button>
                <button
                  onClick={() => {
                    setAdding(false);
                    setBody("");
                  }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600"
                >
                  Hủy
                </button>
              </div>
            </div>
          )}
          {scoped.length === 0 && !adding ? (
            <p className="text-xs text-slate-500">Chưa có nhận xét cho dataset này.</p>
          ) : (
            scoped.map((n) => (
              <NoteCard key={n._id} note={n} onDelete={() => remove(n._id)} deleting={deletingId === n._id} />
            ))
          )}
        </div>
      )}
    </div>
  );
}
