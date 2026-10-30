"""The registered analysis of the weakness-map calibration (plan weakness-map-v1; card MC-103).

Run once, after the run:
  .venv/bin/python -m code_benchmark.analyze_weakness_map --run-dir all_res/diagnostic_router_loop/weakness_map/<profile>

Per dataset (60 items each of VMLU valid, VM14K and ViBidLQA train), for the student and for Qwen3.5-9B on the same
items (its MC-95 B-r1, B-r2 and S-r1):
* arm means on draw 1 (accuracy for multiple choice, token-F1 for reading), B's second draw, and the rule loop
  (B-r1 kept when it agrees with B-r2 under normalized-answer-v1, otherwise S-r1);
* each fix against B-r1: the mean paired difference with a percentile bootstrap interval (2,000 resamples, seed 7)
  and a two-sided sign-flip p-value (20,000 resamples, seed 7). Also the rescued items (B-r1 wrong, fix right) and
  the damaged items (B-r1 right, fix wrong), where right means a correct letter or a token-F1 of at least 0.5;
* noise: how often B-r1 and B-r2 agree, and their paired difference;
* the point map and the reliable map of each model, and the datasets where the two models' maps differ;
* the interaction: the student's S-r1 minus B-r1 against Qwen's, item by item, with the same interval and p-value;
* finish reasons, truncation, S and Q format compliance, response model ids, reported tokens and the list-price cost.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_router as router
    from code_benchmark import diagnostic_weakness_map as wm
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_multimodel_expansion as v2
except ImportError:  # executed from code_benchmark/
    import analyze_router_labels as arl
    import diagnostic_router as router
    import diagnostic_weakness_map as wm
    import vi_multimodel as v1
    import vi_multimodel_expansion as v2

PLAN_ID = "weakness-map-v1"
REPORT_NAME = "weakness_map_report.json"
MAPS_NAME = "weakness_maps.json"
REFERENCE_ARMS = ("S1",)


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def _mean_tokens(rows: list[dict[str, Any]]) -> float | None:
    values = [row["total_tokens"] for row in rows if isinstance(row.get("total_tokens"), int)]
    return round(statistics.fmean(values), 1) if values else None


def model_block(rows: list[dict[str, dict[str, Any]]], fixes: tuple[str, ...], threshold: float) -> dict[str, Any]:
    """The per-dataset block of one model from its aligned cells ({B1, B2, S1[, Q1]: scored row})."""
    task = wm.task_of(rows[0]["B1"])
    cells = ("B1", "B2", *fixes)
    means = {cell: _pct(statistics.fmean(wm.score(row[cell]) for row in rows)) for cell in cells}
    first = [wm.score(row["B1"]) for row in rows]
    gains, outcomes = {}, {}
    for cell in fixes:
        gains[cell[0]] = arl.difference_block([wm.score(row[cell]) for row in rows], first)
        outcomes[cell[0]] = {
            "rescued": sum(not wm.is_right(row["B1"], threshold) and wm.is_right(row[cell], threshold) for row in rows),
            "damaged": sum(wm.is_right(row["B1"], threshold) and not wm.is_right(row[cell], threshold) for row in rows)}
    agree = [router.answers_agree(str(row["B1"].get("prediction") or ""), str(row["B2"].get("prediction") or ""), task)
             for row in rows]
    rule = [wm.score(row["B1"] if same else row["S1"]) for row, same in zip(rows, agree, strict=True)]
    return {
        "n": len(rows), "task": task, "means": means, "gains": gains, "rescue_damage": outcomes,
        "noise": {"b1_b2_agree": sum(agree), "b2_vs_b1": arl.difference_block([wm.score(row["B2"]) for row in rows], first)},
        "rule_loop": _pct(statistics.fmean(rule)),
        "tokens": {cell: _mean_tokens([row[cell] for row in rows]) for cell in cells},
        "truncated": {cell: sum(row[cell].get("finish_reason") == "length" for row in rows) for cell in cells},
        "format_ok": {cell: sum(bool(row[cell].get("format_ok")) for row in rows) for cell in fixes},
    }


def maps_of(block: dict[str, Any], tie_points: float) -> dict[str, str]:
    means = {cell[0]: value for cell, value in block["means"].items() if cell != "B2"}
    return {"point": wm.point_map(means, tie_points), "reliable": wm.reliable_map(block["gains"])}


def cost_block(rows: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    def total(key: str) -> int:
        return sum(row[key] for row in rows if isinstance(row.get(key), int))
    prompt, cached, completion = total("prompt_tokens"), total("cached_prompt_tokens"), total("completion_tokens")
    usd = ((prompt - cached) * profile["input_price_usd_per_million"] + cached * profile["cached_input_price_usd_per_million"]
           + completion * profile["output_price_usd_per_million"]) / 1e6
    return {"prompt_tokens": prompt, "cached_prompt_tokens": cached, "completion_tokens": completion,
            "reasoning_tokens": total("reasoning_tokens"), "total_tokens": total("total_tokens"),
            "list_price_usd": round(usd, 4), "price_checked_at": profile.get("price_checked_at"),
            "billing_mode": profile.get("billing_mode")}


def build_report(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config, _ = wm.load_config()
    analysis = config["analysis"]
    manifest = wm.load_frozen_manifest()
    registration = json.loads(wm.REGISTRATION_PATH.read_text(encoding="utf-8"))
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if run.get("status") != "complete" or run.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise _fail(f"the run in {run_dir} is not a complete run of the frozen manifest")
    scores_path = run_dir / "scores.jsonl"
    reference_path = wm.dp.ROOT / config["reference"]["scores"]
    if v1.sha256_file(reference_path) != config["reference"]["scores_sha256"]:
        raise _fail("the reference scores differ from the registered file")
    keys = {key for dataset_keys in manifest["calibration_items"].values() for key in dataset_keys}
    student = wm.load_cells(scores_path, keys, (*wm.EVERY_ITEM, *wm.READING_ONLY))
    reference = wm.load_cells(reference_path, keys, tuple(config["reference"]["arms"]))
    threshold = analysis["right_threshold_reading_token_f1"]
    tie = analysis["point_map"]["tie_points"]
    by_dataset: dict[str, Any] = {}
    maps: dict[str, dict[str, dict[str, str]]] = {"student": {}, "reference": {}}
    for dataset_id in sorted(manifest["calibration_items"]):
        dataset_keys = manifest["calibration_items"][dataset_id]
        mine = [student.get(key, {}) for key in dataset_keys]
        theirs = [reference.get(key, {}) for key in dataset_keys]
        first = mine[0].get("B1")
        fixes = ("S1", "Q1") if first is not None and wm.task_of(first) == "reading" else ("S1",)
        if (first is None or any(set(cell) != {"B1", "B2", *fixes} for cell in mine)
                or any(set(cell) != {"B1", "B2", "S1"} for cell in theirs)):
            raise _fail(f"{dataset_id}: the scored attempts are incomplete")
        own, ref = model_block(mine, fixes, threshold), model_block(theirs, REFERENCE_ARMS, threshold)
        by_dataset[dataset_id] = {
            "student": own, "reference": ref,
            "interaction_S": arl.difference_block([wm.score(cell["S1"]) - wm.score(cell["B1"]) for cell in mine],
                                                  [wm.score(cell["S1"]) - wm.score(cell["B1"]) for cell in theirs]),
        }
        maps["student"][dataset_id], maps["reference"][dataset_id] = maps_of(own, tie), maps_of(ref, tie)
    rows = [row for cells in student.values() for row in cells.values()]
    differ = {kind: [dataset for dataset in maps["student"] if maps["student"][dataset][kind] != maps["reference"][dataset][kind]]
              for kind in ("point", "reliable")}
    report = {
        "plan_id": PLAN_ID, "card_id": registration["card_ids"][wm.PHASE], "manifest_sha256": manifest["manifest_sha256"],
        "scores_sha256": v1.sha256_file(scores_path), "reference_sha256": config["reference"]["scores_sha256"],
        "by_dataset": by_dataset,
        "maps": {"student": maps["student"], "reference": maps["reference"], "differ": differ},
        "distributions": {
            "response_model_ids": dict(Counter(str(row.get("response_model_id")) for row in rows)),
            "finish_reasons": {cell: dict(Counter(str(cells[cell].get("finish_reason")) for cells in student.values()
                                                  if cell in cells)) for cell in ("B1", "B2", "S1", "Q1")},
            "reasoning_tokens_mean": {cell: (round(statistics.fmean(values), 1) if values else None)
                                      for cell in ("B1", "B2", "S1", "Q1")
                                      for values in [[cells[cell]["reasoning_tokens"] for cells in student.values()
                                                      if cell in cells and isinstance(cells[cell].get("reasoning_tokens"), int)]]},
        },
        "cost": cost_block(rows, v2.load_profiles()[config["student"]["profile_id"]]),
    }
    report_bytes = json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8")
    frozen_maps = {"plan_id": PLAN_ID, "card_id": report["card_id"], "items": "MC-95 calibration items (180)",
                   "report_sha256": v1.sha256_bytes(report_bytes + b"\n"),
                   "models": {config["student"]["model_id"]: maps["student"], config["reference"]["model"]: maps["reference"]}}
    return report, frozen_maps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report, frozen_maps = build_report(args.run_dir)
    registered = json.loads(wm.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.run_dir / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / MAPS_NAME).write_text(json.dumps(frozen_maps, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for dataset_id, block in report["by_dataset"].items():
        own, ref = block["student"], block["reference"]
        print(f"{dataset_id}: student {own['means']} | Qwen {ref['means']} | "
              f"maps student {report['maps']['student'][dataset_id]} Qwen {report['maps']['reference'][dataset_id]}")
    print(f"maps differ: {report['maps']['differ']}; cost {report['cost']['total_tokens']} tokens, "
          f"list price ${report['cost']['list_price_usd']}")
    print(f"report -> {out / REPORT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
