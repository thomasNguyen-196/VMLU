"""Exploratory simulation of the rule loop on existing Qwen3.5-9B runs (openspec change diagnostic-router-loop, task 1.1).

No request is sent: every answer below was already recorded by MC-90 to MC-101.

The rule loop, fixed before any number was computed:
* ask B (draw a); ask B again (draw b);
* if the two parsed answers agree under `normalized-answer-v1` (`diagnostic_router.answers_agree`), keep B's draw-a
  answer; otherwise take the enhancement F's draw-a answer;
* both draw orders (a, b) = (1, 2) and (2, 1) are averaged.

For each run group, dataset and enhancement F it reports always-B, always-F, the loop, the share of items the loop
sends to F, an ideal-detector ceiling (per item the better of B and F on draw a: what a router that always knew a weak
first answer could reach) and mean reported tokens. Arm O (oracle evidence) is never an enhancement here; it is
reported as a ceiling only.

Where a stronger model's own answers to the same items are logged (MC-80/81, Muse Spark 1.3 direct), it also reports
that model as a detector (its answer disagrees with B's) and the cascade "ask B twice; on disagreement take the
stronger model's answer", with the stronger model's tokens. Every figure is exploratory: these runs were used to
design earlier routers.

  .venv/bin/python -m code_benchmark.simulate_router_loop [--out <json>]
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_router as router
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_router as router

ROOT = dp.ROOT
RUNS = ROOT / "all_res"
PROFILE = "qwen3-5-9b-65k-prospective"
GROUPS: dict[str, list[str]] = {
    "wide (MC-90/91/92, MC-97)": ["diagnostic_prospective/wide", "diagnostic_prospective/wide-supplements/wide-b-r2",
                                  "diagnostic_prospective/wide-supplements/wide-s-r2", "diagnostic_llm_router/menu"],
    "MC-94 held-out": ["diagnostic_router_v2/heldout"],
    "MC-95 held-out": ["diagnostic_router_v3/heldout"],
    "MC-96 no passage": ["diagnostic_k2/heldout"],
    "MC-101 Legal MC": ["diagnostic_legal_retrieval/run"],
}
DRAW_ORDERS = (("1", "2"), ("2", "1"))
CEILING_ONLY = frozenset({"O"})
OUT_PATH = RUNS / "diagnostic_router_loop" / "simulation" / "rule_loop_sim.json"
STRONG_PATH = RUNS / "vi_multimodel_v1" / "main" / "muse-spark-1-3-contributor" / "scores.jsonl"


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def load_cells(paths: list[Path]) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    """{(dataset_id, item_id): {"B1": row, "S2": row, ...}} from score files; a repeated attempt fails closed."""
    cells: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            arm, _, draw = row["replicate_id"].partition("-r")
            key = f"{arm}{draw}"
            cell = cells[(row["dataset_id"], str(row["item_id"]))]
            if key in cell:
                raise _fail(f"two {key} rows for {row['dataset_id']}:{row['item_id']} in {path}")
            cell[key] = row
    return dict(cells)


def score(row: dict[str, Any]) -> float:
    """Accuracy for multiple choice, token-F1 for reading."""
    return float(row["correct"]) if "correct" in row else float(row["token_f1"])


def task_of(row: dict[str, Any]) -> str:
    return "multiple_choice" if "correct" in row else "reading"


def tokens(row: dict[str, Any]) -> float | None:
    value = row.get("total_tokens")
    return float(value) if isinstance(value, int) else None


def simulate(cells: list[dict[str, dict[str, Any]]], arm: str) -> dict[str, Any]:
    """The rule loop with enhancement `arm` on items that have B and `arm` on both draws."""
    usable = [cell for cell in cells if all(f"{name}{draw}" in cell for name in ("B", arm) for draw in ("1", "2"))]
    if not usable:
        return {"n": 0}
    always_b, always_f, loop, ideal, sent = [], [], [], [], []
    loop_tokens, b_tokens, f_tokens = [], [], []
    for cell in usable:
        for a, b in DRAW_ORDERS:
            first, probe, fix = cell[f"B{a}"], cell[f"B{b}"], cell[f"{arm}{a}"]
            agree = router.answers_agree(str(first.get("prediction") or ""), str(probe.get("prediction") or ""),
                                         task_of(first))
            always_b.append(score(first))
            always_f.append(score(fix))
            loop.append(score(first) if agree else score(fix))
            ideal.append(max(score(first), score(fix)))
            sent.append(0.0 if agree else 1.0)
            first_tokens, probe_tokens, fix_tokens = tokens(first), tokens(probe), tokens(fix)
            if first_tokens is not None and probe_tokens is not None and fix_tokens is not None:
                b_tokens.append(first_tokens)
                f_tokens.append(fix_tokens)
                loop_tokens.append(first_tokens + probe_tokens + (0.0 if agree else fix_tokens))
    pct = lambda values: round(100 * statistics.fmean(values), 2)  # noqa: E731
    mean = lambda values: round(statistics.fmean(values), 1) if values else None  # noqa: E731
    return {"n": len(usable), "always_B": pct(always_b), "always_F": pct(always_f), "loop": pct(loop),
            "loop_minus_B": round(pct(loop) - pct(always_b), 2), "loop_minus_F": round(pct(loop) - pct(always_f), 2),
            "sent_to_F_pct": pct(sent), "ideal_detector": pct(ideal),
            "tokens": {"B": mean(b_tokens), "F": mean(f_tokens), "loop": mean(loop_tokens)}}


def load_strong(path: Path = STRONG_PATH) -> dict[tuple[str, str], dict[str, Any]]:
    """{(dataset_id, item_id): row} of the stronger model's own logged answers (MC-80/81, Muse Spark 1.3 direct)."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(row["dataset_id"], str(row["item_id"])): row for row in rows}


