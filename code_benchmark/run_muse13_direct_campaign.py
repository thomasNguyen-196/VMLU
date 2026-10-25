"""Recover MC-80, then run the remaining VMLU splits as MC-81.

Run from root: .venv/bin/python -m code_benchmark.run_muse13_direct_campaign --execute
Uses at most three recovery passes per phase, retaining failed attempts and
skipping all completed items. Quota/auth/request-configuration pauses stop the
campaign; MC-81 starts only after all 2,043 MC-80 items are complete.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess  # nosec B404

from code_benchmark import run_muse13_direct_mc80 as base
from code_benchmark import run_muse13_direct_remaining_vmlu_mc81 as rest

ROOT = base.ROOT
STATE = ROOT / "all_res/muse13_direct_campaign"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    base.inputs()
    rest.inputs()
    print("campaign preflight passed: recover MC-80 -> MC-81 remaining VMLU", flush=True)
    if not args.execute:
        return
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / ".campaign.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Error: campaign already running") from None
        status = {"pid": os.getpid(), "started_at": base.now(), "status": "running", "steps": []}
        base.atomic_json(STATE / "campaign.json", status)
        for card, module, output in [
            ("MC-80", "code_benchmark.run_muse13_direct_mc80", base.OUT),
            ("MC-81", "code_benchmark.run_muse13_direct_remaining_vmlu_mc81", rest.OUT),
        ]:
            recovery_pass = 0
            while True:
                meta_path = output / "run.json"
                old = json.loads(meta_path.read_text()) if meta_path.exists() else None
                if old and old["status"] == "complete":
                    break
                if recovery_pass >= 3:
                    status.update({"status": "needs_attention", "phase": card, "reason": "bounded recovery exhausted"})
                    base.atomic_json(STATE / "campaign.json", status)
                    return
                command = [str(ROOT / ".venv/bin/python"), "-u", "-m", module, "--execute"]
                if old:
                    command.append("--resume")
                status.update({"phase": card, "recovery_pass": recovery_pass, "updated_at": base.now()})
                base.atomic_json(STATE / "campaign.json", status)
                log = ROOT / "logs" / ("muse13_direct_mc80.log" if card == "MC-80" else "muse13_direct_mc81.log")
                log.parent.mkdir(exist_ok=True)
                print(f"starting {card} pass={recovery_pass} resume={bool(old)}", flush=True)
                with log.open("ab") as stream:
                    result = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, check=False)  # nosec B603
                new = json.loads(meta_path.read_text()) if meta_path.exists() else {}
                status["steps"].append({"card": card, "pass": recovery_pass, "exit_code": result.returncode,
                                        "completed": new.get("complete_items"), "errors": new.get("request_error_items"), "finished_at": base.now()})
                base.atomic_json(STATE / "campaign.json", status)
                if result.returncode or new.get("status") == "paused":
                    status.update({"status": "needs_attention", "phase": card, "reason": "runner error or quota/auth/configuration pause"})
                    base.atomic_json(STATE / "campaign.json", status)
                    return
                if new.get("status") == "complete":
                    break
                recovery_pass += 1
            print(f"{card} complete; next phase eligible", flush=True)
        status.update({"status": "complete", "finished_at": base.now()})
        base.atomic_json(STATE / "campaign.json", status)


if __name__ == "__main__":
    main()
