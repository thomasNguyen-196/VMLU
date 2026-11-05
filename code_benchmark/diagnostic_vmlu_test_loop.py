"""The self-improvement loop on VMLU test, asked round by round (openspec change diagnostic-router-loop, task 2.9;
card MC-109).

MC-105's Qwen multiple-choice loop on the 9,833 VMLU test items, whose gold only vmlu.ai holds. MC-105 asked every
attempt of every item and replayed the loop offline. Here each attempt is asked only when the loop's rule needs it:

* round 1: B-r1, the MC-43 letter probe, for every item; the loop keeps it when its confidence is at least 0.80;
* round 2: S-r1 only for the other items; the loop keeps B-r1 when S-r1 agrees with it;
* round 3: S-r2 and S-r3 only for the items where S-r1 does not agree; the loop takes the majority of S-r1 to S-r3.

The attempts are independent, so the final answer is the one MC-105's replay (`diagnostic_table_loop.choose`)
would pick from the same attempts; `final_of` is checked against it in the tests. The manifest lists every possible
attempt (four per item); the runner sends the subset the rule needs.

  .venv/bin/python -m code_benchmark.diagnostic_vmlu_test_loop      # rebuild the manifest and print its self-hash
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
    from code_benchmark import diagnostic_table_loop as tl
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_multimodel_expansion as v2
    from code_benchmark.run_mc_eval import extract_answer
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_router as router
    import diagnostic_self_loop as sl
    import diagnostic_table_loop as tl
    import vi_multimodel as v1
    import vi_multimodel_expansion as v2
    from run_mc_eval import extract_answer

DATA_DIR = dp.ROOT / "data" / "diagnostic_router_loop"
CONFIG_PATH = DATA_DIR / "vmlu_test_loop_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration_vmlu_test_loop.json"
PROTOCOL_ID = "vmlu-diagnostic-vmlu-test-loop"
PHASE = "vmlu_test_loop"
STUDENTS = ("qwen",)
DATASET = "vi-multimodel-v2-vmlu-test"
TASK = "multiple_choice"
REPLICATES = ("B-r1", "S-r1", "S-r2", "S-r3")
CONFIG_KEYS = ("loop_id", "protocol_id", "protocol_version", "change", "purpose", "items", "arms", "arm_meaning",
               "schedule", "students", "loop", "reference", "analysis")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or set(config) != set(CONFIG_KEYS):
        raise _fail(f"the VMLU test loop configuration must have exactly the keys {list(CONFIG_KEYS)}")
    if (config["protocol_id"], config["protocol_version"]) != (PROTOCOL_ID, 1):
        raise _fail("unsupported VMLU test loop protocol id or version")
    if set(config["arms"]) != set(STUDENTS) or set(config["students"]) != set(STUDENTS):
        raise _fail(f"the students must be exactly {list(STUDENTS)}")
    if config["arms"]["qwen"] != list(REPLICATES):
        raise _fail(f"Qwen answers {list(REPLICATES)}: the probe once and S three times")
    if config["items"].get("dataset_id") != DATASET:
        raise _fail(f"the items are {DATASET}")
    threshold = config["loop"]["threshold"]
    if threshold != sl.load_config()[0]["loop"]["qwen"]["threshold"] or threshold != tl.load_config()[0]["loop"][
            "multiple_choice"]["threshold"]:
        raise _fail("the Qwen threshold must be MC-104's and MC-105's registered one")
    if not isinstance(config["schedule"].get("max_passes"), int) or config["schedule"]["max_passes"] < 3:
        raise _fail("the schedule needs at least three passes, one per round")
    return config


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        return validate_config(json.loads(raw)), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the VMLU test loop configuration {path}: {exc}") from exc


# ---------------------------------------------------------------- items and prompts

def vmlu_test_items(config: dict[str, Any]) -> tuple[list[v2.ExpandedItem], str]:
    """The VMLU test items, each checked against the frozen v2 VMLU manifest row by row (prompt included)."""
    frozen = v2.load_manifest("vmlu")
    if frozen["manifest_sha256"] != config["items"]["vmlu_manifest_sha256"]:
        raise _fail("the frozen v2 VMLU manifest is not the one the configuration names")
    rebuilt = v2.rebuild_items("vmlu")
    items = [v2.item_from_manifest_row(row, rebuilt) for row in frozen["items"] if row["dataset_id"] == DATASET]
    if len(items) != config["items"]["count"] or len({item.item_id for item in items}) != len(items):
        raise _fail(f"{DATASET}: expected {config['items']['count']} unique items, found {len(items)}")
    if any(item.task != TASK or item.gold_status != "withheld" or item.gold_answer is not None for item in items):
        raise _fail("every VMLU test item is multiple choice with withheld gold")
    return items, frozen["manifest_sha256"]


def expand(items: list[v2.ExpandedItem]) -> list[v2.ExpandedItem]:
    """Item-major attempts: B-r1 is the frozen prompt itself, S-r1 to S-r3 the campaign step-by-step template."""
    templates = dp.load_templates()
    out: list[v2.ExpandedItem] = []
    for item in items:
        prompts = {arm: dp.build_arm_prompt(item, arm, templates) for arm in ("B", "S")}  # type: ignore[arg-type]
        if prompts["B"] != item.prompt:
            raise _fail(f"{item.run_key}: the B prompt is not the frozen prompt")
        out += [dataclasses.replace(item, replicate_id=r, prompt=prompts[dp.arm_of_replicate(r)]) for r in REPLICATES]
    return out


def build_manifest(student: str, config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], dict[str, v2.ExpandedItem]]:
    """(manifest, rebuilt run-key map) of one student, self-hashed like the campaign manifests. Only its self-hash
    is frozen (in the registration); the runner rebuilds it and writes the copy it ran with into the outputs."""
    if student not in STUDENTS:
        raise _fail(f"unknown student {student!r}")
    config, digest = load_config(config_path)
    base, vmlu_sha = vmlu_test_items(config)
    items = expand(base)
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate VMLU test loop run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "student": student,
        "config_sha256": digest, "vmlu_manifest_sha256": vmlu_sha,
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "source_sha256": v2.source_hashes(),
        "n": len(items), "item_count": len(base),
        "dataset_counts": {DATASET: len(base)},
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "items": [v2._item_manifest(item) for item in items],  # noqa: SLF001 - the frozen v2 row contract
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def verify_rows(manifest: dict[str, Any], rebuilt: dict[str, v2.ExpandedItem]) -> list[v2.ExpandedItem]:
    """Strict equality of every row with the rebuilt item (prompt and input hashes)."""
    unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != v1.sha256_bytes(v1.canonical_json(unhashed)):
        raise _fail("VMLU test loop manifest hash mismatch")
    return [v2.item_from_manifest_row(row, rebuilt) for row in manifest["items"]]


# ---------------------------------------------------------------- the loop, round by round

def b_prediction(row: dict[str, Any]) -> str:
    """The probe's letter, by the frozen parser (as MC-105 scored B)."""
    return extract_answer(str(row.get("raw_response", "")))


