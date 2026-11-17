"""Post hoc and exploratory: score against tokens for the self-correction loop and its cheaper and dearer
neighbours (plan page priority 2, 2026-11-06). Sends no request and registers no condition; every number comes from
scored attempts that MC-104 and MC-105 already logged.

  .venv/bin/python -m code_benchmark.analyze_loop_pareto [--markdown PATH]

Five policies per item, each paying for every attempt it reads:
* always_B: B-r1.
* gate_S, the two-round loop: round 1 of the registered loop (Qwen's multiple choice: the probe's confidence at the
  registered threshold; otherwise B asked twice and compared); an unsure item takes S-r1.
* loop: the registered loop (MC-104 / MC-105), which on an unsure item keeps the answer S-r1 confirms and otherwise
  takes the majority of three S answers.
* always_S: S-r1.
* always_vote: the majority of three S answers.

The four registered policies are recomputed and must equal the frozen MC-104 and MC-105 reports to the last digit,
or the script stops. Per student and dataset it reports each policy's score and mean tokens, the policies no other
policy beats on both (the Pareto set), the points each gains over always_B per 1,000 extra tokens, and paired
differences (bootstrap interval, sign-flip p, Holm over the cells of one comparison and source). Multiple choice is
scored by accuracy, reading by token-F1 under vi-reading-v3. Writes
all_res/diagnostic_router_loop/pareto/loop_pareto_report.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import analyze_self_loop as asl
    from code_benchmark import analyze_table_loop as atl
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_self_loop as sl
    from code_benchmark import diagnostic_table_loop as tl
    from code_benchmark import vi_multimodel as v1
    from code_benchmark.analyze_diagnostic_prospective import holm_adjust
except ImportError:  # executed from code_benchmark/
    import analyze_router_labels as arl
    import analyze_self_loop as asl
    import analyze_table_loop as atl
    import diagnostic_prospective as dp
    import diagnostic_self_loop as sl
    import diagnostic_table_loop as tl
    import vi_multimodel as v1
    from analyze_diagnostic_prospective import holm_adjust

PLAN_ID = "loop-pareto-v1 (post hoc, exploratory)"
OUTPUT_ROOT = dp.ROOT / "all_res" / "diagnostic_router_loop" / "pareto"
REPORT_NAME = "loop_pareto_report.json"
TABLE_REPORT = atl.OUTPUT_ROOT / "analysis" / atl.REPORT_NAME
SELF_REPORT = asl.OUTPUT_ROOT / "analysis" / asl.REPORT_NAME
POLICIES = ("always_B", "gate_S", "loop", "always_S", "always_vote")
REGISTERED = ("always_B", "always_S", "always_vote", "loop")
COMPARISONS = {"S_vs_B": ("always_S", "always_B"), "loop_vs_B": ("loop", "always_B"),
               "gate_S_vs_B": ("gate_S", "always_B"), "gate_S_vs_S": ("gate_S", "always_S"),
               "gate_S_vs_loop": ("gate_S", "loop"), "loop_vs_S": ("loop", "always_S")}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


# ---------------------------------------------------------------- per item

def outcome(scores: dict[str, float], tokens: dict[str, int]) -> dict[str, Any]:
    """One item's {policy: score} and {policy: tokens}, in POLICIES order."""
    return {"score": {name: scores[name] for name in POLICIES}, "tokens": {name: tokens[name] for name in POLICIES}}


def table_item(student: str, task: str, attempts: dict[str, dict[str, Any]], threshold: float) -> dict[str, Any]:
    """An MC-105 item: the registered policies exactly as analyze_table_loop scores them, plus gate_S."""
    base = atl.item_outcome(student, task, attempts, threshold)
    metric = "accuracy" if task == "multiple_choice" else "token_f1"
    scores = {name: base["scores"][name][metric] for name in REGISTERED}
    tokens = dict(base["cost"])
    first = ["B-r1"] if task == "multiple_choice" and student == "qwen" else ["B-r1", "B-r2"]
    sure = base["rounds"] == 1
    scores["gate_S"] = scores["loop"] if sure else scores["always_S"]
    tokens["gate_S"] = sum(atl._tokens(attempts[r]) for r in first) + (0 if sure else atl._tokens(attempts["S-r1"]))
    return {**outcome(scores, tokens), "sure": sure}


