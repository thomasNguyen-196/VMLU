"""Run V-Bench with Muse Spark 1.3 Free through two fixed OMP workers.

From repo root: .venv/bin/python -m code_benchmark.run_muse13_free_vbench --execute
Uses an independent card and output directory; preserves active Muse 1.2 runs.
"""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path

try:
    from code_benchmark import run_muse_router_matched as campaign
except ImportError:
    import run_muse_router_matched as campaign

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "muse-spark-1-3-contributor-free"
CARD_ID = "MC-76"
CARD_PATH = ROOT / "docs/measurement_cards/MC-76-muse13-free-vbench.md"
OUTPUT_ROOT = ROOT / "all_res/muse13_free_vbench_mc76"
BASE_PROFILE = campaign.router_profile
BASE_INPUTS = campaign.inputs_for


def profile() -> dict:
    result = BASE_PROFILE()
    result.update({
        "profile_id": PROFILE_ID,
        "display_name": "Muse Spark 1.3 Contributor Free",
        "provider": "9ROUTER / OpenCode Free",
        "model_id": "oc/muse-spark-1.3-contributor-free",
        "model_ref": "router9/oc/muse-spark-1.3-contributor-free",
        "measurement_card_ids_v2": {"vbench": CARD_ID},
    })
    return result


def configure() -> None:
    campaign.PROFILE_ID = PROFILE_ID
    campaign.OUTPUT_ROOT = OUTPUT_ROOT
    campaign.CARDS = {**campaign.CARDS, "vbench": CARD_ID}
    campaign.router_profile = profile


def inputs() -> tuple[dict, dict, dict]:
    configure()
    profiles, protocol, manifest = BASE_INPUTS("vbench")
    protocol["workers_per_profile"] = 2
    manifest["execution_workers"] = 2
    manifest["scheduling_policy"] = "fixed-shards"
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = campaign.v1.sha256_bytes(campaign.v1.canonical_json(manifest))
    return profiles, protocol, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--score", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--omp-bin", default="omp")
    args = parser.parse_args()
    if args.resume and not args.execute:
        parser.error("--resume requires --execute")
    os.chdir(ROOT)
    condition = inputs()
    print(f"card={CARD_ID} model=oc/muse-spark-1.3-contributor-free items=5141 workers=2 parts=2571+2570 tools=none temperature=1.0 thinking=auto seed=omitted", flush=True)
    print(f"manifest_sha256={condition[2]['manifest_sha256']}", flush=True)
    base = ["--phase", "vbench", "--profile", PROFILE_ID]
    if args.score:
        campaign.invoke(campaign.v2_scorer, "vbench", base, condition)
        return
    run_args = [*base, "--omp-bin", args.omp_bin, "--max-cost-usd", "1", "--fixed-shards", "--measurement-card", str(CARD_PATH)]
    if not args.execute:
        campaign.invoke(campaign.v2_runner, "vbench", run_args, condition)
        return
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT_ROOT / ".campaign.lock").open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Error: Muse 1.3 Free V-Bench already running") from exc
        campaign.freeze_inputs("vbench", condition)
        run_args.append("--execute")
        if args.resume:
            run_args.append("--resume")
        with campaign.sampling_relay():
            campaign.invoke(campaign.v2_runner, "vbench", run_args, condition)
        campaign.invoke(campaign.v2_scorer, "vbench", base, condition)


if __name__ == "__main__":
    main()
