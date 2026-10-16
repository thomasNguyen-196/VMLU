"""Build a UI-safe snapshot for the expanded VMLU/V-Bench Go campaign.

Withheld server-gold scores are never inferred from local parsing diagnostics.
Run from repo root: .venv/bin/python code_benchmark/build_dashboard_vi_multimodel_expansion.py [--watch]
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "all_res" / "vi_multimodel_v2"
PROTOCOL_PATH = ROOT / "data" / "vi_multimodel_protocol_v2.json"
PROFILE_PATH = ROOT / "data" / "vi_multimodel_profiles_v2.json"
WEB_OUTPUT = ROOT / "web" / "data" / "vi-multimodel-expansion-v2-results.json"

GO_PROFILES = (
    "muse-spark-1-3-contributor",
    "mimo-v2-6-flash",
    "mimo-v2-5",
)
QWEN_PROFILE = "qwen3-5-9b-65k"
VMLU_PROFILES = (*GO_PROFILES, QWEN_PROFILE)
ALL_PROFILES = (*GO_PROFILES, QWEN_PROFILE)
DATASET_SPECS = (
    {
        "id": "vmlu_local",
        "label": "VMLU valid + dev",
        "short_label": "kiến thức",
        "n": 1_047,
        "metric": "accuracy",
        "gold": "local",
        "phase": "vmlu",
        "dataset_ids": ("vi-multimodel-v2-vmlu-valid", "vi-multimodel-v2-vmlu-dev"),
    },
    {
        "id": "vmlu_test",
        "label": "VMLU test",
        "short_label": "server grade",
        "n": 9_833,
        "metric": "server_accuracy",
        "gold": "withheld",
        "phase": "vmlu",
        "dataset_ids": ("vi-multimodel-v2-vmlu-test",),
    },
    {
        "id": "vbench_mc",
        "label": "V-Bench MC",
        "short_label": "server grade",
        "n": 4_141,
        "metric": "server_accuracy",
        "gold": "server",
        "phase": "vbench",
        "dataset_ids": ("vi-multimodel-v2-vbench-mc",),
    },
    {
        "id": "vbench_agentic",
        "label": "V-Bench agentic",
        "short_label": "function call · server grade",
        "n": 1_000,
        "metric": "server_function_accuracy",
        "gold": "server",
        "phase": "vbench",
        "dataset_ids": ("vi-multimodel-v2-vbench-agentic",),
    },
)
EXPECTED_BY_PHASE = {"vmlu": 10_880, "vbench": 5_141}
PAUSED_STATES = {"paused", "incomplete", "incomplete_exhausted", "probe_failed"}


def _read_json(path: Path, *, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: invalid JSON in {path}: {exc}") from exc


def _read_attempts(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        last_newline = raw.rfind(b"\n")
        raw = raw[: last_newline + 1] if last_newline >= 0 else b""
    latest: dict[str, dict[str, Any]] = {}
    for line_no, line in enumerate(raw.splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Error: corrupt attempt ledger {path}:{line_no}: {exc}") from exc
        key = str(row.get("run_key", ""))
        if key:
            latest[key] = row
    return latest


def _wilson_interval(successes: int, n: int) -> list[float] | None:
    if n <= 0:
        return None
    z = 1.959963984540054
    proportion = successes / n
    denominator = 1 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    radius = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * n)) / n) / denominator
    return [round(max(0.0, center - radius) * 100, 4), round(min(1.0, center + radius) * 100, 4)]


def _phase_snapshot(phase: str, profile_id: str) -> dict[str, Any]:
    run_dir = OUTPUT_ROOT / phase / profile_id
    metadata = _read_json(run_dir / "run.json")
    if metadata is None:
        return {
            "status": "queued",
            "expected_n": EXPECTED_BY_PHASE[phase],
            "complete_n": 0,
            "request_error_n": 0,
            "by_dataset": {},
            "metadata": None,
            "summary": {},
        }

    attempts = _read_attempts(run_dir / "attempts.jsonl")
    by_dataset: dict[str, dict[str, int]] = {}
    for row in attempts.values():
        dataset_id = str(row.get("dataset_id", ""))
        counts = by_dataset.setdefault(dataset_id, {"complete_n": 0, "request_error_n": 0})
        if row.get("status") == "complete":
            counts["complete_n"] += 1
        else:
            counts["request_error_n"] += 1

    summary = _read_json(run_dir / "summary.json")
    summary_by_id = {
        str(row.get("dataset_id")): row
        for row in (summary or {}).get("datasets", [])
        if isinstance(row, dict)
    }
    return {
        "status": str(metadata.get("status", "unknown")),
        "expected_n": int(metadata.get("item_count", EXPECTED_BY_PHASE[phase])),
        "complete_n": sum(row.get("status") == "complete" for row in attempts.values()),
        "request_error_n": sum(row.get("status") != "complete" for row in attempts.values()),
        "by_dataset": by_dataset,
        "metadata": metadata,
        "summary": summary_by_id,
    }


def _cell(
    *,
    spec: dict[str, Any],
    phase: dict[str, Any],
    profile_id: str,
    card_id: str | None,
) -> dict[str, Any]:
    supported_profiles = VMLU_PROFILES if spec["phase"] == "vmlu" else GO_PROFILES
    if profile_id not in supported_profiles:
        return {
            "profile_id": profile_id,
            "dataset_id": spec["id"],
            "status": "awaiting_user_review",
            "expected_n": spec["n"],
            "completed_n": 0,
            "request_error_n": 0,
            "accuracy": None,
            "accuracy_ci95": None,
            "parse_valid_n": None,
            "parse_valid_pct": None,
            "truncated_n": None,
            "latency_s_p50": None,
            "latency_s_p90": None,
            "card_id": card_id,
        }

    dataset_stats = [phase["by_dataset"].get(dataset_id, {}) for dataset_id in spec["dataset_ids"]]
    completed_n = sum(int(row.get("complete_n", 0)) for row in dataset_stats)
    request_error_n = sum(int(row.get("request_error_n", 0)) for row in dataset_stats)
    if phase["status"] == "running" and completed_n >= spec["n"]:
        # A local-gold subset may finish before the withheld split completes.
        # Keep it out of the headline until the phase summary is finalized.
        initial_status = "pending_score"
    else:
        initial_status = "queued" if phase["status"] == "queued" else "running"
    cell: dict[str, Any] = {
        "profile_id": profile_id,
        "dataset_id": spec["id"],
        "status": initial_status,
        "expected_n": spec["n"],
        "completed_n": completed_n,
        "request_error_n": request_error_n,
        "accuracy": None,
        "accuracy_ci95": None,
        "parse_valid_n": None,
        "parse_valid_pct": None,
        "truncated_n": None,
        "latency_s_p50": None,
        "latency_s_p90": None,
        "card_id": card_id,
    }

    if phase["status"] in PAUSED_STATES:
        cell["status"] = "paused"
    elif phase["status"] == "complete":
        cell["status"] = "pending_score"

    score_rows = [phase["summary"].get(dataset_id) for dataset_id in spec["dataset_ids"]]
    if spec["gold"] == "local":
        if len(score_rows) == len(spec["dataset_ids"]) and all(
            row and row.get("status") == "complete_local_score" for row in score_rows
        ):
            correct = sum(int(row.get("correct", 0)) for row in score_rows)
            parse_valid_n = sum(int(row.get("parse_valid_n", 0)) for row in score_rows)
            truncated_n = sum(int(row.get("truncated_n", 0)) for row in score_rows)
            cell.update({
                "status": "scored",
                "completed_n": spec["n"],
                "correct": correct,
                "accuracy": round(100 * correct / spec["n"], 2),
                "accuracy_ci95": _wilson_interval(correct, spec["n"]),
                "parse_valid_n": parse_valid_n,
                "parse_valid_pct": round(100 * parse_valid_n / spec["n"], 2),
                "truncated_n": truncated_n,
                "latency_s_p50": None,
                "latency_s_p90": None,
                "request_error_n": 0,
            })
        return cell

    score_row = score_rows[0] if score_rows else None
    if score_row:
        cell["completed_n"] = int(score_row.get("request_completed_n", completed_n))
        cell["request_error_n"] = int(score_row.get("request_error_n", request_error_n))
        cell["parse_valid_n"] = score_row.get("parse_valid_n")
        cell["parse_valid_pct"] = score_row.get("parse_valid_pct_of_completed")
        cell["truncated_n"] = score_row.get("truncated_n")
        cell["latency_s_p50"] = score_row.get("latency_s_p50")
        cell["latency_s_p90"] = score_row.get("latency_s_p90")
        if score_row.get("status") == "complete_awaiting_server_score":
            cell["status"] = "awaiting_server_grade"
        elif score_row.get("status", "").startswith("incomplete"):
            cell["status"] = "running" if phase["status"] == "running" else "paused"
    return cell


def build_snapshot() -> dict[str, Any]:
    try:
        protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        profile_doc = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read expansion-v2 configuration: {exc}") from exc

    profiles_by_id = {row["profile_id"]: row for row in profile_doc["profiles"]}
    phases: dict[tuple[str, str], dict[str, Any]] = {}
    for profile_id in ALL_PROFILES:
        for phase_name in ("vmlu", "vbench"):
            phases[(phase_name, profile_id)] = _phase_snapshot(phase_name, profile_id)

    profile_rows = []
    cells = []
    for profile_id in ALL_PROFILES:
        config = profiles_by_id[profile_id]
        card_ids = config.get("measurement_card_ids_v2", {})
        vmlu = phases.get(("vmlu", profile_id))
        vbench = phases.get(("vbench", profile_id))
        run_statuses = [phase["status"] for phase in (vmlu, vbench) if phase is not None]
        if profile_id == QWEN_PROFILE:
            profile_status = (
                "awaiting_server_grade"
                if vmlu and vmlu["status"] == "complete"
                else "paused" if vmlu and vmlu["status"] in PAUSED_STATES
                else str(vmlu["status"]) if vmlu else "awaiting_user_review"
            )
        elif any(status in PAUSED_STATES for status in run_statuses):
            profile_status = "paused"
        elif all(status == "complete" for status in run_statuses):
            profile_status = "complete"
        else:
            profile_status = "running" if any(status == "running" for status in run_statuses) else "queued"

        profile_rows.append({
            "id": profile_id,
            "display_name": config.get("display_name", profile_id),
            "provider": config.get("provider", ""),
            "api_protocol": config.get("api_protocol", ""),
            "status": profile_status,
            "billing_mode": config.get("billing_mode", ""),
            "reasoning": "auto" if profile_id in VMLU_PROFILES else "chờ duyệt",
        })

        for spec in DATASET_SPECS:
            phase = phases.get((spec["phase"], profile_id))
            if phase is None:
                cell = _cell(spec=spec, phase={"status": "queued", "by_dataset": {}, "summary": {}}, profile_id=profile_id, card_id=None)
            else:
                metadata = phase.get("metadata") or {}
                card_id = metadata.get("measurement_card_id") or card_ids.get(spec["phase"])
                cell = _cell(spec=spec, phase=phase, profile_id=profile_id, card_id=card_id)
            cells.append(cell)

    pilot_rows = []
    for profile_id in ALL_PROFILES:
        path = OUTPUT_ROOT / "pilot" / profile_id / "summary.json"
        summary = _read_json(path)
        by_dataset = {
            str(row.get("dataset_id")): row
            for row in (summary or {}).get("datasets", [])
            if isinstance(row, dict)
        }
        dev = by_dataset.get("vi-multimodel-v2-vmlu-dev", {})
        agentic = by_dataset.get("vi-multimodel-v2-pilot-agentic-synthetic", {})
        pilot_rows.append({
            "profile_id": profile_id,
            "status": "complete" if summary and summary.get("request_error_n") == 0 else "awaiting_user_review" if profile_id not in GO_PROFILES else "queued",
            "vmlu_dev_accuracy": dev.get("accuracy"),
            "vmlu_dev_n": dev.get("expected_n"),
            "vmlu_dev_repeat_agreement_pct": dev.get("repeat_agreement_pct"),
            "vmlu_dev_parse_valid_pct": dev.get("parse_valid_pct_of_completed"),
            "synthetic_agentic_accuracy": agentic.get("accuracy"),
            "synthetic_agentic_n": agentic.get("expected_n"),
            "synthetic_agentic_parse_valid_pct": agentic.get("parse_valid_pct_of_completed"),
            "synthetic_agentic_repeat_agreement_pct": agentic.get("repeat_agreement_pct"),
        })

    manifest_hashes = {}
    for phase_name in ("vmlu", "vbench"):
        path = ROOT / "data" / "vi_multimodel_v2" / f"{phase_name}_v2.json"
        manifest = _read_json(path, default={}) or {}
        manifest_hashes[phase_name] = manifest.get("manifest_sha256")

    vmlu_states = [phases[("vmlu", profile_id)]["status"] for profile_id in VMLU_PROFILES]
    if any(state in PAUSED_STATES for state in vmlu_states):
        campaign_status = "paused"
    elif any(state in {"running", "queued"} for state in vmlu_states):
        campaign_status = "running"
    else:
        campaign_status = "awaiting_server_grade"

    return {
        "protocol_id": protocol["protocol_id"],
        "protocol_version": protocol["protocol_version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": campaign_status,
        "profiles": profile_rows,
        "datasets": [
            {key: value for key, value in spec.items() if key not in {"phase", "dataset_ids"}}
            for spec in DATASET_SPECS
        ],
        "cells": cells,
        "phases": {
            f"{phase_name}:{profile_id}": {
                "status": phases[(phase_name, profile_id)]["status"],
                "expected_n": phases[(phase_name, profile_id)]["expected_n"],
                "complete_n": phases[(phase_name, profile_id)]["complete_n"],
                "request_error_n": phases[(phase_name, profile_id)]["request_error_n"],
                "card_id": (phases[(phase_name, profile_id)]["metadata"] or {}).get("measurement_card_id"),
                "manifest_sha256": (phases[(phase_name, profile_id)]["metadata"] or {}).get("manifest_sha256"),
            }
            for phase_name in ("vmlu", "vbench")
            for profile_id in ALL_PROFILES
        },
        "pilot": pilot_rows,
        "manifest_hashes": manifest_hashes,
        "conditions": {
            "execution_transport": protocol["execution_transport"],
            "omp_version_required": protocol["omp_version_required"],
            "mode": protocol["omp_mode"],
            "system_prompt": protocol["omp_system_prompt"],
            "tools": protocol["omp_tools"],
            "session_policy": protocol["omp_session_policy"],
            "workers_per_profile": protocol["workers_per_profile"],
            "max_parallel_opencode_profiles": protocol["max_parallel_opencode_profiles"],
            "reasoning_policy": protocol["reasoning_policy"],
            "sdk_retries": protocol["sdk_retries"],
            "max_technical_recovery_attempts": protocol["max_technical_recovery_attempts"],
            "max_time_seconds": protocol["omp_max_time_seconds"],
            "completion_token_caps": {
                "vmlu_multiple_choice": protocol["phases"]["vmlu"]["max_completion_tokens"]["multiple_choice"],
                "vbench_multiple_choice": protocol["phases"]["vbench"]["max_completion_tokens"]["multiple_choice"],
                "vbench_function_call": protocol["phases"]["vbench"]["max_completion_tokens"]["function_call"],
            },
            "gold_policy": protocol["gold_policy"],
            "safety_policy": protocol["safety_policy"],
            "submission_policy": "artifacts are prepared locally; no portal upload has been made",
            "qwen_policy": "MC-70 VMLU-only run complete at 10,880 requests with temperature 1.0 and thinking auto; VMLU Test awaits user-submitted server grade; V-Bench remains deferred.",
            "muse_data_handling_note": "OpenCode documents Muse Spark Contributor prompts and completions as eligible for Meta model training; benchmark source items are public.",
            "muse_data_handling_source": "https://opencode.ai/docs/go/",
        },
    }


def _write_snapshot(snapshot: dict[str, Any]) -> None:
    WEB_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = WEB_OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(WEB_OUTPUT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the expansion-v2 dashboard snapshot from run ledgers.")
    parser.add_argument("--watch", action="store_true", help="refresh repeatedly while the campaign runs")
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args()
    if args.interval_seconds < 30:
        raise SystemExit("Error: --interval-seconds must be at least 30")

    while True:
        snapshot = build_snapshot()
        _write_snapshot(snapshot)
        print(f"wrote {WEB_OUTPUT}", flush=True)
        if not args.watch:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
