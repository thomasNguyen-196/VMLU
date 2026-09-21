"""One-shot migration: seed registries -> import finals -> upsert runs/items/summaries.

Reads the per-model finals already on disk under all_res/ollama_result/<dir>/
and mirrors them into Mongo (db `vmlu`), stamping every run/item with the
canonical `model_id` + `dataset_id` (design D4). Idempotent upserts: re-runs
are safe; `--drop` wipes the migrated collections first (opt-in).

Provenance rule (frozen by the repo's measurement history): the numbers on
disk are the published ones. The migration NEVER recomputes accuracy/EM —
it copies per-item rows + the committed accuracy/summary rows verbatim and
refuses to complete when row-counts or identity disagree (spec: Migration
verification).

  .venv/bin/python code_benchmark/migrate_results_to_mongo.py [--uri ...] [--db vmlu] [--drop] [--only <model_id>]

Run -> item mapping (design D2/D3; dataset_id is the evaluated SET, not the
file that happened to hold it):
  full_evaluation_Qwen3_5-9B-28K.csv        -> vmlu-mqa-all-gold / MC-9
  raw_result_9833_Qwen3_5-9B-28K.csv        -> vmlu-mqa-test      / MC-7
  vbench_result_5141_Qwen3_5-9B-28K.csv     -> vbench-public-test / MC-8
  reading_scores_Qwen3_5-9B-28K.csv         -> reading-400        / MC-3
  full_evaluation_legal_Qwen3_5-9B-28K.csv  -> legal-mc-146       / MC-10
  full_evaluation_nli_Qwen3_5-9B-28K.csv    -> legal-nli-150      / MC-13
  reading_scores_bidlqa_val_Qwen3_5-9B-28K  -> bidlqa-val         / MC-12
  reading_scores_bidlqa_test_Qwen3_5-9B-28K -> bidlqa-test        / MC-11
  full_evaluation_vm14k_Qwen3_5-9B-28K.csv  -> vm14k-public-12488 / MC-14b
  (same shapes for the gguf dir; qwen38-nothink carries legal-mc-146 / MC-6)

The Mongo client is accepted as a dependency (design D5) so unit tests run
the same code against a fake adapter.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

try:
    from code_benchmark.common import read_csv_checked
    from code_benchmark.seed_registries import canonical_model_id, make_run_id, seed
except ImportError:
    from common import read_csv_checked
    from seed_registries import canonical_model_id, make_run_id, seed


MONGO_URI_DEFAULT = "mongodb://127.0.0.1:27017/"
DB_DEFAULT = "vmlu"
RESULTS_DIR = Path("all_res/ollama_result")
MEASUREMENT_CARD = Path("measurement_card.md")

# (dir_slug, model_id, [(finals filename, dataset_id, card_id, kind)])
# kind: mc | vbench | reading  -> target item collection + summary source.
# MC-9's committed dev number (229/303) came from the dev-run checkpoint
# (raw_result_303, answer A on 54-0002); the later all_gold overwrite flipped
# that row to C. CSVs on disk are the source of truth — see module docstring.
MIGRATION_PLAN = [
    ("Qwen3_5-9B-28K", "qwen3-5-9b-28k", [
        ("full_evaluation_Qwen3_5-9B-28K.csv", "vmlu-mqa-all-gold", "MC-9", "mc"),
        ("raw_result_9833_Qwen3_5-9B-28K.csv", "vmlu-mqa-test", "MC-7", "mc"),
        ("vbench_result_5141_Qwen3_5-9B-28K.csv", "vbench-public-test", "MC-8", "vbench"),
        ("reading_scores_Qwen3_5-9B-28K.csv", "reading-400", "MC-3", "reading"),
        ("full_evaluation_legal_Qwen3_5-9B-28K.csv", "legal-mc-146", "MC-10", "mc"),
        ("full_evaluation_nli_Qwen3_5-9B-28K.csv", "legal-nli-150", "MC-13", "mc"),
        ("reading_scores_bidlqa_val_Qwen3_5-9B-28K.csv", "bidlqa-val", "MC-12", "reading"),
        ("reading_scores_bidlqa_test_Qwen3_5-9B-28K.csv", "bidlqa-test", "MC-11", "reading"),
        ("full_evaluation_vm14k_Qwen3_5-9B-28K.csv", "vm14k-public-12488", "MC-14b", "mc"),
    ]),
    ("Qwen3_8-27B-Q4_K_M_gguf", "qwen3-8-27b-q4-k-m-gguf", [
        ("full_evaluation_Qwen3_8-27B-Q4_K_M_gguf.csv", "vmlu-mqa-all-gold", "MC-1", "mc"),
        ("vbench_result_5141_Qwen3_8-27B-Q4_K_M_gguf.csv", "vbench-public-test", "MC-2", "vbench"),
        ("reading_scores_Qwen3_8-27B-Q4_K_M_gguf.csv", "reading-400", "MC-3", "reading"),
    ]),
    ("qwen38-nothink", "qwen38-nothink", [
        ("full_evaluation_qwen38-nothink.csv", "legal-mc-146", "MC-6", "mc"),
    ]),
]

ITEM_COLLECTION = {"mc": "mc_items", "vbench": "vbench_items", "reading": "reading_items"}

# Runner configs per card (temperature/seed/max-tokens/workers/prompt_style).
RUN_CONFIGS = {
    "MC-1": {"temperature": 0.0, "seed": 42, "max_tokens": 4, "workers": 4, "prompt_style": "build_prompt"},
    "MC-2": {"temperature": 0.0, "seed": 42, "max_tokens": 512, "workers": 4, "prompt_style": "minimal"},
    "MC-3": {"temperature": 0.0, "seed": 42, "max_tokens": 48, "workers": 4, "prompt_style": "build_reading_prompt"},
    "MC-6": {"temperature": 0.0, "seed": 42, "max_tokens": 512, "workers": 4, "prompt_style": "build_prompt"},
    "MC-7": {"temperature": 0.0, "seed": 42, "max_tokens": 4, "workers": 4, "prompt_style": "build_prompt"},
    "MC-8": {"temperature": 0.0, "seed": 42, "max_tokens": 512, "workers": 4, "prompt_style": "minimal"},
    "MC-9": {"temperature": 0.0, "seed": 42, "max_tokens": 4, "workers": 4, "prompt_style": "build_prompt"},
    "MC-10": {"temperature": 0.0, "seed": 42, "max_tokens": 4, "workers": 4, "prompt_style": "build_prompt"},
    "MC-11": {"temperature": 0.0, "seed": 42, "max_tokens": 48, "workers": 4, "prompt_style": "build_reading_prompt"},
    "MC-12": {"temperature": 0.0, "seed": 42, "max_tokens": 48, "workers": 4, "prompt_style": "build_reading_prompt"},
    "MC-13": {"temperature": 0.0, "seed": 42, "max_tokens": 4, "workers": 4, "prompt_style": "build_prompt"},
    "MC-14b": {"temperature": 0.0, "seed": 42, "max_tokens": 4, "workers": 8, "prompt_style": "build_prompt"},
}


def measurement_card_hash(path: Path = MEASUREMENT_CARD) -> str:
    if not path.exists():
        raise SystemExit(f"Error: {path} missing — every stored run must cite a measurement card")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_finals_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"Error: empty finals file: {path}")
    return rows


def mc_item(row: dict, *, run_id: str, model_id: str, dataset_id: str, card_hash: str) -> dict:
    item_id = str(row.get("id", "")).strip()
    if not item_id:
        raise SystemExit(f"Error: MC row without id in run {run_id}: {str(row)[:160]}")
    return {
        "_id": f"{run_id}::{item_id}",
        "run_id": run_id, "model_id": model_id, "dataset_id": dataset_id,
        "item_id": item_id,
        "question": row.get("question", ""), "prompt": row.get("prompt", ""),
        "raw_response": row.get("raw_response", ""), "answer": row.get("answer", ""),
        "gold": row.get("gold_answer", ""),
        "correct": int(row["correct"]) if str(row.get("correct", "")).strip() != "" else None,
        "measurement_card_hash": card_hash,
    }


def vbench_item(row: dict, *, run_id: str, model_id: str, dataset_id: str, card_hash: str) -> dict:
    item_id = str(row.get("id", "")).strip()
    if not item_id:
        raise SystemExit(f"Error: V-Bench row without id in run {run_id}: {str(row)[:160]}")
    return {
        "_id": f"{run_id}::{item_id}",
        "run_id": run_id, "model_id": model_id, "dataset_id": dataset_id,
        "item_id": item_id,
        "domain": row.get("domain", ""), "track": row.get("track", ""),
        "question": row.get("question", ""),
        "raw_response": row.get("raw_response", ""), "answer": row.get("answer", ""),
        "measurement_card_hash": card_hash,
    }


def reading_item(row: dict, *, run_id: str, model_id: str, dataset_id: str, card_hash: str) -> dict:
    dataset = str(row.get("dataset", "")).strip()
    item_id = str(row.get("item_id", "")).strip()
    if not item_id:
        raise SystemExit(f"Error: reading row without item_id in run {run_id}: {str(row)[:160]}")
    return {
        "_id": f"{run_id}::{dataset}:{item_id}",
        "run_id": run_id, "model_id": model_id, "dataset_id": dataset_id,
        "dataset": dataset, "item_id": f"{dataset}:{item_id}",
        "stratum": row.get("stratum", ""),
        "gold": row.get("gold_answer", ""),
        "raw_response": row.get("raw_response", ""), "prediction": row.get("prediction", ""),
        "em": int(row["em"]) if str(row.get("em", "")).strip() != "" else None,
        "f1": float(row["f1"]) if str(row.get("f1", "")).strip() != "" else None,
        "measurement_card_hash": card_hash,
    }


BUILDERS = {"mc": mc_item, "vbench": vbench_item, "reading": reading_item}


def accuracy_summary_rows(model_dir: Path, dir_slug: str) -> dict[str, list[dict]]:
    """accuracy_<infix>_<slug>.csv rows keyed by dataset: the committed aggregates."""
    out: dict[str, list[dict]] = {}
    for infix, dataset_id in (("", "vmlu-mqa-all-gold"), ("_legal", "legal-mc-146"), ("_nli", "legal-nli-150"),
                              ("_vm14k", "vm14k-public-12488")):
        for cand in (f"accuracy{infix}_{dir_slug}.csv", f"accuracy_{dir_slug}.csv"):
            path = model_dir / cand
            if path.exists():
                out[dataset_id] = read_csv_checked(path, required={"level", "name", "n", "correct"},
                                                   label=f"accuracy{infix}")
                break
    return out


def reading_summary_rows(model_dir: Path, filename: str) -> list[dict]:
    path = model_dir / filename
    if not path.exists():
        return []
    return read_csv_checked(path, required={"dataset", "n", "em_count", "em", "char_f1"},
                            label="reading_summary")


def migrate(db, *, only: str | None = None, card_hash: str | None = None) -> dict[str, int]:
    """Seed registries, import every planned finals file, verify counts + identity.

    Returns {"runs": R, "items": N}. Raises SystemExit naming the offending
    file/count on any mismatch; never marks a partial import complete.
    """
    seed(db)
    card_hash = card_hash or measurement_card_hash()
    counts = {"runs": 0, "items": 0}
    for dir_slug, model_id, files in MIGRATION_PLAN:
        if only and model_id != only:
            continue
        if canonical_model_id(dir_slug) != model_id:
            raise SystemExit(f"Error: dir {dir_slug!r} -> {canonical_model_id(dir_slug)!r} != {model_id!r}")
        model_dir = RESULTS_DIR / dir_slug
        if not model_dir.is_dir():
            raise SystemExit(f"Error: model dir missing: {model_dir}")
        acc = accuracy_summary_rows(model_dir, dir_slug)
        for filename, dataset_id, card_id, kind in files:
            path = model_dir / filename
            if not path.exists():
                raise SystemExit(f"Error: finals file missing: {path}")
            rows = read_finals_csv(path)
            run_id = make_run_id(model_id, dataset_id, card_id)
            build = BUILDERS[kind]
            docs = [build(r, run_id=run_id, model_id=model_id, dataset_id=dataset_id,
                          card_hash=card_hash) for r in rows]
            for d in docs:
                if not d.get("model_id") or not d.get("dataset_id"):
                    raise SystemExit(f"Error: doc without identity in {path}: {d.get('_id')}")
            seen = set()
            for d in docs:
                if d["_id"] in seen:
                    raise SystemExit(f"Error: duplicate item {d['_id']} in {path}")
                seen.add(d["_id"])
            config = RUN_CONFIGS.get(card_id)
            if config is None:
                raise SystemExit(f"Error: no runner config for card {card_id}")
            db["runs"].update_one(
                {"_id": run_id},
                {"$set": {
                    "_id": run_id, "model_id": model_id, "dataset_id": dataset_id,
                    "card_id": card_id, "prompt_condition": config["prompt_style"],
                    "config": config, "measurement_card_hash": card_hash,
                    "n": len(docs), "source_file": str(path),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True)
            coll = db[ITEM_COLLECTION[kind]]
            for d in docs:
                coll.update_one({"_id": d["_id"]}, {"$set": d}, upsert=True)
            got = coll.count_documents({"run_id": run_id})
            if got != len(docs):
                raise SystemExit(f"Error: count mismatch for {path}: file={len(docs)} db={got}")
            summary: dict = {"_id": run_id, "run_id": run_id, "model_id": model_id,
                             "dataset_id": dataset_id, "card_id": card_id,
                             "measurement_card_hash": card_hash, "n": len(docs)}
            if kind == "mc" and dataset_id in acc:
                summary["accuracy_rows"] = acc[dataset_id]
            elif kind == "reading":
                slug = filename.removeprefix("reading_scores").removesuffix(".csv").lstrip("_")
                summary["reading_rows"] = reading_summary_rows(model_dir, f"reading_summary_{slug}.csv")
            elif kind == "vbench":
                valid_path = model_dir / f"vbench_valid_summary_{dir_slug}.csv"
                if valid_path.exists():
                    summary["valid_rows"] = read_csv_checked(
                        valid_path, required={"track", "domain", "n", "valid"}, label="vbench_valid")
                server_path = model_dir / f"vbench_server_scores_{dir_slug}.csv"
                if server_path.exists():
                    summary["server_rows"] = read_csv_checked(
                        server_path, required={"domain", "track", "score", "correct", "total"},
                        label="vbench_server")
            db["summaries"].update_one({"_id": run_id}, {"$set": summary}, upsert=True)
            counts["runs"] += 1
            counts["items"] += len(docs)
            print(f"  {run_id}: {len(docs)} items <- {path}")
    for coll_name in ("mc_items", "reading_items", "vbench_items"):
        try:
            db[coll_name].create_index([("run_id", 1), ("item_id", 1)], unique=True)
        except Exception as e:  # fake adapters in unit tests have no index support
            print(f"  note: index skipped on {coll_name}: {e}")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Migrate per-model finals CSVs to Mongo.")
    ap.add_argument("--uri", default=MONGO_URI_DEFAULT)
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--drop", action="store_true", help="wipe runs/items/summaries first (opt-in)")
    ap.add_argument("--only", default=None, help="migrate one canonical model_id only")
    args = ap.parse_args()
    try:
        from pymongo import MongoClient
    except ImportError as e:
        raise SystemExit("Error: pymongo missing — run: uv pip install --python .venv/bin/python pymongo") from e
    client = MongoClient(args.uri, serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ping")
    except Exception as e:
        raise SystemExit(f"Error: cannot reach Mongo at {args.uri}: {e}") from e
    db = client[args.db]
    if args.drop:
        for name in ("runs", "mc_items", "reading_items", "vbench_items", "summaries"):
            db[name].drop()
        print(f"dropped runs/items/summaries in {args.db}")
    if args.only and args.only not in {m for _, m, _ in MIGRATION_PLAN}:
        raise SystemExit(f"Error: --only {args.only!r} not in migration plan")
    counts = migrate(db, only=args.only)
    total_items = sum(db[c].count_documents({}) for c in ("mc_items", "reading_items", "vbench_items"))
    print(f"migrated runs={counts['runs']} items={counts['items']} (db total items={total_items})")
    print("row-count + identity gates: PASS (0 partial)")


if __name__ == "__main__":
    main()
