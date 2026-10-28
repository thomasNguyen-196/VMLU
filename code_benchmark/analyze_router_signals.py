"""Analysis of the router signals (openspec change diagnostic-router-signals, plan `diagnostic-router-signals-v1`;
card MC-99). Fixed before any Jev request on a benchmark item. Descriptive: every item is design data.

Reading (the 967 wide reading items, token-F1, arms B, Q and S with two draws each):

* the ceiling block: how much of each item's benefit repeats between draws, and what an ideal router could gain;
* pre-hoc policies, each choosing on one draw and scored on the other, both ways, averaged:
  P1 the best fixed arm per dataset (the baseline), P2 keyword groups, P3 Muse groups (MC-98, ViBidLQA),
  P4 Jev groups, P5 Jev groups gated by confidence, P6 a ridge rule on Jev's probabilities (B or S);
* post-hoc policies, deciding from the answer B actually gave on a draw and scored on that draw:
  P7 agreement of the two B answers, P8 Jev's answer check at 0.5, P9 the check with a threshold chosen on the
  other draw, P10 a combined check;
* Jev's own spread and agreement with Muse and the keywords, and how well the answer check tracks B's token-F1.

VMLU (J3, the 660 items of MC-94 and MC-95, accuracy, B and S with two draws each, and the temperature-0 answer and
first-token confidence of MC-43/44): M1 always-B at temperature 0, M2 always-S (the baseline), M3 agreement of the
two B answers, M4 the logprob cascade with a cross-fitted threshold.

Reading rule: a policy is promising when its pooled score beats the baseline by at least 1.0 point, or stays within
0.5 points of it at no more than 60% of its student-model tokens.

Usage (repo root):
  .venv/bin/python -m code_benchmark.analyze_router_signals --run-dir all_res/diagnostic_router_signals/jev/jev-1.13-free
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist
from typing import Any, Callable

import numpy as np

try:
    from code_benchmark import analyze_menu_q as am
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_llm_router as llm_router
    from code_benchmark import diagnostic_menu as menu
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_router as rule_router
    from code_benchmark import diagnostic_router_signals as sig
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_menu_q as am
    import analyze_router_labels as arl
    import diagnostic_llm_router as llm_router
    import diagnostic_menu as menu
    import diagnostic_prospective as dp
    import diagnostic_router as rule_router
    import diagnostic_router_signals as sig
    import vi_multimodel as v1

PLAN_ID = "diagnostic-router-signals-v1"
ROOT = sig.ROOT
MENU_RUN_DIR = ROOT / "all_res" / "diagnostic_llm_router" / "menu" / "qwen3-5-9b-65k-prospective"
MUSE_LABELS = ROOT / "all_res" / "diagnostic_llm_router" / "labels" / "muse-spark-1-3-contributor" / "labels.jsonl"
VMLU_SOURCES = {
    "MC-94": ROOT / "all_res" / "diagnostic_router_v2" / "heldout" / "qwen3-5-9b-65k-prospective" / "scores.jsonl",
    "MC-95": ROOT / "all_res" / "diagnostic_router_v3" / "heldout" / "qwen3-5-9b-65k-prospective" / "scores.jsonl",
}
CALIBRATION = (ROOT / "all_res" / "ollama_result" / "Qwen3_5-9B-65K"
               / "mc_calibration_items_vmlu_mqa_all_gold_Qwen3_5-9B-65K-cal.csv")
K2_SCORES = ROOT / "all_res" / "diagnostic_k2" / "heldout" / "qwen3-5-9b-65k-prospective" / "scores.jsonl"
READING_ARMS = ("B", "Q", "S")  # least to most thorough; ties go to the more thorough arm
DRAWS = ("1", "2")
OTHER = {"1": "2", "2": "1"}
QUALITY_POINTS, COST_SLACK_POINTS, COST_SHARE = 1.0, 0.5, 0.6
GATE_CONFIDENCE, CHECK_THRESHOLD, COMBINED_THRESHOLD = 0.5, 0.5, 0.5
TAU_GRID = [round(0.05 * step, 2) for step in range(1, 20)]          # 0.05 .. 0.95
LOGPROB_GRID = [round(0.50 + 0.01 * step, 2) for step in range(50)]  # 0.50 .. 0.99
RIDGE_LAMBDA, FOLDS, MIN_GROUP = 1.0, 5, 20

Policy = dict[str, list[Any]]  # {"scores": [...], "tokens": [...], "escalated": [... or None]}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def _tokens(row: dict[str, Any]) -> int:
    value = dp.reported_tokens(row)
    if value is None:
        raise _fail(f"no reported usage for {row.get('dataset_id')}:{row.get('item_id')}:{row.get('replicate_id')}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read {path}: {exc}") from exc


# ---------------------------------------------------------------- shared policy machinery

def best_arm(means: dict[str, float], arms: tuple[str, ...]) -> str:
    """The arm with the highest mean; ties within 1e-12 go to the more thorough (later) arm."""
    top = max(means.values())
    return [arm for arm in arms if top - means[arm] <= 1e-12][-1]


def score_of(item: dict[str, Any], arm: str, draw: str) -> float:
    return item["score"][f"{arm}{draw}"]


def tokens_of(item: dict[str, Any], arm: str, draw: str) -> int:
    return item["tokens"][f"{arm}{draw}"]


def fixed_arm(items: list[dict[str, Any]], draw: str, arms: tuple[str, ...]) -> str:
    return best_arm({arm: statistics.fmean(score_of(item, arm, draw) for item in items) for arm in arms}, arms)


def _cross(items: list[dict[str, Any]], choose: Callable[[str], list[str]]) -> Policy:
    """Per item, the arm chosen with the fitting draw scored on the other draw, averaged over both directions.
    `choose(fit_draw)` returns one arm per item, decided from the fitting draw only."""
    picks = {draw: choose(draw) for draw in DRAWS}
    scores = [statistics.fmean(score_of(item, picks[d][i], OTHER[d]) for d in DRAWS) for i, item in enumerate(items)]
    tokens = [statistics.fmean(tokens_of(item, picks[d][i], OTHER[d]) for d in DRAWS) for i, item in enumerate(items)]
    return {"scores": scores, "tokens": tokens, "escalated": [None] * len(items)}


def per_dataset_fixed(items: list[dict[str, Any]], arms: tuple[str, ...]) -> Policy:
    by_dataset: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        by_dataset[item["dataset"]].append(index)

    def choose(draw: str) -> list[str]:
        picks = [""] * len(items)
        for indices in by_dataset.values():
            arm = fixed_arm([items[i] for i in indices], draw, arms)
            for i in indices:
                picks[i] = arm
        return picks
    return _cross(items, choose)


def grouped(items: list[dict[str, Any]], labels: list[str | None], arms: tuple[str, ...]) -> Policy:
    """Groups mapped to arms within each dataset on the fitting draw; groups under MIN_GROUP items and unlabelled
    items take the dataset's fixed arm of that draw."""
    by_dataset: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        by_dataset[item["dataset"]].append(index)

    def choose(draw: str) -> list[str]:
        picks = [""] * len(items)
        for indices in by_dataset.values():
            fallback = fixed_arm([items[i] for i in indices], draw, arms)
            members: dict[str | None, list[int]] = defaultdict(list)
            for i in indices:
                members[labels[i]].append(i)
            for label, group in members.items():
                arm = fallback if label is None or len(group) < MIN_GROUP else fixed_arm([items[i] for i in group],
                                                                                        draw, arms)
                for i in group:
                    picks[i] = arm
        return picks
    return _cross(items, choose)


