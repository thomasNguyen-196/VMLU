/** Shared data contracts for the review pass (openspec revamp-review-ui).
 *  These mirror — and must not drift from — the Python blob builder
 *  (`code_benchmark/build_review_ui.py`) and the static fallback's envelope:
 *  slug parity + export equivalence are asserted from CI (`TestNextContracts`). */

export const SCHEMA_VERSION = 1;

export interface ReviewItem {
  dataset: string;
  item_id: string;
  stratum: string;
  passage_key: string;
  question: string;
  /** model tag -> raw answer text; absent/null = the model lacks this item */
  answers: Record<string, string | null>;
}

/** The blob emitted by `build_review_ui.py export-blob` (web/data/review-blob.json). */
export interface ReviewBlob {
  schema_version: number;
  created: string;
  models: string[];
  passages: Record<string, string>; // passage_key -> context
  items: ReviewItem[]; // workbook order, passage-contiguous
}

export type Decision = "accept" | "reject" | null;

/** One reviewer's call on one item. `c` is the corrected answer (gold when
 *  decision === "reject"), `n` a free-text note. */
export interface ItemState {
  d: Decision;
  c: string;
  n: string;
}

/** Envelope persisted per (reviewer, model) bucket — identical shape to the
 *  static UI's localStorage value and to state_*.json exports. */
export interface StateEnvelope {
  schema_version: number;
  annotator: string;
  model: string;
  saved_at: string;
  items: Record<string, ItemState>; // key = `${dataset}:${item_id}`
}

export const itemKey = (it: Pick<ReviewItem, "dataset" | "item_id">): string =>
  `${it.dataset}:${it.item_id}`;
