"use client";

/** Light / dark / follow-the-OS switch for the harness study.
 *
 *  The palette was already token-based (`--paper`, `--card`, `--ink`…), so this
 *  only has to set `data-theme` on <html>; `globals.css` owns the actual colours.
 *  "auto" removes the attribute so the `prefers-color-scheme` media query takes
 *  over again — the honest default, not a remembered guess.
 */
import { useEffect, useState } from "react";

const KEY = "vmlu-theme";
const ORDER = ["auto", "light", "dark"] as const;
type Choice = (typeof ORDER)[number];
const LABEL: Record<Choice, string> = { auto: "Tự động", light: "Sáng", dark: "Tối" };

function read(): Choice {
  if (typeof document === "undefined") return "auto";
  const v = document.documentElement.dataset.theme;
  return v === "light" || v === "dark" ? v : "auto";
}

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const [choice, setChoice] = useState<Choice>("auto");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setChoice(read());
    setMounted(true);
  }, []);

  function pick(next: Choice) {
    setChoice(next);
    if (next === "auto") {
      delete document.documentElement.dataset.theme;
      try {
        localStorage.removeItem(KEY);
      } catch {}
    } else {
      document.documentElement.dataset.theme = next;
      try {
        localStorage.setItem(KEY, next);
      } catch {}
    }
  }

  // Before hydration the server knows nothing about the stored preference, so
  // render a stable placeholder instead of guessing and flipping.
  if (!mounted) {
    return <div className={`flex items-center gap-1 ${className}`} aria-hidden="true" />;
  }

  return (
    <div className={`flex items-center gap-0.5 rounded-full border border-hair bg-card p-0.5 ${className}`}>
      <span className="px-1.5 text-[11px] text-ink-3">Giao diện</span>
      {ORDER.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => pick(c)}
          aria-pressed={choice === c}
          title={c === "auto" ? "Theo hệ điều hành" : `Chủ động ${LABEL[c].toLowerCase()}`}
          className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-medium transition-colors ${
            choice === c ? "bg-ink text-paper" : "text-ink-2 hover:text-ink"
          }`}
        >
          {LABEL[c]}
        </button>
      ))}
    </div>
  );
}
