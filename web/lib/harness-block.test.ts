/** Contract tests for the harness block (web/lib/harness-block.ts).
 *
 * Offline và thuần hàm: block giả lập đúng shape do
 * `code_benchmark/build_dashboard_harness.py` ghi. Mục tiêu là bắt được
 * khối cũ/nửa vời trước khi nó hiển thị số 0 lên trang.
 * Run: `cd web && bun test lib/harness-block.test.ts`
 */
import { describe, expect, test } from "bun:test";
import { parseHarnessBlock, readHarnessBlock, rowsForDataset } from "./harness-block.ts";

const row = (over: Record<string, unknown> = {}) => ({
  role: "harness",
  arm: "H5",
  arm_slug: "ompH5clean_Qwen3_5-9B-28K",
  label: "omp sạch",
  card: "MC-22",
  dataset: "reading400",
  dataset_label: "reading-400 (EM)",
  metric: "EM",
  n: 400,
  arm_a: 79.75,
  arm_b: 57.5,
  delta: -22.25,
  ci95_low: -26.75,
  ci95_high: -17.75,
  mcnemar_p: "1.5e-20",
  both: 222,
  a_only: 97,
  b_only: 8,
  neither: 73,
  char_f1: 74.92,
  blanks: 0,
  ...over,
});

// Shape verbatim from speed_summary_*.csv — every number is a STRING.
const speedPair = (over: Record<string, unknown> = {}) => [
  {
    arm: "H5",
    label: "omp sạch",
    side: "direct",
    dataset: "legal_mc",
    n: "24",
    workers: "6",
    wall_p50_s: "0.70",
    wall_mean_s: "0.71",
    items_per_min: "505.6",
    prompt_tok_per_item: "226",
    completion_tok_per_item: "2",
    total_tok_per_item: "228",
    overhead_s_per_item: "0.00",
    note: "max_tokens=4",
    ...over,
  },
  {
    arm: "H5",
    label: "omp sạch",
    side: "omp",
    dataset: "legal_mc",
    n: "24",
    workers: "6",
    wall_p50_s: "2.62",
    wall_mean_s: "2.63",
    items_per_min: "136.9",
    prompt_tok_per_item: "5363",
    completion_tok_per_item: "26",
    total_tok_per_item: "5389",
    overhead_s_per_item: "1.81",
    note: "system prompt + tool schemas included in prompt_tokens",
    ...over,
  },
];

const secondary = (over: Record<string, unknown> = {}) => ({
  arm: "H2",
  label: "omp (rò cấu hình)",
  dataset: "reading400",
  dataset_label: "reading-400 (EM)",
  n: 400,
  em_verbatim: 27.0,
  em_stripped: 49.25,
  wrapper_cost: 22.25,
  ...over,
});

const repeat = (over: Record<string, unknown> = {}) => ({
  cell: "ompH5clean",
  repeat: 2,
  arm: "ompH5clean·r2",
  label: "**omp sạch** — lặp 2",
  card: "MC-27",
  dataset: "legal_mc",
  dataset_label: "legal-MC (accuracy)",
  n: 146,
  arm_a: 87.67,
  arm_b: 70.55,
  delta: -17.12,
  ci95_low: -24.66,
  ci95_high: -10.27,
  mcnemar_p: "1.093e-05",
  cell_n: 3,
  cell_mean: 70.78,
  cell_spread: 3.42,
  cell_min: 69.18,
  cell_max: 72.6,
  ...over,
});

const block = (ladder: unknown[] = [row(), row({ role: "baseline", arm: "A", delta: 0, ci95_low: 0, ci95_high: 0, mcnemar_p: "" })]) => ({
  benchmark_name: "Harness arm",
  date: "2026-09-26",
  model_id: "Qwen3.5-9B-28K",
  endpoint: "https://llmapi.iec-uit.com/v1",
  harness: "omp v18.2.7",
  condition: "prompt byte-identical",
  measurement_card: "MC-15…MC-23",
  measurement_card_hash: "hash",
  scorer: "frozen",
  ladder,
  cost: [],
  speed: speedPair(),
  secondary_metrics: [secondary()],
  repeatability: [
    repeat({ repeat: 1, cell_n: 3, arm_b: 69.18, delta: -18.49, ci95_low: -26.33, ci95_high: -10.65, cell_min: 69.18, cell_max: 72.6 }),
    repeat(),
    repeat({ repeat: 3, cell_n: 3, arm_b: 72.6, delta: -15.07, ci95_low: -21.92, ci95_high: -8.22, cell_min: 69.18, cell_max: 72.6 }),
  ],
  totals: { items_harness: 2956, failures: 0, tool_use_items: 4, net_attempt_items: 0, path_escape_items: 3 },
  leak: { what: "w", evidence: "e", fix: "f", guard: "g" },
  caveats: ["c1"],
  sources: { report: "r", docs: "d" },
});

