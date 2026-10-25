import { emptyDiagnosticJudgment, isDiagnosticReviewComplete, type DiagnosticJudgment, type VerifiedContrast } from "./diagnostic-review.ts";
import type { DiagnosticDraftEnvelope } from "./diagnostic-store.ts";

export interface HumanEdit { editedBy: string; editedAt: string | null }
export type DiagnosticProgressStatus = "unreviewed" | "in-progress" | "reviewed" | "deferred";
export function reviewerIdentity(value: string): string { return value.trim().normalize("NFC").toLowerCase(); }
export function sameJudgment(a?: DiagnosticJudgment, b?: DiagnosticJudgment): boolean {
  if (!a || !b) return a === b;
  return Object.keys(emptyDiagnosticJudgment()).every((key) => JSON.stringify(a[key as keyof DiagnosticJudgment]) === JSON.stringify(b[key as keyof DiagnosticJudgment]));
}
/** AI-only proposals do not count as human work, even when they fill most fields. */
export function diagnosticProgressStatus(row: DiagnosticJudgment | undefined, edit: HumanEdit | undefined, contrasts: VerifiedContrast[] = [], key?: string): DiagnosticProgressStatus {
  if (!row) return "unreviewed";
  if (isDiagnosticReviewComplete(row, contrasts, key)) return row.review_status === "deferred" ? "deferred" : "reviewed";
  return edit ? "in-progress" : "unreviewed";
}
/** Older v4 caches have no edit markers. Only preserve evidence of human changes;
 * identical AI proposals never acquire invented edit times or human signoff. */
export function withLegacyHumanEdits(draft: DiagnosticDraftEnvelope, proposals: Record<string, DiagnosticJudgment>): DiagnosticDraftEnvelope {
  if (draft.humanEdits) return draft;
  const humanEdits: Record<string, HumanEdit> = {};
  for (const [key, row] of Object.entries(draft.answers)) {
    const baseline = proposals[key] ?? emptyDiagnosticJudgment();
    if (!sameJudgment(row, baseline)) humanEdits[key] = { editedBy: draft.reviewer, editedAt: null };
  }
  return { ...draft, humanEdits, pendingKeys: Object.keys(humanEdits) };
}
export interface DiagnosticProgressRecord { schema_version: 1; revision: number; saved_at: string; draft: DiagnosticDraftEnvelope }
export function restoreDiagnosticProgress(local: DiagnosticDraftEnvelope | undefined, record: DiagnosticProgressRecord | null): DiagnosticDraftEnvelope | undefined {
  if (!record) return local;
  const remote = { ...record.draft, serverRevision: record.revision, serverSavedAt: record.saved_at, pendingKeys: [] };
  if (!local?.pendingKeys?.length) return remote;
  if (local.serverRevision !== record.revision) throw new Error("Có chỉnh sửa chưa đồng bộ trên trình duyệt và tiến độ server đã khác. Hãy tải bản tiến độ trên trình duyệt để đối chiếu trước khi tiếp tục.");
  const answers = { ...remote.answers }, humanEdits = { ...remote.humanEdits };
  for (const key of local.pendingKeys) { answers[key] = local.answers[key]; if (local.humanEdits?.[key]) humanEdits[key] = local.humanEdits[key]; }
  return { ...remote, answers, humanEdits, pendingKeys: local.pendingKeys };
}
/** A save response may arrive after more typing. Acknowledge only the exact
 * values sent; leave newer changes queued and keep the active review intact. */
export function acknowledgeDiagnosticSave(current: DiagnosticDraftEnvelope, sent: DiagnosticDraftEnvelope, record: DiagnosticProgressRecord): DiagnosticDraftEnvelope {
  return { ...current, serverRevision: record.revision, serverSavedAt: record.saved_at,
    pendingKeys: (current.pendingKeys ?? []).filter((key) => !sameJudgment(current.answers[key], sent.answers[key]) || JSON.stringify(current.humanEdits?.[key]) !== JSON.stringify(sent.humanEdits?.[key])),
  };
}
