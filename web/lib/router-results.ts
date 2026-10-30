/** Router and diagnosis experiments (MC-90 to MC-103) for /table. Written by
 *  code_benchmark/build_router_results.py: every number comes from a registered analysis report, whose SHA-256 is
 *  kept beside it. Each experiment ran on its own items, so each has its own tables. A malformed blob throws
 *  instead of rendering zeros. */
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export type RouterStatus = "met" | "partial" | "not_met" | "descriptive";
export type RouterRole = "candidate" | "baseline" | "ceiling" | "reference";
export interface RouterCell { score: number; ci: [number, number] | null; tokens: number | null }
export interface RouterColumn { id: string; label: string; metric: string; n: number }
export interface RouterRow { id: string; label: string; role: RouterRole; cells: Record<string, RouterCell> }
export interface RouterTable { title: string; columns: RouterColumn[]; rows: RouterRow[]; note: string }
export interface RouterTest {
  label: string;
  diff: number | null;
  ci: [number, number] | null;
  p: number | null;
  p_kind: string;
  note: string;
  primary: boolean;
}
export interface RouterExperiment {
  id: string;
  cards: string;
  title: string;
  question: string;
  student: string;
  items: string;
  status: RouterStatus;
  verdict: string;
  tables: RouterTable[];
  tests: RouterTest[];
  notes: string[];
  sources: Array<{ path: string; sha256: string }>;
}
export interface RouterResults { schema_version: 1; generated_at: string; alpha: number; experiments: RouterExperiment[] }

const STATUSES = new Set(["met", "partial", "not_met", "descriptive"]);
const ROLES = new Set(["candidate", "baseline", "ceiling", "reference"]);

function fail(message: string): never {
  throw new Error(`Invalid router results: ${message}`);
}
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function text(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) fail(`${label} must be non-empty text`);
  return value;
}
function finite(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail(`${label} must be a finite number`);
  return value;
}
function interval(value: unknown, label: string): void {
  if (value === null) return;
  if (!Array.isArray(value) || value.length !== 2) fail(`${label} must be a pair or null`);
  if (finite(value[0], label) > finite(value[1], label)) fail(`${label} is reversed`);
}

export function parseRouterResults(value: unknown): RouterResults {
  if (!object(value) || value.schema_version !== 1 || !Array.isArray(value.experiments) || !value.experiments.length)
    fail("schema/version or experiments");
  text(value.generated_at, "generated_at");
  finite(value.alpha, "alpha");
  const ids = new Set<string>();
  for (const experiment of value.experiments) {
    if (!object(experiment)) fail("experiment entry");
    for (const key of ["id", "cards", "title", "question", "student", "items", "verdict"]) text(experiment[key], `experiment.${key}`);
    const id = String(experiment.id);
    if (ids.has(id)) fail(`duplicate experiment ${id}`);
    ids.add(id);
    if (!STATUSES.has(String(experiment.status))) fail(`status of ${id}`);
    if (!Array.isArray(experiment.tables) || !experiment.tables.length || !Array.isArray(experiment.tests)
        || !Array.isArray(experiment.notes) || !Array.isArray(experiment.sources) || !experiment.sources.length)
      fail(`tables, tests, notes or sources of ${id}`);
    for (const table of experiment.tables) {
      if (!object(table) || !Array.isArray(table.columns) || !table.columns.length || !Array.isArray(table.rows) || !table.rows.length)
        fail(`table of ${id}`);
      text(table.title, `table title of ${id}`);
      if (typeof table.note !== "string") fail(`table note of ${id}`);
      const columns = new Set<string>();
      for (const column of table.columns) {
        if (!object(column)) fail(`column of ${id}`);
        for (const key of ["id", "label", "metric"]) text(column[key], `column.${key} of ${id}`);
        const n = finite(column.n, `column.n of ${id}`);
        if (!Number.isInteger(n) || n < 1) fail(`column.n of ${id}`);
        columns.add(String(column.id));
      }
      for (const row of table.rows) {
        if (!object(row) || !object(row.cells) || !ROLES.has(String(row.role))) fail(`row of ${id}`);
        text(row.id, `row.id of ${id}`);
        text(row.label, `row.label of ${id}`);
        for (const [key, cell] of Object.entries(row.cells)) {
          if (!columns.has(key) || !object(cell)) fail(`cell ${key} of ${id}`);
          finite(cell.score, `cell.score of ${id}`);
          interval(cell.ci, `cell.ci of ${id}`);
          if (cell.tokens !== null) finite(cell.tokens, `cell.tokens of ${id}`);
        }
      }
    }
    for (const test of experiment.tests) {
      if (!object(test) || typeof test.primary !== "boolean" || typeof test.p_kind !== "string" || typeof test.note !== "string")
        fail(`test of ${id}`);
      text(test.label, `test label of ${id}`);
      if (test.diff !== null) finite(test.diff, `test.diff of ${id}`);
      interval(test.ci, `test.ci of ${id}`);
      if (test.p !== null) {
        const p = finite(test.p, `test.p of ${id}`);
        if (p < 0 || p > 1) fail(`test.p of ${id} outside [0, 1]`);
      }
    }
    for (const note of experiment.notes) text(note, `note of ${id}`);
    for (const source of experiment.sources) {
      if (!object(source) || !/^[0-9a-f]{64}$/.test(String(source.sha256))) fail(`source of ${id}`);
      text(source.path, `source path of ${id}`);
    }
  }
  return value as unknown as RouterResults;
}

export async function loadRouterResults(): Promise<RouterResults> {
  return parseRouterResults(JSON.parse(await readFile(join(process.cwd(), "data", "router-results.json"), "utf-8")) as unknown);
}
