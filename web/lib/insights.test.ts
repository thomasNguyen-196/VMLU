/** Contract tests for the /results insight layer.
 *
 * Offline, thuần hàm: summary giả lập theo đúng shape `summaries` (giá trị CSV
 * dạng chuỗi như migrate_results_to_mongo ghi vào Mongo).
 * Run: `cd web && bun test lib/insights.test.ts`
 */
import { describe, expect, test } from "bun:test";
import { buildInsight, canonicalModelId, deriveEvidence, summaryFromBlob } from "./insights.ts";

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
  test("MC: tổng + nhóm + môn thấp + số môn dưới 50%", () => {
    const ev = deriveEvidence(mcSummary);
    expect(ev.join("\n")).toContain("Tổng: 30/40 = 75%");
    expect(ev.join("\n")).toContain("Nhóm thấp nhất: Other 60%");
    expect(ev.join("\n")).toContain("Môn thấp nhất: 37 Administrative Law 30% (n=10)");
    expect(ev.join("\n")).toContain("1/2 môn dưới 50%");
  });

  test("reading: tách nguồn + chênh EM→char-F1", () => {
    const ev = deriveEvidence(readingSummary);
    expect(ev.join("\n")).toContain("Tổng: EM 80.25% · char-F1 86.55 (321/400 khớp EM)");
    expect(ev.join("\n")).toContain("Chênh EM→char-F1: 6.30 điểm");
    expect(ev.join("\n")).toContain("drop: EM 63% · char-F1 74.49 (n=200)");
  });

  test("vbench: micro từ máy chủ + agentic + độ hợp lệ cú pháp", () => {
    const ev = deriveEvidence(vbenchSummary);
    expect(ev.join("\n")).toContain("Micro (máy chủ chấm): 556/1313 = 42.35%");
    expect(ev.join("\n")).toContain("Agentic: 39.7% (397/1000)");
    expect(ev.join("\n")).toContain("mc 125/125 hợp lệ");
  });

  test("summary rỗng/null không ném lỗi", () => {
    expect(deriveEvidence(null)).toEqual([]);
    const ev = deriveEvidence({ n: 10 });
    expect(ev).toHaveLength(1);
    expect(ev[0]).toContain("n=10");
  });
});

describe("buildInsight", () => {
  test("cặp đã có diễn giải: có giả thuyết, hướng kiểm chứng và giới hạn", () => {
    const ins = buildInsight("qwen3-5-9b-28k", "vmlu-mqa-all-gold", mcSummary);
    expect(ins.curated).toBe(true);
    expect(ins.causes.length).toBeGreaterThan(0);
    expect(ins.actions.length).toBeGreaterThan(0);
    expect(ins.caveat).toBeTruthy();
    expect(ins.evidence.length).toBeGreaterThan(0);
  });

  test("bộ dữ liệu có seed '*' (valid) vẫn curated cho mô hình lạ", () => {
    const ins = buildInsight("unknown-model", "vmlu-mqa-valid", mcSummary);
    expect(ins.curated).toBe(true);
  });

  test("cặp chưa có seed: fallback + vẫn giữ bằng chứng số", () => {
    const ins = buildInsight("unknown-model", "unknown-dataset", mcSummary);
    expect(ins.curated).toBe(false);
    expect(ins.verdict).toContain("Chưa có diễn giải chuyên biệt");
    expect(ins.evidence.length).toBeGreaterThan(0);
    expect(ins.causes).toEqual([]);
    expect(ins.actions).toEqual([]);
  });

  test("diễn giải không biến tương quan thành kết luận nhân quả", () => {
    const vmlu = buildInsight("qwen3-5-9b-28k", "vmlu-mqa-all-gold", mcSummary);
    expect(vmlu.verdict).toContain("chưa có đối chứng song ngữ");
    expect(vmlu.verdict).not.toContain("không phải tiếng Việt");

    const vbench = buildInsight("qwen3-5-9b-28k", "vbench-public-test", vbenchSummary);
    expect(vbench.verdict).toContain("14 câu được hỏi lại theo guided");
    expect(vbench.verdict).toContain("không đại diện cho một điều kiện minimal thuần");

    const reading = buildInsight("qwen3-8-27b-q4-k-m-gguf", "reading-400", readingSummary);
    expect(reading.verdict).toContain("không đủ để quy toàn bộ cho hạn chế suy luận");
    expect(reading.caveat).toContain("321 câu được Accept");

    const legal = buildInsight("qwen3-5-9b-28k", "legal-nli-150", mcSummary);
    expect(legal.verdict).toContain("phân loại khả năng hỗ trợ");
    expect(legal.verdict).toContain("không phải NLI ba nhãn đầy đủ");
  });

  test("65K legal-mc-146: seed mang kết quả position bias (MC-36), không thêm cause 'robustness'", () => {
    const ins = buildInsight("qwen3-5-9b-65k", "legal-mc-146", mcSummary);
    expect(ins.curated).toBe(true);
    expect(ins.verdict).toContain("89,04% (130/146)");
    expect(ins.verdict).toContain("Δ +0,00");
    expect(ins.verdict).toContain("126/146 câu giữ nguyên text");
    // đã kiểm tra robustness và không thấy hiệu ứng: nó không được là "cause"
    expect(ins.causes.map((c) => c.tag)).toEqual(["normative"]);
    expect(ins.caveat).toContain("không suy sang bộ khác");
  });
});

