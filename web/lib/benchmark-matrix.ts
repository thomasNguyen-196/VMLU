/** Curated model × dataset comparisons. Unknown controls never create a cohort. */
import type { BenchmarkReports, BenchmarkRunSummary, EvaluationReport, ReportCondition, ReportScore } from "./benchmark-reports.ts";
import { fmtNum, fmtPct } from "./format.ts";

export type MatrixMetric = "accuracy" | "em" | "token_f1" | "char_f1";
export interface MatrixModel { id: string; name: string; provider: string }
export interface MatrixCell { score: ReportScore; condition: ReportCondition; reportId: string; rankEligible?: boolean }
export interface MatrixColumn {
  id: string;
  label: string;
  n: number | null;
  sourceLabel: string;
  gold: string;
  cells: Record<string, MatrixCell>;
}
export interface MetricMatrix { metric: MatrixMetric; title: string; columns: MatrixColumn[]; comment: string; ciComment: string }
export interface MatrixGroup {
  id: string;
  kind: "omp-no-tools" | "direct";
  label: string;
  detail: string;
  models: MatrixModel[];
  matrices: MetricMatrix[];
  conditions: ReportCondition[];
  notes: string[];
}
export interface BenchmarkMatrixView { groups: MatrixGroup[]; generatedAt: string; directReason: string; runSummaries: BenchmarkRunSummary[] }

const MODEL_ORDER = ["muse-spark-1-3-contributor", "muse12-vmlu-mc74-mc79", "mimo-v2-6-flash", "mimo-v2-5", "qwen3-5-9b-65k"];
const METRICS: MatrixMetric[] = ["accuracy", "em", "token_f1", "char_f1"];
const LABELS: Record<MatrixMetric, string> = { accuracy: "Accuracy", em: "EM", token_f1: "F1 · token", char_f1: "F1 · character" };
const DATASETS: Record<string, { id: string; label: string; order: number }> = {
  "vi-multimodel-v1-vmlu-valid": { id: "vmlu-valid", label: "VMLU Valid", order: 1 },
  "vi-multimodel-v2-vmlu-valid": { id: "vmlu-valid", label: "VMLU Valid", order: 1 },
  "vi-multimodel-v2-vmlu-test": { id: "vmlu-test", label: "VMLU Test", order: 0 },
  "vi-multimodel-v2-vmlu-dev": { id: "vmlu-dev", label: "VMLU Dev", order: 2 },
  "vi-multimodel-v1-legal-mc-146": { id: "legal-mc", label: "Legal MC", order: 3 },
  "vi-multimodel-v1-legal-nli-150": { id: "legal-nli", label: "Legal NLI", order: 4 },
  "vi-multimodel-v1-vi-squad-200": { id: "vi-squad", label: "Vi-SQuAD", order: 5 },
  "vi-multimodel-v1-vi-drop-200": { id: "vi-drop", label: "Vi-DROP", order: 6 },
  "vi-multimodel-v1-bidlqa-test": { id: "bidlqa-test", label: "ViBidLQA Test", order: 7 },
};

type Candidate = MatrixCell & { model: MatrixModel; canonicalId: string; label: string; order: number; metric: MatrixMetric; cohort: string; priority: number };
/** Visual maximum covers every displayed model; matching controls is a separate annotation. */
export function columnMaximum(column: MatrixColumn): number | null {
  const scores = Object.values(column.cells).map((cell) => cell.score.score);
  return scores.length ? Math.max(...scores) : null;
}
function displayMetric(score: ReportScore): MatrixMetric | null {
  if (score.metric === "accuracy" || score.metric === "server_accuracy") return "accuracy";
  return METRICS.includes(score.metric as MatrixMetric) ? score.metric as MatrixMetric : null;
}
function model(condition: ReportCondition): MatrixModel {
  return { id: condition.controls!.profile_id, name: condition.model, provider: condition.fields.provider.split(" · ")[0] };
}

export function eligibleOmp(condition: ReportCondition): boolean {
  const c = condition.controls;
  return Boolean(c && c.transport === "omp" && c.tools === "none" && c.temperature_effective === 1 && c.thinking === "auto" && ["omp/18.0.0", "18.0.0"].includes(c.harness_version ?? "") && c.workers === 4 && c.system_prompt === "Answer the user's question." && c.seed_sent === false && condition.comparison_group);
}

