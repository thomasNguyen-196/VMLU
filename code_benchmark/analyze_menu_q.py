"""Descriptive analysis of the menu design run (openspec change diagnostic-llm-router, plan `diagnostic-menu-q-v1`;
card MC-97). Nothing is tested.

On the 967 reading items of the wide phase, every item has two draws of each menu arm: B (MC-90 B-r1, MC-91 B-r2),
S (MC-90 S-r1, MC-92 S-r2) and Q (MC-97 Q-r1, Q-r2). Per dataset and pooled, it reports:

* per arm: mean token-F1 and exact match over the two draws, and mean reported tokens per attempt;
* per item: the arm with the highest mean token-F1 (a tie at the top is counted as a tie), and whether the arm that
  wins draw 1 wins draw 2 again (an item with a tie at the top of either draw is undecided);
* two bounds for choosing per item. "Cross" chooses on one draw and scores the other, both ways, averaged; ties go to
  the earlier arm in B, Q, S. "Same draws" takes each item's best mean, so it counts luck as skill;
* the best fixed arm per dataset (ties to the earlier arm), and the pooled score of that per-dataset rule;
* each arm's failure types and the token-F1 each loses: over-long (recall >= 0.8, precision < 0.8), partial
  (precision >= 0.8, recall < 0.8), near (both >= 0.8, F1 < 1), wrong (F1 0) and mixed (the rest);
* Q against B and against S: items where Q's mean token-F1 is higher, lower or equal.

Writes analysis/menu_report.json and analysis/menu_items.jsonl (per-item arm means and winners, the material for the
router's groups) under the run directory.

Usage (repo root):
  .venv/bin/python -m code_benchmark.analyze_menu_q --run-dir all_res/diagnostic_llm_router/menu/qwen3-5-9b-65k-prospective
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_menu as menu
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_menu as menu
    import diagnostic_prospective as dp
    import vi_multimodel as v1

PLAN_ID = "diagnostic-menu-q-v1"
ARMS = ("B", "Q", "S")  # cheapest to most thorough; ties go to the earlier arm
WIDE = dp.ROOT / "all_res" / "diagnostic_prospective"
PROFILE = "qwen3-5-9b-65k-prospective"
SOURCES = {"B1": WIDE / "wide" / PROFILE / "scores.jsonl", "S1": WIDE / "wide" / PROFILE / "scores.jsonl",
           "B2": WIDE / "wide-supplements" / "wide-b-r2" / PROFILE / "scores.jsonl",
           "S2": WIDE / "wide-supplements" / "wide-s-r2" / PROFILE / "scores.jsonl"}
KINDS = ("correct", "near", "over", "partial", "mixed", "wrong")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def failure_kind(row: dict[str, Any]) -> str:
    f1 = row["token_f1"]
    if f1 == 1.0:
        return "correct"
    predicted, gold = v1.tokenize_vi(row.get("prediction") or ""), v1.tokenize_vi(row.get("gold_answer") or "")
    overlap = sum((Counter(predicted) & Counter(gold)).values())
    precision = overlap / len(predicted) if predicted else 0.0
    recall = overlap / len(gold) if gold else 0.0
    if precision >= 0.8 and recall >= 0.8:
        return "near"
    if recall >= 0.8:
        return "over"
    if precision >= 0.8:
        return "partial"
    return "wrong" if f1 == 0.0 else "mixed"


def _top(scores: dict[str, float]) -> str | None:
    """The arm with the highest score, or None when the top is tied."""
    best = max(scores.values())
    leaders = [arm for arm in ARMS if scores[arm] == best]
    return leaders[0] if len(leaders) == 1 else None


def _first_best(scores: dict[str, float]) -> str:
    best = max(scores.values())
    return next(arm for arm in ARMS if scores[arm] == best)


def item_record(cell: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Per-item arm means and winners from one item's six rows (keys B1, B2, Q1, Q2, S1, S2)."""
    draw = {d: {arm: float(cell[f"{arm}{d}"]["token_f1"]) for arm in ARMS} for d in ("1", "2")}
    means = {arm: (draw["1"][arm] + draw["2"][arm]) / 2 for arm in ARMS}
    first, second = _top(draw["1"]), _top(draw["2"])
    return {"means": means, "draws": draw, "winner": _top(means), "draw1_winner": first, "draw2_winner": second,
            "repeats": None if first is None or second is None else first == second,
            "cross": (draw["2"][_first_best(draw["1"])] + draw["1"][_first_best(draw["2"])]) / 2,
            "same_draws": max(means.values())}