def fold_of(passage_id: str) -> int:
    return int(v1.sha256_bytes(str(passage_id).encode("utf-8")), 16) % FOLDS


def ridge_fit(x: np.ndarray, y: np.ndarray, lam: float = RIDGE_LAMBDA) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Ridge on features standardised with the training data; the intercept is the mean target, unpenalised."""
    mean, std = x.mean(axis=0), x.std(axis=0)
    std[std == 0] = 1.0
    z = (x - mean) / std
    weights = np.linalg.solve(z.T @ z + lam * np.eye(z.shape[1]), z.T @ (y - y.mean()))
    return weights, mean, std, float(y.mean())


def ridge_rule(items: list[dict[str, Any]], features: np.ndarray) -> Policy:
    """B or S per item from a ridge prediction of S - B, fitted on the other folds (grouped by passage) on the
    fitting draw and scored on the other draw."""
    folds = np.array([fold_of(item["passage_id"]) for item in items])

    def choose(draw: str) -> list[str]:
        target = np.array([score_of(item, "S", draw) - score_of(item, "B", draw) for item in items])
        picks = [""] * len(items)
        for fold in range(FOLDS):
            train, test = folds != fold, folds == fold
            if not test.any():
                continue
            weights, mean, std, intercept = ridge_fit(features[train], target[train])
            predicted = ((features[test] - mean) / std) @ weights + intercept
            for i, value in zip(np.flatnonzero(test), predicted, strict=True):
                picks[i] = "S" if value > 0 else "B"
        return picks
    return _cross(items, choose)


def cascade(items: list[dict[str, Any]], accept: Callable[[dict[str, Any], str], bool],
            extra_tokens: Callable[[dict[str, Any], str], int] | None = None) -> Policy:
    """Post-hoc: per draw, keep B's answer when `accept` says so, else S on the same draw; averaged over draws.
    The cost is B, plus S when escalated, plus any extra student-model calls the decision needed."""
    scores, tokens, escalated = [], [], []
    for item in items:
        per_draw = []
        for draw in DRAWS:
            keep = accept(item, draw)
            extra = extra_tokens(item, draw) if extra_tokens else 0
            cost = tokens_of(item, "B", draw) + extra + (0 if keep else tokens_of(item, "S", draw))
            per_draw.append((score_of(item, "B" if keep else "S", draw), cost, not keep))
        scores.append(statistics.fmean(value for value, _, _ in per_draw))
        tokens.append(statistics.fmean(cost for _, cost, _ in per_draw))
        escalated.append(statistics.fmean(flag for _, _, flag in per_draw))
    return {"scores": scores, "tokens": tokens, "escalated": escalated}


def crossfit_threshold(items: list[dict[str, Any]], probability: Callable[[dict[str, Any], str], float],
                       grid: list[float], accepted_score: Callable[[dict[str, Any], str], float] | None = None
                       ) -> tuple[Policy, dict[str, float]]:
    """Accept B when probability >= tau, with tau chosen on the other draw (ties to the lower tau, which escalates
    less). `accepted_score` overrides the score of an accepted item (J3 keeps the temperature-0 answer)."""
    def kept_score(item: dict[str, Any], draw: str) -> float:
        return accepted_score(item, draw) if accepted_score else score_of(item, "B", draw)

    def mean_on(draw: str, tau: float) -> float:
        return statistics.fmean(kept_score(item, draw) if probability(item, draw) >= tau else score_of(item, "S", draw)
                                for item in items)
    chosen = {}
    for draw in DRAWS:
        fit = OTHER[draw]
        values = [mean_on(fit, tau) for tau in grid]
        chosen[draw] = grid[values.index(max(values))]
    scores, tokens, escalated = [], [], []
    for item in items:
        per_draw = []
        for draw in DRAWS:
            keep = probability(item, draw) >= chosen[draw]
            cost = tokens_of(item, "B", draw) + (0 if keep else tokens_of(item, "S", draw))
            per_draw.append((kept_score(item, draw) if keep else score_of(item, "S", draw), cost, not keep))
        scores.append(statistics.fmean(value for value, _, _ in per_draw))
        tokens.append(statistics.fmean(cost for _, cost, _ in per_draw))
        escalated.append(statistics.fmean(flag for _, _, flag in per_draw))
    return {"scores": scores, "tokens": tokens, "escalated": escalated}, chosen


def summary(policy: Policy) -> dict[str, Any]:
    escalated = [value for value in policy["escalated"] if value is not None]
    return {"score": _pct(statistics.fmean(policy["scores"])), "mean_student_tokens": round(statistics.fmean(policy["tokens"]), 1),
            "escalated_share": round(statistics.fmean(escalated), 4) if escalated else None}


def reading_rule(policy: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    gain = round(policy["score"] - baseline["score"], 2)
    token_share = round(policy["mean_student_tokens"] / baseline["mean_student_tokens"], 3)
    quality = gain >= QUALITY_POINTS
    cost = gain >= -COST_SLACK_POINTS and token_share <= COST_SHARE
    return {"gain_points": gain, "token_share": token_share, "quality": quality, "cost": cost,
            "promising": quality or cost}


# ---------------------------------------------------------------- ceilings

def ceiling(a1: list[float], a2: list[float], c1: list[float], c2: list[float]) -> dict[str, Any]:
    """Repeatability of the per-item benefit of arm a over arm c, and what an ideal router could gain over the
    better fixed arm (points)."""
    d1 = [100 * (x - y) for x, y in zip(a1, c1, strict=True)]
    d2 = [100 * (x - y) for x, y in zip(a2, c2, strict=True)]
    mean = statistics.fmean(d1 + d2)
    covariance = statistics.covariance(d1, d2)
    tau = max(covariance, 0.0) ** 0.5
    fixed_a = statistics.fmean(a1 + a2) >= statistics.fmean(c1 + c2)
    cross = []
    for i in range(len(d1)):
        for fit, score_a, score_c in ((d1[i], a2[i], c2[i]), (d2[i], a1[i], c1[i])):
            cross.append(score_a if fit > 0 or (fit == 0 and fixed_a) else score_c)
    fixed = max(statistics.fmean(a1 + a2), statistics.fmean(c1 + c2))
    normal = NormalDist()
    estimate = (mean * normal.cdf(mean / tau) + tau * normal.pdf(mean / tau) - max(mean, 0)) if tau else 0.0
    spread = statistics.pstdev(d1) and statistics.pstdev(d2)
    return {
        "items": len(d1), "mean_benefit_points": round(mean, 2),
        "draw_correlation": round(statistics.correlation(d1, d2), 3) if spread else None,
        "repeatable_sd_points": round(tau, 2),
        "wins_both_draws": {"a": sum(x > 0 and y > 0 for x, y in zip(d1, d2, strict=True)),
                            "c": sum(x < 0 and y < 0 for x, y in zip(d1, d2, strict=True))},
        "single_draw_router_gain_points": round(100 * statistics.fmean(cross) - 100 * fixed, 2),
        "ideal_gain_cap_points": round((mean + (mean * mean + tau * tau) ** 0.5) / 2 - max(mean, 0), 2),
        "ideal_gain_normal_points": round(estimate, 2),
    }


# ---------------------------------------------------------------- loading

def reading_items() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = menu.load_frozen_manifest()
    cells = am.load_cells(MENU_RUN_DIR, manifest)
    by_key = {dp.item_key(cell["B1"]["dataset_id"], cell["B1"]["item_id"]): cell
              for cells_in in cells.values() for cell in cells_in}
    questions = {dp.item_key(item.dataset_id, item.item_id): item for item in menu.design_items()}
    items = []
    for key, item in questions.items():
        cell = by_key[key]
        items.append({"key": key, "dataset": item.dataset_id, "item_id": item.item_id,
                      "passage_id": item.passage_id or item.item_id, "question": item.question,
                      "score": {name: float(row["token_f1"]) for name, row in cell.items()},
                      "tokens": {name: _tokens(row) for name, row in cell.items()},
                      "prediction": {name: str(row.get("prediction") or "") for name, row in cell.items()}})
    return items, {"menu_manifest_sha256": manifest["manifest_sha256"],
                   "menu_scores_sha256": v1.sha256_file(MENU_RUN_DIR / "scores.jsonl")}


def load_signals(run_dir: Path, items: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{dataset:item -> {"pre": row, "post1": row, "post2": row}}; every request must have completed."""
    rows = _read_jsonl(run_dir / "signals.jsonl")
    post_ids = {config["requests"]["post"]["replicate_ids"][draw]: f"post{draw[-1]}" for draw in sig.DRAWS}
    signals: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in rows:
        dataset, item_id, replicate = row["run_key"].rsplit(":", 2)
        slot = "pre" if replicate == config["requests"]["pre"]["replicate_id"] else post_ids[replicate]
        signals[dp.item_key(dataset, item_id)][slot] = row
    missing = [item["key"] for item in items if set(signals.get(item["key"], {})) != {"pre", "post1", "post2"}]
    if missing:
        raise _fail(f"{len(missing)} items lack a completed Jev signal, for example {missing[:3]}")
    return dict(signals)


