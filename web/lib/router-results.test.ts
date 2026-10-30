import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { parseRouterResults } from "./router-results.ts";

const raw = () => JSON.parse(readFileSync(new URL("../data/router-results.json", import.meta.url), "utf-8"));

describe("router results", () => {
  test("the published blob parses and keeps the registered verdicts", () => {
    const data = parseRouterResults(raw());
    expect(data.experiments.map((experiment) => experiment.cards)).toEqual(
      ["MC-90, MC-91, MC-92", "MC-93", "MC-94", "MC-95", "MC-96", "MC-97", "MC-98", "MC-100", "MC-101", "MC-102", "MC-103"]);
    const status = Object.fromEntries(data.experiments.map((experiment) => [experiment.cards, experiment.status]));
    expect([status["MC-94"], status["MC-100"], status["MC-102"], status["MC-103"]]).toEqual(["partial", "met", "not_met", "descriptive"]);
    const v2 = data.experiments.find((experiment) => experiment.id === "mc-94")!.tables[0].rows.find((row) => row.id === "v2")!;
    expect(v2.cells.vmlu.score).toBe(76.67);
    expect(data.experiments.every((experiment) => experiment.sources.every((source) => source.path.startsWith("all_res/")))).toBe(true);
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
  });
});
