"use client";

/** One nav strip shared by every surface: Review (`/`), Benchmark
 *  (`/benchmark`), frozen results (`/table`), multi-model live view
 *  (`/multimodel`) and Harness (`/harness`).
 *
 * WHY it exists: the pages were separate products — `/` and `/harness` wore
 * the paper/ink tokens while `/benchmark` wore an indigo/slate skin, and the
 * only link between them was one `← Review` button. Same study, one shared navigation.
 * The active entry follows the pathname, so every page marks where it is
 * without each one having to say so.
 *
 * Shared site chrome lives here: destinations and the app-wide appearance
 * control. Dataset, model and card controls stay with their pages.
 */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import ThemeToggle from "@/components/ThemeToggle.tsx";

const ITEMS = [
  { href: "/", label: "Review", hint: "400 câu đọc hiểu" },
  { href: "/benchmark", label: "Benchmark", hint: "số live từ Mongo" },
  { href: "/table", label: "Bảng", hint: "kết quả main tiếng Việt đã chấm" },
  { href: "/diagnostic", label: "Diagnostic", hint: "review pilot lỗi từng câu" },
  { href: "/multimodel", label: "Ma trận live", hint: "số lấy từ Mongo" },
  { href: "/harness", label: "Harness", hint: "đường truy xuất có agent" },
] as const;

export default function SiteNav() {
  const path = usePathname() ?? "/";
  const router = useRouter();
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
          const active = path === it.href || (it.href === "/table" && path === "/table/v2");
          return (
            <Link
              key={it.href}
              href={it.href}
              scroll={false}
              onNavigate={(event) => {
                try {
                  const saved = sessionStorage.getItem(`vmlu-last-url:${it.href}`);
                  if (saved && saved !== it.href) {
                    const url = new URL(saved, window.location.origin);
                    if (url.origin === window.location.origin && url.pathname === it.href) {
                      event.preventDefault();
                      router.push(`${url.pathname}${url.search}`, { scroll: false });
                    }
                  }
                } catch { /* Fall back to the normal link if storage is unavailable. */ }
              }}
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
        <ThemeToggle className="ml-auto shrink-0" />
      </div>
    </nav>
  );
}