def self_item(student: str, cell: dict[str, Any], threshold: float) -> dict[str, Any]:
    """An MC-104 multiple-choice item: the registered policies exactly as analyze_self_loop scores them, plus gate_S."""
    chosen = asl.policies(student, cell, threshold)
    sure = chosen["loop"][2] == 1
    gate = chosen["loop"][:2] if sure else (cell["s"][0], sum(cell["b_tokens"]) + cell["s_tokens"][0])
    answers = {**{name: chosen[name][0] for name in REGISTERED}, "gate_S": gate[0]}
    tokens = {**{name: chosen[name][1] for name in REGISTERED}, "gate_S": gate[1]}
    scores = {name: float(bool(answer) and answer == cell["gold"]) for name, answer in answers.items()}
    return {**outcome(scores, tokens), "sure": sure}


# ---------------------------------------------------------------- per cell

def pareto_set(policies: dict[str, dict[str, Any]]) -> list[str]:
    """The policies that no other policy matches or beats on both score and tokens while beating it on one."""
    def beats(a: dict[str, Any], b: dict[str, Any]) -> bool:
        return (a["score"] >= b["score"] and a["mean_tokens"] <= b["mean_tokens"]
                and (a["score"] > b["score"] or a["mean_tokens"] < b["mean_tokens"]))
    return [name for name, mine in policies.items()
            if not any(beats(other, mine) for key, other in policies.items() if key != name)]