export function directSignature(condition: ReportCondition, metric: MatrixMetric): string | null {
  const c = condition.controls;
  if (!c || c.transport !== "direct" || c.tools !== "none" || c.thinking === null || c.seed_sent === null || c.workers === null || c.system_prompt === null || c.prompt_version === null) return null;
  const temperature = c.temperature_effective ?? c.temperature_requested;
  const cap = c.output_caps[metric === "accuracy" ? "multiple_choice" : "reading"];
  if (temperature === null || cap === undefined || (c.seed_sent && c.seed_requested === null)) return null;
  return JSON.stringify([temperature, c.thinking, c.seed_sent ? c.seed_requested : "omitted", cap, c.workers, c.system_prompt, c.prompt_version]);
}

function ranked(column: MatrixColumn): Array<MatrixCell & { name: string }> {
  return Object.values(column.cells).filter((cell) => cell.rankEligible !== false).map((cell) => ({ ...cell, name: cell.condition.model })).sort((a, b) => b.score.score - a.score.score);
}
function overlaps(a: ReportScore, b: ReportScore) {
  return a.ci_low !== null && a.ci_high !== null && b.ci_low !== null && b.ci_high !== null && a.ci_low <= b.ci_high && b.ci_low <= a.ci_high;
}

export function matrixComments(metric: MatrixMetric, columns: MatrixColumn[]): { comment: string; ciComment: string } {
  const complete = columns.filter((column) => ranked(column).length >= 2);
  const gaps = complete.map((column) => ({ column, rows: ranked(column) })).sort((a, b) => (b.rows[0].score.score - b.rows[1].score.score) - (a.rows[0].score.score - a.rows[1].score.score));
  if (!gaps.length) return { comment: "Chưa đủ model có dữ liệu so sánh trong cùng điều kiện.", ciComment: "Chưa có khoảng tin cậy đối chiếu." };
  const prominent = metric === "accuracy" ? gaps.find((entry) => entry.column.id === "vmlu-test") ?? gaps[0] : gaps[0];
  const [best, second] = prominent.rows;
  const gap = best.score.score - second.score.score;
  let comment: string;
  if (metric === "accuracy") {
    comment = `Nhìn chung, ${best.name} tạo lợi thế rõ nhất ở ${prominent.column.label}: ${fmtPct(best.score.score)} so với ${fmtPct(second.score.score)} của ${second.name}, chênh ${fmtNum(gap)} điểm phần trăm.`;
    const exception = gaps.find((entry) => entry.rows[0].name !== best.name);
    if (exception) {
      const formerLeader = exception.rows.find((entry) => entry.name === best.name);
      comment += ` Tuy nhiên, thứ hạng thay đổi ở ${exception.column.label}, nơi ${exception.rows[0].name} đạt ${fmtPct(exception.rows[0].score.score)}${formerLeader ? `, cao hơn ${fmtPct(formerLeader.score.score)} của ${best.name}` : " và đứng đầu nhóm đã chạy"}.`;
    }
    else comment += " Ưu thế này mô tả kết quả trắc nghiệm trong cấu hình đang chọn, gồm cả hiểu câu hỏi, kiến thức và suy luận.";
  } else if (metric === "em") {
    const sameLeader = complete.every((column) => ranked(column)[0].name === best.name);
    comment = `${best.name} ${sameLeader ? "dẫn đầu trên toàn bộ các tập đọc đã chạy" : `nổi bật nhất ở ${prominent.column.label}`}, với khoảng cách lớn nhất tại ${prominent.column.label}: ${fmtPct(best.score.score)} so với ${fmtPct(second.score.score)} của ${second.name}. EM cho thấy mức khớp nguyên văn với đáp án tham chiếu; cách diễn đạt khác vẫn có thể bị chấm không khớp.`;
  } else {
    const close = gaps[gaps.length - 1];
    comment = `${best.name} giữ lợi thế ở ${prominent.column.label}, nhưng khoảng cách thu hẹp rõ tại ${close.column.label}: ${close.rows[1].name} đạt ${fmtPct(close.rows[1].score.score)}, gần mức ${fmtPct(close.rows[0].score.score)} của ${close.rows[0].name}. F1 phản ánh mức chồng lấp từ vựng, chưa xác nhận câu trả lời đúng về ngữ nghĩa.`;
  }
  const measured = gaps.filter((entry) => entry.rows[0].score.ci_low !== null && entry.rows[1].score.ci_low !== null);
  const overlapping = [...measured].reverse().find((entry) => overlaps(entry.rows[0].score, entry.rows[1].score));
  const ciComment = overlapping
    ? `Ở ${overlapping.column.label}, CI95 của ${overlapping.rows[0].name} và ${overlapping.rows[1].name} chồng lấp; các điểm gần nhau cần được đọc cùng mức bất định. Khoảng tin cậy của từng model chưa thay cho kiểm định chênh lệch ghép đôi.`
    : measured.length
      ? `Các khoảng tin cậy ở ${measured[0].column.label} phản ánh sự tách biệt của các vùng ước lượng quanh điểm quan sát. Đây là CI của từng model, chưa phải kiểm định chênh lệch ghép đôi.`
      : "Nguồn kết quả chưa công bố CI95 cho các điểm này, nên các ô được giữ trống.";
  return { comment, ciComment: ciComment + (metric === "accuracy" && columns.some((column) => column.gold === "withheld") ? " VMLU Test chỉ có server grade; chưa có CI95 từ server." : "") };
}

