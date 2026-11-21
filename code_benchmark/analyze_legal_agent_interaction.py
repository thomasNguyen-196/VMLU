"""Model x harness interaction in the legal agent (MC-112 to MC-116): at which step of the agent loop does it arise?

NOT pre-registered; exploratory. The plan was written and hashed before the MiMo stage numbers were read:
docs/research/legal-agent-interaction-plan-2026-11-20.md (its SHA-256 is checked below). The module reads frozen
run outputs only, checks every score file against its recorded SHA-256, and calls no model.

Cells, all on the same 646 items and folders, draws 1-2:
  Qwen3.5-9B DSHF and OMPF: MC-112/113 (134 Legal MC items), MC-114 (112 VMLU law items, 400 ViBidLQA items);
  MiMo-V2.6-Flash DSHF and OMPF: MC-116.
The interaction of an item is (MiMo's OMPF - DSHF) - (Qwen's OMPF - DSHF), each the mean over the two draws.
Stages (search -> find -> open -> read the governing article) and the two-fold split are
analyze_legal_agent_mechanism's; here each model's OMPF - DSHF gap is split at DSHF's read premium, and the
interaction's parts are MiMo's parts minus Qwen's, with one item resample shared by both models.

Run from the repo root:  .venv/bin/python -m code_benchmark.analyze_legal_agent_interaction [--markdown]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import unicodedata
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_legal_agent as ala
    from code_benchmark import analyze_legal_agent_mechanism as mech
    from code_benchmark import analyze_legal_agent_mimo as amimo
    from code_benchmark import analyze_legal_agent_v2 as alv2
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_agent_v2 as l2
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_legal_agent as ala  # type: ignore[no-redef]
    import analyze_legal_agent_mechanism as mech  # type: ignore[no-redef]
    import analyze_legal_agent_mimo as amimo  # type: ignore[no-redef]
    import analyze_legal_agent_v2 as alv2  # type: ignore[no-redef]
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = l2.ROOT
MC116_RUN = ROOT / "all_res" / "diagnostic_legal_agent_mimo" / "run" / "mimo-v2-6-flash-legal-agent"
OUT = ROOT / "all_res" / "diagnostic_legal_agent_mimo" / "interaction" / "interaction_report.json"
PLAN = ROOT / "docs" / "research" / "legal-agent-interaction-plan-2026-11-20.md"
PLAN_SHA256 = "641ef1aaa4de03db5d7a64ddf4fb5b8150b38cce9573212b203ca122cf91014b"
ARMS = ("DSHF", "OMPF")
MODELS = ("qwen", "mimo")
DRAWS = mech.DRAWS
TERMINAL = ("answer_cap", "request_cap", "harness_end", "upstream_4xx")
SEED, RESAMPLES = mech.SEED, mech.RESAMPLES
PARTS = ("gap", "rate_part", "within_part")
# the registered report's "beside" values (MC-116, b6f8a7cb...): the interaction over all items must reproduce them
REGISTERED_INTERACTION = {"M": 14.63, "S": 11.64}
GROUPS = {"M": lambda a: a["part"] == "M", "M_legal_mc": lambda a: a["source"] == "legal_mc",
          "M_vmlu_law": lambda a: a["source"] == "vmlu_law", "S": lambda a: a["part"] == "S"}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100.0 * value, 2)


def _ci(values: list[float]) -> list[float]:
    values = sorted(values)
    return [round(values[int(0.025 * len(values))], 2), round(values[int(0.975 * len(values)) - 1], 2)]


# ---------------------------------------------------------------- the attempts

def unclean_text(text: str) -> bool:
    """Vietnamese typed with decomposed (NFD) or stray combining marks: looks right, but differs byte for byte."""
    nfc = unicodedata.normalize("NFC", text)
    return text != nfc or any(unicodedata.combining(ch) for ch in nfc)


def qwen_attempts(root: Path = ROOT) -> list[dict[str, Any]]:
    """MC-112/113/114's DSHF and OMPF attempts (draws 1-2), as the mechanism module loads them."""
    return [{**a, "model": "qwen"} for a in mech.load_attempts(root) if a["arm"] in ARMS]


