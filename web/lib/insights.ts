/** Insight layer for /results — mỗi cặp (model × dataset) một nhận định chẩn đoán
 *  + hướng hành động, kèm bằng chứng số rút tự động từ summary của run.
 *
 * Hai phần tách bạch:
 *  - `SEEDS`  — nhận định thủ công (chủ quan, có căn cứ số) viết theo taxonomy của
 *               đề cương KLTN: thiếu tri thức tham số vs quy chuẩn, hạn chế suy luận,
 *               ảo giác quy chuẩn; hành động bám các hướng được phép (grounding/RAG,
 *               ngân sách suy luận, định tuyến, chuẩn hoá định dạng, hiệu chỉnh) —
 *               KHÔNG đề xuất fine-tune (ngoài phạm vi đề cương).
 *  - `deriveEvidence` — số liệu lấy từ `summaries` lúc render (nguồn sự thật).
 *
 * Lưu ý: vài con số neo trong `verdict` là số tại thời điểm viết (2026-09-21, các
 * card MC-1…MC-14b); khi lệch với bảng "Bằng chứng số" thì tin bảng.
 */

export type InsightCause =
  | "parametric"
  | "normative"
  | "reasoning"
  | "format"
  | "calibration"
  | "robustness";

export const CAUSE_LABEL: Record<InsightCause, string> = {
  parametric: "Thiếu tri thức tham số",
  normative: "Thiếu tri thức quy chuẩn",
  reasoning: "Hạn chế suy luận",
  format: "Định dạng / ngân sách token",
  calibration: "Thiên lệch đáp án",
  robustness: "Nhạy với cách hỏi / phân bố",
};

export interface InsightSeed {
  /** Chẩn đoán 1–2 câu, có số neo. */
  verdict: string;
  /** Nhóm nguyên nhân khả nghi (taxonomy đề cương). */
  causes: InsightCause[];
  /** Hướng hành động + phương pháp cải thiện (không fine-tune). */
  actions: string[];
  /** Điều KHÔNG được suy diễn từ run này. */
  caveat?: string;
}

export interface Insight {
  verdict: string;
  evidence: string[];
  causes: Array<{ tag: InsightCause; label: string }>;
  actions: string[];
  caveat?: string;
  /** true = có nhận định thủ công; false = chỉ có bằng chứng tự động. */
  curated: boolean;
}

const FALLBACK_VERDICT =
  "Chưa có nhận định thủ công cho cặp model × dataset này — bảng dưới là bằng chứng số rút tự động từ summary của run.";