describe("parseHarnessBlock", () => {
  test("accepts a well-formed block", () => {
    const b = parseHarnessBlock(block());
    expect(b.ladder).toHaveLength(2);
    expect(b.totals.items_harness).toBe(2956);
  });

  test("rejects a block with no ladder", () => {
    expect(() => parseHarnessBlock(block([]))).toThrow(/thiếu .ladder/);
  });

  test("rejects a block with no caveats (the honesty section must not be optional)", () => {
    const b = { ...block(), caveats: [] };
    expect(() => parseHarnessBlock(b)).toThrow(/thiếu .caveats/);
  });

  test("rejects an inverted CI instead of rendering it", () => {
    const b = block([row({ ci95_low: 5, ci95_high: -5 })]);
    expect(() => parseHarnessBlock(b)).toThrow(/CI đảo ngược/);
  });

  test("rejects a row with n <= 0", () => {
    expect(() => parseHarnessBlock(block([row({ n: 0 })]))).toThrow(/không hợp lệ/);
  });

  test("requires a baseline row so the table can be compared", () => {
    expect(() => parseHarnessBlock(block([row()]))).toThrow(/không có dòng baseline/);
  });

  test("non-objects are rejected", () => {
    expect(() => parseHarnessBlock(null)).toThrow();
    expect(() => parseHarnessBlock("nope")).toThrow();
  });

  test("requires the speed table (the cost probe the block promises)", () => {
    expect(() => parseHarnessBlock({ ...block(), speed: [] })).toThrow(/thiếu .speed/);
  });
});

describe("speed rows (cost probe)", () => {
  test("accepts a real direct+omp pair", () => {
    expect(parseHarnessBlock(block()).speed).toHaveLength(2);
  });

  test("rejects a row without an explicit side (the arm-identity bug)", () => {
    // the probe's own column is the pair id A_direct/B_omp_h2, NOT the arm
    const [d, o] = speedPair();
    const { side: _d, ...noDirectSide } = d as Record<string, unknown>;
    const { side: _o, ...noOmpSide } = o as Record<string, unknown>;
    expect(() => parseHarnessBlock({ ...block(), speed: [noDirectSide, noOmpSide] })).toThrow(
      /thiếu side hợp lệ/,
    );
  });

  test("rejects n / workers that are not positive integers", () => {
    const [d, o] = speedPair();
    expect(() => parseHarnessBlock({ ...block(), speed: [{ ...d, n: "0" }, o] })).toThrow(
      /n không phải số nguyên dương/,
    );
    expect(() => parseHarnessBlock({ ...block(), speed: [d, { ...o, workers: "0" }] })).toThrow(
      /workers không phải số nguyên dương/,
    );
    expect(() => parseHarnessBlock({ ...block(), speed: [{ ...d, n: "24.5" }, o] })).toThrow(
      /n không phải số nguyên dương/,
    );
  });

  test("rejects a non-zero overhead on the direct arm (it is the pair's own zero)", () => {
    const [d, o] = speedPair();
    expect(() => parseHarnessBlock({ ...block(), speed: [{ ...d, overhead_s_per_item: "1.20" }, o] })).toThrow(
      /overhead của arm direct phải bằng 0/,
    );
  });

  test("rejects an omp row with no direct twin to compare against", () => {
    const [d, o] = speedPair();
    expect(() => parseHarnessBlock({ ...block(), speed: [d, { ...o, n: "48" }] })).toThrow(
      /không có dòng direct cùng n=48/,
    );
    expect(() => parseHarnessBlock({ ...block(), speed: [d, { ...o, arm: "H8" }] })).toThrow(
      /không có dòng direct/,
    );
  });

  test("rejects a row missing the arm/dataset/note identity", () => {
    const [d, o] = speedPair();
    expect(() => parseHarnessBlock({ ...block(), speed: [{ ...d, note: "" }, o] })).toThrow(/không hợp lệ/);
  });
});

