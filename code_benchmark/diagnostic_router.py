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

Cue words come from the cue lexicon (`data/diagnostic_prospective_v1/cue_lexicon_v1.json`), whose groups name
a need and the labels it points to. A rule that tests cues loads only with the lexicon: every cue must be in
it, in a group that shares a target with the condition.

A rule may also declare a probe (router v2, openspec change diagnostic-router-v2): arm B answered twice, and a
condition may test whether the two parsed answers agree ("probe": "agree" | "disagree"). The probe runs only
when a condition whose other features hold needs it; when the decision is then B, the first probe answer is the
answer. Only the model's own answers enter the probe, never gold or scores.

    {"router_id": "router-v2", "probe": {"arm": "B", "samples": 2, "agreement": "normalized-answer-v1"},
     "conditions": [{"arm": "S", "targets": ["reasoning_gap"], "when": {"probe": "disagree"}}],
     "default": {"arm": "B", "targets": []}}

Usage (repo root): .venv/bin/python -m code_benchmark.diagnostic_router --rule <rule.json> [--lexicon <json>]
prints the SHA-256 of the rule and of the lexicon and the arm the rule selects per dataset on the core anchors
and the wide items.
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
FEATURES = ("dataset", "b_prompt_chars", "question_cues", "probe")
LENGTH_BOUNDS = ("at_least", "below")
RULE_KEYS = ("router_id", "description", "probe", "conditions", "default")
PROBE_KEYS = ("arm", "samples", "agreement")
AGREEMENT_RULES = ("normalized-answer-v1",)
PROBE_OUTCOMES = ("agree", "disagree")
CONDITION_KEYS = ("arm", "targets", "when", "note")
DEFAULT_KEYS = ("arm", "targets")
LEXICON_KEYS = ("lexicon_id", "description", "match", "written", "groups", "excluded")
GROUP_KEYS = ("need", "targets", "cues")
RULE_PATH = dp.DATA_DIR / "router_v1.json"
LEXICON_PATH = dp.DATA_DIR / "cue_lexicon_v1.json"


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


def _check_probe(probe: Any) -> None:
    if not isinstance(probe, dict) or set(probe) != set(PROBE_KEYS):
        raise _fail(f"the probe must have exactly the keys {list(PROBE_KEYS)}")
    if probe["arm"] != "B":
        raise _fail(f"the probe answers with arm B, not {probe['arm']!r}")
    if isinstance(probe["samples"], bool) or probe["samples"] != 2:
        raise _fail("the probe compares exactly 2 samples")
    if probe["agreement"] not in AGREEMENT_RULES:
        raise _fail(f"unknown agreement rule {probe['agreement']!r} (known: {list(AGREEMENT_RULES)})")


def _check_when(when: Any, where: str, datasets: frozenset[str], has_probe: bool = False) -> None:
    if not isinstance(when, dict) or not when:
        raise _fail(f"{where}: `when` must be a non-empty object")
    unknown = sorted(set(when) - set(FEATURES))
    if unknown:
        raise _fail(f"{where} tests {unknown}, which is not a router feature (allowed: {list(FEATURES)})")
    if "probe" in when:
        if when["probe"] not in PROBE_OUTCOMES:
            raise _fail(f"{where}: probe takes one of {list(PROBE_OUTCOMES)}")
        if not has_probe:
            raise _fail(f"{where} tests the probe but the rule declares no probe")
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
    if "probe" in rule:
        _check_probe(rule["probe"])
    allowed = frozenset(datasets)
    for number, condition in enumerate(rule["conditions"], 1):
        where = f"condition {number}"
        _check_decision(condition, where, CONDITION_KEYS, ("arm", "targets", "when"))
        _check_when(condition["when"], where, allowed, "probe" in rule)
    _check_decision(rule.get("default"), "default", DEFAULT_KEYS, DEFAULT_KEYS)
    return rule


