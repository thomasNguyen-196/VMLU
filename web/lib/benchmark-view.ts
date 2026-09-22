/** Assembled benchmark view-model (change results-into-benchmark).
 *
 * One deep module: all Mongo reads + shaping live here; page.tsx stays a
 * thin pass-through (`getBenchmarkView(modelId)` → props). Numbers are
 * NEVER recomputed from items — overall/category/subject rows come from
 * the precomputed `summaries.accuracy_rows`, EM/F1 from `reading_rows`,
 * V-Bench micro/macro from `server_rows`. Baselines and by-gold splits
 * are the only derived numbers (counted from mc_items gold/correct, no
 * gold stored anywhere else). Reading strata EM can only come from
 * items today (summaries carry no stratum rows) — computed on demand
 * per (run, source) and cached per request.
 *
 * Blob-only content (failure ledger, ablation, synthesis prose) has no DB
 * counterpart and is intentionally dropped: the merged page shows live
 * DB numbers with the benchmark look, not the frozen commentary.
 */

import {
  getDatasets,
  getItemsPage,
  getModels,
  getRuns,
  getSummary,
  type DatasetDoc,
  type ModelDoc,
  type RunDoc,
} from "./db.ts";

export const SUBJECTS: Record<number, { name: string; category: string }> = {
  1: { name: "Elementary Mathematics", category: "STEM" },
  2: { name: "Elementary Science", category: "STEM" },
  3: { name: "Middle School Biology", category: "STEM" },
  4: { name: "Middle School Chemistry", category: "STEM" },
  5: { name: "Middle School Mathematics", category: "STEM" },
  6: { name: "Middle School Physics", category: "STEM" },
  7: { name: "High School Biology", category: "STEM" },
  8: { name: "High School Chemistry", category: "STEM" },
  9: { name: "High School Mathematics", category: "STEM" },
  10: { name: "High School Physics", category: "STEM" },
  11: { name: "Applied Informatics", category: "STEM" },
  12: { name: "Computer Architecture", category: "STEM" },
  13: { name: "Computer Network", category: "STEM" },
  14: { name: "Discrete Mathematics", category: "STEM" },
  15: { name: "Electrical Engineering", category: "STEM" },
  16: { name: "Introduction to Chemistry", category: "STEM" },
  17: { name: "Introduction to Physics", category: "STEM" },
  18: { name: "Introduction to Programming", category: "STEM" },
  19: { name: "Metrology Engineer", category: "STEM" },
  20: { name: "Operating System", category: "STEM" },
  21: { name: "Statistics and Probability", category: "STEM" },
  22: { name: "Middle School Civil Education", category: "Social Science" },
  23: { name: "Middle School Geography", category: "Social Science" },
  24: { name: "High School Civil Education", category: "Social Science" },
  25: { name: "High School Geography", category: "Social Science" },
  26: { name: "Business Administration", category: "Social Science" },
  27: { name: "Ho Chi Minh Ideology", category: "Social Science" },
  28: { name: "Macroeconomics", category: "Social Science" },
  29: { name: "Microeconomics", category: "Social Science" },
  30: { name: "Principles of Marxism and Leninism", category: "Social Science" },
  31: { name: "Sociology", category: "Social Science" },
  32: { name: "Elementary History", category: "Humanity" },
  33: { name: "Middle School History", category: "Humanity" },
  34: { name: "Middle School Literature", category: "Humanity" },
  35: { name: "High School History", category: "Humanity" },
  36: { name: "High School Literature", category: "Humanity" },
  37: { name: "Administrative Law", category: "Humanity" },
  38: { name: "Business Law", category: "Humanity" },
  39: { name: "Civil Law", category: "Humanity" },
  40: { name: "Criminal Law", category: "Humanity" },
  41: { name: "Economic Law", category: "Humanity" },
  42: { name: "Education Law", category: "Humanity" },
  43: { name: "History of World Civilization", category: "Humanity" },
  44: { name: "Idealogical and Moral Cultivation", category: "Humanity" },
  45: { name: "Introduction to Laws", category: "Humanity" },
  46: { name: "Introduction to Vietnam Culture", category: "Humanity" },
  47: { name: "Logic", category: "Humanity" },
  48: { name: "Revolutionary Policy of the Vietnamese Commununist Part", category: "Humanity" },
  49: { name: "Vietnamese Language and Literature", category: "Humanity" },
  50: { name: "Accountant", category: "Other" },
  51: { name: "Clinical Pharmacology", category: "Other" },
  52: { name: "Environmental Engineering", category: "Other" },
  53: { name: "Internal Basic Medicine", category: "Other" },
  54: { name: "Preschool Pedagogy", category: "Other" },
  55: { name: "Tax Accountant", category: "Other" },
  56: { name: "Tax Civil Servant", category: "Other" },
  57: { name: "Civil Servant", category: "Other" },
  58: { name: "Driving License Certificate", category: "Other" },
};