def strong_model(cells: list[tuple[dict[str, dict[str, Any]], dict[str, Any]]], arm: str | None) -> dict[str, Any]:
    """With the stronger model's logged answer M of each item, on both draw orders:
    * `flag_by_M_to_F`: keep B's draw-a answer when M agrees with it, otherwise take F's draw-a answer (F = arm);
    * `cascade_to_M`: ask B twice; keep B when the two agree, otherwise take M (M is called on flagged items only);
    * `M_alone`: M on every item.
    Detector counts use the first answer's correctness (token-F1 below 0.5 counts as wrong for reading)."""
    use = [(cell, strong) for cell, strong in cells
           if all(f"B{draw}" in cell for draw in ("1", "2")) and (arm is None or all(f"{arm}{draw}" in cell for draw in ("1", "2")))]
    if not use:
        return {"n": 0}
    flag_fix, cascade, alone, wrong, caught, false_flags, sent, strong_tokens = [], [], [], 0, 0, 0, [], []
    for cell, strong in use:
        for a, b in DRAW_ORDERS:
            first, probe = cell[f"B{a}"], cell[f"B{b}"]
            task = task_of(first)
            agrees_strong = router.answers_agree(str(first.get("prediction") or ""), str(strong.get("prediction") or ""), task)
            agrees_probe = router.answers_agree(str(first.get("prediction") or ""), str(probe.get("prediction") or ""), task)
            if arm is not None:
                flag_fix.append(score(first) if agrees_strong else score(cell[f"{arm}{a}"]))
            cascade.append(score(first) if agrees_probe else score(strong))
            alone.append(score(strong))
            is_wrong = score(first) < (1.0 if task == "multiple_choice" else 0.5)
            wrong += is_wrong
            caught += is_wrong and not agrees_strong
            false_flags += (not is_wrong) and not agrees_strong
            sent.append(0.0 if agrees_probe else 1.0)
            cost = (strong.get("prompt_tokens") or 0) + (strong.get("completion_tokens") or 0)
            strong_tokens.append(0.0 if agrees_probe else float(cost))
    pct = lambda values: round(100 * statistics.fmean(values), 2)  # noqa: E731
    total = len(use) * len(DRAW_ORDERS)
    return {"n": len(use), **({"flag_by_M_to_F": pct(flag_fix)} if arm is not None else {}),
            "cascade_to_M": pct(cascade), "M_alone": pct(alone), "cascade_sends_to_M_pct": pct(sent),
            "M_detector": {"first_answers_wrong": wrong, "caught": caught, "false_flags": false_flags,
                           "first_answers_right": total - wrong},
            "M_tokens_per_item": {"cascade": round(statistics.fmean(strong_tokens), 1),
                                  "alone": round(statistics.fmean((strong.get("prompt_tokens") or 0)
                                                                  + (strong.get("completion_tokens") or 0)
                                                                  for _, strong in use), 1)}}


