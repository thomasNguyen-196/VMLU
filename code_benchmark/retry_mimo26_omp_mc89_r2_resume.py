"""Continue MC-89-R2 after the systemd-oomd kill: process the remaining 36 keys.

The first R2 pass was killed by systemd-oomd at 2026-10-21 05:12 UTC (memory
peak 6.5G + 5G swap) after 59/95 attempts. This continuation keeps the R2
condition, appends to the R2 ledger, and lowers concurrency from 12 to 8 to
reduce memory pressure. The scheduling change is recorded in the recovery
record; it does not change the model, prompts, caps, or timeouts.

From the repository root:
  .venv/bin/python -m code_benchmark.retry_mimo26_omp_mc89_r2_resume
  .venv/bin/python -m code_benchmark.retry_mimo26_omp_mc89_r2_resume --execute
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from code_benchmark import retry_mimo26_omp_mc89_1800s as r1
from code_benchmark import retry_mimo26_omp_mc89_r2_overrides as r2
from code_benchmark import run_mimo26_omp_mc89 as mc89


R2_DIR = r2.R2_DIR
R2_PATH = r2.R2_PATH
CONTINUATION_ID = "MC-89-R2-C1"
CONTINUATION_WORKERS = 8
EXPECTED_PENDING = 36


def _now() -> str:
    return r2._now()


def _combined_rows() -> tuple[dict[str, dict], Counter[str]]:
    rows, counts, _attempts = r1._load_latest_attempts()
    for path in (r1.RECOVERY_DIR / "attempts.jsonl", R2_DIR / "attempts.jsonl"):
        for row in mc89.read_jsonl(path):
            run_key = str(row.get("run_key", ""))
            if not run_key:
                raise SystemExit(f"Error: ledger row without run_key in {path}")
            rows[run_key] = row
            counts[run_key] += 1
    return rows, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run the R2 continuation")
    args = parser.parse_args()

    if not R2_PATH.is_file():
        raise SystemExit("Error: the MC-89-R2 recovery record is missing")
    recovery = json.loads(R2_PATH.read_text(encoding="utf-8"))
    if recovery.get("status") != "running":
        raise SystemExit(f"Error: MC-89-R2 is not an interrupted running pass ({recovery.get('status')})")
    if "continuation" in recovery:
        raise SystemExit("Error: the R2 continuation already ran; refusing a duplicate")

    data, _latest, _counts, _targets, runtime, _retry_items = r1._prepare()
    if r1._has_live_campaign_process():
        raise SystemExit("Error: an MC-89 campaign/recovery process is already active")

    effective_condition = json.loads((R2_DIR / "condition.json").read_text(encoding="utf-8"))
    effective_hash = mc89.v1.sha256_bytes(mc89.v1.canonical_json(effective_condition))
    if effective_hash != recovery.get("recovery_condition_sha256"):
        raise SystemExit("Error: R2 recovery condition hash differs from the recovery record")

    rows, attempts_by_key = _combined_rows()
    processed = {row["run_key"] for row in mc89.read_jsonl(R2_DIR / "attempts.jsonl")}
    selected = set(recovery["selected_run_keys"])
    pending_keys = sorted(selected - processed)
    if len(pending_keys) != EXPECTED_PENDING:
        raise SystemExit(f"Error: expected {EXPECTED_PENDING} pending R2 keys, found {len(pending_keys)}")
    requests_by_key = {row["run_key"]: row for row in data["requests"]}
    pending_rows = [rows[key] for key in pending_keys]
    if any(attempts_by_key[key] != 2 for key in pending_keys):
        raise SystemExit("Error: a pending key does not have exactly two prior attempts")
    pending_items = [requests_by_key[key] for key in pending_keys]
    grouped: dict[str, list[dict]] = {name: [] for name in r2.GROUPS}
    for item, row in zip(pending_items, pending_rows, strict=True):
        grouped[r2._group_of(row)].append(item)
    parent_hash = recovery["parent_condition_sha256"]

    plan = {
        "continuation_id": CONTINUATION_ID,
        "parent_recovery_id": recovery["recovery_id"],
        "reason": "systemd-oomd killed the R2 unit after 59/95 attempts (memory peak 6.5G + 5G swap)",
        "selected_n": len(pending_items),
        "groups": {name: len(grouped[name]) for name in r2.GROUPS},
        "workers": CONTINUATION_WORKERS,
        "workers_before": mc89.WORKERS,
        "previous_r2_ledger_sha256": mc89.sha256_file(R2_DIR / "attempts.jsonl"),
        "runner_sha256": mc89.sha256_file(Path(mc89.__file__)),
        "continuation_driver_sha256": mc89.sha256_file(Path(__file__).resolve()),
        "status": "planned",
    }
    print(
        f"{CONTINUATION_ID} plan: items={len(pending_items)} workers={CONTINUATION_WORKERS} "
        f"groups={{ {', '.join(f'{name}:{len(grouped[name])}' for name in r2.GROUPS)} }} "
        f"condition_sha256={effective_hash} endpoint_calls=0",
        flush=True,
    )
    if not args.execute:
        print("Plan only; no model endpoint was called.", flush=True)
        return

    mc89.WORKERS = CONTINUATION_WORKERS
    mc89.OUTPUT_ROOT = R2_DIR
    mc89.MAIN_OUT = R2_DIR / "main" / mc89.PROFILE
    mc89.VMLU_OUT = R2_DIR / "vmlu" / mc89.PROFILE
    mc89.AGENT_ROOT = R2_DIR / "omp_workers"
    mc89.LOG_PATH = mc89.ROOT / "logs/mimo26_omp_mc89_recovery_r2.log"
    r1._patch_parsing()
    original_run_item = mc89._run_item

    def run_recovery_item(*call_args: Any, **call_kwargs: Any) -> dict[str, Any]:
        row = original_run_item(*call_args, **call_kwargs)
        row.update({
            "recovery_id": r2.RECOVERY_ID,
            "continuation_id": CONTINUATION_ID,
            "parent_condition_sha256": parent_hash,
            "recovery_condition_sha256": effective_hash,
            "max_time_seconds_per_item": r2.GROUP_TIMEOUT[r2._group_of(rows[row["run_key"]])],
            "max_tokens_per_turn": r2.GROUP_MAX_TOKENS[r2._group_of(rows[row["run_key"]])],
            "recovery_group": r2._group_of(rows[row["run_key"]]),
        })
        return row

    mc89._run_item = run_recovery_item

    state = json.loads((R2_DIR / "campaign.json").read_text(encoding="utf-8"))
    state.update({
        "pid": os.getpid(),
        "status": "running",
        "continuation_id": CONTINUATION_ID,
        "workers": CONTINUATION_WORKERS,
        "current_pass_progress": 0,
        "current_pass_total": len(pending_items),
    })
    recovery["continuation"] = dict(plan, started_at=_now(), status="running")
    mc89.atomic_json(R2_PATH, recovery)

    relay_server = relay_thread = None
    sandbox_home = scratch_root = None
    try:
        relay_server, relay_thread, local_base_url, relay_key = mc89._start_credential_relay(
            runtime["endpoint"], runtime["api_key"]
        )
        sandbox_home = Path(tempfile.mkdtemp(prefix="vmlu-mc89-r2c1-home-")).resolve()
        scratch_root = Path(tempfile.mkdtemp(prefix="vmlu-mc89-r2c1-scratch-")).resolve()
        fatal = False
        group_results: dict[str, dict[str, int]] = {}
        for name in r2.GROUPS:
            group_items = grouped[name]
            if not group_items:
                group_results[name] = {"selected": 0, "recovered": 0, "remaining": 0}
                continue
            mc89.MAX_TIME_SECONDS = r2.GROUP_TIMEOUT[name]
            mc89.MAX_OUTPUT_TOKENS_PER_TURN = r2.GROUP_MAX_TOKENS[name]
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
                f"{CONTINUATION_ID} group={name} items={len(group_items)} "
                f"timeout={r2.GROUP_TIMEOUT[name]}s max_tokens={r2.GROUP_MAX_TOKENS[name]} "
                f"workers={CONTINUATION_WORKERS}"
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
            mc89.report(f"{CONTINUATION_ID} group={name} done recovered={recovered}/{len(group_items)}")
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
        continuation = recovery["continuation"]
        continuation.update({
            "finished_at": _now(),
            "status": "complete" if not any(
                rows[item["run_key"]].get("status") != "complete" for item in pending_items
            ) else "incomplete",
            "successful_retries": sum(rows[item["run_key"]].get("status") == "complete" for item in pending_items),
            "remaining_errors": sum(rows[item["run_key"]].get("status") != "complete" for item in pending_items),
            "group_results": group_results,
        })
        recovery.update({
            "finished_at": _now(),
            "status": "complete" if not missing else "incomplete",
            "successful_retries": sum(
                rows[key].get("status") == "complete" for key in recovery["selected_run_keys"]
            ),
            "remaining_errors": sum(
                rows[key].get("status") != "complete" for key in recovery["selected_run_keys"]
            ),
            "group_results": {"continuation": group_results},
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
            f"{CONTINUATION_ID} status={continuation['status']} successful={continuation['successful_retries']}/"
            f"{len(pending_items)} campaign={final_status} complete={result['completed_n']}/"
            f"{result['expected_n']} errors={result['request_error_n']} groups={group_results}"
        )
    except BaseException as exc:
        recovery.setdefault("continuation", {}).update(
            finished_at=_now(), status="failed", failure_type=type(exc).__name__,
        )
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