def cell_block(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    series = {name: [o["score"][name] for o in outcomes] for name in POLICIES}
    policies: dict[str, dict[str, Any]] = {name: {"score": atl._mean_pct(series[name]),
                       "mean_tokens": round(statistics.fmean(o["tokens"][name] for o in outcomes), 1)}
                for name in POLICIES}
    base = policies["always_B"]
    for name, entry in policies.items():
        extra = entry["mean_tokens"] - base["mean_tokens"]
        entry["points_per_1k_extra_tokens"] = (round(1000 * (entry["score"] - base["score"]) / extra, 2)
                                               if name != "always_B" and extra > 0 else None)
    return {"n": len(outcomes), "policies": policies, "pareto": pareto_set(policies),
            "unsure_share": round(100 * sum(not o["sure"] for o in outcomes) / len(outcomes), 2),
            "comparisons": {key: arl.difference_block(series[a], series[b]) for key, (a, b) in COMPARISONS.items()}}


def add_holm(cells: dict[str, dict[str, Any]]) -> None:
    """Holm over the cells of one source, separately for each comparison."""
    for key in COMPARISONS:
        adjusted = holm_adjust({name: block["comparisons"][key]["sign_flip_p"] for name, block in cells.items()})
        for name, p_holm in adjusted.items():
            cells[name]["comparisons"][key]["p_holm"] = p_holm


# ---------------------------------------------------------------- parity with the frozen reports

def check_table_parity(student: str, dataset_id: str, block: dict[str, Any], frozen: dict[str, Any]) -> None:
    registered = frozen["datasets"][student][dataset_id]
    metric = registered["metric"]
    for name in REGISTERED:
        mine, theirs = block["policies"][name], registered["policies"][name]
        if (mine["score"], mine["mean_tokens"]) != (theirs[metric], theirs["mean_tokens"]):
            raise _fail(f"MC-105 {student} {dataset_id} {name}: recomputed {mine} differs from the frozen report")


def check_self_parity(student: str, label: str, block: dict[str, Any], frozen_row: dict[str, Any]) -> None:
    for name in REGISTERED:
        mine, theirs = block["policies"][name], frozen_row[name]
        if (mine["score"], mine["mean_tokens"]) != (theirs["accuracy"], theirs["mean_tokens"]):
            raise _fail(f"MC-104 {student} {label} {name}: recomputed {mine} differs from the frozen report")


# ---------------------------------------------------------------- sources

def table_source() -> dict[str, Any]:
    config, _ = tl.load_config()
    registration = json.loads(tl.REGISTRATION_PATH.read_text(encoding="utf-8"))
    threshold = config["loop"]["multiple_choice"]["threshold"]
    families = config["items"]["families"]
    frozen = json.loads(TABLE_REPORT.read_text(encoding="utf-8"))
    cells: dict[str, dict[str, Any]] = {}
    pools: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for student in tl.STUDENTS:
        manifest = tl.load_frozen_manifest(student)
        run_dir = atl.OUTPUT_ROOT / atl.PROFILES[student]
        rows = atl.load_rows(run_dir, manifest, atl.accepted_unanswered(registration, student))
        if v1.sha256_file(run_dir / "scores.jsonl") != frozen["scores_sha256"][student]:
            raise _fail(f"MC-105 {student}: scores.jsonl differs from the one the frozen report read")
        by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for (dataset_id, _), attempts in atl.item_groups(rows, manifest).items():
            task = "multiple_choice" if dataset_id in families["multiple_choice"] else "reading"
            by_dataset[dataset_id].append(table_item(student, task, attempts, threshold))
        for dataset_id in config["items"]["datasets"]:
            task = "multiple_choice" if dataset_id in families["multiple_choice"] else "reading"
            block = {"student": student, "dataset_id": dataset_id, "task": task,
                     "metric": "accuracy" if task == "multiple_choice" else "token_f1_v3",
                     **cell_block(by_dataset[dataset_id])}
            check_table_parity(student, dataset_id, block, frozen)
            cells[f"{student}:{dataset_id}"] = block
            pools[f"{student}:{task}"].extend(by_dataset[dataset_id])
    add_holm(cells)
    return {"card_id": frozen["card_id"], "report_sha256": v1.sha256_file(TABLE_REPORT),
            "scores_sha256": frozen["scores_sha256"], "cells": cells,
            "pooled": {key: cell_block(outcomes) for key, outcomes in pools.items()}}


def self_source() -> dict[str, Any]:
    config, _ = sl.load_config()
    threshold = config["loop"]["qwen"]["threshold"]
    frozen = json.loads(SELF_REPORT.read_text(encoding="utf-8"))
    cells: dict[str, dict[str, Any]] = {}
    pooled: dict[str, dict[str, Any]] = {}
    for student in sl.STUDENTS:
        manifest = sl.load_frozen_manifest(student)
        run_dir = asl.OUTPUT_ROOT / asl.PROFILES[student]
        rows = asl.load_rows(run_dir, manifest)
        if v1.sha256_file(run_dir / "scores.jsonl") != frozen["scores_sha256"][student]:
            raise _fail(f"MC-104 {student}: scores.jsonl differs from the one the frozen report read")
        items = list(dict.fromkeys((ref["dataset_id"], ref["item_id"]) for ref in manifest["items"]
                                   if ref["dataset_id"] in (sl.VMLU, sl.VM14K)))
        mc_cells = asl.mc_cells(student, rows, items)
        outcomes = [self_item(student, cell, threshold) for cell in mc_cells]
        frozen_mc = frozen["multiple_choice"][student]
        for dataset_id in (sl.VMLU, sl.VM14K):
            block = {"student": student, "dataset_id": dataset_id, "task": "multiple_choice", "metric": "accuracy",
                     **cell_block([o for o, c in zip(outcomes, mc_cells, strict=True) if c["dataset_id"] == dataset_id])}
            check_self_parity(student, dataset_id, block, frozen_mc["by_dataset"][dataset_id])
            cells[f"{student}:{dataset_id}"] = block
        pooled[student] = cell_block(outcomes)
        check_self_parity(student, "pooled", pooled[student], frozen_mc["pooled"])
    add_holm(cells)
    return {"card_id": frozen["card_id"], "report_sha256": v1.sha256_file(SELF_REPORT),
            "scores_sha256": frozen["scores_sha256"], "cells": cells, "pooled": pooled}


def build_report() -> dict[str, Any]:
    return {"plan_id": PLAN_ID, "policies": list(POLICIES), "comparisons": {k: list(v) for k, v in COMPARISONS.items()},
            "mc105_table_suite": table_source(), "mc104_fresh_items": self_source()}


# ---------------------------------------------------------------- markdown

LABELS = {"always_B": "Hỏi thẳng (B)", "gate_S": "2 vòng", "loop": "3 vòng (đã đăng ký)",
          "always_S": "Luôn S", "always_vote": "Bỏ phiếu 3 S"}


def _num(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:,.{digits}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _diff(block: dict[str, Any]) -> str:
    low, high = block["ci95_points"]
    return f"{_num(block['mean_points'])} [{_num(low)}; {_num(high)}], p Holm {_num(block['p_holm'], 3)}"


def pooled_markdown(report: dict[str, Any], names: dict[str, str]) -> list[str]:
    """One row per pooled group: each policy's score (tokens), and the points it gains over B per 1,000 extra tokens."""
    family = {"multiple_choice": "trắc nghiệm", "reading": "đọc hiểu"}
    lines = ["### Gộp theo loại bài: điểm (token mỗi câu) · điểm tăng so với B trên 1.000 token thêm", "",
             "| Nguồn | Model | Gộp | Số câu | " + " | ".join(LABELS[p] for p in POLICIES) + " |",
             "|---|---|---|---:|" + "---:|" * len(POLICIES)]
    sources = (("mc105_table_suite", "MC-105"), ("mc104_fresh_items", "MC-104 (câu mới)"))
    for source_key, source_label in sources:
        for key, block in report[source_key]["pooled"].items():
            student, _, kind = key.partition(":")
            parts = []
            for name in POLICIES:
                entry = block["policies"][name]
                text = f"{_num(entry['score'])} ({_num(entry['mean_tokens'], 0)})"
                if entry["points_per_1k_extra_tokens"] is not None:
                    text += f" · {_num(entry['points_per_1k_extra_tokens'], 1)}"
                parts.append(f"**{text}**" if name in block["pareto"] else text)
            group = family.get(kind, "trắc nghiệm (VMLU dev + VM14K)")
            lines.append(f"| {source_label} | {names[student]} | {group} | {block['n']:,} | ".replace(",", ".")
                         + " | ".join(parts) + " |")
    return lines + [""]


def render_markdown(report: dict[str, Any], names: dict[str, str]) -> str:
    lines: list[str] = pooled_markdown(report, names)
    for source_key, title in (("mc105_table_suite", "MC-105, các bộ của /table"),
                              ("mc104_fresh_items", "MC-104, câu mới (VMLU dev, VM14K)")):
        cells = report[source_key]["cells"]
        lines += [f"### {title}: điểm và token mỗi câu", "",
                  "| Model | Bộ | " + " | ".join(LABELS[p] for p in POLICIES) + " | Câu chưa chắc |",
                  "|---|---|" + "---:|" * (len(POLICIES) + 1)]
        for block in cells.values():
            parts = []
            for name in POLICIES:
                entry = block["policies"][name]
                text = f"{_num(entry['score'])} ({_num(entry['mean_tokens'], 0)})"
                parts.append(f"**{text}**" if name in block["pareto"] else text)
            lines.append(f"| {names[block['student']]} | {names[block['dataset_id']]} | " + " | ".join(parts)
                         + f" | {_num(block['unsure_share'], 1)}% |")
        lines += ["", f"### {title}: chênh lệch theo cặp câu (điểm, khoảng 95%, p Holm)", "",
                  "| Model | Bộ | S − B | 2 vòng − B | 2 vòng − luôn S | 2 vòng − 3 vòng | Token 2 vòng / luôn S |",
                  "|---|---|---:|---:|---:|---:|---:|"]
        for block in cells.values():
            comp, pol = block["comparisons"], block["policies"]
            ratio = pol["gate_S"]["mean_tokens"] / pol["always_S"]["mean_tokens"]
            lines.append(f"| {names[block['student']]} | {names[block['dataset_id']]} | {_diff(comp['S_vs_B'])} | "
                         f"{_diff(comp['gate_S_vs_B'])} | {_diff(comp['gate_S_vs_S'])} | "
                         f"{_diff(comp['gate_S_vs_loop'])} | {_num(100 * ratio, 0)}% |")
        lines.append("")
    return "\n".join(lines)


NAMES = {"qwen": "Qwen3.5-9B", "mimo": "MiMo V2.6 Flash",
         "vi-multimodel-v1-vmlu-valid": "VMLU valid", "vi-multimodel-v1-legal-mc-146": "Legal MC",
         "vi-multimodel-v1-legal-nli-150": "Legal NLI", "vi-multimodel-v1-vi-squad-200": "Vi-SQuAD",
         "vi-multimodel-v1-vi-drop-200": "Vi-DROP", "vi-multimodel-v1-bidlqa-test": "ViBidLQA test",
         sl.VMLU: "VMLU dev", sl.VM14K: "VM14K"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--markdown", type=Path, help="also write the tables as Markdown to this path")
    args = ap.parse_args(argv)
    report = build_report()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for source in ("mc105_table_suite", "mc104_fresh_items"):
        for key, block in report[source]["cells"].items():
            line = " ".join(f"{name} {p['score']}/{p['mean_tokens']}" for name, p in block["policies"].items())
            print(f"{source} {key}: {line} | pareto {block['pareto']} | unsure {block['unsure_share']}%")
    if args.markdown:
        args.markdown.write_text(render_markdown(report, NAMES) + "\n", encoding="utf-8")
        print(f"markdown -> {args.markdown}")
    print(f"parity with the frozen MC-104 and MC-105 reports: ok; report -> {OUTPUT_ROOT / REPORT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
