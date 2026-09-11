"use client";

import { useEffect } from "react";

/** The 13-key review protocol. Keys are ignored while typing in a form field
 *  and for modified chords; Escape blurs + closes overlays. The e/n/g targets
 *  are a DOM-id contract with DecisionPanel (#corr, #note) and NavDock
 *  (#goto) — if those ids move, move them here too. */
export function useKeyboard({
  enabled,
  idx,
  total,
  go,
  setDecision,
  jumpUnreviewed,
  onCloseOverlay,
  onToggleHelp,
}: {
  enabled: boolean;
  idx: number;
  total: number;
  go: (i: number) => void;
  setDecision: (d: "accept" | "reject" | "clear") => void;
  jumpUnreviewed: () => void;
  onCloseOverlay: () => void;
  onToggleHelp: () => void;
}) {
  useEffect(() => {
    if (!enabled) return; // gate open: keys belong to the form
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        (document.activeElement as HTMLElement | null)?.blur();
        onCloseOverlay();
        return;
      }
      if (/^(TEXTAREA|INPUT|SELECT)$/.test(String(document.activeElement?.tagName))) return;
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      switch (ev.key) {
        case "j": case "ArrowDown": go(idx + 1); ev.preventDefault(); break;
        case "k": case "ArrowUp": go(idx - 1); ev.preventDefault(); break;
        case "a": case " ": setDecision("accept"); ev.preventDefault(); break;
        case "r": setDecision("reject"); ev.preventDefault(); break;
        case "u": setDecision("clear"); ev.preventDefault(); break;
        case "e": document.getElementById("corr")?.focus(); ev.preventDefault(); break;
        case "n": document.getElementById("note")?.focus(); ev.preventDefault(); break;
        case "g": document.getElementById("goto")?.focus(); ev.preventDefault(); break;
        case "t": jumpUnreviewed(); ev.preventDefault(); break;
        case "Home": go(0); ev.preventDefault(); break;
        case "End": go(total - 1); ev.preventDefault(); break;
        case "?": onToggleHelp(); ev.preventDefault(); break;
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [enabled, idx, total, go, setDecision, jumpUnreviewed, onCloseOverlay, onToggleHelp]);
}
