"""Offline analysis for the prospective diagnostic campaign (openspec change: diagnostic-prospective-campaign).

Pure functions over the scored attempt rows that run_diagnostic_prospective writes to scores.jsonl.
Written and tested before any prospective data exist. The plan is fixed in the change's design.md
(Decision 8) and in data/diagnostic_prospective_v1/protocol.json (`analysis`):

* item outcome = strict majority of correct replicates (a tie counts as incorrect and is reported);
* rescue = B incorrect and arm correct; regression = the reverse; recovery = rescues / B-incorrect items;
  regression rate = regressions / B-correct items; net gain = (rescues - regressions) / paired items;
* exact two-sided McNemar per arm versus B inside each family (multiple choice, reading), Holm-corrected
  across the arms of a family; Wilson intervals for recovery and regression; passage-cluster bootstrap
  for the net gain; per-dataset counts are descriptive only;
* noise reference: attempt-level rescue / regression between the replicates of B itself (core), shown
  next to each arm's attempt-level rescue / regression against B, so a rescue is read against sampling noise;
* secondary and labelled as such: a sensitivity analysis restricted to items whose reasoning-arm attempts
  all carried the final-answer label; for reading, the paired token-F1 difference with a passage-cluster
  interval and the number of rescues that look like format effects (B already near-matched the gold);
* wide only: a parity gate comparing B per dataset with the MC-83 reference interval;
* oracle-routing ceilings are always reported next to the ceiling over B replicates alone;
* every discordant item is exported in both directions for human semantic review, and reading items with
  token-F1 at or above the threshold but exact match zero are listed as audit candidates, never as correct;
* wide supplement MC-91 (a second B draw of every item): `noise_reference` reads that draw against the
  registered first draws of B and S, as drift, B-versus-B noise, S against an independent baseline draw,
  S against the noise on items selected by the first B draw, stable categories and an oracle ceiling with a
  noise floor. It never replaces the registered S-versus-B analysis of MC-90;
* wide supplement MC-92 (a second S draw of every item): `s_noise_reference` adds the sampling noise of S itself,
  a comparison of how often B and S change their result between two draws, the items one arm wins in both draws,
  the S-versus-B effect over two draws per arm and the oracle ceiling over each arm's own two draws;
* core, design Decision 12: `recovery_by_hypothesis` groups the anchors by adjudicated hypothesis, reports the
  rescues and regressions per arm and lists contrast candidates for a reviewer; it never upgrades a hypothesis.

Usage: .venv/bin/python -m code_benchmark.analyze_diagnostic_prospective --scores <scores.jsonl> --phase core
       ... --phase wide --scores <MC-90 scores.jsonl> --noise-scores <MC-91 scores.jsonl> --noise-out <json>
       ... --s-noise-scores <MC-92 scores.jsonl> --s-noise-out <json>   (needs --noise-scores)
       ... --phase core --diagnosis <anchor_diagnosis_v1.jsonl> --diagnosis-out <json>
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark.score_vi_multimodel import clustered_mean_interval, wilson_interval
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    from score_vi_multimodel import clustered_mean_interval, wilson_interval

BASELINE = "B"
FAMILIES = ("mc", "reading")


def attempt_correct(row: dict[str, Any]) -> bool:
    if "correct" in row:
        return bool(row["correct"])
    if "em" in row:
        return bool(row["em"])
    raise ValueError("scored row has neither `correct` nor `em`")


def family_of(row: dict[str, Any]) -> str:
    return "mc" if "correct" in row else "reading"


def item_key_of(row: dict[str, Any]) -> str:
    return dp.item_key(row["dataset_id"], row["item_id"])


def arm_of(row: dict[str, Any]) -> str:
    return row.get("arm") or dp.arm_of_replicate(row["replicate_id"])


def replicate_number(row: dict[str, Any]) -> int:
    return int(str(row["replicate_id"]).partition("-r")[2])


def group_attempts(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """{(arm, dataset:item): attempts ordered by replicate number}."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(arm_of(row), item_key_of(row))].append(row)
    for attempts in groups.values():
        attempts.sort(key=replicate_number)
    return dict(groups)


def item_outcome(attempts: list[dict[str, Any]]) -> tuple[bool, bool]:
    """(correct by strict majority, tie). A tie counts as incorrect."""
    n, k = len(attempts), sum(attempt_correct(a) for a in attempts)
    return 2 * k > n, n % 2 == 0 and 2 * k == n


def mcnemar_exact_p(regressions: int, rescues: int) -> float:
    """Exact two-sided McNemar p-value from the discordant counts."""
    n = regressions + rescues
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(regressions, rescues) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def holm_adjust(pvalues: dict[str, float]) -> dict[str, float]:
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    total, running, adjusted = len(ordered), 0.0, {}
    for index, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (total - index) * p))
        adjusted[name] = running
    return adjusted


def paired_counts(outcomes: dict[tuple[str, str], bool], arm: str, keys: set[str] | None = None,
                  baseline: str = BASELINE) -> dict[str, Any]:
    arm_items = {key for (a, key) in outcomes if a == arm}
    base_items = {key for (a, key) in outcomes if a == baseline}
    shared = sorted((arm_items & base_items) if keys is None else (arm_items & base_items & keys))
    both = regress = rescue = neither = 0
    for key in shared:
        b_ok, a_ok = outcomes[(baseline, key)], outcomes[(arm, key)]
        both += b_ok and a_ok
        regress += b_ok and not a_ok
        rescue += (not b_ok) and a_ok
        neither += (not b_ok) and (not a_ok)
    b_wrong, b_right, n = rescue + neither, both + regress, len(shared)
    return {
        "arm": arm, "n_pairs": n, "both_correct": both, "regressions": regress, "rescues": rescue,
        "both_incorrect": neither, "baseline_incorrect": b_wrong, "baseline_correct": b_right,
        "recovery": rescue / b_wrong if b_wrong else None,
        "regression_rate": regress / b_right if b_right else None,
        "net_gain": (rescue - regress) / n if n else None,
        "mcnemar_p": mcnemar_exact_p(regress, rescue),
    }


# ---------------------------------------------------------------- noise reference (attempt level)

def _tally(first_ok: bool, second_ok: bool, counts: dict[str, int]) -> None:
    if first_ok:
        counts["first_correct"] += 1
        counts["regressions"] += not second_ok
    else:
        counts["first_incorrect"] += 1
        counts["rescues"] += second_ok


def _rates(counts: dict[str, int]) -> dict[str, Any]:
    first_wrong, first_right = counts["first_incorrect"], counts["first_correct"]
    return {**counts,
            "recovery": counts["rescues"] / first_wrong if first_wrong else None,
            "regression_rate": counts["regressions"] / first_right if first_right else None}