export const DOMAIN_META: Record<string, { name: string; icon: string; category: string }> = {
  computer_science: { name: "Khoa học Máy tính (CS)", icon: "💻", category: "STEM" },
  philosophy: { name: "Triết học (Philosophy)", icon: "🏛️", category: "Humanity" },
  laws: { name: "Pháp luật (Laws)", icon: "⚖️", category: "Social" },
  dialect: { name: "Phương ngữ Việt (Dialect)", icon: "🗣️", category: "Linguistics" },
  psychology: { name: "Tâm lý học (Psychology)", icon: "🧠", category: "Social" },
  culture: { name: "Văn hóa Việt Nam (Culture)", icon: "🏮", category: "Humanity" },
  literature: { name: "Văn học (Literature)", icon: "📚", category: "Humanity" },
  chemistry: { name: "Hóa học (Chemistry)", icon: "🧪", category: "STEM" },
  agentic: { name: "Gọi hàm Agentic (Tool Use)", icon: "🤖", category: "Agentic" },
  medicine: { name: "Y học & Dược (Medicine)", icon: "🩺", category: "Life Sciences" },
  physics: { name: "Vật lý (Physics)", icon: "⚡", category: "STEM" },
  logics: { name: "Tư duy & Logic", icon: "🧩", category: "Reasoning" },
  mathematics: { name: "Toán học (Mathematics)", icon: "📐", category: "Reasoning" },
};

export const STRATUM_LABELS: Record<string, string> = {
  "short-direct": "Ngắn — trả lời trực tiếp",
  "mid-direct": "Trung bình — trả lời trực tiếp",
  "long-direct": "Dài — trả lời trực tiếp",
  "short-infer": "Ngắn — phải suy luận",
  "mid-infer": "Trung bình — phải suy luận",
  "long-infer": "Dài — phải suy luận",
  add_sub: "Cộng/trừ số học",
  comparison: "So sánh",
  count: "Đếm",
  selection: "Chọn đáp án",
  other: "Dạng khác",
  auction: "Đấu thầu",
};

/** What the dataset is + how its headline number is computed. Shown under
 *  every hero so all tabs share one vocabulary. `metric` names the single
 *  aggregate family the tab reports; `metricNote` says what it does NOT mean
 *  where the roadmap flags a confusion risk (accept-rate≠accuracy, valid≠correct). */
export interface DatasetMeta {
  about: string;
  shape: string;
  metric: string;
  metricNote: string;
}

