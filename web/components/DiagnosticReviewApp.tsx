"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { diagnosticDraftKey, diagnosticReviewErrors, isDiagnosticReviewComplete, normalizeDiagnosticDisplayText, normalizeDiagnosticJudgment, previousDiagnosticDraftBackup, serializeDiagnosticReviewCsv, stripAssistantRationaleMeta, emptyDiagnosticJudgment, type VerifiedContrast, type DiagnosticJudgment, type DiagnosticPilotRow } from "@/lib/diagnostic-review.ts";
import { DIAGNOSTIC_LABELS, OBSERVED_ISSUES } from "@/lib/diagnostic-taxonomy.ts";
import { diagnosticProgressStatus, withLegacyHumanEdits, restoreDiagnosticProgress, acknowledgeDiagnosticSave, type HumanEdit } from "@/lib/diagnostic-progress.ts";
import { progressUrl, readProgressResponse, postDiagnosticProgress, useDiagnosticProgressSync } from "@/components/hooks/use-diagnostic-progress-sync.ts";
import { useDiagnosticStore, type DiagnosticDraftEnvelope, type DiagnosticScope } from "@/lib/diagnostic-store.ts";

export type PilotRow = DiagnosticPilotRow;
type Scope = DiagnosticScope;
type Judgment = DiagnosticJudgment;
export interface AssistantSuggestion {
  observation_key: string;
  proposal: Omit<Judgment, "review_scope" | "review_assistance_mode" | "reviewer_attestation" | "blind_review_attestation" | "review_status">;
  confidence: "low" | "medium" | "high";
  basis: string;
}

const EMPTY_ANSWERS: Record<string, Judgment> = {};
const EMPTY_EDITS: Record<string, HumanEdit> = {};
const emptyJudgment = emptyDiagnosticJudgment;
function suggestionJudgment(suggestion: AssistantSuggestion): Judgment {
  return { ...emptyJudgment(), ...suggestion.proposal, rationale: stripAssistantRationaleMeta(suggestion.proposal.rationale), review_scope: "primary-60", review_assistance_mode: "ai_assisted", reviewer_attestation: false, blind_review_attestation: false, review_status: "" };
}
const complete = isDiagnosticReviewComplete;
/** Outcome is the only control that drives the rest of the panel: review_status is
 * fully implied by it, and "no issue" is only valid with correct semantics + valid gold. */
const OUTCOME_OPTIONS: Array<[NonNullable<Judgment["diagnostic_outcome"]>, string, string]> = [
  ["no_observed_issue", "Không phát hiện vấn đề", "Đáp án đúng, gold hợp lệ — không có biểu hiện lỗi"],
  ["issue_observed", "Có vấn đề được quan sát", "Có ít nhất một biểu hiện lỗi; nguyên nhân có thể chưa rõ"],
  ["unresolved", "Chưa thể kết luận", "Thiếu hoặc xung đột bằng chứng — tạm hoãn, không ép gán"],
];
/** Revision 4 has no versioned corpus, so these hypotheses have no premises to stand on. */
const CORPUS_DEPENDENT_LABELS = new Set(["retrieval_gap", "context_assembly_gap"]);
function datasetName(id: string): string {
  if (id.endsWith("legal-mc-146")) return "Legal MC";
  if (id.endsWith("legal-nli-150")) return "Legal NLI";
  if (id.endsWith("vi-squad-200")) return "Vi-SQuAD";
  if (id.endsWith("vi-drop-200")) return "Vi-DROP";
  if (id.endsWith("bidlqa-test")) return "ViBidLQA";
  return id;
}

