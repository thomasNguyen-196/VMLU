/** Reporting schema v1 preserves evaluation arms and does not rescore outputs. */
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export type ReportSurface = "v1" | "v2" | "history";
export type ReportMetric = "accuracy" | "server_accuracy" | "server_macro" | "em" | "token_f1" | "char_f1" | "valid_rate" | "agreement" | "function_exact";
export interface ReportControls {
  profile_id: string;
  transport: "omp" | "direct";
  harness_version: string | null;
  tools: string | null;
  temperature_requested: number | null;
  temperature_effective: number | null;
  thinking: string | null;
  seed_sent: boolean | null;
  seed_requested: number | null;
  output_caps: Record<string, number>;
  workers: number | null;
  system_prompt: string | null;
  prompt_version: string | null;
}
export interface ReportCondition {
  id: string;
  model: string;
  card: string;
  comparison_group: string | null;
  fields: Record<string, string>;
  sources: Array<{ path: string; label: string }>;
  manifest_sha256: string | null;
  measurement_card_hash: string | null;
  controls?: ReportControls;
}
export interface ReportScore {
  condition_id: string;
  dataset_id: string;
  dataset: string;
  level: "dataset" | "category" | "subject";
  category: string;
  metric: ReportMetric;
  score: number;
  n: number | null;
  correct: number | null;
  ci_low: number | null;
  ci_high: number | null;
  gold: string;
  truncated: number | null;
  source: string;
  delta: number | null;
  delta_ci_low: number | null;
  delta_ci_high: number | null;
}
export interface EvaluationReport {
  id: string;
  surface: ReportSurface;
  title: string;
  protocol: string;
  scope: string;
  conditions: ReportCondition[];
  benchmarks: ReportScore[];
  comments: string[];
  notes: string[];
}
export interface BenchmarkReports {
  schema_version: 1;
  generated_at: string;
  field_labels: Record<string, string>;
  metric_labels: Record<ReportMetric, string>;
  reports: EvaluationReport[];
  run_summaries: BenchmarkRunSummary[];
}
export interface BenchmarkRunSummaryRoute {
  condition_id: string;
  route: string;
  item_count: number;
}
export interface BenchmarkRunSummaryDataset {
  dataset_id: string;
  dataset: string;
  gold: "local" | "withheld";
  request_completed: number;
  total_items: number;
  request_errors: number;
  accuracy: number | null;
  correct: number | null;
  ci_low?: number | null;
  ci_high?: number | null;
  server_accuracy: number | null;
  server_grade_source: string | null;
  server_breakdown: Array<{ category: string; subject: string | null; score: number }>;
  route_breakdown: BenchmarkRunSummaryRoute[];
}
export type WebSearchStatus = "success" | "failure" | "unrecorded";
export interface WebSearchEvent {
  event_id: string;
  source: string;
  dataset_id: string;
  dataset: string;
  item_id: string;
  phase: string;
  attempt: number;
  worker_id: number | null;
  call_index: number;
  tool_call_id: string;
  status: WebSearchStatus;
  status_source: string;
  started_at: string;
  finished_at: string;
}
export interface WebSearchUsage {
  total_calls: number;
  succeeded: number;
  failed: number;
  unrecorded: number;
  events: WebSearchEvent[];
}
export interface BenchmarkRunSummary {
  id: string;
  title: string;
  model: string;
  condition: string;
  status: "complete" | "partial";
  completed_items: number;
  total_items: number;
  request_errors: number;
  shards: number;
  workers_per_shard: number;
  total_workers: number;
  route_breakdown: BenchmarkRunSummaryRoute[];
  datasets: BenchmarkRunSummaryDataset[];
  source: string;
  notes: string[];
  web_search?: WebSearchUsage;
}

const METRICS = new Set(["accuracy", "server_accuracy", "server_macro", "em", "token_f1", "char_f1", "valid_rate", "agreement", "function_exact"]);
const CONDITION_FIELDS = ["harness", "provider", "temperature", "thinking", "seed", "tools", "prompt", "context", "session", "output_cap", "workers", "timeout", "retry", "gold", "identity", "date"];
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function text(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`Invalid report ${label}: text required`);
}
function strings(value: unknown, label: string) {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) throw new Error(`Invalid report ${label}`);
}
function number(value: unknown, label: string, min: number, max: number, integer = false) {
  if (value === null) return;
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max || (integer && !Number.isInteger(value))) throw new Error(`Invalid report ${label}: numeric bounds`);
}

