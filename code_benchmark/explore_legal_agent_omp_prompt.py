"""Exploratory follow-up to MC-117 (not registered; written after the registered report bfd544bd... was read).

Question: why does dsh's prompt in omp (OMPS) help Qwen and hurt MiMo? Two candidate channels, per model and part,
OMPS against OMPF and DSHF on draws 1-2 of the same items:
  1. the read state: how often the attempt read the governing provision, and the score when it did and did not
     (the step split of analyze_legal_agent_interaction, which MC-117's protocol lists beside the tests but its
     registered report did not compute);
  2. compliance with the answer format the prompt asks for ("only the letter" on MC, "a short phrase or number" on
     ViBidLQA): length, markdown, extra explanation, citations; on MC, the share of one-letter answers and strict
     accuracy (right only when the answer is one letter equal to gold); on ViBidLQA, token-F1 split into gold-token
     recall and precision (token-F1 penalises long answers through precision).

    .venv/bin/python -m code_benchmark.explore_legal_agent_omp_prompt
"""
from __future__ import annotations

import json
import random
import re
import statistics
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_legal_agent as ala
    from code_benchmark import analyze_legal_agent_interaction as ali
    from code_benchmark import analyze_legal_agent_mechanism as mech
    from code_benchmark import analyze_legal_agent_v2 as alv2
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_agent_omp_prompt as lp
    from code_benchmark import diagnostic_legal_agent_v2 as l2
except ImportError:  # pragma: no cover - run from code_benchmark/
    import analyze_legal_agent as ala  # type: ignore[no-redef]
    import analyze_legal_agent_interaction as ali  # type: ignore[no-redef]
    import analyze_legal_agent_mechanism as mech  # type: ignore[no-redef]
    import analyze_legal_agent_v2 as alv2  # type: ignore[no-redef]
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_omp_prompt as lp  # type: ignore[no-redef]
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]

ROOT = lp.ROOT
REPORT_SHA256 = "bfd544bdd5b981aab380ce12a6de033760e2d943937752a81cdcfca4b3b15b78"
REPORT = lp.WORK_ROOT / "analysis" / "legal_agent_omp_prompt_report.json"
OUT = lp.WORK_ROOT / "explore" / "omp_prompt_followup.json"
ARMS = ("OMPS", "OMPF", "DSHF")
SEED, RESAMPLES = 7, 2000
_WORD = re.compile(r"\w+", re.UNICODE)


def _pct(x: float) -> float:
    return round(100.0 * x, 2)


def omps_attempts() -> list[dict[str, Any]]:
    """MC-117's OMPS attempts in the shape analyze_legal_agent_interaction uses (no yardstick needed)."""
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if mech.v1.sha256_file(REPORT) != REPORT_SHA256:
        raise SystemExit("Error: the registered report differs from bfd544bd...")
    manifest = l2.load_frozen_manifest()
    support = manifest["support"]
    legal_provisions, other_provisions = la.load_provisions(), l2.load_provisions()
    out = []
    for model in lp.MODELS:
        run_dir = lp.WORK_ROOT / "run" / lp.model_spec(lp.load_protocol(), model)["profile_id"]
        rows = mech._load_scores(run_dir / "scores.jsonl", report["scores_sha256"][model])  # noqa: SLF001
        for row in rows:
            key = f"{row['dataset_id']}:{row['item_id']}"
            legal = row["dataset_id"] == alv2.LEGAL_MC
            part = "S" if row.get("part") == "S" else "M"
            provisions = legal_provisions if legal else other_provisions
            located = provisions[row["item_id"]]["provisions"] if support.get(key) != "no_provision" else []
            out.append({"part": part, "source": "legal_mc" if legal else ("bidlqa" if part == "S" else "vmlu_law"),
                        "key": key, "arm": "OMPS", "draw": str(row["replicate_id"]).split("-r")[1],
                        "score": float(row.get(mech.METRIC[part]) or 0.0), "baseline": 0.0,
                        "run_dir": run_dir, "row": row, "provisions": located, "model": model})
    return out


