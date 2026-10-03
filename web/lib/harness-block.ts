/** The harness block of `web/public/benchmark-data.json` (change harness-block).
 *
 * The harness study is a *frozen* artifact set — 9 arms of the same model
 * measured on the same items — with no per-item DB counterpart, so unlike
 * /benchmark it cannot be assembled from Mongo. It is read from the static blob
 * that `code_benchmark/build_dashboard_harness.py` patches, and validated here
 * so a stale or half-written block fails loudly instead of rendering zeros.
 *
 * Contract: the Python builder is the single source of truth (labels, card ids
 * and the leak/caveat prose live there). Nothing is recomputed in TS.
 */

export interface HarnessRow {
  /** "baseline" = the direct-prompt arm A (no paired stats), "harness" = an arm. */
  role: "baseline" | "harness";
  /** The model this row measures. A row is only meaningful inside one model. */
  model: string;
  arm: string;
  arm_slug: string;
  label: string;
  card: string | null;
  dataset: string;
  dataset_label: string;
  /** `agreement_with_arm_A` = no local gold (V-Bench MC), so the pairable
   *  number is "did the agent change the answer?", never accuracy. */
  metric: "accuracy" | "EM" | "valid_rate" | "agreement" | "agreement_with_arm_A";
  n: number;
  arm_a: number;
  arm_b: number;
  delta: number;
  ci95_low: number;
  ci95_high: number;
  mcnemar_p: string;
  both: number | string;
  a_only: number | string;
  b_only: number | string;
  neither: number | string;
  char_f1: number | null;
  /** Server-side score, when a `vbench_server_scores_*.csv` snapshot exists. It is
   *  a DIFFERENT measurement from `arm_b` (accuracy vs schema validity) and is
   *  never merged into it — the two differed by 3.4x on V-Bench (MC-28). */
  server_score?: number;
  server_correct?: number;
  server_total?: number;
  blanks: number;
}

export interface HarnessCostRow {
  arm: string;
  arm_slug: string;
  label: string;
  n: number;
  datasets: number;
  wall_s_per_item: number;
  turns_per_item: number;
  failures: number;
  tool_use_items: number;
  net_attempt_items: number;
  path_escape_items: number;
  reported_input_tokens: number;
  reported_cache_read: number;
  completion_tokens: number;
}

/** One row of the cost probe. `side` is which end of the pair the row measures
 *  ("direct" = arm A's own HTTP call, "omp" = the same item inside the agent);
 *  `arm` is the REAL arm identity from the builder's registry. Every number is
 *  a string because it is read verbatim from `speed_summary_*.csv` — mirroring
 *  the file is the point (see `overhead_s_per_item`, which is a signed delta). */
export interface HarnessSpeedRow {
  arm: string;
  label: string;
  side: "direct" | "omp";
  dataset: string;
  n: string;
  workers: string;
  wall_p50_s: string;
  wall_mean_s: string;
  items_per_min: string;
  prompt_tok_per_item: string;
  completion_tok_per_item: string;
  total_tok_per_item: string;
  overhead_s_per_item: string;
  note: string;
}

/** One stratum cut of a paired comparison (1.2): the same predicate as the
 *  ALL row, restricted to one stratum. Small-n groups keep their wide CIs —
 *  the interval speaks, hiding them would be editorializing. */
export interface HarnessBreakdownGroup {
  group: string;
  n: number;
  arm_a: number;
  arm_b: number;
  delta: number;
  ci95_low: number;
  ci95_high: number;
  mcnemar_p: string;
}

export interface HarnessBreakdown {
  arm: string;
  arm_slug: string;
  label: string;
  model: string;
  dataset: string;
  dataset_label: string;
  metric: string;
  groups: HarnessBreakdownGroup[];
}

/** Partial argument credit per agentic arm (1.3): required-arg fill rate and
 *  supplied-arg precision beside the 0/1 validity the headline uses. Both
 *  rates are micro-averaged with their denominators shown. */
export interface HarnessArgCredit {
  arm: string;
  arm_slug: string;
  label: string;
  model: string;
  n_items: number;
  n_attempted: number;
  n_required_slots: number;
  n_required_ok: number;
  required_fill_rate: number;
  n_supplied: number;
  n_supplied_ok: number;
  arg_precision: number;
  n_unparseable: number;
}

/** SECONDARY attribution metric: EM on the verbatim reply vs EM on the same
 *  reply with the harness's wrapper peeled off. Never replaces the headline EM. */
export interface HarnessSecondaryRow {
  arm: string;
  label: string;
  dataset: string;
  dataset_label: string;
  n: number;
  em_verbatim: number;
  em_stripped: number;
  wrapper_cost: number;
}

