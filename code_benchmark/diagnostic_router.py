"""Rule-based router of the prospective diagnostic campaign (openspec change: diagnostic-prospective-campaign,
design Decisions 11 and 12, spec `diagnostic-router`).

The router picks one deployable arm per item from what is known when the request is sent: the item's
dataset, the length in characters of its frozen B prompt and literal cue words in its question. It sees a
RequestView, never the EvalItem, so gold answers, audit labels and the outcomes of any arm cannot reach it.

A rule is a JSON file with a closed grammar, validated fail closed:

    {"router_id": "router-v1", "description": "...",
     "conditions": [{"arm": "S", "targets": ["reasoning_gap"],
                     "when": {"dataset": ["vi-multimodel-v1-vi-drop-200"],
                              "b_prompt_chars": {"at_least": 2000, "below": 8000},
                              "question_cues": ["bao nhiêu"]},
                     "note": "..."}],
     "default": {"arm": "B", "targets": []}}

Every feature a condition names must hold; inside a list one entry is enough. The first matching condition
decides, otherwise the default. Cue words match whole words after NFC normalisation and case folding, in
the question only (reading: the text after "Câu hỏi:"; multiple choice: the stem before the first option).
`targets` names the audit-taxonomy labels the routed arm is meant to address; it is checked against the arm
and never changes the selection.

Usage (repo root): .venv/bin/python -m code_benchmark.diagnostic_router --rule <rule.json>
prints the rule's SHA-256 and the arm it selects per dataset on the core anchors and the wide items.
"""
from __future__ import annotations

import argparse
import dataclasses
import functools
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_retrieval as dr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_retrieval as dr
    import vi_multimodel as v1

DEPLOYABLE_ARMS = ("B", "S", "K", "KS")
# The diagnostic labels each arm is designed to address (Decision 12). S changes how the given input is
# processed, so it cannot separate a reading failure from a reasoning one; K adds provisions the input lacks.
_S_TARGETS = frozenset({"reasoning_gap", "reading_representation_gap"})
_K_TARGETS = frozenset({"external_evidence_gap", "parametric_knowledge_gap", "parametric_knowledge_error"})
ADDRESSABLE = {"B": frozenset(), "S": _S_TARGETS, "K": _K_TARGETS, "KS": _S_TARGETS | _K_TARGETS}
FEATURES = ("dataset", "b_prompt_chars", "question_cues")
LENGTH_BOUNDS = ("at_least", "below")
RULE_KEYS = ("router_id", "description", "conditions", "default")
CONDITION_KEYS = ("arm", "targets", "when", "note")
DEFAULT_KEYS = ("arm", "targets")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


# ---------------------------------------------------------------- what the router may see

@dataclasses.dataclass(frozen=True)
class RequestView:
    """What a deployed router could know when the request is sent: no gold, no audit field, no outcome."""
    dataset_id: str
    item_id: str
    task: str
    prompt: str  # the frozen B prompt

    @property
    def run_key(self) -> str:
        return f"{self.dataset_id}:{self.item_id}:{dp.MAIN_REPLICATE}"


@dataclasses.dataclass(frozen=True)
class Features:
    dataset_id: str
    b_prompt_chars: int
    question: str  # folded: NFC, case-folded, whitespace collapsed


def request_view(item: v1.EvalItem) -> RequestView:
    """The router's view of a frozen main-v1 item, whose prompt is the B prompt."""
    if item.replicate_id != dp.MAIN_REPLICATE:
        raise _fail(f"{item.run_key}: the router reads the frozen B prompt of the main-v1 item")
    return RequestView(item.dataset_id, item.item_id, item.task, item.prompt)


def fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def features_of(view: RequestView) -> Features:
    if view.task == "multiple_choice":
        question = dr.mc_question_and_options(view)[0]  # type: ignore[arg-type]  # a RequestView parses like an item
    else:
        question = dp.parse_frozen_prompt(view).question  # type: ignore[arg-type]
    return Features(view.dataset_id, len(view.prompt), fold(question))


