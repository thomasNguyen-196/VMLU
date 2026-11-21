"""Action flows of the legal agent's two harnesses for two models (MC-112 to MC-116): Phase 1b, exploratory.

NOT pre-registered. It describes, per model and harness, what the agent did around the model calls, using
harness_flow's timelines (the harness's event stream joined with the proxy's records):
  * the model's actions: tool calls, greps, reads, and who chose each read window;
  * what the harness showed back: result sizes, empty greps, truncation, paging, elision;
  * what the harness did on its own: compaction (with the summary's language), notices, hand-off requests,
    re-sends, cancelled and refused requests, and the end reason;
  * where the answer came from: the last tool result before it (a grep or a read), and whether a compaction
    hand-off had replaced the context;
  * on the same item and draw, the first step at which OMPF's flow departs from DSHF's.
Cells are analyze_legal_agent_interaction's: Qwen3.5-9B (MC-112/113/114) and MiMo-V2.6-Flash (MC-116), draws 1-2.
Reads frozen outputs only and calls no model.

Run from the repo root:  .venv/bin/python -m code_benchmark.analyze_harness_flows [--markdown]
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_legal_agent_interaction as ai
    from code_benchmark import harness_flow as hf
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_legal_agent_interaction as ai  # type: ignore[no-redef]
    import harness_flow as hf  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

OUT = ai.ROOT / "all_res" / "diagnostic_legal_agent_mimo" / "flows" / "flow_report.json"
CELLS = [(model, arm) for model in ai.MODELS for arm in ai.ARMS]
GROUPS = {"M": lambda a: a["part"] == "M", "S": lambda a: a["part"] == "S"}


def _pct(value: float) -> float:
    return round(100.0 * value, 1)


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def add_flows(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for a in attempts:
        directory = a["run_dir"] / str(a["row"].get("attempt_dir") or "")
        flow = hf.attempt_flow(directory, "omp" if a["arm"] == "OMPF" else "dsh")
        a["flow"] = flow
        a["flow_summary"] = hf.summary(flow)
        a["answer_source"] = answer_source(flow)
    return attempts


def answer_source(flow: hf.Flow) -> str:
    """Where the answer came from: the last tool result before it (grep, read, glob), none, or no answer."""
    tokens = flow.tokens
    if "A" not in tokens:
        return "no_answer"
    before = [t for t in tokens[:tokens.index("A")] if t != "C"]
    if not before:
        return "no_tool"
    return {"G": "grep", "R": "read", "F": "glob"}.get(before[-1][0], "other")


def collapse(tokens: list[str]) -> str:
    """A sequence with runs folded: G+ G+ G+ R A -> G+x3 R A."""
    out: list[str] = []
    for t in tokens:
        if out and out[-1].split("x")[0] == t:
            base, _, n = out[-1].partition("x")
            out[-1] = f"{base}x{int(n or 1) + 1}"
        else:
            out.append(t)
    return " ".join(out)


def cell_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    s = [a["flow_summary"] for a in rows]
    flows = [a["flow"] for a in rows]
    results = [st for f in flows for st in f.steps if st["kind"] == "result"]
    grep_chars = [st["chars"] for st in results if st["tool"] == "grep" and not st["error"]]
    read_chars = [st["chars"] for st in results if st["tool"] == "read" and not st["error"]]
    reads = sum(x["reads"] for x in s)
    greps = sum(x["greps"] for x in s)
    sources = Counter(a["answer_source"] for a in rows)
    by_source = {src: {"share_pct": _pct(n / len(rows)),
                       "score": _mean([100 * a["score"] for a in rows if a["answer_source"] == src])}
                 for src, n in sources.most_common()}
    compacted = [a for a in rows if a["flow_summary"]["compactions"]]
    after = [a for a in rows if a["flow_summary"]["answered_after_handoff"]]
    langs = Counter(lang for a in compacted for lang in a["flow_summary"]["compaction_summary_lang"])
    sequences = Counter(collapse(a["flow"].tokens) for a in rows)
    api = Counter()
    for x in s:
        api.update(x["api_by_kind"])
    return {
        "attempts": len(rows), "score": _mean([100 * a["score"] for a in rows]),
        "model_actions": {
            "tool_calls": _mean([x["tool_calls"] for x in s]), "greps": _mean([x["greps"] for x in s]),
            "reads": _mean([x["reads"] for x in s]),
            "read_window_model_pct": _pct(sum(x["reads_model_window"] for x in s) / reads) if reads else None,
            "read_window_harness_pct": _pct(sum(x["reads_harness_window"] for x in s) / reads) if reads else None,
            "think_chars": _mean([x["think_chars"] for x in s]),
        },
        "shown_back": {
            "empty_grep_pct": _pct(sum(x["empty_greps"] for x in s) / greps) if greps else None,
            "grep_result_chars_median": _median(grep_chars), "read_result_chars_median": _median(read_chars),
            "reads_elided_pct": _pct(sum(x["reads_elided"] for x in s) / reads) if reads else None,
            "truncated_results_per_attempt": _mean([x["truncated_results"] for x in s]),
            "result_chars_median": _median([x["result_chars"] for x in s]),
        },
        "harness_actions": {
            "attempts_with_compaction_pct": _pct(len(compacted) / len(rows)),
            "compaction_summary_lang": dict(langs),
            "answered_after_handoff_pct": _pct(len(after) / len(rows)),
            "score_answered_after_handoff": _mean([100 * a["score"] for a in after]),
            "attempts_with_notice_pct": _pct(sum(bool(x["notices"]) for x in s) / len(rows)),
            "api_calls_per_attempt": {k: round(v / len(rows), 3) for k, v in sorted(api.items())},
            "end": {k: v for k, v in Counter(x["end"] for x in s).most_common()},
        },
        "answer_source": by_source,
        "top_sequences": [{"sequence": seq, "share_pct": _pct(n / len(rows)),
                           "score": _mean([100 * a["score"] for a in rows if collapse(a["flow"].tokens) == seq])}
                          for seq, n in sequences.most_common(8)],
    }


def divergence(rows: list[dict[str, Any]], model: str) -> dict[str, Any]:
    """Same item and draw: the first step where OMPF's action string departs from DSHF's."""
    by: dict[tuple[str, str], dict[str, list[str]]] = {}
    for a in rows:
        if a["model"] == model:
            by.setdefault((a["key"], a["draw"]), {})[a["arm"]] = a["flow"].tokens
    pairs, positions, same = Counter(), [], 0
    for arms in by.values():
        d, o = arms.get("DSHF"), arms.get("OMPF")
        if d is None or o is None:
            continue
        i = next((k for k in range(max(len(d), len(o))) if k >= len(d) or k >= len(o) or d[k] != o[k]), None)
        if i is None:
            same += 1
            continue
        positions.append(i)
        pairs[(d[i] if i < len(d) else "-", o[i] if i < len(o) else "-")] += 1
    total = len(positions) + same
    return {"pairs": total, "identical_pct": _pct(same / total) if total else None,
            "first_divergence_step_median": _median(positions),
            "at_divergence_DSHF_vs_OMPF": [{"DSHF": d, "OMPF": o, "share_pct": _pct(n / total)}
                                           for (d, o), n in pairs.most_common(8)]}


def build_report(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {"analysis": "harness-flows", "preregistered": False,
                              "cards": ["MC-112", "MC-113", "MC-114", "MC-116"], "draws": list(ai.DRAWS), "groups": {}}
    for name, keep in GROUPS.items():
        rows = [a for a in attempts if keep(a)]
        report["groups"][name] = {
            "cells": {f"{m}_{arm}": cell_profile([a for a in rows if a["model"] == m and a["arm"] == arm])
                      for m, arm in CELLS},
            "divergence": {m: divergence(rows, m) for m in ai.MODELS},
        }
    return report


def markdown(report: dict[str, Any]) -> str:
    lines = []
    labels = [("Score", lambda c: c["score"]),
              ("Tool calls / attempt", lambda c: c["model_actions"]["tool_calls"]),
              ("Greps / attempt", lambda c: c["model_actions"]["greps"]),
              ("Reads / attempt", lambda c: c["model_actions"]["reads"]),
              ("Read window chosen by model (%)", lambda c: c["model_actions"]["read_window_model_pct"]),
              ("Read window cut by harness (%)", lambda c: c["model_actions"]["read_window_harness_pct"]),
              ("Thinking chars / attempt", lambda c: c["model_actions"]["think_chars"]),
              ("Empty greps (%)", lambda c: c["shown_back"]["empty_grep_pct"]),
              ("Grep result chars (median)", lambda c: c["shown_back"]["grep_result_chars_median"]),
              ("Read result chars (median)", lambda c: c["shown_back"]["read_result_chars_median"]),
              ("Reads with middle elided (%)", lambda c: c["shown_back"]["reads_elided_pct"]),
              ("Truncated results / attempt", lambda c: c["shown_back"]["truncated_results_per_attempt"]),
              ("Attempts with compaction (%)", lambda c: c["harness_actions"]["attempts_with_compaction_pct"]),
              ("Answered after a hand-off (%)", lambda c: c["harness_actions"]["answered_after_handoff_pct"]),
              ("Score when answered after hand-off", lambda c: c["harness_actions"]["score_answered_after_handoff"]),
              ("Compaction summary language", lambda c: c["harness_actions"]["compaction_summary_lang"] or "-"),
              ("Attempts with a notice (%)", lambda c: c["harness_actions"]["attempts_with_notice_pct"]),
              ("API calls by kind / attempt", lambda c: c["harness_actions"]["api_calls_per_attempt"]),
              ("End reasons", lambda c: c["harness_actions"]["end"])]
    for name, g in report["groups"].items():
        cells = g["cells"]
        lines += [f"### {name}", "", "| | " + " | ".join(cells) + " |", "|---|" + "---:|" * len(cells)]
        for label, get in labels:
            lines.append(f"| {label} | " + " | ".join(str(get(c)) for c in cells.values()) + " |")
        lines.append("")
        for cell, c in cells.items():
            src = "; ".join(f"{k} {v['share_pct']}% (score {v['score']})" for k, v in c["answer_source"].items())
            lines.append(f"- {cell} answer from: {src}")
        for cell, c in cells.items():
            lines.append(f"- {cell} top sequences: " + "; ".join(
                f"`{t['sequence']}` {t['share_pct']}% ({t['score']})" for t in c["top_sequences"][:5]))
        for m, d in g["divergence"].items():
            lines.append(f"- {m}: OMPF vs DSHF on the same item and draw: identical {d['identical_pct']}%, first "
                         f"divergence at step {d['first_divergence_step_median']} (median); at that step: " + "; ".join(
                             f"DSHF {p['DSHF']} / OMPF {p['OMPF']} {p['share_pct']}%" for p in d["at_divergence_DSHF_vs_OMPF"][:6]))
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exploratory: the two harnesses' action flows for two models.")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    attempts = add_flows(ai.featurize(ai.qwen_attempts() + ai.mimo_attempts()))
    ai.check_alignment(attempts)
    report = build_report(attempts)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.out} sha256 {v1.sha256_file(args.out)}")
    if args.markdown:
        print(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