// ── Nhận định thủ công (model × dataset) ────────────────────────────────
// dataset_id theo registry (code_benchmark/seed_registries.py); "*" = mọi model.
const SEEDS: Record<string, Record<string, InsightSeed>> = {
  "vmlu-mqa-all-gold": {
    "qwen3-5-9b-28k": {
      verdict:
        "73,35% (768/1.047) nhưng phân hoá mạnh theo loại tri thức: STEM 79% còn nhóm quy chuẩn — Luật hành chính, Thuế, Nghiệp vụ công chức — chỉ 30–44%. Nút thắt là loại tri thức (quy chuẩn/bản địa), không phải tiếng Việt.",
      causes: ["normative", "parametric"],
      actions: [
        "Lấy nhóm môn dưới 50% làm tập hiệu chuẩn để chọn ngưỡng định tuyến RAG (hướng C3 của đề cương).",
        "Thử grounding cho câu quy chuẩn (luật, thuế, nghiệp vụ) và đo lại có kiểm soát; giữ closed-book làm baseline C1.",
        "Báo cáo theo môn kèm n của môn — không lấy 10–20 câu/môn làm đại diện cả mảng.",
      ],
      caveat: "1.047 câu dev+valid, không phải leaderboard; mỗi môn chỉ 10–20 câu.",
    },
    "qwen3-8-27b-q4-k-m-gguf": {
      verdict:
        "73,35% (768/1.047) — cùng profile trũng như mọi model: Luật hành chính 30%, Sư phạm mầm non 30%, Thuế 33%, Văn THPT 40%. So với Qwen3.5-9B: 54/58 môn trùng khớp tuyệt đối (gấp ~3 tham số không tạo khác biệt) — bằng chứng “capacity không phải nút thắt”.",
      causes: ["normative", "parametric"],
      actions: [
        "Dùng làm lập luận chuyển ngân sách từ tăng tham số sang grounding/định tuyến trong giai đoạn C.",
        "Kiểm chứng chéo trên bộ khác dạng (V-Bench, VM14K) trước khi kết luận về khoảng trống.",
      ],
      caveat: "Model đã rời endpoint 12/09 — không tái lập được (MC-4).",
    },
  },
  "vmlu-mqa-valid": {
    "*": {
      verdict:
        "744 câu valid có gold local — subset cùng phân bố với all_gold, dùng kiểm tra độ ổn định của điểm tổng (Qwen3.5: 540/744 = 72,58%).",
      causes: ["normative"],
      actions: [
        "Chỉ dùng để đối chiếu ổn định giữa các lần chạy; mọi kết luận theo môn lấy từ all_gold.",
      ],
      caveat: "Không so ngang với điểm leaderboard (test withheld).",
    },
  },
  "vmlu-mqa-dev": {
    "*": {
      verdict:
        "303 câu dev có gold local — subset nhỏ nhất, dùng làm smoke/probe điều kiện đo (Qwen3.5: 229/303 = 75,58%).",
      causes: ["robustness"],
      actions: [
        "Giữ vai trò probe: chạy trước để kiểm tra endpoint/prompt, không dùng để kết luận năng lực.",
      ],
      caveat: "n nhỏ theo từng môn — không bẻ nhỏ thêm.",
    },
  },
  "vmlu-mqa-test": {
    "qwen3-5-9b-28k": {
      verdict:
        "Leaderboard 67,87% (STEM 65,65 · SocSci 74,97 · Humanity 68,61 · Other 63,67) — thấp hơn dev+valid 73,35% khoảng 5,5 điểm; không có gold local nên chỉ đọc được cấu trúc điểm.",
      causes: ["robustness", "normative"],
      actions: [
        "Dùng khoảng cách ~5,5 điểm như ước lượng độ khó phân bố test; không suy theo môn vì không có gold.",
        "Muốn chẩn đoán theo môn trên test: cần BTC mở gold, hoặc thay bằng bộ gold local cùng miền.",
      ],
      caveat: "Điểm chỉ có sau submit; submission 9.833 dòng id khớp 1:1, 0 blank (MC-7).",
    },
  },
  "vbench-public-test": {
    "qwen3-5-9b-28k": {
      verdict:
        "Macro 45,22 · micro 45,61% (2.345/5.141). Tách track: MC 47,04% vs agentic 39,70%; cú pháp gọi hàm 100% valid nhưng chỉ 391/1.000 khớp tham chiếu → nút thắt nằm ở ngữ nghĩa, không ở format.",
      causes: ["reasoning", "robustness"],
      actions: [
        "Hướng chính: kiểm chứng tham số trước khi gọi hàm (đối chiếu ngữ cảnh/grounding) — không chỉ đúng schema.",
        "Giữ điều kiện minimal khi công bố; muốn thử detailed/guided thì phải là card riêng (đổi cách hỏi làm 42,2% câu agentic đổi đáp án).",
        "Ghi nhãn 14 câu guided là điều kiện thứ 3 khi báo cáo, không trộn vào minimal.",
      ],
      caveat: "Điểm server-side (vbench.ai), không recompute local; valid ≠ correct.",
    },
    "qwen3-8-27b-q4-k-m-gguf": {
      verdict:
        "Macro 44,97 · micro 45,46% — cùng cấu trúc lỗi như Qwen3.5-9B: toán 19,2 · logic 24,0 · lý 29,9; MC 47,0% vs agentic 39,1%. Từng miền lệch ≤2,1 điểm so với 9B dù lớn gấp 3 lần; đổi prompt minimal→detailed làm 42,2% câu agentic đổi đáp án.",
      causes: ["robustness", "reasoning"],
      actions: [
        "Đọc như bằng chứng “prompt nhạy”: mọi so sánh phải khoá một điều kiện hỏi duy nhất.",
        "Dùng ablation detailed làm cơ sở thiết kế C1/C2 (đo phần điểm thuê từ prompt).",
      ],
      caveat: "Model đã rời endpoint; số là snapshot MC-2/MC-2b.",
    },
  },
  "reading-400": {
    "qwen3-5-9b-28k": {
      verdict:
        "EM 79,75% · char-F1 86,49% — Vi-SQuAD gần trần (EM 96,5%) nhưng Vi-DROP chỉ 63,0%; khoảng trống nằm ở suy luận số. Gần bằng Qwen3.8-27B (80,25/86,55) dù nhỏ hơn ~3 lần.",
      causes: ["reasoning"],
      actions: [
        "Vi-DROP là điểm nghẽn chung của cả hai model → ưu tiên can thiệp suy luận số học (ngân sách/CoT có kiểm soát) thay vì tăng tham số.",
        "Giữ cặp model làm đối chứng kích thước: cải tiến giúp cả hai = tín hiệu phương pháp; chỉ giúp model lớn = tín hiệu capacity.",
      ],
      caveat: "Run ghi nhận bổ sung tại MC-3b (chạy 20/09, cùng card hash MC-3); single-rater, chưa IAA.",
    },
    "qwen3-8-27b-q4-k-m-gguf": {
      verdict:
        "EM 80,25% · char-F1 86,55% nhưng tách nguồn lộ rõ: Vi-SQuAD EM 97,5% (gần trần trích xuất) vs Vi-DROP EM 63,0% (suy luận số). Khoảng trống nằm ở suy luận, không ở đọc hiểu.",
      causes: ["reasoning"],
      actions: [
        "DROP là điểm nghẽn: 74 câu bị bác tập trung vào cộng/trừ 2 thành phần (23), so sánh (22), đếm (21) → ưu tiên ngân sách suy luận/CoT có kiểm soát cho dạng số học.",
        "Giữ SQuAD làm đối chứng trần; không gộp điểm 2 nguồn thành một “năng lực chung”.",
        "Thử chuẩn hoá câu trả lời để tách “sai nội dung” khỏi “sai định dạng”.",
      ],
      caveat: "single-rater, chưa có IAA; EM/F1 trên gold hiệu đính 1 người.",
    },
  },
  "legal-mc-146": {
    "qwen3-5-9b-28k": {
      verdict:
        "87,67% (128/146), baseline A 62,33% → +25,3 điểm; 0 blank (parse 146/146) — mảng Luật phổ thông không yếu như nhóm luật trên VMLU (30–44%).",
      causes: ["normative"],
      actions: [
        "Giữ làm mốc closed-book cho mảng Luật; bước tiếp là thử RAG văn bản quy phạm (C3) và so có/không grounding.",
        "Luôn báo kèm baseline vì mất cân bằng A=91/146; không so ngang % VMLU (suite khác dạng).",
      ],
      caveat: "Public-test 146 câu, model 9B vượt giới hạn ≤4B của suite — ghi rõ khi công bố.",
    },
    "qwen38-nothink": {
      verdict:
        "82,88% (121/146) — thấp hơn Qwen3.5-9B 4,8 điểm; 21 câu blank (raw rỗng) dù đã nâng max_tokens lên 512 → vấn đề ngân sách/định dạng, không phải kiến thức.",
      causes: ["format", "reasoning"],
      actions: [
        "Trước khi dùng lại model này: probe budget lớn hơn hoặc tắt thinking ẩn, rồi mới kết luận năng lực luật.",
        "Không cộng điểm bù cho 21 blank — giữ là sai như đã ghi trong MC-6.",
      ],
      caveat: "Model 27B > 4B của suite; đã rời endpoint.",
    },
  },
  "legal-nli-150": {
    "qwen3-5-9b-28k": {
      verdict:
        "90,0% (135/150) vs baseline 50% → +40 điểm, nhưng lệch hệ thống: gold B đúng 100%, gold A chỉ 80% (model thiên “Không”).",
      causes: ["calibration", "reasoning"],
      actions: [
        "Hiệu chỉnh thiên lệch B trước khi dùng cho định tuyến/kiểm chứng: đo lại trên split khác hoặc đảo nhãn (counterfactual).",
        "Dùng NLI làm bước verification trong RAG (điều luật có trả lời được câu hỏi không) — hướng C3.",
      ],
      caveat: "Nhị phân 75/75; đoán bừa đã được 50%.",
    },
  },
  "bidlqa-val": {
    "qwen3-5-9b-28k": {
      verdict:
        "EM 32,78% · char-F1 74,16% — 105/482 câu (21,8%) có F1≥0,8 nhưng EM=0, chỉ 2 câu F1=0. Lỗi chủ yếu là định dạng/độ dài câu trả lời, không phải không tìm được thông tin.",
      causes: ["format", "reasoning"],
      actions: [
        "Thử ràng buộc trích span ngắn/nguyên văn (hoặc hạ token budget) — mục tiêu kéo 21,8% near-miss về EM.",
        "Báo EM là cận dưới (file-gold chưa review 2 người); dùng F1 cho so sánh.",
        "Đây là open-book: chạy thêm điều kiện closed-book nếu muốn tách “không biết” khỏi “không tìm thấy”.",
      ],
      caveat: "Gold file-native, không phải reviewed-gold.",
    },
  },
  "bidlqa-test": {
    "qwen3-5-9b-28k": {
      verdict:
        "EM 33,17% · char-F1 73,21% — lệch val chỉ 0,4 điểm EM → ổn định qua split unseen; 120/603 câu (19,9%) F1≥0,8 nhưng EM=0, cùng dạng lỗi định dạng như val.",
      causes: ["format", "reasoning"],
      actions: [
        "Dùng cặp val/test làm kiểm tra độ ổn định của mọi cải tiến định dạng (một split để chọn, một để xác nhận).",
      ],
      caveat: "Gold file-native; không so ngang model khác.",
    },
  },
  "vm14k-public-12488": {
    "qwen3-5-9b-28k": {
      verdict:
        "64,79% (8.091/12.488), parse 100%, 0 blank; vượt baseline A (31,35%) +33,4 điểm. Giảm đơn điệu theo độ khó: Easy 67,19 → Medium 64,01 → Challenging 61,78 → Hard 56,67; câu 4 lựa chọn 64,16% (câu Đúng/Sai 69,84% kéo điểm lên).",
      causes: ["parametric", "reasoning"],
      actions: [
        "Đối chiếu với V-Bench medicine của CÙNG model (38,57%, 189/490) chỉ theo “cùng/khác hướng”: VM14K 64,79 vs 38,57 là khác hướng mạnh — nghi do dạng câu/độ khó khác (nhiều câu Đúng/Sai, có câu 1 lựa chọn), KHÔNG được trừ hai phần trăm cho nhau.",
        "Báo cáo bẻ theo difficulty (đã có trong manifest) để tách “khó” khỏi “không biết”; giữ 4-lựa-chọn làm số chính, nêu riêng Đúng/Sai.",
        "Bản phát hành có caveat dữ liệu (1.377 dòng ≠ 4 lựa chọn, 34 dòng placeholder, ~6% trùng lặp) — muốn số sạch hơn thì pre-register bản lọc riêng (card mới), không tự ý sửa bộ raw.",
      ],
      caveat: "HF release lệch paper (12.488 vs 4k+10k+2k), không license; suite giới hạn ≤4B mà model 9B; đối chiếu V-Bench chỉ “cùng/khác hướng”.",
    },
  },
};

