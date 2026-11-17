"""The registered analysis of the loop for the two Muse students on the /table suite (plan table-loop-muse-v1; card
MC-108). Run once, after both runs.

  .venv/bin/python -m code_benchmark.analyze_table_loop_muse

Per student (Muse Spark 1.3 and Muse Spark 1.2, both on OpenCode Go) and dataset, from the scored attempts: always-B
(B-r1, the before), always-S (S-r1), always-vote (the majority of three S answers) and the loop (the after), each with
its score and mean reported tokens; the rounds the loop used. Multiple choice is scored by accuracy, reading by
token-F1 under vi-reading-v3 with exact match and vi-reading-v2 beside. Primary: the loop against always-B in each of
the 14 student and dataset cells, VMLU dev included (exact McNemar for multiple choice, sign-flip on token-F1 for
reading), Holm over the 14. Beside each dataset: the number /table publishes for the student (MC-80 and MC-82, MC-84)
and MC-105's loop-minus-B for Qwen and MiMo. Writes
all_res/diagnostic_router_loop/table_loop_muse/analysis/table_loop_muse_report.json.

The per-item replay, the tests and the dataset blocks are MC-105's functions, imported unchanged.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_self_loop as asl
    from code_benchmark import analyze_table_loop as atl
    from code_benchmark import diagnostic_table_loop_muse as tm
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_multimodel_expansion as v2
    from code_benchmark.analyze_diagnostic_prospective import holm_adjust
except ImportError:  # executed from code_benchmark/
    import analyze_self_loop as asl
    import analyze_table_loop as atl
    import diagnostic_table_loop_muse as tm
    import vi_multimodel as v1
    import vi_multimodel_expansion as v2
    from analyze_diagnostic_prospective import holm_adjust

PLAN_ID = "table-loop-muse-v1"
OUTPUT_ROOT = atl.dp.ROOT / "all_res" / "diagnostic_router_loop" / "table_loop_muse"
REPORT_NAME = "table_loop_muse_report.json"
REFERENCE_PATH = atl.REFERENCE_PATH
MC105_REPORT = atl.OUTPUT_ROOT / "analysis" / atl.REPORT_NAME
# The price row both students are billed at (OpenCode Go lists Muse Spark 1.2 and 1.3 at the same tariff).
PRICE_PROFILE = "muse-spark-1-3-contributor"


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def task_of(config: dict[str, Any], dataset_id: str) -> str:
    return "multiple_choice" if dataset_id in config["items"]["families"]["multiple_choice"] else "reading"


def datasets(config: dict[str, Any]) -> list[str]:
    """The seven columns in the order /table shows them: VMLU dev first, then the six main-v1 datasets."""
    return [config["items"]["vmlu_dev"]["dataset_id"], *config["items"]["datasets"]]


def reference_for(reference: dict[str, Any], config: dict[str, Any], student: str, dataset_id: str) -> dict[str, float]:
    if dataset_id == tm.VMLU_DEV:
        condition, published = config["reference"]["table_vmlu_dev_conditions"][student], "vi-multimodel-v2-vmlu-dev"
    else:
        named = config["reference"]["table_conditions"][student]
        condition, published = named.get(dataset_id, named["other"]), dataset_id
    return atl.table_reference(reference, condition, published, task_of(config, dataset_id))


def cost_block(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    profile = v2.load_profiles()[PRICE_PROFILE]
    prompt = sum(row.get("prompt_tokens") or 0 for row in rows.values())
    cached = sum(row.get("cached_prompt_tokens") or 0 for row in rows.values())
    completion = sum(row.get("completion_tokens") or 0 for row in rows.values())
    block = asl.cost_block("muse", rows)
    block["list_price_usd"] = round(((prompt - cached) * profile["input_price_usd_per_million"]
                                     + cached * profile["cached_input_price_usd_per_million"]
                                     + completion * profile["output_price_usd_per_million"]) / 1e6, 4)
    return block


def beside_mc105(path: Path = MC105_REPORT) -> dict[str, Any]:
    """MC-105's loop-minus-B per student and dataset (Qwen and MiMo), with the report's hash."""
    report = json.loads(path.read_text(encoding="utf-8"))
    return {"source": str(path.relative_to(atl.dp.ROOT)),
            "students": {student: {dataset_id: {"loop_minus_B_points": report["primary"][f"{student}:{dataset_id}"]
                                                ["loop_minus_B_points"],
                                                "met": report["primary"][f"{student}:{dataset_id}"]["met"]}
                                   for dataset_id in blocks} for student, blocks in report["datasets"].items()}}


def build_report(root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    config, _ = tm.load_config()
    registration = json.loads(tm.REGISTRATION_PATH.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    report: dict[str, Any] = {"plan_id": PLAN_ID, "card_id": registration["card_ids"][tm.PHASE],
                              "manifest_sha256": {}, "scores_sha256": {},
                              "reference_sha256": v1.sha256_file(REFERENCE_PATH),
                              "mc105_report_sha256": v1.sha256_file(MC105_REPORT), "datasets": {}, "primary": {},
                              "beside_mc105": beside_mc105(), "cost": {}}
    pvalues: dict[str, float] = {}
    for student in tm.STUDENTS:
        manifest = tm.load_frozen_manifest(student)
        run_dir = root / config["students"][student]["profile_id"]
        rows = asl.load_rows(run_dir, manifest)
        report["manifest_sha256"][student] = manifest["manifest_sha256"]
        report["scores_sha256"][student] = v1.sha256_file(run_dir / "scores.jsonl")
        by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for (dataset_id, _), attempts in atl.item_groups(rows, manifest).items():
            by_dataset[dataset_id].append(atl.item_outcome(student, task_of(config, dataset_id), attempts, 0.0))
        report["datasets"][student] = {}
        for dataset_id in datasets(config):
            task = task_of(config, dataset_id)
            block = atl.dataset_block(student, dataset_id, task, by_dataset[dataset_id],
                                      reference_for(reference, config, student, dataset_id))
            report["datasets"][student][dataset_id] = block
            pvalues[f"{student}:{dataset_id}"] = block["loop_vs_B"]["p"]
        report["cost"][student] = cost_block(rows)
    if len(pvalues) != 14:
        raise _fail(f"the primary family has {len(pvalues)} tests, not the registered 14")
    adjusted = holm_adjust(pvalues)
    alpha = config["analysis"]["alpha"]
    for key, p_holm in adjusted.items():
        student, dataset_id = key.split(":", 1)
        block = report["datasets"][student][dataset_id]
        metric = block["metric"]
        gain = block["policies"]["loop"][metric] - block["policies"]["always_B"][metric]
        report["primary"][key] = {"p_holm": p_holm, "loop_minus_B_points": round(gain, 2),
                                  "met": p_holm < alpha and gain > 0}
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=OUTPUT_ROOT)
    args = ap.parse_args(argv)
    report = build_report(args.root)
    registered = json.loads(tm.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.root / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for student, blocks in report["datasets"].items():
        for dataset_id, block in blocks.items():
            metric, policies = block["metric"], block["policies"]
            line = " ".join(f"{name} {policies[name][metric]} ({policies[name]['mean_tokens']} tok)"
                            for name in atl.POLICIES)
            print(f"{student} {dataset_id}: {line} | /table {block['table_reference']} | "
                  f"primary {report['primary'][f'{student}:{dataset_id}']}")
    print(f"report -> {out / REPORT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
