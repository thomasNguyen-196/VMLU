# MC-86 — Muse Spark 1.3 Contributor, OMP full tools, remaining MC-85 items

Registered 2026-10-16 (+07) before the first benchmark-item request, following the user's request to run Muse Spark 1.3 with OMP full tools on the MC-85 population not already covered by MC-71.

| Field | Condition |
| --- | --- |
| Model / route | Muse Spark 1.3 Contributor; provider model ID `muse-spark-1.3-contributor`, OMP model ref `zen-go/muse-spark-1.3-contributor`; OpenCode Go Responses. The OMP provider route differs from MC-85's direct `ocg/mimo-v2.6-flash` route. |
| Harness | OMP 18.0.0, JSON mode; `--tools all` omits an explicit tool list and uses OMP's full default menu; default coding-agent system prompt; `--auto-approve`; no session, title, extensions, skills, rules, or LSP. |
| Credential boundary | Resolve OpenCode Go authentication in the parent process and forward model requests through a loopback streaming proxy. OMP and its tools receive only an ephemeral local relay key; the upstream key is not present in the agent environment or scratch directory. |
| Item isolation | Run OMP in a Bubblewrap user/PID/mount namespace. Bind only the item scratch, isolated OMP profile, fake HOME, and read-only runtime files; keep network available for the model relay and full tools. The host home, repo, datasets, and gold files are not mounted. |
| Scope | 12,033 items from MC-85: VMLU Valid 744, Legal NLI 150, Vi-SQuAD 200, Vi-DROP 200, ViBidLQA Test 603, VMLU Dev 303, and VMLU Test 9,833. Exclude the 146 Legal MC items already run in MC-71. MC-71 IDs and prompt hashes were checked against MC-85 before exclusion. No V-Bench or pilot items. |
| Inputs and prompts | Freeze the MC-85 manifests and item order; preserve each frozen user prompt byte-for-byte; send no gold. Each OMP process gets an isolated scratch directory with only its item prompt. Local gold is retained only for local scoring. |
| Sampling | Temperature 1.0 set in the isolated OMP profile; `--thinking auto`; seed omitted. The provider's effective sampling and reasoning settings are not independently observable. |
| Token and time limits | Model `maxTokens=20000` per assistant turn; `--max-time 300` seconds/item plus a 60-second subprocess timeout margin. OMP can make multiple assistant calls per item, so cumulative output across an item can exceed 20,000 tokens; retain all reported usage. |
| Workers and scheduling | 12 worker threads/processes pull from one global queue ordered by the frozen manifests. A worker takes the next pending item when its current item ends, including items from another dataset. No fixed worker-to-dataset assignment. Record worker ID, dataset, active peak, and item timing. |
| Retries | No SDK retries. Only failed technical attempts identified as transient may be retried, up to three total attempts; completed responses, truncations, and unparsed answers are terminal. Never retry for correctness. Stop on authentication, permission, billing, or model-configuration errors. |
| Scoring | Frozen V1 scorer for Main local-gold datasets and frozen V2 scorer for Dev/Test. Keep unparsed model responses in local-gold denominators. Test gold remains withheld; no local Test accuracy is claimed. Create a local `id,answer` Test submission only after complete Test coverage; do not upload it. |
| Provenance and outputs | Record filtered MC-85 parent manifests, source prompt hashes, MC-71 exclusion ledger hash, condition/card/runner/scorer hashes, per-attempt usage and tool audit, and all output files under `all_res/muse13_omp_mc86/`. OMP preflight is a non-benchmark request and is excluded from the 12,033 items. |
| Comparison limits | This is a tool-enabled multi-turn OMP run, not an API-direct replication. The OMP system prompt, provider route, thinking mode, multi-call token accounting, and dynamic scheduler differ from MC-85; do not describe any score difference as a model-only effect. OpenCode Go tariff is not available, so no dollar cost is inferred. |