function createGroup(id: string, kind: MatrixGroup["kind"], candidates: Candidate[], allowSingleton = false): MatrixGroup | null {
  const cohorts = new Map<string, Candidate[]>();
  for (const candidate of candidates) {
    const key = JSON.stringify([candidate.metric, candidate.canonicalId, candidate.cohort, candidate.score.n]);
    cohorts.set(key, [...(cohorts.get(key) ?? []), candidate]);
  }
  const selected = new Map<string, Candidate[]>();
  for (const rows of cohorts.values()) {
    const modelCount = new Set(rows.map((entry) => entry.model.id)).size;
    if ((!allowSingleton && modelCount < 2) || modelCount !== rows.length) continue;
    const key = `${rows[0].metric}:${rows[0].canonicalId}`;
    const previous = selected.get(key);
    if (!previous || rows[0].priority > previous[0].priority) selected.set(key, rows);
  }
  if (!selected.size) return null;
  const used = [...selected.values()].flat();
  const byId = new Map(used.map((candidate) => [candidate.model.id, candidate.model]));
  const models = [...byId.values()].sort((a, b) => {
    const ai = MODEL_ORDER.indexOf(a.id); const bi = MODEL_ORDER.indexOf(b.id);
    return (ai === -1 ? 100 : ai) - (bi === -1 ? 100 : bi) || a.name.localeCompare(b.name);
  });
  const matrices = METRICS.flatMap((metric) => {
    const chosen = [...selected.values()].filter((entries) => entries[0].metric === metric).sort((a, b) => a[0].order - b[0].order);
    if (!chosen.length) return [];
    const columns = chosen.map((entries): MatrixColumn => {
      const first = entries[0];
      return { id: first.canonicalId, label: first.label, n: first.score.n, sourceLabel: first.reportId === "vmlu-v2" ? "VMLU V2" : first.reportId === "main-v1" ? "Main V1" : "API trực tiếp", gold: first.score.gold,
        cells: Object.fromEntries(entries.map((entry) => [entry.model.id, { score: entry.score, condition: entry.condition, reportId: entry.reportId }])) };
    });
    return [{ metric, title: LABELS[metric], columns, ...matrixComments(metric, columns) }];
  });
  const conditions = [...new Map(used.map((entry) => [entry.condition.id, entry.condition])).values()];
  const controls = conditions[0].controls!;
  const detail = kind === "omp-no-tools" ? "Temperature 1,0 · thinking auto · seed không gửi" : `Temperature ${controls.temperature_effective ?? controls.temperature_requested} · seed ${controls.seed_sent ? controls.seed_requested : "không gửi"} · ${controls.workers} workers`;
  const notes = kind === "omp-no-tools" ? [
    "VMLU dùng các run V2 MC-62–64 và MC-70; các bài đọc và Legal dùng MC-53–55 cùng Qwen MC-72. Mỗi cột lấy cùng nhóm cấu hình và cùng mẫu; VMLU Valid ưu tiên lượt V2 mới hơn.",
    "Qwen MC-72 bổ sung đủ 1.299 câu: Legal MC/NLI, Vi-SQuAD, Vi-DROP và ViBidLQA Test; prompt hashes khớp từng run Go. Qwen MC-56 temp 0/thinking off/seed 42 được giữ riêng và không vào bảng này.",
    "OMP 18.0.0, JSON mode; system prompt tối giản; tools tắt; một process/item, không session history; 4 workers. Auto là chính sách của provider, không ghim mức low/medium/high.",
    "Output cap do benchmark đặt: 4.096 token cho MC, 2.048 cho reading; có thể gồm reasoning. Truncation đếm phản hồi kết thúc do length.",
    "EM và token-F1 là phép đo khớp văn bản. Gold reading-400 có đáp án kế thừa từ output đã được review; ViBidLQA dùng file-gold upstream. Chưa có semantic/human score cho bảng này.",
    "Accuracy VMLU Test là server grade do người dùng cung cấp; chưa có correct count và CI95 để tự suy ra từ phần trăm đã làm tròn.",
  ] : ["Chỉ ghép model khi temperature, thinking, seed, prompt, workers và output budget của cùng dataset đã được xác minh tương đương.", "F1 token và character có bảng riêng; không trộn hai phép đo."];
  return { id, kind, label: kind === "omp-no-tools" ? "OMP · không tools" : "API trực tiếp", detail, models, matrices, conditions, notes };
}

