## Context

Current verified state (2026-09-20):

- Model: `Qwen3.5-9B-28K` (non-thinking; probe `max_tokens=4` → answer) via IEC
  OpenAI-compatible endpoint. `.env` `OPENAI_MODEL` still points at the dead
  Qwen3.8 — always pass `--model Qwen3.5-9B-28K`.
- Done on Qwen3.5: reading-400 (MC-3 pipeline, scorer `score_reading_eval.py`,
  builder `build_dashboard_reading.py`), legal-MC-146 (adapter pattern MC-10,
  builder `build_dashboard_legal.py` with `--card/--max-tokens/--model-id`).
- Gold on disk: `v_legal_slsp/bidlqa/{test 603, val 482, train 1928}` rows
  `{context, question, answer}` all non-empty, no ids; `v_legal_slsp/legal_slm/nli.jsonl`
  150 rows `{legal_document, specific_question, question≡1, choices=[Có,Không],
  answer 0/1}` balanced 75/75; syllogism 144 free-text answers (no short gold).
- D7 from the prior change still holds: sequential runs on the IEC endpoint,
  no parallel inference against one gateway.

## Goals / Non-Goals

**Goals:** every remaining gold-bearing set Qwen3.5 can run with EXISTING
runners gets a full run, a card, and a dashboard block: bidlqa-test, bidlqa-val,
legal-nli.

**Non-Goals:** syllogism judge (separate change — needs judge-model decision);
train split (not an eval set); SQuAD/DROP-full (no gold); dialog (no gold, no
runner); seatau telecom (explicit user exclusion); regime B/C; contract changes.

## Decisions

**D1. BidLQA rides the reading pipeline, two separate runs.** Manifest per split
(test 603 → MC-11, val 482 → MC-12) with stable ids + pinned sha; same open-book
prompt + 48-token budget + temp 0/seed 42 as MC-3 so numbers compare. Scorer
takes `--gold` pointing at the manifest-derived gold (file gold, not review
gold) — no scorer change if it already accepts `--gold`; else a `--gold` flag
is the only allowed edit (scoring math untouched).

**D2. NLI rides the frozen MC runner via letter map.** Adapter emits
`{id: LG-NLI-XXXX, question: legal_document + specific_question + question,
choices: ["A. Có","B. Không"], answer: A/B}` — the question concatenation order
is frozen in the adapter and recorded in MC-13. Runner, prompt, parser, and
max-tokens 4 all identical to MC-10. Baseline recomputed (≈50%), never hardcoded.

**D3. Dashboard: two new keys, no reshaping.** `bidlqa: {test:{...}, val:{...}}`
and `legal_nli: {...}` alongside existing keys; builders gain `--card/--model-id`
like the legal builder did. Old keys byte-identical after patch (assert in task).

**D4. Order: NLI first (150q, ~3 min), then bidlqa-val (482), then bidlqa-test
(603).** Smallest run validates the endpoint first; each run commits its card
before the next starts. Dashboard patches batch at the end.

## Risks / Trade-offs

- [BidLQA gold is file-native, not reviewed] → report as file-gold EM (like MC-10
  manifest gold), never as reviewed-gold; caveat in the block.
- [NLI question concatenation is a new prompt surface] → frozen string in adapter
  + recorded verbatim in MC-13; any reformulation = new card.
- [Endpoint flakiness] → per-model checkpoints + `--resume` on both runners.
- [Syllogism temptation] → explicitly out; no half-built judge in this change.

## Migration Plan

One commit per track (NLI, bidlqa-val, bidlqa-test, dashboard batch). Rollback =
revert the track commit; CSVs stay source of truth. No schema dependency.

## Open Questions

- Should val run before test (smaller pilot) — default yes per D4.
- Does `score_reading_eval.py` already accept `--gold`? — answered in task 1.1
  (read flags first; add only if missing).
