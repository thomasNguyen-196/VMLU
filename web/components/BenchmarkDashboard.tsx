"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { InsightPanel } from "@/components/InsightPanel.tsx";
import { summaryFromBlob } from "@/lib/insights.ts";
import type {
  BenchmarkView,
  LegalBlock as DbLegal,
  ReadingBlock as DbReading,
  ReadingSourceVM,
  ReadingStratumVM,
  VbenchDomainVM,
  Vm14kBlock as DbVm14k,
  VmluQuestionVM,
  VmluSubjectVM,
} from "@/lib/benchmark-view.ts";
export type { BenchmarkView };

type VmluSubject = VmluSubjectVM;
type VmluQuestion = VmluQuestionVM;
type VbenchDomain = VbenchDomainVM;
type ReadingStratum = ReadingStratumVM;
type ReadingSource = ReadingSourceVM;

interface VbenchFailure {
  id: number;
  domain: string;
  track: string;
  reason: string;
  failure_class: string;
  raw_response: string;
}

type LegalBlock = DbLegal & {
  benchmark_name: string;
  date: string;
  condition: string;
  measurement_card_hash: string;
  blank_ids: string[];
  caveat: string;
};

type ReadingBlock = DbReading & {
  benchmark_name: string;
  date: string;
  condition: string;
  measurement_card_hash: string;
  caveat: string;
  scorer: string;
};

type Vm14kBlock = DbVm14k & {
  benchmark_name: string;
  date: string;
  condition: string;
  measurement_card_hash: string;
  blank_ids: string[];
  caveat: string;
};

interface BenchmarkData {
  model_info: {
    model_name: string;
    framework: string;
    parameters: string;
    quantization: string;
    hardware: string;
    inference_settings: string;
  };
  datasetMeta: Record<string, { about: string; shape: string; metric: string; metricNote: string }>;
  vmlu: {
    benchmark_name: string;
    date: string;
    condition: string;
    overall: { n: number; correct: number; accuracy: number };
    categories: Array<{ name: string; n: number; correct: number; accuracy: number }>;
    subjects: VmluSubject[];
    weakest_subjects: VmluSubject[];
    strongest_subjects: VmluSubject[];
    questions_sample: VmluQuestion[];
    total_questions_count: number;
  };
  vbench: {
    benchmark_name: string;
    date: string;
    condition: string;
    macro_score: number;
    micro_accuracy: number;
    total_items: number;
    total_correct: number;
    tracks: {
      multiple_choice: { total: number; correct: number; accuracy: number };
      agentic: { total: number; correct: number; accuracy: number };
    };
    domains: VbenchDomain[];
    failure_summary: Array<{ class: string; count: number; desc: string; examples: string }>;
    rejected_items: VbenchFailure[];
    ablation_finding: {
      comparison: string;
      answers_changed_pct: number;
      answers_changed_count: string;
      function_changed_count: number;
      insight: string;
    };
  };
  reading: ReadingBlock;
  legal: LegalBlock;
  legal_nli: LegalBlock | null;
  bidlqa_val: ReadingBlock | null;
  bidlqa_test: ReadingBlock | null;
  vm14k: Vm14kBlock | null;
}

/** Live view (DB) → dashboard props. Missing blocks render their tab as
 *  "model chưa chạy dataset" instead of crashing on undefined. */
export function viewToDashboardData(view: BenchmarkView): { data: BenchmarkData; questions: VmluQuestion[] } {
  const modelName = view.activeModel.display_name;
  const model_info = {
    model_name: modelName,
    framework: "Mongo-backed results store (db vmlu)",
    parameters: view.activeModel.params ?? "—",
    quantization: view.activeModel.quantization ?? "—",
    hardware: view.activeModel.endpoint ?? "—",
    inference_settings: "Số live từ Mongo — hero/cards/bảng từ summaries đã commit",
  };
  const emptyLegal = (benchmark_name: string): LegalBlock => ({
    benchmark_name,
    date: "",
    condition: "",
    measurement_card_hash: "",
    overall: { n: 0, correct: 0, accuracy: 0, valid: 0, blanks: 0, wrong_parsed: 0 },
    baseline: { majority_letter: "—", majority_n: 0, majority_accuracy: 0, label: "—" },
    by_gold: [],
    blank_ids: [],
    caveat: "",
  });
  const emptyReading = (benchmark_name: string): ReadingBlock => ({
    benchmark_name,
    date: "",
    condition: "",
    measurement_card_hash: "",
    overall: { n: 0, em_count: 0, em: 0, char_f1: 0, label: "Tổng" },
    sources: [],
    caveat: "",
    scorer: "",
  });
  const withLegalMeta = (
    block: DbLegal | null,
    benchmark_name: string,
    datasetId: "legal-mc-146" | "legal-nli-150",
  ): LegalBlock => ({
    ...(block ?? emptyLegal(benchmark_name)),
    benchmark_name,
    date: "",
    condition: view.runMeta[datasetId]?.condition ?? "",
    measurement_card_hash: view.runMeta[datasetId]?.measurement_card_hash ?? "",
    blank_ids: [],
    caveat:
      datasetId === "legal-mc-146"
        ? "Baseline + by-gold đếm trực tiếp từ mc_items (majority là dữ liệu, không hardcode)."
        : "NLI nhị phân Có→A / Không→B qua MC runner frozen; baseline 75/75 ≈ 50%.",
  });
  const withVm14kMeta = (block: DbVm14k | null): Vm14kBlock => ({
    ...(block ?? {
      overall: { n: 0, correct: 0, accuracy: 0, valid: 0, blanks: 0, wrong_parsed: 0 },
      baseline: { majority_letter: "—", majority_n: 0, majority_accuracy: 0, label: "—" },
      by_gold: [],
      by_difficulty: [],
      by_n_choices: [],
      by_category: [],
    }),
    benchmark_name: "VM14K public release — trắc nghiệm Y khoa (12.488 câu)",
    date: "",
    condition: view.runMeta["vm14k-public-12488"]?.condition ?? "",
    measurement_card_hash: view.runMeta["vm14k-public-12488"]?.measurement_card_hash ?? "",
    blank_ids: [],
    caveat:
      "Baseline + by-gold live từ mc_items; breakdown độ khó/số lựa chọn join manifest tiền đăng ký " +
      "(data/vm14k_manifest.json). Public release lệch paper + không license; ~6% trùng lặp giữ nguyên; " +
      "chỉ đối chiếu hướng với V-Bench medicine.",
  });
  const withReadingMeta = (
    block: DbReading | null,
    benchmark_name: string,
    datasetId: string,
    caveat: string,
    scorer: string,
  ): ReadingBlock => ({
    ...(block ?? emptyReading(benchmark_name)),
    benchmark_name,
    date: "",
    condition: view.runMeta[datasetId]?.condition ?? "",
    measurement_card_hash: view.runMeta[datasetId]?.measurement_card_hash ?? "",
    caveat,
    scorer,
  });
  const vmluBlock = view.vmlu;
  const vbenchBlock = view.vbench;
  const data: BenchmarkData = {
    model_info,
    datasetMeta: view.datasetMeta,
    vmlu: {
      benchmark_name: "VMLU (Vietnamese Multitask Language Understanding)",
      date: "",
      condition: view.runMeta["vmlu-mqa-all-gold"]?.condition ?? "",
      overall: vmluBlock?.overall ?? { n: 0, correct: 0, accuracy: 0 },
      categories: vmluBlock?.categories ?? [],
      subjects: vmluBlock?.subjects ?? [],
      weakest_subjects: vmluBlock?.weakest_subjects ?? [],
      strongest_subjects: vmluBlock?.strongest_subjects ?? [],
      questions_sample: vmluBlock?.questions_sample ?? [],
      total_questions_count: vmluBlock?.overall.n ?? 0,
    },
    vbench: {
      benchmark_name: "V-Bench Public Test (v2026.03.28)",
      date: "",
      condition: view.runMeta["vbench-public-test"]?.condition ?? "",
      macro_score: vbenchBlock?.macro_score ?? 0,
      micro_accuracy: vbenchBlock?.micro_accuracy ?? 0,
      total_items: vbenchBlock?.total_items ?? 0,
      total_correct: vbenchBlock?.total_correct ?? 0,
      tracks: vbenchBlock?.tracks ?? {
        multiple_choice: { total: 0, correct: 0, accuracy: 0 },
        agentic: { total: 0, correct: 0, accuracy: 0 },
      },
      domains: vbenchBlock?.domains ?? [],
      failure_summary: [],
      rejected_items: [],
      ablation_finding: {
        comparison: "",
        answers_changed_pct: 0,
        answers_changed_count: "",
        function_changed_count: 0,
        insight: "",
      },
    },
    reading: withReadingMeta(
      view.reading,
      "Reading comprehension — 400 câu tiền đăng ký (Vi-SQuAD + Vi-DROP)",
      "reading-400",
      "EM/F1 live từ Mongo. Strata EM đếm từ items (summaries hiện không lưu stratum).",
      "summaries.reading_rows + items",
    ),
    legal: withLegalMeta(view.legal, "VLSP2025-LegalSLM public-test — multichoice (luật, trắc nghiệm)", "legal-mc-146"),
    legal_nli: view.legal_nli
      ? withLegalMeta(view.legal_nli, "VLSP2025-LegalSLM public-test — nli (entailment nhị phân)", "legal-nli-150")
      : null,
    bidlqa_val: view.bidlqa_val
      ? withReadingMeta(view.bidlqa_val, "ViBidLQA — đấu thầu (đọc hiểu, open-book)", "bidlqa-val", "Gold lấy nguyên văn trong file (file-gold).", "summaries.reading_rows + items")
      : null,
    bidlqa_test: view.bidlqa_test
      ? withReadingMeta(view.bidlqa_test, "ViBidLQA — đấu thầu (đọc hiểu, open-book)", "bidlqa-test", "Gold lấy nguyên văn trong file (file-gold).", "summaries.reading_rows + items")
      : null,
    vm14k: view.vm14k ? withVm14kMeta(view.vm14k) : null,
  };
  return { data, questions: vmluBlock?.questions_sample ?? [] };
}

