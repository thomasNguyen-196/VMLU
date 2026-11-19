"""MC-116's registered analysis (plan diagnostic-legal-agent-mimo), run once after every attempt is final.

The item score is the mean over MiMo's draws 1-2 (MC-116's scores). Tests, Holm over two within each part:
  Part M (246 items, correctness):  M1 OMPF-DSHF, M2 DSHF-B, margin 2.24 points
  Part S (400 items, token-F1 v3):  S1 OMPF-DSHF, S2 DSHF-C, no margin
Each: mean per-item difference, 95% percentile bootstrap (2,000, seed 7), two-sided paired sign-flip p (20,000, seed 7),
as MC-112 to MC-115.

Beside, not tested: Qwen's same comparisons on the same items (draws 1-2 from MC-111 to MC-114; draws 1-4 with
MC-115), each score file read by its registered SHA-256; the model difference in the harness gap (per item, MiMo's
OMPF-DSHF minus Qwen's on draws 1-2); MiMo minus Qwen per arm on draws 1-2; Part M by source; and per arm the outcomes,
requests, tool calls and tokens of MiMo's attempts.

From the repo root:
  .venv/bin/python -m code_benchmark.analyze_legal_agent_mimo --run-dir all_res/diagnostic_legal_agent_mimo/run/<profile>
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_legal_agent_draws as ad
    from code_benchmark import analyze_legal_agent_v2 as alv2
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_legal_agent_draws as ld
    from code_benchmark import diagnostic_legal_agent_mimo as lm
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_legal_agent_draws as ad  # type: ignore[no-redef]
    import analyze_legal_agent_v2 as alv2  # type: ignore[no-redef]
    import analyze_router_labels as arl  # type: ignore[no-redef]
    import diagnostic_legal_agent_draws as ld  # type: ignore[no-redef]
    import diagnostic_legal_agent_mimo as lm  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

PLAN_ID = "diagnostic-legal-agent-mimo"
CARD_ID = "MC-116"
REPORT_FILE = "legal_agent_mimo_report.json"
DRAWS = ("1", "2")
QWEN_ALL = ("1", "2", "3", "4")
METRIC = ad.METRIC
Cells = ad.Cells
# Qwen's draws: which arms each earlier score file holds, and whether it covers the Legal MC items or the others
QWEN_SOURCES = {"mc111_scores": "legal", "mc112_scores": "legal", "mc113_scores": "legal", "mc114_scores": "other",
                "mc115_scores": "all"}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


# ---------------------------------------------------------------- cells

def qwen_cells(protocol: dict[str, Any], manifest: dict[str, Any], root: Path = lm.ROOT) -> Cells:
    """Qwen's draws 1-4 of DSHF, OMPF, B and C on MC-116's items: draws 1-2 from MC-111 (B), MC-112 (DSHF) and MC-113
    (OMPF) on the Legal MC items and from MC-114 on the others; draws 3-4 from MC-115 on all."""
    if set(protocol["reference"]) != set(QWEN_SOURCES):
        raise _fail(f"the reference score files must be {sorted(QWEN_SOURCES)}")
    datasets = set(manifest["dataset_counts"])
    cells: Cells = {}
    for name, scope in QWEN_SOURCES.items():
        rows = alv2.load_reference(protocol, name, root)
        targets = ([ld.LEGAL_MC] if scope == "legal" else sorted(datasets - {ld.LEGAL_MC}) if scope == "other"
                   else sorted(datasets))
        for dataset_id in targets:
            alv2.add_rows(cells, rows, tuple(protocol["reference"][name]["arms"]), dataset_id)
    return cells


def check_complete(cells: Cells, parts: dict[str, list[str]], draws: tuple[str, ...], label: str) -> None:
    for part, keys in parts.items():
        for key in keys:
            missing = [f"{arm}{draw}" for arm in lm.PART_ARMS[part] for draw in draws
                       if f"{arm}{draw}" not in cells.get(key, {})]
            if missing:
                raise _fail(f"{label} {key} lacks {missing[:4]}")


# ---------------------------------------------------------------- beside: the model comparison

def item_scores(keys: list[str], cells: Cells, arm: str, metric: str, draws: tuple[str, ...]) -> list[float]:
    return [ad.item_score(cells[key], arm, metric, draws) for key in keys]


def gap_difference(keys: list[str], mimo: Cells, qwen: Cells, left: str, right: str, metric: str) -> dict[str, Any]:
    """Per item, MiMo's left-right gap minus Qwen's on draws 1-2: positive when MiMo's gap is larger."""
    mimo_gap = [a - b for a, b in zip(item_scores(keys, mimo, left, metric, DRAWS),
                                      item_scores(keys, mimo, right, metric, DRAWS), strict=True)]
    qwen_gap = [a - b for a, b in zip(item_scores(keys, qwen, left, metric, DRAWS),
                                      item_scores(keys, qwen, right, metric, DRAWS), strict=True)]
    return {"n": len(keys), "draws": list(DRAWS), "mimo_gap_points": ad._pct(statistics.fmean(mimo_gap)),  # noqa: SLF001
            "qwen_gap_points": ad._pct(statistics.fmean(qwen_gap)),  # noqa: SLF001
            "mimo_minus_qwen": arl.difference_block(mimo_gap, qwen_gap)}


