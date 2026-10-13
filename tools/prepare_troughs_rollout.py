#!/usr/bin/env python3
"""Prepare batch JSON files for the 3 remaining unrun V-Bench troughs:
culture, literature, psychology (100 questions each -> 5 batches of 20).
"""
import json
import os

def extract_domain_batches(domain_name, total_target=100, batch_size=20):
    items = []
    with open("v_bench/public-test.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("domain") == domain_name:
                items.append({
                    "id": r["id"],
                    "domain": domain_name,
                    "track": "mc",
                    "question": r["question"],
                    "choices": r["choices"]
                })
                if len(items) == total_target:
                    break

    num_batches = total_target // batch_size
    out_files = []
    for b_idx in range(num_batches):
        batch = items[b_idx * batch_size : (b_idx + 1) * batch_size]
        p = f"all_res/antigravity_gemini/batch_{domain_name}_{b_idx + 1}.json"
        with open(p, "w", encoding="utf-8") as out_f:
            json.dump(batch, out_f, ensure_ascii=False, indent=2)
        s_id = batch[0]["id"]
        e_id = batch[-1]["id"]
        print(f"Generated {p}: {len(batch)} items ({s_id} -> {e_id})")
        out_files.append(p)
    return out_files

if __name__ == "__main__":
    for dom in ["culture", "literature", "psychology"]:
        print(f"\n--- Extracting {dom} ---")
        extract_domain_batches(dom, total_target=100, batch_size=20)
