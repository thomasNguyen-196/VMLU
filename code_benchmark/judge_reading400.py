"""Reading-400: model-as-judge check of the automatic reading metrics (exploratory, offline).

Plan: docs/research/reading-judge-2026-11-25/plan.md (hashed before any answer was judged).

    python -m code_benchmark.judge_reading400 build     # blind shard files + the private key
    python -m code_benchmark.judge_reading400 analyze   # join the judges' labels, TP/FP/FN/TN per metric

The judged answers are MC-88 (Qwen3.5-9B in omp) and MC-89 (MiMo-V2.6 in omp) on the 400 Reading-400 items.
Shard files hold passages, questions, golds and the two answers in a random order, never a model name or a score.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import vi_reading_v3 as v3
    from code_benchmark import vi_multimodel as v1
    from code_benchmark.score_reading_eval import score_pair
except ImportError:  # executed from code_benchmark/
    import vi_reading_v3 as v3
    import vi_multimodel as v1
    from score_reading_eval import score_pair

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/research/reading-judge-2026-11-25/plan.md"
OUT = ROOT / "all_res/reading_judge_20261125"
MANIFEST = ROOT / "data/eval_set_manifest.csv"
SOURCES = {"squad": (ROOT / "vmlu_squad_v1/vi_squad_benchmark_question_only.json", "id"),
           "drop": (ROOT / "vmlu_drop_v1/vi_drop_benchmark_3309_question_only.json", "question_id")}
RUNS = {"qwen": ROOT / "all_res/qwen_omp_mc88/main/qwen3-5-9b-65k-omp-full-tools-mc88/scores.jsonl",
        "mimo": ROOT / "all_res/mimo26_omp_mc89/final/main/mimo-v2-6-flash-omp-full-tools-mc89/scores.jsonl"}
SEED = 7
SHARDS = 4
OVERLAP = 15
METRICS = ("em_v3", "em_lenient", "f1_ge_05", "r_eq_1", "r_ge_05")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_items() -> list[dict[str, Any]]:
    """The 400 items with passage, question, gold and the two runs' raw answers."""
    manifest = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    passages = {}
    for dataset, (path, key) in SOURCES.items():
        for row in json.loads(path.read_text(encoding="utf-8"))["data"]:
            passages[(dataset, str(row[key]))] = row["context"]
    answers: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for model, path in RUNS.items():
        rows = {}
        for line in open(path, encoding="utf-8"):
            row = json.loads(line)
            dataset = "squad" if "squad" in row["dataset_id"] else "drop" if "drop" in row["dataset_id"] else None
            if dataset:
                rows[(dataset, str(row["item_id"]))] = row
        answers[model] = rows
    items = []
    for row in manifest:
        key = (row["dataset"], str(row["item_id"]))
        for model in RUNS:
            got = answers[model].get(key)
            if got is None or got["gold_answer"] != row["gold_answer"]:
                raise _fail(f"{model} has no answer or another gold for {key}")
        if key not in passages:
            raise _fail(f"no passage for {key}")
        items.append({"dataset": key[0], "item_id": key[1], "stratum": row["stratum"], "question": row["question"],
                      "gold": row["gold_answer"], "passage": passages[key],
                      "raw": {model: str(answers[model][key].get("raw_response") or "") for model in RUNS}})
    if len(items) != 400:
        raise _fail(f"expected 400 items, found {len(items)}")
    return items


def plan_shards(n: int, seed: int = SEED, shards: int = SHARDS, overlap: int = OVERLAP) -> dict[str, Any]:
    """Item order, owner shard, the second-judge copies and the answer slots, all from one seed."""
    rng = random.Random(seed)
    order = list(range(n))
    rng.shuffle(order)
    size = n // shards
    owned = [order[k * size:(k + 1) * size] for k in range(shards)]
    extra = [owned[(k + 1) % shards][:overlap] for k in range(shards)]
    files = []
    for k in range(shards):
        units = owned[k] + extra[k]
        rng.shuffle(units)
        files.append(units)
    slots = {i: (["qwen", "mimo"] if rng.random() < 0.5 else ["mimo", "qwen"]) for i in range(n)}
    return {"owned": owned, "extra": extra, "files": files, "slots": slots}


