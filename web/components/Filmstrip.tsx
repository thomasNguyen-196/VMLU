"use client";

import { memo, useEffect, useMemo, useRef } from "react";
import type { ItemState, ReviewItem } from "@/lib/types.ts";
import type { PeerMap } from "@/lib/records.ts";
import { itemKey } from "@/lib/types.ts";
import { passageGroups, stateOf } from "@/lib/review-logic.ts";

/** The signature element (design D5): a full-width ruler of one cell per
 *  item, grouped into one segment per passage (segments grow with their item
 *  count, so a 5-question passage reads wider). Progress bar, decision
 *  overview, and jump-to navigator in one object. Decided cells grow taller
 *  and take on decision color; unreviewed stay short and null-grey; a reject
 *  with no correction is amber (invalid — no gold derivable). */
function FilmstripInner({
  items,
  bucket,
  peers,
  idx,
  onJump,
}: {
  items: ReviewItem[];
  bucket: Record<string, ItemState>;
  peers: PeerMap;
  idx: number;
  onJump: (i: number) => void;
}) {
  const groups = useMemo(() => passageGroups(items), [items]);
  const current = groups.findIndex((g) => idx >= g.first && idx < g.first + g.indices.length);
  const selfRef = useRef<HTMLDivElement>(null);

  // keep the current segment in view as navigation moves across the strip
  useEffect(() => {
    const g = selfRef.current?.children[current] as HTMLElement | undefined;
    g?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [current]);

  if (!items.length) return null;
  return (
    <div ref={selfRef} className="flex min-w-full gap-0 px-0.5" role="group" aria-label="Tổng quan tiến độ 400 câu">
      {groups.map((g, gi) => (
        <button
          key={g.key}
          type="button"
          onClick={() => onJump(g.first)}
          aria-label={`đoạn ${g.key}, ${g.indices.length} câu`}
          title={`${g.key} · ${g.indices.length} câu`}
          className="group relative flex-1 basis-0 overflow-hidden border-0 bg-transparent p-0"
          style={{ flexGrow: g.indices.length, minWidth: 3, boxShadow: gi > 0 ? "inset 1.5px 0 0 var(--hair)" : undefined }}
        >
          {g.indices.map((i, k) => {
            const s = stateOf(items, bucket, i);
            const locked = !!peers[itemKey(items[i])];
            return (
              <span
                key={i}
                aria-hidden
                className={[
                  "absolute bottom-1.5 rounded-[2px] transition-[height,background-color] duration-150 ease-[cubic-bezier(.2,.8,.3,1)]",
                  s === "" && !locked && "h-[9px] bg-null",
                  s === "" && locked && "h-5 peer-stripe",
                  s === "accept" && "h-5 bg-accept",
                  s === "reject" && "h-5 bg-reject",
                  s === "flag" && "h-5 bg-flag",
                  "group-hover:brightness-[.86]",
                ]
                  .filter(Boolean)
                  .join(" ")}
                style={{ left: `${(k / g.indices.length) * 100}%`, width: `${100 / g.indices.length}%` }}
              />
            );
          })}
          {gi === current && (
            <span
              aria-hidden
              className="absolute -bottom-[7px] left-1/2 h-0 w-0 -translate-x-1/2 border-x-4 border-t-[5px] border-x-transparent border-t-ink"
            />
          )}
        </button>
      ))}
    </div>
  );
}

export const Filmstrip = memo(FilmstripInner);
