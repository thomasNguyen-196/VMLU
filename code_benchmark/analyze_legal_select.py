"""The registered analysis of the Legal MC "chọn rồi trả lời" test (plan diagnostic-legal-select-v1; card MC-111).

Run once, after both rounds:
  .venv/bin/python -m code_benchmark.analyze_legal_select --run-dir all_res/diagnostic_legal_select/run/<profile>

* Item score: the mean over the two draws: correctness for an answer arm (0, 0.5 or 1); selection hit for PICK.
* Selection hit: the selection holds an oracle article (document number and article, any part counting, matched as
  MC-101's hit report matches); an empty or unparsed selection is a miss.
* Filter question, on the items with MC-100 oracle provisions: PICK's selection hit against BM25's top-2 hit.
* Route question, on the pool: always-SEL against always-B.
* Both: the mean per-item difference with a percentile bootstrap interval (2,000 resamples, seed 7) and a two-sided
  sign-flip p-value (20,000 resamples, seed 7), Holm-adjusted over the two; a question is met when the left mean is
  higher and the adjusted p-value is below 0.05.
* Everything else is description.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_diagnostic_prospective as adp
    from code_benchmark import analyze_legal_oracle as alo
    from code_benchmark import analyze_legal_retrieval as alr
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_legal_retrieval as lr
    from code_benchmark import diagnostic_legal_select as ls
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_diagnostic_prospective as adp
    import analyze_legal_oracle as alo
    import analyze_legal_retrieval as alr
    import analyze_router_labels as arl
    import diagnostic_legal_oracle as lo
    import diagnostic_legal_retrieval as lr
    import diagnostic_legal_select as ls
    import diagnostic_prospective as dp
    import vi_multimodel as v1

PLAN_ID = "diagnostic-legal-select-v1"
DRAWS = alr.DRAWS
ANSWER_ARMS = ("B", "K", "K10", "SEL", "O")
MC101_REPORT = lr.WORK_ROOT / "run" / "qwen3-5-9b-65k-prospective" / "analysis" / "legal_retrieval_report.json"


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def answer_refs(manifest: dict[str, Any]) -> dict[str, Any]:
    return {**manifest, "items": [ref for ref in manifest["items"]
                                  if dp.arm_of_replicate(ref["replicate_id"]) != "PICK"]}


def selections_by_item(round2: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """{item_id: {draw: selection}} from the parsed selections the round-2 manifest records."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for key, selection in round2["selections"].items():
        item_id, replicate = key.split(":")[-2:]
        out.setdefault(item_id, {})[replicate.partition("-r")[2]] = selection
    return out


def selection_hit(selection: dict[str, Any], candidates: dict[str, Any], targets: set[tuple[str, str, str]]) -> bool:
    if selection["status"] != "picked":
        return False
    return any(lr.unit_target(candidates["ranking"][number - 1]["chunk_id"]) in targets
               for number in selection["picks"])


