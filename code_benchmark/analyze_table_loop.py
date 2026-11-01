"""The registered analysis of the loop on the /table suite (plan table-loop-v1; card MC-105). Run once, after both
runs.

  .venv/bin/python -m code_benchmark.analyze_table_loop

Per student (Qwen3.5-9B on IEC, MiMo V2.6 Flash on OpenCode Go) and dataset, from the scored attempts: always-B (B-r1,
the before), always-S (S-r1), always-vote (the majority of three S answers) and the loop (the after), each with its
score and mean reported tokens; the rounds the loop used. Multiple choice is scored by accuracy, reading by token-F1
under vi-reading-v3 with exact match and vi-reading-v2 beside. Primary: the loop against always-B in each of the 12
student and dataset cells (exact McNemar for multiple choice, sign-flip on token-F1 for reading), Holm over the 12.
Beside each dataset, the number /table publishes for the student (MC-83, MC-85); beside the six datasets, MC-104's
VMLU dev row. Writes all_res/diagnostic_router_loop/table_loop/analysis/table_loop_report.json.
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
    from code_benchmark import analyze_self_loop as asl
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_table_loop as tl
    from code_benchmark import vi_multimodel as v1
    from code_benchmark.analyze_diagnostic_prospective import holm_adjust, mcnemar_exact_p
except ImportError:  # executed from code_benchmark/
    import analyze_router_labels as arl
    import analyze_self_loop as asl
    import diagnostic_prospective as dp
    import diagnostic_table_loop as tl
    import vi_multimodel as v1
    from analyze_diagnostic_prospective import holm_adjust, mcnemar_exact_p

PLAN_ID = "table-loop-v1"
OUTPUT_ROOT = dp.ROOT / "all_res" / "diagnostic_router_loop" / "table_loop"
PROFILES = {"qwen": "qwen3-5-9b-65k-prospective", "mimo": "mimo-v2-6-flash"}
REPORT_NAME = "table_loop_report.json"
REFERENCE_PATH = dp.ROOT / "web" / "data" / "benchmark-reports.json"
MC104_REPORT = asl.OUTPUT_ROOT / "analysis" / asl.REPORT_NAME
POLICIES = ("always_B", "always_S", "always_vote", "loop")
READING_KEYS = ("token_f1", "em", "token_f1_v2", "em_v2")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _tokens(row: dict[str, Any]) -> int:
    value = dp.reported_tokens(row)
    return value if isinstance(value, int) else 0


def _mean_pct(values: list[float]) -> float:
    return round(100 * statistics.fmean(values), 2)


def accepted_unanswered(registration: dict[str, Any], student: str) -> set[str]:
    """Amendment 1: the run keys of a student that never returned within the registered timeout after the re-sends
    and are scored as no answer, as the registration lists them."""
    return {key for amendment in registration.get("amendments", []) if amendment.get("student") == student
            for key in amendment.get("unanswered_attempts", [])}


def load_rows(run_dir: Path, manifest: dict[str, Any], unanswered: set[str]) -> dict[str, dict[str, Any]]:
    """The scored attempts of a run of the frozen manifest. A run may stop short only by exactly the attempts that
    amendment 1 lists; each is added as an answer that scores nothing (no prediction, unknown usage)."""
    if not unanswered:
        return asl.load_rows(run_dir, manifest)
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if run.get("manifest_sha256") != manifest["manifest_sha256"] or run.get("status") not in ("complete", "incomplete"):
        raise _fail(f"the run in {run_dir} is not a finished run of the frozen manifest")
    rows = {dp.run_key(row): row for row in (json.loads(line) for line in
            (run_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    refs = {dp.run_key(ref): ref for ref in manifest["items"]}
    missing = set(refs) - set(rows)
    if missing != unanswered or set(rows) - set(refs) or run.get("request_error_items") != len(unanswered):
        raise _fail(f"{run_dir}: the unscored attempts {sorted(missing)[:5]} are not the {len(unanswered)} that "
                    "amendment 1 lists")
    for key in sorted(unanswered):
        ref = refs[key]
        sibling = next(row for k, row in rows.items() if k.rsplit(":", 1)[0] == key.rsplit(":", 1)[0])
        row = {name: ref[name] for name in ("dataset_id", "item_id", "replicate_id")}
        row.update({"prediction": "", "gold_answer": sibling["gold_answer"], "total_tokens": None, "unanswered": True})
        if "token_f1" in sibling:
            row.update(dict.fromkeys(READING_KEYS, 0.0))
        else:
            row["correct"] = 0
        rows[key] = row
    return rows


def item_groups(rows: dict[str, dict[str, Any]], manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, dict]]:
    """{(dataset, item): {replicate: scored row}} in manifest order."""
    groups: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for ref in manifest["items"]:
        groups[(ref["dataset_id"], ref["item_id"])][ref["replicate_id"]] = rows[dp.run_key(ref)]
    return groups


def item_outcome(student: str, task: str, attempts: dict[str, dict[str, Any]], threshold: float) -> dict[str, Any]:
    """For one item: each policy's chosen replicate, its scores and tokens, and the rounds the loop used."""
    predictions = {r: str(row.get("prediction") or "") for r, row in attempts.items()}
    confidence = attempts["B-r1"].get("confidence") if task == "multiple_choice" and student == "qwen" else None
    final, rounds = tl.choose(task, student, predictions, confidence, threshold)
    chosen = {"always_B": "B-r1", "always_S": "S-r1", "always_vote": tl.vote(predictions, task), "loop": final}
    tokens = {r: _tokens(row) for r, row in attempts.items()}
    first = ["B-r1"] if task == "multiple_choice" and student == "qwen" else ["B-r1", "B-r2"]
    used = first + (["S-r1"] if rounds >= 2 else []) + (["S-r2", "S-r3"] if rounds == 3 else [])
    cost = {"always_B": tokens["B-r1"], "always_S": tokens["S-r1"],
            "always_vote": sum(tokens[r] for r in tl.S_REPLICATES), "loop": sum(tokens[r] for r in used)}

    def scores(row: dict[str, Any]) -> dict[str, float]:
        if task == "multiple_choice":
            answer = str(row.get("prediction") or "").strip().upper()
            return {"accuracy": float(bool(answer) and answer == str(row["gold_answer"]).strip().upper())}
        return {key: float(row[key]) for key in READING_KEYS}
    return {"rounds": rounds, "cost": cost, "scores": {name: scores(attempts[r]) for name, r in chosen.items()}}


