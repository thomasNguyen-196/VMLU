import { createHash } from "node:crypto";
import type { Db } from "mongodb";
import { getDb } from "./db.ts";
import type { DiagnosticDraftEnvelope } from "./diagnostic-store.ts";
import { emptyDiagnosticJudgment } from "./diagnostic-review.ts";
import { reviewerIdentity, type DiagnosticProgressRecord } from "./diagnostic-progress.ts";

export class ProgressError extends Error { constructor(message: string, public status = 409) { super(message); } }
export interface ProgressIdentity { reviewer: string; pilotSha: string; protocolSha: string; scope: "primary-60" | "independent-15" }
function reviewerHash(reviewer: string): string { return createHash("sha256").update(reviewerIdentity(reviewer)).digest("hex"); }
function recordKey(id: ProgressIdentity): string { return `${reviewerHash(id.reviewer)}:${id.pilotSha}:${id.protocolSha}:${id.scope}`; }
export interface ProgressPersistence {
  read(key: string): Promise<DiagnosticProgressRecord | null>;
  write(key: string, record: DiagnosticProgressRecord, expectedRevision: number): Promise<void>;
  hasExposure(reviewerKey: string): Promise<boolean>;
  markExposure(reviewerKey: string): Promise<void>;
}
/** _id is the unique reviewer/pilot/scope key. Revision is checked in the DB
 * write itself, so concurrent tabs and separate web processes cannot clobber it. */
