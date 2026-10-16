import { describe, expect, test } from "bun:test";
import type { Db } from "mongodb";
import { emptyDiagnosticJudgment } from "./diagnostic-review.ts";
import type { DiagnosticDraftEnvelope } from "./diagnostic-store.ts";
import type { DiagnosticProgressRecord } from "./diagnostic-progress.ts";
import { loadDiagnosticProgress, mongoProgressPersistence, saveDiagnosticProgress, type ProgressIdentity } from "./diagnostic-progress-server.ts";
const id:ProgressIdentity={reviewer:"Nguyễn A",pilotSha:"p",protocolSha:"h",scope:"primary-60"};
function draft(identity=id):DiagnosticDraftEnvelope{return{version:4,...identity,assistanceMode:identity.scope==="primary-60"?"ai_assisted":"human_only",answers:{one:{...emptyDiagnosticJudgment(),review_scope:identity.scope,review_assistance_mode:identity.scope==="primary-60"?"ai_assisted":"human_only"}},humanEdits:{one:{editedBy:identity.reviewer,editedAt:"2026-10-15T00:00:00Z"}},pendingKeys:["one"]};}
const keys=new Set(["one"]);
function fixture(){
 const records=new Map<string,DiagnosticProgressRecord & {_id:string}>(), exposures=new Set<string>();
 const db={collection:(name:string)=> name==="diagnostic_progress"?{
  findOne:async(q:{_id:string})=>structuredClone(records.get(q._id)??null),
  insertOne:async(doc:DiagnosticProgressRecord & {_id:string})=>{if(records.has(doc._id))throw Object.assign(new Error("duplicate"),{code:11000});records.set(doc._id,structuredClone(doc));return{acknowledged:true};},
  replaceOne:async(q:{_id:string;revision:number},doc:DiagnosticProgressRecord & {_id:string})=>{if(records.get(q._id)?.revision!==q.revision)return{matchedCount:0};records.set(q._id,structuredClone({...doc,_id:q._id}));return{matchedCount:1};},
 }:{findOne:async(q:{_id:string})=>exposures.has(q._id)?{_id:q._id}:null,updateOne:async(q:{_id:string})=>{exposures.add(q._id);return{acknowledged:true};}}};
 return{records,exposures,repo:mongoProgressPersistence(db as unknown as Db)};
}
describe("MongoDB reviewer progress",()=>{
 test("roundtrip survives client recreation and uses case-normalized distinct reviewer identities",async()=>{
  const{repo,records}=fixture();expect(await loadDiagnosticProgress(id,keys,repo)).toBe(null);
  const saved=await saveDiagnosticProgress(id,keys,draft(),0,repo);expect(saved.revision).toBe(1);expect(saved.draft.pendingKeys).toBeUndefined();
  expect((await loadDiagnosticProgress({...id,reviewer:"  nguyễn a "},keys,repo))?.draft.humanEdits?.one.editedBy).toBe("Nguyễn A");
  expect(await loadDiagnosticProgress({...id,reviewer:"Nguyen A"},keys,repo)).toBe(null);
  expect(await loadDiagnosticProgress({...id,reviewer:"Other"},keys,repo)).toBe(null);
  expect([...records.keys()][0]).not.toContain("Nguyễn");
 });
 test("stale and simultaneous creators cannot overwrite accepted progress",async()=>{
  const{repo}=fixture();const results=await Promise.allSettled([saveDiagnosticProgress(id,keys,draft(),0,repo),saveDiagnosticProgress(id,keys,draft(),0,repo)]);
  expect(results.filter(r=>r.status==="fulfilled")).toHaveLength(1);expect(results.filter(r=>r.status==="rejected")).toHaveLength(1);
  await expect(saveDiagnosticProgress(id,keys,draft(),0,repo)).rejects.toThrow("tab/máy khác");
  expect((await loadDiagnosticProgress(id,keys,repo))?.revision).toBe(1);
 });
 test("two DB writers racing the same revision are serialized by atomic compare-and-replace",async()=>{
  const{repo}=fixture();await saveDiagnosticProgress(id,keys,draft(),0,repo);
  const results=await Promise.allSettled([saveDiagnosticProgress(id,keys,draft(),1,repo),saveDiagnosticProgress(id,keys,draft(),1,repo)]);
  expect(results.filter(r=>r.status==="fulfilled")).toHaveLength(1);expect(results.filter(r=>r.status==="rejected")).toHaveLength(1);
  expect((await loadDiagnosticProgress(id,keys,repo))?.revision).toBe(2);
 });
 test("invalid identity, scope and edit provenance fail before writes",async()=>{
  const{repo,records}=fixture();await expect(saveDiagnosticProgress(id,keys,draft({...id,reviewer:"B"}),0,repo)).rejects.toThrow("không khớp");
  await expect(saveDiagnosticProgress(id,new Set(),draft(),0,repo)).rejects.toThrow("ngoài phạm vi");
  const bad=draft();bad.humanEdits!.one.editedBy="Someone else";await expect(saveDiagnosticProgress(id,keys,bad,0,repo)).rejects.toThrow("người chỉnh sửa");expect(records.size).toBe(0);
 });
 test("AI exposure follows identity across clients and pilot revisions",async()=>{
  const{repo}=fixture();await saveDiagnosticProgress(id,keys,draft(),0,repo);
  const independent={...id,scope:"independent-15" as const,protocolSha:"new"};
  await expect(loadDiagnosticProgress(independent,keys,repo)).rejects.toThrow("đã mở gợi ý AI");
  await expect(saveDiagnosticProgress(independent,keys,draft(independent),0,repo)).rejects.toThrow("đã mở gợi ý AI");
  const other={...independent,reviewer:"B"};expect((await saveDiagnosticProgress(other,keys,draft(other),0,repo)).draft.scope).toBe("independent-15");
 });
 test("corrupt DB records fail closed and remain unchanged",async()=>{
  const{repo,records}=fixture();await saveDiagnosticProgress(id,keys,draft(),0,repo);
  const key=[...records.keys()][0];records.get(key)!.schema_version=99 as 1;
  await expect(saveDiagnosticProgress(id,keys,draft(),1,repo)).rejects.toThrow("không được ghi đè");expect(records.get(key)!.schema_version).toBe(99);
 });
});