export function parseBenchmarkReports(value: unknown): BenchmarkReports {
  if (!object(value) || value.schema_version !== 1 || !Array.isArray(value.reports)) throw new Error("Invalid report schema/version");
  text(value.generated_at, "generated_at");
  if (!object(value.field_labels) || !object(value.metric_labels)) throw new Error("Invalid report labels");
  const runSummaries = value.run_summaries ?? [];
  if (!Array.isArray(runSummaries)) throw new Error("Invalid run summaries");
  const runSummaryIds = new Set<string>();
  for (const summary of runSummaries) {
    if (!object(summary) || !["complete", "partial"].includes(String(summary.status))) throw new Error("Invalid run summary");
    for (const key of ["id", "title", "model", "condition", "source"]) text(summary[key], `run_summary.${key}`);
    if (runSummaryIds.has(String(summary.id))) throw new Error("Duplicate run summary id");
    runSummaryIds.add(String(summary.id));
    for (const key of ["completed_items", "total_items", "request_errors", "shards", "workers_per_shard", "total_workers"])
      number(summary[key], `run_summary.${key}`, 0, Number.MAX_SAFE_INTEGER, true);
    if (typeof summary.completed_items !== "number" || typeof summary.total_items !== "number" || summary.completed_items > summary.total_items || !Array.isArray(summary.route_breakdown) || !Array.isArray(summary.datasets))
      throw new Error("Invalid run summary counts");
    strings(summary.notes, "run_summary.notes");
    if (summary.web_search !== undefined) {
      const usage = summary.web_search;
      if (!object(usage) || !Array.isArray(usage.events)) throw new Error("Invalid run summary web search log");
      for (const key of ["total_calls", "succeeded", "failed", "unrecorded"])
        number(usage[key], `run_summary.web_search.${key}`, 0, Number.MAX_SAFE_INTEGER, true);
      const totalCalls = usage.total_calls as number;
      const succeeded = usage.succeeded as number;
      const failed = usage.failed as number;
      const unrecorded = usage.unrecorded as number;
      const eventIds = new Set<string>();
      for (const event of usage.events) {
        if (!object(event) || !["success", "failure", "unrecorded"].includes(String(event.status)))
          throw new Error("Invalid run summary web search event");
        for (const key of ["event_id", "source", "dataset_id", "dataset", "item_id", "phase", "status_source"])
          text(event[key], `run_summary.web_search.event.${key}`);
        for (const key of ["attempt", "call_index"])
          number(event[key], `run_summary.web_search.event.${key}`, 1, Number.MAX_SAFE_INTEGER, true);
        if (event.worker_id !== null) number(event.worker_id, "run_summary.web_search.event.worker_id", 1, Number.MAX_SAFE_INTEGER, true);
        if (typeof event.tool_call_id !== "string" || typeof event.started_at !== "string" || typeof event.finished_at !== "string")
          throw new Error("Invalid run summary web search event text fields");
        if (eventIds.has(String(event.event_id))) throw new Error("Duplicate run summary web search event");
        eventIds.add(String(event.event_id));
      }
      if (usage.events.length !== totalCalls
          || succeeded + failed + unrecorded !== totalCalls
          || usage.events.filter((event) => event.status === "success").length !== succeeded
          || usage.events.filter((event) => event.status === "failure").length !== failed
          || usage.events.filter((event) => event.status === "unrecorded").length !== unrecorded)
        throw new Error("Invalid run summary web search counts");
    }
    const validateRoutes = (routes: unknown[]) => {
      for (const route of routes) {
        if (!object(route)) throw new Error("Invalid run summary route");
        text(route.condition_id, "run_summary.route.condition_id");
        text(route.route, "run_summary.route.route");
        number(route.item_count, "run_summary.route.item_count", 1, Number.MAX_SAFE_INTEGER, true);
      }
    };
    validateRoutes(summary.route_breakdown);
    for (const dataset of summary.datasets) {
      if (!object(dataset) || !["local", "withheld"].includes(String(dataset.gold)) || !Array.isArray(dataset.route_breakdown))
        throw new Error("Invalid run summary dataset");
      for (const key of ["dataset_id", "dataset"]) text(dataset[key], `run_summary.dataset.${key}`);
      for (const key of ["request_completed", "total_items", "request_errors"])
        number(dataset[key], `run_summary.dataset.${key}`, 0, Number.MAX_SAFE_INTEGER, true);
      number(dataset.accuracy, "run_summary.dataset.accuracy", 0, 100);
      number(dataset.correct, "run_summary.dataset.correct", 0, Number.MAX_SAFE_INTEGER, true);
      if (dataset.ci_low !== undefined || dataset.ci_high !== undefined) {
        number(dataset.ci_low, "run_summary.dataset.ci_low", 0, 100);
        number(dataset.ci_high, "run_summary.dataset.ci_high", 0, 100);
        if ((dataset.ci_low === null) !== (dataset.ci_high === null)
            || (typeof dataset.ci_low === "number" && typeof dataset.ci_high === "number" && dataset.ci_low > dataset.ci_high)
            || (dataset.gold === "withheld" && (dataset.ci_low !== null || dataset.ci_high !== null)))
          throw new Error("Invalid run summary confidence interval");
      }
      number(dataset.server_accuracy, "run_summary.dataset.server_accuracy", 0, 100);
      if (dataset.server_grade_source !== null) text(dataset.server_grade_source, "run_summary.dataset.server_grade_source");
      if (!Array.isArray(dataset.server_breakdown)) throw new Error("Invalid run summary server breakdown");
      for (const grade of dataset.server_breakdown) {
        if (!object(grade)) throw new Error("Invalid run summary server grade");
        text(grade.category, "run_summary.server_grade.category");
        if (grade.subject !== null) text(grade.subject, "run_summary.server_grade.subject");
        number(grade.score, "run_summary.server_grade.score", 0, 100);
      }
      if (typeof dataset.request_completed !== "number" || typeof dataset.total_items !== "number" || dataset.request_completed > dataset.total_items)
        throw new Error("Invalid run summary dataset counts");
      if (dataset.gold === "withheld" && (dataset.accuracy !== null || dataset.correct !== null))
        throw new Error("Withheld-gold run summary must not contain accuracy or correct count");
      if ((dataset.accuracy === null) !== (dataset.correct === null) || (typeof dataset.correct === "number" && dataset.correct > dataset.request_completed))
        throw new Error("Invalid run summary dataset score");
      if (dataset.gold === "local" && (dataset.server_accuracy !== null || dataset.server_grade_source !== null || dataset.server_breakdown.length))
        throw new Error("Local-gold run summary cannot carry a server grade");
      if ((dataset.server_accuracy === null) !== (dataset.server_grade_source === null)
          || (dataset.server_accuracy === null) !== (dataset.server_breakdown.length === 0))
        throw new Error("Incomplete server grade metadata");
      validateRoutes(dataset.route_breakdown);
    }
  }
  const reportIds = new Set<string>();
  for (const raw of value.reports) {
    if (!object(raw)) throw new Error("Invalid report entry");
    for (const key of ["id", "title", "protocol", "scope"]) text(raw[key], key);
    if (!["v1", "v2", "history"].includes(String(raw.surface)) || reportIds.has(String(raw.id))) throw new Error("Invalid report surface/duplicate id");
    reportIds.add(String(raw.id));
    if (!Array.isArray(raw.conditions) || !raw.conditions.length || !Array.isArray(raw.benchmarks)) throw new Error("Invalid report conditions/scores");
    const conditionIds = new Set<string>();
    for (const condition of raw.conditions) {
      if (!object(condition) || !object(condition.fields) || !Array.isArray(condition.sources)) throw new Error("Invalid condition record");
      for (const key of ["id", "model", "card"]) text(condition[key], key);
      if (conditionIds.has(String(condition.id))) throw new Error("Duplicate condition id");
      conditionIds.add(String(condition.id));
      if (condition.comparison_group !== null) text(condition.comparison_group, "comparison_group");
      for (const key of CONDITION_FIELDS) text(condition.fields[key], `condition.${key}`);
      if (Object.values(condition.fields).some((entry) => typeof entry !== "string")) throw new Error("Invalid condition fields");
      for (const evidence of condition.sources) {
        if (!object(evidence)) throw new Error("Invalid evidence");
        text(evidence.path, "source.path"); text(evidence.label, "source.label");
      }
      if (condition.controls !== undefined) {
        const controls = condition.controls;
        if (!object(controls) || !object(controls.output_caps) || !["omp", "direct"].includes(String(controls.transport))) throw new Error("Invalid typed controls");
        text(controls.profile_id, "controls.profile_id");
        for (const key of ["harness_version", "tools", "thinking", "system_prompt", "prompt_version"]) if (controls[key] !== null) text(controls[key], `controls.${key}`);
        if (controls.seed_sent !== null && typeof controls.seed_sent !== "boolean") throw new Error("Invalid inference seed policy");
        for (const key of ["temperature_requested", "temperature_effective"]) number(controls[key], key, 0, 2);
        number(controls.seed_requested, "seed_requested", 0, Number.MAX_SAFE_INTEGER, true);
        number(controls.workers, "workers", 1, Number.MAX_SAFE_INTEGER, true);
        for (const cap of Object.values(controls.output_caps)) number(cap, "output cap", 1, Number.MAX_SAFE_INTEGER, true);
      }
    }
    const seen = new Set<string>();
    for (const score of raw.benchmarks) {
      if (!object(score) || !conditionIds.has(String(score.condition_id)) || !METRICS.has(String(score.metric))) throw new Error("Invalid report score identity/metric");
      for (const key of ["dataset_id", "dataset", "source", "gold"]) text(score[key], key);
      if (!["dataset", "category", "subject"].includes(String(score.level)) || typeof score.category !== "string") throw new Error("Invalid score level/category");
      const key = JSON.stringify([score.condition_id, score.dataset_id, score.level, score.category, score.metric]);
      if (seen.has(key)) throw new Error("Duplicate report score");
      seen.add(key);
      if (score.score === null) throw new Error("Missing report point score");
      for (const field of ["score", "ci_low", "ci_high"]) number(score[field], field, 0, 100);
      for (const field of ["delta", "delta_ci_low", "delta_ci_high"]) number(score[field], field, -100, 100);
      for (const field of ["n", "correct", "truncated"]) number(score[field], field, 0, Number.MAX_SAFE_INTEGER, true);
      if ((score.ci_low === null) !== (score.ci_high === null) || (typeof score.ci_low === "number" && typeof score.ci_high === "number" && score.ci_low > score.ci_high)) throw new Error("Invalid score CI");
      if (typeof score.correct === "number" && typeof score.n === "number" && score.correct > score.n) throw new Error("Invalid numerator/denominator");
      if (score.metric === "accuracy" && score.gold !== "local") throw new Error("Local accuracy requires local gold");
      if (score.gold === "withheld" && (score.correct !== null || score.ci_low !== null || score.ci_high !== null)) throw new Error("Withheld-gold count/CI must remain unknown");
    }
    strings(raw.comments, "comments"); strings(raw.notes, "notes");
  }
  return { ...value, run_summaries: runSummaries } as unknown as BenchmarkReports;
}

export function ranksForScores(report: EvaluationReport): Map<ReportScore, number> {
  const conditions = new Map(report.conditions.map((condition) => [condition.id, condition]));
  const groups = new Map<string, ReportScore[]>();
  for (const score of report.benchmarks) {
    const group = conditions.get(score.condition_id)?.comparison_group;
    if (!group || ["valid_rate", "agreement"].includes(score.metric)) continue;
    const key = JSON.stringify([group, score.dataset_id, score.level, score.category, score.metric]);
    groups.set(key, [...(groups.get(key) ?? []), score]);
  }
  const ranks = new Map<ReportScore, number>();
    for (const rows of groups.values()) {
    if (rows.length < 2 || new Set(rows.map((score) => score.n)).size !== 1) continue;
    const sorted = [...rows].sort((a, b) => b.score - a.score);
    for (const score of rows) ranks.set(score, sorted.findIndex((entry) => entry.score === score.score) + 1);
  }
  return ranks;
}

export async function loadBenchmarkReports(): Promise<BenchmarkReports> {
  return parseBenchmarkReports(JSON.parse(await readFile(join(process.cwd(), "data", "benchmark-reports.json"), "utf-8")) as unknown);
}
