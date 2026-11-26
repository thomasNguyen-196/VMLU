# MC-118, exploratory: a blind judge on all 4,800 agent answers (results)

Run on 2026-11-26/27 under `plan.md` (sha256 `cd097ac8…`, written before judging). This pass is **exploratory and not part of MC-118's registration.** The registered analysis (report `9c376d4c…`) and the registered judge sample (`dd8219cb…`) stand.

## Setup

- **Code and outputs.** Code `code_benchmark/judge_reading_agent_full.py`. Outputs under `all_res/diagnostic_reading_agent/judge_full/` (gitignored); report SHA-256 `d1843e78650b242ee4e85510720ab51fe1727ce720eb4d7315419498276f7b6e`.
- **Answers.** Every DSHF, OMPF and OMPS answer of Qwen3.5-9B-65K and MiMo-V2.6-Flash on the 400 Reading-400 items, both draws: 4,800. C and O were not judged.
- **Judges.** 14 fresh Claude Opus 5.5 instances, one shard of 28–29 items each. Each item showed its 12 answers in a seeded order, with no model, arm, draw or score. The rubric was 2026-11-25's, unchanged.
- **Cost.** 1,658,457 subagent tokens in all, 111–127k per instance; the plan estimated 1.6–1.8M.
- **Reliability.** The registered sample's 600 answers were judged again by different instances, and the two passes agree on 595 of 600 (99.17%), κ 0.98.

## Judge accuracy (points, mean over 400 items × 2 draws)

| | DSHF | OMPF | OMPS |
|---|---|---|---|
| Qwen | 53.00 | 54.12 | 59.50 |
| MiMo | 82.88 | 82.88 | 82.75 |

## MC-118's tests on judge labels (exploratory; bootstrap and sign-flip as registered, Holm over four)

| Test | Judge | 95% CI | Holm p | R (registered) |
|---|---|---|---|---|
| H1 Qwen OMPF − DSHF | +1.12 | [−2.75, 5.25] | 1.000 | +2.43, Holm 0.572 |
| H2 MiMo OMPF − DSHF | 0.00 | [−1.62, 1.50] | 1.000 | −0.47, Holm 0.999 |
| H3 interaction ι | −1.12 | [−5.50, 2.88] | 1.000 | −2.89, Holm 0.572 |
| H4 P3 | **−5.50** | [−9.38, −1.62] | **0.030** | −1.27, not read |

**Beside:**
- P1, Qwen OMPS − OMPF: **+5.38** [1.75, 9.00], p 0.005.
- P2, MiMo: −0.12 [−1.62, 1.38].
- Remaining interaction (OMPS − DSHF, MiMo minus Qwen): −6.62 [−11.00, −2.38].

## Readings

1. **The judge confirms the registered conclusion.** On general reading neither model's harness gap is detectable, and there is no model × harness interaction (H3 ≈ −1, interval across 0). The legal cards' reversal does not recur.
2. **New, exploratory: dsh's system prompt inside omp helps Qwen by about 5 points** (59.5 against 54.1) and leaves MiMo unchanged. This is the direction MC-117 found on legal texts, where Qwen started paging itself under dsh's prompt. R saw the same direction but smaller, +2.78 [−0.5, 6.0]. Because MC-118's registered reading rule does not read H4 without H3, this stays an exploratory finding.
3. **R's bias on the full set is similar across arms.** It ranges from −2.26 to −4.86 points (R below the judge in every cell). The differences between arms within a model are under 3 points: Qwen OMPS − OMPF −2.60; MiMo OMPS − OMPF +1.64; MiMo OMPF − DSHF −0.46. The registered sample's flags (5.5–5.6 points on 100 items) were mostly sampling noise. R still under-reads Qwen's OMPS gain by about 2.6 points. κ for R ≥ 0.5 against the judge is 0.74–0.81 per cell.
4. **Why agents miss.** Most wrong answers come from reading a different passage of the same kind, typically another US-census paragraph, and answering from it. Vi-DROP's census-style passages are near duplicates of each other.
5. **Gold.** The judges flagged 88 answer rows as `gold_suspect`, almost all on about ten items: the seven flagged on 2026-11-25, plus 8ee880ad, bf212871, ef91b2fd and b5fa6be2.
