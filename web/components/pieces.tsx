"use client";

import { useState } from "react";
import type { Save } from "./hooks/use-bucket-sync.ts";

/** Small presentational pieces of ReviewApp, colocated. All pure. */

/** One header stat tile (accept %, reviewed/total, reject count). */
export function Stat({ label, value, tone }: { label: string; value: string; tone?: "accept" | "reject" }) {
  return (
    <div className="flex min-w-19 flex-col leading-tight">
      <b className={"font-disp text-[21px] font-semibold tabular-nums " + (tone === "accept" ? "text-accept" : tone === "reject" ? "text-reject" : "")}>
        {value}
      </b>
      <span className="mt-[3px] text-[10.5px] uppercase leading-[1.4] tracking-[.1em] text-ink-3">{label}</span>
    </div>
  );
}

/** Filmstrip legend swatch. */
export function Key({ swatch, striped, children }: { swatch?: string; striped?: boolean; children: React.ReactNode }) {
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

/** The autosave status dot + label (header right and the NavDock share it). */
export function SavePill({ save, savedLabel }: { save: Save; savedLabel: string }) {
  return (
    <span className={"flex items-center gap-1.5 whitespace-nowrap text-[12px] " + (save === "bad" ? "text-reject" : "text-ink-2")}>
      <span aria-hidden className={"h-[7px] w-[7px] shrink-0 rounded-full " + (save === "ok" ? "bg-accept" : save === "dirty" ? "bg-flag" : "bg-reject")} />
      {savedLabel}
    </span>
  );
}

/** The reviewer-identity gate: one name field, blind-protocol reminder. */
export function Gate({ onSubmit }: { onSubmit: (v: string) => void }) {
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

/** Generic modal shell (backdrop click closes). */
export function Overlay({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
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
