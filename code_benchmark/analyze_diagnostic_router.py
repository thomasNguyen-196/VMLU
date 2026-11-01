"""Offline evaluation of a router rule (openspec change: diagnostic-prospective-campaign, design Decisions 11
and 12, spec `diagnostic-router`).

* design_fit (wide, design only): the rule routes the 1,239 wide items, and an item's accuracy under an arm
  is the mean of that arm's two wide draws (B: MC-90 and MC-91; S: MC-90 and MC-92). Items routed to K or KS
  have no wide outcome and are counted apart. Nothing is tested and no interval is computed. For the reading
  items of the first draw pair, each routed group's exact-match rescues and regressions of S against B are
  set against the semantic review of task 12: a rescue whose B answer was already right in meaning, or a
  regression whose S answer was, is a measurement effect.
* design_fit_probe (wide, design only, router v2): a rule with a B probe is fitted through two rotations,
  (B1 answers, B2 is the probe's second answer, S1 on escalation) and (B2, B1, S2), and the rotations are
  averaged. The cost of an item includes both probe answers whenever the probe ran. It also reports the share of
  escalated items and B and S accuracy where the two B answers agree and where they differ.
* best_fixed_arm (wide): B or S, whichever has the higher mean accuracy over its two draws (a tie goes to the
  arm with fewer mean reported tokens).
* design-fit and evaluate load the rule with the cue lexicon (`diagnostic_router.load_lexicon`): a cue outside
  it fails, and the lexicon's SHA-256 is part of both results.
* evaluate (core, once): the SHA-256 of the rule, of the cue lexicon and of the anchor diagnosis must equal
  the registration.
  The evaluation set is the anchors whose core manifest holds the arm the rule selects; the others are
  listed. The item outcome is the strict majority of replicates. For the router, always-B, always-S and the
  registered best fixed arm: accuracy with a Wilson interval and the mean reported total tokens per item
  (unknown usage stays unknown); exact McNemar of the router against always-B and against always-S, Holm over
  the two; the ceiling over the deployable arms next to the B-replicate ceiling; the same comparisons without
  the gold-not-valid anchors; and a descriptive detection block that scores the routing against the
  adjudicated hypotheses, which the router itself never reads.

Usage (repo root):
  .venv/bin/python -m code_benchmark.analyze_diagnostic_router design-fit --rule <rule.json> [--rule ...] \
      [--lexicon <json>] [--out <json>]
  .venv/bin/python -m code_benchmark.analyze_diagnostic_router evaluate --run-dir <core output dir> \
      [--rule data/diagnostic_prospective_v1/router_v1.json] [--lexicon <json>] \
      [--diagnosis <anchor_diagnosis_v1.jsonl>] [--with-design-fit] [--out <json>]
  .venv/bin/python -m code_benchmark.analyze_diagnostic_router heldout --run-dir <held-out output dir>
  .venv/bin/python -m code_benchmark.analyze_diagnostic_router heldout-semantic --run-dir <held-out output dir>
  .venv/bin/python -m code_benchmark.analyze_diagnostic_router heldout-v3 --run-dir <held-out v3 output dir>
  .venv/bin/python -m code_benchmark.analyze_diagnostic_router calibration-check [--out <json>]
  .venv/bin/python -m code_benchmark.analyze_diagnostic_router k2 --run-dir <K2 output dir>

heldout-semantic (descriptive, after the single held-out evaluation): the reading items whose exact match differs
between B and S in the first rotation, set against the AI-assisted semantic review of the answer that lost
(`diagnostic_semantic_review build --heldout`); it writes its own file and leaves the registered report as it is.

heldout-v3 (router v3, openspec change diagnostic-router-v3, run once): per rotation, the calibration items of each
dataset choose its policy through the frozen procedure (`diagnostic_calibration`) and the emitted rule routes the
test items; v3, the frozen v2 rule, always-B and always-S are compared per family, with McNemar of v3 against v2 and
against always-S (Holm over the two), and per dataset the choice is set against the best policy in hindsight.
calibration-check (exploratory design information): the same procedure on random calibration samples of the used
draws (wide and MC-94), scored on each dataset's other items.

k2 (openspec change diagnostic-k2-retrieval, run once): ViBidLQA questions without their passage. Per rotation the
60 calibration items choose among always-B (closed book), always-K, the K cascade and always-KS by mean token-F1
(`diagnostic_k2`), and the emitted rule routes the 300 test items; the router is tested against always-K and
always-KS with paired sign-flip tests on token-F1 (Holm over the two), next to the O ceiling and the retrieval hits.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from code_benchmark import analyze_diagnostic_prospective as an
    from code_benchmark import diagnostic_calibration as cal
    from code_benchmark import diagnostic_heldout as dh
    from code_benchmark import diagnostic_heldout_v3 as h3
    from code_benchmark import diagnostic_k2 as k2
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_router as router
    from code_benchmark import diagnostic_semantic_review as sr
    from code_benchmark import vi_multimodel as v1
    from code_benchmark.score_vi_multimodel import wilson_interval
except ImportError:  # executed from code_benchmark/
    import analyze_diagnostic_prospective as an
    import diagnostic_calibration as cal
    import diagnostic_heldout as dh
    import diagnostic_heldout_v3 as h3
    import diagnostic_k2 as k2
    import diagnostic_prospective as dp
    import diagnostic_router as router
    import diagnostic_semantic_review as sr
    import vi_multimodel as v1
    from score_vi_multimodel import wilson_interval

RESULTS_DIR = dp.ROOT / "all_res" / "diagnostic_prospective"
MODEL_DIR = "qwen3-5-9b-65k-prospective"
WIDE_SCORES = (RESULTS_DIR / "wide" / MODEL_DIR / "scores.jsonl",
               RESULTS_DIR / "wide-supplements" / "wide-b-r2" / MODEL_DIR / "scores.jsonl",
               RESULTS_DIR / "wide-supplements" / "wide-s-r2" / MODEL_DIR / "scores.jsonl")
SEMANTIC_DIR = RESULTS_DIR / "wide" / MODEL_DIR / "semantic_review"
DIAGNOSIS_PATH = RESULTS_DIR / "audit" / "anchor_diagnosis_v1.jsonl"
WIDE_ARMS = ("B", "S")
WIDE_DRAWS = (1, 2)
ROUTER_REPORT_KEYS = ("rule_id", "rule_sha256", "cue_lexicon_sha256", "anchor_diagnosis_sha256", "best_fixed_arm",
                      "anchors", "evaluation_set", "excluded_anchors", "routing", "primary", "secondary_valid_gold",
                      "deployable_ceiling", "detection", "design_fit_wide")
HELDOUT_PLAN_ID = "diagnostic-router-v2-heldout-v1"
HELDOUT_REPORT_KEYS = ("plan_id", "rule_id", "rule_sha256", "manifest_sha256", "v1_equals_always_B",
                       "primary_family", "primary_rotation", "families")
HELDOUT_V2_SCORES = dp.ROOT / "all_res" / "diagnostic_router_v2" / "heldout" / MODEL_DIR / "scores.jsonl"
V3_PLAN_ID = "diagnostic-router-v3-heldout-v1"
V3_REPORT_KEYS = ("plan_id", "procedure_id", "procedure_sha256", "manifest_sha256", "v2_rule_sha256",
                  "primary_family", "primary_rotation", "calibration", "families")
V3_POLICIES = ("v3", "v2", "always_B", "always_S")
K2_PLAN_ID = "diagnostic-k2-heldout-v1"
K2_REPORT_KEYS = ("plan_id", "procedure_id", "procedure_sha256", "manifest_sha256", "retrieval_config_sha256",
                  "primary_rotation", "retrieval", "calibration", "rotations")
K2_POLICIES = ("router", *k2.CANDIDATES, "O")
K2_SIGN_FLIPS, K2_BOOTSTRAP, K2_SEED = 20_000, 2_000, 7


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read {path}: {exc}") from exc


def mean_tokens(attempts: list[dict[str, Any]]) -> float | None:
    """Mean reported total tokens of an item's attempts; unknown if any attempt reported no usage."""
    values = [dp.reported_tokens(attempt) for attempt in attempts]
    return None if any(value is None for value in values) else statistics.fmean(values)  # type: ignore[arg-type]


def _known_mean(values: Iterable[float | None]) -> tuple[float | None, int]:
    values = list(values)
    known = [value for value in values if value is not None]
    return (statistics.fmean(known) if known else None), len(values) - len(known)


# ---------------------------------------------------------------- wide: design fit

