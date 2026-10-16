"""Continue uncompleted MC-74 VMLU items through the requested OCG route.

Completed CMC answers stay in their original run. The OCG continuation gets a
separate condition and output directory; a mixed-route artifact is written only
after all remaining items complete. From root:
    .venv/bin/python -m code_benchmark.run_muse12_ocg_vmlu_continuation --execute
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from collections import Counter
from contextlib import ExitStack
from pathlib import Path

try:
    from code_benchmark import run_muse_router_matched as campaign
except ImportError:
    import run_muse_router_matched as campaign

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "muse-spark-1-2-contributor-ocg"
CARD_ID = "MC-79"
CARD_PATH = ROOT / "docs/measurement_cards/MC-79-muse12-ocg-vmlu-continuation.md"
OUTPUT_ROOT = ROOT / "all_res/muse12_ocg_vmlu_mc79"
SOURCE_ROOT = ROOT / "all_res/muse_router_matched"
SOURCE_RUN = SOURCE_ROOT / "vmlu/muse-spark-1-2-contributor"
SOURCE_MANIFEST = SOURCE_ROOT / "vmlu/condition_manifest.json"
SOURCE_CARD_ID = "MC-74"
SOURCE_MODEL_ID = "cmc/meta/muse-spark-1.2-contributor"
MODEL_ID = "ocg/muse-spark-1.2-contributor"
SOURCE_MANIFEST_SHA256 = "4046145d633931454c8760f8ffb74ae5d2e267bdb6aa02878adba68f8a472655"
SOURCE_ATTEMPTS_SHA256 = "903794668864e982d7d63c694401973423b3f6bd80cfadec6d0d8d5f4244a817"
TOTAL_ITEMS = 10880
SOURCE_COMPLETED_ITEMS = 7504
SHARDS = 4
WORKERS_PER_SHARD = 3
BASE_PROFILE = campaign.router_profile


def profile() -> dict:
    result = BASE_PROFILE()
    result.update({
        "profile_id": PROFILE_ID,
        "display_name": "Muse Spark 1.2 Contributor (OCG continuation)",
        "provider": "9ROUTER / OCG",
        "model_id": MODEL_ID,
        "model_ref": f"router9/{MODEL_ID}",
        "measurement_card_ids_v2": {"vmlu": CARD_ID},
    })
    return result


def completed_source() -> tuple[dict[str, dict], str, dict]:
    if not SOURCE_MANIFEST.is_file() or not (SOURCE_RUN / "run.json").is_file():
        raise SystemExit("Error: paused MC-74 source run or manifest is missing")
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    source_meta = json.loads((SOURCE_RUN / "run.json").read_text(encoding="utf-8"))
    ledger_path = SOURCE_RUN / "attempts.jsonl"
    ledger_bytes = ledger_path.read_bytes()
    source_hash = campaign.v1.sha256_bytes(ledger_bytes)
    if source_manifest.get("manifest_sha256") != SOURCE_MANIFEST_SHA256:
        raise SystemExit("Error: MC-74 source manifest changed")
    if source_hash != SOURCE_ATTEMPTS_SHA256:
        raise SystemExit("Error: MC-74 source attempt ledger changed after continuation was prepared")
    if source_meta.get("manifest_sha256") != SOURCE_MANIFEST_SHA256:
        raise SystemExit("Error: MC-74 run metadata no longer matches its frozen manifest")
    if source_meta.get("model_id") != SOURCE_MODEL_ID or source_meta.get("measurement_card_id") != SOURCE_CARD_ID:
        raise SystemExit("Error: MC-74 source run identity changed")

    latest: dict[str, dict] = {}
    for line in ledger_bytes.decode("utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            latest[str(row["run_key"])] = row
    completed = {key: row for key, row in latest.items() if row.get("status") == "complete"}
    if len(completed) != SOURCE_COMPLETED_ITEMS:
        raise SystemExit(f"Error: expected {SOURCE_COMPLETED_ITEMS} completed MC-74 items, found {len(completed)}")
    return completed, source_hash, source_manifest


def inputs() -> tuple[dict, dict, dict]:
    campaign.PROFILE_ID = PROFILE_ID
    campaign.OUTPUT_ROOT = OUTPUT_ROOT
    campaign.CARDS = {**campaign.CARDS, "vmlu": CARD_ID}
    campaign.router_profile = profile
    profiles, protocol, manifest = campaign.inputs_for("vmlu")
    completed, source_hash, source_manifest = completed_source()

    references = {
        f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}": row
        for row in manifest["items"]
    }
    if set(completed) - set(references):
        raise SystemExit("Error: MC-74 completed keys are outside the frozen VMLU manifest")
    for key, row in completed.items():
        if row.get("prompt_sha256") != references[key].get("prompt_sha256"):
            raise SystemExit(f"Error: MC-74 source prompt differs from parent manifest: {key}")

    manifest["items"] = [row for key, row in references.items() if key not in completed]
    manifest["n"] = manifest["item_count"] = len(manifest["items"])
    manifest["dataset_counts"] = dict(Counter(row["dataset_id"] for row in manifest["items"]))
    manifest["carried_completed_keys"] = sorted(completed)
    manifest["source_condition_id"] = SOURCE_CARD_ID
    manifest["source_route"] = SOURCE_MODEL_ID
    manifest["source_manifest_sha256"] = source_manifest["manifest_sha256"]
    manifest["source_attempts_sha256"] = source_hash
    manifest["mixed_route_continuation"] = True
    manifest["execution_workers"] = SHARDS
    manifest["workers_per_shard"] = WORKERS_PER_SHARD
    manifest["scheduling_policy"] = "fixed-shards"
    if manifest["n"] != 3376 or manifest["dataset_counts"] != {"vi-multimodel-v2-vmlu-test": 3376}:
        raise SystemExit(f"Error: expected the 3,376 unfinished VMLU test items, got {manifest['dataset_counts']}")
    protocol["workers_per_profile"] = SHARDS
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = campaign.v1.sha256_bytes(campaign.v1.canonical_json(manifest))
    return profiles, protocol, manifest


def combine_results(manifest: dict) -> None:
    completed, source_hash, _source_manifest = completed_source()
    if source_hash != manifest["source_attempts_sha256"]:
        raise SystemExit("Error: MC-74 source ledger changed before mixed-route combination")
    predictions_path = OUTPUT_ROOT / "vmlu" / PROFILE_ID / "predictions.jsonl"
    if not predictions_path.is_file():
        raise SystemExit("Error: OCG continuation predictions are missing")

    combined = {
        key: {**row, "source_condition_id": SOURCE_CARD_ID, "source_route": SOURCE_MODEL_ID}
        for key, row in completed.items()
    }
    residual_keys = {
        f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"
        for row in manifest["items"]
    }
    for line in predictions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = str(row["run_key"])
        if key not in residual_keys or key in combined or row.get("status") != "complete":
            raise SystemExit(f"Error: duplicate, out-of-manifest, or incomplete OCG result: {key}")
        if row.get("prompt_sha256") != next(ref["prompt_sha256"] for ref in manifest["items"]
                                             if f"{ref['dataset_id']}:{ref['item_id']}:{ref['replicate_id']}" == key):
            raise SystemExit(f"Error: OCG continuation prompt differs from manifest: {key}")
        combined[key] = {**row, "source_condition_id": CARD_ID, "source_route": MODEL_ID}

    expected = set(manifest["carried_completed_keys"]) | residual_keys
    if set(combined) != expected or len(combined) != TOTAL_ITEMS:
        raise SystemExit(f"Error: mixed-route coverage differs from {TOTAL_ITEMS}: {len(combined)}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    campaign.v1.write_jsonl_atomic(
        OUTPUT_ROOT / "combined_predictions_mixed_routes.jsonl",
        [combined[key] for key in sorted(combined)],
    )
    campaign.v1_runner._atomic_json(OUTPUT_ROOT / "combined_provenance.json", {
        "mixed_routes": True,
        "homogeneous_model_score_allowed": False,
        "item_count": TOTAL_ITEMS,
        "counts_by_route": dict(Counter(row["source_route"] for row in combined.values())),
        "counts_by_condition": dict(Counter(row["source_condition_id"] for row in combined.values())),
        "source_manifest_sha256": manifest["source_manifest_sha256"],
        "source_attempts_sha256": manifest["source_attempts_sha256"],
        "continuation_manifest_sha256": manifest["manifest_sha256"],
        "note": (
            "This convenience artifact combines completed MC-74 CMC responses with MC-79 OCG responses. "
            "The 3,376 OCG continuation items are all VMLU test with withheld gold; do not report this "
            "mixed-route file as one homogeneous model condition or local accuracy result."
        ),
    })


def run_condition(*, execute: bool, resume: bool) -> None:
    condition = inputs()
    manifest = condition[2]
    print(
        f"condition={CARD_ID} model={MODEL_ID} source={SOURCE_CARD_ID} carried={len(manifest['carried_completed_keys'])} "
        f"remaining={manifest['n']} workers={SHARDS} workers_per_shard={WORKERS_PER_SHARD} "
        "total_workers=12 tools=none temperature=1.0 thinking=auto seed=omitted",
        flush=True,
    )
    print(f"manifest_sha256={manifest['manifest_sha256']}", flush=True)
    base = ["--phase", "vmlu", "--profile", PROFILE_ID]
    run_args = [
        *base,
        "--max-cost-usd", "1",
        "--fixed-shards",
        "--workers-per-shard", str(WORKERS_PER_SHARD),
        "--measurement-card", str(CARD_PATH),
    ]
    if not execute:
        campaign.invoke(campaign.v2_runner, "vmlu", run_args, condition)
        return

    campaign.freeze_inputs("vmlu", condition)
    run_args.append("--execute")
    if resume:
        run_args.append("--resume")
    with campaign.sampling_relay():
        campaign.invoke(campaign.v2_runner, "vmlu", run_args, condition)
    campaign.invoke(campaign.v2_scorer, "vmlu", base, condition)
    combine_results(manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.resume and not args.execute:
        parser.error("--resume requires --execute")
    os.chdir(ROOT)
    if not args.execute:
        run_condition(execute=False, resume=False)
        return

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        try:
            source_lock = stack.enter_context((SOURCE_ROOT / ".campaign.lock").open("a+"))
            fcntl.flock(source_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            output_lock = stack.enter_context((OUTPUT_ROOT / ".campaign.lock").open("a+"))
            fcntl.flock(output_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Error: MC-74 source or MC-79 continuation campaign is already running") from exc
        run_condition(execute=True, resume=args.resume)


if __name__ == "__main__":
    main()