def summarize(cells: list[dict[str, dict[str, Any]]]) -> dict[str, Any]:
    if not cells:
        raise _fail("no items to summarize")
    n = len(cells)
    records = [item_record(cell) for cell in cells]
    arms: dict[str, Any] = {}
    for arm in ARMS:
        rows = [cell[f"{arm}{d}"] for cell in cells for d in ("1", "2")]
        tokens = [dp.reported_tokens(row) for row in rows]
        known = [value for value in tokens if value is not None]
        kinds = Counter(failure_kind(row) for row in rows)
        lost: dict[str, float] = defaultdict(float)
        for row in rows:
            lost[failure_kind(row)] += 1 - float(row["token_f1"])
        arms[arm] = {
            "token_f1": round(100 * sum(float(row["token_f1"]) for row in rows) / len(rows), 2),
            "em": round(100 * sum(int(row["em"]) for row in rows) / len(rows), 2),
            "mean_reported_tokens": round(sum(known) / len(known), 1) if known else None,
            "unknown_usage_n": len(tokens) - len(known),
            "failure_share_pct": {kind: round(100 * kinds[kind] / len(rows), 1) for kind in KINDS},
            "failure_f1_lost": {kind: round(100 * lost[kind] / len(rows), 2) for kind in KINDS[1:]},
        }
    best_fixed = next(arm for arm in ARMS if arms[arm]["token_f1"] == max(arms[a]["token_f1"] for a in ARMS))
    decided = [record for record in records if record["repeats"] is not None]
    pairwise = {}
    for other in ("B", "S"):
        diffs = [record["means"]["Q"] - record["means"][other] for record in records]
        pairwise[f"Q_vs_{other}"] = {"better": sum(d > 0 for d in diffs), "worse": sum(d < 0 for d in diffs),
                                     "equal": sum(d == 0 for d in diffs),
                                     "mean_difference": round(100 * sum(diffs) / n, 2)}
    return {
        "items": n, "arms": arms, "best_fixed_arm": best_fixed,
        "winners": {**{arm: sum(record["winner"] == arm for record in records) for arm in ARMS},
                    "tie": sum(record["winner"] is None for record in records)},
        "repeat": {"decided_both_draws": len(decided), "same_winner": sum(record["repeats"] for record in decided),
                   "same_winner_pct": round(100 * sum(record["repeats"] for record in decided) / len(decided), 1)
                   if decided else None},
        "bounds": {"cross": round(100 * sum(record["cross"] for record in records) / n, 2),
                   "same_draws": round(100 * sum(record["same_draws"] for record in records) / n, 2)},
        "pairwise": pairwise,
    }


def _rows(path: Path, replicate_ids: set[str]) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise _fail(f"cannot read {path}: {exc}") from exc
    return [row for row in map(json.loads, filter(None, lines)) if row["replicate_id"] in replicate_ids]


def load_cells(run_dir: Path, manifest: dict[str, Any]) -> dict[str, list[dict[str, dict[str, Any]]]]:
    """{dataset: [cell]} in menu-manifest order; every menu item must have all six rows."""
    keys = list(dict.fromkeys(dp.item_key(row["dataset_id"], row["item_id"]) for row in manifest["items"]))
    cells: dict[str, dict[str, dict[str, Any]]] = {key: {} for key in keys}
    sources = [(path, {f"{name[0]}-r{name[1]}"}) for name, path in SOURCES.items()]
    sources.append((run_dir / "scores.jsonl", {"Q-r1", "Q-r2"}))
    for path, wanted in sources:
        for row in _rows(path, wanted):
            key = dp.item_key(row["dataset_id"], row["item_id"])
            if key in cells:
                arm, _, k = row["replicate_id"].partition("-r")
                cells[key][f"{arm}{k}"] = row
    missing = [key for key, cell in cells.items() if len(cell) != 6]
    if missing:
        raise _fail(f"{len(missing)} menu items lack one of the six draws, for example {missing[:3]}")
    by_dataset: dict[str, list[dict[str, dict[str, Any]]]] = defaultdict(list)
    for key in keys:
        by_dataset[key.split(":", 1)[0]].append(cells[key])
    return dict(by_dataset)


def build_report(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = menu.load_frozen_manifest()
    by_dataset = load_cells(run_dir, manifest)
    datasets = {dataset: summarize(cells) for dataset, cells in sorted(by_dataset.items())}
    pooled = summarize([cell for cells in by_dataset.values() for cell in cells])
    rule = {dataset: block["best_fixed_arm"] for dataset, block in datasets.items()}
    rule_f1 = sum(datasets[d]["arms"][arm]["token_f1"] * datasets[d]["items"] for d, arm in rule.items()) / pooled["items"]
    pooled["per_dataset_rule"] = {"arms": rule, "token_f1": round(rule_f1, 2)}
    report = {
        "plan_id": PLAN_ID, "card_id": "MC-97", "manifest_sha256": manifest["manifest_sha256"],
        "sources_sha256": {name: v1.sha256_file(path) for name, path in SOURCES.items()}
        | {"Q": v1.sha256_file(run_dir / "scores.jsonl")},
        "tie_rule": "per-item winner: a tie at the top is a tie; bounds and best fixed arm: the earlier arm in B, Q, S",
        "datasets": datasets, "pooled": pooled,
    }
    items = []
    for dataset, cells in sorted(by_dataset.items()):
        for cell in cells:
            record = item_record(cell)
            first = cell["B1"]
            items.append({"dataset_id": dataset, "item_id": first["item_id"], "gold_answer": first["gold_answer"],
                          **{key: record[key] for key in ("means", "draws", "winner", "draw1_winner", "draw2_winner",
                                                          "repeats")},
                          "predictions": {name: cell[name].get("prediction") for name in sorted(cell)}})
    return report, items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Descriptive analysis of the menu design run (MC-97).")
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report, items = build_report(args.run_dir)
    out = args.run_dir / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / "menu_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    v1.write_jsonl_atomic(out / "menu_items.jsonl", items)
    for name, block in [*report["datasets"].items(), ("pooled", report["pooled"])]:
        arms = " ".join(f"{arm} {block['arms'][arm]['token_f1']:.1f}/{block['arms'][arm]['em']:.1f}"
                        f"/{block['arms'][arm]['mean_reported_tokens']}" for arm in ARMS)
        print(f"{name.split('-v1-')[-1]:14s} n={block['items']:4d} F1/EM/tok {arms} | best fixed {block['best_fixed_arm']} "
              f"| bounds cross {block['bounds']['cross']:.1f} same {block['bounds']['same_draws']:.1f} "
              f"| repeat {block['repeat']['same_winner_pct']}% of {block['repeat']['decided_both_draws']}")
    print(f"per-dataset rule {report['pooled']['per_dataset_rule']}")
    print(f"wrote {out / 'menu_report.json'} and {out / 'menu_items.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