def featurize(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cache: dict[str, list[str]] = {}
    for a in attempts:
        records = ala.load_attempt_records(a["run_dir"], a["row"])
        a["features"] = mech.attempt_features(records, "dsh" if a["arm"] == "DSHF" else "omp", a["provisions"], cache)
    return attempts


def style(a: dict[str, Any]) -> dict[str, float]:
    raw = str(a["row"].get("raw_response") or "")
    scored = str(a["row"].get("prediction") or "")
    out = {"raw_chars": len(raw), "raw_words": len(_WORD.findall(raw)), "scored_words": len(_WORD.findall(scored)),
           "markdown": float("**" in raw or "\n- " in raw or raw.lstrip().startswith(("-", "#"))),
           "multiline": float("\n" in raw.strip()),
           "cites_article": float(bool(re.search(r"Điều\s+\d+", raw))),
           "explains": float(bool(re.search(r"(?i)cơ sở|căn cứ|vì |theo quy định|giải thích", raw)))}
    if a["part"] == "M":
        out["unparsed"] = float(not scored.strip())
    else:
        f1 = float(a["row"].get("token_f1") or 0.0)
        recall = float(a["row"].get("token_recall") or 0.0)
        # token-F1 = 2PR/(P+R)  ->  P = F1*R / (2R - F1) when 2R > F1
        out["token_recall"] = recall
        out["token_precision"] = (f1 * recall / (2 * recall - f1)) if 2 * recall - f1 > 1e-9 else 0.0
        out["em"] = float(a["row"].get("em") or 0.0)
    return out


def _boot(values: list[float]) -> list[float]:
    rng = random.Random(SEED)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(RESAMPLES))
    return [round(means[int(0.025 * RESAMPLES)], 3), round(means[int(0.975 * RESAMPLES) - 1], 3)]


def cell(rows: list[dict[str, Any]]) -> dict[str, Any]:
    styles = [style(a) for a in rows]
    located = [a for a in rows if a["features"]["stage"]]
    read = [a["score"] for a in located if a["features"]["stage"] == "read"]
    unread = [a["score"] for a in located if a["features"]["stage"] != "read"]
    out: dict[str, Any] = {
        "attempts": len(rows), "score_points": _pct(statistics.fmean(a["score"] for a in rows)),
        "read_rate_pct": _pct(len(read) / len(located)) if located else None,
        "score_read_points": _pct(statistics.fmean(read)) if read else None,
        "score_not_read_points": _pct(statistics.fmean(unread)) if unread else None,
        "requests_mean": round(statistics.fmean(a["features"]["requests"] for a in rows), 2),
        "read_calls_mean": round(statistics.fmean(a["features"]["read_calls"] for a in rows), 2),
        "search_calls_mean": round(statistics.fmean(a["features"]["search_calls"] for a in rows), 2),
    }
    for name in styles[0]:
        values = [s[name] for s in styles]
        mean = statistics.fmean(values)
        out[name] = round(mean, 3) if name.endswith(("chars", "words")) else _pct(mean)
    return out


def paired_style(rows: list[dict[str, Any]], model: str, part: str, name: str) -> dict[str, Any]:
    """Per item, OMPS - OMPF of a style measure (mean over draws), with a bootstrap CI over items."""
    by: dict[str, dict[str, list[float]]] = {}
    for a in rows:
        if a["model"] == model and a["part"] == part and a["arm"] in ("OMPS", "OMPF"):
            by.setdefault(a["key"], {}).setdefault(a["arm"], []).append(style(a)[name])
    diffs = [statistics.fmean(v["OMPS"]) - statistics.fmean(v["OMPF"]) for v in by.values() if len(v) == 2]
    return {"items": len(diffs), "mean": round(statistics.fmean(diffs), 3), "ci95": _boot(diffs)}


def within_read_state(rows: list[dict[str, Any]], model: str, part: str) -> dict[str, Any]:
    """OMPS - OMPF on the same item and draw when both attempts read the governing provision."""
    pairs: dict[tuple[str, str], dict[str, float]] = {}
    for a in rows:
        if a["model"] == model and a["part"] == part and a["arm"] in ("OMPS", "OMPF") and \
                a["features"]["stage"] == "read":
            pairs.setdefault((a["key"], a["draw"]), {})[a["arm"]] = a["score"]
    diffs = [v["OMPS"] - v["OMPF"] for v in pairs.values() if len(v) == 2]
    return {"pairs": len(diffs), "mean_points": _pct(statistics.fmean(diffs)) if diffs else None,
            "ci95_points": [round(100 * x, 2) for x in _boot(diffs)] if len(diffs) > 1 else None}


_STATED = re.compile(r"(?i)đáp án(?:\s+đúng)?(?:\s+là)?\s*[:：]?\s*[*_`\s]*([A-E])(?![\w])")


def stated_letter(raw: str, frozen: str) -> str:
    """Exploratory MC reading (not the registered scorer): the letter on the answer's last non-empty line when that
    line is only a letter (markdown stripped); else the last 'Đáp án (đúng) (là) X' in the text; else the frozen V1
    extractor's letter. It targets answers that explain first and give the letter at the end, which the frozen
    extractor reads as the first standalone letter of the explanation."""
    lines = [line for line in raw.splitlines() if line.strip()]
    if lines:
        last = re.sub(r"[*_`\s.:)(\[\]]", "", lines[-1])
        if re.fullmatch(r"[A-E]", last):
            return last
    found = _STATED.findall(raw)
    return found[-1].upper() if found else frozen