def mimo_attempts() -> list[dict[str, Any]]:
    """MC-116's DSHF and OMPF attempts, with MiMo's own B (MC items) or C (ViBidLQA) as the item's yardstick."""
    report = json.loads((MC116_RUN / "analysis" / amimo.REPORT_FILE).read_text(encoding="utf-8"))
    rows = mech._load_scores(MC116_RUN / "scores.jsonl", report["scores_sha256"])  # noqa: SLF001
    cells: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        arm, _, draw = str(row["replicate_id"]).partition("-r")
        cells.setdefault(f"{row['dataset_id']}:{row['item_id']}", {})[f"{arm}{draw}"] = row
    manifest = l2.load_frozen_manifest()
    support = manifest["support"]
    legal = sorted(key for key in cells if key.split(":", 1)[0] == alv2.LEGAL_MC)
    sources = [("M", "legal_mc", legal, la.load_provisions()),
               ("M", "vmlu_law", manifest["parts"]["M"], l2.load_provisions()),
               ("S", "bidlqa", manifest["parts"]["S"], l2.load_provisions())]
    out = []
    for part, source, keys, provisions in sources:
        yardstick = "B" if part == "M" else "C"
        for key in keys:
            cell, item = cells[key], key.split(":", 1)[1]
            located = provisions[item]["provisions"] if support.get(key) != "no_provision" else []
            baseline = statistics.fmean(float(cell[f"{yardstick}{d}"].get(mech.METRIC[part]) or 0.0) for d in DRAWS)
            letters = [str(cell[f"B{d}"].get("prediction") or "") for d in DRAWS] if part == "M" else []
            for arm in ARMS:
                for draw in DRAWS:
                    row = cell[f"{arm}{draw}"]
                    out.append({"part": part, "source": source, "key": key, "arm": arm, "draw": draw,
                                "score": float(row.get(mech.METRIC[part]) or 0.0), "baseline": baseline,
                                "baseline_letters": letters, "run_dir": MC116_RUN, "row": row,
                                "provisions": located, "model": "mimo"})
    return out


def extra_features(records: list[dict[str, Any]], harness: str) -> dict[str, Any]:
    """Grep outcomes the mechanism module does not count: empty results and patterns with broken Unicode."""
    observations = (ot.omp_observations if harness == "omp" else la.model_observations)(records)
    _, _, raw = ot._calls_and_results(records)  # noqa: SLF001
    greps = [o for o in observations if o["tool"] == "grep"]
    return {"greps": len(greps),
            "zero_hit_greps": sum(raw.get(o["call_id"], "").strip().startswith("No matches found") for o in greps),
            "unclean_greps": sum(unclean_text(str(o["arguments"].get("pattern") or "")) for o in greps)}


