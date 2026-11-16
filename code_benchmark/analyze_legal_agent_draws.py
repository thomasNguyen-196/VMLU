"""MC-115's registered analysis (plan diagnostic-legal-agent-draws), run once after every attempt is final.

The item score is the mean over draws 1-4: draws 1-2 from the earlier cards' score files (MC-111's B and MC-112/113's
DSHF and OMPF on the Legal MC items; MC-114's DSHF, OMPF, B and C on the other items), each read by its registered
SHA-256, and draws 3-4 from MC-115. Tests, Holm over three within each part:
  Part M (246 items, correctness):  M1 OMPF-DSHF, M2 DSHF-B, M3 OMPF-B, margin 2.24 points
  Part S (400 items, token-F1 v3):  S1 OMPF-DSHF, S2 DSHF-C, S3 OMPF-C, no margin
Each: mean per-item difference, 95% percentile bootstrap (2,000, seed 7), two-sided paired sign-flip p (20,000, seed 7).
Beside, not tested: the same comparisons on draws 3-4 alone, each arm's drift between rounds, its draw-to-draw
disagreement and within-item SD, and Part M by source.

From the repo root:
  .venv/bin/python -m code_benchmark.analyze_legal_agent_draws --run-dir all_res/diagnostic_legal_agent_draws/run/<profile>
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_diagnostic_router as ar
    from code_benchmark import analyze_legal_agent_v2 as alv2
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_legal_agent_draws as ld
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_diagnostic_router as ar  # type: ignore[no-redef]
    import analyze_legal_agent_v2 as alv2  # type: ignore[no-redef]
    import analyze_router_labels as arl  # type: ignore[no-redef]
    import diagnostic_legal_agent_draws as ld  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

PLAN_ID = "diagnostic-legal-agent-draws"
CARD_ID = "MC-115"
REPORT_FILE = "legal_agent_draws_report.json"
ALL_DRAWS = ("1", "2", "3", "4")
OLD_DRAWS = ("1", "2")
NEW_DRAWS = ("3", "4")
METRIC = {"M": "correct", "S": "token_f1"}
Cells = dict[str, dict[str, dict[str, Any]]]


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


# ---------------------------------------------------------------- cells

def earlier_cells(protocol: dict[str, Any], manifest: dict[str, Any], root: Path = ld.ROOT) -> Cells:
    """Draws 1-2 of every compared arm: MC-111's B, MC-112's DSHF and MC-113's OMPF on the Legal MC items; MC-114's
    DSHF, OMPF, B and C on the other items. Each score file is read by its registered SHA-256."""
    cells: Cells = {}
    datasets = set(manifest["dataset_counts"])
    for name, spec in protocol["reference"].items():
        rows = alv2.load_reference(protocol, name, root)
        targets = [ld.LEGAL_MC] if name != "mc114_scores" else sorted(datasets - {ld.LEGAL_MC})
        for dataset_id in targets:
            alv2.add_rows(cells, rows, tuple(spec["arms"]), dataset_id)
    return cells


def merge(old: Cells, new: Cells) -> Cells:
    out: Cells = {key: dict(cell) for key, cell in old.items()}
    for key, cell in new.items():
        clash = set(cell) & set(out.get(key, {}))
        if clash:
            raise _fail(f"{key}: draws {sorted(clash)} appear in both an earlier card and MC-115")
        out.setdefault(key, {}).update(cell)
    return out


def check_complete(cells: Cells, parts: dict[str, list[str]]) -> None:
    for part, keys in parts.items():
        for key in keys:
            missing = [f"{arm}{draw}" for arm in ld.PART_ARMS[part] for draw in ALL_DRAWS
                       if f"{arm}{draw}" not in cells.get(key, {})]
            if missing:
                raise _fail(f"{key} lacks {missing[:4]}; every compared arm needs draws 1-4")


# ---------------------------------------------------------------- statistics

def item_score(cell: dict[str, dict[str, Any]], arm: str, metric: str, draws: tuple[str, ...]) -> float:
    return statistics.fmean(float(cell[f"{arm}{draw}"].get(metric) or 0.0) for draw in draws)


def compare(keys: list[str], cells: Cells, left: str, right: str, metric: str,
            draws: tuple[str, ...] = ALL_DRAWS) -> dict[str, Any]:
    a = [item_score(cells[key], left, metric, draws) for key in keys]
    b = [item_score(cells[key], right, metric, draws) for key in keys]
    return {"n": len(keys), "draws": list(draws), left: _pct(statistics.fmean(a)), right: _pct(statistics.fmean(b)),
            f"{left}_versus_{right}": arl.difference_block(a, b)}


def questions(keys: list[str], cells: Cells, spec: dict[str, list[str]], metric: str,
              draws: tuple[str, ...] = ALL_DRAWS) -> dict[str, Any]:
    return {name: compare(keys, cells, left, right, metric, draws) for name, (left, right) in spec.items()}


def drift(keys: list[str], cells: Cells, arm: str, metric: str) -> dict[str, Any]:
    """Mean of draws 3-4 minus mean of draws 1-2, per item, with a bootstrap CI: a server change between rounds
    would show here."""
    old = [item_score(cells[key], arm, metric, OLD_DRAWS) for key in keys]
    new = [item_score(cells[key], arm, metric, NEW_DRAWS) for key in keys]
    diffs = [b - a for a, b in zip(old, new, strict=True)]
    return {"draws_1_2": _pct(statistics.fmean(old)), "draws_3_4": _pct(statistics.fmean(new)),
            "drift_points": _pct(statistics.fmean(diffs)), "ci95_points": ar.bootstrap_mean_ci(diffs)}


def noise(keys: list[str], cells: Cells, arm: str, metric: str) -> dict[str, Any]:
    """Within-item spread over the four draws: the mean within-item SD (points) and, on correctness, the share of
    items whose four draws do not all agree."""
    sds = [statistics.pstdev([float(cells[key][f"{arm}{d}"].get(metric) or 0.0) for d in ALL_DRAWS]) for key in keys]
    out: dict[str, Any] = {"mean_within_item_sd_points": _pct(statistics.fmean(sds))}
    if metric == "correct":
        out["items_with_disagreeing_draws_pct"] = _pct(sum(sd > 0 for sd in sds) / len(sds))
    return out


# ---------------------------------------------------------------- the report

def build_report(run_dir: Path, root: Path = ld.ROOT, protocol: dict[str, Any] | None = None,
                 manifest: dict[str, Any] | None = None, old: Cells | None = None) -> dict[str, Any]:
    protocol = protocol or ld.load_protocol()
    manifest = manifest or ld.load_frozen_manifest()
    scores_path = run_dir / "scores.jsonl"
    new = alv2.load_cells([json.loads(line) for line in scores_path.read_text(encoding="utf-8").splitlines()
                           if line.strip()], manifest)
    cells = merge(earlier_cells(protocol, manifest, root) if old is None else old, new)
    parts = {part: list(keys) for part, keys in manifest["parts"].items()}
    check_complete(cells, parts)
    plan = protocol["analysis"]
    alpha = plan["alpha"]
    out: dict[str, Any] = {"plan_id": PLAN_ID, "card_id": CARD_ID, "manifest_sha256": manifest["manifest_sha256"],
                           "scores_sha256": v1.sha256_file(scores_path),
                           "reference_sha256": {name: spec["sha256"] for name, spec in protocol["reference"].items()}}
    for part in ("M", "S"):
        spec, keys, metric = plan[f"part_{part}"], parts[part], METRIC[part]
        blocks = questions(keys, cells, spec["questions"], metric)
        out[f"part_{part}"] = {
            "n_items": len(keys), "item_score": "mean over draws 1-4", "questions": blocks,
            "rules": alv2.rules(blocks, spec["questions"], alpha, spec["margin_points"], spec["margin_on"]),
        }
    beside: dict[str, Any] = {}
    for part in ("M", "S"):
        spec, keys, metric = plan[f"part_{part}"], parts[part], METRIC[part]
        arms = ld.PART_ARMS[part]
        beside[part] = {
            "draws_3_4_only": questions(keys, cells, spec["questions"], metric, NEW_DRAWS),
            "draws_1_2_only": questions(keys, cells, spec["questions"], metric, OLD_DRAWS),
            "drift": {arm: drift(keys, cells, arm, metric) for arm in arms},
            "noise": {arm: noise(keys, cells, arm, metric) for arm in arms},
        }
    m_keys = parts["M"]
    beside["M"]["by_source"] = {
        source: questions([k for k in m_keys if (k.startswith(f"{ld.LEGAL_MC}:")) == (source == "legal_mc")],
                          cells, plan["part_M"]["questions"], METRIC["M"])
        for source in ("legal_mc", "vmlu_law")}
    out["beside_not_tested"] = beside
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    registered = json.loads(ld.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
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
    print(f"report -> {out} sha256 {v1.sha256_file(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
