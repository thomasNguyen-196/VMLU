"""Run the expanded VMLU/V-Bench protocol through OMP.

The v2 manifest distinguishes local gold from withheld server-scored tracks.
V1 outputs remain untouched. Run from repo root; preflight is the default.
"""
from __future__ import annotations

import atexit
import argparse
import fcntl
import json
import math
import os
import re
import shutil
import subprocess  # nosec B404 # used for the fixed OMP version probe below
import tempfile
import threading
from collections import Counter, deque
from contextlib import ExitStack
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from tqdm import tqdm

try:
    from code_benchmark.run_vi_multimodel_eval import (
        _price,
        _request_bound_usd,
        _resolve_model,
        _run_omp_request,
        _atomic_json,
    )
    from code_benchmark.score_reading_eval import measurement_card_hash
    from code_benchmark.vi_multimodel import canonical_json, sha256_bytes, write_jsonl_atomic
    from code_benchmark.vi_multimodel_expansion import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        ExpandedItem,
        item_from_manifest_row,
        load_manifest,
        load_profiles,
        rebuild_items,
    )
except ImportError:
    from run_vi_multimodel_eval import (
        _price,
        _request_bound_usd,
        _resolve_model,
        _run_omp_request,
        _atomic_json,
    )
    from score_reading_eval import measurement_card_hash
    from vi_multimodel import canonical_json, sha256_bytes, write_jsonl_atomic
    from vi_multimodel_expansion import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        ExpandedItem,
        item_from_manifest_row,
        load_manifest,
        load_profiles,
        rebuild_items,
    )

load_dotenv()

PROTOCOL_PATH = Path("data/vi_multimodel_protocol_v2.json")
MAX_TECHNICAL_ATTEMPTS = 3
PAUSE_ERRORS_IN_FLIGHT = 3
SNAPSHOT_EVERY = 100


def fixed_shard_batches(items: list, workers: int) -> list[list]:
    """Stable contiguous partitions of the full manifest, including on resume."""
    if workers < 1:
        raise ValueError("workers must be positive")
    quotient, remainder = divmod(len(items), workers)
    batches = []
    start = 0
    for index in range(workers):
        stop = start + quotient + int(index < remainder)
        batches.append(items[start:stop])
        start = stop
    return batches


def _release_run_lock(handle) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _acquire_run_lock(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise SystemExit(f"Error: another process owns this model/phase run: {path.parent}") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}) + "\n")
    handle.flush()
    os.fsync(handle.fileno())
    atexit.register(_release_run_lock, handle)


def _read_protocol() -> dict[str, Any]:
    try:
        protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read expansion protocol: {exc}") from exc
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 2:
        raise SystemExit(f"Error: invalid expansion protocol identity: {PROTOCOL_PATH}")
    return protocol


def _cap_for(item: ExpandedItem, phase_settings: dict[str, Any]) -> int:
    cap_key = "function_call" if item.task == "function_call" else "multiple_choice"
    cap = phase_settings.get("max_completion_tokens", {}).get(cap_key)
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise SystemExit(f"Error: missing positive output cap for {cap_key}")
    return cap


def _usage_cost(row: dict[str, Any], profile: dict[str, Any]) -> float | None:
    prompt_tokens = row.get("prompt_tokens")
    cached_tokens = row.get("cached_prompt_tokens")
    completion_tokens = row.get("completion_tokens")
    if not all(isinstance(v, int) and v >= 0 for v in (prompt_tokens, cached_tokens, completion_tokens)):
        return None
    input_rate = float(profile.get("input_price_usd_per_million", 0.0))
    cached_rate = float(profile.get("cached_input_price_usd_per_million", 0.0))
    output_rate = float(profile.get("output_price_usd_per_million", 0.0))
    cached = min(prompt_tokens, cached_tokens)
    uncached = prompt_tokens - cached
    return (uncached * input_rate + cached * cached_rate + completion_tokens * output_rate) / 1_000_000


