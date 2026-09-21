/** Contract tests for the /results insight layer.
 *
 * Offline, thuần hàm: summary giả lập theo đúng shape `summaries` (giá trị CSV
 * dạng chuỗi như migrate_results_to_mongo ghi vào Mongo).
 * Run: `cd web && bun test lib/insights.test.ts`
 */
import { describe, expect, test } from "bun:test";
import { buildInsight, deriveEvidence } from "./insights.ts";

const mcSummary = {
  n: 40,
  accuracy_rows: [
    { level: "overall", name: "overall", n: "40", correct: "30", accuracy: "75" },
    { level: "category", name: "STEM", n: "20", correct: "18", accuracy: "90" },
    { level: "category", name: "Other", n: "20", correct: "12", accuracy: "60" },
    { level: "subject", name: "37 Administrative Law", n: "10", correct: "3", accuracy: "30" },
    { level: "subject", name: "02 Elementary Science", n: "10", correct: "10", accuracy: "100" },
  ],
};

const readingSummary = {
  n: 400,
  reading_rows: [
    { dataset: "squad", n: "200", em_count: "195", em: "97.5", char_f1: "98.61" },
    { dataset: "drop", n: "200", em_count: "126", em: "63", char_f1: "74.49" },
    { dataset: "ALL", n: "400", em_count: "321", em: "80.25", char_f1: "86.55" },
  ],
};

const vbenchSummary = {
  n: 5141,
  valid_rows: [
    { track: "mc", domain: "mathematics", n: "125", valid: "125", valid_rate: "100" },
    { track: "agentic", domain: "agentic", n: "1000", valid: "1000", valid_rate: "100" },
  ],
  server_rows: [
    { domain: "mathematics", track: "multiple-choice", score: "20", correct: "25", total: "125" },
    { domain: "computer_science", track: "multiple-choice", score: "71.28", correct: "134", total: "188" },
    { domain: "agentic", track: "function calling", score: "39.7", correct: "397", total: "1000" },
  ],
};

describe("deriveEvidence", () => {
  test("MC: overall + nhóm + môn trũng + số môn dưới 50%", () => {
    const ev = deriveEvidence(mcSummary);
    expect(ev.join("\n")).toContain("Overall: 30/40 = 75%");
    expect(ev.join("\n")).toContain("Nhóm thấp nhất: Other 60%");
    expect(ev.join("\n")).toContain("Môn trũng nhất: 37 Administrative Law 30% (n=10)");
    expect(ev.join("\n")).toContain("1/2 môn dưới 50%");
  });

  test("reading: tách nguồn + gap EM→F1", () => {
    const ev = deriveEvidence(readingSummary);
    expect(ev.join("\n")).toContain("Tổng: EM 80.25% · char-F1 86.55 (321/400 exact)");
    expect(ev.join("\n")).toContain("Gap EM→F1: 6.30 điểm");
    expect(ev.join("\n")).toContain("drop: EM 63% · F1 74.49 (n=200)");
  });

  test("vbench: micro từ server rows + agentic + cú pháp", () => {
    const ev = deriveEvidence(vbenchSummary);
    expect(ev.join("\n")).toContain("Micro (server rows): 556/1313 = 42.35%");
    expect(ev.join("\n")).toContain("Agentic: 39.7% (397/1000)");
    expect(ev.join("\n")).toContain("mc 125/125 valid");
  });

  test("summary rỗng/null không ném lỗi", () => {
    expect(deriveEvidence(null)).toEqual([]);
    const ev = deriveEvidence({ n: 10 });
    expect(ev).toHaveLength(1);
    expect(ev[0]).toContain("n=10");
  });
});

describe("buildInsight", () => {
  test("cặp đã có seed: curated + causes/actions đầy đủ", () => {
    const ins = buildInsight("qwen3-5-9b-28k", "vmlu-mqa-all-gold", mcSummary);
    expect(ins.curated).toBe(true);
    expect(ins.causes.length).toBeGreaterThan(0);
    expect(ins.actions.length).toBeGreaterThan(0);
    expect(ins.caveat).toBeTruthy();
    expect(ins.evidence.length).toBeGreaterThan(0);
  });

  test("dataset có seed '*' (valid) vẫn curated cho model lạ", () => {
    const ins = buildInsight("unknown-model", "vmlu-mqa-valid", mcSummary);
    expect(ins.curated).toBe(true);
  });

  test("cặp chưa có seed: fallback + vẫn giữ bằng chứng số", () => {
    const ins = buildInsight("unknown-model", "unknown-dataset", mcSummary);
    expect(ins.curated).toBe(false);
    expect(ins.verdict).toContain("Chưa có nhận định thủ công");
    expect(ins.evidence.length).toBeGreaterThan(0);
    expect(ins.causes).toEqual([]);
    expect(ins.actions).toEqual([]);
  });
});
