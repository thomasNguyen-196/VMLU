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
  return value as unknown as BenchmarkReports;
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