describe("server score (accuracy thật, KHÁC validity)", () => {
  const withServer = (over: Record<string, unknown> = {}) => ({
    ...block(),
    ladder: [row({ server_score: 30.8, server_correct: 308, server_total: 1000, ...over }),
             row({ role: "baseline", arm: "A", delta: 0, ci95_low: 0, ci95_high: 0, mcnemar_p: "",
                   server_score: 39.7, server_correct: 397, server_total: 1000 })],
  });

  test("accepts a coherent trio on both arms", () => {
    const b = parseHarnessBlock(withServer());
    expect(b.ladder[0].server_correct).toBe(308);
  });

  test("a row with NO server keys is fine (most datasets have no server score)", () => {
    expect(parseHarnessBlock(block()).ladder[0].server_score).toBeUndefined();
  });

  test("an explicit null reads as ABSENT, not as a score of 0", () => {
    const b = parseHarnessBlock(withServer({ server_score: null, server_correct: null, server_total: null }));
    expect(b.ladder[0].server_score ?? "absent").toBe("absent");
  });

  test("rejects a half-present trio", () => {
    expect(() => parseHarnessBlock({ ...block(), ladder: [row({ server_score: 30.8 })] })).toThrow(
      /phải có đủ cả ba/,
    );
  });

  test("rejects correct > total, score outside [0,100], and a score that is not 100·correct/total", () => {
    expect(() => parseHarnessBlock(withServer({ server_correct: 1001 }))).toThrow(/server_correct .* > server_total/);
    // score out of range while correct <= total, so the range check is what fires
    expect(() => parseHarnessBlock(withServer({ server_score: 140 }))).toThrow(/ngoài \[0,100\]/);
    expect(() => parseHarnessBlock(withServer({ server_score: 99.9 }))).toThrow(/≠ 100·correct\/total/);
    expect(() => parseHarnessBlock(withServer({ server_total: 0 }))).toThrow(/server_total phải > 0/);
  });
});

describe("repeatability (mức sàn nhiễu)", () => {
  test("accepts three repeats of one cell sharing the same summary", () => {
    const b = parseHarnessBlock(block());
    expect(b.repeatability).toHaveLength(3);
    expect(b.repeatability.every((r) => r.cell_spread === 3.42)).toBe(true);
  });

  test("a single run is allowed and is not given a spread", () => {
    const solo = [repeat({ repeat: 1, cell_n: undefined, cell_mean: undefined, cell_spread: undefined, cell_min: undefined, cell_max: undefined })];
    expect(parseHarnessBlock({ ...block(), repeatability: solo }).repeatability[0].cell_spread).toBeUndefined();
  });

  test("rejects a delta that is not arm_b − arm_a", () => {
    expect(() => parseHarnessBlock({ ...block(), repeatability: [repeat({ delta: -5 })] })).toThrow(
      /delta .* ≠ arm_b − arm_a/,
    );
  });

  test("rejects a delta outside its own CI", () => {
    // keep delta == arm_b − arm_a so the CI check is what fires
    expect(() =>
      parseHarnessBlock({ ...block(), repeatability: [repeat({ arm_b: 57.67, delta: -30 })] }),
    ).toThrow(/nằm NGOÀI CI/);
  });

  test("rejects an inverted CI", () => {
    expect(() => parseHarnessBlock({ ...block(), repeatability: [repeat({ ci95_low: 1, ci95_high: -1 })] })).toThrow(
      /CI đảo ngược/,
    );
  });

  test("rejects a cell_spread that is not cell_max − cell_min", () => {
    expect(() => parseHarnessBlock({ ...block(), repeatability: [repeat({ cell_spread: 9 })] })).toThrow(
      /cell_spread .* ≠ cell_max − cell_min/,
    );
  });

  test("rejects repeats of one cell carrying DIFFERENT summaries", () => {
    // each row internally coherent (spread == max − min) yet the two disagree
    const b = {
      ...block(),
      repeatability: [
        repeat({ cell_n: 2 }),
        repeat({ repeat: 3, cell_n: 2, cell_spread: 1.02, cell_mean: 70.0, cell_min: 70.0, cell_max: 71.02 }),
      ],
    };
    expect(() => parseHarnessBlock(b)).toThrow(/không cùng cell_mean\/cell_spread/);
  });

  test("rejects a cell_n that disagrees with the number of rows on disk", () => {
    expect(() => parseHarnessBlock({ ...block(), repeatability: [repeat({ cell_n: 7 })] })).toThrow(
      /cell_n=7 khác số dòng thật/,
    );
  });

  test("rejects a cell with repeats but no spread (invites reading one run as the cell)", () => {
    const b = {
      ...block(),
      repeatability: [
        repeat({ cell_n: undefined, cell_mean: undefined, cell_spread: undefined, cell_min: undefined, cell_max: undefined }),
        repeat({ repeat: 3, cell_n: undefined, cell_mean: undefined, cell_spread: undefined, cell_min: undefined, cell_max: undefined }),
      ],
    };
    expect(() => parseHarnessBlock(b)).toThrow(/có 2 lặp nhưng thiếu cell_mean/);
  });

  test("rejects n <= 0, repeat < 1 and a non-array", () => {
    expect(() => parseHarnessBlock({ ...block(), repeatability: [repeat({ n: 0 })] })).toThrow(/n phải là số nguyên dương/);
    expect(() => parseHarnessBlock({ ...block(), repeatability: [repeat({ repeat: 0 })] })).toThrow(/repeat phải ≥ 1/);
    expect(() => parseHarnessBlock({ ...block(), repeatability: {} })).toThrow(/không phải mảng/);
  });

  test("rows of DIFFERENT n are never summarised together", () => {
    // 100-item run and 146-item run are separate experiments: each group must
    // carry its own summary, and a cross-n group would be a made-up number.
    const b = {
      ...block(),
      repeatability: [
        repeat({ n: 100, repeat: 1, cell_n: undefined, cell_mean: undefined, cell_spread: undefined, cell_min: undefined, cell_max: undefined }),
        repeat({ cell_n: 1 }),
      ],
    };
    expect(() => parseHarnessBlock(b)).not.toThrow();
  });
});