// ── Bằng chứng số (tự động từ summary) ──────────────────────────────────

type Row = Record<string, unknown>;

const asRows = (v: unknown): Row[] => (Array.isArray(v) ? (v as Row[]) : []);

const num = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : Number.NaN;
  return Number.isFinite(n) ? n : null;
};

const fmt = (v: unknown): string => (v == null ? "?" : String(v));

function mcEvidence(rows: Row[]): string[] {
  const out: string[] = [];
  const overall = rows.find((r) => r.level === "overall");
  if (overall) out.push(`Overall: ${fmt(overall.correct)}/${fmt(overall.n)} = ${fmt(overall.accuracy)}%`);

  const cats = rows.filter((r) => r.level === "category" && r.name !== "unknown");
  if (cats.length > 1) {
    const by = (dir: 1 | -1) =>
      [...cats].sort((a, b) => dir * ((num(a.accuracy) ?? 0) - (num(b.accuracy) ?? 0))).slice(0, 2);
    out.push(`Nhóm thấp nhất: ${by(1).map((r) => `${fmt(r.name)} ${fmt(r.accuracy)}%`).join(" · ")}`);
    out.push(`Nhóm cao nhất: ${by(-1).map((r) => `${fmt(r.name)} ${fmt(r.accuracy)}%`).join(" · ")}`);
  }

  const subs = rows.filter((r) => r.level === "subject" && r.name !== "unknown");
  if (subs.length > 1) {
    const big = subs.filter((r) => (num(r.n) ?? 0) >= 10);
    const pool = big.length ? big : subs;
    const sorted = [...pool].sort((a, b) => (num(a.accuracy) ?? 0) - (num(b.accuracy) ?? 0));
    out.push(
      `Môn trũng nhất: ${sorted.slice(0, 3).map((r) => `${fmt(r.name)} ${fmt(r.accuracy)}% (n=${fmt(r.n)})`).join(" · ")}`,
    );
    const below = subs.filter((r) => (num(r.accuracy) ?? 100) < 50).length;
    if (below) out.push(`${below}/${subs.length} môn dưới 50%`);
  }
  return out;
}

