# Qwen3.5 gold-matrix 2 — ViBidLQA test/val + Legal NLI (cards MC-11/12/13)

Điều kiện đo: `MC-11` (bidlqa-test), `MC-12` (bidlqa-val), `MC-13` (legal-nli),
measurement_card.md. Model `Qwen3.5-9B-28K` qua `https://llmapi.iec-uit.com/v1`
(temp 0, seed 42). Cấm so ngang model khác (MC-1/MC-2/MC-3/MC-6 là model khác).

## Kết quả

| Track | Card | n | Metric | Kết quả | Baseline |
| --- | --- | --- | --- | --- | --- |
| ViBidLQA test | MC-11 | 603 | EM / char-F1 | **33,17%** (200/603) / **73,21%** | — (không baseline; QA trích xuất) |
| ViBidLQA val | MC-12 | 482 | EM / char-F1 | **32,78%** (158/482) / **74,16%** | — |
| Legal NLI-150 | MC-13 | 150 | accuracy (chữ cái) | **90,00%** (135/150) | luôn-A 75/150 = **50,00%** → **+40,0đ** |

Tất cả recompute từ per-item CSV khớp summary/accuracy (0 mismatch);
key-set 2 chiều khớp manifest; 0 empty raw trên cả 3 tracks.

## Nhận xét chéo với 5 cụm cũ (cùng model, khác suite — mô tả, không xếp hạng)

- **NLI 90,00% vs legal-MC 87,67% (MC-10):** cùng họ luật, cùng runner frozen —
  model làm tốt entailment nhị phân Có/Không. Lệch duy nhất: 15 sai toàn là
  gold-A (Có) đoán B (Không); gold-B đúng 75/75. Model thiên "Không" khi passage
  không nêu trực tiếp câu trả lời (entailment chặt hơn gold).
- **BidLQA EM ~33% vs reading-400 EM 79,75% (MC-3):** KHÔNG phải sụt năng lực —
  gold khác bản chất. Reading-400 gold có 321/400 câu kế thừa từ chính câu trả
  lời model (accept-rate, cận trên thiên lệch thuận); BidLQA gold file-native,
  câu trả lời dài theo văn phong luật (điều/khoản/văn bản hợp đồng), EM khắt khe
  với paraphrase. Char-F1 ~73–74% mới là số so được: model nắm nội dung nhưng
  diễn đạt lại (EM=0/F1≈0.98: thêm tiền tố "Khi…", thiếu hậu tố điều luật).
- **BidLQA val 32,78 vs test 33,17 (chênh 0,4đ, cùng điều kiện):** hai split nhất
  quán — pilot val dự báo đúng test. Không có dấu hiệu contamination lệch split.
- **VMLU 67,87 (MC-7) / V-Bench macro 45,22 (MC-8):** suite khác dạng, chỉ ghi
  nhận — NLI/BidLQA không gộp với hai số này.

## Outputs (gitignored) + manifests (tracked)

- `all_res/ollama_result/Qwen3_5-9B-28K/reading_answers_bidlqa_{val,test}_*.csv`
  + `reading_scores_bidlqa_*` + `reading_summary_bidlqa_*` (checkpoints
  `bidlqa_{val,test}_result_*`); `full_evaluation_nli_*` + `accuracy_nli_*` +
  `submission_nli_*` (MC-9/MC-10 finals nguyên vẹn trên đĩa).
- `data/bidlqa_{val,test}_manifest.csv` (sha `4cafca9d…`/`b99b9484…`, rebuild
  byte-identical), `data/legal_nli_manifest.json` (sha `43ffd837…`).
- Blob `web/public/benchmark-data.json`: `.bidlqa.{val,test}` + `.legal_nli`;
  5 keys cũ byte-identical.

## Không làm trong change này

- **Syllogism-144 DEFER:** gold là luận chứng tự do 551–1819 chars, không có đáp
  án ngắn để chấm EM/chữ cái — cần LLM-judge semantic; quyết judge model ở
  change sau.
- **ViBidLQA_train (1.928) skip:** train split, không phải eval set.
