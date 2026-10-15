"use client";

import { useLayoutEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";

/** Keep each page/condition's reading position for this browser tab. */
export default function ScrollRestoration() {
  const pathname = usePathname();
  const search = useSearchParams().toString();

  useLayoutEffect(() => {
    const key = `vmlu-scroll-v1:${pathname}${search ? `?${search}` : ""}`;
    let restoring = !window.location.hash;
    let frame = 0;
    let target = { x: 0, y: 0 };
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) ?? "null");
      if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) target = saved;
    } catch { /* Storage may be unavailable. Navigation must still work. */ }

    const save = () => {
      if (restoring) return;
      try {
        sessionStorage.setItem(key, JSON.stringify({ x: window.scrollX, y: window.scrollY }));
        sessionStorage.setItem(`vmlu-last-url:${pathname}`, `${pathname}${search ? `?${search}` : ""}`);
      } catch { /* Private or quota-limited storage is optional. */ }
    };
    const cancelRestore = () => { restoring = false; cancelAnimationFrame(frame); };
    const started = performance.now();
    const restore = () => {
      if (!restoring) return;
      window.scrollTo({ left: target.x, top: target.y, behavior: "instant" });
      // Streaming content can initially be shorter than the saved position.
      if (Math.abs(window.scrollY - target.y) < 2 || performance.now() - started > 2000) {
        restoring = false;
      } else frame = requestAnimationFrame(restore);
    };
    // Run after the router has committed and applied its own scroll handling.
    if (restoring) frame = requestAnimationFrame(() => { frame = requestAnimationFrame(restore); });
    const previous = history.scrollRestoration;
    history.scrollRestoration = "manual";
    window.addEventListener("scroll", save, { passive: true });
    window.addEventListener("pagehide", save);
    document.addEventListener("click", save, true);
    window.addEventListener("wheel", cancelRestore, { passive: true });
    window.addEventListener("touchstart", cancelRestore, { passive: true });
    window.addEventListener("keydown", cancelRestore);
    return () => {
      cancelRestore();
      history.scrollRestoration = previous;
      window.removeEventListener("scroll", save);
      window.removeEventListener("pagehide", save);
      document.removeEventListener("click", save, true);
      window.removeEventListener("wheel", cancelRestore);
      window.removeEventListener("touchstart", cancelRestore);
      window.removeEventListener("keydown", cancelRestore);
    };
  }, [pathname, search]);

  return null;
}