def load_semantic_review(review_dir: Path, scores_path: Path) -> dict[str, dict[str, Any]]:
    """{dataset:item: direction and whether the answer that lost on exact match was right in meaning} for every
    exact-match rescue (B reviewed) and regression (S reviewed) of the first draw pair; strict labels."""
    design = json.loads((review_dir / "design.json").read_text(encoding="utf-8"))
    if design.get("scores_sha256") != v1.sha256_file(scores_path):
        raise _fail(f"the semantic review in {review_dir} was built from other scores than {scores_path}")
    key = json.loads((review_dir / "key.json").read_text(encoding="utf-8"))
    valid = {unit["unit_id"] for unit in key}
    first, second = (sr.read_labels(review_dir / name, valid) for name in ("labels_A.jsonl", "labels_B.jsonl"))
    adjudicated_path = review_dir / "adjudicated.jsonl"
    final = sr.consensus(first, second, sr.read_labels(adjudicated_path, valid) if adjudicated_path.is_file() else {},
                         key)
    reviewed = {"R": ("rescue", "B"), "G": ("regression", "S")}
    result: dict[str, dict[str, Any]] = {}
    for unit in key:
        if unit["stratum"] not in reviewed:
            continue
        direction, loser = reviewed[unit["stratum"]]
        if unit["arm"] != loser:
            raise _fail(f"semantic unit {unit['unit_id']}: stratum {unit['stratum']} should review arm {loser}")
        result[unit["item_key"]] = {"direction": direction, "loser_right_in_meaning": final[unit["unit_id"]] == "correct",
                                    "loser_label": final[unit["unit_id"]]}
    return result


def _two_draws(groups: dict[tuple[str, str], list[dict[str, Any]]], keys: Iterable[str]) -> None:
    for key in keys:
        for arm in WIDE_ARMS:
            draws = tuple(an.replicate_number(a) for a in groups.get((arm, key), []))
            if draws != WIDE_DRAWS:
                raise _fail(f"wide item {key} needs draws {WIDE_DRAWS} of arm {arm}, found {draws}")


