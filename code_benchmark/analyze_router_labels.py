"""Analysis of the Muse router's design-stage check (openspec change diagnostic-llm-router, plan
`diagnostic-router-labels-v1`; card MC-98). Descriptive: the items are design data.

On the 591 ViBidLQA design items, each with two draws of B, S (MC-90 to MC-92) and Q (MC-97) and one Muse group
(MC-98), it reports:

* the distribution of Muse groups, unrecognised outputs and format compliance;
* per Muse group: items, the mean token-F1 of B, Q and S over both draws, and the arm chosen on each draw;
* routing scores, all cross-draw (an arm chosen on one draw is scored on the other, both ways, averaged): the Muse
  grouping, the frozen keyword grouping, always-B, always-Q, always-S, and the per-item bound (each item's own arm
  chosen on one draw, scored on the other);
* paired per-item differences of the Muse grouping against always-S and against the keyword grouping: mean with a
  percentile bootstrap interval (2,000 resamples, seed 7) and a two-sided sign-flip p-value (20,000 resamples,
  seed 7);
* Muse groups against keyword groups, and the router's cost (tokens and latency per call);
* the registered reading rule: promising when the Muse grouping beats always-S by at least 1.0 token-F1 point and
  beats the keyword grouping.

Writes analysis/router_labels_report.json under the router run directory.

Usage (repo root):
  .venv/bin/python -m code_benchmark.analyze_router_labels \
      --run-dir all_res/diagnostic_llm_router/labels/muse-spark-1-3-contributor \
      [--menu-run-dir all_res/diagnostic_llm_router/menu/qwen3-5-9b-65k-prospective]
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_diagnostic_router as ar
    from code_benchmark import analyze_menu_q as am
    from code_benchmark import diagnostic_llm_router as router
    from code_benchmark import diagnostic_menu as menu
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_diagnostic_router as ar
    import analyze_menu_q as am
    import diagnostic_llm_router as router
    import diagnostic_menu as menu
    import vi_multimodel as v1

PLAN_ID = "diagnostic-router-labels-v1"
THRESHOLD_POINTS = 1.0
MENU_RUN_DIR = menu.dp.ROOT / "all_res" / "diagnostic_llm_router" / "menu" / "qwen3-5-9b-65k-prospective"


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def _mean(values: list[float]) -> float:
    return statistics.fmean(values)


def fixed_scores(cells: list[dict[str, dict[str, Any]]], arm: str) -> list[float]:
    return [(float(cell[f"{arm}1"]["token_f1"]) + float(cell[f"{arm}2"]["token_f1"])) / 2 for cell in cells]


def difference_block(left: list[float], right: list[float]) -> dict[str, Any]:
    differences = [a - b for a, b in zip(left, right, strict=True)]
    return {"mean_points": _pct(_mean(differences)), "ci95_points": ar.bootstrap_mean_ci(differences),
            "sign_flip_p": ar.sign_flip_p(differences),
            "better": sum(d > 0 for d in differences), "worse": sum(d < 0 for d in differences),
            "equal": sum(d == 0 for d in differences)}


def evaluate(cells: list[dict[str, dict[str, Any]]], muse: list[str | None], keywords: list[str],
             config: dict[str, Any], labels: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The report body from aligned cells, Muse groups (None = unrecognised) and keyword groups."""
    muse_scores, muse_first, muse_second = router.cross_draw_scores(cells, muse, config)
    keyword_scores, keyword_first, keyword_second = router.cross_draw_scores(cells, keywords, config)
    fixed = {arm: fixed_scores(cells, arm) for arm in router.ARMS}
    bound = [am.item_record(cell)["cross"] for cell in cells]
    table = {}
    for group in [*router.group_ids(config), None]:
        members = [cell for cell, label in zip(cells, muse, strict=True) if label == group]
        if not members:
            continue
        table[str(group)] = {"items": len(members),
                             **{arm: _pct(_mean(fixed_scores(members, arm))) for arm in router.ARMS},
                             "arm_draw1": muse_first[group], "arm_draw2": muse_second[group]}
    routing = {"muse_grouping": _pct(_mean(muse_scores)), "keyword_grouping": _pct(_mean(keyword_scores)),
               **{f"always_{arm}": _pct(_mean(fixed[arm])) for arm in router.ARMS},
               "per_item_bound": _pct(_mean(bound))}
    versus_s = difference_block(muse_scores, fixed["S"])
    versus_keywords = difference_block(muse_scores, keyword_scores)
    promising = (routing["muse_grouping"] - routing["always_S"] >= THRESHOLD_POINTS
                 and routing["muse_grouping"] > routing["keyword_grouping"])
    report = {
        "items": len(cells),
        "groups": dict(Counter(str(label) for label in muse)), "unrecognised": sum(label is None for label in muse),
        "group_table": table, "routing": routing,
        "mapping": {"muse": {"draw1": {str(k): v for k, v in muse_first.items()},
                             "draw2": {str(k): v for k, v in muse_second.items()}},
                    "keywords": {"draw1": keyword_first, "draw2": keyword_second}},
        "muse_minus_always_S": versus_s, "muse_minus_keywords": versus_keywords,
        "muse_by_keyword": {f"{m}|{k}": n for (m, k), n in sorted(Counter(zip(map(str, muse), keywords, strict=True)).items())},
        "reading_rule": {"threshold_points": THRESHOLD_POINTS, "promising": promising,
                         "muse_minus_always_S_points": round(routing["muse_grouping"] - routing["always_S"], 2),
                         "muse_minus_keywords_points": round(routing["muse_grouping"] - routing["keyword_grouping"], 2)},
    }
    if labels is not None:
        known = lambda key: [row[key] for row in labels if isinstance(row.get(key), (int, float))]  # noqa: E731
        report["router_cost"] = {key: round(_mean(known(key)), 1) if known(key) else None
                                 for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
                                             "latency_s")}
        report["format_ok"] = sum(bool(row.get("format_ok")) for row in labels)
        report["incomplete_responses"] = sum(row.get("response_status") == "incomplete" for row in labels)
    return report