@functools.lru_cache(maxsize=None)
def _cue_pattern(cue: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(fold(cue))}(?!\w)")


def cue_present(cue: str, folded_question: str) -> bool:
    return _cue_pattern(cue).search(folded_question) is not None


# ---------------------------------------------------------------- the rule grammar

def _check_decision(decision: Any, where: str, keys: tuple[str, ...], required: tuple[str, ...]) -> None:
    if not isinstance(decision, dict):
        raise _fail(f"{where} must be an object")
    unknown = sorted(set(decision) - set(keys))
    if unknown:
        raise _fail(f"{where} has keys outside the grammar: {unknown} (allowed: {list(keys)})")
    missing = [key for key in required if key not in decision]
    if missing:
        raise _fail(f"{where} lacks {missing}")
    arm, targets = decision["arm"], decision["targets"]
    if arm == "O":
        raise _fail(f"{where}: arm O is not deployable; its reviewer-cited provisions do not exist at request time")
    if arm not in DEPLOYABLE_ARMS:
        raise _fail(f"{where}: arm {arm!r} is not one of {list(DEPLOYABLE_ARMS)}")
    if (not isinstance(targets, list) or not all(isinstance(t, str) for t in targets)
            or len(targets) != len(set(targets))):
        raise _fail(f"{where}: targets must be a list of distinct label names")
    outside = sorted(set(targets) - ADDRESSABLE[arm])
    if outside:
        raise _fail(f"{where}: arm {arm} cannot address {outside}; it addresses {sorted(ADDRESSABLE[arm])}")
    if arm != "B" and not targets:
        raise _fail(f"{where}: arm {arm} must name at least one diagnostic label it targets")
    if "note" in decision and not isinstance(decision["note"], str):
        raise _fail(f"{where}: note must be text")


def _check_when(when: Any, where: str, datasets: frozenset[str]) -> None:
    if not isinstance(when, dict) or not when:
        raise _fail(f"{where}: `when` must be a non-empty object")
    unknown = sorted(set(when) - set(FEATURES))
    if unknown:
        raise _fail(f"{where} tests {unknown}, which is not a router feature (allowed: {list(FEATURES)})")
    if "dataset" in when:
        values = when["dataset"]
        if (not isinstance(values, list) or not values or len(values) != len(set(values))
                or not set(values) <= datasets):
            raise _fail(f"{where}: dataset must be a non-empty list of distinct campaign datasets {sorted(datasets)}")
    if "b_prompt_chars" in when:
        bounds = when["b_prompt_chars"]
        if (not isinstance(bounds, dict) or not bounds or not set(bounds) <= set(LENGTH_BOUNDS)
                or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in bounds.values())):
            raise _fail(f"{where}: b_prompt_chars takes non-negative integers under {list(LENGTH_BOUNDS)}")
        if bounds.get("at_least", 0) >= bounds.get("below", math.inf):
            raise _fail(f"{where}: b_prompt_chars at_least must be below `below`")
    if "question_cues" in when:
        cues = when["question_cues"]
        if (not isinstance(cues, list) or not cues
                or not all(isinstance(cue, str) and re.search(r"\w", cue) for cue in cues)):
            raise _fail(f"{where}: question_cues must be a non-empty list of words or phrases")
        if len({fold(cue) for cue in cues}) != len(cues):
            raise _fail(f"{where}: question_cues repeats a cue (case and Unicode form are ignored)")


def validate_rule(rule: Any, datasets: Iterable[str]) -> dict[str, Any]:
    """Fail closed on anything outside the grammar: unknown keys, features, arms or targets."""
    if not isinstance(rule, dict):
        raise _fail("a router rule must be a JSON object")
    unknown = sorted(set(rule) - set(RULE_KEYS))
    if unknown:
        raise _fail(f"rule has keys outside the grammar: {unknown} (allowed: {list(RULE_KEYS)})")
    if not isinstance(rule.get("router_id"), str) or not rule["router_id"].strip():
        raise _fail("rule lacks a router_id")
    if "description" in rule and not isinstance(rule["description"], str):
        raise _fail("rule description must be text")
    if not isinstance(rule.get("conditions"), list):
        raise _fail("rule conditions must be a list (it may be empty)")
    allowed = frozenset(datasets)
    for number, condition in enumerate(rule["conditions"], 1):
        where = f"condition {number}"
        _check_decision(condition, where, CONDITION_KEYS, ("arm", "targets", "when"))
        _check_when(condition["when"], where, allowed)
    _check_decision(rule.get("default"), "default", DEFAULT_KEYS, DEFAULT_KEYS)
    return rule


