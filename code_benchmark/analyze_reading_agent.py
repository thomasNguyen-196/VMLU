"""MC-118's registered analysis (plan diagnostic-reading-agent), run once after both models' runs are final, and the
judge sample (design §8).

Item score: the mean over draws 1-2 of each arm. Tests, Holm over the four within each family (gold-token recall R,
primary; vi-reading-v3 token-F1, continuity), no margin:
  H1  Qwen OMPF - DSHF;   H2  MiMo OMPF - DSHF;   H3  per item, H2's difference - H1's (the interaction iota);
  H4  per item, (OMPS - OMPF)_MiMo - (OMPS - OMPF)_Qwen (P3: the share of the interaction omp's prompt carries).
Each: mean per-item difference (points), 95% percentile bootstrap (2,000, seed 7), two-sided paired sign-flip p
(20,000, seed 7). Readings: H1/H2 better/worse with a Holm p below 0.05; H3 "recurs" (iota > 0) or "reversed"; H4
"carries part of the interaction" when P3 < 0, read only when H3 is detected.
Beside, not tested: P1, P2, the remaining interaction, DSHF - C and O - DSHF, splits, the sensitivity without the
flagged golds, gold-passage reading, answer seen, the score by read state, action flows, format and attempts.

From the repo root:
  .venv/bin/python -m code_benchmark.analyze_reading_agent analyze            # the registered report, once
  .venv/bin/python -m code_benchmark.analyze_reading_agent judge-build        # blind shards for the judge sample
  .venv/bin/python -m code_benchmark.analyze_reading_agent judge-join         # join the judges' labels
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_diagnostic_prospective as adp
    from code_benchmark import analyze_legal_agent_omp_prompt as alp
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_reading_agent as ra
    from code_benchmark import judge_reading400 as jr
    from code_benchmark import run_reading_agent as rr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_diagnostic_prospective as adp  # type: ignore[no-redef]
    import analyze_legal_agent_omp_prompt as alp  # type: ignore[no-redef]
    import analyze_router_labels as arl  # type: ignore[no-redef]
    import diagnostic_reading_agent as ra  # type: ignore[no-redef]
    import judge_reading400 as jr  # type: ignore[no-redef]
    import run_reading_agent as rr  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

PLAN_ID = "diagnostic-reading-agent"
CARD_ID = "MC-118"
ANALYSIS_ROOT = ra.WORK_ROOT / "analysis"
REPORT_PATH = ANALYSIS_ROOT / "report.json"
JUDGE_ROOT = ra.WORK_ROOT / "judge"
DRAWS = ("1", "2")
ALPHA = 0.05
FAMILIES = {"primary": "token_recall", "continuity": "token_f1"}
TESTS = ("H1", "H2", "H3", "H4")
JUDGE_CELLS = tuple((model, arm) for model in ra.MODELS for arm in ra.AGENT_ARMS)
Cells = dict[str, dict[str, dict[str, Any]]]


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


# ---------------------------------------------------------------- cells and scores

def cells_of(rows: list[dict[str, Any]]) -> Cells:
    """{dataset_id:item_id: {arm+draw: scored row}}."""
    cells: Cells = defaultdict(dict)
    for row in rows:
        arm, draw = str(row["replicate_id"]).split("-r")
        slot = f"{arm}{draw}"
        key = f"{row['dataset_id']}:{row['item_id']}"
        if slot in cells[key]:
            raise _fail(f"{key} has two {slot} rows")
        cells[key][slot] = row
    return dict(cells)


def check_complete(cells: Cells, keys: list[str], label: str) -> None:
    needed = [f"{arm}{draw}" for arm in ra.ARMS for draw in DRAWS]
    for key in keys:
        missing = [slot for slot in needed if slot not in cells.get(key, {})]
        if missing:
            raise _fail(f"{label} {key} lacks {missing[:5]}")


def scores(cells: Cells, keys: list[str], arm: str, metric: str, draws: tuple[str, ...] = DRAWS) -> list[float]:
    return [statistics.fmean(float(cells[key][f"{arm}{d}"].get(metric) or 0.0) for d in draws) for key in keys]


def gap(cells: Cells, keys: list[str], left: str, right: str, metric: str) -> list[float]:
    return [a - b for a, b in zip(scores(cells, keys, left, metric), scores(cells, keys, right, metric), strict=True)]


def interaction(cells: dict[str, Cells], keys: list[str], left: str, right: str, metric: str) -> list[float]:
    """Per item, MiMo's (left - right) minus Qwen's."""
    return [m - q for m, q in zip(gap(cells["mimo"], keys, left, right, metric),
                                  gap(cells["qwen"], keys, left, right, metric), strict=True)]


def test_values(cells: dict[str, Cells], keys: list[str], metric: str) -> dict[str, list[float]]:
    return {"H1": gap(cells["qwen"], keys, "OMPF", "DSHF", metric),
            "H2": gap(cells["mimo"], keys, "OMPF", "DSHF", metric),
            "H3": interaction(cells, keys, "OMPF", "DSHF", metric),
            "H4": interaction(cells, keys, "OMPS", "OMPF", metric)}


def reading(name: str, mean: float, p_holm: float, h3_detected: bool) -> str:
    significant = p_holm < ALPHA
    if name in ("H1", "H2"):
        model = "Qwen" if name == "H1" else "MiMo"
        return (f"{model}: OMPF better than DSHF" if significant and mean > 0 else
                f"{model}: OMPF worse than DSHF" if significant and mean < 0 else
                f"{model}: no clear difference between OMPF and DSHF")
    if name == "H3":
        return ("the legal interaction recurs on general reading" if significant and mean > 0 else
                "the interaction is reversed on general reading" if significant and mean < 0 else "not detected")
    if not h3_detected:
        return "reported, not read: no interaction was detected (H3)"
    return ("omp's default prompt carries part of the interaction on general reading" if significant and mean < 0
            else "not shown")


def family(cells: dict[str, Cells], keys: list[str], metric: str) -> dict[str, Any]:
    values = test_values(cells, keys, metric)
    blocks = {name: arl.difference_block(v, [0.0] * len(v)) for name, v in values.items()}
    holm = adp.holm_adjust({name: block["sign_flip_p"] for name, block in blocks.items()})
    h3 = blocks["H3"]["mean_points"]
    h3_detected = holm["H3"] < ALPHA and h3 != 0
    rules = {name: {"mean_points": blocks[name]["mean_points"], "ci95_points": blocks[name]["ci95_points"],
                    "p": blocks[name]["sign_flip_p"], "p_holm": round(holm[name], 6),
                    "reading": reading(name, blocks[name]["mean_points"], holm[name], h3_detected)} for name in TESTS}
    arms = {model: {arm: _pct(statistics.fmean(scores(cells[model], keys, arm, metric))) for arm in ra.ARMS}
            for model in ra.MODELS}
    return {"metric": metric, "n_items": len(keys), "arm_means_points": arms, "tests": blocks, "rules": rules}


# ---------------------------------------------------------------- beside

def point_estimates(cells: dict[str, Cells], keys: list[str], metric: str) -> dict[str, Any]:
    if not keys:
        return {"n": 0}
    return {"n": len(keys), **{name: _pct(statistics.fmean(v)) for name, v in test_values(cells, keys, metric).items()},
            "arm_means_points": {model: {arm: _pct(statistics.fmean(scores(cells[model], keys, arm, metric)))
                                         for arm in ra.ARMS} for model in ra.MODELS}}


def effects(cells: dict[str, Cells], keys: list[str], metric: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for model in ra.MODELS:
        c = cells[model]
        out[model] = {"P_OMPS_minus_OMPF": arl.difference_block(scores(c, keys, "OMPS", metric),
                                                                scores(c, keys, "OMPF", metric)),
                      "search_DSHF_minus_C": arl.difference_block(scores(c, keys, "DSHF", metric),
                                                                  scores(c, keys, "C", metric)),
                      "ceiling_O_minus_DSHF": arl.difference_block(scores(c, keys, "O", metric),
                                                                   scores(c, keys, "DSHF", metric))}
    remaining = interaction(cells, keys, "OMPS", "DSHF", metric)
    out["remaining_interaction"] = arl.difference_block(remaining, [0.0] * len(remaining))
    return out


def gold_seen_items(items: list[v1.EvalItem], passages: dict[str, str]) -> set[str]:
    """Items whose gold is verbatim (normalised) in their passage: the only ones `answer_seen` applies to."""
    return {f"{i.dataset_id}:{i.item_id}" for i in items
            if v1.normalized_key(i.gold_answer) and v1.normalized_key(i.gold_answer) in v1.normalized_key(
                passages[i.passage_id])}


def load_records(run_dir: Path, row: dict[str, Any]) -> list[dict[str, Any]]:
    path = run_dir / str(row.get("attempt_dir") or "") / "proxy_log.jsonl"
    if not row.get("attempt_dir") or not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def reading_behaviour(rows: list[dict[str, Any]], run_dir: Path, items: dict[str, v1.EvalItem],
                      passages: dict[str, str], seen_items: set[str]) -> dict[str, Any]:
    """Per agent arm: gold passage read, answer seen, and R by whether the passage was read (the read state)."""
    out: dict[str, Any] = {}
    for arm in ra.AGENT_ARMS:
        subset = [r for r in rows if r.get("arm") == arm]
        read, seen, by_state = 0, [0, 0], {True: [], False: []}
        for row in subset:
            key = f"{row['dataset_id']}:{row['item_id']}"
            item = items[key]
            texts = rr.tool_texts(load_records(run_dir, row))
            joined = v1.normalized_key("\n".join(texts))
            hit = v1.normalized_key(passages[item.passage_id])[:80] in joined
            read += hit
            by_state[hit].append(float(row.get("token_recall") or 0.0))
            if key in seen_items:
                seen[1] += 1
                seen[0] += v1.normalized_key(item.gold_answer) in joined
        out[arm] = {"attempts": len(subset),
                    "gold_passage_read_pct": round(100 * read / len(subset), 1) if subset else None,
                    "answer_seen_pct": round(100 * seen[0] / seen[1], 1) if seen[1] else None,
                    "answer_seen_base": seen[1],
                    "recall_when_read_points": _pct(statistics.fmean(by_state[True])) if by_state[True] else None,
                    "recall_when_not_read_points": _pct(statistics.fmean(by_state[False])) if by_state[False] else None}
    return out


def format_compliance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for arm in ra.ARMS:
        subset = [r for r in rows if r.get("arm") == arm and r.get("status") == "complete"]
        if not subset:
            continue
        short = sum(len(v1.tokenize_vi(str(r.get("prediction") or ""))) <= 8 for r in subset)
        bare = sum(str(r.get("raw_response") or "").strip() == str(r.get("prediction") or "").strip() for r in subset)
        out[arm] = {"complete": len(subset), "short_answer_pct": round(100 * short / len(subset), 1),
                    "answer_is_prediction_pct": round(100 * bare / len(subset), 1)}
    return out


# ---------------------------------------------------------------- the report

def build_report(rows: dict[str, list[dict[str, Any]]], run_dirs: dict[str, Path], protocol: dict[str, Any],
                 manifest: dict[str, Any], with_records: bool = True) -> dict[str, Any]:
    items = {f"{i.dataset_id}:{i.item_id}": i for i in ra.base_items()}
    keys = sorted(items)
    cells = {model: cells_of(rows[model]) for model in ra.MODELS}
    for model in ra.MODELS:
        check_complete(cells[model], keys, model)
    plan = protocol["analysis"]
    out: dict[str, Any] = {"plan_id": PLAN_ID, "card_id": CARD_ID, "manifest_sha256": manifest["manifest_sha256"],
                           "scores_sha256": {model: v1.sha256_file(run_dirs[model] / "scores.jsonl")
                                             for model in ra.MODELS if (run_dirs[model] / "scores.jsonl").is_file()},
                           "item_score": "mean over draws 1-2", "holm": "over H1-H4 within each family",
                           "families": {name: family(cells, keys, metric) for name, metric in FAMILIES.items()}}
    strata = json.loads((ra.ROOT / plan["retrievability"]).read_text(encoding="utf-8"))["items"]
    splits: dict[str, Any] = {}
    for name, members in (
            ("source", {ds: [k for k in keys if k.startswith(ds)] for ds in sorted({k.split(":")[0] for k in keys})}),
            ("drop_category", {s: [k for k in keys if items[k].source_dataset == "drop" and items[k].stratum == s]
                               for s in sorted({i.stratum for i in items.values() if i.source_dataset == "drop"})}),
            ("bm25", {s: [k for k in keys if strata[k]["stratum"] == s] for s in ("top1", "top5", "beyond")})):
        splits[name] = {group: point_estimates(cells, member, FAMILIES["primary"]) for group, member in members.items()}
    flagged = set(plan["flagged_golds"])
    kept = [k for k in keys if k not in flagged]
    beside: dict[str, Any] = {
        "effects": {name: effects(cells, keys, metric) for name, metric in FAMILIES.items()},
        "em_v3_arm_means_points": {model: {arm: _pct(statistics.fmean(scores(cells[model], keys, arm, "em")))
                                           for arm in ra.ARMS} for model in ra.MODELS},
        "splits": splits,
        "without_flagged_golds": {name: {test: arl.difference_block(v, [0.0] * len(v)) for test, v in
                                         test_values(cells, kept, metric).items()}
                                  for name, metric in FAMILIES.items()},
        "format": {model: format_compliance(rows[model]) for model in ra.MODELS},
        "attempts": {model: {arm: alp.attempt_profile([r for r in rows[model] if r.get("arm") == arm])
                             for arm in ra.ARMS} for model in ra.MODELS},
    }
    if with_records:
        passages = {v1.sha256_bytes(k.encode("utf-8")): e["text"] for k, e in ra.load_passages().items()}
        seen_items = gold_seen_items(list(items.values()), passages)
        beside["reading_behaviour"] = {model: reading_behaviour(rows[model], run_dirs[model], items, passages,
                                                                seen_items) for model in ra.MODELS}
        beside["action_flows"] = {model: {arm: alp.flow_indicators([r for r in rows[model] if r.get("arm") == arm],
                                                                   run_dirs[model]) for arm in ra.AGENT_ARMS}
                                  for model in ra.MODELS}
    out["beside_not_tested"] = beside
    return out


# ---------------------------------------------------------------- the judge sample (design §8)

def judge_units(rows: dict[str, list[dict[str, Any]]], sample: list[str]) -> list[dict[str, Any]]:
    """One unit per sampled item: its six draw-1 agent answers in an order permuted by seed 7."""
    by_cell = {(model, str(r["replicate_id"]).split("-r")[0], f"{r['dataset_id']}:{r['item_id']}"): r
               for model in ra.MODELS for r in rows[model] if str(r["replicate_id"]).endswith("-r1")}
    items = {f"{i.dataset_id}:{i.item_id}": i for i in ra.base_items()}
    passages = {v1.sha256_bytes(k.encode("utf-8")): e["text"] for k, e in ra.load_passages().items()}
    units = []
    for key in sample:
        order = list(JUDGE_CELLS)
        random.Random(f"{ra.SEED}:{key}").shuffle(order)
        answers = []
        for model, arm in order:
            row = by_cell.get((model, arm, key))
            if row is None:
                raise _fail(f"{key}: no draw-1 {model} {arm} row")
            answers.append({"model": model, "arm": arm, "raw": str(row.get("raw_response") or "")})
        item = items[key]
        units.append({"key": key, "jid": v1.sha256_bytes(key.encode())[:8], "question": item.question,
                      "gold": item.gold_answer, "passage": passages[item.passage_id], "answers": answers})
    return units


def render_unit(unit: dict[str, Any]) -> str:
    lines = [f"=== ITEM {unit['jid']} ===", "PASSAGE:", unit["passage"].strip(), "",
             f"QUESTION: {unit['question'].strip()}", f"GOLD: {unit['gold'].strip()}"]
    for number, answer in enumerate(unit["answers"], 1):
        lines += [f"--- ANSWER {number} ---", answer["raw"].strip() or "(empty)"]
    return "\n".join(lines) + "\n"


def judge_build(rows: dict[str, list[dict[str, Any]]], sample: list[str], out: Path = JUDGE_ROOT,
                shards: int = 4, overlap: int = 15) -> dict[str, Any]:
    units = judge_units(rows, sample)
    size = len(units) // shards
    owned = [units[k * size:(k + 1) * size] for k in range(shards)]
    (out / "shards").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    key = {"units": []}
    for k in range(shards):
        extra = owned[(k + 1) % shards][:overlap]
        members = owned[k] + extra
        random.Random(f"{ra.SEED}:shard:{k}").shuffle(members)
        (out / "shards" / f"shard_{k}.txt").write_text("\n".join(render_unit(u) for u in members), encoding="utf-8")
        for unit in owned[k]:
            key["units"].append({"jid": unit["jid"], "key": unit["key"], "owner": k,
                                 "second": (k - 1) % shards if unit in owned[k][:overlap] else None,
                                 "slots": [[a["model"], a["arm"]] for a in unit["answers"]]})
    (out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return key


def judge_join(rows: dict[str, list[dict[str, Any]]], out: Path = JUDGE_ROOT, shards: int = 4) -> dict[str, Any]:
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))
    labels = {k: jr.read_labels(out / "labels" / f"shard_{k}.csv", len(JUDGE_CELLS)) for k in range(shards)}
    scored = {(model, str(r["replicate_id"]).split("-r")[0], f"{r['dataset_id']}:{r['item_id']}"): r
              for model in ra.MODELS for r in rows[model] if str(r["replicate_id"]).endswith("-r1")}
    joined, second = [], []
    for unit in key["units"]:
        for slot, (model, arm) in enumerate(unit["slots"], 1):
            label = labels[unit["owner"]].get((unit["jid"], slot))
            if label is None:
                raise _fail(f"shard {unit['owner']} has no label for {unit['jid']} answer {slot}")
            if unit["second"] is not None:
                other = labels[unit["second"]].get((unit["jid"], slot))
                if other is None:
                    raise _fail(f"shard {unit['second']} has no second label for {unit['jid']} answer {slot}")
                second.append((label["label"], other["label"]))
            row = scored[(model, arm, unit["key"])]
            recall = float(row.get("token_recall") or 0.0)
            joined.append({"key": unit["key"], "model": model, "arm": arm, "label": label["label"], "recall": recall,
                           "r_eq_1": recall >= 1.0, "r_ge_05": recall >= 0.5})
    cells: dict[str, Any] = {}
    for model, arm in JUDGE_CELLS:
        subset = [j for j in joined if (j["model"], j["arm"]) == (model, arm)]
        cells[f"{model}:{arm}"] = {
            "n": len(subset), "judge_accuracy_points": _pct(statistics.fmean(j["label"] for j in subset)),
            "mean_recall_points": _pct(statistics.fmean(j["recall"] for j in subset)),
            "recall_bias_points": _pct(statistics.fmean(j["recall"] - j["label"] for j in subset)),
            "r_ge_05": jr.confusion([(j["r_ge_05"], j["label"]) for j in subset]),
            "r_eq_1": jr.confusion([(j["r_eq_1"], j["label"]) for j in subset])}
    flags, differences = [], {}
    for model in ra.MODELS:
        for left, right in (("OMPF", "DSHF"), ("OMPS", "OMPF")):
            diff = round(cells[f"{model}:{left}"]["recall_bias_points"] - cells[f"{model}:{right}"]["recall_bias_points"], 2)
            differences[f"{model}:{left}-{right}"] = diff
            if abs(diff) > 5:
                flags.append(f"{model}: R's bias differs by {diff} points between {left} and {right}")
    judge_means = {(j["model"], j["arm"], j["key"]): float(j["label"]) for j in joined}
    units = sorted({j["key"] for j in joined})

    def mean_diff(model: str, left: str, right: str) -> list[float]:
        return [judge_means[(model, left, k)] - judge_means[(model, right, k)] for k in units]
    estimates = {"H1": _pct(statistics.fmean(mean_diff("qwen", "OMPF", "DSHF"))),
                 "H2": _pct(statistics.fmean(mean_diff("mimo", "OMPF", "DSHF"))),
                 "H3": _pct(statistics.fmean(m - q for m, q in zip(mean_diff("mimo", "OMPF", "DSHF"),
                                                                     mean_diff("qwen", "OMPF", "DSHF"), strict=True))),
                 "H4": _pct(statistics.fmean(m - q for m, q in zip(mean_diff("mimo", "OMPS", "OMPF"),
                                                                     mean_diff("qwen", "OMPS", "OMPF"), strict=True)))}
    agree = sum(a == b for a, b in second)
    report = {"plan_id": PLAN_ID, "items": len(units), "answers": len(joined), "cells": cells,
              "bias_differences_points": differences, "flags": flags, "judge_estimates_points_draw1": estimates,
              "second_judge": {"answers": len(second), "agreement": round(agree / len(second), 4) if second else None,
                               "kappa": jr.confusion(second)["kappa"] if second else None}}
    (out / "judge_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return report


# ---------------------------------------------------------------- main

def load_rows(protocol: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Path]]:
    run_dirs = {model: rr.OUTPUT_ROOT / ra.model_spec(protocol, model)["profile_id"] for model in ra.MODELS}
    rows = {}
    for model, run_dir in run_dirs.items():
        path = run_dir / "scores.jsonl"
        if not path.is_file():
            raise _fail(f"{model}: {path} is missing; the analysis runs once, after both runs are final")
        rows[model] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows, run_dirs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("analyze", "judge-build", "judge-join"))
    args = ap.parse_args(argv)
    protocol = ra.load_protocol()
    rows, run_dirs = load_rows(protocol)
    if args.command == "judge-build":
        sample = json.loads((ra.ROOT / protocol["judge"]["sample"]).read_text(encoding="utf-8"))["items"]
        key = judge_build(rows, sample)
        print(f"judge shards -> {JUDGE_ROOT / 'shards'} ({len(key['units'])} items)")
        return 0
    if args.command == "judge-join":
        report = judge_join(rows)
        print(json.dumps({k: report[k] for k in ("bias_differences_points", "flags", "judge_estimates_points_draw1",
                                                 "second_judge")}, ensure_ascii=False))
        return 0
    manifest = ra.load_frozen_manifest()
    report = build_report(rows, run_dirs, protocol, manifest)
    registered = json.loads(ra.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    if REPORT_PATH.is_file():
        raise _fail(f"{REPORT_PATH} exists; the registered analysis runs once")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name in FAMILIES:
        for test, rule in report["families"][name]["rules"].items():
            print(f"{name} {test}: {rule['mean_points']:+.2f} p_holm={rule['p_holm']:.4f} -> {rule['reading']}")
    print(f"report -> {REPORT_PATH} sha256 {v1.sha256_file(REPORT_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
