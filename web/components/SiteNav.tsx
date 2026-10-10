"use client";

/** One nav strip shared by every surface: Review (`/`), Benchmark
 *  (`/benchmark`), Harness (`/harness`) and Results (`/results`).
 *
 * WHY it exists: the three pages were three products — `/` and `/harness` wore
 * the paper/ink tokens while `/benchmark` wore an indigo/slate skin, and the
 * only link between them was one `← Review` button. Same study, three doors.
 * The active entry follows the pathname, so every page marks where it is
 * without each one having to say so.
 *
 * Deliberately dumb: a list of destinations and their active state. It knows
 * nothing about datasets, models or cards — those belong to the pages.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Review", hint: "400 câu đọc hiểu" },
  { href: "/benchmark", label: "Benchmark", hint: "số live từ Mongo" },
  { href: "/table", label: "Bảng", hint: "kết quả main tiếng Việt đã chấm" },
  { href: "/harness", label: "Harness", hint: "đường truy xuất có agent" },
] as const;

export default function SiteNav() {
  const path = usePathname() ?? "/";
  return (
    <nav
      aria-label="Các mặt phẳng nghiên cứu"
      className="border-b border-hair bg-paper"
    >
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-1 gap-y-1 px-4 py-1.5 sm:px-8">
        <span className="mr-2 font-disp text-[13px] font-semibold tracking-[-.01em] text-ink">
          VMLU
        </span>
        {ITEMS.map((it) => {
          const active = path === it.href;
          return (
            <Link
              key={it.href}
              href={it.href}
              aria-current={active ? "page" : undefined}
              title={it.hint}
              className={`rounded-lg px-2.5 py-1 text-[12.5px] leading-none transition-colors ${
                active
                  ? "border border-hair bg-card font-semibold text-ink"
                  : "border border-transparent text-ink-2 hover:bg-card hover:text-ink"
              }`}
            >
              {it.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}