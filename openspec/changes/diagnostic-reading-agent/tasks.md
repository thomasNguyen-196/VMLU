The arms below run on two routes:
- **Qwen:** IEC `Qwen3.5-9B-65K` over the VPN (MC-115's route).
- **MiMo:** OpenCode Go `mimo-v2.6-flash` (MC-116's route).

Arms: DSHF (dsh 0.2.2-rc.1), OMPF (omp 18.0.0), OMPS (OMPF + `--system-prompt` with dsh's prompt), C and O (direct).

## 0. Owner decisions

- [x] 0.1 The owner asks for the legal-agent experiment on another field, with OMPS.

  (2026-11-25: "lên plan cho phần thực nghiệm với harness giống phần luật đi (bao gồm đổi system prompt của omp thành dsh luôn)". The owner chose long files, "File dài, giống luật", and R as the score with a judge on a sample, "R chính + giám khảo trên mẫu".)
- [x] 0.2 The owner approves this design: the corpus and layout, the reworded DSHF instruction, the five arms and two draws, H1–H4 in two families, and the judge sample.

  (2026-11-25: "duyệt".)

## 1. Build (offline)

- [x] 1.1 `diagnostic_reading_agent.py`, with tests:
  - the corpus (design §1): 2,284 passages, 46 files, headings, one sentence per line, the passage index and the folder hash;
  - the item-to-passage map;
  - the BM25 retrievability strata;
  - the NFC report.

  (2026-11-25. Folder `cc9b461c…`; index `67de96e1…`; 1 non-NFC passage and no non-NFC question. BM25 strata: top-1 318 (viSQuAD 194/200, Vi-DROP 124/200), top-5 38, beyond 44 (all Vi-DROP).)
- [x] 1.2 `data/diagnostic_reading_agent/`:
  - the protocol;
  - `agent_prompts_v1.json` (the reading DSHF instruction, MC-112's separator, MC-96's closed-book prompt by SHA-256);
  - the corpus index;
  - the smoke questions.

  (Also `retrievability_v1.json` `9df2365a…` and `judge_sample_v1.json` `fd6090a3…`, both fixed before data, and smoke questions `7301237f…`. The protocol leaves the pins and budgets null until the smoke test.)
- [x] 1.3 The manifest: 400 items × 5 arms × 2 draws per model, in the seeded arm order, every task checked against the prompts.

  (4,000 attempts, 800 per arm. Build-time hash `f372deee…`. It is frozen after the smoke test, because the protocol hash is one of its inputs.)
- [x] 1.4 `run_reading_agent.py --model qwen|mimo`, with tests:
  - the corpus folder;
  - the OMPS overlay;
  - the direct arms;
  - MC-117's stall rule, halted-row identity and budget hook;
  - a self-test against scripted servers, including the paging check (design §1).

  (The work directory is set in-process, design §1. **Paging check.** The first layout, one line per passage, failed: omp cut 19% of lines at 768 characters and showed 200-line files whole. The owner chose one sentence per line on 2026-11-25. With it, the self-test passes for both models, and omp pages at 300 lines while dsh caps at about 41k characters. The system messages equal the legal cards' byte for byte: Qwen `d6bd65aa`, `3d04a885`, `b868301f`; MiMo `54d89951`, `616bebaf`, `32a43405`.)
- [x] 1.5 `analyze_reading_agent.py`: the registered analysis (design §7), the judge-sample builder and its join (design §8), with tests on synthetic cells. Also a dry run on relabelled MC-88/89 answers, where they map onto items.

  (The dry run used DSHF, C and O from the direct runs MC-83/85, and OMPF and OMPS from the omp runs MC-88/89, with both draws the same. The whole path ran, report keys included, and H4 came out 0 as built. These numbers check the code, not a result.)
- [x] 1.6 Checks:
  - the new tests, `test_suite`, `test_parsing`, ruff and bandit;
  - the self-test with the paging check (if omp shows whole files, stop for the owner);
  - the offline preflight for both models.

  (2026-11-25. New tests 21/21; `test_suite` 287 OK; `test_parsing`, ruff and bandit clean; the MC-112 to MC-117 runner tests OK. Preflight for both models, `endpoint_calls=0`: identity passes. Card, frozen hashes, budget, smoke, pins and the frozen manifest wait for §2–§3.)

## 2. Smoke test (ask the owner first; the VPN for Qwen)

- [x] 2.1 `--smoke --execute` per model: 4 questions × 5 arms, 40 attempts, no benchmark item. Record the reports and their SHA-256.

  (2026-11-25 about 22:17 +07, after the owner's go ("okay"). MiMo ran without the VPN; Qwen ran with it open, and it was closed afterwards.
  - **MiMo** `b0762674…`: 20/20 complete.
  - **Qwen** `f4e476d5…`: 12/12 agent attempts complete; C and O got 8 × HTTP 500 from IEC's Responses API.
  - **Retry** `4839248e…` (`--smoke-arms C,O`): 8 × HTTP 500 again.
  - On the owner's choice ("Thử lại, lỗi nữa thì đổi route"), Qwen's C and O moved to chat completions on the same endpoint (protocol `models.qwen.direct`), and `66907603…` completed 8/8.

  Every first system message equals the legal cards' pins, and omp paged corpus files.)
- [x] 2.2 From the reports:
  - dsh's system message in `/work/bai-viet` against MC-117's files, which decides OMPS's prompt file;
  - the pins;
  - the budgets.

  Freeze `manifest_v1.json`.

  (dsh's message equals MC-117's files, so OMPS uses them.
  - **Pins:** Qwen `d6bd65aa` / `3d04a885` / `b868301f`, MiMo `54d89951` / `616bebaf` / `32a43405`.
  - **Budgets:** Qwen 110,000,000 (smoke basis 105.7M) and MiMo 85,000,000 (80.4M), basis in `protocol.smoke.budget_basis`.
  - **Manifest frozen:** self-hash `32c70e10…`, file `abaf2f97…`.)

## 3. Registration

- [x] 3.1 The MC-118 root block, the detail card and `registration.json`.

  (2026-11-25. The root block was appended to `measurement_card.md` with no other line changed. Detail card `docs/measurement_cards/MC-118-diagnostic-reading-agent.md`. `registration.json` `55d9fda0…`. Full preflight for both models: 8 of 8 gates pass, `endpoint_calls=0`. New tests, `test_suite`, ruff and bandit OK; `openspec validate --strict` OK.)
- [ ] 3.2 With the owner's go, commit `pre-register MC-118`. Every preflight gate must pass for both models.

## 4. Run (ask the owner first)

- [ ] 4.1 Launch both models as `systemd-run --user` units (Qwen with the VPN), with a relauncher for budget, breaker and technical stops.
- [ ] 4.2 Record the runs in the detail card. Close the VPN at the end.

## 5. Analysis, judge sample and record

- [ ] 5.1 Run the analysis once. Record the report's SHA-256 and the results.
- [ ] 5.2 Build the 600-answer judge sample. Judge it blind with four Opus 5.5 instances under the 2026-11-25 rubric, join the labels, and record the judge report.
- [ ] 5.3 With the owner's go, update the thesis draft (Chapter 5) and Notion.
