"""The self-improvement loop on the /table benchmark suite (openspec change diagnostic-router-loop, decision 12,
task 2.7; card MC-105).

Before and after on the six main-v1 datasets with local gold, the items and prompts of the /table runs: VMLU valid,
Legal MC, Legal NLI, Vi-SQuAD, Vi-DROP and ViBidLQA test. For each student, B is the before: the frozen main-v1
prompt, byte for byte. The loop of MC-104 is the after, and the student writes every final answer:

* multiple choice: as MC-104. Qwen's B is the MC-43 probe and its confidence decides round 2 at the registered
  threshold; MiMo answers B twice.
* reading: a free-text answer has no letter to probe, so both students answer B twice. Round 1 keeps B when the two
  agree; round 2 keeps S-r1 when it agrees with one of them; round 3 takes the majority of three S answers.

The loop is replayed offline from the logged answers (`choose`). These items were used to design the router (MC-90
to MC-95); the comparison is descriptive of the familiar benchmark numbers, and the held-out evidence is MC-104.

  .venv/bin/python -m code_benchmark.diagnostic_table_loop [--write]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_router as router
    from code_benchmark import diagnostic_self_loop as sl
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_router as router
    import diagnostic_self_loop as sl
    import vi_multimodel as v1

DATA_DIR = dp.ROOT / "data" / "diagnostic_router_loop"
CONFIG_PATH = DATA_DIR / "table_loop_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration_table_loop.json"
PROTOCOL_ID = "vmlu-diagnostic-table-loop"
PHASE = "table_loop"
STUDENTS = ("qwen", "mimo")
FAMILIES = ("multiple_choice", "reading")
S_REPLICATES = ("S-r1", "S-r2", "S-r3")
CONFIG_KEYS = ("loop_id", "protocol_id", "protocol_version", "change", "purpose", "items", "arms", "arm_meaning",
               "students", "loop", "reference", "analysis")
# Frozen manifests of earlier router cards on these datasets, for the overlap the manifest records.
EARLIER = {"MC-90 to MC-92": dp.DATA_DIR / "wide_v1.json",
           "MC-94": dp.ROOT / "data" / "diagnostic_router_v2" / "heldout_v1.json",
           "MC-95": dp.ROOT / "data" / "diagnostic_router_v3" / "heldout_v3.json"}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def manifest_path(student: str) -> Path:
    return DATA_DIR / f"table_loop_manifest_{student}_v1.json"


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or set(config) != set(CONFIG_KEYS):
        raise _fail(f"the table-loop configuration must have exactly the keys {list(CONFIG_KEYS)}")
    if (config["protocol_id"], config["protocol_version"]) != (PROTOCOL_ID, 1):
        raise _fail("unsupported table-loop protocol id or version")
    if set(config["arms"]) != set(STUDENTS) or set(config["students"]) != set(STUDENTS):
        raise _fail(f"the students must be exactly {list(STUDENTS)}")
    families = config["items"]["families"]
    if set(families) != set(FAMILIES) or set(families["multiple_choice"]) | set(families["reading"]) != set(
            config["items"]["datasets"]):
        raise _fail("every dataset belongs to exactly the multiple-choice or the reading family")
    for student, arms in config["arms"].items():
        for family in FAMILIES:
            if [dp.arm_of_replicate(r) for r in arms[family]].count("S") != 3 or arms[family][-3:] != list(S_REPLICATES):
                raise _fail(f"{student} {family}: the arms end with S-r1, S-r2 and S-r3")
        if arms["reading"][:2] != ["B-r1", "B-r2"]:
            raise _fail(f"{student}: reading answers B twice")
    if config["arms"]["qwen"]["multiple_choice"][:2] != ["B-r1", "S-r1"] or config["arms"]["mimo"]["multiple_choice"][:2] \
            != ["B-r1", "B-r2"]:
        raise _fail("multiple choice: Qwen answers B once (the probe), MiMo twice")
    threshold = config["loop"]["multiple_choice"]["threshold"]
    if threshold != sl.load_config()[0]["loop"]["qwen"]["threshold"]:
        raise _fail("the Qwen threshold must be MC-104's registered one")
    return config


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        return validate_config(json.loads(raw)), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the table-loop configuration {path}: {exc}") from exc


# ---------------------------------------------------------------- items and prompts

def table_items(config: dict[str, Any]) -> tuple[list[v1.EvalItem], str]:
    """The main-v1 items, each checked against the frozen /table manifest row by row (prompt included)."""
    frozen = v1.load_manifest("main")
    if frozen["manifest_sha256"] != config["items"]["main_manifest_sha256"]:
        raise _fail("the frozen main-v1 manifest is not the one the configuration names")
    rows = {dp.run_key(row): row for row in frozen["items"]}
    items = v1.load_main_items()
    differing = [item.run_key for item in items if rows.get(item.run_key) != v1.manifest_item(item)]
    if differing or len(items) != len(rows):
        raise _fail(f"{len(differing)} main-v1 items differ from the frozen /table manifest: {differing[:3]}")
    if dict(Counter(item.dataset_id for item in items)) != config["items"]["datasets"]:
        raise _fail("main-v1 dataset counts differ from the configuration")
    return items, frozen["manifest_sha256"]


def family_of(item: v1.EvalItem) -> str:
    return "multiple_choice" if item.task == "multiple_choice" else "reading"


def expand(student: str, config: dict[str, Any], items: list[v1.EvalItem]) -> list[v1.EvalItem]:
    """Item-major attempts of one student; B is the frozen prompt itself, S the campaign template."""
    templates = dp.load_templates()
    arms = config["arms"][student]
    out: list[v1.EvalItem] = []
    for item in items:
        prompts = {arm: dp.build_arm_prompt(item, arm, templates) for arm in ("B", "S")}
        if prompts["B"] != item.prompt:
            raise _fail(f"{item.run_key}: the B prompt is not the frozen prompt")
        out += [dataclasses.replace(item, replicate_id=r, prompt=prompts[dp.arm_of_replicate(r)])
                for r in arms[family_of(item)]]
    return out


def seen_before(items: list[v1.EvalItem]) -> dict[str, int]:
    """Per dataset, how many items earlier router cards (MC-90 to MC-95) already used."""
    used: dict[str, set[str]] = {}
    for path in EARLIER.values():
        for row in json.loads(path.read_text(encoding="utf-8"))["items"]:
            used.setdefault(row["dataset_id"], set()).add(row["item_id"])
    counts = Counter(item.dataset_id for item in items if item.item_id in used.get(item.dataset_id, set()))
    return {dataset: counts.get(dataset, 0) for dataset in sorted({item.dataset_id for item in items})}


def build_manifest(student: str, config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map) of one student, self-hashed like the campaign manifests."""
    if student not in STUDENTS:
        raise _fail(f"unknown student {student!r}")
    config, digest = load_config(config_path)
    base, main_sha = table_items(config)
    items = expand(student, config, base)
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate table-loop run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "student": student,
        "config_sha256": digest, "main_manifest_sha256": main_sha,
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "earlier_manifest_sha256": {card: v1.sha256_file(path) for card, path in EARLIER.items()},
        "source_sha256": v1.source_hashes(),
        "seen_in_router_cards": seen_before(base),
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
        raise _fail(f"cannot read the frozen table-loop manifest of {student}: {exc}") from exc


