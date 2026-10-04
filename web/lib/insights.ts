/** Lớp nhận xét cho /results — mỗi cặp (mô hình × bộ dữ liệu) có một diễn giải
 *  + hướng kiểm chứng, kèm bằng chứng số rút tự động từ bản tổng hợp của lần chạy.
 *
 * Hai phần tách bạch:
 *  - `SEEDS`  — diễn giải chuyên biệt (chủ quan, có căn cứ số) theo taxonomy của
 *               đề cương KLTN. Mọi nguyên nhân đều được diễn đạt là giả thuyết,
 *               không phải kết luận nhân quả; hành động bám các hướng được phép
 *               (cung cấp ngữ cảnh có căn cứ, ngân sách suy luận, định tuyến,
 *               chuẩn hoá định dạng, kiểm chứng thiên lệch) — không đề xuất
 *               fine-tune ngoài phạm vi đề cương.
 *  - `deriveEvidence` — số liệu lấy từ `summaries` lúc render (nguồn số hiển thị).
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
  parametric: "Có thể chưa được huấn luyện đủ về mảng kiến thức này",
  normative: "Có thể thiếu tri thức quy chuẩn hoặc bối cảnh bản địa",
  reasoning: "Có thể gặp hạn chế ở bước suy luận",
  format: "Có thể do lỗi định dạng hoặc giới hạn ngân sách",
  calibration: "Thiên lệch nhãn đáp án",
  robustness: "Nhạy với cách hỏi hoặc phân bố",
};

/** Mô tả 1 dòng cho mỗi nhóm nguyên nhân — hiển thị trong UI để dễ hiểu.
 *  Đây là giả thuyết cần kiểm chứng, không phải nguyên nhân đã được chứng minh. */
export const CAUSE_DESC: Record<InsightCause, string> = {
  parametric: "Mô hình có thể chưa được huấn luyện đủ về mảng kiến thức này. Cần thử đổi cách hỏi hoặc cung cấp ngữ cảnh để kiểm chứng.",
  normative: "Kết quả có thể liên quan đến tri thức quy chuẩn hoặc bối cảnh Việt Nam. Nên thử cung cấp văn bản có căn cứ và so với điều kiện không có ngữ cảnh.",
  reasoning: "Mô hình có thể sai ở bước tính, so sánh, đếm hoặc suy luận. Cần phép thử có kiểm soát với ngân sách suy luận khác nhau.",
  format: "Câu trả lời rỗng hoặc lệch chuẩn có thể liên quan đến định dạng, mẫu hỏi hoặc giới hạn token; cần lưu `finish_reason` và số token để xác định.",
  calibration: "Phân bố dự đoán lệch theo nhãn. Chưa đủ gọi là hiệu chuẩn nếu chưa đo xác suất, lỗi phân loại chuẩn hóa (ECE) hoặc điểm Brier.",
  robustness: "Đáp án thay đổi khi đổi cách hỏi hoặc phân bố. Mọi so sánh phải khóa điều kiện hỏi và báo cáo độ nhạy cảm.",
};

export interface InsightSeed {
  /** Diễn giải 1–2 câu, có số neo và giới hạn kết luận. */
  verdict: string;
  /** Nhóm giả thuyết cần kiểm chứng theo đề cương. */
  causes: InsightCause[];
  /** Hướng kiểm chứng và phương pháp cải thiện (không fine-tune). */
  actions: string[];
  /** Điều KHÔNG được suy diễn từ run này. */
  caveat?: string;
}

export interface Insight {
  verdict: string;
  evidence: string[];
  causes: Array<{ tag: InsightCause; label: string; desc: string }>;
  actions: string[];
  caveat?: string;
  /** true = có diễn giải chuyên biệt; false = chỉ có bằng chứng tự động. */
  curated: boolean;
}