def load_rule(path: Path, datasets: Iterable[str] | None = None) -> tuple[dict[str, Any], str]:
    """The validated rule and the SHA-256 of its bytes (the value the core registration records)."""
    try:
        raw = path.read_bytes()
        rule = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read router rule {path}: {exc}") from exc
    return validate_rule(rule, datasets if datasets is not None else dp.load_protocol()["datasets"]), v1.sha256_bytes(raw)


def fixed_rule(arm: str) -> dict[str, Any]:
    """Always-<arm> written in the same grammar, so every policy goes through route()."""
    return {"router_id": f"always-{arm}", "conditions": [],
            "default": {"arm": arm, "targets": sorted(ADDRESSABLE[arm])}}


# ---------------------------------------------------------------- routing

@dataclasses.dataclass(frozen=True)
class Decision:
    arm: str
    targets: tuple[str, ...]
    condition: int | None  # 1-based number of the deciding condition; None for the default


def _matches(when: dict[str, Any], features: Features) -> bool:
    if "dataset" in when and features.dataset_id not in when["dataset"]:
        return False
    bounds = when.get("b_prompt_chars")
    if bounds and not bounds.get("at_least", 0) <= features.b_prompt_chars < bounds.get("below", math.inf):
        return False
    cues = when.get("question_cues")
    return not cues or any(cue_present(cue, features.question) for cue in cues)


def route(rule: dict[str, Any], features: Features) -> Decision:
    for number, condition in enumerate(rule["conditions"], 1):
        if _matches(condition["when"], features):
            return Decision(condition["arm"], tuple(condition["targets"]), number)
    return Decision(rule["default"]["arm"], tuple(rule["default"]["targets"]), None)


def route_items(rule: dict[str, Any], items: Iterable[v1.EvalItem]) -> dict[str, Decision]:
    """{dataset:item: decision} for frozen main-v1 items, each seen only through its RequestView."""
    return {dp.item_key(item.dataset_id, item.item_id): route(rule, features_of(request_view(item)))
            for item in items}


# ---------------------------------------------------------------- command line

def phase_items(phase: str, protocol: dict[str, Any], main_items: dict[str, v1.EvalItem]) -> list[v1.EvalItem]:
    anchors, _ = dp.anchor_item_keys(dp.ROOT / protocol["parent"]["pilot_dir"])
    return dp.phase_base_items(phase, protocol, main_items, anchors)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a router rule and show the arms it selects (offline).")
    ap.add_argument("--rule", type=Path, required=True, help="router rule JSON")
    args = ap.parse_args(argv)
    protocol = dp.load_protocol()
    rule, digest = load_rule(args.rule, protocol["datasets"])
    main_items = v1.rebuild_items(protocol["parent"]["manifest_phase"])
    print(f"rule {rule['router_id']}  sha256 {digest}")
    for phase in dp.PHASES:
        items = phase_items(phase, protocol, main_items)
        decisions = route_items(rule, items)
        counts = Counter((item.dataset_id, decisions[dp.item_key(item.dataset_id, item.item_id)].arm) for item in items)
        print(f"{phase}: {len(items)} items, arms {dict(sorted(Counter(d.arm for d in decisions.values()).items()))}")
        for dataset_id in sorted({dataset for dataset, _ in counts}):
            arms = {arm: n for (dataset, arm), n in sorted(counts.items()) if dataset == dataset_id}
            print(f"  {dataset_id}: {arms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