/** One shared "what is this dataset + how is it scored" strip. Rendered
 *  under every hero from DATASET_META so all tabs share one vocabulary:
 *  about (dataset là gì) · shape (dạng câu) · metric (thang điểm) ·
 *  metricNote (không được hiểu nhầm thành gì). */
function DatasetStrip({
  meta,
  headline,
}: {
  meta: { about: string; shape: string; metric: string; metricNote: string } | undefined;
  headline: string;
}) {
  if (!meta) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs space-y-1.5">
      <p className="text-xs text-slate-700 leading-relaxed">
        <span className="font-bold text-slate-900">Dataset: </span>
        {meta.about}
      </p>
      <p className="text-xs text-slate-600 leading-relaxed">
        <span className="font-semibold text-slate-800">Dạng câu: </span>
        {meta.shape}
      </p>
      <p className="text-xs text-slate-600 leading-relaxed">
        <span className="font-semibold text-slate-800">Thang điểm hero: </span>
        <span className="font-mono font-bold text-indigo-700">{headline}</span>
        <span className="text-slate-500"> — {meta.metric}</span>
      </p>
      <p className="text-[11px] text-amber-800 leading-relaxed bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5">
        ⚠️ {meta.metricNote}
      </p>
    </div>
  );
}

/** Insight khối DB-view cho một tab: model = `activeModelId` (view đã canonical),
 *  bằng chứng số dùng chung với /results qua `summaryFromBlob`. */
function TabInsight({
  datasetId,
  modelId,
  block,
}: {
  datasetId: string;
  modelId: string;
  block: unknown;
}) {
  const summary = summaryFromBlob(datasetId, block);
  if (!summary) return null;
  return <InsightPanel modelId={modelId} datasetId={datasetId} summary={summary} />;
}

