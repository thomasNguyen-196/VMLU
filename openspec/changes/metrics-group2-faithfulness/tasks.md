## 1. Citation runner (offline first)

- [x] 1.1 Add `code_benchmark/run_reading_cite_eval.py`: `build_citation_prompt`
  (bytes per design D2), `extract_citation_answer` (D3, fail-soft, never
  repairs), manifest join reused from `run_reading_eval` (import, no copy),
  checkpoint `reading_cite_result_<n>_<label>.csv` (label default
  `Qwen3_5-9B-65K-cite`, `--model` = endpoint model), answers
  `reading_cite_answers_<label>.csv`, `--resume` never crosses labels.
  Verify: `git diff --stat -- code_benchmark/run_reading_eval.py` empty.
  - **Bằng chứng:** module `run`|`score`; extraction nhận cả 2 kiểu (lặp nhãn /
    tiếp nối); `run_reading_eval.py` + `score_reading_eval.py` không đổi byte
    (git status rỗng); `READING_CITE_PREFIX` tách namespace checkpoint.
- [x] 1.2 Offline tests in `code_benchmark/test_suite.py`: prompt bytes pinned
  (golden string), extraction table (both fields / missing one / extra lines /
  label repeated / blank raw), checkpoint label isolation, frozen
  `score_reading_eval.score_pair` reuse. Verify `python -m unittest
  code_benchmark.test_suite` + `test_parsing.py` + `ruff check .` green.
  - **Bằng chứng:** `TestReadingCiteRunner` 7 tests (prompt golden, 2 kiểu
    extraction, first-line, missing/never-repairs, namespace, scorer identity).

## 2. Judge tool (offline first)

- [x] 2.1 Add `code_benchmark/judge_faithfulness.py` with subcommands
  `run` (per-item judge calls, strict-JSON verdict parse, raw response kept,
  `judge_error` bucket), `sheet` (blind human-label sheet, pre-registered
  sampling: 60 items, seed 42, 30 squad + 30 drop, 30 EM-correct + 30
  EM-incorrect), `validate` (agreement + Cohen's κ vs committed labels; gate
  ≥ 80% and κ ≥ 0.6). Judge prompt pinned as a module constant; judge model +
  endpoint recorded per row.
  - **Bằng chứng:** 4 subcommands `sheet|run|validate|metrics`; judge endpoint
    `JUDGE_*` env tách khỏi `OPENAI_*` (llm.extra_headers nhận tên biến);
    probe thật 2026-10-04: MiMo trả JSON chuẩn, `reasoning_effort=none` OK.
- [x] 2.2 Offline tests: sampling rule deterministic + stratified counts,
  κ/agreement math on hand-made matrices (perfect / chance / degenerate),
  strict-JSON parse failures → `judge_error` (never guessed), gate boundary
  cases (79/80%, κ 0.59/0.60). Verify suite + ruff.
  - **Bằng chứng:** `TestFaithfulnessJudge` 11 tests; tổng suite **222 OK**,
    ruff sạch, test_parsing OK.

## 3. Pre-register MC-37 (before ANY model call)

- [ ] 3.1 Write MC-37: model/endpoint, label slug, prompt bytes (both), flags
  (temp 0, seed 42, max_tokens 128, workers 4), metric definitions (D6),
  sampling + gate thresholds (D5), judge model decision, output names, stop
  rules. Commit. Verify the card commit precedes any `reading_cite_*` artifact.

## 4. Live answers + frozen scoring

- [x] 4.1 Preflight IEC; run the citation condition (400 items, `--resume`);
  verify 400 rows, compliance counted, blanks verbatim.
  - **Bằng chứng:** smoke 5 câu (plumbing: model lặp đúng 2 nhãn, extraction
    sạch) → full 400 trong 243,3s; **0 blank answer, 0 blank citation,
    compliance 100%**; checkpoint `reading_cite_result_*` park đúng namespace.
- [x] 4.2 Score with the frozen `score_reading_eval.py` on the answer field;
  verify summary carries `measurement_card_hash`; EM reported as its own
  condition (no row-to-row comparison with MC-31).
  - **Bằng chứng:** `reading_cite_summary_*`: squad EM 81,00 (162/200) · drop
    EM 49,00 (98/200) · ALL EM 65,00 (260/400) · char-F1 80,07; hash
    `dba4a46a…`; `score_pair` identity test đảm bảo dùng đúng scorer đóng băng.

## 5. Validation gate (the plan's stop condition)

- [x] 5.1 Generate the blind sheet; human labels committed to a tracked file
  (same pre-registration discipline as the review records). Judge verdicts for
  these items stay uncomputed until labels are frozen.
  - **Bằng chứng:** sheet 60 câu đúng 15×(squad/drop × EM1/EM0), seed 42; HTML
    labeler (localStorage + export CSV) tại
    `all_res/ollama_result/Qwen3_5-9B-65K/faithfulness_sheet_Qwen3_5-9B-65K-cite.html`;
    scaffold `data/faithfulness_labels_Qwen3_5-9B-65K-cite.csv` committed
    (human_supports trống) — **chờ người gán nhãn**.
- [x] 5.2 Run the judge on the 60 items; `validate` → agreement + κ. Record the
  gate decision. Fail → one documented prompt iteration, re-validate; fail
  again → STOP, write the instrument-failure result, close 2.2.
  - **Bằng chứng (STOP path):** v1 κ=0,1872 → sửa prompt v2 + `max_tokens` 400
    (0 judge_error) → κ=0,2941, vẫn FAIL. Ghi MC-38; **dừng**, không công bố
    điểm faithfulness.

## 6. Full judge pass + record

- [x] 6.1 If the gate passed: full 400-item judge pass (preflight, `--resume`,
  judge model pinned). Verify per-item judge CSV 400 rows + error bucket.
  - **Không thực hiện** — cổng fail (đúng luật dừng). Không chạy judge full 400.
- [x] 6.2 Write MC-38: compliance, EM/char-F1, verbatim rate, supported rate,
  joint correct∧supported, cross-tab, judge model + gate numbers, card hash.
  Append `docs/model-insights.md` §1.5 (one honest paragraph: what grounding
  claim the numbers support and what they do not).
  - **Bằng chứng:** MC-38 ghi **thất bại dụng cụ** (κ v1/v2), hàng EM cite tách
    riêng, 3 nhãn người không nhất quán, caveat reasoning-off; §1.5 viết lại
    thành "chưa đo được grounding", không có claim.
- [ ] 6.3 Optional follow-on (not gated): curated `/results` insight seed for
  `reading-400 × qwen3-5-9b-65k` citing MC-38.
  - **Đóng** — không có điểm faithfulness để đưa lên UI.
