/** Router and diagnosis experiments (MC-90 to MC-105) for /table. Written by
 *  code_benchmark/build_router_results.py: every number comes from a registered analysis report, whose SHA-256 is
 *  kept beside it. Each experiment ran on its own items, so each has its own tables. The two overview tables on top
 *  only name cells and tests of those tables (Bảng 1: MC-105's before / after; Bảng 2: lines of one experiment each),
 *  so they cannot disagree with them. A malformed blob or a name that points nowhere throws instead of rendering. */
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export type RouterStatus = "met" | "partial" | "not_met" | "descriptive";
export type RouterRole = "candidate" | "baseline" | "ceiling" | "reference";
/** `vs_b`: score minus the row's B on the same column (same items), in points; null on B and reference rows. */
export interface RouterCell { score: number; ci: [number, number] | null; tokens: number | null; vs_b: number | null }
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
/** One collapsed section under a card: prose, then one block of counted facts and worked examples per student. */
export interface RouterFact { label: string; value: string }
export interface RouterExample {
  item: string;
  question: string;
  gold: string;
  answers: string[];
  final: string;
  tokens: number[];
  verdict: string;
}
export interface RouterExplainerGroup { title: string; facts: RouterFact[]; examples: RouterExample[] }
export interface RouterExplainer {
  id: string;
  title: string;
  paragraphs: string[];
  groups: RouterExplainerGroup[];
  note: string;
}
/** A row of one of the experiment's tables, with the label an overview table prints for it. */
export interface RouterRef { row: string; label: string }
/** A registered comparison, named by its full label in `tests`, with the short label an overview line prints. */
export interface RouterTestRef { test: string; label: string }
/** One line of Bảng 2: rows of `tables[table]` read on `column`, so every number on the line shares its items. */
export interface RouterOverviewLine {
  label: string;
  table: number;
  column: string;
  tried: RouterRef;
  always_b: string | null;
  always_s: string | null;
  others: RouterRef[];
  tests: RouterTestRef[];
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
  overview: RouterOverviewLine[];
  notes: string[];
  explainers?: RouterExplainer[];
  sources: Array<{ path: string; sha256: string }>;
}
/** A row of Bảng 1; `changes` maps a column id to the full label of the test whose difference is printed there. */
export interface RouterBenchmarkRow { row: string; label: string; changes: Record<string, string> }
export interface RouterBenchmarkGroup { label: string; table: number; rows: RouterBenchmarkRow[] }
/** One round of the policy Bảng 1 tries: what is asked, and when it stops. */
export interface RouterStep { title: string; text: string }
/** How the tried row of Bảng 1 picks its answer, written by the builder from the registered loop. */
export interface RouterMethod { title: string; steps: RouterStep[]; note: string }
/** Bảng 1: one experiment's tables with the same columns, one group of rows per model. */
export interface RouterBenchmark {
  experiment: string;
  title: string;
  note: string;
  method: RouterMethod;
  groups: RouterBenchmarkGroup[];
}
export interface RouterResults {
  schema_version: 2;
  generated_at: string;
  alpha: number;
  benchmark: RouterBenchmark;
  experiments: RouterExperiment[];
}

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

/** A row's cell on one column, or a failure naming what the overview pointed at. */
function cellOf(table: RouterTable, row: string, column: string, where: string): RouterCell {
  const cell = table.rows.find((entry) => entry.id === row)?.cells[column];
  if (!cell) fail(`${where} names row ${row} without a cell on column ${column}`);
  return cell;
}

/** The cell an overview line names, on that line's column. */
export function overviewCell(experiment: RouterExperiment, line: RouterOverviewLine, row: string): RouterCell {
  const table = experiment.tables[line.table];
  if (!table) fail(`overview line ${line.label} of ${experiment.id} points at no table`);
  return cellOf(table, row, line.column, `overview line ${line.label} of ${experiment.id}`);
}

/** A registered comparison of the experiment, found by its full label. */
export function namedTest(experiment: RouterExperiment, label: string): RouterTest {
  const found = experiment.tests.find((entry) => entry.label === label);
  if (!found) fail(`${experiment.id} has no test ${label}`);
  return found;
}

function overviewOf(experiment: RouterExperiment, value: unknown): void {
  const id = experiment.id;
  if (!Array.isArray(value)) fail(`overview of ${id}`);
  const seen = new Set<string>();
  for (const line of value) {
    if (!object(line) || !object(line.tried) || !Array.isArray(line.others) || !Array.isArray(line.tests))
      fail(`overview line of ${id}`);
    text(line.label, `overview label of ${id}`);
    text(line.column, `overview column of ${id}`);
    if (!Number.isInteger(line.table) || !experiment.tables[line.table as number]) fail(`overview table of ${id}`);
    const typed = line as unknown as RouterOverviewLine;
    // A line is one row read on one column of one table; the same three twice would be a repeated line.
    const key = `${typed.table}:${typed.column}:${String(line.tried.row)}`;
    if (seen.has(key)) fail(`overview of ${id} repeats line ${key}`);
    seen.add(key);
    for (const ref of [line.tried, ...line.others]) {
      if (!object(ref)) fail(`overview row of ${id}`);
      text(ref.label, `overview row label of ${id}`);
      overviewCell(experiment, typed, text(ref.row, `overview row of ${id}`));
    }
    for (const key of ["always_b", "always_s"]) {
      if (line[key] !== null) overviewCell(experiment, typed, text(line[key], `overview ${key} of ${id}`));
    }
    for (const ref of line.tests) {
      if (!object(ref)) fail(`overview test of ${id}`);
      text(ref.label, `overview test label of ${id}`);
      namedTest(experiment, text(ref.test, `overview test of ${id}`));
    }
  }
}