function attachMuse12Run(group: MatrixGroup, summary: BenchmarkRunSummary | undefined, mainReport?: EvaluationReport): MatrixGroup {
  if (!summary || group.kind !== "omp-no-tools") return group;
  const model: MatrixModel = { id: summary.id, name: summary.model, provider: "9ROUTER · CMC (Test: CMC + OCG)" };
  const condition: ReportCondition = {
    id: summary.id,
    model: summary.model,
    card: "MC-74 + MC-79",
    comparison_group: null,
    fields: {
      date: "MC-74 + MC-79; server grade received 2026-10-12",
      harness: "OMP · omp/18.0.0",
      provider: "9ROUTER · CMC + OCG, route varies by item",
      temperature: "requested 1.0; metadata 1.0; upstream effective value not exposed",
      thinking: "auto",
      seed: "không gửi (profile seed 42 không được gửi tới model)",
      tools: "none",
      prompt: "VMLU V2 frozen prompts; system: Answer the user's question.",
      context: "VMLU question + choices; gold không gửi cho model",
      session: "một process riêng/item; không persisted session; stable request session ID",
      output_cap: "4.096 token/item; cap gồm cả reasoning nếu provider tính như vậy",
      workers: `${summary.total_workers} workers · ${summary.shards} phần × ${summary.workers_per_shard} workers/phần`,
      timeout: "300 giây/item",
      retry: "MC-74 còn thiếu 3.376 câu Test; MC-79 tiếp tục phần đó; 0 item thiếu trong file tổng hợp",
      gold: "Valid/Dev local gold; Test withheld, có server grade",
      identity: "MC-74 CMC (7.504 item) + MC-79 OCG (3.376 item); mixed-route Test",
    },
    sources: [
      { path: summary.source, label: "Mixed-route provenance" },
      { path: "docs/research/muse12-vmlu-test-server-grade-2026-10-12.json", label: "VMLU Test server grade" },
      { path: "measurement_card.md", label: "MC-74" },
      { path: "docs/measurement_cards/MC-79-muse12-ocg-vmlu-continuation.md", label: "MC-79" },
    ],
    manifest_sha256: null,
    measurement_card_hash: null,
  };
  const accuracy = group.matrices.find((matrix) => matrix.metric === "accuracy");
  if (!accuracy) return group;

  const columns = accuracy.columns.map((column) => {
    const dataset = summary.datasets.find((entry) => DATASETS[entry.dataset_id]?.id === column.id);
    if (!dataset) return column;
    const value = dataset.server_accuracy ?? dataset.accuracy;
    if (value === null) return column;
    const metric = dataset.server_accuracy !== null ? "server_accuracy" : "accuracy";
    const score: ReportScore = {
      condition_id: condition.id,
      dataset_id: dataset.dataset_id,
      dataset: dataset.dataset,
      level: "dataset",
      category: "",
      metric,
      score: value,
      n: dataset.total_items,
      correct: dataset.correct,
      ci_low: dataset.ci_low ?? null,
      ci_high: dataset.ci_high ?? null,
      gold: dataset.gold,
      truncated: null,
      source: dataset.server_accuracy !== null ? "docs/research/muse12-vmlu-test-server-grade-2026-10-12.json" : summary.source,
      delta: null,
      delta_ci_low: null,
      delta_ci_high: null,
    };
    return {
      ...column,
      cells: {
        ...column.cells,
        [model.id]: { score, condition, reportId: summary.id, rankEligible: false },
      },
    };
  });
  const mainConditions = new Map(mainReport?.conditions.map((entry) => [entry.id, entry]) ?? []);
  const matrices = group.matrices.map((matrix) => {
    const baseColumns = matrix.metric === "accuracy" ? columns : matrix.columns;
    const displayedColumns = baseColumns.map((column) => {
      const mainScore = mainReport?.benchmarks.find((score) => score.level === "dataset"
        && displayMetric(score) === matrix.metric && DATASETS[score.dataset_id]?.id === column.id);
      if (!mainScore) return column;
      const mainCondition = mainConditions.get(mainScore.condition_id)!;
      return { ...column, cells: { ...column.cells,
        [model.id]: { score: mainScore, condition: mainCondition, reportId: mainReport!.id, rankEligible: false },
      } };
    });
    const maxima = displayedColumns.map((column) => {
      const max = columnMaximum(column);
      if (max === null) return "";
      const winners = Object.values(column.cells).filter((cell) => cell.score.score === max).map((cell) => cell.condition.model);
      return `${column.label}: ${winners.join(" và ")} ${fmtPct(max)}${winners.length > 1 ? " (đồng hạng)" : ""}`;
    }).filter(Boolean);
    return { ...matrix, columns: displayedColumns,
      comment: `${maxima.join("; ")}. Đây là các điểm lớn nhất đang hiển thị; khác biệt route, workers và timeout được ghi trong condition, chưa phải kết luận ý nghĩa thống kê.`,
      ciComment: "CI95 lấy từ scorer của từng run: MC dùng Wilson, reading dùng bootstrap theo passage. VMLU Test chỉ có điểm server, chưa có CI95; không suy CI hoặc số câu đúng từ tỷ lệ đã làm tròn. CI của từng model chưa thay cho kiểm định chênh lệch ghép đôi.",
    };
  });
  const models = [...group.models, model].sort((a, b) => {
    const ai = MODEL_ORDER.indexOf(a.id); const bi = MODEL_ORDER.indexOf(b.id);
    return (ai === -1 ? 100 : ai) - (bi === -1 ? 100 : bi) || a.name.localeCompare(b.name);
  });
  return {
    ...group,
    models,
    matrices,
    conditions: [...group.conditions, condition, ...(mainReport?.conditions ?? [])],
    notes: [
      ...group.notes,
      "Muse Spark 1.2 MC-74/MC-79 được thêm vào bảng Accuracy để so sánh trực quan. Run này dùng 12 workers và VMLU Test trộn CMC/OCG; không thuộc cohort xếp hạng khớp 4-worker. Valid/Dev chỉ dùng CMC.",
      "Muse 1.2 Legal MC/NLI và các bài đọc lấy từ MC-73: CMC, 4 workers, timeout 300 giây/item. Tô đậm và nhận xét các điểm lớn nhất xét tất cả model đang hiển thị, kể cả khi khác worker/route; không tự suy ra ý nghĩa thống kê.",
    ],
  };
}

