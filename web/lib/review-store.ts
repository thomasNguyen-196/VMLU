import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Bucket } from "./types.ts";

/** Persisted review session: reviewer identity, active model, current item
 *  position and the (reviewer × model) decision bucket — restored instantly on
 *  every return, before the /api/state round-trip. The server envelope stays
 *  the durable truth; the store is a fast-resume cache + permanent local
 *  mirror (the old failure-only `bucketLsKey` mirror is subsumed: persist
 *  writes on every change, so a dead server never costs work).
 *
 *  skipHydration: SSR/initial render always uses the defaults so the server
 *  HTML and the client's first render agree; ReviewApp rehydrates once in an
 *  effect after mount. */
interface ReviewSessionStore {
  annotator: string | null; // null = gate open
  model: string;
  idx: number;
  bucket: Bucket;
  /** ISO timestamp of the last local change (mirror-freshness vs disk). */
  savedAt: string;
  setAnnotator(a: string | null): void;
  setModel(m: string): void;
  setIdx(i: number): void;
  setBucket(next: Bucket): void;
}

export const useReviewStore = create<ReviewSessionStore>()(
  persist(
    (set) => ({
      annotator: null,
      model: "",
      idx: 0,
      bucket: {},
      savedAt: "",
      setAnnotator: (a) => set({ annotator: a }),
      setModel: (m) => set({ model: m, idx: 0 }),
      setIdx: (i) => set({ idx: i }),
      setBucket: (b) => set({ bucket: b, savedAt: new Date().toISOString() }),
    }),
    {
      name: "vmlu.review.ui",
      version: 1,
      skipHydration: true,
      partialize: (s) => ({
        annotator: s.annotator,
        model: s.model,
        idx: s.idx,
        bucket: s.bucket,
        savedAt: s.savedAt,
      }),
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
