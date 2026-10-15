import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { parseBenchmarkReports, ranksForScores } from "./benchmark-reports.ts";

const fixture = () => JSON.parse(readFileSync(new URL("../data/benchmark-reports.json", import.meta.url), "utf-8"));

describe("reporting preserves evaluation boundaries", () => {
  test("all published reports load with model-specific conditions", () => {
    const data = parseBenchmarkReports(fixture());
    expect(data.reports.some((report) => report.conditions.some((condition) => condition.card === "MC-1"))).toBe(true);
    expect(data.reports.some((report) => report.conditions.some((condition) => condition.card === "MC-70"))).toBe(true);
    expect(data.reports.some((report) => report.conditions.some((condition) => condition.card === "MC-71"))).toBe(true);
  });
  test("Qwen V1 is unranked in the Go comparison", () => {
    const report = parseBenchmarkReports(fixture()).reports.find((entry) => entry.id === "main-v1")!;
    const qwen = report.conditions.find((entry) => entry.card === "MC-56")!;
    const ranks = ranksForScores(report);
    expect(qwen.comparison_group).toBeNull();
    expect(report.benchmarks.filter((entry) => entry.condition_id === qwen.id).every((entry) => !ranks.has(entry))).toBe(true);
    expect(ranks.size).toBeGreaterThan(0);
  });
  test("server grade is visible without invented local correctness", () => {
    const report = parseBenchmarkReports(fixture()).reports.find((entry) => entry.id === "vmlu-v2")!;
    const qwen = report.conditions.find((entry) => entry.card === "MC-70")!;
    const score = report.benchmarks.find((entry) => entry.condition_id === qwen.id && entry.metric === "server_accuracy" && entry.level === "dataset")!;
    expect(score.score).toBe(63.86); expect(score.correct).toBeNull(); expect(score.ci_low).toBeNull();
  });
  test("withheld-gold local score and inferred CI are rejected", () => {
    for (const mutation of ["metric", "ci_low"] as const) {
      const data = fixture();
      const report = data.reports.find((entry: { id: string }) => entry.id === "vmlu-v2");
      const score = report.benchmarks.find((entry: { metric: string }) => entry.metric === "server_accuracy");
      if (mutation === "metric") score.metric = "accuracy";
      else { score.ci_low = 50; score.ci_high = 60; }
      expect(() => parseBenchmarkReports(data)).toThrow();
    }
  });
  test("unknown condition references and missing controls are rejected", () => {
    const data = fixture(); data.reports[0].benchmarks[0].condition_id = "unknown";
    expect(() => parseBenchmarkReports(data)).toThrow();
    const missing = fixture(); delete missing.reports[0].conditions[0].fields.thinking;
    expect(() => parseBenchmarkReports(missing)).toThrow();
  });
  test("unequal sample counts cannot produce ranks", () => {
    const report = parseBenchmarkReports(fixture()).reports.find((entry) => entry.id === "main-v1")!;
    const candidates = report.benchmarks.filter((entry) => entry.level === "dataset" && entry.metric === "accuracy" && entry.dataset_id.endsWith("vmlu-valid"));
    candidates[0].n = 1;
    const ranks = ranksForScores(report);
    expect(candidates.every((entry) => !ranks.has(entry))).toBe(true);
  });
});
