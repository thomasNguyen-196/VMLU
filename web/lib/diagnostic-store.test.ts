import { expect, test } from "bun:test";
import { createDiagnosticStore, type DiagnosticDraftEnvelope } from "./diagnostic-store.ts";
import { diagnosticDraftKey, emptyDiagnosticJudgment } from "./diagnostic-review.ts";
test("Zustand v4 persists scoped drafts and hydration while leaving v3 storage untouched",async()=>{
 const values=new Map<string,string>(); const storage={getItem:(k:string)=>values.get(k)??null,setItem:(k:string,v:string)=>{values.set(k,v);},removeItem:(k:string)=>{values.delete(k);}};
 values.set("vmlu.diagnostic.v3.zustand","old-human-draft-backup");
 const useDiagnosticStore = createDiagnosticStore(storage);
 useDiagnosticStore.setState({drafts:{},assistantSeen:{}});
 const key=diagnosticDraftKey("p4","h4","A","primary-60");
 const draft:DiagnosticDraftEnvelope={version:4,pilotSha:"p4",protocolSha:"h4",reviewer:"A",scope:"primary-60",assistanceMode:"ai_assisted",answers:{one:emptyDiagnosticJudgment()}};
 useDiagnosticStore.getState().saveDraft(key,draft);useDiagnosticStore.getState().markAssistantSeen("A");
 const saved=values.get("vmlu.diagnostic.v4.zustand")!;expect(saved).toContain(key);
 useDiagnosticStore.setState({drafts:{},assistantSeen:{}});values.set("vmlu.diagnostic.v4.zustand",saved);
 await useDiagnosticStore.persist.rehydrate();
 expect(useDiagnosticStore.getState().drafts[key]).toEqual(draft);expect(useDiagnosticStore.getState().hasSeenAssistant(" a ")).toBe(true);
 expect(useDiagnosticStore.getState().drafts[diagnosticDraftKey("p4","h4","B","primary-60")]).toBeUndefined();
 expect(useDiagnosticStore.getState().drafts[diagnosticDraftKey("p4","h4","A","independent-15")]).toBeUndefined();
 expect(values.get("vmlu.diagnostic.v3.zustand")).toBe("old-human-draft-backup");
});