def jid(item: dict[str, Any]) -> str:
    return hashlib.sha256(f"{item['dataset']}:{item['item_id']}".encode()).hexdigest()[:8]


def render_unit(item: dict[str, Any], slots: list[str]) -> str:
    lines = [f"=== ITEM {jid(item)} ===", "PASSAGE:", item["passage"].strip(), "",
             f"QUESTION: {item['question'].strip()}", f"GOLD: {item['gold'].strip()}"]
    for number, model in enumerate(slots, 1):
        lines += [f"--- ANSWER {number} ---", item["raw"][model].strip() or "(empty)"]
    return "\n".join(lines) + "\n"


def build() -> None:
    items = load_items()
    plan = plan_shards(len(items))
    (OUT / "shards").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)
    key = {"plan_sha256": sha256_file(PLAN), "seed": SEED, "units": []}
    owner = {i: k for k, ids in enumerate(plan["owned"]) for i in ids}
    for k, units in enumerate(plan["files"]):
        text = "\n".join(render_unit(items[i], plan["slots"][i]) for i in units)
        path = OUT / "shards" / f"shard_{k}.txt"
        path.write_text(text, encoding="utf-8")
        print(f"shard {k}: {len(units)} items, {len(text):,} chars, sha256 {sha256_file(path)[:12]}")
    for i, item in enumerate(items):
        key["units"].append({"jid": jid(item), "dataset": item["dataset"], "item_id": item["item_id"],
                             "stratum": item["stratum"], "owner": owner[i],
                             "second": next((k for k, ids in enumerate(plan["extra"]) if i in ids), None),
                             "slots": plan["slots"][i]})
    if len({u["jid"] for u in key["units"]}) != len(items):
        raise _fail("item ids collide")
    (OUT / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"plan sha256 {key['plan_sha256']}")


def metric_values(raw: str, gold: str) -> dict[str, Any]:
    scored = v3.score_reading(raw, gold)
    prediction = scored["prediction"]
    gold_tokens = Counter(v1.tokenize_vi(v3.strip_marks(gold)))
    overlap = Counter(v1.tokenize_vi(prediction)) & gold_tokens
    recall = sum(overlap.values()) / sum(gold_tokens.values()) if gold_tokens else 1.0
    f1 = float(scored["token_f1"])
    return {"prediction": prediction, "token_f1": f1, "recall": recall,
            "em_v3": bool(scored["em"]), "em_lenient": bool(score_pair(prediction, gold)[2]),
            "f1_ge_05": f1 >= 0.5, "r_eq_1": recall >= 1.0, "r_ge_05": recall >= 0.5}


