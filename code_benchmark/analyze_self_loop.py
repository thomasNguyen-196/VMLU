"""The registered analysis of the self-improvement loop (plan self-loop-v1; card MC-104). Run once, after both runs.

  .venv/bin/python -m code_benchmark.analyze_self_loop

Per student (Qwen3.5-9B on IEC, MiMo V2.6 Flash on OpenCode Go), from the scored attempts:
* multiple choice (VMLU dev 303 and VM14K 300, pooled; per dataset descriptive): accuracy and mean reported tokens
  of always-B, always-S, always-vote (the majority of three S answers), the loop and the map; the rounds the loop
  used. Primary: the loop against always-B (exact McNemar, Holm over the two students), and the loop against
  always-S (the mean paired difference with a percentile bootstrap interval; met when the lower bound is above -1.0
  point and the loop's mean tokens are lower).
* knowledge (300 ViBidLQA questions without their passage): token-F1 under vi-reading-v3 with v2 and exact match
  beside, of B, K top 2, K top 5 and O. Primary: K top 5 against K top 2 (sign-flip p, Holm over the students).
  Descriptive: K as a share of O, and the scores by where BM25 ranked the item's own clause.
Writes all_res/diagnostic_router_loop/self_loop/analysis/self_loop_report.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_self_loop as sl
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_multimodel_expansion as v2
    from code_benchmark.analyze_diagnostic_prospective import holm_adjust, mcnemar_exact_p
except ImportError:  # executed from code_benchmark/
    import analyze_router_labels as arl
    import diagnostic_prospective as dp
    import diagnostic_self_loop as sl
    import vi_multimodel as v1
    import vi_multimodel_expansion as v2
    from analyze_diagnostic_prospective import holm_adjust, mcnemar_exact_p

PLAN_ID = "self-loop-v1"
OUTPUT_ROOT = dp.ROOT / "all_res" / "diagnostic_router_loop" / "self_loop"
PROFILES = {"qwen": "qwen3-5-9b-65k-prospective", "mimo": "mimo-v2-6-flash"}
REPORT_NAME = "self_loop_report.json"
MAP = {"qwen": {sl.VMLU: "S", sl.VM14K: "B"}, "mimo": {sl.VMLU: "B", sl.VM14K: "S"}}
NON_INFERIORITY_POINTS = -1.0


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def _tokens(row: dict[str, Any]) -> int:
    value = dp.reported_tokens(row)
    return value if isinstance(value, int) else 0


def load_rows(run_dir: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if run.get("status") != "complete" or run.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise _fail(f"the run in {run_dir} is not a complete run of the frozen manifest")
    rows = {}
    for line in (run_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[dp.run_key(row)] = row
    expected = {dp.run_key(ref) for ref in manifest["items"]}
    if set(rows) != expected:
        raise _fail(f"{run_dir}: scored attempts differ from the manifest ({len(rows)} of {len(expected)})")
    return rows


def mc_cells(student: str, rows: dict[str, dict[str, Any]], items: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Per multiple-choice item: gold, dataset, the B and S answers with their tokens, Qwen's confidence."""
    b_reps = ["B-r1"] if student == "qwen" else ["B-r1", "B-r2"]
    cells = []
    for dataset_id, item_id in items:
        b = [rows[f"{dataset_id}:{item_id}:{replicate}"] for replicate in b_reps]
        s = [rows[f"{dataset_id}:{item_id}:S-r{k}"] for k in (1, 2, 3)]
        cells.append({"dataset_id": dataset_id, "gold": str(b[0]["gold_answer"]).strip().upper(),
                      "b": [str(r.get("prediction") or "") for r in b], "s": [str(r.get("prediction") or "") for r in s],
                      "b_tokens": [_tokens(r) for r in b], "s_tokens": [_tokens(r) for r in s],
                      "confidence": b[0].get("confidence")})
    return cells


