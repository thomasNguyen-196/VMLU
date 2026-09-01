"use client";

import { memo } from "react";
import type { ItemState } from "@/lib/types.ts";
import type { PeerDecision, RecordFileRow } from "@/lib/records.ts";
import type { Stats } from "@/lib/review-logic.ts";

/** Right column: the verdict instruments — decision radios, the correction
 *  field (enabled only on Reject, red-flagged when Reject has no text, because
 *  then no gold is derivable), the note field, the per-group stats, and the
 *  export/import row that keeps this app compatible with the CSV merge step. */
function DecisionPanelInner({
  st,
  peerLock,
  modelAnswer,
  onDecision,
  onCorrection,
  onNote,
  stats,
  onExportCsv,
  onExportState,
  onImportState,
  reviewer,
  model,
  peerFiles,
}: {
  st: ItemState | undefined;
  peerLock: PeerDecision | undefined;
  modelAnswer: string | null;
  onDecision: (d: "accept" | "reject" | "clear") => void;
  onCorrection: (v: string) => void;
  onNote: (v: string) => void;
  stats: Stats;
  onExportCsv: () => void;
  onExportState: () => void;
  onImportState: (f: File) => void;
  reviewer: string;
  model: string;
  peerFiles: RecordFileRow[];
}) {
  const d = st?.d ?? "";
  const badFlag = d === "reject" && !(st?.c ?? "").trim();
  const card = "rounded-[10px] border border-card-edge bg-card p-5";
  const btn =
    "flex items-center justify-center gap-2 rounded-lg border px-2 py-2.5 text-[13px] font-medium transition-colors";
  return (
    <div className="flex flex-col gap-5">
      <div className={card}>
        {peerLock ? (
          <>
            <span className="text-[10.5px] font-semibold uppercase tracking-[.1em] text-ink-3">
              Đã có người chốt
            </span>
            <p className="mt-2.5 text-[14px] leading-relaxed">
              <b className="font-semibold text-ink">{peerLock.reviewer}</b>{" "}
              {peerLock.decision === "accept" ? (
                <>
                  đã <b className="text-accept">accept</b> — model answer thành gold:
                  <span className="mt-1.5 block rounded-lg bg-hair/30 px-3 py-2 text-[13.5px] leading-[1.6]">
                    {modelAnswer || "—"}
                  </span>
                </>
              ) : (
                <>
                  đã <b className="text-reject">reject</b> — đáp án sửa thành gold:
                  <span className="mt-1.5 block rounded-lg bg-hair/30 px-3 py-2 text-[13.5px] leading-[1.6]">
                    {peerLock.c}
                  </span>
                </>
              )}
              {peerLock.n && (
                <span className="mt-1.5 block text-[12.5px] italic text-ink-2">ghi chú: {peerLock.n}</span>
              )}
            </p>
            <p className="mt-3 rounded-lg border border-hair bg-hair/20 px-3 py-2 text-[12.5px] leading-snug text-ink-2">
              Câu này khóa chỉ-đọc để hai người không làm trùng (sổ phân công{" "}
              <code className="font-mono">review_records/</code>). Phím{" "}
              <kbd className="rounded border border-hair bg-card px-1.5 py-0.5 font-mono text-[10.5px]">t</kbd>{" "}
              nhảy tới câu chưa có người làm.
            </p>
          </>
        ) : (
          <>
        <span className="text-[10.5px] font-semibold uppercase tracking-[.1em] text-ink-3">
          Quyết định của bạn
        </span>
        <div role="radiogroup" aria-label="Quyết định" className="mt-2.5 grid grid-cols-3 gap-2">
          <SegBtn on={d === "accept"} kind="accept" k="a" onClick={() => onDecision("accept")}>
            Accept
          </SegBtn>
          <SegBtn on={d === "reject"} kind="reject" k="r" onClick={() => onDecision("reject")}>
            Reject
          </SegBtn>
          <SegBtn on={d === ""} kind="null" k="u" onClick={() => onDecision("clear")}>
            Bỏ trống
          </SegBtn>
        </div>
        <p className="mt-2.5 text-[12px] leading-snug text-ink-3">
          Accept = đáp án của model thành gold. Reject = đáp án sửa bên dưới thành gold.
        </p>

        <div className="mt-4">
          <label htmlFor="corr" className="block text-[10.5px] font-semibold uppercase tracking-[.1em] text-ink-3">
            Đáp án sửa <span className="normal-case tracking-normal">— bắt buộc khi Reject</span>{" "}
            <kbd className="font-mono text-[10.5px]">e</kbd>
          </label>
          <textarea
            id="corr"
            lang="vi"
            rows={3}
            disabled={d !== "reject"}
            value={st?.c ?? ""}
            onChange={(e) => onCorrection(e.target.value)}
            placeholder="Đáp án đúng theo bạn…"
            className={
              "mt-1.5 w-full resize-y rounded-lg border bg-card px-3 py-2.5 text-[14px] leading-[1.6] transition-colors placeholder:text-ink-3 focus:outline-none disabled:cursor-not-allowed disabled:bg-hair/25 disabled:text-ink-3 " +
              (badFlag
                ? "border-reject bg-reject-soft/50 focus:outline-2 focus:outline-reject/45"
                : "border-hair focus:border-ink-2")
            }
          />
          {badFlag && (
            <p className="mt-1.5 text-[12px] font-medium text-reject">
              Reject cần một đáp án sửa — nếu không, gold không suy ra được và câu này rơi vào adjudication.
            </p>
          )}
        </div>

        <div className="mt-4">
          <label htmlFor="note" className="block text-[10.5px] font-semibold uppercase tracking-[.1em] text-ink-3">
            Ghi chú <kbd className="font-mono text-[10.5px]">n</kbd>
          </label>
          <textarea
            id="note"
            lang="vi"
            rows={3}
            value={st?.n ?? ""}
            onChange={(e) => onNote(e.target.value)}
            placeholder="Lý do reject, nguồn span… (không bắt buộc)"
            className="mt-1.5 w-full resize-y rounded-lg border border-hair bg-card px-3 py-2.5 text-[14px] leading-[1.6] transition-colors placeholder:text-ink-3 focus:border-ink-2 focus:outline-none"
          />
        </div>
          </>
        )}
      </div>

      <div className={card}>
        <span className="text-[10.5px] font-semibold uppercase tracking-[.1em] text-ink-3">
          Tiến độ theo nhóm câu
        </span>
        <div className="mt-2.5 text-[13px]">
          <StatRow k="toàn bộ" v={`${stats.accept}/${stats.reviewed} · ${stats.total ? Math.round((100 * stats.accept) / stats.total) : 0}%`} />
          {Object.entries(stats.byDataset)
            .sort()
            .map(([k, [a, r]]) => (
              <StatRow key={k} k={k} v={`${a}/${r} · ${r ? Math.round((100 * a) / r) : 0}%`} />
            ))}
          {Object.entries(stats.byStratum)
            .sort()
            .map(([k, [a, r]]) => (
              <StatRow key={k} k={k} v={`${a}/${r} · ${r ? Math.round((100 * a) / r) : 0}%`} muted />
            ))}
        </div>
      </div>

      <div className={card}>
        <span className="text-[10.5px] font-semibold uppercase tracking-[.1em] text-ink-3">Xuất kết quả</span>
        <div className="mt-2.5 grid grid-cols-2 gap-2">
          <button type="button" onClick={onExportCsv} className={`${btn} border-dashed`}>
            Export CSV
          </button>
          <button type="button" onClick={onExportState} className={`${btn} border-dashed`}>
            Export state
          </button>
          <label className={`${btn} col-span-2 cursor-pointer border-dashed`}>
            Import state (JSON đã export)
            <input
              type="file"
              accept=".json"
              className="sr-only"
              onChange={(e) => e.target.files?.[0] && onImportState(e.target.files[0])}
            />
          </label>
        </div>
        <p className="mt-3 text-[11.5px] leading-relaxed text-ink-3">
          State tự lưu vào đĩa <code className="font-mono">review_state/{reviewer ? `/${slugPreview(reviewer)}__${slugPreview(model)}.json` : ""}</code>.
          Export CSV khi cần đưa cho bước merge{" "}
          <code className="font-mono">export_annotation_workbooks.py review</code>.
        </p>
        <div className="mt-3 border-t border-hair pt-3 text-[11.5px] leading-relaxed text-ink-3">
          <span className="font-semibold uppercase tracking-[.08em]">Sổ phân công · review_records/</span>
          {peerFiles.length ? (
            <ul className="mt-1.5 space-y-1">
              {peerFiles.map((f) =>
                f.error ? (
                  <li key={f.file} className="text-reject">
                    <code className="font-mono">{f.file}</code> — bỏ qua: {f.error}
                  </li>
                ) : (
                  <li key={f.file}>
                    <code className="font-mono">{f.file}</code> — {f.annotator}: {f.decided} câu đã chốt
                  </li>
                ),
              )}
            </ul>
          ) : (
            <p className="mt-1.5">chưa có ai export — Export CSV ở trên sẽ công bố file của bạn vào đây.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function slugPreview(s: string) {
  return s
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "_") || "…";
}

function StatRow({ k, v, muted }: { k: string; v: string; muted?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-hair py-[7px] last:border-b-0">
      <span className={muted ? "break-words text-[12px] text-ink-3" : "text-ink-2"}>{k}</span>
      <span className={"whitespace-nowrap font-semibold tabular-nums " + (muted ? "text-[12px] text-ink-2" : "text-accept")}>
        {v}
      </span>
    </div>
  );
}

function SegBtn({
  on,
  kind,
  k,
  unset,
  onClick,
  children,
}: {
  on: boolean;
  kind: "accept" | "reject" | "null";
  k: string;
  unset?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const colors =
    kind === "accept"
      ? "border-accept bg-accept-soft text-accept"
      : kind === "reject"
        ? "border-reject bg-reject-soft text-reject"
        : "border-ink-2 bg-hair/40";
  const mark =
    kind === "accept" ? "bg-accept" : kind === "reject" ? "bg-reject" : "";
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      onClick={onClick}
      className={
        "flex flex-col items-center gap-2 rounded-lg border-[1.5px] px-2 pb-3 pt-3.5 text-[14px] font-semibold transition-[border-color,background-color] duration-100 " +
        (on ? colors : "border-hair bg-card hover:border-ink-3")
      }
    >
      <span
        aria-hidden
        className={
          "block h-4 w-4 rounded-full border-[1.5px] " +
          (on ? `border-transparent ${mark} ${kind === "null" ? "bg-ink-3" : ""}` : "border-ink-3")
        }
      />
      {children}
      <kbd className="font-mono text-[10.5px] font-normal">{unset ? "u" : k}</kbd>
    </button>
  );
}

export const DecisionPanel = memo(DecisionPanelInner);
