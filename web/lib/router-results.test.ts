import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { parseRouterResults } from "./router-results.ts";

const raw = () => JSON.parse(readFileSync(new URL("../data/router-results.json", import.meta.url), "utf-8"));

describe("router results", () => {
  test("the published blob parses and keeps the registered verdicts", () => {
    const data = parseRouterResults(raw());
    expect(data.experiments.map((experiment) => experiment.cards)).toEqual(
      ["MC-90, MC-91, MC-92", "MC-93", "MC-94", "MC-95", "MC-96", "MC-97", "MC-98", "MC-100", "MC-101", "MC-102", "MC-103",
        "MC-104", "MC-105"]);
    const status = Object.fromEntries(data.experiments.map((experiment) => [experiment.cards, experiment.status]));
    expect([status["MC-94"], status["MC-100"], status["MC-102"], status["MC-103"], status["MC-104"], status["MC-105"]])
      .toEqual(["partial", "met", "not_met", "descriptive", "partial", "partial"]);
    const table = data.experiments.find((experiment) => experiment.id === "mc-105")!;
    expect(table.tables.map((block) => block.rows.map((row) => row.id))).toEqual(
      [["always_B", "loop", "always_S", "always_vote", "table"], ["always_B", "loop", "always_S", "always_vote", "table"]]);
    expect(table.tests.filter((entry) => entry.primary)).toHaveLength(12);
    const v2 = data.experiments.find((experiment) => experiment.id === "mc-94")!.tables[0].rows.find((row) => row.id === "v2")!;
    expect(v2.cells.vmlu.score).toBe(76.67);
    expect(data.experiments.every((experiment) => experiment.sources.every((source) => source.path.startsWith("all_res/")))).toBe(true);
  });

  test("the vote explainer carries the funnel and the worked examples that MC-104 reports", () => {
    const data = parseRouterResults(raw());
    const explainer = data.experiments.find((experiment) => experiment.id === "mc-104")!.explainers![0];
    expect(explainer.title).toContain("Bỏ phiếu");
    expect(explainer.groups.map((group) => group.title)).toEqual(["Qwen3.5-9B", "MiMo V2.6 Flash"]);
    const [qwen, mimo] = explainer.groups;
    expect(qwen.facts[0]).toEqual({ label: "Ba lần ra cùng một đáp án", value: "428 / 603" });
    expect(mimo.facts[0]).toEqual({ label: "Ba lần ra cùng một đáp án", value: "462 / 603" });
    const n = Number(qwen.facts[0].value.split("/")[1]);
    const counted = qwen.facts.slice(0, 3).reduce((total, fact) => total + Number(fact.value.split(" / ")[0]), 0);
    expect(counted).toBe(n);
    expect(qwen.examples.map((example) => example.verdict.split(":")[0])).toEqual(["Cứu", "Phá", "Hoà"]);
    expect(qwen.examples.every((example) => example.answers.length === 3 && example.tokens.length === 3)).toBe(true);
    expect(qwen.examples[0].final).toBe(qwen.examples[0].gold);
    expect(data.experiments.find((experiment) => experiment.id === "mc-105")!.explainers![0].groups).toEqual([]);
  });

  test("a broken blob fails loudly instead of rendering", () => {
    const unknownColumn = raw();
    unknownColumn.experiments[0].tables[0].rows[0].cells.unknown = { score: 1, ci: null, tokens: null };
    expect(() => parseRouterResults(unknownColumn)).toThrow(/cell unknown/);
    const badP = raw();
    badP.experiments[2].tests[0].p = 1.5;
    expect(() => parseRouterResults(badP)).toThrow(/outside/);
    const badStatus = raw();
    badStatus.experiments[0].status = "great";
    expect(() => parseRouterResults(badStatus)).toThrow(/status/);
    const reversed = raw();
    reversed.experiments[1].tables[0].rows[0].cells.core.ci = [80, 50];
    expect(() => parseRouterResults(reversed)).toThrow(/reversed/);
    const shortExample = raw();
    shortExample.experiments.find((experiment: { id: string }) => experiment.id === "mc-104").explainers[0]
      .groups[0].examples[0].answers = ["A", "B"];
    expect(() => parseRouterResults(shortExample)).toThrow(/three answers/);
    const noTitle = raw();
    delete noTitle.experiments.find((experiment: { id: string }) => experiment.id === "mc-104").explainers[0].title;
    expect(() => parseRouterResults(noTitle)).toThrow(/explainer.title/);
  });
});