def confusion(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    """pairs of (metric positive, judge correct)."""
    tp = sum(m and j for m, j in pairs)
    fp = sum(m and not j for m, j in pairs)
    fn = sum(j and not m for m, j in pairs)
    tn = sum(not m and not j for m, j in pairs)
    n = len(pairs)

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    agree = (tp + tn) / n if n else 0.0
    pm, pj = (tp + fp) / n if n else 0.0, (tp + fn) / n if n else 0.0
    chance = pm * pj + (1 - pm) * (1 - pj)
    kappa = round((agree - chance) / (1 - chance), 4) if n and chance < 1 else None
    return {"n": n, "TP": tp, "FP": fp, "FN": fn, "TN": tn, "agreement": ratio(tp + tn, n),
            "precision": ratio(tp, tp + fp), "sensitivity": ratio(tp, tp + fn), "specificity": ratio(tn, tn + fp),
            "kappa": kappa, "metric_rate_pts": round(100 * pm, 2), "judge_rate_pts": round(100 * pj, 2),
            "bias_pts": round(100 * (pm - pj), 2)}


def read_labels(path: Path, slots: int = 2) -> dict[tuple[str, int], dict[str, Any]]:
    out = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            label = str(row["label"]).strip()
            if label not in ("0", "1") or str(row["slot"]).strip() not in {str(k) for k in range(1, slots + 1)}:
                raise _fail(f"bad label row in {path.name}: {row}")
            unit = (row["jid"].strip(), int(row["slot"]))
            if unit in out:
                raise _fail(f"duplicate label {unit} in {path.name}")
            out[unit] = {"label": label == "1", "hedge": str(row.get("hedge", "0")).strip() == "1",
                         "gold_suspect": str(row.get("gold_suspect", "0")).strip() == "1",
                         "reason": str(row.get("reason", "")).strip()}
    return out


def analyze() -> dict[str, Any]:
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    if key["plan_sha256"] != sha256_file(PLAN):
        raise _fail("the plan changed after the shards were built")
    items = {jid(item): item for item in load_items()}
    labels = {k: read_labels(OUT / "labels" / f"shard_{k}.csv") for k in range(SHARDS)}
    rows, second = [], []
    for unit in key["units"]:
        item = items[unit["jid"]]
        for slot, model in enumerate(unit["slots"], 1):
            primary = labels[unit["owner"]].get((unit["jid"], slot))
            if primary is None:
                raise _fail(f"shard {unit['owner']} has no label for {unit['jid']} answer {slot}")
            if unit["second"] is not None:
                other = labels[unit["second"]].get((unit["jid"], slot))
                if other is None:
                    raise _fail(f"shard {unit['second']} has no second label for {unit['jid']} answer {slot}")
                second.append((primary["label"], other["label"]))
            rows.append({"jid": unit["jid"], "slot": slot, "model": model, "dataset": unit["dataset"],
                         "item_id": unit["item_id"], "stratum": unit["stratum"], "question": item["question"],
                         "gold": item["gold"], "raw": item["raw"][model], **primary,
                         **metric_values(item["raw"][model], item["gold"])})
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for name in ("all", row["model"], row["dataset"], f"{row['model']}:{row['dataset']}"):
            groups[name].append(row)
    report: dict[str, Any] = {"plan_sha256": key["plan_sha256"], "answers": len(rows), "metrics": {}}
    for metric in METRICS:
        report["metrics"][metric] = {name: confusion([(r[metric], r["label"]) for r in group])
                                     for name, group in sorted(groups.items())}
        q, m = report["metrics"][metric]["qwen"], report["metrics"][metric]["mimo"]
        report["metrics"][metric]["bias_mimo_minus_qwen_pts"] = round(m["bias_pts"] - q["bias_pts"], 2)
    report["continuous"] = {name: {"judge_accuracy_pts": round(100 * statistics.fmean(r["label"] for r in g), 2),
                                   "mean_token_f1_pts": round(100 * statistics.fmean(r["token_f1"] for r in g), 2),
                                   "mean_recall_pts": round(100 * statistics.fmean(r["recall"] for r in g), 2)}
                            for name, g in sorted(groups.items())}
    agree = sum(a == b for a, b in second)
    report["second_judge"] = {"answers": len(second), "agreement": round(agree / len(second), 4) if second else None,
                              **{k: v for k, v in confusion(second).items() if k in ("kappa", "TP", "FP", "FN", "TN")}}
    report["flags"] = {"hedge": sum(r["hedge"] for r in rows), "gold_suspect_items": len({r["jid"] for r in rows
                                                                                         if r["gold_suspect"]})}
    cases = [r for r in rows if r["em_v3"] != r["label"] or r["r_eq_1"] != r["label"] or r["gold_suspect"]]
    with open(OUT / "disagreements.csv", "w", encoding="utf-8", newline="") as handle:
        cols = ["model", "dataset", "item_id", "stratum", "question", "gold", "prediction", "raw", "label", "em_v3",
                "r_eq_1", "f1_ge_05", "token_f1", "recall", "hedge", "gold_suspect", "reason"]
        writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(cases)
    with open(OUT / "judged.csv", "w", encoding="utf-8", newline="") as handle:
        cols = ["model", "dataset", "item_id", "stratum", "label", "hedge", "gold_suspect", "reason", "token_f1",
                "recall", *METRICS]
        writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    (OUT / "report.json").write_text(text, encoding="utf-8")
    print(f"report sha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Reading-400 model-as-judge check of the reading metrics")
    parser.add_argument("command", choices=("build", "analyze"))
    args = parser.parse_args(argv)
    if args.command == "build":
        build()
    else:
        report = analyze()
        for metric in METRICS:
            cell = report["metrics"][metric]
            print(metric, {k: cell[k] for k in ("all", "qwen", "mimo")}, "bias mimo-qwen",
                  cell["bias_mimo_minus_qwen_pts"])
        print("second judge", report["second_judge"], "flags", report["flags"])


if __name__ == "__main__":
    sys.exit(main())