def best_fixed_arm(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups = an.group_attempts(rows)
    keys = sorted({key for (_, key) in groups})
    _two_draws(groups, keys)
    accuracy = {arm: statistics.fmean(statistics.fmean(an.attempt_correct(groups[(arm, key)][draw - 1]) for key in keys)
                                      for draw in WIDE_DRAWS) for arm in WIDE_ARMS}
    tokens = {arm: _known_mean(mean_tokens(groups[(arm, key)]) for key in keys)[0] for arm in WIDE_ARMS}
    best = max(WIDE_ARMS, key=lambda arm: (accuracy[arm], -(tokens[arm] or 0.0)))
    return {"arm": best, "items": len(keys), "mean_accuracy_over_two_draws": accuracy, "mean_total_tokens": tokens}


def design_fit(rule: dict[str, Any], rule_sha256: str, items: list[v1.EvalItem], rows: list[dict[str, Any]],
               semantic: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    decisions = router.route_items(rule, items)
    groups = an.group_attempts(rows)
    keys = list(decisions)
    _two_draws(groups, keys)
    measurable = [key for key in keys if decisions[key].arm in WIDE_ARMS]
    scored = set(measurable)
    arm_for: dict[str, Callable[[str], str]] = {
        "router": lambda key: decisions[key].arm, "always_B": lambda key: "B", "always_S": lambda key: "S"}

    def accuracy(subset: list[str], draw: int | None = None) -> dict[str, float | None]:
        def correct(arm: str, key: str) -> float:
            values = [an.attempt_correct(a) for a in groups[(arm, key)]]
            return float(values[draw - 1]) if draw else statistics.fmean(values)
        return {policy: statistics.fmean(correct(f(key), key) for key in subset) if subset else None
                for policy, f in arm_for.items()}

    by_dataset: dict[str, list[str]] = defaultdict(list)
    by_condition: dict[int | None, list[str]] = defaultdict(list)
    for key in keys:
        by_dataset[key.split(":", 1)[0]].append(key)
        by_condition[decisions[key].condition].append(key)
    report: dict[str, Any] = {
        "design_fit": True, "note": "wide outcomes informed the rule: design fit, no test and no interval",
        "rule_id": rule["router_id"], "rule_sha256": rule_sha256, "items": len(keys),
        "routed": dict(sorted(Counter(decisions[key].arm for key in keys).items())),
        "not_measurable_on_wide": len(keys) - len(measurable),
        "accuracy": accuracy(measurable),
        "accuracy_by_draw_pair": {str(draw): accuracy(measurable, draw) for draw in WIDE_DRAWS},
        "mean_total_tokens": {policy: _known_mean(mean_tokens(groups[(f(key), key)]) for key in measurable)[0]
                              for policy, f in arm_for.items()},
        "by_dataset": {dataset: {"items": len(subset),
                                 "routed": dict(sorted(Counter(decisions[k].arm for k in subset).items())),
                                 **accuracy([k for k in subset if k in scored])}
                       for dataset, subset in sorted(by_dataset.items())},
        "by_condition": [],
        "semantic_review": None,
    }
    for condition in sorted(by_condition, key=lambda c: (c is None, c or 0)):
        subset = by_condition[condition]
        decision = rule["conditions"][condition - 1] if condition else rule["default"]
        report["by_condition"].append({"condition": condition or "default", "arm": decision["arm"],
                                       "targets": decision["targets"], "items": len(subset),
                                       **accuracy([k for k in subset if k in scored])})
    if semantic is not None:
        report["semantic_review"] = _semantic_block(rule, by_condition, groups, semantic)
    return report


ROTATIONS = ((0, 1, 0), (1, 0, 1))  # (index of the answering B draw, of the probe's second B draw, of the S draw)


def _tokens(*attempts: dict[str, Any]) -> int | None:
    values = [dp.reported_tokens(attempt) for attempt in attempts]
    return None if any(value is None for value in values) else sum(values)  # type: ignore[arg-type]


def design_fit_probe(rule: dict[str, Any], rule_sha256: str, items: list[v1.EvalItem], rows: list[dict[str, Any]],
                     semantic: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Design fit of a rule that may probe B, on items with two draws of B and of S, over two rotations."""
    groups = an.group_attempts(rows)
    keyed = {dp.item_key(item.dataset_id, item.item_id): item for item in items}
    _two_draws(groups, list(keyed))
    cells, first_rotation = [], {}
    for key, item in keyed.items():
        features = router.features_of(router.request_view(item))
        for rotation, (answer, probe, s_draw) in enumerate(ROTATIONS, 1):
            b1, b2, s = groups[("B", key)][answer], groups[("B", key)][probe], groups[("S", key)][s_draw]
            agree = router.answers_agree(str(b1.get("prediction") or ""), str(b2.get("prediction") or ""), item.task)
            decision = router.route(rule, features, agree)
            chosen = {"B": b1, "S": s}.get(decision.arm)  # K and KS have no wide draw
            if chosen is None:
                cost = None
            elif not decision.probed:
                cost = _tokens(chosen)
            else:  # both probe answers are paid, and the first one is the B answer
                cost = _tokens(b1, b2) if chosen is b1 else _tokens(b1, b2, chosen)
            cells.append({"key": key, "dataset": item.dataset_id, "rotation": rotation, "agree": agree,
                          "decision": decision, "rule": None if chosen is None else an.attempt_correct(chosen),
                          "always_B": an.attempt_correct(b1), "always_S": an.attempt_correct(s),
                          "tokens": {"rule": cost, "always_B": _tokens(b1), "always_S": _tokens(s)}})
            if rotation == 1:
                first_rotation[key] = decision
    policies = ("rule", "always_B", "always_S")

    def summary(subset: list[dict[str, Any]]) -> dict[str, Any]:
        measured = [cell for cell in subset if cell["rule"] is not None]
        return {"cells": len(subset), **{policy: statistics.fmean(c[policy] for c in measured) if measured else None
                                         for policy in policies}}

    by_condition: dict[int | None, list[str]] = defaultdict(list)
    for key, decision in first_rotation.items():
        by_condition[decision.condition].append(key)
    measured = [cell for cell in cells if cell["rule"] is not None]
    report: dict[str, Any] = {
        "design_fit": True, "note": "wide outcomes informed the rule: design fit, no test and no interval",
        "rule_id": rule["router_id"], "rule_sha256": rule_sha256, "items": len(keyed), "rotations": len(ROTATIONS),
        "routed": dict(sorted(Counter(cell["decision"].arm for cell in cells).items())),
        "not_measurable_on_wide": len(cells) - len(measured),
        "accuracy": summary(cells),
        "accuracy_by_rotation": {str(r): summary([c for c in cells if c["rotation"] == r]) for r in (1, 2)},
        "mean_total_tokens": {policy: _known_mean(c["tokens"][policy] for c in measured)[0] for policy in policies},
        "probed_share": statistics.fmean(cell["decision"].probed for cell in cells),
        "escalated_share": statistics.fmean(cell["decision"].probed and cell["decision"].arm != "B" for cell in cells),
        "probe_split": {name: summary([c for c in cells if c["agree"] is flag])
                        for name, flag in (("agree", True), ("disagree", False))},
        "by_dataset": {dataset: {**summary(subset),
                                 "escalated_share": statistics.fmean(c["decision"].probed and c["decision"].arm != "B"
                                                                     for c in subset),
                                 "mean_total_tokens_rule": _known_mean(c["tokens"]["rule"] for c in subset)[0]}
                       for dataset, subset in sorted(_group_by(cells, "dataset").items())},
        "by_condition": [{"condition": condition or "default",
                          "arm": (rule["conditions"][condition - 1] if condition else rule["default"])["arm"],
                          **summary([c for c in cells if c["decision"].condition == condition])}
                         for condition in sorted({c["decision"].condition for c in cells},
                                                 key=lambda c: (c is None, c or 0))],
        "semantic_review": None,
    }
    if semantic is not None:  # the semantic review covers the first draw pair, that is the first rotation
        report["semantic_review"] = _semantic_block(rule, by_condition, groups, semantic)
    return report


def evaluate_heldout(rule: dict[str, Any], rule_sha256: str, registered: dict[str, Any], manifest_sha256: str,
                     items: list[v1.EvalItem], rows: list[dict[str, Any]], v1_rule: dict[str, Any],
                     families: dict[str, list[str]], primary_family: str) -> dict[str, Any]:
    """The single held-out evaluation of the frozen v2 rule (spec diagnostic-router-heldout). Per family and
    rotation: v2, always-B and always-S with Wilson intervals and mean reported tokens (both probe answers
    included whenever the probe ran), McNemar of v2 against each fixed policy with Holm over the two."""
    for name, actual in (("rule", rule_sha256), ("manifest", manifest_sha256)):
        if actual != registered.get(f"{name}_sha256"):
            raise _fail(f"{name} sha256 {actual} differs from the registered {registered.get(f'{name}_sha256')}; "
                        "nothing is reported")
    keyed = {dp.item_key(item.dataset_id, item.item_id): item for item in items}
    groups = an.group_attempts(rows)
    _two_draws(groups, list(keyed))
    features = {key: router.features_of(router.request_view(item)) for key, item in keyed.items()}
    report_families: dict[str, Any] = {}
    for family, datasets in families.items():
        keys = [key for key, item in keyed.items() if item.dataset_id in datasets]
        rotations: dict[str, Any] = {}
        discordant: list[dict[str, Any]] = []
        for rotation, (answer, probe, s_draw) in enumerate(ROTATIONS, 1):
            outcomes: dict[tuple[str, str], bool] = {}
            tokens: dict[tuple[str, str], float | None] = {}
            f1: dict[str, list[float]] = defaultdict(list)
            split: dict[str, Counter] = {"agree": Counter(), "disagree": Counter()}
            escalated = 0
            for key in keys:
                b1, b2, s = groups[("B", key)][answer], groups[("B", key)][probe], groups[("S", key)][s_draw]
                agree = router.answers_agree(str(b1.get("prediction") or ""), str(b2.get("prediction") or ""),
                                             keyed[key].task)
                decision = router.route(rule, features[key], agree)
                if decision.arm not in WIDE_ARMS:
                    raise _fail(f"{key}: the held-out set has no arm {decision.arm}")
                chosen = b1 if decision.arm == "B" else s
                cost = (_tokens(chosen) if not decision.probed else
                        _tokens(b1, b2) if chosen is b1 else _tokens(b1, b2, chosen))
                escalated += decision.probed and decision.arm != "B"
                for policy, attempt, spent in (("v2", chosen, cost), ("always_B", b1, _tokens(b1)),
                                               ("always_S", s, _tokens(s))):
                    outcomes[(policy, key)] = bool(an.attempt_correct(attempt))
                    tokens[(policy, key)] = spent
                    if "token_f1" in attempt:
                        f1[policy].append(float(attempt["token_f1"]))
                name = "agree" if agree else "disagree"
                split[name]["items"] += 1
                split[name]["B_correct"] += outcomes[("always_B", key)]
                split[name]["S_correct"] += outcomes[("always_S", key)]
                if rotation == 1 and (outcomes[("v2", key)] != outcomes[("always_B", key)]
                                      or outcomes[("v2", key)] != outcomes[("always_S", key)]):
                    discordant.append({"item_key": key, "arm": decision.arm, "probe_agrees": agree,
                                       **{policy: outcomes[(policy, key)] for policy in ("v2", "always_B", "always_S")}})
            block = _comparisons(keys, {"router": lambda key: "v2", "always_B": lambda key: "always_B",
                                        "always_S": lambda key: "always_S"}, outcomes, tokens)
            block["policies"]["v2"] = block["policies"].pop("router")
            block["tests"] = {name.replace("router", "v2"): test for name, test in block["tests"].items()}
            rotations[str(rotation)] = {
                "items": block.pop("anchors"), **block,
                "escalated_share": escalated / len(keys) if keys else None,
                "probe_split": {name: {"items": c["items"],
                                       "B_accuracy": c["B_correct"] / c["items"] if c["items"] else None,
                                       "S_accuracy": c["S_correct"] / c["items"] if c["items"] else None}
                                for name, c in split.items()},
                "mean_token_f1": {policy: statistics.fmean(values) for policy, values in f1.items()} or None,
            }
        report_families[family] = {"datasets": datasets, "items": len(keys), "rotations": rotations,
                                   "discordant_rotation_1": discordant}
    return {
        "plan_id": HELDOUT_PLAN_ID, "rule_id": rule["router_id"], "rule_sha256": rule_sha256,
        "manifest_sha256": manifest_sha256,
        "v1_equals_always_B": all(router.route(v1_rule, features[key]).arm == "B" for key in keyed),
        "primary_family": primary_family, "primary_rotation": 1, "families": report_families,
    }


def _group_by(cells: list[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        grouped[cell[field]].append(cell)
    return grouped


def _semantic_block(rule: dict[str, Any], by_condition: dict[int | None, list[str]],
                    groups: dict[tuple[str, str], list[dict[str, Any]]], semantic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for condition in sorted(by_condition, key=lambda c: (c is None, c or 0)):
        counts = Counter()
        for key in by_condition[condition]:
            b1, s1 = groups[("B", key)][0], groups[("S", key)][0]
            if "em" not in b1 or an.attempt_correct(b1) == an.attempt_correct(s1):
                continue
            direction = "rescue" if an.attempt_correct(s1) else "regression"
            review = semantic.get(key)
            if review is None or review["direction"] != direction:
                raise _fail(f"the semantic review has no {direction} unit for {key}")
            counts[f"em_{direction}s"] += 1
            counts[f"em_{direction}s_measurement_effect"] += review["loser_right_in_meaning"]
        decision = rule["conditions"][condition - 1] if condition else rule["default"]
        rows.append({"condition": condition or "default", "arm": decision["arm"],
                     **{name: counts[name] for name in ("em_rescues", "em_rescues_measurement_effect",
                                                        "em_regressions", "em_regressions_measurement_effect")}})
    return {"source": "semantic review of the first wide draw pair (task 12, AI-assisted, strict labels)",
            "measurement_effect": "the answer that lost on exact match was right in meaning", "groups": rows}


HELDOUT_SEMANTIC_SOURCE = ("AI-assisted semantic review of the held-out reading answers that lost on exact match in "
                           "the first rotation: two blind AI reviewers and a blind adjudication; descriptive, not a "
                           "blind human review")


def heldout_semantic(report: dict[str, Any], semantic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The held-out reading discordance (first rotation) in meaning. In a discordant item exactly one of the B and
    S answers is exact; it counts as right, and the review labels the other one. Strict: only `correct` is right;
    lenient: `partial` too. A losing answer right in meaning is a measurement effect. Items whose B and S answers
    are both exact or both inexact were not reviewed, so their differences in meaning are not counted."""
    reading = report["families"]["reading"]
    discordant = reading["discordant_rotation_1"]
    if {d["item_key"] for d in discordant} != set(semantic):
        raise _fail("the semantic review must cover exactly the reading items discordant in the first rotation")
    groups: dict[tuple[str, bool], Counter] = defaultdict(Counter)
    tests = {mode: {name: Counter(rescues=0, regressions=0) for name in ("v2_vs_always_B", "v2_vs_always_S")}
             for mode in ("exact_match", "strict", "lenient")}
    for d in discordant:
        if d["always_B"] == d["always_S"]:
            raise _fail(f"{d['item_key']}: B and S are both exact or both inexact, so v2 cannot differ from one")
        direction = "rescue" if d["always_S"] else "regression"
        review = semantic[d["item_key"]]
        if review["direction"] != direction:
            raise _fail(f"the semantic review has no {direction} unit for {d['item_key']}")
        group = groups[(d["arm"], d["probe_agrees"])]
        group[f"em_{direction}s"] += 1
        group[f"em_{direction}s_loser_{review['loser_label']}"] += 1
        for mode, right in (("exact_match", False), ("strict", review["loser_label"] == "correct"),
                            ("lenient", review["loser_label"] != "incorrect")):
            b, s = d["always_B"] or right, d["always_S"] or right
            chosen = s if d["arm"] == "S" else b
            for name, fixed in (("v2_vs_always_B", b), ("v2_vs_always_S", s)):
                tests[mode][name]["rescues"] += chosen and not fixed
                tests[mode][name]["regressions"] += fixed and not chosen
    registered = reading["rotations"]["1"]["tests"]
    for name, counts in tests["exact_match"].items():
        if (counts["rescues"], counts["regressions"]) != (registered[name]["rescues"], registered[name]["regressions"]):
            raise _fail(f"{name}: the discordant items do not reproduce the reported exact-match counts")
    return {
        "source": HELDOUT_SEMANTIC_SOURCE, "rotation": 1, "reading_items": reading["items"],
        "items_reviewed": len(discordant),
        "loser_labels": dict(sorted(Counter(review["loser_label"] for review in semantic.values()).items())),
        "groups": [{"v2_arm": arm, "probe": "agree" if agrees else "disagree", **dict(sorted(counts.items()))}
                   for (arm, agrees), counts in sorted(groups.items())],
        "tests": {mode: {name: {**counts, "net": counts["rescues"] - counts["regressions"]}
                         for name, counts in by_name.items()} for mode, by_name in tests.items()},
    }


# ---------------------------------------------------------------- router v3: calibration, then one evaluation

def _deployed(decision: router.Decision, b1: dict[str, Any], b2: dict[str, Any], s: dict[str, Any]
              ) -> tuple[dict[str, Any], int | None]:
    """The attempt a routing decision returns and its reported tokens, both probe answers included when it ran."""
    chosen = b1 if decision.arm == "B" else s
    if not decision.probed:
        return chosen, _tokens(chosen)
    return chosen, _tokens(b1, b2) if chosen is b1 else _tokens(b1, b2, chosen)


def _least(candidates: Iterable[str], score: dict[str, float], tokens: dict[str, float | None]) -> str:
    """The highest score; a tie goes to fewer mean tokens, then to the order given (the procedure's tie rule)."""
    candidates = list(candidates)
    return min(candidates, key=lambda c: (-score[c], float("inf") if tokens[c] is None else tokens[c],
                                          candidates.index(c)))


def evaluate_v3(procedure: dict[str, Any], procedure_sha256: str, registered: dict[str, Any],
                manifest: dict[str, Any], items: list[v1.EvalItem], rows: list[dict[str, Any]],
                v2_rule: dict[str, Any], v2_rule_sha256: str, families: dict[str, list[str]], primary_family: str,
                datasets: list[str]) -> dict[str, Any]:
    """The single evaluation of the router v3 procedure (spec diagnostic-router-v3-heldout). Per rotation the
    calibration items of each dataset choose its policy and the emitted rule routes the test items. Per family and
    rotation: v3, the frozen v2 rule, always-B and always-S on the test items with Wilson intervals and mean reported
    tokens (both probe answers whenever the probe ran), McNemar of v3 against v2 and against always-S with Holm over
    the two; per dataset the choice, the best of always-B, v2 and always-S in hindsight and the regret against it."""
    for name, actual in (("procedure", procedure_sha256), ("manifest", manifest["manifest_sha256"]),
                         ("v2_rule", v2_rule_sha256)):
        if actual != registered.get(f"{name}_sha256"):
            raise _fail(f"{name} sha256 {actual} differs from the registered {registered.get(f'{name}_sha256')}; "
                        "nothing is reported")
    keyed = {dp.item_key(item.dataset_id, item.item_id): item for item in items}
    calibration = {dataset: list(keys) for dataset, keys in manifest["calibration_items"].items()}
    in_calibration = {key for keys in calibration.values() for key in keys}
    if not in_calibration <= set(keyed) or set(calibration) != set(datasets):
        raise _fail("the calibration items must be held-out items of the registered datasets")
    groups = an.group_attempts(rows)
    _two_draws(groups, list(keyed))
    features = {key: router.features_of(router.request_view(item)) for key, item in keyed.items()}
    task_of = {item.dataset_id: item.task for item in items}
    report_calibration: dict[str, Any] = {}
    rules: dict[int, dict[str, Any]] = {}
    for rotation, (answer, probe, s_draw) in enumerate(ROTATIONS, 1):
        chosen: dict[str, dict[str, Any]] = {}
        for dataset in sorted(calibration):
            cells = [(groups[("B", key)][answer], groups[("B", key)][probe], groups[("S", key)][s_draw])
                     for key in calibration[dataset]]
            chosen[dataset] = cal.choose(procedure, cells, task_of[dataset])
            spent = [_tokens(*cell) for cell in cells]
            chosen[dataset]["calibration_tokens"] = None if None in spent else sum(spent)  # type: ignore[arg-type]
        choices = {dataset: result["choice"] for dataset, result in chosen.items()}
        rules[rotation] = cal.emit_rule(procedure, choices, datasets, f"{procedure['procedure_id']}-rotation-{rotation}")
        report_calibration[str(rotation)] = {"choices": choices, "datasets": chosen, "rule": rules[rotation]}
    report_families: dict[str, Any] = {}
    for family, family_datasets in families.items():
        keys = sorted(key for key, item in keyed.items() if item.dataset_id in family_datasets and key not in in_calibration)
        rotations: dict[str, Any] = {}
        discordant: list[dict[str, Any]] = []
        for rotation, (answer, probe, s_draw) in enumerate(ROTATIONS, 1):
            outcomes: dict[tuple[str, str], bool] = {}
            tokens: dict[tuple[str, str], float | None] = {}
            scores: dict[tuple[str, str], float] = {}
            v3_arms: Counter = Counter()
            for key in keys:
                item = keyed[key]
                b1, b2, s = groups[("B", key)][answer], groups[("B", key)][probe], groups[("S", key)][s_draw]
                agree = router.answers_agree(str(b1.get("prediction") or ""), str(b2.get("prediction") or ""), item.task)
                returned = {}
                for policy, rule in (("v3", rules[rotation]), ("v2", v2_rule)):
                    decision = router.route(rule, features[key], agree)
                    if decision.arm not in WIDE_ARMS:
                        raise _fail(f"{key}: the held-out v3 set has no arm {decision.arm}")
                    returned[policy] = _deployed(decision, b1, b2, s)
                    if policy == "v3":
                        v3_arms[decision.arm] += 1
                returned["always_B"], returned["always_S"] = (b1, _tokens(b1)), (s, _tokens(s))
                for policy, (attempt, spent) in returned.items():
                    outcomes[(policy, key)] = bool(an.attempt_correct(attempt))
                    tokens[(policy, key)] = spent
                    scores[(policy, key)] = cal.score_of(attempt, item.task)
                if rotation == 1 and (outcomes[("v3", key)] != outcomes[("always_B", key)]
                                      or outcomes[("v3", key)] != outcomes[("always_S", key)]):
                    discordant.append({"item_key": key, "arm": "B" if returned["v3"][0] is b1 else "S",
                                       "probe_agrees": agree,
                                       **{policy: outcomes[(policy, key)] for policy in V3_POLICIES}})
            block = _comparisons(keys, {"router": lambda key: "v3", **{p: (lambda key, p=p: p) for p in V3_POLICIES[1:]}},
                                 outcomes, tokens, against=("v2", "always_S"))
            block["policies"] = {"v3": block["policies"].pop("router"), **block["policies"]}
            block["tests"] = {name.replace("router", "v3"): test for name, test in block["tests"].items()}
            by_dataset: dict[str, Any] = {}
            for dataset in sorted(family_datasets):
                subset = [key for key in keys if keyed[key].dataset_id == dataset]
                mean_score = {p: statistics.fmean(scores[(p, key)] for key in subset) for p in V3_POLICIES}
                mean_spent = {p: _known_mean(tokens[(p, key)] for key in subset)[0] for p in V3_POLICIES}
                best = _least(("always_B", "v2", "always_S"), mean_score, mean_spent)
                by_dataset[dataset] = {"test_items": len(subset), "score": cal.SCORES[task_of[dataset]],
                                       "choice": report_calibration[str(rotation)]["choices"][dataset],
                                       "scores": mean_score, "mean_tokens": mean_spent, "best_in_hindsight": best,
                                       "regret": mean_score[best] - mean_score["v3"]}
            rotations[str(rotation)] = {"items": block.pop("anchors"), **block, "v3_arms": dict(sorted(v3_arms.items())),
                                        "by_dataset": by_dataset}
        report_families[family] = {"datasets": family_datasets, "test_items": len(keys), "rotations": rotations,
                                   "discordant_rotation_1": discordant}
    return {
        "plan_id": V3_PLAN_ID, "procedure_id": procedure["procedure_id"], "procedure_sha256": procedure_sha256,
        "manifest_sha256": manifest["manifest_sha256"], "v2_rule_sha256": v2_rule_sha256,
        "primary_family": primary_family, "primary_rotation": 1, "calibration": report_calibration,
        "families": report_families,
    }


def _candidate_score(cells: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]], candidate: str,
                     task: str) -> float:
    return statistics.fmean(cal.score_of(cal.outcome(candidate, *cell, task)[0], task) for cell in cells)


def calibration_check(procedure: dict[str, Any], rows: list[dict[str, Any]], *, resamples: int = 300,
                      seed: int = 7) -> dict[str, Any]:
    """Exploratory design information on used draws: per dataset, the procedure chooses from a random calibration
    sample in a random rotation, and the choice is scored on the dataset's other items of that rotation against the
    best candidate on those items (regret). Items without two draws of B and of S are left out."""
    groups = an.group_attempts(rows)
    entries: dict[str, list[str]] = defaultdict(list)
    task_of: dict[str, str] = {}
    for (arm, key), attempts in sorted(groups.items()):
        if arm == "B" and len(attempts) == 2 and len(groups.get(("S", key), [])) == 2:
            entries[attempts[0]["dataset_id"]].append(key)
            task_of[attempts[0]["dataset_id"]] = "reading" if "em" in attempts[0] else "multiple_choice"
    rng = random.Random(seed)
    size = procedure["calibration_items"]
    result: dict[str, Any] = {"resamples": resamples, "seed": seed, "calibration_items": size, "datasets": {}}
    for dataset, keys in sorted(entries.items()):
        task = task_of[dataset]
        cells = [[(groups[("B", key)][a], groups[("B", key)][p], groups[("S", key)][s]) for key in keys]
                 for a, p, s in ROTATIONS]

        whole = {c: statistics.fmean(_candidate_score(rotation_cells, c, task) for rotation_cells in cells) for c in cal.CANDIDATES}
        picks: Counter = Counter()
        regrets = []
        for _ in range(resamples):
            rotation = rng.randrange(len(ROTATIONS))
            chosen_idx = set(rng.sample(range(len(keys)), size))
            sample = [cell for i, cell in enumerate(cells[rotation]) if i in chosen_idx]
            rest = [cell for i, cell in enumerate(cells[rotation]) if i not in chosen_idx]
            choice = cal.choose(procedure, sample, task)["choice"]
            picks[choice] += 1
            regrets.append(max(_candidate_score(rest, c, task) for c in cal.CANDIDATES) - _candidate_score(rest, choice, task))
        result["datasets"][dataset] = {"items": len(keys), "score": cal.SCORES[task], "whole_set_scores": whole,
                                       "choices": {c: picks[c] for c in cal.CANDIDATES},
                                       "mean_regret": statistics.fmean(regrets)}
    return result


# ---------------------------------------------------------------- K2: calibration, then one evaluation

def sign_flip_p(differences: list[float], resamples: int = K2_SIGN_FLIPS, seed: int = K2_SEED) -> float:
    """Two-sided paired sign-flip test of a zero mean difference: Monte Carlo over random signs, the observed
    arrangement counted once, so p = (1 + hits) / (1 + resamples)."""
    nonzero = [value for value in differences if value != 0]
    if not nonzero:
        return 1.0
    observed = abs(sum(nonzero))
    rng = random.Random(seed)
    hits = 0
    for _ in range(resamples):
        signs = rng.getrandbits(len(nonzero))
        total = sum(value if signs >> index & 1 else -value for index, value in enumerate(nonzero))
        hits += abs(total) >= observed - 1e-12
    return (1 + hits) / (1 + resamples)


def bootstrap_mean_ci(values: list[float], resamples: int = K2_BOOTSTRAP, seed: int = K2_SEED) -> list[float] | None:
    """95% percentile bootstrap interval of a mean, in percent."""
    if not values:
        return None
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(resamples))
    return [100 * means[int(0.025 * resamples)], 100 * means[int(0.975 * resamples) - 1]]


