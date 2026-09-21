#!/usr/bin/env bash
# MC-14 run wrapper — VM14K raw shuffled0, Qwen3.5-9B-28K @ IEC endpoint.
# Run from the repo root: code_benchmark/run_vm14k_mc14.sh
#
# Why a wrapper: run_mc_eval.py writes fixed output names
#   all_res/ollama_result/<slug>/{full_evaluation,accuracy}_<slug>.csv
# so a VM14K run would overwrite the MC-9 (VMLU all_gold) finals. It also writes
# raw_result_<n>_<slug>.csv checkpoints, and VM14K's 12,488 would become the
# highest count for this model (current max 9,833 from MC-7), poisoning
# find_latest_checkpoint() for other suites. This wrapper:
#   1. backs up the MC-9 finals and restores them on exit (trap),
#   2. renames the VM14K finals to *_vm14k_*,
#   3. parks the new VM14K checkpoints in vm14k_checkpoints/.
#
# Usage:
#   ./run_mc14.sh              # full 12,488 (~50 min, 4 workers)
#   LIMIT=20 ./run_mc14.sh     # smoke test (same protection)
#   RESUME=1 ./run_mc14.sh     # ONLY after an interruption past ~9,833 questions
#                              # (below that, find_latest_checkpoint picks MC-7's
#                              #  checkpoint and restarts fresh — harmless, no gain)
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="Qwen3.5-9B-28K"
SLUG="Qwen3_5-9B-28K"
RES="all_res/ollama_result/$SLUG"
BK="v_med_vm14k/backup_mc9"
mkdir -p "$BK" "$RES/vm14k_checkpoints"

# 1) MC-9 finals backup (keep the first copy — never overwrite with a VM14K one)
[ -f "$BK/full_evaluation_$SLUG.csv" ] || cp "$RES/full_evaluation_$SLUG.csv" "$BK/"
[ -f "$BK/accuracy_$SLUG.csv" ] || cp "$RES/accuracy_$SLUG.csv" "$BK/"

# checkpoint snapshot so we can tell the VM14K ones from pre-existing ones
declare -A before=()
for f in "$RES"/raw_result_*_"$SLUG".csv; do
  if [ -e "$f" ]; then before["$f"]=1; fi
done

restore_mc9() {
  cp -f "$BK/full_evaluation_$SLUG.csv" "$RES/full_evaluation_$SLUG.csv"
  cp -f "$BK/accuracy_$SLUG.csv" "$RES/accuracy_$SLUG.csv"
}
trap restore_mc9 EXIT

args=(--folder v_med_vm14k --file vm14k_input.jsonl --workers 4
      --model "$MODEL"
      --submission-out "v_med_vm14k/submission_vm14k_$SLUG.csv")
if [ -n "${LIMIT:-}" ]; then args+=(--limit "$LIMIT"); fi
if [ -n "${RESUME:-}" ]; then args+=(--resume); fi

.venv/bin/python code_benchmark/run_mc_eval.py "${args[@]}"

# 2) rename VM14K finals (trap restores MC-9 on exit)
mv "$RES/full_evaluation_$SLUG.csv" "$RES/full_evaluation_vm14k_$SLUG.csv"
mv "$RES/accuracy_$SLUG.csv" "$RES/accuracy_vm14k_$SLUG.csv"

# 3) park the new VM14K checkpoints
for f in "$RES"/raw_result_*_"$SLUG".csv; do
  if [ -e "$f" ] && [ -z "${before[$f]:-}" ]; then
    mv "$f" "$RES/vm14k_checkpoints/"
  fi
done

echo "MC-14 done -> $RES/full_evaluation_vm14k_$SLUG.csv + accuracy_vm14k_$SLUG.csv"
