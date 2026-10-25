#!/usr/bin/env bash
# Periodically report the expansion-v2 OpenCode Go campaign without sending requests.
# Run from any directory: code_benchmark/watch_vi_multimodel_go_campaign.sh [interval_minutes]
set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
OUTPUT_ROOT="$REPO_ROOT/all_res/vi_multimodel_v2"
SUBMISSION_ROOT="$REPO_ROOT/submissions/vi_multimodel_v2"
LOG_DIR="$REPO_ROOT/logs/vi_multimodel_v2"
LOG_PATH="$LOG_DIR/watch-go-campaign.log"
WATCH_INTERVAL_MINUTES="${1:-15}"

if [[ ! "$WATCH_INTERVAL_MINUTES" =~ ^[1-9][0-9]*$ ]]; then
  printf 'Error: interval must be a positive integer number of minutes\n' >&2
  exit 2
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  printf 'Error: repository Python environment not found: %s\n' "$PYTHON_BIN" >&2
  exit 2
fi

WATCH_INTERVAL_SECONDS=$((WATCH_INTERVAL_MINUTES * 60))
mkdir -p "$LOG_DIR"

notify_desktop() {
  local title="$1"
  local body="$2"
  if command -v notify-send >/dev/null 2>&1; then
    notify-send --app-name="VMLU benchmark" "$title" "$body" || true
  fi
}

while true; do
  snapshot="$("$PYTHON_BIN" - "$OUTPUT_ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
profiles = (
    "muse-spark-1-3-contributor",
    "mimo-v2-6-flash",
    "mimo-v2-5",
)
expected = {"vmlu": 10_880, "vbench": 5_141}
terminal_error_states = {"paused", "incomplete", "incomplete_exhausted", "probe_failed"}
all_complete = True
has_paused_run = False
lines = []

for profile in profiles:
    for phase, expected_n in expected.items():
        run_dir = root / phase / profile
        run_path = run_dir / "run.json"
        attempts_path = run_dir / "attempts.jsonl"
        if not run_path.is_file():
            all_complete = False
            lines.append(f"{profile} {phase}: queued 0/{expected_n}, errors=0")
            continue

        try:
            metadata = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print("STATE=paused")
            print(f"{profile} {phase}: cannot read run metadata: {exc}")
            raise SystemExit(0)

        status = str(metadata.get("status", "unknown"))
        if status != "complete":
            all_complete = False
        if status in terminal_error_states:
            has_paused_run = True

        latest = {}
        if attempts_path.is_file():
            raw = attempts_path.read_bytes()
            complete = raw.endswith(b"\n")
            rows = raw.splitlines()
            if not complete and rows:
                rows = rows[:-1]
            for line_no, line in enumerate(rows, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    print("STATE=paused")
                    print(f"{profile} {phase}: corrupt ledger at line {line_no}: {exc}")
                    raise SystemExit(0)
                key = str(row.get("run_key", ""))
                if key:
                    latest[key] = row

        complete_n = sum(row.get("status") == "complete" for row in latest.values())
        error_n = sum(row.get("status") != "complete" for row in latest.values())
        total_n = int(metadata.get("item_count", expected_n))
        lines.append(f"{profile} {phase}: {status} {complete_n}/{total_n}, errors={error_n}")

print("STATE=paused" if has_paused_run else "STATE=complete" if all_complete else "STATE=running")
print("\n".join(lines))
PY
)"

  now="$(date --iso-8601=seconds)"
  printf '[%s]\n%s\n' "$now" "$snapshot" | tee -a "$LOG_PATH"

  state="${snapshot%%$'\n'*}"
  if [[ "$state" == "STATE=paused" ]]; then
    notify_desktop "VMLU OpenCode Go campaign paused" "A run needs attention. See $LOG_PATH"
    exit 1
  fi

  if [[ "$state" == "STATE=complete" ]]; then
    manifests_ready=1
    for profile in muse-spark-1-3-contributor mimo-v2-6-flash mimo-v2-5; do
      if [[ ! -f "$SUBMISSION_ROOT/$profile/submission_manifest.json" ]]; then
        manifests_ready=0
        break
      fi
    done
    if (( manifests_ready )); then
      notify_desktop "VMLU OpenCode Go campaign complete" "All Go runs and local score/submission artifacts are ready. Qwen was not started."
      exit 0
    fi
    printf 'Submission artifact export is still running; checking again in %s minutes.\n' "$WATCH_INTERVAL_MINUTES" | tee -a "$LOG_PATH"
  else
    notify_desktop "VMLU benchmark progress" "OpenCode Go campaign status updated. See $LOG_PATH"
  fi

  sleep "$WATCH_INTERVAL_SECONDS"
done