/** EM/F1 reading layout shared by reading-400 + bidlqa val/test (single source). */
function ReadingTabView({
  block,
  title,
  eyebrow,
  meta,
  datasetId,
  modelId,
}: {
  block: ReadingBlock;
  title: string;
  eyebrow: string;
  meta: { about: string; shape: string; metric: string; metricNote: string } | undefined;
  datasetId: string;
  modelId: string;
}) {
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-emerald-900 via-teal-900 to-slate-900 text-white rounded-2xl p-6 sm:p-8 shadow-sm">
        <div className="space-y-3 max-w-3xl">
          <div className="flex items-center gap-2 text-emerald-300 text-xs font-semibold uppercase tracking-wider">
            <span>{eyebrow}</span>
          </div>
          <h2 className="text-2xl font-bold">{title}</h2>
          <p className="text-sm text-emerald-100/80 leading-relaxed">
            {block.condition}
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
            <div className="text-emerald-300 text-[11px] font-semibold uppercase tracking-wide">Số câu (n)</div>
            <div className="text-2xl font-black font-mono mt-1">{block.overall.n}</div>
          </div>
          <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
            <div className="text-emerald-300 text-[11px] font-semibold uppercase tracking-wide">EM</div>
            <div className="text-2xl font-black font-mono mt-1">{block.overall.em.toFixed(2)}%</div>
            <div className="text-[11px] text-emerald-200/70 font-mono">
              {block.overall.em_count}/{block.overall.n}
            </div>
          </div>
          <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
            <div className="text-emerald-300 text-[11px] font-semibold uppercase tracking-wide">char-F1</div>
            <div className="text-2xl font-black font-mono mt-1">{block.overall.char_f1.toFixed(2)}%</div>
          </div>
          <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
            <div className="text-emerald-300 text-[11px] font-semibold uppercase tracking-wide">Chênh EM→F1</div>
            <div className="text-2xl font-black font-mono mt-1 text-amber-300">
              {(block.overall.char_f1 - block.overall.em).toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      <DatasetStrip meta={meta} headline={`EM ${block.overall.em.toFixed(2)}% · F1 ${block.overall.char_f1.toFixed(2)}% (n=${block.overall.n})`} />
      <TabInsight datasetId={datasetId} modelId={modelId} block={block} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {block.sources.map((src) => (
          <div key={src.label} className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
            <div className="p-5 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div>
                <h3 className="font-bold text-slate-900">{src.label}</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  n = {src.n} · {src.em_count} câu exact
                </p>
              </div>
              <div className="text-right">
                <div className="text-xl font-black font-mono text-emerald-600">{src.em.toFixed(2)}%</div>
                <div className="text-[11px] text-slate-500 font-mono">EM · F1 {src.char_f1.toFixed(2)}%</div>
              </div>
            </div>
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-slate-100 text-slate-700 font-semibold">
                <tr>
                  <th className="py-2 px-4">Dạng câu hỏi</th>
                  <th className="py-2 px-3 text-right">n</th>
                  <th className="py-2 px-3 text-right">EM (%)</th>
                  <th className="py-2 px-3 text-right">char-F1 (%)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {[...src.strata]
                  .sort((a, b) => a.em - b.em)
                  .map((st) => (
                    <tr key={st.stratum}>
                      <td className="py-2 px-4">{st.label}</td>
                      <td className="py-2 px-3 text-right font-mono">{st.n}</td>
                      <td
                        className={`py-2 px-3 text-right font-mono font-bold ${
                          st.em < 60 ? "text-rose-600" : st.em < 80 ? "text-amber-600" : "text-emerald-600"
                        }`}
                      >
                        {st.em.toFixed(2)}
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-slate-600">
                        {st.char_f1.toFixed(2)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">⚠️</span>
          <h3 className="font-bold text-amber-900 text-sm">Đọc con số này thế nào</h3>
        </div>
        <p className="text-xs text-amber-900/90 leading-relaxed">{block.caveat}</p>
        <p className="text-[11px] text-amber-800/70 font-mono pt-1 border-t border-amber-200">
          scorer: {block.scorer} · card {block.measurement_card_hash.slice(0, 12)}…
        </p>
      </div>
    </div>
  );
}


export function BenchmarkDashboard({
  data,
  questions,
  models,
  activeModelId,
  onModelChange,
}: {
  data: BenchmarkData;
  questions: VmluQuestion[];
  models: Array<{ id: string; display_name: string }>;
  activeModelId: string;
  onModelChange: (id: string) => void;
}) {
  const [tab, setTab] = useState<"vmlu" | "vbench" | "reading" | "legal" | "nli" | "bidlqa-val" | "bidlqa-test" | "vm14k">(
    data.vmlu.overall.n > 0 ? "vmlu" : "legal",
  );

  // Tabs render only when the model ran that dataset (DB has the block).
  // Badges are live numbers from Mongo, not frozen blob constants.
  const tabs = [
    data.vmlu.overall.n > 0 && {
      id: "vmlu" as const,
      label: "🇻🇳 VMLU Benchmark",
      badge: `${data.vmlu.overall.accuracy.toFixed(2)}%`,
      badgeClass: "bg-indigo-50 text-indigo-700",
    },
    data.vbench.total_items > 0 && {
      id: "vbench" as const,
      label: "🚀 V-Bench",
      badge: `${data.vbench.macro_score.toFixed(2)}`,
      badgeClass: "bg-slate-100 text-slate-700",
    },
    data.reading.overall.n > 0 && {
      id: "reading" as const,
      label: "📖 Đọc hiểu (400 câu)",
      badge: `EM ${data.reading.overall.em.toFixed(2)}%`,
      badgeClass: "bg-emerald-50 text-emerald-700",
    },
    data.legal.overall.n > 0 && {
      id: "legal" as const,
      label: "⚖️ LegalSLM (146 câu)",
      badge: `${data.legal.overall.accuracy.toFixed(2)}%`,
      badgeClass: "bg-sky-50 text-sky-700",
    },
    data.legal_nli && data.legal_nli.overall.n > 0 && {
      id: "nli" as const,
      label: "🔀 Legal NLI (150 câu)",
      badge: `${data.legal_nli.overall.accuracy.toFixed(2)}%`,
      badgeClass: "bg-violet-50 text-violet-700",
    },
    data.bidlqa_val && data.bidlqa_val.overall.n > 0 && {
      id: "bidlqa-val" as const,
      label: `📑 BidLQA val (${data.bidlqa_val.overall.n})`,
      badge: `EM ${data.bidlqa_val.overall.em.toFixed(2)}%`,
      badgeClass: "bg-teal-50 text-teal-700",
    },
    data.bidlqa_test && data.bidlqa_test.overall.n > 0 && {
      id: "bidlqa-test" as const,
      label: `📑 BidLQA test (${data.bidlqa_test.overall.n})`,
      badge: `EM ${data.bidlqa_test.overall.em.toFixed(2)}%`,
      badgeClass: "bg-teal-50 text-teal-700",
    },
    data.vm14k && data.vm14k.overall.n > 0 && {
      id: "vm14k" as const,
      label: `🩺 VM14K (${data.vm14k.overall.n})`,
      badge: `${data.vm14k.overall.accuracy.toFixed(2)}%`,
      badgeClass: "bg-cyan-50 text-cyan-700",
    },
  ].filter((t): t is { id: "vmlu" | "vbench" | "reading" | "legal" | "nli" | "bidlqa-val" | "bidlqa-test" | "vm14k"; label: string; badge: string; badgeClass: string } => Boolean(t));

  // VMLU subject table filters
  const [vmluCat, setVmluCat] = useState<string>("ALL");
  const [vmluSearch, setVmluSearch] = useState<string>("");
  const [vmluSortAsc, setVmluSortAsc] = useState<boolean>(false);

  // Wrong-answer explorer: local filter over the 50 wrong items + paging
  // through the full wrong set via /api/results/items-page.
  const [qCat, setQCat] = useState<string>("ALL");
  const [qSearch, setQSearch] = useState<string>("");

  // Modal
  const [selectedQuestion, setSelectedQuestion] = useState<VmluQuestion | null>(null);

  // Filtered VMLU subjects
  const filteredSubjects = useMemo(() => {
    const list = data.vmlu.subjects.filter((s) => {
      const matchCat = vmluCat === "ALL" || s.category === vmluCat;
      const matchSearch =
        s.full_name.toLowerCase().includes(vmluSearch.toLowerCase()) ||
        s.code.toLowerCase().includes(vmluSearch.toLowerCase());
      return matchCat && matchSearch;
    });
    return list.sort((a, b) =>
      vmluSortAsc ? a.accuracy - b.accuracy : b.accuracy - a.accuracy
    );
  }, [data.vmlu.subjects, vmluCat, vmluSearch, vmluSortAsc]);

  // Filtered wrong-answer items (client-side slice of the loaded page)
  const filteredQuestions = useMemo(() => {
    return questions.filter((q) => {
      if (qCat !== "ALL" && q.category !== qCat) return false;
      if (
        qSearch &&
        !q.question.toLowerCase().includes(qSearch.toLowerCase()) &&
        !q.id.toLowerCase().includes(qSearch.toLowerCase())
      ) {
        return false;
      }
      return true;
    });
  }, [questions, qCat, qSearch]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* TOP HEADER — brand + review link left, model switch lives in sidebar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-blue-600 to-emerald-500 flex items-center justify-center text-white font-black text-xl shadow-sm">
                V
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="font-bold text-lg text-slate-900 leading-tight">
                    Benchmark Research Hub
                  </h1>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                    live · Mongo
                  </span>
                </div>
                <p className="text-xs text-slate-500">
                  Số live từ Mongo — hero/cards/bảng từ summaries đã commit
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Link
                href="/"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors shadow-2xs"
              >
                <span>📝 Trình Review 400 câu</span>
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* BODY: content + sticky dataset rail */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex gap-6 items-start">
      <main className="min-w-0 flex-1 space-y-6">
        {/* ========================================================== */}
        {/* TAB 1: VMLU */}
        {/* ========================================================== */}
        {tab === "vmlu" && (
          <div className="space-y-6">
            {/* Header Hero Banner */}
            <div className="bg-gradient-to-r from-indigo-900 via-slate-900 to-blue-950 text-white rounded-2xl p-6 sm:p-8 shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div className="space-y-2 max-w-2xl">
                  <div className="flex items-center gap-2 text-indigo-300 text-xs font-semibold uppercase tracking-wider">
                    <span>Chuẩn Đánh Giá Tiếng Việt</span> &bull; <span>58 Môn Học</span>
                  </div>
                  <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
                    VMLU Benchmark (1,047 câu Gold Dev+Valid)
                  </h2>
                  <p className="text-slate-300 text-sm leading-relaxed">
                    Mô hình đạt độ chính xác chung{" "}
                    <strong className="text-emerald-400 font-mono text-base">73.35%</strong>{" "}
                    (768 / 1,047 câu đúng). Tuy nhiên bộc lộ sự phân hóa cực đoan: các môn tự nhiên STEM
                    đạt gần 80%, nhưng nhóm Pháp luật, Thuế và Nghiệp vụ công chức rớt xuống 30%–47%.
                  </p>
                </div>

                <div className="flex items-center gap-4 bg-white/10 backdrop-blur-md p-4 rounded-xl border border-white/10 shrink-0">
                  <div className="text-center px-3 border-r border-white/10">
                    <div className="text-3xl font-black text-emerald-400 font-mono">73.35%</div>
                    <div className="text-[11px] text-slate-300 uppercase tracking-wider mt-0.5">
                      Độ chính xác
                    </div>
                  </div>
                  <div className="text-center px-3">
                    <div className="text-2xl font-bold text-white font-mono">
                      768<span className="text-sm font-normal text-slate-400">/1047</span>
                    </div>
                    <div className="text-[11px] text-slate-300 uppercase tracking-wider mt-0.5">
                      Số câu đúng
                    </div>
                  </div>
                </div>
              </div>

              {/* 4 Category cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mt-6 pt-6 border-t border-white/10">
                {data.vmlu.categories.map((cat) => (
                  <div key={cat.name} className="bg-white/5 rounded-xl p-3 sm:p-4 border border-white/5">
                    <div className="text-xs text-indigo-200 font-medium truncate">{cat.name}</div>
                    <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">
                      {cat.accuracy.toFixed(2)}%
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      {cat.correct} / {cat.n} câu
                    </div>
                    <div className="w-full bg-white/10 h-1.5 rounded-full mt-2 overflow-hidden">
                      <div
                        className="bg-emerald-400 h-full rounded-full"
                        style={{ width: `${cat.accuracy}%` }}
                      ></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <DatasetStrip meta={data.datasetMeta["vmlu-mqa-all-gold"]} headline={`Accuracy ${data.vmlu.overall.accuracy.toFixed(2)}% (${data.vmlu.overall.correct}/${data.vmlu.overall.n}) · 4 categories + 58 subjects`} />
            <TabInsight datasetId="vmlu-mqa-all-gold" modelId={activeModelId} block={data.vmlu} />

            {/* Highlighting Weakest vs Strongest */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Weakest */}
              <div className="bg-white rounded-xl p-5 border border-rose-200 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-slate-900 flex items-center gap-2 text-sm">
                    <span className="w-2 h-2 rounded-full bg-rose-500"></span>
                    Top 6 Môn Yếu Nhất (Điểm trũng cần can thiệp)
                  </h3>
                  <span className="text-xs font-semibold px-2 py-0.5 bg-rose-50 text-rose-700 rounded border border-rose-200">
                    Cần Tra cứu VBPL
                  </span>
                </div>
                <div className="space-y-2">
                  {data.vmlu.weakest_subjects.slice(0, 6).map((s) => (
                    <div
                      key={s.code}
                      className="flex items-center justify-between p-2 rounded-lg bg-rose-50/70 border border-rose-100 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-rose-800 font-bold">{s.code}</span>
                        <span className="font-medium text-slate-800">{s.name}</span>
                      </div>
                      <span className="font-mono font-bold text-rose-700 bg-white px-2 py-0.5 rounded border border-rose-200">
                        {s.accuracy.toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Strongest */}
              <div className="bg-white rounded-xl p-5 border border-emerald-200 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-slate-900 flex items-center gap-2 text-sm">
                    <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                    Top 6 Môn Mạnh Nhất (Thế mạnh tri thức tham số)
                  </h3>
                  <span className="text-xs font-semibold px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded border border-emerald-200">
                    Fast Path (Zero-shot)
                  </span>
                </div>
                <div className="space-y-2">
                  {data.vmlu.strongest_subjects.slice(0, 6).map((s) => (
                    <div
                      key={s.code}
                      className="flex items-center justify-between p-2 rounded-lg bg-emerald-50/70 border border-emerald-100 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-emerald-800 font-bold">{s.code}</span>
                        <span className="font-medium text-slate-800">{s.name}</span>
                      </div>
                      <span className="font-mono font-bold text-emerald-700 bg-white px-2 py-0.5 rounded border border-emerald-200">
                        {s.accuracy.toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 58 SUBJECTS TABLE */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
              <div className="p-5 border-b border-slate-200 bg-slate-50/70 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h3 className="font-bold text-slate-900 text-base">Bảng Xếp Hạng 58 Môn Học VMLU</h3>
                  <p className="text-xs text-slate-500">
                    Tra cứu chi tiết tỷ lệ đúng, số lượng mẫu và nhóm ngành
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex items-center bg-white p-1 rounded-lg border border-slate-200 text-xs shadow-2xs">
                    {["ALL", "STEM", "Social Science", "Humanity", "Other"].map((cat) => (
                      <button
                        key={cat}
                        onClick={() => setVmluCat(cat)}
                        className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                          vmluCat === cat
                            ? "text-indigo-700 bg-indigo-50"
                            : "text-slate-600 hover:text-slate-900"
                        }`}
                      >
                        {cat === "ALL" ? "Tất cả (58)" : cat}
                      </button>
                    ))}
                  </div>

                  <input
                    type="text"
                    value={vmluSearch}
                    onChange={(e) => setVmluSearch(e.target.value)}
                    placeholder="Tìm tên môn hoặc mã..."
                    className="text-xs bg-white border border-slate-200 rounded-lg px-3 py-1.5 w-44 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div className="overflow-x-auto max-h-[480px]">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-100 text-slate-600 font-semibold sticky top-0 border-b border-slate-200 z-10">
                    <tr>
                      <th className="py-2.5 px-4 w-16">Mã</th>
                      <th className="py-2.5 px-4">Tên môn học</th>
                      <th className="py-2.5 px-4 w-32">Nhóm ngành</th>
                      <th
                        className="py-2.5 px-4 w-28 text-right cursor-pointer hover:bg-slate-200"
                        onClick={() => setVmluSortAsc(!vmluSortAsc)}
                      >
                        Độ chính xác {vmluSortAsc ? "▲" : "▼"}
                      </th>
                      <th className="py-2.5 px-4 w-28 text-right">Số câu đúng</th>
                      <th className="py-2.5 px-4 w-40">Phân bố tỷ lệ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredSubjects.map((s) => {
                      let barColor = "bg-emerald-500";
                      let badgeColor = "text-emerald-700 bg-emerald-50 border-emerald-200";
                      if (s.accuracy < 40) {
                        barColor = "bg-rose-500";
                        badgeColor = "text-rose-700 bg-rose-50 border-rose-200";
                      } else if (s.accuracy < 60) {
                        barColor = "bg-amber-500";
                        badgeColor = "text-amber-700 bg-amber-50 border-amber-200";
                      } else if (s.accuracy < 80) {
                        barColor = "bg-blue-500";
                        badgeColor = "text-blue-700 bg-blue-50 border-blue-200";
                      }

                      return (
                        <tr key={s.code} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-2.5 px-4 font-mono font-bold text-slate-500">
                            {s.code}
                          </td>
                          <td className="py-2.5 px-4 font-medium text-slate-900">{s.name}</td>
                          <td className="py-2.5 px-4">
                            <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700">
                              {s.category}
                            </span>
                          </td>
                          <td className="py-2.5 px-4 text-right font-mono font-bold">
                            <span className={`px-2 py-0.5 rounded border ${badgeColor}`}>
                              {s.accuracy.toFixed(1)}%
                            </span>
                          </td>
                          <td className="py-2.5 px-4 text-right font-mono text-slate-600">
                            {s.correct} / {s.n}
                          </td>
                          <td className="py-2.5 px-4">
                            <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden border border-slate-200">
                              <div
                                className={`${barColor} h-full rounded-full`}
                                style={{ width: `${Math.min(100, s.accuracy)}%` }}
                              ></div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* WRONG-ANSWER EXPLORER (DB: first 50 correct=0 of this run) */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-5 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
                <div>
                  <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                    <span>🔍 Câu trả lời sai (Wrong-answer explorer)</span>
                    <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-rose-100 text-rose-800">
                      {filteredQuestions.length} câu
                    </span>
                  </h3>
                  <p className="text-xs text-slate-500">
                    50 câu sai đầu tiên của run này (sort theo item_id) — bấm để soi prompt, raw response, gold
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={qCat}
                    onChange={(e) => setQCat(e.target.value)}
                    className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-slate-50 font-medium"
                  >
                    <option value="ALL">Mọi nhóm ngành</option>
                    <option value="STEM">STEM</option>
                    <option value="Social Science">Social Science</option>
                    <option value="Humanity">Humanity</option>
                    <option value="Other">Other</option>
                  </select>

                  <input
                    type="text"
                    value={qSearch}
                    onChange={(e) => setQSearch(e.target.value)}
                    placeholder="Tìm từ khóa trong đề bài..."
                    className="text-xs border border-slate-200 rounded-lg px-3 py-1.5 w-48 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                {filteredQuestions.slice(0, 50).map((q) => (
                  <div
                    key={q.id}
                    onClick={() => setSelectedQuestion(q)}
                    className="p-4 rounded-xl border transition-all cursor-pointer border-rose-200 bg-rose-50/20 hover:border-rose-400"
                  >
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-rose-700">
                          {q.id}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10.5px] bg-slate-100 text-slate-600">
                          {q.category}
                        </span>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-100 text-rose-800">
                        {`❌ Sai (Chọn ${q.answer} / Đúng: ${q.gold_answer})`}
                      </span>
                    </div>
                    <div className="text-xs text-slate-900 font-medium line-clamp-2">
                      {q.question}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================== */}
        {/* TAB 2: V-BENCH */}
        {/* ========================================================== */}
        {tab === "vbench" && (
          <div className="space-y-6">
            {/* Header Hero Banner */}
            <div className="bg-gradient-to-r from-slate-900 via-sky-950 to-indigo-950 text-white rounded-2xl p-6 sm:p-8 shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div className="space-y-2 max-w-2xl">
                  <div className="flex items-center gap-2 text-sky-300 text-xs font-semibold uppercase tracking-wider">
                    <span>Bảng Xếp Hạng Độc Lập</span> &bull; <span>Public Test v2026.03.28</span>
                  </div>
                  <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
                    V-Bench Leaderboard (5,141 câu)
                  </h2>
                  <p className="text-slate-300 text-sm leading-relaxed">
                    Kết quả chính thức được chấm bởi hệ thống máy chủ{" "}
                    <strong className="text-white">vbench.ai</strong>. Đo lường ở điều kiện trung thực{" "}
                    <span className="text-sky-300 font-mono">minimal prompt</span> (không mớm rule,
                    không CoT, temp 0, seed 42).
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3 bg-white/10 backdrop-blur-md p-4 rounded-xl border border-white/10 shrink-0">
                  <div className="text-center px-2">
                    <div className="text-3xl font-black text-sky-400 font-mono">
                      {data.vbench.macro_score.toFixed(2)}
                    </div>
                    <div className="text-[11px] text-slate-300 uppercase tracking-wider mt-0.5">
                      Macro Score (13)
                    </div>
                  </div>
                  <div className="text-center px-2 border-l border-white/10">
                    <div className="text-3xl font-black text-emerald-400 font-mono">
                      {data.vbench.micro_accuracy.toFixed(2)}%
                    </div>
                    <div className="text-[11px] text-slate-300 uppercase tracking-wider mt-0.5">
                      Micro Acc ({data.vbench.total_correct}/{data.vbench.total_items})
                    </div>
                  </div>
                </div>
              </div>

              {/* 2 Track Stats */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6 pt-6 border-t border-white/10">
                <div className="bg-white/5 rounded-xl p-4 border border-white/5 flex items-center justify-between">
                  <div>
                    <div className="text-xs text-sky-200 font-medium">
                      📋 Multiple-Choice Track (12 domains)
                    </div>
                    <div className="text-xl font-bold font-mono text-white mt-1">
                      {data.vbench.tracks.multiple_choice.accuracy.toFixed(2)}%{" "}
                      <span className="text-xs font-normal text-slate-400">
                        ({data.vbench.tracks.multiple_choice.correct} /{" "}
                        {data.vbench.tracks.multiple_choice.total} câu)
                      </span>
                    </div>
                  </div>
                  <span className="px-2.5 py-1 rounded bg-sky-500/20 text-sky-300 text-xs font-mono font-bold">
                    4,141 items
                  </span>
                </div>

                <div className="bg-white/5 rounded-xl p-4 border border-white/5 flex items-center justify-between">
                  <div>
                    <div className="text-xs text-purple-200 font-medium">
                      🤖 Agentic Function Calling Track
                    </div>
                    <div className="text-xl font-bold font-mono text-white mt-1">
                      {data.vbench.tracks.agentic.accuracy.toFixed(2)}%{" "}
                      <span className="text-xs font-normal text-slate-400">
                        ({data.vbench.tracks.agentic.correct} /{" "}
                        {data.vbench.tracks.agentic.total} câu đúng)
                      </span>
                    </div>
                  </div>
                  <span className="px-2.5 py-1 rounded bg-purple-500/20 text-purple-300 text-xs font-mono font-bold">
                    1,000 items
                  </span>
                </div>
              </div>
            </div>

            <DatasetStrip meta={data.datasetMeta["vbench-public-test"]} headline={`Micro ${data.vbench.micro_accuracy.toFixed(2)}% (${data.vbench.total_correct}/${data.vbench.total_items}) · Macro ${data.vbench.macro_score.toFixed(2)} (13 miền)`} />
            <TabInsight datasetId="vbench-public-test" modelId={activeModelId} block={data.vbench} />

            {/* 13 Domains Leaderboard */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
              <div className="p-5 border-b border-slate-200 bg-slate-50/70 flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-slate-900 text-base">
                    Bảng Xếp Hạng 13 Miền Tri Thức (Domains)
                  </h3>
                  <p className="text-xs text-slate-500">
                    Phân hóa mạnh mẽ giữa tri thức ngữ nghĩa và năng lực suy luận toán logic
                  </p>
                </div>
                <span className="text-xs font-mono px-2.5 py-1 bg-slate-200 text-slate-700 rounded-md font-semibold">
                  13 Domains Rated
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-100 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-4 w-12 text-center">#</th>
                      <th className="py-2.5 px-4">Miền tri thức (Domain)</th>
                      <th className="py-2.5 px-4 w-32">Thể loại (Track)</th>
                      <th className="py-2.5 px-4 w-28 text-right">Điểm số (Score)</th>
                      <th className="py-2.5 px-4 w-28 text-right">Số câu đúng</th>
                      <th className="py-2.5 px-4 w-48">Thanh hiệu suất</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.vbench.domains.map((d, i) => {
                      const barColor =
                        d.score >= 60
                          ? "bg-emerald-500"
                          : d.score >= 40
                          ? "bg-blue-500"
                          : "bg-rose-500";
                      return (
                        <tr key={d.domain} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-3 px-4 text-center font-mono font-bold text-slate-400">
                            {i + 1}
                          </td>
                          <td className="py-3 px-4 font-semibold text-slate-900 flex items-center gap-2">
                            <span>{d.icon || "📄"}</span>
                            <span>{d.name}</span>
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-mono ${
                                d.track === "function-calling"
                                  ? "bg-purple-100 text-purple-800"
                                  : "bg-slate-100 text-slate-700"
                              }`}
                            >
                              {d.track}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-sm text-slate-900">
                            {d.score.toFixed(2)}%
                          </td>
                          <td className="py-3 px-4 text-right font-mono text-slate-600">
                            {d.correct} / {d.total}
                          </td>
                          <td className="py-3 px-4">
                            <div className="w-full bg-slate-100 h-2.5 rounded-full overflow-hidden border border-slate-200">
                              <div
                                className={`${barColor} h-full rounded-full`}
                                style={{ width: `${d.score}%` }}
                              ></div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        )}

        {/* TAB 3: READING COMPREHENSION */}
        {tab === "reading" && (
          <ReadingTabView
            block={data.reading}
            title={`Bài kiểm tra Đọc hiểu — ${data.reading.overall.n} câu`}
            eyebrow="Tiền đăng ký · seed 42 · 200 Vi-SQuAD + 200 Vi-DROP"
            meta={data.datasetMeta["reading-400"]}
            datasetId="reading-400"
            modelId={activeModelId}
          />
        )}
        {/* ========================================================== */}
        {/* TAB: LEGALSLM MULTICHOICE (MC-6) */}
        {/* ========================================================== */}
        {tab === "legal" && (
          <div className="space-y-6">
            <div className="bg-gradient-to-r from-sky-900 via-blue-900 to-slate-900 text-white rounded-2xl p-6 sm:p-8 shadow-sm">
              <div className="space-y-3 max-w-3xl">
                <div className="flex items-center gap-2 text-sky-300 text-xs font-semibold uppercase tracking-wider">
                  <span>Tiền đăng ký · seed 42 · closed-book · card MC-6</span>
                </div>
                <h2 className="text-2xl font-bold">Luật trắc nghiệm — {data.legal.overall.n} câu</h2>
                <p className="text-sm text-sky-100/80 leading-relaxed">
                  {data.legal.condition}
                </p>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-sky-300 text-[11px] font-semibold uppercase tracking-wide">Accuracy</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.legal.overall.accuracy.toFixed(2)}%</div>
                  <div className="text-[11px] text-sky-200/70 font-mono">
                    {data.legal.overall.correct}/{data.legal.overall.n}
                  </div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-sky-300 text-[11px] font-semibold uppercase tracking-wide">Baseline ({data.legal.baseline.label})</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.legal.baseline.majority_accuracy.toFixed(2)}%</div>
                  <div className="text-[11px] text-sky-200/70 font-mono">
                    {data.legal.baseline.majority_n}/{data.legal.overall.n}
                  </div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-sky-300 text-[11px] font-semibold uppercase tracking-wide">Hơn baseline</div>
                  <div className="text-2xl font-black font-mono mt-1 text-emerald-300">
                    +{(data.legal.overall.accuracy - data.legal.baseline.majority_accuracy).toFixed(2)}
                  </div>
                  <div className="text-[11px] text-sky-200/70">điểm phần trăm</div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-sky-300 text-[11px] font-semibold uppercase tracking-wide">Valid (parse được)</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.legal.overall.valid}/{data.legal.overall.n}</div>
                  <div className="text-[11px] text-sky-200/70 font-mono">
                    sai trong số parse được: {data.legal.overall.wrong_parsed}
                  </div>
                </div>
              </div>
            </div>

            <DatasetStrip meta={data.datasetMeta["legal-mc-146"]} headline={`Accuracy ${data.legal.overall.accuracy.toFixed(2)}% (${data.legal.overall.correct}/${data.legal.overall.n}) · baseline ${data.legal.baseline.majority_accuracy.toFixed(2)}%`} />
            <TabInsight datasetId="legal-mc-146" modelId={activeModelId} block={data.legal} />

            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
              <div className="p-5 border-b border-slate-200 bg-slate-50">
                <h3 className="font-bold text-slate-900 text-sm">
                  Accuracy theo đáp án đúng
                </h3>
              </div>
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-100 text-slate-700 font-semibold">
                  <tr>
                    <th className="py-2 px-4">Đáp án đúng</th>
                    <th className="py-2 px-3 text-right">n</th>
                    <th className="py-2 px-3 text-right">Đúng</th>
                    <th className="py-2 px-3 text-right">Accuracy (%)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {data.legal.by_gold.map((g) => (
                    <tr key={g.gold}>
                      <td className="py-2 px-4 font-mono font-bold">{g.gold}</td>
                      <td className="py-2 px-3 text-right font-mono">{g.n}</td>
                      <td className="py-2 px-3 text-right font-mono">{g.correct}</td>
                      <td className="py-2 px-3 text-right font-mono font-bold text-sky-700">
                        {g.accuracy.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-lg">⚠️</span>
                <h3 className="font-bold text-amber-900 text-sm">Đọc con số này thế nào</h3>
              </div>
              <p className="text-xs text-amber-900/90 leading-relaxed">{data.legal.caveat}</p>
              <p className="text-[11px] text-amber-800/70 font-mono pt-1 border-t border-amber-200">
                card {data.legal.measurement_card_hash.slice(0, 12)}… · {data.legal.blank_ids.length} câu blank
              </p>
            </div>
          </div>
        )}

        {/* NLI tab reuses the legal layout (binary A/B through the frozen MC runner) */}
        {tab === "nli" && data.legal_nli && (
          <div className="space-y-6">
            <div className="bg-gradient-to-r from-violet-900 via-purple-900 to-slate-900 text-white rounded-2xl p-6 sm:p-8 shadow-sm">
              <div className="space-y-3 max-w-3xl">
                <div className="flex items-center gap-2 text-violet-300 text-xs font-semibold uppercase tracking-wider">
                  <span>Nhị phân Có→A / Không→B · seed 42 · MC runner frozen</span>
                </div>
                <h2 className="text-2xl font-bold">Suy luận entailment — {data.legal_nli.overall.n} câu</h2>
                <p className="text-sm text-violet-100/80 leading-relaxed">
                  {data.legal_nli.condition}
                </p>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-violet-300 text-[11px] font-semibold uppercase tracking-wide">Accuracy</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.legal_nli.overall.accuracy.toFixed(2)}%</div>
                  <div className="text-[11px] text-violet-200/70 font-mono">
                    {data.legal_nli.overall.correct}/{data.legal_nli.overall.n}
                  </div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-violet-300 text-[11px] font-semibold uppercase tracking-wide">Baseline ({data.legal_nli.baseline.label})</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.legal_nli.baseline.majority_accuracy.toFixed(2)}%</div>
                  <div className="text-[11px] text-violet-200/70 font-mono">
                    {data.legal_nli.baseline.majority_n}/{data.legal_nli.overall.n}
                  </div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-violet-300 text-[11px] font-semibold uppercase tracking-wide">Hơn baseline</div>
                  <div className="text-2xl font-black font-mono mt-1 text-emerald-300">
                    +{(data.legal_nli.overall.accuracy - data.legal_nli.baseline.majority_accuracy).toFixed(2)}
                  </div>
                  <div className="text-[11px] text-violet-200/70">điểm phần trăm</div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-violet-300 text-[11px] font-semibold uppercase tracking-wide">Valid (parse được)</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.legal_nli.overall.valid}/{data.legal_nli.overall.n}</div>
                  <div className="text-[11px] text-violet-200/70 font-mono">
                    sai trong số parse được: {data.legal_nli.overall.wrong_parsed}
                  </div>
                </div>
              </div>
            </div>

            <DatasetStrip meta={data.datasetMeta["legal-nli-150"]} headline={`Accuracy ${data.legal_nli.overall.accuracy.toFixed(2)}% (${data.legal_nli.overall.correct}/${data.legal_nli.overall.n}) · baseline ${data.legal_nli.baseline.majority_accuracy.toFixed(2)}%`} />
            <TabInsight datasetId="legal-nli-150" modelId={activeModelId} block={data.legal_nli} />

            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
              <div className="p-5 border-b border-slate-200 bg-slate-50">
                <h3 className="font-bold text-slate-900 text-sm">
                  Accuracy theo đáp án đúng (Có=A / Không=B)
                </h3>
              </div>
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-100 text-slate-700 font-semibold">
                  <tr>
                    <th className="py-2 px-4">Đáp án đúng</th>
                    <th className="py-2 px-3 text-right">n</th>
                    <th className="py-2 px-3 text-right">Đúng</th>
                    <th className="py-2 px-3 text-right">Accuracy (%)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {data.legal_nli.by_gold.map((g) => (
                    <tr key={g.gold}>
                      <td className="py-2 px-4 font-mono font-bold">{g.gold}</td>
                      <td className="py-2 px-3 text-right font-mono">{g.n}</td>
                      <td className="py-2 px-3 text-right font-mono">{g.correct}</td>
                      <td className="py-2 px-3 text-right font-mono font-bold text-violet-700">
                        {g.accuracy.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-lg">⚠️</span>
                <h3 className="font-bold text-amber-900 text-sm">Đọc con số này thế nào</h3>
              </div>
              <p className="text-xs text-amber-900/90 leading-relaxed">{data.legal_nli.caveat}</p>
              <p className="text-[11px] text-amber-800/70 font-mono pt-1 border-t border-amber-200">
                card {data.legal_nli.measurement_card_hash.slice(0, 12)}… · {data.legal_nli.blank_ids.length} câu blank
              </p>
            </div>
          </div>
        )}

        {/* BidLQA tabs reuse the reading layout (single-source EM/F1, file gold) */}
        {(tab === "bidlqa-val" || tab === "bidlqa-test") &&
          (tab === "bidlqa-val" ? data.bidlqa_val : data.bidlqa_test) && (
            <ReadingTabView
              block={(tab === "bidlqa-val" ? data.bidlqa_val : data.bidlqa_test)!}
              title={tab === "bidlqa-val" ? "ViBidLQA val — 482 câu" : "ViBidLQA test — 603 câu"}
              eyebrow="File-gold · open-book · seed 42"
              meta={data.datasetMeta[tab]}
              datasetId={tab === "bidlqa-val" ? "bidlqa-val" : "bidlqa-test"}
              modelId={activeModelId}
            />
          )}

        {/* VM14K tab: legal-style MC hero + manifest breakdowns (difficulty / n_choices) */}
        {tab === "vm14k" && data.vm14k && (
          <div className="space-y-6">
            <div className="bg-gradient-to-r from-teal-900 via-cyan-900 to-slate-900 text-white rounded-2xl p-6 sm:p-8 shadow-sm">
              <div className="space-y-3 max-w-3xl">
                <div className="flex items-center gap-2 text-teal-300 text-xs font-semibold uppercase tracking-wider">
                  <span>Public release · shuffled0 · closed-book · seed 42 · card MC-14b</span>
                </div>
                <h2 className="text-2xl font-bold">Trắc nghiệm Y khoa — {data.vm14k.overall.n} câu</h2>
                <p className="text-sm text-teal-100/80 leading-relaxed">
                  {data.vm14k.condition}
                </p>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-teal-300 text-[11px] font-semibold uppercase tracking-wide">Accuracy</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.vm14k.overall.accuracy.toFixed(2)}%</div>
                  <div className="text-[11px] text-teal-200/70 font-mono">
                    {data.vm14k.overall.correct}/{data.vm14k.overall.n}
                  </div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-teal-300 text-[11px] font-semibold uppercase tracking-wide">Baseline ({data.vm14k.baseline.label})</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.vm14k.baseline.majority_accuracy.toFixed(2)}%</div>
                  <div className="text-[11px] text-teal-200/70 font-mono">
                    {data.vm14k.baseline.majority_n}/{data.vm14k.overall.n}
                  </div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-teal-300 text-[11px] font-semibold uppercase tracking-wide">Hơn baseline</div>
                  <div className="text-2xl font-black font-mono mt-1 text-emerald-300">
                    +{(data.vm14k.overall.accuracy - data.vm14k.baseline.majority_accuracy).toFixed(2)}
                  </div>
                  <div className="text-[11px] text-teal-200/70">điểm phần trăm</div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-teal-300 text-[11px] font-semibold uppercase tracking-wide">Valid (parse được)</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.vm14k.overall.valid}/{data.vm14k.overall.n}</div>
                  <div className="text-[11px] text-teal-200/70 font-mono">
                    sai trong số parse được: {data.vm14k.overall.wrong_parsed}
                  </div>
                </div>
              </div>
            </div>

            <DatasetStrip meta={data.datasetMeta["vm14k-public-12488"]} headline={`Accuracy ${data.vm14k.overall.accuracy.toFixed(2)}% (${data.vm14k.overall.correct}/${data.vm14k.overall.n}) · baseline ${data.vm14k.baseline.majority_accuracy.toFixed(2)}%`} />
            <TabInsight datasetId="vm14k-public-12488" modelId={activeModelId} block={data.vm14k} />

            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
              <div className="p-5 border-b border-slate-200 bg-slate-50">
                <h3 className="font-bold text-slate-900 text-sm">
                  Accuracy theo nhóm chuyên khoa (9 nhóm + unknown)
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Nhóm = tag đầu tiên của medical_topic (taxonomy tiền đăng ký); Nội khoa chiếm một nửa bộ
                </p>
              </div>
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-100 text-slate-700 font-semibold">
                  <tr>
                    <th className="py-2 px-4">Nhóm chuyên khoa</th>
                    <th className="py-2 px-3 text-right">n</th>
                    <th className="py-2 px-3 text-right">Đúng</th>
                    <th className="py-2 px-3 text-right">Accuracy (%)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {data.vm14k.by_category.map((d) => (
                    <tr key={d.category}>
                      <td className="py-2 px-4 font-semibold">{d.category}</td>
                      <td className="py-2 px-3 text-right font-mono">{d.n}</td>
                      <td className="py-2 px-3 text-right font-mono">{d.correct}</td>
                      <td className="py-2 px-3 text-right font-mono font-bold text-teal-700">
                        {d.accuracy.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
                <div className="p-5 border-b border-slate-200 bg-slate-50">
                  <h3 className="font-bold text-slate-900 text-sm">
                    Accuracy theo độ khó tự khai báo
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Thang độ khó của bộ có tín hiệu (giảm đơn điệu)
                  </p>
                </div>
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-100 text-slate-700 font-semibold">
                    <tr>
                      <th className="py-2 px-4">Độ khó</th>
                      <th className="py-2 px-3 text-right">n</th>
                      <th className="py-2 px-3 text-right">Đúng</th>
                      <th className="py-2 px-3 text-right">Accuracy (%)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {data.vm14k.by_difficulty.map((d) => (
                      <tr key={d.difficulty}>
                        <td className="py-2 px-4 font-semibold">{d.difficulty}</td>
                        <td className="py-2 px-3 text-right font-mono">{d.n}</td>
                        <td className="py-2 px-3 text-right font-mono">{d.correct}</td>
                        <td className="py-2 px-3 text-right font-mono font-bold text-teal-700">
                          {d.accuracy.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
                <div className="p-5 border-b border-slate-200 bg-slate-50">
                  <h3 className="font-bold text-slate-900 text-sm">
                    Accuracy theo số lựa chọn
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Câu Đúng/Sai (2 lựa chọn) kéo điểm tổng lên — báo 4-lựa-chọn làm số chính
                  </p>
                </div>
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-100 text-slate-700 font-semibold">
                    <tr>
                      <th className="py-2 px-4">Số lựa chọn</th>
                      <th className="py-2 px-3 text-right">n</th>
                      <th className="py-2 px-3 text-right">Đúng</th>
                      <th className="py-2 px-3 text-right">Accuracy (%)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {data.vm14k.by_n_choices.map((d) => (
                      <tr key={d.n_choices}>
                        <td className="py-2 px-4 font-mono font-bold">{d.n_choices}</td>
                        <td className="py-2 px-3 text-right font-mono">{d.n}</td>
                        <td className="py-2 px-3 text-right font-mono">{d.correct}</td>
                        <td className="py-2 px-3 text-right font-mono font-bold text-teal-700">
                          {d.accuracy.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
              <div className="p-5 border-b border-slate-200 bg-slate-50">
                <h3 className="font-bold text-slate-900 text-sm">
                  Accuracy theo đáp án đúng
                </h3>
              </div>
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-100 text-slate-700 font-semibold">
                  <tr>
                    <th className="py-2 px-4">Đáp án đúng</th>
                    <th className="py-2 px-3 text-right">n</th>
                    <th className="py-2 px-3 text-right">Đúng</th>
                    <th className="py-2 px-3 text-right">Accuracy (%)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {data.vm14k.by_gold.map((g) => (
                    <tr key={g.gold}>
                      <td className="py-2 px-4 font-mono font-bold">{g.gold}</td>
                      <td className="py-2 px-3 text-right font-mono">{g.n}</td>
                      <td className="py-2 px-3 text-right font-mono">{g.correct}</td>
                      <td className="py-2 px-3 text-right font-mono font-bold text-teal-700">
                        {g.accuracy.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-lg">⚠️</span>
                <h3 className="font-bold text-amber-900 text-sm">Đọc con số này thế nào</h3>
              </div>
              <p className="text-xs text-amber-900/90 leading-relaxed">{data.vm14k.caveat}</p>
              <p className="text-[11px] text-amber-800/70 font-mono pt-1 border-t border-amber-200">
                card {data.vm14k.measurement_card_hash.slice(0, 12)}… · {data.vm14k.blank_ids.length} câu blank
              </p>
            </div>
          </div>
        )}

      </main>

      {/* MODAL INSPECTOR */}
      {selectedQuestion && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold px-2 py-0.5 bg-slate-200 text-slate-800 rounded">
                  {selectedQuestion.id}
                </span>
                <span className="text-xs font-semibold text-slate-600">
                  {selectedQuestion.category}
                </span>
              </div>
              <button
                onClick={() => setSelectedQuestion(null)}
                className="w-7 h-7 rounded-lg hover:bg-slate-200 text-slate-500 hover:text-slate-800 flex items-center justify-center font-bold text-lg"
              >
                &times;
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4 text-xs">
              <div>
                <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                  Nội dung câu hỏi:
                </div>
                <div className="text-sm font-medium text-slate-900 leading-relaxed bg-slate-50 p-3 rounded-lg border border-slate-200">
                  {selectedQuestion.question}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg border border-slate-200 bg-slate-50">
                  <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Mô hình chọn:
                  </div>
                  <div
                    className={`text-xl font-mono font-black mt-1 ${
                      selectedQuestion.correct ? "text-emerald-600" : "text-rose-600"
                    }`}
                  >
                    {selectedQuestion.answer || "N/A"}
                  </div>
                </div>
                <div className="p-3 rounded-lg border border-emerald-200 bg-emerald-50">
                  <div className="text-[11px] font-bold text-emerald-700 uppercase tracking-wider">
                    Đáp án chuẩn (Gold):
                  </div>
                  <div className="text-xl font-mono font-black text-emerald-700 mt-1">
                    {selectedQuestion.gold_answer}
                  </div>
                </div>
              </div>

              <div>
                <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                  Phản hồi nguyên bản (Raw Response):
                </div>
                <pre className="bg-slate-900 text-slate-100 p-3.5 rounded-lg font-mono text-[11.5px] overflow-x-auto whitespace-pre-wrap max-h-48 border border-slate-800">
                  {selectedQuestion.raw_response || "(Trống)"}
                </pre>
              </div>

              <div>
                <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                  Đề bài & Các lựa chọn A/B/C/D (Prompt):
                </div>
                <pre className="bg-slate-100 text-slate-800 p-3.5 rounded-lg text-[11.5px] overflow-x-auto whitespace-pre-wrap max-h-48 border border-slate-200">
                  {selectedQuestion.prompt || "(Trống)"}
                </pre>
              </div>
            </div>

            <div className="p-3 border-t border-slate-200 bg-slate-50 flex justify-end">
              <button
                onClick={() => setSelectedQuestion(null)}
                className="px-4 py-1.5 text-xs font-semibold bg-slate-800 text-white rounded-lg hover:bg-slate-700"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}

      {/* RIGHT RAIL — sticky model + dataset switcher */}

      <aside className="hidden lg:block w-72 shrink-0 sticky top-24 space-y-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs space-y-3">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Model</p>
            <div className="mt-1.5 space-y-1.5" role="radiogroup" aria-label="Chọn model">
              {models.map((m) => {
                const active = m.id === activeModelId;
                return (
                  <button
                    key={m.id}
                    role="radio"
                    aria-checked={active}
                    onClick={() => {
                      if (!active) onModelChange(m.id);
                    }}
                    className={`w-full text-left px-3 py-2 rounded-xl border text-xs transition-colors ${
                      active
                        ? "border-indigo-600 bg-indigo-50 text-indigo-900 font-bold"
                        : "border-slate-200 bg-white text-slate-700 hover:border-indigo-300 hover:bg-indigo-50/50"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full shrink-0 ${active ? "bg-indigo-600" : "bg-slate-300"}`}
                      ></span>
                      <span className="font-mono truncate">{m.display_name}</span>
                    </span>
                    <span className="block font-mono text-[10.5px] text-slate-400 truncate mt-0.5 ml-4">
                      {m.id}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="border-t border-slate-100 pt-3">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Dataset</p>
            <div className="mt-1.5 space-y-1.5">
              {tabs.map((t) => {
                const active = tab === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => setTab(t.id)}
                    className={`w-full flex items-center justify-between gap-2 px-3 py-2 rounded-xl border text-xs transition-colors ${
                      active
                        ? "border-indigo-600 bg-indigo-600 text-white font-bold shadow-sm"
                        : "border-slate-200 bg-white text-slate-700 hover:border-indigo-300 hover:bg-indigo-50/50"
                    }`}
                  >
                    <span className="truncate">{t.label}</span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10.5px] font-mono font-bold shrink-0 ${active ? "bg-white/20 text-white" : t.badgeClass}`}
                    >
                      {t.badge}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </aside>
      </div>

      {/* MOBILE dataset switcher (rail is lg+) */}
      <div className="lg:hidden max-w-7xl mx-auto px-4 sm:px-6 pb-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-2xs flex gap-2 overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-2 text-xs font-semibold rounded-xl border whitespace-nowrap transition-colors ${
                tab === t.id
                  ? "border-indigo-600 bg-indigo-600 text-white"
                  : "border-slate-200 bg-white text-slate-600"
              }`}
            >
              {t.label} · {t.badge}
            </button>
          ))}
        </div>
      </div>

    </div>
  );
}
