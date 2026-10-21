import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { parseBenchmarkReports, type BenchmarkReports, type ReportCondition } from "./benchmark-reports.ts";
import { buildBenchmarkMatrix, columnMaximum, directSignature, eligibleOmp, selectMatrixGroup } from "./benchmark-matrix.ts";

const data = () => parseBenchmarkReports(JSON.parse(readFileSync(new URL("../data/benchmark-reports.json", import.meta.url), "utf-8")));

describe("current matrix eligibility and source selection", () => {
  test("OMP and current API Direct groups are displayed; retired Qwen group is excluded", () => {
    const view = buildBenchmarkMatrix(data());
    expect(view.groups.map((group) => group.id)).toEqual(["omp-no-tools", "omp-full-tools", "direct-default"]);
    expect(view.groups[0].models).toHaveLength(5);
    expect(view.groups[0].matrices.map((matrix) => matrix.metric)).toEqual(["accuracy", "em", "token_f1"]);
    const cards = view.groups[0].conditions.map((condition) => condition.card);
    expect(cards).not.toContain("MC-56"); expect(cards).not.toContain("MC-71"); expect(cards).not.toContain("MC-49");
    expect(view.directReason).toBe("");
    expect(selectMatrixGroup(view, "direct-qwen65k")?.id).toBe("omp-no-tools");
    expect(view.groups.find((group) => group.id === "direct-default")!.models.some((entry) => entry.id === "qwen3-5-9b-65k-direct-20k")).toBe(true);
  });
  test("full tools retains Muse, Qwen and MiMo arms with recovery provenance without ranking server grades", () => {
    const reports = data();
    const group = buildBenchmarkMatrix(reports).groups.find((entry) => entry.id === "omp-full-tools")!;
    expect(group.models).toHaveLength(4);
    const accuracy = group.matrices.find((matrix) => matrix.metric === "accuracy")!;
    const column = accuracy.columns.find((entry) => entry.id === "vmlu-test")!;
    const muse12 = column.cells["muse-spark-1-2-contributor-omp-full-tools-mc87"];
    const muse13 = column.cells["muse-spark-1-3-contributor-omp-full-tools-mc86"];
    const qwen = column.cells["qwen3-5-9b-65k-omp-full-tools-mc88"];
    const mimo = column.cells["mimo-v2-6-flash-omp-full-tools-mc89"];
    expect(muse12.score.score).toBe(87.94);
    expect(muse13.score.score).toBe(87.53);
    expect(qwen.score.score).toBe(53.43);
    expect(mimo.score.score).toBe(79.6);
    for (const cell of [muse12, muse13, qwen, mimo]) {
      expect(cell.score.metric).toBe("server_accuracy");
      expect(cell.score.n).toBe(9833);
      expect(cell.score.correct).toBeNull();
      expect(cell.score.ci_low).toBeNull();
      expect(cell.score.ci_high).toBeNull();
      expect(cell.rankEligible).toBe(false);
    }
    expect(muse12.condition.fields.timeout).toContain("900s");
    expect(muse12.condition.controls!.temperature_requested).toBe(1);
    expect(muse12.condition.controls!.temperature_effective).toBeNull();
    expect(muse12.condition.fields.thinking).toContain("effort not pinned");
    expect(qwen.condition.card).toBe("MC-88");
    expect(qwen.condition.fields.timeout).toContain("900s");
    expect(qwen.condition.controls!.temperature_requested).toBe(1);
    expect(qwen.condition.controls!.temperature_effective).toBeNull();
    expect(mimo.condition.card).toBe("MC-89");
    expect(mimo.condition.fields.timeout).toContain("1800s");
    expect(mimo.condition.controls!.temperature_requested).toBe(1);
    expect(mimo.condition.controls!.temperature_effective).toBeNull();
    const usage = reports.run_summaries.find((summary) => summary.id === muse12.condition.id)!.web_search!;
    expect(usage.failed).toBeGreaterThan(0);
    expect(usage.total_calls).toBe(usage.succeeded + usage.failed + usage.unrecorded);
    expect(usage.events).toHaveLength(usage.total_calls);
    const qwenUsage = reports.run_summaries.find((summary) => summary.id === "qwen-omp-full-tools-mc88")!.web_search!;
    expect(qwenUsage.total_calls).toBe(0);
    expect(qwenUsage.events).toHaveLength(0);
    const mimoUsage = reports.run_summaries.find((summary) => summary.id === "mimo-omp-full-tools-mc89")!.web_search!;
    expect(mimoUsage.total_calls).toBeGreaterThan(0);
    expect(mimoUsage.events).toHaveLength(mimoUsage.total_calls);
  });
  test("Muse direct exposes measured scores without inventing effort or Test confidence intervals", () => {
    const view = buildBenchmarkMatrix(data());
    const group = view.groups.find((entry) => entry.id === "direct-default")!;
    expect(selectMatrixGroup(view, "direct-muse13")?.id).toBe("direct-default");
    expect(group.models.map((entry) => entry.name)).toEqual(["Muse Spark 1.3 Contributor", "MiMo V2.6 Flash", "Muse Spark 1.2 Contributor", "Qwen3.5-9B-65K · Q4_K_M"]);
    expect(group.detail).toContain("reasoning mặc định");
    expect(group.models[0].provider).toBe("API Direct");
    const accuracy = group.matrices.find((matrix) => matrix.metric === "accuracy")!;
    const testCell = accuracy.columns.find((column) => column.id === "vmlu-test")!.cells["muse-spark-1-3-contributor"];
    expect(testCell.score.score).toBe(88.41);
    expect(testCell.score.n).toBe(9833);
    expect(testCell.score.correct).toBeNull();
    expect(testCell.score.ci_low).toBeNull();
    expect(testCell.rankEligible).toBe(false);
    expect(testCell.condition.controls!.thinking).toBeNull();
    expect(directSignature(testCell.condition, "accuracy")).toBeNull();
    expect(testCell.condition.controls!.output_caps.multiple_choice).toBe(20000);
    const validCell = accuracy.columns.find((column) => column.id === "vmlu-valid")!.cells["muse-spark-1-3-contributor"];
    expect(validCell.score.score).toBe(91.4);
    expect(validCell.condition.card).toBe("MC-80");
    expect(validCell.condition.controls!.output_caps.multiple_choice).toBe(4096);
    expect(group.matrices.find((matrix) => matrix.metric === "em")!.columns).toHaveLength(3);
    expect(group.notes.join(" ")).toContain("7 câu recovery");
    const qwen = "qwen3-5-9b-65k-direct-20k";
    const qwenTest = accuracy.columns.find((column) => column.id === "vmlu-test")!.cells[qwen];
    expect(qwenTest.score.score).toBe(62.94);
    expect(qwenTest.score.metric).toBe("server_accuracy");
    expect(qwenTest.score.correct).toBeNull();
    expect(qwenTest.score.ci_low).toBeNull();
    expect(qwenTest.condition.card).toBe("MC-83");
    const qwenValid = accuracy.columns.find((column) => column.id === "vmlu-valid")!.cells[qwen];
    expect(qwenValid.score.score).toBe(68.55);
    expect(qwenValid.condition.controls!.output_caps.multiple_choice).toBe(20000);
    expect(qwenTest.rankEligible).toBe(false);
    const mimoTest = accuracy.columns.find((column) => column.id === "vmlu-test")!.cells["mimo-v2-6-flash-direct-20k"];
    expect(mimoTest.score.score).toBe(77.68);
    expect(mimoTest.score.correct).toBeNull();
    expect(mimoTest.score.ci_low).toBeNull();
    expect(mimoTest.rankEligible).toBe(false);
    expect(mimoTest.condition.fields.workers).toContain("work stealing");
    const muse12 = "muse-spark-1-2-contributor-direct-20k";
    const muse12Test = accuracy.columns.find((column) => column.id === "vmlu-test")!.cells[muse12];
    expect(muse12Test.score.score).toBe(87.49);
    expect(muse12Test.condition.card).toBe("MC-84");
    expect(muse12Test.score.correct).toBeNull();
    expect(muse12Test.score.ci_low).toBeNull();
    expect(muse12Test.condition.controls!.output_caps.multiple_choice).toBe(20000);
    expect(accuracy.comment).toContain("Muse Spark 1.2 Contributor đạt 87,49%");
    expect(accuracy.columns.find((column) => column.id === "legal-mc")!.cells[muse12].score.score).toBe(95.21);
  });
  test("Muse 1.2 server grade is embedded in the VMLU accuracy matrix but excluded from matched ranking", () => {
    const view = buildBenchmarkMatrix(data());
    expect(view.runSummaries.map((summary) => summary.id)).toContain("muse12-vmlu-mc74-mc79");
    const group = view.groups[0];
    expect(group.models.some((model) => model.name === "Muse Spark 1.2 Contributor")).toBe(true);
    const accuracy = group.matrices.find((matrix) => matrix.metric === "accuracy")!;
    const test = accuracy.columns.find((column) => column.id === "vmlu-test")!.cells["muse12-vmlu-mc74-mc79"];
    expect(test.score.score).toBe(87.41);
    expect(test.score.metric).toBe("server_accuracy");
    expect(test.rankEligible).toBe(false);
    expect(test.condition.fields.workers).toContain("12 workers");
    const valid = accuracy.columns.find((column) => column.id === "vmlu-valid")!.cells["muse12-vmlu-mc74-mc79"];
    expect(valid.score.score).toBe(90.32);
    expect(valid.score.correct).toBe(672);
    expect(accuracy.comment).toContain("Muse Spark 1.2 Contributor 87,41%");
    expect(accuracy.comment).toContain("Legal MC: Muse Spark 1.2 Contributor 95,21%");
  });
  test("VMLU takes the V2 run as a whole cohort, without choosing each model's best score", () => {
    const group = buildBenchmarkMatrix(data()).groups[0];
    const valid = group.matrices[0].columns.find((column) => column.id === "vmlu-valid")!;
    expect(valid.cells["mimo-v2-6-flash"].score.score).toBe(80.24);
    expect(valid.cells["mimo-v2-5"].score.score).toBe(78.23);
    expect(Object.values(valid.cells).filter((cell) => cell.reportId === "vmlu-v2")).toHaveLength(4);
    expect(valid.cells["muse12-vmlu-mc74-mc79"].score.score).toBe(90.32);
    const legal = group.matrices[0].columns.find((column) => column.id === "legal-mc")!;
    expect(legal.cells["muse-spark-1-3-contributor"].condition.card).toBe("MC-53");
  });
  test("MC-73 completes Muse 1.2 Legal and reading cells with their own condition and CI", () => {
    const group = buildBenchmarkMatrix(data()).groups[0];
    for (const [metric, dataset, expected] of [
      ["accuracy", "legal-mc", 95.21], ["accuracy", "legal-nli", 85.33],
      ["em", "vi-squad", 43], ["token_f1", "vi-squad", 66.23],
      ["em", "vi-drop", 9], ["token_f1", "vi-drop", 19.45],
      ["em", "bidlqa-test", 14.43], ["token_f1", "bidlqa-test", 55.62],
    ] as const) {
      const cell = group.matrices.find((matrix) => matrix.metric === metric)!.columns.find((column) => column.id === dataset)!.cells["muse12-vmlu-mc74-mc79"];
      expect(cell.score.score).toBe(expected);
      expect(cell.condition.card).toBe("MC-73");
      expect(cell.condition.controls!.workers).toBe(4);
      expect(cell.score.ci_low).not.toBeNull();
    }
  });
  test("visual maximum includes mixed conditions, ties and zero without inventing missing scores", () => {
    const column = structuredClone(buildBenchmarkMatrix(data()).groups[0].matrices[0].columns[0]);
    for (const cell of Object.values(column.cells)) cell.score.score = 0;
    expect(columnMaximum(column)).toBe(0);
    const supplemental = column.cells["muse12-vmlu-mc74-mc79"];
    supplemental.score.score = 100;
    expect(supplemental.rankEligible).toBe(false);
    expect(columnMaximum(column)).toBe(100);
    const another = Object.values(column.cells).find((cell) => cell !== supplemental)!;
    another.score.score = 100;
    expect(Object.values(column.cells).filter((cell) => cell.score.score === columnMaximum(column))).toHaveLength(2);
    column.cells = {};
    expect(columnMaximum(column)).toBeNull();
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
        expect(Object.keys(column.cells)).toHaveLength(5);
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