def muse_groups() -> dict[str, str | None]:
    return {dp.item_key(row["dataset_id"], row["item_id"]): row.get("group") for row in _read_jsonl(MUSE_LABELS)}


def _flag(value: Any) -> int:
    return int(str(value).strip().lower() in {"1", "1.0", "true"})


def vmlu_items() -> list[dict[str, Any]]:
    """The VMLU items of MC-94 and MC-95 with B and S twice, plus the MC-43/44 temperature-0 answer and confidence."""
    with CALIBRATION.open(encoding="utf-8") as handle:
        calibration = {row["id"]: row for row in csv.DictReader(handle)}
    cells: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for source, path in VMLU_SOURCES.items():
        for row in _read_jsonl(path):
            if "vmlu" not in row["dataset_id"]:
                continue
            arm, _, draw = row["replicate_id"].partition("-r")
            cells[f"{source}:{row['item_id']}"][f"{arm}{draw}"] = row
    items = []
    for key, cell in cells.items():
        item_id = key.split(":", 1)[1]
        if set(cell) != {"B1", "B2", "S1", "S2"} or item_id not in calibration:
            raise _fail(f"VMLU item {key} lacks a draw or its MC-43/44 row")
        cal = calibration[item_id]
        items.append({"key": key, "dataset": "vmlu", "item_id": item_id, "passage_id": item_id,
                      "score": {name: float(row["correct"]) for name, row in cell.items()},
                      "tokens": {name: _tokens(row) for name, row in cell.items()},
                      "prediction": {name: str(row.get("prediction") or "") for name, row in cell.items()},
                      "t0_correct": _flag(cal["correct"]),
                      # a row without a letter confidence counts as 0, so the cascade always escalates it
                      "t0_confidence": float(cal["confidence"]) if cal["confidence"].strip() else 0.0,
                      "t0_confidence_missing": not cal["confidence"].strip()})
    return items