def baseline_noise(rows: Iterable[dict[str, Any]], baseline: str = BASELINE) -> dict[str, Any] | None:
    """Attempt-level rescue / regression between the replicates of B itself (every ordered pair of
    replicates of an item). It is the sampling-noise reference for an arm's own attempt-level rates."""
    counts = {"ordered_pairs": 0, "first_incorrect": 0, "first_correct": 0, "rescues": 0, "regressions": 0}
    for (arm, _), attempts in group_attempts(rows).items():
        if arm != baseline:
            continue
        for i, first in enumerate(attempts):
            for j, second in enumerate(attempts):
                if i != j:
                    counts["ordered_pairs"] += 1
                    _tally(attempt_correct(first), attempt_correct(second), counts)
    return _rates(counts) if counts["ordered_pairs"] else None


def attempt_level_counts(rows: Iterable[dict[str, Any]], arm: str, baseline: str = BASELINE) -> dict[str, Any] | None:
    """Attempt-level rescue / regression of `arm` against B, pairing the attempts that share a replicate number."""
    groups = group_attempts(rows)
    counts = {"attempt_pairs": 0, "first_incorrect": 0, "first_correct": 0, "rescues": 0, "regressions": 0}
    for (a, key), attempts in groups.items():
        if a != arm or (baseline, key) not in groups:
            continue
        partner_of = {replicate_number(r): r for r in groups[(baseline, key)]}
        for attempt in attempts:
            partner = partner_of.get(replicate_number(attempt))
            if partner is not None:
                counts["attempt_pairs"] += 1
                _tally(attempt_correct(partner), attempt_correct(attempt), counts)
    return _rates(counts) if counts["attempt_pairs"] else None


# ---------------------------------------------------------------- secondary and sensitivity analyses

def compliant_item_keys(groups: dict[tuple[str, str], list[dict[str, Any]]], arm: str,
                        keys: set[str]) -> set[str] | None:
    """Items whose attempts of `arm` ALL carried the final-answer label; None when the arm has no format flag."""
    arm_groups = {key: attempts for (a, key), attempts in groups.items() if a == arm and key in keys}
    if not any(r.get("format_ok") is not None for attempts in arm_groups.values() for r in attempts):
        return None
    return {key for key, attempts in arm_groups.items() if all(r.get("format_ok") is True for r in attempts)}


def item_mean_f1(groups: dict[tuple[str, str], list[dict[str, Any]]]) -> dict[tuple[str, str], float]:
    return {key: statistics.fmean(float(r["token_f1"]) for r in attempts)
            for key, attempts in groups.items() if all("token_f1" in r for r in attempts)}


