import { describe, expect, test } from "bun:test";
import { emptyDiagnosticJudgment, type DiagnosticJudgment } from "./diagnostic-review.ts";
import { acknowledgeDiagnosticSave, diagnosticProgressStatus, restoreDiagnosticProgress, withLegacyHumanEdits, type DiagnosticProgressRecord } from "./diagnostic-progress.ts";
import type { DiagnosticDraftEnvelope } from "./diagnostic-store.ts";
const proposal: DiagnosticJudgment = {...emptyDiagnosticJudgment(),review_scope:"primary-60",review_assistance_mode:"ai_assisted",semantic_correctness:"correct",gold_validity:"valid",input_evidence_sufficiency:"sufficient",corpus_evidence_availability:"not_assessed",diagnostic_outcome:"no_observed_issue",audit_evidence_kind:"input_span",evidence_reference:"Câu 1",rationale:"Gợi ý AI"};
const edit={editedBy:"A",editedAt:"2026-10-15T10:00:00Z"};
const base=():DiagnosticDraftEnvelope=>({version:4,pilotSha:"p",protocolSha:"h",reviewer:"A",scope:"primary-60",assistanceMode:"ai_assisted",answers:{one:proposal},humanEdits:{},pendingKeys:[]});
const record=(draft:DiagnosticDraftEnvelope,revision=1):DiagnosticProgressRecord=>({schema_version:1,revision,saved_at:"2026-10-15T10:01:00Z",draft});
describe("human progress, distinct from AI proposal and audit submission",()=>{
 test("prefilled AI rows are unreviewed and only human edits count as in progress",()=>{
  expect(diagnosticProgressStatus(proposal,undefined)).toBe("unreviewed");
  expect(diagnosticProgressStatus(proposal,edit)).toBe("in-progress");
  expect(diagnosticProgressStatus({...proposal,review_status:"reviewed",reviewer_attestation:true},edit)).toBe("reviewed");
  expect(diagnosticProgressStatus({...proposal,review_status:"reviewed",reviewer_attestation:false},edit)).toBe("in-progress");
  expect(diagnosticProgressStatus({...proposal,diagnostic_outcome:"unresolved",semantic_correctness:"uncertain",review_status:"deferred",reviewer_attestation:true},edit)).toBe("deferred");
 });
 test("legacy AI-only cache creates no human progress; changed values retain unknown edit time",()=>{
  const {humanEdits:_edits,...legacy}=base();void _edits;
  expect(withLegacyHumanEdits(legacy,{one:proposal}).humanEdits).toEqual({});
  const result=withLegacyHumanEdits({...legacy,answers:{one:{...proposal,rationale:"Tôi kiểm tra lại"}}},{one:proposal});
  expect(result.humanEdits?.one).toEqual({editedBy:"A",editedAt:null});
  expect(result.answers.one.reviewer_attestation).toBe(false);
 });
 test("server restores progress without a browser cache and overlays only known unsynced keys",()=>{
  const remote={...base(),humanEdits:{one:edit}};
  expect(restoreDiagnosticProgress(undefined,record(remote))?.humanEdits).toEqual({one:edit});
  const local={...base(),serverRevision:1,pendingKeys:["one"],answers:{one:{...proposal,rationale:"new"}},humanEdits:{one:edit}};
  expect(restoreDiagnosticProgress(local,record(remote))?.answers.one.rationale).toBe("new");
  expect(()=>restoreDiagnosticProgress(local,record(remote,2))).toThrow("server đã khác");
 });
 test("late save acknowledgments never clear edits typed while saving",()=>{
  const sent={...base(),serverRevision:1,pendingKeys:["one"],humanEdits:{one:edit}};
  const newer={...sent,answers:{one:{...proposal,rationale:"More typing"}}};
  const ack=acknowledgeDiagnosticSave(newer,sent,record(sent,2));
  expect(ack.pendingKeys).toEqual(["one"]);expect(ack.answers.one.rationale).toBe("More typing");
  expect(acknowledgeDiagnosticSave(sent,sent,record(sent,2)).pendingKeys).toEqual([]);
 });
});