# ---------------------------------------------------------------- Jev diagnostics

def auroc(scores: list[float], positives: list[bool]) -> float | None:
    ranked = sorted(zip(scores, positives, strict=True))
    n_pos = sum(positives)
    n_neg = len(positives) - n_pos
    if not n_pos or not n_neg:
        return None
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        mid = (i + j + 1) / 2  # average 1-based rank of the tie block
        rank_sum += mid * sum(flag for _, flag in ranked[i:j])
        i = j
    return round((rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg), 4)


def jev_diagnostics(items: list[dict[str, Any]], signals: dict[str, dict[str, Any]], config: dict[str, Any],
                    keywords: list[str], muse: dict[str, str | None]) -> dict[str, Any]:
    pre_nouls = [qid for qid, q in config["requests"]["pre"]["questions"].items() if q["type"] == "noul"]
    groups = [signals[item["key"]]["pre"]["group"] for item in items]
    confidence = [float(signals[item["key"]]["pre"]["group_confidence"]) for item in items]
    viblqa = [i for i, item in enumerate(items) if item["dataset"] == llm_router.DATASET]
    muse_labels = [muse.get(items[i]["key"]) for i in viblqa]
    check = {draw: [float(signals[item["key"]][f"post{draw}"]["answer_correct"]) for item in items] for draw in DRAWS}
    b_f1 = {draw: [score_of(item, "B", draw) for item in items] for draw in DRAWS}
    return {
        "group_counts": dict(Counter(groups)),
        "group_confidence": {"mean": round(statistics.fmean(confidence), 3),
                             "share_at_least_gate": round(sum(c >= GATE_CONFIDENCE for c in confidence) / len(items), 3)},
        "pre_noul_means": {qid: round(statistics.fmean(float(signals[item["key"]]["pre"][qid]) for item in items), 3)
                           for qid in pre_nouls},
        "agreement_with_muse_viblqa": round(sum(groups[i] == m for i, m in zip(viblqa, muse_labels, strict=True))
                                            / len(viblqa), 3),
        "jev_by_muse_viblqa": dict(Counter(f"{groups[i]}|{m}" for i, m in zip(viblqa, muse_labels, strict=True))),
        "jev_by_keyword": dict(Counter(f"{g}|{k}" for g, k in zip(groups, keywords, strict=True))),
        "answer_check": {f"draw{draw}": {
            "spearman_with_b_token_f1": round(statistics.correlation(check[draw], b_f1[draw], method="ranked"), 3),
            "auroc_b_token_f1_at_least_0_5": auroc(check[draw], [value >= 0.5 for value in b_f1[draw]]),
            "mean_probability": round(statistics.fmean(check[draw]), 3)} for draw in DRAWS},
    }


