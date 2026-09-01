"use client";

/** Fixed bottom navigation dock (spec review-ui "Always-available sequential
 *  navigation"): Prev / position counter / Next always one click away,
 *  plus the next-unreviewed jump. Boundary direction disables rather than
 *  wrapping, so End-of-set is a felt fact, not a silent loop. */
export function NavDock({
  idx,
  total,
  onPrev,
  onNext,
  onNextUnreviewed,
  status,
}: {
  idx: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  onNextUnreviewed: () => void;
  status: React.ReactNode;
}) {
  const first = idx <= 0;
  const last = idx >= total - 1;
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
