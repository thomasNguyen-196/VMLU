## Why

Earlier cards measured what Qwen3.5-9B does with legal evidence that someone else selected:

- **MC-100.** The governing provisions, located with the gold, lifted the Legal MC items Qwen had missed from 37% to 83%.
- **MC-101.** BM25's top two units (K) scored 84.7 against 84.3 for closed-book B.
- **MC-111.** Shown BM25's top ten, Qwen selected the governing article no better than BM25's order. Answering from its own selection did not beat B (B 86.6, K 88.1, SEL and K10 near B).
- **MC-88.** With `omp` and web tools, Qwen never searched.

None of these let the model search for itself in a place where the answer is known to be. On 2026-11-11 the owner asked for exactly that. Qwen runs inside DeepSeek Harness (`dsh`), a light open-source agent harness, with only `glob`, `grep` and `read`. Its working folder holds the full texts of the Vietnamese legal documents that govern the 134 Legal MC items. The folder is complete on purpose: every item is answerable from it, so the test is the best case "if the model does not know".

The question has two parts:

1. Does the model know to search, find the governing provision and read it?
2. Does that make its answers better than closed-book B?

## What Changes

- **Items.** The 134 Legal MC items of MC-101 and MC-111, with two draws each. They are not fresh: the same pool motivated MC-101 and MC-111.
- **Corpus folder** (`corpus_v1`, built and checked offline before this proposal). It has 310 plain-text files, one per document, holding the whole text of each document: preamble, chapters, articles, signature and annexes. That is 44.5 million characters, and the folder SHA-256 is `5f3240a2…`.
  - **Sources.** MC-101's 303 pages, plus 6 hethongphapluat.com pages added by a gold-aware coverage audit, plus 3 full texts from other sites where hethongphapluat.com withholds the passage.
  - **What is removed.** The site's injected instruction to AI readers is removed. No question stem or answer-key line is in the folder.
- **Provisions** (`item_provisions_v1.jsonl`, built offline). For each item, the provisions that govern it, each as a file and an exact anchor line of that file:
  - **Coverage.** 134 items and 180 provisions. 126 items support the gold, 2 contradict it and 6 are unclear.
  - **Sources.** MC-100's oracle evidence (53 items), and four gold-aware agent batches (81 items).
  - **Owner check.** The owner checked 14 of the 81 items and agreed with all 14.
  - **Use.** Only the analysis reads this file. The model never sees it.
- **Arms.** Two new arms, each with two draws, 536 attempts in all:
  - **DSH (search allowed).** A short instruction says that the working folder holds the full texts of Vietnamese legal documents, one per file, and that the model may search them with `glob`, `grep` and `read` if it finds that useful. The frozen main-v1 MC prompt follows.
  - **DSHF (search required).** The same opening, then: the model must find the governing provision with `grep` and read it with `read` before it answers. The frozen prompt follows.
  - **B and O are not re-run.** MC-111's B (268 attempts) and O (106 attempts) are the reference, read from MC-111's score file by its registered hash, as the owner decided on 2026-11-12.
- **Harness.**
  - **Version.** dsh 0.2.2-rc.1, from the vulnerability-patched install whose lockfile is hashed. The headless profile is patched to keep only `glob`, `grep` and `read`.
  - **Switched off.** Web, bash, sub-agents, AGENTS.md loading and session titles.
  - **Isolation.** Each attempt runs in its own sandbox with no network. It gets a fresh home, the folder mounted read-only, and an empty environment.
- **Proxy.** A loopback proxy outside the sandbox is the attempt's only way out.
  - **What it changes.** It adds `temperature: 1.0` to each request, which is what MC-90 to MC-111 requested, and swaps in the real API key. Nothing else in the request changes.
  - **What it records.** Every request and response.
  - **Limits.** A per-request timeout and a per-attempt request cap.