# ---------------------------------------------------------------- report

def compare(policies: dict[str, Policy], baseline_name: str) -> dict[str, Any]:
    baseline = policies[baseline_name]
    base_summary = summary(baseline)
    block = {}
    for name, policy in policies.items():
        entry = summary(policy)
        if name != baseline_name:
            entry["versus_baseline"] = arl.difference_block(policy["scores"], baseline["scores"])
            entry["reading_rule"] = reading_rule(entry, base_summary)
        block[name] = entry
    return block


def reading_report(items: list[dict[str, Any]], signals: dict[str, dict[str, Any]], config: dict[str, Any]
                   ) -> dict[str, Any]:
    mc98, _ = llm_router.load_config()
    group_ids = llm_router.group_ids(mc98)
    keywords = [llm_router.keyword_group(item["question"], mc98) for item in items]
    muse = muse_groups()
    pre = [signals[item["key"]]["pre"] for item in items]
    jev = [row["group"] for row in pre]
    gated = [row["group"] if float(row["group_confidence"]) >= GATE_CONFIDENCE else None for row in pre]
    muse_or_none = [muse.get(item["key"]) if item["dataset"] == llm_router.DATASET else None for item in items]
    pre_nouls = [qid for qid, q in config["requests"]["pre"]["questions"].items() if q["type"] == "noul"]
    datasets = sorted({item["dataset"] for item in items})
    features = np.array([[float(row[qid]) for qid in pre_nouls]
                         + [float(row["group_probabilities"].get(group, 0.0)) for group in group_ids]
                         + [float(item["dataset"] == dataset) for dataset in datasets]
                         for row, item in zip(pre, items, strict=True)])

    def check(name: str) -> Callable[[dict[str, Any], str], float]:
        return lambda item, draw: float(signals[item["key"]][f"post{draw}"][name])

    def combined(item: dict[str, Any], draw: str) -> float:
        row = signals[item["key"]][f"post{draw}"]
        return float(row["answer_correct"]) * float(row["answer_complete"]) * (1 - float(row["answer_extra"]))

    agree = {item["key"]: rule_router.answers_agree(item["prediction"]["B1"], item["prediction"]["B2"], "reading")
             for item in items}
    p9, p9_tau = crossfit_threshold(items, check("answer_correct"), TAU_GRID)
    policies: dict[str, Policy] = {
        "P1_fixed_per_dataset": per_dataset_fixed(items, READING_ARMS),
        "P2_keyword_groups": grouped(items, keywords, READING_ARMS),
        "P3_muse_groups": grouped(items, muse_or_none, READING_ARMS),
        "P4_jev_groups": grouped(items, jev, READING_ARMS),
        "P5_jev_groups_gated": grouped(items, gated, READING_ARMS),
        "P6_jev_ridge_rule": ridge_rule(items, features),
        "P7_b_agreement": cascade(items, lambda item, draw: agree[item["key"]],
                                  lambda item, draw: tokens_of(item, "B", OTHER[draw])),
        "P8_jev_check": cascade(items, lambda item, draw: check("answer_correct")(item, draw) >= CHECK_THRESHOLD),
        "P9_jev_check_crossfit": p9,
        "P10_jev_combined_check": cascade(items, lambda item, draw: combined(item, draw) >= COMBINED_THRESHOLD),
    }
    references = {
        "same_draw_oracle_B_S": _pct(statistics.fmean(statistics.fmean(max(score_of(item, "B", d), score_of(item, "S", d))
                                                                       for d in DRAWS) for item in items)),
        "cross_draw_bound_B_Q_S": _pct(statistics.fmean(am.item_record({name: {"token_f1": value} for name, value in
                                                                         item["score"].items()})["cross"]
                                                        for item in items)),
    }
    by_dataset = {dataset: {name: summary({key: [value for value, item in zip(policy[key], items, strict=True)
                                                 if item["dataset"] == dataset] for key in policy})
                            for name, policy in policies.items()} for dataset in datasets}
    return {"items": len(items), "policies": compare(policies, "P1_fixed_per_dataset"),
            "p9_thresholds": p9_tau, "references": references, "by_dataset": by_dataset,
            "jev": jev_diagnostics(items, signals, config, keywords, muse)}


