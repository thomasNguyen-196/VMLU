"use client";

/** Sticky table-of-contents for /harness: one glance at where you are, one click
 *  to jump. The active entry follows the scroll position; no routing, no state
 *  outside this component. */
import { useEffect, useState } from "react";

export interface TocItem {
  id: string;
  label: string;
}

export default function TocNav({ items }: { items: TocItem[] }) {
  const [active, setActive] = useState<string>(items[0]?.id ?? "");
  const key = JSON.stringify(items.map((i) => i.id));
  useEffect(() => {
    const onScroll = () => {
      let current = items[0]?.id ?? "";
      for (const it of items) {
        const el = document.getElementById(it.id);
        if (el && el.getBoundingClientRect().top <= 140) current = it.id;
      }
      setActive((prev) => (prev === current ? prev : current));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return (
    <nav
      aria-label="Mục lục"
      className="sticky top-6 max-h-[calc(100dvh-3rem)] overflow-y-auto rounded-lg border border-hair bg-card p-3"
    >
      <p className="px-2 text-[11.5px] font-semibold uppercase tracking-wider text-ink-2">
        Mục lục
      </p>
      <ul className="mt-1.5 space-y-0.5">
        {items.map((it) => (
          <li key={it.id}>
            <a
              href={`#${it.id}`}
              aria-current={it.id === active ? "true" : undefined}
              className={`block rounded px-2 py-1 text-[12.5px] leading-snug ${
                it.id === active
                  ? "bg-flag-soft/60 font-semibold text-ink"
                  : "text-ink-2 hover:text-ink"
              }`}
            >
              {it.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