def policies(student: str, cell: dict[str, Any], threshold: float) -> dict[str, tuple[str, int, int]]:
    """{policy: (answer, reported tokens, rounds)} for one item; the loop pays for every request its rounds use."""
    b, s, bt, st = cell["b"], cell["s"], cell["b_tokens"], cell["s_tokens"]
    if student == "qwen":
        loop, rounds = sl.loop_qwen(b[0], cell["confidence"], s, threshold)
    else:
        loop, rounds = sl.loop_mimo(b[0], b[1], s)
    loop_tokens = sum(bt) + (st[0] if rounds >= 2 else 0) + (st[1] + st[2] if rounds == 3 else 0)
    always_b, always_s = (b[0], bt[0], 1), (s[0], st[0], 1)
    return {"always_B": always_b, "always_S": always_s, "always_vote": (sl.majority(s), sum(st), 1),
            "loop": (loop, loop_tokens, rounds), "map": always_b if MAP[student][cell["dataset_id"]] == "B" else always_s}


def mc_block(student: str, cells: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    outcome = [policies(student, cell, threshold) for cell in cells]
    correct = {name: [int(o[name][0] == cell["gold"] and bool(o[name][0])) for o, cell in zip(outcome, cells, strict=True)]
               for name in outcome[0]}
    tokens = {name: [o[name][1] for o in outcome] for name in outcome[0]}

    def summary(indices: list[int]) -> dict[str, Any]:
        return {name: {"accuracy": _pct(statistics.fmean(correct[name][i] for i in indices)),
                       "mean_tokens": round(statistics.fmean(tokens[name][i] for i in indices), 1)}
                for name in correct}
    everything = list(range(len(cells)))
    rounds = [o["loop"][2] for o in outcome]
    rescues = sum(loop and not base for loop, base in zip(correct["loop"], correct["always_B"], strict=True))
    regressions = sum(base and not loop for loop, base in zip(correct["loop"], correct["always_B"], strict=True))
    versus_s = arl.difference_block([float(x) for x in correct["loop"]], [float(x) for x in correct["always_S"]])
    return {
        "n": len(cells), "pooled": summary(everything),
        "by_dataset": {dataset: summary([i for i, cell in enumerate(cells) if cell["dataset_id"] == dataset])
                       for dataset in (sl.VMLU, sl.VM14K)},
        "loop_rounds": {str(k): rounds.count(k) for k in (1, 2, 3)},
        "loop_vs_B": {"rescues": rescues, "regressions": regressions, "mcnemar_p": mcnemar_exact_p(regressions, rescues)},
        "loop_vs_S": versus_s,
        "vote_vs_S": arl.difference_block([float(x) for x in correct["always_vote"]], [float(x) for x in correct["always_S"]]),
        "missing_confidence": sum(cell["confidence"] is None for cell in cells) if student == "qwen" else None,
    }


def knowledge_block(rows: dict[str, dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    arms = {"B": (sl.KNOW, "B-r1"), "K2": (sl.KNOW, "K-r1"), "K5": (sl.KNOW5, "K-r1"), "O": (sl.KNOW, "O-r1")}
    ids = list(manifest["retrieval"])
    def values(arm: str, key: str) -> list[float]:
        dataset_id, replicate = arms[arm]
        return [float(rows[f"{dataset_id}:{item_id}:{replicate}"][key]) for item_id in ids]
    f1 = {arm: values(arm, "token_f1") for arm in arms}
    means = {arm: {"token_f1": _pct(statistics.fmean(f1[arm])), "em": _pct(statistics.fmean(values(arm, "em"))),
                   "token_f1_v2": _pct(statistics.fmean(values(arm, "token_f1_v2"))),
                   "em_v2": _pct(statistics.fmean(values(arm, "em_v2"))),
                   "mean_tokens": round(statistics.fmean(_tokens(rows[f"{arms[arm][0]}:{i}:{arms[arm][1]}"]) for i in ids), 1)}
             for arm in arms}
    ranks = [manifest["retrieval"][item_id]["own_rank"] for item_id in ids]
    groups = {"own_clause_top_2": [i for i, r in enumerate(ranks) if r is not None and r <= 2],
              "own_clause_rank_3_to_5": [i for i, r in enumerate(ranks) if r is not None and 3 <= r <= 5],
              "own_clause_below_5": [i for i, r in enumerate(ranks) if r is None or r > 5]}
    return {
        "n": len(ids), "means": means,
        "k5_vs_k2": arl.difference_block(f1["K5"], f1["K2"]),
        "share_of_O": {arm: round(statistics.fmean(f1[arm]) / statistics.fmean(f1["O"]), 4) for arm in ("K2", "K5", "B")},
        "by_retrieval": {name: {"items": len(index),
                                **{arm: _pct(statistics.fmean(f1[arm][i] for i in index)) if index else None
                                   for arm in arms}} for name, index in groups.items()},
    }


def cost_block(student: str, rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total = sum(_tokens(row) for row in rows.values())
    block: dict[str, Any] = {"reported_tokens": total, "attempts": len(rows)}
    if student == "mimo":
        profile = v2.load_profiles()[PROFILES["mimo"]]
        prompt = sum(row.get("prompt_tokens") or 0 for row in rows.values())
        cached = sum(row.get("cached_prompt_tokens") or 0 for row in rows.values())
        completion = sum(row.get("completion_tokens") or 0 for row in rows.values())
        block["list_price_usd"] = round(((prompt - cached) * profile["input_price_usd_per_million"]
                                         + cached * profile["cached_input_price_usd_per_million"]
                                         + completion * profile["output_price_usd_per_million"]) / 1e6, 4)
    return block


def build_report(root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    config, _ = sl.load_config()
    registration = json.loads(sl.REGISTRATION_PATH.read_text(encoding="utf-8"))
    threshold = config["loop"]["qwen"]["threshold"]
    report: dict[str, Any] = {"plan_id": PLAN_ID, "card_id": registration["card_ids"][sl.PHASE],
                              "manifest_sha256": {}, "scores_sha256": {}, "multiple_choice": {}, "knowledge": {},
                              "primary": {}, "cost": {}}
    for student in sl.STUDENTS:
        manifest = sl.load_frozen_manifest(student)
        run_dir = root / PROFILES[student]
        rows = load_rows(run_dir, manifest)
        report["manifest_sha256"][student] = manifest["manifest_sha256"]
        report["scores_sha256"][student] = v1.sha256_file(run_dir / "scores.jsonl")
        mc_items = list(dict.fromkeys((ref["dataset_id"], ref["item_id"]) for ref in manifest["items"]
                                      if ref["dataset_id"] in (sl.VMLU, sl.VM14K)))
        report["multiple_choice"][student] = mc_block(student, mc_cells(student, rows, mc_items), threshold)
        report["knowledge"][student] = knowledge_block(rows, manifest)
        report["cost"][student] = cost_block(student, rows)
    alpha = config["analysis"]["alpha"]
    loop_b = holm_adjust({s: report["multiple_choice"][s]["loop_vs_B"]["mcnemar_p"] for s in sl.STUDENTS})
    k5 = holm_adjust({s: report["knowledge"][s]["k5_vs_k2"]["sign_flip_p"] for s in sl.STUDENTS})
    for student in sl.STUDENTS:
        mc, know = report["multiple_choice"][student], report["knowledge"][student]
        pooled = mc["pooled"]
        report["primary"][student] = {
            "loop_beats_B": {"p_holm": loop_b[student], "met": loop_b[student] < alpha
                             and pooled["loop"]["accuracy"] > pooled["always_B"]["accuracy"]},
            "loop_not_worse_than_S": {"lower_bound_points": mc["loop_vs_S"]["ci95_points"][0],
                                      "met": mc["loop_vs_S"]["ci95_points"][0] > NON_INFERIORITY_POINTS
                                      and pooled["loop"]["mean_tokens"] < pooled["always_S"]["mean_tokens"]},
            "k5_beats_k2": {"p_holm": k5[student], "met": k5[student] < alpha and know["k5_vs_k2"]["mean_points"] > 0},
        }
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=OUTPUT_ROOT)
    args = ap.parse_args(argv)
    report = build_report(args.root)
    registered = json.loads(sl.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.root / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for student in sl.STUDENTS:
        pooled = report["multiple_choice"][student]["pooled"]
        know = report["knowledge"][student]["means"]
        print(f"{student}: MC " + ", ".join(f"{name} {v['accuracy']} ({v['mean_tokens']} tok)" for name, v in pooled.items())
              + " | knowledge F1 " + ", ".join(f"{arm} {v['token_f1']}" for arm, v in know.items())
              + f" | primary {report['primary'][student]}")
    print(f"report -> {out / REPORT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
