"""The registered analysis of the Legal MC retrieval test (plan diagnostic-legal-retrieval-v1; card MC-101).

Run once, after the run:
  .venv/bin/python -m code_benchmark.analyze_legal_retrieval --run-dir all_res/diagnostic_legal_retrieval/run/<profile>

* Item score: the mean correctness of an arm over its two draws (0, 0.5 or 1).
* Primary: always-K against always-B over the 134 items: the mean per-item difference with a percentile bootstrap
  interval (2,000 resamples, seed 7) and a two-sided sign-flip p-value (20,000 resamples, seed 7).
* Reading rule: K becomes the Legal MC arm of the router when its mean exceeds B's and p < 0.05; otherwise
  always-B stays the Legal MC route.
* Description: per MC-100 stratum on supports_gold items, K and O against B and K against O, with the share of O's
  gain K keeps in stratum `wrong`; K against B on the items outside MC-100; retrieval hits against the MC-100 oracle
  articles and each arm's accuracy on hit and miss items; each arm's options on contradicts_gold items (gold, the
  owner's option, other); the share answering A; mean tokens; evidence length.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_legal_oracle as alo
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_legal_retrieval as lr
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_legal_oracle as alo
    import analyze_router_labels as arl
    import diagnostic_legal_oracle as lo
    import diagnostic_legal_retrieval as lr
    import diagnostic_prospective as dp
    import vi_multimodel as v1

PLAN_ID = "diagnostic-legal-retrieval-v1"
DRAWS = ("1", "2")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def load_cells(scores: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """{item_id: {"B1": row, "B2": row, "K1": ..., "O2": ...}}; every manifest attempt must be scored."""
    by_key = {dp.run_key(row): row for row in scores}
    cells: dict[str, dict[str, dict[str, Any]]] = {}
    for ref in manifest["items"]:
        key = dp.run_key(ref)
        if key not in by_key:
            raise _fail(f"no scored row for {key}")
        arm, _, draw = ref["replicate_id"].partition("-r")
        cells.setdefault(ref["item_id"], {})[f"{arm}{draw}"] = by_key[key]
    return cells


def arm_mean(cell: dict[str, dict[str, Any]], arm: str) -> float:
    return statistics.fmean(float(cell[f"{arm}{draw}"]["correct"]) for draw in DRAWS)


def compare(item_ids: list[str], cells: dict[str, dict[str, dict[str, Any]]], left: str, right: str
            ) -> dict[str, Any]:
    """`left` against `right` on the items that ran both arms."""
    both = [item for item in item_ids if f"{left}1" in cells[item] and f"{right}1" in cells[item]]
    if not both:
        return {"n": 0}
    a = [arm_mean(cells[item], left) for item in both]
    b = [arm_mean(cells[item], right) for item in both]
    return {"n": len(both), left: _pct(statistics.fmean(a)), right: _pct(statistics.fmean(b)),
            f"{left}_versus_{right}": arl.difference_block(a, b),
            "clear_rescues": sum(x == 1.0 and y == 0.0 for x, y in zip(a, b, strict=True)),
            "clear_regressions": sum(x == 0.0 and y == 1.0 for x, y in zip(a, b, strict=True))}


def reading_rule(primary: dict[str, Any], alpha: float) -> dict[str, Any]:
    block = primary["K_versus_B"]
    adopt = block["mean_points"] > 0 and block["sign_flip_p"] < alpha
    return {"mean_points": block["mean_points"], "sign_flip_p": block["sign_flip_p"], "alpha": alpha,
            "k_beats_b": adopt, "legal_mc_route": "K" if adopt else "B"}


def stratum_blocks(strata: dict[str, list[str]], support: dict[str, str],
                   cells: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    out = {}
    for name, items in strata.items():
        primary = [item for item in items if support[item] == "supports_gold"]
        k_b, o_b = compare(primary, cells, "K", "B"), compare(primary, cells, "O", "B")
        block: dict[str, Any] = {"K_vs_B": k_b, "O_vs_B": o_b, "K_vs_O": compare(primary, cells, "K", "O")}
        if name == "wrong" and k_b.get("n") and o_b.get("n"):
            gain = o_b["O_versus_B"]["mean_points"]
            block["share_of_O_gain_kept_by_K"] = (round(k_b["K_versus_B"]["mean_points"] / gain, 4)
                                                  if gain > 0 else None)
        out[name] = block
    return out


def hit_split(hits: dict[str, Any], cells: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Each arm's accuracy where the top 2 units hold an oracle article and where they do not."""
    groups = {"hit_at_2": [row["item_id"] for row in hits["per_item"]
                           if row["first_hit_rank"] is not None and row["first_hit_rank"] <= 2],
              "miss_at_2": [row["item_id"] for row in hits["per_item"]
                            if row["first_hit_rank"] is None or row["first_hit_rank"] > 2]}
    return {name: {"n": len(items), **{arm: _pct(statistics.fmean(arm_mean(cells[item], arm) for item in items))
                                       for arm in ("B", "K", "O") if items and all(f"{arm}1" in cells[item]
                                                                                   for item in items)}}
            for name, items in groups.items()}


