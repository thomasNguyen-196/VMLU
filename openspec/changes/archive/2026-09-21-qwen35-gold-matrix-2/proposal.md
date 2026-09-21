## Why

Qwen3.5-9B-28K đã có số trên 5 cụm (VMLU test 67,87 · gold local 73,35 · reading-400 EM 79,75 ·
V-Bench macro 45,22 · legal-MC 87,67) nhưng 3 dataset CÓ GOLD vẫn chưa chạy: ViBidLQA
test/val (gold free-text sẵn trong file), Legal NLI-150 (gold Có/Không cân bằng 75/75).
Syllogism-144 có gold nhưng là luận chứng tự do — chưa có phương pháp chấm, để riêng.

## What Changes

- **Track 1** — ViBidLQA test (603) + val (482) qua pipeline `run_reading_eval` có sẵn
  (adapter manifest, prompt + budget 48 tokens y hệt MC-3), chấm EM/char-F1 bằng
  `score_reading_eval.py` với gold trong file. Hai runs tách bạch, hai card mới.
- **Track 2** — Legal NLI-150 qua `run_mc_eval` frozen: map Có→A / Không→B, choices
  prefix `A./B.`, gold letter (pattern y hệt adapter MC-10). Runner không sửa.
- **Track 3 (ghi nhận, không làm)** — Syllogism-144 DEFER: cần LLM-judge semantic,
  quyết judge model ở change sau. ViBidLQA_train (1.928) bỏ — train split không eval.
- Dashboard `.reading` mở rộng thêm block bidlqa (hoặc block riêng), `.legal` thêm NLI;
  SQuAD/DROP-full, Dialog, SEATau telecom đều ngoài scope (không gold / theo yêu cầu user).

## Capabilities

### New Capabilities

- `bidlqa-eval`: ViBidLQA test/val inference + EM/char-F1 scoring + dashboard cho một model.
- `legal-nli`: Legal NLI-150 binary qua MC runner (adapter Có→A/Không→B) + accuracy + dashboard.

### Modified Capabilities

(none — additive; prompt/parser/scoring contracts giữ byte-frozen)

## Impact

- Code: 1 adapter input script pattern MC-10 (NLI) + manifest bidlqa (test/val tách);
  runners/scorers dùng nguyên qua CLI flags hiện có.
- Outputs: per-model CSVs như hiện tại + 3 measurement cards mới (MC-11 bidlqa-test,
  MC-12 bidlqa-val, MC-13 legal-nli) + dashboard patch.
- Docs: `docs/` record mỗi track; syllogism defer ghi rõ lý do.
- Non-goals: syllogism judge, train split, SQuAD/DROP-full, dialog, seatau telecom,
  regime B/C, contract changes.

## Evaluation regime touched

Regime **A** (official template, temperature 0, seed 42, short answer budgets).