const FALLBACK_VERDICT =
  "Chưa có diễn giải chuyên biệt cho cặp mô hình × bộ dữ liệu này. Bảng bên dưới chỉ là bằng chứng số rút tự động từ bản tổng hợp của lần chạy.";

// ── Diễn giải chuyên biệt (mô hình × bộ dữ liệu) ───────────────────────
// dataset_id theo registry (code_benchmark/seed_registries.py); "*" = mọi mô hình.
const SEEDS: Record<string, Record<string, InsightSeed>> = {
  "vmlu-mqa-all-gold": {
    "qwen3-5-9b-28k": {
      verdict:
        "73,35% (768/1.047); điểm thấp tập trung ở một số môn quy chuẩn như Luật hành chính, Thuế và Nghiệp vụ công chức. Kết quả này phù hợp với giả thuyết thiếu tri thức bản địa, nhưng chưa có đối chứng song ngữ để kết luận đây không phải hạn chế về tiếng Việt.",
      causes: ["normative", "parametric"],
      actions: [
        "Dùng các môn dưới 50% làm tập nghiên cứu để kiểm tra tác động của việc cung cấp ngữ cảnh có căn cứ.",
        "Chạy phép thử có/không có ngữ cảnh trên cùng câu hỏi; giữ điều kiện không có ngữ cảnh làm mốc đối chứng.",
        "Báo cáo theo môn kèm cỡ mẫu và khoảng tin cậy; không dùng 10–20 câu/môn để đại diện cho cả một mảng.",
      ],
      caveat: "Đây là 1.047 câu dev+valid, không phải điểm leaderboard; mỗi môn chỉ có 10–20 câu và chưa có phép thử song ngữ.",
    },
    "qwen3-8-27b-q4-k-m-gguf": {
      verdict:
        "73,35% (768/1.047); 54/58 môn có cùng số câu đúng với Qwen3.5-9B. Đây là mô tả một cặp kết quả, chưa phải kiểm định tương đương: quy mô, lượng tử hóa, điều kiện suy luận và tính bất biến của dịch vụ đều cần được kiểm soát.",
      causes: ["normative", "parametric", "robustness"],
      actions: [
        "Chạy lại hai mô hình trong cùng điều kiện với nhiều lần lặp hoặc dùng thiết kế ghép cặp trước khi so sánh.",
        "Báo cáo mức chênh lệch và khoảng tin cậy; không kết luận về vai trò của quy mô khi chưa có phép thử tương đương.",
        "Dùng bộ khác dạng để kiểm chứng xu hướng, nhưng không gộp điểm của các bộ không cùng thang đo.",
      ],
      caveat: "Mô hình đã rời endpoint ngày 12/09 nên không tái lập được nguyên trạng (MC-4).",
    },
  },
  "vmlu-mqa-valid": {
    "*": {
      verdict:
        "744 câu valid có gold nội bộ; Qwen3.5 đạt 540/744 = 72,58%. Đây là kết quả mô tả của một lần chạy, chưa đủ đánh giá tính ổn định nếu không có các lần lặp cùng điều kiện.",
      causes: [],
      actions: [
        "Dùng valid để đối chiếu giữa các lần chạy; lấy kết luận theo môn từ all_gold và luôn kèm cỡ mẫu.",
      ],
      caveat: "Không so ngang trực tiếp với điểm leaderboard của tập test có gold bị giữ kín.",
    },
  },
  "vmlu-mqa-dev": {
    "*": {
      verdict:
        "303 câu dev có gold nội bộ; Qwen3.5 đạt 229/303 = 75,58%. Tập này phù hợp để kiểm tra đầu-cuối và điều kiện hỏi, không phù hợp để kết luận chi tiết theo môn.",
      causes: ["robustness"],
      actions: [
        "Giữ vai trò kiểm tra đầu-cuối: xác nhận endpoint, mẫu hỏi, bộ phân tích đầu ra và câu trả lời rỗng trước khi chạy bộ lớn.",
      ],
      caveat: "Cỡ mẫu nhỏ và không đều theo môn; không bẻ nhỏ thêm.",
    },
  },
  "vmlu-mqa-test": {
    "qwen3-5-9b-28k": {
      verdict:
        "Điểm leaderboard là 67,87% (STEM 65,65 · xã hội 74,97 · nhân văn 68,61 · nhóm khác 63,67), thấp hơn dev+valid khoảng 5,5 điểm. Chênh lệch này có thể do phân bố tập hoặc biến động điều kiện chạy; chưa đủ để ước lượng riêng độ khó của test.",
      causes: ["robustness"],
      actions: [
        "Mô tả chênh lệch như một hiện tượng cần kiểm tra, không dùng ngay để kết luận test khó hơn.",
        "Muốn chẩn đoán theo môn trên test cần gold độc lập hoặc bộ có gold nội bộ cùng phạm vi.",
      ],
      caveat: "Điểm chỉ có sau khi gửi tệp dự thi; tệp 9.833 dòng khớp id 1:1 và không có câu trả lời rỗng (MC-7).",
    },
  },
  "vbench-public-test": {
    "qwen3-5-9b-28k": {
      verdict:
        "Tệp chấm cuối có macro 45,22 và micro 45,61% (2.345/5.141). Điểm agentic cuối gồm 14 câu được hỏi lại theo guided; điều kiện minimal thuần đạt 986/1.000 câu hợp lệ, còn guided đạt 1.000/1.000. Vì vậy điểm cuối không đại diện cho một điều kiện minimal thuần.",
      causes: ["format", "reasoning", "robustness"],
      actions: [
        "Báo riêng kết quả minimal thuần, guided và điểm tổng của tệp cuối; không gọi toàn bộ tệp cuối là minimal.",
        "Kiểm chứng các tham số chọn hàm bằng đối chiếu ngữ cảnh; độ hợp lệ cú pháp không chứng minh lựa chọn hàm hoặc tham số đúng.",
        "Dùng phép đối chiếu minimal↔detailed trên 27B làm thí nghiệm độ nhạy của cách hỏi, tách khỏi so sánh điểm của mô hình 9B.",
      ],
      caveat: "Điểm do máy chủ vbench.ai chấm; hợp lệ về cú pháp không đồng nghĩa đúng nội dung, và 14 câu guided là điều kiện thứ ba.",
    },
    "qwen3-8-27b-q4-k-m-gguf": {
      verdict:
        "Macro 44,97 · micro 45,46%; điểm các miền gần Qwen3.5-9B trong các lần chạy hiện có. Chênh lệch nhỏ không tự chứng minh hai mô hình tương đương. Riêng phép đối chiếu minimal→detailed trên mô hình 27B làm 42,2% câu agentic đổi đáp án.",
      causes: ["robustness", "reasoning"],
      actions: [
        "Khóa một điều kiện hỏi cho mỗi phép so sánh và báo cáo độ nhạy cảm khi đổi mẫu hỏi.",
        "Tách riêng kết quả của phép đối chiếu detailed khỏi điểm của một điều kiện.",
      ],
      caveat: "Mô hình đã rời endpoint; các số là snapshot MC-2/MC-2b.",
    },
  },
  "reading-400": {
    "qwen3-5-9b-28k": {
      verdict:
        "EM 79,75% · char-F1 86,49%; Vi-SQuAD đạt EM 96,5%, còn Vi-DROP 63,0%. Chênh lệch phù hợp với giả thuyết rằng các câu cần tính, so sánh hoặc đếm khó hơn, nhưng chưa tách được lỗi suy luận khỏi khác biệt về dạng câu, cách tạo gold và định dạng câu trả lời.",
      causes: ["reasoning", "format"],
      actions: [
        "Dựng lại gold độc lập, không nhìn thấy câu trả lời của mô hình, rồi chạy kiểm tra bởi ít nhất hai người.",
        "So sánh các điều kiện có và không có ngân sách suy luận với cùng ngân sách tổng để đo tác động thay vì giả định nguyên nhân.",
        "Báo cáo EM, char-F1 và đánh giá ngữ nghĩa riêng; char-F1 không tự chứng minh câu trả lời cùng nghĩa.",
      ],
      caveat: "Gold được duyệt bởi một người nhìn thấy câu trả lời của Qwen3.8; 321/400 câu dùng nguyên văn câu trả lời được Accept, nên điểm không độc lập hoàn toàn với quy trình chọn gold.",
    },
    "qwen3-8-27b-q4-k-m-gguf": {
      verdict:
        "EM 80,25% · char-F1 86,55%; Vi-SQuAD đạt EM 97,5%, còn Vi-DROP 63,0%. Chênh lệch cho thấy độ khó theo dạng nhiệm vụ khác nhau, nhưng không đủ để quy toàn bộ cho hạn chế suy luận.",
      causes: ["reasoning", "format"],
      actions: [
        "Kiểm chứng các cụm cộng/trừ, so sánh và đếm bằng phép thử có kiểm soát thay vì dùng tỷ lệ bị bác làm bằng chứng nguyên nhân.",
        "Giữ Vi-SQuAD và Vi-DROP thành hai lát cắt mô tả riêng; không gộp thành một “năng lực đọc hiểu chung”.",
        "Bổ sung đánh giá ngữ nghĩa của câu trả lời trước khi dùng char-F1 để kết luận rằng lỗi chỉ nằm ở định dạng.",
      ],
      caveat: "Điểm EM 80,25% trùng với 321 câu được Accept; một người duyệt và nhìn thấy câu trả lời của chính mô hình này, nên chưa có độ khớp giữa người đánh giá (IAA) hay gold độc lập.",
    },
  },
  "legal-mc-146": {
    "qwen3-5-9b-28k": {
      verdict:
        "87,67% (128/146), cao hơn mốc đối chứng A 62,33% là 25,3 điểm; 146/146 câu phân tích được và không có câu trả lời rỗng. Kết quả này chỉ mô tả LegalSLM-146, chưa đủ để kết luận về năng lực pháp luật nói chung.",
      causes: ["normative"],
      actions: [
        "Dùng LegalSLM-146 làm mốc đối chứng có ngưỡng mô hình ≤4B; không so ngang trực tiếp với các môn luật của VMLU.",
        "Thử cung cấp văn bản quy phạm và so với điều kiện không có ngữ cảnh trước khi giải thích chênh lệch.",
        "Luôn báo kèm mốc đối chứng vì phân bố gold lệch mạnh: A=91, B=39, C=16, D=0.",
      ],
      caveat: "Public-test có 146 câu; mô hình 9B vượt giới hạn ≤4B của bộ dữ liệu và cần được nêu rõ khi công bố.",
    },
    "qwen38-nothink": {
      verdict:
        "82,88% (121/146), thấp hơn Qwen3.5-9B 4,8 điểm; 21 câu trả lời rỗng dù đã tăng giới hạn lên 512 token. Nguyên nhân có thể liên quan đến ngân sách, mẫu hỏi hoặc cấu hình suy luận, nhưng hiện chưa đủ dữ liệu để loại trừ hạn chế tri thức.",
      causes: ["format", "reasoning"],
      actions: [
        "Chạy kiểm tra có/không suy luận ẩn và lưu `finish_reason`, số token đầu ra cùng nội dung thô.",
        "Giữ 21 câu trả lời rỗng là sai; không cộng điểm bù.",
      ],
      caveat: "Mô hình 27B vượt giới hạn ≤4B của bộ dữ liệu và đã rời endpoint.",
    },
    "qwen3-5-9b-65k": {
      verdict:
        "89,04% (130/146). Đã kiểm tra position bias (MC-35/36): shuffle đổi phân bố gold từ A-majority 62,3% sang gần đều (30,8%) nhưng accuracy không đổi — Δ +0,00 (CI −5,48..+5,48), 126/146 câu giữ nguyên text được chọn (letter-anchored chỉ 4). Con số này không bị thổi bởi vị trí đáp án; phần dư 16 câu đổi cả text chưa tách được khỏi nhiễu chạy lại vì chưa có repeat.",
      causes: ["normative"],
      actions: [
        "Dùng 89,04% làm baseline 65K cho mọi so sánh harness trên legal-mc-146; giữ đúng điều kiện MC-31.",
        "Muốn kết luận dưới ±5,5 điểm thì chạy lặp cùng điều kiện trước — CI của Δ trên n=146 rộng ±5,5 điểm.",
      ],
      caveat: "Position bias mới đo trên legal_mc-146 của riêng model này (MC-36), không suy sang bộ khác; mô hình 9B vượt giới hạn ≤4B của bộ dữ liệu.",
    },
  },
  "legal-nli-150": {
    "qwen3-5-9b-28k": {
      verdict:
        "Đây là phân loại khả năng hỗ trợ câu hỏi từ văn bản pháp lý dạng Có/Không, không phải NLI ba nhãn đầy đủ. Mô hình đạt 90,0% (135/150) so với mốc 50%; độ chính xác theo gold B là 100%, theo gold A là 80%.",
      causes: ["calibration", "reasoning"],
      actions: [
        "Kiểm tra thiên lệch nhãn trên tập độc lập và phép đảo nhãn trước khi dùng làm bước kiểm chứng trong RAG.",
        "Chỉ gọi là hiệu chuẩn nếu có xác suất tin cậy và thước đo hiệu chuẩn phù hợp; ma trận nhầm lẫn hiện tại mới là bằng chứng thiên lệch nhãn.",
      ],
      caveat: "Tập nhị phân cân bằng 75/75; đoán ngẫu nhiên đạt 50%. Tên NLI trong giao diện không mô tả đầy đủ cấu trúc nhãn.",
    },
  },
  "bidlqa-val": {
    "qwen3-5-9b-28k": {
      verdict:
        "EM 32,78% · char-F1 74,16%; 105/482 câu có char-F1≥0,8 nhưng EM=0. Đây là mức trùng lớn ở mặt chữ, chưa đủ chứng minh 105 câu có cùng ý nghĩa hoặc chỉ sai định dạng.",
      causes: ["format", "robustness"],
      actions: [
        "Bổ sung kiểm tra ngữ nghĩa bằng người hoặc nhiều bộ chấm đã được hiệu chuẩn trước khi phân loại lỗi.",
        "Thử ràng buộc trích nguyên văn và ghi `finish_reason`; không dùng char-F1 làm thước đo thay thế riêng cho EM.",
        "Chạy thêm điều kiện không có ngữ cảnh nếu muốn tách kiến thức nền khỏi khả năng đọc ngữ cảnh.",
      ],
      caveat: "Gold lấy từ tệp nguồn, chưa qua hai người duyệt; điểm không nên được gọi là chấm ngữ nghĩa đầy đủ.",
    },
  },
  "bidlqa-test": {
    "qwen3-5-9b-28k": {
      verdict:
        "EM 33,17% · char-F1 73,21%, gần với val (32,78% · 74,16%). Hai điểm gần nhau là mô tả tương đồng trên một lần chạy, chưa đủ chứng minh tính ổn định hay khả năng tổng quát; 120/603 câu có char-F1≥0,8 nhưng EM=0.",
      causes: ["format", "robustness"],
      actions: [
        "Dùng val để chọn thay đổi và test để mô tả xác nhận, rồi lặp thêm nếu cần kết luận về tính ổn định.",
        "Kiểm chứng ngữ nghĩa các câu có char-F1 cao trước khi quy chúng là lỗi định dạng.",
      ],
      caveat: "Gold lấy từ tệp nguồn; chưa có kiểm chứng hai người và chưa so ngang mô hình khác.",
    },
  },
  "vm14k-public-12488": {
    "qwen3-5-9b-28k": {
      verdict:
        "Độ chính xác tổng 64,79% (8.091/12.488), cao hơn mốc A 31,35% là 33,4 điểm; 12.488/12.488 câu phân tích được. Điểm giảm theo nhãn độ khó (67,19 → 64,01 → 61,78 → 56,67), nhưng tổng hợp các câu 1–7 lựa chọn nên chỉ nên dùng như số mô tả, không phải kết luận về nguyên nhân.",
      causes: ["parametric", "reasoning"],
      actions: [
        "Đối chiếu với V-Bench y khoa của cùng mô hình (38,57%, 189/490) chỉ như hai phép đo khác dạng; không trừ phần trăm của chúng cho nhau.",
        "Báo riêng câu bốn lựa chọn làm số chính và Đúng/Sai làm lát cắt phụ; kèm cỡ mẫu, khoảng tin cậy và phân bố chuyên khoa.",
        "Đăng ký trước một phiên bản đã lọc câu rỗng, câu giữ chỗ, số lựa chọn không hợp lệ và trùng lặp; không sửa bộ dữ liệu thô của MC-14b.",
      ],
      caveat: "Bản phát hành cục bộ lệch mô tả bài báo, có khoảng 6% trùng lặp và điều khoản cấp phép cần xác minh; mô hình 9B vượt giới hạn ≤4B.",
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
  if (overall) out.push(`Tổng: ${fmt(overall.correct)}/${fmt(overall.n)} = ${fmt(overall.accuracy)}%`);

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
      `Môn thấp nhất: ${sorted.slice(0, 3).map((r) => `${fmt(r.name)} ${fmt(r.accuracy)}% (n=${fmt(r.n)})`).join(" · ")}`,
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
    out.push(`Tổng: EM ${fmt(all.em)}% · char-F1 ${fmt(all.char_f1)} (${fmt(all.em_count)}/${fmt(all.n)} khớp EM)`);
    const gap = (num(all.char_f1) ?? 0) - (num(all.em) ?? 0);
    if (gap > 0) out.push(`Chênh EM→char-F1: ${gap.toFixed(2)} điểm`);
  }
  for (const r of rows.filter((x) => x.dataset !== "ALL")) {
    out.push(`${fmt(r.dataset)}: EM ${fmt(r.em)}% · char-F1 ${fmt(r.char_f1)} (n=${fmt(r.n)})`);
  }
  return out;
}

function vbenchEvidence(valid: Row[], server: Row[]): string[] {
  const out: string[] = [];
  const total = server.reduce((a, r) => a + (num(r.total) ?? 0), 0);
  const correct = server.reduce((a, r) => a + (num(r.correct) ?? 0), 0);
  if (total) out.push(`Micro (máy chủ chấm): ${correct}/${total} = ${((100 * correct) / total).toFixed(2)}%`);

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
      ([t, v]) => `${t} ${v.valid}/${v.n} hợp lệ${v.n ? ` (${((100 * v.valid) / v.n).toFixed(1)}%)` : ""}`,
    );
    out.push(`Độ hợp lệ cú pháp: ${parts.join(" · ")}`);
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
  if (!out.length) out.push(`Lần chạy chưa có bảng số tổng hợp (n=${fmt(summary.n)}; gold nội bộ bị giữ kín hoặc bản tổng hợp chưa được chuyển sang) — điểm chỉ có thể đọc từ nguồn chấm bên ngoài.`);
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
    causes: (seed?.causes ?? []).map((tag) => ({ tag, label: CAUSE_LABEL[tag], desc: CAUSE_DESC[tag] })),
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

  if (datasetId === "legal-mc-146" || datasetId === "legal-nli-150" || datasetId === "vm14k-public-12488") {
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