function benchmarkOf(value: unknown, experiments: RouterExperiment[]): void {
  if (!object(value) || !Array.isArray(value.groups) || !value.groups.length) fail("benchmark");
  text(value.title, "benchmark.title");
  text(value.note, "benchmark.note");
  const method = value.method;
  if (!object(method) || !Array.isArray(method.steps) || !method.steps.length) fail("benchmark.method needs steps");
  text(method.title, "benchmark.method.title");
  text(method.note, "benchmark.method.note");
  for (const step of method.steps) {
    if (!object(step)) fail("benchmark.method step");
    text(step.title, "benchmark.method step title");
    text(step.text, "benchmark.method step text");
  }
  const source = experiments.find((experiment) => experiment.id === value.experiment);
  if (!source) fail(`benchmark experiment ${String(value.experiment)}`);
  let columns: string | null = null;
  for (const group of value.groups) {
    if (!object(group) || !Array.isArray(group.rows) || !group.rows.length) fail("benchmark group");
    text(group.label, "benchmark group label");
    const table = Number.isInteger(group.table) ? source.tables[group.table as number] : undefined;
    if (!table) fail(`benchmark group ${String(group.label)} points at no table`);
    const ids = table.columns.map((column) => column.id);
    if (columns !== null && ids.join("\n") !== columns) fail("benchmark groups need the same columns");
    columns = ids.join("\n");
    for (const row of group.rows) {
      if (!object(row) || !object(row.changes)) fail(`benchmark row of ${String(group.label)}`);
      text(row.label, "benchmark row label");
      const rowId = text(row.row, "benchmark row");
      if (!table.rows.some((entry) => entry.id === rowId)) fail(`benchmark row ${rowId} of ${String(group.label)}`);
      for (const [column, label] of Object.entries(row.changes)) {
        if (!ids.includes(column)) fail(`benchmark change on unknown column ${column}`);
        namedTest(source, text(label, `benchmark change ${column}`));
      }
    }
  }
  // Bảng 2 must list every card that Bảng 1 does not show; a card without lines would drop out silently.
  for (const experiment of experiments) {
    if (experiment.id !== source.id && !experiment.overview.length) fail(`overview of ${experiment.id} is empty`);
  }
}

export function parseRouterResults(value: unknown): RouterResults {
  if (!object(value) || value.schema_version !== 2 || !Array.isArray(value.experiments) || !value.experiments.length)
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
          if (cell.vs_b !== null) finite(cell.vs_b, `cell.vs_b of ${id}`);
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
    if (experiment.explainers !== undefined) {
      if (!Array.isArray(experiment.explainers)) fail(`explainers of ${id}`);
      for (const explainer of experiment.explainers) {
        if (!object(explainer)) fail(`explainer of ${id}`);
        for (const key of ["id", "title", "note"]) text(explainer[key], `explainer.${key} of ${id}`);
        if (!Array.isArray(explainer.paragraphs) || !explainer.paragraphs.length) fail(`explainer paragraphs of ${id}`);
        for (const paragraph of explainer.paragraphs) text(paragraph, `explainer paragraph of ${id}`);
        if (!Array.isArray(explainer.groups)) fail(`explainer groups of ${id}`);
        for (const group of explainer.groups) {
          if (!object(group) || !Array.isArray(group.facts) || !Array.isArray(group.examples))
            fail(`explainer group of ${id}`);
          text(group.title, `explainer group title of ${id}`);
          for (const fact of group.facts) {
            if (!object(fact)) fail(`explainer fact of ${id}`);
            text(fact.label, `explainer fact label of ${id}`);
            text(fact.value, `explainer fact value of ${id}`);
          }
          for (const example of group.examples) {
            if (!object(example) || !Array.isArray(example.answers) || !Array.isArray(example.tokens))
              fail(`explainer example of ${id}`);
            for (const key of ["item", "question", "gold", "final", "verdict"]) text(example[key], `example.${key} of ${id}`);
            if (example.answers.length !== 3 || example.tokens.length !== 3)
              fail(`explainer example ${String(example.item)} needs three answers and three token counts`);
            for (const answer of example.answers) text(answer, `explainer answer of ${id}`);
            for (const tokens of example.tokens) {
              const count = finite(tokens, `explainer tokens of ${id}`);
              if (!Number.isInteger(count) || count < 0) fail(`explainer tokens of ${id}`);
            }
          }
        }
      }
    }
    for (const source of experiment.sources) {
      if (!object(source) || !/^[0-9a-f]{64}$/.test(String(source.sha256))) fail(`source of ${id}`);
      text(source.path, `source path of ${id}`);
    }
    overviewOf(experiment as unknown as RouterExperiment, experiment.overview);
  }
  benchmarkOf(value.benchmark, value.experiments as unknown as RouterExperiment[]);
  return value as unknown as RouterResults;
}

export async function loadRouterResults(): Promise<RouterResults> {
  return parseRouterResults(JSON.parse(await readFile(join(process.cwd(), "data", "router-results.json"), "utf-8")) as unknown);
}
