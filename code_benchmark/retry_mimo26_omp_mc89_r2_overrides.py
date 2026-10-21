"""MC-89-R2: recover the last failed keys with per-group overrides.

The user approved a third attempt with:
  - output_cap_20k  : 27 keys that generated exactly 20,000 completion tokens
                      in one turn -> maxTokens 32768, 1800 s
  - tool_loop_cap   : keys that hit the 1800 s cap during tool loops -> 3600 s
  - retry_short     : remaining technical failures -> 1800 s, unchanged controls

The runner reads MAX_TIME_SECONDS / MAX_OUTPUT_TOKENS_PER_TURN as module
globals, so the groups run sequentially (one pool each) instead of racing the
globals across 12 workers. Attempt 3 appends to its own ledger and overlays the
parent + R1/C1 results.

From the repository root:
  .venv/bin/python -m code_benchmark.retry_mimo26_omp_mc89_r2_overrides
  .venv/bin/python -m code_benchmark.retry_mimo26_omp_mc89_r2_overrides --execute
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
from typing import Any

from code_benchmark import retry_mimo26_omp_mc89_1800s as r1
from code_benchmark import run_mimo26_omp_mc89 as mc89


PARENT_ROOT = mc89.OUTPUT_ROOT
R1_DIR = r1.RECOVERY_DIR
R2_DIR = PARENT_ROOT / "recovery_mc89_r2"
R2_PATH = R2_DIR / "recovery.json"
RECOVERY_ID = "MC-89-R2"
GROUPS = ("output_cap_20k", "tool_loop_cap", "retry_short")
GROUP_TIMEOUT = {"output_cap_20k": 1800, "tool_loop_cap": 3600, "retry_short": 1800}
GROUP_MAX_TOKENS = {"output_cap_20k": 32768, "tool_loop_cap": 20000, "retry_short": 20000}
EXPECTED_MAX_TARGETS = 95


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _group_of(row: dict[str, Any]) -> str:
    if int(row.get("completion_tokens") or 0) == 20000:
        return "output_cap_20k"
    if float(row.get("latency_s") or 0) >= 1790:
        return "tool_loop_cap"
    return "retry_short"


def _combined_rows() -> tuple[dict[str, dict], Counter[str]]:
    rows, counts, _attempts = r1._load_latest_attempts()
    for row in mc89.read_jsonl(R1_DIR / "attempts.jsonl"):
        run_key = str(row.get("run_key", ""))
        if not run_key:
            raise SystemExit("Error: R1 ledger row without run_key")
        rows[run_key] = row
        counts[run_key] += 1
    return rows, counts


def _prepare() -> tuple[dict, dict[str, dict], Counter[str], list[dict], dict[str, Any], dict[str, list[dict]]]:
    data, _latest, _counts, _targets, runtime, _retry_items = r1._prepare()
    recovery = json.loads((R1_DIR / "recovery.json").read_text(encoding="utf-8"))
    if recovery.get("status") == "running":
        raise SystemExit("Error: MC-89-R1 is still running; finish it before R2")
    continuation = recovery.get("continuation") or {}
    if continuation.get("status") == "running":
        raise SystemExit("Error: the R1 continuation is still running; finish it before R2")
    if (R1_DIR / "condition.json").is_file():
        previous_condition = mc89.v1.sha256_bytes(
            mc89.v1.canonical_json(json.loads((R1_DIR / "condition.json").read_text(encoding="utf-8")))
        )
    else:
        previous_condition = None

    rows, attempts_by_key = _combined_rows()
    targets = [row for row in rows.values() if row.get("status") == "request_error"]
    if not targets:
        raise SystemExit("Error: no failed keys remain for R2")
    if len(targets) > EXPECTED_MAX_TARGETS:
        raise SystemExit(f"Error: unexpected target count {len(targets)} > {EXPECTED_MAX_TARGETS}")
    if any(attempts_by_key[row["run_key"]] != 2 for row in targets):
        raise SystemExit("Error: a selected item does not have exactly two prior attempts")
    targets.sort(key=lambda row: row["run_key"])
    grouped: dict[str, list[dict]] = {name: [] for name in GROUPS}
    for row in targets:
        grouped[_group_of(row)].append(row)
    requests_by_key = {row["run_key"]: row for row in data["requests"]}
    for name, group_rows in grouped.items():
        grouped[name] = [requests_by_key[row["run_key"]] for row in group_rows]
    return data, rows, attempts_by_key, targets, {
        **runtime,
        "previous_recovery_condition_sha256": previous_condition,
        "r1_recovery": recovery,
    }, grouped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run the three R2 groups")
    args = parser.parse_args()

    data, rows, attempts_by_key, targets, runtime, grouped = _prepare()
    if R2_PATH.exists():
        raise SystemExit("Error: MC-89-R2 recovery record already exists; refusing a duplicate pass")

    ids = [row["run_key"] for row in targets]
    group_plan = {
        name: {
            "timeout_seconds": GROUP_TIMEOUT[name],
            "max_tokens_per_turn": GROUP_MAX_TOKENS[name],
            "keys": [item["run_key"] for item in grouped[name]],
        }
        for name in GROUPS
    }
    plan = {
        "recovery_id": RECOVERY_ID,
        "parent_protocol_id": mc89.PROTOCOL_ID,
        "parent_measurement_card_id": mc89.CARD_ID,
        "parent_condition_sha256": runtime["condition_hash"],
        "previous_recovery_condition_sha256": runtime["previous_recovery_condition_sha256"],
        "previous_ledgers": {
            "parent": mc89.sha256_file(PARENT_ROOT / "attempts.jsonl"),
            "r1": mc89.sha256_file(R1_DIR / "attempts.jsonl"),
        },
        "selection": "latest request_error across parent + R1/C1 overlay",
        "selected_n": len(targets),
        "selected_run_keys": ids,
        "previous_attempts": 2,
        "recovery_attempt": 3,
        "workers": mc89.WORKERS,
        "model_ref": mc89.MODEL_REF,
        "omp_version_required": mc89.OMP_VERSION_REQUIRED,
        "groups": group_plan,
        "authorized_action": "User-approved third attempt: output-cap group at maxTokens 32768, tool-loop group at 3600 s, remaining failures retried unchanged.",
        "runner_sha256": mc89.sha256_file(Path(mc89.__file__)),
        "recovery_driver_sha256": mc89.sha256_file(Path(__file__).resolve()),
        "status": "planned",
    }
    print(
        f"{RECOVERY_ID} plan: targets={len(targets)} attempt=3 workers={mc89.WORKERS} "
        f"groups={{ {', '.join(f'{name}:{len(grouped[name])}' for name in GROUPS)} }} "
        f"condition_sha256={runtime['condition_hash']} endpoint_calls=0",
        flush=True,
    )
    for row in targets[:10]:
        print(f"  {row['run_key']} {row.get('error_type')} latency_s={row.get('latency_s')} group={_group_of(row)}", flush=True)
    if not args.execute:
        print("Plan only; no model endpoint was called.", flush=True)
        return

    R2_DIR.mkdir(parents=True, exist_ok=False)
    effective_condition = {
        "recovery_id": RECOVERY_ID,
        "parent_condition_sha256": runtime["condition_hash"],
        "previous_recovery_condition_sha256": runtime["previous_recovery_condition_sha256"],
        "previous_ledgers": plan["previous_ledgers"],
        "selected_run_keys": ids,
        "groups": {name: {k: v for k, v in group_plan[name].items() if k != "keys"} for name in GROUPS},
        "composition": "parent + R1/C1 overlay with only the selected keys replaced by R2 attempts",
    }
    effective_hash = mc89.v1.sha256_bytes(mc89.v1.canonical_json(effective_condition))
    plan["recovery_condition_sha256"] = effective_hash
    mc89.atomic_json(R2_DIR / "condition.json", effective_condition)
    parent_hash = runtime["condition_hash"]
    group_by_key = {item["run_key"]: name for name in GROUPS for item in grouped[name]}
    original_run_item = mc89._run_item

    def run_recovery_item(*call_args: Any, **call_kwargs: Any) -> dict[str, Any]:
        row = original_run_item(*call_args, **call_kwargs)
        row.update({
            "recovery_id": RECOVERY_ID,
            "parent_condition_sha256": parent_hash,
            "recovery_condition_sha256": effective_hash,
            "max_time_seconds_per_item": GROUP_TIMEOUT[group_by_key[row["run_key"]]],
            "max_tokens_per_turn": GROUP_MAX_TOKENS[group_by_key[row["run_key"]]],
            "recovery_group": group_by_key[row["run_key"]],
        })
        return row

    mc89._run_item = run_recovery_item
    mc89.OUTPUT_ROOT = R2_DIR
    mc89.MAIN_OUT = R2_DIR / "main" / mc89.PROFILE
    mc89.VMLU_OUT = R2_DIR / "vmlu" / mc89.PROFILE
    mc89.AGENT_ROOT = R2_DIR / "omp_workers"
    mc89.LOG_PATH = mc89.ROOT / "logs/mimo26_omp_mc89_recovery_r2.log"
    r1._patch_parsing()

    recovery = dict(plan)
    recovery.update({"status": "running", "started_at": _now()})
    mc89.atomic_json(R2_PATH, recovery)
    state = {
        "pid": os.getpid(),
        "started_at": _now(),
        "status": "running",
        "pass": 3,
        "worker_assignments": {},
        "peak_concurrent_items": 0,
        "recovery_id": RECOVERY_ID,
        "recovery_condition_sha256": effective_hash,
    }

    relay_server = relay_thread = None
    sandbox_home = scratch_root = None
    try:
        relay_server, relay_thread, local_base_url, relay_key = mc89._start_credential_relay(
            runtime["endpoint"], runtime["api_key"]
        )
        sandbox_home = Path(tempfile.mkdtemp(prefix="vmlu-mc89-r2-home-")).resolve()
        scratch_root = Path(tempfile.mkdtemp(prefix="vmlu-mc89-r2-scratch-")).resolve()
        fatal = False
        group_results: dict[str, dict[str, int]] = {}
        for name in GROUPS:
            group_items = grouped[name]
            if not group_items:
                group_results[name] = {"selected": 0, "recovered": 0, "remaining": 0}
                continue
            mc89.MAX_TIME_SECONDS = GROUP_TIMEOUT[name]
            mc89.MAX_OUTPUT_TOKENS_PER_TURN = GROUP_MAX_TOKENS[name]
            state.update({
                "group": name,
                "current_pass_progress": 0,
                "current_pass_total": len(group_items),
            })
            agent_dirs, runtime_models = mc89._prepare_agent_dirs(
                runtime["config"], runtime["base_models"], runtime["append_system"], local_base_url
            )
            mc89._write_campaign_snapshot(rows, data["requests"], effective_hash, "running", state)
            mc89.report(
                f"{RECOVERY_ID} group={name} items={len(group_items)} "
                f"timeout={GROUP_TIMEOUT[name]}s max_tokens={GROUP_MAX_TOKENS[name]}"
            )
            fatal = mc89._run_pool(
                group_items, rows, attempts_by_key, data, effective_hash, state,
                agent_dirs, runtime_models, relay_key, runtime["omp_bin"], runtime["bwrap_bin"],
                sandbox_home, scratch_root, pass_number=3,
            )
            recovered = sum(rows[item["run_key"]].get("status") == "complete" for item in group_items)
            group_results[name] = {
                "selected": len(group_items),
                "recovered": recovered,
                "remaining": len(group_items) - recovered,
            }
            mc89.report(
                f"{RECOVERY_ID} group={name} done recovered={recovered}/{len(group_items)}"
            )
            if fatal:
                break
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
        recovery.update({
            "finished_at": _now(),
            "status": "complete" if not missing else "incomplete",
            "successful_retries": sum(rows[key].get("status") == "complete" for key in ids),
            "remaining_errors": sum(rows[key].get("status") != "complete" for key in ids),
            "group_results": group_results,
            "campaign_status": final_status,
        })
        mc89.atomic_json(R2_PATH, recovery)
        state.update({
            "finished_at": _now(),
            "status": final_status,
            "missing_or_failed_keys_n": len(missing),
            "missing_or_failed_keys_sample": missing[:20],
            "total_tool_calls": result["tool_calls"],
            "total_input_tokens": result["total_input_tokens"],
            "total_output_tokens": result["total_output_tokens"],
        })
        mc89._write_campaign_snapshot(rows, data["requests"], effective_hash, final_status, state)
        mc89.report(
            f"{RECOVERY_ID} status={recovery['status']} successful={recovery['successful_retries']}/"
            f"{len(ids)} campaign={final_status} complete={result['completed_n']}/"
            f"{result['expected_n']} errors={result['request_error_n']} groups={group_results}"
        )
    except BaseException as exc:
        recovery.update({"finished_at": _now(), "status": "failed", "failure_type": type(exc).__name__})
        mc89.atomic_json(R2_PATH, recovery)
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
