## Context

See `proposal.md` for motivation. `diagnostic-protocol-ledger-pilot` froze the 60 anchors (MC-72 source, seed 42, 12 per dataset, 15 blind-human keys) and the readiness gates; its `inference_ready` requires `audit_complete` plus every prospective control in `data/diagnostic_v1/protocol.json`, all of which are unset. The SHA-256 of that file binds the review page, `import-review` and adjudication (`_read_pilot`), the assistant-suggestion manifest and the browser and Mongo draft keys, so it must not change while the human review is in progress.

Existing machinery to reuse: the frozen main-v1 manifest (2,043 items, replicate id `main-000`, `EvalItem` records with prompt, gold and task), the frozen extractors and scorers in `vi_multimodel.py` and `score_vi_multimodel.py`, and the MC-80/82/83 direct-API engine (`execute`: lock file, condition freeze, shards by lanes workers, attempt ledger, resume). Two properties of the frozen scorers shape the design: `score_rows` groups summaries by dataset only and would therefore pool arms, and the multiple-choice parser takes the first key-phrase match, which misreads a response that discusses other options before its final answer.

Measured on 2026-10-22 (24 synthetic prompts, 3 workers, Responses API, temperature 1.0): the endpoint reports `/home/llm/llama.cpp/models/Qwen3.5-9B-Q4_K_M.gguf`, reports no reasoning tokens, answers B-style prompts in 2 to 7 tokens (mean latency 3 s) and S-style prompts in 140 to 970 tokens (mean latency 7 s); effective parallelism was 2.93 of 3. These numbers calibrate budgets only; they are not benchmark results.

## Goals / Non-Goals

**Goals:** a campaign whose every request is traceable to frozen hashes; arms that differ only in the declared way; automatic scoring wherever gold exists so effect sizes do not wait for humans; a held-out split; fail-closed gates; analysis code fixed before data.

**Non-Goals:** everything under Non-goals in the proposal; a human review UI for campaign outputs; any change to the frozen scorers or prompts.

## Decisions

### 1. Two phases on one engine
`core` is the 60 anchors (development set, three replicates). `wide` is the other 1,239 items of the same five datasets (held-out with respect to rule design, one replicate, arms B and S only). Alternative: one pooled manifest; rejected because replicate policy, gating (core needs `inference_ready`, wide needs only a registered card) and role (development versus held-out) differ.