def _technical_pause_reason(row: dict[str, Any]) -> str | None:
    if row.get("status") == "complete":
        return None
    detail = f"{row.get('error_type', '')} {row.get('error_detail', '')}".casefold()
    if any(token in detail for token in ("401", "403", "unauthorized", "authentication", "forbidden")):
        return "provider_auth_or_access"
    if any(token in detail for token in ("400", "bad request", "invalid model", "model not found", "unsupported parameter")):
        return "provider_request_configuration"
    if any(token in detail for token in ("429", "rate limit", "quota", "too many requests", "resource_exhausted", "usage limit")):
        return "provider_rate_or_quota_limit"
    return None


def _write_snapshot(output_dir: Path, rows_by_key: dict[str, dict[str, Any]]) -> None:
    ordered = [rows_by_key[key] for key in sorted(rows_by_key)]
    write_jsonl_atomic(output_dir / "predictions.jsonl", ordered)


def _append_attempt(output_dir: Path, attempt: dict[str, Any]) -> None:
    path = output_dir / "attempts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(attempt, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_attempts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = path.read_bytes()
    complete = data.endswith(b"\n")
    lines = data.splitlines(keepends=True)
    if lines and not complete:
        tail = lines.pop()
        if tail:
            partial = path.with_suffix(".partial")
            partial.write_bytes(tail)
        good_bytes = b"".join(lines)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_bytes(good_bytes)
        tmp.replace(path)
    rows = []
    for lineno, line in enumerate(lines, 1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Error: corrupt attempt ledger {path}:{lineno}: {exc}") from exc
    return rows


def _load_existing(output_dir: Path, *, config_hash: str, resume: bool, expected_keys: set[str], config: dict[str, Any]):
    run_path = output_dir / "run.json"
    if not run_path.exists():
        unrelated = [path.name for path in output_dir.iterdir() if path.name != ".run.lock"] if output_dir.exists() else []
        if not unrelated:
            return {}, {}, []
        raise SystemExit(f"Error: partial output directory has no run metadata: {output_dir}")
    if not output_dir.exists():
        return {}, {}, []
    if not resume:
        raise SystemExit(f"Error: output directory exists; pass --resume: {output_dir}")
    if not run_path.is_file():
        raise SystemExit(f"Error: cannot resume without {run_path}")
    meta = json.loads(run_path.read_text(encoding="utf-8"))
    if meta.get("config_sha256") != config_hash:
        raise SystemExit(f"Error: settings/source/card changed since this run: {output_dir}")
    attempt_rows = _read_attempts(output_dir / "attempts.jsonl")
    latest: dict[str, dict[str, Any]] = {}
    attempts: dict[str, int] = {}
    for row in attempt_rows:
        key = str(row.get("run_key", ""))
        if not key or key not in expected_keys:
            raise SystemExit(f"Error: attempt outside frozen manifest: {key!r}")
        next_attempt = int(row.get("attempt_index", 0))
        if next_attempt != attempts.get(key, 0) + 1:
            raise SystemExit(f"Error: attempt index gap/duplicate for {key}")
        attempts[key] = next_attempt
        latest[key] = row
    if not attempt_rows:
        predictions_path = output_dir / "predictions.jsonl"
        if predictions_path.exists():
            for row in (json.loads(line) for line in predictions_path.read_text(encoding="utf-8").splitlines() if line.strip()):
                key = str(row.get("run_key", ""))
                if not key or key not in expected_keys:
                    raise SystemExit(f"Error: checkpoint outside frozen manifest: {key!r}")
                if row.get("status") not in {"complete", "request_error"}:
                    raise SystemExit(f"Error: invalid checkpoint status for {key}")
                latest[key] = row
                attempts[key] = int(row.get("attempts", 1))
    return latest, meta, attempt_rows


def _save_card_snapshot(card_path: Path, output_dir: Path, expected_hash: str) -> None:
    snapshot_path = output_dir / "measurement_card_snapshot.md"
    current = card_path.read_bytes()
    if sha256_bytes(current) != expected_hash:
        raise SystemExit("Error: measurement card changed while preparing the run")
    if snapshot_path.exists():
        if sha256_bytes(snapshot_path.read_bytes()) != expected_hash:
            raise SystemExit(f"Error: card snapshot differs from frozen hash: {snapshot_path}")
        return
    tmp = snapshot_path.with_suffix(".md.tmp")
    tmp.write_bytes(current)
    tmp.replace(snapshot_path)


def run_phase(*, phase: str, profile_id: str, args: argparse.Namespace) -> int:
    profiles = load_profiles()
    profile = profiles.get(profile_id)
    if profile is None:
        raise SystemExit(f"Error: unknown expansion profile {profile_id}")
    protocol = _read_protocol()
    phase_settings = protocol["phases"].get(phase)
    if not isinstance(phase_settings, dict):
        raise SystemExit(f"Error: no frozen settings for expansion phase {phase}")
    if protocol.get("execution_transport") != "omp" or protocol.get("sdk_retries") != 0:
        raise SystemExit("Error: expansion v2 requires OMP transport with SDK retries disabled")
    manifest = load_manifest(phase)
    rebuilt = rebuild_items(phase)
    items = [item_from_manifest_row(row, rebuilt) for row in manifest["items"]]
    workers = int(protocol.get("workers_per_profile", 0))
    if not 1 <= workers <= 4:
        raise SystemExit("Error: expansion protocol permits 1..4 workers per profile")
    workers_per_shard = int(getattr(args, "workers_per_shard", 1))
    fixed_shards_requested = bool(getattr(args, "fixed_shards", False))
    if workers_per_shard < 1 or workers * workers_per_shard > 12:
        raise SystemExit("Error: fixed-shard concurrency must be between 1 and 12 workers total")
    if workers_per_shard > 1 and not fixed_shards_requested:
        raise SystemExit("Error: --workers-per-shard requires --fixed-shards")
    input_rate = _price(profile, "input_price_usd_per_million")
    output_rate = _price(profile, "output_price_usd_per_million")
    cached_rate = _price(profile, "cached_input_price_usd_per_million")
    caps = {item.run_key: _cap_for(item, phase_settings) for item in items}
    bounds = {
        item.run_key: _request_bound_usd(item.prompt, caps[item.run_key], input_rate, output_rate)
        for item in items
    }
    probe_bound = _request_bound_usd("ping", int(protocol["probe_max_tokens"]), input_rate, output_rate)
    estimate = sum(bounds.values()) + probe_bound
    guard = float(phase_settings["budget_guard_usd_equivalent"][profile_id])
    print(f"worst_case_usage_usd_equivalent={estimate:.6f}")
    schedule = (
        f"shards={workers} workers_per_shard={workers_per_shard} total_workers={workers * workers_per_shard}"
        if fixed_shards_requested else f"workers={workers}"
    )
    print(
        f"protocol={PROTOCOL_ID} phase={phase} profile={profile_id} items={len(items)} "
        f"{schedule} tasks={dict(Counter(item.task for item in items))} guard={guard:.2f}"
    )
    if estimate > guard:
        raise SystemExit(f"Error: preflight bound {estimate:.6f} exceeds frozen guard {guard:.6f}")
    if not args.execute:
        print("preflight only; no model endpoint was called")
        return 0
    if args.max_cost_usd is None or args.max_cost_usd <= 0 or not math.isfinite(args.max_cost_usd):
        raise SystemExit("Error: --execute requires a positive --max-cost-usd")
    if args.max_cost_usd > guard:
        raise SystemExit(f"Error: requested cap {args.max_cost_usd:.6f} exceeds preregistered guard {guard:.6f}")
    if estimate > args.max_cost_usd:
        raise SystemExit(f"Error: preflight bound {estimate:.6f} exceeds requested cap {args.max_cost_usd:.6f}")

    endpoint, api_key, request_model, credential_source = _resolve_model(profile)
    card_id = str(profile.get("measurement_card_ids_v2", {}).get(phase, ""))
    card_path = Path(getattr(args, "measurement_card", "measurement_card.md"))
    if not card_id or not card_path.is_file() or f"| `{card_id}` |" not in card_path.read_text(encoding="utf-8"):
        raise SystemExit(f"Error: preregister card for {profile_id}/{phase} before inference")
    card_hash = measurement_card_hash(card_path)
    version_result = subprocess.run([args.omp_bin, "--version"], capture_output=True, text=True, timeout=15, check=False)  # nosec B603 # operator-selected executable, fixed version flag, no shell
    if version_result.returncode != 0:
        raise SystemExit(f"Error: cannot launch OMP ({version_result.returncode})")
    omp_version = (version_result.stdout or version_result.stderr).strip()
    if omp_version != str(protocol["omp_version_required"]):
        raise SystemExit(f"Error: OMP version drift: expected {protocol['omp_version_required']}, got {omp_version}")

    output_dir = OUTPUT_DIR / phase / profile_id
    output_dir.mkdir(parents=True, exist_ok=True)
    _acquire_run_lock(output_dir / ".run.lock")
    config = {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": 2,
        "phase": phase,
        "profile_id": profile_id,
        "model_id": profile["model_id"],
        "model_ref": profile["model_ref"],
        "provider": profile["provider"],
        "api_protocol": profile["api_protocol"],
        "billing_mode": profile["billing_mode"],
        "credential_source": credential_source,
        "endpoint_host": re.sub(r"^https?://", "", endpoint).split("/", 1)[0],
        "transport": "omp",
        "omp_version": omp_version,
        "omp_mode": protocol["omp_mode"],
        "omp_system_prompt": protocol["omp_system_prompt"],
        "omp_tools": protocol["omp_tools"],
        "omp_session_policy": protocol["omp_session_policy"],
        "omp_max_time_seconds": int(protocol["omp_max_time_seconds"]),
        "measurement_card_id": card_id,
        "measurement_card_hash": card_hash,
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": manifest["protocol_sha256"],
        "profile_roster_sha256": manifest["profile_roster_sha256"],
        "profile_file_sha256": manifest["profile_file_sha256"],
        "source_sha256": manifest["source_sha256"],
        "temperature_effective": profile.get("temperature_effective", profile.get("temperature", 0.0)),
        "temperature_policy": profile.get("temperature_policy", "profile/model config"),
        "seed_requested": 42,
        "seed_sent": bool(profile.get("send_seed", True)),
        "seed_policy": profile.get("seed_policy", "profile/model config"),
        "omp_reasoning": bool(profile.get("omp_reasoning", True)),
        "omp_thinking": str(profile.get("omp_thinking", "auto")),
        "workers": workers,
        "sdk_retries": 0,
        "max_technical_attempts": MAX_TECHNICAL_ATTEMPTS,
        "input_price_usd_per_million": input_rate,
        "cached_input_price_usd_per_million": cached_rate,
        "output_price_usd_per_million": output_rate,
        "budget_guard_usd_equivalent": guard,
        "max_cost_usd": args.max_cost_usd,
        "worst_case_usage_usd_equivalent": estimate,
        "item_count": len(items),
        "safety_rows_skipped": manifest.get("safety_rows_skipped", 0),
    }
    config_hash = sha256_bytes(canonical_json(config))
    expected_keys = {item.run_key for item in items}
    latest, old_meta, attempt_rows = _load_existing(
        output_dir,
        config_hash=config_hash,
        resume=args.resume,
        expected_keys=expected_keys,
        config=config,
    )
    fixed_shards = bool(getattr(args, "fixed_shards", False))
    if old_meta.get("scheduling_policy") == "fixed-shards" and not fixed_shards:
        raise SystemExit("Error: resume this run with --fixed-shards to preserve worker assignments")
    shard_batches = fixed_shard_batches(items, workers) if fixed_shards else []
    if fixed_shards:
        plan = {"manifest_sha256": manifest["manifest_sha256"], "workers": workers,
                "shards": [{"worker": index + 1, "run_keys": [item.run_key for item in batch]}
                           for index, batch in enumerate(shard_batches)]}
        plan_path = output_dir / "fixed_shards.json"
        if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
            raise SystemExit("Error: fixed worker assignments changed since this run")
        _atomic_json(plan_path, plan)
        manifest_batches = fixed_shard_batches(manifest["items"], workers)
        for index, rows in enumerate(manifest_batches):
            part_path = output_dir / "fixed_shards" / f"worker_{index + 1}.jsonl"
            if part_path.exists():
                saved_rows = [json.loads(line) for line in part_path.read_text().splitlines() if line.strip()]
                if saved_rows != rows:
                    raise SystemExit(f"Error: saved worker part changed: {part_path}")
            else:
                part_path.parent.mkdir(parents=True, exist_ok=True)
                write_jsonl_atomic(part_path, rows)
    attempts_by_key: dict[str, int] = {}
    attempt_cost = 0.0
    for row in attempt_rows:
        key = str(row["run_key"])
        attempts_by_key[key] = int(row["attempt_index"])
        attempt_cost += float(row.get("reserved_cost_usd", 0.0))
    for key, row in latest.items():
        attempts_by_key.setdefault(key, int(row.get("attempts", 0)))
        if not attempt_rows:
            attempt_cost += float(row.get("reserved_cost_usd", 0.0))
    completed = {key for key, row in latest.items() if row.get("status") == "complete"}
    remaining = [item for item in items if item.run_key not in completed]
    next_attempt_reserve = sum(
        bounds[item.run_key]
        for item in remaining
        if attempts_by_key.get(item.run_key, 0) < MAX_TECHNICAL_ATTEMPTS
    )
    pending_reserve = next_attempt_reserve
    old_probe_reserve = float(old_meta.get("probe_reserved_cost_usd", 0.0)) if old_meta else 0.0
    probe_pending = not bool(old_meta.get("probe_completed")) if old_meta else True
    probe_reserve_total = old_probe_reserve + (probe_bound if probe_pending else 0.0)
    projected = attempt_cost + next_attempt_reserve + probe_reserve_total
    if projected > args.max_cost_usd:
        raise SystemExit(f"Error: cumulative retry reserve {projected:.6f} exceeds run cap {args.max_cost_usd:.6f}")

    _save_card_snapshot(card_path, output_dir, card_hash)
    attempt_path = output_dir / "attempts.jsonl"
    lock = threading.Lock()
    temp_root = Path(tempfile.mkdtemp(prefix=f"vmlu-omp-v2-{phase}-{profile_id}-"))
    fake_home = temp_root / "home"
    fake_home.mkdir()
    agent_root = temp_root / "agents"
    agent_root.mkdir()
    meta = dict(old_meta or {})
    if args.resume and meta.get("pause_reason"):
        meta["previous_pause_reason"] = meta.pop("pause_reason")
    if args.resume and meta.get("paused_at"):
        meta["last_resumed_at"] = datetime.now(timezone.utc).isoformat()
        meta.pop("paused_at")
    meta.update(config)
    meta.update({
        "config_sha256": config_hash,
        "started_at": meta.get("started_at") or datetime.now(timezone.utc).isoformat(),
        "status": "probe_pending" if probe_pending else "running",
        "complete_items": len(completed),
        "failed_items": sum(row.get("status") == "request_error" for row in latest.values()),
        "pending_items": len(items) - len(completed),
        "latest_attempted_items": len(latest),
        "attempt_ledger": str(attempt_path),
    })
    if fixed_shards:
        meta["scheduling_policy"] = "fixed-shards"
        meta.setdefault("scheduling_changed_at", datetime.now(timezone.utc).isoformat())
        meta.setdefault("completed_before_fixed_shards", len(completed))
        current_layout = {
            "shards": workers,
            "workers_per_shard": workers_per_shard,
            "total_workers": workers * workers_per_shard,
        }
        previous_layout = {
            "shards": int((old_meta or {}).get("workers", workers)),
            "workers_per_shard": int((old_meta or {}).get("workers_per_shard", 1)),
        }
        previous_layout["total_workers"] = previous_layout["shards"] * previous_layout["workers_per_shard"]
        layout_history = list(meta.get("worker_layout_history", []))
        if old_meta and previous_layout != current_layout:
            if not layout_history:
                layout_history.append({
                    **previous_layout,
                    "observed_at": old_meta.get("last_progress_at") or old_meta.get("started_at", ""),
                })
            last_layout = layout_history[-1]
            if any(last_layout.get(key) != value for key, value in current_layout.items()):
                layout_history.append({**current_layout, "observed_at": datetime.now(timezone.utc).isoformat()})
        meta["workers_per_shard"] = workers_per_shard
        meta["total_workers"] = workers * workers_per_shard
        meta["omp_home_initialization_policy"] = "serialize-first-omp-request-per-run"
        meta["worker_layout_history"] = layout_history
    _atomic_json(output_dir / "run.json", meta)

    def save_progress(status: str | None = None, pause_reason: str | None = None) -> None:
        nonlocal meta
        with lock:
            _write_snapshot(output_dir, latest)
            meta["complete_items"] = sum(row.get("status") == "complete" for row in latest.values())
            meta["failed_items"] = sum(row.get("status") == "request_error" for row in latest.values())
            meta["pending_items"] = len(items) - meta["complete_items"]
            meta["latest_attempted_items"] = len(latest)
            meta["last_progress_at"] = datetime.now(timezone.utc).isoformat()
            if fixed_shards:
                meta["shards"] = [{
                    "worker": index + 1, "assigned": len(batch),
                    "workers": workers_per_shard,
                    "complete": sum(latest.get(item.run_key, {}).get("status") == "complete" for item in batch),
                    "failed": sum(latest.get(item.run_key, {}).get("status") == "request_error" for item in batch),
                } for index, batch in enumerate(shard_batches)]
            if status:
                meta["status"] = status
            if pause_reason:
                meta["pause_reason"] = pause_reason
            _atomic_json(output_dir / "run.json", meta)

    if fixed_shards:
        save_progress(status=meta["status"])

    try:
        if probe_pending:
            meta["probe_attempt_count"] = int(meta.get("probe_attempt_count", 0)) + 1
            meta["probe_max_tokens"] = int(protocol["probe_max_tokens"])
            meta["probe_reserved_cost_usd"] = old_probe_reserve + probe_bound
            _atomic_json(output_dir / "run.json", meta)
            probe = _run_omp_request(
                omp_bin=args.omp_bin,
                profile=profile,
                model_id=request_model,
                endpoint=endpoint,
                prompt="ping",
                request_key=f"probe:{PROTOCOL_ID}:{phase}:{profile_id}",
                max_tokens=int(protocol["probe_max_tokens"]),
                max_time=int(protocol["omp_max_time_seconds"]),
                thinking=str(profile.get("omp_thinking", "auto")),
                tmp_root=agent_root,
                fake_home=fake_home,
                api_key=api_key,
            )
            meta["probe_status"] = probe["status"]
            meta["probe_request_id"] = probe.get("request_id", "")
            meta["probe_response_model_id"] = probe.get("response_model_id", "")
            meta["probe_prompt_tokens"] = probe.get("prompt_tokens")
            meta["probe_completion_tokens"] = probe.get("completion_tokens")
            meta["probe_error_type"] = probe.get("error_type", "")
            meta["probe_error_detail"] = probe.get("error_detail", "")
            meta["probe_completed"] = probe["status"] == "complete"
            if probe["status"] != "complete":
                meta["status"] = "probe_failed"
                _atomic_json(output_dir / "run.json", meta)
                raise SystemExit(f"Error: OMP preflight probe failed: {probe.get('error_detail', '')}")
            meta["status"] = "running"
            _atomic_json(output_dir / "run.json", meta)

        retries_exhausted = [item.run_key for item in remaining if attempts_by_key.get(item.run_key, 0) >= MAX_TECHNICAL_ATTEMPTS]
        if retries_exhausted:
            meta["exhausted_error_items"] = retries_exhausted
            save_progress(status="incomplete_exhausted")
            raise SystemExit(f"Error: {len(retries_exhausted)} items reached {MAX_TECHNICAL_ATTEMPTS} technical attempts")

        home_initialization_lock = threading.Lock()
        home_initialized = False

        def process(item: ExpandedItem, attempt_index: int) -> dict[str, Any]:
            nonlocal home_initialized
            cap = _cap_for(item, phase_settings)
            run_key = item.run_key
            request_key = f"{PROTOCOL_ID}:{phase}:{profile_id}:{run_key}"

            def request_item() -> dict[str, Any]:
                return _run_omp_request(
                    omp_bin=args.omp_bin,
                    profile=profile,
                    model_id=request_model,
                    endpoint=endpoint,
                    prompt=item.prompt,
                    request_key=request_key,
                    max_tokens=cap,
                    max_time=int(protocol["omp_max_time_seconds"]),
                    thinking=str(profile.get("omp_thinking", "auto")),
                    tmp_root=agent_root,
                    fake_home=fake_home,
                    api_key=api_key,
                )

            with home_initialization_lock:
                initialize_home = not home_initialized
                result = request_item() if initialize_home else None
                sqlite_schema_race = (
                    "no such table: main.auth_credential_refresh_leases"
                    in str(result.get("error_detail", "")).casefold()
                    if result else False
                )
                if initialize_home and not sqlite_schema_race:
                    home_initialized = True
            if not initialize_home:
                result = request_item()
            return {
                "run_key": run_key,
                "protocol_id": PROTOCOL_ID,
                "phase": phase,
                "profile_id": profile_id,
                "dataset_id": item.dataset_id,
                "item_id": item.item_id,
                "replicate_id": item.replicate_id,
                "track": item.task,
                "stratum": item.stratum,
                "gold_status": item.gold_status,
                "prompt_sha256": sha256_bytes(item.prompt.encode("utf-8")),
                "schema_sha256": sha256_bytes(canonical_json(item.functions)) if item.functions else "",
                "raw_prompt": item.prompt,
                "raw_response": result["raw_response"],
                "response_model_id": result["response_model_id"],
                "request_id": result["request_id"],
                "finish_reason": result["finish_reason"],
                "prompt_tokens": result["prompt_tokens"],
                "cached_prompt_tokens": result["cached_prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "total_tokens": result["total_tokens"],
                "reasoning_tokens": result["reasoning_tokens"],
                "latency_s": result["latency_s"],
                "tool_calls": result["tool_calls"],
                "omp_session_id": result["session_id"],
                "reserved_cost_usd": bounds[run_key],
                "reported_usage_usd_equivalent": _usage_cost({**result, "prompt_tokens": result["prompt_tokens"]}, profile),
                "status": result["status"],
                "error_type": result["error_type"],
                "error_detail": result["error_detail"],
                "attempt_index": attempt_index + 1,
                "attempted_at": datetime.now(timezone.utc).isoformat(),
            }

        pending_items = iter(remaining)
        shard_pending = [deque(item for item in batch if item.run_key not in completed) for batch in shard_batches]
        active: dict[Any, ExpandedItem] = {}
        active_shards: dict[Any, tuple[int, int]] = {}
        item_claim_lock = threading.Lock()
        in_flight_keys: set[str] = set()
        scheduled_keys: set[str] = set()
        pause_reason = ""
        consecutive_errors = 0
        completed_since_snapshot = 0
        failures = []

        def claim_item(item: ExpandedItem) -> bool:
            with item_claim_lock:
                if item.run_key in completed or item.run_key in in_flight_keys or item.run_key in scheduled_keys:
                    return False
                in_flight_keys.add(item.run_key)
                scheduled_keys.add(item.run_key)
                return True

        def release_item(item: ExpandedItem) -> None:
            with item_claim_lock:
                in_flight_keys.discard(item.run_key)

        with ExitStack() as executor_stack:
            if fixed_shards:
                shard_executors = [
                    executor_stack.enter_context(
                        ThreadPoolExecutor(max_workers=workers_per_shard, thread_name_prefix=f"shard-{index + 1}")
                    )
                    for index in range(workers)
                ]
            else:
                executor = executor_stack.enter_context(ThreadPoolExecutor(max_workers=workers))
            def fill_slots() -> None:
                if fixed_shards:
                    busy = set(active_shards.values())
                    for index, queue in enumerate(shard_pending):
                        for lane_index in range(workers_per_shard):
                            if pause_reason or not queue:
                                break
                            if (index, lane_index) in busy:
                                continue
                            item = queue.popleft()
                            if not claim_item(item):
                                continue
                            try:
                                future = shard_executors[index].submit(
                                    process, item, attempts_by_key.get(item.run_key, 0)
                                )
                            except BaseException:
                                release_item(item)
                                raise
                            active[future] = item
                            active_shards[future] = (index, lane_index)
                            busy.add((index, lane_index))
                    return
                while not pause_reason and len(active) < workers:
                    try:
                        item = next(pending_items)
                    except StopIteration:
                        break
                    if not claim_item(item):
                        continue
                    try:
                        future = executor.submit(process, item, attempts_by_key.get(item.run_key, 0))
                    except BaseException:
                        release_item(item)
                        raise
                    active[future] = item

            fill_slots()
            with tqdm(total=len(remaining), initial=0, desc=f"{phase}:{profile_id}") as progress:
                while active:
                    done, _ = wait(active, return_when=FIRST_COMPLETED)
                    for future in done:
                        item = active.pop(future)
                        try:
                            row = future.result()
                        finally:
                            release_item(item)
                        if fixed_shards:
                            shard_index, lane_index = active_shards.pop(future)
                            row["worker_shard"] = shard_index + 1
                            row["worker_lane"] = lane_index + 1
                        with lock:
                            attempt_rows = dict(row)
                            _append_attempt(output_dir, attempt_rows)
                            latest[item.run_key] = row
                            attempts_by_key[item.run_key] = int(row["attempt_index"])
                            attempt_cost += float(row["reserved_cost_usd"])
                            if row["status"] == "complete" or attempts_by_key[item.run_key] >= MAX_TECHNICAL_ATTEMPTS:
                                pending_reserve = max(0.0, pending_reserve - bounds[item.run_key])
                            completed_since_snapshot += 1
                        progress.update(1)
                        if row["status"] == "complete":
                            consecutive_errors = 0
                        else:
                            failures.append(row)
                            consecutive_errors += 1
                            pause = _technical_pause_reason(row)
                            if pause:
                                pause_reason = pause
                            elif consecutive_errors >= PAUSE_ERRORS_IN_FLIGHT:
                                pause_reason = "consecutive_technical_errors"
                        if attempt_cost + probe_reserve_total + pending_reserve > args.max_cost_usd:
                            pause_reason = pause_reason or "cumulative_budget_guard"
                        if completed_since_snapshot >= SNAPSHOT_EVERY or row["status"] != "complete":
                            save_progress(status="running", pause_reason=pause_reason or None)
                            completed_since_snapshot = 0
                    if not pause_reason:
                        fill_slots()
        if completed_since_snapshot:
            save_progress(status="running")

        complete_count = sum(row.get("status") == "complete" for row in latest.values())
        failure_count = sum(row.get("status") == "request_error" for row in latest.values())
        pending_count = len(items) - complete_count
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        meta["complete_items"] = complete_count
        meta["failed_items"] = failure_count
        meta["pending_items"] = pending_count
        meta["status"] = "complete" if complete_count == len(items) else "paused" if pause_reason else "incomplete"
        if pause_reason:
            meta["pause_reason"] = pause_reason
        _write_snapshot(output_dir, latest)
        _atomic_json(output_dir / "run.json", meta)
        if complete_count != len(items):
            raise SystemExit(
                f"Expansion run {phase}/{profile_id} paused at {complete_count}/{len(items)}; "
                f"pending={pending_count}, request_errors={failure_count}, reason={pause_reason or 'incomplete'}. "
                "Checkpoint saved; resume with the same profile, card and usage guard."
            )
        print(f"completed {complete_count}/{len(items)} via omp -> {output_dir / 'predictions.jsonl'}")
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run expansion-v2 VMLU/V-Bench items through OMP.")
    parser.add_argument("--phase", choices=("pilot", "vmlu", "vbench"), required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--omp-bin", default="omp")
    parser.add_argument("--execute", action="store_true", help="send OMP requests; otherwise preflight only")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fixed-shards", action="store_true", help="fixed contiguous manifest part per worker; no task stealing")
    parser.add_argument("--workers-per-shard", type=int, default=1, help="parallel OMP requests allowed within each fixed shard")
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--measurement-card", default="measurement_card.md", help="preregistered card source, frozen into run metadata")
    args = parser.parse_args()
    if args.execute and (args.max_cost_usd is None or args.max_cost_usd <= 0 or not math.isfinite(args.max_cost_usd)):
        parser.error("--execute requires a positive finite --max-cost-usd")
    raise SystemExit(run_phase(phase=args.phase, profile_id=args.profile, args=args))


if __name__ == "__main__":
    main()