function readingEvidence(rows: Row[]): string[] {
  const out: string[] = [];
  const all = rows.find((r) => r.dataset === "ALL") ?? rows[0];
  if (all) {
    out.push(`Tổng: EM ${fmt(all.em)}% · char-F1 ${fmt(all.char_f1)} (${fmt(all.em_count)}/${fmt(all.n)} exact)`);
    const gap = (num(all.char_f1) ?? 0) - (num(all.em) ?? 0);
    if (gap > 0) out.push(`Gap EM→F1: ${gap.toFixed(2)} điểm`);
  }
  for (const r of rows.filter((x) => x.dataset !== "ALL")) {
    out.push(`${fmt(r.dataset)}: EM ${fmt(r.em)}% · F1 ${fmt(r.char_f1)} (n=${fmt(r.n)})`);
  }
  return out;
}

function vbenchEvidence(valid: Row[], server: Row[]): string[] {
  const out: string[] = [];
  const total = server.reduce((a, r) => a + (num(r.total) ?? 0), 0);
  const correct = server.reduce((a, r) => a + (num(r.correct) ?? 0), 0);
  if (total) out.push(`Micro (server rows): ${correct}/${total} = ${((100 * correct) / total).toFixed(2)}%`);

  const scored = server.filter((r) => num(r.score) != null);
  if (scored.length > 1) {
    const sorted = [...scored].sort((a, b) => (num(a.score) ?? 0) - (num(b.score) ?? 0));
    out.push(
      `Miền thấp nhất: ${sorted.slice(0, 2).map((r) => `${fmt(r.domain)} ${fmt(r.score)}%`).join(" · ")}`,
    );
    out.push(
      `Miền cao nhất: ${sorted.slice(-2).reverse().map((r) => `${fmt(r.domain)} ${fmt(r.score)}%`).join(" · ")}`,
    );
  }
  const agentic = server.find((r) => r.track !== "multiple-choice");
  if (agentic) out.push(`Agentic: ${fmt(agentic.score)}% (${fmt(agentic.correct)}/${fmt(agentic.total)})`);

  if (valid.length) {
    const byTrack = new Map<string, { n: number; valid: number }>();
    for (const r of valid) {
      const t = fmt(r.track);
      const cur = byTrack.get(t) ?? { n: 0, valid: 0 };
      cur.n += num(r.n) ?? 0;
      cur.valid += num(r.valid) ?? 0;
      byTrack.set(t, cur);
    }
    const parts = [...byTrack.entries()].map(
      ([t, v]) => `${t} ${v.valid}/${v.n} valid${v.n ? ` (${((100 * v.valid) / v.n).toFixed(1)}%)` : ""}`,
    );
    out.push(`Cú pháp: ${parts.join(" · ")}`);
  }
  return out;
}

