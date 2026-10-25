"""Import a completed vi-multimodel-v1 score run into the results database.

This importer requires exact protocol/profile/manifest/card identity and refuses
partial datasets or a run ID that already carries different settings.
Run from repo root:
  .venv/bin/python code_benchmark/migrate_vi_multimodel_to_mongo.py --phase main --profile muse-spark-1-3-contributor
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

try:
    from code_benchmark.common import item_key
    from code_benchmark.seed_registries import make_run_id, seed
    from code_benchmark.vi_multimodel import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        item_from_manifest_row,
        load_manifest,
        load_model_profiles,
        load_protocol,
        rebuild_items,
    )
except ImportError:
    from common import item_key
    from seed_registries import make_run_id, seed
    from vi_multimodel import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        item_from_manifest_row,
        load_manifest,
        load_model_profiles,
        load_protocol,
        rebuild_items,
    )

MONGO_URI_DEFAULT = "mongodb://127.0.0.1:27017/"
DB_DEFAULT = "vmlu"


def import_profile(db, profile: dict, phase: str) -> tuple[int, int]:
    run_dir = OUTPUT_DIR / phase / profile["profile_id"]
    run_path = run_dir / "run.json"
    score_path = run_dir / "scores.jsonl"
    summary_path = run_dir / "summary.json"
    if not all(path.is_file() for path in (run_path, score_path, summary_path)):
        raise SystemExit(f"Error: scored run artifacts missing under {run_dir}")
    run_meta = json.loads(run_path.read_text(encoding="utf-8"))
    summary_file = json.loads(summary_path.read_text(encoding="utf-8"))
    protocol = load_protocol()
    manifest = load_manifest(phase)
    if run_meta.get("status") != "complete":
        raise SystemExit(f"Error: refusing incomplete run {run_dir}")
    if run_meta.get("protocol_id") != PROTOCOL_ID or run_meta.get("phase") != phase:
        raise SystemExit(f"Error: run protocol/phase mismatch under {run_dir}")
    card_id = profile["measurement_card_ids"][phase]
    if run_meta.get("profile_id") != profile["profile_id"]:
        raise SystemExit(f"Error: run profile mismatch under {run_dir}")
    if run_meta.get("measurement_card_id") != card_id:
        raise SystemExit(f"Error: run measurement card mismatch under {run_dir}")
    if run_meta.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise SystemExit(f"Error: run item manifest mismatch under {run_dir}")
    if run_meta.get("config_sha256") != summary_file.get("config_sha256"):
        raise SystemExit(f"Error: scored summary config mismatch under {run_dir}")
    if summary_file.get("protocol_id") != protocol["protocol_id"]:
        raise SystemExit(f"Error: summary protocol mismatch under {run_dir}")
    if (summary_file.get("profile_id") != profile["profile_id"]
            or summary_file.get("phase") != phase
            or summary_file.get("measurement_card_id") != card_id
            or summary_file.get("manifest_sha256") != manifest["manifest_sha256"]
            or summary_file.get("measurement_card_hash") != run_meta.get("measurement_card_hash")):
        raise SystemExit(f"Error: summary profile/phase/card/manifest mismatch under {run_dir}")

    item_map = rebuild_items(phase)
    prediction_rows = [
        json.loads(line) for line in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    score_rows = [
        json.loads(line) for line in score_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    score_by_key = {item_key({"dataset": row["dataset_id"], "item_id": row["item_id"]}): row
                    for row in score_rows}
    predictions_by_key = {str(row["run_key"]): row for row in prediction_rows}
    if len(score_by_key) != len(score_rows):
        raise SystemExit(f"Error: duplicate scored item in {score_path}")
    expected_item_keys = {
        item_key({"dataset": row["dataset_id"], "item_id": row["item_id"]})
        for row in manifest["items"]
    }
    expected_run_keys = {
        f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"
        for row in manifest["items"]
    }
    if set(score_by_key) != expected_item_keys or set(predictions_by_key) != expected_run_keys:
        raise SystemExit(f"Error: scored rows or prediction rows differ from manifest under {run_dir}")
    if any(row.get("status") != "complete" for row in predictions_by_key.values()):
        raise SystemExit(f"Error: non-complete prediction found under {run_dir}")
    summaries = {str(row["dataset_id"]): row for row in summary_file.get("datasets", [])}
    expected_datasets = {row["dataset_id"] for row in manifest["items"]}
    if set(summaries) != expected_datasets:
        raise SystemExit(f"Error: scored summary datasets differ from manifest under {run_dir}")
    model_id = profile["model_id"]
    run_count = 0
    item_count = 0

    # Make all run documents first, then item documents, then summaries. Every
    # upsert is keyed by an immutable run_id + source item identity.
    for dataset_id, dataset_summary in summaries.items():
        dataset_rows = [row for row in manifest["items"] if row["dataset_id"] == dataset_id]
        if (len(dataset_rows) != dataset_summary.get("expected_n")
                or dataset_summary.get("status") != "complete"
                or dataset_summary.get("request_status") != "complete"):
            raise SystemExit(f"Error: incomplete denominator for {dataset_id}")
        run_id = make_run_id(model_id, dataset_id, card_id)
        run_meta_existing = db["runs"].find_one({"_id": run_id})
        if run_meta_existing and run_meta_existing.get("config", {}).get("config_sha256") != run_meta["config_sha256"]:
            raise SystemExit(f"Error: {run_id} already exists with different settings; use a new card ID")
        config = {
            **run_meta,
            "config_sha256": run_meta["config_sha256"],
            "api_key_env": profile["api_key_env"],
        }
        db["runs"].update_one(
            {"_id": run_id},
            {"$set": {
                "_id": run_id,
                "model_id": model_id,
                "dataset_id": dataset_id,
                "card_id": card_id,
                "prompt_condition": "omp-single-turn, minimal-system-prompt, no-tools",
                "config": config,
                "measurement_card_hash": run_meta["measurement_card_hash"],
                "n": dataset_summary["expected_n"],
                "source_file": str(score_path),
                "created_at": run_meta.get("finished_at") or datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        kind = "mc" if dataset_summary.get("accuracy") is not None else "reading"
        collection = db["mc_items" if kind == "mc" else "reading_items"]
        docs = []
        for manifest_row in dataset_rows:
            key = f"{dataset_id}:{manifest_row['item_id']}:{manifest_row['replicate_id']}"
            eval_item = item_from_manifest_row(manifest_row, item_map)
            scored = score_by_key.get(item_key({
                "dataset": dataset_id, "item_id": manifest_row["item_id"],
            }))
            prediction = predictions_by_key.get(key)
            if scored is None or prediction is None or prediction.get("status") != "complete":
                raise SystemExit(f"Error: scored output missing for {key}")
            if kind == "mc":
                doc = {
                    "_id": f"{run_id}::{manifest_row['item_id']}",
                    "run_id": run_id,
                    "model_id": model_id,
                    "dataset_id": dataset_id,
                    "item_id": manifest_row["item_id"],
                    "question": eval_item.question,
                    "prompt": eval_item.prompt,
                    "raw_response": prediction["raw_response"],
                    "answer": scored.get("prediction", ""),
                    "gold": eval_item.gold_answer,
                    "correct": int(scored.get("correct", 0)),
                    "measurement_card_hash": run_meta["measurement_card_hash"],
                    "prompt_tokens": prediction.get("prompt_tokens"),
                    "cached_prompt_tokens": prediction.get("cached_prompt_tokens"),
                    "completion_tokens": prediction.get("completion_tokens"),
                    "reasoning_tokens": prediction.get("reasoning_tokens"),
                    "total_tokens": prediction.get("total_tokens"),
                    "latency_s": prediction.get("latency_s"),
                    "finish_reason": prediction.get("finish_reason", ""),
                    "response_model_id": prediction.get("response_model_id", ""),
                    "system_fingerprint": prediction.get("system_fingerprint", ""),
                    "service_tier": prediction.get("service_tier", ""),
                    "request_id": prediction.get("request_id", ""),
                }
            else:
                doc = {
                    "_id": f"{run_id}::{eval_item.source_dataset}:{manifest_row['item_id']}",
                    "run_id": run_id,
                    "model_id": model_id,
                    "dataset_id": dataset_id,
                    "source_dataset": eval_item.source_dataset,
                    "item_id": f"{eval_item.source_dataset}:{manifest_row['item_id']}",
                    "stratum": eval_item.stratum,
                    "gold": eval_item.gold_answer,
                    "raw_response": prediction["raw_response"],
                    "prediction": scored.get("prediction", ""),
                    "em": int(scored.get("em", 0)),
                    "f1": float(scored.get("legacy_final_char_f1", 0)),
                    "token_f1": float(scored.get("token_f1", 0)),
                    "legacy_raw_em": int(scored.get("legacy_raw_em", 0)),
                    "legacy_raw_char_f1": float(scored.get("legacy_raw_char_f1", 0)),
                    "passage_id": eval_item.passage_id,
                    "measurement_card_hash": run_meta["measurement_card_hash"],
                    "prompt_tokens": prediction.get("prompt_tokens"),
                    "cached_prompt_tokens": prediction.get("cached_prompt_tokens"),
                    "completion_tokens": prediction.get("completion_tokens"),
                    "reasoning_tokens": prediction.get("reasoning_tokens"),
                    "total_tokens": prediction.get("total_tokens"),
                    "latency_s": prediction.get("latency_s"),
                    "finish_reason": prediction.get("finish_reason", ""),
                    "response_model_id": prediction.get("response_model_id", ""),
                    "system_fingerprint": prediction.get("system_fingerprint", ""),
                    "service_tier": prediction.get("service_tier", ""),
                    "request_id": prediction.get("request_id", ""),
                }
            docs.append(doc)
        expected_collection_n = collection.count_documents({"run_id": run_id})
        if expected_collection_n not in (0, len(docs)):
            raise SystemExit(
                f"Error: partial existing import {run_id}: db={expected_collection_n}, file={len(docs)}"
            )
        for doc in docs:
            collection.update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
        imported_n = collection.count_documents({"run_id": run_id})
        if imported_n != len(docs):
            raise SystemExit(f"Error: item count mismatch for {run_id}: {imported_n} != {len(docs)}")

        summary_doc = {
            "_id": run_id,
            "run_id": run_id,
            "model_id": model_id,
            "dataset_id": dataset_id,
            "card_id": card_id,
            "measurement_card_hash": run_meta["measurement_card_hash"],
            "n": dataset_summary["expected_n"],
            "protocol_id": PROTOCOL_ID,
            "phase": phase,
            "run_cost": summary_file.get("cost"),
            "token_usage": {
                key: dataset_summary.get(key)
                for key in (
                    "prompt_tokens_known_n", "prompt_tokens_mean",
                    "completion_tokens_known_n", "completion_tokens_mean",
                    "completion_tokens_p50", "completion_tokens_p90", "completion_tokens_max",
                    "reasoning_tokens_known_n", "reasoning_tokens_mean",
                    "reasoning_tokens_p90", "reasoning_tokens_max",
                    "latency_s_p50", "latency_s_p90", "finish_reason_counts", "truncated_n",
                )
            },
        }
        if kind == "mc":
            summary_doc["accuracy_rows"] = dataset_summary.get("accuracy_rows", [])
            summary_doc["ci95"] = dataset_summary.get("ci95")
        else:
            legacy_char = dataset_summary.get("legacy_final_char_f1")
            summary_doc["reading_rows"] = [{
                "dataset": "ALL",
                "n": dataset_summary["expected_n"],
                "em_count": dataset_summary.get("em_count", 0),
                "em": dataset_summary.get("em", 0),
                "char_f1": legacy_char if legacy_char is not None else 0,
                "token_f1": dataset_summary.get("token_f1", 0),
                "em_ci95": dataset_summary.get("em_ci95"),
                "token_f1_ci95": dataset_summary.get("token_f1_ci95"),
                "empty_answer_n": dataset_summary.get("empty_answer_n", 0),
                "legacy_final_em": dataset_summary.get("legacy_final_em"),
                "legacy_final_char_f1": dataset_summary.get("legacy_final_char_f1"),
                "legacy_raw_em": dataset_summary.get("legacy_raw_em"),
                "legacy_raw_char_f1": dataset_summary.get("legacy_raw_char_f1"),
            }]
        db["summaries"].update_one({"_id": run_id}, {"$set": summary_doc}, upsert=True)
        run_count += 1
        item_count += len(docs)
        print(f"  {run_id}: {len(docs)} items")
    return run_count, item_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Import one completed vi-multimodel-v1 phase to Mongo.")
    parser.add_argument("--phase", choices=("main",), required=True,
                        help="pilot is local diagnostic data and is not imported into the headline matrix")
    parser.add_argument("--profile", default="all")
    parser.add_argument("--uri", default=MONGO_URI_DEFAULT)
    parser.add_argument("--db", default=DB_DEFAULT)
    args = parser.parse_args()
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise SystemExit("Error: pymongo missing; install the repo's optional Mongo dependency") from exc
    profiles = load_model_profiles()
    selected = list(profiles.values()) if args.profile == "all" else [profiles.get(args.profile)]
    if any(profile is None for profile in selected):
        parser.error(f"unknown profile: {args.profile}")
    client = MongoClient(args.uri, serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ping")
        db = client[args.db]
        seed(db)
        run_count = item_count = 0
        for profile in selected:
            runs, items = import_profile(db, profile, args.phase)
            run_count += runs
            item_count += items
        print(f"imported runs={run_count} items={item_count} -> {args.db}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