def vmlu_report(items: list[dict[str, Any]]) -> dict[str, Any]:
    def t0_score(item: dict[str, Any], draw: str) -> float:
        return float(item["t0_correct"])

    def always_b_t0(item: dict[str, Any], draw: str) -> bool:
        return True

    agree = {item["key"]: rule_router.answers_agree(item["prediction"]["B1"], item["prediction"]["B2"],
                                                    "multiple_choice") for item in items}
    m4, m4_tau = crossfit_threshold(items, lambda item, draw: item["t0_confidence"], LOGPROB_GRID, t0_score)
    always_s: Policy = {"scores": [statistics.fmean(score_of(item, "S", d) for d in DRAWS) for item in items],
                        "tokens": [statistics.fmean(tokens_of(item, "S", d) for d in DRAWS) for item in items],
                        "escalated": [None] * len(items)}
    m1 = cascade(items, always_b_t0)
    m1["scores"] = [float(item["t0_correct"]) for item in items]
    policies: dict[str, Policy] = {
        "M2_always_S": always_s, "M1_always_B_t0": m1,
        "M3_b_agreement": cascade(items, lambda item, draw: agree[item["key"]],
                                  lambda item, draw: tokens_of(item, "B", OTHER[draw])),
        "M4_logprob_cascade": m4,
    }
    curve = []
    for tau in LOGPROB_GRID[::5]:
        keep = [item["t0_confidence"] >= tau for item in items]
        accuracy = statistics.fmean(statistics.fmean(item["t0_correct"] if k else score_of(item, "S", d) for d in DRAWS)
                                    for item, k in zip(items, keep, strict=True))
        tokens = statistics.fmean(statistics.fmean(tokens_of(item, "B", d) + (0 if k else tokens_of(item, "S", d))
                                                   for d in DRAWS) for item, k in zip(items, keep, strict=True))
        curve.append({"tau": tau, "accuracy": _pct(accuracy), "mean_student_tokens": round(tokens, 1),
                      "escalated_share": round(1 - statistics.fmean(keep), 4)})
    return {"items": len(items), "t0_confidence_missing": sum(item["t0_confidence_missing"] for item in items),
            "policies": compare(policies, "M2_always_S"), "m4_thresholds": m4_tau,
            "logprob_curve": curve,
            "ceiling_S_minus_B": ceiling(*[[score_of(item, arm, d) for item in items] for arm, d in
                                           (("S", "1"), ("S", "2"), ("B", "1"), ("B", "2"))])}


