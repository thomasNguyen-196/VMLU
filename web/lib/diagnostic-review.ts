import { DIAGNOSTIC_LABELS, OBSERVED_ISSUES } from "./diagnostic-taxonomy.ts";
export interface DiagnosticPilotRow {
  observation_key: string;
  item_key: string;
  dataset_id: string;
  item_id: string;
  replicate_id: string;
  source_run_id: string;
  source_manifest_sha256: string;
  prompt_sha256: string;
  task_mode: string;
  question: string;
  rendered_input: string;
  raw_response: string;
  prediction: string;
  source_gold: string;
  source_metrics: Record<string, number | string | null>;
  finish_reason: string | null;
  passage_group: string | null;
  selection_reason: string;
  exposure: string;
  protocol_sha256: string;
  rubric_version: string;
  packet_sha256: string;
}

export interface DiagnosticSupport {
  label: string;
  status: "hypothesis" | "contrast_supported";
  evidence_reference: string;
  contrast_id: string;
}
export interface VerifiedContrast { contrast_id: string; observation_key: string; label: string; kind?: "controlled_model_contrast" | "deterministic_replay" }
export interface DiagnosticJudgment {
  review_scope: "" | "primary-60" | "independent-15";
  review_assistance_mode: "" | "human_only" | "ai_assisted";
  semantic_correctness: "" | "correct" | "incorrect" | "uncertain";
  gold_validity: "" | "valid" | "suspect" | "unassessable";
  input_evidence_sufficiency: "" | "sufficient" | "insufficient" | "unassessable" | "not_applicable";
  corpus_evidence_availability: "" | "not_assessed" | "present" | "absent" | "not_applicable";
  corpus_evidence_reference: string;
  diagnostic_outcome: "" | "no_observed_issue" | "issue_observed" | "unresolved";
  observed_issues: string[];
  audit_evidence_kind: "" | "input_span" | "source_comparison" | "derivation" | "raw_output" | "parser_replay" | "unavailable";
  evidence_reference: string;
  diagnostic_labels: string[];
  diagnostic_support: DiagnosticSupport[];
  rationale: string;
  reviewer_attestation: boolean;
  blind_review_attestation: boolean;
  review_status: "" | "reviewed" | "deferred";
}
export const REVIEWER_ATTESTATION = "I attest that these are my independent human judgments.";
export const AI_ASSISTED_ATTESTATION = "I reviewed the AI suggestions and affirm my final human judgments.";
export const BLIND_ATTESTATION = "I have not seen AI suggestions or other reviewer judgments for this pilot.";
export function normalizeDiagnosticDisplayText(value: string): string { return value.normalize("NFC"); }
export function diagnosticDraftKey(pilotSha: string, protocolSha: string, reviewer: string, scope: "primary-60" | "independent-15", revision: 1 | 2 | 3 | 4 = 4): string {
  return `vmlu.diagnostic.v${revision}:${pilotSha}:${protocolSha}:${scope}:${encodeURIComponent(reviewer.trim().toLocaleLowerCase())}`;
}
export function previousDiagnosticDraftBackup(raw: string | null, expected: {
  reviewer: string; scope: "primary-60" | "independent-15"; pilotSha: string; protocolSha: string; observationKeys: string[]; revision: 1 | 2 | 3;
}): string | null {
  if (!raw) return null;
  try {
    const old = JSON.parse(raw);
    if (old.version !== expected.revision || old.scope !== expected.scope || typeof old.reviewer !== "string" || old.reviewer.trim().toLocaleLowerCase() !== expected.reviewer.trim().toLocaleLowerCase() || old.pilotSha !== expected.pilotSha || old.protocolSha !== expected.protocolSha || !old.answers || typeof old.answers !== "object" || Array.isArray(old.answers)) return null;
    if (Object.keys(old.answers).some((key) => !expected.observationKeys.includes(key))) return null;
    return raw;
  } catch { return null; }
}
export function emptyDiagnosticJudgment(): DiagnosticJudgment {
  return { review_scope: "", review_assistance_mode: "", semantic_correctness: "", gold_validity: "", input_evidence_sufficiency: "", corpus_evidence_availability: "", corpus_evidence_reference: "", diagnostic_outcome: "", observed_issues: [], audit_evidence_kind: "", evidence_reference: "", diagnostic_labels: [], diagnostic_support: [], rationale: "", reviewer_attestation: false, blind_review_attestation: false, review_status: "" };
}
export function diagnosticReviewErrors(row: DiagnosticJudgment, contrasts: VerifiedContrast[] = [], observationKey?: string): string[] {
  const errors: string[] = [];
  const required: Array<[unknown, string[], string]> = [
    [row.review_scope, ["primary-60", "independent-15"], "Phạm vi review"],
    [row.review_assistance_mode, ["human_only", "ai_assisted"], "Provenance hỗ trợ"],
    [row.semantic_correctness, ["correct", "incorrect", "uncertain"], "Đúng về ngữ nghĩa"],
    [row.gold_validity, ["valid", "suspect", "unassessable"], "Gold gốc"],
    [row.input_evidence_sufficiency, ["sufficient", "insufficient", "unassessable", "not_applicable"], "Dữ kiện trong input"],
    [row.corpus_evidence_availability, ["not_assessed", "present", "absent", "not_applicable"], "Evidence trong corpus"],
    [row.diagnostic_outcome, ["no_observed_issue", "issue_observed", "unresolved"], "Kết luận audit"],
    [row.audit_evidence_kind, ["input_span", "source_comparison", "derivation", "raw_output", "parser_replay", "unavailable"], "Loại bằng chứng audit"],
    [row.review_status, ["reviewed", "deferred"], "Trạng thái review"],
  ];
  for (const [value, allowed, label] of required) if (!allowed.includes(String(value))) errors.push(`Chọn ${label}.`);
  if (!row.evidence_reference.trim()) errors.push("Ghi đoạn/câu/phép tính hoặc phần bằng chứng audit còn thiếu.");
  if (!row.rationale.trim()) errors.push("Ghi lý do audit.");
  if (!row.reviewer_attestation) errors.push("Xác nhận kết luận cuối của reviewer.");
  if (["present", "absent"].includes(row.corpus_evidence_availability) && !row.corpus_evidence_reference.trim()) errors.push("Evidence corpus cần tham chiếu riêng đến corpus/document/version.");
  if (row.review_scope === "independent-15" && (row.review_assistance_mode !== "human_only" || !row.blind_review_attestation)) errors.push("Review độc lập cần human-only và xác nhận chưa xem gợi ý/nhãn khác.");
  if (row.review_scope === "primary-60" && row.blind_review_attestation) errors.push("Primary không ký xác nhận review độc lập mù.");
  const issues = row.observed_issues;
  const labels = row.diagnostic_labels;
  if (issues.some((v) => !OBSERVED_ISSUES.some(([id]) => id === v)) || new Set(issues).size !== issues.length) errors.push("Biểu hiện lỗi không hợp lệ/trùng.");
  if (labels.some((v) => !DIAGNOSTIC_LABELS.some(([id]) => id === v)) || new Set(labels).size !== labels.length) errors.push("Giả thuyết nguyên nhân không hợp lệ/trùng.");
  if (row.diagnostic_outcome === "no_observed_issue" && (issues.length || labels.length || row.diagnostic_support.length || row.semantic_correctness !== "correct" || row.gold_validity !== "valid" || row.review_status !== "reviewed")) errors.push("Không phát hiện vấn đề: đáp án đúng, gold hợp lệ, đã review; không có issue/cause/support.");
  if (row.diagnostic_outcome === "issue_observed" && (!issues.length || row.review_status !== "reviewed")) errors.push("Có vấn đề: chọn biểu hiện quan sát và đã review; nguyên nhân có thể chưa rõ.");
  if (row.diagnostic_outcome === "unresolved" && (issues.length || labels.length || row.diagnostic_support.length || row.review_status !== "deferred")) errors.push("Chưa kết luận: tạm hoãn và không ép issue/cause.");
  if (row.diagnostic_outcome !== "unresolved" && row.audit_evidence_kind === "unavailable") errors.push("Audit hoàn tất cần bằng chứng đối chiếu sẵn có.");
  if (row.diagnostic_support.length !== labels.length || labels.some((label) => row.diagnostic_support.filter((v) => v.label === label).length !== 1)) errors.push("Mỗi giả thuyết phải có đúng một support riêng.");
  for (const support of row.diagnostic_support) {
    if (!labels.includes(support.label) || !support.evidence_reference.trim() || !["hypothesis", "contrast_supported"].includes(support.status)) errors.push("Giả thuyết cần support và tham chiếu riêng.");
    if (support.status === "hypothesis" && support.contrast_id) errors.push("Giả thuyết chưa đối chiếu không gắn contrast_id.");
    if (support.status === "contrast_supported") {
      if (!contrasts.some((c) => c.contrast_id === support.contrast_id && c.label === support.label && c.observation_key === observationKey)) errors.push("Chưa có đối chiếu/replay đã xác minh cho giả thuyết này.");
      if (! ["external_evidence_gap", "parser_gap", "measurement_gap", "context_assembly_gap"].includes(support.label) && !contrasts.some((c) => c.contrast_id === support.contrast_id && c.kind === "controlled_model_contrast")) errors.push("Giả thuyết này cần controlled model probes; replay chỉ hỗ trợ một số lỗi component/evidence.");
      if (["reasoning_gap", "reading_representation_gap", "instruction_gap", "generator_evidence_use_gap"].includes(support.label) && row.input_evidence_sufficiency !== "sufficient") errors.push("Giả thuyết này cần đủ premises trong input.");
      if (["retrieval_gap", "context_assembly_gap"].includes(support.label) && row.corpus_evidence_availability !== "present") errors.push("Retrieval/assembly cần corpus có evidence.");
      if (support.label === "external_evidence_gap" && row.input_evidence_sufficiency !== "insufficient") errors.push("Thiếu evidence ngoài cần ghi rõ input thiếu dữ kiện.");
    }
  }
  return errors;
}
export function isDiagnosticReviewComplete(row: DiagnosticJudgment, contrasts: VerifiedContrast[] = [], observationKey?: string): boolean {
  return diagnosticReviewErrors(row, contrasts, observationKey).length === 0;
}
function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}
export function serializeDiagnosticReviewCsv(rows: DiagnosticPilotRow[], judgments: Record<string, DiagnosticJudgment>, annotatorId: string, scope: "primary-60" | "independent-15" = "primary-60", contrasts: VerifiedContrast[] = []): string {
  return [REVIEW_COLUMNS.join(","), ...rows.map((row) => {
    const judgment = judgments[row.observation_key];
    const complete = Boolean(judgment && isDiagnosticReviewComplete(judgment, contrasts, row.observation_key) && judgment.review_scope === scope);
    const fields: Record<string, unknown> = { ...row, annotator_id: annotatorId, review_scope: scope };
    for (const column of REVIEW_JUDGMENT_COLUMNS) {
      if (column === "annotator_id" || column === "review_scope") continue;
      fields[column] = complete ? judgment![column as keyof DiagnosticJudgment] : "";
    }
    if (complete) {
      fields.observed_issues = [...judgment!.observed_issues].sort().join(";");
      fields.diagnostic_labels = [...judgment!.diagnostic_labels].sort().join(";");
      fields.reviewer_attestation = judgment!.review_assistance_mode === "ai_assisted" ? AI_ASSISTED_ATTESTATION : REVIEWER_ATTESTATION;
      fields.blind_review_attestation = scope === "independent-15" && judgment!.blind_review_attestation ? BLIND_ATTESTATION : "";
    }
    return REVIEW_COLUMNS.map((column) => csvCell(fields[column])).join(",");
  })].join("\r\n");
}

export const REVIEW_IMMUTABLE_COLUMNS = ["observation_key", "item_key", "dataset_id", "item_id", "replicate_id", "source_run_id", "source_manifest_sha256", "prompt_sha256", "task_mode", "question", "rendered_input", "raw_response", "prediction", "source_gold", "source_metrics", "finish_reason", "passage_group", "selection_reason", "exposure", "protocol_sha256", "rubric_version", "packet_sha256"] as const;
export const REVIEW_JUDGMENT_COLUMNS = ["annotator_id", "review_scope", "review_assistance_mode", "semantic_correctness", "gold_validity", "input_evidence_sufficiency", "corpus_evidence_availability", "corpus_evidence_reference", "diagnostic_outcome", "observed_issues", "audit_evidence_kind", "evidence_reference", "diagnostic_labels", "diagnostic_support", "rationale", "reviewer_attestation", "blind_review_attestation", "review_status"] as const;
export const REVIEW_COLUMNS = [...REVIEW_IMMUTABLE_COLUMNS, ...REVIEW_JUDGMENT_COLUMNS] as const;
