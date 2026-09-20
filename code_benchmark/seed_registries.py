"""Seed the `models` + `datasets` registries (spec: results-backend).

Writes to Mongo local (`vmlu-mongo:27017`, db `vmlu`); idempotent upserts.

  .venv/bin/python code_benchmark/seed_registries.py [--uri ...] [--db vmlu]

Canonical rules (design D1/D2, pinned here):
  model_id   = lower(NFD-strip(sanitize_model(model))) with [^a-z0-9]+ -> '-'
  dataset_id = fixed vocabulary (no free text)
  run_id     = {model_id}__{dataset_id}__{card_id}
"""

from __future__ import annotations

import argparse
import hashlib
import re
import unicodedata
from pathlib import Path

try:
    from code_benchmark.common import sanitize_model
except ImportError:
    from common import sanitize_model


MONGO_URI_DEFAULT = "mongodb://127.0.0.1:27017/"
DB_DEFAULT = "vmlu"


def canonical_model_id(model: str) -> str:
    """One canonical id per model (design D1): lowercase, hyphen-joined, URL-safe.

    Examples: Qwen3.5-9B-28K -> qwen3-5-9b-28k; qwen38-nothink -> qwen38-nothink;
    Qwen3_8-27B-Q4_K_M_gguf -> qwen3-8-27b-q4-k-m-gguf.
    """
    t = sanitize_model(model)
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t


def make_run_id(model_id: str, dataset_id: str, card_id: str) -> str:
    """Composite run id (design D3): {model_id}__{dataset_id}__{card_id}."""
    for part_name, part in (("model_id", model_id), ("dataset_id", dataset_id), ("card_id", card_id)):
        if not part or "__" in part:
            raise ValueError(f"bad {part_name} for run_id: {part!r}")
    return f"{model_id}__{dataset_id}__{card_id}"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Registry payloads ──────────────────────────────────────────────
# dir_slugs: every observed CSV directory spelling for the model (D1).
# endpoint_ids: endpoint labels the model was served from (informational).
MODELS = [
    {
        "_id": "qwen3-5-9b-28k",
        "display_name": "Qwen3.5-9B-28K",
        "dir_slugs": ["Qwen3_5-9B-28K"],
        "endpoint_ids": ["iec-uit"],
        "params": "9B",
        "quantization": "Q6_K",
        "endpoint": "https://llmapi.iec-uit.com/v1",
        "notes": "Backend Qwen3.5-9B-Q6_K.gguf; non-thinking (MC-4). Primary model MC-7..MC-13.",
    },
    {
        "_id": "qwen38-nothink",
        "display_name": "qwen38-nothink",
        "dir_slugs": ["qwen38-nothink"],
        "endpoint_ids": ["ngrok-tunnel"],
        "params": "27B",
        "quantization": "Q4_K_M",
        "endpoint": "https://porridge-livable-umbrella.ngrok-free.dev/v1 (FROM qwen3.8:27b-q4_K_M, think false)",
        "notes": "Compare model for legal-MC (MC-6, 82.88%).",
    },
    {
        "_id": "qwen3-8-27b-q4-k-m-gguf",
        "display_name": "Qwen3_8-27B-Q4_K_M_gguf",
        "dir_slugs": ["Qwen3_8-27B-Q4_K_M_gguf"],
        "endpoint_ids": ["iec-uit"],
        "params": "27B",
        "quantization": "Q4_K_M",
        "endpoint": "https://llmapi.iec-uit.com/v1",
        "notes": "Compare model for VMLU-MQA all_gold + reading-400 + V-Bench (left endpoint 2026-09-12, MC-4).",
    },
]


def dataset_docs() -> list[dict]:
    """Fixed vocabulary (design D2); sha256 computed from the tracked sources."""
    specs = [
        # (dataset_id, benchmark, split, n, source_file, gold_kind, manifest_path)
        ("vmlu-mqa-valid", "VMLU-MQA", "valid", 744, "vmlu_mqa_v1.5/valid.jsonl", "file", None),
        ("vmlu-mqa-dev", "VMLU-MQA", "dev", 303, "vmlu_mqa_v1.5/dev.jsonl", "file", None),
        ("vmlu-mqa-all-gold", "VMLU-MQA", "all_gold", 1047, "vmlu_mqa_v1.5/all_gold.jsonl", "file", None),
        ("vmlu-mqa-test", "VMLU-MQA", "test", 9833, "vmlu_mqa_v1.5/test.jsonl", "withheld", None),
        ("vbench-public-test", "V-Bench", "public-test", 9141, "v_bench/public-test.jsonl", "withheld", None),
        ("reading-400", "reading", "eval-400", 400, "data/eval_set_manifest.csv", "reviewed", "data/eval_set_manifest.csv"),
        ("legal-mc-146", "VLSP2025-LegalSLM", "multichoice", 146, "v_legal_slsp/legal_slm/multichoice.jsonl", "file",
         "data/legal_slm_multichoice_manifest.json"),
        ("legal-nli-150", "VLSP2025-LegalSLM", "nli", 150, "v_legal_slsp/legal_slm/nli.jsonl", "file",
         "data/legal_nli_manifest.json"),
        ("bidlqa-val", "ViBidLQA", "val", 482, "v_legal_slsp/bidlqa/ViBidLQA_val.jsonl", "file",
         "data/bidlqa_val_manifest.csv"),
        ("bidlqa-test", "ViBidLQA", "test", 603, "v_legal_slsp/bidlqa/ViBidLQA_test.jsonl", "file",
         "data/bidlqa_test_manifest.csv"),
    ]
    docs = []
    for dataset_id, benchmark, split, n, source_file, gold_kind, manifest_path in specs:
        src = Path(source_file)
        if not src.exists():
            raise SystemExit(f"Error: dataset source missing: {source_file}")
        docs.append({
            "_id": dataset_id,
            "benchmark": benchmark,
            "split": split,
            "n": n,
            "source_file": source_file,
            "source_sha256": sha256_file(src),
            "gold_kind": gold_kind,
            "manifest_path": manifest_path,
        })
    return docs


def seed(db) -> dict[str, int]:
    """Upsert both registries. Returns {'models': N, 'datasets': N}."""
    n_models = 0
    for doc in MODELS:
        got = canonical_model_id(doc["display_name"])
        for slug in doc["dir_slugs"]:
            if canonical_model_id(slug) != doc["_id"]:
                raise SystemExit(f"Error: dir_slug {slug!r} -> {canonical_model_id(slug)!r} != {doc['_id']!r}")
        if got != doc["_id"] and canonical_model_id(doc["_id"]) != doc["_id"]:
            raise SystemExit(f"Error: model {doc['display_name']!r} -> {got!r} != {doc['_id']!r}")
        db["models"].update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
        n_models += 1
    n_datasets = 0
    for doc in dataset_docs():
        db["datasets"].update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
        n_datasets += 1
    return {"models": n_models, "datasets": n_datasets}


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed models + datasets registries to Mongo.")
    ap.add_argument("--uri", default=MONGO_URI_DEFAULT)
    ap.add_argument("--db", default=DB_DEFAULT)
    args = ap.parse_args()
    try:
        from pymongo import MongoClient
    except ImportError as e:
        raise SystemExit("Error: pymongo missing — run: uv pip install --python .venv/bin/python pymongo") from e
    client = MongoClient(args.uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as e:
        raise SystemExit(f"Error: cannot reach Mongo at {args.uri}: {e}") from e
    counts = seed(client[args.db])
    print(f"seeded models={counts['models']} datasets={counts['datasets']} -> {args.db}")


if __name__ == "__main__":
    main()
