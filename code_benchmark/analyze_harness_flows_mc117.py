"""Action flows of six cells: Qwen3.5-9B and MiMo-V2.6-Flash x DSHF, OMPF and OMPS (MC-112 to MC-117). Exploratory.

NOT pre-registered. It extends analyze_harness_flows (Phase 1b, four cells; registered by SHA-256 with MC-117 and left
unchanged) with MC-117's OMPS cells: omp 18.0.0 with dsh's system prompt, both models, draws 1-2. The per-cell profile
and the flow vocabulary are analyze_harness_flows' and harness_flow's; the step at which two arms first diverge on the
same item and draw is computed for DSHF against OMPF and for OMPF against OMPS. Reads frozen outputs only and calls no
model.

    .venv/bin/python -m code_benchmark.analyze_harness_flows_mc117 [--markdown]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_harness_flows as ahf
    from code_benchmark import analyze_legal_agent_interaction as ai
    from code_benchmark import diagnostic_legal_agent_omp_prompt as lp
    from code_benchmark import harness_flow as hf
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_harness_flows as ahf  # type: ignore[no-redef]
    import analyze_legal_agent_interaction as ai  # type: ignore[no-redef]
    import diagnostic_legal_agent_omp_prompt as lp  # type: ignore[no-redef]
    import harness_flow as hf  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

OUT = lp.WORK_ROOT / "flows" / "flow_report.json"
REGISTERED_REPORT = lp.WORK_ROOT / "analysis" / "legal_agent_omp_prompt_report.json"
ARMS = ("DSHF", "OMPF", "OMPS")
CELLS = [(model, arm) for model in ai.MODELS for arm in ARMS]
PAIRS = [("DSHF", "OMPF"), ("OMPF", "OMPS")]


def omps_attempts() -> list[dict[str, Any]]:
    """MC-117's OMPS attempts (draws 1-2), read from the score files whose SHA-256 the registered report recorded."""
    report = json.loads(REGISTERED_REPORT.read_text(encoding="utf-8"))
    protocol = lp.load_protocol()
    out = []
    for model in lp.MODELS:
        run_dir = lp.WORK_ROOT / "run" / lp.model_spec(protocol, model)["profile_id"]
        path = run_dir / "scores.jsonl"
        if v1.sha256_file(path) != report["scores_sha256"][model]:
            raise SystemExit(f"Error: {path} differs from the SHA-256 in MC-117's registered report")
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            part = "S" if row.get("part") == "S" else "M"
            out.append({"part": part, "key": f"{row['dataset_id']}:{row['item_id']}", "arm": "OMPS",
                        "draw": str(row["replicate_id"]).split("-r")[1], "model": model, "run_dir": run_dir,
                        "row": row, "score": float(row.get("correct" if part == "M" else "token_f1") or 0.0)})
    return out


def add_flows(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for a in attempts:
        directory = a["run_dir"] / str(a["row"].get("attempt_dir") or "")
        flow = hf.attempt_flow(directory, "dsh" if a["arm"] == "DSHF" else "omp")
        a["flow"] = flow
        a["flow_summary"] = hf.summary(flow)
        a["answer_source"] = ahf.answer_source(flow)
    return attempts


def divergence(rows: list[dict[str, Any]], model: str, left: str, right: str) -> dict[str, Any]:
    """Same item and draw: the first step where the right arm's action string departs from the left arm's."""
    by: dict[tuple[str, str], dict[str, list[str]]] = {}
    for a in rows:
        if a["model"] == model:
            by.setdefault((a["key"], a["draw"]), {})[a["arm"]] = a["flow"].tokens
    pairs, positions, same = Counter(), [], 0
    for arms in by.values():
        lt, rt = arms.get(left), arms.get(right)
        if lt is None or rt is None:
            continue
        i = next((k for k in range(max(len(lt), len(rt))) if k >= len(lt) or k >= len(rt) or lt[k] != rt[k]), None)
        if i is None:
            same += 1
            continue
        positions.append(i)
        pairs[(lt[i] if i < len(lt) else "-", rt[i] if i < len(rt) else "-")] += 1
    total = len(positions) + same
    return {"left": left, "right": right, "pairs": total,
            "identical_pct": ahf._pct(same / total) if total else None,  # noqa: SLF001
            "first_divergence_step_median": ahf._median(positions),  # noqa: SLF001
            "at_divergence": [{left: lv, right: rv, "share_pct": ahf._pct(n / total)}  # noqa: SLF001
                              for (lv, rv), n in pairs.most_common(8)]}


def build_report(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {"analysis": "harness-flows-six-cells", "preregistered": False,
                              "cards": ["MC-112", "MC-113", "MC-114", "MC-116", "MC-117"], "draws": list(ai.DRAWS),
                              "groups": {}}
    for name, keep in ahf.GROUPS.items():
        rows = [a for a in attempts if keep(a)]
        report["groups"][name] = {
            "cells": {f"{m}_{arm}": ahf.cell_profile([a for a in rows if a["model"] == m and a["arm"] == arm])
                      for m, arm in CELLS},
            "divergence": {f"{m}_{left}_vs_{right}": divergence(rows, m, left, right)
                           for m in ai.MODELS for left, right in PAIRS},
        }
    return report


def markdown(report: dict[str, Any]) -> str:
    """The per-cell table of analyze_harness_flows, then the divergence lines for both arm pairs."""
    lines = []
    for name, g in report["groups"].items():
        four = {"groups": {name: {"cells": g["cells"], "divergence": {}}}}
        lines.append(ahf.markdown(four))
        for key, d in g["divergence"].items():
            left, right = d["left"], d["right"]
            lines.append(f"- {key}: identical {d['identical_pct']}%, first divergence at step "
                         f"{d['first_divergence_step_median']} (median); at that step: " + "; ".join(
                             f"{left} {p[left]} / {right} {p[right]} {p['share_pct']}%" for p in d["at_divergence"][:6]))
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exploratory: action flows of six cells (two models x three arms).")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    attempts = ai.featurize(ai.qwen_attempts() + ai.mimo_attempts())
    ai.check_alignment(attempts)
    report = build_report(add_flows(attempts + omps_attempts()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.out} sha256 {v1.sha256_file(args.out)}")
    if args.markdown:
        print(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
