"""The registered analysis of MC-114 (plan diagnostic-legal-agent-v2; openspec change diagnostic-legal-agent-v2).

Run once, after the run:
  .venv/bin/python -m code_benchmark.analyze_legal_agent_v2 --run-dir all_res/diagnostic_legal_agent_v2/run/<profile>

* Item score: an arm's mean over its two draws of `correct` (part M) or vi-reading-v3 token-F1 (part S), in points.
* Each test: the mean per-item difference, a 95% percentile bootstrap (2,000 resamples, seed 7) and a two-sided
  paired sign-flip p-value (20,000 resamples, seed 7) (`analyze_router_labels.difference_block`).
* Part M, pooled 246 items, Holm over 2: M1 OMPF vs DSHF (needs a gap above 2.24 points), M2 DSHF vs DSH. The 134
  Legal MC items use MC-112's DSH and DSHF and MC-113's OMPF, read by registered SHA-256; the 112 VMLU items use
  this card's arms.
* Part S, 400 items, Holm over 3: S1 OMPF vs DSHF, S2 DSHF vs DSH, S3 DSHF vs C.
* Reading rule: an arm is better when its mean is higher and its Holm-adjusted p is below alpha (and, where a margin
  applies, the gap exceeds it); worse in the mirror case; otherwise no clear difference.
* Description: each part's tests on its subsets; part M against B, by support label, on the stale-gold items and the
  contradicts/unclear items; part S against O and beside MC-96; behaviour, retrieval hits and scores by retrieval.
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
    from code_benchmark import analyze_legal_agent as ala
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_agent_v2 as l2
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_diagnostic_prospective as adp  # type: ignore[no-redef]
    import analyze_legal_agent as ala  # type: ignore[no-redef]
    import analyze_router_labels as arl  # type: ignore[no-redef]
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

PLAN_ID = "diagnostic-legal-agent-v2"
CARD_ID = "MC-114"
DRAWS = ("1", "2")
HITS = ala.HITS
REPORT_FILE = "legal_agent_v2_report.json"
METRIC = {"M": "correct", "S": "token_f1"}
LEGAL_MC = "vi-multimodel-v1-legal-mc-146"
MC96_DATASET = "bidlqa-train-retrieval"

Cells = dict[str, dict[str, dict[str, Any]]]


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_cells(scores: list[dict[str, Any]], manifest: dict[str, Any]) -> Cells:
    """{item key: {"DSH1": row, ...}}; every manifest attempt must be scored."""
    by_key = {dp.run_key(row): row for row in scores}
    cells: Cells = {}
    for ref in manifest["items"]:
        key = dp.run_key(ref)
        if key not in by_key:
            raise _fail(f"no scored row for {key}")
        arm, _, draw = ref["replicate_id"].partition("-r")
        cells.setdefault(dp.item_key(ref["dataset_id"], ref["item_id"]), {})[f"{arm}{draw}"] = by_key[key]
    return cells


def load_reference(protocol: dict[str, Any], name: str, root: Path = l2.ROOT) -> list[dict[str, Any]]:
    spec = protocol["reference"][name]
    path = root / spec["path"]
    if not path.is_file() or v1.sha256_file(path) != spec["sha256"]:
        raise _fail(f"{spec['card']}'s score file {path} is missing or differs from its registered SHA-256")
    return _read_jsonl(path)


def add_rows(cells: Cells, rows: list[dict[str, Any]], arms: tuple[str, ...], dataset_id: str) -> None:
    """Put `arms` of an earlier card's rows into cells keyed by item key, as DSH1, DSH2, ..."""
    for row in rows:
        arm, _, draw = str(row["replicate_id"]).partition("-r")
        if arm in arms and row["dataset_id"] == dataset_id:
            cells.setdefault(dp.item_key(row["dataset_id"], row["item_id"]), {})[f"{arm}{draw}"] = row


def legal_mc_cells(protocol: dict[str, Any], root: Path = l2.ROOT) -> Cells:
    """The 134 Legal MC items: DSH and DSHF from MC-112, OMPF from MC-113, every draw present."""
    cells: Cells = {}
    add_rows(cells, load_reference(protocol, "mc112_scores", root), ("DSH", "DSHF"), LEGAL_MC)
    add_rows(cells, load_reference(protocol, "mc113_scores", root), ("OMPF",), LEGAL_MC)
    incomplete = [key for key, cell in cells.items()
                  if not all(f"{arm}{draw}" in cell for arm in ("DSH", "DSHF", "OMPF") for draw in DRAWS)]
    if incomplete or len(cells) != 134:
        raise _fail(f"MC-112/113's Legal MC cells: {len(cells)} items, incomplete {incomplete[:3]}")
    return cells