export function mongoProgressPersistence(db: Db): ProgressPersistence {
  const progress = db.collection<DiagnosticProgressRecord & { _id: string }>("diagnostic_progress");
  const exposures = db.collection<{ _id: string; first_seen: string }>("diagnostic_reviewer_exposure");
  return {
    async read(key) { const doc = await progress.findOne({ _id: key }); if (!doc) return null; return { schema_version: doc.schema_version, revision: doc.revision, saved_at: doc.saved_at, draft: doc.draft }; },
    async write(key, record, expectedRevision) {
      try {
        if (expectedRevision === 0) await progress.insertOne({ _id: key, ...record });
        else {
          const result = await progress.replaceOne({ _id: key, revision: expectedRevision }, record);
          if (result.matchedCount !== 1) throw new ProgressError("Tiến độ đã được cập nhật ở tab/máy khác. Tải tiến độ mới trước khi lưu tiếp.");
        }
      } catch (error) {
        if ((error as {code?: number}).code === 11000) throw new ProgressError("Tiến độ đã được cập nhật ở tab/máy khác. Tải tiến độ mới trước khi lưu tiếp.");
        throw error;
      }
    },
    async hasExposure(key) { return !!await exposures.findOne({ _id: key }); },
    async markExposure(key) { await exposures.updateOne({ _id: key }, { $setOnInsert: { first_seen: new Date().toISOString() } }, { upsert: true }); },
  };
}
function identityMatches(draft: DiagnosticDraftEnvelope, id: ProgressIdentity): boolean {
  return draft.version === 4 && reviewerIdentity(draft.reviewer) === reviewerIdentity(id.reviewer) && draft.pilotSha === id.pilotSha && draft.protocolSha === id.protocolSha && draft.scope === id.scope && draft.assistanceMode === (id.scope === "primary-60" ? "ai_assisted" : "human_only");
}
export function checkProgressDraft(value: unknown, id: ProgressIdentity, keys: Set<string>): asserts value is DiagnosticDraftEnvelope {
  if (!value || typeof value !== "object") throw new ProgressError("Tiến độ không hợp lệ.", 400);
  const d = value as DiagnosticDraftEnvelope;
  if (typeof d.reviewer !== "string" || !identityMatches(d, id)) throw new ProgressError("Reviewer, scope hoặc pilot không khớp.");
  if (!d.answers || typeof d.answers !== "object" || Array.isArray(d.answers) || !d.humanEdits || typeof d.humanEdits !== "object" || Array.isArray(d.humanEdits)) throw new ProgressError("Thiếu dữ liệu tiến độ.", 400);
  const template = emptyDiagnosticJudgment();
  for (const [key, row] of Object.entries(d.answers)) {
    if (!keys.has(key) || !row || typeof row !== "object" || Array.isArray(row)) throw new ProgressError("Item ngoài phạm vi pilot.", 400);
    for (const [field, sample] of Object.entries(template)) {
      const v = row[field as keyof typeof row];
      if (Array.isArray(sample) ? !Array.isArray(v) : typeof v !== typeof sample) throw new ProgressError("Trường đánh giá không hợp lệ.", 400);
    }
    if (row.review_scope && row.review_scope !== id.scope || row.review_assistance_mode && row.review_assistance_mode !== d.assistanceMode) throw new ProgressError("Provenance đánh giá không khớp.", 400);
    if (row.observed_issues.some(v=>typeof v!=="string") || row.diagnostic_labels.some(v=>typeof v!=="string") || row.diagnostic_support.some(v=>!v || typeof v!=="object" || [v.label,v.status,v.evidence_reference,v.contrast_id].some(s=>typeof s!=="string"))) throw new ProgressError("Cấu trúc nhãn không hợp lệ.",400);
  }
  for (const [key, edit] of Object.entries(d.humanEdits)) {
    if (!keys.has(key) || !d.answers[key] || !edit || typeof edit.editedBy !== "string" || reviewerIdentity(edit.editedBy) !== reviewerIdentity(id.reviewer) || edit.editedAt !== null && (typeof edit.editedAt !== "string" || !Number.isFinite(Date.parse(edit.editedAt)))) throw new ProgressError("Thông tin người chỉnh sửa không khớp.", 400);
  }
}
async function readRecord(id: ProgressIdentity, keys: Set<string>, repo: ProgressPersistence): Promise<DiagnosticProgressRecord | null> {
  const record = await repo.read(recordKey(id));
  if (!record) return null;
  if (record.schema_version !== 1 || !Number.isInteger(record.revision) || record.revision < 1 || typeof record.saved_at !== "string") throw new ProgressError("Tiến độ trong database không hợp lệ; không được ghi đè.");
  checkProgressDraft(record.draft, id, keys);
  return record;
}
export async function loadDiagnosticProgress(id: ProgressIdentity, keys: Set<string>, persistence?: ProgressPersistence): Promise<DiagnosticProgressRecord | null> {
  const repo = persistence ?? mongoProgressPersistence(await getDb());
  if (id.scope === "independent-15" && await repo.hasExposure(reviewerHash(id.reviewer))) throw new ProgressError("Reviewer này đã mở gợi ý AI ở Primary; cần người khác cho Independent-15.");
  return readRecord(id, keys, repo);
}
export async function saveDiagnosticProgress(id: ProgressIdentity, keys: Set<string>, draft: unknown, expectedRevision: number, persistence?: ProgressPersistence): Promise<DiagnosticProgressRecord> {
  checkProgressDraft(draft, id, keys);
  if (!Number.isInteger(expectedRevision) || expectedRevision < 0) throw new ProgressError("Thiếu revision để lưu an toàn.", 400);
  const repo = persistence ?? mongoProgressPersistence(await getDb());
  const current = await loadDiagnosticProgress(id, keys, repo);
  if ((current?.revision ?? 0) !== expectedRevision) throw new ProgressError("Tiến độ đã được cập nhật ở tab/máy khác. Tải tiến độ mới trước khi lưu tiếp.");
  if (id.scope === "primary-60") await repo.markExposure(reviewerHash(id.reviewer));
  const { serverRevision: _revision, serverSavedAt: _saved, pendingKeys: _pending, ...clean } = draft;
  void _revision; void _saved; void _pending;
  const record: DiagnosticProgressRecord = { schema_version: 1, revision: expectedRevision + 1, saved_at: new Date().toISOString(), draft: clean };
  await repo.write(recordKey(id), record, expectedRevision);
  return record;
}