def model_difference(keys: list[str], mimo: Cells, qwen: Cells, arm: str, metric: str) -> dict[str, Any]:
    a, b = item_scores(keys, mimo, arm, metric, DRAWS), item_scores(keys, qwen, arm, metric, DRAWS)
    return {"n": len(keys), "draws": list(DRAWS), "mimo": ad._pct(statistics.fmean(a)),  # noqa: SLF001
            "qwen": ad._pct(statistics.fmean(b)), "mimo_versus_qwen": arl.difference_block(a, b)}  # noqa: SLF001


def attempt_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per arm: outcomes, and the mean requests, tool calls and tokens per attempt (reported usage)."""
    out: dict[str, Any] = {}
    for arm in sorted({str(row.get("arm")) for row in rows}):
        mine = [row for row in rows if row.get("arm") == arm]

        def mean(key: str, rows: list[dict[str, Any]] = mine) -> float | None:
            values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
            return round(statistics.fmean(values), 1) if values else None

        calls = [sum((row.get("tool_calls") or {}).values()) for row in mine if isinstance(row.get("tool_calls"), dict)]
        out[arm] = {"attempts": len(mine), "outcomes": dict(sorted(Counter(str(r.get("outcome")) for r in mine).items())),
                    "mean_requests": mean("requests"), "mean_tool_calls": round(statistics.fmean(calls), 2) if calls else None,
                    "mean_total_tokens": mean("total_tokens"), "mean_reasoning_tokens": mean("reasoning_tokens"),
                    "mean_completion_tokens": mean("completion_tokens"),
                    "max_completion_tokens_used": max((int(r["max_completion_tokens_used"]) for r in mine
                                                       if isinstance(r.get("max_completion_tokens_used"), int)), default=None)}
    return out


# ---------------------------------------------------------------- the report

def build_report(run_dir: Path, root: Path = lm.ROOT, protocol: dict[str, Any] | None = None,
                 manifest: dict[str, Any] | None = None, qwen: Cells | None = None) -> dict[str, Any]:
    protocol = protocol or lm.load_protocol()
    manifest = manifest or lm.load_frozen_manifest()
    scores_path = run_dir / "scores.jsonl"
    rows = [json.loads(line) for line in scores_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    mimo = alv2.load_cells(rows, manifest)
    parts = {part: list(keys) for part, keys in manifest["parts"].items()}
    check_complete(mimo, parts, DRAWS, "MiMo")
    qwen = qwen_cells(protocol, manifest, root) if qwen is None else qwen
    check_complete(qwen, parts, QWEN_ALL, "Qwen")
    plan = protocol["analysis"]
    alpha = plan["alpha"]
    out: dict[str, Any] = {"plan_id": PLAN_ID, "card_id": CARD_ID, "manifest_sha256": manifest["manifest_sha256"],
                           "scores_sha256": v1.sha256_file(scores_path),
                           "reference_sha256": {name: spec["sha256"] for name, spec in protocol["reference"].items()}}
    for part in ("M", "S"):
        spec, keys, metric = plan[f"part_{part}"], parts[part], METRIC[part]
        blocks = ad.questions(keys, mimo, spec["questions"], metric, DRAWS)
        out[f"part_{part}"] = {
            "n_items": len(keys), "item_score": "mean over MiMo's draws 1-2", "questions": blocks,
            "rules": alv2.rules(blocks, spec["questions"], alpha, spec["margin_points"], spec["margin_on"]),
        }
    beside: dict[str, Any] = {}
    for part in ("M", "S"):
        spec, keys, metric = plan[f"part_{part}"], parts[part], METRIC[part]
        beside[part] = {
            "qwen_draws_1_2": ad.questions(keys, qwen, spec["questions"], metric, DRAWS),
            "qwen_draws_1_4": ad.questions(keys, qwen, spec["questions"], metric, QWEN_ALL),
            "harness_gap_mimo_minus_qwen": gap_difference(keys, mimo, qwen, "OMPF", "DSHF", metric),
            "arm_mimo_minus_qwen": {arm: model_difference(keys, mimo, qwen, arm, metric)
                                    for arm in lm.PART_ARMS[part]},
        }
    m_keys = parts["M"]
    beside["M"]["by_source"] = {
        source: ad.questions([k for k in m_keys if k.startswith(f"{ld.LEGAL_MC}:") == (source == "legal_mc")],
                             mimo, plan["part_M"]["questions"], METRIC["M"], DRAWS)
        for source in ("legal_mc", "vmlu_law")}
    beside["attempts"] = attempt_profile(rows)
    out["beside_not_tested"] = beside
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    registered = json.loads(lm.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
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
