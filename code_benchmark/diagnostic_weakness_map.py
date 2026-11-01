"""Weakness map of an API student on router v3's calibration items (openspec change diagnostic-router-loop, Phase 2;
card MC-103).

* Items: the 180 calibration items of the MC-95 held-out set (60 each of VMLU valid, VM14K and ViBidLQA train), on
  which Qwen3.5-9B answered B and S twice (MC-95).
* Arms: B twice and S once on every item, and Q ("trích rồi đáp") once on the ViBidLQA items, 600 attempts. B and S
  are the MC-95 prompts byte for byte; Q comes from the MC-97 builder.
* Maps (analysis: code_benchmark/analyze_weakness_map.py), per dataset: the point map takes the arm with the highest
  draw-1 mean and keeps B unless a fix beats B-r1 by the tie margin; the reliable map takes a fix only when its paired
  gain over B-r1 has a 95% interval above zero.

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_weakness_map            # build the manifest, compare with the frozen one
  .venv/bin/python -m code_benchmark.diagnostic_weakness_map --write    # freeze data/diagnostic_router_loop/weakness_manifest_v1.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_heldout_v3 as h3
    from code_benchmark import diagnostic_menu as menu
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_heldout_v3 as h3
    import diagnostic_menu as menu
    import diagnostic_prospective as dp
    import vi_multimodel as v1

DATA_DIR = dp.ROOT / "data" / "diagnostic_router_loop"
CONFIG_PATH = DATA_DIR / "weakness_map_v1.json"
MANIFEST_PATH = DATA_DIR / "weakness_manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration_weakness_map.json"
PROTOCOL_ID = "vmlu-diagnostic-weakness-map"
PHASE = "weakness_map"
CONFIG_KEYS = ("map_id", "protocol_id", "protocol_version", "change", "purpose", "items", "arms", "student",
               "reference", "analysis")
EVERY_ITEM = ("B-r1", "B-r2", "S-r1")
READING_ONLY = ("Q-r1",)
CELL_OF = {"B-r1": "B1", "B-r2": "B2", "S-r1": "S1", "Q-r1": "Q1"}
FIXES = ("S", "Q")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _read_json_bytes(path: Path, label: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        return json.loads(raw), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the {label} {path}: {exc}") from exc


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or set(config) != set(CONFIG_KEYS):
        raise _fail(f"the weakness-map configuration must have exactly the keys {list(CONFIG_KEYS)}")
    if config["protocol_id"] != PROTOCOL_ID or config["protocol_version"] != 1:
        raise _fail("unsupported weakness-map configuration id/version")
    if config["arms"] != {"every_item": list(EVERY_ITEM), "reading_items": list(READING_ONLY)}:
        raise _fail(f"the arms are {list(EVERY_ITEM)} on every item and {list(READING_ONLY)} on reading items")
    student = config["student"]
    if student.get("api_protocol") != "openai-chat-completions" or student.get("stream") is not False:
        raise _fail("the student route is the non-streaming chat-completions API")
    for key in ("max_completion_tokens", "timeout_seconds", "max_in_flight", "stop_after_timeouts", "budget_tokens"):
        if isinstance(student.get(key), bool) or not isinstance(student.get(key), int) or student[key] < 1:
            raise _fail(f"student {key} must be a positive integer")
    if student.get("sdk_retries") != 0 or not student.get("model_identity"):
        raise _fail("the student route sends no SDK retries and names a model-identity token")
    if config["reference"].get("arms") != list(EVERY_ITEM):
        raise _fail(f"the reference arms are {list(EVERY_ITEM)}")
    return config


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    """The validated weakness-map configuration and the SHA-256 of its bytes."""
    config, digest = _read_json_bytes(path, "weakness-map configuration")
    return validate_config(config), digest


def build_manifest(config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed. Item-major, in the MC-95 calibration order: B-r1, B-r2, S-r1,
    then Q-r1 on reading items."""
    config, digest = load_config(config_path)
    source, source_items = h3.build_manifest()
    if source != h3.load_frozen_manifest():
        raise _fail("the MC-95 held-out manifest no longer rebuilds byte-identically")
    if source["manifest_sha256"] != config["items"]["source_manifest_self_sha256"]:
        raise _fail("the MC-95 held-out manifest is not the registered one")
    counts = {dataset: len(keys) for dataset, keys in source["calibration_items"].items()}
    if counts != config["items"]["dataset_counts"]:
        raise _fail(f"the calibration items are {counts}, not {config['items']['dataset_counts']}")
    q_protocol = menu.load_protocol()
    items: list[v1.EvalItem] = []
    for dataset_id in sorted(source["calibration_items"]):
        for key in source["calibration_items"][dataset_id]:
            replicas = [source_items[f"{key}:{replicate}"] for replicate in EVERY_ITEM]
            items.extend(replicas)
            if replicas[0].task == "reading":
                items.append(dataclasses.replace(replicas[0], replicate_id=READING_ONLY[0],
                                                 prompt=menu.q_prompt(replicas[0], q_protocol)))
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate weakness-map run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "map_id": config["map_id"],
        "weakness_config_sha256": digest, "source_manifest_self_sha256": source["manifest_sha256"],
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "q_protocol_sha256": v1.sha256_file(menu.PROTOCOL_PATH),
        "n": len(items), "item_count": sum(counts.values()), "dataset_counts": dict(sorted(counts.items())),
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "calibration_items": source["calibration_items"],
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest, _ = _read_json_bytes(path, "frozen weakness-map manifest")
    return manifest


