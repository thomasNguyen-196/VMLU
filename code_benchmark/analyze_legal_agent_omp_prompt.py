"""MC-117's registered analysis (plan diagnostic-legal-agent-omp-prompt), run once after both models' runs are final.

The item score is the mean over draws 1-2. Comparators come from the registered score files by SHA-256:
  Qwen  OMPF and DSHF from MC-113 and MC-112 on the 134 Legal MC items and from MC-114 on the others (draws 1-2),
        OMPF draws 3-4 from MC-115 (beside only);
  MiMo  OMPF and DSHF from MC-116 (draws 1-2).
Tests per part, Holm over three, margin 2.24 points on Part M and none on Part S:
  P1  Qwen OMPS - OMPF;   P2  MiMo OMPS - OMPF;   P3  per item, MiMo's (OMPS - OMPF) - Qwen's (OMPS - OMPF).
Each: mean per-item difference, 95% percentile bootstrap (2,000, seed 7), two-sided paired sign-flip p (20,000, seed 7).
P3 reads "omp's default prompt carries part of the interaction" when it is below -margin with a Holm p below 0.05,
"carries none detectable" when its interval lies within +-margin (Part M) or contains 0 (Part S), else "not determined".
Beside, not tested: the remaining interaction (OMPS - DSHF of MiMo minus Qwen's) against the original, P1 against
Qwen's OMPF draws 1-4, the two action-flow indicators per model and arm, and attempt profiles.

From the repo root:
  .venv/bin/python -m code_benchmark.analyze_legal_agent_omp_prompt
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_harness_flows as ahf
    from code_benchmark import analyze_legal_agent_draws as ad
    from code_benchmark import analyze_legal_agent_v2 as alv2
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_legal_agent_draws as ld
    from code_benchmark import diagnostic_legal_agent_omp_prompt as lp
    from code_benchmark import harness_flow as hf
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_harness_flows as ahf  # type: ignore[no-redef]
    import analyze_legal_agent_draws as ad  # type: ignore[no-redef]
    import analyze_legal_agent_v2 as alv2  # type: ignore[no-redef]
    import analyze_router_labels as arl  # type: ignore[no-redef]
    import diagnostic_legal_agent_draws as ld  # type: ignore[no-redef]
    import diagnostic_legal_agent_omp_prompt as lp  # type: ignore[no-redef]
    import harness_flow as hf  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

PLAN_ID = "diagnostic-legal-agent-omp-prompt"
CARD_ID = "MC-117"
REPORT_FILE = "legal_agent_omp_prompt_report.json"
DRAWS = ("1", "2")
QWEN_ALL = ("1", "2", "3", "4")
METRIC = ad.METRIC
Cells = dict[str, dict[str, dict[str, Any]]]
# reference score file -> (model, arms, items it covers)
COMPARATORS = {"mc112_scores": ("qwen", ("DSHF",), "legal"), "mc113_scores": ("qwen", ("OMPF",), "legal"),
               "mc114_scores": ("qwen", ("DSHF", "OMPF"), "other"), "mc115_scores": ("qwen", ("DSHF", "OMPF"), "all"),
               "mc116_scores": ("mimo", ("DSHF", "OMPF"), "all")}
ORIGINAL_INTERACTION = {"M": 14.63, "S": 11.64}  # MC-116's registered report (b6f8a7cb...), beside


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


# ---------------------------------------------------------------- cells

def comparator_cells(protocol: dict[str, Any], manifest: dict[str, Any], root: Path = lp.ROOT
                     ) -> tuple[dict[str, Cells], dict[str, Path]]:
    """{model: cells of OMPF and DSHF}, and {score file name: its run directory} for the action flows."""
    datasets = set(manifest["dataset_counts"])
    cells: dict[str, Cells] = {model: {} for model in lp.MODELS}
    run_dirs = {}
    for name, (model, arms, scope) in COMPARATORS.items():
        rows = alv2.load_reference(protocol, name, root)
        run_dirs[name] = (root / protocol["reference"][name]["path"]).parent
        targets = ([ld.LEGAL_MC] if scope == "legal" else sorted(datasets - {ld.LEGAL_MC}) if scope == "other"
                   else sorted(datasets))
        for dataset_id in targets:
            alv2.add_rows(cells[model], rows, arms, dataset_id)
    return cells, run_dirs


def merge(base: Cells, extra: Cells) -> Cells:
    out = {key: dict(cell) for key, cell in base.items()}
    for key, cell in extra.items():
        clash = set(cell) & set(out.get(key, {}))
        if clash:
            raise _fail(f"{key}: {sorted(clash)} appear twice")
        out.setdefault(key, {}).update(cell)
    return out


def check_complete(cells: Cells, keys: list[str], needed: list[str], label: str) -> None:
    for key in keys:
        missing = [name for name in needed if name not in cells.get(key, {})]
        if missing:
            raise _fail(f"{label} {key} lacks {missing[:4]}")


# ---------------------------------------------------------------- tests

def scores(keys: list[str], cells: Cells, arm: str, metric: str, draws: tuple[str, ...] = DRAWS) -> list[float]:
    return [ad.item_score(cells[key], arm, metric, draws) for key in keys]


def change(keys: list[str], cells: Cells, metric: str, right: str = "OMPF",
           right_draws: tuple[str, ...] = DRAWS) -> list[float]:
    """Per item, OMPS (draws 1-2) minus `right`."""
    return [a - b for a, b in zip(scores(keys, cells, "OMPS", metric), scores(keys, cells, right, metric, right_draws),
                                  strict=True)]


def blocks(keys: list[str], cells: dict[str, Cells], metric: str) -> dict[str, dict[str, Any]]:
    q, m = change(keys, cells["qwen"], metric), change(keys, cells["mimo"], metric)
    out = {}
    for name, model in (("P1", "qwen"), ("P2", "mimo")):
        a, b = scores(keys, cells[model], "OMPS", metric), scores(keys, cells[model], "OMPF", metric)
        out[name] = {"n": len(keys), "draws": list(DRAWS), "model": model, "OMPS": ad._pct(statistics.fmean(a)),  # noqa: SLF001
                     "OMPF": ad._pct(statistics.fmean(b)), "OMPS_versus_OMPF": arl.difference_block(a, b)}  # noqa: SLF001
    out["P3"] = {"n": len(keys), "draws": list(DRAWS), "mimo_change_points": ad._pct(statistics.fmean(m)),  # noqa: SLF001
                 "qwen_change_points": ad._pct(statistics.fmean(q)),  # noqa: SLF001
                 "mimo_change_versus_qwen_change": arl.difference_block(m, q)}
    return out


SPEC = {"P1": ["OMPS", "OMPF"], "P2": ["OMPS", "OMPF"], "P3": ["mimo_change", "qwen_change"]}


def p3_reading(block: dict[str, Any], rule: dict[str, Any], margin: float, alpha: float) -> str:
    low, high = block["mimo_change_versus_qwen_change"]["ci95_points"]
    if rule["mean_points"] < -margin and rule["p_holm"] < alpha:
        return "omp's default prompt carries part of the interaction"
    if (margin > 0 and -margin <= low and high <= margin) or (margin == 0 and low <= 0 <= high):
        return "omp's default prompt carries none of the interaction detectable here"
    return "not determined"


# ---------------------------------------------------------------- beside

def remaining_interaction(keys: list[str], cells: dict[str, Cells], metric: str, part: str) -> dict[str, Any]:
    def gap(model: str, left: str) -> list[float]:
        return [a - b for a, b in zip(scores(keys, cells[model], left, metric), scores(keys, cells[model], "DSHF", metric),
                                      strict=True)]
    original = [m - q for m, q in zip(gap("mimo", "OMPF"), gap("qwen", "OMPF"), strict=True)]
    remaining = [m - q for m, q in zip(gap("mimo", "OMPS"), gap("qwen", "OMPS"), strict=True)]
    first = ad._pct(statistics.fmean(original))  # noqa: SLF001
    if abs(first - ORIGINAL_INTERACTION[part]) > 0.006:
        raise _fail(f"part {part}: the original interaction {first} is not MC-116's {ORIGINAL_INTERACTION[part]}")
    left = ad._pct(statistics.fmean(remaining))  # noqa: SLF001
    return {"n": len(keys), "original_points": first, "remaining_points": left,
            "remaining": arl.difference_block(remaining, [0.0] * len(remaining)),
            "share_removed_pct": round(100 * (first - left) / first, 1) if first else None}


def flow_indicators(rows: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    """The two registered mechanism indicators: the share of read windows the model chose, and the share of answers
    given straight after a grep; with the answer-source split."""
    summaries, sources = [], Counter()
    for row in rows:
        flow = hf.attempt_flow(run_dir / str(row.get("attempt_dir") or ""), "omp" if row["arm"] != "DSHF" else "dsh")
        summaries.append(hf.summary(flow))
        sources[ahf.answer_source(flow)] += 1
    reads = sum(s["reads"] for s in summaries)
    return {"attempts": len(rows),
            "read_window_model_pct": round(100 * sum(s["reads_model_window"] for s in summaries) / reads, 1) if reads else None,
            "answer_after_grep_pct": round(100 * sources["grep"] / len(rows), 1) if rows else None,
            "answer_source_pct": {k: round(100 * v / len(rows), 1) for k, v in sources.most_common()},
            "attempts_with_compaction_pct": round(100 * sum(bool(s["compactions"]) for s in summaries) / len(rows), 1)
            if rows else None}


def attempt_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(name: str) -> float | None:
        values = [float(r[name]) for r in rows if isinstance(r.get(name), (int, float))]
        return round(statistics.fmean(values), 1) if values else None
    return {"attempts": len(rows), "outcomes": dict(Counter(str(r.get("outcome")) for r in rows)),
            "mean_requests": mean("requests"), "mean_total_tokens": mean("total_tokens"),
            "mean_reasoning_tokens": mean("reasoning_tokens"), "stalls": sum(int(r.get("stalls") or 0) for r in rows)}


# ---------------------------------------------------------------- the report

def build_report(omps_rows: dict[str, list[dict[str, Any]]], run_dirs: dict[str, Path], root: Path = lp.ROOT,
                 protocol: dict[str, Any] | None = None, manifest: dict[str, Any] | None = None,
                 with_flows: bool = True) -> dict[str, Any]:
    protocol = protocol or lp.load_protocol()
    manifest = manifest or lp.load_frozen_manifest()
    comparators, comparator_dirs = comparator_cells(protocol, manifest, root)
    cells = {model: merge(comparators[model], alv2.load_cells(omps_rows[model], manifest)) for model in lp.MODELS}
    parts = {part: list(keys) for part, keys in manifest["parts"].items()}
    for model in lp.MODELS:
        draws = QWEN_ALL if model == "qwen" else DRAWS
        needed = [f"OMPS{d}" for d in DRAWS] + [f"{arm}{d}" for arm in ("OMPF", "DSHF") for d in draws]
        check_complete(cells[model], parts["M"] + parts["S"], needed, model)
    plan = protocol["analysis"]
    alpha = plan["alpha"]
    out: dict[str, Any] = {"plan_id": PLAN_ID, "card_id": CARD_ID, "manifest_sha256": manifest["manifest_sha256"],
                           "scores_sha256": {model: v1.sha256_file(run_dirs[model] / "scores.jsonl")
                                             for model in lp.MODELS if (run_dirs[model] / "scores.jsonl").is_file()},
                           "reference_sha256": {name: spec["sha256"] for name, spec in protocol["reference"].items()}}
    for part in ("M", "S"):
        keys, metric, margin = parts[part], METRIC[part], plan[f"part_{part}"]["margin_points"]
        tests = blocks(keys, cells, metric)
        spec = {name: [f"{name}_{left}", f"{name}_{right}"] for name, (left, right) in SPEC.items()}
        renamed = {name: {f"{name}_{SPEC[name][0]}_versus_{name}_{SPEC[name][1]}": next(
            v for k, v in block.items() if k.endswith("_versus_" + SPEC[name][1]))} for name, block in tests.items()}
        rules = alv2.rules(renamed, spec, alpha, margin, list(SPEC) if margin else [])
        for name, model in (("P1", "qwen"), ("P2", "mimo")):
            rule = rules[name]
            rule.update({"left": f"{model} OMPS", "right": f"{model} OMPF", "reading": f"{model}: " + (
                "OMPS is better than OMPF" if rule["left_better"] else "OMPS is worse than OMPF" if rule["left_worse"]
                else "no clear difference between OMPS and OMPF")})
        rules["P3"].update({"left": "MiMo's OMPS - OMPF", "right": "Qwen's OMPS - OMPF",
                            "reading": p3_reading(tests["P3"], rules["P3"], margin, alpha)})
        out[f"part_{part}"] = {"n_items": len(keys), "item_score": "mean over draws 1-2", "tests": tests,
                               "rules": rules}
    beside: dict[str, Any] = {}
    for part in ("M", "S"):
        keys, metric = parts[part], METRIC[part]
        q4 = change(keys, cells["qwen"], metric, "OMPF", QWEN_ALL)
        beside[part] = {
            "remaining_interaction": remaining_interaction(keys, cells, metric, part),
            "p1_against_qwen_ompf_draws_1_4": {"n": len(keys), "mean_points": ad._pct(statistics.fmean(q4)),  # noqa: SLF001
                                               "difference": arl.difference_block(q4, [0.0] * len(q4))},
        }
    if with_flows:
        flows: dict[str, Any] = {}
        reference = {name: alv2.load_reference(protocol, name, root) for name in ("mc113_scores", "mc114_scores",
                                                                                    "mc112_scores", "mc116_scores")}
        for model in lp.MODELS:
            flows[model] = {"OMPS": flow_indicators(omps_rows[model], run_dirs[model])}
            for arm in ("OMPF", "DSHF"):
                sources = (("mc116_scores",) if model == "mimo" else
                           ("mc113_scores", "mc114_scores") if arm == "OMPF" else ("mc112_scores", "mc114_scores"))
                rows = [(name, r) for name in sources for r in reference[name]
                        if str(r["replicate_id"]).split("-r")[0] == arm and str(r["replicate_id"]).split("-r")[1] in DRAWS
                        and (name not in ("mc112_scores", "mc113_scores") or r["dataset_id"] == ld.LEGAL_MC)
                        and (name != "mc114_scores" or r["dataset_id"] != ld.LEGAL_MC)]
                per_dir: dict[str, list[dict[str, Any]]] = {}
                for name, r in rows:
                    per_dir.setdefault(name, []).append(r)
                merged = [flow_indicators(rs, comparator_dirs[name]) for name, rs in per_dir.items()]
                n = sum(m["attempts"] for m in merged)
                flows[model][arm] = {"attempts": n, "by_source": dict(zip(per_dir, merged, strict=True))}
        beside["action_flows"] = flows
    beside["attempts"] = {model: attempt_profile(omps_rows[model]) for model in lp.MODELS}
    out["beside_not_tested"] = beside
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=lp.WORK_ROOT / "analysis" / REPORT_FILE)
    args = ap.parse_args(argv)
    protocol = lp.load_protocol()
    run_dirs = {model: lp.WORK_ROOT / "run" / lp.model_spec(protocol, model)["profile_id"] for model in lp.MODELS}
    rows = {}
    for model, run_dir in run_dirs.items():
        path = run_dir / "scores.jsonl"
        if not path.is_file():
            raise _fail(f"{model}: {path} is missing; the analysis runs once, after both runs are final")
        rows[model] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = build_report(rows, run_dirs, protocol=protocol)
    registered = json.loads(lp.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    if args.out.is_file():
        raise _fail(f"{args.out} exists; the registered analysis runs once")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for part in ("part_M", "part_S"):
        for name in SPEC:
            rule = report[part]["rules"][name]
            print(f"{part} {name}: {rule['mean_points']:+.2f} p_holm={rule['p_holm']:.4f} -> {rule['reading']}")
    print(f"report -> {args.out} sha256 {v1.sha256_file(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
