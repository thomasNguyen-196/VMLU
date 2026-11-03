"""MC-105's self-improvement loop for two more students, Muse Spark 1.3 and Muse Spark 1.2 (openspec change
diagnostic-router-loop, decision 12; card MC-108).

Before and after on the seven columns of the /table before-and-after table: the six main-v1 datasets with local gold
(the items and prompts of the /table runs, checked row by row against the frozen manifest) and VMLU dev 303 (the
items and prompts of MC-104). Both students answer B twice and S three times on every item. The loop is MC-105's
MiMo loop, unchanged (`diagnostic_table_loop.choose` with a student other than Qwen): round 1 keeps B when the two B
answers agree, round 2 keeps S-r1 when it agrees with one of them, round 3 takes the majority of three S answers.
It has no threshold, so nothing in it is fitted to a Muse answer.

The frozen MC-105 module is imported, never changed: its items, prompts and loop are reused as they are.

  .venv/bin/python -m code_benchmark.diagnostic_table_loop_muse [--write]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_table_loop as tl
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_table_loop as tl
    import vi_multimodel as v1

DATA_DIR = tl.DATA_DIR
CONFIG_PATH = DATA_DIR / "table_loop_muse_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration_table_loop_muse.json"
PROTOCOL_ID = "vmlu-diagnostic-table-loop-muse"
PHASE = "table_loop_muse"
STUDENTS = ("muse13", "muse12")
FAMILIES = tl.FAMILIES
S_REPLICATES = tl.S_REPLICATES
ARMS = ["B-r1", "B-r2", "S-r1", "S-r2", "S-r3"]
CONFIG_KEYS = tl.CONFIG_KEYS
VMLU_DEV = "vmlu-mqa-dev"


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def manifest_path(student: str) -> Path:
    return DATA_DIR / f"table_loop_muse_manifest_{student}_v1.json"


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or set(config) != set(CONFIG_KEYS):
        raise _fail(f"the Muse table-loop configuration must have exactly the keys {list(CONFIG_KEYS)}")
    if (config["protocol_id"], config["protocol_version"]) != (PROTOCOL_ID, 1):
        raise _fail("unsupported Muse table-loop protocol id or version")
    if set(config["arms"]) != set(STUDENTS) or set(config["students"]) != set(STUDENTS):
        raise _fail(f"the students must be exactly {list(STUDENTS)}")
    items = config["items"]
    if items["vmlu_dev"]["dataset_id"] != VMLU_DEV or VMLU_DEV in items["datasets"]:
        raise _fail("VMLU dev is named apart from the six main-v1 datasets")
    families = items["families"]
    if set(families) != set(FAMILIES) or set(families["multiple_choice"]) | set(families["reading"]) != {
            *items["datasets"], VMLU_DEV} or set(families["multiple_choice"]) & set(families["reading"]):
        raise _fail("every dataset belongs to exactly the multiple-choice or the reading family")
    for student, arms in config["arms"].items():
        if set(arms) != set(FAMILIES) or any(arms[family] != ARMS for family in FAMILIES):
            raise _fail(f"{student}: every item is answered {ARMS}")
    for student, route in config["students"].items():
        if route["model_identity"] not in route["model_id"] or route["api_protocol"] != "openai-responses":
            raise _fail(f"{student}: the identity token must be part of the model id, on the Responses API")
    if config["loop"]["fitted_parameters"].split(":")[0] != "none":
        raise _fail("the Muse loop has no fitted parameter")
    return config


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        return validate_config(json.loads(raw)), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the Muse table-loop configuration {path}: {exc}") from exc


# ---------------------------------------------------------------- items and prompts

def vmlu_dev_items(config: dict[str, Any]) -> list[v1.EvalItem]:
    spec = config["items"]["vmlu_dev"]
    items = v1._load_vmlu("dev")  # noqa: SLF001 - the frozen VMLU loader, dev split, as in MC-104
    if len(items) != spec["n"] or {item.dataset_id for item in items} != {VMLU_DEV}:
        raise _fail(f"VMLU dev has {len(items)} items, not {spec['n']}")
    return items


def base_items(config: dict[str, Any]) -> tuple[list[v1.EvalItem], str]:
    """VMLU dev, then the main-v1 items checked against the frozen /table manifest (MC-105's check)."""
    main, main_sha = tl.table_items(config)
    return vmlu_dev_items(config) + main, main_sha


def expand(student: str, config: dict[str, Any], items: list[v1.EvalItem]) -> list[v1.EvalItem]:
    """Item-major attempts; MC-105's expansion, so B is the frozen prompt itself and S the campaign template."""
    return tl.expand(student, config, items)


def build_manifest(student: str, config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map) of one student, self-hashed like the campaign manifests."""
    if student not in STUDENTS:
        raise _fail(f"unknown student {student!r}")
    config, digest = load_config(config_path)
    base, main_sha = base_items(config)
    items = expand(student, config, base)
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate Muse table-loop run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "student": student,
        "config_sha256": digest, "main_manifest_sha256": main_sha,
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "earlier_manifest_sha256": {card: v1.sha256_file(path) for card, path in tl.EARLIER.items()},
        "source_sha256": v1.source_hashes(),
        "seen_in_router_cards": tl.seen_before([item for item in base if item.dataset_id != VMLU_DEV]),
        "n": len(items), "item_count": len(base),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in base).items())),
        "arm_counts": dict(sorted(Counter(f"{item.dataset_id}:{dp.arm_of_replicate(item.replicate_id)}"
                                          for item in items).items())),
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(student: str) -> dict[str, Any]:
    try:
        return json.loads(manifest_path(student).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the frozen Muse table-loop manifest of {student}: {exc}") from exc


# ---------------------------------------------------------------- the loop

def choose(task: str, student: str, predictions: dict[str, str]) -> tuple[str, int]:
    """(the replicate whose answer is final, rounds used): MC-105's loop for a student without a probe, unchanged."""
    if student not in STUDENTS:
        raise _fail(f"unknown student {student!r}")
    return tl.choose(task, student, predictions, None, 0.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Muse table-loop manifests (offline).")
    ap.add_argument("--write", action="store_true", help="freeze both manifests")
    args = ap.parse_args(argv)
    status = 0
    for student in STUDENTS:
        manifest, _ = build_manifest(student)
        print(f"{student}: manifest {manifest['manifest_sha256']}: {manifest['item_count']} items, {manifest['n']} "
              f"attempts, datasets {manifest['dataset_counts']}, seen in router cards {manifest['seen_in_router_cards']}")
        path = manifest_path(student)
        if args.write:
            if path.exists():
                raise _fail(f"{path} is frozen; delete it deliberately to rebuild")
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"  frozen -> {path}")
        elif path.exists():
            same = load_frozen_manifest(student) == manifest
            print(f"  frozen manifest {'matches' if same else 'DIFFERS'}")
            status |= 0 if same else 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
