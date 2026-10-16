"""Resume and schedule all approved OpenCode Go expansion-v2 phases.

The campaign is checkpointed per item. This scheduler keeps at most two Go
profiles active, scores completed phases, and exports local submission files
without uploading them. Run from repo root:
  .venv/bin/python code_benchmark/run_vi_multimodel_go_campaign.py
"""
from __future__ import annotations

import fcntl
import json
import subprocess  # nosec B404 -- Local campaign scripts run with fixed argv and no shell.
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"
RUNNER = ROOT / "code_benchmark/run_vi_multimodel_expansion.py"
SCORER = ROOT / "code_benchmark/score_vi_multimodel_expansion.py"
EXPORTER = ROOT / "code_benchmark/export_vi_multimodel_submissions.py"
PROTOCOL = json.loads((ROOT / "data/vi_multimodel_protocol_v2.json").read_text(encoding="utf-8"))
PROFILES = (
    "muse-spark-1-3-contributor",
    "mimo-v2-6-flash",
    "mimo-v2-5",
)
TASKS = tuple((phase, profile) for phase in ("vmlu", "vbench") for profile in PROFILES)
OUTPUT_ROOT = ROOT / "all_res/vi_multimodel_v2"
LOG_ROOT = ROOT / "logs/vi_multimodel_v2"
MAX_RESUME_LAUNCHES = 3
POLL_SECONDS = 10
REPORT_SECONDS = 60
FATAL_PAUSE_REASONS = {
    "provider_auth_or_access",
    "provider_request_configuration",
    "provider_rate_or_quota_limit",
    "cumulative_budget_guard",
    "incomplete_exhausted",
}


@dataclass
class ActiveRun:
    phase: str
    profile: str
    process: subprocess.Popen | None
    log_handle: Any = None
    launch_count: int = 1


def run_dir(phase: str, profile: str) -> Path:
    return OUTPUT_ROOT / phase / profile


def read_meta(phase: str, profile: str) -> dict[str, Any] | None:
    path = run_dir(phase, profile) / "run.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: corrupt run metadata {path}: {exc}") from exc