export function deriveEvidence(summary: Record<string, unknown> | null): string[] {
  if (!summary) return [];
  const out: string[] = [];
  const acc = asRows(summary.accuracy_rows);
  if (acc.length) out.push(...mcEvidence(acc));
  const reading = asRows(summary.reading_rows);
  if (reading.length) out.push(...readingEvidence(reading));
  const server = asRows(summary.server_rows);
  if (server.length) out.push(...vbenchEvidence(asRows(summary.valid_rows), server));
  if (!out.length) out.push(`Run không có bảng số precomputed (n=${fmt(summary.n)}; gold local withheld hoặc summary chưa migrate) — điểm chỉ đọc được từ nguồn chấm ngoài.`);
  return out;
}

export function buildInsight(
  modelId: string,
  datasetId: string,
  summary: Record<string, unknown> | null,
): Insight {
  const seed = SEEDS[datasetId]?.[modelId] ?? SEEDS[datasetId]?.["*"];
  return {
    verdict: seed?.verdict ?? FALLBACK_VERDICT,
    evidence: deriveEvidence(summary),
    causes: (seed?.causes ?? []).map((tag) => ({ tag, label: CAUSE_LABEL[tag] })),
    actions: seed?.actions ?? [],
    caveat: seed?.caveat,
    curated: Boolean(seed),
  };
}