/** One measurement of one cell. Repeats of the same cell at the same n appear as
 *  several rows sharing `cell` — that repetition IS the noise floor, and the
 *  `cell_*` fields are attached identically to each of them. Never pool across
 *  `n`: a 100-item run and a 146-item run are different experiments. */
export interface HarnessRepeatRow {
  cell: string;
  repeat: number;
  arm: string;
  label: string;
  card: string | null;
  dataset: string;
  dataset_label: string;
  n: number;
  arm_a: number;
  arm_b: number;
  delta: number;
  ci95_low: number;
  ci95_high: number;
  mcnemar_p: string;
  cell_n?: number;
  cell_mean?: number;
  cell_spread?: number;
  cell_min?: number;
  cell_max?: number;
}

/** The interpretation layer. Every number in `body` is INTERPOLATED from the rows
 *  the builder already carries (see `insight()` in build_dashboard_harness.py), so
 *  a claim cannot go stale the way a hand-typed sentence would. Claims whose
 *  evidence rows are absent are omitted, never printed with a hole. */
export interface HarnessInsightClaim {
  id: string;
  title: string;
  body: string;
  evidence: { label: string; value: string }[];
}

/** One row of the direct comparison the study exists for: the same model and the
 *  same prompt with and without the agent in the path. `no_harness` is the direct
 *  API call of THE SAME MODEL; `with_harness` is that model's clean scaffold
 *  (H5 for Qwen, M6 for MiMo). One row per (model, dataset) — a row is only
 *  meaningful inside one model, because the arm holds the model fixed. Sorted by
 *  model then delta, so the worst case of each model is the first thing read. */
export interface HarnessComparisonRow {
  model: string;
  dataset: string;
  dataset_label: string;
  metric: string;
  n: number;
  no_harness: number;
  with_harness: number;
  delta: number;
  /** Số câu trống/unparseable mỗi phía (1.1) — chỉ có nghĩa với metric
   *  accuracy/EM. Optional để blob cũ vẫn đọc được; khi có phải là số
   *  nguyên ≥ 0. */
  a_blanks?: number;
  b_blanks?: number;
}

export interface HarnessInsight {
  verdict: string;
  claims: HarnessInsightClaim[];
  comparison: HarnessComparisonRow[];
}

export interface HarnessBlock {
  benchmark_name: string;
  date: string;
  model_id: string;
  endpoint: string;
  harness: string;
  condition: string;
  measurement_card: string;
  measurement_card_hash: string;
  scorer: string;
  ladder: HarnessRow[];
  cost: HarnessCostRow[];
  speed: HarnessSpeedRow[];
  secondary_metrics: HarnessSecondaryRow[];
  repeatability: HarnessRepeatRow[];
  /** Per-stratum paired cuts (1.2). Optional like secondary_metrics: an older
   *  block predates it, but when present every group must add up. */
  breakdown?: HarnessBreakdown[];
  /** Partial argument credit (1.3). Optional; when present the rates must
   *  match their fractions. */
  arg_credit?: HarnessArgCredit[];
  insight: HarnessInsight;
  totals: {
    items_harness: number;
    failures: number;
    tool_use_items: number;
    net_attempt_items: number;
    path_escape_items: number;
  };
  leak: { what: string; evidence: string; fix: string; guard: string };
  caveats: string[];
  sources: Record<string, string>;
}

export const HARNESS_BLOB_HINT =
  "chạy: .venv/bin/python code_benchmark/build_dashboard_harness.py (từ thư mục gốc repo)";

function fail(message: string): never {
  throw new Error(`${message} — ${HARNESS_BLOB_HINT}`);
}