def build_report(run_dir: Path, menu_run_dir: Path = MENU_RUN_DIR) -> dict[str, Any]:
    config, digest = router.load_config()
    manifest = router.load_frozen_manifest()
    labels_path = run_dir / "labels.jsonl"
    try:
        labels = [json.loads(line) for line in labels_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        raise _fail(f"cannot read {labels_path}: {exc}") from exc
    by_item = {row["item_id"]: row for row in labels}
    expected = [row["item_id"] for row in manifest["items"]]
    missing = [item for item in expected if item not in by_item]
    if missing:
        raise _fail(f"{len(missing)} router labels are missing, for example {missing[:3]}")
    cells_by_item = {cell["B1"]["item_id"]: cell
                     for cell in am.load_cells(menu_run_dir, menu.load_frozen_manifest())[router.DATASET]}
    questions = {item.item_id: item.question for item in router.design_items()}
    cells = [cells_by_item[item] for item in expected]
    muse = [by_item[item]["group"] for item in expected]
    keywords = [router.keyword_group(questions[item], config) for item in expected]
    return {"plan_id": PLAN_ID, "card_id": "MC-98", "router_id": config["router_id"], "router_config_sha256": digest,
            "manifest_sha256": manifest["manifest_sha256"],
            "sources_sha256": {"labels": v1.sha256_file(labels_path), "menu_scores": v1.sha256_file(menu_run_dir / "scores.jsonl")},
            **evaluate(cells, muse, keywords, config, [by_item[item] for item in expected])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analysis of the Muse router's design-stage check (MC-98).")
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--menu-run-dir", type=Path, default=MENU_RUN_DIR)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir, args.menu_run_dir)
    out = args.run_dir / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / "router_labels_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                                   encoding="utf-8")
    print(f"groups {report['groups']} unrecognised {report['unrecognised']} format_ok {report.get('format_ok')}")
    for group, row in report["group_table"].items():
        print(f"  {group:10s} n={row['items']:4d} B {row['B']:5.1f} Q {row['Q']:5.1f} S {row['S']:5.1f} "
              f"-> {row['arm_draw1']},{row['arm_draw2']}")
    print(f"routing {report['routing']}")
    print(f"muse - always_S {report['muse_minus_always_S']}")
    print(f"muse - keywords {report['muse_minus_keywords']}")
    print(f"reading rule {report['reading_rule']} | router cost {report.get('router_cost')}")
    print(f"wrote {out / 'router_labels_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