- **Smoke test before registration.** A few requests to the IEC endpoint through the whole path, with questions written for the smoke and no benchmark item. It checks that the endpoint returns tool calls and records the read format and step costs. It needs the VPN, so the owner is asked first.
- **Analysis.** Fixed before data and run once.
  - **Three Holm-adjusted questions:**
    1. DSHF against DSH, within this card.
    2. DSH against MC-111's B.
    3. DSHF against MC-111's B.

    Questions 2 and 3 cross cards, so they also require the difference to exceed the 2.24-point gap between MC-101's and MC-111's B on the same 134 items.
  - **Description:** whether each attempt searched, found and read a governing provision; accuracy when it did and when it did not; tool use and cost; each arm against MC-111's O on its 53 items.
- **Card.** MC-112, registered and committed before the first benchmark-item request.

## Capabilities

### New Capabilities
- `diagnostic-legal-agent`: the corpus folder and provisions, the dsh profile, the sandbox and proxy, the two arm prompts, attempt statuses, the trajectory parser and hit rules, the manifest and runner gates, and the registered analysis.

### Modified Capabilities
- None. The following are reused unchanged:
  - the frozen main-v1 MC prompt, the extractor and the scorer;
  - the campaign engine;
  - MC-101's source list and corpus units;
  - MC-100's oracle evidence;
  - MC-111's outputs, which are read only.

## Evaluation regime

Regime B-style only, as MC-90 to MC-111: Qwen3.5-9B-65K served as Q4_K_M GGUF on llama.cpp through the IEC endpoint. Regimes A and C are not touched.

## Non-goals

- **No control arms that take the harness apart.** There is no dsh without tools and no dsh with an empty folder. The owner rejected these on 2026-11-11: dsh without tools is just B.
- **No re-run of B or O.** MC-111's values are the reference.
- **No web access** and no tool other than `glob`, `grep` and `read`.
- **No tuning on any outcome.** The prompts, the profile, the caps and the folder are not changed after seeing an outcome. The smoke test uses questions written for it, and it sets only the token budget.
- **No other harness** (`pi`, `omp`) and no second model in this card. Either can follow if this one is informative.
- **No change** to the frozen files of MC-100, MC-101 or MC-111.
- **No training or fine-tuning.**

## Impact

- **New code:**
  - `code_benchmark/diagnostic_legal_agent.py` already holds the folder builder and provisions. It gains the prompts, the manifest, the trajectory parser and the hit rules.
  - `code_benchmark/dsh_proxy.py`: the loopback proxy and the in-sandbox relay.
  - `code_benchmark/run_legal_agent.py`: the runner, the sandbox launcher and the smoke test.
  - `code_benchmark/analyze_legal_agent.py`: the analysis.
  - Offline tests for each of these.
- **New data** in `data/diagnostic_legal_agent/`. Already there: `added_documents_v1.json`, `offsite_documents_v1.json` and `item_provisions_v1.jsonl`. To add: `protocol.json`, `agent_prompts_v1.json`, `dsh_profile_v1.yml`, `manifest_v1.json` and `registration.json`.
- **Outputs.** The corpus folder, the source stores, the audit and the run outputs go to `all_res/diagnostic_legal_agent/` (gitignored). The audit holds the gold and stays out of the repo.
- **Requests.**
  - **Volume.** 536 dsh attempts, each several model requests, so an estimated 3,000 to 8,000 requests. Tokens may reach tens of millions, most of them re-sent context.
  - **Budget.** The smoke test sets the token budget before registration.
  - **Time.** Several hours with four attempts in flight. The run needs the VPN.
- **Comparison limits** (written into the card):
  - The API differs: Chat Completions here, the Responses API for MC-111.
  - The system prompt differs: dsh's English persona here, `Answer the user's question.` for MC-111.
  - B is from another card, so drift is possible.
  - The folder is gold-aware and complete. It is an upper bound for real search.
  - Three texts come from sites other than hethongphapluat.com.
  - The pool is not held out.
  - VLSP 2025 LegalSLM forbids external access at inference, so both arms are diagnostic conditions outside the benchmark's rules.
