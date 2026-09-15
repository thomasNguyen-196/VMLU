#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

mkdir -p logs all_res/ollama_result

echo "=== [$(date)] Starting Full Evaluation Pipeline for Qwen3-8-27B Q4_K_M ==="

# 1. VMLU-MQA Full Test Split (9,833 questions)
echo "=== [$(date)] 1/4: Running VMLU-MQA test.jsonl (9,833 items) ==="
python3 code_benchmark/run_mc_eval.py \
  --folder vmlu_datasets/vmlu_mqa_v1.5 \
  --file test.jsonl \
  --workers 4 \
  --resume \
  --submission-out data/submission_mqa_qwen3_8_27b.csv

# 2. VMLU Reading Vi-SQuAD Full (3,310 questions)
echo "=== [$(date)] 2/4: Running Vi-SQuAD Full (3,310 items) ==="
python3 code_benchmark/test_generative.py \
  --task squad \
  --folder vmlu_datasets/vmlu_squad_v1 \
  --workers 4 \
  --run-tag qwen3_8_27b \
  --resume

# 3. VMLU Reading Vi-DROP Full (3,309 questions)
echo "=== [$(date)] 3/4: Running Vi-DROP Full (3,309 items) ==="
python3 code_benchmark/test_generative.py \
  --task drop \
  --folder vmlu_datasets/vmlu_drop_v1 \
  --strategy baseline \
  --workers 4 \
  --run-tag qwen3_8_27b \
  --resume

# 4. VMLU Reading Vi-Dialog Full (210 conversations)
echo "=== [$(date)] 4/4: Running Vi-Dialog Full (210 conversations) ==="
python3 code_benchmark/test_generative.py \
  --task dialog \
  --folder vmlu_datasets/vmlu_dialog_v1 \
  --workers 4 \
  --run-tag qwen3_8_27b \
  --resume

echo "=== [$(date)] Full Evaluation Pipeline Completed Successfully ==="