def table_reference(reference: dict[str, Any], condition_id: str, dataset_id: str, task: str) -> dict[str, float]:
    """The published /table numbers of one condition and dataset; fails closed when one is missing."""
    wanted = ("accuracy",) if task == "multiple_choice" else ("token_f1_v3", "em_v3", "token_f1", "em")
    found = {row["metric"]: row["score"] for report in reference["reports"] for row in report["benchmarks"]
             if row["condition_id"] == condition_id and row["dataset_id"] == dataset_id and row["level"] == "dataset"}
    missing = [metric for metric in wanted if metric not in found]
    if missing:
        raise _fail(f"/table has no {missing} for {condition_id} {dataset_id}")
    return {metric: found[metric] for metric in wanted}


def dataset_block(student: str, dataset_id: str, task: str, outcomes: list[dict[str, Any]],
                  reference: dict[str, float]) -> dict[str, Any]:
    primary = "accuracy" if task == "multiple_choice" else "token_f1"
    keys = ("accuracy",) if task == "multiple_choice" else READING_KEYS
    series = {name: [o["scores"][name][primary] for o in outcomes] for name in POLICIES}
    policies = {name: {**{key: _mean_pct([o["scores"][name][key] for o in outcomes]) for key in keys},
                       "mean_tokens": round(statistics.fmean(o["cost"][name] for o in outcomes), 1)}
                for name in POLICIES}
    rounds = [o["rounds"] for o in outcomes]
    if task == "multiple_choice":
        pairs = list(zip(series["loop"], series["always_B"], strict=True))
        rescues, regressions = sum(1 for a, b in pairs if a and not b), sum(1 for a, b in pairs if b and not a)
        versus_b = {"rescues": rescues, "regressions": regressions, "p": mcnemar_exact_p(regressions, rescues),
                    "test": "exact McNemar",
                    "mean_points": round(policies["loop"][primary] - policies["always_B"][primary], 2)}
    else:
        block = arl.difference_block(series["loop"], series["always_B"])
        versus_b = {**block, "p": block["sign_flip_p"], "test": "sign-flip on token-F1"}
    return {"student": student, "dataset_id": dataset_id, "task": task, "n": len(outcomes), "metric": primary,
            "policies": policies, "loop_rounds": {str(k): rounds.count(k) for k in (1, 2, 3)},
            "loop_vs_B": versus_b, "loop_vs_S": arl.difference_block(series["loop"], series["always_S"]),
            "vote_vs_S": arl.difference_block(series["always_vote"], series["always_S"]),
            "table_reference": reference}


