## Purpose

Measure, with enough items to settle gaps of about 6 points, whether requiring Qwen3.5-9B to search a complete local folder of Vietnamese legal texts changes its answers (DSHF against DSH), and whether the harness matters (omp's OMPF against dsh's DSHF). This is done on new multiple-choice items pooled with MC-112/113's Legal MC items, and on closed-book ViBidLQA span items, where finding the governing article decides most of the score. The registration is fixed before the first request.

## ADDED Requirements

### Requirement: Corpus folder corpus_v2
The run SHALL use corpus_v2, which is MC-112's corpus_v1 with every one of its 310 files byte-identical, plus the 25 pages of `added_documents_v2.json`. Each page SHALL be read from its stored copy, checked against its fetch-log SHA-256. The build SHALL fail when:
- a corpus_v1 file differs;
- an MC-101 article is not whole;
- site text is left;
- MC-101's leak check fails on the Legal MC and VMLU items, other than the exemptions recorded in the folder manifest.

Before any request, the runner SHALL rebuild the folder in a fresh directory and SHALL refuse to run when its folder SHA-256 differs from the registration.

#### Scenario: A stored page changed
- **WHEN** a stored page's bytes differ from its fetch-log SHA-256
- **THEN** the build fails and no folder is written

#### Scenario: A corpus_v1 file came out different
- **WHEN** any corpus_v1 file in the new folder has a SHA-256 other than corpus_v1's
- **THEN** the build fails

### Requirement: New items
Part M SHALL hold the 112 gold VMLU items of subjects 37–42 and 45 from dev and valid, each with its frozen main-v1 MC prompt. Part S SHALL hold the first 400 usable ViBidLQA items in SHA-256 order of `legal-agent-v2-bidlqa|<dataset_id>:<item_id>`. A ViBidLQA item SHALL be usable only when all of the following hold:
- its context is headed by an article of Luật Đấu thầu 22/2023/QH15;
- its question appears once across train, val and test;
- that article exists in the official text with the same title;
- the article holds the answer verbatim after NFC and whitespace normalization.

The item sets SHALL be frozen in the manifest with their SHA-256.

#### Scenario: A decree context
- **WHEN** a ViBidLQA context is headed by the guiding decree
- **THEN** the item is not usable

#### Scenario: A repeated question
- **WHEN** a ViBidLQA question appears in more than one row across the splits
- **THEN** none of those rows is usable

### Requirement: Item provisions
`item_provisions_v2.jsonl` SHALL hold MC-112's keys for every new item.
- **VMLU items.** Provisions SHALL come from the four audit batches. The owner's spot-check labels SHALL replace the agents' labels. A `no_provision` item SHALL have no provision.
- **ViBidLQA items.** The provision SHALL be the heading line of the named article of `luat-dau-thau-2023.txt`.

Every anchor SHALL be a whole line of its corpus_v2 file. No gold letter or gold span SHALL be in the file. Provisions SHALL be read only by the analysis.

#### Scenario: An anchor is not a line
- **WHEN** an anchor is not a whole line of its file
- **THEN** writing the provisions fails

### Requirement: Arms and tasks
Each item SHALL run two draws of each arm of its part:
- **Part M:** DSH, DSHF, OMPF and B.
- **Part S:** DSH, DSHF, OMPF, C and O.

Prompts:
- An agent task SHALL be the arm's MC-112 instruction, a blank line, then the item prompt: the frozen MC prompt in Part M, MC-96's registered closed-book prompt in Part S, checked by the SHA-256 of `data/diagnostic_k2/protocol.json`.
- OMPF's task SHALL equal DSHF's byte for byte.
- B SHALL send the frozen MC prompt, C the closed-book prompt, and O the frozen reading prompt with the item's own passage. All three SHALL go through the campaign request of MC-90 to MC-111.
- No prompt SHALL carry a gold, a provision, a label or an audit note.

#### Scenario: Task drift
- **WHEN** an attempt's task text differs from its manifest entry
- **THEN** the omp proxy refuses the request, or the dsh path refuses the attempt, and the run pauses

### Requirement: Reused harness paths
dsh attempts SHALL run MC-112's dsh install, profile, sandbox, relay and proxy, checked by MC-112's registered hashes. omp attempts SHALL run MC-113's binary, configuration, sandbox and proxy request-shape checks, checked by MC-113's registered hashes. MC-112's and MC-113's modules SHALL be imported and not edited. The folder mounted read-only at `/work/van-ban-phap-luat` SHALL be corpus_v2.

#### Scenario: A reused module changed
- **WHEN** the SHA-256 of an MC-112 or MC-113 module or install differs from its registration
- **THEN** the runner refuses to start

### Requirement: Scoring
Part M answers SHALL be scored by the frozen MC extractor and scorer. Part S answers SHALL be scored by vi-reading-v3, with token-F1 as the primary metric. An attempt that ends with a terminal status SHALL score 0 and SHALL stay in the denominator. Only technical failures SHALL be re-run.

#### Scenario: A verbose span answer
- **WHEN** an agent's final text contains the gold span inside a longer explanation without a final-answer label
- **THEN** it is scored as written, losing precision, and is not edited

### Requirement: Smoke test and budget
Before registration, three smoke questions drawn from no benchmark SHALL run once with DSHF and once with OMPF on corpus_v2. The budget guard SHALL be set to 1.5 times the projection the smoke test gives. The smoke test SHALL produce no score. It SHALL run only after the owner has agreed to open the VPN.

#### Scenario: Tool calls fail on corpus_v2
- **WHEN** either harness cannot complete a smoke attempt
- **THEN** the card is not registered and the owner is told

### Requirement: Registered analysis
The analysis SHALL be fixed before data and run once.
- **Part M** SHALL test OMPF against DSHF, with the 2.24-point margin, and DSHF against DSH, on the pooled 246 items, with Holm over the two p-values. The pooled scores SHALL be MC-112's and MC-113's scores on the 134 Legal MC items, read by registered SHA-256, and this card's scores on the 112 VMLU items.
- **Part S** SHALL test OMPF against DSHF, DSHF against DSH, and DSHF against C, on its 400 items, with Holm over the three p-values.
- **Statistics.** Each test SHALL use the mean per-item difference over two-draw item scores, a 95% percentile bootstrap (2,000 resamples, seed 7) and a two-sided paired sign-flip p-value (20,000 resamples, seed 7).
- **Report.** The report's top-level keys SHALL be recorded in the registration.

#### Scenario: A reference score file changed
- **WHEN** MC-112's or MC-113's score file differs from its registered SHA-256
- **THEN** the analysis refuses to run

### Requirement: Registration before the first request
The MC-114 root block, its detail card and `registration.json` SHALL be committed as `pre-register MC-114` before the first benchmark-item request. The registration SHALL record the SHA-256 of every frozen input. The runner SHALL refuse to run when any is missing or differs.

#### Scenario: Unregistered run
- **WHEN** `--execute` is given and the registration is missing or a hash differs
- **THEN** the runner refuses and no request is sent
