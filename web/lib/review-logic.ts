import { itemKey, type ItemState, type ReviewItem } from "./types.ts";

/** Pure selectors over the blob + a reviewer's in-memory bucket. No React,
 *  no I/O — the same maths the static fallback does imperatively in render. */

export type StripState = "" | "accept" | "reject" | "flag";

export function stateOf(
  items: ReviewItem[],
  bucket: Record<string, ItemState>,
  index: number,
): StripState {
  const st = bucket[itemKey(items[index])];
  if (!st?.d) return "";
  if (st.d === "reject" && !st.c.trim()) return "flag";
  return st.d;
}

export interface Stats {
  reviewed: number;
  accept: number;
  reject: number;
  total: number;
  acceptPct: number | null;
  byDataset: Record<string, [number, number]>; // dataset -> [accept, reviewed]
  byStratum: Record<string, [number, number]>;
}

export function computeStats(items: ReviewItem[], bucket: Record<string, ItemState>): Stats {
  let reviewed = 0, accept = 0, reject = 0;
  const byDataset: Record<string, [number, number]> = {};
  const byStratum: Record<string, [number, number]> = {};
  for (const it of items) {
    const st = bucket[itemKey(it)];
    if (!st?.d) continue;
    reviewed++;
    const ds = (byDataset[it.dataset] ??= [0, 0]);
    const str = (byStratum[`${it.dataset}/${it.stratum}`] ??= [0, 0]);
    ds[1]++;
    str[1]++;
    if (st.d === "accept") {
      accept++;
      ds[0]++;
      str[0]++;
    } else reject++;
  }
  return {
    reviewed, accept, reject, total: items.length,
    acceptPct: reviewed ? (100 * accept) / reviewed : null,
    byDataset, byStratum,
  };
}

/** Wrap-around index of the next item with no decision; null if none left.
 *  `locked` (peer-published itemKeys, see lib/records) also counts as done —
 *  the jump is the work queue, and a peer's item is not yours. */
export function nextUnreviewed(
  items: ReviewItem[],
  bucket: Record<string, ItemState>,
  from: number,
  locked: Record<string, unknown> = {},
): number | null {
  for (let step = 1; step <= items.length; step++) {
    const i = (from + step) % items.length;
    const k = itemKey(items[i]);
    if (!bucket[k]?.d && !locked[k]) return i;
  }
  return null;
}

/** Contiguous passage runs (workbook order is passage-contiguous by build). */
export interface PassageGroup {
  key: string;
  first: number;
  indices: number[];
}
export function passageGroups(items: ReviewItem[]): PassageGroup[] {
  const out: PassageGroup[] = [];
  items.forEach((it, i) => {
    const last = out[out.length - 1];
    if (last && last.key === it.passage_key) last.indices.push(i);
    else out.push({ key: it.passage_key, first: i, indices: [i] });
  });
  return out;
}

export interface Position {
  within: number; // 1-based position of idx inside its passage
  of: number; // how many questions in this passage
}
export function passagePosition(groups: PassageGroup[], idx: number): Position {
  const g = groups.find((x) => idx >= x.first && idx < x.first + x.indices.length);
  if (!g) return { within: 1, of: 1 };
  return { within: idx - g.first + 1, of: g.indices.length };
}

export function answerFor(
  it: ReviewItem,
  model: string,
  extra: Record<string, Record<string, string>>,
): string | null {
  if (extra[model]) return extra[model][itemKey(it)] ?? null;
  return it.answers[model] ?? null;
}
