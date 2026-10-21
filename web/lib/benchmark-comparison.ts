/** Descriptive comparisons reuse curated table cells; they never create a matched cohort. */
import type { MatrixGroup, MatrixMetric } from "./benchmark-matrix.ts";

export type ComparisonMode = "omp-no-tools" | "omp-full-tools" | "direct-default";
export interface ComparisonCell {
  score: number;
  n: number | null;
  correct: number | null;
  gold: string;
  card: string;
  model: string;
  provider: string;
  source: string;
  delta: number | null;
}
export interface ComparisonRow {
  id: string;
  name: string;
  cells: Record<ComparisonMode, ComparisonCell | null>;
}
export interface ComparisonSlice {
  datasetId: string;
  dataset: string;
  metric: MatrixMetric;
  metricLabel: string;
  rows: ComparisonRow[];
}
export interface BenchmarkComparison {
  series: Array<{ id: ComparisonMode; label: string }>;
  slices: ComparisonSlice[];
}

// Explicit display families only. Source model names (including quantization) stay in each cell.
const MODELS = [
  { id: "muse13", name: "Muse Spark 1.3", profiles: ["muse-spark-1-3-contributor", "muse-spark-1-3-contributor-omp-full-tools-mc86"] },
  { id: "muse12", name: "Muse Spark 1.2", profiles: ["muse12-vmlu-mc74-mc79", "muse-spark-1-2-contributor-omp-full-tools-mc87", "muse-spark-1-2-contributor-direct-20k"] },
  { id: "mimo26", name: "MiMo V2.6 Flash", profiles: ["mimo-v2-6-flash", "mimo-v2-6-flash-direct-20k", "mimo-v2-6-flash-omp-full-tools-mc89"] },
  { id: "mimo25", name: "MiMo V2.5", profiles: ["mimo-v2-5"] },
  { id: "qwen65k", name: "Qwen3.5-9B-65K", profiles: ["qwen3-5-9b-65k", "qwen3-5-9b-65k-omp-full-tools-mc88", "qwen3-5-9b-65k-direct-20k"] },
];
const SERIES: BenchmarkComparison["series"] = [
  { id: "omp-no-tools", label: "OMP · không tools" },
  { id: "omp-full-tools", label: "OMP · full tools" },
  { id: "direct-default", label: "API trực tiếp" },
];

export function buildBenchmarkComparison(groups: MatrixGroup[]): BenchmarkComparison {
  const slices = new Map<string, ComparisonSlice>();
  for (const series of SERIES) {
    const group = groups.find((group) => group.id === series.id);
    if (!group) continue;
    for (const matrix of group.matrices) for (const column of matrix.columns) {
      const key = `${column.id}:${matrix.metric}`;
      const slice = slices.get(key) ?? {
        datasetId: column.id, dataset: column.label, metric: matrix.metric, metricLabel: matrix.title, rows: [],
      };
      slices.set(key, slice);
      for (const model of group.models) {
        const cell = column.cells[model.id];
        if (!cell) continue;
        const family = MODELS.find((entry) => entry.profiles.includes(model.id));
        const id = family?.id ?? model.id;
        let row = slice.rows.find((row) => row.id === id);
        if (!row) {
          row = { id, name: family?.name ?? model.name, cells: { "omp-no-tools": null, "omp-full-tools": null, "direct-default": null } };
          slice.rows.push(row);
        }
        row.cells[series.id] = {
          score: cell.score.score, n: cell.score.n, correct: cell.score.correct, gold: cell.score.gold,
          card: cell.condition.card, model: cell.condition.model,
          provider: cell.condition.fields.provider, source: cell.score.source, delta: null,
        };
      }
    }
  }
  for (const slice of slices.values()) {
    slice.rows.sort((a, b) => {
      const order = (id: string) => { const i = MODELS.findIndex((model) => model.id === id); return i < 0 ? MODELS.length : i; };
      return order(a.id) - order(b.id) || a.name.localeCompare(b.name);
    });
    for (const row of slice.rows) {
      const baseline = row.cells["omp-no-tools"];
      for (const mode of ["omp-full-tools", "direct-default"] as const) {
        const cell = row.cells[mode];
        if (cell && baseline && cell.n !== null && cell.n === baseline.n && cell.gold === baseline.gold) {
          cell.delta = Math.round((cell.score - baseline.score) * 100) / 100;
        }
      }
    }
  }
  return { series: SERIES, slices: [...slices.values()] };
}