def load_rule(path: Path, datasets: Iterable[str] | None = None,
              lexicon: dict[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    """The validated rule and the SHA-256 of its bytes (the value the core registration records). A rule that
    tests question cues needs the lexicon they come from."""
    try:
        raw = path.read_bytes()
        rule = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read router rule {path}: {exc}") from exc
    rule = validate_rule(rule, datasets if datasets is not None else dp.load_protocol()["datasets"])
    if any("question_cues" in condition["when"] for condition in rule["conditions"]):
        if lexicon is None:
            raise _fail(f"{path} tests question cues; load it with the cue lexicon they come from")
        check_cues(rule, lexicon)
    return rule, v1.sha256_bytes(raw)


def fixed_rule(arm: str) -> dict[str, Any]:
    """Always-<arm> written in the same grammar, so every policy goes through route()."""
    return {"router_id": f"always-{arm}", "conditions": [],
            "default": {"arm": arm, "targets": sorted(ADDRESSABLE[arm])}}


# ---------------------------------------------------------------- the cue lexicon

def _check_group(name: str, group: Any, seen: dict[str, str]) -> None:
    where = f"cue group {name}"
    if not isinstance(group, dict) or set(group) != set(GROUP_KEYS):
        raise _fail(f"{where} must have exactly the keys {list(GROUP_KEYS)}")
    if not isinstance(group["need"], str) or not group["need"].strip():
        raise _fail(f"{where}: need must be text")
    addressable = frozenset().union(*ADDRESSABLE.values())
    targets = group["targets"]
    if (not isinstance(targets, list) or not targets or not all(isinstance(t, str) for t in targets)
            or len(targets) != len(set(targets)) or not set(targets) <= addressable):
        raise _fail(f"{where}: targets must be distinct labels that a deployable arm addresses {sorted(addressable)}")
    if not isinstance(group["cues"], list) or not group["cues"]:
        raise _fail(f"{where}: cues must be a non-empty list")
    for entry in group["cues"]:
        if (not isinstance(entry, dict) or set(entry) != {"cue", "gloss"} or not isinstance(entry["cue"], str)
                or not re.search(r"\w", entry["cue"]) or not isinstance(entry["gloss"], str)):
            raise _fail(f"{where}: each cue is {{cue, gloss}} naming a word or phrase, not {entry!r}")
        folded = fold(entry["cue"])
        if folded in seen:
            raise _fail(f"cue {entry['cue']!r} appears in {seen[folded]} and in {name}")
        seen[folded] = name


def validate_lexicon(lexicon: Any) -> dict[str, Any]:
    """Fail closed: groups named by need, each with the labels that need points to and its cue words."""
    if not isinstance(lexicon, dict):
        raise _fail("a cue lexicon must be a JSON object")
    unknown = sorted(set(lexicon) - set(LEXICON_KEYS))
    if unknown:
        raise _fail(f"cue lexicon has keys outside its schema: {unknown} (allowed: {list(LEXICON_KEYS)})")
    if not isinstance(lexicon.get("lexicon_id"), str) or not lexicon["lexicon_id"].strip():
        raise _fail("cue lexicon lacks a lexicon_id")
    if any(not isinstance(lexicon[key], str) for key in ("description", "match", "written") if key in lexicon):
        raise _fail("cue lexicon description, match and written must be text")
    if not isinstance(lexicon.get("groups"), dict) or not lexicon["groups"]:
        raise _fail("cue lexicon needs at least one group")
    seen: dict[str, str] = {}
    for name, group in lexicon["groups"].items():
        _check_group(name, group, seen)
    excluded = lexicon.get("excluded", [])
    if not isinstance(excluded, list):
        raise _fail("cue lexicon excluded must be a list")
    for entry in excluded:
        if not isinstance(entry, dict) or set(entry) != {"cue", "reason"} or not isinstance(entry["cue"], str):
            raise _fail(f"each excluded cue is {{cue, reason}}, not {entry!r}")
        if fold(entry["cue"]) in seen:
            raise _fail(f"cue {entry['cue']!r} is both in {seen[fold(entry['cue'])]} and excluded")
    return lexicon


def load_lexicon(path: Path = LEXICON_PATH) -> tuple[dict[str, Any], str]:
    """The validated lexicon and the SHA-256 of its bytes."""
    try:
        raw = path.read_bytes()
        lexicon = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read cue lexicon {path}: {exc}") from exc
    return validate_lexicon(lexicon), v1.sha256_bytes(raw)


def check_cues(rule: dict[str, Any], lexicon: dict[str, Any]) -> None:
    """Every cue a condition tests is in the lexicon, in a group whose targets the condition shares."""
    group_of = {fold(entry["cue"]): name for name, group in lexicon["groups"].items() for entry in group["cues"]}
    for number, condition in enumerate(rule["conditions"], 1):
        for cue in condition["when"].get("question_cues", []):
            name = group_of.get(fold(cue))
            if name is None:
                raise _fail(f"condition {number}: cue {cue!r} is not in the cue lexicon {lexicon['lexicon_id']}")
            needs = lexicon["groups"][name]["targets"]
            if not set(needs) & set(condition["targets"]):
                raise _fail(f"condition {number}: cue {cue!r} marks the need {name} (targets {needs}), which "
                            f"shares no target with the condition's {condition['targets']}")


# ---------------------------------------------------------------- routing

@dataclasses.dataclass(frozen=True)
class Decision:
    arm: str
    targets: tuple[str, ...]
    condition: int | None  # 1-based number of the deciding condition; None for the default
    probed: bool = False   # the B probe ran before the decision (its two answers are part of the cost)


def answers_agree(first: str, second: str, task: str) -> bool:
    """normalized-answer-v1: both parsed answers non-empty and equal (multiple choice: the letter; reading: the
    exact-match normalization). An empty parse is a disagreement, so an unparsed B answer is never trusted."""
    def normal(answer: str) -> str:
        return v1.normalize_em_answer(answer) if task == "reading" else answer.strip().upper()
    a, b = normal(first or ""), normal(second or "")
    return bool(a) and a == b


def _matches(when: dict[str, Any], features: Features) -> bool:
    """The static features of a condition (everything but the probe)."""
    if "dataset" in when and features.dataset_id not in when["dataset"]:
        return False
    bounds = when.get("b_prompt_chars")
    if bounds and not bounds.get("at_least", 0) <= features.b_prompt_chars < bounds.get("below", math.inf):
        return False
    cues = when.get("question_cues")
    return not cues or any(cue_present(cue, features.question) for cue in cues)


def needs_probe(rule: dict[str, Any], features: Features) -> bool:
    """Whether routing this request reaches a probe condition before a condition decides without one."""
    for condition in rule["conditions"]:
        if _matches(condition["when"], features):
            return "probe" in condition["when"]
    return False


def route(rule: dict[str, Any], features: Features, probe_agrees: bool | None = None) -> Decision:
    """The first condition that holds decides. A condition testing the probe is read only after its static
    features hold; from then on the probe has run, whatever the final decision."""
    probed = False
    for number, condition in enumerate(rule["conditions"], 1):
        when = condition["when"]
        if not _matches(when, features):
            continue
        if "probe" in when:
            if probe_agrees is None:
                raise _fail(f"condition {number} of {rule['router_id']} needs the probe outcome")
            probed = True
            if (when["probe"] == "agree") != probe_agrees:
                continue
        return Decision(condition["arm"], tuple(condition["targets"]), number, probed)
    return Decision(rule["default"]["arm"], tuple(rule["default"]["targets"]), None, probed)


def route_items(rule: dict[str, Any], items: Iterable[v1.EvalItem],
                probe_agrees: dict[str, bool] | None = None) -> dict[str, Decision]:
    """{dataset:item: decision} for frozen main-v1 items, each seen only through its RequestView. A probe rule
    needs the probe outcome of every item that reaches a probe condition."""
    decisions = {}
    for item in items:
        key = dp.item_key(item.dataset_id, item.item_id)
        decisions[key] = route(rule, features_of(request_view(item)), (probe_agrees or {}).get(key))
    return decisions


# ---------------------------------------------------------------- command line

def phase_items(phase: str, protocol: dict[str, Any], main_items: dict[str, v1.EvalItem]) -> list[v1.EvalItem]:
    anchors, _ = dp.anchor_item_keys(dp.ROOT / protocol["parent"]["pilot_dir"])
    return dp.phase_base_items(phase, protocol, main_items, anchors)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a router rule and show the arms it selects (offline).")
    ap.add_argument("--rule", type=Path, required=True, help="router rule JSON")
    ap.add_argument("--lexicon", type=Path, default=LEXICON_PATH, help=f"cue lexicon (default: {LEXICON_PATH})")
    args = ap.parse_args(argv)
    protocol = dp.load_protocol()
    lexicon, lexicon_digest = load_lexicon(args.lexicon)
    rule, digest = load_rule(args.rule, protocol["datasets"], lexicon)
    main_items = v1.rebuild_items(protocol["parent"]["manifest_phase"])
    print(f"rule {rule['router_id']}  sha256 {digest}")
    print(f"cue lexicon {lexicon['lexicon_id']}  sha256 {lexicon_digest}")
    for phase in dp.PHASES:
        items = phase_items(phase, protocol, main_items)
        if "probe" in rule:  # the arm depends on the probe outcome, which only a run can give
            views = [features_of(request_view(item)) for item in items]
            arms = {outcome: dict(Counter(route(rule, view, outcome == "agree").arm for view in views))
                    for outcome in PROBE_OUTCOMES}
            print(f"{phase}: {len(items)} items, probe needed for {sum(needs_probe(rule, v) for v in views)}; "
                  f"arms if every probe agrees {arms['agree']}, if every probe disagrees {arms['disagree']}")
            continue
        decisions = route_items(rule, items)
        counts = Counter((item.dataset_id, decisions[dp.item_key(item.dataset_id, item.item_id)].arm) for item in items)
        print(f"{phase}: {len(items)} items, arms {dict(sorted(Counter(d.arm for d in decisions.values()).items()))}")
        for dataset_id in sorted({dataset for dataset, _ in counts}):
            arms = {arm: n for (dataset, arm), n in sorted(counts.items()) if dataset == dataset_id}
            print(f"  {dataset_id}: {arms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
