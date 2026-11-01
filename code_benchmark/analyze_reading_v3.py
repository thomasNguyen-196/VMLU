"""Post-hoc re-scoring with vi-reading-v3 (openspec change diagnostic-router-loop, decision 10, task 2.5).

Decided on 2026-10-30, after the registered MC-103 analysis and an exploratory look at its ViBidLQA answers, so
nothing here is confirmatory. Every registered result stays as it is, scored by vi-reading-v2.

  .venv/bin/python -m code_benchmark.analyze_reading_v3

Two parts, written to all_res/diagnostic_router_loop/reading_v3/reading_v3_report.json:
* mc103: the weakness-map-v1 analysis of MC-103's reading dataset (ViBidLQA train, 60 items) with every reading cell
  re-scored by v3, for MiMo and for Qwen on the same items: arm means, gains against B-r1, rescued and damaged items,
  noise, the rule loop, both maps and the interaction, beside the registered v2 block. The multiple-choice datasets
  are scored by letter and do not change.
* sensitivity: for every registered run with reading answers (one score file per card), the mean token-F1 and exact
  match under v2 and v3 per arm and dataset, the answers carrying a mark, and the answers whose score changes.
Both parts first check that every stored score is the frozen v2 score of the stored text.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import analyze_weakness_map as awm
    from code_benchmark import diagnostic_weakness_map as wm
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_reading_v3 as v3
except ImportError:  # executed from code_benchmark/
    import analyze_router_labels as arl
    import analyze_weakness_map as awm
    import diagnostic_weakness_map as wm
    import vi_multimodel as v1
    import vi_reading_v3 as v3

PLAN_ID = "reading-v3-rescore-v1"
ROOT = wm.dp.ROOT
MC103_DIR = Path("all_res/diagnostic_router_loop/weakness_map/mimo-v2-6-flash")
OUT_DIR = Path("all_res/diagnostic_router_loop/reading_v3")
REPORT_NAME = "reading_v3_report.json"
# One score file per registered card with reading answers; where a card has several copies, the one the dashboards
# read (MC-87: recovery r3; MC-89: final). Pilots are left out.
SOURCES = (
    ("MC-53", "all_res/vi_multimodel_v1/main/muse-spark-1-3-contributor"),
    ("MC-54", "all_res/vi_multimodel_v1/main/mimo-v2-6-flash"),
    ("MC-55", "all_res/vi_multimodel_v1/main/mimo-v2-5"),
    ("MC-56", "all_res/vi_multimodel_v1/main/qwen3-5-9b-65k"),
    ("MC-72", "all_res/qwen_matched_mc72/main/qwen3-5-9b-65k"),
    ("MC-73", "all_res/muse_router_matched/main/muse-spark-1-2-contributor"),
    ("MC-80", "all_res/muse13_direct_mc80/main/muse-spark-1-3-contributor-ocg"),
    ("MC-83", "all_res/qwen_direct_mc83/main/qwen3-5-9b-65k-direct-20k"),
    ("MC-84", "all_res/muse12_direct_mc84/main/muse-spark-1-2-contributor-direct-20k"),
    ("MC-85", "all_res/mimo26_direct_mc85/main/mimo-v2-6-flash-direct-20k"),
    ("MC-86", "all_res/muse13_omp_mc86/main/muse-spark-1-3-contributor-omp-full-tools-mc86"),
    ("MC-87", "all_res/muse12_omp_mc87/recovery_mc87_r3/main/muse-spark-1-2-contributor-omp-full-tools-mc87"),
    ("MC-88", "all_res/qwen_omp_mc88/main/qwen3-5-9b-65k-omp-full-tools-mc88"),
    ("MC-89", "all_res/mimo26_omp_mc89/final/main/mimo-v2-6-flash-omp-full-tools-mc89"),
    ("MC-90", "all_res/diagnostic_prospective/wide/qwen3-5-9b-65k-prospective"),
    ("MC-91", "all_res/diagnostic_prospective/wide-supplements/wide-b-r2/qwen3-5-9b-65k-prospective"),
    ("MC-92", "all_res/diagnostic_prospective/wide-supplements/wide-s-r2/qwen3-5-9b-65k-prospective"),
    ("MC-93", "all_res/diagnostic_prospective/core/qwen3-5-9b-65k-prospective"),
    ("MC-94", "all_res/diagnostic_router_v2/heldout/qwen3-5-9b-65k-prospective"),
    ("MC-95", "all_res/diagnostic_router_v3/heldout/qwen3-5-9b-65k-prospective"),
    ("MC-96", "all_res/diagnostic_k2/heldout/qwen3-5-9b-65k-prospective"),
    ("MC-97", "all_res/diagnostic_llm_router/menu/qwen3-5-9b-65k-prospective"),
    ("MC-103", str(MC103_DIR)),
)


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def scored_text(row: dict[str, Any]) -> str:
    return str(row["scoring_response"] if "scoring_response" in row else row["raw_response"])


def check_v2(rows: list[dict[str, Any]], label: str) -> None:
    """Fail closed unless every stored reading score is the frozen v2 score of the stored text."""
    for row in rows:
        if "token_f1" not in row:
            continue
        expected = v1.score_vi_reading(v1.extract_final_answer(scored_text(row)), str(row["gold_answer"]))
        if expected["em"] != row["em"] or abs(expected["token_f1"] - row["token_f1"]) > 1e-12:
            raise _fail(f"{label}: the stored score of {row['dataset_id']}:{row['item_id']}:{row['replicate_id']} "
                        f"is not the {v3.BASE_VERSION} score of its text")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """v2 against v3 on scored reading rows: means in points, answers carrying a mark, answers whose score changes."""
    new = [v3.rescore_row(row) for row in rows]
    return {
        "n": len(rows),
        "marked": sum(any(mark in scored_text(row) for mark in v3.MARKS) for row in rows),
        "changed": sum(a["em"] != b["em"] or a["token_f1"] != b["token_f1"] for a, b in zip(rows, new, strict=True)),
        "token_f1": {"v2": _pct(statistics.fmean(row["token_f1"] for row in rows)),
                     "v3": _pct(statistics.fmean(row["token_f1"] for row in new))},
        "em": {"v2": _pct(statistics.fmean(row["em"] for row in rows)),
               "v3": _pct(statistics.fmean(row["em"] for row in new))},
    }


def _json_round_trip(value: Any) -> Any:
    return json.loads(json.dumps(value))


def mc103(run_dir: Path) -> dict[str, Any]:
    config, _ = wm.load_config()
    manifest = wm.load_frozen_manifest()
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if run.get("status") != "complete" or run.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise _fail(f"the run in {run_dir} is not a complete run of the frozen manifest")
    scores_path = run_dir / "scores.jsonl"
    reference_path = ROOT / config["reference"]["scores"]
    if v1.sha256_file(reference_path) != config["reference"]["scores_sha256"]:
        raise _fail("the reference scores differ from the registered file")
    registered = json.loads((run_dir / "analysis" / awm.REPORT_NAME).read_text(encoding="utf-8"))
    if registered["scores_sha256"] != v1.sha256_file(scores_path):
        raise _fail("the scores differ from the ones the registered analysis read")
    keys = {key for dataset_keys in manifest["calibration_items"].values() for key in dataset_keys}
    student = wm.load_cells(scores_path, keys, (*wm.EVERY_ITEM, *wm.READING_ONLY))
    reference = wm.load_cells(reference_path, keys, tuple(config["reference"]["arms"]))
    for label, cells in (("MC-103", student), ("MC-95 reference", reference)):
        check_v2([row for cell in cells.values() for row in cell.values()], label)
    threshold = config["analysis"]["right_threshold_reading_token_f1"]
    tie = config["analysis"]["point_map"]["tie_points"]
    blocks: dict[str, Any] = {}
    for dataset_id in sorted(manifest["calibration_items"]):
        dataset_keys = manifest["calibration_items"][dataset_id]
        mine, theirs = [student[key] for key in dataset_keys], [reference[key] for key in dataset_keys]
        if wm.task_of(mine[0]["B1"]) != "reading":
            continue
        fixes = ("S1", "Q1")
        before = registered["by_dataset"][dataset_id]
        if (_json_round_trip(awm.model_block(mine, fixes, threshold)) != before["student"]
                or _json_round_trip(awm.model_block(theirs, awm.REFERENCE_ARMS, threshold)) != before["reference"]):
            raise _fail(f"{dataset_id}: the v2 blocks do not reproduce the registered report")
        mine3 = [{cell: v3.rescore_row(row) for cell, row in cells.items()} for cells in mine]
        theirs3 = [{cell: v3.rescore_row(row) for cell, row in cells.items()} for cells in theirs]
        own, ref = awm.model_block(mine3, fixes, threshold), awm.model_block(theirs3, awm.REFERENCE_ARMS, threshold)
        blocks[dataset_id] = {
            "v2_registered": {**before, "maps": {"student": registered["maps"]["student"][dataset_id],
                                                 "reference": registered["maps"]["reference"][dataset_id]}},
            "v3": {"student": own, "reference": ref,
                   "interaction_S": arl.difference_block([wm.score(c["S1"]) - wm.score(c["B1"]) for c in mine3],
                                                         [wm.score(c["S1"]) - wm.score(c["B1"]) for c in theirs3]),
                   "maps": {"student": awm.maps_of(own, tie), "reference": awm.maps_of(ref, tie)}},
            "rows": {"student": {cell: summarize([c[cell] for c in mine]) for cell in ("B1", "B2", *fixes)},
                     "reference": {cell: summarize([c[cell] for c in theirs]) for cell in ("B1", "B2", "S1")}},
        }
    return {"card_id": registered["card_id"], "scores_sha256": registered["scores_sha256"],
            "reference_sha256": registered["reference_sha256"],
            "registered_report_sha256": v1.sha256_file(run_dir / "analysis" / awm.REPORT_NAME),
            "by_dataset": blocks}


def sensitivity() -> dict[str, Any]:
    sources, groups, runs = [], [], []
    for card_id, folder in SOURCES:
        path = ROOT / folder / "scores.jsonl"
        summary = json.loads((ROOT / folder / "summary.json").read_text(encoding="utf-8"))
        if summary.get("measurement_card_id") != card_id:
            raise _fail(f"{folder} belongs to {summary.get('measurement_card_id')}, not {card_id}")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        reading = [row for row in rows if "token_f1" in row]
        if not reading:
            raise _fail(f"{card_id}: no reading answers in {path}")
        check_v2(reading, card_id)
        sources.append({"card_id": card_id, "model_id": summary.get("model_id"), "scores": f"{folder}/scores.jsonl",
                        "sha256": v1.sha256_file(path)})
        by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in reading:
            arm = str(row.get("arm", "-"))
            by_arm[arm].append(row)
            by_group[(arm, row["dataset_id"])].append(row)
        for arm, arm_rows in sorted(by_arm.items()):
            runs.append({"card_id": card_id, "model_id": summary.get("model_id"), "arm": arm, **summarize(arm_rows)})
        for (arm, dataset_id), group in sorted(by_group.items()):
            groups.append({"card_id": card_id, "arm": arm, "dataset_id": dataset_id, **summarize(group)})
    return {"sources": sources, "by_run": runs, "by_dataset": groups}


def build_report(run_dir: Path) -> dict[str, Any]:
    return {"plan_id": PLAN_ID, "scorer_version": v3.SCORER_VERSION, "base_version": v3.BASE_VERSION,
            "marks": v3.MARKS, "post_hoc": True, "mc103": mc103(run_dir), "sensitivity": sensitivity()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, default=ROOT / MC103_DIR)
    ap.add_argument("--out", type=Path, default=ROOT / OUT_DIR)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for dataset_id, block in report["mc103"]["by_dataset"].items():
        for side in ("student", "reference"):
            old, new = block["v2_registered"][side], block["v3"][side]
            print(f"{dataset_id} {side}: v2 {old['means']} -> v3 {new['means']}; S gain v3 "
                  f"{new['gains']['S']['mean_points']} {new['gains']['S']['ci95_points']} p {new['gains']['S']['sign_flip_p']}; "
                  f"maps v2 {block['v2_registered']['maps'][side]} -> v3 {block['v3']['maps'][side]}")
        interaction = block["v3"]["interaction_S"]
        print(f"{dataset_id} interaction S (v3): {interaction['mean_points']} {interaction['ci95_points']} "
              f"p {interaction['sign_flip_p']}")
    for run in report["sensitivity"]["by_run"]:
        print(f"{run['card_id']:>6} {str(run['model_id']):<36} {run['arm']:<3} n={run['n']:>5} marked {run['marked']:>4} "
              f"changed {run['changed']:>4}  F1 {run['token_f1']['v2']:6.2f} -> {run['token_f1']['v3']:6.2f}  "
              f"EM {run['em']['v2']:6.2f} -> {run['em']['v3']:6.2f}")
    print(f"report -> {args.out / REPORT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