def _k2_policy_block(keys: list[str], f1: dict[str, float], em: dict[str, bool], tokens: dict[str, int | None]
                     ) -> dict[str, Any]:
    values = [f1[key] for key in keys]
    correct = sum(em[key] for key in keys)
    mean, unknown = _known_mean(tokens[key] for key in keys)
    return {"n": len(keys), "mean_token_f1": statistics.fmean(values) if values else None,
            "token_f1_ci95_pct": bootstrap_mean_ci(values), "em_correct": correct,
            "em": correct / len(keys) if keys else None, "em_ci95_pct": wilson_interval(correct, len(keys)),
            "mean_total_tokens": mean, "tokens_unknown_items": unknown}


def evaluate_k2(procedure: dict[str, Any], procedure_sha256: str, registered: dict[str, Any], manifest: dict[str, Any],
                items: list[v1.EvalItem], rows: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    """The single evaluation of K2 (spec diagnostic-k2-router). Per rotation the calibration items choose among
    always-B, always-K, the K cascade and always-KS and the emitted rule routes the test items. For the router, each
    candidate and O: mean token-F1 with a bootstrap interval, exact match with a Wilson interval and mean reported
    tokens (both K answers whenever the probe ran); sign-flip tests of the router against always-K and always-KS on
    token-F1 with Holm over the two; the best candidate in hindsight, the regret and the retrieval split."""
    for name, actual in (("procedure", procedure_sha256), ("manifest", manifest["manifest_sha256"]),
                         ("retrieval_config", manifest["retrieval_config_sha256"])):
        if actual != registered.get(f"{name}_sha256"):
            raise _fail(f"{name} sha256 {actual} differs from the registered {registered.get(f'{name}_sha256')}; "
                        "nothing is reported")
    keyed = {dp.item_key(item.dataset_id, item.item_id): item for item in items}
    calibration = list(manifest["calibration_items"])
    if not set(calibration) <= set(keyed) or len(calibration) != procedure["calibration_items"]:
        raise _fail("the calibration items must be K2 items, as many as the procedure takes")
    test = sorted(set(keyed) - set(calibration))
    groups = an.group_attempts(rows)
    for key in keyed:
        for arm in k2.ARMS:
            draws = tuple(an.replicate_number(a) for a in groups.get((arm, key), []))
            if draws != WIDE_DRAWS:
                raise _fail(f"K2 item {key} needs draws {WIDE_DRAWS} of arm {arm}, found {draws}")
    features = {key: k2.request_features(item, protocol) for key, item in keyed.items()}
    retrieval = manifest["retrieval"]
    hit = {key: retrieval[key]["own_rank"] is not None and retrieval[key]["own_rank"] <= 2 for key in keyed}
    report_calibration: dict[str, Any] = {}
    report_rotations: dict[str, Any] = {}
    discordant: list[dict[str, Any]] = []
    for rotation, (answer, probe, _) in enumerate(ROTATIONS, 1):
        def draws(key: str, answer: int = answer, probe: int = probe) -> tuple[dict[str, Any], ...]:
            return (groups[("B", key)][answer], groups[("K", key)][answer], groups[("K", key)][probe],
                    groups[("KS", key)][answer])
        cells = [draws(key) for key in calibration]
        chosen = k2.choose(procedure, cells)
        spent = [_tokens(*cell) for cell in cells]
        chosen["calibration_tokens"] = None if None in spent else sum(spent)  # type: ignore[arg-type]
        rule = k2.emit_rule(procedure, chosen["choice"], f"{procedure['procedure_id']}-rotation-{rotation}")
        report_calibration[str(rotation)] = {**chosen, "rule": rule}
        f1: dict[str, dict[str, float]] = defaultdict(dict)
        em: dict[str, dict[str, bool]] = defaultdict(dict)
        tokens: dict[str, dict[str, int | None]] = defaultdict(dict)
        router_arms: Counter = Counter()
        for key in test:
            b, k, k_second, ks = draws(key)
            agree = router.answers_agree(str(k.get("prediction") or ""), str(k_second.get("prediction") or ""), "reading")
            decision = router.route(rule, features[key], agree)
            router_arms[decision.arm] += 1
            attempt = {"B": b, "K": k, "KS": ks}[decision.arm]
            cost = (_tokens(attempt) if not decision.probed else
                    _tokens(k, k_second) if attempt is k else _tokens(k, k_second, attempt))
            returned = {"router": (attempt, cost),
                        **{candidate: k2.outcome(candidate, b, k, k_second, ks) for candidate in k2.CANDIDATES},
                        "O": (groups[("O", key)][answer], _tokens(groups[("O", key)][answer]))}
            for policy, (row, row_tokens) in returned.items():
                f1[policy][key] = cal.score_of(row, "reading")
                em[policy][key] = bool(an.attempt_correct(row))
                tokens[policy][key] = row_tokens
            if rotation == 1 and (em["router"][key] != em["always_K"][key] or em["router"][key] != em["always_KS"][key]):
                discordant.append({"item_key": key, "arm": decision.arm, "own_passage_retrieved": hit[key],
                                   **{policy: em[policy][key] for policy in ("router", "always_K", "always_KS")}})
        policies = {policy: _k2_policy_block(test, f1[policy], em[policy], tokens[policy]) for policy in K2_POLICIES}
        tests = {}
        for other in ("always_K", "always_KS"):
            differences = [f1["router"][key] - f1[other][key] for key in test]
            rescues = sum(em["router"][key] and not em[other][key] for key in test)
            regressions = sum(em[other][key] and not em["router"][key] for key in test)
            tests[f"router_vs_{other}"] = {
                "mean_token_f1_difference": statistics.fmean(differences) if differences else None,
                "items_differing": sum(value != 0 for value in differences),
                "sign_flip_p": sign_flip_p(differences),
                "em_rescues": rescues, "em_regressions": regressions,
                "em_mcnemar_p": an.mcnemar_exact_p(regressions, rescues)}
        adjusted = an.holm_adjust({name: result["sign_flip_p"] for name, result in tests.items()})
        for name, result in tests.items():
            result["sign_flip_p_holm"] = adjusted[name]
        means = {candidate: policies[candidate]["mean_token_f1"] for candidate in k2.CANDIDATES}
        best = max(means.values())
        best_in_hindsight = [c for c in k2.CANDIDATES if best - means[c] <= procedure["equal_within"]][-1]
        by_retrieval = {}
        for label, subset in (("own_passage_in_top_2", [key for key in test if hit[key]]),
                              ("own_passage_missed", [key for key in test if not hit[key]])):
            by_retrieval[label] = {"items": len(subset), **{
                policy: statistics.fmean(f1[policy][key] for key in subset) if subset else None
                for policy in ("always_B", "always_K", "always_KS", "O")}}
        report_rotations[str(rotation)] = {
            "test_items": len(test), "choice": chosen["choice"], "router_arms": dict(sorted(router_arms.items())),
            "policies": policies, "tests": tests, "best_in_hindsight": best_in_hindsight,
            "regret": means[best_in_hindsight] - policies["router"]["mean_token_f1"], "by_retrieval": by_retrieval,
        }
    report_rotations["1"]["discordant"] = discordant
    ranks = {role: [retrieval[key]["own_rank"] for key in keys] for role, keys in (("calibration", calibration), ("test", test))}
    return {
        "plan_id": K2_PLAN_ID, "procedure_id": procedure["procedure_id"], "procedure_sha256": procedure_sha256,
        "manifest_sha256": manifest["manifest_sha256"], "retrieval_config_sha256": manifest["retrieval_config_sha256"],
        "primary_rotation": 1,
        "retrieval": {role: {"items": len(values), "own_rank_1": sum(rank == 1 for rank in values),
                             "own_in_top_2": sum(rank is not None and rank <= 2 for rank in values),
                             "own_not_ranked": sum(rank is None for rank in values)} for role, values in ranks.items()},
        "calibration": report_calibration, "rotations": report_rotations,
    }


# ---------------------------------------------------------------- core: one evaluation

def _comparisons(keys: list[str], arms_for: dict[str, Callable[[str], str]],
                 outcomes: dict[tuple[str, str], bool], tokens: dict[tuple[str, str], float | None],
                 against: tuple[str, ...] = ("always_B", "always_S")) -> dict[str, Any]:
    policies = {}
    for name, arm_for in arms_for.items():
        correct = sum(outcomes[(arm_for(key), key)] for key in keys)
        mean, unknown = _known_mean(tokens[(arm_for(key), key)] for key in keys)
        policies[name] = {"n": len(keys), "correct": correct, "accuracy": correct / len(keys) if keys else None,
                          "accuracy_ci95_pct": wilson_interval(correct, len(keys)), "mean_total_tokens": mean,
                          "tokens_unknown_items": unknown}
    chosen = arms_for["router"]
    tests = {}
    for other in against:
        fixed = arms_for[other]
        rescues = sum(outcomes[(chosen(key), key)] and not outcomes[(fixed(key), key)] for key in keys)
        regressions = sum(outcomes[(fixed(key), key)] and not outcomes[(chosen(key), key)] for key in keys)
        tests[f"router_vs_{other}"] = {"rescues": rescues, "regressions": regressions,
                                       "mcnemar_p": an.mcnemar_exact_p(regressions, rescues)}
    adjusted = an.holm_adjust({name: test["mcnemar_p"] for name, test in tests.items()})
    for name, test in tests.items():
        test["mcnemar_p_holm"] = adjusted[name]
    return {"anchors": len(keys), "policies": policies, "tests": tests}


def detection(keys: list[str], decisions: dict[str, router.Decision],
              diagnosis: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Descriptive: did the router send each anchor with an adjudicated hypothesis to an arm that targets it?"""
    addressable = frozenset().union(*router.ADDRESSABLE.values())
    per_label: dict[str, Counter] = defaultdict(Counter)
    anchors = []
    for key in keys:
        labels, decision = diagnosis[key]["diagnostic_labels"], decisions[key]
        for label in labels:
            per_label[label]["anchors"] += 1
            per_label[label]["sent_to_a_targeting_arm"] += label in decision.targets
        if labels:
            anchors.append({"item_key": key, "labels": labels, "arm": decision.arm, "targets": list(decision.targets),
                            "addressable": bool(set(labels) & addressable),
                            "detected": bool(set(labels) & set(decision.targets))})
    no_issue = [key for key in keys if diagnosis[key]["diagnostic_outcome"] == "no_observed_issue"]
    return {
        "descriptive": True,
        "anchors_with_hypotheses": len(anchors),
        "anchors_with_addressable_hypotheses": sum(a["addressable"] for a in anchors),
        "detected": sum(a["detected"] for a in anchors),
        "per_label": {label: {"anchors": counts["anchors"], "sent_to_a_targeting_arm": counts["sent_to_a_targeting_arm"],
                              "addressable_by_a_deployable_arm": label in addressable}
                      for label, counts in sorted(per_label.items())},
        "no_issue_anchors": len(no_issue),
        "no_issue_sent_beyond_B": sum(decisions[key].arm != "B" for key in no_issue),
        "issue_without_hypothesis": sum(diagnosis[key]["diagnostic_outcome"] == "issue_observed"
                                        and not diagnosis[key]["diagnostic_labels"] for key in keys),
        "unresolved": sum(diagnosis[key]["diagnostic_outcome"] == "unresolved" for key in keys),
        "anchors": anchors,
    }


def evaluate(rule: dict[str, Any], rule_sha256: str, lexicon_sha256: str, registered: dict[str, Any],
             decisions: dict[str, router.Decision], manifest_arms: dict[str, set[str]], rows: list[dict[str, Any]],
             diagnosis: dict[str, dict[str, Any]], diagnosis_sha256: str,
             design_fit_wide: dict[str, Any] | None = None) -> dict[str, Any]:
    """The single core evaluation of the frozen rule. Exits before computing anything when a hash differs."""
    for name, actual in (("rule", rule_sha256), ("cue_lexicon", lexicon_sha256), ("anchor_diagnosis", diagnosis_sha256)):
        expected = registered.get(f"{name}_sha256")
        if actual != expected:
            raise _fail(f"{name} sha256 {actual} differs from the registered {expected}; nothing is reported")
    best = registered.get("best_fixed_arm")
    if best not in WIDE_ARMS:
        raise _fail(f"the registered best fixed arm must be one of {list(WIDE_ARMS)}, not {best!r}")
    anchors = list(decisions)
    if set(anchors) != set(manifest_arms) or set(anchors) != set(diagnosis):
        raise _fail("the routed anchors, the core manifest and the anchor diagnosis must cover the same anchors")
    excluded = [{"item_key": key, "selected_arm": decisions[key].arm,
                 "reason": f"the core manifest has no arm {decisions[key].arm} for this anchor"}
                for key in anchors if decisions[key].arm not in manifest_arms[key]]
    keys = [key for key in anchors if decisions[key].arm in manifest_arms[key]]
    arms_for: dict[str, Callable[[str], str]] = {
        "router": lambda key: decisions[key].arm, "always_B": lambda key: "B", "always_S": lambda key: "S",
        "best_fixed": lambda key: best}
    groups = an.group_attempts(rows)
    needed = sorted({(arm_for(key), key) for arm_for in arms_for.values() for key in keys})
    missing = [f"{arm} on {key}" for arm, key in needed if (arm, key) not in groups]
    if missing:
        raise _fail(f"no scored attempt for {missing[:3]} ({len(missing)} in all)")
    outcomes = {pair: an.item_outcome(groups[pair])[0] for pair in needed}
    tokens = {pair: mean_tokens(groups[pair]) for pair in needed}
    valid = [key for key in keys if diagnosis[key]["gold_validity"] == "valid"]
    in_set = set(keys)
    return {
        "rule_id": rule["router_id"], "rule_sha256": rule_sha256, "cue_lexicon_sha256": lexicon_sha256,
        "anchor_diagnosis_sha256": diagnosis_sha256,
        "best_fixed_arm": best, "anchors": len(anchors), "evaluation_set": len(keys), "excluded_anchors": excluded,
        "routing": {"arms": dict(sorted(Counter(decisions[key].arm for key in anchors).items())),
                    "conditions": dict(Counter(str(decisions[key].condition or "default") for key in anchors))},
        "primary": _comparisons(keys, arms_for, outcomes, tokens),
        "secondary_valid_gold": {**_comparisons(valid, arms_for, outcomes, tokens), "removed": len(keys) - len(valid),
                                 "removed_anchors": [key for key in keys if key not in set(valid)]},
        "deployable_ceiling": an.oracle_ceilings(r for r in rows if an.arm_of(r) != "O" and an.item_key_of(r) in in_set),
        "detection": detection(keys, decisions, diagnosis),
        "design_fit_wide": design_fit_wide,
    }


# ---------------------------------------------------------------- command line

def _wide_inputs(protocol: dict[str, Any]) -> tuple[list[v1.EvalItem], list[dict[str, Any]]]:
    main_items = v1.rebuild_items(protocol["parent"]["manifest_phase"])
    rows = [row for path in WIDE_SCORES for row in read_jsonl(path)]
    return router.phase_items("wide", protocol, main_items), rows


def _print_fit(fit: dict[str, Any]) -> None:
    def pct(value):
        return "—" if value is None else f"{100 * value:5.1f}"
    acc, tokens = fit["accuracy"], fit["mean_total_tokens"]
    print(f"{fit['rule_id']}  sha256 {fit['rule_sha256'][:12]}  routed {fit['routed']}  "
          f"not measurable on wide {fit['not_measurable_on_wide']}")
    print(f"  accuracy (mean of two draws)  router {pct(acc['router'])}  always-B {pct(acc['always_B'])}  "
          f"always-S {pct(acc['always_S'])}   tokens router {tokens['router'] or 0:.0f}  "
          f"B {tokens['always_B'] or 0:.0f}  S {tokens['always_S'] or 0:.0f}")
    for draw, values in fit["accuracy_by_draw_pair"].items():
        print(f"  draw pair {draw}  router {pct(values['router'])}  always-B {pct(values['always_B'])}  "
              f"always-S {pct(values['always_S'])}")
    for group in fit["by_condition"]:
        print(f"  condition {group['condition']} -> {group['arm']} {group['targets']}: {group['items']} items, "
              f"router {pct(group['router'])}  B {pct(group['always_B'])}  S {pct(group['always_S'])}")
    for group in (fit["semantic_review"] or {}).get("groups", []):
        print(f"  reading pair 1, condition {group['condition']}: EM rescues {group['em_rescues']} "
              f"({group['em_rescues_measurement_effect']} measurement), EM regressions {group['em_regressions']} "
              f"({group['em_regressions_measurement_effect']} measurement)")


def _heldout_cli(args: argparse.Namespace, protocol: dict[str, Any], lexicon: dict[str, Any]) -> int:
    registration = json.loads(dh.REGISTRATION_PATH.read_text(encoding="utf-8"))
    entry = registration["router"]
    if entry.get("report_keys") != list(HELDOUT_REPORT_KEYS):
        raise _fail("the registered held-out report keys differ from the evaluator's")
    heldout = dh.load_protocol()
    rule, digest = router.load_rule(dh.RULE_PATH, protocol["datasets"], lexicon)
    v1_rule, _ = router.load_rule(router.RULE_PATH, protocol["datasets"], lexicon)
    manifest, _ = dh.build_manifest(heldout)
    if manifest != dh.load_frozen_manifest():
        raise _fail("the rebuilt held-out manifest differs from the frozen one")
    report = evaluate_heldout(rule, digest, {**entry, "manifest_sha256": registration["frozen"]["manifest_sha256"]},
                              manifest["manifest_sha256"], dh.sample_items(heldout),
                              read_jsonl(args.run_dir / "scores.jsonl"), v1_rule,
                              heldout["analysis"]["families"], heldout["analysis"]["primary_family"])
    out = args.out or args.run_dir / "analysis" / "router_v2_report.json"
    _write_json(out, report)
    for family, block in report["families"].items():
        for rotation, result in block["rotations"].items():
            policies, tests = result["policies"], result["tests"]
            print(f"{family} rotation {rotation} ({result['items']} items, escalated {100 * result['escalated_share']:.1f}%): "
                  + "  ".join(f"{name} {p['correct']}/{p['n']} tokens {p['mean_total_tokens'] or 0:.0f}"
                              for name, p in policies.items())
                  + "  |  " + "  ".join(f"{name}: +{t['rescues']}/-{t['regressions']} p {t['mcnemar_p']:.3f} "
                                        f"holm {t['mcnemar_p_holm']:.3f}" for name, t in tests.items()))
    print(f"v1 equals always-B on the held-out set: {report['v1_equals_always_B']}")
    print(f"report -> {out}")
    return 0


def _heldout_semantic_cli(args: argparse.Namespace) -> int:
    review_dir = args.review_dir or args.run_dir / "semantic_review"
    report_path = args.run_dir / "analysis" / "router_v2_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    result = heldout_semantic(report, load_semantic_review(review_dir, args.run_dir / "scores.jsonl"))
    design = json.loads((review_dir / "design.json").read_text(encoding="utf-8"))
    key = json.loads((review_dir / "key.json").read_text(encoding="utf-8"))
    valid = {unit["unit_id"] for unit in key}
    first, second = (sr.read_labels(review_dir / name, valid) for name in ("labels_A.jsonl", "labels_B.jsonl"))
    result.update({"review_design": {name: design[name] for name in ("seed", "population", "sampled", "units")},
                   "reviewer_agreement": sr.agreement(first, second, key), "report_sha256": v1.sha256_file(report_path)})
    out = args.out or args.run_dir / "analysis" / "router_v2_semantic_review.json"
    _write_json(out, result)
    agreement = result["reviewer_agreement"]
    kappa = agreement["kappa_three_class"]
    print(f"{result['source']}\n{result['items_reviewed']} items; reviewers agree on "
          f"{agreement['units'] - agreement['disagreements']}/{agreement['units']} "
          f"(kappa {'—' if kappa is None else f'{kappa:.2f}'}); losing answers {result['loser_labels']}")
    for group in result["groups"]:
        print(f"  v2 -> {group['v2_arm']} (probe {group['probe']}): "
              + ", ".join(f"{name} {value}" for name, value in group.items() if name.startswith("em_")))
    for mode, by_name in result["tests"].items():
        print(f"  {mode:11} " + "  ".join(f"{name}: +{t['rescues']}/-{t['regressions']} (net {t['net']:+d})"
                                          for name, t in by_name.items()))
    print(f"report -> {out}")
    return 0


def _heldout_v3_cli(args: argparse.Namespace) -> int:
    registration = json.loads(h3.REGISTRATION_PATH.read_text(encoding="utf-8"))
    entry = registration["router"]
    if entry.get("report_keys") != list(V3_REPORT_KEYS):
        raise _fail("the registered held-out v3 report keys differ from the evaluator's")
    campaign, protocol = dp.load_protocol(), h3.load_protocol()
    procedure, digest = cal.load_procedure()
    v2_rule, v2_digest = router.load_rule(dh.RULE_PATH, campaign["datasets"])
    manifest, _ = h3.build_manifest(protocol)
    if manifest != h3.load_frozen_manifest():
        raise _fail("the rebuilt held-out v3 manifest differs from the frozen one")
    items, _ = h3.sample_items(protocol)
    analysis = protocol["analysis"]
    report = evaluate_v3(procedure, digest, {**entry, "manifest_sha256": registration["frozen"]["manifest_sha256"]},
                         manifest, items, read_jsonl(args.run_dir / "scores.jsonl"), v2_rule, v2_digest,
                         analysis["families"], analysis["primary_family"], protocol["datasets"])
    out = args.out or args.run_dir / "analysis" / "router_v3_report.json"
    _write_json(out, report)
    for rotation, block in report["calibration"].items():
        print(f"rotation {rotation} choices: " + "  ".join(f"{d}: {c}" for d, c in block["choices"].items()))
    for family, block in report["families"].items():
        for rotation, result in block["rotations"].items():
            print(f"{family} rotation {rotation} ({result['items']} test items, v3 arms {result['v3_arms']}): "
                  + "  ".join(f"{name} {p['correct']}/{p['n']} tokens {p['mean_total_tokens'] or 0:.0f}"
                              for name, p in result["policies"].items())
                  + "  |  " + "  ".join(f"{name}: +{t['rescues']}/-{t['regressions']} holm {t['mcnemar_p_holm']:.3f}"
                                        for name, t in result["tests"].items()))
            for dataset, row in result["by_dataset"].items():
                print(f"    {dataset}: chose {row['choice']}, best in hindsight {row['best_in_hindsight']}, "
                      f"regret {row['regret']:+.4f}")
    print(f"report -> {out}")
    return 0


def _calibration_check_cli(args: argparse.Namespace) -> int:
    procedure, digest = cal.load_procedure()
    rows = [row for path in (*WIDE_SCORES, HELDOUT_V2_SCORES) for row in read_jsonl(path)]
    result = {"procedure_sha256": digest, **calibration_check(procedure, rows, resamples=args.resamples)}
    for dataset, row in result["datasets"].items():
        whole = "  ".join(f"{c} {row['whole_set_scores'][c]:.3f}" for c in cal.CANDIDATES)
        print(f"{dataset.replace('vi-multimodel-v1-', ''):16} n {row['items']:4}  {row['score']:13} {whole}  "
              f"choices {row['choices']}  mean regret {row['mean_regret']:.4f}")
    if args.out:
        _write_json(args.out, result)
    return 0


def _k2_cli(args: argparse.Namespace) -> int:
    registration = json.loads(k2.REGISTRATION_PATH.read_text(encoding="utf-8"))
    entry, frozen = registration["router"], registration["frozen"]
    if entry.get("report_keys") != list(K2_REPORT_KEYS):
        raise _fail("the registered K2 report keys differ from the evaluator's")
    protocol = k2.load_protocol()
    procedure, digest = k2.load_procedure()
    manifest, rebuilt = k2.build_manifest(protocol)
    if manifest != k2.load_frozen_manifest():
        raise _fail("the rebuilt K2 manifest differs from the frozen one")
    report = evaluate_k2(procedure, digest, {**entry, "manifest_sha256": frozen["manifest_sha256"],
                                             "retrieval_config_sha256": frozen["retrieval_config_sha256"]},
                         manifest, k2.base_items(rebuilt), read_jsonl(args.run_dir / "scores.jsonl"), protocol)
    out = args.out or args.run_dir / "analysis" / "k2_report.json"
    _write_json(out, report)
    print("retrieval: " + "  ".join(f"{role} {r['own_in_top_2']}/{r['items']} own passage in the top 2"
                                    for role, r in report["retrieval"].items()))
    for rotation, block in report["rotations"].items():
        calibration = report["calibration"][rotation]
        print(f"rotation {rotation}: calibration chose {calibration['choice']} ("
              + ", ".join(f"{c} {v:.3f}" for c, v in calibration["scores"].items()) + f"); router arms {block['router_arms']}")
        print("  " + "  ".join(f"{name} F1 {p['mean_token_f1']:.3f} EM {p['em_correct']}/{p['n']} tok "
                               f"{p['mean_total_tokens'] or 0:.0f}" for name, p in block["policies"].items()))
        print("  " + "  ".join(f"{name}: {t['mean_token_f1_difference']:+.4f} holm {t['sign_flip_p_holm']:.3f}"
                               for name, t in block["tests"].items())
              + f"  |  best in hindsight {block['best_in_hindsight']}, regret {block['regret']:+.4f}")
    print(f"report -> {out}")
    return 0


def _print_probe_fit(fit: dict[str, Any]) -> None:
    def pct(value):
        return "—" if value is None else f"{100 * value:5.1f}"
    acc, tokens = fit["accuracy"], fit["mean_total_tokens"]
    print(f"{fit['rule_id']}  sha256 {fit['rule_sha256'][:12]}  routed (item x rotation) {fit['routed']}  "
          f"probed {pct(fit['probed_share'])}%  escalated {pct(fit['escalated_share'])}%")
    print(f"  accuracy (mean of two rotations)  rule {pct(acc['rule'])}  always-B {pct(acc['always_B'])}  "
          f"always-S {pct(acc['always_S'])}   tokens rule {tokens['rule'] or 0:.0f}  B {tokens['always_B'] or 0:.0f}  "
          f"S {tokens['always_S'] or 0:.0f}")
    for name, split in fit["probe_split"].items():
        print(f"  probe {name}: {split['cells']} cells  B {pct(split['always_B'])}  S {pct(split['always_S'])}")
    for dataset, row in fit["by_dataset"].items():
        print(f"  {dataset.replace('vi-multimodel-v1-', ''):14} rule {pct(row['rule'])}  B {pct(row['always_B'])}  "
              f"S {pct(row['always_S'])}  escalated {pct(row['escalated_share'])}%  "
              f"tokens {row['mean_total_tokens_rule'] or 0:.0f}")
    for group in (fit["semantic_review"] or {}).get("groups", []):
        print(f"  reading rotation 1, condition {group['condition']}: EM rescues {group['em_rescues']} "
              f"({group['em_rescues_measurement_effect']} measurement), EM regressions {group['em_regressions']} "
              f"({group['em_regressions_measurement_effect']} measurement)")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate a router rule offline (design fit on wide, once on core).")
    sub = ap.add_subparsers(dest="command", required=True)
    fit = sub.add_parser("design-fit", help="design fit of candidate rules on the wide draws (no tests)")
    fit.add_argument("--rule", type=Path, action="append", required=True, help="candidate rule JSON (repeatable)")
    fit.add_argument("--lexicon", type=Path, default=router.LEXICON_PATH, help=f"default: {router.LEXICON_PATH}")
    fit.add_argument("--semantic-review", type=Path, default=SEMANTIC_DIR, help=f"default: {SEMANTIC_DIR}")
    fit.add_argument("--out", type=Path, help="write the design fits and the best fixed arm as JSON")
    ev = sub.add_parser("evaluate", help="the single core evaluation of the registered rule")
    ev.add_argument("--run-dir", type=Path, required=True, help="core output dir (scores.jsonl, source_manifest.json)")
    ev.add_argument("--rule", type=Path, default=router.RULE_PATH, help=f"default: {router.RULE_PATH}")
    ev.add_argument("--lexicon", type=Path, default=router.LEXICON_PATH, help=f"default: {router.LEXICON_PATH}")
    ev.add_argument("--diagnosis", type=Path, default=DIAGNOSIS_PATH, help=f"default: {DIAGNOSIS_PATH}")
    ev.add_argument("--with-design-fit", action="store_true", help="add the wide design fit of the same rule")
    ev.add_argument("--out", type=Path, help="default: <run-dir>/analysis/router_report.json")
    ho = sub.add_parser("heldout", help="the single held-out evaluation of router v2 (MC-94)")
    ho.add_argument("--run-dir", type=Path, required=True, help="held-out output dir (scores.jsonl)")
    ho.add_argument("--lexicon", type=Path, default=router.LEXICON_PATH, help=f"default: {router.LEXICON_PATH}")
    ho.add_argument("--out", type=Path, help="default: <run-dir>/analysis/router_v2_report.json")
    hs = sub.add_parser("heldout-semantic", help="descriptive: the held-out reading discordance in meaning")
    hs.add_argument("--run-dir", type=Path, required=True, help="held-out output dir (scores.jsonl, analysis/)")
    hs.add_argument("--review-dir", type=Path, help="default: <run-dir>/semantic_review")
    hs.add_argument("--out", type=Path, help="default: <run-dir>/analysis/router_v2_semantic_review.json")
    v3 = sub.add_parser("heldout-v3", help="the single evaluation of the router v3 procedure (MC-95)")
    v3.add_argument("--run-dir", type=Path, required=True, help="held-out v3 output dir (scores.jsonl)")
    v3.add_argument("--out", type=Path, help="default: <run-dir>/analysis/router_v3_report.json")
    check = sub.add_parser("calibration-check", help="exploratory: the v3 procedure on the used draws (wide, MC-94)")
    check.add_argument("--resamples", type=int, default=300)
    check.add_argument("--out", type=Path, help="write the check as JSON")
    kk = sub.add_parser("k2", help="the single evaluation of K2 (MC-96)")
    kk.add_argument("--run-dir", type=Path, required=True, help="K2 output dir (scores.jsonl)")
    kk.add_argument("--out", type=Path, help="default: <run-dir>/analysis/k2_report.json")
    args = ap.parse_args(argv)
    if args.command == "heldout-semantic":
        return _heldout_semantic_cli(args)
    if args.command == "heldout-v3":
        return _heldout_v3_cli(args)
    if args.command == "calibration-check":
        return _calibration_check_cli(args)
    if args.command == "k2":
        return _k2_cli(args)
    protocol = dp.load_protocol()
    lexicon, lexicon_digest = router.load_lexicon(args.lexicon)
    if args.command == "heldout":
        return _heldout_cli(args, protocol, lexicon)
    if args.command == "design-fit":
        items, rows = _wide_inputs(protocol)
        semantic = load_semantic_review(args.semantic_review, WIDE_SCORES[0])
        result = {"cue_lexicon": {"lexicon_id": lexicon["lexicon_id"], "sha256": lexicon_digest},
                  "best_fixed_arm": best_fixed_arm(rows), "fits": []}
        print(f"cue lexicon {lexicon['lexicon_id']}  sha256 {lexicon_digest}")
        for path in args.rule:
            rule, digest = router.load_rule(path, protocol["datasets"], lexicon)
            if "probe" in rule:
                result["fits"].append(design_fit_probe(rule, digest, items, rows, semantic))
                _print_probe_fit(result["fits"][-1])
            else:
                result["fits"].append(design_fit(rule, digest, items, rows, semantic))
                _print_fit(result["fits"][-1])
        best = result["best_fixed_arm"]
        print(f"best fixed arm {best['arm']} (mean of two draws: "
              + ", ".join(f"{arm} {100 * value:.2f}" for arm, value in best["mean_accuracy_over_two_draws"].items()) + ")")
        if args.out:
            _write_json(args.out, result)
        return 0
    entry = dp.load_registration().get("router")
    if not isinstance(entry, dict):
        raise _fail("the registration has no router entry yet (task 6.5)")
    if entry.get("report_keys") != list(ROUTER_REPORT_KEYS):
        raise _fail("the registered router report keys differ from the evaluator's")
    rule, digest = router.load_rule(args.rule, protocol["datasets"], lexicon)
    diagnosis, diagnosis_digest = dp.load_anchor_diagnosis(args.diagnosis)
    main_items = v1.rebuild_items(protocol["parent"]["manifest_phase"])
    decisions = router.route_items(rule, router.phase_items("core", protocol, main_items))
    manifest = json.loads((args.run_dir / "source_manifest.json").read_text(encoding="utf-8"))
    manifest_arms: dict[str, set[str]] = defaultdict(set)
    for row in manifest["items"]:
        manifest_arms[dp.item_key(row["dataset_id"], row["item_id"])].add(dp.arm_of_replicate(row["replicate_id"]))
    wide = None
    if args.with_design_fit:
        items, rows = _wide_inputs(protocol)
        wide = design_fit(rule, digest, items, rows, load_semantic_review(SEMANTIC_DIR, WIDE_SCORES[0]))
    report = evaluate(rule, digest, lexicon_digest, entry, decisions, dict(manifest_arms),
                      read_jsonl(args.run_dir / "scores.jsonl"), diagnosis, diagnosis_digest, wide)
    out = args.out or args.run_dir / "analysis" / "router_report.json"
    _write_json(out, report)
    primary = report["primary"]
    print(f"evaluation set {report['evaluation_set']}/{report['anchors']}  "
          + "  ".join(f"{name} {policy['correct']}/{policy['n']}" for name, policy in primary["policies"].items()))
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
