"""Why the omp arm (OMPF) scores below the dsh arm (DSHF) in MC-112/113/114: an exploratory, descriptive analysis.

NOT pre-registered. The registered results are the MC-113 and MC-114 reports; this module only explains them. It
reads the frozen run outputs (score rows and the request bodies the proxy recorded), calls no model, and checks
every score file against the hash its card recorded before using it.

Each agent attempt on an item with a located provision falls in exactly one stage of the chain
search -> find the right document -> open it -> read the governing article:

* `no_tool`: no tool call at all.
* `not_found`: no tool result or tool argument names any of the item's provision files.
* `found_not_opened`: a provision file was named (in a search result or an argument) but never read.
* `opened_not_read`: a provision file was read, but no read result showed the article's anchor line. The reason
  is taken from the shown line ranges: the anchor sat in the middle omp elided, past the last shown line, or
  before the first one.
* `read`: a read result showed the anchor line (MC-112's `read`).

The gap decomposition is the two-fold Oaxaca split at attempt level: gap = (read-rate difference x the reference
arm's read premium) + (score differences within read / not read). Reading is not randomised, so the split is an
association, not a causal effect. CIs resample items (2,000 resamples, seed 7, as the registered analyses do).

Run from the repo root:  .venv/bin/python -m code_benchmark.analyze_legal_agent_mechanism [--markdown]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_legal_agent as ala
    from code_benchmark import analyze_legal_agent_v2 as alv2
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_agent_v2 as l2
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_legal_agent as ala  # type: ignore[no-redef]
    import analyze_legal_agent_v2 as alv2  # type: ignore[no-redef]
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = l2.ROOT
MC114_RUN = ROOT / "all_res" / "diagnostic_legal_agent_v2" / "run" / "qwen3-5-9b-65k-legal-agent-v2"
CORPUS = ROOT / "all_res" / "diagnostic_legal_agent_v2" / "corpus_v2" / "docs"  # corpus_v1's files byte for byte
OUT = ROOT / "all_res" / "diagnostic_legal_agent_v2" / "mechanism" / "mechanism_report.json"  # not the registered dir
ARMS = ("DSH", "DSHF", "OMPF")
HARNESS = {"DSH": "dsh", "DSHF": "dsh", "OMPF": "omp"}
DRAWS = ("1", "2")
METRIC = {"M": "correct", "S": "token_f1"}
STAGES = ("no_tool", "not_found", "found_not_opened", "opened_not_read", "read")
MISS_REASONS = ("elided_middle", "after_shown", "before_shown", "unknown")
DEPTHS = ((0, 0, "0"), (1, 1, "1"), (2, 3, "2-3"), (4, 7, "4-7"), (8, 10**9, "8+"))
SEED, RESAMPLES = 7, 2000

_ARTICLE_QUERY = re.compile(r"điều\s*\d")
_OMP_SHOWN = re.compile(r"^\[Showing lines (\d+)-(\d+)(?: and (\d+)-(\d+))? of ([\d,]+)", re.MULTILINE)
_DSH_LINE = re.compile(r"^(\d+): ?", re.MULTILINE)
NOTES = {  # descriptive counts of what a harness cut from a tool result
    "omp_read_elided_middle": ("read", re.compile(r"^\[Showing lines \d+-\d+ and \d+-\d+ of", re.MULTILINE)),
    "omp_read_paged": ("read", re.compile(r"^\[Showing lines \d+-\d+ of", re.MULTILINE)),
    "omp_grep_lines_truncated": ("grep", re.compile(r"^\[Some lines truncated to \d+ chars\]", re.MULTILINE)),
    "omp_grep_size_limit": ("grep", re.compile(r"KB limit\)", re.MULTILINE)),
    "omp_glob_limit": ("glob", re.compile(r"results limit reached", re.MULTILINE)),
    "dsh_grep_spilled": ("grep", re.compile(r"^\(Omitted \d+ bytes\. Full formatted result stored at", re.MULTILINE)),
}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100.0 * value, 2)


# ---------------------------------------------------------------- one attempt

def shown_ranges(harness: str, content: str) -> list[tuple[int, int]] | None:
    """1-based inclusive line ranges a `read` result showed; None when the result does not say."""
    if harness == "omp":
        match = _OMP_SHOWN.search(content)
        if not match:
            return [(1, 10**9)]  # no note: the whole file was shown
        a, b, c, d = match.groups()[:4]
        return [(int(a), int(b))] + ([(int(c), int(d))] if c and d else [])
    numbers = [int(n) for n in _DSH_LINE.findall(content.split("<content>\n", 1)[-1])]
    return [(min(numbers), max(numbers))] if numbers else None


def miss_reason(ranges: list[tuple[int, int]] | None, anchors: list[int]) -> str:
    """Why a read of the right file did not show the anchor line (numbers are the anchor's line numbers)."""
    if not ranges or not anchors:
        return "unknown"
    if len(ranges) == 2 and any(ranges[0][1] < n < ranges[1][0] for n in anchors):
        return "elided_middle"
    last, first = max(end for _, end in ranges), min(start for start, _ in ranges)
    if all(n > last for n in anchors):
        return "after_shown"
    if all(n < first for n in anchors):
        return "before_shown"
    return "unknown"


def _file_lines(file: str, cache: dict[str, list[str]]) -> list[str]:
    if file not in cache:
        path = CORPUS / file
        cache[file] = path.read_text(encoding="utf-8").split("\n") if path.is_file() else []
    return cache[file]


def anchor_numbers(file: str, anchor: str, cache: dict[str, list[str]]) -> list[int]:
    return [i + 1 for i, line in enumerate(_file_lines(file, cache)) if line == anchor]


_NEXT_UNIT = re.compile(r"^(?:Điều \d+|Chương [IVXLC\d]+|CHƯƠNG|Mục \d+|MỤC \d+)")
ARTICLE_MAX_LINES = 80


def article_span(lines: list[str], start: int) -> tuple[int, int]:
    """1-based inclusive span of the provision that starts at line `start`: up to the line before the next article,
    chapter or section heading, at most ARTICLE_MAX_LINES lines."""
    end = min(len(lines), start + ARTICLE_MAX_LINES - 1)
    for n in range(start + 1, end + 1):
        if _NEXT_UNIT.match(lines[n - 1]):
            return start, n - 1
    return start, end


def coverage(span: tuple[int, int], ranges: list[tuple[int, int]]) -> float:
    """Share of the span's lines that some shown range covers."""
    start, end = span
    shown = sum(1 for n in range(start, end + 1) if any(a <= n <= b for a, b in ranges))
    return shown / (end - start + 1)


def final_request_text(records: list[dict[str, Any]]) -> str:
    """Every message text (and tool-call argument) of the request whose response was the final answer: the last
    request answered with text and no tool call (omp may log a cancelled hand-off request after it)."""
    finals = [r for r in records if isinstance(r.get("response"), dict) and not r["response"].get("tool_calls")
              and str(r["response"].get("content") or "").strip()]
    record = finals[-1] if finals else (records[-1] if records else {})
    try:
        body = json.loads(record.get("body_received") or "")
    except json.JSONDecodeError:
        return ""
    parts = []
    for message in body.get("messages") or [] if isinstance(body, dict) else []:
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        parts.append(str(content or ""))
        parts.extend(str((call.get("function") or {}).get("arguments") or "") for call in message.get("tool_calls") or [])
    return "\n".join(parts)


def version_stem(file: str) -> str:
    """A corpus file name without its years: the same law's other versions share the stem."""
    return re.sub(r"-?(?:19|20)\d\d", "", file)


def attempt_features(records: list[dict[str, Any]], harness: str, provisions: list[dict[str, Any]],
                     corpus_cache: dict[str, list[str]]) -> dict[str, Any]:
    """Behaviour and the search -> read stage of one attempt, from the request bodies the proxy recorded."""
    observations = (ot.omp_observations if harness == "omp" else la.model_observations)(records)
    _, _, raw = ot._calls_and_results(records)  # call id -> the tool result text as the model received it
    usage = [r["response"]["usage"] for r in records
             if isinstance(r.get("response"), dict) and isinstance(r["response"].get("usage"), dict)]
    notes = Counter()
    for o in observations:
        content = raw.get(o["call_id"], "")
        for name, (tool, pattern) in NOTES.items():
            notes[name] += o["tool"] == tool and bool(pattern.search(content))
    patterns = [unicodedata.normalize("NFC", str(o["arguments"].get("pattern") or "")).casefold()
                for o in observations if o["tool"] == "grep"]
    out: dict[str, Any] = {
        "calls": len(observations),
        "search_calls": sum(o["tool"] in ("grep", "glob") for o in observations),
        "read_calls": sum(o["tool"] == "read" for o in observations),
        "corpus_reads": sum(o["tool"] == "read" and bool(o["read_file"]) for o in observations),
        "error_calls": sum(o["status"] == "error" for o in observations),
        "read_errors": sum(o["tool"] == "read" and o["status"] == "error" for o in observations),
        "article_query": any(_ARTICLE_QUERY.search(p) for p in patterns),
        "result_chars": sum(o["chars"] for o in observations),
        "requests": len(records),
        "first_prompt_tokens": usage[0].get("prompt_tokens") if usage else None,
        "max_prompt_tokens": max((u.get("prompt_tokens") or 0 for u in usage), default=None),
        "notes": dict(notes),
        "stage": None, "miss_reason": None,
    }
    if not provisions:
        return out
    hits = la.provision_hits(observations, provisions)
    files = {p["file"] for p in provisions}
    named = any(f in json.dumps(o["arguments"], ensure_ascii=False) for o in observations for f in files) or any(
        f in raw.get(o["call_id"], "") for o in observations if not o["read_file"] for f in files)
    if any(h["read"] for h in hits):
        out["stage"] = "read"
        # how much of the governing provision's text (not only its heading line) the reads showed
        best = 0.0
        for p in provisions:
            ranges = [r for o in observations
                      if o["tool"] == "read" and o["read_file"] == p["file"] and o["status"] == "completed"
                      for r in shown_ranges(harness, raw.get(o["call_id"], "")) or []]
            lines = _file_lines(p["file"], corpus_cache)
            for start in anchor_numbers(p["file"], p["anchor_line"], corpus_cache):
                best = max(best, coverage(article_span(lines, start), ranges))
        out["article_coverage"] = round(best, 4)
        # was the article still in front of the model when it answered, and how far back
        final = final_request_text(records)
        positions = [final.rfind(p["anchor_line"]) for p in provisions if p["anchor_line"] in final]
        first_read = next(i for i, o in enumerate(observations) if o["tool"] == "read" and o["read_file"] in files
                          and any(p["anchor_line"] in o["lines"].get(o["read_file"], []) for p in provisions))
        shown = {f for o in observations for f in o["lines"]}
        out["final_context"] = {
            "anchor_present": bool(positions), "chars_total": len(final),
            "chars_after_anchor": len(final) - max(positions) if positions else None,
            "calls_after_read": len(observations) - first_read - 1,
            "other_version_shown": any(version_stem(f) == version_stem(t) and f != t for f in shown for t in files),
        }
    elif any(h["opened"] for h in hits):
        out["stage"] = "opened_not_read"
        reasons = []
        for o in observations:
            if o["tool"] == "read" and o["read_file"] in files and o["status"] == "completed":
                anchors = [n for p in provisions if p["file"] == o["read_file"]
                           for n in anchor_numbers(p["file"], p["anchor_line"], corpus_cache)]
                reasons.append(miss_reason(shown_ranges(harness, raw.get(o["call_id"], "")), anchors))
        out["miss_reason"] = next((r for r in MISS_REASONS if r in reasons), "unknown")
    elif named:
        out["stage"] = "found_not_opened"
    else:
        out["stage"] = "no_tool" if not observations else "not_found"
    return out


# ---------------------------------------------------------------- the attempts

def _load_scores(path: Path, sha256: str) -> list[dict[str, Any]]:
    if not path.is_file() or v1.sha256_file(path) != sha256:
        raise _fail(f"{path} is missing or differs from its recorded SHA-256")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def baselines(cells: dict[str, dict[str, dict[str, Any]]], manifest: dict[str, Any]
              ) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Item key -> the no-tool baseline's mean score over its two draws, the item's difficulty yardstick: B for
    Legal MC (MC-111's draws, the B that MC-112/113 compared with), B for the VMLU law items, C (closed book)
    for ViBidLQA. Also item key -> B's predicted letters (MC only)."""
    out: dict[str, float] = {}
    letters: dict[str, list[str]] = {}
    legal: dict[str, list[float]] = {}
    for row in la.load_reference(la.load_protocol()):
        if str(row["replicate_id"]).startswith("B-r") and row["dataset_id"] == alv2.LEGAL_MC:
            key = f"{row['dataset_id']}:{row['item_id']}"
            legal.setdefault(key, []).append(float(row.get("correct") or 0.0))
            letters.setdefault(key, []).append(str(row.get("prediction") or ""))
    out.update({key: statistics.fmean(values) for key, values in legal.items()})
    for part, arm in (("M", "B"), ("S", "C")):
        for key in manifest["parts"][part]:
            out[key] = statistics.fmean(float(cells[key][f"{arm}{d}"].get(METRIC[part]) or 0.0) for d in DRAWS)
            if part == "M":
                letters[key] = [str(cells[key][f"B{d}"].get("prediction") or "") for d in DRAWS]
    return out, letters


def load_attempts(root: Path = ROOT) -> list[dict[str, Any]]:
    """Every DSH/DSHF/OMPF attempt of MC-114's parts M and S plus MC-112/113's 134 Legal MC items."""
    protocol = l2.load_protocol()
    manifest = l2.load_frozen_manifest()
    report = json.loads((MC114_RUN / "analysis" / alv2.REPORT_FILE).read_text(encoding="utf-8"))
    cells = alv2.load_cells(_load_scores(MC114_RUN / "scores.jsonl", report["scores_sha256"]), manifest)
    legal = alv2.legal_mc_cells(protocol, root)
    baseline, b_letters = baselines(cells, manifest)
    if any(key not in baseline for key in legal):
        raise _fail("MC-111's B is missing for a Legal MC item")
    run_of = {"DSH": root / protocol["reference"]["mc112_scores"]["path"],
              "DSHF": root / protocol["reference"]["mc112_scores"]["path"],
              "OMPF": root / protocol["reference"]["mc113_scores"]["path"]}
    p_v1, p_v2 = la.load_provisions(), l2.load_provisions()
    support = manifest["support"]
    sources = [("M", "legal_mc", sorted(legal), legal, p_v1, {arm: path.parent for arm, path in run_of.items()}),
               ("M", "vmlu_law", manifest["parts"]["M"], cells, p_v2, dict.fromkeys(ARMS, MC114_RUN)),
               ("S", "bidlqa", manifest["parts"]["S"], cells, p_v2, dict.fromkeys(ARMS, MC114_RUN))]
    out = []
    for part, source, keys, table, provisions, runs in sources:
        for key in keys:
            item = key.split(":", 1)[1]
            located = provisions[item]["provisions"] if support.get(key) != "no_provision" else []
            for arm in ARMS:
                for draw in DRAWS:
                    row = table[key][f"{arm}{draw}"]
                    out.append({"part": part, "source": source, "key": key, "arm": arm, "draw": draw,
                                "score": float(row.get(METRIC[part]) or 0.0), "baseline": baseline[key],
                                "baseline_letters": b_letters.get(key, []),
                                "run_dir": runs[arm], "row": row, "provisions": located})
    return out


def featurize(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cache: dict[str, list[str]] = {}
    for a in attempts:
        records = ala.load_attempt_records(a["run_dir"], a["row"])
        a["features"] = attempt_features(records, HARNESS[a["arm"]], a["provisions"], cache)
    return attempts


# ---------------------------------------------------------------- summaries

def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def behaviour(rows: list[dict[str, Any]]) -> dict[str, Any]:
    f = [a["features"] for a in rows]
    notes = Counter()
    for x in f:
        notes.update(x["notes"])
    depth = {}
    for low, high, label in DEPTHS:
        inside = [a for a in rows if low <= a["features"]["calls"] <= high]
        depth[label] = {"share_pct": _pct(len(inside) / len(rows)),
                        "mean_score_points": _pct(statistics.fmean(a["score"] for a in inside)) if inside else None}
    first = [x["first_prompt_tokens"] for x in f if x["first_prompt_tokens"]]
    peak = [x["max_prompt_tokens"] for x in f if x["max_prompt_tokens"]]
    return {
        "attempts": len(rows), "mean_score_points": _pct(statistics.fmean(a["score"] for a in rows)),
        "calls_mean": _mean([x["calls"] for x in f]), "search_calls_mean": _mean([x["search_calls"] for x in f]),
        "read_calls_mean": _mean([x["read_calls"] for x in f]),
        "corpus_reads_mean": _mean([x["corpus_reads"] for x in f]),
        "no_corpus_read_pct": _pct(statistics.fmean(x["corpus_reads"] == 0 for x in f)),
        "read_error_share_of_reads_pct": _pct(sum(x["read_errors"] for x in f) / max(1, sum(x["read_calls"] for x in f))),
        "article_query_pct": _pct(statistics.fmean(x["article_query"] for x in f)),
        "result_chars_mean": _mean([x["result_chars"] for x in f]),
        "requests_mean": _mean([x["requests"] for x in f]),
        "first_prompt_tokens_median": statistics.median(first) if first else None,
        "max_prompt_tokens_median": statistics.median(peak) if peak else None,
        "notes_per_attempt": {k: round(v / len(rows), 3) for k, v in sorted(notes.items())},
        "depth": depth,
    }


def stages(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [a for a in rows if a["features"]["stage"]]
    if not rows:
        return {"attempts": 0}
    out: dict[str, Any] = {"attempts": len(rows)}
    for stage in STAGES:
        inside = [a for a in rows if a["features"]["stage"] == stage]
        out[stage] = {"share_pct": _pct(len(inside) / len(rows)), "mean_score_points": None,
                      "baseline_same_items_points": None, "lift_over_baseline_points": None}
        if inside:
            score = _pct(statistics.fmean(a["score"] for a in inside))
            base = _pct(statistics.fmean(a["baseline"] for a in inside))
            out[stage].update(mean_score_points=score, baseline_same_items_points=base,
                              lift_over_baseline_points=round(score - base, 2))
    found = [a for a in rows if a["features"]["stage"] in ("found_not_opened", "opened_not_read", "read")]
    opened = [a for a in found if a["features"]["stage"] != "found_not_opened"]
    out["opened_given_found_pct"] = _pct(len(opened) / len(found)) if found else None
    out["read_given_opened_pct"] = (_pct(sum(a["features"]["stage"] == "read" for a in opened) / len(opened))
                                    if opened else None)
    misses = Counter(a["features"]["miss_reason"] for a in rows if a["features"]["stage"] == "opened_not_read")
    out["opened_not_read_reasons"] = {r: misses.get(r, 0) for r in MISS_REASONS}
    read = [a for a in rows if a["features"]["stage"] == "read"]
    out["read_article_coverage"] = None
    if read:
        full = [a for a in read if a["features"]["article_coverage"] >= 0.999]
        part = [a for a in read if a["features"]["article_coverage"] < 0.999]
        out["read_article_coverage"] = {
            "mean_pct": _pct(statistics.fmean(a["features"]["article_coverage"] for a in read)),
            "whole_article_shown_pct": _pct(len(full) / len(read)),
            "score_whole_points": _pct(statistics.fmean(a["score"] for a in full)) if full else None,
            "score_partial_points": _pct(statistics.fmean(a["score"] for a in part)) if part else None,
            "lift_whole_points": _pct(statistics.fmean(a["score"] - a["baseline"] for a in full)) if full else None,
            "lift_partial_points": _pct(statistics.fmean(a["score"] - a["baseline"] for a in part)) if part else None,
        }
    return out


def _value(attempt: dict[str, Any], adjusted: bool) -> float:
    """The attempt's score, or its lift over the item's no-tool baseline (removes item difficulty)."""
    return attempt["score"] - attempt["baseline"] if adjusted else attempt["score"]


def oaxaca(rows: list[dict[str, Any]], left: str, right: str, adjusted: bool = False) -> dict[str, float]:
    """gap = left - right = rate part (at right's read premium) + within-state part; points."""
    def parts(arm: str) -> tuple[float, float, float]:
        mine = [a for a in rows if a["arm"] == arm]
        read = [_value(a, adjusted) for a in mine if a["features"]["stage"] == "read"]
        other = [_value(a, adjusted) for a in mine if a["features"]["stage"] != "read"]
        rate = len(read) / len(mine)
        return rate, statistics.fmean(read) if read else 0.0, statistics.fmean(other) if other else 0.0
    rl, l1, l0 = parts(left)
    rr, r1, r0 = parts(right)
    rate = (rl - rr) * (r1 - r0)
    within = rl * (l1 - r1) + (1 - rl) * (l0 - r0)
    return {"gap": 100 * (rate + within), "rate_part": 100 * rate, "within_part": 100 * within,
            "rate_part_at_left_premium": 100 * (rl - rr) * (l1 - l0),
            "read_rate_left_pct": 100 * rl, "read_rate_right_pct": 100 * rr}


def oaxaca_with_ci(rows: list[dict[str, Any]], left: str, right: str, adjusted: bool = False) -> dict[str, Any]:
    rows = [a for a in rows if a["features"]["stage"] and a["arm"] in (left, right)]
    point = oaxaca(rows, left, right, adjusted)
    by_item: dict[str, list[dict[str, Any]]] = {}
    for a in rows:
        by_item.setdefault(a["key"], []).append(a)
    keys = sorted(by_item)
    rng = random.Random(SEED)
    draws = {name: [] for name in ("gap", "rate_part", "within_part")}
    for _ in range(RESAMPLES):
        sample = [a for key in rng.choices(keys, k=len(keys)) for a in by_item[key]]
        value = oaxaca(sample, left, right, adjusted)
        for name in draws:
            draws[name].append(value[name])
    out: dict[str, Any] = {name: round(value, 2) for name, value in point.items()}
    for name, values in draws.items():
        values.sort()
        out[f"{name}_ci95"] = [round(values[int(0.025 * RESAMPLES)], 2), round(values[int(0.975 * RESAMPLES) - 1], 2)]
    out["rate_share_of_gap_pct"] = round(100 * point["rate_part"] / point["gap"], 1) if point["gap"] else None
    out["n_items"] = len(keys)
    return out


def build_report(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {"M": [a for a in attempts if a["part"] == "M"],
              "M_legal_mc": [a for a in attempts if a["source"] == "legal_mc"],
              "M_vmlu_law": [a for a in attempts if a["source"] == "vmlu_law"],
              "S": [a for a in attempts if a["part"] == "S"]}
    report: dict[str, Any] = {"analysis": "legal-agent-mechanism", "preregistered": False,
                              "cards": ["MC-112", "MC-113", "MC-114"], "groups": {}}
    for name, rows in groups.items():
        report["groups"][name] = {
            "items": len({a["key"] for a in rows}),
            "items_with_provision": len({a["key"] for a in rows if a["provisions"]}),
            "behaviour": {arm: behaviour([a for a in rows if a["arm"] == arm]) for arm in ARMS},
            "stages": {arm: stages([a for a in rows if a["arm"] == arm]) for arm in ARMS},
            "decomposition_DSHF_vs_OMPF": oaxaca_with_ci(rows, "DSHF", "OMPF"),
            "decomposition_DSHF_vs_OMPF_difficulty_adjusted": oaxaca_with_ci(rows, "DSHF", "OMPF", adjusted=True),
            "harm_and_rescue": {arm: harm_and_rescue([a for a in rows if a["arm"] == arm]) for arm in ARMS}
            if name.startswith("M") else None,
            "answer_format": {arm: answer_format([a for a in rows if a["arm"] == arm]) for arm in ARMS}
            if name.startswith("M") else None,
        }
        if name.startswith("M"):  # read but still wrong: forgetting, distractors, prior, letters, scorer
            report["groups"][name]["read_state"] = {arm: read_state([a for a in rows if a["arm"] == arm])
                                                    for arm in ("DSHF", "OMPF")}
            report["groups"][name]["paired_read"] = paired_read(rows, "DSHF", "OMPF")
            report["groups"][name]["letters"] = {arm: letters([a for a in rows if a["arm"] == arm]) for arm in ARMS}
            report["groups"][name]["scorer_check"] = {arm: scorer_check([a for a in rows if a["arm"] == arm])
                                                      for arm in ARMS}
    return report


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _item_ci(rows: list[dict[str, Any]], value) -> list[float]:
    """95% percentile bootstrap over items of the attempt-level mean of value(attempt), in points."""
    by_item: dict[str, list[float]] = {}
    for a in rows:
        by_item.setdefault(a["key"], []).append(value(a))
    keys, rng, means = sorted(by_item), random.Random(SEED), []
    for _ in range(RESAMPLES):
        sample = [v for key in rng.choices(keys, k=len(keys)) for v in by_item[key]]
        means.append(statistics.fmean(sample))
    means.sort()
    return [_pct(means[int(0.025 * RESAMPLES)]), _pct(means[int(0.975 * RESAMPLES) - 1])]


def read_state(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """MC attempts that read the governing article: their lift over B, whether the article was still in the final
    request, how far back, other versions of the law in view, and how the wrong answers relate to B's answers."""
    read = [a for a in rows if a["features"]["stage"] == "read"]
    if not read:
        return {"attempts": 0}
    ctx = [a["features"]["final_context"] for a in read]
    wrong = [a for a in read if a["score"] == 0.0]
    return {
        "attempts": len(read), "items": len({a["key"] for a in read}), "wrong": len(wrong),
        "lift_over_baseline_points": _pct(statistics.fmean(a["score"] - a["baseline"] for a in read)),
        "lift_ci95_items": _item_ci(read, lambda a: a["score"] - a["baseline"]),
        "anchor_in_final_request_pct": _pct(statistics.fmean(c["anchor_present"] for c in ctx)),
        "chars_after_anchor_median": _median([c["chars_after_anchor"] for c in ctx if c["chars_after_anchor"] is not None]),
        "final_request_chars_median": _median([c["chars_total"] for c in ctx]),
        "calls_after_read_median": _median([c["calls_after_read"] for c in ctx]),
        "other_version_shown_pct": _pct(statistics.fmean(c["other_version_shown"] for c in ctx)),
        "wrong_other_version_shown_pct": _pct(statistics.fmean(a["features"]["final_context"]["other_version_shown"]
                                                               for a in wrong)) if wrong else None,
        "wrong_matches_a_B_answer_pct": _pct(statistics.fmean(str(a["row"].get("prediction") or "") in
                                                              a["baseline_letters"] for a in wrong)) if wrong else None,
        "wrong_where_B_right_both_pct": _pct(statistics.fmean(a["baseline"] == 1.0 for a in wrong)) if wrong else None,
    }


def sign_test_p(wins: int, losses: int) -> float:
    """Two-sided exact sign test (ties dropped)."""
    n, k = wins + losses, min(wins, losses)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def paired_read(rows: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    """Items where both arms read the governing article in at least one draw: per item, the mean score of the
    read attempts of each arm."""
    by: dict[str, dict[str, list[float]]] = {}
    for a in rows:
        if a["features"]["stage"] == "read" and a["arm"] in (left, right):
            by.setdefault(a["key"], {}).setdefault(a["arm"], []).append(a["score"])
    diffs = [statistics.fmean(v[left]) - statistics.fmean(v[right]) for v in by.values() if left in v and right in v]
    wins, losses = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    return {"items": len(diffs), "mean_diff_points": _pct(statistics.fmean(diffs)) if diffs else None,
            f"{left}_better": wins, f"{right}_better": losses, "equal": len(diffs) - wins - losses,
            "sign_test_p": round(sign_test_p(wins, losses), 4)}


PEAK_BUCKETS = ((0, 2000, "<2k"), (2000, 10000, "2k-10k"), (10000, 25000, "10k-25k"), (25000, 10**9, "25k+"))


def letters(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """MC: the predicted letters, and how often the last option D is chosen where gold is not D, by the attempt's
    largest prompt (does the pull toward D grow with context length?)."""
    predicted = Counter(str(a["row"].get("prediction") or "-") for a in rows)
    not_d = [a for a in rows if str(a["row"].get("gold_answer")) != "D"]
    by_peak = {}
    for low, high, label in PEAK_BUCKETS:
        inside = [a for a in not_d if low <= (a["features"]["max_prompt_tokens"] or 0) < high]
        by_peak[label] = {"attempts": len(inside), "d_pct": _pct(statistics.fmean(
            str(a["row"].get("prediction")) == "D" for a in inside)) if inside else None}
    wrong = [a for a in rows if a["score"] == 0.0]
    return {"predicted_pct": {k: _pct(v / len(rows)) for k, v in sorted(predicted.items())},
            "gold_pct": {k: _pct(v / len(rows)) for k, v in sorted(Counter(
                str(a["row"].get("gold_answer")) for a in rows).items())},
            "d_where_gold_not_d_pct": _pct(statistics.fmean(str(a["row"].get("prediction")) == "D" for a in not_d))
            if not_d else None,
            "baseline_d_where_gold_not_d_pct": _pct(statistics.fmean(
                statistics.fmean(letter == "D" for letter in a["baseline_letters"]) for a in not_d
                if a["baseline_letters"])) if any(a["baseline_letters"] for a in not_d) else None,
            "d_share_of_wrong_pct": _pct(statistics.fmean(str(a["row"].get("prediction")) == "D" for a in wrong))
            if wrong else None,
            "d_where_gold_not_d_by_peak_prompt": by_peak}


_STATED = re.compile(r"đáp án(?:\s+đúng)?\s*(?:là\s*[:：]?|[:：])\s*\**\s*\(?([A-E])\b", re.IGNORECASE)
_LINE_LETTER = re.compile(r"\(?([A-E])\)?\.?")


def stated_letter(raw: str) -> str | None:
    """The letter the model itself names as its answer, read post hoc (not the registered scorer). Signals: the last
    "đáp án (đúng) là X" / "đáp án: X", a last line that is only a letter, a first line that is only a letter. Returns
    the letter when every signal present agrees, else None (no signal, or the model named two letters)."""
    text = raw.strip()
    lines = [line.strip().strip("*").strip() for line in text.split("\n") if line.strip()]
    signals = [match.upper() for match in _STATED.findall(text)[-1:]]
    for line in lines[-1:] + lines[:1]:
        match = _LINE_LETTER.fullmatch(line)
        if match:
            signals.append(match.group(1))
    return signals[0] if signals and len(set(signals)) == 1 else None


def scorer_check(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """MC: how often the registered prediction differs from the letter the model named, and the score if the named
    letter were used. Descriptive only; the registered score stands."""
    changed = gains = losses = 0
    rescored = []
    for a in rows:
        predicted, gold = str(a["row"].get("prediction") or ""), str(a["row"].get("gold_answer"))
        stated = stated_letter(str(a["row"].get("raw_response") or ""))
        if stated and stated != predicted:
            changed += 1
            gains += stated == gold
            losses += predicted == gold
        rescored.append((stated or predicted) == gold)
    return {"attempts": len(rows), "named_letter_differs": changed, "would_gain": gains, "would_lose": losses,
            "registered_points": _pct(statistics.fmean(a["score"] for a in rows)),
            "named_letter_points": _pct(statistics.fmean(rescored))}


_BARE = re.compile(r"(?:Đáp án:?\s*)?\(?[A-E]\)?\.?")


def answer_format(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """MC only. A bare final answer is just the letter; otherwise the model wrote text (often a quoted provision)
    before it. Score and lift over B per format."""
    out: dict[str, Any] = {}
    groups = {"bare": [], "with_text": []}
    for a in rows:
        bare = bool(_BARE.fullmatch(str(a["row"].get("raw_response") or "").strip()))
        groups["bare" if bare else "with_text"].append(a)
    for name, inside in groups.items():
        out[name] = {"share_pct": _pct(len(inside) / len(rows)) if rows else None,
                     "mean_score_points": _pct(statistics.fmean(a["score"] for a in inside)) if inside else None,
                     "lift_over_baseline_points": _pct(statistics.fmean(a["score"] - a["baseline"] for a in inside))
                     if inside else None}
    return out


def harm_and_rescue(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """MC only. Harm: the attempt is wrong on an item B got right in both draws; rescue: right where B failed
    both. Split by whether the governing provision was read."""
    out: dict[str, Any] = {}
    for label, base, wanted in (("harm", 1.0, 0.0), ("rescue", 0.0, 1.0)):
        inside = [a for a in rows if a["baseline"] == base]
        out[label] = {"attempts": len(inside),
                      "rate_pct": _pct(statistics.fmean(a["score"] == wanted for a in inside)) if inside else None}
        for state, test in (("read", lambda s: s == "read"), ("not_read", lambda s: s != "read")):
            part = [a for a in inside if a["features"]["stage"] and test(a["features"]["stage"])]
            out[label][state] = {"attempts": len(part), "rate_pct": _pct(statistics.fmean(
                a["score"] == wanted for a in part)) if part else None}
    return out


# ---------------------------------------------------------------- output

def markdown(report: dict[str, Any]) -> str:
    lines = []
    for name, group in report["groups"].items():
        lines += [f"### {name} ({group['items']} items, {group['items_with_provision']} with a located provision)", "",
                  "| | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
        b = group["behaviour"]
        for label, key in (("Score", "mean_score_points"), ("Tool calls / attempt", "calls_mean"),
                           ("Corpus reads / attempt", "corpus_reads_mean"), ("No corpus read (%)", "no_corpus_read_pct"),
                           ("Read errors (% of reads)", "read_error_share_of_reads_pct"),
                           ("Searched an article number (%)", "article_query_pct"),
                           ("Requests / attempt", "requests_mean"), ("First prompt tokens (median)", "first_prompt_tokens_median"),
                           ("Peak prompt tokens (median)", "max_prompt_tokens_median")):
            lines.append(f"| {label} | " + " | ".join(str(b[arm][key]) for arm in ARMS) + " |")
        s = group["stages"]
        if s["DSHF"].get("attempts"):
            for stage in STAGES:
                lines.append(f"| Stage {stage}: % (score; baseline) | " + " | ".join(
                    f"{s[arm][stage]['share_pct']} ({s[arm][stage]['mean_score_points']}; "
                    f"{s[arm][stage]['baseline_same_items_points']})" for arm in ARMS) + " |")
            for label, key in (("Opened given found (%)", "opened_given_found_pct"),
                               ("Read given opened (%)", "read_given_opened_pct")):
                lines.append(f"| {label} | " + " | ".join(str(s[arm][key]) for arm in ARMS) + " |")
            lines.append("| Read: whole article shown % (score whole / partial) | " + " | ".join(
                (lambda c: f"{c['whole_article_shown_pct']} ({c['score_whole_points']} / {c['score_partial_points']})"
                 if c else "-")(s[arm]["read_article_coverage"]) for arm in ARMS) + " |")
            lines.append("| Opened-not-read reasons | " + " | ".join(
                ", ".join(f"{k} {v}" for k, v in s[arm]["opened_not_read_reasons"].items() if v) or "-"
                for arm in ARMS) + " |")
            lines.append("")
            for label, key in (("raw", "decomposition_DSHF_vs_OMPF"),
                               ("difficulty-adjusted", "decomposition_DSHF_vs_OMPF_difficulty_adjusted")):
                d = group[key]
                lines.append(f"DSHF - OMPF on located items ({label}): gap {d['gap']} {d['gap_ci95']}; read-rate "
                             f"part {d['rate_part']} {d['rate_part_ci95']} ({d['rate_share_of_gap_pct']}% of the gap; "
                             f"{d['rate_part_at_left_premium']} at DSHF's premium); within-state part "
                             f"{d['within_part']} {d['within_part_ci95']}; read rate "
                             f"{round(d['read_rate_left_pct'], 1)} vs {round(d['read_rate_right_pct'], 1)}.")
            if group["harm_and_rescue"]:
                for arm in ARMS:
                    h = group["harm_and_rescue"][arm]
                    lines.append(f"- {arm}: harm {h['harm']['rate_pct']}% of {h['harm']['attempts']} (read "
                                 f"{h['harm']['read']['rate_pct']}, not read {h['harm']['not_read']['rate_pct']}); "
                                 f"rescue {h['rescue']['rate_pct']}% of {h['rescue']['attempts']} (read "
                                 f"{h['rescue']['read']['rate_pct']}, not read {h['rescue']['not_read']['rate_pct']})")
                for arm in ("DSHF", "OMPF"):
                    r = group["read_state"][arm]
                    lines.append(f"- {arm} read state: {r['attempts']} attempts on {r['items']} items, {r['wrong']} wrong; "
                                 f"lift {r['lift_over_baseline_points']} {r['lift_ci95_items']}; article in final request "
                                 f"{r['anchor_in_final_request_pct']}%, {r['chars_after_anchor_median']} chars after it, "
                                 f"{r['calls_after_read_median']} calls after the read; other version shown "
                                 f"{r['other_version_shown_pct']}%; wrong = a B answer {r['wrong_matches_a_B_answer_pct']}%,"
                                 f" B right both {r['wrong_where_B_right_both_pct']}%")
                p = group["paired_read"]
                lines.append(f"- both read, same item: {p['items']} items, DSHF better {p['DSHF_better']}, OMPF better "
                             f"{p['OMPF_better']}, equal {p['equal']}, mean {p['mean_diff_points']}, sign test p "
                             f"{p['sign_test_p']}")
                for arm in ARMS:
                    L, c = group["letters"][arm], group["scorer_check"][arm]
                    lines.append(f"- {arm}: D where gold is not D {L['d_where_gold_not_d_pct']}% (B "
                                 f"{L['baseline_d_where_gold_not_d_pct']}%), by peak prompt "
                                 f"{ {k: v['d_pct'] for k, v in L['d_where_gold_not_d_by_peak_prompt'].items()} }; "
                                 f"scorer check {c['registered_points']} -> {c['named_letter_points']} "
                                 f"(+{c['would_gain']}/-{c['would_lose']})")
                for arm in ARMS:
                    f = group["answer_format"][arm]
                    lines.append(f"- {arm} answer format: bare letter {f['bare']['share_pct']}% (score "
                                 f"{f['bare']['mean_score_points']}, lift {f['bare']['lift_over_baseline_points']}); "
                                 f"with text {f['with_text']['share_pct']}% (score "
                                 f"{f['with_text']['mean_score_points']}, lift "
                                 f"{f['with_text']['lift_over_baseline_points']})")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exploratory: why OMPF scores below DSHF (MC-112/113/114).")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--markdown", action="store_true", help="also print the tables as Markdown")
    args = parser.parse_args(argv)
    report = build_report(featurize(load_attempts()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} sha256 {v1.sha256_file(args.out)}")
    if args.markdown:
        print(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