def gold_check(cells: dict[str, dict[str, dict[str, Any]]], support: dict[str, str], answers: dict[str, str]
               ) -> dict[str, Any]:
    """On the contradicts_gold items, which option each arm picks: the gold's, the owner's or another."""
    contradicted = sorted(item for item, label in support.items() if label == "contradicts_gold")
    picks = {}
    for arm in ("B", "K", "O"):
        chosen = [(str(cells[item][f"{arm}{draw}"].get("prediction") or ""),
                   str(cells[item][f"{arm}{draw}"]["gold_answer"]), answers.get(item))
                  for item in contradicted if item in answers for draw in DRAWS if f"{arm}{draw}" in cells[item]]
        gold_hits = sum(pick == gold for pick, gold, _ in chosen)
        owner_hits = sum(pick == owner for pick, _, owner in chosen)
        picks[arm] = {"answers": len(chosen), "gold_option": gold_hits, "owner_option": owner_hits,
                      "other": len(chosen) - gold_hits - owner_hits}
    return {"contradicts_gold_items": contradicted,
            "without_owner_option": [item for item in contradicted if item not in answers], "picks": picks}


def build_report(run_dir: Path) -> dict[str, Any]:
    protocol = lr.load_protocol()
    manifest = lr.load_frozen_manifest()
    scores_path = run_dir / "scores.jsonl"
    scores = [json.loads(line) for line in scores_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cells = load_cells(scores, manifest)
    pool, strata, support = manifest["pool"], manifest["strata"], manifest["support"]
    primary = compare(pool, cells, "K", "B")
    if primary["n"] != len(pool):
        raise _fail(f"the primary comparison covers {primary['n']} of {len(pool)} items")
    index = lr.load_index()
    records = lr.load_k_evidence(lr.EVIDENCE_PATH, pool, index)
    mc100 = lr.mc100_frozen()
    hits = lr.hit_report(records, mc100["oracle"], index)
    in_mc100 = {item for items in strata.values() for item in items}
    answers = alo.owner_answers(json.loads(lo.REGISTRATION_PATH.read_text(encoding="utf-8")))
    k_chars = [sum(len(provision["text"]) for provision in record["provisions"]) for record in records.values()]
    return {
        "plan_id": PLAN_ID, "card_id": "MC-101", "manifest_sha256": manifest["manifest_sha256"],
        "k_evidence_sha256": manifest["k_evidence_sha256"], "corpus_sha256": manifest["corpus_sha256"],
        "scores_sha256": v1.sha256_file(scores_path),
        "primary": primary,
        "reading_rule": reading_rule(primary, protocol["analysis"]["reading_rule"]["alpha"]),
        "mc100_strata": stratum_blocks(strata, support, cells),
        "outside_mc100": compare([item for item in pool if item not in in_mc100], cells, "K", "B"),
        "retrieval": {**{key: value for key, value in hits.items() if key != "per_item"},
                      "by_hit": hit_split(hits, cells)},
        "gold_check": gold_check(cells, support, answers),
        "descriptive": {
            "share_answering_A": {arm: alo.letter_share(cells, arm) for arm in lr.ARMS},
            "mean_tokens": {arm: alo.token_means(cells, arm) for arm in lr.ARMS},
            "k_evidence_chars": {"mean": round(statistics.fmean(k_chars), 1), "max": max(k_chars)},
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    registered = json.loads(lr.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.run_dir / "analysis" / "legal_retrieval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    block = report["primary"]
    print(f"pool: n={block['n']} B={block['B']} K={block['K']} K-B={block['K_versus_B']['mean_points']} "
          f"p={block['K_versus_B']['sign_flip_p']:.4f}")
    print(f"reading rule: {report['reading_rule']}")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
