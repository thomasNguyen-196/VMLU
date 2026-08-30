## Context

`test_ollama.py` is a single self-contained script (see CLAUDE.md pipeline). Today it never reads the input's `answer` field; results rows are `{id, question, prompt, raw_response, answer}` where `answer` = model's parsed letter. The gold field exists only in `dev.jsonl`/`valid.jsonl` (1,047 records, all present). Checkpoints (`raw_result_<N>.csv`) are mid-run snapshots merged back via `--resume`. Constraints: `build_prompt`/`extract_answer` are byte-frozen contracts; CI runs `test_parsing.py` + `test_suite.py` on every PR.

The 58-subject → 4-category mapping has one trap: the repo-root `dataset_stat.csv` lists subjects in a **different order** than the official VMLU numbering, and it is the `id` prefix (official numbering: 01–21 STEM, 22–31 Social Science, 32–49 Humanities, 50–58 Other) that is authoritative — verified against real records (e.g. `28-0001` is macroeconomics questions, `15-0001` electrical engineering).

## Goals / Non-Goals

**Goals:**
- Scoring computed from one pure function so it is unit-testable without an API endpoint.
- Zero behavior change on the non-scorable (test.jsonl) path — same files, same columns, same prints plus none.
- Old checkpoints remain consumable after this change.

**Non-Goals:**
- No per-run statistics beyond accuracy (no bootstrap CI, no confusion matrices — results-reporting problem, not pipeline).
- No new CLI flags unless a decision below forces one (it does not).

## Decisions

**D1. Scorable detection in `load_questions`.** After loading, `scorable = all("answer" in r and str(r["answer"]).strip() for r in records)`. Mixed → warn once, treat as non-scorable. Rationale: fail-safe toward the existing behavior; the leaderboard path must never accidentally change. Alternative (per-record scoring where gold exists) rejected — partial accuracy tables invite silent misreading.

**D2. `SUBJECT_CATEGORY` as a verified constant, not `dataset_stat.csv`.** Embed `SUBJECTS: dict[int, tuple[str, str]]` (number → (english_name, category)) in `test_ollama.py`, built from the official README table (counts: STEM 21, Social Science 10, Humanities 18, Other 9 = 58). `dataset_stat.csv` is ignored by code (wrong ordering). Alternative (ship a separate CSV mapping) rejected — one source of truth beats a config file for a constant that changes only with a benchmark version bump; a unit test asserts the group sizes.

**D3. Scoring at end-of-run over merged results.** `score_results(rows, gold_by_id) -> list[dict]` compares case-insensitively on the letter; empty parsed answer → incorrect. Called once after all futures resolve and after checkpoint merge — never inside the per-item worker (avoids thread-safety concerns and keeps mid-run snapshots simple). Row dicts gain `gold_answer` + `correct` only when scorable, so snapshots/resume of scorable runs also carry them going forward; for pre-existing checkpoints lacking the columns, D3's end-of-run recompute over the merged set makes them correct anyway (spec "Resume compatibility").

**D4. Outputs.** Scorable runs additionally write `all_res/ollama_result/accuracy_<model>.csv` — long format: `level` (overall/category/subject), `name`, `n`, `correct`, `accuracy`. Console prints overall line + 4-category table after "Time taken". Non-scorable runs write nothing new. `submission.csv` logic untouched in both paths (its `answer` column remains the model's).

**D5. Tests in `test_suite.py` only** (needs package import; CI already runs it from repo root). Coverage: mapping invariants (58 subjects, 21/10/18/9 split), empty answer = incorrect, resume merge recompute, `unknown` bucket for out-of-range prefixes, and category-sum-equals-total roll-up. `test_parsing.py` untouched — parity contract stays the standalone reference.

## Risks / Trade-offs

- [Local numbers (1,047) ≠ leaderboard numbers (10,880) may drift] → expected by design; docs must keep calling the local set "dev+valid probe", never "VMLU score".
- [`extract_answer` returns `''` on refusal/format-break, counted incorrect] → correct semantics for MC accuracy; the raw_response column preserves evidence for manual triage.
- [Constant mapping goes stale if VMLU renumbers subjects] → accepted; benchmark is versioned (`v1.5` folder names), and the unit test documents the source.
- [Checkpoint CSVs gain two columns for scorable runs → old tooling reading them may assume schema] → outputs are gitignored local artifacts; no external consumers.

## Migration Plan

Purely additive; one commit. Rollback = revert the commit (no persisted-schema dependency: non-scorable path unchanged, scorable CSVs are regenerable).

## Open Questions

- Whether `--limit` smoke runs should still print the accuracy summary (they will — harmless); revisit only if noise bothers.