def item_score(cell: dict[str, dict[str, Any]], arm: str, metric: str) -> float:
    return statistics.fmean(float(cell[f"{arm}{draw}"].get(metric) or 0.0) for draw in DRAWS)


def compare(keys: list[str], cells: Cells, left: str, right: str, metric: str) -> dict[str, Any]:
    both = [key for key in keys if f"{left}1" in cells[key] and f"{right}1" in cells[key]]
    if not both:
        return {"n": 0}
    a = [item_score(cells[key], left, metric) for key in both]
    b = [item_score(cells[key], right, metric) for key in both]
    return {"n": len(both), left: _pct(statistics.fmean(a)), right: _pct(statistics.fmean(b)),
            f"{left}_versus_{right}": arl.difference_block(a, b)}


def questions(keys: list[str], cells: Cells, spec: dict[str, list[str]], metric: str) -> dict[str, Any]:
    blocks = {name: compare(keys, cells, left, right, metric) for name, (left, right) in spec.items()}
    short = [name for name, block in blocks.items() if block["n"] != len(keys)]
    if short:
        raise _fail(f"the comparisons {short} do not cover all {len(keys)} items")
    return blocks


def rules(blocks: dict[str, dict[str, Any]], spec: dict[str, list[str]], alpha: float, margin: float,
          margin_on: list[str]) -> dict[str, Any]:
    tests = {name: blocks[name][f"{left}_versus_{right}"] for name, (left, right) in spec.items()}
    adjusted = adp.holm_adjust({name: test["sign_flip_p"] for name, test in tests.items()})
    out: dict[str, Any] = {"alpha": alpha, "multiplicity": "holm", "margin_points": margin, "margin_on": margin_on}
    for name, (left, right) in spec.items():
        mean, p = tests[name]["mean_points"], adjusted[name]
        gap = margin if name in margin_on else 0.0
        better, worse = mean > gap and p < alpha, mean < -gap and p < alpha
        out[name] = {"left": left, "right": right, "mean_points": mean, "sign_flip_p": tests[name]["sign_flip_p"],
                     "p_holm": round(p, 6), "left_better": better, "left_worse": worse,
                     "reading": (f"{left} is better than {right}" if better else f"{left} is worse than {right}"
                                 if worse else f"no clear difference between {left} and {right}")}
    return out


# ---------------------------------------------------------------- description

def attempt_hits(run_dir: Path, cells: Cells, keys: list[str], provisions: dict[str, dict[str, Any]]
                 ) -> dict[str, dict[str, dict[str, bool]]]:
    """{item key: {"DSH1": {seen, read, opened}, ...}} for the agent arms, each parsed by its harness's parser."""
    out: dict[str, dict[str, dict[str, bool]]] = {}
    for key in keys:
        targets = provisions[key.split(":", 1)[1]]["provisions"]
        for arm in l2.AGENT_ARMS:
            parse = ot.omp_observations if arm == "OMPF" else la.model_observations
            for draw in DRAWS:
                per = la.provision_hits(parse(ala.load_attempt_records(run_dir, cells[key][f"{arm}{draw}"])), targets)
                out.setdefault(key, {})[f"{arm}{draw}"] = {kind: any(p[kind] for p in per) for kind in HITS}
    return out


