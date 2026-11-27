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
- [x] 3.2 With the owner's go, commit `pre-register MC-118`. Every preflight gate must pass for both models.

  (2026-11-25, owner: "ok". Commit `c474867` on `dev`, not pushed.)

## 4. Run (ask the owner first)

- [x] 4.1 Launch both models as `systemd-run --user` units (Qwen with the VPN), with a relauncher for budget, breaker and technical stops.

  (2026-11-25 at 22:37 +07. Units `mc118-qwen-launch1` (`--execute --tunnel-dns 172.16.30.1`) and `mc118-mimo-launch1` (`--execute`), with relaunchers `mc118-{qwen,mimo}-relauncher` (`all_res/diagnostic_reading_agent/run/mc118_relauncher.py`, operational). All 8 gates passed for each. The first 30+ attempts per model completed with no error. Mean tokens per agent attempt so far: Qwen DSHF 11.9k, OMPF 15.6k, OMPS 20.5k; MiMo 6.5k, 21.5k, 18.1k. Both runs are well inside their guards.)
  - **Amendment 1** (`e6943a4`, 2026-11-26 about 00:40 +07, owner: "Amendment nâng trần 140M"). At 1.93 h, MiMo's omp attempts averaged 48–50k tokens against the smoke's 24–29k, projecting 91.6M against the 85M guard. MiMo's guard became 140M (×1.5 rule); Qwen kept 110M (projection 46.7M). Launch 1 keeps 85M in memory, so it pauses there and the relauncher resumes under 140M.
  - **Progress at 00:34:** Qwen 2,572/4,000, no error; MiMo 964/4,000, with 3 technical `APIConnectionError` rows.
  - **Qwen complete:** 4,000/4,000 at 01:49:59 +07 on 2026-11-26, 48.1M tokens, no error row. The relauncher closed the VPN.
  - **MiMo launch 1** paused at 05:23 on its 85M guard (85,951,523 counted; 2,551 complete). Launch 2 refused the checkpoint with "checkpoint condition drift": one blocked direct row (`…drop-200:1598:C-r1`, `budget_cap`) had no `model_id`. The relauncher stopped.
  - **Amendments 2 and 3** (`01b0220`, owner: "Sửa lỗi + trần 350M, chạy tiếp").
    - Amendment 2: MiMo's guard became 350M. Vi-DROP agent attempts cost 155–184k tokens against viSQuAD's 17–38k, and the manifest lists viSQuAD first; the projection is 231.1M, ×1.5.
    - Amendment 3: direct blocked rows now carry the model id, and budget amendments chain. The blocked row was moved to `attempts_moved_aside.jsonl`; no request had been sent for it.
  - **MiMo launch 3** from about 11:35 +07 (`mc118-mimo-launch3`, relauncher `mc118-mimo-relauncher2`, starting at launch 4). Gates 8/8; `budget_tokens=350000000 used=85951523`; the checkpoint loaded and attempts resumed.
  - **Host reboot** at 11:23:36 +07 (kernel 7.0.0-43 → 7.0.0-44) killed launch 3 at 2,564 complete. Launch 4 (`mc118-mimo-launch4`, 11:32) was refused by the omp proxy on every OMPS retry, because omp's `<workstation>` OS and Kernel lines changed the system prompt (`f9dfeea9…`). The relauncher stopped for the owner.
  - **Amendment 4** (`1363bb9`). The owner ruled: "ghi phiên bản kernel làm gì, cứ chạy tiếp trên kernel mới thôi. Việc kernel của máy ta không cho vào". The pin check now reads those two lines as the registered host's; the pins themselves are unchanged.
  - **MiMo launch 5** from about 11:45 (`mc118-mimo-launch5`, relauncher `mc118-mimo-relauncher4` from launch 6). Gates 8/8; omp attempts complete again. A few OMPS attempts keep hitting `APIConnectionError` (technical, re-run).
- [x] 4.2 Record the runs in the detail card. Close the VPN at the end.

  (Run record appended 2026-11-26 at about 23:40 +07. Qwen complete at 01:49:59 and the VPN closed; MiMo complete at 23:28:27 after launches 1–7 and amendments 1–4.)

## 5. Analysis, judge sample and record

- [x] 5.1 Run the analysis once. Record the report's SHA-256 and the results.

  (Report `9c376d4c…`. R: H1 +2.43, H2 −0.47, H3 −2.89 not detected, H4 not read. Token-F1: H2 +5.07, Holm p 0.0004.)
- [x] 5.2 Build the 600-answer judge sample. Judge it blind with four Opus 5.5 instances under the 2026-11-25 rubric, join the labels, and record the judge report.

  (Judge report `dd8219cb…`; κ 0.98 between judges. Flags: R's bias on OMPS − OMPF for both models, which affects H4 and P1/P2. Judge estimates: H1 +3, H2 +1, H3 −2, H4 −10.)
- [x] 5.3 With the owner's go, update the thesis draft (Chapter 5) and Notion.

  (2026-11-27, owner: "commit, rồi cập nhật Chương 5 và Notion".
  - Run record committed as `c77a41d`.
  - Chapter 5 built as `kltn_draft/chuong_5_agent_harness.md`, untracked by design: old sections 3.7.8 and 4.8 gathered, tables renumbered 5.1–5.16, new section 5.8 on MC-118 and 5.9 on discussion. Sections 3.7.8 and 4.8 now hold pointers to it; section 4.9, Chapter 1's structure and the table of contents were updated.
  - Notion core page: new §22 on MC-118, appendix renumbered §23. Plan page: Chapter 5 milestone row updated.)