# ---------------------------------------------------------------- the loop

def _normal(answer: str, task: str) -> str:
    return v1.normalize_em_answer(answer) if task == "reading" else answer.strip().upper()


def vote(predictions: dict[str, str], task: str) -> str:
    """The earliest S replicate holding the most frequent non-empty answer; S-r1 when none is non-empty."""
    keys = [_normal(predictions[r] or "", task) for r in S_REPLICATES]
    counts = Counter(key for key in keys if key)
    if not counts:
        return S_REPLICATES[0]
    top = max(counts.values())
    return next(r for r, key in zip(S_REPLICATES, keys, strict=True) if key and counts[key] == top)


def choose(task: str, student: str, predictions: dict[str, str], confidence: float | None,
           threshold: float) -> tuple[str, int]:
    """(the replicate whose answer is final, rounds used). Multiple choice repeats MC-104's rules; reading uses the
    two B answers as the signal for both students. Agreement is router v2's normalized-answer-v1."""
    agree = router.answers_agree
    if task == "multiple_choice" and student == "qwen":
        if confidence is not None and confidence >= threshold:
            return "B-r1", 1
        if agree(predictions["S-r1"], predictions["B-r1"], task):
            return "B-r1", 2
        return vote(predictions, task), 3
    if agree(predictions["B-r1"], predictions["B-r2"], task):
        return "B-r1", 1
    if any(agree(predictions["S-r1"], predictions[b], task) for b in ("B-r1", "B-r2")):
        return "S-r1", 2
    return vote(predictions, task), 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the table-loop manifests (offline).")
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
