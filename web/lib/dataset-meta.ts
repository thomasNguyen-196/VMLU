/** Dataset descriptions + shared metric vocabulary (change dataset-meta).
 *
 * One deep module: every benchmark tab renders its "what / how-scored"
 * strip from DATASET_META, so all seven tabs share one vocabulary and no
 * hero hardcodes its own prose. Page/route stays a thin pass-through.
 */

export interface DatasetMeta {
  /** Dataset là gì, bao nhiêu câu, nguồn nào. */
  about: string;
  /** Dạng câu hỏi + cách chấm (MC khớp chữ cái / EM+char-F1 / server-side). */
  shape: string;
  /** Thang điểm hero của tab (Accuracy / Micro+Macro / EM+F1 / ...). */
  metric: string;
  /** Không được hiểu nhầm thành gì (accept-rate≠accuracy, valid≠correct...). */
  metricNote: string;
}

export const DATASET_META: Record<string, DatasetMeta> = {
  vmlu: {
    about: "Trắc nghiệm kiến thức tiếng Việt 58 môn (STEM, xã hội, nhân văn, khác) — 1.047 câu dev+valid có gold local, dùng dò điểm trũng theo môn.",
    shape: "Mỗi câu 1 đáp án đúng trong A–E · chấm khớp chữ cái (case-insensitive)",
    metric: "Accuracy = số câu đúng / tổng số câu",
    metricNote: "Không phải điểm leaderboard (bộ test 9.833 câu bị withheld, chấm server-side).",
  },
  vbench: {
    about: "Bảng public test đa miền (12 miền trắc nghiệm + 1 track gọi hàm agentic) — đo kiến thức tổng quát và khả năng gọi tool đúng schema.",
    shape: "MC: chọn 1 đáp án · Agentic: trả JSON gọi hàm đúng schema",
    metric: "Micro = đúng/tổng câu · Macro = trung bình điểm 13 miền",
    metricNote: "Điểm server-side (vbench.ai). Valid (đúng cú pháp) ≠ correct (đúng nội dung).",
  },
  reading: {
    about: "Đọc hiểu 400 câu tiền đăng ký (200 Vi-SQuAD trích xuất + 200 Vi-DROP suy luận số) — đo đọc hiểu tiếng Việt có ngữ cảnh.",
    shape: "Trả lời tự do từ đoạn văn cho sẵn (open-book, 48 token)",
    metric: "EM = khớp tuyệt đối · char-F1 = tín chỉ từng phần theo ký tự",
    metricNote: "Không phải accept-rate (tỷ lệ duyệt viên bấm chấp nhận) — EM/F1 chấm trên gold đã hiệu đính.",
  },
  legal: {
    about: "Trắc nghiệm pháp luật Việt Nam 146 câu (VLSP 2025 LegalSLM) — đo mảng Luật đã lộ yếu trên VMLU (mục 3.1 roadmap).",
    shape: "Trắc nghiệm A–D qua MC runner frozen (4 token, closed-book)",
    metric: "Accuracy + baseline majority (đáp án phổ biến nhất)",
    metricNote: "So với baseline để thấy lift; không so ngang % VMLU (suite khác dạng).",
  },
  legal_nli: {
    about: "Suy luận entailment pháp luật 150 câu nhị phân (điều luật có trả lời được câu hỏi không: Có/Không) — đo mảng Luật dạng NLI.",
    shape: "Nhị phân Có/Không qua MC runner frozen (ánh xạ A/B)",
    metric: "Accuracy + baseline majority (≈50% vì 75/75 cân bằng)",
    metricNote: "By-gold A/B cho thấy lệch theo đáp án đúng.",
  },
  bidlqa_val: {
    about: "Hỏi-đáp đấu thầu 482 câu (ViBidLQA split val) — đọc hiểu chuyên ngành pháp lý đấu thầu, gold nguyên văn trong file.",
    shape: "Trả lời tự do từ ngữ cảnh văn bản đấu thầu (open-book, 48 token)",
    metric: "EM + char-F1 trên file-gold",
    metricNote: "Gold chưa qua review 2 người — EM là cận dưới theo chữ, F1 bù diễn đạt lại.",
  },
  bidlqa_test: {
    about: "Hỏi-đáp đấu thầu 603 câu (ViBidLQA split test) — cùng dạng val, đo khái quát hóa sang split unseen.",
    shape: "Trả lời tự do từ ngữ cảnh văn bản đấu thầu (open-book, 48 token)",
    metric: "EM + char-F1 trên file-gold",
    metricNote: "Đọc cùng val để thấy độ ổn định qua 2 split.",
  },
};
