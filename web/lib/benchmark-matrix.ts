/** Curated model × dataset comparisons. Unknown controls never create a cohort. */
import type { BenchmarkReports, ReportCondition, ReportScore } from "./benchmark-reports.ts";
import { fmtNum, fmtPct } from "./format.ts";

export type MatrixMetric = "accuracy" | "em" | "token_f1" | "char_f1";
export interface MatrixModel { id: string; name: string; provider: string }
export interface MatrixCell { score: ReportScore; condition: ReportCondition; reportId: string }
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
export interface BenchmarkMatrixView { groups: MatrixGroup[]; generatedAt: string; directReason: string }

const MODEL_ORDER = ["muse-spark-1-3-contributor", "mimo-v2-6-flash", "mimo-v2-5", "qwen3-5-9b-65k"];
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
  return Object.values(column.cells).map((cell) => ({ ...cell, name: cell.condition.model })).sort((a, b) => b.score.score - a.score.score);
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

function createGroup(id: string, kind: MatrixGroup["kind"], candidates: Candidate[]): MatrixGroup | null {
  const cohorts = new Map<string, Candidate[]>();
  for (const candidate of candidates) {
    const key = JSON.stringify([candidate.metric, candidate.canonicalId, candidate.cohort, candidate.score.n]);
    cohorts.set(key, [...(cohorts.get(key) ?? []), candidate]);
  }
  const selected = new Map<string, Candidate[]>();
  for (const rows of cohorts.values()) {
    const modelCount = new Set(rows.map((entry) => entry.model.id)).size;
    if (modelCount < 2 || modelCount !== rows.length) continue;
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
  const detail = kind === "omp-no-tools" ? "Temperature 1,0 · thinking auto · seed không gửi" : `Temperature ${controls.temperature_effective ?? controls.temperature_requested} · thinking ${controls.thinking}`;
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

export function buildBenchmarkMatrix(data: BenchmarkReports): BenchmarkMatrixView {
  const omp: Candidate[] = []; const direct: Candidate[] = [];
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
      if (sig !== null) direct.push({ ...candidate, cohort: sig });
    }
  }
  const groups: MatrixGroup[] = [];
  const active = createGroup("omp-no-tools", "omp-no-tools", omp);
  if (active) groups.push(active);
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
  return { groups, generatedAt: data.generated_at, directReason: groups.some((group) => group.kind === "direct") ? "" : "Tạm bỏ qua: chưa có ít nhất hai model với cùng temperature, thinking và output budget được xác minh trên cùng dataset. Thinking của một số run cũ thiếu metadata; Legal MC dùng cap 4 và 512 token ở hai model non-thinking." };
}

export function selectMatrixGroup(view: BenchmarkMatrixView, requested?: string): MatrixGroup | null {
  return view.groups.find((group) => group.id === requested) ?? view.groups[0] ?? null;
}
