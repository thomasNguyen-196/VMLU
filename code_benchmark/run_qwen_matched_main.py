"""Launch MC-72: Qwen on five non-VMLU datasets under the matched OMP condition.

Uses the frozen v1 prompts and scorers without modifying historical runs.
From repo root (default: offline preflight):
  .venv/bin/python code_benchmark/run_qwen_matched_main.py
  .venv/bin/python code_benchmark/run_qwen_matched_main.py --execute
  .venv/bin/python code_benchmark/run_qwen_matched_main.py --execute --resume
  .venv/bin/python code_benchmark/run_qwen_matched_main.py --score
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
import sys
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

try:
    from code_benchmark import run_vi_multimodel_eval as runner
    from code_benchmark import score_vi_multimodel as scorer
    from code_benchmark import vi_multimodel as contract
except ImportError:
    import run_vi_multimodel_eval as runner
    import score_vi_multimodel as scorer
    import vi_multimodel as contract

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "qwen3-5-9b-65k"
CARD_ID = "MC-72"
OUTPUT_ROOT = ROOT / "all_res/qwen_matched_mc72"
DATASET_COUNTS = {
    "vi-multimodel-v1-legal-mc-146": 146,
    "vi-multimodel-v1-legal-nli-150": 150,
    "vi-multimodel-v1-vi-squad-200": 200,
    "vi-multimodel-v1-vi-drop-200": 200,
    "vi-multimodel-v1-bidlqa-test": 603,
}


def matched_inputs() -> tuple[dict, dict, dict]:
    """Validate the frozen parent first, then hash the explicit derived condition."""
    parent = contract.load_manifest("main")
    profiles = copy.deepcopy(contract.load_model_profiles())
    protocol = copy.deepcopy(contract.load_protocol())
    profile = profiles[PROFILE_ID]
    profile.update({
        "omp_options": {"temperature": 1.0},
        "temperature": 1.0,
        "temperature_effective": 1.0,
        "temperature_policy": "explicit 1.0; nominally matched to OpenCode Go",
        "omp_reasoning": True,
        "omp_thinking": "auto",
        "send_seed": False,
        "seed_policy": "omitted to match OpenCode Go",
    })
    profile["measurement_card_ids"]["main"] = CARD_ID
    protocol["main"]["measurement_card_ids"][PROFILE_ID] = CARD_ID
    manifest = copy.deepcopy(parent)
    manifest["items"] = [row for row in parent["items"] if row["dataset_id"] in DATASET_COUNTS]
    counts = dict(Counter(row["dataset_id"] for row in manifest["items"]))
    if counts != DATASET_COUNTS:
        raise SystemExit(f"Error: MC-72 dataset coverage changed: {counts}")
    manifest["parent_manifest_sha256"] = parent["manifest_sha256"]
    manifest["condition_id"] = CARD_ID
    manifest["item_count"] = sum(counts.values())
    manifest["n"] = sum(counts.values())
    manifest["dataset_counts"] = counts
    # Derive identity from both parent bytes and the effective profile override.
    manifest["protocol_sha256"] = contract.protocol_phase_hash(protocol, "main")
    manifest["profile_roster_sha256"] = contract.sha256_bytes(contract.canonical_json(profiles))
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = contract.sha256_bytes(contract.canonical_json(manifest))
    rebuilt = contract.rebuild_items("main")
    for row in manifest["items"]:
        contract.item_from_manifest_row(row, rebuilt)
    return profiles, protocol, manifest


def invoke(module, argv: list[str], inputs: tuple[dict, dict, dict]) -> None:
    profiles, protocol, manifest = inputs
    with ExitStack() as stack:
        stack.enter_context(patch.object(module, "OUTPUT_DIR", OUTPUT_ROOT))
        stack.enter_context(patch.object(module, "load_model_profiles", return_value=profiles))
        stack.enter_context(patch.object(module, "load_protocol", return_value=protocol))
        stack.enter_context(patch.object(module, "load_manifest", return_value=manifest))
        stack.enter_context(patch.object(sys, "argv", [str(Path(__file__)), *argv]))
        module.main()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="run inference, then score if complete")
    mode.add_argument("--score", action="store_true", help="score existing MC-72 outputs offline")
    parser.add_argument("--resume", action="store_true", help="resume only unfinished technical requests")
    parser.add_argument("--omp-bin", default="omp")
    parser.add_argument("--max-cost-usd", type=float, default=1.0, help="internal guard, not a tariff estimate")
    args = parser.parse_args()
    if args.resume and not args.execute:
        parser.error("--resume requires --execute")
    os.chdir(ROOT)
    inputs = matched_inputs()
    print(f"condition={CARD_ID} model={PROFILE_ID} tools=none temperature=1.0 thinking=auto seed=omitted")
    print(f"datasets={json.dumps(DATASET_COUNTS, ensure_ascii=False)}")
    print(f"manifest_sha256={inputs[2]['manifest_sha256']}")
    print(f"output={OUTPUT_ROOT / 'main' / PROFILE_ID}")
    base = ["--phase", "main", "--profile", PROFILE_ID]
    if args.score:
        invoke(scorer, base, inputs)
        return
    run_args = [*base, "--omp-bin", args.omp_bin, "--max-cost-usd", str(args.max_cost_usd)]
    if not args.execute:
        invoke(runner, run_args, inputs)
        return
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT_ROOT / ".campaign.lock").open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Error: MC-72 is already running") from exc
        contract.write_jsonl_atomic(OUTPUT_ROOT / "condition_manifest.jsonl", [inputs[2]])
        run_args.append("--execute")
        if args.resume:
            run_args.append("--resume")
        invoke(runner, run_args, inputs)
        invoke(scorer, base, inputs)


if __name__ == "__main__":
    main()