def ceiling(cells: list[dict[str, dict[str, Any]]], arm: str) -> dict[str, Any]:
    usable = [cell for cell in cells if all(f"{arm}{draw}" in cell for draw in ("1", "2"))]
    if not usable:
        return {"n": 0}
    return {"n": len(usable), "mean": round(100 * statistics.fmean(score(cell[f"{arm}{draw}"]) for cell in usable
                                                                    for draw in ("1", "2")), 2)}


def run_all(groups: dict[str, list[str]] = GROUPS, runs: Path = RUNS, strong_path: Path = STRONG_PATH
            ) -> dict[str, Any]:
    strong = load_strong(strong_path) if strong_path.is_file() else {}
    report: dict[str, Any] = {}
    for label, dirs in groups.items():
        paths = [runs / directory / PROFILE / "scores.jsonl" for directory in dirs]
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise _fail(f"{label}: missing score files {missing}")
        by_dataset: dict[str, list[tuple[str, dict[str, dict[str, Any]]]]] = defaultdict(list)
        for (dataset_id, item_id), cell in load_cells(paths).items():
            by_dataset[dataset_id].append((item_id, cell))
        block = {}
        for dataset_id, entries in sorted(by_dataset.items()):
            cells = [cell for _, cell in entries]
            arms = sorted({key[:-1] for cell in cells for key in cell} - {"B"})
            paired = [(cell, strong[(dataset_id, item_id)]) for item_id, cell in entries if (dataset_id, item_id) in strong]
            block[dataset_id] = {
                "items": len(cells),
                "loops": {arm: simulate(cells, arm) for arm in arms if arm not in CEILING_ONLY},
                "ceilings": {arm: ceiling(cells, arm) for arm in arms if arm in CEILING_ONLY},
                "strong_model": ({arm: strong_model(paired, arm) for arm in arms if arm not in CEILING_ONLY}
                                 | {"none": strong_model(paired, None)}) if paired else {},
            }
        report[label] = block
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args(argv)
    report = run_all()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for label, block in report.items():
        for dataset_id, entry in block.items():
            for arm, sim in entry["loops"].items():
                if sim.get("n"):
                    print(f"{label:28s} {dataset_id:38s} F={arm:2s} n={sim['n']:4d} B={sim['always_B']:6.2f} "
                          f"F={sim['always_F']:6.2f} loop={sim['loop']:6.2f} sent={sim['sent_to_F_pct']:5.1f}% "
                          f"ideal={sim['ideal_detector']:6.2f} tok B/F/loop={sim['tokens']['B']}/"
                          f"{sim['tokens']['F']}/{sim['tokens']['loop']}")
            for arm, top in entry["ceilings"].items():
                print(f"{label:28s} {dataset_id:38s} ceiling {arm}: n={top['n']} mean={top['mean']}")
            for arm, block in entry["strong_model"].items():
                if block.get("n"):
                    detector = block["M_detector"]
                    print(f"{label:28s} {dataset_id:38s} strong M, F={arm:4s} n={block['n']:4d} "
                          f"flag-by-M->F={block.get('flag_by_M_to_F', '-')} cascade->M={block['cascade_to_M']} "
                          f"(M on {block['cascade_sends_to_M_pct']}%) M alone={block['M_alone']} "
                          f"caught {detector['caught']}/{detector['first_answers_wrong']} false "
                          f"{detector['false_flags']}/{detector['first_answers_right']} "
                          f"M tokens cascade/alone={block['M_tokens_per_item']['cascade']}/"
                          f"{block['M_tokens_per_item']['alone']}")
    print(f"report -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