# ---------------------------------------------------------------- shared by the analysis

def task_of(row: dict[str, Any]) -> str:
    return "multiple_choice" if "correct" in row else "reading"


def score(row: dict[str, Any]) -> float:
    """Accuracy for multiple choice, token-F1 for reading."""
    return float(row["correct"]) if "correct" in row else float(row["token_f1"])


def is_right(row: dict[str, Any], threshold: float) -> bool:
    return bool(row["correct"]) if "correct" in row else float(row["token_f1"]) >= threshold


def load_cells(path: Path, keys: set[str], replicates: tuple[str, ...]) -> dict[str, dict[str, dict[str, Any]]]:
    """{dataset:item: {B1, B2, S1, Q1: scored row}} for the given items and replicates; a repeated row fails closed."""
    cells: dict[str, dict[str, dict[str, Any]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = dp.item_key(row["dataset_id"], row["item_id"])
        if key not in keys or row["replicate_id"] not in replicates:
            continue
        cell = cells.setdefault(key, {})
        name = CELL_OF[row["replicate_id"]]
        if name in cell:
            raise _fail(f"two {row['replicate_id']} rows for {key} in {path}")
        cell[name] = row
    return cells


def point_map(means: dict[str, float], tie_points: float) -> str:
    """The arm with the highest draw-1 mean (points); B unless a fix beats B by at least tie_points."""
    best = max((arm for arm in FIXES if arm in means), key=lambda arm: means[arm], default=None)
    return best if best is not None and means[best] - means["B"] >= tie_points else "B"


def reliable_map(gains: dict[str, dict[str, Any]]) -> str:
    """The fix with the largest mean gain over B among those whose 95% interval lies above zero; otherwise B."""
    reliable = [arm for arm in FIXES if arm in gains and gains[arm]["ci95_points"][0] > 0]
    return max(reliable, key=lambda arm: gains[arm]["mean_points"]) if reliable else "B"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the weakness-map manifest (offline).")
    ap.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    manifest, _ = build_manifest()
    print(f"weakness-map manifest {manifest['manifest_sha256']}: {manifest['item_count']} items, {manifest['n']} attempts, "
          f"datasets {manifest['dataset_counts']}, arms {manifest['arm_counts']}")
    if args.write:
        if MANIFEST_PATH.exists():
            raise _fail(f"{MANIFEST_PATH} is frozen; delete it deliberately to rebuild")
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"frozen -> {MANIFEST_PATH}")
    elif MANIFEST_PATH.exists():
        same = load_frozen_manifest() == manifest
        print(f"frozen manifest {'matches' if same else 'DIFFERS'}")
        return 0 if same else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