Sizes: core = 60x2x3 = 360 (B, S) plus 12x3 each for O, K and KS = 468 attempts, or 396 when K and KS are left out of the first registration (the draft's proposal, because they need a frozen corpus and a separate card); wide = 1,239x2x1 = 2,478 attempts (per dataset 134 Legal MC, 138 Legal NLI, 188 Vi-SQuAD, 188 Vi-DROP, 591 ViBidLQA). From the probe: core takes well under one hour and wide about one to four hours at 3 to 12 workers (serial worst case about 3.5 h); expected usage is about 2 M tokens in total.

### 2. Arm encoded in the replicate id
`replicate_id = <ARM>-r<k>` (for example `S-r2`), so run keys stay `dataset:item:replicate` and the engine, the ledger identity triple and the manifest equality check work unchanged; arm items are `EvalItem` copies made with `dataclasses.replace` (new replicate id and arm prompt). Alternative: one run directory per arm; rejected because arms would execute hours apart and endpoint drift would be confounded with arm. Items are ordered item-major (item, replicate, arm) and the engine's contiguous shard split plus lane striding keeps the attempts of one item adjacent in time. Summaries are produced by calling the frozen `score_rows` once per arm on an arm-filtered manifest.

### 3. Transport and sampling
Direct API on `http://llmapi.iec/v1`: OpenAI Responses API, streaming, `temperature=1.0`, no seed, no reasoning field, system prompt "Answer the user's question.", header `x-9router-token-saver: off`, SDK retries 0, 300 s timeout, 12 workers (4 shards x 3 lanes), `max_output_tokens=4096` for every arm and dataset (the largest observed S output was 966 tokens; 4,096 equals the historical multiple-choice cap). The shape is that of MC-83 so the engine adapter is reused, with the cap parameterised instead of the MC-82 module constant. Alternative: the OMP harness; rejected because it adds an agent scaffold as a confound and is slower.

### 4. Prompts
B is the frozen main-v1 prompt, byte-identical and verified by hash. S replaces the answer-only instruction by a decomposition instruction and a pinned final line and drops the trailing completion cue; the question, options or passage are untouched, so S adds no information. O and K prepend one frozen evidence block to the B prompt; KS prepends the same block to the S prompt. Construction is string surgery on the frozen prompt with head and tail assertions that fail closed. Template text lives in `data/diagnostic_prospective_v1/prompt_templates_v1.json` and its SHA-256 is part of the condition. Draft wording (Vietnamese, to be validated and then frozen):

- S, multiple choice: "Trả lời câu hỏi trắc nghiệm sau. Hãy phân rã bài toán thành các bước nhỏ, kiểm tra từng bước dựa trên thông tin đã cho trong đề, rồi kết luận. Dòng cuối cùng của câu trả lời phải đúng một dòng có dạng `Đáp án: X` (X là một chữ cái A, B, C, D hoặc E), không thêm ký tự hay định dạng nào khác."
- S, reading: "Đọc đoạn văn dưới đây và trả lời câu hỏi. Hãy phân rã câu hỏi thành các bước nhỏ, đối chiếu từng bước với đoạn văn, rồi kết luận. Dòng cuối cùng phải đúng một dòng có dạng `Trả lời: <cụm từ hoặc số ngắn gọn, lấy nguyên văn trong đoạn văn khi có thể>`, không dùng định dạng markdown và không viết thêm gì sau dòng đó."
- Evidence block: "Căn cứ tham khảo (có thể chưa đầy đủ):" followed by numbered provisions (document, locator, verbatim text) and a blank line.

Wording is developed only on synthetic prompts (no benchmark text) until final-label compliance reaches at least 95% on a synthetic set of at least 36 prompts, then frozen before any benchmark-item request. Alternative: tune S on the anchors; rejected as design on the evaluation set.

### 5. Scoring wrapper
B, O and K use the frozen chain on the raw response. S and KS take the response after the last final-answer label (the frozen label pattern). A multiple-choice response with no label is unparsed (empty prediction, incorrect, kept in the denominator) and the first-match parser is not applied to the whole response; reading uses the frozen last-label extraction unchanged. Each scored row adds `arm`, `format_ok` and `scoring_source` and keeps the raw text. Format compliance (label present; no markdown on the reading final line) is a separate summary field so a prompt-compliance loss is not mistaken for a reasoning loss. Alternative: a lenient fallback to the whole response; rejected because it reintroduces the first-match misread and would move S up or down for parser reasons.

### 6. Gates and registration order
`--execute` requires the card heading in `measurement_card.md` plus the detail card; endpoint host and model equal to the card; frozen manifest, template and evidence hashes; and, for `core`, `inference_ready`. Because registering controls edits `data/diagnostic_v1/protocol.json` and changes its hash, the order is: (a) human review finished, imported and adjudicated so that `audit-report.json` is final; (b) controls filled in `protocol.json` (the pilot is rebuilt afterwards only if the demo page is still needed); (c) cards registered and committed with title `pre-register MC-NN`; (d) `wide` may run as soon as (c) holds, `core` once `inference_ready` is true. Until (a) the decisions live in `preregistration-draft.json` in this change.

### 7. Evidence: oracle first, retriever second
Oracle evidence is the verbatim provisions the reviewer cites for the 12 Legal MC anchors (recorded in the audit `evidence_reference`), so it needs no retriever. Corpus v0 is the full text of the same documents plus a small set of distractor documents, chunked by article; retrieval is lexical (BM25 over articles) with a hashed configuration; the gap between oracle and K isolates retrieval from evidence need. K and KS are a pilot with about six B-incorrect items and their results are descriptive. Alternative: a corpus for all 146 Legal MC questions; rejected because the set spans many legal areas and only 24 questions name a numbered document, which is a separate project.

### 8. Analysis plan, fixed before data
The unit of analysis is the item. The outcome is the majority of correct replicates (core) or the single attempt (wide). Exact two-sided McNemar for each of S, O, K and KS versus B within the multiple-choice family and the reading family, Holm correction over the arm comparisons, Wilson intervals for proportions, passage-cluster bootstrap (2,000 resamples, seed 42) for reading differences; per-dataset results are descriptive only. The rule-based router is written down before outcomes are unblinded, tuned on core and evaluated once on wide. Oracle-routing ceilings are reported next to the same ceiling over B replicates. Discordant pairs are exported in both directions for semantic review. Reference and secondary analyses were added before registration, after the MC-83 baseline showed a ceiling in the multiple-choice family and a strict exact-match scorer in reading: attempt-level rescue and regression between B replicates as the noise reference; a compliant-only sensitivity analysis; for reading, the paired token-F1 difference and a format-suspect flag on rescues; and, on wide only, a parity gate comparing B per dataset with the MC-83 interval. The multiple-choice family has only about thirty B-incorrect items on wide, so a null result there is reported as insufficient power, not as no effect.

### 9. Process-local endpoint resolution
The tunnel pushes no DNS, so the runner can map the endpoint host to the answer of the in-tunnel DNS server (`172.16.30.1`, documented in MC-88) inside its own process, leaving the `Host` header unchanged and the system resolver and hosts file untouched.

## Risks / Trade-offs

- [S final-label non-compliance depresses S accuracy] → measure compliance separately, freeze the wording only after the synthetic-set threshold, report accuracy over all attempts.
- [Temperature 1.0 makes single draws noisy] → three replicates on core; wide relies on n, not replication.
- [Endpoint drift or a model swap behind the gateway] → record `response_model_id` per attempt, pause on a change, interleave arms in time, list drift under threats to validity.
- [A shared VPN profile may evict another user] → the operator connects and disconnects deliberately; runs are short.
- [Small K sample] → label it a pilot, use the oracle-first contrast, make no population claim.
- [Hash binding of `protocol.json`] → the registration order in Decision 6; nothing in this change edits that file.
- [Evidence leaks the answer] → the validator rejects letters and rationales; evidence is verbatim provisions.
- [Wide items were seen by earlier runs] → declared held-out with respect to rule design only, not pristine.

## Migration Plan

Additive only; nothing existing is edited. Rollback is deleting the new files. Verified 2026-10-22: `git status` shows no tracked file changed by this change; the SHA-256 of `data/diagnostic_v1/protocol.json` still equals the pilot's `selection.protocol_sha256`, so the review page, review import and the reviewer's drafts are unaffected; frozen prompts and scorers are untouched; B-arm prompt hashes equal main-v1 for all 1,299 items; with the draft controls merged into an in-memory copy of `protocol.json`, the readiness report's only remaining blocker is the completed, independently reviewed pilot audit. Run outputs go to new ignored directories under `all_res/` and are never mixed with MC-72 or MC-83 outputs.

## Open Questions

- Lexical versus dense retrieval, decided when corpus v0 is frozen.
- Whether core replicates stay at three after the synthetic compliance run.
- Whether `wide` later adds VMLU valid for a closed-book contrast without evidence arms.
- Measurement-card ids, assigned at registration.