def parity_gate(rows: Iterable[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    """Wide only: is B per dataset inside the MC-83 reference interval? A failure points at the infrastructure,
    not at the arms, and stops the interpretation of any effect."""
    reference = protocol["analysis"]["parity_reference"]
    rows = list(rows)
    results: dict[str, Any] = {}
    for dataset_id, spec in reference["datasets"].items():
        attempts = [r for r in rows if arm_of(r) == BASELINE and r["dataset_id"] == dataset_id]
        if not attempts:
            results[dataset_id] = None
            continue
        observed = 100 * sum(attempt_correct(r) for r in attempts) / len(attempts)
        low, high = spec["ci95"]
        results[dataset_id] = {"metric": spec["metric"], "n": len(attempts), "observed": round(observed, 2),
                               "reference": spec["value"], "reference_ci95": [low, high],
                               "within_reference_ci": low <= observed <= high}
    measured = [v for v in results.values() if v]
    return {"source": reference["source"], "datasets": results,
            "all_within": bool(measured) and all(v["within_reference_ci"] for v in measured)}


# ---------------------------------------------------------------- exports

def semantic_audit_candidates(rows: Iterable[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    """Reading attempts with exact match 0 but token-F1 at or above the threshold (not counted as correct)."""
    return [
        {"dataset_id": r["dataset_id"], "item_id": r["item_id"], "replicate_id": r["replicate_id"], "arm": arm_of(r),
         "token_f1": r["token_f1"], "prediction": r.get("prediction"), "gold_answer": r.get("gold_answer")}
        for r in rows if "em" in r and not r["em"] and float(r.get("token_f1", 0.0)) >= threshold
    ]


def discordant_pairs(rows: Iterable[dict[str, Any]], arm: str, baseline: str = BASELINE,
                     f1_threshold: float | None = None) -> list[dict[str, Any]]:
    """Every item whose majority outcome differs between `arm` and B, rescues and regressions alike.
    A reading rescue is flagged `format_suspect` when B already near-matched the gold (mean token-F1 at or
    above the threshold), which points at an answer-format effect rather than a reasoning one."""
    threshold = f1_threshold if f1_threshold is not None else dp.load_protocol()["scoring"]["semantic_audit_candidate_token_f1"]
    groups = group_attempts(rows)
    items = sorted({key for (a, key) in groups if a == arm} & {key for (a, key) in groups if a == baseline})

    def side(attempts):
        return [{"replicate_id": a["replicate_id"], "correct": attempt_correct(a), "prediction": a.get("prediction"),
                 "prompt_sha256": a.get("prompt_sha256"), "raw_response": a.get("raw_response")} for a in attempts]

    exported = []
    for key in items:
        b_ok, _ = item_outcome(groups[(baseline, key)])
        a_ok, _ = item_outcome(groups[(arm, key)])
        if b_ok == a_ok:
            continue
        base_attempts = groups[(baseline, key)]
        suspect = None
        if a_ok and all("token_f1" in r for r in base_attempts):
            suspect = statistics.fmean(float(r["token_f1"]) for r in base_attempts) >= threshold
        exported.append({"item_key": key, "arm": arm, "direction": "rescue" if a_ok else "regression",
                         "format_suspect": suspect, "gold_answer": groups[(arm, key)][0].get("gold_answer"),
                         baseline: side(base_attempts), arm: side(groups[(arm, key)])})
    return exported


def oracle_ceilings(rows: Iterable[dict[str, Any]], baseline: str = BASELINE) -> dict[str, Any]:
    """Oracle-routing ceiling over the arms available per item (first draw of each arm), reported with the
    same ceiling over replicates of B alone (same number of draws). Without B replicates there is no valid
    noise floor and the null is reported as unavailable."""
    groups = group_attempts(rows)
    items = sorted({key for (_, key) in groups})
    used = observed = null = capped = 0
    for key in items:
        arms = [arm for arm in dp.ARMS if (arm, key) in groups]
        if baseline not in arms or len(arms) < 2:
            continue
        used += 1
        observed += any(attempt_correct(groups[(arm, key)][0]) for arm in arms)
        b_attempts = groups[(baseline, key)]
        capped += len(b_attempts) < len(arms)
        null += any(attempt_correct(a) for a in b_attempts[:len(arms)])
    if not used:
        return {"items": 0, "observed": None, "null_from_baseline_replicates": None, "headroom_over_null": None,
                "null_capped_items": 0, "note": "no item has B and a second arm"}
    result: dict[str, Any] = {"items": used, "observed": observed / used, "null_capped_items": capped}
    if capped == used:
        result.update({"null_from_baseline_replicates": None, "headroom_over_null": None,
                       "note": "single draw per arm: no noise floor from B replicates; do not read the ceiling as headroom"})
    else:
        result.update({"null_from_baseline_replicates": null / used, "headroom_over_null": (observed - null) / used,
                       "note": "null capped on some items (fewer B replicates than arms)" if capped else "ok"})
    return result


# ---------------------------------------------------------------- the report

def analyze(rows: Iterable[dict[str, Any]], *, phase: str, protocol: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = list(rows)
    protocol = protocol or dp.load_protocol()
    plan = protocol["analysis"]
    f1_threshold = protocol["scoring"]["semantic_audit_candidate_token_f1"]
    groups = group_attempts(rows)
    outcomes: dict[tuple[str, str], bool] = {}
    ties = 0
    for key, attempts in groups.items():
        outcomes[key], tie = item_outcome(attempts)
        ties += tie
    mean_f1 = item_mean_f1(groups)
    passage_of: dict[str, str] = {}
    family_items: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        key = item_key_of(row)
        family_items[family_of(row)].add(key)
        passage_of.setdefault(key, str(row.get("passage_id") or key))
    arms = [arm for arm in dp.ARMS if arm != BASELINE and any(a == arm for (a, _) in outcomes)]
    report: dict[str, Any] = {"phase": phase, "plan_id": plan["plan_id"], "baseline": BASELINE, "item_ties": ties,
                              "per_dataset_is_descriptive_only": True, "families": {}, "baseline_noise": {}}
    for family in FAMILIES:
        keys = family_items.get(family, set())
        if not keys:
            continue
        family_rows = [r for r in rows if family_of(r) == family]
        counts = {arm: paired_counts(outcomes, arm, keys) for arm in arms}
        counts = {arm: value for arm, value in counts.items() if value["n_pairs"]}
        adjusted = holm_adjust({arm: value["mcnemar_p"] for arm, value in counts.items()})
        report["baseline_noise"][family] = baseline_noise(family_rows)
        for arm, value in counts.items():
            value["mcnemar_p_holm"] = adjusted[arm]
            value["recovery_ci95"] = wilson_interval(value["rescues"], value["baseline_incorrect"])
            value["regression_ci95"] = wilson_interval(value["regressions"], value["baseline_correct"])
            shared = sorted(k for k in keys if (arm, k) in outcomes and (BASELINE, k) in outcomes)
            diffs = [{"diff": int(outcomes[(arm, k)]) - int(outcomes[(BASELINE, k)]),
                      "cluster": passage_of[k] if family == "reading" else k} for k in shared]
            value["net_gain_ci95_pct"] = clustered_mean_interval(
                diffs, value_key="diff", cluster_key="cluster", seed=plan["bootstrap_seed"],
                samples=plan["bootstrap_resamples"])
            by_dataset: dict[str, dict[str, int]] = defaultdict(lambda: {"n_pairs": 0, "rescues": 0, "regressions": 0})
            for key in shared:
                slot = by_dataset[key.split(":")[0]]
                slot["n_pairs"] += 1
                slot["rescues"] += (not outcomes[(BASELINE, key)]) and outcomes[(arm, key)]
                slot["regressions"] += outcomes[(BASELINE, key)] and not outcomes[(arm, key)]
            value["by_dataset_descriptive"] = dict(sorted(by_dataset.items()))
            value["attempt_level"] = attempt_level_counts(family_rows, arm)
            compliant = compliant_item_keys(groups, arm, keys)
            if compliant is None:
                value["sensitivity_format_compliant"] = None
            else:
                sensitivity = paired_counts(outcomes, arm, keys & compliant)
                sensitivity["items_excluded"] = value["n_pairs"] - sensitivity["n_pairs"]
                value["sensitivity_format_compliant"] = sensitivity
            value["mean_f1_diff"] = value["mean_f1_diff_ci95_pts"] = value["rescues_format_suspect"] = None
            if family == "reading":
                f1_diffs = [{"diff": mean_f1[(arm, k)] - mean_f1[(BASELINE, k)], "cluster": passage_of[k]}
                            for k in shared if (arm, k) in mean_f1 and (BASELINE, k) in mean_f1]
                if f1_diffs:
                    value["mean_f1_diff"] = statistics.fmean(d["diff"] for d in f1_diffs)
                    value["mean_f1_diff_ci95_pts"] = clustered_mean_interval(
                        f1_diffs, value_key="diff", cluster_key="cluster", seed=plan["bootstrap_seed"],
                        samples=plan["bootstrap_resamples"])
                value["rescues_format_suspect"] = sum(
                    1 for k in shared if not outcomes[(BASELINE, k)] and outcomes[(arm, k)]
                    and mean_f1.get((BASELINE, k), 0.0) >= f1_threshold)
        report["families"][family] = {"item_count": len(keys), "arms": counts}
    report["oracle_routing"] = oracle_ceilings(rows)
    report["semantic_audit_candidates_n"] = len(semantic_audit_candidates(rows, f1_threshold))
    report["parity_gate"] = parity_gate(rows, protocol) if phase == "wide" else None
    return report


# ---------------------------------------------------------------- B replicate supplement (MC-91)

NOISE_FAMILY_KEYS = ("n_items", "accuracy", "drift", "noise_recovery", "noise_recovery_ci95", "noise_regression_rate",
                     "noise_regression_ci95", "agreement_rate", "s_vs_b2", "s_vs_noise_given_b1_wrong",
                     "s_vs_noise_given_b1_right", "stable", "oracle", "mean_f1", "by_dataset_descriptive")
NOISE_TOP_KEYS = ("plan_id", "noise_replicate", "items_shared", "items_missing_in_noise_run", "families",
                  "parity_gate_b2")


def _conditional_contrast(items: list[str], s: dict[str, bool], b2: dict[str, bool], *, wrong: bool) -> dict[str, Any]:
    """Two fresh draws (S and the second B) compared on items selected by the first B draw. The selection acts on
    the first draw only, so regression to the mean affects both comparands alike and cancels in the difference."""
    flag = (lambda ok: not ok) if wrong else (lambda ok: ok)
    only_s = sum(flag(s[k]) and not flag(b2[k]) for k in items)
    only_b2 = sum(flag(b2[k]) and not flag(s[k]) for k in items)
    n = len(items)
    return {"n": n, "s_count": sum(flag(s[k]) for k in items), "b2_count": sum(flag(b2[k]) for k in items),
            "s_only": only_s, "b2_only": only_b2, "difference": (only_s - only_b2) / n if n else None,
            "mcnemar_p": mcnemar_exact_p(only_s, only_b2)}


def noise_reference(primary_rows: Iterable[dict[str, Any]], noise_rows: Iterable[dict[str, Any]], *,
                    protocol: dict[str, Any] | None = None, noise_replicate: int = 2) -> dict[str, Any]:
    """Sampling-noise reference for wide (supplement MC-91): the second B draw of every item read against the
    registered first draws of B and S. It never replaces the registered S-versus-B analysis."""
    protocol = protocol or dp.load_protocol()
    plan = protocol["analysis"]
    primary = list(primary_rows)
    noise = [r for r in noise_rows if arm_of(r) == BASELINE]
    if any(replicate_number(r) != noise_replicate for r in noise):
        raise ValueError(f"noise rows must all be replicate {noise_replicate} of arm B")

    def first_draws(arm: str) -> dict[str, dict[str, Any]]:
        return {item_key_of(r): r for r in primary if arm_of(r) == arm and replicate_number(r) == 1}

    b1_rows, s1_rows, b2_rows = first_draws(BASELINE), first_draws("S"), {item_key_of(r): r for r in noise}
    shared = sorted(set(b1_rows) & set(s1_rows) & set(b2_rows))
    b1, s1, b2 = ({k: attempt_correct(rows[k]) for k in shared} for rows in (b1_rows, s1_rows, b2_rows))
    report: dict[str, Any] = {
        "plan_id": plan["plan_id"], "noise_replicate": noise_replicate, "items_shared": len(shared),
        "items_missing_in_noise_run": len((set(b1_rows) & set(s1_rows)) - set(b2_rows)), "families": {},
        "parity_gate_b2": parity_gate(noise, protocol)}
    for family in FAMILIES:
        keys = [k for k in shared if family_of(b1_rows[k]) == family]
        if not keys:
            continue
        n = len(keys)
        both_ok = sum(b1[k] and b2[k] for k in keys)
        regress = sum(b1[k] and not b2[k] for k in keys)
        rescue = sum((not b1[k]) and b2[k] for k in keys)
        both_wrong = n - both_ok - regress - rescue
        b1_wrong, b1_right = rescue + both_wrong, both_ok + regress
        passage_of = {k: str(b1_rows[k].get("passage_id") or k) for k in keys}
        s_rescue = sum((not b2[k]) and s1[k] for k in keys)
        s_regress = sum(b2[k] and not s1[k] for k in keys)
        b2_wrong, b2_right = sum(not b2[k] for k in keys), sum(b2[k] for k in keys)
        diffs = [{"diff": int(s1[k]) - int(b2[k]), "cluster": passage_of[k] if family == "reading" else k} for k in keys]
        member = set(keys)
        oracle_rows = [r for r in primary + noise if item_key_of(r) in member]
        block: dict[str, Any] = {
            "n_items": n,
            "accuracy": {"b1": b1_right / n, "b2": b2_right / n, "s1": sum(s1[k] for k in keys) / n},
            "drift": {"rescues": rescue, "regressions": regress, "net": (rescue - regress) / n,
                      "mcnemar_p": mcnemar_exact_p(regress, rescue)},
            "noise_recovery": rescue / b1_wrong if b1_wrong else None,
            "noise_recovery_ci95": wilson_interval(rescue, b1_wrong),
            "noise_regression_rate": regress / b1_right if b1_right else None,
            "noise_regression_ci95": wilson_interval(regress, b1_right),
            "agreement_rate": (both_ok + both_wrong) / n,
            "s_vs_b2": {
                "rescues": s_rescue, "regressions": s_regress,
                "recovery": s_rescue / b2_wrong if b2_wrong else None,
                "regression_rate": s_regress / b2_right if b2_right else None,
                "net_gain": (s_rescue - s_regress) / n, "mcnemar_p": mcnemar_exact_p(s_regress, s_rescue),
                "net_gain_ci95_pct": clustered_mean_interval(diffs, value_key="diff", cluster_key="cluster",
                                                             seed=plan["bootstrap_seed"], samples=plan["bootstrap_resamples"])},
            "s_vs_noise_given_b1_wrong": _conditional_contrast([k for k in keys if not b1[k]], s1, b2, wrong=False),
            "s_vs_noise_given_b1_right": _conditional_contrast([k for k in keys if b1[k]], s1, b2, wrong=True),
            "stable": {"both_correct": both_ok, "both_wrong": both_wrong, "unstable": regress + rescue,
                       "s_correct_on_both_wrong": sum(s1[k] for k in keys if not b1[k] and not b2[k]),
                       "s_wrong_on_both_correct": sum(not s1[k] for k in keys if b1[k] and b2[k])},
            "oracle": oracle_ceilings(oracle_rows),
            "mean_f1": None,
        }
        if family == "reading":
            f1 = {name: [float(rows[k]["token_f1"]) for k in keys] for name, rows in
                  (("b1", b1_rows), ("b2", b2_rows), ("s1", s1_rows))}
            block["mean_f1"] = {name: statistics.fmean(values) for name, values in f1.items()}
            block["mean_f1"]["mean_abs_b1_b2_change"] = statistics.fmean(abs(a - b) for a, b in zip(f1["b1"], f1["b2"], strict=True))
        by_dataset: dict[str, dict[str, Any]] = {}
        for dataset_id in sorted({k.split(":")[0] for k in keys}):
            subset = [k for k in keys if k.startswith(dataset_id + ":")]
            by_dataset[dataset_id] = {
                "n": len(subset), "accuracy_b1": sum(b1[k] for k in subset) / len(subset),
                "accuracy_b2": sum(b2[k] for k in subset) / len(subset),
                "accuracy_s1": sum(s1[k] for k in subset) / len(subset),
                "b1_b2_flips": sum(b1[k] != b2[k] for k in subset)}
        block["by_dataset_descriptive"] = by_dataset
        report["families"][family] = block
    conditional = ("s_vs_noise_given_b1_wrong", "s_vs_noise_given_b1_right")
    adjusted = holm_adjust({f"{family}:{name}": block[name]["mcnemar_p"]
                            for family, block in report["families"].items() for name in conditional})
    for family, block in report["families"].items():  # Holm over the conditional contrasts (families x conditions)
        for name in conditional:
            block[name]["mcnemar_p_holm"] = adjusted[f"{family}:{name}"]
    return report


def format_noise_report(report: dict[str, Any]) -> str:
    def pct(x):
        return "-" if x is None else f"{100 * x:.1f}%"

    def span(c):  # Wilson intervals are already in percent, as in the primary report
        return "-" if not c else f"[{c[0]:.1f}, {c[1]:.1f}]"

    parity = report["parity_gate_b2"]
    lines = [f"B replicate {report['noise_replicate']} over {report['items_shared']} items "
             f"(missing in the noise run: {report['items_missing_in_noise_run']})",
             f"parity gate of the second B draw vs MC-83: "
             f"{'PASS' if parity['all_within'] else 'FAIL - the drift check below decides how to read this run'}"]
    for dataset_id, v in parity["datasets"].items():
        if v:
            lines.append(f"  {dataset_id.split('-v1-')[-1]:<14}{v['metric']:<9}{v['observed']:>7.2f}  ref {v['reference']:.2f} "
                         f"[{v['reference_ci95'][0]:.2f}, {v['reference_ci95'][1]:.2f}] {'ok' if v['within_reference_ci'] else 'OUT'}")
    for family, b in report["families"].items():
        acc, drift, sb2 = b["accuracy"], b["drift"], b["s_vs_b2"]
        lines += [
            f"[{family}] items={b['n_items']}  accuracy B1 {pct(acc['b1'])}  B2 {pct(acc['b2'])}  S1 {pct(acc['s1'])}",
            f"  drift B1->B2: rescues {drift['rescues']} regressions {drift['regressions']} net {pct(drift['net'])} "
            f"p={drift['mcnemar_p']:.3f} | agreement {pct(b['agreement_rate'])}",
            f"  B-vs-B noise: recovery {pct(b['noise_recovery'])} {span(b['noise_recovery_ci95'])}  "
            f"regression {pct(b['noise_regression_rate'])} {span(b['noise_regression_ci95'])}",
            f"  S1 vs B2 (independent baseline draw): rescues {sb2['rescues']} regressions {sb2['regressions']} "
            f"net {pct(sb2['net_gain'])} CI95 pts [{sb2['net_gain_ci95_pct'][0]:.1f}, {sb2['net_gain_ci95_pct'][1]:.1f}] "
            f"p={sb2['mcnemar_p']:.3f}"]
        for label, key in (("B1 wrong", "s_vs_noise_given_b1_wrong"), ("B1 right", "s_vs_noise_given_b1_right")):
            c = b[key]
            what = "S correct" if key.endswith("wrong") else "S wrong"
            lines.append(f"  given {label} (n={c['n']}): {what} {c['s_count']} vs second B draw {c['b2_count']} "
                         f"diff {pct(c['difference'])} p={c['mcnemar_p']:.3f} (Holm {c['mcnemar_p_holm']:.3f})")
        st, orc = b["stable"], b["oracle"]
        lines.append(f"  stable: both correct {st['both_correct']}, both wrong {st['both_wrong']}, unstable {st['unstable']}; "
                     f"S correct on both-wrong {st['s_correct_on_both_wrong']}, S wrong on both-correct {st['s_wrong_on_both_correct']}")
        lines.append(f"  oracle B/S {pct(orc['observed'])} vs B/B null {pct(orc['null_from_baseline_replicates'])} "
                     f"headroom {pct(orc['headroom_over_null'])}")
        if b["mean_f1"]:
            f = b["mean_f1"]
            lines.append(f"  mean token-F1 B1 {100 * f['b1']:.1f} B2 {100 * f['b2']:.1f} S1 {100 * f['s1']:.1f}; "
                         f"mean |B1-B2| {100 * f['mean_abs_b1_b2_change']:.1f} pts")
    return "\n".join(lines)


# ---------------------------------------------------------------- S replicate supplement (MC-92)

S_NOISE_FAMILY_KEYS = ("n_items", "accuracy", "s_drift", "s_noise_recovery", "s_noise_recovery_ci95",
                       "s_noise_regression_rate", "s_noise_regression_ci95", "s_agreement_rate", "flip_comparison",
                       "stable_wins", "two_draw_effect", "s2_vs_b", "oracle", "mean_f1", "by_dataset_descriptive")
S_NOISE_TOP_KEYS = ("plan_id", "s_replicate", "items_shared", "items_missing", "families", "s2_format")


def _paired_draws(arm_draw: dict[str, bool], base_draw: dict[str, bool], keys: list[str]) -> dict[str, Any]:
    """Rescues (base wrong, arm right) and regressions (base right, arm wrong) of one draw against another."""
    rescues = sum((not base_draw[k]) and arm_draw[k] for k in keys)
    regressions = sum(base_draw[k] and not arm_draw[k] for k in keys)
    return {"rescues": rescues, "regressions": regressions, "net_gain": (rescues - regressions) / len(keys),
            "mcnemar_p": mcnemar_exact_p(regressions, rescues)}


def s_noise_reference(primary_rows: Iterable[dict[str, Any]], b_noise_rows: Iterable[dict[str, Any]],
                      s_noise_rows: Iterable[dict[str, Any]], *, protocol: dict[str, Any] | None = None,
                      s_replicate: int = 2) -> dict[str, Any]:
    """Supplement MC-92: the second S draw of every wide item read with the first draws of B and S (MC-90) and the
    second draw of B (MC-91). It never repeats or replaces the registered analyses of MC-90 and MC-91."""
    protocol = protocol or dp.load_protocol()
    plan = protocol["analysis"]
    primary, b_noise = list(primary_rows), list(b_noise_rows)
    s2_list = [r for r in s_noise_rows if arm_of(r) == "S"]
    if any(replicate_number(r) != s_replicate for r in s2_list):
        raise ValueError(f"S noise rows must all be replicate {s_replicate} of arm S")

    def draws(rows: list[dict[str, Any]], arm: str, replicate: int) -> dict[str, dict[str, Any]]:
        return {item_key_of(r): r for r in rows if arm_of(r) == arm and replicate_number(r) == replicate}

    b1_rows, s1_rows = draws(primary, BASELINE, 1), draws(primary, "S", 1)
    b2_rows, s2_rows = draws(b_noise, BASELINE, 2), {item_key_of(r): r for r in s2_list}
    base = set(b1_rows) & set(s1_rows) & set(b2_rows)
    shared = sorted(base & set(s2_rows))
    b1, b2, s1, s2 = ({k: attempt_correct(rows[k]) for k in shared} for rows in (b1_rows, b2_rows, s1_rows, s2_rows))
    cap = protocol["transport"]["max_output_tokens"]
    report: dict[str, Any] = {
        "plan_id": plan["plan_id"], "s_replicate": s_replicate, "items_shared": len(shared),
        "items_missing": len(base - set(s2_rows)), "families": {},
        "s2_format": {"n": len(s2_list), "format_ok": sum(bool(r.get("format_ok")) for r in s2_list),
                      "cut_at_cap": sum(r.get("completion_tokens") == cap for r in s2_list)}}
    for family in FAMILIES:
        keys = [k for k in shared if family_of(b1_rows[k]) == family]
        if not keys:
            continue
        n = len(keys)
        s_both = sum(s1[k] and s2[k] for k in keys)
        s_regress = sum(s1[k] and not s2[k] for k in keys)
        s_rescue = sum((not s1[k]) and s2[k] for k in keys)
        s_neither = n - s_both - s_regress - s_rescue
        s1_wrong, s1_right = s_rescue + s_neither, s_both + s_regress
        flips_b = {k for k in keys if b1[k] != b2[k]}
        flips_s = {k for k in keys if s1[k] != s2[k]}
        b_only, s_only = len(flips_b - flips_s), len(flips_s - flips_b)
        s_stable = sum(s1[k] and s2[k] and not b1[k] and not b2[k] for k in keys)
        b_stable = sum(b1[k] and b2[k] and not s1[k] and not s2[k] for k in keys)
        passage_of = {k: str(b1_rows[k].get("passage_id") or k) for k in keys}
        diffs = [{"diff": (int(s1[k]) + int(s2[k]) - int(b1[k]) - int(b2[k])) / 2,
                  "cluster": passage_of[k] if family == "reading" else k} for k in keys]

        observed = sum(b1[k] or s1[k] for k in keys) / n
        null_b, null_s = sum(b1[k] or b2[k] for k in keys) / n, sum(s1[k] or s2[k] for k in keys) / n
        block: dict[str, Any] = {
            "n_items": n,
            "accuracy": {name: sum(draw[k] for k in keys) / n for name, draw in (("b1", b1), ("b2", b2), ("s1", s1), ("s2", s2))},
            "s_drift": {"rescues": s_rescue, "regressions": s_regress, "net": (s_rescue - s_regress) / n,
                        "mcnemar_p": mcnemar_exact_p(s_regress, s_rescue)},
            "s_noise_recovery": s_rescue / s1_wrong if s1_wrong else None,
            "s_noise_recovery_ci95": wilson_interval(s_rescue, s1_wrong),
            "s_noise_regression_rate": s_regress / s1_right if s1_right else None,
            "s_noise_regression_ci95": wilson_interval(s_regress, s1_right),
            "s_agreement_rate": (s_both + s_neither) / n,
            "flip_comparison": {"b_flips": len(flips_b), "s_flips": len(flips_s), "b_flip_rate": len(flips_b) / n,
                                "s_flip_rate": len(flips_s) / n, "b_only": b_only, "s_only": s_only,
                                "mcnemar_p": mcnemar_exact_p(b_only, s_only)},
            "stable_wins": {"s_stable_better": s_stable, "b_stable_better": b_stable,
                            "sign_test_p": mcnemar_exact_p(b_stable, s_stable)},
            "two_draw_effect": {
                "mean_diff": statistics.fmean(d["diff"] for d in diffs),
                "ci95_pct": clustered_mean_interval(diffs, value_key="diff", cluster_key="cluster",
                                                    seed=plan["bootstrap_seed"], samples=plan["bootstrap_resamples"])},
            "s2_vs_b": {"vs_b1": _paired_draws(s2, b1, keys), "vs_b2": _paired_draws(s2, b2, keys)},
            "oracle": {"b_s_first_draws": observed, "null_b": null_b, "null_s": null_s,
                       "headroom_over_null_b": observed - null_b, "headroom_over_null_s": observed - null_s},
            "mean_f1": None,
        }
        if family == "reading":
            f1 = {name: [float(rows[k]["token_f1"]) for k in keys] for name, rows in
                  (("b1", b1_rows), ("b2", b2_rows), ("s1", s1_rows), ("s2", s2_rows))}
            block["mean_f1"] = {name: statistics.fmean(values) for name, values in f1.items()}
            block["mean_f1"]["mean_abs_b1_b2_change"] = statistics.fmean(abs(a - b) for a, b in zip(f1["b1"], f1["b2"], strict=True))
            block["mean_f1"]["mean_abs_s1_s2_change"] = statistics.fmean(abs(a - b) for a, b in zip(f1["s1"], f1["s2"], strict=True))
        by_dataset: dict[str, dict[str, Any]] = {}
        for dataset_id in sorted({k.split(":")[0] for k in keys}):
            subset = [k for k in keys if k.startswith(dataset_id + ":")]
            by_dataset[dataset_id] = {
                "n": len(subset), **{f"accuracy_{name}": sum(draw[k] for k in subset) / len(subset)
                                     for name, draw in (("b1", b1), ("b2", b2), ("s1", s1), ("s2", s2))},
                "b_flips": sum(b1[k] != b2[k] for k in subset), "s_flips": sum(s1[k] != s2[k] for k in subset)}
        block["by_dataset_descriptive"] = by_dataset
        report["families"][family] = block
    adjusted = holm_adjust({f"{family}:{name}": block[name][key]  # Holm over the four primary tests of the card
                            for family, block in report["families"].items()
                            for name, key in (("flip_comparison", "mcnemar_p"), ("stable_wins", "sign_test_p"))})
    for family, block in report["families"].items():
        block["flip_comparison"]["mcnemar_p_holm"] = adjusted[f"{family}:flip_comparison"]
        block["stable_wins"]["sign_test_p_holm"] = adjusted[f"{family}:stable_wins"]
    return report


def format_s_noise_report(report: dict[str, Any]) -> str:
    def pct(x):
        return "-" if x is None else f"{100 * x:.1f}%"

    def span(c):  # Wilson intervals are already in percent
        return "-" if not c else f"[{c[0]:.1f}, {c[1]:.1f}]"

    fmt = report["s2_format"]
    ok_pct = 100 * fmt["format_ok"] / fmt["n"] if fmt["n"] else float("nan")
    lines = [f"S replicate {report['s_replicate']} over {report['items_shared']} items (missing: {report['items_missing']}); "
             f"final-answer label {fmt['format_ok']}/{fmt['n']} ({ok_pct:.1f}%), cut at the token cap {fmt['cut_at_cap']}"]
    for family, b in report["families"].items():
        acc, drift, flips, wins = b["accuracy"], b["s_drift"], b["flip_comparison"], b["stable_wins"]
        eff, vs1, vs2, orc = b["two_draw_effect"], b["s2_vs_b"]["vs_b1"], b["s2_vs_b"]["vs_b2"], b["oracle"]
        lines += [
            f"[{family}] items={b['n_items']}  accuracy B1 {pct(acc['b1'])}  B2 {pct(acc['b2'])}  S1 {pct(acc['s1'])}  S2 {pct(acc['s2'])}",
            f"  S drift S1->S2: rescues {drift['rescues']} regressions {drift['regressions']} net {pct(drift['net'])} "
            f"p={drift['mcnemar_p']:.3f} | agreement {pct(b['s_agreement_rate'])}",
            f"  S-vs-S noise: recovery {pct(b['s_noise_recovery'])} {span(b['s_noise_recovery_ci95'])}  "
            f"regression {pct(b['s_noise_regression_rate'])} {span(b['s_noise_regression_ci95'])}",
            f"  instability (items that change between two draws): B {flips['b_flips']} ({pct(flips['b_flip_rate'])}), "
            f"S {flips['s_flips']} ({pct(flips['s_flip_rate'])}); B only {flips['b_only']}, S only {flips['s_only']}; "
            f"p={flips['mcnemar_p']:.3f} (Holm {flips['mcnemar_p_holm']:.3f})",
            f"  stable wins (better in both draws): S {wins['s_stable_better']}, B {wins['b_stable_better']}; "
            f"p={wins['sign_test_p']:.3f} (Holm {wins['sign_test_p_holm']:.3f})",
            f"  two-draw effect S - B: {100 * eff['mean_diff']:+.2f} pts CI95 [{eff['ci95_pct'][0]:+.2f}, {eff['ci95_pct'][1]:+.2f}]",
            f"  S2 vs B1: rescues {vs1['rescues']} regressions {vs1['regressions']} net {pct(vs1['net_gain'])} p={vs1['mcnemar_p']:.3f}; "
            f"S2 vs B2: rescues {vs2['rescues']} regressions {vs2['regressions']} net {pct(vs2['net_gain'])} p={vs2['mcnemar_p']:.3f}",
            f"  oracle B1/S1 {pct(orc['b_s_first_draws'])} vs B/B null {pct(orc['null_b'])} (headroom {pct(orc['headroom_over_null_b'])}) "
            f"and S/S null {pct(orc['null_s'])} (headroom {pct(orc['headroom_over_null_s'])})"]
        if b["mean_f1"]:
            f = b["mean_f1"]
            lines.append(f"  mean token-F1 B1 {100 * f['b1']:.1f} B2 {100 * f['b2']:.1f} S1 {100 * f['s1']:.1f} S2 {100 * f['s2']:.1f}; "
                         f"mean |B1-B2| {100 * f['mean_abs_b1_b2_change']:.1f} pts, mean |S1-S2| {100 * f['mean_abs_s1_s2_change']:.1f} pts")
    return "\n".join(lines)


# ---------------------------------------------------------------- recovery by diagnostic hypothesis (core, Decision 12)

HYPOTHESIS_PLAN_ID = "diagnostic-prospective-recovery-by-hypothesis-v1"
HYPOTHESIS_REPORT_KEYS = ("plan_id", "anchor_diagnosis_sha256", "descriptive", "audited_answers", "groups",
                          "contrast_candidates", "not_reproduced")
# Matched contrasts the core arms provide for a recorded hypothesis: (arm, its baseline, required input sufficiency).
MATCHED_CONTRASTS = {"reasoning_gap": ("S", "B", "sufficient"),
                     "reading_representation_gap": ("S", "B", "sufficient"),
                     "external_evidence_gap": ("O", "B", "insufficient")}


def _candidate(key: str, record: dict[str, Any], label: str, contrast: str) -> dict[str, Any]:
    return {"item_key": key, "label": label, "contrast": contrast,
            "hypothesis_recorded": label in record["diagnostic_labels"],
            "status": record["hypothesis_status"].get(label)}


def recovery_by_hypothesis(rows: Iterable[dict[str, Any]], diagnosis: dict[str, dict[str, Any]],
                           diagnosis_sha256: str) -> dict[str, Any]:
    """Descriptive recovery per adjudicated hypothesis on core, plus contrast candidates for a reviewer. The audit
    judged the historical B answer, so an issue anchor whose new B majority is correct is reported as not
    reproduced. Nothing here changes a hypothesis status: a candidate becomes contrast_supported only through the
    audit's contrast records."""
    groups = group_attempts(rows)
    outcomes = {pair: item_outcome(attempts)[0] for pair, attempts in groups.items()}
    missing = sorted(key for key in diagnosis if (BASELINE, key) not in outcomes)
    if missing:
        raise SystemExit(f"Error: no B attempt for anchors {missing[:3]} ({len(missing)} in all)")
    arms = [arm for arm in dp.ARMS if arm != BASELINE and any(a == arm for (a, _) in outcomes)]
    members: dict[str, list[str]] = defaultdict(list)
    for key, record in diagnosis.items():
        if record["diagnostic_outcome"] != "issue_observed":
            members[record["diagnostic_outcome"]].append(key)
        elif not record["diagnostic_labels"]:
            members["issue_without_hypothesis"].append(key)
        for label in record["diagnostic_labels"]:
            members[label].append(key)
    report_groups = {}
    for name, keys in sorted(members.items()):
        per_arm = {}
        for arm in arms:
            paired = [key for key in keys if (arm, key) in outcomes]
            if paired:
                per_arm[arm] = {"paired": len(paired),
                                "rescues": sum(not outcomes[(BASELINE, k)] and outcomes[(arm, k)] for k in paired),
                                "regressions": sum(outcomes[(BASELINE, k)] and not outcomes[(arm, k)] for k in paired)}
        report_groups[name] = {
            "anchors": len(keys), "b_majority_incorrect": sum(not outcomes[(BASELINE, k)] for k in keys),
            "not_reproduced": sum(diagnosis[k]["diagnostic_outcome"] == "issue_observed" and outcomes[(BASELINE, k)]
                                  for k in keys),
            "arms": per_arm,
            "no_arm_correct": sum(not any(outcomes.get((arm, k), False) for arm in (BASELINE, *arms)) for k in keys),
            "items": sorted(keys)}
    candidates = []
    for key, record in sorted(diagnosis.items()):
        if record["diagnostic_outcome"] != "issue_observed":
            continue
        for label in record["diagnostic_labels"]:
            if label not in MATCHED_CONTRASTS:
                continue
            arm, base, sufficiency = MATCHED_CONTRASTS[label]
            if (record["input_evidence_sufficiency"] == sufficiency and (arm, key) in outcomes
                    and outcomes[(arm, key)] and not outcomes[(base, key)]):
                candidates.append(_candidate(key, record, label, f"{arm} correct where {base} is incorrect"))
        if outcomes.get(("O", key)) and outcomes.get(("K", key)) is False:
            candidates.append(_candidate(key, record, "retrieval_gap", "K incorrect where O is correct"))
        if len({attempt_correct(a) for a in groups[(BASELINE, key)]}) > 1:
            candidates.append(_candidate(key, record, "run_instability", "B replicates disagree"))
    return {"plan_id": HYPOTHESIS_PLAN_ID, "anchor_diagnosis_sha256": diagnosis_sha256, "descriptive": True,
            "audited_answers": "historical MC-72 B outputs; the groups set them against the new core arms",
            "groups": report_groups, "contrast_candidates": candidates,
            "not_reproduced": sorted(key for key, record in diagnosis.items()
                                     if record["diagnostic_outcome"] == "issue_observed" and outcomes[(BASELINE, key)])}


def format_report(report: dict[str, Any]) -> str:
    def pct(x):
        return "-" if x is None else f"{100 * x:.1f}%"

    lines = [f"phase={report['phase']} plan={report['plan_id']} item_ties={report['item_ties']}"]
    parity = report.get("parity_gate")
    if parity:
        lines.append(f"parity gate vs MC-83 (B per dataset inside the reference interval): "
                     f"{'PASS' if parity['all_within'] else 'FAIL - check the infrastructure before reading any effect'}")
        for dataset_id, v in parity["datasets"].items():
            if v:
                lines.append(f"  {dataset_id.split('-v1-')[-1]:<14}{v['metric']:<9}{v['observed']:>7.2f}  ref {v['reference']:.2f} "
                             f"[{v['reference_ci95'][0]:.2f}, {v['reference_ci95'][1]:.2f}] {'ok' if v['within_reference_ci'] else 'OUT'}")
    for family, block in report["families"].items():
        lines.append(f"[{family}] items={block['item_count']}  (per-dataset numbers are descriptive only)")
        lines.append(f"  {'arm':<4}{'pairs':>6}{'rescue':>7}{'regress':>8}{'recovery':>10}{'regr.rate':>10}"
                     f"{'net gain':>10}{'p':>8}{'p_holm':>8}")
        noise = report["baseline_noise"].get(family)
        for arm, v in block["arms"].items():
            lines.append(f"  {arm:<4}{v['n_pairs']:>6}{v['rescues']:>7}{v['regressions']:>8}{pct(v['recovery']):>10}"
                         f"{pct(v['regression_rate']):>10}{pct(v['net_gain']):>10}{v['mcnemar_p']:>8.3f}"
                         f"{v['mcnemar_p_holm']:>8.3f}")
            level = v["attempt_level"]
            if level and noise:
                lines.append(f"      attempt level: recovery {pct(level['recovery'])} vs B-vs-B noise {pct(noise['recovery'])}; "
                             f"regression {pct(level['regression_rate'])} vs {pct(noise['regression_rate'])}")
            elif level:
                lines.append(f"      attempt level: recovery {pct(level['recovery'])}, regression {pct(level['regression_rate'])} "
                             f"(no B replicates: no noise reference)")
            sens = v["sensitivity_format_compliant"]
            if sens:
                lines.append(f"      secondary, compliant-only: rescues {sens['rescues']} regressions {sens['regressions']} "
                             f"(items excluded {sens['items_excluded']})")
            if v["mean_f1_diff"] is not None:
                lines.append(f"      secondary, mean token-F1 difference {100 * v['mean_f1_diff']:+.1f} pts, "
                             f"rescues that look like format effects: {v['rescues_format_suspect']}")
    oracle = report["oracle_routing"]
    lines.append(f"oracle routing: observed={oracle['observed']} null_from_B_replicates={oracle['null_from_baseline_replicates']} "
                 f"headroom={oracle['headroom_over_null']} ({oracle['note']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scores", type=Path, required=True, help="scores.jsonl written by run_diagnostic_prospective")
    parser.add_argument("--phase", choices=dp.PHASES, required=True)
    parser.add_argument("--out", type=Path, help="write the full report as JSON")
    parser.add_argument("--discordant-out", type=Path, help="write discordant pairs (both directions) as JSONL")
    parser.add_argument("--noise-scores", type=Path,
                        help="scores.jsonl of the B-replicate supplement (MC-91): adds the sampling-noise reference")
    parser.add_argument("--noise-out", type=Path, help="write the noise-reference report as JSON")
    parser.add_argument("--s-noise-scores", type=Path,
                        help="scores.jsonl of the S-replicate supplement (MC-92); needs --noise-scores (the second B draw)")
    parser.add_argument("--s-noise-out", type=Path, help="write the S-replicate report as JSON")
    parser.add_argument("--diagnosis", type=Path,
                        help="core: anchor_diagnosis_v1.jsonl; adds the recovery-by-hypothesis analysis")
    parser.add_argument("--diagnosis-out", type=Path, help="write the recovery-by-hypothesis report as JSON")
    args = parser.parse_args(argv)
    if args.noise_scores and args.phase != "wide":
        parser.error("--noise-scores applies to the wide phase (supplement wide-b-r2)")
    if args.s_noise_scores and not (args.noise_scores and args.phase == "wide"):
        parser.error("--s-noise-scores applies to the wide phase and needs --noise-scores")
    if args.diagnosis and args.phase != "core":
        parser.error("--diagnosis applies to the core phase (the audit anchors)")
    rows = [json.loads(line) for line in args.scores.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = analyze(rows, phase=args.phase)
    print(format_report(report))
    if args.noise_scores:
        noise_rows = [json.loads(line) for line in args.noise_scores.read_text(encoding="utf-8").splitlines() if line.strip()]
        noise = noise_reference(rows, noise_rows)
        print("\n" + format_noise_report(noise))
        if args.noise_out:
            args.noise_out.write_text(json.dumps(noise, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.s_noise_scores:
            s_rows = [json.loads(line) for line in args.s_noise_scores.read_text(encoding="utf-8").splitlines() if line.strip()]
            s_noise = s_noise_reference(rows, noise_rows, s_rows)
            print("\n" + format_s_noise_report(s_noise))
            if args.s_noise_out:
                args.s_noise_out.write_text(json.dumps(s_noise, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.diagnosis:
        diagnosis, digest = dp.load_anchor_diagnosis(args.diagnosis)
        by_hypothesis = recovery_by_hypothesis(rows, diagnosis, digest)
        for name, group in by_hypothesis["groups"].items():
            arms = ", ".join(f"{arm} +{v['rescues']}/-{v['regressions']}" for arm, v in group["arms"].items())
            print(f"{name}: {group['anchors']} anchors, B incorrect {group['b_majority_incorrect']}, "
                  f"not reproduced {group['not_reproduced']}, no arm correct {group['no_arm_correct']}; {arms}")
        print(f"contrast candidates for a reviewer: {len(by_hypothesis['contrast_candidates'])}")
        if args.diagnosis_out:
            args.diagnosis_out.write_text(json.dumps(by_hypothesis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.discordant_out:
        pairs = [pair for arm in sorted({arm_of(r) for r in rows} - {BASELINE}) for pair in discordant_pairs(rows, arm)]
        args.discordant_out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs), encoding="utf-8")
        print(f"discordant pairs exported: {len(pairs)} -> {args.discordant_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