export const DATASET_META: Record<string, DatasetMeta> = {
  "vmlu-mqa-all-gold": {
    about: "Trắc nghiệm kiến thức tiếng Việt 58 môn (STEM, xã hội, nhân văn, khác) — 1.047 câu dev+valid có gold local, dùng dò điểm trũng theo môn.",
    shape: "Mỗi câu 1 đáp án đúng trong A–E · chấm khớp chữ cái (case-insensitive)",
    metric: "Accuracy = số câu đúng / tổng số câu",
    metricNote: "Không phải điểm leaderboard (bộ test 9.833 câu bị withheld, chấm server-side).",
  },
  "vbench-public-test": {
    about: "Bảng public test đa miền (12 miền trắc nghiệm + 1 track gọi hàm agentic) — đo kiến thức tổng quát và khả năng gọi tool đúng schema.",
    shape: "MC: chọn 1 đáp án · Agentic: trả JSON gọi hàm đúng schema",
    metric: "Micro = đúng/tổng câu · Macro = trung bình điểm 13 miền",
    metricNote: "Điểm server-side (vbench.ai). Valid (đúng cú pháp) ≠ correct (đúng nội dung).",
  },
  "reading-400": {
    about: "Đọc hiểu 400 câu tiền đăng ký (200 Vi-SQuAD trích xuất + 200 Vi-DROP suy luận số) — đo đọc hiểu tiếng Việt có ngữ cảnh.",
    shape: "Trả lời tự do từ đoạn văn cho sẵn (open-book, 48 token)",
    metric: "EM = khớp tuyệt đối · char-F1 = tín chỉ từng phần theo ký tự",
    metricNote: "Không phải accept-rate (tỷ lệ duyệt viên bấm chấp nhận) — EM/F1 chấm trên gold đã hiệu đính.",
  },
  "legal-mc-146": {
    about: "Trắc nghiệm pháp luật Việt Nam 146 câu (VLSP 2025 LegalSLM) — đo mảng Luật đã lộ yếu trên VMLU (mục 3.1 roadmap).",
    shape: "Trắc nghiệm A–D qua MC runner frozen (4 token, closed-book)",
    metric: "Accuracy + baseline majority (đáp án phổ biến nhất)",
    metricNote: "So với baseline để thấy lift; không so ngang % VMLU (suite khác dạng).",
  },
  "legal-nli-150": {
    about: "Suy luận entailment pháp luật 150 câu nhị phân (điều luật có trả lời được câu hỏi không: Có/Không) — đo mảng Luật dạng NLI.",
    shape: "Nhị phân Có→A / Không→B qua MC runner frozen",
    metric: "Accuracy + baseline majority (≈50% vì 75/75 cân bằng)",
    metricNote: "By-gold A/B cho thấy lệch theo đáp án đúng.",
  },
  "bidlqa-val": {
    about: "Hỏi-đáp đấu thầu 482 câu (ViBidLQA split val) — đọc hiểu chuyên ngành pháp lý đấu thầu, gold nguyên văn trong file.",
    shape: "Trả lời tự do từ ngữ cảnh văn bản đấu thầu (open-book, 48 token)",
    metric: "EM + char-F1 trên file-gold",
    metricNote: "Gold chưa qua review 2 người — EM là cận dưới theo chữ, F1 bù diễn đạt lại.",
  },
  "bidlqa-test": {
    about: "Hỏi-đáp đấu thầu 603 câu (ViBidLQA split test) — cùng dạng val, đo khái quát hóa sang split unseen.",
    shape: "Trả lời tự do từ ngữ cảnh văn bản đấu thầu (open-book, 48 token)",
    metric: "EM + char-F1 trên file-gold",
    metricNote: "Đọc cùng val để thấy độ ổn định qua 2 split.",
  },
  "vm14k-public-12488": {
    about: "Trắc nghiệm Y khoa tiếng Việt 12.488 câu (VM14K public release, shuffled0) — đo mảng Y đã lộ yếu trên V-Bench medicine.",
    shape: "Trắc nghiệm A–E qua MC runner frozen (4 token, closed-book); lẫn 1.240 câu Đúng/Sai + câu 1 lựa chọn",
    metric: "Accuracy + baseline majority + bẻ theo độ khó / số lựa chọn",
    metricNote: "Chỉ đối chiếu hướng với V-Bench medicine (khác dạng câu); báo 4-lựa-chọn làm số chính.",
  },
};

/* ------------------------------ view types ------------------------------ */

export interface VmluSubjectVM {
  code: string;
  name: string;
  full_name: string;
  category: string;
  n: number;
  correct: number;
  accuracy: number;
}