def ceilings(items: list[dict[str, Any]]) -> dict[str, Any]:
    blocks: dict[str, Any] = {}
    for dataset in sorted({item["dataset"] for item in items}):
        subset = [item for item in items if item["dataset"] == dataset]
        for a, c in (("S", "B"), ("Q", "B"), ("Q", "S")):
            blocks[f"{dataset}|{a}-{c}"] = ceiling(*[[score_of(item, arm, d) for item in subset] for arm, d in
                                                     ((a, "1"), (a, "2"), (c, "1"), (c, "2"))])
    k2: dict[str, dict[str, float]] = defaultdict(dict)
    for row in _read_jsonl(K2_SCORES):
        arm, _, draw = row["replicate_id"].partition("-r")
        k2[row["item_id"]][f"{arm}{draw}"] = float(row["token_f1"])
    k2_items = [cell for cell in k2.values() if len(cell) == 8]
    for a, c in (("K", "B"), ("KS", "K"), ("O", "K")):
        blocks[f"mc96-bidlqa-train-retrieval|{a}-{c}"] = ceiling(*[[cell[f"{arm}{d}"] for cell in k2_items] for arm, d in
                                                                   ((a, "1"), (a, "2"), (c, "1"), (c, "2"))])
    return blocks


def build_report(run_dir: Path) -> dict[str, Any]:
    config, config_sha = sig.load_config()
    manifest = sig.load_frozen_manifest()
    items, sources = reading_items()
    signals = load_signals(run_dir, items, config)
    vmlu = vmlu_items()
    return {"plan_id": PLAN_ID, "card_id": "MC-99", "signals_config_sha256": config_sha,
            "signals_manifest_sha256": manifest["manifest_sha256"],
            "sources_sha256": {**sources, "signals": v1.sha256_file(run_dir / "signals.jsonl"),
                               "muse_labels": v1.sha256_file(MUSE_LABELS), "calibration": v1.sha256_file(CALIBRATION),
                               **{name: v1.sha256_file(path) for name, path in VMLU_SOURCES.items()},
                               "k2_scores": v1.sha256_file(K2_SCORES)},
            "constants": {"min_group": MIN_GROUP, "gate_confidence": GATE_CONFIDENCE,
                          "check_threshold": CHECK_THRESHOLD, "ridge_lambda": RIDGE_LAMBDA, "folds": FOLDS,
                          "quality_points": QUALITY_POINTS, "cost_slack_points": COST_SLACK_POINTS,
                          "cost_share": COST_SHARE},
            "ceilings": ceilings(items), "reading": reading_report(items, signals, config), "vmlu": vmlu_report(vmlu)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analysis of the router signals (MC-99).")
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    out = args.run_dir / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / "router_signals_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                                    encoding="utf-8")
    for family in ("reading", "vmlu"):
        print(f"== {family}")
        for name, entry in report[family]["policies"].items():
            rule = entry.get("reading_rule") or {}
            print(f"  {name:26s} score {entry['score']:6.2f} tokens {entry['mean_student_tokens']:8.1f} "
                  f"escalated {entry['escalated_share']} gain {rule.get('gain_points')} promising {rule.get('promising')}")
    print(f"wrote {out / 'router_signals_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
