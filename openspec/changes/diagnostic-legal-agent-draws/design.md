## Context

See proposal.md for the motivation. The earlier cards and what MC-115 reads from them:

| Items | Arms with draws 1–2 | Card and folder | Score file (SHA-256) |
|---|---|---|---|
| 134 Legal MC (`vi-multimodel-v1-legal-mc-146`) | DSH, DSHF | MC-112, corpus_v1 | `01084c90…` |
| same | OMPF | MC-113, corpus_v1 | `303902b7…` |
| same | B, O | MC-111 (direct) | `4e755671…` |
| 112 VMLU law, Part M | DSH, DSHF, OMPF, B | MC-114, corpus_v2 | MC-114's `scores.jsonl`, by its report's `scores_sha256` |
| 400 ViBidLQA, Part S | DSH, DSHF, OMPF, C, O | MC-114, corpus_v2 | same |

- **Folders.** corpus_v1: 310 files, folder SHA-256 `5f3240a2…`. corpus_v2: corpus_v1's 310 files byte for byte plus 25 pages, folder SHA-256 `2b40c1c7…`. Both are on disk and hash as registered (checked 2026-11-16). Both are mounted read-only at `/work/van-ban-phap-luat`.
- **Prompt parity already holds.** MC-114's Part M tasks are MC-112's (`agent_task` reads MC-112's prompt file by SHA-256). MC-113's OMPF sent MC-112's DSHF task byte for byte. MC-111's B prompts equal the frozen MC prompts of the 134 items (268 of 268 rows, checked 2026-11-16).
- **Real cost per attempt** (reported tokens): Legal MC DSHF 95,908 and OMPF 81,637 (MC-112/113); MC-114 Part M DSHF 98,625, OMPF 65,912, B 138; Part S DSHF 56,981, OMPF 57,649, C 155. MC-111's B on Legal MC: 235.
- **Real time per attempt** (mean seconds): Legal MC DSHF 57, OMPF 61 (MC-112/113); MC-114 Part M DSHF 49.3, OMPF 42.6, B 3.8; Part S DSHF 38.7, OMPF 41.5, C 3.9.

## Goals / Non-Goals

**Goals:**
- Halve the draw-to-draw part of the noise in the per-item scores of DSHF, OMPF and the no-tool baseline, on the same items and in the same conditions.
- Test the harness (OMPF vs DSHF) and each agent against the direct call, on 4-draw item means.

**Non-Goals:**
- New items, new arms, or changes to any earlier condition.
- Revising the earlier cards' registered conclusions. MC-115 reports its own.

## Decisions

### 1. Items and arms
| Part | Items | Arms, draws 3 and 4 |
|---|---|---|
| M | 134 Legal MC + 112 VMLU law = 246 | DSHF, OMPF, B |
| S | 400 ViBidLQA | DSHF, OMPF, C |

Attempts: agents 2,584 (984 in Part M, 1,600 in Part S); direct 1,292 (492 B, 800 C).

### 2. Condition parity
Every new attempt repeats its item's draw-1 condition:
- **Task bytes:** the draw-1 item of the same arm and item, with only `replicate_id` changed.
- **Harnesses:** MC-112's dsh pins (protocol `42ec6e9b…`, registration `e5a48051…`) and MC-113's omp pins (protocol `23965e31…`, registration `4d2bfe09…`), as MC-114 used them. omp's registered system prompt `3d04a885…` is checked on every first request, as before.
- **Folder:** corpus_v1 for `vi-multimodel-v1-legal-mc-146`, corpus_v2 for every other dataset. The runner refuses to run when either folder's listing hash differs from the registration, and corpus_v2 is also rebuilt fresh, as MC-114 did.
- **Direct arms:** the campaign request of MC-90 to MC-114.
- **Limits:** temperature 1.0 by the proxy; 300 s per request; 30 requests and 3 hours per attempt; 4,096 completion tokens; no retries; a pause on a changed response model id.

### 3. Manifest
`diagnostic_legal_agent_draws.build_manifest`:
1. Rebuild MC-112's, MC-113's and MC-114's manifests with their own modules; each must equal its frozen file, or the build fails.
2. Take the draw-1 items: Legal MC DSHF from MC-112, Legal MC OMPF from MC-113; Part M DSHF, OMPF, B and Part S DSHF, OMPF, C from MC-114. B on Legal MC is the frozen MC prompt of the item (`diagnostic_legal_oracle.legal_items`), which MC-112's build already checks against MC-111's B.
3. Copy each to `-r3` and `-r4`. Order: item-major, Legal MC, then Part M VMLU, then Part S; per item draw 3 then draw 4; arms in the order above.
4. Record every source manifest's SHA-256, both folder hashes and the per-dataset folder map, and self-hash.

### 4. Runner
`run_legal_agent_draws.py` reuses MC-114's runner functions where they carry no card identity (`harness_protocols`, `check_harnesses`, `proxy_config`, `finish_agent_row`, `rescore`, `summarize`, the selftest) and writes its own `agent_row`, `make_request`, `score_callback`, gates and condition with MC-115's identity. Same engine, budget guard, outage guard, statuses and `--resume`. Scoring: the frozen MC scorer on Part M; vi-reading-v3 on Part S, with the v2 values beside.

### 5. Smoke test (before registration, no benchmark item)
MC-112's `smoke-2` (an MC question answered from corpus_v1) on corpus_v1, and MC-114's `smoke-s2` (a span question on Luật Đấu thầu 2023) on corpus_v2, each once with DSHF and once with OMPF: 4 attempts. It checks the VPN path, the per-item folder switch and omp's system prompt on this machine. No score is computed. A smoke attempt that cannot complete blocks registration.

### 6. Operation
At most 4 attempts in flight; stop after 4 timeouts; budget guard 270,000,000 reported tokens (176.4M projected from the real costs above × 1.5, rounded up). Run as a `systemd-run --user` unit with a VPN watcher.

### 7. Analysis (fixed before data, run once)
`analyze_legal_agent_draws`, plan `diagnostic-legal-agent-draws`.
- **Inputs, by SHA-256:** MC-115's scores; MC-112's and MC-113's score files (Legal MC DSHF and OMPF, draws 1–2); MC-111's (Legal MC B, draws 1–2); MC-114's (Part M VMLU and Part S, draws 1–2). Every item must have all 4 draws of every compared arm.
- **Item score:** the mean over draws 1–4. Part M: correctness. Part S: vi-reading-v3 token-F1, in points.
- **Part M (246 items), Holm over 3:** M1 OMPF vs DSHF; M2 DSHF vs B; M3 OMPF vs B.
- **Part S (400 items), Holm over 3:** S1 OMPF vs DSHF; S2 DSHF vs C; S3 OMPF vs C.
- **Statistics,** as MC-112 to MC-114: the mean per-item difference; a 95% percentile bootstrap over items (2,000 resamples, seed 7); a two-sided paired sign-flip p-value (20,000 resamples, seed 7).
- **Reading rule:** the left arm is better when its mean exceeds the right arm's by more than the margin with a Holm-adjusted p below 0.05, worse when it trails by more than the margin with such a p, and otherwise there is no clear difference. Margin 2.24 points on M1–M3 (the B-to-B gap between MC-101 and MC-111, as MC-112/113 used it against B); 0 on S1–S3.
- **Reported beside, not tested:**
  - the same six comparisons on draws 3–4 alone (fresh data);
  - the drift of each arm: mean of draws 3–4 minus mean of draws 1–2, with a bootstrap CI;
  - each arm's draw-to-draw disagreement rate (Part M) and within-item SD;
  - the comparisons by source (Legal MC, VMLU law).

### 8. Registration (MC-115)
A root block in `measurement_card.md`, the detail card `docs/measurement_cards/MC-115-diagnostic-legal-agent-draws.md` and `data/diagnostic_legal_agent_draws/registration.json`, with every frozen input hashed. The commit is titled `pre-register MC-115` and comes before the first benchmark-item request.

### Open choices for the owner (defaults are the recommendation)

(2026-11-16: the owner kept all four defaults.)

1. **Baseline draws** (default yes). B and C also get draws 3–4. They cost 1,292 short direct requests (about 0.2M tokens, a few minutes) and make the agent-vs-direct tests 4 draws against 4.
2. **Primary data** (default: draws 1–4). The tests use 4-draw means, which is what the noise reduction is for; the catch is that draws 1–2 were already seen, so these tests are not independent of the earlier cards. The alternative makes draws 3–4 alone primary: a clean replication, but at the old noise level (2 draws). Either way the other is reported beside.
3. **Margin against B** (default 2.24 on M1–M3). The alternative is 2.24 on M1 only, as in MC-114.
4. **Smoke test** (default yes, 4 attempts). The alternative is none, relying on the offline selftest and the gates.

## Risks / Trade-offs

- **Draws 1–2 were seen.** The questions were picked after seeing them (DSHF vs B is the one the noise blocked). Registering all six comparisons, not only the interesting one, and reporting draws 3–4 alone bound this, but do not remove it.
- **Time between rounds.** Draws 3–4 run 2–3 days after draws 1–2 (MC-114) and 3 days after MC-112/113, on the same endpoint and model id. A server-side change would show as drift; the drift is reported per arm.
- **B on Legal MC mixes cards:** draws 1–2 from MC-111, draws 3–4 from MC-115. This is why the 2.24 margin applies against B.
- **4 draws is a floor, not a cure.** Item-to-item variance stays; the detectable gap on Part M stays above 5 points.
- **Cost:** about 176M tokens and 8–9 hours over the VPN, guarded by the per-attempt caps, the budget guard and resumable launches.