export interface VmluQuestionVM {
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

export interface VmluBlock {
  overall: { n: number; correct: number; accuracy: number };
  categories: Array<{ name: string; n: number; correct: number; accuracy: number }>;
  subjects: VmluSubjectVM[];
  weakest_subjects: VmluSubjectVM[];
  strongest_subjects: VmluSubjectVM[];
  questions_sample: VmluQuestionVM[];
}

export interface VbenchDomainVM {
  domain: string;
  name: string;
  track: string;
  score: number;
  correct: number;
  total: number;
  category: string;
  icon: string;
}

export interface VbenchBlock {
  macro_score: number;
  micro_accuracy: number;
  total_items: number;
  total_correct: number;
  tracks: {
    multiple_choice: { total: number; correct: number; accuracy: number };
    agentic: { total: number; correct: number; accuracy: number };
  };
  domains: VbenchDomainVM[];
}

export interface ReadingStratumVM {
  stratum: string;
  label: string;
  n: number;
  em_count: number;
  em: number;
  char_f1: number;
}

export interface ReadingSourceVM {
  label: string;
  n: number;
  em_count: number;
  em: number;
  char_f1: number;
  strata: ReadingStratumVM[];
}

export interface ReadingBlock {
  overall: { n: number; em_count: number; em: number; char_f1: number; label: string };
  sources: ReadingSourceVM[];
}

export interface LegalBlock {
  overall: { n: number; correct: number; accuracy: number; valid: number; blanks: number; wrong_parsed: number };
  baseline: { majority_letter: string; majority_n: number; majority_accuracy: number; label: string };
  by_gold: Array<{ gold: string; n: number; correct: number; accuracy: number }>;
}

/** VM14K = LegalBlock + breakdowns joined from the pre-registered manifest
 *  (difficulty_level, n_choices). Correctness stays live from mc_items;
 *  labels come from data/vm14k_manifest.json (tracked, byte-frozen). */
export interface Vm14kBlock extends LegalBlock {
  by_difficulty: Array<{ difficulty: string; n: number; correct: number; accuracy: number }>;
  by_n_choices: Array<{ n_choices: number; n: number; correct: number; accuracy: number }>;
  by_category: Array<{ category: string; n: number; correct: number; accuracy: number }>;
}

export interface BenchmarkView {
  models: Array<{ id: string; display_name: string; params?: string; quantization?: string; endpoint?: string }>;
  activeModel: { id: string; display_name: string; params?: string; quantization?: string; endpoint?: string };
  modelDatasets: DatasetDoc[];
  runMeta: Record<string, { card_id: string; measurement_card_hash: string; condition: string; dataset_n: number }>;
  datasetMeta: Record<string, DatasetMeta>;
  vmlu: VmluBlock | null;
  vbench: VbenchBlock | null;
  reading: ReadingBlock | null;
  legal: LegalBlock | null;
  legal_nli: LegalBlock | null;
  bidlqa_val: ReadingBlock | null;
  bidlqa_test: ReadingBlock | null;
  vm14k: Vm14kBlock | null;
}

/* ------------------------------ small helpers ------------------------------ */

function num(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return 0;
}

function rowsOf(summary: Record<string, unknown> | null, key: string): Array<Record<string, unknown>> {
  if (!summary) return [];
  const v = summary[key];
  return Array.isArray(v) ? (v as Array<Record<string, unknown>>) : [];
}

function overallOf(summary: Record<string, unknown> | null): { n: number; correct: number; accuracy: number } {
  const row = rowsOf(summary, "accuracy_rows").find((r) => String(r.level) === "overall");
  if (!row) return { n: 0, correct: 0, accuracy: 0 };
  return { n: num(row.n), correct: num(row.correct), accuracy: num(row.accuracy) };
}

function conditionOf(run: RunDoc | undefined): string {
  if (!run) return "";
  const c = (run.config ?? {}) as Record<string, unknown>;
  const bits: string[] = [];
  if (run.prompt_condition) bits.push(String(run.prompt_condition));
  if (c.temperature !== undefined) bits.push(`temp ${c.temperature}`);
  if (c.seed !== undefined) bits.push(`seed ${c.seed}`);
  if (c.max_tokens !== undefined) bits.push(`${c.max_tokens} token`);
  if (run.card_id) bits.push(`card ${run.card_id}`);
  return bits.join(" · ");
}

function subjectCodeOf(itemId: string): string {
  const m = /^(\d{1,2})-/.exec(itemId);
  return m ? m[1].padStart(2, "0") : "??";
}

function strataFor(source: string, docs: Array<Record<string, unknown>>): ReadingStratumVM[] {
  const byStratum: Record<string, { n: number; em: number; f1: number }> = {};
  for (const d of docs) {
    if (source !== "ALL" && String(d.dataset ?? "") !== source) continue;
    const key = String(d.stratum ?? "other") || "other";
    const slot = byStratum[key] ?? { n: 0, em: 0, f1: 0 };
    slot.n += 1;
    slot.em += Number(d.em) === 1 ? 1 : 0;
    slot.f1 += Number(d.f1) || 0;
    byStratum[key] = slot;
  }
  return Object.entries(byStratum)
    .map(([stratum, s]) => ({
      stratum,
      label: STRATUM_LABELS[stratum] ?? stratum,
      n: s.n,
      em_count: s.em,
      em: s.n > 0 ? (s.em / s.n) * 100 : 0,
      char_f1: s.n > 0 ? (s.f1 / s.n) * 100 : 0,
    }))
    .sort((a, b) => a.em - b.em);
}

async function buildVmlu(run: RunDoc, summary: Record<string, unknown> | null): Promise<VmluBlock> {
  const overall = overallOf(summary);
  const rows = rowsOf(summary, "accuracy_rows");
  const categories = rows
    .filter((r) => String(r.level) === "category")
    .map((r) => ({
      name: String(r.name),
      n: num(r.n),
      correct: num(r.correct),
      accuracy: num(r.accuracy),
    }));
  const subjects: VmluSubjectVM[] = rows
    .filter((r) => String(r.level) === "subject" && String(r.name) !== "unknown")
    .map((r) => {
      const full = String(r.name);
      const m = /^(\d{1,2})\s+(.*)$/.exec(full);
      const code = m ? m[1].padStart(2, "0") : full;
      const numCode = Number.parseInt(code, 10);
      const meta = SUBJECTS[numCode];
      return {
        code,
        name: m ? m[2] : full,
        full_name: full,
        category: meta?.category ?? "Other",
        n: num(r.n),
        correct: num(r.correct),
        accuracy: num(r.accuracy),
      };
    })
    .sort((a, b) => b.accuracy - a.accuracy);
  const rankedAsc = [...subjects].sort((a, b) => a.accuracy - b.accuracy);

  // Wrong-answer sample: first 50 correct=0 items, shaped like the blob's
  // questions_sample (id, subject_code, category, question, prompt, answer, gold).
  const page = await getItemsPage(run._id, { collection: "mc_items", correct: 0, skip: 0, limit: 50 });
  const questions_sample: VmluQuestionVM[] = page.docs.map((d) => {
    const id = String(d.item_id ?? "");
    const code = subjectCodeOf(id);
    const meta = SUBJECTS[Number.parseInt(code, 10)];
    return {
      id,
      subject_code: code,
      category: meta?.category ?? "Other",
      question: String(d.question ?? ""),
      prompt: String(d.prompt ?? ""),
      raw_response: String(d.raw_response ?? ""),
      answer: String(d.answer ?? ""),
      gold_answer: String(d.gold ?? ""),
      correct: false,
    };
  });

  return {
    overall,
    categories,
    subjects,
    weakest_subjects: rankedAsc.slice(0, 6),
    strongest_subjects: subjects.slice(0, 6),
    questions_sample,
  };
}

function buildVbench(summary: Record<string, unknown> | null): VbenchBlock {
  const servers = rowsOf(summary, "server_rows").map((r) => ({
    domain: String(r.domain),
    track: String(r.track),
    score: num(r.score),
    correct: Math.round(num(r.correct)),
    total: Math.round(num(r.total)),
  }));
  const total = servers.reduce((s, r) => s + r.total, 0);
  const correct = servers.reduce((s, r) => s + r.correct, 0);
  const macro = servers.length > 0 ? servers.reduce((s, r) => s + r.score, 0) / servers.length : 0;
  const mc = servers.filter((r) => r.track === "multiple-choice");
  const ag = servers.filter((r) => r.track === "function calling");
  const sum = (xs: typeof servers) => ({
    total: xs.reduce((s, r) => s + r.total, 0),
    correct: xs.reduce((s, r) => s + r.correct, 0),
  });
  const mcSum = sum(mc);
  const agSum = sum(ag);
  return {
    macro_score: macro,
    micro_accuracy: total > 0 ? (correct / total) * 100 : 0,
    total_items: total,
    total_correct: correct,
    tracks: {
      multiple_choice: {
        ...mcSum,
        accuracy: mcSum.total > 0 ? (mcSum.correct / mcSum.total) * 100 : 0,
      },
      agentic: { ...agSum, accuracy: agSum.total > 0 ? (agSum.correct / agSum.total) * 100 : 0 },
    },
    domains: servers.map((d) => ({
      ...d,
      name: DOMAIN_META[d.domain]?.name ?? d.domain,
      icon: DOMAIN_META[d.domain]?.icon ?? "📄",
      category: DOMAIN_META[d.domain]?.category ?? d.track,
    })),
  };
}


async function buildReading(
  summary: Record<string, unknown> | null,
  fetchItems: () => Promise<Array<Record<string, unknown>>>,
  sourceLabels: Record<string, string>,
): Promise<ReadingBlock> {
  const rows = rowsOf(summary, "reading_rows");
  const overallRow = rows.find((r) => String(r.dataset) === "ALL") ?? rows[0];
  const overall = overallRow
    ? {
        n: Math.round(num(overallRow.n)),
        em_count: Math.round(num(overallRow.em_count)),
        em: num(overallRow.em),
        char_f1: num(overallRow.char_f1),
        label: "Tổng",
      }
    : { n: 0, em_count: 0, em: 0, char_f1: 0, label: "Tổng" };
  const splitNames = rows.map((r) => String(r.dataset)).filter((d) => d !== "ALL");
  // Strata need items (summaries carry no stratum rows): one paged scan per
  // source would be N round trips, so fetch up to 1000 docs once and split
  // locally. Bounded: reading/bidlqa runs are ≤603 docs.
  const docs = splitNames.length > 0 || overall.n > 0 ? await fetchItems() : [];
  const sources: ReadingSourceVM[] = rows
    .filter((r) => String(r.dataset) !== "ALL")
    .map((r) => {
      const key = String(r.dataset);
      return {
        label: sourceLabels[key] ?? key,
        n: Math.round(num(r.n)),
        em_count: Math.round(num(r.em_count)),
        em: num(r.em),
        char_f1: num(r.char_f1),
        strata: strataFor(key, docs),
      };
    });
  return { overall, sources };
}

async function buildLegal(run: RunDoc): Promise<LegalBlock> {
  // Baseline + by-gold counted from items (majority letter is data, not config).
  const counts: Record<string, { n: number; correct: number }> = {};
  let blanks = 0;
  let skip = 0;
  for (;;) {
    const page = await getItemsPage(run._id, { collection: "mc_items", skip, limit: 200 });
    if (page.docs.length === 0) break;
    for (const d of page.docs) {
      const gold = String(d.gold ?? "");
      const slot = counts[gold] ?? { n: 0, correct: 0 };
      slot.n += 1;
      if (Number(d.correct) === 1) slot.correct += 1;
      counts[gold] = slot;
      if (!d.raw_response || !d.answer) blanks += 1;
    }
    skip += page.docs.length;
    if (skip >= page.total) break;
  }
  const entries = Object.entries(counts).filter(([g]) => g !== "").sort((a, b) => b[1].n - a[1].n);
  const n = entries.reduce((s, [, v]) => s + v.n, 0);
  const correct = entries.reduce((s, [, v]) => s + v.correct, 0);
  const [majLetter, maj] = entries[0] ?? ["—", { n: 0, correct: 0 }];
  const round2 = (x: number) => Math.round(x * 100) / 100;
  return {
    overall: {
      n,
      correct,
      accuracy: n > 0 ? round2((correct / n) * 100) : 0,
      valid: n - blanks,
      blanks,
      wrong_parsed: n - correct - blanks,
    },
    baseline: {
      majority_letter: majLetter,
      majority_n: maj.n,
      majority_accuracy: n > 0 ? round2((maj.n / n) * 100) : 0,
      label: `Luôn đáp ${majLetter}`,
    },
    by_gold: entries.map(([gold, v]) => ({
      gold,
      n: v.n,
      correct: v.correct,
      accuracy: v.n > 0 ? round2((v.correct / v.n) * 100) : 0,
    })),
  };
}

/** Pre-registered VM14K manifest labels (id → category / difficulty / n_choices).
 *  Server-only: benchmark-view.ts never ships to the browser (client modules
 *  import it with `import type` only). Cached per server process; degrades to
 *  an empty map when the file is absent so the tab still shows live overall. */
let vm14kManifestCache: Record<string, { difficulty: string; n_choices: number; category: string }> | null = null;

async function vm14kManifestLabels(): Promise<Record<string, { difficulty: string; n_choices: number; category: string }>> {
  if (vm14kManifestCache) return vm14kManifestCache;
  try {
    const { readFile } = await import("node:fs/promises");
    const { join } = await import("node:path");
    for (const p of [join(process.cwd(), "data/vm14k_manifest.json"), join(process.cwd(), "../data/vm14k_manifest.json")]) {
      try {
        const raw = await readFile(p, "utf-8");
        const man = JSON.parse(raw) as { items?: Array<{ id?: unknown; difficulty_level?: unknown; n_choices?: unknown; category?: unknown }> };
        const map: Record<string, { difficulty: string; n_choices: number; category: string }> = {};
        for (const it of man.items ?? []) {
          if (typeof it.id !== "string" || !it.id) continue;
          map[it.id] = {
            difficulty: typeof it.difficulty_level === "string" && it.difficulty_level ? it.difficulty_level : "unknown",
            n_choices: typeof it.n_choices === "number" ? it.n_choices : 0,
            category: typeof it.category === "string" && it.category ? it.category : "unknown",
          };
        }
        vm14kManifestCache = map;
        return map;
      } catch {
        // try the next candidate path
      }
    }
  } catch {
    // fs unavailable — degrade to overall-only below
  }
  vm14kManifestCache = {};
  return vm14kManifestCache;
}

const VM14K_DIFFICULTY_ORDER = ["Easy", "Medium", "Challenging", "Hard"];

/** Category display order — mirror of CATEGORY_ORDER in code_benchmark/vm14k_taxonomy.py. */
const VM14K_CATEGORY_ORDER = [
  "Nội khoa",
  "Sản – Nhi",
  "Ngoại – Gây mê – Hồi sức – Cấp cứu",
  "Dược – Độc – Điều trị",
  "Chuyên khoa khác",
  "Cận lâm sàng & Chẩn đoán",
  "Khoa học cơ sở",
  "Ung bướu & Chăm sóc giảm nhẹ",
  "Y tế công cộng & Dự phòng",
  "unknown",
];

async function buildVm14k(run: RunDoc): Promise<Vm14kBlock> {
  // Same paging loop as buildLegal (baseline + by-gold live from items),
  // plus a correct-by-id map for the manifest join. One scan, no re-reads.
  const counts: Record<string, { n: number; correct: number }> = {};
  const correctById: Record<string, number> = {};
  let blanks = 0;
  let skip = 0;
  for (;;) {
    const page = await getItemsPage(run._id, { collection: "mc_items", skip, limit: 200 });
    if (page.docs.length === 0) break;
    for (const d of page.docs) {
      const gold = String(d.gold ?? "");
      const slot = counts[gold] ?? { n: 0, correct: 0 };
      slot.n += 1;
      const ok = Number(d.correct) === 1 ? 1 : 0;
      if (ok === 1) slot.correct += 1;
      counts[gold] = slot;
      correctById[String(d.item_id ?? "")] = ok;
      if (!d.raw_response || !d.answer) blanks += 1;
    }
    skip += page.docs.length;
    if (skip >= page.total) break;
  }
  const entries = Object.entries(counts).filter(([g]) => g !== "").sort((a, b) => b[1].n - a[1].n);
  const n = entries.reduce((s, [, v]) => s + v.n, 0);
  const correct = entries.reduce((s, [, v]) => s + v.correct, 0);
  const [majLetter, maj] = entries[0] ?? ["—", { n: 0, correct: 0 }];
  const round2 = (x: number) => Math.round(x * 100) / 100;

  const labels = await vm14kManifestLabels();
  const byDiff: Record<string, { n: number; correct: number }> = {};
  const byNc: Record<number, { n: number; correct: number }> = {};
  const byCat: Record<string, { n: number; correct: number }> = {};
  for (const [id, lab] of Object.entries(labels)) {
    const ok = correctById[id];
    if (ok === undefined) continue; // manifest id with no run item — skip, never guess
    const ds = byDiff[lab.difficulty] ?? { n: 0, correct: 0 };
    ds.n += 1;
    ds.correct += ok;
    byDiff[lab.difficulty] = ds;
    const ns = byNc[lab.n_choices] ?? { n: 0, correct: 0 };
    ns.n += 1;
    ns.correct += ok;
    byNc[lab.n_choices] = ns;
    const cs = byCat[lab.category] ?? { n: 0, correct: 0 };
    cs.n += 1;
    cs.correct += ok;
    byCat[lab.category] = cs;
  }
  const diffRows = [
    ...VM14K_DIFFICULTY_ORDER.filter((d) => byDiff[d]).map((d) => ({ difficulty: d, ...byDiff[d] })),
    ...Object.keys(byDiff).filter((d) => !VM14K_DIFFICULTY_ORDER.includes(d)).sort().map((d) => ({ difficulty: d, ...byDiff[d] })),
  ].map((r) => ({ ...r, accuracy: r.n > 0 ? round2((r.correct / r.n) * 100) : 0 }));
  const ncRows = Object.entries(byNc)
    .map(([nc, v]) => ({ n_choices: Number(nc), ...v }))
    .sort((a, b) => a.n_choices - b.n_choices)
    .map((r) => ({ ...r, accuracy: r.n > 0 ? round2((r.correct / r.n) * 100) : 0 }));
  const catRows = [
    ...VM14K_CATEGORY_ORDER.filter((c) => byCat[c]).map((c) => ({ category: c, ...byCat[c] })),
    ...Object.keys(byCat).filter((c) => !VM14K_CATEGORY_ORDER.includes(c)).sort().map((c) => ({ category: c, ...byCat[c] })),
  ].map((r) => ({ ...r, accuracy: r.n > 0 ? round2((r.correct / r.n) * 100) : 0 }));

  return {
    overall: {
      n,
      correct,
      accuracy: n > 0 ? round2((correct / n) * 100) : 0,
      valid: n - blanks,
      blanks,
      wrong_parsed: n - correct - blanks,
    },
    baseline: {
      majority_letter: majLetter,
      majority_n: maj.n,
      majority_accuracy: n > 0 ? round2((maj.n / n) * 100) : 0,
      label: `Luôn đáp ${majLetter}`,
    },
    by_gold: entries.map(([gold, v]) => ({
      gold,
      n: v.n,
      correct: v.correct,
      accuracy: v.n > 0 ? round2((v.correct / v.n) * 100) : 0,
    })),
    by_difficulty: diffRows,
    by_n_choices: ncRows,
    by_category: catRows,
  };
}

export async function getBenchmarkView(modelId?: string): Promise<BenchmarkView> {
  const [models, datasets, runs] = await Promise.all([getModels(), getDatasets(), getRuns()]);
  if (models.length === 0) throw new Error("no models in registry — run seed_registries first");
  const picked: ModelDoc =
    (modelId ? models.find((m) => m._id === modelId) : undefined) ??
    models.find((m) => m._id === "qwen3-5-9b-28k") ??
    models[0];
  const runByDataset: Record<string, RunDoc> = {};
  for (const r of runs) if (r.model_id === picked._id) runByDataset[r.dataset_id] = r;
  const modelDatasets = datasets.filter((d) => runByDataset[d._id]);

  const summaries: Record<string, Record<string, unknown> | null> = {};
  await Promise.all(
    Object.values(runByDataset).map(async (r) => {
      summaries[r.dataset_id] = await getSummary(r._id);
    }),
  );

  const runMeta: BenchmarkView["runMeta"] = {};
  for (const ds of Object.keys(runByDataset)) {
    const run = runByDataset[ds];
    runMeta[ds] = {
      card_id: run.card_id,
      measurement_card_hash: run.measurement_card_hash,
      condition: conditionOf(run),
      dataset_n: run.n,
    };
  }

  const get = (ds: string) => runByDataset[ds];
  const sum = (ds: string) => summaries[ds] ?? null;

  const vmluRun = get("vmlu-mqa-all-gold");
  const vbenchDs = "vbench-public-test";
  const readingRun = get("reading-400");
  const legalRun = get("legal-mc-146");
  const nliRun = get("legal-nli-150");
  const bidValRun = get("bidlqa-val");
  const bidTestRun = get("bidlqa-test");
  const vm14kRun = get("vm14k-public-12488");

  const [vmlu, reading, legal, legal_nli, bidlqa_val, bidlqa_test, vm14k] = await Promise.all([
    vmluRun ? buildVmlu(vmluRun, sum("vmlu-mqa-all-gold")) : Promise.resolve(null),
    readingRun
      ? buildReading(
          sum("reading-400"),
          async () => (await getItemsPage(readingRun._id, { collection: "reading_items", limit: 200, skip: 0 })).docs.concat(
            (await getItemsPage(readingRun._id, { collection: "reading_items", limit: 200, skip: 200 })).docs,
          ),
          { squad: "Vi-SQuAD", drop: "Vi-DROP" },
        )
      : Promise.resolve(null),
    legalRun ? buildLegal(legalRun) : Promise.resolve(null),
    nliRun ? buildLegal(nliRun) : Promise.resolve(null),
    bidValRun
      ? buildReading(sum("bidlqa-val"), async () => {
          const pages: Array<Record<string, unknown>> = [];
          let skip = 0;
          for (;;) {
            const p = await getItemsPage(bidValRun._id, { collection: "reading_items", skip, limit: 200 });
            pages.push(...p.docs);
            skip += p.docs.length;
            if (skip >= p.total || p.docs.length === 0) break;
          }
          return pages;
        }, { bidlqa: "ViBidLQA-val" })
      : Promise.resolve(null),
    bidTestRun
      ? buildReading(sum("bidlqa-test"), async () => {
          const pages: Array<Record<string, unknown>> = [];
          let skip = 0;
          for (;;) {
            const p = await getItemsPage(bidTestRun._id, { collection: "reading_items", skip, limit: 200 });
            pages.push(...p.docs);
            skip += p.docs.length;
            if (skip >= p.total || p.docs.length === 0) break;
          }
          return pages;
        }, { bidlqa: "ViBidLQA-test" })
      : Promise.resolve(null),
    vm14kRun ? buildVm14k(vm14kRun) : Promise.resolve(null),
  ]);
  return {
    models: models.map((m) => ({
      id: m._id,
      display_name: m.display_name ?? m._id,
      params: m.params,
      quantization: m.quantization,
      endpoint: m.endpoint,
    })),
    activeModel: {
      id: picked._id,
      display_name: picked.display_name ?? picked._id,
      params: picked.params,
      quantization: picked.quantization,
      endpoint: picked.endpoint,
    },
    modelDatasets,
    runMeta,
    datasetMeta: Object.fromEntries(
      modelDatasets
        .filter((d) => DATASET_META[d._id] !== undefined)
        .map((d) => [d._id, DATASET_META[d._id]]),
    ) as Record<string, DatasetMeta>,
    vmlu,
    vbench: get(vbenchDs) ? buildVbench(sum(vbenchDs)) : null,
    reading,
    legal,
    legal_nli,
    bidlqa_val,
    bidlqa_test,
    vm14k,
  };
}

export type { DatasetDoc, ModelDoc, RunDoc };