/** Validate the block the builder wrote. Fails loud on a stale/partial file. */
export function parseHarnessBlock(raw: unknown): HarnessBlock {
  if (typeof raw !== "object" || raw === null) fail("benchmark-data.json không phải object");
  const b = raw as Partial<HarnessBlock>;
  if (!Array.isArray(b.ladder) || !b.ladder.length) fail("block .harness thiếu .ladder");
  if (!Array.isArray(b.caveats) || !b.caveats.length) fail("block .harness thiếu .caveats");
  if (!b.totals) fail("block .harness thiếu .totals");
  for (const row of b.ladder) {
    if (!row.model) {
      fail(`dòng .ladder thiếu .model: ${JSON.stringify(row).slice(0, 120)} — một dòng chỉ có nghĩa bên trong một model`);
    }
    if (!row.arm || !row.dataset || typeof row.n !== "number" || row.n <= 0) {
      fail(`dòng .ladder không hợp lệ: ${JSON.stringify(row).slice(0, 120)}`);
    }
    if (row.role === "harness" && row.ci95_low > row.ci95_high) {
      fail(`${row.arm}/${row.dataset}: CI đảo ngược (${row.ci95_low} > ${row.ci95_high})`);
    }
    // `!= null` (not `!== undefined`): a hand-edited blob may carry an explicit
    // null, which must read as ABSENT, not as a score of 0.
    const trio = [row.server_score, row.server_correct, row.server_total];
    if (trio.some((v) => v != null)) {
      if (trio.some((v) => v == null)) {
        fail(`${row.arm}/${row.dataset}: server_score/correct/total phải có đủ cả ba`);
      }
      if (row.server_total! <= 0) fail(`${row.arm}/${row.dataset}: server_total phải > 0`);
      if (row.server_correct! > row.server_total!) {
        fail(`${row.arm}/${row.dataset}: server_correct (${row.server_correct}) > server_total (${row.server_total})`);
      }
      if (row.server_score! < 0 || row.server_score! > 100) {
        fail(`${row.arm}/${row.dataset}: server_score ${row.server_score} ngoài [0,100]`);
      }
      if (Math.abs(row.server_score! - (100 * row.server_correct!) / row.server_total!) > 0.02) {
        fail(`${row.arm}/${row.dataset}: server_score ${row.server_score} ≠ 100·correct/total`);
      }
    }
  }
  if (!b.ladder.some((r) => r.role === "baseline")) {
    fail("block .harness không có dòng baseline (arm A) — không so sánh được");
  }
  if (!Array.isArray(b.speed) || !b.speed.length) fail("block .harness thiếu .speed");
  for (const r of b.speed) {
    // `side` is load-bearing: the probe's own column used to be the pair id
    // (`A_direct`/`B_omp_h2`), so every arm rendered as H2 until the builder
    // projected it. A row without an explicit side is that bug again.
    if (r.side !== "direct" && r.side !== "omp") {
      fail(`dòng .speed thiếu side hợp lệ (direct|omp): ${JSON.stringify(r).slice(0, 120)}`);
    }
    if (!r.arm || !r.dataset || !r.note) {
      fail(`dòng .speed không hợp lệ: ${JSON.stringify(r).slice(0, 120)}`);
    }
    if (!/^\d+$/.test(r.n) || Number(r.n) <= 0) fail(`${r.arm}/${r.dataset}: n không phải số nguyên dương (${r.n})`);
    if (!/^\d+$/.test(r.workers) || Number(r.workers) <= 0) {
      fail(`${r.arm}/${r.dataset}: workers không phải số nguyên dương (${r.workers})`);
    }
    if (r.side === "direct" && Number(r.overhead_s_per_item) !== 0) {
      fail(`${r.arm}/${r.dataset}: overhead của arm direct phải bằng 0 (nó là gốc của cặp) — ${r.overhead_s_per_item}`);
    }
  }
  // A pair is the whole point of the probe: every omp row needs its direct twin.
  for (const r of b.speed.filter((s) => s.side === "omp")) {
    const twin = b.speed.find(
      (o) => o.side === "direct" && o.arm === r.arm && o.dataset === r.dataset && o.n === r.n,
    );
    if (!twin) fail(`${r.arm}/${r.dataset}: dòng omp không có dòng direct cùng n=${r.n} để so`);
  }
  // `secondary_metrics` is OPTIONAL (an older block may predate it) but when
  // present it must be arithmetically coherent — a mismatch means the file was
  // hand-edited, which is exactly what the ladder exists to prevent.
  if (b.secondary_metrics !== undefined) {
    if (!Array.isArray(b.secondary_metrics)) fail("block .harness .secondary_metrics không phải mảng");
    for (const m of b.secondary_metrics) {
      if (!m.arm || !m.dataset || typeof m.n !== "number" || m.n <= 0) {
        fail(`dòng .secondary_metrics không hợp lệ: ${JSON.stringify(m).slice(0, 120)}`);
      }
      const gap = Math.abs(m.wrapper_cost - (m.em_stripped - m.em_verbatim));
      if (gap > 0.02) {
        fail(`${m.arm}/${m.dataset}: wrapper_cost (${m.wrapper_cost}) ≠ em_stripped − em_verbatim (${gap.toFixed(2)})`);
      }
      if (m.em_stripped < m.em_verbatim) {
        fail(`${m.arm}/${m.dataset}: EM sau cắt vỏ (${m.em_stripped}) < EM nguyên văn (${m.em_verbatim}) — bóc vỏ không thể làm điểm giảm`);
      }
    }
  }
  // `breakdown` is OPTIONAL (an older block may predate it) but when present
  // every group must be arithmetically coherent with its headline row.
  if (b.breakdown !== undefined) {
    if (!Array.isArray(b.breakdown)) fail("block .harness .breakdown không phải mảng");
    for (const d of b.breakdown) {
      if (!d.arm || !d.dataset || !Array.isArray(d.groups) || !d.groups.length) {
        fail(`dòng .breakdown không hợp lệ: ${JSON.stringify(d).slice(0, 120)}`);
      }
      for (const g of d.groups) {
        if (!g.group || !Number.isInteger(g.n) || g.n <= 0) {
          fail(`${d.arm}/${d.dataset}: nhóm không hợp lệ (${JSON.stringify(g).slice(0, 80)})`);
        }
        if (Math.abs(g.delta - (g.arm_b - g.arm_a)) > 0.02) {
          fail(`${d.arm}/${d.dataset}/${g.group}: delta (${g.delta}) ≠ arm_b − arm_a`);
        }
        if (g.ci95_low > g.ci95_high) {
          fail(`${d.arm}/${d.dataset}/${g.group}: CI đảo ngược (${g.ci95_low} > ${g.ci95_high})`);
        }
      }
    }
  }
  // `arg_credit` is OPTIONAL but when present the two rates must match their
  // fractions, and attempted + unparseable must equal n_items.
  if (b.arg_credit !== undefined) {
    if (!Array.isArray(b.arg_credit)) fail("block .harness .arg_credit không phải mảng");
    for (const a of b.arg_credit) {
      if (!a.arm || !Number.isInteger(a.n_items) || a.n_items <= 0) {
        fail(`dòng .arg_credit không hợp lệ: ${JSON.stringify(a).slice(0, 120)}`);
      }
      if (a.n_attempted + a.n_unparseable !== a.n_items) {
        fail(`${a.arm}: attempted (${a.n_attempted}) + unparseable (${a.n_unparseable}) ≠ n_items (${a.n_items})`);
      }
      if (a.n_required_slots > 0 && Math.abs(a.required_fill_rate - (100 * a.n_required_ok) / a.n_required_slots) > 0.02) {
        fail(`${a.arm}: required_fill_rate (${a.required_fill_rate}) ≠ 100·ok/slots`);
      }
      if (a.n_supplied > 0 && Math.abs(a.arg_precision - (100 * a.n_supplied_ok) / a.n_supplied) > 0.02) {
        fail(`${a.arm}: arg_precision (${a.arg_precision}) ≠ 100·ok/supplied`);
      }
    }
  }
  // The insight layer is the page's actual answer, so an empty one is a broken
  // page, not a cosmetic gap.
  if (!b.insight || !Array.isArray(b.insight.claims) || !b.insight.claims.length) {
    fail("block .harness thiếu .insight.claims — trang không có phần nhận xét");
  }
  if (!b.insight.verdict) fail("block .harness .insight.verdict rỗng");
  const seenIds = new Set<string>();
  for (const c of b.insight.claims) {
    if (!c.id || !c.title || !c.body) fail(`claim thiếu id/title/body: ${JSON.stringify(c).slice(0, 100)}`);
    if (seenIds.has(c.id)) fail(`claim id trùng: ${c.id}`);
    seenIds.add(c.id);
    if (!Array.isArray(c.evidence) || !c.evidence.length) {
      fail(`claim ${c.id} không có evidence — một claim không kèm số thể chỉ là ý kiến`);
    }
    for (const e of c.evidence) {
      if (!e.label || !e.value) fail(`claim ${c.id}: evidence thiếu label/value`);
    }
  }
  // The with/without-harness table is the study's reason for existing.
  if (!Array.isArray(b.insight.comparison) || !b.insight.comparison.length) {
    fail("block .harness .insight.comparison rỗng — đây chính là phép so sánh cốt lõi");
  }
  for (const c of b.insight.comparison) {
    if (!c.model) fail(`dòng .comparison thiếu .model: ${JSON.stringify(c).slice(0, 100)} — một dòng so chỉ có nghĩa bên trong một model`);
    if (!c.dataset || !c.dataset_label || !c.metric) fail(`dòng .comparison thiếu nhãn: ${JSON.stringify(c).slice(0, 100)}`);
    if (!Number.isInteger(c.n) || c.n <= 0) fail(`${c.dataset}: n phải là số nguyên dương (${c.n})`);
    for (const k of ["no_harness", "with_harness"] as const) {
      if (c[k] < 0 || c[k] > 100) fail(`${c.dataset}: ${k} = ${c[k]} ngoài [0,100]`);
    }
    if (Math.abs(c.delta - (c.with_harness - c.no_harness)) > 0.02) {
      fail(`${c.dataset}: delta (${c.delta}) ≠ with_harness − no_harness`);
    }
    for (const k of ["a_blanks", "b_blanks"] as const) {
      const v = c[k];
      if (v !== undefined && (!Number.isInteger(v) || v < 0)) {
        fail(`${c.dataset}: ${k} = ${v} phải là số nguyên ≥ 0`);
      }
    }
  }
  // `repeatability` is required once present in the schema: a table that omits
  // the noise floor invites reading one run per cell as a measurement.
  if (b.repeatability !== undefined) {
    if (!Array.isArray(b.repeatability)) fail("block .harness .repeatability không phải mảng");
    validateRepeatability(b.repeatability);
  }
  return b as HarnessBlock;
}

