"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Bucket, StateEnvelope } from "@/lib/types.ts";
import { SCHEMA_VERSION } from "@/lib/types.ts";
import { useReviewStore } from "@/lib/review-store.ts";
import type { PeerMap, RecordFileRow } from "@/lib/records.ts";
import { chooseBucketToAdopt } from "@/lib/review-logic.ts";

export type Save = "ok" | "dirty" | "bad";
export interface Banner {
  t: string;
  m: string;
  fix?: { l: string; fn: () => void };
}

const hhmm = (iso: string) =>
  new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

/** POST one envelope; pure over its args so callers keep a stable saveNow()
 *  (module-level function, no closure to churn in deps arrays). */
async function postState(
  a: string,
  m: string,
  items: Bucket,
): Promise<{ ok: true; savedAt: string } | { ok: false; error: string }> {
  const saved_at = new Date().toISOString();
  const env: StateEnvelope = { schema_version: SCHEMA_VERSION, annotator: a, model: m, saved_at, items };
  try {
    const res = await fetch(`/api/state?r=${encodeURIComponent(a)}&m=${encodeURIComponent(m)}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(env),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.error || `HTTP ${res.status}`);
    return { ok: true, savedAt: saved_at };
  } catch (e) {
    // never lose work: every change is already persisted to the session store,
    // which the boot mirror-check replays when disk is older/empty
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

/** Persistence + split-400 peer sync for the active (reviewer × model) bucket.
 *
 *  Owns the save/replay cluster: saveNow/commit (the SINGLE write path), the
 *  450 ms debounce (retry-bump flushes immediately), the disk-adoption effect
 *  (peer locks + localStorage-mirror replay, rule in review-logic) and the
 *  error banner. Invariants: decisions during the adoption window are rejected
 *  via bucketLoadingRef; the peer scan fails open (worst case duplicate
 *  review, never hidden progress). Declare AFTER the session-rehydration
 *  effect — React runs effects in declaration order, and adoption reads the
 *  store mirror, which must be hydrated first. */
export function useBucketSync(annotator: string | null, model: string) {
  const bucket = useReviewStore((s) => s.bucket); // debounced effect watches it
  const setBucket = useReviewStore((s) => s.setBucket);
  const [save, setSave] = useState<Save>("ok");
  const [savedLabel, setSavedLabel] = useState("đang mở…");
  const [banner, setBanner] = useState<Banner | null>(null);
  // peer locks from review_records/*.csv (split-400 sync): items other
  // reviewers already published — read-only here, striped in the filmstrip.
  const [peers, setPeers] = useState<PeerMap>({});
  const [peerFiles, setPeerFiles] = useState<RecordFileRow[]>([]);

  const dirtyRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // true while the (reviewer, model) bucket is being adopted from disk —
  // decisions in that window would sit in the stale bucket and vanish on adopt
  const bucketLoadingRef = useRef(false);
  const [saveNonce, setSaveNonce] = useState(0); // bump + retry flag: flush NOW (error-banner button)
  const retryNowRef = useRef(false);

  const saveNow = useCallback(async (a: string, m: string): Promise<boolean> => {
    const r = await postState(a, m, useReviewStore.getState().bucket);
    if (r.ok) {
      dirtyRef.current = false;
      setSave("ok");
      setSavedLabel("đã lưu " + hhmm(r.savedAt));
      setBanner(null);
      return true;
    }
    dirtyRef.current = true;
    setSave("bad");
    setSavedLabel("lỗi lưu");
    setBanner({
      t: "Máy chủ không nhận được state",
      m: `${r.error} — đã giữ bản sao trong localStorage của trình duyệt này.`,
      fix: {
        l: "Thử lưu ngay",
        fn: () => {
          retryNowRef.current = true;
          setSaveNonce((n) => n + 1);
        },
      },
    });
    return false;
  }, []);

  /** The single write path: mutate ref + mirror to React + mark dirty (which
   *  arms the debounce effect below). `save: false` is the load-injection case
   *  — adopting disk state must not round-trip it back. */
  const commit = useCallback((next: Bucket, opts: { save?: boolean; label?: string } = {}) => {
    setBucket(next);
    if (opts.save === false) {
      dirtyRef.current = false;
      setSave("ok");
      setSavedLabel(opts.label ?? "đồng bộ đĩa");
    } else {
      dirtyRef.current = true;
      setSave("dirty");
      setSavedLabel("chưa lưu…");
    }
  }, [setBucket]);

  // debounce every dirty change into a save (retry-bump flushes immediately)
  useEffect(() => {
    if (!annotator || !model || !dirtyRef.current) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    const delay = retryNowRef.current ? 0 : 450;
    retryNowRef.current = false;
    timerRef.current = setTimeout(() => {
      if (dirtyRef.current) void saveNow(annotator, model);
    }, delay);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [bucket, annotator, model, saveNonce, saveNow]);

  /** Flush a pending debounce before an identity switch or an export — a
   *  model switch clears the timer effect's deps, losing the last <450 ms of
   *  edits to the previous bucket. False return = save failed, caller keeps
   *  the old session's mirror. */
  const flushPending = useCallback(async (): Promise<boolean> => {
    if (!annotator || !model) return true;
    if (dirtyRef.current && timerRef.current) {
      clearTimeout(timerRef.current);
      return saveNow(annotator, model);
    }
    return true;
  }, [annotator, model, saveNow]);

  // load the bucket whenever the (reviewer, model) pair changes
  useEffect(() => {
    if (!annotator || !model) return;
    bucketLoadingRef.current = true;
    let alive = true;
    (async () => {
      // peer sync (the split-400 workflow): scan committed review_records/*.csv
      // so items a colleague already published are locked + marked from the
      // first render. Fail-open: if the scan errors, nobody is locked — the
      // worst case is duplicate review, never hidden progress.
      try {
        const res = await fetch(`/api/records?r=${encodeURIComponent(annotator)}&m=${encodeURIComponent(model)}`);
        if (res.ok) {
          const j = (await res.json()) as { peers?: PeerMap; files?: RecordFileRow[] };
          if (alive) {
            setPeers(j.peers ?? {});
            setPeerFiles(j.files ?? []);
          }
        } else if (alive) {
          setPeers({});
        }
      } catch {
        if (alive) setPeers({});
      }
      const label = (iso: string) => "đã lưu " + hhmm(iso);
      try {
        const res = await fetch(`/api/state?r=${encodeURIComponent(annotator)}&m=${encodeURIComponent(model)}`);
        const obj = (await res.json().catch(() => null)) as (StateEnvelope & { empty?: boolean; error?: string }) | null;
        if (!alive) return;
        if (res.status === 409) {
          bucketLoadingRef.current = false;
          commit({}, { save: false, label: "lỗi đĩa" });
          setBanner({
            t: "State trên đĩa không đọc được",
            m: `${obj?.error ?? "file hỏng"} — sửa file rồi tải lại, hoặc export CSV đã có.`,
          });
          return;
        }
        // local mirror = the persisted session store (written on every change):
        // when disk is empty/older, the client copy is replayed so work made
        // while the server was unreachable is never lost
        const st = useReviewStore.getState();
        const mirror: { items: Bucket; savedAt: string } | null =
          st.bucket && Object.keys(st.bucket).length > 0
            ? { items: st.bucket, savedAt: st.savedAt }
            : null;
        const diskItems = obj?.items && obj.schema_version === SCHEMA_VERSION ? obj.items : null;
        const choice = chooseBucketToAdopt(!!diskItems, !!obj?.empty, obj?.saved_at ?? null, mirror);
        bucketLoadingRef.current = false;
        if (choice === "mirror" && mirror) {
          commit(mirror.items, {
            label: diskItems ? "phục hồi localStorage (mới hơn đĩa)" : "phục hồi localStorage",
          });
        } else if (choice === "disk" && diskItems) {
          commit(diskItems, {
            save: false,
            label: obj?.saved_at ? label(obj.saved_at) : "đồng bộ đĩa",
          });
        } else {
          commit({}, { save: false, label: "chưa có thay đổi" });
        }
      } catch (e) {
        if (!alive) return;
        bucketLoadingRef.current = false;
        commit({}, { save: false, label: "mất kết nối" });
        setBanner({ t: "Không đọc được state", m: e instanceof Error ? e.message : String(e) });
      }
    })();
    return () => {
      alive = false;
    };
  }, [annotator, model, commit]);

  return { save, savedLabel, banner, setBanner, peers, peerFiles, bucketLoadingRef, commit, flushPending };
}
