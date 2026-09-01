"use client";

import { useRef, useState } from "react";

/** Fixed bottom navigation dock (spec review-ui "Always-available sequential
 *  navigation"): Prev / position counter / Next always one click away,
 *  plus the next-unreviewed jump. Boundary direction disables rather than
 *  wrapping, so End-of-set is a felt fact, not a silent loop.
 *  The number field jumps straight to a 1-based question number (the same
 *  numbering as the filmstrip and the counter); validation lives in
 *  ReviewApp so out-of-range input gets the shared toast. */
export function NavDock({
  idx,
  total,
  onPrev,
  onNext,
  onNextUnreviewed,
  onJumpToNumber,
  status,
}: {
  idx: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  onNextUnreviewed: () => void;
  onJumpToNumber: (n: number) => void;
  status: React.ReactNode;
}) {
  const first = idx <= 0;
  const last = idx >= total - 1;
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = () => {
    const t = q.trim();
    if (!/^\d+$/.test(t)) {
      onJumpToNumber(NaN); // ReviewApp toasts "nhập số câu hợp lệ"
      return;
    }
    onJumpToNumber(parseInt(t, 10));
    setQ("");
    inputRef.current?.blur(); // return keys (j/k/a/r) to the page
  };

  return (
    <nav
      aria-label="Điều hướng câu"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-hair bg-paper/90 backdrop-blur-md"
    >
      <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-3 px-4 sm:gap-5 sm:px-8">
        <div className="flex shrink-0 items-stretch gap-2">
          <button
            type="button"
            onClick={onPrev}
            disabled={first}
            className="flex min-w-26 flex-col items-center gap-0.5 rounded-lg border border-hair bg-card px-3.5 py-2 text-[13.5px] font-semibold shadow-sm transition-[transform,border-color] duration-100 hover:not-disabled:-translate-y-px hover:not-disabled:border-ink-2 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            ← Trước
            <small className="font-mono text-[10px] font-normal text-ink-3">k / ↑</small>
          </button>
          <div className="flex flex-col justify-center leading-tight">
            <span className="font-disp text-[22px] font-semibold tabular-nums">
              {idx + 1}
              <span className="font-normal text-ink-3"> / {total}</span>
            </span>
            <span className="text-[10.5px] uppercase tracking-widest text-ink-3">câu hỏi</span>
          </div>
          <button
            type="button"
            onClick={onNext}
            disabled={last}
            className="flex min-w-26 flex-col items-center gap-0.5 rounded-lg border border-ink bg-ink px-3.5 py-2 text-[13.5px] font-semibold text-paper shadow-sm transition-[transform,border-color] duration-100 hover:not-disabled:-translate-y-px disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            Tiếp →
            <small className="font-mono text-[10px] font-normal text-paper/60">j / ↓</small>
          </button>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="flex shrink-0 items-stretch gap-2"
        >
          <label className="flex flex-col justify-center leading-tight">
            <span className="sr-only">Nhảy tới số câu</span>
            <input
              ref={inputRef}
              id="goto"
              type="text"
              inputMode="numeric"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={`# 1–${total}`}
              className="w-24 rounded-lg border border-hair bg-card px-3 py-2 text-[13.5px] font-medium tabular-nums shadow-sm placeholder:text-ink-3 focus:border-ink-2 focus:outline-none"
            />
          </label>
          <button
            type="submit"
            className="rounded-lg border border-hair bg-card px-3.5 py-2 text-[13.5px] font-semibold shadow-sm transition-[transform,border-color] duration-100 hover:-translate-y-px hover:border-ink-2"
          >
            Nhảy tới ⏎
          </button>
        </form>
        <div className="flex-1" />
        {status}
        <button
          type="button"
          onClick={onNextUnreviewed}
          className="hidden rounded-lg border border-hair bg-card px-3 py-2 text-[13px] font-medium shadow-sm transition-colors hover:border-ink-3 sm:block"
        >
          Câu chưa review kế tiếp <kbd className="font-mono text-[10.5px] text-ink-3">t</kbd>
        </button>
      </div>
    </nav>
  );
}
