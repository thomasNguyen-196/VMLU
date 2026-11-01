import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { parseBenchmarkReports } from "./benchmark-reports.ts";
import { buildBenchmarkMatrix } from "./benchmark-matrix.ts";
import { buildBenchmarkComparison } from "./benchmark-comparison.ts";

const view = () => buildBenchmarkMatrix(parseBenchmarkReports(JSON.parse(
  readFileSync(new URL("../data/benchmark-reports.json", import.meta.url), "utf-8"),
)));

describe("comparison across the three displayed tables", () => {
  test("joins measured model profiles across modes and preserves source variants", () => {
    const comparison = buildBenchmarkComparison(view().groups);
    const testSet = comparison.slices.find((slice) => slice.datasetId === "vmlu-test" && slice.metric === "accuracy")!;
    expect(testSet.rows).toHaveLength(5);
    const muse = testSet.rows.find((row) => row.id === "muse13")!;
    expect(muse.cells["omp-full-tools"]?.card).toBe("MC-86 / R2");
    expect(muse.cells["omp-full-tools"]?.score).toBe(87.53);
    expect(muse.cells["direct-default"]?.score).toBe(88.41);
    expect(muse.cells["omp-full-tools"]?.correct).toBeNull();
    const mio = testSet.rows.find((row) => row.id === "mimo26")!;
    expect(mio.cells["omp-full-tools"]?.card).toBe("MC-89");
    expect(mio.cells["omp-full-tools"]?.score).toBe(79.6);
    expect(mio.cells["omp-full-tools"]?.correct).toBeNull();
    const qwen = testSet.rows.find((row) => row.id === "qwen65k")!;
    expect(qwen.cells["direct-default"]?.model).toContain("Q4_K_M");
    expect(qwen.cells["omp-full-tools"]?.model).toContain("IEC");
    expect(qwen.cells["direct-default"]?.delta).toBeCloseTo(-0.92, 6);
    expect(qwen.cells["direct-default"]?.source).toBeTruthy();
  });

  test("keeps missing Legal MC cells missing, rather than zero", () => {
    const comparison = buildBenchmarkComparison(view().groups);
    const legal = comparison.slices.find((slice) => slice.datasetId === "legal-mc")!;
    expect(legal.rows.find((row) => row.id === "muse13")!.cells["omp-full-tools"]).toBeNull();
    expect(legal.rows.find((row) => row.id === "mimo26")!.cells["omp-full-tools"]).toBeNull();
    const testSet = comparison.slices.find((slice) => slice.datasetId === "vmlu-test")!;
    expect(testSet.rows.find((row) => row.id === "mimo25")!.cells["direct-default"]).toBeNull();
  });

  test("separates EM and token F1 for the same reading dataset", () => {
    const comparison = buildBenchmarkComparison(view().groups);
    const squad = comparison.slices.filter((slice) => slice.datasetId === "vi-squad");
    expect(squad.map((slice) => slice.metric)).toEqual(["em", "em_v3", "token_f1", "token_f1_v3"]);
    const em = squad.find((slice) => slice.metric === "em")!;
    const f1 = squad.find((slice) => slice.metric === "token_f1")!;
    expect(em.rows[0].cells["omp-no-tools"]?.score).not.toBe(f1.rows[0].cells["omp-no-tools"]?.score);
  });

  test("shows zero scores and suppresses deltas for unmatched denominators or gold", () => {
    const groups = view().groups;
    const direct = groups.find((group) => group.id === "direct-default")!;
    const testSet = direct.matrices.find((matrix) => matrix.metric === "accuracy")!.columns.find((column) => column.id === "vmlu-test")!;
    const muse = testSet.cells["muse-spark-1-3-contributor"];
    muse.score.score = 0;
    muse.score.n = 1;
    let row = buildBenchmarkComparison(groups).slices.find((slice) => slice.datasetId === "vmlu-test")!.rows.find((row) => row.id === "muse13")!;
    expect(row.cells["direct-default"]?.score).toBe(0);
    expect(row.cells["direct-default"]?.delta).toBeNull();
    muse.score.n = 9833;
    muse.score.gold = "local";
    row = buildBenchmarkComparison(groups).slices.find((slice) => slice.datasetId === "vmlu-test")!.rows.find((row) => row.id === "muse13")!;
    expect(row.cells["direct-default"]?.delta).toBeNull();
  });

  test("does not merge unknown profiles by similar names or include archived groups", () => {
    const groups = view().groups;
    const direct = groups.find((group) => group.id === "direct-default")!;
    direct.models[0].id = "unregistered-muse-variant";
    const archive = structuredClone(direct);
    archive.id = "direct-archived";
    const comparison = buildBenchmarkComparison([...groups, archive]);
    const testSet = comparison.slices.find((slice) => slice.datasetId === "vmlu-test")!;
    expect(testSet.rows.find((row) => row.id === "muse13")!.cells["direct-default"]).toBeNull();
    expect(comparison.series.map((series) => series.id)).toEqual(["omp-no-tools", "omp-full-tools", "direct-default"]);
    expect(buildBenchmarkComparison([]).slices).toEqual([]);
  });
});
