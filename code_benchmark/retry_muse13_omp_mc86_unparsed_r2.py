"""Re-run the eight VMLU Test answers that parsed as blank with a longer wait.

From the repository root:
  .venv/bin/python -m code_benchmark.retry_muse13_omp_mc86_unparsed_r2  # plan only
  .venv/bin/python -m code_benchmark.retry_muse13_omp_mc86_unparsed_r2 --execute

This is an isolated recovery arm: it uses the frozen MC-86 item prompts and OMP
profile, raises only the per-item OMP time limit from 300s to 600s, and writes
results under recovery_mc86_r2/ without replacing the frozen MC-86 outputs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from code_benchmark import run_muse13_omp_mc86 as mc86


RECOVERY_ID = "MC-86-R2"
RECOVERY_DIR = mc86.OUTPUT_ROOT / "recovery_mc86_r2"
RECOVERY_PATH = RECOVERY_DIR / "recovery.json"
ATTEMPTS_PATH = RECOVERY_DIR / "attempts.jsonl"
PREDICTIONS_PATH = RECOVERY_DIR / "predictions.jsonl"
ANSWERS_PATH = RECOVERY_DIR / "retry_answers.csv"
PREVIOUS_MAX_TIME_SECONDS = 300
RECOVERY_MAX_TIME_SECONDS = 600
TARGET_DATASET = "vi-multimodel-v2-vmlu-test"
TARGET_IDS = {
    "01-0108", "05-0073", "09-0044", "09-0133",
    "20-0121", "20-0123", "26-0072", "34-0034",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_live_runner() -> bool:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return False
    modules = {
        b"code_benchmark.run_muse13_omp_mc86",
        b"code_benchmark.retry_muse13_omp_mc86_errors",
        b"code_benchmark.retry_muse13_omp_mc86_unparsed_r2",
    }
    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().split(b"\0")
            module_index = argv.index(b"-m")
        except (OSError, ValueError):
            continue
        if module_index + 2 < len(argv) and argv[module_index + 1] in modules and b"--execute" in argv[module_index + 2:]:
            return True
    return False


def _load_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _prepare() -> tuple[dict, dict[str, dict], dict[str, int], list[dict], dict, list[dict]]:
    if mc86.MAX_TIME_SECONDS != PREVIOUS_MAX_TIME_SECONDS:
        raise SystemExit("Error: MC-86 base timeout changed; inspect before recovery")
    data, _main_rebuilt, vmlu_rebuilt, requests = mc86._load_inputs()
    mc86.ACTIVE_V2_REBUILT = vmlu_rebuilt

    condition_path = mc86.OUTPUT_ROOT / "condition.json"
    if not condition_path.is_file():
        raise SystemExit("Error: frozen MC-86 condition.json is missing")
    condition = json.loads(condition_path.read_text(encoding="utf-8"))
    condition_hash = mc86.v1.sha256_bytes(mc86.v1.canonical_json(condition))
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
    if recomputed_hash != condition_hash:
        raise SystemExit("Error: current files/configuration differ from frozen MC-86")
    if condition.get("max_time_seconds_per_item") != PREVIOUS_MAX_TIME_SECONDS:
        raise SystemExit("Error: MC-86 frozen timeout is not 300 seconds")
    if condition.get("max_tokens_per_turn") != mc86.MAX_OUTPUT_TOKENS_PER_TURN:
        raise SystemExit("Error: MC-86 token cap differs from the frozen condition")

    campaign = json.loads((mc86.OUTPUT_ROOT / "campaign.json").read_text(encoding="utf-8"))
    if campaign.get("status") != "complete" or campaign.get("condition_sha256") != condition_hash:
        raise SystemExit("Error: MC-86 must be complete under the frozen condition before R2")
    if _has_live_runner():
        raise SystemExit("Error: an MC-86 campaign or recovery runner is active")
    if RECOVERY_PATH.exists():
        raise SystemExit("Error: MC-86-R2 already exists; refusing a duplicate run")
    preflight = json.loads((mc86.OUTPUT_ROOT / "preflight.json").read_text(encoding="utf-8"))
    if preflight.get("status") != "complete":
        raise SystemExit("Error: saved MC-86 preflight is not successful")

    attempts = _load_rows(mc86.OUTPUT_ROOT / "attempts.jsonl")
    latest: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for row in attempts:
        key = row.get("run_key")
        if not key:
            raise SystemExit("Error: MC-86 ledger row without run_key")
        latest[key] = row
        counts[key] = counts.get(key, 0) + 1
    if len(latest) != len(requests):
        raise SystemExit(f"Error: expected {len(requests)} ledger keys, found {len(latest)}")

    targets = [
        row for row in latest.values()
        if row.get("dataset_id") == TARGET_DATASET
        and row.get("item_id") in TARGET_IDS
        and row.get("status") == "complete"
        and row.get("parse_valid") is False
        and row.get("raw_response", "").strip()
    ]
    targets.sort(key=lambda row: row["item_id"])
    if {row["item_id"] for row in targets} != TARGET_IDS or len(targets) != len(TARGET_IDS):
        raise SystemExit("Error: the expected eight completed, non-parsing Test rows have changed")
    if any(counts[row["run_key"]] != 1 for row in targets):
        raise SystemExit("Error: a selected item already has a recovery attempt")
    request_by_key = {row["run_key"]: row for row in requests}
    retry_items = [request_by_key[row["run_key"]] for row in targets]
    runtime = {
        "profile": profile,
        "endpoint": endpoint,
        "api_key": api_key,
        "config": config,
        "base_models": base_models,
        "append_system": append_system,
        "omp_bin": omp_bin,
        "bwrap_bin": bwrap_bin,
        "condition_hash": condition_hash,
        "campaign": campaign,
    }
    return data, latest, counts, targets, runtime, retry_items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run the eight-item recovery arm")
    args = parser.parse_args()
    data, latest, attempt_counts, targets, runtime, retry_items = _prepare()

    plan = {
        "recovery_id": RECOVERY_ID,
        "status": "planned",
        "parent_protocol_id": mc86.PROTOCOL_ID,
        "parent_measurement_card_id": mc86.CARD_ID,
        "parent_condition_sha256": runtime["condition_hash"],
        "selection": "the eight named VMLU Test rows with complete requests and parse_valid=false",
        "selected_n": len(retry_items),
        "selected_run_keys": [row["run_key"] for row in targets],
        "previous_attempts": 1,
        "recovery_attempt": 2,
        "model_ref": mc86.MODEL_REF,
        "workers": mc86.WORKERS,
        "tools": "all",
        "max_time_seconds_per_item_before": PREVIOUS_MAX_TIME_SECONDS,
        "max_time_seconds_per_item": RECOVERY_MAX_TIME_SECONDS,
        "hard_subprocess_timeout_seconds": RECOVERY_MAX_TIME_SECONDS + mc86.TIMEOUT_SLACK_SECONDS,
        "max_output_tokens_per_turn": mc86.MAX_OUTPUT_TOKENS_PER_TURN,
        "change_scope": "Only the per-item OMP time limit is increased; frozen MC-86 files and outputs remain untouched.",
        "runner_sha256": mc86.sha256_file(Path(mc86.__file__)),
        "recovery_driver_sha256": mc86.sha256_file(Path(__file__).resolve()),
        "authorized_action": "User-requested rerun of the eight blank VMLU Test answers with a longer wait.",
    }
    print(
        f"MC-86-R2 plan: items={len(retry_items)} model={mc86.MODEL_REF} workers={mc86.WORKERS} "
        f"max_time={RECOVERY_MAX_TIME_SECONDS}s hard_timeout={RECOVERY_MAX_TIME_SECONDS + mc86.TIMEOUT_SLACK_SECONDS}s "
        f"condition_sha256={runtime['condition_hash']} endpoint_calls=0",
        flush=True,
    )
    for row in targets:
        print(f"  {row['run_key']} prior_parse_valid=false", flush=True)
    if not args.execute:
        print("Plan only; no model endpoint was called.", flush=True)
        return

    RECOVERY_DIR.mkdir(parents=True, exist_ok=False)
    recovery = dict(plan, status="running", started_at=_now(), completed_attempts=0)
    mc86.atomic_json(RECOVERY_PATH, recovery)
    sandbox_home = Path(tempfile.mkdtemp(prefix="vmlu-mc86-r2-home-")).resolve()
    scratch_root = Path(tempfile.mkdtemp(prefix="vmlu-mc86-r2-scratch-")).resolve()
    relay_server = relay_thread = None
    started = time.monotonic()
    results: dict[str, dict] = {}
    try:
        # Keep the original condition untouched; this recovery changes only the item wait limit.
        mc86.MAX_TIME_SECONDS = RECOVERY_MAX_TIME_SECONDS
        relay_server, relay_thread, local_base_url, relay_key = mc86._start_credential_relay(
            runtime["endpoint"], runtime["api_key"]
        )
        agent_dirs, runtime_models = mc86._prepare_agent_dirs(
            runtime["config"], runtime["base_models"], runtime["append_system"], local_base_url
        )

        def run_one(worker_id: int, item: dict) -> dict:
            row = mc86._run_item(
                item,
                worker_id=worker_id,
                attempt=attempt_counts[item["run_key"]] + 1,
                agent_dir=agent_dirs[worker_id - 1],
                base_models=runtime_models,
                relay_key=relay_key,
                omp_bin=runtime["omp_bin"],
                bwrap_bin=runtime["bwrap_bin"],
                home=sandbox_home,
                scratch_root=scratch_root,
            )
            row["pass"] = 2
            row["recovery_id"] = RECOVERY_ID
            row["max_time_seconds_per_item"] = RECOVERY_MAX_TIME_SECONDS
            parsed = mc86.v2.parse_expanded_answer(mc86.data_item_from_key(item), row.get("raw_response", ""))
            row["retry_prediction"] = parsed["prediction"]
            row["retry_parse_valid"] = parsed["parse_valid"]
            return row

        with ThreadPoolExecutor(max_workers=mc86.WORKERS, thread_name_prefix="mc86-r2") as pool:
            future_by_key = {
                pool.submit(run_one, index, item): item["run_key"]
                for index, item in enumerate(retry_items, start=1)
            }
            with ATTEMPTS_PATH.open("a", encoding="utf-8") as ledger:
                for future in as_completed(future_by_key):
                    key = future_by_key[future]
                    row = future.result()
                    results[key] = row
                    ledger.write(json.dumps(row, ensure_ascii=False) + "\n")
                    ledger.flush()
                    os.fsync(ledger.fileno())
                    recovery["completed_attempts"] = len(results)
                    recovery["progress"] = {
                        "request_complete": sum(v.get("status") == "complete" for v in results.values()),
                        "request_error": sum(v.get("status") != "complete" for v in results.values()),
                        "parse_valid": sum(v.get("retry_parse_valid") is True for v in results.values()),
                        "parse_invalid": sum(v.get("retry_parse_valid") is False for v in results.values()),
                    }
                    mc86.atomic_json(RECOVERY_PATH, recovery)
                    print(
                        f"MC-86-R2 {len(results)}/{len(retry_items)} item={row['item_id']} "
                        f"request={row['status']} parse_valid={row.get('retry_parse_valid')} "
                        f"latency_s={row.get('latency_s')}",
                        flush=True,
                    )

        ordered = [results[item["run_key"]] for item in retry_items]
        mc86.write_jsonl(PREDICTIONS_PATH, ordered)
        answers = [
            {"id": row["item_id"], "answer": row.get("retry_prediction", "")}
            for row in ordered
        ]
        mc86.write_csv_atomic(ANSWERS_PATH, answers, ["id", "answer"])
        recovery.update({
            "finished_at": _now(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "status": "complete" if all(row.get("status") == "complete" for row in ordered) else "incomplete",
            "request_complete_n": sum(row.get("status") == "complete" for row in ordered),
            "request_error_n": sum(row.get("status") != "complete" for row in ordered),
            "parse_valid_n": sum(row.get("retry_parse_valid") is True for row in ordered),
            "blank_answer_n": sum(not row.get("retry_prediction", "").strip() for row in ordered),
            "retry_results": [
                {k: row.get(k) for k in ["run_key", "item_id", "attempt", "status", "finish_reason",
                                          "retry_parse_valid", "retry_prediction", "latency_s", "tool_calls"]}
                for row in ordered
            ],
            "outputs": {
                "attempts": str(ATTEMPTS_PATH.relative_to(mc86.ROOT)),
                "predictions": str(PREDICTIONS_PATH.relative_to(mc86.ROOT)),
                "answers": str(ANSWERS_PATH.relative_to(mc86.ROOT)),
            },
        })
        mc86.atomic_json(RECOVERY_PATH, recovery)
        print(
            f"MC-86-R2 status={recovery['status']} requests={recovery['request_complete_n']}/"
            f"{len(ordered)} parse_valid={recovery['parse_valid_n']} blank={recovery['blank_answer_n']}",
            flush=True,
        )
    except BaseException as exc:
        recovery.update({"finished_at": _now(), "status": "failed", "failure_type": type(exc).__name__})
        mc86.atomic_json(RECOVERY_PATH, recovery)
        raise
    finally:
        shutil.rmtree(sandbox_home, ignore_errors=True)
        shutil.rmtree(scratch_root, ignore_errors=True)
        if relay_server is not None:
            relay_server.shutdown()
            relay_server.server_close()
        if relay_thread is not None:
            relay_thread.join(timeout=2)


if __name__ == "__main__":
    main()