def lock_held(phase: str, profile: str) -> bool:
    path = run_dir(phase, profile) / ".run.lock"
    if not path.is_file():
        return False
    with path.open("r+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return False


def score_phase(phase: str, profile: str) -> None:
    print(f"scoring phase={phase} profile={profile}", flush=True)
    subprocess.run(  # nosec B603 -- Fixed Python/scorer paths and campaign phase/profile identifiers.
        [str(PYTHON), str(SCORER), "--phase", phase, "--profile", profile],
        cwd=ROOT,
        check=True,
    )


def start_phase(phase: str, profile: str, *, resume: bool, launch_count: int) -> ActiveRun:
    cap = PROTOCOL["phases"][phase]["budget_guard_usd_equivalent"][profile]
    command = [
        str(PYTHON),
        str(RUNNER),
        "--phase",
        phase,
        "--profile",
        profile,
        "--execute",
        "--max-cost-usd",
        str(cap),
    ]
    if resume:
        command.append("--resume")

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = LOG_ROOT / f"{phase}-{profile}.log"
    log_handle = log_path.open("a", encoding="utf-8")
    print(
        f"starting phase={phase} profile={profile} resume={resume} "
        f"launch={launch_count}/{MAX_RESUME_LAUNCHES} guard={cap:.2f}",
        flush=True,
    )
    process = subprocess.Popen(  # nosec B603 -- Fixed runner argv; no shell interpolation.
        command,
        cwd=ROOT,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return ActiveRun(phase, profile, process, log_handle, launch_count)


def close_log(active: ActiveRun) -> None:
    if active.log_handle is not None:
        active.log_handle.close()


def report(active_runs: dict[str, ActiveRun], queue: list[tuple[str, str]]) -> None:
    lines = []
    for profile, active in sorted(active_runs.items()):
        metadata = read_meta(active.phase, profile) or {}
        completed = metadata.get("complete_items", 0)
        expected = metadata.get("item_count", "?")
        lines.append(f"{profile}/{active.phase} {completed}/{expected}")
    print(
        f"campaign active={len(active_runs)} queued={len(queue)} "
        + ("; ".join(lines) if lines else "no active profiles"),
        flush=True,
    )


def main() -> int:
    if PROTOCOL.get("protocol_id") != "vi-multimodel-expansion-v2":
        raise SystemExit("Error: unexpected campaign protocol")
    if int(PROTOCOL.get("max_parallel_opencode_profiles", 0)) != 2:
        raise SystemExit("Error: this scheduler is frozen for two concurrent Go profiles")

    queue = list(TASKS)
    active_runs: dict[str, ActiveRun] = {}
    launch_counts: dict[tuple[str, str], int] = {}
    halt_reason = ""

    # Adopt runs that are already holding their per-phase locks.
    for phase, profile in TASKS:
        if lock_held(phase, profile):
            if profile in active_runs:
                raise SystemExit(f"Error: overlapping phases already hold locks for {profile}")
            active_runs[profile] = ActiveRun(phase, profile, None)
            queue.remove((phase, profile))
            print(f"adopted active phase={phase} profile={profile}", flush=True)

    last_report = 0.0
    while queue or active_runs:
        for profile, active in list(active_runs.items()):
            metadata = read_meta(active.phase, profile)
            status = str((metadata or {}).get("status", "unknown"))
            held = lock_held(active.phase, profile)

            if active.process is None:
                if held:
                    continue
                if status == "complete":
                    score_phase(active.phase, profile)
                    del active_runs[profile]
                    continue
                if status in FATAL_PAUSE_REASONS or (metadata or {}).get("pause_reason") in FATAL_PAUSE_REASONS:
                    halt_reason = f"{active.phase}/{profile} paused: {status}/{(metadata or {}).get('pause_reason')}"
                    del active_runs[profile]
                    continue
                active.launch_count = launch_counts.get(active.task, 0) + 1 if hasattr(active, "task") else 1
                active_runs[profile] = start_phase(active.phase, profile, resume=metadata is not None, launch_count=active.launch_count)
                launch_counts[(active.phase, profile)] = active.launch_count
                continue

            return_code = active.process.poll()
            if return_code is None:
                continue
            close_log(active)
            if return_code == 0 and status == "complete":
                score_phase(active.phase, profile)
                del active_runs[profile]
                continue

            pause_reason = str((metadata or {}).get("pause_reason", ""))
            if status in FATAL_PAUSE_REASONS or pause_reason in FATAL_PAUSE_REASONS:
                halt_reason = f"{active.phase}/{profile} paused: {status}/{pause_reason}"
                del active_runs[profile]
                continue

            next_launch = active.launch_count + 1
            if status in {"incomplete", "paused", "running"} and next_launch <= MAX_RESUME_LAUNCHES:
                print(
                    f"resuming phase={active.phase} profile={profile} "
                    f"after exit={return_code}, status={status}",
                    flush=True,
                )
                active_runs[profile] = start_phase(active.phase, profile, resume=True, launch_count=next_launch)
                launch_counts[(active.phase, profile)] = next_launch
                continue

            halt_reason = f"{active.phase}/{profile} stopped: exit={return_code}, status={status}"
            del active_runs[profile]

        if not halt_reason:
            for task in list(queue):
                phase, profile = task
                if profile in active_runs:
                    continue
                if len(active_runs) >= 2:
                    break
                metadata = read_meta(phase, profile)
                status = str((metadata or {}).get("status", "unknown"))
                if status == "complete" and not lock_held(phase, profile):
                    score_phase(phase, profile)
                    queue.remove(task)
                    continue
                pause_reason = str((metadata or {}).get("pause_reason", ""))
                if status in FATAL_PAUSE_REASONS or pause_reason in FATAL_PAUSE_REASONS:
                    halt_reason = f"{phase}/{profile} paused: {status}/{pause_reason}"
                    break
                if lock_held(phase, profile):
                    active_runs[profile] = ActiveRun(phase, profile, None)
                    queue.remove(task)
                    print(f"adopted active phase={phase} profile={profile}", flush=True)
                    continue
                launch_count = launch_counts.get(task, 0) + 1
                active_runs[profile] = start_phase(
                    phase,
                    profile,
                    resume=metadata is not None,
                    launch_count=launch_count,
                )
                launch_counts[task] = launch_count
                queue.remove(task)

        now = time.monotonic()
        if now - last_report >= REPORT_SECONDS:
            report(active_runs, queue)
            last_report = now
        if halt_reason and not active_runs:
            print(f"campaign halted: {halt_reason}", file=sys.stderr, flush=True)
            return 1
        time.sleep(POLL_SECONDS)

    if halt_reason:
        print(f"campaign halted: {halt_reason}", file=sys.stderr, flush=True)
        return 1

    for profile in PROFILES:
        print(f"exporting local submission artifacts profile={profile}", flush=True)
        subprocess.run(  # nosec B603 -- Fixed Python/exporter paths and enumerated profile identifiers.
            [str(PYTHON), str(EXPORTER), "--profile", profile],
            cwd=ROOT,
            check=True,
        )
    print("OpenCode Go VMLU/V-Bench campaign complete; Qwen was not started.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