def featurize(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cache: dict[str, list[str]] = {}
    for a in attempts:
        records = ala.load_attempt_records(a["run_dir"], a["row"])
        harness = mech.HARNESS[a["arm"]]
        a["features"] = {**mech.attempt_features(records, harness, a["provisions"], cache),
                         **extra_features(records, harness)}
        a["terminal"] = str(a["row"].get("outcome")) in TERMINAL
    return attempts


def check_alignment(attempts: list[dict[str, Any]]) -> None:
    """Both models must hold the same items and arms, two draws each."""
    seen = {model: sorted((a["key"], a["arm"], a["draw"]) for a in attempts if a["model"] == model)
            for model in MODELS}
    if seen["qwen"] != seen["mimo"]:
        raise _fail("the Qwen and MiMo attempts do not cover the same items, arms and draws")


# ---------------------------------------------------------------- the interaction

def item_gaps(rows: list[dict[str, Any]], model: str, drop_terminal: bool = False) -> dict[str, float]:
    """Item key -> OMPF - DSHF of one model, each arm the mean over its (kept) draws."""
    by: dict[str, dict[str, list[float]]] = {}
    for a in rows:
        if a["model"] == model and not (drop_terminal and a["terminal"]):
            by.setdefault(a["key"], {}).setdefault(a["arm"], []).append(a["score"])
    return {key: statistics.fmean(v["OMPF"]) - statistics.fmean(v["DSHF"])
            for key, v in by.items() if "OMPF" in v and "DSHF" in v}


def interaction(rows: list[dict[str, Any]], drop_terminal: bool = False) -> dict[str, Any]:
    mimo, qwen = item_gaps(rows, "mimo", drop_terminal), item_gaps(rows, "qwen", drop_terminal)
    keys = sorted(set(mimo) & set(qwen))
    diffs = [mimo[k] - qwen[k] for k in keys]
    rng = random.Random(SEED)
    means = [statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(RESAMPLES)]
    return {"items": len(keys), "mimo_gap_points": _pct(statistics.fmean(mimo[k] for k in keys)),
            "qwen_gap_points": _pct(statistics.fmean(qwen[k] for k in keys)),
            "interaction_points": _pct(statistics.fmean(diffs)), "ci95_points": _ci([100 * m for m in means])}


def _sums(rows: list[dict[str, Any]], adjusted: bool) -> dict[tuple[str, str], list[float]]:
    """(model, arm) -> [read n, read sum, other n, other sum] of the score (or lift over the yardstick)."""
    out: dict[tuple[str, str], list[float]] = {}
    for a in rows:
        s = out.setdefault((a["model"], a["arm"]), [0.0, 0.0, 0.0, 0.0])
        value = a["score"] - a["baseline"] if adjusted else a["score"]
        i = 0 if a["features"]["stage"] == "read" else 2
        s[i] += 1
        s[i + 1] += value
    return out


def oaxaca_from_sums(s: dict[tuple[str, str], list[float]], model: str) -> dict[str, float]:
    """mech.oaxaca(rows, "OMPF", "DSHF") from summed counts: left - right at the right arm's read premium."""
    def parts(arm: str) -> tuple[float, float, float]:
        n1, t1, n0, t0 = s.get((model, arm), [0.0, 0.0, 0.0, 0.0])
        return n1 / (n1 + n0), t1 / n1 if n1 else 0.0, t0 / n0 if n0 else 0.0
    rl, l1, l0 = parts("OMPF")
    rr, r1, r0 = parts("DSHF")
    rate, within = (rl - rr) * (r1 - r0), rl * (l1 - r1) + (1 - rl) * (l0 - r0)
    return {"gap": 100 * (rate + within), "rate_part": 100 * rate, "within_part": 100 * within,
            "read_rate_ompf_pct": 100 * rl, "read_rate_dshf_pct": 100 * rr}


def decomposition(rows: list[dict[str, Any]], adjusted: bool = False) -> dict[str, Any]:
    """Each model's OMPF - DSHF split on items with a located provision; the interaction's parts with a shared
    item bootstrap."""
    rows = [a for a in rows if a["features"]["stage"]]
    by_item: dict[str, list[dict[str, Any]]] = {}
    for a in rows:
        by_item.setdefault(a["key"], []).append(a)
    item_sums = {key: _sums(group, adjusted) for key, group in by_item.items()}

    def point(keys: list[str]) -> dict[str, dict[str, float]]:
        total: dict[tuple[str, str], list[float]] = {}
        for key in keys:
            for cell, values in item_sums[key].items():
                acc = total.setdefault(cell, [0.0, 0.0, 0.0, 0.0])
                for i in range(4):
                    acc[i] += values[i]
        out = {model: oaxaca_from_sums(total, model) for model in MODELS}
        out["interaction"] = {name: out["mimo"][name] - out["qwen"][name] for name in PARTS}
        return out

    keys = sorted(by_item)
    estimate = point(keys)
    rng = random.Random(SEED)
    resampled = {name: [] for name in PARTS}
    for _ in range(RESAMPLES):
        value = point(rng.choices(keys, k=len(keys)))["interaction"]
        for name in PARTS:
            resampled[name].append(value[name])
    result: dict[str, Any] = {"items": len(keys)}
    for model in MODELS:
        result[model] = {name: round(value, 2) for name, value in estimate[model].items()}
    inter = estimate["interaction"]
    summary: dict[str, Any] = {name: round(inter[name], 2) for name in PARTS}
    summary.update({f"{name}_ci95": _ci(resampled[name]) for name in PARTS})
    for name in ("rate_part", "within_part"):
        summary[f"{name}_share_pct"] = round(100 * inter[name] / inter["gap"], 1) if inter["gap"] else None
    result["interaction"] = summary
    return result


def readings(decomp: dict[str, Any], whole: dict[str, Any], kept: dict[str, Any]) -> list[str]:
    """The plan's reading rules, applied as written."""
    out = []
    inter = decomp["interaction"]
    for name, label in (("rate_part", "reaching and reading the governing article"),
                        ("within_part", "the answer given the same read state")):
        low, high = inter[f"{name}_ci95"]
        share = inter[f"{name}_share_pct"]
        if (low > 0 or high < 0) and share is not None and share >= 50:
            out.append(f"the interaction lies in {label} ({share}% of it)")
    total = whole["interaction_points"]
    if total and (total - kept["interaction_points"]) / total >= 0.5:
        out.append("part of the interaction comes from attempts that ended without an answer "
                   f"({total} -> {kept['interaction_points']} without them)")
    return out or ["not determined"]


# ---------------------------------------------------------------- cell profiles

def profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    f = [a["features"] for a in rows]
    greps = sum(x["greps"] for x in f)
    tokens = [int(a["row"].get("total_tokens") or 0) for a in rows]
    reasoning = [int(a["row"].get("reasoning_tokens") or 0) for a in rows]
    located = [a for a in rows if a["features"]["stage"]]
    read = [a["score"] for a in located if a["features"]["stage"] == "read"]
    unread = [a["score"] for a in located if a["features"]["stage"] != "read"]
    return {
        "attempts": len(rows), "score_points": _pct(statistics.fmean(a["score"] for a in rows)),
        "located_attempts": len(located),
        "read_rate_pct": _pct(len(read) / len(located)) if located else None,
        "score_read_points": _pct(statistics.fmean(read)) if read else None,
        "score_not_read_points": _pct(statistics.fmean(unread)) if unread else None,
        "terminal_pct": {o: _pct(statistics.fmean(str(a["row"].get("outcome")) == o for a in rows)) for o in TERMINAL},
        "greps_per_attempt": round(greps / len(rows), 3),
        "zero_hit_share_of_greps_pct": _pct(sum(x["zero_hit_greps"] for x in f) / greps) if greps else None,
        "unclean_share_of_greps_pct": _pct(sum(x["unclean_greps"] for x in f) / greps) if greps else None,
        "attempts_with_unclean_grep_pct": _pct(statistics.fmean(x["unclean_greps"] > 0 for x in f)),
        "omp_paged_reads_per_attempt": round(statistics.fmean(x["notes"].get("omp_read_paged", 0) for x in f), 3),
        "tokens_mean": round(statistics.fmean(tokens)), "reasoning_tokens_mean": round(statistics.fmean(reasoning)),
        "behaviour": mech.behaviour(rows), "stages": mech.stages(rows),
    }


def build_report(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {"analysis": "legal-agent-interaction", "preregistered": False,
                              "plan": {"path": str(PLAN.relative_to(ROOT)), "sha256": PLAN_SHA256},
                              "cards": ["MC-112", "MC-113", "MC-114", "MC-116"], "draws": list(DRAWS), "groups": {}}
    for name, keep in GROUPS.items():
        rows = [a for a in attempts if keep(a)]
        whole, kept = interaction(rows), interaction(rows, drop_terminal=True)
        if name in REGISTERED_INTERACTION and abs(whole["interaction_points"] - REGISTERED_INTERACTION[name]) > 0.006:
            raise _fail(f"{name}: interaction {whole['interaction_points']} differs from the registered "
                        f"{REGISTERED_INTERACTION[name]}")
        decomp = decomposition(rows)
        report["groups"][name] = {
            "items": len({a["key"] for a in rows}),
            "items_with_provision": len({a["key"] for a in rows if a["provisions"]}),
            "cells": {f"{model}_{arm}": profile([a for a in rows if a["model"] == model and a["arm"] == arm])
                      for model in MODELS for arm in ARMS},
            "interaction_all_items": whole,
            "interaction_without_terminal": kept,
            "decomposition": decomp,
            "decomposition_difficulty_adjusted": decomposition(rows, adjusted=True),
            "paired_read": {model: mech.paired_read([a for a in rows if a["model"] == model], "OMPF", "DSHF")
                            for model in MODELS},
            "readings": readings(decomp, whole, kept),
        }
    return report


# ---------------------------------------------------------------- output

CELLS = [f"{model}_{arm}" for model in MODELS for arm in ARMS]


def _table_row(cells: dict[str, Any], label: str, get) -> str:
    return f"| {label} | " + " | ".join(str(get(cells[cell])) for cell in CELLS) + " |"


def markdown(report: dict[str, Any]) -> str:
    lines = []
    for name, g in report["groups"].items():
        c = g["cells"]
        lines += [f"### {name} ({g['items']} items, {g['items_with_provision']} with a located provision)", "",
                  "| | Qwen DSHF | Qwen OMPF | MiMo DSHF | MiMo OMPF |", "|---|---:|---:|---:|---:|"]
        def row(label: str, get, c=c, lines=lines) -> None:
            lines.append(_table_row(c, label, get))
        row("Score", lambda x: x["score_points"])
        row("Ended without an answer (%)", lambda x: round(sum(x["terminal_pct"].values()), 2))
        for stage in mech.STAGES:
            row(f"Stage {stage} (%)", lambda x, s=stage: x["stages"].get(s, {}).get("share_pct") if x["stages"].get("attempts") else "-")
        row("Read the article (% of located attempts)", lambda x: x["read_rate_pct"])
        row("Score when read", lambda x: x["score_read_points"])
        row("Score when not read", lambda x: x["score_not_read_points"])
        row("Tool calls / attempt", lambda x: x["behaviour"]["calls_mean"])
        row("Corpus reads / attempt", lambda x: x["behaviour"]["corpus_reads_mean"])
        row("omp paged reads / attempt", lambda x: x["omp_paged_reads_per_attempt"])
        row("Greps / attempt", lambda x: x["greps_per_attempt"])
        row("Empty greps (% of greps)", lambda x: x["zero_hit_share_of_greps_pct"])
        row("Broken-Unicode greps (% of greps)", lambda x: x["unclean_share_of_greps_pct"])
        row("Tokens / attempt", lambda x: x["tokens_mean"])
        row("Reasoning tokens / attempt", lambda x: x["reasoning_tokens_mean"])
        w, k, d = g["interaction_all_items"], g["interaction_without_terminal"], g["decomposition"]
        lines += ["",
                  f"- Interaction, all items: {w['interaction_points']} {w['ci95_points']} (MiMo gap "
                  f"{w['mimo_gap_points']}, Qwen gap {w['qwen_gap_points']}, {w['items']} items); without the attempts "
                  f"that ended without an answer: {k['interaction_points']} {k['ci95_points']} ({k['items']} items).",
                  f"- Split on {d['items']} items with a provision: interaction {d['interaction']['gap']} "
                  f"{d['interaction']['gap_ci95']} = read-rate part {d['interaction']['rate_part']} "
                  f"{d['interaction']['rate_part_ci95']} ({d['interaction']['rate_part_share_pct']}%) + within-state "
                  f"part {d['interaction']['within_part']} {d['interaction']['within_part_ci95']} "
                  f"({d['interaction']['within_part_share_pct']}%). Read rate OMPF/DSHF: Qwen "
                  f"{round(d['qwen']['read_rate_ompf_pct'], 1)}/{round(d['qwen']['read_rate_dshf_pct'], 1)}, MiMo "
                  f"{round(d['mimo']['read_rate_ompf_pct'], 1)}/{round(d['mimo']['read_rate_dshf_pct'], 1)}.",
                  f"- Difficulty-adjusted split: rate part {g['decomposition_difficulty_adjusted']['interaction']['rate_part']}"
                  f" {g['decomposition_difficulty_adjusted']['interaction']['rate_part_ci95']}, within-state "
                  f"{g['decomposition_difficulty_adjusted']['interaction']['within_part']} "
                  f"{g['decomposition_difficulty_adjusted']['interaction']['within_part_ci95']}.",
                  "- Both harnesses read the article, same item: " + "; ".join(
                      f"{m}: {p['items']} items, OMPF - DSHF {p['mean_diff_points']} (OMPF better {p['OMPF_better']}, "
                      f"DSHF better {p['DSHF_better']}, sign test p {p['sign_test_p']})" for m, p in g["paired_read"].items()),
                  "- Reading: " + "; ".join(g["readings"]) + ".", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exploratory: where the model x harness interaction arises.")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--markdown", action="store_true", help="also print the tables as Markdown")
    args = parser.parse_args(argv)
    if not PLAN.is_file() or v1.sha256_file(PLAN) != PLAN_SHA256:
        raise _fail(f"the analysis plan {PLAN} is missing or changed since it was hashed")
    attempts = featurize(qwen_attempts() + mimo_attempts())
    check_alignment(attempts)
    report = build_report(attempts)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} sha256 {v1.sha256_file(args.out)}")
    if args.markdown:
        print(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
