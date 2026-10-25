"""Continue MC-89-R1 after the machine shutdown: process the remaining unselected keys.

The first R1 pass stopped at 412/475 attempts when the host powered off at
2026-10-20 18:29 UTC. This continuation keeps the same recovery condition
(MC-89-R1, 1800 s override), appends to the same recovery ledger, and skips
every key that already has an R1 attempt.

From the repository root:
  .venv/bin/python -m code_benchmark.retry_mimo26_omp_mc89_1800s_resume
  .venv/bin/python -m code_benchmark.retry_mimo26_omp_mc89_1800s_resume --execute
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any

from code_benchmark import retry_mimo26_omp_mc89_1800s as r1
from code_benchmark import run_mimo26_omp_mc89 as mc89


RECOVERY_DIR = r1.RECOVERY_DIR
RECOVERY_PATH = r1.RECOVERY_PATH
EXPECTED_UNPROCESSED = 63
CONTINUATION_ID = "MC-89-R1-C1"


def _now() -> str:
    return r1._now()


def _combined_rows() -> tuple[dict[str, dict], Any]:
    rows, counts, _attempts = r1._load_latest_attempts()
    ledger = mc89.read_jsonl(RECOVERY_DIR / "attempts.jsonl")
    for row in ledger:
        run_key = str(row.get("run_key", ""))
        if not run_key:
            raise SystemExit("Error: R1 ledger row without run_key")
        rows[run_key] = row
        counts[run_key] += 1
    return rows, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run the continuation pass")
    args = parser.parse_args()

    if not RECOVERY_PATH.is_file():
        raise SystemExit("Error: the MC-89-R1 recovery record is missing; nothing to continue")
    recovery = json.loads(RECOVERY_PATH.read_text(encoding="utf-8"))
    if recovery.get("status") != "running":
        raise SystemExit(f"Error: MC-89-R1 is not an interrupted running pass ({recovery.get('status')})")
    if "continuation" in recovery:
        raise SystemExit("Error: the R1 continuation already ran; refusing a duplicate")

    data, _latest_parent, _counts_parent, targets, runtime, _retry_items = r1._prepare()
    processed = {row["run_key"] for row in mc89.read_jsonl(RECOVERY_DIR / "attempts.jsonl")}
    pending = [row for row in targets if row["run_key"] not in processed]
    if len(pending) != EXPECTED_UNPROCESSED:
        raise SystemExit(f"Error: expected {EXPECTED_UNPROCESSED} unprocessed keys, found {len(pending)}")
    if r1._has_live_campaign_process():
        raise SystemExit("Error: an MC-89 campaign/recovery process is already active")

    effective_condition = json.loads((RECOVERY_DIR / "condition.json").read_text(encoding="utf-8"))
    effective_hash = mc89.v1.sha256_bytes(mc89.v1.canonical_json(effective_condition))
    if effective_hash != recovery.get("recovery_condition_sha256"):
        raise SystemExit("Error: R1 recovery condition hash differs from the recovery record")

    rows, attempts_by_key = _combined_rows()
    requests_by_key = {row["run_key"]: row for row in data["requests"]}
    retry_items = [requests_by_key[row["run_key"]] for row in pending]
    parent_hash = recovery["parent_condition_sha256"]

    plan = {
        "continuation_id": CONTINUATION_ID,
        "parent_recovery_id": recovery["recovery_id"],
        "reason": "host shutdown interrupted the R1 pass at 412/475 attempts",
        "selected_n": len(pending),
        "selected_run_keys": [row["run_key"] for row in pending],
        "recovery_condition_sha256": effective_hash,
        "workers": mc89.WORKERS,
        "max_time_seconds_per_item": r1.RECOVERY_TIMEOUT_SECONDS,
        "previous_r1_ledger_sha256": mc89.sha256_file(RECOVERY_DIR / "attempts.jsonl"),
        "runner_sha256": mc89.sha256_file(Path(mc89.__file__)),
        "continuation_driver_sha256": mc89.sha256_file(Path(__file__).resolve()),
        "status": "planned",
    }
    print(
        f"{CONTINUATION_ID} plan: items={len(retry_items)} attempt=2 workers={mc89.WORKERS} "
        f"max_time={r1.RECOVERY_TIMEOUT_SECONDS}s condition_sha256={effective_hash} endpoint_calls=0",
        flush=True,
    )
    for row in pending[:10]:
        print(f"  {row['run_key']} {row.get('error_type')} latency_s={row.get('latency_s')}", flush=True)
    if not args.execute:
        print("Plan only; no model endpoint was called.", flush=True)
        return

    mc89.MAX_TIME_SECONDS = r1.RECOVERY_TIMEOUT_SECONDS
    mc89.OUTPUT_ROOT = RECOVERY_DIR
    mc89.MAIN_OUT = RECOVERY_DIR / "main" / mc89.PROFILE
    mc89.VMLU_OUT = RECOVERY_DIR / "vmlu" / mc89.PROFILE
    mc89.AGENT_ROOT = RECOVERY_DIR / "omp_workers"
    mc89.LOG_PATH = mc89.ROOT / "logs/mimo26_omp_mc89_recovery_1800s.log"
    r1._patch_parsing()
    original_run_item = mc89._run_item

    def run_recovery_item(*call_args: Any, **call_kwargs: Any) -> dict[str, Any]:
        row = original_run_item(*call_args, **call_kwargs)
        row.update({
            "recovery_id": r1.RECOVERY_ID,
            "continuation_id": CONTINUATION_ID,
            "parent_condition_sha256": parent_hash,
            "recovery_condition_sha256": effective_hash,
            "max_time_seconds_per_item": r1.RECOVERY_TIMEOUT_SECONDS,
        })
        return row

    mc89._run_item = run_recovery_item

    state = json.loads((RECOVERY_DIR / "campaign.json").read_text(encoding="utf-8"))
    state.update({
        "pid": os.getpid(),
        "status": "running",
        "continuation_id": CONTINUATION_ID,
        "current_pass_progress": 0,  # nosec B105 - pass counter in the retry ledger, not a password
        "current_pass_total": len(retry_items),
    })
    recovery["continuation"] = dict(plan, started_at=_now(), status="running")
    mc89.atomic_json(RECOVERY_PATH, recovery)

    relay_server = relay_thread = None
    sandbox_home = scratch_root = None
    started = time.monotonic()
    try:
        relay_server, relay_thread, local_base_url, relay_key = mc89._start_credential_relay(
            runtime["endpoint"], runtime["api_key"]
        )
        agent_dirs, runtime_models = mc89._prepare_agent_dirs(
            runtime["config"], runtime["base_models"], runtime["append_system"], local_base_url
        )
        sandbox_home = Path(tempfile.mkdtemp(prefix="vmlu-mc89-c1-home-")).resolve()
        scratch_root = Path(tempfile.mkdtemp(prefix="vmlu-mc89-c1-scratch-")).resolve()
        mc89._write_campaign_snapshot(rows, data["requests"], effective_hash, "running", state)
        mc89.report(
            f"{CONTINUATION_ID} starts; items={len(retry_items)} attempt=2 "
            f"condition_sha256={effective_hash} previous_r1_attempts={len(processed)}"
        )

        fatal = mc89._run_pool(
            retry_items, rows, attempts_by_key, data, effective_hash, state,
            agent_dirs, runtime_models, relay_key, runtime["omp_bin"], runtime["bwrap_bin"],
            sandbox_home, scratch_root, pass_number=2,
        )
        for phase, manifest in (("main", data["main_manifest"]), ("vmlu", data["vmlu_manifest"])):
            keys = data[f"{phase}_keys"]
            phase_status = "complete" if all(rows.get(key, {}).get("status") == "complete" for key in keys) else "incomplete"
            mc89._write_phase_snapshot(phase, rows, keys, manifest, effective_hash, phase_status)
        result = mc89._score_outputs(data, rows, effective_hash)
        missing = [
            item["run_key"] for item in data["requests"]
            if rows.get(item["run_key"], {}).get("status") != "complete"
        ]
        final_status = "needs_attention" if fatal else "complete" if not missing else "incomplete"
        continuation_results = [
            {
                "run_key": row["run_key"], "status": rows[row["run_key"]].get("status"),
                "error_type": rows[row["run_key"]].get("error_type"),
                "latency_s": rows[row["run_key"]].get("latency_s"),
                "parse_valid": rows[row["run_key"]].get("parse_valid"),
            }
            for row in pending
        ]
        continuation = recovery["continuation"]
        continuation.update({
            "finished_at": _now(),
            "status": "complete" if all(row["status"] == "complete" for row in continuation_results) else "incomplete",
            "successful_retries": sum(row["status"] == "complete" for row in continuation_results),
            "remaining_errors": sum(row["status"] != "complete" for row in continuation_results),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "results": continuation_results,
        })
        recovery.update({
            "finished_at": _now(),
            "status": "complete" if not missing else "incomplete",
            "successful_retries": sum(rows[key].get("status") == "complete" for key in recovery["selected_run_keys"]),
            "remaining_errors": sum(rows[key].get("status") != "complete" for key in recovery["selected_run_keys"]),
            "campaign_status": final_status,
        })
        mc89.atomic_json(RECOVERY_PATH, recovery)
        state.update({
            "finished_at": _now(),
            "status": final_status,
            "current_pass_progress": len(retry_items),
            "current_pass_total": len(retry_items),
            "missing_or_failed_keys_n": len(missing),
            "missing_or_failed_keys_sample": missing[:20],
            "total_tool_calls": result["tool_calls"],
            "total_input_tokens": result["total_input_tokens"],
            "total_output_tokens": result["total_output_tokens"],
        })
        mc89._write_campaign_snapshot(rows, data["requests"], effective_hash, final_status, state)
        mc89.report(
            f"{CONTINUATION_ID} status={continuation['status']} successful={continuation['successful_retries']}/"
            f"{len(retry_items)} campaign={final_status} complete={result['completed_n']}/"
            f"{result['expected_n']} errors={result['request_error_n']}"
        )
    except BaseException as exc:
        recovery["continuation"] = dict(
            recovery.get("continuation", {"continuation_id": CONTINUATION_ID}),
            finished_at=_now(), status="failed", failure_type=type(exc).__name__,
        )
        mc89.atomic_json(RECOVERY_PATH, recovery)
        raise
    finally:
        if sandbox_home is not None:
            shutil.rmtree(sandbox_home, ignore_errors=True)
        if scratch_root is not None:
            shutil.rmtree(scratch_root, ignore_errors=True)
        if relay_server is not None:
            relay_server.shutdown()
            relay_server.server_close()
        if relay_thread is not None:
            relay_thread.join(timeout=2)


if __name__ == "__main__":
    main()
