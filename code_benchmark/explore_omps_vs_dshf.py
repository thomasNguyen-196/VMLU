"""Exploratory: does omp with dsh's system prompt (OMPS, MC-117) match dsh (DSHF)? Not pre-registered.

MC-117's registered tests compare OMPS with OMPF. This compares OMPS with DSHF, and OMPF with DSHF for reference, per
model and part, on the same items (item mean over draws 1-2; 95% percentile bootstrap over items, 2,000 resamples,
seed 7), under the registered scorer and under content readings: strict multiple choice (the answer is only the gold
letter, as the prompt asks) and gold-token recall on ViBidLQA. Reads frozen outputs only and calls no model.

    .venv/bin/python -m code_benchmark.explore_omps_vs_dshf
"""
from __future__ import annotations

import json
import random
import statistics
from typing import Any

try:
    from code_benchmark import analyze_legal_agent_interaction as ali
    from code_benchmark import explore_legal_agent_omp_prompt as e
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_legal_agent_interaction as ali  # type: ignore[no-redef]
    import explore_legal_agent_omp_prompt as e  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

OUT = e.OUT.parent / "omps_vs_dshf.json"
READINGS = {"M": ("registered", "strict"), "S": ("registered", "recall")}


def _ci(values: list[float]) -> list[float]:
    rng = random.Random(e.SEED)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(e.RESAMPLES))
    return [round(100 * means[int(0.025 * e.RESAMPLES)], 2), round(100 * means[int(0.975 * e.RESAMPLES) - 1], 2)]


def cells(attempts: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], dict[str, list[float]]]:
    out: dict[tuple[str, str, str, str], dict[str, list[float]]] = {}
    for a in attempts:
        raw, gold = str(a["row"].get("raw_response") or ""), str(a["row"].get("gold_answer") or "")
        c = out.setdefault((a["model"], a["arm"], a["part"], a["key"]), {"registered": [], "strict": [], "recall": []})
        c["registered"].append(a["score"])
        if a["part"] == "M":
            c["strict"].append(float(e.lone_letter(raw) == gold))
        else:
            c["recall"].append(float(a["row"].get("token_recall") or 0.0))
    return out


def build() -> dict[str, Any]:
    c = cells(e.omps_attempts() + ali.qwen_attempts() + ali.mimo_attempts())
    report: dict[str, Any] = {"analysis": "omps-vs-dshf", "preregistered": False,
                              "after_registered_report": e.REPORT_SHA256, "draws": ["1", "2"], "contrasts": {}}
    for part, readings in READINGS.items():
        keys = sorted({k for (_, _, p, k) in c if p == part})
        for model in ("qwen", "mimo"):
            for left in ("OMPF", "OMPS"):
                for reading in readings:
                    diffs = [statistics.fmean(c[(model, left, part, k)][reading])
                             - statistics.fmean(c[(model, "DSHF", part, k)][reading]) for k in keys]
                    report["contrasts"][f"{part}_{model}_{left}_minus_DSHF_{reading}"] = {
                        "items": len(keys), "mean_points": round(100 * statistics.fmean(diffs), 2), "ci95_points": _ci(diffs)}
    return report


OUT_DRIFT = e.OUT.parent / "omps_vs_dshf_drift_compaction.json"
MC115_SCORES = e.ROOT / "all_res" / "diagnostic_legal_agent_draws" / "run" / "qwen3-5-9b-65k-legal-agent-draws" / "scores.jsonl"


def drift_and_compaction() -> dict[str, Any]:
    """Qwen, multiple choice, registered scorer. (a) DSHF's own drift between draws 1-2 and draws 3-4 (thesis (3.15)),
    and OMPS against DSHF draws 1-2, draws 3-4 and all four; (b) the gap to DSHF tied to OMPS attempts answered after an
    omp compaction, on the same item and draw (thesis (3.17))."""
    try:
        from code_benchmark import analyze_harness_flows_mc117 as flows
    except ImportError:  # executed from code_benchmark/
        import analyze_harness_flows_mc117 as flows  # type: ignore[no-redef]
    late: dict[str, list[float]] = {}
    for line in MC115_SCORES.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if str(row["replicate_id"]).startswith("DSHF-") and row.get("part") == "M":
            late.setdefault(f"{row['dataset_id']}:{row['item_id']}", []).append(float(row.get("correct") or 0.0))
    early: dict[str, list[float]] = {}
    dshf: dict[tuple[str, str], float] = {}
    for a in ali.qwen_attempts():
        if a["arm"] == "DSHF" and a["part"] == "M":
            early.setdefault(a["key"], []).append(a["score"])
            dshf[(a["key"], a["draw"])] = a["score"]
    omps = [a for a in flows.omps_attempts() if a["model"] == "qwen" and a["part"] == "M"]
    by_item: dict[str, list[float]] = {}
    for a in omps:
        by_item.setdefault(a["key"], []).append(a["score"])
    keys = sorted(set(by_item) & set(early) & set(late))

    def block(diffs: list[float]) -> dict[str, Any]:
        return {"items": len(diffs), "mean_points": round(100 * statistics.fmean(diffs), 2), "ci95_points": _ci(diffs)}

    m = statistics.fmean
    out: dict[str, Any] = {
        "dshf_drift_draws34_minus_draws12": block([m(late[k]) - m(early[k]) for k in keys]),
        "omps_minus_dshf_draws12": block([m(by_item[k]) - m(early[k]) for k in keys]),
        "omps_minus_dshf_draws34": block([m(by_item[k]) - m(late[k]) for k in keys]),
        "omps_minus_dshf_all4": block([m(by_item[k]) - m(early[k] + late[k]) for k in keys]),
    }
    compacted = [a for a in flows.add_flows(omps) if a["flow_summary"]["answered_after_handoff"]]
    rest_keys = {(a["key"], a["draw"]) for a in compacted}
    rest = [a for a in omps if (a["key"], a["draw"]) not in rest_keys]
    out["compaction"] = {
        "attempts_total": len(omps), "attempts_answered_after_compaction": len(compacted),
        "omps_score_compacted": round(100 * m(a["score"] for a in compacted), 2),
        "dshf_same_item_draw_compacted": round(100 * m(dshf[(a["key"], a["draw"])] for a in compacted), 2),
        "omps_score_rest": round(100 * m(a["score"] for a in rest), 2),
        "dshf_same_item_draw_rest": round(100 * m(dshf[(a["key"], a["draw"])] for a in rest), 2),
        "L_C_points": round(100 * sum(dshf[(a["key"], a["draw"])] - a["score"] for a in compacted) / len(omps), 2),
    }
    return out


def main() -> int:
    report = build()
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, v in report["contrasts"].items():
        print(f"{name:40} {v['mean_points']:+7.2f} {v['ci95_points']}")
    print(f"wrote {OUT} sha256 {v1.sha256_file(OUT)}")
    extra = drift_and_compaction()
    OUT_DRIFT.write_text(json.dumps(extra, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(extra, ensure_ascii=False))
    print(f"wrote {OUT_DRIFT} sha256 {v1.sha256_file(OUT_DRIFT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