def filter_question(oracle_items: list[str], selections: dict[str, dict[str, dict[str, Any]]],
                    candidates: dict[str, dict[str, Any]], oracle: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """PICK's selection hit (mean over draws) against BM25's top-2 hit (0 or 1), item by item."""
    picked, bm25 = [], []
    for item_id in oracle_items:
        targets = lr.oracle_targets(oracle[item_id]["provisions"])
        picked.append(statistics.fmean(float(selection_hit(selections[item_id][draw], candidates[item_id], targets))
                                       for draw in DRAWS))
        bm25.append(float(any(lr.unit_target(entry["chunk_id"]) in targets
                              for entry in candidates[item_id]["ranking"][:2])))
    return {"n": len(oracle_items), "PICK": _pct(statistics.fmean(picked)), "BM25_top2": _pct(statistics.fmean(bm25)),
            "PICK_versus_BM25_top2": arl.difference_block(picked, bm25)}


def rules(filter_block: dict[str, Any], route_block: dict[str, Any], alpha: float) -> dict[str, Any]:
    tests = {"filter": filter_block["PICK_versus_BM25_top2"], "route": route_block["SEL_versus_B"]}
    adjusted = adp.holm_adjust({name: block["sign_flip_p"] for name, block in tests.items()})
    out: dict[str, Any] = {"alpha": alpha, "multiplicity": "holm"}
    for name, block in tests.items():
        met = block["mean_points"] > 0 and adjusted[name] < alpha
        out[name] = {"mean_points": block["mean_points"], "sign_flip_p": block["sign_flip_p"],
                     "p_holm": round(adjusted[name], 6), "met": met}
    worse = out["filter"]["mean_points"] < 0 and out["filter"]["p_holm"] < alpha
    out["filter"]["reading"] = ("Qwen filters retrieved legal evidence better than BM25's order" if out["filter"]["met"]
                                else "Qwen filters retrieved legal evidence worse than BM25's order" if worse
                                else "no evidence that Qwen filters better than BM25's order")
    out["route"]["legal_mc_route"] = "SEL" if out["route"]["met"] else "B"
    return out


def group_block(items: list[str], cells: dict[str, dict[str, dict[str, Any]]], *, gain_share: bool = False
                ) -> dict[str, Any]:
    block: dict[str, Any] = {"n": len(items)}
    for arm in ANSWER_ARMS:
        ran = [item for item in items if f"{arm}1" in cells[item]]
        block[arm] = _pct(statistics.fmean(alr.arm_mean(cells[item], arm) for item in ran)) if ran else None
    pairs = [("K", "B"), ("K10", "B"), ("SEL", "B"), ("O", "B"), ("SEL", "K"), ("SEL", "K10"), ("K10", "K"),
             ("SEL", "O")]
    block["comparisons"] = {f"{left}_vs_{right}": alr.compare(items, cells, left, right) for left, right in pairs}
    if gain_share:
        gain = block["comparisons"]["O_vs_B"].get("O_versus_B", {}).get("mean_points")
        block["share_of_O_gain_kept"] = {
            arm: (round(block["comparisons"][f"{arm}_vs_B"][f"{arm}_versus_B"]["mean_points"] / gain, 4)
                  if gain and gain > 0 else None) for arm in ("K", "K10", "SEL")}
    return block


def selection_behaviour(pool: list[str], oracle_items: list[str], selections: dict[str, dict[str, dict[str, Any]]],
                        candidates: dict[str, dict[str, Any]], oracle: dict[str, dict[str, Any]]) -> dict[str, Any]:
    every = [selections[item][draw] for item in pool for draw in DRAWS]
    picked = [s for s in every if s["status"] == "picked"]
    reach, out_of_reach, picked_units, oracle_units = [], [], 0, 0
    for item_id in oracle_items:
        targets = lr.oracle_targets(oracle[item_id]["provisions"])
        units = [lr.unit_target(entry["chunk_id"]) for entry in candidates[item_id]["ranking"]]
        in_reach = any(unit in targets for unit in units)
        for draw in DRAWS:
            selection = selections[item_id][draw]
            (reach if in_reach else out_of_reach).append((item_id, selection, targets))
            if selection["status"] == "picked":
                picked_units += len(selection["picks"])
                oracle_units += sum(units[number - 1] in targets for number in selection["picks"])
    return {
        "draws": len(every), "status": dict(Counter(s["status"] for s in every)),
        "picks_per_selection": dict(sorted(Counter(len(s["picks"]) for s in every).items())),
        "positions": dict(sorted(Counter(number for s in picked for number in s["picks"]).items())),
        "share_exactly_1_and_2": round(sum(set(s["picks"]) == {1, 2} for s in picked) / len(picked), 4) if picked else None,
        "precision_on_oracle_items": round(oracle_units / picked_units, 4) if picked_units else None,
        "recall_within_reach": {"items": len({item for item, _, _ in reach}), "draws": len(reach),
                                "hit_share": round(statistics.fmean(
                                    float(selection_hit(s, candidates[item], t)) for item, s, t in reach), 4)
                                if reach else None},
        "none_where_no_oracle_in_top10": {"items": len({item for item, _, _ in out_of_reach}),
                                          "draws": len(out_of_reach),
                                          "none_share": round(statistics.fmean(float(s["status"] == "none")
                                                                               for _, s, _ in out_of_reach), 4)
                                          if out_of_reach else None},
    }


def by_selection(oracle_items: list[str], selections: dict[str, dict[str, dict[str, Any]]],
                 candidates: dict[str, dict[str, Any]], oracle: dict[str, dict[str, Any]],
                 cells: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """SEL's step-2 accuracy over draws whose selection hits and draws whose selection misses."""
    groups: dict[str, list[float]] = {"hit": [], "miss": []}
    for item_id in oracle_items:
        targets = lr.oracle_targets(oracle[item_id]["provisions"])
        for draw in DRAWS:
            hit = selection_hit(selections[item_id][draw], candidates[item_id], targets)
            groups["hit" if hit else "miss"].append(float(cells[item_id][f"SEL{draw}"]["correct"]))
    return {name: {"draws": len(values), "SEL": _pct(statistics.fmean(values)) if values else None}
            for name, values in groups.items()}


def gold_check(cells: dict[str, dict[str, dict[str, Any]]], support: dict[str, str], answers: dict[str, str]
               ) -> dict[str, Any]:
    contradicted = sorted(item for item, label in support.items() if label == "contradicts_gold")
    picks = {}
    for arm in ANSWER_ARMS:
        chosen = [(str(cells[item][f"{arm}{draw}"].get("prediction") or ""),
                   str(cells[item][f"{arm}{draw}"]["gold_answer"]), answers.get(item))
                  for item in contradicted if item in answers for draw in DRAWS if f"{arm}{draw}" in cells[item]]
        gold_hits = sum(pick == gold for pick, gold, _ in chosen)
        owner_hits = sum(pick == owner for pick, _, owner in chosen)
        picks[arm] = {"answers": len(chosen), "gold_option": gold_hits, "owner_option": owner_hits,
                      "other": len(chosen) - gold_hits - owner_hits}
    return {"contradicts_gold_items": contradicted,
            "without_owner_option": [item for item in contradicted if item not in answers], "picks": picks}


def pick_tokens(picks: list[dict[str, Any]]) -> dict[str, float | None]:
    def mean(field: str) -> float | None:
        values = [row[field] for row in picks if isinstance(row.get(field), int)]
        return round(statistics.fmean(values), 1) if values else None
    return {"prompt": mean("prompt_tokens"), "completion": mean("completion_tokens"), "total": mean("total_tokens")}


def replication(cells: dict[str, dict[str, dict[str, Any]]], pool: list[str], wrong: list[str],
                report_path: Path = MC101_REPORT) -> dict[str, Any]:
    this = {"pool_B": alr.compare(pool, cells, "K", "B").get("B"), "pool_K": alr.compare(pool, cells, "K", "B").get("K"),
            "wrong_O": alr.compare(wrong, cells, "O", "B").get("O")}
    if not report_path.is_file():
        return {"this_run": this, "mc101": None}
    mc101 = json.loads(report_path.read_text(encoding="utf-8"))
    return {"this_run": this, "mc101": {"pool_B": mc101["primary"]["B"], "pool_K": mc101["primary"]["K"],
                                        "wrong_O": mc101["mc100_strata"]["wrong"]["O_vs_B"]["O"]},
            "mc101_report_sha256": v1.sha256_file(report_path)}


def build_report(run_dir: Path) -> dict[str, Any]:
    protocol = ls.load_protocol()
    round1 = ls.load_frozen_round1()
    round2_path = run_dir / "round2" / "manifest_round2.json"
    round2 = json.loads(round2_path.read_text(encoding="utf-8"))
    if round2["round1_manifest_sha256"] != round1["manifest_sha256"]:
        raise _fail("the round-2 manifest was not built from the frozen round-1 manifest")
    scores1_path, scores2_path = run_dir / "round1" / "scores.jsonl", run_dir / "round2" / "scores.jsonl"
    cells = alr.load_cells(_read_jsonl(scores1_path), answer_refs(round1))
    for item_id, cell in alr.load_cells(_read_jsonl(scores2_path), round2).items():
        cells.setdefault(item_id, {}).update(cell)
    pool, strata, support = round1["pool"], round1["strata"], round1["support"]
    inputs = ls.load_inputs()
    oracle = inputs.mc100["oracle"]
    oracle_items = sorted(item for item, record in oracle.items() if record["provisions"])
    selections = selections_by_item(round2)
    if set(selections) != set(pool) or any(set(by_draw) != set(DRAWS) for by_draw in selections.values()):
        raise _fail("the round-2 manifest must record a selection for every pool item and draw")
    filter_block = filter_question(oracle_items, selections, inputs.candidates, oracle)
    route_block = alr.compare(pool, cells, "SEL", "B")
    if route_block["n"] != len(pool):
        raise _fail(f"the route comparison covers {route_block['n']} of {len(pool)} items")
    in_mc100 = {item for items in strata.values() for item in items}
    primary = {name: [item for item in items if support[item] == "supports_gold"] for name, items in strata.items()}
    answers = alo.owner_answers(json.loads(lo.REGISTRATION_PATH.read_text(encoding="utf-8")))
    picks_path = run_dir / "round1" / "picks.jsonl"
    return {
        "plan_id": PLAN_ID, "card_id": "MC-111",
        "round1_manifest_sha256": round1["manifest_sha256"], "round2_manifest_sha256": round2["manifest_sha256"],
        "candidates_sha256": round1["candidates_sha256"],
        "scores_sha256": {"round1": v1.sha256_file(scores1_path), "round2": v1.sha256_file(scores2_path)},
        "filter": filter_block,
        "route": route_block,
        "rules": rules(filter_block, route_block, protocol["analysis"]["alpha"]),
        "mc100_strata": {name: group_block(items, cells, gain_share=name == "wrong") for name, items in primary.items()},
        "outside_mc100": group_block([item for item in pool if item not in in_mc100], cells),
        "selection": selection_behaviour(pool, oracle_items, selections, inputs.candidates, oracle),
        "by_selection": by_selection(oracle_items, selections, inputs.candidates, oracle, cells),
        "gold_check": gold_check(cells, support, answers),
        "descriptive": {
            "share_answering_A": {arm: alo.letter_share(cells, arm) for arm in ANSWER_ARMS},
            "mean_tokens": {**{arm: alo.token_means(cells, arm) for arm in ANSWER_ARMS},
                            "PICK": pick_tokens(_read_jsonl(picks_path)) if picks_path.is_file() else None},
        },
        "replication": replication(cells, pool, primary["wrong"]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    registered = json.loads(ls.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.run_dir / "analysis" / "legal_select_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"filter: n={report['filter']['n']} PICK={report['filter']['PICK']} BM25 top 2={report['filter']['BM25_top2']}")
    print(f"route: n={report['route']['n']} B={report['route']['B']} SEL={report['route']['SEL']}")
    print(f"rules: {report['rules']}")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