def vmlu_dev(reference: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """MC-104's VMLU dev row beside the /table number, as the configuration names them."""
    report = json.loads(MC104_REPORT.read_text(encoding="utf-8"))
    out: dict[str, Any] = {"source": str(MC104_REPORT.relative_to(dp.ROOT)), "report_sha256": v1.sha256_file(MC104_REPORT)}
    for student in tl.STUDENTS:
        row = report["multiple_choice"][student]["by_dataset"]["vmlu-mqa-dev"]
        condition = config["reference"]["table_vmlu_dev_conditions"][student]
        out[student] = {"policies": {name: row[name] for name in POLICIES},
                        "table_reference": table_reference(reference, condition, "vi-multimodel-v2-vmlu-dev",
                                                           "multiple_choice")}
    return out


def build_report(root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    config, _ = tl.load_config()
    registration = json.loads(tl.REGISTRATION_PATH.read_text(encoding="utf-8"))
    threshold = config["loop"]["multiple_choice"]["threshold"]
    families = config["items"]["families"]
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    report: dict[str, Any] = {"plan_id": PLAN_ID, "card_id": registration["card_ids"][tl.PHASE],
                              "manifest_sha256": {}, "scores_sha256": {},
                              "reference_sha256": v1.sha256_file(REFERENCE_PATH), "datasets": {}, "primary": {},
                              "vmlu_dev": {}, "cost": {}}
    pvalues: dict[str, float] = {}
    for student in tl.STUDENTS:
        manifest = tl.load_frozen_manifest(student)
        run_dir = root / PROFILES[student]
        rows = load_rows(run_dir, manifest, accepted_unanswered(registration, student))
        report["manifest_sha256"][student] = manifest["manifest_sha256"]
        report["scores_sha256"][student] = v1.sha256_file(run_dir / "scores.jsonl")
        by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for (dataset_id, _), attempts in item_groups(rows, manifest).items():
            task = "multiple_choice" if dataset_id in families["multiple_choice"] else "reading"
            by_dataset[dataset_id].append(item_outcome(student, task, attempts, threshold))
        report["datasets"][student] = {}
        for dataset_id in config["items"]["datasets"]:
            task = "multiple_choice" if dataset_id in families["multiple_choice"] else "reading"
            condition = config["reference"]["table_conditions"][student]
            block = dataset_block(student, dataset_id, task, by_dataset[dataset_id],
                                  table_reference(reference, condition, dataset_id, task))
            report["datasets"][student][dataset_id] = block
            pvalues[f"{student}:{dataset_id}"] = block["loop_vs_B"]["p"]
        report["cost"][student] = asl.cost_block(student, rows)
    adjusted = holm_adjust(pvalues)
    alpha = config["analysis"]["alpha"]
    for key, p_holm in adjusted.items():
        student, dataset_id = key.split(":", 1)
        block = report["datasets"][student][dataset_id]
        metric = block["metric"]
        gain = block["policies"]["loop"][metric] - block["policies"]["always_B"][metric]
        report["primary"][key] = {"p_holm": p_holm, "loop_minus_B_points": round(gain, 2),
                                  "met": p_holm < alpha and gain > 0}
    report["vmlu_dev"] = vmlu_dev(reference, config)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=OUTPUT_ROOT)
    args = ap.parse_args(argv)
    report = build_report(args.root)
    registered = json.loads(tl.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.root / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for student, blocks in report["datasets"].items():
        for dataset_id, block in blocks.items():
            metric, policies = block["metric"], block["policies"]
            line = " ".join(f"{name} {policies[name][metric]} ({policies[name]['mean_tokens']} tok)" for name in POLICIES)
            print(f"{student} {dataset_id}: {line} | /table {block['table_reference']} | "
                  f"primary {report['primary'][f'{student}:{dataset_id}']}")
    print(f"report -> {out / REPORT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