def s_prediction(row: dict[str, Any]) -> str:
    """An S letter, read from the line after the last final-answer label (as the campaign scores S)."""
    return extract_answer(dp.final_segment(str(row.get("raw_response", "")))[0])


@dataclasses.dataclass(frozen=True)
class ItemState:
    item_id: str
    needed: tuple[str, ...]          # replicates the rule still needs (sent next)
    final: str | None                # the replicate whose answer is final, once decided
    rounds: int | None
    predictions: dict[str, str]      # parsed letters of the completed attempts the rule read
    confidence: float | None

    @property
    def answer(self) -> str | None:
        return None if self.final is None else self.predictions[self.final]


def item_state(item_id: str, complete: dict[str, dict[str, Any]], threshold: float) -> ItemState:
    """What the rule needs next for one item, or its final answer, from the item's completed attempts only."""
    predictions: dict[str, str] = {}
    b = complete.get("B-r1")
    if b is None:
        return ItemState(item_id, ("B-r1",), None, None, predictions, None)
    confidence = b.get("confidence")
    predictions["B-r1"] = b_prediction(b)
    if confidence is not None and confidence >= threshold:
        return ItemState(item_id, (), "B-r1", 1, predictions, confidence)
    s1 = complete.get("S-r1")
    if s1 is None:
        return ItemState(item_id, ("S-r1",), None, None, predictions, confidence)
    predictions["S-r1"] = s_prediction(s1)
    if router.answers_agree(predictions["S-r1"], predictions["B-r1"], TASK):
        return ItemState(item_id, (), "B-r1", 2, predictions, confidence)
    missing = tuple(r for r in ("S-r2", "S-r3") if r not in complete)
    if missing:
        return ItemState(item_id, missing, None, None, predictions, confidence)
    predictions.update({r: s_prediction(complete[r]) for r in ("S-r2", "S-r3")})
    return ItemState(item_id, (), tl.vote(predictions, TASK), 3, predictions, confidence)


def plan(item_ids: list[str], rows: dict[str, dict[str, Any]], threshold: float) -> list[ItemState]:
    """Every item's state from the latest row per run key; only completed rows count."""
    complete: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows.values():
        if row.get("status") == "complete":
            complete.setdefault(str(row["item_id"]), {})[str(row["replicate_id"])] = row
    return [item_state(item_id, complete.get(item_id, {}), threshold) for item_id in item_ids]


def final_of(predictions: dict[str, str], confidence: float | None, threshold: float) -> tuple[str, int]:
    """MC-105's offline replay on a full set of attempts, for the equivalence check."""
    return tl.choose(TASK, "qwen", predictions, confidence, threshold)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rebuild the VMLU test loop manifest (offline) and print its self-hash.")
    ap.parse_args(argv)
    for student in STUDENTS:
        manifest, _ = build_manifest(student)
        print(f"{student}: manifest {manifest['manifest_sha256']}: {manifest['item_count']} items, {manifest['n']} "
              f"possible attempts, arms {manifest['arm_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
