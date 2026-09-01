import { itemKey, type ReviewBlob, type StateEnvelope } from "./types.ts";

/** The 9-column review CSV contract consumed by
 *  `export_annotation_workbooks.py review --a --b` (REVIEW_COLS there —
 *  keep both lists in lockstep; CI asserts an exported CSV parses).
 *  Row semantics match the static fallback's client-side buildCsv():
 *  one row per item in workbook order; empty decision for unreviewed;
 *  corrected_answer populated only for rejects; model_answer comes from
 *  the ACTIVE blob's answers for this model, not from the stored state. */
export const REVIEW_COLS = [
  "annotator", "model", "dataset", "item_id", "stratum",
  "decision", "model_answer", "corrected_answer", "note",
] as const;

/** RFC-4180 quoting, identical rule to the template's csvCell(). */
export function csvCell(v: unknown): string {
  const s = String(v ?? "");
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

export function makeExportCsv(blob: ReviewBlob, envelope: StateEnvelope): string {
  const lines = [REVIEW_COLS.join(",")];
  for (const it of blob.items) {
    const st = envelope.items[itemKey(it)];
    const ans = it.answers[envelope.model];
    lines.push([
      envelope.annotator, envelope.model, it.dataset, it.item_id, it.stratum,
      st?.d ?? "",
      ans == null ? "" : ans,
      st?.d === "reject" ? st.c || "" : "",
      st?.n ?? "",
    ].map(csvCell).join(","));
  }
  return "﻿" + lines.join("\r\n") + "\r\n";
}
