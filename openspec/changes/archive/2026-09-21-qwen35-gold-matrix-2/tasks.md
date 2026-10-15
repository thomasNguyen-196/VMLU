## 1. NLI-150 qua MC runner frozen (MC-13, làm trước — nhỏ nhất)

- [x] 1.1 Build adapter input `/tmp/legal_nli_input/legal_nli_150.jsonl`: ids `LG-NLI-0001…0150`
  theo thứ tự source, question = `legal_document + specific_question + question` (order
  frozen, ghi verbatim vào card), choices `["A. Có","B. Không"]`, gold Có→A/Không→B;
  verify sha source + gold map 150/150 + baseline recompute (~50%)
- [x] 1.2 Run: `run_mc_eval.py --folder /tmp/legal_nli_input --file legal_nli_150.jsonl
  --model Qwen3.5-9B-28K --workers 4 --max-tokens 4` — ✅ exit 0, 145s, 150/150 (raw_result_150_*); finals đổi tên `*_nli_*`, MC-9 restore nguyên vẹn
- [x] 1.3 Verify: cross-check gold 150/150 vs source, recompute accuracy từ per-row
  `correct` khớp `accuracy_nli_*` (0 mismatch) — ✅ 135/150=90.00%, baseline A 75/150=50.00% (+40.0đ), by-gold A 60/75=80.00% B 75/75=100.00%, valid 150/150
- [x] 1.4 Card MC-13 mới (adapter string verbatim + baseline + kết quả) + commit track — ✅ commit `f076db2`

## 2. BidLQA-val 482 (MC-12, pilot cho test)

- [x] 2.1 `score_reading_eval.py --gold` đã có (default review gold, `--gold` trỏ file gold) — ✅ unit offline 2 rows: EM 1/2=50.00, scores+summary ghi đúng; scoring math không chạm
- [x] 2.2 Build manifest val 482 `data/bidlqa_val_manifest.csv` (`BIDLQA-V-0001…0482`, MANIFEST_COLS, sha `4cafca9d…` pinned) — ✅ 482 rows, 0 empty gold/question, rebuild byte-identical; runner mới `code_benchmark/run_bidlqa_eval.py` (frozen prompt import, MC-3 condition)
- [x] 2.3 Run `run_bidlqa_eval.py --split val` MC-3 condition — ✅ exit 0, 1098s, 482/482, 0 empty; score `--gold manifest`: EM 158/482=32.78, F1 74.16, recompute 0 mismatch
- [x] 2.4 Card MC-12 mới + commit track — ✅ commit `7dfaaab`

## 3. BidLQA-test 603 (MC-11)

- [x] 3.1 Build manifest test 603 `data/bidlqa_test_manifest.csv` (`BIDLQA-T-0001…0603`, MANIFEST_COLS, sha `b99b9484…` pinned) — ✅ 603 rows, 0 empty gold/question, rebuild byte-identical
- [x] 3.2 Run `run_bidlqa_eval.py --split test` MC-3 condition — ✅ exit 0, 1359s, 603/603, 0 empty; score `--gold manifest`: EM 200/603=33.17, F1 73.21, recompute 0 mismatch
- [x] 3.3 Card MC-11 mới + commit track — ✅ commit `e32d1dd`

## 4. Dashboard + report + đóng change

- [x] 4.1 Patch blob `bidlqa: {test EM 33.17/F1 73.21, val EM 32.78/F1 74.16}` + `legal_nli 90.00` — ✅ 5 keys cũ byte-identical, recompute-clean, node parse + tsc OK + commit `3bdf48b`
- [x] 4.2 Report `docs/bidlqa-nli-qwen35.md` — ✅ test EM 33.17/F1 73.21, val EM 32.78/F1 74.16, NLI 90.00 (+40.0đ); nhận xét chéo 5 cụm cũ (F1-not-EM, B-bias, val-test 0.4đ) + commit `fa9d326`
- [x] 4.3 Defer syllogism-144 (gold luận chứng tự do 551–1819 chars, cần LLM-judge — change sau) + train-1928 skip (train split) — ✅ ghi trong `docs/bidlqa-nli-qwen35.md`; gates xanh: 81 tests + parsing + ruff + bandit + tsc
