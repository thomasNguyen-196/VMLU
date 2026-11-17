# MC-107 — ViNumQA / FP16 eval-only / P against the version-6 G_all step-20 adapter

Prepared 2026-10-31 (+07), before inference under this condition. The notebook is saved for the owner to run manually; no GPU session is started by this edit.

| Field | Registered development condition |
|---|---|
| Question | On the same 32 validation items, how do answer accuracy, program accuracy and DSL validity change after the existing 20-step G_all SFT? This is a development smoke, not a confirmatory thesis comparison. |
| Notebook | Private `tungnguyen05/vinumqa-baseline-setup-p-g-b-c`, kernel `141804648`; new source saved with Quick Save. |
| Arms | P: original base model. G_all: the existing final step-20 adapter from notebook output version 6. No training, no teacher request, no B/C, no final test, no checkpoint search. |
| Base model | `Qwen/Qwen3-1.7B`, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, tokenizer at the same revision; 4-bit NF4 with double quantization; non-thinking. Both arms explicitly use FP16 compute. Native BF16 is not inferred from emulation support. |
| Source adapter | `tungnguyen05/vinumqa-baseline-setup-p-g-b-c/versions/6`, relative directory `vinumqa-baselines/mc106-vinumqa-gpu-smoke-v1/training/G_all/seed-42-2bc1a7d7d347/adapter`. Source training condition SHA-256 `2bc1a7d7d347e1ddad1fb7714d8ddd020121c7e5bff4aa8962bd92677d8aeb95`; source step 20. |
| Adapter identity | SHA-256 over `adapter_config.json` followed by `adapter_model.safetensors`, including each basename as in the existing adapter_fingerprint function: `11a5904761c3d5fc00964262e0b97b311593de4a192592cdb8ce4e829dbded1e`. Base identity, dataset split, terminal step and weight bytes are checked before model loading. Source training used BF16; this new condition changes inference precision for both P and G_all. |
| Restore | Reuse verified working files or mounted version-6 output; otherwise use KaggleHub with the version-6 handle and integrated Kaggle authentication. No credential is embedded. If auto-mount is unavailable, the notebook stops with an Add Input / Notebook Output instruction. |
| Dataset | Same pinned ViNumQA source hashes, source-disjoint split and metric adapter as MC-106. Manifest SHA-256 `ec29d6e2f6287b17dcbab41e959a0e53efac8e6bd8b42ef9521730c48e2415fd`. |
| Items | First 32 of 485 validation rows ordered by SHA-256(item ID), exactly as the BF16 development sample. P and G_all must have identical item IDs, rendered prompts and denominator. No test outcome is opened. |
| Generation | Seed 42; greedy; max 256 new tokens; total context budget 4,096 including output reserve. Same prompt, tokenizer, quantization, dtype, runtime and generation limits for the pair. |
| Metric | `finqa-vinumqa-string-rowalias-v1`, pinned FinQA EA/PA adapter. Empty/invalid/overflow remain in the denominator. Record EA, PA, valid rate, EA rescues/regressions and raw responses; no significance claim from n=32. |
| Comparison | Both P and G_all are generated under this FP16 condition. The BF16 P result of MC-106 is historical context only, not the paired comparator. |
| Resource control | Save only; the owner controls GPU connection and Run All. At execution, use one visible CUDA device and process the arms sequentially. TRAIN_ARMS is empty; EVAL_ARMS contains G_all; ALLOW_FINAL_TEST is false. |
| Provenance | Per-arm condition binds actual prompts, model/tokenizer revision, runtime/dtype and adapter bytes. Local registration pins the final notebook source and execution hash after card hashes are filled. |
| Outputs | Separate working namespace `/kaggle/working/vinumqa-baselines/mc107-vinumqa-fp16-eval32-v1/`; `runs/P`, `runs/G_all`, `source_adapter.json`, `paired_eval_summary.json`. No MC-106 artifact is overwritten. |

No result of MC-107 has been observed at preparation time.
