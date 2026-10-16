"use client";
import { useEffect, useRef, useState } from "react";
import { useDiagnosticStore, type DiagnosticDraftEnvelope } from "@/lib/diagnostic-store.ts";
import { acknowledgeDiagnosticSave, type DiagnosticProgressRecord } from "@/lib/diagnostic-progress.ts";
export function progressUrl(draft: Pick<DiagnosticDraftEnvelope,"reviewer"|"scope"|"pilotSha"|"protocolSha">): string {
  return `/api/diagnostic-progress?${new URLSearchParams({reviewer:draft.reviewer,scope:draft.scope,pilot_sha:draft.pilotSha,protocol_sha:draft.protocolSha})}`;
}
export async function readProgressResponse(response: Response): Promise<DiagnosticProgressRecord | null> {
  const body=await response.json() as {record?:DiagnosticProgressRecord|null;error?:string};
  if(!response.ok || !("record" in body)) throw new Error(body.error ?? "Không đồng bộ được tiến độ.");
  return body.record ?? null;
}
export async function postDiagnosticProgress(draft: DiagnosticDraftEnvelope): Promise<DiagnosticProgressRecord> {
  const record=await readProgressResponse(await fetch(progressUrl(draft),{method:"POST",signal:AbortSignal.timeout(10_000),headers:{"Content-Type":"application/json"},body:JSON.stringify({draft,expectedRevision:draft.serverRevision ?? 0})}));
  if(!record)throw new Error("Server chưa xác nhận lưu tiến độ.");
  return record;
}
export function useDiagnosticProgressSync(key: string) {
  const draft=useDiagnosticStore(state=>state.drafts[key]);
  const [failure,setFailure]=useState<{key:string;message:string}|null>(null);
  const [retry,setRetry]=useState(0);
  const busy=useRef(new Set<string>());
  const error=failure?.key===key?failure.message:"";
  useEffect(()=>{
    if(!key || !draft?.pendingKeys?.length || error)return;
    const timer=setTimeout(()=>{
      if(busy.current.has(key))return;
      busy.current.add(key);
      void postDiagnosticProgress(draft).then(record=>{
        const current=useDiagnosticStore.getState().drafts[key];
        if(current)useDiagnosticStore.getState().saveDraft(key,acknowledgeDiagnosticSave(current,draft,record));
      }).catch((e)=>{setFailure({key,message:e instanceof Error?e.message:"Không đồng bộ được tiến độ."});})
        .finally(()=>{busy.current.delete(key);});
    },500);
    return ()=>clearTimeout(timer);
  },[key,draft,error,retry]);
  useEffect(()=>{
    if(!draft?.pendingKeys?.length)return;
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();};
    window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);
  },[draft?.pendingKeys?.length]);
  return {error,retry:()=>{setFailure(null);setRetry(value=>value+1);},pending:!!draft?.pendingKeys?.length};
}