export default function DiagnosticReviewApp({ rows, pilotSha, protocolSha, selection, previousRevisions, verifiedContrasts }: {
  rows: PilotRow[]; pilotSha: string; protocolSha: string; selection: Record<string, unknown>; verifiedContrasts: VerifiedContrast[]; previousRevisions: Array<{ revision: 1 | 2 | 3; pilotSha: string; protocolSha: string }>;
}) {
  const [nameInput, setNameInput] = useState("");
  const [scopeInput, setScopeInput] = useState<Scope>("primary-60");
  const [session, setSession] = useState<{ reviewer: string; scope: Scope; assistanceMode: "human_only" | "ai_assisted" } | null>(null);
  const [starting, setStarting] = useState(false);
  const [storeHydrated, setStoreHydrated] = useState(false);
  const [index, setIndex] = useState(0);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [saveState, setSaveState] = useState("Chưa bắt đầu");
  const [exportMessage, setExportMessage] = useState("");
  const [gateError, setGateError] = useState("");
  const [previousDrafts, setPreviousDrafts] = useState<Array<{ revision: 1 | 2 | 3; raw: string }>>([]);
  const [suggestions, setSuggestions] = useState<AssistantSuggestion[]>([]);
  const [suggestionsState, setSuggestionsState] = useState<"hidden" | "loading" | "ready" | "error">("hidden");
  const activeDraftKey = session ? diagnosticDraftKey(pilotSha, protocolSha, session.reviewer, session.scope, 4) : "";
  const activeDraft = useDiagnosticStore((state) => state.drafts[activeDraftKey]);
  const answers = activeDraft?.answers ?? EMPTY_ANSWERS;
  const humanEdits = activeDraft?.humanEdits ?? EMPTY_EDITS;
  const sync = useDiagnosticProgressSync(activeDraftKey);
  const status = (row?: Judgment, contrasts: VerifiedContrast[] = [], key?: string) => diagnosticProgressStatus(row, key ? humanEdits[key] : undefined, contrasts, key);
  const secondKeys = useMemo(() => new Set((selection.second_review_keys as string[]) ?? []), [selection.second_review_keys]);
  const suggestionsByKey = useMemo(() => new Map(suggestions.map((row) => [row.observation_key, row])), [suggestions]);
  const persist = useCallback((target: { reviewer: string; scope: Scope; assistanceMode: "human_only" | "ai_assisted" }, nextAnswers: Record<string, Judgment>, editedKey: string) => {
    const key = diagnosticDraftKey(pilotSha, protocolSha, target.reviewer, target.scope, 4);
    const current = useDiagnosticStore.getState().drafts[key];
    const envelope: DiagnosticDraftEnvelope = { ...current, version: 4, pilotSha, protocolSha, ...target, answers: nextAnswers,
      humanEdits: { ...current?.humanEdits, [editedKey]: { editedBy: target.reviewer, editedAt: new Date().toISOString() } },
      pendingKeys: [...new Set([...(current?.pendingKeys ?? []), editedKey])],
    };
    try { useDiagnosticStore.getState().saveDraft(key, envelope); }
    catch { setSaveState("Không lưu được bản dự phòng trên trình duyệt — hãy xuất tiến độ ngay."); }
  }, [pilotSha, protocolSha]);
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        await useDiagnosticStore.persist.rehydrate();
      } catch {
        if (alive) setGateError("Không khôi phục được tiến độ trên trình duyệt; hãy tải lại trang.");
      } finally {
        if (alive) setStoreHydrated(true);
      }
    })();
    return () => { alive = false; };
  }, []);
  const scopeRows = useMemo(() => session?.scope === "independent-15" ? rows.filter((row) => secondKeys.has(row.observation_key)) : rows, [rows, session?.scope, secondKeys]);
  const visibleRows = scopeRows.filter((row) => {
    const rowStatus = status(answers[row.observation_key], verifiedContrasts, row.observation_key);
    const query = normalizeDiagnosticDisplayText(search.trim().toLocaleLowerCase());
    const matchesSearch = !query || normalizeDiagnosticDisplayText(`${row.dataset_id} ${row.item_id} ${row.question}`).toLocaleLowerCase().includes(query);
    return (filter === "all" || filter === rowStatus) && matchesSearch;
  });
  const current = scopeRows[index];
  const currentJudgment = current ? answers[current.observation_key] ?? emptyJudgment() : emptyJudgment();
  const currentErrors = diagnosticReviewErrors(currentJudgment, verifiedContrasts, current?.observation_key);
  const progressCounts = Object.fromEntries(["unreviewed", "in-progress", "reviewed", "deferred"].map(value => [value, scopeRows.filter(row => status(answers[row.observation_key], verifiedContrasts, row.observation_key) === value).length]));
  const completedCount = progressCounts.reviewed;
  const progressLabels = { unreviewed: "Chưa làm", "in-progress": "Đã chỉnh · chưa xác nhận", reviewed: "Đã hoàn tất", deferred: "Tạm hoãn" };
  const exportableCount = scopeRows.filter((row) => complete(answers[row.observation_key] ?? emptyJudgment(), verifiedContrasts, row.observation_key)).length;

  const update = (key: string, change: (old: Judgment) => Judgment) => {
    const assistanceMode = session?.scope === "primary-60" ? "ai_assisted" as const : "human_only" as const;
    // normalizeDiagnosticJudgment derives review_status from the outcome and pins the
    // corpus fields (no versioned corpus in this protocol), so the form never asks for them.
    const base: Judgment = { ...(answers[key] ?? emptyJudgment()), review_scope: session?.scope ?? "", review_assistance_mode: assistanceMode };
    const next = { ...answers, [key]: normalizeDiagnosticJudgment(change(base)) };
    if (session) persist(session, next, key);
  };
  const start = async () => {
    const reviewer = nameInput.trim();
    if (!reviewer || !storeHydrated || starting) return;
    setStarting(true);
    const assistanceMode = scopeInput === "primary-60" ? "ai_assisted" as const : "human_only" as const;
    const nextSession = { reviewer, scope: scopeInput, assistanceMode };
    const key = diagnosticDraftKey(pilotSha, protocolSha, reviewer, scopeInput, 4);
    let localDraft: DiagnosticDraftEnvelope | undefined;
    try {
      const state = useDiagnosticStore.getState();
      let saved = state.drafts[key];
      if (!saved) {
        const raw = localStorage.getItem(key);
        if (raw) saved = JSON.parse(raw) as DiagnosticDraftEnvelope;
      }
      if (saved) {
        if (saved.version !== 4 || saved.pilotSha !== pilotSha || saved.protocolSha !== protocolSha || saved.scope !== scopeInput || saved.assistanceMode !== assistanceMode || saved.reviewer.toLocaleLowerCase() !== reviewer.toLocaleLowerCase()) throw new Error("Reviewer/pilot mismatch");
        localDraft = saved;
        setSaveState("Đã tải tiến độ của reviewer");
      } else { setSaveState("Chưa có thao tác đánh giá của reviewer"); }
    } catch {
      setStarting(false);
      setGateError("Không đọc được tiến độ trong trình duyệt. Bản lưu được giữ nguyên để tải về đối chiếu.");
      return;
    }
    setPreviousDrafts([]);
    for (const previousRevision of previousRevisions) {
      try {
        const oldKey = diagnosticDraftKey(previousRevision.pilotSha, previousRevision.protocolSha, reviewer, scopeInput, previousRevision.revision);
        let raw = localStorage.getItem(oldKey);
        if (previousRevision.revision === 3) {
          const legacyStore = JSON.parse(localStorage.getItem("vmlu.diagnostic.v3.zustand") || "{}");
          const oldDraft = legacyStore.state?.drafts?.[oldKey];
          if (oldDraft) raw = JSON.stringify(oldDraft);
        }
        const backup = previousDiagnosticDraftBackup(raw, {
          reviewer, scope: scopeInput, ...previousRevision,
          observationKeys: rows.filter((row) => scopeInput === "primary-60" || secondKeys.has(row.observation_key)).map((row) => row.observation_key),
        });
        if (backup) setPreviousDrafts((current) => [...current, { revision: previousRevision.revision, raw: backup }]);
      } catch { /* Keep corrupt old drafts untouched; they never hydrate the current revision. */ }
    }
    const legacyAssistantSeenKey = `vmlu.diagnostic.v3:assistant-seen:${encodeURIComponent(reviewer.toLocaleLowerCase())}`;
    let legacyAssistantSeen = false;
    try {
      const oldStore = JSON.parse(localStorage.getItem("vmlu.diagnostic.v3.zustand") || "{}");
      legacyAssistantSeen = Boolean(localStorage.getItem(legacyAssistantSeenKey) || oldStore.state?.assistantSeen?.[reviewer.toLocaleLowerCase()]);
    } catch { /* The Zustand marker remains authoritative for new sessions. */ }
    if (scopeInput === "primary-60") {
      try { useDiagnosticStore.getState().markAssistantSeen(reviewer); } catch { setStarting(false); setGateError("Không lưu được trạng thái hỗ trợ AI trên trình duyệt này."); return; }
    } else if (useDiagnosticStore.getState().hasSeenAssistant(reviewer) || legacyAssistantSeen) {
      setStarting(false);
      setGateError("Reviewer này đã mở gợi ý AI ở scope primary nên không thể đồng thời làm reviewer độc lập.");
      return;
    }
    try {
      const identity = { reviewer, scope: scopeInput, pilotSha, protocolSha };
      const record = await readProgressResponse(await fetch(progressUrl(identity), { cache: "no-store", signal: AbortSignal.timeout(10_000) }));
      let loadedSuggestions: AssistantSuggestion[] = [];
      if (scopeInput === "primary-60") {
        const params = new URLSearchParams({ pilot_sha: pilotSha, protocol_sha: protocolSha });
        const response = await fetch(`/api/diagnostic-suggestions?${params}`, { cache: "no-store", signal: AbortSignal.timeout(10_000) });
        const body = await response.json();
        if (!response.ok || !Array.isArray(body.suggestions)) throw new Error("Không tải được gợi ý AI; tiến độ hiện có được giữ nguyên. Thử mở lại.");
        loadedSuggestions = body.suggestions;
      }
      const proposals = Object.fromEntries(loadedSuggestions.map(value => [value.observation_key, suggestionJudgment(value)]));
      const rawProposals = Object.fromEntries(loadedSuggestions.map(value => [value.observation_key, { ...suggestionJudgment(value), rationale: value.proposal.rationale }]));
      const assistantRationales = new Map(loadedSuggestions.map(value => [value.observation_key, value.proposal.rationale]));
      if (localDraft) localDraft = withLegacyHumanEdits(localDraft, rawProposals);
      let restored = restoreDiagnosticProgress(localDraft, record) ?? { version: 4 as const, ...identity, assistanceMode, answers: {}, humanEdits: {}, pendingKeys: [] };
      // Re-derive review_status and drop stale corpus citations from drafts written before
      // the form was simplified; otherwise those rows stay permanently "chưa hoàn tất".
      const filledAnswers: Record<string, Judgment> = {};
      for (const [key, row] of Object.entries(restored.answers)) {
        const normalized = normalizeDiagnosticJudgment(row);
        // Drafts saved before the cleanup still carry the raw AI rationale in section 6.
        // Only rewrite it when it is byte-identical to the assistant proposal; human edits
        // (including a rationale the reviewer chose to keep) are never touched.
        filledAnswers[key] = assistantRationales.get(key) === normalized.rationale
          ? { ...normalized, rationale: stripAssistantRationaleMeta(normalized.rationale) }
          : normalized;
      }
      for (const [key, proposal] of Object.entries(proposals)) if (!filledAnswers[key]) filledAnswers[key] = normalizeDiagnosticJudgment(proposal);
      restored = { ...restored, answers: filledAnswers };
      if (!record) {
        restored = { ...restored, serverRevision: 0 };
        const saved = await postDiagnosticProgress(restored);
        restored = acknowledgeDiagnosticSave(restored, restored, saved);
      }
      useDiagnosticStore.getState().saveDraft(key, restored);
      setSuggestions(loadedSuggestions); setSuggestionsState(scopeInput === "primary-60" ? "ready" : "hidden");
      setGateError("");
      const eligibleRows = rows.filter(row => scopeInput === "primary-60" || secondKeys.has(row.observation_key));
      const firstUnfinished = eligibleRows.findIndex(row => diagnosticProgressStatus(restored.answers[row.observation_key], restored.humanEdits?.[row.observation_key], verifiedContrasts, row.observation_key) !== "reviewed");
      setIndex(Math.max(0, firstUnfinished)); setSession(nextSession);
    } catch (error) { setGateError(error instanceof Error ? error.message : "Không tải được tiến độ server."); }
    finally { setStarting(false); }
  };
  const downloadLocalProgress = () => {
    const key = diagnosticDraftKey(pilotSha, protocolSha, nameInput, scopeInput, 4);
    const draft = useDiagnosticStore.getState().drafts[key];
    if (!draft) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(draft)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `diagnostic-progress-v4-${encodeURIComponent(nameInput)}.json`; link.click(); URL.revokeObjectURL(url);
  };
  const downloadCsv = () => {
    if (!session) return;
    const csv = serializeDiagnosticReviewCsv(scopeRows, answers, session.reviewer, session.scope, verifiedContrasts);
    const link = document.createElement("a");
    const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
    link.href = url;
    link.download = `diagnostic-review-v4-${session.scope}-${session.reviewer.replace(/[^\p{L}\p{N}_-]+/gu, "-")}.csv`;
    link.click(); URL.revokeObjectURL(url);
    setExportMessage(`Đã xuất ${scopeRows.length} dòng; ${exportableCount} dòng đã đủ trường để nhập.`);
  };

  const downloadPreviousDraft = (revision: number, raw: string) => {
    if (!session) return;
    const url = URL.createObjectURL(new Blob([raw], { type: "application/json;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url; link.download = `diagnostic-review-v${revision}-${session.scope}-${session.reviewer.replace(/[^\p{L}\p{N}_-]+/gu, "-")}.json`;
    link.click(); URL.revokeObjectURL(url);
  };
  const changeOutcome = (outcome: Judgment["diagnostic_outcome"]) => {
    if (!current || !outcome) return;
    update(current.observation_key, (old) => ({
      ...old, diagnostic_outcome: outcome,
      observed_issues: outcome === "issue_observed" ? old.observed_issues : [],
      diagnostic_labels: outcome === "issue_observed" ? old.diagnostic_labels : [],
      diagnostic_support: outcome === "issue_observed" ? old.diagnostic_support : [],
      // review_status is implied by the outcome on every completion rule, so it gets no control.
      review_status: outcome === "unresolved" ? "deferred" : "reviewed",
      // "no observed issue" is only valid with correct semantics and valid gold; the panel
      // states this instead of offering combinations the schema will reject.
      semantic_correctness: outcome === "no_observed_issue" ? "correct" : old.semantic_correctness,
      gold_validity: outcome === "no_observed_issue" ? "valid" : old.gold_validity,
    }));
  };
  const toggleHypothesis = (label: string, checked: boolean) => {
    if (!current) return;
    update(current.observation_key, (old) => ({ ...old,
      diagnostic_labels: checked ? [...old.diagnostic_labels, label] : old.diagnostic_labels.filter((value) => value !== label),
      diagnostic_support: checked ? [...old.diagnostic_support, { label, status: "hypothesis", evidence_reference: "", contrast_id: "" }] : old.diagnostic_support.filter((value) => value.label !== label),
    }));
  };

  if (!session) return <main className="mx-auto max-w-3xl px-5 py-12 sm:py-16">
    <p className="font-mono text-[11px] uppercase tracking-[.12em] text-ink-3">Diagnostic pilot · review v4 · {rows.length} item</p>
    <h1 className="mt-2 font-disp text-3xl font-semibold">Review khoảng trống tri thức</h1>
    <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-2">Đọc câu hỏi, passage/choices, câu trả lời và gold; ghi nhận phán đoán dựa trên bằng chứng. EM/F1 thấp là tín hiệu cần xem, chưa tự kết luận nguyên nhân.</p>
    <section className="mt-8 rounded-2xl border border-hair bg-card p-5 shadow-sm">
      <label className="block text-sm font-semibold" htmlFor="reviewer-id">Mã/tên reviewer</label>
      <input id="reviewer-id" value={nameInput} onChange={(event) => setNameInput(event.target.value)} className="mt-2 w-full rounded-lg border border-hair bg-paper px-3 py-2 text-sm" autoComplete="name" />
      {gateError && <div role="alert" className="mt-2 text-xs text-reject"><p>{gateError}</p><button onClick={downloadLocalProgress} className="mt-2 underline">Tải tiến độ đang giữ trên trình duyệt (JSON)</button></div>}
      <fieldset className="mt-5"><legend className="text-sm font-semibold">Phạm vi review</legend>
        <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-hair p-3"><input type="radio" checked={scopeInput === "primary-60"} onChange={() => setScopeInput("primary-60")} /><span><b className="block text-sm">Primary · 60 câu</b><span className="text-xs text-ink-2">Review chính cho toàn pilot</span></span></label>
        <label className="mt-2 flex cursor-pointer items-start gap-3 rounded-xl border border-hair p-3"><input type="radio" checked={scopeInput === "independent-15"} onChange={() => setScopeInput("independent-15")} /><span><b className="block text-sm">Independent · 15 câu</b><span className="text-xs text-ink-2">Dành cho reviewer thứ hai; đánh giá độc lập</span></span></label>
      </fieldset>
      <p className="mt-4 rounded-lg bg-flag-soft p-3 text-xs leading-5 text-ink-2">Tiến độ được tự động lưu trên server theo tên reviewer, pilot và phạm vi review. Nhập lại cùng tên để tiếp tục trên trình duyệt khác; đây là danh tính tự khai báo, không phải tài khoản xác thực. Gợi ý AI không tính là đã làm. Independent-15 không nhận gợi ý.</p>
      {!storeHydrated && <p className="mt-3 text-xs text-ink-3">Đang chuẩn bị tiến độ review…</p>}
      <button onClick={start} disabled={!nameInput.trim() || !storeHydrated || starting} className="mt-5 rounded-lg bg-ink px-4 py-2.5 text-sm font-semibold text-paper disabled:cursor-not-allowed disabled:opacity-40">{starting ? "Đang tải tiến độ reviewer…" : "Mở tiến độ review"}</button>
    </section>
    <p className="mt-4 text-xs text-ink-3">Pilot `{String(selection.pilot_content_sha256).slice(0, 12)}` · protocol `{protocolSha.slice(0, 12)}` · exposure: development-audit</p>
  </main>;

  return <main className="mx-auto max-w-[1560px] px-4 py-5 sm:px-7">
    <header className="flex flex-wrap items-start justify-between gap-4 border-b border-hair pb-4">
      <div><p className="font-mono text-[10px] uppercase tracking-[.14em] text-ink-3">Diagnostic pilot · review v4 · {session.scope === "primary-60" ? "primary 60 · AI-assisted" : "independent 15 · human-only"}</p><h1 className="mt-1 font-disp text-2xl font-semibold">Review khoảng trống tri thức</h1><p className="mt-1 text-xs text-ink-2">Reviewer: <b>{session.reviewer}</b> · {sync.error ? "Chưa đồng bộ được lên server" : sync.pending ? "Đang lưu tiến độ lên server…" : activeDraft?.serverSavedAt ? `Đã lưu trên server lúc ${new Date(activeDraft.serverSavedAt).toLocaleString("vi-VN")}` : saveState}</p></div>
      <div className="flex items-center gap-2"><button onClick={downloadCsv} className="rounded-lg border border-hair bg-card px-3 py-2 text-xs font-semibold hover:bg-paper">Xuất CSV</button><button onClick={() => { setSession(null); setSuggestions([]); setSuggestionsState("hidden"); }} className="rounded-lg px-3 py-2 text-xs text-ink-2 hover:bg-card">Đổi reviewer</button></div>
    </header>
    <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink-2" aria-label="Tiến độ của reviewer">
      <span><b className="text-ink">{completedCount}/{scopeRows.length}</b> đã hoàn tất</span>
      <span><b className="text-ink">{progressCounts["in-progress"]}</b> đã chỉnh · chưa xác nhận</span>
      <span><b className="text-ink">{progressCounts.unreviewed}</b> chưa làm</span>
      <span><b className="text-ink">{progressCounts.deferred}</b> tạm hoãn</span>
    </div>
    <p className="mt-2 text-[11px] text-ink-3">Gợi ý AI điền sẵn không tính là thao tác của bạn. Tiến độ lưu tự động theo reviewer; xuất CSV để đưa đánh giá đã xác nhận vào audit.</p>
    {sync.error && <div role="alert" className="mt-3 rounded-lg bg-flag-soft p-3 text-xs"><p>{sync.error} Bản chỉnh sửa vẫn được giữ trên trình duyệt.</p><button onClick={sync.retry} className="mt-2 font-semibold underline">Thử đồng bộ lại</button><button onClick={downloadLocalProgress} className="ml-4 underline">Tải tiến độ trên trình duyệt (JSON)</button></div>}
    {!!previousDrafts.length && <details className="mt-3 rounded-lg border border-hair px-3 py-2 text-xs text-ink-2"><summary className="cursor-pointer">Lịch sử rubric · {previousDrafts.length} bản cũ (chỉ để đối chiếu)</summary><p className="mt-2">Đây là các phiên bản rubric cũ, không phải bản mới tạo mỗi lần tắt máy. Tiến độ hiện tại dùng review v4; trạng thái xác nhận cũ không tự chuyển sang v4.</p>{previousDrafts.map(draft => <button key={draft.revision} onClick={() => downloadPreviousDraft(draft.revision, draft.raw)} className="mr-4 mt-2 underline">Tải bản v{draft.revision} (JSON)</button>)}</details>}
    {exportMessage && <p role="status" className="mt-3 rounded-lg bg-accept-soft px-3 py-2 text-xs text-ink">{exportMessage}</p>}
    <div className="mt-5 grid gap-5 min-[680px]:grid-cols-[250px_minmax(0,1fr)] lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="rounded-2xl border border-hair bg-card p-3 min-[680px]:sticky min-[680px]:top-4 min-[680px]:max-h-[calc(100dvh-2rem)] min-[680px]:overflow-auto">
        <label className="sr-only" htmlFor="item-search">Tìm câu</label><input id="item-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm dataset, ID, câu hỏi…" className="w-full rounded-lg border border-hair bg-paper px-3 py-2 text-xs" />
        <div className="mt-2 flex flex-wrap gap-1"><button onClick={() => setFilter("all")} className={`rounded-md px-2 py-1 text-[11px] ${filter === "all" ? "bg-ink text-paper" : "bg-paper text-ink-2"}`}>Tất cả</button>{([["unreviewed", "Chưa làm"], ["in-progress", "Đã chỉnh"], ["reviewed", "Đã hoàn tất"], ["deferred", "Tạm hoãn"]] as const).map(([value, label]) => <button key={value} onClick={() => setFilter(value)} className={`rounded-md px-2 py-1 text-[11px] ${filter === value ? "bg-ink text-paper" : "bg-paper text-ink-2"}`}>{label}</button>)}</div>
        <div className="mt-3 grid grid-cols-5 gap-1">{scopeRows.map((row, rowIndex) => { const rowStatus = status(answers[row.observation_key], verifiedContrasts, row.observation_key); return <button key={row.observation_key} onClick={() => setIndex(rowIndex)} aria-label={`${datasetName(row.dataset_id)} ${row.item_id}: ${progressLabels[rowStatus]}`} title={`${datasetName(row.dataset_id)} · ${row.item_id} · ${progressLabels[rowStatus]}`} className={`h-8 rounded-md border text-[10px] tabular-nums ${rowIndex === index ? "border-ink bg-ink text-paper" : rowStatus === "reviewed" ? "border-accept/40 bg-accept-soft text-ink" : rowStatus === "deferred" ? "border-flag/40 bg-flag-soft text-ink" : rowStatus === "in-progress" ? "border-flag/50 bg-card text-ink" : "border-hair bg-card text-ink-2"}`}>{rowIndex + 1}</button>; })}</div>
        <ul className="mt-3 max-h-[40dvh] space-y-1 overflow-auto border-t border-hair pt-3">{visibleRows.map((row) => { const rowIndex = scopeRows.findIndex((item) => item.observation_key === row.observation_key); const rowStatus = status(answers[row.observation_key], verifiedContrasts, row.observation_key); return <li key={row.observation_key}><button onClick={() => setIndex(rowIndex)} className={`w-full rounded-lg px-2 py-2 text-left ${rowIndex === index ? "bg-paper" : "hover:bg-paper"}`}><span className="flex justify-between gap-2 text-xs font-semibold"><span>{datasetName(row.dataset_id)} · {row.item_id}</span><span className="text-ink-3" title={progressLabels[rowStatus]}>{rowStatus === "unreviewed" ? "○" : rowStatus === "in-progress" ? "◐" : rowStatus === "reviewed" ? "✓" : "Ⅱ"}</span></span><span className="mt-1 block line-clamp-2 text-[11px] leading-4 text-ink-2">{normalizeDiagnosticDisplayText(row.question)}</span></button></li>; })}</ul>
      </aside>
      {current ? <section className="min-w-0 rounded-2xl border border-hair bg-card p-4 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hair pb-4"><div><p className="font-mono text-[10px] uppercase tracking-[.12em] text-ink-3">{datasetName(current.dataset_id)} · item {index + 1} / {scopeRows.length}</p><h2 className="mt-1 text-sm font-semibold">{current.item_id}</h2></div><div className="flex gap-2"><button onClick={() => setIndex(Math.max(0, index - 1))} disabled={index === 0} className="rounded-lg border border-hair px-3 py-2 text-xs disabled:opacity-40">← Trước</button><button onClick={() => setIndex(Math.min(scopeRows.length - 1, index + 1))} disabled={index >= scopeRows.length - 1} className="rounded-lg border border-hair px-3 py-2 text-xs disabled:opacity-40">Tiếp →</button></div></div>
        <p className="mt-3 text-[11px] text-ink-3">{progressLabels[status(currentJudgment, verifiedContrasts, current.observation_key)]}{humanEdits[current.observation_key] ? ` · Người chỉnh: ${humanEdits[current.observation_key].editedBy}${humanEdits[current.observation_key].editedAt ? ` · ${new Date(humanEdits[current.observation_key].editedAt!).toLocaleString("vi-VN")}` : " · khôi phục từ tiến độ cũ, không có thời gian chỉnh"}` : " · chưa có thao tác đánh giá của reviewer"}</p>
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(330px,.8fr)]">
          <div className="min-w-0 space-y-4 pt-4">
            <div><p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">Câu hỏi</p><p className="mt-1 whitespace-pre-wrap text-sm leading-6">{normalizeDiagnosticDisplayText(current.question)}</p></div>
            <section id="model-answer" className="rounded-xl border border-accept/30 bg-accept-soft/40 p-3"><p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">Câu trả lời model</p><p className="mt-1 whitespace-pre-wrap text-sm font-medium leading-6">{normalizeDiagnosticDisplayText(current.raw_response || "Model không tạo được câu trả lời.")}</p><p className="mt-1 text-[10px] text-ink-3">Prediction đã chấm: {normalizeDiagnosticDisplayText(current.prediction || "rỗng / không parse được")} · finish: {current.finish_reason ?? "không có"}</p></section>
            {session.scope === "primary-60" && (suggestionsState === "loading" ? <p className="rounded-lg bg-paper p-3 text-xs text-ink-2">Đang tải gợi ý AI có gắn với pilot này…</p> : suggestionsState === "error" ? <p role="alert" className="rounded-lg bg-flag-soft p-3 text-xs text-ink-2">Không tải được gợi ý AI; bản review vẫn có thể được điền thủ công.</p> : suggestionsByKey.get(current.observation_key) && (() => { const suggestion = suggestionsByKey.get(current.observation_key)!; return <section className="rounded-xl border border-flag/40 bg-flag-soft/40 p-3"><p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">Gợi ý AI · chưa phải kết luận người duyệt · {suggestion.confidence} confidence</p><p className="mt-1 text-xs font-semibold">{suggestion.proposal.diagnostic_outcome}</p><p className="mt-1 text-xs leading-5">{stripAssistantRationaleMeta(suggestion.proposal.rationale)}</p><p className="mt-1 text-[11px] text-ink-2">Basis: {suggestion.basis} · Tham chiếu: {suggestion.proposal.evidence_reference}</p><p className="mt-2 text-[11px] leading-5 text-ink-2">Gợi ý được lưu vào bản nháp riêng nếu câu còn trống. Mọi trường đã có dữ liệu của reviewer được giữ nguyên; hãy tự kiểm tra và chỉnh sửa trước khi xác nhận.</p></section>; })())}
            <details open className="rounded-xl border border-hair bg-paper"><summary className="cursor-pointer px-3 py-2 text-xs font-semibold">Passage / choices và prompt gốc</summary><pre className="max-h-[45dvh] overflow-auto whitespace-pre-wrap px-3 pb-3 text-xs leading-5 text-ink-2">{normalizeDiagnosticDisplayText(current.rendered_input)}</pre></details>
            <div className="grid gap-3 sm:grid-cols-2"><div className="rounded-xl border border-hair p-3"><p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">Gold gốc · không sửa</p><p className="mt-1 whitespace-pre-wrap text-sm">{normalizeDiagnosticDisplayText(current.source_gold)}</p></div><div className="rounded-xl border border-hair p-3"><p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">Chỉ số nguồn · chưa phải đánh giá ngữ nghĩa</p><pre className="mt-1 whitespace-pre-wrap text-xs text-ink-2">{JSON.stringify(current.source_metrics, null, 2)}</pre></div></div>
            <details className="text-[11px] text-ink-3"><summary className="cursor-pointer">Provenance</summary><p className="mt-2 break-all">source {current.source_run_id} · manifest {current.source_manifest_sha256}<br/>prompt {current.prompt_sha256}<br/>selection {current.selection_reason} · {current.exposure}</p></details>
          </div>
          <div className="space-y-4 border-t border-hair pt-4 xl:border-l xl:border-t-0 xl:pl-5"><p className="text-xs leading-5 text-ink-2">Audit đáp án và giả thuyết nguyên nhân là hai phần riêng. Trích dẫn dưới đây xác minh câu trả lời; không tự chứng minh nguyên nhân bên trong model.</p>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">1 · Kết luận audit</p>
              <div className="mt-2 grid gap-1.5">
                {OUTCOME_OPTIONS.map(([value, label, hint]) => {
                  const active = currentJudgment.diagnostic_outcome === value;
                  return <button key={value} type="button" aria-pressed={active} onClick={() => changeOutcome(value)} className={`rounded-lg border px-3 py-2 text-left text-xs leading-5 ${active ? "border-ink bg-ink text-paper" : "border-hair bg-paper text-ink hover:border-ink/40"}`}><b className="block text-[12px]">{label}</b><span className={active ? "text-paper/75" : "text-ink-3"}>{hint}</span></button>;
                })}
              </div>
              {currentJudgment.diagnostic_outcome === "no_observed_issue" && <p className="mt-2 rounded-lg bg-paper p-2.5 text-[11px] leading-5 text-ink-2">Lựa chọn này ghi nhận luôn: đáp án <b>đúng</b> về ngữ nghĩa, gold <b>hợp lệ</b>.</p>}
              {currentJudgment.diagnostic_outcome === "unresolved" && <p className="mt-2 rounded-lg bg-paper p-2.5 text-[11px] leading-5 text-ink-2">Lựa chọn này đặt trạng thái <b>tạm hoãn</b> và không cho gán biểu hiện hay nguyên nhân.</p>}
            </div>
            {currentJudgment.diagnostic_outcome !== "" && <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">2 · Đánh giá đáp án</p>
              <div className="mt-2 space-y-3">
                {currentJudgment.diagnostic_outcome !== "no_observed_issue" && <>
                  <Field label="Đúng về ngữ nghĩa"><select value={currentJudgment.semantic_correctness} onChange={(event) => update(current.observation_key, (old) => ({ ...old, semantic_correctness: event.target.value as Judgment["semantic_correctness"] }))} className="w-full rounded-lg border border-hair bg-paper px-3 py-2 text-xs text-ink"><option value="">Chọn…</option><option value="correct">Đúng</option><option value="incorrect">Sai</option><option value="uncertain">Chưa chắc</option></select></Field>
                  <Field label="Gold gốc"><select value={currentJudgment.gold_validity} onChange={(event) => update(current.observation_key, (old) => ({ ...old, gold_validity: event.target.value as Judgment["gold_validity"] }))} className="w-full rounded-lg border border-hair bg-paper px-3 py-2 text-xs text-ink"><option value="">Chọn…</option><option value="valid">Hợp lệ</option><option value="suspect">Đáng nghi · cần adjudication</option><option value="unassessable">Chưa đánh giá được</option></select></Field>
                </>}
                <Field label="Dữ kiện trong input model nhận"><select value={currentJudgment.input_evidence_sufficiency} onChange={(event) => update(current.observation_key, (old) => ({ ...old, input_evidence_sufficiency: event.target.value as Judgment["input_evidence_sufficiency"] }))} className="w-full rounded-lg border border-hair bg-paper px-3 py-2 text-xs"><option value="">Chọn…</option><option value="sufficient">Đủ để trả lời</option><option value="insufficient">Thiếu dữ kiện cần thiết</option><option value="unassessable">Chưa đánh giá được</option><option value="not_applicable">Không áp dụng</option></select></Field>
              </div>
            </div>}
            {currentJudgment.diagnostic_outcome === "issue_observed" ? <fieldset><legend className="mb-2 text-xs font-semibold">3 · Biểu hiện quan sát từ artifact · có thể chọn nhiều</legend><div className="grid gap-1.5">{OBSERVED_ISSUES.map(([value, label]) => <label key={value} className="flex items-start gap-2 text-xs leading-5"><input type="checkbox" checked={currentJudgment.observed_issues.includes(value)} onChange={(event) => update(current.observation_key, (old) => ({ ...old, observed_issues: event.target.checked ? [...old.observed_issues, value] : old.observed_issues.filter((item) => item !== value) }))} /><span>{label}</span></label>)}</div></fieldset> : null}
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">4 · Bằng chứng cho kết luận</p>
              <div className="mt-2 space-y-3">
                <Field label="Loại bằng chứng"><select value={currentJudgment.audit_evidence_kind} onChange={(event) => update(current.observation_key, (old) => ({ ...old, audit_evidence_kind: event.target.value as Judgment["audit_evidence_kind"] }))} className="w-full rounded-lg border border-hair bg-paper px-3 py-2 text-xs"><option value="">Chọn…</option><option value="input_span">Đoạn/câu trong input</option><option value="source_comparison">Nguồn đối chiếu ngoài</option><option value="derivation">Phép tính/lập luận có thể kiểm tra</option><option value="raw_output">Raw output/trace</option><option value="parser_replay">Replay parser/scorer</option><option value="unavailable">Chưa có bằng chứng đủ rõ</option></select></Field>
                <Field label="Trích dẫn nguyên văn / phép tính đã kiểm"><textarea value={currentJudgment.evidence_reference} onChange={(event) => update(current.observation_key, (old) => ({ ...old, evidence_reference: event.target.value }))} rows={2} placeholder="Dán đúng câu trong passage, hoặc ghi phép tính đã kiểm tra" className="w-full resize-y rounded-lg border border-hair bg-paper px-3 py-2 text-xs text-ink" /></Field>
                <p className="text-[11px] leading-5 text-ink-3">Corpus phiên bản: protocol này chưa có nên không đánh giá evidence ngoài input.</p>
              </div>
            </div>
            {currentJudgment.diagnostic_outcome === "issue_observed" && <section className="space-y-3 rounded-xl border border-hair p-3"><p className="text-xs font-semibold">5 · Giả thuyết nguyên nhân · tùy chọn</p><p className="text-xs leading-5 text-ink-2">Chưa rõ nguyên nhân thì để trống. Có nhiều giả thuyết không có nghĩa đã chứng minh nhiều nguyên nhân. Human review và confidence AI không nâng mức hỗ trợ.</p><div className="grid gap-1.5">{DIAGNOSTIC_LABELS.map(([value, label]) => { const blocked = CORPUS_DEPENDENT_LABELS.has(value); return <label key={value} className={`flex items-start gap-2 text-xs leading-5 ${blocked ? "opacity-50" : ""}`} title={blocked ? "Cần corpus phiên bản để có premise; protocol này chưa có" : undefined}><input type="checkbox" disabled={blocked} checked={currentJudgment.diagnostic_labels.includes(value)} onChange={(event) => toggleHypothesis(value, event.target.checked)} /><span>{label}{blocked && <span className="text-ink-3"> · chưa có corpus</span>}</span></label>; })}</div>{currentJudgment.diagnostic_support.map((support) => { const matches = verifiedContrasts.filter((contrast) => contrast.observation_key === current.observation_key && contrast.label === support.label); return <div key={support.label} className="space-y-2 rounded-lg bg-paper p-3"><p className="text-xs font-semibold">{DIAGNOSTIC_LABELS.find(([id]) => id === support.label)?.[1] ?? support.label}</p><Field label="Support cho giả thuyết này"><select value={support.contrast_id || "hypothesis"} onChange={(event) => update(current.observation_key, (old) => ({ ...old, diagnostic_support: old.diagnostic_support.map((value) => value.label === support.label ? { ...value, status: event.target.value === "hypothesis" ? "hypothesis" : "contrast_supported", contrast_id: event.target.value === "hypothesis" ? "" : event.target.value } : value) }))} className="w-full rounded-lg border border-hair bg-card px-2 py-2 text-xs"><option value="hypothesis">Giả thuyết từ artifact · chưa đối chiếu</option>{matches.map((contrast) => <option key={contrast.contrast_id} value={contrast.contrast_id}>Đối chiếu đã xác minh: {contrast.contrast_id}</option>)}</select></Field>{!matches.length && <p className="text-[11px] text-ink-3">Chưa có contrast/replay đã đăng ký cho item và nhãn này.</p>}<Field label="Bằng chứng riêng cho giả thuyết"><textarea value={support.evidence_reference} onChange={(event) => update(current.observation_key, (old) => ({ ...old, diagnostic_support: old.diagnostic_support.map((value) => value.label === support.label ? { ...value, evidence_reference: event.target.value } : value) }))} rows={2} className="w-full rounded-lg border border-hair bg-card px-2 py-2 text-xs" /></Field></div>; })}</section>}
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">6 · Lý do kết luận</p>
              <Field label="Vì sao bạn kết luận như trên (khác phần trích dẫn ở bước 4)"><textarea value={currentJudgment.rationale} onChange={(event) => update(current.observation_key, (old) => ({ ...old, rationale: event.target.value }))} rows={3} className="w-full rounded-lg border border-hair bg-paper px-3 py-2 text-xs text-ink resize-y" /></Field>
            </div>
            {/* review_status has no control: every completion rule derives it from diagnostic_outcome. */}
            {session.scope === "independent-15" && <label className="flex items-start gap-2 rounded-lg bg-paper p-3 text-xs leading-5"><input type="checkbox" checked={currentJudgment.blind_review_attestation} onChange={(event) => update(current.observation_key, (old) => ({ ...old, blind_review_attestation: event.target.checked }))} /><span>Tôi chưa xem gợi ý AI hoặc phán đoán reviewer khác cho pilot này.</span></label>}
            <label className="flex cursor-pointer items-start gap-2 rounded-lg bg-flag-soft p-3 text-xs leading-5"><input type="checkbox" checked={currentJudgment.reviewer_attestation} onChange={(event) => update(current.observation_key, (old) => ({ ...old, reviewer_attestation: event.target.checked }))} /><span>{currentJudgment.review_assistance_mode === "ai_assisted" ? "Tôi đã xem gợi ý AI, tự kiểm tra/chỉnh sửa và xác nhận đây là kết luận cuối của mình." : "Tôi xác nhận đây là đánh giá độc lập của mình, không dựa trên nhãn reviewer khác."}</span></label>
            <div className={`rounded-lg px-3 py-2 text-xs ${complete(currentJudgment, verifiedContrasts, current?.observation_key) ? "bg-accept-soft text-ink" : "bg-paper text-ink-2"}`}>{complete(currentJudgment, verifiedContrasts, current?.observation_key) ? "Đủ trường để xuất/import" : <><p className="font-semibold">{humanEdits[current.observation_key] ? `Đã chỉnh bởi ${humanEdits[current.observation_key].editedBy} · chưa hoàn tất` : "Bạn chưa đánh giá câu này"}</p><ul className="mt-1 list-disc space-y-1 pl-4">{currentErrors.map((error) => <li key={error}>{error}</li>)}</ul><p className="mt-2">CSV sẽ để trống phần đánh giá của câu chưa hoàn tất; tiến độ chỉnh sửa vẫn được lưu theo reviewer.</p></>}</div>
          </div>
        </div>
      </section> : <div className="rounded-2xl border border-hair bg-card p-8 text-sm text-ink-2">Không có câu trong phạm vi đã chọn.</div>}
    </div>
  </main>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block text-xs font-semibold">{label}<span className="mt-1.5 block">{children}</span></label>;
}
