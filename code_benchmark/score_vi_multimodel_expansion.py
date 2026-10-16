"""Score expansion-v2 outputs without fabricating withheld benchmark gold.

VMLU dev/valid and synthetic pilot use local gold. VMLU test and V-Bench use
server grading; local parser validity is reported separately. Run from repo root.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

try:
    from code_benchmark.score_vi_multimodel import wilson_interval
    from code_benchmark.vi_multimodel import canonical_json, normalize_em_answer, write_jsonl_atomic
    from code_benchmark.vi_multimodel_expansion import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        item_from_manifest_row,
        load_manifest,
        load_profiles,
        parse_expanded_answer,
        rebuild_items,
    )
except ImportError:
    from score_vi_multimodel import wilson_interval
    from vi_multimodel import canonical_json, normalize_em_answer, write_jsonl_atomic
    from vi_multimodel_expansion import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        item_from_manifest_row,
        load_manifest,
        load_profiles,
        parse_expanded_answer,
        rebuild_items,
    )


def clustered_binary_interval(rows: list[dict[str, Any]], *, seed: int = 42, samples: int = 2000):
    """Passage/subject-cluster bootstrap for local-gold MC strata summaries."""
    groups: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("stratum") or row.get("item_id"))].append(int(row["correct"]))
    if len(groups) < 2:
        return None
    names = sorted(groups)
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        chosen = [names[rng.randrange(len(names))] for _ in names]
        values = [value for name in chosen for value in groups[name]]
        estimates.append(sum(values) / len(values) * 100)
    estimates.sort()
    return [estimates[int(0.025 * samples)], estimates[min(samples - 1, int(0.975 * samples))]]


def score_profile(phase: str, profile_id: str, *, allow_incomplete: bool = False) -> dict[str, Any]:
    manifest = load_manifest(phase)
    profiles = load_profiles()
    if profile_id not in profiles:
        raise SystemExit(f"Error: unknown expansion profile {profile_id}")
    run_dir = OUTPUT_DIR / phase / profile_id
    run_meta_path = run_dir / "run.json"
    predictions_path = run_dir / "predictions.jsonl"
    if not run_meta_path.is_file() or not predictions_path.is_file():
        raise SystemExit(f"Error: run outputs missing under {run_dir}")
    run_meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
    if run_meta.get("protocol_id") != PROTOCOL_ID or run_meta.get("phase") != phase or run_meta.get("profile_id") != profile_id:
        raise SystemExit("Error: run identity differs from the selected expansion run")
    if run_meta.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise SystemExit("Error: run item manifest differs from the frozen expansion manifest")

    predictions: dict[str, dict[str, Any]] = {}
    for line_no, line in enumerate(predictions_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        key = str(row.get("run_key", ""))
        if not key or key in predictions:
            raise SystemExit(f"Error: blank/duplicate checkpoint key at {predictions_path}:{line_no}")
        predictions[key] = row
    expected_keys = {
        f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"
        for row in manifest["items"]
    }
    unknown = sorted(set(predictions) - expected_keys)
    if unknown:
        raise SystemExit(f"Error: predictions outside frozen manifest: {unknown[:5]}")

    rebuilt = rebuild_items(phase)
    scored: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, Any]] = {}
    by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ref in manifest["items"]:
        item = item_from_manifest_row(ref, rebuilt)
        prediction = predictions.get(item.run_key)
        base: dict[str, Any] = {
            "run_key": item.run_key,
            "profile_id": profile_id,
            "dataset_id": item.dataset_id,
            "item_id": item.item_id,
            "replicate_id": item.replicate_id,
            "stratum": item.stratum,
            "task": item.task,
            "gold_status": item.gold_status,
            "prompt_sha256": ref["prompt_sha256"],
            "status": str((prediction or {}).get("status", "missing")),
            "finish_reason": str((prediction or {}).get("finish_reason", "")),
            "truncated": int(str((prediction or {}).get("finish_reason", "")).casefold() == "length"),
            "latency_s": (prediction or {}).get("latency_s"),
            "prompt_tokens": (prediction or {}).get("prompt_tokens"),
            "completion_tokens": (prediction or {}).get("completion_tokens"),
            "reasoning_tokens": (prediction or {}).get("reasoning_tokens"),
            "error_type": str((prediction or {}).get("error_type", "")),
        }
        if prediction is not None and prediction.get("status") == "complete":
            if prediction.get("prompt_sha256") != ref["prompt_sha256"]:
                raise SystemExit(f"Error: prompt hash mismatch for {item.run_key}")
            parsed = parse_expanded_answer(item, str(prediction.get("raw_response", "")))
            base.update(parsed)
        else:
            base.update({"prediction": "", "parse_valid": False, "correct": None})
        if item.gold_status == "local" and prediction is not None and prediction.get("status") == "complete":
            if base["correct"] is None:
                raise SystemExit(f"Error: local-gold item has no deterministic score: {item.run_key}")
        scored.append(base)
        by_dataset[item.dataset_id].append(base)

    for dataset_id, all_rows in by_dataset.items():
        primary = [row for row in all_rows if not row["replicate_id"].startswith("repeat-")]
        repeats = [row for row in all_rows if row["replicate_id"].startswith("repeat-")]
        n_expected = len(primary)
        completed = [row for row in primary if row["status"] == "complete"]
        errors = [row for row in primary if row["status"] == "request_error"]
        missing = [row for row in primary if row["status"] == "missing"]
        parse_valid_n = sum(int(bool(row.get("parse_valid"))) for row in completed)
        summary: dict[str, Any] = {
            "dataset_id": dataset_id,
            "profile_id": profile_id,
            "expected_n": n_expected,
            "request_completed_n": len(completed),
            "request_error_n": len(errors),
            "missing_n": len(missing),
            "coverage_pct": round(100 * len(completed) / n_expected, 2) if n_expected else None,
            "parse_valid_n": parse_valid_n,
            "parse_valid_pct_of_completed": round(100 * parse_valid_n / len(completed), 2) if completed else None,
            "truncated_n": sum(int(row["truncated"]) for row in completed),
            "latency_s_p50": None,
            "latency_s_p90": None,
            "gold_status": all_rows[0]["gold_status"],
        }
        latencies = sorted(float(row["latency_s"]) for row in completed if isinstance(row.get("latency_s"), (int, float)))
        if latencies:
            summary["latency_s_p50"] = latencies[min(len(latencies) - 1, int(0.50 * len(latencies)))]
            summary["latency_s_p90"] = latencies[min(len(latencies) - 1, int(0.90 * len(latencies)))]
        if all_rows[0]["gold_status"] == "local":
            if len(completed) == n_expected:
                correct = sum(int(row["correct"]) for row in completed)
                summary.update({
                    "correct": correct,
                    "accuracy": round(100 * correct / n_expected, 2),
                    "accuracy_ci95_wilson": list(wilson_interval(correct, n_expected)),
                    "unparsed_n": n_expected - parse_valid_n,
                    "status": "complete_local_score",
                })
                breakdown: list[dict[str, Any]] = []
                for stratum in sorted({str(row["stratum"]) for row in completed}):
                    group = [row for row in completed if str(row["stratum"]) == stratum]
                    group_correct = sum(int(row["correct"]) for row in group)
                    ci = clustered_binary_interval(group)
                    breakdown.append({
                        "stratum": stratum,
                        "n": len(group),
                        "correct": group_correct,
                        "accuracy": round(100 * group_correct / len(group), 2),
                        "cluster_bootstrap_ci95": ci,
                    })
                summary["by_stratum"] = breakdown
            else:
                summary["status"] = "incomplete_local_score_omitted"
                summary["accuracy"] = None
        elif len(completed) == n_expected:
            summary["status"] = "complete_awaiting_server_score"
        else:
            summary["status"] = "incomplete_awaiting_server_score"

        primary_by_id = {row["item_id"]: row for row in primary if row["status"] == "complete"}
        paired = []
        for row in repeats:
            first = primary_by_id.get(row["item_id"])
            if first is None or row["status"] != "complete":
                continue
            if first["task"] == "multiple_choice":
                same = str(first.get("prediction", "")) == str(row.get("prediction", ""))
            else:
                same = normalize_em_answer(str(first.get("prediction", ""))) == normalize_em_answer(str(row.get("prediction", "")))
            paired.append(same)
        if paired:
            summary["repeat_pair_n"] = len(paired)
            summary["repeat_agreement_pct"] = round(100 * sum(paired) / len(paired), 2)
        summaries[dataset_id] = summary

    incomplete = [key for key, value in summaries.items() if value["status"].startswith("incomplete")]
    if incomplete and not allow_incomplete:
        raise SystemExit(f"Error: incomplete expansion datasets {incomplete}; resume before headline scoring")
    write_jsonl_atomic(run_dir / "scores.jsonl", scored)
    summary_doc = {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": 2,
        "phase": phase,
        "profile_id": profile_id,
        "measurement_card_id": run_meta.get("measurement_card_id"),
        "measurement_card_hash": run_meta.get("measurement_card_hash"),
        "manifest_sha256": manifest["manifest_sha256"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request_expected_n": manifest["n"],
        "request_complete_n": sum(row.get("status") == "complete" for row in predictions.values()),
        "request_error_n": sum(row.get("status") == "request_error" for row in predictions.values()),
        "safety_rows_skipped": manifest.get("safety_rows_skipped", 0),
        "datasets": [summaries[key] for key in sorted(summaries)],
    }
    temp = run_dir / "summary.json.tmp"
    temp.write_bytes(canonical_json(summary_doc) + b"\n")
    temp.replace(run_dir / "summary.json")
    print(f"wrote {run_dir / 'scores.jsonl'} and {run_dir / 'summary.json'}")
    return summary_doc


def main() -> None:
    parser = argparse.ArgumentParser(description="Score one expansion-v2 profile from frozen outputs.")
    parser.add_argument("--phase", choices=("pilot", "vmlu", "vbench"), required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    score_profile(args.phase, args.profile, allow_incomplete=args.allow_incomplete)


if __name__ == "__main__":
    main()
