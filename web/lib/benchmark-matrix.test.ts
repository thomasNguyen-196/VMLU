import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { parseBenchmarkReports, type BenchmarkReports, type ReportCondition } from "./benchmark-reports.ts";
import { buildBenchmarkMatrix, directSignature, eligibleOmp, selectMatrixGroup } from "./benchmark-matrix.ts";

const data = () => parseBenchmarkReports(JSON.parse(readFileSync(new URL("../data/benchmark-reports.json", import.meta.url), "utf-8")));

describe("current matrix eligibility and source selection", () => {
  test("only the accepted OMP condition is displayed; pilots and tools runs are excluded", () => {
    const view = buildBenchmarkMatrix(data());
    expect(view.groups.map((group) => group.id)).toEqual(["omp-no-tools"]);
    expect(view.groups[0].models).toHaveLength(4);
    expect(view.groups[0].matrices.map((matrix) => matrix.metric)).toEqual(["accuracy", "em", "token_f1"]);
    const cards = view.groups[0].conditions.map((condition) => condition.card);
    expect(cards).not.toContain("MC-56"); expect(cards).not.toContain("MC-71"); expect(cards).not.toContain("MC-49");
    expect(view.directReason).toContain("Tạm bỏ qua");
  });
  test("VMLU takes the V2 run as a whole cohort, without choosing each model's best score", () => {
    const group = buildBenchmarkMatrix(data()).groups[0];
    const valid = group.matrices[0].columns.find((column) => column.id === "vmlu-valid")!;
    expect(valid.cells["mimo-v2-6-flash"].score.score).toBe(80.24);
    expect(valid.cells["mimo-v2-5"].score.score).toBe(78.23);
    expect(Object.values(valid.cells).every((cell) => cell.reportId === "vmlu-v2")).toBe(true);
    const legal = group.matrices[0].columns.find((column) => column.id === "legal-mc")!;
    expect(legal.cells["muse-spark-1-3-contributor"].condition.card).toBe("MC-53");
  });
  test("Qwen's off/temp-zero scores do not fill missing reading or legal cells", () => {
    const archivedOnly = data();
    const main = archivedOnly.reports.find((report) => report.id === "main-v1")!;
    const matchedIds = new Set(main.conditions.filter((condition) => condition.card === "MC-72").map((condition) => condition.id));
    main.conditions = main.conditions.filter((condition) => !matchedIds.has(condition.id));
    main.benchmarks = main.benchmarks.filter((score) => !matchedIds.has(score.condition_id));
    const group = buildBenchmarkMatrix(archivedOnly).groups[0];
    const qwen = "qwen3-5-9b-65k";
    for (const matrix of group.matrices.filter((entry) => entry.metric !== "accuracy")) {
      expect(matrix.columns.every((column) => column.cells[qwen] === undefined)).toBe(true);
    }
    const accuracy = group.matrices[0];
    expect(accuracy.columns.find((column) => column.id === "legal-nli")!.cells[qwen]).toBeUndefined();
    const testSet = accuracy.columns.find((column) => column.id === "vmlu-test")!.cells[qwen].score;
    expect(testSet.score).toBe(63.86); expect(testSet.correct).toBeNull(); expect(testSet.ci_low).toBeNull();
  });
  test("MC-72 fills all five Qwen datasets with the verified matched condition", () => {
    const group = buildBenchmarkMatrix(data()).groups[0];
    const qwen = "qwen3-5-9b-65k";
    const accuracy = group.matrices.find((matrix) => matrix.metric === "accuracy")!;
    for (const [dataset, score] of [["legal-mc", 84.25], ["legal-nli", 90.67]] as const) {
      const cell = accuracy.columns.find((column) => column.id === dataset)!.cells[qwen];
      expect(cell.condition.card).toBe("MC-72");
      expect(cell.score.score).toBe(score);
    }
    for (const matrix of group.matrices.filter((entry) => entry.metric === "em" || entry.metric === "token_f1")) {
      expect(matrix.columns).toHaveLength(3);
      for (const column of matrix.columns) {
        expect(column.cells[qwen].condition.card).toBe("MC-72");
        expect(Object.keys(column.cells)).toHaveLength(4);
        expect(column.cells[qwen].score.ci_low).not.toBeNull();
      }
    }
    expect(group.conditions.some((condition) => condition.card === "MC-56")).toBe(false);
  });
  test("changing tools, thinking, temperature or seed invalidates eligibility", () => {
    const source = data().reports.find((report) => report.id === "main-v1")!.conditions[0];
    expect(eligibleOmp(source)).toBe(true);
    for (const change of [{ tools: "all" }, { thinking: "off" }, { temperature_effective: 0 }, { seed_sent: true }, { workers: 6 }]) {
      expect(eligibleOmp({ ...source, controls: { ...source.controls!, ...change } })).toBe(false);
    }
  });
  test("unknown condition URLs do not select archived or tools data", () => {
    const view = buildBenchmarkMatrix(data());
    expect(selectMatrixGroup(view, "muse-full-tools-mc71")?.id).toBe("omp-no-tools");
    expect(selectMatrixGroup(view, "direct")?.id).toBe("omp-no-tools");
  });
});

function directData(): BenchmarkReports {
  const fixture = data();
  const original = fixture.reports.find((report) => report.id === "main-v1")!;
  const base = original.benchmarks.find((score) => score.level === "dataset" && score.dataset_id.endsWith("legal-mc-146"))!;
  const conditions: ReportCondition[] = ["a", "b"].map((id) => ({
    ...structuredClone(original.conditions[0]), id, model: id, card: `card-${id}`, comparison_group: null,
    controls: { profile_id: id, transport: "direct", harness_version: null, tools: "none", temperature_requested: 0, temperature_effective: null, thinking: "off", seed_sent: true, seed_requested: 42, output_caps: { multiple_choice: 4 }, workers: 4, system_prompt: "user prompt only", prompt_version: "build_prompt" },
  }));
  return { ...fixture, reports: [{ ...original, id: "verified-direct", surface: "history", conditions, benchmarks: conditions.map((condition, index) => ({ ...base, condition_id: condition.id, score: 80 + index })) }] };
}

describe("direct API comparisons require recorded matching controls", () => {
  test("two independently verified direct models produce a separate condition", () => {
    const view = buildBenchmarkMatrix(directData());
    expect(view.groups).toHaveLength(1); expect(view.groups[0].kind).toBe("direct"); expect(view.groups[0].models).toHaveLength(2);
  });
  test("unknown thinking and different budgets do not produce a direct table", () => {
    for (const changed of ["thinking", "budget"] as const) {
      const fixture = directData(); const controls = fixture.reports[0].conditions[1].controls!;
      if (changed === "thinking") controls.thinking = null;
      else controls.output_caps.multiple_choice = 512;
      expect(buildBenchmarkMatrix(fixture).groups).toHaveLength(0);
    }
    const fixture = directData(); fixture.reports[0].conditions[0].controls!.thinking = null;
    expect(directSignature(fixture.reports[0].conditions[0], "accuracy")).toBeNull();
  });
  test("multiple runs of the same model are not mistaken for multiple models", () => {
    const fixture = directData(); fixture.reports[0].conditions[1].controls!.profile_id = "a";
    expect(buildBenchmarkMatrix(fixture).groups).toHaveLength(0);
  });
});
