"""Recover the 475 MC-89 failed keys with a separately recorded 1800s timeout.

Run from the repository root:
  .venv/bin/python -m code_benchmark.retry_mimo26_omp_mc89_1800s
  .venv/bin/python -m code_benchmark.retry_mimo26_omp_mc89_1800s --execute

The recovery preserves the parent artifacts, appends attempt 2 rows to its own
ledger, and produces combined predictions/scores by overlaying only the
selected keys. Completed-but-unparsed rows stay terminal and are not re-run.

The 49 parent AttributeError rows are parser crashes on MiMo transcripts. This
driver wraps the parsing entry points with traceback logging (and makes the
reasoning-token extractor tolerant of non-dict usage details) so a recurrence
is diagnosable and does not lose the item.
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
import traceback
from typing import Any

from code_benchmark import run_mimo26_omp_mc89 as mc89


PARENT_ROOT = mc89.OUTPUT_ROOT
RECOVERY_DIR = PARENT_ROOT / "recovery_mc89_1800s"
RECOVERY_PATH = RECOVERY_DIR / "recovery.json"
TRACE_LOG = RECOVERY_DIR / "parse_tracebacks.log"
RECOVERY_TIMEOUT_SECONDS = 1800
RECOVERY_ID = "MC-89-R1"
EXPECTED_REQUEST_ERRORS = 475
EXPECTED_PARSE_TERMINAL = 18
COOLDOWN_SECONDS = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_traceback(label: str, payload: str = "") -> None:
    TRACE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with TRACE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"\n===== {_now()} {label} =====\n")
        handle.write(traceback.format_exc())
        if payload:
            handle.write("\n--- payload tail ---\n")
            handle.write(payload[-4000:])
        handle.write("\n")


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
            b"code_benchmark.run_mimo26_omp_mc89",
            b"code_benchmark.retry_mimo26_omp_mc89_1800s",
        }:
            return True
    return False


def _patch_parsing() -> None:
    """Log tracebacks at the parsing boundaries and tolerate non-dict usage details."""
    harness = mc89.harness

    def wrap(module: Any, name: str, payload_source: str | None = None) -> None:
        original = getattr(module, name)

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return original(*args, **kwargs)
            except Exception:
                payload = ""
                if payload_source == "lines" and args:
                    payload = "\n".join(str(line) for line in args[0]) if isinstance(args[0], (list, tuple)) else str(args[0])
                _log_traceback(name, payload)
                raise

        setattr(module, name, wrapped)

    wrap(harness, "parse_transcript", payload_source="lines")
    wrap(harness, "audit_transcript")
    wrap(harness, "extract_answer")
    if hasattr(harness, "_event_error_detail"):
        wrap(harness, "_event_error_detail")
    wrap(mc89, "_web_search_events")
    wrap(mc89, "data_item_from_key")
    wrap(mc89.v2, "parse_expanded_answer")

    original_reasoning = mc89._reasoning_tokens

    def safe_reasoning_tokens(events: list[dict[str, Any]]) -> int:
        try:
            return original_reasoning(events)
        except Exception:
            _log_traceback("_reasoning_tokens")
            return 0

    mc89._reasoning_tokens = safe_reasoning_tokens


def _load_latest_attempts() -> tuple[dict[str, dict], Counter[str], list[dict]]:
    attempts = mc89.read_jsonl(PARENT_ROOT / "attempts.jsonl")
    latest: dict[str, dict] = {}
    counts: Counter[str] = Counter()
    for row in attempts:
        run_key = str(row.get("run_key", ""))
        if not run_key:
            raise SystemExit("Error: MC-89 ledger row without run_key")
        latest[run_key] = row
        counts[run_key] += 1
    return latest, counts, attempts


def _prepare() -> tuple[dict, dict[str, dict], Counter[str], list[dict], dict[str, Any], list[dict]]:
    data, _main_rebuilt, vmlu_rebuilt, requests = mc89._load_inputs()
    mc89.ACTIVE_V2_REBUILT = vmlu_rebuilt
    condition_path = PARENT_ROOT / "condition.json"
    if not condition_path.is_file():
        raise SystemExit("Error: frozen MC-89 condition.json is missing")
    frozen_condition = json.loads(condition_path.read_text(encoding="utf-8"))
    frozen_hash = mc89.v1.sha256_bytes(mc89.v1.canonical_json(frozen_condition))

    omp_bin = mc89._omp_version(mc89.OMP_BIN)
    bwrap_bin, sandbox_version = mc89._bwrap_version(mc89.BWRAP_BIN)
    profile, endpoint, api_key, _request_model, credential_source = mc89._model_configuration()
    if mc89.urlsplit(endpoint).hostname != mc89.ENDPOINT_HOST:
        raise SystemExit("Error: unexpected OpenCode Go endpoint host")
    config, base_models, append_system = mc89._read_agent_template(endpoint)
    recomputed = mc89._make_condition(
        data, mc89.OMP_VERSION_REQUIRED, sandbox_version, endpoint,
        credential_source, config, base_models, append_system,
    )
    recomputed_hash = mc89.v1.sha256_bytes(mc89.v1.canonical_json(recomputed))
    if recomputed_hash != frozen_hash:
        raise SystemExit("Error: recovery would not match the frozen MC-89 condition")

    preflight = json.loads((PARENT_ROOT / "preflight.json").read_text(encoding="utf-8"))
    if preflight.get("status") != "complete":
        raise SystemExit("Error: saved MC-89 preflight is not successful")
    if mc89.MAX_TIME_SECONDS != 900 or frozen_condition.get("max_time_seconds_per_item") != 900:
        raise SystemExit("Error: expected the parent 900s condition before recovery")
    campaign = json.loads((PARENT_ROOT / "campaign.json").read_text(encoding="utf-8"))
    if campaign.get("status") != "incomplete" or campaign.get("complete_items") != 11558:
        raise SystemExit(f"Error: parent campaign is not the expected terminal state ({campaign.get('status')})")
    if _has_live_campaign_process():
        raise SystemExit("Error: an MC-89 campaign/recovery process is already active")

    latest, attempt_counts, attempts = _load_latest_attempts()
    if len(latest) != len(requests):
        raise SystemExit(f"Error: expected {len(requests)} ledger keys, found {len(latest)}")
    if campaign.get("condition_sha256") != frozen_hash:
        raise SystemExit("Error: campaign condition hash differs from condition.json")

    targets = [row for row in latest.values() if row.get("status") == "request_error"]
    parse_terminal = [
        row for row in latest.values()
        if row.get("status") == "complete" and row.get("parse_valid") is False
    ]
    if len(targets) != EXPECTED_REQUEST_ERRORS:
        raise SystemExit(f"Error: expected {EXPECTED_REQUEST_ERRORS} request errors, found {len(targets)}")
    if len(parse_terminal) != EXPECTED_PARSE_TERMINAL:
        raise SystemExit(f"Error: expected {EXPECTED_PARSE_TERMINAL} terminal parse-invalid rows, found {len(parse_terminal)}")
    if any(attempt_counts[row["run_key"]] != 1 for row in targets):
        raise SystemExit("Error: a selected item does not have exactly one prior attempt")
    targets.sort(key=lambda row: row["run_key"])
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
    if RECOVERY_PATH.exists():
        raise SystemExit("Error: MC-89-R1 recovery record already exists; refusing a duplicate pass")

    ids = [row["run_key"] for row in targets]
    plan = {
        "recovery_id": RECOVERY_ID,
        "parent_protocol_id": mc89.PROTOCOL_ID,
        "parent_measurement_card_id": mc89.CARD_ID,
        "parent_condition_sha256": runtime["condition_hash"],
        "selection": "latest request_error across all datasets; completed parse-invalid rows stay terminal",
        "request_error_n": EXPECTED_REQUEST_ERRORS,
        "parse_invalid_terminal_n": EXPECTED_PARSE_TERMINAL,
        "selected_n": len(targets),
        "selected_run_keys": ids,
        "previous_attempts": 1,
        "recovery_attempt": 2,
        "workers": mc89.WORKERS,
        "model_ref": mc89.MODEL_REF,
        "omp_version_required": mc89.OMP_VERSION_REQUIRED,
        "max_time_seconds_per_item_before": 900,
        "max_time_seconds_per_item": RECOVERY_TIMEOUT_SECONDS,
        "hard_subprocess_timeout_seconds": RECOVERY_TIMEOUT_SECONDS + mc89.TIMEOUT_SLACK_SECONDS,
        "parent_ledger_sha256": mc89.sha256_file(PARENT_ROOT / "attempts.jsonl"),
        "composition": "parent results overlaid with recovered attempts for the selected keys",
        "max_output_tokens_per_turn": mc89.MAX_OUTPUT_TOKENS_PER_TURN,
        "tools": "all",
        "cooldown_seconds": COOLDOWN_SECONDS,
        "authorized_action": "User-approved rerun of the 475 MC-89 failures with timeout increased to 1800 seconds.",
        "runner_sha256": mc89.sha256_file(Path(mc89.__file__)),
        "recovery_driver_sha256": mc89.sha256_file(Path(__file__).resolve()),
        "status": "planned",
    }
    print(
        f"MC-89-R1 plan: items={len(retry_items)} attempt=2 workers={mc89.WORKERS} "
        f"model={mc89.MODEL_REF} max_time={RECOVERY_TIMEOUT_SECONDS}s "
        f"condition_sha256={runtime['condition_hash']} endpoint_calls=0",
        flush=True,
    )
    for row in targets[:10]:
        print(f"  {row['run_key']} {row.get('error_type')} latency_s={row.get('latency_s')}", flush=True)
    if not args.execute:
        print("Plan only; no model endpoint was called.", flush=True)
        return

    RECOVERY_DIR.mkdir(parents=True, exist_ok=False)
    effective_condition = {
        "recovery_id": RECOVERY_ID,
        "parent_condition_sha256": runtime["condition_hash"],
        "parent_ledger_sha256": plan["parent_ledger_sha256"],
        "selected_run_keys": ids,
        "overrides": {"max_time_seconds_per_item": RECOVERY_TIMEOUT_SECONDS},
        "composition": plan["composition"],
    }
    effective_hash = mc89.v1.sha256_bytes(mc89.v1.canonical_json(effective_condition))
    plan["recovery_condition_sha256"] = effective_hash
    mc89.atomic_json(RECOVERY_DIR / "condition.json", effective_condition)
    parent_hash = runtime["condition_hash"]
    runtime["condition_hash"] = effective_hash
    original_run_item = mc89._run_item

    def run_recovery_item(*call_args: Any, **call_kwargs: Any) -> dict[str, Any]:
        row = original_run_item(*call_args, **call_kwargs)
        row.update({
            "recovery_id": RECOVERY_ID,
            "parent_condition_sha256": parent_hash,
            "recovery_condition_sha256": effective_hash,
            "max_time_seconds_per_item": RECOVERY_TIMEOUT_SECONDS,
        })
        return row

    mc89._run_item = run_recovery_item
    mc89.MAX_TIME_SECONDS = RECOVERY_TIMEOUT_SECONDS
    mc89.OUTPUT_ROOT = RECOVERY_DIR
    mc89.MAIN_OUT = RECOVERY_DIR / "main" / mc89.PROFILE
    mc89.VMLU_OUT = RECOVERY_DIR / "vmlu" / mc89.PROFILE
    mc89.AGENT_ROOT = RECOVERY_DIR / "omp_workers"
    mc89.LOG_PATH = mc89.ROOT / "logs/mimo26_omp_mc89_recovery_1800s.log"
    _patch_parsing()

    recovery = dict(plan)
    recovery.update({"status": "running", "started_at": _now()})
    mc89.atomic_json(RECOVERY_PATH, recovery)
    state = {
        "pid": os.getpid(),
        "started_at": _now(),
        "status": "running",
        "pass": 2,
        "worker_assignments": {},
        "peak_concurrent_items": 0,
        "current_pass_progress": 0,
        "current_pass_total": len(retry_items),
        "recovery_id": RECOVERY_ID,
        "parent_condition_sha256": parent_hash,
        "max_time_seconds_per_item": RECOVERY_TIMEOUT_SECONDS,
        "composition": plan["composition"],
    }

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
        sandbox_home = Path(tempfile.mkdtemp(prefix="vmlu-mc89-r1-home-")).resolve()
        scratch_root = Path(tempfile.mkdtemp(prefix="vmlu-mc89-r1-scratch-")).resolve()
        mc89._write_campaign_snapshot(rows, data["requests"], runtime["condition_hash"], "running", state)
        mc89.report(
            f"{RECOVERY_ID} starts after {COOLDOWN_SECONDS}s cooldown; items={len(retry_items)} "
            f"attempt=2 condition_sha256={runtime['condition_hash']}"
        )
        time.sleep(COOLDOWN_SECONDS)

        fatal = mc89._run_pool(
            retry_items, rows, attempts_by_key, data, runtime["condition_hash"], state,
            agent_dirs, runtime_models, relay_key, runtime["omp_bin"], runtime["bwrap_bin"],
            sandbox_home, scratch_root, pass_number=2,
        )
        for phase, manifest in (("main", data["main_manifest"]), ("vmlu", data["vmlu_manifest"])):
            keys = data[f"{phase}_keys"]
            phase_status = "complete" if all(rows.get(key, {}).get("status") == "complete" for key in keys) else "incomplete"
            mc89._write_phase_snapshot(phase, rows, keys, manifest, runtime["condition_hash"], phase_status)
        result = mc89._score_outputs(data, rows, runtime["condition_hash"])
        missing = [
            item["run_key"] for item in data["requests"]
            if rows.get(item["run_key"], {}).get("status") != "complete"
        ]
        final_status = "needs_attention" if fatal else "complete" if not missing else "incomplete"
        retry_results = [
            {
                "run_key": key, "attempt": attempts_by_key[key], "status": rows[key].get("status"),
                "error_type": rows[key].get("error_type"), "retryable": rows[key].get("retryable"),
                "finish_reason": rows[key].get("finish_reason"), "latency_s": rows[key].get("latency_s"),
                "parse_valid": rows[key].get("parse_valid"),
            }
            for key in ids
        ]
        recovery.update({
            "finished_at": _now(),
            "status": "complete" if not missing else "incomplete",
            "successful_retries": sum(row["status"] == "complete" for row in retry_results),
            "remaining_errors": sum(row["status"] != "complete" for row in retry_results),
            "retry_results": retry_results,
            "campaign_status": final_status,
        })
        mc89.atomic_json(RECOVERY_PATH, recovery)
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
        mc89._write_campaign_snapshot(rows, data["requests"], runtime["condition_hash"], final_status, state)
        mc89.report(
            f"{RECOVERY_ID} status={recovery['status']} successful={recovery['successful_retries']}/"
            f"{len(retry_items)} campaign={final_status} complete={result['completed_n']}/"
            f"{result['expected_n']} errors={result['request_error_n']}"
        )
    except BaseException as exc:
        recovery.update({"finished_at": _now(), "status": "failed", "failure_type": type(exc).__name__})
        mc89.atomic_json(RECOVERY_PATH, recovery)
        state.update({"finished_at": _now(), "status": "incomplete", "recovery_failure_type": type(exc).__name__})
        mc89._write_campaign_snapshot(rows, data["requests"], runtime["condition_hash"], "incomplete", state)
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
