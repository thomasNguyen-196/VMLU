"""Score one frozen Vietnamese multi-model run and summarize all metrics.

The v2 reading score preserves Vietnamese diacritics and reports whitespace
token-F1. The frozen scorer is computed alongside it on the same raw response.
Run from repo root:
  .venv/bin/python code_benchmark/score_vi_multimodel.py --phase pilot --profile muse-spark-1-3-contributor
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

try:
    from code_benchmark.run_mc_eval import extract_answer
    from code_benchmark.score_reading_eval import score_pair
    from code_benchmark.vi_multimodel import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        canonical_json,
        extract_final_answer,
        load_manifest,
        load_model_profiles,
        load_protocol,
        normalize_em_answer,
        rebuild_items,
        score_vi_reading,
        write_jsonl_atomic,
    )
except ImportError:
    from run_mc_eval import extract_answer
    from score_reading_eval import score_pair
    from vi_multimodel import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        canonical_json,
        extract_final_answer,
        load_manifest,
        load_model_profiles,
        load_protocol,
        normalize_em_answer,
        rebuild_items,
        score_vi_reading,
        write_jsonl_atomic,
    )

Z95 = 1.959963984540054


def wilson_interval(successes: int, n: int) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = successes / n
    z2 = Z95 * Z95
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    radius = Z95 * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n) / denominator
    return (max(0.0, center - radius) * 100, min(1.0, center + radius) * 100)


def clustered_mean_interval(
    rows: list[dict[str, Any]],
    *,
    value_key: str,
    cluster_key: str,
    seed: int = 42,
    samples: int = 2000,
) -> tuple[float, float] | None:
    """Percentile bootstrap of an item-weighted mean, resampling source passages."""
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(cluster_key) or row.get("item_id"))].append(float(row[value_key]))
    if not groups:
        return None
    names = sorted(groups)
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        chosen = [names[rng.randrange(len(names))] for _ in names]
        values = [value for name in chosen for value in groups[name]]
        estimates.append(sum(values) / len(values) * 100)
    estimates.sort()
    return (estimates[int(0.025 * samples)], estimates[min(samples - 1, int(0.975 * samples))])


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def score_rows(
    manifest: dict[str, Any],
    predictions: dict[str, dict],
    item_map: dict,
) -> tuple[list[dict], dict[str, dict]]:
    scored: list[dict] = []
    expected_by_dataset: dict[str, list[dict]] = defaultdict(list)
    for ref in manifest["items"]:
        key = f"{ref['dataset_id']}:{ref['item_id']}:{ref['replicate_id']}"
        item = item_map.get(key)
        if item is None:
            raise SystemExit(f"Error: frozen item cannot be rebuilt: {key}")
        expected_by_dataset[item.dataset_id].append(ref)
        prediction = predictions.get(key)
        if prediction is not None and (
            prediction.get("dataset_id") != item.dataset_id
            or str(prediction.get("item_id")) != item.item_id
            or str(prediction.get("replicate_id")) != item.replicate_id
        ):
            raise SystemExit(f"Error: prediction identity mismatch for {key}")
        if (prediction is None or prediction.get("status") != "complete"
                or str(prediction.get("finish_reason", "")).lower() in {"error", "failed", "aborted"}):
            continue
        if prediction.get("prompt_sha256") != ref["prompt_sha256"]:
            raise SystemExit(f"Error: prompt hash mismatch in prediction {key}")
        raw = str(prediction.get("raw_response", ""))
        row: dict[str, Any] = {
            "dataset_id": item.dataset_id,
            "source_dataset": item.source_dataset,
            "item_id": item.item_id,
            "replicate_id": item.replicate_id,
            "stratum": item.stratum,
            "passage_id": item.passage_id,
            "gold_answer": item.gold_answer,
            "raw_response": raw,
            "prompt_sha256": ref["prompt_sha256"],
            "finish_reason": prediction.get("finish_reason", ""),
            "response_model_id": prediction.get("response_model_id", ""),
            "system_fingerprint": prediction.get("system_fingerprint", ""),
            "service_tier": prediction.get("service_tier", ""),
            "request_id": prediction.get("request_id", ""),
            "prompt_tokens": prediction.get("prompt_tokens"),
            "cached_prompt_tokens": prediction.get("cached_prompt_tokens"),
            "completion_tokens": prediction.get("completion_tokens"),
            "reasoning_tokens": prediction.get("reasoning_tokens"),
            "total_tokens": prediction.get("total_tokens"),
            "latency_s": prediction.get("latency_s"),
        }
        if item.task == "multiple_choice":
            answer = extract_answer(raw)
            row.update({
                "prediction": answer,
                "correct": int(bool(answer) and answer == item.gold_answer.strip().upper()),
            })
        else:
            final_answer = extract_final_answer(raw)
            strict = score_vi_reading(final_answer, item.gold_answer)
            _, old_raw_f1, old_raw_em, _ = score_pair(raw, item.gold_answer)
            _, old_final_f1, old_final_em, _ = score_pair(final_answer, item.gold_answer)
            row.update({
                "prediction": final_answer,
                "em": strict["em"],
                "token_f1": strict["token_f1"],
                "legacy_raw_em": int(old_raw_em),
                "legacy_raw_char_f1": old_raw_f1,
                "legacy_final_em": int(old_final_em),
                "legacy_final_char_f1": old_final_f1,
            })
        scored.append(row)

    summaries: dict[str, dict] = {}
    for dataset_id, refs in expected_by_dataset.items():
        request_rows = [row for row in scored if row["dataset_id"] == dataset_id]
        primary_refs = [ref for ref in refs if not ref["replicate_id"].startswith("repeat-")]
        repeat_refs = [ref for ref in refs if ref["replicate_id"].startswith("repeat-")]
        rows = [row for row in request_rows if not row["replicate_id"].startswith("repeat-")]
        n = len(rows)
        primary_by_item = {row["item_id"]: row for row in rows}
        paired_repeats = [
            (primary_by_item[row["item_id"]], row)
            for row in request_rows
            if row["replicate_id"].startswith("repeat-") and row["item_id"] in primary_by_item
        ]
        repeat_agreements = sum(
            (
                str(primary["prediction"]) == str(repeat["prediction"])
                if "correct" in primary
                else normalize_em_answer(str(primary["prediction"]))
                == normalize_em_answer(str(repeat["prediction"]))
            )
            for primary, repeat in paired_repeats
        )
        summary: dict[str, Any] = {
            "dataset_id": dataset_id,
            "expected_n": len(primary_refs),
            "completed_n": n,
            "request_n": len(refs),
            "request_completed_n": len(request_rows),
            "request_coverage_pct": round(100 * len(request_rows) / len(refs), 2) if refs else 0.0,
            "coverage_pct": round(100 * n / len(primary_refs), 2) if primary_refs else 0.0,
            "repeat_n": len(repeat_refs),
            "repeat_pair_n": len(paired_repeats),
            "repeat_same_answer_n": repeat_agreements,
            "repeat_answer_agreement_pct": (
                round(100 * repeat_agreements / len(paired_repeats), 2) if paired_repeats else None
            ),
            "status": "complete" if n == len(primary_refs) else "incomplete",
            "request_status": "complete" if len(request_rows) == len(refs) else "incomplete",
            "scorer_version": "vi-reading-v2",
        }
        if n:
            prompt_usage = [float(row["prompt_tokens"]) for row in rows if isinstance(row.get("prompt_tokens"), int)]
            completion_usage = [
                float(row["completion_tokens"]) for row in rows if isinstance(row.get("completion_tokens"), int)
            ]
            reasoning_usage = [
                float(row["reasoning_tokens"]) for row in rows if isinstance(row.get("reasoning_tokens"), int)
            ]
            latency_usage = [float(row["latency_s"]) for row in rows if isinstance(row.get("latency_s"), (int, float))]
            finish_reasons: dict[str, int] = defaultdict(int)
            for row in rows:
                finish_reasons[str(row.get("finish_reason") or "unknown")] += 1
            summary.update({
                "prompt_tokens_known_n": len(prompt_usage),
                "prompt_tokens_mean": round(sum(prompt_usage) / len(prompt_usage), 2) if prompt_usage else None,
                "completion_tokens_known_n": len(completion_usage),
                "completion_tokens_mean": round(sum(completion_usage) / len(completion_usage), 2)
                if completion_usage else None,
                "completion_tokens_p50": percentile(completion_usage, 0.50),
                "completion_tokens_p90": percentile(completion_usage, 0.90),
                "completion_tokens_max": max(completion_usage) if completion_usage else None,
                "reasoning_tokens_known_n": len(reasoning_usage),
                "reasoning_tokens_mean": round(sum(reasoning_usage) / len(reasoning_usage), 2)
                if reasoning_usage else None,
                "reasoning_tokens_p90": percentile(reasoning_usage, 0.90),
                "reasoning_tokens_max": max(reasoning_usage) if reasoning_usage else None,
                "latency_s_p50": percentile(latency_usage, 0.50),
                "latency_s_p90": percentile(latency_usage, 0.90),
                "finish_reason_counts": dict(sorted(finish_reasons.items())),
                "truncated_n": finish_reasons.get("length", 0),
            })
            if "correct" in rows[0]:
                correct = sum(int(row["correct"]) for row in rows)
                unparsed = sum(not str(row["prediction"]) for row in rows)
                ci = wilson_interval(correct, n)
                by_group: dict[str, list[dict]] = defaultdict(list)
                by_subject: dict[str, list[dict]] = defaultdict(list)
                by_gold: dict[str, list[dict]] = defaultdict(list)
                for row in rows:
                    by_group[str(row["stratum"])].append(row)
                    by_subject[str(row["passage_id"])].append(row)
                    by_gold[str(row["gold_answer"])].append(row)
                def accuracy_row(level: str, name: str, subset: list[dict]) -> dict[str, Any]:
                    subset_correct = sum(int(row["correct"]) for row in subset)
                    return {
                        "level": level,
                        "name": name,
                        "n": len(subset),
                        "correct": subset_correct,
                        "unparsed_n": sum(not str(row["prediction"]) for row in subset),
                        "accuracy": round(100 * subset_correct / len(subset), 2),
                    }
                summary.update({
                    "accuracy": round(100 * correct / n, 2),
                    "correct": correct,
                    "unparsed_n": unparsed,
                    "ci95": list(ci) if ci else None,
                    "accuracy_rows": [accuracy_row("overall", "overall", rows)] + [
                        accuracy_row("category", group, subset)
                        for group, subset in sorted(by_group.items())
                    ] + [
                        accuracy_row("subject", group, subset)
                        for group, subset in sorted(by_subject.items())
                    ],
                    "by_gold": [
                        {"gold": gold, "n": len(subset),
                         "correct": sum(int(row["correct"]) for row in subset),
                         "accuracy": round(100 * sum(int(row["correct"]) for row in subset) / len(subset), 2)}
                        for gold, subset in sorted(by_gold.items())
                    ],
                    "by_group": [
                        {
                            "group": group,
                            "n": len(subset),
                            "correct": sum(int(row["correct"]) for row in subset),
                            "accuracy": round(
                                100 * sum(int(row["correct"]) for row in subset) / len(subset), 2
                            ),
                        }
                        for group, subset in sorted(by_group.items())
                    ],
                })
            else:
                em_count = sum(int(row["em"]) for row in rows)
                token_mean = sum(float(row["token_f1"]) for row in rows) / n
                empty_answers = sum(not str(row["prediction"]).strip() for row in rows)
                em_ci = clustered_mean_interval(rows, value_key="em", cluster_key="passage_id")
                token_ci = clustered_mean_interval(
                    rows, value_key="token_f1", cluster_key="passage_id"
                )
                summary.update({
                    "em": round(100 * em_count / n, 2),
                    "em_count": em_count,
                    "em_ci95": list(em_ci) if em_ci else None,
                    "token_f1": round(100 * token_mean, 2),
                    "token_f1_ci95": list(token_ci) if token_ci else None,
                    "empty_answer_n": empty_answers,
                    "legacy_raw_em": round(100 * sum(int(row["legacy_raw_em"]) for row in rows) / n, 2),
                    "legacy_raw_char_f1": round(
                        100 * sum(float(row["legacy_raw_char_f1"]) for row in rows) / n, 2
                    ),
                    "legacy_final_em": round(
                        100 * sum(int(row["legacy_final_em"]) for row in rows) / n, 2
                    ),
                    "legacy_final_char_f1": round(
                        100 * sum(float(row["legacy_final_char_f1"]) for row in rows) / n, 2
                    ),
                })
        summaries[dataset_id] = summary
    return scored, summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a frozen v1 multi-model profile run.")
    parser.add_argument("--phase", choices=("pilot", "pilot_omp", "main"), required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="write coverage and omit headline scores for partial datasets")
    args = parser.parse_args()
    profiles = load_model_profiles()
    if args.profile not in profiles:
        parser.error(f"unknown profile: {args.profile}")
    protocol = load_protocol()
    manifest = load_manifest(args.phase)
    run_dir = OUTPUT_DIR / args.phase / args.profile
    run_path = run_dir / "run.json"
    predictions_path = run_dir / "predictions.jsonl"
    if not run_path.is_file() or not predictions_path.is_file():
        raise SystemExit(f"Error: run outputs missing under {run_dir}")
    run_meta = json.loads(run_path.read_text(encoding="utf-8"))
    if run_meta.get("protocol_id") != protocol["protocol_id"]:
        raise SystemExit("Error: run protocol ID differs from v1")
    if run_meta.get("profile_id") != args.profile or run_meta.get("phase") != args.phase:
        raise SystemExit("Error: run profile/phase differs from the selected run")
    expected_card = profiles[args.profile]["measurement_card_ids"][args.phase]
    if run_meta.get("measurement_card_id") != expected_card:
        raise SystemExit("Error: run measurement card differs from the selected profile")
    if run_meta.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise SystemExit("Error: run item manifest differs from frozen manifest")
    predictions: dict[str, dict] = {}
    for line in predictions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = str(row.get("run_key", ""))
        if not key or key in predictions:
            raise SystemExit(f"Error: blank or duplicate run key in {predictions_path}")
        predictions[key] = row
    expected_keys = {f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}" for row in manifest["items"]}
    unknown_keys = sorted(set(predictions) - expected_keys)
    if unknown_keys:
        raise SystemExit(f"Error: predictions outside frozen manifest: {unknown_keys[:5]}")
    scored, summaries = score_rows(manifest, predictions, rebuild_items(args.phase))
    incomplete = [key for key, value in summaries.items() if value["status"] != "complete"]
    if incomplete and not args.allow_incomplete:
        raise SystemExit(
            f"Error: incomplete datasets {incomplete}; use --allow-incomplete for coverage-only summaries"
        )
    for key in incomplete:
        for metric in (
            "accuracy", "correct", "ci95", "accuracy_rows", "by_gold", "by_group",
            "em", "em_count", "em_ci95",
            "token_f1", "token_f1_ci95", "legacy_raw_em", "legacy_raw_char_f1",
            "legacy_final_em", "legacy_final_char_f1", "unparsed_n", "empty_answer_n",
        ):
            summaries[key].pop(metric, None)
    write_jsonl_atomic(run_dir / "scores.jsonl", scored)
    input_rate = run_meta.get("input_price_usd_per_million")
    cached_input_rate = run_meta.get("cached_input_price_usd_per_million")
    output_rate = run_meta.get("output_price_usd_per_million")
    usage_rows = [row for row in predictions.values() if row.get("status") == "complete"]
    priced_rows = [
        row for row in usage_rows
        if isinstance(row.get("prompt_tokens"), int)
        and isinstance(row.get("completion_tokens"), int)
    ]
    observed_cost = None
    probe_priced = (
        isinstance(run_meta.get("probe_prompt_tokens"), int)
        and isinstance(run_meta.get("probe_completion_tokens"), int)
    )
    if isinstance(input_rate, (int, float)) and isinstance(output_rate, (int, float)):
        observed_cost = sum(
            (
                (row["prompt_tokens"] - min(
                    int(row.get("cached_prompt_tokens") or 0), row["prompt_tokens"]
                )) * input_rate
                + min(int(row.get("cached_prompt_tokens") or 0), row["prompt_tokens"])
                * (cached_input_rate if isinstance(cached_input_rate, (int, float)) else input_rate)
                + row["completion_tokens"] * output_rate
            ) / 1_000_000
            for row in priced_rows
        )
        if probe_priced:
            observed_cost += (
                run_meta["probe_prompt_tokens"] * input_rate
                + run_meta["probe_completion_tokens"] * output_rate
            ) / 1_000_000
    reserved_cost = sum(
        float(row.get("reserved_cost_usd", 0.0)) for row in predictions.values()
    ) + float(run_meta.get("probe_reserved_cost_usd", 0.0))
    attempts_total = sum(int(row.get("attempts", 1)) for row in predictions.values())
    attempts_total += int(run_meta.get("probe_attempt_count", 0))
    usage_priced_attempts = len(priced_rows) + int(probe_priced)
    main_dataset_ids = [task["id"] for task in protocol["datasets"]]
    dataset_ids = [dataset_id for dataset_id in main_dataset_ids if dataset_id in summaries]
    dataset_ids.extend(dataset_id for dataset_id in summaries if dataset_id not in main_dataset_ids)
    summary = {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": protocol["protocol_version"],
        "phase": args.phase,
        "profile_id": args.profile,
        "model_id": profiles[args.profile]["model_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "config_sha256": run_meta["config_sha256"],
        "measurement_card_id": profiles[args.profile]["measurement_card_ids"][args.phase],
        "measurement_card_hash": run_meta.get("measurement_card_hash", ""),
        "source_sha256": manifest["source_sha256"],
        "cost": {
            "usage_reported_cost_usd": round(observed_cost, 6) if observed_cost is not None else None,
            "usage_priced_attempts": usage_priced_attempts,
            "usage_missing_attempts": max(0, attempts_total - usage_priced_attempts),
            "reserved_cost_usd": round(reserved_cost, 6),
            "input_price_usd_per_million": input_rate,
            "cached_input_price_usd_per_million": cached_input_rate,
            "output_price_usd_per_million": output_rate,
            "billing_mode": run_meta.get("billing_mode", ""),
            "cost_basis": "provider-reported tokens × configured rate; OpenCode Go values are quota-equivalent, not extra per-request charges",
            "currency": "USD",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets": [summaries[dataset_id] for dataset_id in dataset_ids],
    }
    summary_path = run_dir / "summary.json"
    tmp = summary_path.with_suffix(".json.tmp")
    tmp.write_bytes(canonical_json(summary) + b"\n")
    tmp.replace(summary_path)
    print(f"wrote {run_dir / 'scores.jsonl'}")
    print(f"wrote {summary_path}")
    request_incomplete = [
        key for key, value in summaries.items() if value["request_status"] != "complete"
    ]
    if incomplete:
        print(f"coverage-only datasets: {', '.join(incomplete)}")
    if request_incomplete:
        print(f"request-incomplete datasets (check repeat coverage): {', '.join(request_incomplete)}")


if __name__ == "__main__":
    main()
