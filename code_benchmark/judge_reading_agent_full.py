"""MC-118, exploratory: a blind judge on all 4,800 agent answers (plan docs/research/reading-agent-full-judge-2026-11-26/).

Not part of MC-118's registration. One unit per item holds its 12 agent answers (2 models × DSHF/OMPF/OMPS × 2 draws)
in a seeded order, with no model, arm, draw or score. 14 shards, one Opus 5.5 instance each, under the 2026-11-25
rubric. The join computes H1-H4 on judge labels (exploratory), R's bias per cell, and the agreement with the
registered judge sample.

  python -m code_benchmark.judge_reading_agent_full build
  python -m code_benchmark.judge_reading_agent_full join
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_diagnostic_prospective as adp
    from code_benchmark import analyze_reading_agent as an
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_reading_agent as ra
    from code_benchmark import judge_reading400 as jr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_diagnostic_prospective as adp  # type: ignore[no-redef]
    import analyze_reading_agent as an  # type: ignore[no-redef]
    import analyze_router_labels as arl  # type: ignore[no-redef]
    import diagnostic_reading_agent as ra  # type: ignore[no-redef]
    import judge_reading400 as jr  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

PLAN = ra.ROOT / "docs/research/reading-agent-full-judge-2026-11-26/plan.md"
OUT = ra.WORK_ROOT / "judge_full"
SHARDS = 14
CELLS = tuple((model, arm, draw) for model in ra.MODELS for arm in ra.AGENT_ARMS for draw in ("1", "2"))


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def by_cell(rows: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    out = {}
    for model in ra.MODELS:
        for row in rows[model]:
            arm, draw = str(row["replicate_id"]).split("-r")
            if arm in ra.AGENT_ARMS:
                out[(model, arm, draw, f"{row['dataset_id']}:{row['item_id']}")] = row
    return out


def build(rows: dict[str, list[dict[str, Any]]], out: Path = OUT, shards: int = SHARDS) -> dict[str, Any]:
    cells = by_cell(rows)
    items = {f"{i.dataset_id}:{i.item_id}": i for i in ra.base_items()}
    passages = {v1.sha256_bytes(k.encode("utf-8")): e["text"] for k, e in ra.load_passages().items()}
    keys = sorted(items)
    random.Random(f"{ra.SEED}:full-order").shuffle(keys)
    (out / "shards").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    key_file: dict[str, Any] = {"plan_sha256": v1.sha256_file(PLAN), "units": []}
    groups = [keys[k::shards] for k in range(shards)]
    for k, group in enumerate(groups):
        texts = []
        for key in group:
            order = list(CELLS)
            random.Random(f"{ra.SEED}:full:{key}").shuffle(order)
            item = items[key]
            unit = {"key": key, "jid": v1.sha256_bytes(key.encode())[:8], "slots": [list(c) for c in order]}
            lines = [f"=== ITEM {unit['jid']} ===", "PASSAGE:", passages[item.passage_id].strip(), "",
                     f"QUESTION: {item.question.strip()}", f"GOLD: {item.gold_answer.strip()}"]
            for number, (model, arm, draw) in enumerate(order, 1):
                row = cells.get((model, arm, draw, key))
                if row is None:
                    raise _fail(f"{key}: no {model} {arm} draw {draw} row")
                lines += [f"--- ANSWER {number} ---", str(row.get("raw_response") or "").strip() or "(empty)"]
            texts.append("\n".join(lines) + "\n")
            key_file["units"].append({**unit, "shard": k})
        (out / "shards" / f"shard_{k:02d}.txt").write_text("\n".join(texts), encoding="utf-8")
    (out / "key.json").write_text(json.dumps(key_file, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return key_file


def join(rows: dict[str, list[dict[str, Any]]], out: Path = OUT) -> dict[str, Any]:
    key_file = json.loads((out / "key.json").read_text(encoding="utf-8"))
    if key_file["plan_sha256"] != v1.sha256_file(PLAN):
        raise _fail("the plan changed after the shards were built")
    labels = {k: jr.read_labels(out / "labels" / f"shard_{k:02d}.csv", len(CELLS)) for k in range(SHARDS)}
    cells = by_cell(rows)
    judged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for unit in key_file["units"]:
        for slot, (model, arm, draw) in enumerate(unit["slots"], 1):
            label = labels[unit["shard"]].get((unit["jid"], slot))
            if label is None:
                raise _fail(f"shard {unit['shard']} has no label for {unit['jid']} answer {slot}")
            judged[(model, arm, draw, unit["key"])] = label
    # rows with the judge label as a metric, for MC-118's test definitions
    judge_rows = {model: [] for model in ra.MODELS}
    for (model, arm, draw, key), label in judged.items():
        row = cells[(model, arm, draw, key)]
        judge_rows[model].append({**row, "judge": float(label["label"])})
    cellmaps = {model: an.cells_of(judge_rows[model]) for model in ra.MODELS}
    keys = sorted({key for *_, key in judged})
    values = an.test_values(cellmaps, keys, "judge")
    blocks = {name: arl.difference_block(v, [0.0] * len(v)) for name, v in values.items()}
    holm = adp.holm_adjust({name: b["sign_flip_p"] for name, b in blocks.items()})
    tests = {name: {"mean_points": b["mean_points"], "ci95_points": b["ci95_points"], "p": b["sign_flip_p"],
                    "p_holm": round(holm[name], 6)} for name, b in blocks.items()}
    arm_means = {model: {arm: an._pct(statistics.fmean(an.scores(cellmaps[model], keys, arm, "judge")))  # noqa: SLF001
                         for arm in ra.AGENT_ARMS} for model in ra.MODELS}
    beside = {model: {"P_OMPS_minus_OMPF": arl.difference_block(an.scores(cellmaps[model], keys, "OMPS", "judge"),
                                                                an.scores(cellmaps[model], keys, "OMPF", "judge"))}
              for model in ra.MODELS}
    remaining = an.interaction(cellmaps, keys, "OMPS", "DSHF", "judge")
    beside["remaining_interaction"] = arl.difference_block(remaining, [0.0] * len(remaining))
    beside["by_source"] = {ds: {name: an._pct(statistics.fmean(v)) for name, v in  # noqa: SLF001
                                an.test_values(cellmaps, [k for k in keys if k.startswith(ds)], "judge").items()}
                           for ds in sorted({k.split(":")[0] for k in keys})}
    per_cell = {}
    for model in ra.MODELS:
        for arm in ra.AGENT_ARMS:
            pairs = [(float(cells[(model, arm, d, k)].get("token_recall") or 0.0), judged[(model, arm, d, k)]["label"])
                     for d in ("1", "2") for k in keys]
            per_cell[f"{model}:{arm}"] = {
                "n": len(pairs), "judge_accuracy_points": an._pct(statistics.fmean(j for _, j in pairs)),  # noqa: SLF001
                "mean_recall_points": an._pct(statistics.fmean(r for r, _ in pairs)),  # noqa: SLF001
                "recall_bias_points": an._pct(statistics.fmean(r - j for r, j in pairs)),  # noqa: SLF001
                "r_ge_05": jr.confusion([(r >= 0.5, j) for r, j in pairs]),
                "r_eq_1": jr.confusion([(r >= 1.0, j) for r, j in pairs])}
    # agreement with the registered judge sample (draw 1)
    sample_key = json.loads((ra.WORK_ROOT / "judge" / "key.json").read_text(encoding="utf-8"))
    sample_labels = {k: jr.read_labels(ra.WORK_ROOT / "judge" / "labels" / f"shard_{k}.csv", 6) for k in range(4)}
    pairs = []
    for unit in sample_key["units"]:
        for slot, (model, arm) in enumerate(unit["slots"], 1):
            first = sample_labels[unit["owner"]].get((unit["jid"], slot))
            again = judged.get((model, arm, "1", unit["key"]))
            if first is not None and again is not None:
                pairs.append((first["label"], again["label"]))
    agreement = {"answers": len(pairs), "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 4) if pairs else None,
                 "kappa": jr.confusion(pairs)["kappa"] if pairs else None}
    report = {"plan_sha256": key_file["plan_sha256"], "status": "exploratory, not registered",
              "answers": len(judged), "items": len(keys), "judge_arm_means_points": arm_means,
              "tests_on_judge_labels": tests, "beside": beside, "per_cell": per_cell,
              "agreement_with_registered_sample": agreement,
              "flags": {"gold_suspect": sum(lab["gold_suspect"] for lab in judged.values()),
                        "hedge": sum(lab["hedge"] for lab in judged.values())}}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    (out / "report.json").write_text(text + "\n", encoding="utf-8")
    print(f"report sha256 {v1.sha256_file(out / 'report.json')}")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MC-118 exploratory full judge")
    ap.add_argument("command", choices=("build", "join"))
    args = ap.parse_args(argv)
    rows, _ = an.load_rows(ra.load_protocol())
    if args.command == "build":
        key_file = build(rows)
        print(f"{len(key_file['units'])} items in {SHARDS} shards -> {OUT / 'shards'}")
        return 0
    report = join(rows)
    print(json.dumps({k: report[k] for k in ("judge_arm_means_points", "tests_on_judge_labels",
                                             "agreement_with_registered_sample", "flags")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
