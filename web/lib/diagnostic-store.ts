import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";
import type { HumanEdit } from "./diagnostic-progress.ts";
import type { DiagnosticJudgment } from "./diagnostic-review.ts";

export type DiagnosticScope = "primary-60" | "independent-15";

export interface DiagnosticDraftEnvelope {
  version: 4;
  pilotSha: string;
  protocolSha: string;
  reviewer: string;
  scope: DiagnosticScope;
  assistanceMode: "human_only" | "ai_assisted";
  answers: Record<string, DiagnosticJudgment>;
  humanEdits?: Record<string, HumanEdit>;
  pendingKeys?: string[];
  serverRevision?: number;
  serverSavedAt?: string;
}

interface DiagnosticStore {
  /** Zustand's persisted local mirror, partitioned by the full reviewer/scope/revision key. */
  drafts: Record<string, DiagnosticDraftEnvelope>;
  /** Local self-attestation marker; this is not authenticated identity. */
  assistantSeen: Record<string, true>;
  saveDraft(key: string, draft: DiagnosticDraftEnvelope): void;
  hasSeenAssistant(reviewer: string): boolean;
  markAssistantSeen(reviewer: string): void;
}

function reviewerKey(reviewer: string): string {
  return reviewer.trim().toLocaleLowerCase();
}

/** Browser cache for reviewer progress; server synchronization is separate from human CSV import. */
export function createDiagnosticStore(storage?: StateStorage) {
  return create<DiagnosticStore>()(
  persist(
    (set, get) => ({
      drafts: {},
      assistantSeen: {},
      saveDraft: (key, draft) => set((state) => ({ drafts: { ...state.drafts, [key]: draft } })),
      hasSeenAssistant: (reviewer) => Boolean(get().assistantSeen[reviewerKey(reviewer)]),
      markAssistantSeen: (reviewer) => set((state) => ({
        assistantSeen: { ...state.assistantSeen, [reviewerKey(reviewer)]: true },
      })),
    }),
    {
      name: "vmlu.diagnostic.v4.zustand",
      version: 1,
      skipHydration: true,
      partialize: (state) => ({ drafts: state.drafts, assistantSeen: state.assistantSeen }),
      storage: createJSONStorage(() => storage ?? localStorage),
    },
  ),
);
}
export const useDiagnosticStore = createDiagnosticStore();
