#!/usr/bin/env python3
"""Generate blind batch JSON files for remaining rollout domains."""
import glob
import json
import csv
from pathlib import Path

from code_benchmark.common import SQUAD_DEFAULT, DROP_DEFAULT, MANIFEST_DEFAULT
from code_benchmark.run_reading_eval import load_manifest, index_sources, join_manifest

# 1. Generate medicine batches (40:60, 60:80, 80:100)
med_rows = []
with open("v_bench/public-test.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("domain") == "medicine":
            med_rows.append({
                "id": r["id"],
                "domain": "medicine",
                "track": "mc",
                "question": r["question"],
                "choices": r["choices"]
            })

for idx, (s, e) in enumerate([(40, 60), (60, 80), (80, 100)], start=3):
    batch = med_rows[s:e]
    p = f"all_res/antigravity_gemini/batch_medicine_{idx}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    start_id = batch[0]["id"]
    end_id = batch[-1]["id"]
    print(f"Generated {p}: {len(batch)} items ({start_id} -> {end_id})")

# 2. Generate CS batches (20:40, 40:60, 60:80, 80:100)
cs_rows = []
with open("v_bench/public-test.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("domain") == "computer_science":
            cs_rows.append({
                "id": r["id"],
                "domain": "computer_science",
                "track": "mc",
                "question": r["question"],
                "choices": r["choices"]
            })

for idx, (s, e) in enumerate([(20, 40), (40, 60), (60, 80), (80, 100)], start=2):
    batch = cs_rows[s:e]
    p = f"all_res/antigravity_gemini/batch_cs_{idx}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    start_id = batch[0]["id"]
    end_id = batch[-1]["id"]
    print(f"Generated {p}: {len(batch)} items ({start_id} -> {end_id})")

# 3. Generate VMLU Legal Batch 3 (remaining 8 items: 38-0012 to 38-0019)
valid_legal = []
legal_existing = set()
for f in sorted(glob.glob("all_res/antigravity_gemini/results_batch_vmlu_legal_*.csv")):
    for r in csv.DictReader(open(f, encoding="utf-8")):
        legal_existing.add(r["id"])

with open("vmlu_mqa_v1.5/valid.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        sid = int(r["id"].split("-")[0])
        if sid in {37, 38, 39, 40, 41} and r["id"] not in legal_existing:
            valid_legal.append({
                "id": r["id"],
                "domain": "legal",
                "track": "mc",
                "question": r["question"],
                "choices": r["choices"]
            })

p = "all_res/antigravity_gemini/batch_vmlu_legal_3.json"
with open(p, "w", encoding="utf-8") as f:
    json.dump(valid_legal, f, ensure_ascii=False, indent=2)
start_id = valid_legal[0]["id"]
end_id = valid_legal[-1]["id"]
print(f"Generated {p}: {len(valid_legal)} items ({start_id} -> {end_id})")

# 4. Generate SQuAD Batches (100:120, 120:140, 140:160, 160:180, 180:200)
manifest = load_manifest(MANIFEST_DEFAULT)
idx_sources = index_sources(SQUAD_DEFAULT, DROP_DEFAULT)
joined = join_manifest(manifest, idx_sources)
squad_joined = [r for r in joined if r["dataset"] == "squad"]

for b_idx, (s, e) in enumerate([(100, 120), (120, 140), (140, 160), (160, 180), (180, 200)], start=6):
    slice_rows = squad_joined[s:e]
    batch = []
    for r in slice_rows:
        words = len(r["context"].split())
        batch.append({
            "dataset": "squad",
            "item_id": int(r["item_id"]),
            "stratum": r["stratum"],
            "question": r["question"],
            "context": r["context"],
            "context_words": words
        })
    p = f"all_res/antigravity_gemini/batch_squad_{b_idx}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    start_id = batch[0]["item_id"]
    end_id = batch[-1]["item_id"]
    print(f"Generated {p}: {len(batch)} items (item_id {start_id} -> {end_id})")