describe("secondary_metrics (metric phụ, không thay số chính)", () => {
  test("accepts a coherent row and a block that omits the key entirely", () => {
    expect(parseHarnessBlock(block()).secondary_metrics).toHaveLength(1);
    const without = { ...block() } as Record<string, unknown>;
    delete without.secondary_metrics;
    expect(parseHarnessBlock(without).secondary_metrics).toBeUndefined();
  });

  test("rejects a wrapper_cost that does not match em_stripped − em_verbatim", () => {
    const b = { ...block(), secondary_metrics: [secondary({ wrapper_cost: 5 })] };
    expect(() => parseHarnessBlock(b)).toThrow(/wrapper_cost/);
  });

  test("rejects stripping that LOWERS the score (bóc vỏ không thể làm điểm giảm)", () => {
    const b = { ...block(), secondary_metrics: [secondary({ em_stripped: 10, wrapper_cost: -17 })] };
    expect(() => parseHarnessBlock(b)).toThrow(/EM sau cắt vỏ/);
  });

  test("rejects a row with n <= 0 and a non-array", () => {
    expect(() => parseHarnessBlock({ ...block(), secondary_metrics: [secondary({ n: 0 })] })).toThrow(
      /không hợp lệ/,
    );
    expect(() => parseHarnessBlock({ ...block(), secondary_metrics: {} })).toThrow(/không phải mảng/);
  });

  test("a clean arm's zero wrapper cost is a legitimate, expected value", () => {
    const clean = secondary({ arm: "H5", em_verbatim: 57.5, em_stripped: 57.5, wrapper_cost: 0 });
    expect(parseHarnessBlock({ ...block(), secondary_metrics: [clean] }).secondary_metrics[0].wrapper_cost).toBe(0);
  });
});

describe("readHarnessBlock", () => {
  test("returns null when the blob has no harness key (older blob)", () => {
    expect(readHarnessBlock({ vmlu: {} })).toBeNull();
    expect(readHarnessBlock(null)).toBeNull();
  });

  test("validates when present", () => {
    expect(readHarnessBlock({ harness: block() })?.ladder).toHaveLength(2);
    expect(() => readHarnessBlock({ harness: { ladder: [] } })).toThrow();
  });
});

describe("rowsForDataset", () => {
  test("filters by dataset and keeps the baseline", () => {
    const b = parseHarnessBlock(
      block([row(), row({ role: "baseline", arm: "A", delta: 0, ci95_low: 0, ci95_high: 0, mcnemar_p: "" }), row({ dataset: "legal_mc" })]),
    );
    expect(rowsForDataset(b, "legal_mc")).toHaveLength(1);
    expect(rowsForDataset(b, "reading400")).toHaveLength(2);
    expect(rowsForDataset(b, "nope")).toHaveLength(0);
  });
});
