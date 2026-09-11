"use client";

import { useState, useMemo } from "react";
import Link from "next/link";

interface VmluSubject {
  code: string;
  name: string;
  full_name: string;
  category: string;
  n: number;
  correct: number;
  accuracy: number;
}

interface VmluQuestion {
  id: string;
  subject_code: string;
  category: string;
  question: string;
  prompt: string;
  raw_response: string;
  answer: string;
  gold_answer: string;
  correct: boolean;
}

interface VbenchDomain {
  domain: string;
  name: string;
  track: string;
  score: number;
  correct: number;
  total: number;
  category: string;
  icon?: string;
}

interface VbenchFailure {
  id: number;
  domain: string;
  track: string;
  reason: string;
  failure_class: string;
  raw_response: string;
}

interface ReadingStratum {
  stratum: string;
  label: string;
  n: number;
  em_count: number;
  em: number;
  char_f1: number;
}

interface ReadingSource {
  label: string;
  n: number;
  em_count: number;
  em: number;
  char_f1: number;
  reject_count: number;
  strata: ReadingStratum[];
}

interface ReadingBlock {
  benchmark_name: string;
  date: string;
  condition: string;
  measurement_card_hash: string;
  overall: { n: number; em_count: number; em: number; char_f1: number; label: string };
  sources: ReadingSource[];
  caveat: string;
  scorer: string;
}

interface BenchmarkData {
  model_info: {
    model_name: string;
    framework: string;
    parameters: string;
    quantization: string;
    hardware: string;
    inference_settings: string;
  };
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
}