def mc_alternative(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Per model and arm on Part M: the frozen accuracy, the accuracy with stated_letter, and how many attempts the
    two readings disagree on; then OMPS - OMPF and the remaining interaction under each reading (item means)."""
    out: dict[str, Any] = {"cells": {}, "omps_minus_ompf": {}, "interaction": {}}
    item: dict[tuple[str, str, str], dict[str, list[float]]] = {}
    for a in attempts:
        if a["part"] != "M":
            continue
        row = a["row"]
        frozen = str(row.get("prediction") or "")
        alt = stated_letter(str(row.get("raw_response") or ""), frozen)
        gold = str(row.get("gold_answer") or "")
        c = out["cells"].setdefault(f"{a['model']}_{a['arm']}", {"attempts": 0, "frozen": 0, "stated": 0, "differ": 0})
        c["attempts"] += 1
        c["frozen"] += int(a["score"] == 1.0)
        c["stated"] += int(alt == gold)
        c["differ"] += int(alt != frozen)
        cell = item.setdefault((a["model"], a["arm"], a["key"]), {"frozen": [], "stated": []})
        cell["frozen"].append(a["score"])
        cell["stated"].append(float(alt == gold))
    for c in out["cells"].values():
        c["frozen_pct"], c["stated_pct"] = _pct(c["frozen"] / c["attempts"]), _pct(c["stated"] / c["attempts"])
    keys = sorted({k for _, _, k in item})

    def mean(model: str, arm: str, key: str, reading: str) -> float:
        return statistics.fmean(item[(model, arm, key)][reading])

    for reading in ("frozen", "stated"):
        for model in lp.MODELS:
            diffs = [mean(model, "OMPS", k, reading) - mean(model, "OMPF", k, reading) for k in keys]
            out["omps_minus_ompf"][f"{model}_{reading}"] = {"mean_points": _pct(statistics.fmean(diffs)),
                                                            "ci95_points": [round(100 * x, 2) for x in _boot(diffs)]}
        for left, name in (("OMPF", "original"), ("OMPS", "remaining")):
            diffs = [(mean("mimo", left, k, reading) - mean("mimo", "DSHF", k, reading))
                     - (mean("qwen", left, k, reading) - mean("qwen", "DSHF", k, reading)) for k in keys]
            out["interaction"][f"{name}_{reading}"] = {"mean_points": _pct(statistics.fmean(diffs)),
                                                       "ci95_points": [round(100 * x, 2) for x in _boot(diffs)]}
    return out


def lone_letter(raw: str) -> str | None:
    """The answer when it is only one letter A-E (markdown, brackets and a full stop allowed): what the MC prompt asks
    for ("Chỉ đưa ra chữ cái đứng trước câu trả lời đúng"); None otherwise."""
    stripped = re.sub(r"[*_`\s.:()\[\]]", "", raw or "")
    return stripped if re.fullmatch(r"[A-E]", stripped) else None


def mc_format(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Part M under the prompt's own format rule. Per model and arm: the share of answers that are only a letter, the
    accuracy among them and among the rest (frozen extractor), and strict accuracy (right only when the answer is one
    letter equal to gold). Then the harness gaps, the OMPS change and the interactions under the registered and the
    strict reading, item means with a bootstrap CI over items."""
    item: dict[tuple[str, str, str], dict[str, list[float]]] = {}
    out: dict[str, Any] = {"cells": {}, "contrasts": {}}
    for a in attempts:
        if a["part"] != "M":
            continue
        raw, gold = str(a["row"].get("raw_response") or ""), str(a["row"].get("gold_answer") or "")
        letter = lone_letter(raw)
        cell = item.setdefault((a["model"], a["arm"], a["key"]), {"registered": [], "strict": [], "lone": []})
        cell["registered"].append(a["score"])
        cell["strict"].append(float(letter == gold))
        cell["lone"].append(float(letter is not None))
        c = out["cells"].setdefault(f"{a['model']}_{a['arm']}", {"attempts": 0, "lone": 0, "lone_right": 0,
                                                                 "long": 0, "long_right": 0, "empty": 0})
        c["attempts"] += 1
        c["empty"] += int(not raw.strip())
        if letter is not None:
            c["lone"] += 1
            c["lone_right"] += int(letter == gold)
        else:
            c["long"] += 1
            c["long_right"] += int(a["score"] == 1.0)
    for c in out["cells"].values():
        c.update({"lone_pct": _pct(c["lone"] / c["attempts"]), "empty_pct": _pct(c["empty"] / c["attempts"]),
                  "accuracy_when_lone_pct": _pct(c["lone_right"] / c["lone"]) if c["lone"] else None,
                  "accuracy_when_long_pct": _pct(c["long_right"] / c["long"]) if c["long"] else None,
                  "strict_accuracy_pct": _pct(c["lone_right"] / c["attempts"])})
    keys = sorted({k for _, _, k in item})

    def m(model: str, arm: str, key: str, reading: str) -> float:
        return statistics.fmean(item[(model, arm, key)][reading])

    contrasts = {
        "qwen_OMPF_minus_DSHF": lambda k, r: m("qwen", "OMPF", k, r) - m("qwen", "DSHF", k, r),
        "mimo_OMPF_minus_DSHF": lambda k, r: m("mimo", "OMPF", k, r) - m("mimo", "DSHF", k, r),
        "interaction_original": lambda k, r: (m("mimo", "OMPF", k, r) - m("mimo", "DSHF", k, r))
        - (m("qwen", "OMPF", k, r) - m("qwen", "DSHF", k, r)),
        "qwen_OMPS_minus_OMPF": lambda k, r: m("qwen", "OMPS", k, r) - m("qwen", "OMPF", k, r),
        "mimo_OMPS_minus_OMPF": lambda k, r: m("mimo", "OMPS", k, r) - m("mimo", "OMPF", k, r),
        "interaction_remaining": lambda k, r: (m("mimo", "OMPS", k, r) - m("mimo", "DSHF", k, r))
        - (m("qwen", "OMPS", k, r) - m("qwen", "DSHF", k, r)),
    }
    for name, f in contrasts.items():
        out["contrasts"][name] = {}
        for reading in ("registered", "strict", "lone"):
            diffs = [f(k, reading) for k in keys]
            out["contrasts"][name][reading] = {"mean_points": _pct(statistics.fmean(diffs)),
                                               "ci95_points": [round(100 * x, 2) for x in _boot(diffs)]}
    return out


def s_recall(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Part S with gold-token recall (descriptive in the registered scorer) in place of token-F1: per model OMPS - OMPF,
    and the original and remaining interaction (item means)."""
    item: dict[tuple[str, str, str], list[float]] = {}
    for a in attempts:
        if a["part"] == "S":
            item.setdefault((a["model"], a["arm"], a["key"]), []).append(float(a["row"].get("token_recall") or 0.0))
    keys = sorted({k for _, _, k in item})

    def mean(model: str, arm: str, key: str) -> float:
        return statistics.fmean(item[(model, arm, key)])

    out: dict[str, Any] = {}
    for model in lp.MODELS:
        diffs = [mean(model, "OMPS", k) - mean(model, "OMPF", k) for k in keys]
        out[f"{model}_omps_minus_ompf"] = {"mean_points": _pct(statistics.fmean(diffs)),
                                           "ci95_points": [round(100 * x, 2) for x in _boot(diffs)]}
    for left, name in (("OMPF", "original"), ("OMPS", "remaining")):
        diffs = [(mean("mimo", left, k) - mean("mimo", "DSHF", k)) - (mean("qwen", left, k) - mean("qwen", "DSHF", k))
                 for k in keys]
        out[f"interaction_{name}"] = {"mean_points": _pct(statistics.fmean(diffs)),
                                      "ci95_points": [round(100 * x, 2) for x in _boot(diffs)]}
    return out


def build() -> dict[str, Any]:
    attempts = featurize(omps_attempts() + ali.qwen_attempts() + ali.mimo_attempts())
    out: dict[str, Any] = {"analysis": "legal-agent-omp-prompt-followup", "preregistered": False,
                           "after_registered_report": REPORT_SHA256, "draws": ["1", "2"], "cells": {}, "paired": {}}
    for part in ("M", "S"):
        for model in lp.MODELS:
            rows = [a for a in attempts if a["part"] == part and a["model"] == model]
            out["cells"][f"{part}_{model}"] = {arm: cell([a for a in rows if a["arm"] == arm]) for arm in ARMS}
            names = ["raw_words", "scored_words", "markdown", "explains", "cites_article"] + (
                ["token_recall", "token_precision"] if part == "S" else ["unparsed"])
            out["paired"][f"{part}_{model}"] = {
                "style_omps_minus_ompf": {n: paired_style(attempts, model, part, n) for n in names},
                "score_when_both_read": within_read_state(attempts, model, part)}
    out["mc_alternative_reading"] = mc_alternative(attempts)
    out["mc_format_rule"] = mc_format(attempts)
    out["s_gold_token_recall"] = s_recall(attempts)
    return out


def main() -> int:
    report = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} sha256 {mech.v1.sha256_file(Path(OUT))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
