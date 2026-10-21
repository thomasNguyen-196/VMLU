"""Run one user-requested recovery pass for MC-86 OMP turn errors.

From the repository root:
  .venv/bin/python -m code_benchmark.retry_muse13_omp_mc86_errors  # plan only
  .venv/bin/python -m code_benchmark.retry_muse13_omp_mc86_errors --execute

The frozen MC-86 runner remains unchanged. This driver selects only the latest
non-retryable ``omp_turn_error`` records, appends attempt 2 to the MC-86 ledger,
and records the explicit recovery separately from the frozen condition.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from code_benchmark import run_muse13_omp_mc86 as mc86


RECOVERY_PATH = mc86.OUTPUT_ROOT / "recovery_mc86_r1.json"
RECOVERY_ID = "MC-86-R1"
RETRY_TYPE = "omp_turn_error"
EXPECTED_TARGETS = 13
COOLDOWN_SECONDS = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_live_campaign_process() -> bool:
    """Refuse overlapping original or recovery runners without exposing argv."""
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return False
    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        try:
            module_index = argv.index(b"-m")
        except ValueError:
            continue
        if module_index + 2 >= len(argv) or b"--execute" not in argv[module_index + 2:]:
            continue
        if argv[module_index + 1] in {
            b"code_benchmark.run_muse13_omp_mc86",
            b"code_benchmark.retry_muse13_omp_mc86_errors",
        }:
            return True
    return False


def _load_latest_attempts() -> tuple[dict[str, dict], Counter[str], list[dict]]:
    attempts = mc86.read_jsonl(mc86.OUTPUT_ROOT / "attempts.jsonl")
    latest: dict[str, dict] = {}
    counts: Counter[str] = Counter()
    for row in attempts:
        run_key = str(row.get("run_key", ""))
        if not run_key:
            raise SystemExit("Error: MC-86 ledger row without run_key")
        latest[run_key] = row
        counts[run_key] += 1
    return latest, counts, attempts


def _prepare() -> tuple[dict, dict[str, dict], Counter[str], list[dict], dict, list[dict]]:
    data, _main_rebuilt, vmlu_rebuilt, requests = mc86._load_inputs()
    mc86.ACTIVE_V2_REBUILT = vmlu_rebuilt
    condition_path = mc86.OUTPUT_ROOT / "condition.json"
    if not condition_path.is_file():
        raise SystemExit("Error: frozen MC-86 condition.json is missing")
    frozen_condition = json.loads(condition_path.read_text(encoding="utf-8"))
    frozen_hash = mc86.v1.sha256_bytes(mc86.v1.canonical_json(frozen_condition))

    omp_bin = mc86._omp_version(mc86.OMP_BIN)
    bwrap_bin, sandbox_version = mc86._bwrap_version(mc86.BWRAP_BIN)
    profile, endpoint, api_key, _request_model, credential_source = mc86._model_configuration()
    if mc86.urlsplit(endpoint).hostname != "opencode.ai":
        raise SystemExit("Error: unexpected OpenCode Go endpoint host")
    config, base_models, append_system = mc86._read_agent_template()
    recomputed = mc86._make_condition(
        data, mc86.OMP_VERSION_REQUIRED, sandbox_version, endpoint,
        credential_source, config, base_models, append_system,
    )
    recomputed_hash = mc86.v1.sha256_bytes(mc86.v1.canonical_json(recomputed))
    if recomputed_hash != frozen_hash:
        raise SystemExit("Error: recovery would not match the frozen MC-86 condition")

    preflight = json.loads((mc86.OUTPUT_ROOT / "preflight.json").read_text(encoding="utf-8"))
    if preflight.get("status") != "complete":
        raise SystemExit("Error: saved MC-86 preflight is not successful")
    if _has_live_campaign_process():
        raise SystemExit("Error: an MC-86 campaign/recovery process is already active")

    latest, attempt_counts, attempts = _load_latest_attempts()
    if len(latest) != len(requests):
        raise SystemExit(f"Error: expected {len(requests)} ledger keys, found {len(latest)}")
    campaign = json.loads((mc86.OUTPUT_ROOT / "campaign.json").read_text(encoding="utf-8"))
    if campaign.get("status") not in {"incomplete", "complete"}:
        raise SystemExit(f"Error: campaign is not terminal ({campaign.get('status')})")
    if campaign.get("condition_sha256") != frozen_hash:
        raise SystemExit("Error: campaign condition hash differs from condition.json")

    targets = [
        row for row in latest.values()
        if row.get("status") == "request_error"
        and row.get("error_type") == RETRY_TYPE
        and row.get("retryable") is False
        and row.get("dataset_id") == "vi-multimodel-v2-vmlu-test"
    ]
    targets.sort(key=lambda row: row["run_key"])
    if len(targets) != EXPECTED_TARGETS:
        raise SystemExit(f"Error: expected {EXPECTED_TARGETS} current targets, found {len(targets)}")
    if any(attempt_counts[row["run_key"]] != 1 for row in targets):
        raise SystemExit("Error: a selected item already has a recovery attempt")

    requests_by_key = {row["run_key"]: row for row in requests}
    retry_items = [requests_by_key[row["run_key"]] for row in targets]
    data["main_keys"] = [row["run_key"] for row in requests if row["phase"] == "main"]
    data["vmlu_keys"] = [row["run_key"] for row in requests if row["phase"] == "vmlu"]
    return data, latest, attempt_counts, targets, {
        "profile": profile,
        "endpoint": endpoint,
        "api_key": api_key,
        "credential_source": credential_source,
        "config": config,
        "base_models": base_models,
        "append_system": append_system,
        "omp_bin": omp_bin,
        "bwrap_bin": bwrap_bin,
        "sandbox_version": sandbox_version,
        "condition_hash": frozen_hash,
        "campaign": campaign,
    }, retry_items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run the single selected recovery pass")
    args = parser.parse_args()

    data, rows, attempts_by_key, targets, runtime, retry_items = _prepare()
    existing_recovery = RECOVERY_PATH.exists()
    if existing_recovery:
        raise SystemExit("Error: MC-86-R1 recovery record already exists; refusing a duplicate pass")

    ids = [row["run_key"] for row in targets]
    plan = {
        "recovery_id": RECOVERY_ID,
        "parent_protocol_id": mc86.PROTOCOL_ID,
        "parent_measurement_card_id": mc86.CARD_ID,
        "parent_condition_sha256": runtime["condition_hash"],
        "selection": "latest request_error with error_type=omp_turn_error, retryable=false, VMLU Test only",
        "selected_n": len(targets),
        "selected_run_keys": ids,
        "previous_attempts": 1,
        "recovery_attempt": 2,
        "workers": mc86.WORKERS,
        "model_ref": mc86.MODEL_REF,
        "omp_version_required": mc86.OMP_VERSION_REQUIRED,
        "max_time_seconds_per_item": mc86.MAX_TIME_SECONDS,
        "max_output_tokens_per_turn": mc86.MAX_OUTPUT_TOKENS_PER_TURN,
        "tools": "all",
        "cooldown_seconds": COOLDOWN_SECONDS,
        "authorized_action": "User-requested single rerun of every MC-86 omp_turn_error item.",
        "runner_sha256": mc86.sha256_file(Path(mc86.__file__)),
        "recovery_driver_sha256": mc86.sha256_file(Path(__file__).resolve()),
        "status": "planned",
    }
    print(
        f"MC-86-R1 plan: items={len(retry_items)} attempt=2 workers={mc86.WORKERS} "
        f"model={mc86.MODEL_REF} max_time={mc86.MAX_TIME_SECONDS}s "
        f"condition_sha256={runtime['condition_hash']} endpoint_calls=0",
        flush=True,
    )
    for row in targets:
        print(f"  {row['run_key']} previous_latency_s={row.get('latency_s')}", flush=True)
    if not args.execute:
        print("Plan only; no model endpoint was called.", flush=True)
        return

    recovery = dict(plan)
    recovery.update({"status": "running", "started_at": _now()})
    mc86.atomic_json(RECOVERY_PATH, recovery)
    state = dict(runtime["campaign"])
    state.pop("finished_at", None)
    state.update({
        "pid": os.getpid(),
        "pass": 2,
        "status": "running",
        "current_pass_progress": 0,
        "current_pass_total": len(retry_items),
        "recovery_id": RECOVERY_ID,
    })

    relay_server = relay_thread = None
    sandbox_home = scratch_root = None
    started = time.monotonic()
    try:
        relay_server, relay_thread, local_base_url, relay_key = mc86._start_credential_relay(
            runtime["endpoint"], runtime["api_key"]
        )
        agent_dirs, runtime_models = mc86._prepare_agent_dirs(
            runtime["config"], runtime["base_models"], runtime["append_system"], local_base_url
        )
        sandbox_home = Path(tempfile.mkdtemp(prefix="vmlu-mc86-recovery-home-")).resolve()
        scratch_root = Path(tempfile.mkdtemp(prefix="vmlu-mc86-recovery-scratch-")).resolve()
        mc86._write_campaign_snapshot(rows, data["requests"], runtime["condition_hash"], "running", state)
        mc86.report(
            f"MC-86-R1 starts after {COOLDOWN_SECONDS}s cooldown; items={len(retry_items)} "
            f"attempt=2 condition_sha256={runtime['condition_hash']}"
        )
        time.sleep(COOLDOWN_SECONDS)

        fatal = False
        fatal = mc86._run_pool(
            retry_items, rows, attempts_by_key, data, runtime["condition_hash"], state,
            agent_dirs, runtime_models, relay_key, runtime["omp_bin"], runtime["bwrap_bin"],
            sandbox_home, scratch_root, pass_number=2,
        )
        for phase, manifest in (("main", data["main_manifest"]), ("vmlu", data["vmlu_manifest"])):
            keys = data[f"{phase}_keys"]
            phase_status = "complete" if all(rows.get(key, {}).get("status") == "complete" for key in keys) else "incomplete"
            mc86._write_phase_snapshot(phase, rows, keys, manifest, runtime["condition_hash"], phase_status)
        result = mc86._score_outputs(data, rows, runtime["condition_hash"])
        missing = [item["run_key"] for item in data["requests"] if rows.get(item["run_key"], {}).get("status") != "complete"]
        final_status = "needs_attention" if fatal else "complete" if not missing else "incomplete"
        retry_results = [
            {"run_key": key, "attempt": attempts_by_key[key], "status": rows[key].get("status"),
             "error_type": rows[key].get("error_type"), "retryable": rows[key].get("retryable"),
             "finish_reason": rows[key].get("finish_reason"), "latency_s": rows[key].get("latency_s")}
            for key in ids
        ]
        recovery.update({
            "finished_at": _now(),
            "status": "complete" if all(row["status"] == "complete" for row in retry_results) else "incomplete",
            "successful_retries": sum(row["status"] == "complete" for row in retry_results),
            "remaining_errors": sum(row["status"] != "complete" for row in retry_results),
            "retry_results": retry_results,
            "campaign_status": final_status,
        })
        mc86.atomic_json(RECOVERY_PATH, recovery)
        state.update({
            "finished_at": _now(),
            "status": final_status,
            "current_pass_progress": len(retry_items),
            "current_pass_total": len(retry_items),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "missing_or_failed_keys_n": len(missing),
            "missing_or_failed_keys_sample": missing[:20],
            "total_tool_calls": result["tool_calls"],
            "total_input_tokens": result["total_input_tokens"],
            "total_output_tokens": result["total_output_tokens"],
        })
        mc86._write_campaign_snapshot(rows, data["requests"], runtime["condition_hash"], final_status, state)
        mc86.report(
            f"MC-86-R1 status={recovery['status']} successful={recovery['successful_retries']}/"
            f"{len(retry_items)} campaign={final_status} complete={result['completed_n']}/"
            f"{result['expected_n']} errors={result['request_error_n']}"
        )
    except BaseException as exc:
        recovery.update({"finished_at": _now(), "status": "failed", "failure_type": type(exc).__name__})
        mc86.atomic_json(RECOVERY_PATH, recovery)
        state.update({"finished_at": _now(), "status": "incomplete", "recovery_failure_type": type(exc).__name__})
        mc86._write_campaign_snapshot(rows, data["requests"], runtime["condition_hash"], "incomplete", state)
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