describe("canonicalModelId", () => {
  test("khớp rule seed_registries (Python)", () => {
    expect(canonicalModelId("Qwen3.5-9B-28K")).toBe("qwen3-5-9b-28k");
    expect(canonicalModelId("Qwen3.8-27B-Q4_K_M (GGUF)")).toBe("qwen3-8-27b-q4-k-m-gguf");
    expect(canonicalModelId("qwen38-nothink")).toBe("qwen38-nothink");
  });
});

describe("summaryFromBlob", () => {
  test("vmlu: overall + categories + subjects → accuracy_rows", () => {
    const s = summaryFromBlob("vmlu-mqa-all-gold", {
      overall: { n: 3, correct: 2, accuracy: 66.67 },
      categories: [{ name: "STEM", n: 2, correct: 2, accuracy: 100 }],
      subjects: [
        { name: "Administrative Law", full_name: "37 Luật hành chính", n: 10, correct: 3, accuracy: 30 },
        { name: "Elementary Science", full_name: "02 Khoa học tiểu học", n: 10, correct: 10, accuracy: 100 },
      ],
    });
    const ev = deriveEvidence(s);
    expect(ev.join("\n")).toContain("Tổng: 2/3 = 66.67%");
    expect(ev.join("\n")).toContain("37 Luật hành chính 30%");
  });

  test("reading: sources + ALL → reading_rows", () => {
    const s = summaryFromBlob("reading-400", {
      overall: { n: 400, em_count: 319, em: 79.75, char_f1: 86.49 },
      sources: [{ label: "Vi-SQuAD", n: 200, em_count: 193, em: 96.5, char_f1: 98.63 }],
    });
    const ev = deriveEvidence(s);
    expect(ev.join("\n")).toContain("Vi-SQuAD: EM 96.5% · char-F1 98.63 (n=200)");
    expect(ev.join("\n")).toContain("Tổng: EM 79.75% · char-F1 86.49 (319/400 khớp EM)");
  });

  test("vbench: domains → server_rows (micro tính lại)", () => {
    const s = summaryFromBlob("vbench-public-test", {
      total_items: 1313,
      domains: [
        { domain: "mathematics", track: "multiple-choice", score: 20, correct: 25, total: 125 },
        { domain: "agentic", track: "function-calling", score: 39.1, correct: 391, total: 1000 },
      ],
    });
    expect(deriveEvidence(s).join("\n")).toContain("Micro (máy chủ chấm): 416/1125 = 36.98%");
  });

  test("legal + bidlqa + vm14k + block lạ", () => {
    const legal = summaryFromBlob("legal-mc-146", { overall: { n: 146, correct: 128, accuracy: 87.67 } });
    expect(deriveEvidence(legal).join("\n")).toContain("Tổng: 128/146 = 87.67%");
    const bid = summaryFromBlob("bidlqa-val", { overall: { n: 482, em_count: 158, em: 32.78, char_f1: 74.16 } });
    expect(deriveEvidence(bid).join("\n")).toContain("Chênh EM→char-F1: 41.38 điểm");
    const vm14k = summaryFromBlob("vm14k-public-12488", { overall: { n: 12488, correct: 8091, accuracy: 64.79 } });
    expect(deriveEvidence(vm14k).join("\n")).toContain("Tổng: 8091/12488 = 64.79%");
    expect(summaryFromBlob("unknown-dataset", { overall: { n: 1 } })).toBeNull();
    expect(summaryFromBlob("vmlu-mqa-all-gold", null)).toBeNull();
  });
});
