"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { itemKey, type ItemState, type ReviewBlob } from "@/lib/types.ts";
import { useReviewStore } from "@/lib/review-store.ts";
import { computeStats, nextUnreviewed, passageGroups, passagePosition } from "@/lib/review-logic.ts";
import { Filmstrip } from "./Filmstrip.tsx";
import { ItemPane } from "./ItemPane.tsx";
import { DecisionPanel } from "./DecisionPanel.tsx";
import { NavDock } from "./NavDock.tsx";
import { Gate, Key, Overlay, SavePill, Stat } from "./pieces.tsx";
import { useBucketSync } from "./hooks/use-bucket-sync.ts";
import { useTransfer } from "./hooks/use-transfer.ts";
import { useKeyboard } from "./hooks/use-keyboard.ts";

/** Legacy pre-zustand identity key — read once at boot to migrate returning
 *  reviewers into the persisted session store. */
const LS_ANNO = "vmlu.review.annotator";

/** The review tool: identity gate, bucket selection, navigation, and layout.
 *  The persistence/peer-sync cluster lives in hooks/use-bucket-sync, the
 *  export/import trio in hooks/use-transfer, the keyboard protocol in
 *  hooks/use-keyboard — this component wires them and renders. */
export function ReviewApp({ blob }: { blob: ReviewBlob }) {
  const annotator = useReviewStore((s) => s.annotator); // null = gate open
  const model = useReviewStore((s) => s.model);
  const idx = useReviewStore((s) => s.idx);
  const bucket = useReviewStore((s) => s.bucket);
  const setAnnotator = useReviewStore((s) => s.setAnnotator);
  const setModel = useReviewStore((s) => s.setModel);
  const setIdx = useReviewStore((s) => s.setIdx);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [help, setHelp] = useState(false);

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

  // persistence + peer sync (declared after rehydration — effect order matters)
  const { save, savedLabel, banner, setBanner, peers, peerFiles, bucketLoadingRef, commit, flushPending } =
    useBucketSync(annotator, model);

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
    [blob.items, idx, commit, peers, bucketLoadingRef, toast2],
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
    [blob.items, idx, commit, peers, bucketLoadingRef],
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
      if (!(await flushPending())) return; // unreachable server — keep the old session's mirror
      setModel(m); // store action: also resets idx to 0
      useReviewStore.getState().setBucket({}); // the store persists only the active session
    },
    [model, annotator, flushPending, setModel],
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
  const { exportCsv, exportState, importState } = useTransfer({
    annotator, model, blob, commit, toast: toast2, flushPending, setBanner,
  });

  /* ---------------- keyboard ---------------- */
  useKeyboard({
    enabled: !!annotator,
    idx,
    total: blob.items.length,
    go,
    setDecision,
    jumpUnreviewed,
    onCloseOverlay: () => setHelp(false),
    onToggleHelp: () => setHelp((h) => !h),
  });

  const pos = passagePosition(groups, idx);
  const curState = item ? bucket[itemKey(item)] : undefined;
  const answer = item ? (item.answers[model] ?? null) : null;

  const pill = <SavePill save={save} savedLabel={savedLabel} />;

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