export function BenchmarkDashboard({
  data,
  questions,
}: {
  data: BenchmarkData;
  questions: VmluQuestion[];
}) {
  const [tab, setTab] = useState<"vmlu" | "vbench" | "reading" | "synthesis">("vmlu");

  // VMLU filters
  const [vmluCat, setVmluCat] = useState<string>("ALL");
  const [vmluSearch, setVmluSearch] = useState<string>("");
  const [vmluSortAsc, setVmluSortAsc] = useState<boolean>(false);

  // Question Explorer filters
  const [qStatus, setQStatus] = useState<"ALL" | "CORRECT" | "INCORRECT">("ALL");
  const [qCat, setQCat] = useState<string>("ALL");
  const [qSearch, setQSearch] = useState<string>("");

  // Modal
  const [selectedQuestion, setSelectedQuestion] = useState<VmluQuestion | null>(null);
  const [selectedFailure, setSelectedFailure] = useState<VbenchFailure | null>(null);

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

  // Filtered Questions
  const filteredQuestions = useMemo(() => {
    return questions.filter((q) => {
      if (qStatus === "CORRECT" && !q.correct) return false;
      if (qStatus === "INCORRECT" && q.correct) return false;
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
  }, [questions, qStatus, qCat, qSearch]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* TOP HEADER */}
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
                    v2026.09
                  </span>
                </div>
                <p className="text-xs text-slate-500">
                  Đối chiếu thực nghiệm đa chiều VMLU (58 Môn) & V-Bench Public Test
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
              <div className="hidden md:flex items-center gap-2 bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 text-xs">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span className="text-slate-500">Model:</span>
                <span className="font-semibold text-slate-800 font-mono">
                  {data.model_info.model_name}
                </span>
              </div>
            </div>
          </div>

          {/* TAB BUTTONS */}
          <div className="flex border-t border-slate-100 space-x-2 sm:space-x-4 pt-1">
            <button
              onClick={() => setTab("vmlu")}
              className={`px-4 py-2.5 text-sm font-semibold border-b-2 flex items-center gap-2 transition-colors ${
                tab === "vmlu"
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              <span>🇻🇳 VMLU Benchmark</span>
              <span className="px-1.5 py-0.5 rounded text-xs bg-indigo-50 text-indigo-700 font-mono font-bold">
                73.35%
              </span>
            </button>

            <button
              onClick={() => setTab("vbench")}
              className={`px-4 py-2.5 text-sm font-semibold border-b-2 flex items-center gap-2 transition-colors ${
                tab === "vbench"
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              <span>🚀 V-Bench (13 Domains)</span>
              <span className="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-700 font-mono font-bold">
                44.97
              </span>
            </button>

            <button
              onClick={() => setTab("reading")}
              className={`px-4 py-2.5 text-sm font-semibold border-b-2 flex items-center gap-2 transition-colors ${
                tab === "reading"
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              <span>📖 Đọc hiểu (400 câu)</span>
              <span className="px-1.5 py-0.5 rounded text-xs bg-emerald-50 text-emerald-700 font-mono font-bold">
                EM {data.reading.overall.em}%
              </span>
            </button>

            <button
              onClick={() => setTab("synthesis")}
              className={`px-4 py-2.5 text-sm font-semibold border-b-2 flex items-center gap-2 transition-colors ${
                tab === "synthesis"
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              <span>⚖️ Đối sánh & Định hướng AER-Legal</span>
              <span className="px-1.5 py-0.5 rounded text-xs bg-amber-100 text-amber-800 font-semibold">
                Pareto Insights
              </span>
            </button>
          </div>
        </div>
      </header>

      {/* BODY CONTENT */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
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

            {/* QUESTION EXPLORER */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-5 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
                <div>
                  <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                    <span>🔍 Trình Duyệt Câu Hỏi VMLU (Question Explorer)</span>
                    <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-indigo-100 text-indigo-800">
                      {filteredQuestions.length} câu
                    </span>
                  </h3>
                  <p className="text-xs text-slate-500">
                    Tra cứu đề bài, đáp án mô hình chọn so với đáp án chuẩn và kiểm tra raw response
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={qStatus}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === "ALL" || v === "CORRECT" || v === "INCORRECT") setQStatus(v);
                    }}
                    className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-slate-50 font-medium"
                  >
                    <option value="ALL">Tất cả kết quả</option>
                    <option value="CORRECT">✅ Chỉ xem câu Đúng (768)</option>
                    <option value="INCORRECT">❌ Chỉ xem câu Sai (279)</option>
                  </select>

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
                    className={`p-4 rounded-xl border transition-all cursor-pointer ${
                      q.correct
                        ? "border-slate-200 bg-white hover:border-emerald-300"
                        : "border-rose-200 bg-rose-50/20 hover:border-rose-400"
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-mono font-bold ${
                            q.correct ? "text-slate-600" : "text-rose-700"
                          }`}
                        >
                          {q.id}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10.5px] bg-slate-100 text-slate-600">
                          {q.category}
                        </span>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                          q.correct
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {q.correct
                          ? `✅ Đúng (${q.answer})`
                          : `❌ Sai (Chọn ${q.answer} / Đúng: ${q.gold_answer})`}
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

            {/* Agentic Breakdown & Failure Ledger */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Failure summary */}
              <div className="lg:col-span-1 bg-white rounded-xl border border-slate-200 shadow-2xs p-5 space-y-4">
                <div className="border-b border-slate-100 pb-3">
                  <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-purple-600"></span>
                    Phân Loại 15 Câu Agentic Bị Từ Chối
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Chỉ có 15 / 1.000 câu không qua được cú pháp nghiêm ngặt
                  </p>
                </div>
                <div className="space-y-3">
                  {data.vbench.failure_summary.map((f) => (
                    <div key={f.class} className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900 text-xs">{f.class}</span>
                        <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-800 font-mono font-bold text-xs">
                          {f.count} câu
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-600 mt-1">{f.desc}</p>
                      <div className="text-[10.5px] font-mono text-slate-400 mt-1">
                        Câu: {f.examples}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="p-3 bg-purple-50 rounded-lg border border-purple-100 text-xs text-purple-900 leading-relaxed">
                  <strong>💡 Phát hiện khoa học:</strong> 98.5% câu Agentic đáp ứng cấu trúc gọi hàm
                  hoàn hảo, nhưng chỉ 39.1% đúng ngữ nghĩa. Điểm nghẽn là nhận diện công cụ chứ không
                  phải format JSON.
                </div>
              </div>

              {/* Rejected items */}
              <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-2xs p-5 space-y-4">
                <div className="border-b border-slate-100 pb-3 flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-slate-900 text-sm">
                      Sổ Ghi Nhận Thất Bại (Failure Ledger — 15 Items)
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Bấm vào từng câu để kiểm tra chi tiết phản hồi nguyên bản của mô hình
                    </p>
                  </div>
                  <span className="text-xs font-mono font-bold text-rose-700 bg-rose-50 px-2.5 py-1 rounded border border-rose-200">
                    15 Rejected Rows
                  </span>
                </div>
                <div className="space-y-2.5 max-h-[440px] overflow-y-auto pr-1">
                  {data.vbench.rejected_items.map((item) => (
                    <div
                      key={item.id}
                      onClick={() => setSelectedFailure(item)}
                      className="p-3 rounded-lg border border-slate-200 hover:border-purple-300 hover:bg-purple-50/30 transition-all cursor-pointer"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                            ID #{item.id}
                          </span>
                          <span className="font-semibold text-slate-800">
                            {item.failure_class}
                          </span>
                        </div>
                        <span className="text-[11px] font-mono text-rose-600">{item.reason}</span>
                      </div>
                      <div className="mt-2 text-[11px] text-slate-600 font-mono bg-slate-50 p-2 rounded truncate border border-slate-100">
                        {item.raw_response}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Prompt ablation */}
            <div className="bg-amber-50 rounded-xl p-5 border border-amber-200 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="text-xs font-bold uppercase tracking-wider text-amber-800">
                  🔬 Kết quả Nghiên cứu Ablation (Prompt Variance)
                </div>
                <h4 className="font-bold text-slate-900 text-base">
                  Tác động của Prompt Engineering lên Năng Lực Agentic
                </h4>
                <p className="text-xs text-slate-700 max-w-3xl leading-relaxed">
                  So sánh cùng model Qwen3.8-27B giữa Minimal Prompt vs Detailed Prompt: có tới{" "}
                  <strong>42.2% câu trả lời bị xáo trộn</strong> (415/983), trong đó{" "}
                  <strong>213 câu thay đổi hẳn hàm được chọn</strong>. Đo lường tách bạch là điều kiện
                  tiên quyết để đo đúng thực chất năng lực.
                </p>
              </div>
              <div className="text-right shrink-0 bg-white px-4 py-3 rounded-lg border border-amber-300 shadow-2xs">
                <div className="text-2xl font-black font-mono text-amber-700">42.2%</div>
                <div className="text-[11px] text-slate-500">Tỷ lệ đổi đáp án</div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================== */}
        {/* TAB 3: READING COMPREHENSION (400 pre-registered) */}
        {/* ========================================================== */}
        {tab === "reading" && (
          <div className="space-y-6">
            <div className="bg-gradient-to-r from-emerald-900 via-teal-900 to-slate-900 text-white rounded-2xl p-6 sm:p-8 shadow-sm">
              <div className="space-y-3 max-w-3xl">
                <div className="flex items-center gap-2 text-emerald-300 text-xs font-semibold uppercase tracking-wider">
                  <span>Tiền đăng ký · seed 42 · 200 Vi-SQuAD + 200 Vi-DROP</span>
                </div>
                <h2 className="text-2xl font-bold">Bài kiểm tra Đọc hiểu — {data.reading.overall.n} câu</h2>
                <p className="text-sm text-emerald-100/80 leading-relaxed">
                  {data.reading.condition}
                </p>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-emerald-300 text-[11px] font-semibold uppercase tracking-wide">Số câu (n)</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.reading.overall.n}</div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-emerald-300 text-[11px] font-semibold uppercase tracking-wide">EM</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.reading.overall.em}%</div>
                  <div className="text-[11px] text-emerald-200/70 font-mono">
                    {data.reading.overall.em_count}/{data.reading.overall.n}
                  </div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-emerald-300 text-[11px] font-semibold uppercase tracking-wide">char-F1</div>
                  <div className="text-2xl font-black font-mono mt-1">{data.reading.overall.char_f1}%</div>
                </div>
                <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
                  <div className="text-emerald-300 text-[11px] font-semibold uppercase tracking-wide">Chênh EM→F1</div>
                  <div className="text-2xl font-black font-mono mt-1 text-amber-300">
                    {(data.reading.overall.char_f1 - data.reading.overall.em).toFixed(2)}
                  </div>
                  <div className="text-[11px] text-emerald-200/70">điểm</div>
                </div>
              </div>
            </div>

            {/* Per-source cards */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {data.reading.sources.map((src) => (
                <div key={src.label} className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
                  <div className="p-5 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
                    <div>
                      <h3 className="font-bold text-slate-900">{src.label}</h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        n = {src.n} · {src.reject_count} câu bị người duyệt bác
                      </p>
                    </div>
                    <div className="text-right">
                      <div className="text-xl font-black font-mono text-emerald-600">{src.em}%</div>
                      <div className="text-[11px] text-slate-500 font-mono">EM · F1 {src.char_f1}%</div>
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

            {/* Caveat box — the honest reading of these numbers */}
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-lg">⚠️</span>
                <h3 className="font-bold text-amber-900 text-sm">Đọc con số này thế nào</h3>
              </div>
              <p className="text-xs text-amber-900/90 leading-relaxed">{data.reading.caveat}</p>
              <p className="text-[11px] text-amber-800/70 font-mono pt-1 border-t border-amber-200">
                scorer: {data.reading.scorer} · card {data.reading.measurement_card_hash.slice(0, 12)}…
              </p>
            </div>
          </div>
        )}

        {/* ========================================================== */}
        {/* TAB 4: CROSS-BENCHMARK SYNTHESIS */}
        {/* ========================================================== */}
        {tab === "synthesis" && (
          <div className="space-y-6">
            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-2xs space-y-4">
              <div className="max-w-3xl">
                <span className="px-2.5 py-1 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                  Luận Điểm Khoa Học Khóa Luận
                </span>
                <h2 className="text-2xl font-bold text-slate-900 mt-2">
                  Đối sánh Hai Bộ Chuẩn & Cơ Sở Kiến Trúc AER-Legal
                </h2>
                <p className="text-sm text-slate-600 mt-1 leading-relaxed">
                  Phân tích đối chứng giữa <strong>VMLU (1,047 câu)</strong> và{" "}
                  <strong>V-Bench (5,141 câu)</strong> bộc lộ quy luật cốt lõi giải thích vì sao mô
                  hình reasoning cần cơ chế định tuyến tri thức (Epistemic Routing) thay vì ReAct phổ
                  quát.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-sm">
                    1
                  </div>
                  <h4 className="font-bold text-slate-900 text-sm">Vùng Tri Thức Tham Số Vững</h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    STEM và CS đều đạt đỉnh ở cả hai benchmark (VMLU STEM đạt 79.4%, V-Bench CS đạt
                    70.2%). Mô hình ghi nhớ kiến thức tự nhiên rất tốt.
                  </p>
                  <div className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-2 py-1 rounded border border-emerald-200">
                    👉 Fast Path: Zero-shot, tắt CoT để tiết kiệm token
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-rose-100 text-rose-700 flex items-center justify-center font-bold text-sm">
                    2
                  </div>
                  <h4 className="font-bold text-slate-900 text-sm">Vùng Trũng Tri Thức Quy Chuẩn</h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    Các môn Pháp luật, Thuế, và Nghiệp vụ công chức rớt xuống 30–47% trên VMLU. Đây là
                    tri thức quy định không thể suy luận logic tự thân.
                  </p>
                  <div className="text-xs font-semibold text-rose-700 bg-rose-50 px-2 py-1 rounded border border-rose-200">
                    👉 Evidence Path: Bắt buộc RAG với VBPL Corpus
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center font-bold text-sm">
                    3
                  </div>
                  <h4 className="font-bold text-slate-900 text-sm">Điểm Nghẽn Tính Toán & Logic</h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    V-Bench Toán (19.2%) và Logic (24.0%) thấp hơn cả xác suất đoán ngẫu nhiên. VMLU
                    Toán tiểu học cũng chỉ đạt 40%. Không có CoT/Calculator, model đoán mò.
                  </p>
                  <div className="text-xs font-semibold text-amber-700 bg-amber-50 px-2 py-1 rounded border border-amber-200">
                    👉 Deep Path: Bật Thinking mode / Python Evaluator
                  </div>
                </div>
              </div>
            </div>

            {/* Cross table */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
              <div className="p-5 border-b border-slate-200 bg-slate-50">
                <h3 className="font-bold text-slate-900 text-sm">
                  Bảng So Sánh Đối Đầu Theo Lĩnh Vực Tương Đồng
                </h3>
              </div>
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-100 text-slate-700 font-semibold">
                  <tr>
                    <th className="py-3 px-4">Lĩnh vực kiến thức</th>
                    <th className="py-3 px-4">Độ chính xác trên VMLU</th>
                    <th className="py-3 px-4">Độ chính xác trên V-Bench</th>
                    <th className="py-3 px-4">Nhận định & Chiến lược định tuyến</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  <tr>
                    <td className="py-3 px-4 font-semibold">Công nghệ thông tin / CS</td>
                    <td className="py-3 px-4 font-mono font-bold text-emerald-600">
                      77.5% (Kiến trúc MT, Mạng, Lập trình)
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-emerald-600">
                      70.21% (Computer Science)
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                        Thế mạnh
                      </span>{" "}
                      — Không cần can thiệp tool.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 font-semibold">Triết học & Tư tưởng</td>
                    <td className="py-3 px-4 font-mono font-bold text-emerald-600">
                      74.3% (Mác-Lênin, Tư tưởng HCM)
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-emerald-600">
                      64.64% (Philosophy)
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                        Tương đồng
                      </span>{" "}
                      — Ghi nhớ tốt các học thuyết lớn.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 font-semibold">Văn học & Ngôn ngữ</td>
                    <td className="py-3 px-4 font-mono font-bold text-amber-600">
                      45.0% (Văn THCS, Văn THPT)
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-amber-600">
                      40.77% (Literature)
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-800">
                        Yếu vừa
                      </span>{" "}
                      — Dễ nhầm tác giả, trích đoạn thơ.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 font-semibold">Pháp luật chuyên ngành</td>
                    <td className="py-3 px-4 font-mono font-bold text-rose-600">
                      30.0% – 47.1% (Hành chính, Kinh tế)
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-blue-600">
                      60.73% (Laws - lý thuyết đại cương)
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-800">
                        Đột phá
                      </span>{" "}
                      — Bắt buộc phải có Grounded Retrieval VBPL.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 font-semibold">Toán học & Suy luận rời rạc</td>
                    <td className="py-3 px-4 font-mono font-bold text-rose-600">
                      40.0% (Toán tiểu học)
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-rose-600">
                      19.20% (Toán) / 24.0% (Logic)
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-800">
                        Điểm chết
                      </span>{" "}
                      — Không có CoT/Calculator sẽ đoán mò.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Pareto formula box */}
            <div className="bg-gradient-to-br from-slate-900 to-indigo-950 text-white rounded-xl p-6 space-y-4">
              <h3 className="font-bold text-lg text-emerald-400">
                Chỉ Số Tối Ưu Hóa Cân Bằng Đa Mục Tiêu (Pareto Frontier)
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Trong đề tài khóa luận <strong>AER-Legal</strong>, mục tiêu là tối ưu hóa chỉ số hiệu quả
                chi phí $E_{"{pareto}"}$ bằng cách hạn chế tối đa việc sinh token suy luận thừa ở các câu hỏi
                dễ:
              </p>
              <div className="bg-black/30 p-4 rounded-lg font-mono text-sm text-center border border-white/10">
                E_pareto = Accuracy(%) / log10(T_avg)
              </div>
              <p className="text-xs text-slate-400 text-center">
                Trong đó $T_{"{avg}"}$ là số lượng output tokens trung bình cho mỗi câu trả lời. AER-Legal
                dự kiến đạt ngang ngửa điểm số của chế độ luôn bật Thinking nhưng tiết kiệm{" "}
                <strong>40%–60% lượng token</strong>.
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

      {/* MODAL FAILURE INSPECTOR */}
      {selectedFailure && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold px-2 py-0.5 bg-purple-100 text-purple-800 rounded">
                  V-Bench #{selectedFailure.id}
                </span>
                <span className="text-xs font-semibold text-slate-600">
                  {selectedFailure.domain} ({selectedFailure.track})
                </span>
              </div>
              <button
                onClick={() => setSelectedFailure(null)}
                className="w-7 h-7 rounded-lg hover:bg-slate-200 text-slate-500 hover:text-slate-800 flex items-center justify-center font-bold text-lg"
              >
                &times;
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4 text-xs">
              <div>
                <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                  Nhóm lỗi & Lý do từ chối:
                </div>
                <div className="text-sm font-semibold text-rose-700 bg-rose-50 p-3 rounded-lg border border-rose-200">
                  {selectedFailure.failure_class} ({selectedFailure.reason})
                </div>
              </div>

              <div>
                <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                  Phản hồi nguyên bản của mô hình:
                </div>
                <pre className="bg-slate-900 text-slate-100 p-3.5 rounded-lg font-mono text-[11.5px] overflow-x-auto whitespace-pre-wrap max-h-64 border border-slate-800">
                  {selectedFailure.raw_response}
                </pre>
              </div>
            </div>

            <div className="p-3 border-t border-slate-200 bg-slate-50 flex justify-end">
              <button
                onClick={() => setSelectedFailure(null)}
                className="px-4 py-1.5 text-xs font-semibold bg-slate-800 text-white rounded-lg hover:bg-slate-700"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