def behaviour(cells: Cells, keys: list[str], arms: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    for arm in arms:
        rows = [cells[key][f"{arm}{draw}"] for key in keys for draw in DRAWS]
        tools: Counter[str] = Counter()
        for row in rows:
            tools.update(row.get("tool_calls") or {})
        tokens = [float(dp.reported_tokens(row) or 0) for row in rows]
        out[arm] = {
            "attempts": len(rows), "searched_share": round(statistics.fmean(bool(row.get("tool_calls")) for row in rows), 4),
            "tool_calls_per_attempt": {name: round(count / len(rows), 3) for name, count in sorted(tools.items())},
            "requests_per_attempt": round(statistics.fmean(int(row.get("requests_forwarded", row.get("requests"))
                                                               or 1) for row in rows), 3),
            "outcomes": dict(sorted(Counter(str(row.get("outcome") or "complete") for row in rows).items())),
            "mean_reported_tokens": round(statistics.fmean(tokens), 1),
        }
    return out


def retrieval(keys: list[str], hits: dict[str, dict[str, dict[str, bool]]]) -> dict[str, Any]:
    if not keys:
        return {"n_items": 0}
    return {"n_items": len(keys), **{arm: {kind: _pct(statistics.fmean(float(hits[key][f"{arm}{draw}"][kind])
                                                                         for key in keys for draw in DRAWS))
                                           for kind in HITS} for arm in l2.AGENT_ARMS}}


def by_retrieval(cells: Cells, keys: list[str], hits: dict[str, dict[str, dict[str, bool]]], metric: str
                 ) -> dict[str, Any]:
    """Attempt-level score when the governing provision was read and when it was not."""
    out = {}
    for arm in l2.AGENT_ARMS:
        groups: dict[str, list[float]] = {"read": [], "not_read": []}
        for key in keys:
            for draw in DRAWS:
                groups["read" if hits[key][f"{arm}{draw}"]["read"] else "not_read"].append(
                    float(cells[key][f"{arm}{draw}"].get(metric) or 0.0))
        out[arm] = {name: {"attempts": len(values), "mean_points": _pct(statistics.fmean(values)) if values else None}
                    for name, values in groups.items()}
    return out


def arm_means(cells: Cells, keys: list[str], arms: tuple[str, ...], metric: str) -> dict[str, Any]:
    return {"n_items": len(keys), **{arm: _pct(statistics.fmean(item_score(cells[key], arm, metric) for key in keys))
                                     for arm in arms if keys}}


def gold_check(cells: Cells, keys: list[str], support: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label in ("contradicts_gold", "unclear"):
        chosen = sorted(key for key in keys if support[key] == label)
        out[label] = {"items": chosen, "picks": {
            arm: dict(Counter("gold" if str(cells[key][f"{arm}{draw}"].get("prediction") or "")
                              == str(cells[key][f"{arm}{draw}"]["gold_answer"]) else "other"
                              for key in chosen for draw in DRAWS)) for arm in l2.PART_ARMS["M"]}}
    return out


def mc96_context(cells: Cells, keys: list[str], protocol: dict[str, Any], root: Path = l2.ROOT) -> dict[str, Any]:
    """On part S train items MC-96 also ran: C beside MC-96's closed-book B, DSHF and OMPF beside its K (BM25 top 2)."""
    mc96: Cells = {}
    for row in load_reference(protocol, "mc96_scores", root):
        if row["dataset_id"] == MC96_DATASET:
            arm, _, draw = str(row["replicate_id"]).partition("-r")
            mc96.setdefault(row["item_id"], {})[f"{arm}{draw}"] = row
    shared = [key for key in keys if key.startswith("bidlqa-train:") and key.split(":", 1)[1] in mc96]
    if not shared:
        return {"n_items": 0}
    def mean(table: Cells, ids: list[str], arm: str) -> float:
        return _pct(statistics.fmean(item_score(table[i], arm, "token_f1") for i in ids))
    ids = [key.split(":", 1)[1] for key in shared]
    return {"n_items": len(shared),
            "this_card": {arm: mean(cells, shared, arm) for arm in ("C", "DSHF", "OMPF", "O")},
            "mc96": {arm: mean(mc96, ids, arm) for arm in ("B", "K", "O") if all(f"{arm}1" in mc96[i] for i in ids)}}


def build_report(run_dir: Path, root: Path = l2.ROOT) -> dict[str, Any]:
    protocol = l2.load_protocol()
    manifest = l2.load_frozen_manifest()
    scores_path = run_dir / "scores.jsonl"
    cells = load_cells(_read_jsonl(scores_path), manifest)
    plan = protocol["analysis"]
    alpha, margin = plan["alpha"], plan["margin_points"]
    m_keys, s_keys = manifest["parts"]["M"], manifest["parts"]["S"]
    support = manifest["support"]
    provisions = l2.load_provisions()
    # part M: pooled with the 134 Legal MC items
    legal = legal_mc_cells(protocol, root)
    pooled = {**legal, **{key: cells[key] for key in m_keys}}
    pooled_keys = [*sorted(legal), *m_keys]
    m_spec, s_spec = plan["part_M"]["questions"], plan["part_S"]["questions"]
    m_blocks = questions(pooled_keys, pooled, m_spec, METRIC["M"])
    s_blocks = questions(s_keys, cells, s_spec, METRIC["S"])
    agent_keys = [*m_keys, *s_keys]
    hits = attempt_hits(run_dir, cells, agent_keys, provisions)
    m_provision_keys = [key for key in m_keys if support[key] != "no_provision"]
    m_supports = [key for key in m_keys if support[key] == "supports_gold"]
    stale = [key for key in m_keys if key.split(":", 1)[1] in set(plan["part_M"]["stale_gold_items"]["items"])]
    return {
        "plan_id": PLAN_ID, "card_id": CARD_ID, "manifest_sha256": manifest["manifest_sha256"],
        "scores_sha256": v1.sha256_file(scores_path),
        "reference_sha256": {name: spec["sha256"] for name, spec in protocol["reference"].items()},
        "part_M": {
            "n_items": len(pooled_keys), "questions": m_blocks,
            "rules": rules(m_blocks, m_spec, alpha, margin, plan["part_M"]["margin_on"]),
            "new_items_only": {name: compare(m_keys, cells, left, right, METRIC["M"])
                               for name, (left, right) in m_spec.items()},
            "legal_mc_only": {name: compare(sorted(legal), legal, left, right, METRIC["M"])
                              for name, (left, right) in m_spec.items()},
        },
        "part_S": {
            "n_items": len(s_keys), "splits": manifest["part_s_splits"], "questions": s_blocks,
            "rules": rules(s_blocks, s_spec, alpha, margin, plan["part_S"]["margin_on"]),
        },
        "part_M_description": {
            "against_B": {arm: compare(m_keys, cells, arm, "B", METRIC["M"]) for arm in l2.AGENT_ARMS},
            "by_support": {label: arm_means(cells, [k for k in m_keys if support[k] == label], l2.PART_ARMS["M"],
                                            METRIC["M"])
                           for label in ("supports_gold", "no_provision", "unclear", "contradicts_gold")},
            "stale_gold": arm_means(cells, stale, l2.PART_ARMS["M"], METRIC["M"]),
            "gold_check": gold_check(cells, m_keys, support),
        },
        "part_S_description": {
            "means": arm_means(cells, s_keys, l2.PART_ARMS["S"], METRIC["S"]),
            "em_v3": arm_means(cells, s_keys, l2.PART_ARMS["S"], "em"),
            "token_recall": arm_means(cells, s_keys, l2.PART_ARMS["S"], "token_recall"),
            "against_O": {arm: compare(s_keys, cells, arm, "O", METRIC["S"]) for arm in (*l2.AGENT_ARMS, "C")},
            "by_split": {split: arm_means(cells, [k for k in s_keys if k.startswith(f"{dataset}:")],
                                          l2.PART_ARMS["S"], METRIC["S"])
                         for split, dataset in (("train", "bidlqa-train"), ("val", "bidlqa-val"),
                                                ("test", "vi-multimodel-v1-bidlqa-test"))},
            "mc96_context": mc96_context(cells, s_keys, protocol, root),
        },
        "behaviour": {"M": behaviour(cells, m_keys, l2.PART_ARMS["M"]), "S": behaviour(cells, s_keys, l2.PART_ARMS["S"])},
        "retrieval": {"M": retrieval(m_provision_keys, hits), "S": retrieval(s_keys, hits)},
        "by_retrieval": {"M_supports_gold": by_retrieval(cells, m_supports, hits, METRIC["M"]),
                         "S": by_retrieval(cells, s_keys, hits, METRIC["S"])},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    registered = json.loads(l2.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.run_dir / "analysis" / REPORT_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for part in ("part_M", "part_S"):
        for name, rule in report[part]["rules"].items():
            if isinstance(rule, dict):
                print(f"{part} {name}: {rule['left']}-{rule['right']} {rule['mean_points']:+.2f} "
                      f"p_holm={rule['p_holm']:.4f} -> {rule['reading']}")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
