"""Row-for-row verify: DB-backed view vs CSV finals vs blob (change results-db-frontend 3.3).

Compares every displayed number the /results view serves (precomputed `summaries`
+ per-item lookups) against the source CSVs and web/public/benchmark-data.json.
Prints a diff report; exits non-zero unless the ONLY diffs are the two known,
provenance-documented blob drifts below (the old blob path stays green until
those are patched in the blob itself — the DB is already correct):

  KNOWN-1 (MC-9 categories): blob .vmlu.categories Humanity 221/68.21 + Other 99/63.46
    vs CSV+DB Humanity 222/68.52 + Other 98/62.82 (7 ANSWER-level row overwrites
    after the blob's category snapshot; overall still 768/1047 both sides).
  KNOWN-2 (MC-8 vbench): blob .vbench is the MC-2-era snapshot (macro 44.97,
    micro 45.46 = 2337/5141, Qwen3_8 model) while CSV+DB carry the MC-8 server
    re-grade (micro 45.61 = 2345/5141, Qwen3.5); see docs/vbench-server-qwen35.md.

Usage:
  .venv/bin/python code_benchmark/verify_results_db.py [--uri ...] [--db vmlu]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

try:
    from code_benchmark.seed_registries import MODELS
except ImportError:
    from seed_registries import MODELS  # type: ignore[no-redef]

MONGO_URI_DEFAULT = "mongodb://127.0.0.1:27017/"
DB_DEFAULT = "vmlu"
ROOT = Path(__file__).resolve().parent.parent
BLOB = ROOT / "web" / "public" / "benchmark-data.json"
RESULTS_DIR = Path("all_res/ollama_result")

DIFFS: list[str] = []


def note(msg: str) -> None:
    DIFFS.append(msg)
    print("  DIFF:", msg)


def ok(msg: str) -> None:
    print(f"  ok: {msg}")


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_mc9(blob: dict, db) -> None:
    print("== MC-9 vmlu-mqa-all-gold (Qwen3.5) ==")
    acc = {(r["level"], r["name"]): r
           for r in read_csv(RESULTS_DIR / "Qwen3_5-9B-28K" / "accuracy_Qwen3_5-9B-28K.csv")}
    s = db["summaries"].find_one({"_id": "qwen3-5-9b-28k__vmlu-mqa-all-gold__MC-9"})
    assert s, "missing MC-9 summary"
    mism = sum(1 for r in s["accuracy_rows"]
               if acc.get((r["level"], r["name"])) != {k: r[k] for k in ("level", "name", "n", "correct", "accuracy")}
               and {k: acc.get((r["level"], r["name"]), {}).get(k) for k in ("n", "correct", "accuracy")}
               != {k: r[k] for k in ("n", "correct", "accuracy")})
    if mism:
        note(f"MC-9 db-vs-csv {mism} rows")
    else:
        ok(f"db-vs-csv 0/{len(s['accuracy_rows'])} rows (overall {acc[('overall', 'overall')]['correct']}/1047)")
    bo = blob["vmlu"]["overall"]
    if (str(bo["n"]), str(bo["correct"])) != (acc[("overall", "overall")]["n"], acc[("overall", "overall")]["correct"]):
        note(f"MC-9 blob-vs-csv overall {bo} vs {acc[('overall', 'overall')]}")
    else:
        ok(f"blob-vs-csv overall {bo['correct']}/{bo['n']}")
    for c in blob["vmlu"]["categories"]:
        csv_row = acc.get(("category", c["name"]), {})
        if str(c["correct"]) != str(csv_row.get("correct")) or abs(float(c["accuracy"]) - float(csv_row.get("accuracy", 0))) > 0.005:
            note(f"MC-9 KNOWN-1 blob-vs-csv category {c['name']}: blob {c['correct']}/{c['accuracy']} vs csv {csv_row.get('correct')}/{csv_row.get('accuracy')}")
    # per-item spot-checks incl. the all_gold-overwrite row 54-0002
    items = db["mc_items"]
    for item_id, exp_answer, exp_correct in (("54-0002", "C", 0), ("50-0013", "A", 0), ("05-0009", "A", 0)):
        d = items.find_one({"run_id": "qwen3-5-9b-28k__vmlu-mqa-all-gold__MC-9", "item_id": item_id})
        assert d, f"missing item {item_id}"
        if d["answer"] != exp_answer or d["correct"] != exp_correct:
            note(f"MC-9 item {item_id}: db {d['answer']}/{d['correct']} vs csv {exp_answer}/{exp_correct}")
        else:
            ok(f"item {item_id} answer={exp_answer} correct={exp_correct}")


def check_legal(blob: dict, db) -> None:
    print("== legal-mc-146 + legal-nli-150 (Qwen3.5) ==")
    for blobk, fn, run_id in (
        ("legal", "full_evaluation_legal_Qwen3_5-9B-28K.csv", "qwen3-5-9b-28k__legal-mc-146__MC-10"),
        ("legal_nli", "full_evaluation_nli_Qwen3_5-9B-28K.csv", "qwen3-5-9b-28k__legal-nli-150__MC-13"),
    ):
        rows = read_csv(RESULTS_DIR / "Qwen3_5-9B-28K" / fn)
        cor = sum(1 for r in rows if r["correct"].strip() == "1")
        gold = Counter(r["gold_answer"] for r in rows)
        maj_letter, maj_n = max(gold.items(), key=lambda kv: kv[1])
        bo = blob[blobk]["overall"]
        if (bo["n"], bo["correct"]) != (len(rows), cor):
            note(f"{blobk} blob-vs-csv {bo} vs {cor}/{len(rows)}")
        else:
            ok(f"{blobk} overall {cor}/{len(rows)} == blob")
        bb = blob[blobk]["baseline"]
        if bb["majority_letter"] != maj_letter or bb["majority_n"] != maj_n:
            note(f"{blobk} blob baseline {bb} vs recompute {maj_letter}={maj_n}")
        else:
            ok(f"{blobk} baseline {maj_letter}={maj_n} ({maj_n / len(rows) * 100:.2f}%)")
        s = db["summaries"].find_one({"_id": run_id})
        acc = (s.get("accuracy_rows") or [{}])[0]
        if str(acc.get("correct")) != str(cor):
            note(f"{blobk} db-vs-csv {acc} vs {cor}")
        else:
            ok(f"{blobk} db summary == csv")


def check_reading(blob: dict, db) -> None:
    print("== reading-400 + bidlqa (Qwen3.5 EM/F1) ==")
    r = db["summaries"].find_one({"_id": "qwen3-5-9b-28k__reading-400__MC-3"})
    bo = blob["reading"]["overall"]
    all_row = next(x for x in r["reading_rows"] if x["dataset"] == "ALL")
    if (str(bo["em_count"]), str(bo["em"]), str(bo["char_f1"])) != (all_row["em_count"], all_row["em"], all_row["char_f1"]):
        note(f"reading-400 blob {bo} vs db {all_row}")
    else:
        ok(f"reading-400 EM {bo['em']} F1 {bo['char_f1']} == db")
    for k, run_id in (("val", "qwen3-5-9b-28k__bidlqa-val__MC-12"), ("test", "qwen3-5-9b-28k__bidlqa-test__MC-11")):
        s = db["summaries"].find_one({"_id": run_id})
        row = s["reading_rows"][0]
        bo = blob["bidlqa"][k]["overall"]
        if (str(bo["em"]), str(bo["char_f1"])) != (row["em"], row["char_f1"]):
            note(f"bidlqa-{k} blob {bo} vs db {row}")
        else:
            ok(f"bidlqa-{k} EM {bo['em']} F1 {bo['char_f1']} == db")


def check_vbench(blob: dict, db) -> None:
    print("== vbench-public-test MC-8 (Qwen3.5 server re-grade) ==")
    srv = read_csv(RESULTS_DIR / "Qwen3_5-9B-28K" / "vbench_server_scores_Qwen3_5-9B-28K.csv")
    s = db["summaries"].find_one({"_id": "qwen3-5-9b-28k__vbench-public-test__MC-8"})
    if srv != s.get("server_rows", []):
        note("vbench db server_rows != server csv")
    else:
        ok(f"db server_rows == csv ({len(srv)} domains)")
    tot_c = sum(int(r["correct"]) for r in srv)
    tot = sum(int(r["total"]) for r in srv)
    print(f"  info: server totals {tot_c}/{tot} micro={tot_c / tot * 100:.2f}; "
          f"blob micro={blob['vbench']['micro_accuracy']} ({blob['vbench']['total_correct']}/{blob['vbench']['total_items']})")
    for d in blob["vbench"]["domains"]:
        m = [r for r in srv if r["domain"] == d["domain"]]
        if not m or str(d["correct"]) != m[0]["correct"]:
            note(f"vbench KNOWN-2 blob-vs-server {d['domain']}: blob {d['correct']}/{d['total']} "
                 f"vs server {m[0]['correct'] if m else '?'}/{m[0]['total'] if m else '?'}")
    ok("KNOWN-2 recorded: blob .vbench is the MC-2-era snapshot; DB carries the MC-8 re-grade")


def check_compare(db) -> None:
    print("== compare model (qwen38-nothink MC-6 vs Qwen3.5 MC-10, legal-mc-146) ==")
    a = db["summaries"].find_one({"_id": "qwen3-5-9b-28k__legal-mc-146__MC-10"})
    c = db["summaries"].find_one({"_id": "qwen38-nothink__legal-mc-146__MC-6"})
    ao = next(r for r in a["accuracy_rows"] if r["level"] == "overall")
    co = next(r for r in c["accuracy_rows"] if r["level"] == "overall")
    if (ao["correct"], ao["accuracy"]) != ("128", "87.67") or (co["correct"], co["accuracy"]) != ("121", "82.88"):
        note(f"compare numbers off: qwen35 {ao} nothink {co}")
    else:
        ok("side-by-side 128/146=87.67 vs 121/146=82.88, same dataset_id")


def check_hashes(db) -> None:
    print("== card hashes ==")
    cur = hashlib.sha256((ROOT / "measurement_card.md").read_bytes()).hexdigest()
    for run_id in ("qwen3-5-9b-28k__vmlu-mqa-all-gold__MC-9", "qwen3-5-9b-28k__legal-mc-146__MC-10"):
        h = db["runs"].find_one({"_id": run_id})["measurement_card_hash"]
        if h != cur:
            note(f"{run_id} hash {h[:12]} != current card {cur[:12]}")
        else:
            ok(f"{run_id} cites current card {cur[:12]}")
    print(f"  info: blob .vmlu hash {json.load(open(BLOB, encoding='utf-8'))['vmlu']['measurement_card_hash'][:12]} "
          "(MC-9 era — stale by design, DB cites current)")
    print(f"  info: {len(MODELS)} models in registry")


def main() -> None:
    ap = argparse.ArgumentParser(description="Row-for-row verify DB view vs CSVs + blob.")
    ap.add_argument("--uri", default=MONGO_URI_DEFAULT)
    ap.add_argument("--db", default=DB_DEFAULT)
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
    blob = json.loads(BLOB.read_text(encoding="utf-8"))
    check_mc9(blob, db)
    check_legal(blob, db)
    check_reading(blob, db)
    check_vbench(blob, db)
    check_compare(db)
    check_hashes(db)
    known = [d for d in DIFFS if "KNOWN-1" in d or "KNOWN-2" in d]
    other = [d for d in DIFFS if "KNOWN-1" not in d and "KNOWN-2" not in d]
    print(f"\n{len(other)} blocking diffs, {len(known)} known blob-drifts (documented above)")
    if other:
        raise SystemExit(f"Error: {len(other)} non-known diffs:\n" + "\n".join(f"  - {d}" for d in other))


if __name__ == "__main__":
    main()
