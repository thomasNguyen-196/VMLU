import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { namedTest, overviewCell, parseRouterResults } from "./router-results.ts";

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

  test("the two overview tables read their numbers from the cards' own cells and tests", () => {
    const data = parseRouterResults(raw());
    const card = (id: string) => data.experiments.find((experiment) => experiment.id === id)!;
    // Bảng 1: MC-105, one group per model, the change under "Sau" is the registered paired difference.
    expect(data.benchmark.experiment).toBe("mc-105");
    expect(data.benchmark.groups.map((group) => [group.label, group.rows.map((row) => row.row)])).toEqual(
      [["Qwen3.5-9B", ["always_B", "loop", "always_S"]], ["MiMo V2.6 Flash", ["always_B", "loop", "always_S"]]]);
    const [qwen, mimo] = data.benchmark.groups;
    expect(card("mc-105").tables[qwen.table].title.startsWith("Qwen3.5-9B")).toBe(true);
    expect(card("mc-105").tables[mimo.table].title.startsWith("MiMo V2.6 Flash")).toBe(true);
    const loop = qwen.rows.find((row) => row.row === "loop")!;
    expect(Object.keys(loop.changes)).toHaveLength(6);
    expect(loop.changes["vmlu-dev"]).toBeUndefined();
    const vmlu = namedTest(card("mc-105"), loop.changes["vi-multimodel-v1-vmlu-valid"]);
    expect([vmlu.label.startsWith("Qwen3.5-9B"), vmlu.diff, vmlu.primary, vmlu.p! < data.alpha]).toEqual([true, 12.1, true, true]);
    expect(Object.values(mimo.rows[1].changes).every((label) => label.startsWith("MiMo V2.6 Flash"))).toBe(true);
    // The detail tables print each row's difference from B; B and the /table reference row have none.
    const qwenTable = card("mc-105").tables[qwen.table];
    const vsB = (id: string) => qwenTable.rows.find((row) => row.id === id)!.cells["vi-multimodel-v1-vmlu-valid"].vs_b;
    expect([vsB("always_B"), vsB("loop"), vsB("table")]).toEqual([null, 12.1, null]);
    // The rules of the "Sau" row sit under Bảng 1, with the registered threshold.
    expect(data.benchmark.method.steps.map((step) => step.title)).toEqual(["Hỏi thẳng (B)", "Suy luận từng bước (S)", "Bỏ phiếu"]);
    expect(data.benchmark.method.steps[0].text).toContain("từ 0,80 trở lên");
    // Bảng 2: every other card has lines, and a line's numbers are that card's cells on one column.
    expect(Object.fromEntries(data.experiments.map((experiment) => [experiment.cards, experiment.overview.length]))).toEqual({
      "MC-90, MC-91, MC-92": 2, "MC-93": 1, "MC-94": 1, "MC-95": 1, "MC-96": 1, "MC-97": 1, "MC-98": 1, "MC-100": 2,
      "MC-101": 2, "MC-102": 1, "MC-103": 2, "MC-104": 4, "MC-105": 0 });
    const v2 = card("mc-94");
    const line = v2.overview[0];
    expect([line.tried.row, line.column]).toEqual(["v2", "vmlu"]);
    expect([overviewCell(v2, line, line.tried.row).score, overviewCell(v2, line, line.always_b!).score,
      overviewCell(v2, line, line.always_s!).score]).toEqual([76.67, 68.33, 80]);
    expect(line.tests.map((ref) => namedTest(v2, ref.test).diff)).toEqual([8.33, -3.33]);
    const selfLoop = card("mc-104");
    expect(selfLoop.overview.map((entry) => entry.tests.map((ref) => ref.test.split(":")[0]))).toEqual(
      [["Qwen3.5-9B", "Qwen3.5-9B"], ["MiMo V2.6 Flash", "MiMo V2.6 Flash"], ["Qwen3.5-9B"], ["MiMo V2.6 Flash"]]);
  });

  test("an overview name that points nowhere fails loudly", () => {
    const card = (blob: ReturnType<typeof raw>, id: string) =>
      blob.experiments.find((experiment: { id: string }) => experiment.id === id);
    const unknownRow = raw();
    card(unknownRow, "mc-94").overview[0].always_s = "always_Q";
    expect(() => parseRouterResults(unknownRow)).toThrow(/without a cell/);
    const unknownTest = raw();
    card(unknownTest, "mc-94").overview[0].tests[0].test = "Router v2 so với luôn Q, VMLU";
    expect(() => parseRouterResults(unknownTest)).toThrow(/has no test/);
    const repeated = raw();
    card(repeated, "mc-93").overview.push(card(repeated, "mc-93").overview[0]);
    expect(() => parseRouterResults(repeated)).toThrow(/repeats line/);
    const dropped = raw();
    card(dropped, "mc-93").overview = [];
    expect(() => parseRouterResults(dropped)).toThrow(/overview of mc-93 is empty/);
    const unknownChange = raw();
    unknownChange.benchmark.groups[0].rows[1].changes["vi-multimodel-v1-vmlu-valid"] = "Qwen3.5-9B · VMLU test: sau so với trước";
    expect(() => parseRouterResults(unknownChange)).toThrow(/has no test/);
    const otherColumns = raw();
    const mimoTable = card(otherColumns, "mc-105").tables[1];
    mimoTable.columns.pop();
    for (const row of mimoTable.rows) delete row.cells["vmlu-dev"];
    expect(() => parseRouterResults(otherColumns)).toThrow(/same columns/);
    const noSteps = raw();
    noSteps.benchmark.method.steps = [];
    expect(() => parseRouterResults(noSteps)).toThrow(/benchmark.method needs steps/);
    const emptyStep = raw();
    emptyStep.benchmark.method.steps[1].text = " ";
    expect(() => parseRouterResults(emptyStep)).toThrow(/benchmark.method step text/);
    const oldSchema = raw();
    oldSchema.schema_version = 1;
    expect(() => parseRouterResults(oldSchema)).toThrow(/schema\/version/);
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
    const badDifference = raw();
    badDifference.experiments[0].tables[0].rows[1].cells.mc.vs_b = "+4";
    expect(() => parseRouterResults(badDifference)).toThrow(/cell.vs_b/);
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