export function buildBenchmarkMatrix(data: BenchmarkReports): BenchmarkMatrixView {
  const omp: Candidate[] = []; const direct: Candidate[] = []; const museDirect: Candidate[] = [];
  for (const report of data.reports) {
    const conditions = new Map(report.conditions.map((entry) => [entry.id, entry]));
    for (const score of report.benchmarks) {
      if (score.level !== "dataset") continue;
      const metric = displayMetric(score); if (metric === null) continue;
      const condition = conditions.get(score.condition_id)!;
      if (!condition.controls || score.dataset_id === "vmlu_local_dev_valid") continue;
      const spec = DATASETS[score.dataset_id] ?? { id: score.dataset_id, label: score.dataset, order: 100 };
      const candidate = { score, condition, reportId: report.id, model: model(condition), canonicalId: spec.id, label: spec.label, order: spec.order, metric, cohort: "", priority: report.id === "vmlu-v2" ? 2 : 1 };
      if (["main-v1", "vmlu-v2"].includes(report.id) && eligibleOmp(condition)) {
        const c = condition.controls;
        const cap = c.output_caps[metric === "accuracy" ? "multiple_choice" : "reading"];
        if (cap !== undefined) omp.push({ ...candidate, cohort: JSON.stringify([condition.comparison_group, c.harness_version, c.tools, c.temperature_effective, c.thinking, c.seed_sent ? c.seed_requested : "omitted", cap, c.workers, c.system_prompt, c.prompt_version]) });
      }
      const sig = directSignature(condition, metric);
      if (["muse13-direct", "qwen-direct-mc83", "muse12-direct-mc84", "mimo26-direct-mc85"].includes(report.id) && condition.controls.transport === "direct") {
        // Display measured results with default effort; do not invent a matched cohort.
        museDirect.push({ ...candidate, cohort: "direct-default-display", rankEligible: false });
      } else if (report.id === "history-direct-qwen3-5-9b-65k" && condition.model === "Qwen3.5-9B-65K") {
        continue;
      } else if (sig !== null) direct.push({ ...candidate, cohort: sig });
    }
  }
  const groups: MatrixGroup[] = [];
  const active = createGroup("omp-no-tools", "omp-no-tools", omp);
  if (active) groups.push(attachMuse12Run(active, data.run_summaries.find((summary) => summary.id === "muse12-vmlu-mc74-mc79"), data.reports.find((report) => report.id === "muse12-main-mc73")));
  const muse = createGroup("direct-default", "direct", museDirect, true);
  if (muse) {
    muse.detail = "Temperature 1,0 · reasoning mặc định · 12 workers";
    muse.notes = [...new Set(data.reports.filter((report) => ["muse13-direct", "qwen-direct-mc83", "muse12-direct-mc84", "mimo26-direct-mc85"].includes(report.id)).flatMap((report) => report.notes))];
    for (const matrix of muse.matrices) {
      for (const column of matrix.columns) for (const cell of Object.values(column.cells)) cell.rankEligible = false;
      const testColumn = matrix.columns.find((column) => column.id === "vmlu-test");
      const testScores = testColumn ? muse.models.flatMap((model) => {
        const cell = testColumn.cells[model.id];
        return cell ? [`${model.name} đạt ${fmtPct(cell.score.score)}`] : [];
      }).join("; ") : "";
      matrix.comment = matrix.metric === "accuracy"
        ? `VMLU Test: ${testScores}. Điểm Test do server chấm; các tập còn lại dùng gold cục bộ. Budget của Valid và Legal/reading được ghi riêng trong điều kiện từng run.`
        : "Đối chiếu khớp đáp án của các model API Direct; EM và token-F1 được trình bày riêng. Xem budget theo dataset trong chi tiết điều kiện.";
    }
    groups.push(muse);
  }
  // Separate direct decoding configurations before looking for common datasets.
  const directGroups = new Map<string, Candidate[]>();
  for (const entry of direct) {
    const c = entry.condition.controls!;
    const key = JSON.stringify([c.temperature_effective ?? c.temperature_requested, c.thinking, c.seed_sent ? c.seed_requested : "omitted", c.workers, c.system_prompt]);
    directGroups.set(key, [...(directGroups.get(key) ?? []), entry]);
  }
  let index = 0;
  for (const entries of directGroups.values()) {
    const group = createGroup(`direct-${index++}`, "direct", entries);
    if (group) groups.push(group);
  }
  return { groups, generatedAt: data.generated_at, directReason: groups.some((group) => group.kind === "direct") ? "" : "Tạm bỏ qua: chưa có ít nhất hai model với cùng temperature, thinking và output budget được xác minh trên cùng dataset. Thinking của một số run cũ thiếu metadata; Legal MC dùng cap 4 và 512 token ở hai model non-thinking.", runSummaries: data.run_summaries };
}

export function selectMatrixGroup(view: BenchmarkMatrixView, requested?: string): MatrixGroup | null {
  const id = requested === "direct-muse13" ? "direct-default" : requested;
  return view.groups.find((group) => group.id === id) ?? view.groups[0] ?? null;
}
