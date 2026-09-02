"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ItemState, ReviewBlob, StateEnvelope } from "@/lib/types.ts";
import { SCHEMA_VERSION, itemKey } from "@/lib/types.ts";
import { slug } from "@/lib/slug.ts";
import { useReviewStore } from "@/lib/review-store.ts";
import type { PeerMap, RecordFileRow } from "@/lib/records.ts";
import { computeStats, nextUnreviewed, passageGroups, passagePosition } from "@/lib/review-logic.ts";
import { Filmstrip } from "./Filmstrip.tsx";
import { ItemPane } from "./ItemPane.tsx";
import { DecisionPanel } from "./DecisionPanel.tsx";
import { NavDock } from "./NavDock.tsx";

/** Legacy pre-zustand identity key — read once at boot to migrate returning
 *  reviewers into the persisted session store. */
const LS_ANNO = "vmlu.review.annotator";

type Save = "ok" | "dirty" | "bad";

const hhmm = (iso: string) =>
  new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

/** POST one envelope; pure over its args so the component keeps a stable
 *  saveNow() (module-level function, no closure to churn in deps arrays). */
async function postState(
  a: string,
  m: string,
  items: Record<string, ItemState>,
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

/** The review tool. Owns: identity gate, the active (reviewer × model)
 *  bucket, debounced autosave to /api/state (with a localStorage mirror so a
 *  dead server never costs work), navigation, and the keyboard protocol. */
export function ReviewApp({ blob }: { blob: ReviewBlob }) {
  const annotator = useReviewStore((s) => s.annotator); // null = gate open
  const model = useReviewStore((s) => s.model);
  const idx = useReviewStore((s) => s.idx);
  const bucket = useReviewStore((s) => s.bucket);
  const setAnnotator = useReviewStore((s) => s.setAnnotator);
  const setModel = useReviewStore((s) => s.setModel);
  const setIdx = useReviewStore((s) => s.setIdx);
  const setBucket = useReviewStore((s) => s.setBucket);
  const [save, setSave] = useState<Save>("ok");
  const [savedLabel, setSavedLabel] = useState("đang mở…");
  const [banner, setBanner] = useState<{ t: string; m: string; fix?: { l: string; fn: () => void } } | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [help, setHelp] = useState(false);
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

  const groups = useMemo(() => passageGroups(blob.items), [blob.items]);
  const stats = useMemo(() => computeStats(blob.items, bucket), [blob.items, bucket]);
  const item = blob.items[idx];

  const toast2 = useCallback((m: string) => {
    setToastMsg(m);
    setTimeout(() => setToastMsg((cur) => (cur === m ? null : cur)), 2400);
  }, []);

  // resume the persisted session once, after mount: SSR renders defaults so
  // the server HTML matches, then the store fills in on the client
  useEffect(() => {
    let alive = true;
    void (async () => {
      const p = useReviewStore.persist.rehydrate();
      if (p) await p;
      if (!alive) return;
      const s = useReviewStore.getState();
      if (!s.annotator) {
        try {
          const legacy = localStorage.getItem(LS_ANNO);
          if (legacy) s.setAnnotator(legacy);
        } catch {
          /* private mode */
        }
      }
      if (s.idx > blob.items.length - 1) s.setIdx(blob.items.length - 1);
      if (!s.model || !blob.models.includes(s.model)) {
        if (blob.models[0]) s.setModel(blob.models[0]);
      }
    })();
    return () => {
      alive = false;
    };
  }, [blob.models, blob.items.length]);

  /* ---------------- persistence ---------------- */
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
  const commit = useCallback((next: Record<string, ItemState>, opts: { save?: boolean; label?: string } = {}) => {
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
        const mirror: { items: Record<string, ItemState>; savedAt: string } | null =
          st.bucket && Object.keys(st.bucket).length > 0
            ? { items: st.bucket, savedAt: st.savedAt }
            : null;
        if (obj?.empty) {
          if (mirror) {
            // a copy saved while the server was unreachable: replay it
            bucketLoadingRef.current = false;
            commit(mirror.items, { label: "phục hồi localStorage" });
          } else {
            bucketLoadingRef.current = false;
            commit({}, { save: false, label: "chưa có thay đổi" });
          }
          return;
        }
        if (obj?.items && obj.schema_version === SCHEMA_VERSION) {
          const diskNewer = !(mirror?.savedAt && obj.saved_at && mirror.savedAt > obj.saved_at);
          if (!diskNewer && mirror) {
            bucketLoadingRef.current = false;
            commit(mirror.items, { label: "phục hồi localStorage (mới hơn đĩa)" });
          } else {
            bucketLoadingRef.current = false;
            commit(obj.items, { save: false, label: obj.saved_at ? label(obj.saved_at) : "đồng bộ đĩa" });
          }
          return;
        }
        bucketLoadingRef.current = false;
        commit({}, { save: false, label: "chưa có thay đổi" });
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

  /* ---------------- mutations ---------------- */
  const peerLock = item ? peers[itemKey(item)] : undefined;
  const setDecision = useCallback(
    (d: "accept" | "reject" | "clear") => {
      const k = itemKey(blob.items[idx]);
      if (bucketLoadingRef.current) return; // bucket being adopted — a write here would vanish
      if (peers[k]) {
        toast2(`Câu này ${peers[k].reviewer} đã chốt (${peers[k].decision}) — bỏ qua`);
        return;
      }
      const bk = useReviewStore.getState().bucket;
      const cur = bk[k] ?? { d: null, c: "", n: "" };
      const nd: ItemState["d"] = d === "clear" ? null : cur.d === d ? null : d;
      commit({ ...bk, [k]: { ...cur, d: nd } });
      if (nd === "reject" && !cur.c.trim()) {
        requestAnimationFrame(() => document.getElementById("corr")?.focus());
      }
    },
    [blob.items, idx, commit, peers, toast2],
  );

  const setField = useCallback(
    (which: "c" | "n") => (v: string) => {
      const k = itemKey(blob.items[idx]);
      if (bucketLoadingRef.current) return; // same adopt window as setDecision
      if (peers[k]) return;
      const bk = useReviewStore.getState().bucket;
      const cur = bk[k] ?? { d: null, c: "", n: "" };
      commit({ ...bk, [k]: { ...cur, [which]: v } });
    },
    [blob.items, idx, commit, peers],
  );

  /* ---------------- navigation ---------------- */
  const go = useCallback(
    (i: number) => {
      const cur = useReviewStore.getState().idx;
      const n = Math.max(0, Math.min(blob.items.length - 1, i));
      if (n !== cur) {
        window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        setIdx(n);
      }
    },
    [blob.items.length, setIdx],
  );

  /** Jump by 1-based question number (same numbering as the filmstrip). */
  const jumpToNumber = useCallback(
    (n: number) => {
      if (!Number.isFinite(n)) {
        toast2(`Nhập số câu hợp lệ (1–${blob.items.length})`);
        return;
      }
      if (n < 1 || n > blob.items.length) {
        toast2(`Câu ${n} ngoài phạm vi — bộ có ${blob.items.length} câu`);
        return;
      }
      go(n - 1);
    },
    [blob.items.length, go, toast2],
  );

  const jumpUnreviewed = useCallback(() => {
    const i = nextUnreviewed(blob.items, useReviewStore.getState().bucket, idx, peers);
    if (i === null) toast2("Hết! Mọi câu đã có quyết định 🎉");
    else {
      go(i);
      if (i !== (idx + 1) % blob.items.length) toast2(`câu ${i + 1} chưa review`);
    }
  }, [blob.items, idx, go, toast2, peers]);

  const pickModel = useCallback(
    async (m: string) => {
      if (!m || m === model || !annotator) return;
      // flush a pending debounce now: model switch clears the timer effect deps,
      // losing the last <450ms of edits to the previous model's bucket
      if (dirtyRef.current && timerRef.current) {
        clearTimeout(timerRef.current);
        const ok = await saveNow(annotator, model);
        if (!ok) return; // unreachable server — keep the old session's mirror
      }
      setModel(m); // store action: also resets idx to 0
      setBucket({}); // the store persists only the active session
    },
    [model, annotator, saveNow, setModel, setBucket],
  );

  const submitReviewer = useCallback(
    (v: string) => {
      const name = v.trim();
      if (!name) return;
      setAnnotator(name); // persisted — the session resumes on the next visit
    },
    [setAnnotator],
  );

  /* ---------------- export / import ---------------- */
  const exportCsv = useCallback(async () => {
    if (!annotator) return;
    if (dirtyRef.current && timerRef.current) {
      clearTimeout(timerRef.current);
      await saveNow(annotator, model);
    }
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
      toast2("Đã tải review CSV" + pub);
    } catch (e) {
      setBanner({ t: "Xuất CSV thất bại", m: e instanceof Error ? e.message : String(e) });
    }
  }, [annotator, model, saveNow, toast2]);

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
        toast2("File không phải JSON hợp lệ");
        return;
      }
      if (!obj || obj.schema_version !== SCHEMA_VERSION) {
        toast2(`schema_version ${String(obj?.schema_version)} ≠ ${SCHEMA_VERSION} — không import`);
        return;
      }
      if (slug(obj.annotator ?? "") !== slug(annotator)) {
        toast2(`State của '${obj.annotator}' ≠ bạn ('${annotator}') — giữ blind protocol`);
        return;
      }
      if (obj.model && obj.model !== model) {
        toast2(`State của model '${obj.model}' ≠ model đang chọn — đổi model rồi import lại`);
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
      toast2(`Đã import: +${added} quyết định`);
    },
    [annotator, model, blob.items, commit, toast2],
  );

  /* ---------------- keyboard ---------------- */
  useEffect(() => {
    if (!annotator) return; // gate open: keys belong to the form
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        (document.activeElement as HTMLElement | null)?.blur();
        setHelp(false);
        return;
      }
      if (/^(TEXTAREA|INPUT|SELECT)$/.test(String(document.activeElement?.tagName))) return;
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      switch (ev.key) {
        case "j": case "ArrowDown": go(idx + 1); ev.preventDefault(); break;
        case "k": case "ArrowUp": go(idx - 1); ev.preventDefault(); break;
        case "a": case " ": setDecision("accept"); ev.preventDefault(); break;
        case "r": setDecision("reject"); ev.preventDefault(); break;
        case "u": setDecision("clear"); ev.preventDefault(); break;
        case "e": document.getElementById("corr")?.focus(); ev.preventDefault(); break;
        case "n": document.getElementById("note")?.focus(); ev.preventDefault(); break;
        case "g": document.getElementById("goto")?.focus(); ev.preventDefault(); break;
        case "t": jumpUnreviewed(); ev.preventDefault(); break;
        case "Home": go(0); ev.preventDefault(); break;
        case "End": go(blob.items.length - 1); ev.preventDefault(); break;
        case "?": setHelp((h) => !h); ev.preventDefault(); break;
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [annotator, idx, go, setDecision, jumpUnreviewed, blob.items.length]);

  const pos = passagePosition(groups, idx);
  const curState = item ? bucket[itemKey(item)] : undefined;
  const answer = item ? (item.answers[model] ?? null) : null;

  const pill = (
    <span className={"flex items-center gap-1.5 whitespace-nowrap text-[12px] " + (save === "bad" ? "text-reject" : "text-ink-2")}>
      <span aria-hidden className={"h-[7px] w-[7px] shrink-0 rounded-full " + (save === "ok" ? "bg-accept" : save === "dirty" ? "bg-flag" : "bg-reject")} />
      {savedLabel}
    </span>
  );

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-hair bg-paper/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-6 gap-y-2 px-4 pt-3.5 sm:px-8">
          <div className="flex min-w-0 items-baseline gap-2.5">
            <h1 className="font-disp text-[19px] font-semibold tracking-[-.01em] whitespace-nowrap">Reading Review</h1>
            <span className="text-[11px] uppercase tracking-[.06em] text-ink-3 whitespace-nowrap">
              VMLU · {blob.items.length} câu · issue&nbsp;#3
            </span>
          </div>
          <Stat label="accept %" value={stats.acceptPct === null ? "—" : stats.acceptPct.toFixed(1)} tone="accept" />
          <Stat label="đã review" value={`${stats.reviewed}/${stats.total}`} />
          <Stat label="reject" value={String(stats.reject)} tone="reject" />
          <div className="min-w-2 flex-1" />
          <label className="flex items-center gap-2">
            <span className="text-[10.5px] font-semibold uppercase tracking-[.1em] text-ink-3">Model</span>
            <select
              value={model}
              onChange={(e) => pickModel(e.target.value)}
              className="rounded-lg border border-hair bg-card px-3 py-2 text-[13.5px] font-medium"
            >
              {blob.models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <span className="whitespace-nowrap text-[12.5px] text-ink-2">
            reviewer: <b className="font-semibold text-ink">{annotator ?? "—"}</b>
          </span>
          {pill}
          <button
            type="button"
            onClick={() => setHelp(true)}
            aria-label="Phím tắt"
            className="rounded-lg px-2 py-2 text-[13.5px] font-medium text-ink-2 transition-colors hover:bg-hair/35 hover:text-ink"
          >
            ?
          </button>
        </div>
        <div className="mx-auto max-w-[1440px] overflow-x-auto px-4 py-2.5 sm:px-8 [scrollbar-width:thin]">
          {item && <Filmstrip items={blob.items} bucket={bucket} peers={peers} idx={idx} onJump={go} />}
        </div>
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-3.5 gap-y-1.5 px-4 pb-2.5 text-[11px] text-ink-3 sm:px-8">
          <Key swatch="bg-accept">accept</Key>
          <Key swatch="bg-reject">reject</Key>
          <Key swatch="bg-flag">reject thiếu đáp án sửa</Key>
          <Key swatch="bg-null">chưa review</Key>
          <Key striped>người khác đã chốt</Key>
          <span>· mỗi vạch đứng = một đoạn văn, click để nhảy tới câu</span>
        </div>
      </header>

      {banner && (
        <div className="border-b border-reject/30 bg-reject-soft px-4 py-2 text-[13px] sm:px-8" role="status">
          <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-2.5">
            <b className="text-reject">{banner.t}</b>
            <span>{banner.m}</span>
            {banner.fix && (
              <button
                type="button"
                onClick={banner.fix.fn}
                className="rounded-lg border border-hair bg-card px-2.5 py-1 text-[12.5px] font-medium"
              >
                {banner.fix.l}
              </button>
            )}
            <button type="button" onClick={() => setBanner(null)} aria-label="Đóng thông báo" className="ml-auto text-ink-2 hover:text-ink">
              ✕
            </button>
          </div>
        </div>
      )}

      <main className="mx-auto grid max-w-[1440px] grid-cols-1 items-start gap-4 px-4 py-4 sm:px-8 lg:grid-cols-[minmax(0,1.55fr)_minmax(340px,1fr)] lg:gap-7">
        {item ? (
          <>
            <ItemPane
              it={item}
              context={blob.passages[item.passage_key] ?? ""}
              answer={answer}
              model={model}
              position={pos}
              total={blob.items.length}
              idx={idx}
            />
            <DecisionPanel
              st={curState}
              peerLock={peerLock}
              modelAnswer={answer}
              onDecision={setDecision}
              onCorrection={setField("c")}
              onNote={setField("n")}
              stats={stats}
              onExportCsv={() => void exportCsv()}
              onExportState={exportState}
              onImportState={(f) => void importState(f)}
              reviewer={annotator ?? "…"}
              model={model}
              peerFiles={peerFiles}
            />
          </>
        ) : (
          <p className="col-span-full py-16 text-center text-ink-3">blob không có câu nào — chạy lại export-blob</p>
        )}
      </main>

      <NavDock
        idx={idx}
        total={blob.items.length}
        onPrev={() => go(idx - 1)}
        onNext={() => go(idx + 1)}
        onNextUnreviewed={jumpUnreviewed}
        onJumpToNumber={jumpToNumber}
        status={pill}
      />

      {!annotator && <Gate onSubmit={submitReviewer} />}
      {help && (
        <Overlay onClose={() => setHelp(false)}>
          <h2 className="font-disp text-[20px] font-semibold">Phím tắt</h2>
          <p className="mt-1.5 text-[14px] text-ink-2">Các phím này tắt khi con trỏ đang ở trong ô văn bản.</p>
          <div className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 text-[13.5px]">
            {(
              [
                ["j / ↓", "Câu kế tiếp"],
                ["k / ↑", "Câu trước"],
                ["a · space", "Accept (lần 2 = bỏ trống)"],
                ["r", "Reject · focus ô sửa nếu đang trống"],
                ["u", "Bỏ trống quyết định"],
                ["e", "Tới ô đáp án sửa"],
                ["n", "Tới ô ghi chú"],
                ["g", "Gõ số câu để nhảy tới"],
                ["t", "Nhảy tới câu chưa review kế tiếp"],
                ["Home / End", "Câu đầu / câu cuối"],
                ["? · Esc", "Mở / đóng bảng này"],
              ] as const
            ).map(([k, v]) => (
              <div key={k} className="contents">
                <span className="text-right whitespace-nowrap">
                  <kbd className="rounded border border-hair bg-card px-1.5 py-0.5 font-mono text-[10.5px] text-ink-2">{k}</kbd>
                </span>
                <span>{v}</span>
              </div>
            ))}
          </div>
        </Overlay>
      )}
      {toastMsg && (
        <div role="status" aria-live="polite" className="pointer-events-none fixed bottom-22 left-1/2 z-50 max-w-[min(90vw,460px)] -translate-x-1/2 rounded-lg bg-ink px-4 py-2.5 text-center text-[13px] font-medium text-paper">
          {toastMsg}
        </div>
      )}
    </>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "accept" | "reject" }) {
  return (
    <div className="flex min-w-19 flex-col leading-tight">
      <b className={"font-disp text-[21px] font-semibold tabular-nums " + (tone === "accept" ? "text-accept" : tone === "reject" ? "text-reject" : "")}>
        {value}
      </b>
      <span className="mt-[3px] text-[10.5px] uppercase leading-[1.4] tracking-[.1em] text-ink-3">{label}</span>
    </div>
  );
}

function Key({ swatch, striped, children }: { swatch?: string; striped?: boolean; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <i
        className={"inline-block h-[9px] w-[9px] rounded-[2px] " + (striped ? "peer-stripe" : swatch)}
        aria-hidden
      />
      {children}
    </span>
  );
}

function Gate({ onSubmit }: { onSubmit: (v: string) => void }) {
  const [v, setV] = useState("");
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="gate-title" className="fixed inset-0 z-60 flex items-center justify-center bg-black/60 p-5">
      <form
        className="w-full max-w-[420px] rounded-[14px] border border-card-edge bg-card p-6 shadow-2xl sm:p-8"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(v);
        }}
      >
        <h2 id="gate-title" className="font-disp text-[24px] font-semibold">Bạn là ai?</h2>
        <p className="mt-1.5 text-[14px] leading-relaxed text-ink-2">
          Nhãn trạng thái được lưu riêng cho từng <b>người review × model</b>. Hai người phải review độc lập — đừng nhập state của người khác.
        </p>
        <label className="mt-5 block">
          <span className="block text-[10.5px] font-semibold uppercase tracking-[.1em] text-ink-3">Tên người review</span>
          <input
            autoFocus
            value={v}
            onChange={(e) => setV(e.target.value)}
            autoComplete="off"
            placeholder="vd: linh (gõ không dấu cũng được)"
            className="mt-2 w-full rounded-lg border border-hair bg-card px-3.5 py-3 text-[15px] focus:border-ink-2 focus:outline-none"
          />
        </label>
        <button
          type="submit"
          className="mt-4 w-full rounded-lg border border-ink bg-ink px-3 py-3 text-[14px] font-semibold text-paper"
        >
          Bắt đầu review
        </button>
      </form>
    </div>
  );
}

function Overlay({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-5"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-[560px] rounded-[14px] border border-card-edge bg-card p-6 shadow-2xl sm:p-8">{children}</div>
    </div>
  );
}