/** Canonical model id — mirror of seed_registries.canonical_model_id (Python):
 *  sanitize_model → NFD-strip → lower → [^a-z0-9]+ → '-' → trim '-'. */
export function canonicalModelId(model: string): string {
  let t = model.replace(/[^a-zA-Z0-9_-]/g, "_");
  t = t.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  t = t.toLowerCase();
  return t.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

/** Adapt một khối blob `/benchmark` (shape riêng của dashboard) sang shape
 *  `summaries` mà `deriveEvidence` đọc được — để panel insight dùng chung một
 *  nguồn bằng chứng ở cả `/benchmark` (blob) lẫn `/results` (DB). */
export function summaryFromBlob(datasetId: string, block: unknown): Record<string, unknown> | null {
  if (!block || typeof block !== "object") return null;
  const b = block as Row;

  if (datasetId === "vmlu-mqa-all-gold") {
    const rows: Row[] = [];
    if (b.overall && typeof b.overall === "object") {
      rows.push({ level: "overall", name: "overall", ...(b.overall as Row) });
    }
    for (const c of asRows(b.categories)) rows.push({ level: "category", ...c });
    for (const s of asRows(b.subjects)) {
      rows.push({ level: "subject", ...s, name: s.full_name ?? s.name });
    }
    return { n: (b.overall as Row | undefined)?.n, accuracy_rows: rows };
  }

  if (datasetId === "vbench-public-test") {
    return {
      n: b.total_items,
      server_rows: asRows(b.domains).map((d) => ({
        domain: d.domain,
        track: d.track,
        score: d.score,
        correct: d.correct,
        total: d.total,
      })),
    };
  }

  if (datasetId === "reading-400") {
    const rows: Row[] = asRows(b.sources).map((s) => ({
      dataset: s.label,
      n: s.n,
      em_count: s.em_count,
      em: s.em,
      char_f1: s.char_f1,
    }));
    const overall = b.overall as Row | undefined;
    if (overall) rows.push({ dataset: "ALL", ...overall });
    return { n: overall?.n, reading_rows: rows };
  }

  if (datasetId === "legal-mc-146" || datasetId === "legal-nli-150") {
    const overall = b.overall as Row | undefined;
    return overall
      ? { n: overall.n, accuracy_rows: [{ level: "overall", name: "overall", ...overall }] }
      : null;
  }

  if (datasetId === "bidlqa-val" || datasetId === "bidlqa-test") {
    const overall = b.overall as Row | undefined;
    return overall ? { n: overall.n, reading_rows: [{ dataset: "ALL", ...overall }] } : null;
  }

  return null;
}
