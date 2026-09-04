"use client";

import { useCallback } from "react";
import { SCHEMA_VERSION, itemKey, type Bucket, type ReviewBlob, type StateEnvelope } from "@/lib/types.ts";
import { slug } from "@/lib/slug.ts";
import { useReviewStore } from "@/lib/review-store.ts";

/** The data-transfer cluster: CSV export (+ publish to review_records/),
 *  state JSON export, state JSON import. All three flush the pending autosave
 *  first where a save matters, and route errors to the banner/toast the same
 *  way ReviewApp did pre-extraction. */
export function useTransfer({
  annotator,
  model,
  blob,
  commit,
  toast,
  flushPending,
  setBanner,
}: {
  annotator: string | null;
  model: string;
  blob: ReviewBlob;
  commit: (next: Bucket, opts?: { save?: boolean; label?: string }) => void;
  toast: (m: string) => void;
  flushPending: () => Promise<boolean>;
  setBanner: (b: { t: string; m: string } | null) => void;
}) {
  const exportCsv = useCallback(async () => {
    if (!annotator) return;
    await flushPending();
    try {
      const res = await fetch(`/api/export?r=${encodeURIComponent(annotator)}&m=${encodeURIComponent(model)}`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.error || `HTTP ${res.status}`);
      const text = await res.text();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
      a.download = `review_${slug(annotator)}_${slug(model)}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
      // publish: same bytes land in review_records/ — git commit + push hands
      // the finished items to the next reviewer (the split-400 sync record).
      let pub = "";
      try {
        const pr = await fetch(`/api/records?r=${encodeURIComponent(annotator)}&m=${encodeURIComponent(model)}`, { method: "POST" });
        const pj = (await pr.json().catch(() => null)) as { ok?: boolean; file?: string; error?: string } | null;
        pub = pj?.ok ? ` · đã công bố ${pj.file} — nhớ git commit` : ` · ⚠ không công bố được (${pj?.error ?? "lỗi"})`;
      } catch (e) {
        pub = ` · ⚠ không công bố được (${e instanceof Error ? e.message : String(e)})`;
      }
      toast("Đã tải review CSV" + pub);
    } catch (e) {
      setBanner({ t: "Xuất CSV thất bại", m: e instanceof Error ? e.message : String(e) });
    }
  }, [annotator, model, flushPending, toast, setBanner]);

  const exportState = useCallback(() => {
    if (!annotator) return;
    const env: StateEnvelope = { schema_version: SCHEMA_VERSION, annotator, model, saved_at: new Date().toISOString(), items: useReviewStore.getState().bucket };
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(env)], { type: "application/json" }));
    a.download = `state_${slug(annotator)}_${slug(model)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }, [annotator, model]);

  const importState = useCallback(
    async (file: File) => {
      if (!annotator) return;
      let obj: Partial<StateEnvelope> | null = null;
      try {
        obj = JSON.parse(await file.text()) as Partial<StateEnvelope>;
      } catch {
        toast("File không phải JSON hợp lệ");
        return;
      }
      if (!obj || obj.schema_version !== SCHEMA_VERSION) {
        toast(`schema_version ${String(obj?.schema_version)} ≠ ${SCHEMA_VERSION} — không import`);
        return;
      }
      if (slug(obj.annotator ?? "") !== slug(annotator)) {
        toast(`State của '${obj.annotator}' ≠ bạn ('${annotator}') — giữ blind protocol`);
        return;
      }
      if (obj.model && obj.model !== model) {
        toast(`State của model '${obj.model}' ≠ model đang chọn — đổi model rồi import lại`);
        return;
      }
      const valid = new Set(blob.items.map(itemKey));
      const next = { ...useReviewStore.getState().bucket };
      let added = 0;
      for (const [k, v] of Object.entries(obj.items ?? {})) {
        if (!valid.has(k)) continue;
        if (next[k]?.d) continue; // never overwrite an existing decision
        if (!next[k] && v?.d) {
          next[k] = { d: v.d, c: v.c ?? "", n: v.n ?? "" };
          added++;
        }
      }
      commit(next);
      toast(`Đã import: +${added} quyết định`);
    },
    [annotator, model, blob.items, commit, toast],
  );

  return { exportCsv, exportState, importState };
}
