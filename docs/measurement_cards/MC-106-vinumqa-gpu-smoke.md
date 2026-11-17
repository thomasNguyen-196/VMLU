# MC-106 — ViNumQA / Qwen3-1.7B / Kaggle GPU development smoke

Registered 2026-10-31 (+07), before model inference or training requests of this condition.
This is an operational pilot of the new ViNumQA notebook, not a confirmatory thesis comparison.

| Field | Registered condition |
|---|---|
| Purpose | Verify GPU allocation, model loading, baseline inference, QLoRA training and a full Trainer checkpoint before spending quota on a complete experiment. |
| Destination | Private Kaggle notebook `tungnguyen05/vinumqa-baseline-setup-p-g-b-c`, kernel ID `141804648`; save and run a new version through Kaggle MCP. |
| Model | Hugging Face `Qwen/Qwen3-1.7B`, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`; tokenizer at the same revision; non-thinking mode; 4-bit NF4 base weights. |
| Data | ViNumQA mirror at commit `281bdcd70abde7753d95014dbd9babec7f97f3fd`. Source SHA-256 values and grouping are frozen in `data/vinumqa_distill_v1/gpu_smoke_mc106.json`. Split priority test > validation > train; group by the path parent of each question ID. Expected rows: train 2,038; validation 485; test 497. |
| P smoke | First 32 validation rows in ascending SHA-256(item ID) order; one greedy generation each; seed 42, 4,096 total context budget including a 256-token response reserve. No final test. |
| G_all smoke | Gold train programs passing the registered adapter's self EA and PA audit, then fit within 4,096 training tokens. Expected 2,017 before the tokenizer/context filter. QLoRA rank 16, alpha 32, dropout 0.05, all-linear targets; LR 2e-4, warmup 3%, micro-batch 1, accumulation 8; seed 42; maximum 20 optimizer steps. Prompt labels are masked with -100. |
| Validation in training | Validation loss once at the training epoch boundary, on usable reference programs fitting context; it is diagnostic and not a selected best-EA checkpoint. No post-training final-test run. |
| Checkpoint | Save full Trainer checkpoint at step 20, including optimizer/scheduler/RNG; save the final adapter separately. Resumability is not claimed merely from an adapter file. |
| Scorer | FinQA evaluator commit `0f16e2867befa6840783e58be38c9efb9229d742`, source SHA-256 `845cd131cab843eceff256cf6d392978cc470a7da4a80107beb56027fdca5c13`; adapter `finqa-vinumqa-string-rowalias-v1`: numeric-string gold normalization and table-row aliases. This adapter is not asserted equivalent to the shared task's official scorer. |
| Limits | Request Kaggle shape `NvidiaTeslaT4`, use visible CUDA device 0 only, Internet enabled, TPU disabled, session timeout 1,800 s. Current quota was read as 108,000 s total, 0 used/reserved; allocation remains subject to Kaggle. No teacher calls and no B/C training. |
| Failure policy | Stop on package/model/GPU/authentication/identity failure. Do not rerun completed predictions or silently change a registered condition. A corrected execution condition gets its own label and amendment before relaunch. |
| Interpretation | Report actual GPU, dependency versions, P's smoke denominator/EA/PA, optimizer steps, elapsed time, excluded IDs and checkpoint files. No statistical superiority or generalization claim from this pilot. |
| Provenance | Runtime condition files contain card ID/detail hash, registry hash, model/tokenizer revision, split hash, prompts, adapter hash and runtime. The pre-launch registration pins the actual notebook source hash; launch receipts store the Kaggle version/session. |
| Outputs | Local receipt root `all_res/vinumqa_distill_v1/mc106_gpu_smoke/`; Kaggle working root `/kaggle/working/vinumqa-baselines/mc106-vinumqa-gpu-smoke-v1/`. Save/Run output is retained as a Kaggle version. No public publishing. |

The existing VMLU, Reading-400, V-Bench and router measurement cards are unaffected.