/** Validate the repeatability rows: the per-cell spread is what decides whether
 *  a factorial contrast is a result or noise, so its arithmetic is checked. */
function validateRepeatability(rows: HarnessRepeatRow[]): void {
  const byCell = new Map<string, HarnessRepeatRow[]>();
  for (const r of rows) {
    if (!r.cell || !r.dataset || r.dataset_label === undefined) {
      fail(`dòng .repeatability không hợp lệ: ${JSON.stringify(r).slice(0, 120)}`);
    }
    if (!Number.isInteger(r.n) || r.n <= 0) fail(`${r.cell}: n phải là số nguyên dương (${r.n})`);
    if (!Number.isInteger(r.repeat) || r.repeat < 1) {
      fail(`${r.cell}: repeat phải ≥ 1 (got ${r.repeat})`);
    }
    if (Math.abs(r.delta - (r.arm_b - r.arm_a)) > 0.02) {
      fail(`${r.cell}/r${r.repeat}/n=${r.n}: delta (${r.delta}) ≠ arm_b − arm_a (${(r.arm_b - r.arm_a).toFixed(2)})`);
    }
    if (r.ci95_low > r.ci95_high) {
      fail(`${r.cell}/r${r.repeat}: CI đảo ngược (${r.ci95_low} > ${r.ci95_high})`);
    }
    if (r.delta < r.ci95_low - 0.02 || r.delta > r.ci95_high + 0.02) {
      fail(`${r.cell}/r${r.repeat}: delta ${r.delta} nằm NGOÀI CI ${r.ci95_low}..${r.ci95_high}`);
    }
    if (r.cell_spread !== undefined) {
      if (r.cell_min === undefined || r.cell_max === undefined) {
        fail(`${r.cell}: có cell_spread nhưng thiếu cell_min/cell_max`);
      }
      if (Math.abs(r.cell_spread - (r.cell_max! - r.cell_min!)) > 0.02) {
        fail(`${r.cell}: cell_spread (${r.cell_spread}) ≠ cell_max − cell_min`);
      }
      if (r.cell_spread < 0) fail(`${r.cell}: cell_spread âm (${r.cell_spread})`);
      const members = rows.filter((o) => o.cell === r.cell && o.n === r.n);
      if (members.length !== r.cell_n) {
        fail(`${r.cell}/n=${r.n}: cell_n=${r.cell_n} khác số dòng thật (${members.length})`);
      }
      if (members.some((o) => o.cell_spread !== r.cell_spread || o.cell_mean !== r.cell_mean)) {
        fail(`${r.cell}/n=${r.n}: các lặp không cùng cell_mean/cell_spread — số phải dán nhãn nhất quán`);
      }
    }
    const key = `${r.cell}|${r.dataset}|${r.n}`;
    if (!byCell.has(key)) byCell.set(key, []);
    byCell.get(key)!.push(r);
  }
  // A cell with repeats MUST be summarised, otherwise the table invites reading a
  // single run as if it were the cell's value.
  for (const [key, members] of byCell) {
    if (members.length > 1 && members.some((m) => m.cell_spread === undefined)) {
      fail(`${key}: có ${members.length} lặp nhưng thiếu cell_mean/cell_spread`);
    }
  }
}

/** Read + validate the harness block out of the benchmark blob. */
export function readHarnessBlock(blob: unknown): HarnessBlock | null {
  if (typeof blob !== "object" || blob === null) return null;
  const h = (blob as { harness?: unknown }).harness;
  if (h === undefined || h === null) return null;
  return parseHarnessBlock(h);
}

/** Ladder rows for one dataset, harness arms first then the baseline. */
export function rowsForDataset(block: HarnessBlock, dataset: string): HarnessRow[] {
  return block.ladder.filter((r) => r.dataset === dataset);
}
