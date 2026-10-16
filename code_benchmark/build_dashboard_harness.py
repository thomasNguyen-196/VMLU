"""Persist the harness-arm results: patch `web/public/benchmark-data.json` and
write a self-contained `harness_report.html`.

WHAT THIS IS FOR
----------------
The harness study produced ~2.700 item-level results across 9 arms (direct
prompt, the `omp` agent with/without tools, with/without the coding persona,
with/without the leaked `APPEND_SYSTEM.md`). Those numbers only existed in CSVs
under `all_res/` and in prose in `docs/` + `measurement_card.md`, so nothing
could be displayed or reviewed from one place. This builder makes the JSON block
the single display surface, the same way the other `build_dashboard_*.py` scripts
do it for VMLU/V-Bench/reading/legal/ViBidLQA/VM14K.

NO NUMBER IS TYPED HERE. Everything is read from the artifacts the run wrote:
  * `harness_compare_<ds>[_tag]_<slug>.csv` — paired Δ / CI / McNemar / 2×2
  * `harness_ledger_<ds>_<slug>.csv`       — per-item cost + audit columns
  * `reading_summary_<slug>.csv`           — the frozen scorer's own table
  * `speed_summary_<ds>[_tag]_<slug>.csv`  — the cost probe
Each row is cross-checked against the arm's own per-item file (the same
"summary must agree with the items" gate the other builders use), and a missing
or partial artifact aborts instead of silently shrinking the table.

  out: web/public/benchmark-data.json  ->  .harness
       harness_report.html               (offline, no build step, like review_ui.html)

Run from repo root:
  .venv/bin/python code_benchmark/build_dashboard_harness.py
  .venv/bin/python code_benchmark/build_dashboard_harness.py --no-html
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
from pathlib import Path

try:
    from code_benchmark.common import read_csv_checked
    from code_benchmark.run_harness_eval import (ARM_A, _mc_eval_path, _vbench_mc_letters)
    from code_benchmark.score_reading_eval import measurement_card_hash, score_pair
except ImportError:
    from common import read_csv_checked
    from run_harness_eval import (ARM_A, _mc_eval_path, _vbench_mc_letters)
    from score_reading_eval import measurement_card_hash, score_pair

DASHBOARD = Path("web/public/benchmark-data.json")
RESULTS_DIR = Path("all_res/ollama_result")
HTML_OUT = Path("harness_report.html")

# Which arm is which condition, in report order. The METRICS come from the
# artifacts; only the human labels and the card ids are declared here.
ARMS = [
    ("A_direct", "Qwen3_5-9B-28K", "A", "Gọi API trực tiếp (không harness)", None),
    ("ompH2_Qwen3_5-9B-28K", "ompH2_Qwen3_5-9B-28K", "H2",
     "omp: tool đầy đủ + system prompt của omp (có rò style)", "MC-15/16/17"),
    ("ompH1_Qwen3_5-9B-28K", "ompH1_Qwen3_5-9B-28K", "H1",
     "omp: không tool + system prompt của omp (có rò style)", "MC-20"),
    ("ompH3_Qwen3_5-9B-28K", "ompH3_Qwen3_5-9B-28K", "H3",
     "omp: tool đầy đủ + system prompt trung tính (có rò style)", "MC-21"),
    ("ompH4_Qwen3_5-9B-28K", "ompH4_Qwen3_5-9B-28K", "H4",
     "omp: không tool + system prompt trung tính (có rò style)", "MC-21"),
    ("ompH5clean_Qwen3_5-9B-28K", "ompH5clean_Qwen3_5-9B-28K", "H5",
     "omp sạch: không tool + system prompt trung tính, HOME override", "MC-22"),
    ("ompH6clean_Qwen3_5-9B-28K", "ompH6clean_Qwen3_5-9B-28K", "H6",
     "omp sạch + tool menu đầy đủ", "MC-23"),
    ("ompH7clean_Qwen3_5-9B-28K", "ompH7clean_Qwen3_5-9B-28K", "H7",
     "omp sạch + system prompt của omp, không tool", "MC-23"),
    ("ompH8clean_Qwen3_5-9B-28K", "ompH8clean_Qwen3_5-9B-28K", "H8",
     "omp sạch + tool menu + system prompt của omp", "MC-23"),
    ("ompV1clean_Qwen3_5-9B-28K", "ompV1clean_Qwen3_5-9B-28K", "V1",
     "omp sạch + tool menu đầy đủ, trên V-Bench function-calling (nơi scaffold "
     "*có thể* thắng)", "MC-26"),
    # ── model thứ hai (MC-30): cùng scaffold, model khác, điều kiện đã vá theo MC-29 ──
    ("A2_direct_mimo", "mimo-v2_5", "A2",
     "MiMo V2.5: gọi API trực tiếp (không harness)", None),
    ("ompM6clean_mimo-v2.5", "ompM6clean_mimo-v2_5", "M6",
     "MiMo V2.5: omp sạch, không công cụ, prompt trung tính, sandbox ngoài repo; proxy ghim "
     "temperature 0 và tắt reasoning", "MC-30"),
    ("ompM6inrepo_mimo-v2.5", "ompM6inrepo_mimo-v2_5", "M6L",
     "MiMo V2.5: cùng arm M6 nhưng sandbox trong repo, nên AGENTS.md được nạp vào mọi item; "
     "ablation MC-29", "MC-30"),
    # ── model thứ ba (MC-31/MC-32): Qwen3.5-9B-65K, node duy nhất còn chạy ──
    ("A3_direct", "Qwen3_5-9B-65K", "A3",
     "Qwen3.5-9B-65K: gọi API trực tiếp (không harness)", None),
    ("ompT65_Qwen3_5-9B-65K", "ompT65_Qwen3_5-9B-65K", "T65",
     "Qwen3.5-9B-65K: omp sạch + tool menu đầy đủ, temperature 0 ghim bằng proxy",
     "MC-31/32"),
    # ── MC-46/47: the persona × tools FACTORIAL on the model under test. On 28K the
    #    two genes were indistinguishable from zero and the scaffold took the blame;
    #    on 65K the reading INVERTS — the minimal scaffold cell is nearly free and
    #    the tools plus omp's own persona are what cost. Same arm, one gene moved.
    ("ompF5clean_Qwen3_5-9B-65K", "ompF5clean_Qwen3_5-9B-65K", "F5",
     "65K: omp sạch, không công cụ, prompt trung tính — scaffold tối giản",
     "MC-46/47"),
    ("ompF7clean_Qwen3_5-9B-65K", "ompF7clean_Qwen3_5-9B-65K", "F7",
     "65K: omp sạch, không công cụ, prompt gốc của omp", "MC-46/47"),
    ("ompF8clean_Qwen3_5-9B-65K", "ompF8clean_Qwen3_5-9B-65K", "F8",
     "65K: omp sạch + tool menu đầy đủ, system prompt gốc của omp", "MC-46/47"),
    # Two clean repeats of the tools+minimal-prompt cell: the 65K noise floor. They
    # are arms in their own right because a repeat that is not displayed is a
    # measurement nobody can see — and the floor is what every small contrast is
    # measured against.
    ("ompT65r2_Qwen3_5-9B-65K", "ompT65r2_Qwen3_5-9B-65K", "T65r2",
     "65K: lặp 2 của ô tool đầy đủ + prompt trung tính (sàn nhiễu)", "MC-47"),
    ("ompT65r3_Qwen3_5-9B-65K", "ompT65r3_Qwen3_5-9B-65K", "T65r3",
     "65K: lặp 3 của ô tool đầy đủ + prompt trung tính (sàn nhiễu)", "MC-47"),
]
# Short ids of the direct-prompt baselines (one per model). A harness arm is
# scored against its OWN arm A, so a new model must extend this tuple — the two
# `in ("A", "A2")` checks below both read it.
BASELINE_SHORTS = ("A", "A2", "A3")
# Which MODEL each arm measures. A ladder row is only comparable inside one model:
# the whole point of the arm is that model, prompt and scorer are held fixed, so a
# delta that spans two models is not a delta at all.
ARM_MODEL = {short: "Qwen3.5-9B-28K" for _k, _s, short, _l, _c in ARMS[:10]}
ARM_MODEL.update({"A2": "MiMo V2.5", "M6": "MiMo V2.5", "M6L": "MiMo V2.5"})
ARM_MODEL.update({"A3": "Qwen3.5-9B-65K", "T65": "Qwen3.5-9B-65K"})
# MC-46/47 factorial cells and repeats, all on the model under test.
ARM_MODEL.update({s: "Qwen3.5-9B-65K" for s in ("F5", "F7", "F8", "T65r2", "T65r3")})
# The arms that carry the "clean scaffold" condition. An explicit set, not a
# substring test on the slug: M6L is clean in every way EXCEPT that its sandbox sits
# inside the repo, and a substring match would silently fold it into the headline.
CLEAN_ARMS = {"H5", "H6", "H7", "H8", "V1", "M6", "T65",
              "F5", "F7", "F8", "T65r2", "T65r3"}
# The one clean arm that represents its model in the with/without table.
REPRESENTATIVE = {"Qwen3.5-9B-28K": "H5", "MiMo V2.5": "M6", "Qwen3.5-9B-65K": "T65"}
DATASETS = ["reading400", "legal_mc", "legal_nli", "bidlqa_val", "vbench_agentic"]
# Per-arm coverage = what each arm ACTUALLY ran, declared. A dataset is only
# claimed by an arm that has a paired compare for it; an arm that does not list a
# dataset is never asked for it, and an arm that lists one but has no per-item
# file aborts the build rather than silently shrinking the table. The Qwen arms
# are deliberately uneven (the factorial cells ran 100 legal-MC items only; V1 ran
# V-Bench only) — that is the run history, not an oversight.
_ALL = DATASETS
_FOUR = ["reading400", "legal_mc", "legal_nli", "bidlqa_val"]
_MC = ["legal_mc"]
# Keyed by SLUG, not by the short id: the slug is the arm's real identity (its
# folder), so a caller passing its own `arms=` list can never inherit a coverage
# promise meant for a different arm that happens to share a display id.
ARM_DATASETS = {
    "Qwen3_5-9B-28K": _ALL,
    "ompH2_Qwen3_5-9B-28K": _FOUR, "ompH1_Qwen3_5-9B-28K": _MC,
    "ompH3_Qwen3_5-9B-28K": _MC, "ompH4_Qwen3_5-9B-28K": _MC,
    "ompH5clean_Qwen3_5-9B-28K": _FOUR, "ompH6clean_Qwen3_5-9B-28K": _MC,
    "ompH7clean_Qwen3_5-9B-28K": _MC, "ompH8clean_Qwen3_5-9B-28K": _MC,
    "ompV1clean_Qwen3_5-9B-28K": ["vbench_agentic"],
    "mimo-v2_5": _ALL + ["vbench_mc"],
    "ompM6clean_mimo-v2_5": _ALL + ["vbench_mc"],
    "ompM6inrepo_mimo-v2_5": _MC,
    "Qwen3_5-9B-65K": _ALL + ["vbench_mc"],
    "ompT65_Qwen3_5-9B-65K": _ALL + ["vbench_mc"],
    "ompF5clean_Qwen3_5-9B-65K": _MC, "ompF7clean_Qwen3_5-9B-65K": _MC,
    "ompF8clean_Qwen3_5-9B-65K": _MC,
    "ompT65r2_Qwen3_5-9B-65K": _MC, "ompT65r3_Qwen3_5-9B-65K": _MC,
}


def datasets_for(slug: str) -> list[str]:
    """An arm's declared coverage; an arm nobody declared falls back to "try
    everything", which is what an ad-hoc `arms=` list (the tests) wants."""
    return ARM_DATASETS.get(slug, DATASETS)
DATASET_LABEL = {"reading400": "reading-400 (EM)", "legal_mc": "legal-MC (accuracy)",
                 "legal_nli": "legal-NLI (accuracy)", "bidlqa_val": "ViBidLQA val (EM)",
                 "vbench_agentic": "V-Bench agentic — schema validity, không có gold cục bộ",
                 "vbench_mc": "V-Bench MC 12 domain — trùng khớp arm A, không có gold cục bộ"}

# Short metric notes appear on the metric label and in the shared legend.
METRIC_NOTE: dict[str, dict] = {
    "accuracy": {
        "unit": "điểm", "not_a_score": False,
        "what": "Tỷ lệ câu đúng trên bộ gold cục bộ.",
    },
    "EM": {
        "unit": "điểm", "not_a_score": False,
        "what": "Tỷ lệ khớp chính xác trên gold đã hiệu đính.",
    },
    "server_accuracy": {
        "unit": "điểm", "not_a_score": False,
        "what": "Điểm do vbench.ai chấm; không có gold cục bộ để kiểm chứng offline.",
    },
    "valid_rate": {
        "unit": "tỉ lệ", "not_a_score": True,
        "what": "Tỷ lệ lời gọi khớp schema; không cho biết hàm và tham số có đúng không.",
    },
    "agreement": {
        "unit": "tỉ lệ", "not_a_score": True,
        "what": "Tỷ lệ câu agent giữ nguyên đáp án so với arm A; không đo độ đúng.",
    },
}

# Server-side ACCURACY for V-Bench MC's 12 domains, read from the snapshot the
# grade endpoint returned. This is the one number in the whole block that answers
# "did the model actually get more answers wrong" — agreement cannot, and before
# MC-48 the block carried no such column at all, which is how a −22.39 agreement
# delta got read as a −22.39 quality drop that does not exist (MiMo's real MC
# accuracy went UP 2.13 points under the same scaffold).
# The same metric is spelled two ways in the artifacts: `arm_metrics` computes
# it and calls it `agreement`, while the `compare` CSV carries the machine name
# `agreement_with_arm_A`. Two spellings for one metric meant the page's note
# lookup silently missed and rendered "agreement_with_arm_A (?)" -- the exact
# ambiguity this table exists to remove. One alias table, one canonical name;
# the verbatim CSV name is kept as `metric_raw` for provenance.
METRIC_ALIASES = {
    "agreement_with_arm_A": "agreement",
}


def canonical_metric(metric: str) -> str:
    return METRIC_ALIASES.get(metric, metric)


SERVER_MC_REQUIRED = {"domain", "score", "correct", "total"}


def vbench_mc_server(folder: Path, slug: str) -> dict | None:
    """Server accuracy over the 12 MC domains for one arm, or None if ungraded.

    Aggregated from the per-domain rows the site returned, never from prose. The
    site's denominator is `totalQuestions`, so a blank/unparsed answer we did not
    submit counts as WRONG — it is not dropped, and this number therefore already
    carries the cost of any crash in that arm.
    """
    snap = folder / f"vbench_server_scores_{slug}.csv"
    if not snap.exists():
        return None
    rows = read_csv_checked(snap, required=SERVER_MC_REQUIRED, label=f"{slug} server MC snapshot")
    mc = [r for r in rows if r["domain"] != "agentic"]
    if not mc:
        return None
    correct = sum(int(r["correct"]) for r in mc)
    total = sum(int(r["total"]) for r in mc)
    if total <= 0:
        return None
    domains = {r["domain"]: round(f2(r["score"]), 2) for r in mc}
    return {"score": round(100.0 * correct / total, 2), "correct": correct, "total": total,
            "matched": sum(int(r["matched"]) for r in mc) if "matched" in mc[0] else "",
            "domains": domains}


def _int_or_blank(value: str) -> int | str:
    """A paired cell that the track deliberately leaves empty stays empty.

    The baseline arm already emits "" for those; a harness arm must not invent a
    0, or the page shows "0 items where only arm A was right" for a track that
    never computed that split.
    """
    text = (value or "").strip()
    return int(text) if text else ""


def f2(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def vi_num(value: float, digits: int = 2) -> str:
    """Format numbers for Vietnamese prose, including grouped thousands."""
    return f"{value:,.{digits}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def vi_delta(value: float, digits: int = 2) -> str:
    """Format a signed score delta with Vietnamese decimal separators."""
    return f"{value:+,.{digits}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def vi_int(value: int | float) -> str:
    """Format an integer count with dot thousands separators."""
    return f"{int(value):,}".replace(",", ".")


def read_compare(folder: Path, dataset: str, tag: str = "vsA") -> dict | None:
    """One paired comparison row (Δ vs arm A) for a dataset, or None if absent."""
    path = folder / f"harness_compare_{dataset}_{tag}_{folder.name}.csv"
    if not path.exists():
        return None
    rows = read_csv_checked(path, required={"metric", "n", "arm_a", "arm_b", "delta",
                                            "ci95_low", "ci95_high", "mcnemar_p"},
                            label=f"compare {dataset} {tag}")
    if len(rows) != 1:
        raise SystemExit(f"Error: {path} has {len(rows)} rows, want exactly 1 (group=ALL)")
    return rows[0]


def arm_metrics(folder: Path, dataset: str, spec: dict, slug: str,
                *, arm_a_slug: str | None = None) -> dict | None:
    """The arm's own score, recomputed from its per-item file (never from prose).

    Works for the direct-prompt baseline too: `_mc_eval_path` resolves both the
    historical `full_evaluation_legal_*` naming and the harness arms'
    `full_evaluation_<dataset>_*` one.
    """
    kind = spec["kind"]
    if kind == "mc":
        try:
            path = _mc_eval_path(folder, dataset, slug)
        except SystemExit:
            return None
        rows = read_csv_checked(path, required={"id", "answer", "gold_answer", "correct"},
                                label=f"{slug}/{dataset}")
        n = len(rows)
        correct = sum(int(r["correct"]) for r in rows)
        blanks = sum(1 for r in rows if not str(r["answer"]).strip())
        return {"n": n, "metric": "accuracy", "score": round(100.0 * correct / n, 2) if n else 0.0,
                "correct": correct, "blanks": blanks, "unit": "correct"}
    if kind == "vbench":
        # No gold: the arm's own validity summary is the score of record, and it
        # is the SAME computation arm A's summary used (a non-empty shipped
        # answer), so the two sides of the comparison mean the same thing.
        path = folder / f"vbench_valid_summary_{slug}.csv"
        if not path.exists():
            return None
        rows = read_csv_checked(path, required={"track", "n", "valid"}, label=f"{slug}/{dataset}")
        row = next((r for r in rows if r["track"] == "agentic"), None)
        if row is None:
            return None
        n, valid = int(row["n"]), int(row["valid"])
        if not n:
            return None
        out = {"n": n, "metric": "valid_rate", "score": round(100.0 * valid / n, 2),
               "correct": valid, "blanks": n - valid, "unit": "schema-valid call",
               "char_f1": None}
        # Server-side ACCURACY, when a snapshot exists. Validity only says the call
        # matched the schema; the server says whether it was the right call — and the
        # two differ by 3.4x here (MC-28), so they are never merged into one number.
        snap = folder / f"vbench_server_scores_{slug}.csv"
        if snap.exists():
            srows = read_csv_checked(snap, required={"domain", "score", "correct", "total"},
                                     label=f"{slug} server snapshot")
            ag = next((r for r in srows if r["domain"] == "agentic"), None)
            if ag:
                out["server_score"] = round(f2(ag["score"]), 2)
                out["server_correct"] = int(ag["correct"])
                out["server_total"] = int(ag["total"])
        return out
    if kind == "vbench_mc":
        # No gold anywhere, so the pairable number is AGREEMENT with the direct
        # arm: did routing the same prompt through the agent change the letter?
        # Recomputed from both sides' per-item letters so the number cannot be
        # inherited from a prose claim. The direct arm agrees with itself by
        # construction, which is also why no paired test is reported for it.
        if not arm_a_slug:
            return None
        # Arm A's letters live in ARM A's folder, not this arm's: a harness arm has
        # no vbench_result_* checkpoint of its own, only a ledger. `folder.parent`
        # (not the module's RESULTS_DIR) keeps a caller's --results-dir honored.
        a = _vbench_mc_letters(folder.parent / arm_a_slug, arm_a_slug, harness_arm=False)
        if not a:
            return None
        b = _vbench_mc_letters(folder, slug, harness_arm=True)
        if not b:
            # Only the DIRECT arm may fall back to self-agreement: it agrees with
            # itself by construction, and that 100 is the reference its model's
            # harness row is read against. A harness arm with no ledger is not a
            # 100 — it is an unfinished run, so return None and let build_ladder's
            # declared-coverage guard abort, instead of displaying a perfect score
            # that no answer stands behind.
            if slug != arm_a_slug:
                return None
            b = None
        shared = list(a) if b is None else [i for i in a if i in b]
        if not shared:
            return None
        # Two EMPTY answers are not agreement: an empty cell is not an answer, so
        # it must count against the arm that produced it. 9 of the 4.141 rows are
        # blank on both sides here, and counting them as agreeing inflated the
        # recompute by 0.22 points against the compare row.
        same = (len(shared) if b is None
                else sum(1 for i in shared if a[i] and b[i] and a[i] == b[i]))
        n = len(shared)
        out = {"n": n, "metric": "agreement", "score": round(100.0 * same / n, 2),
               "correct": same, "blanks": n - same, "char_f1": None,
               "unit": "cùng chữ cái với arm A"}
        # The REAL accuracy for this cell, when the site has graded it. Agreement
        # and accuracy can point opposite ways (MiMo: −22.39 agreement, +2.13
        # accuracy), so a block that shows only agreement invites reading a
        # "changed answers" count as a "lost points" count.
        mc_server = vbench_mc_server(folder, slug)
        if mc_server:
            out["server_mc"] = mc_server
        if arm_a_slug and arm_a_slug != slug:
            a_server = vbench_mc_server(folder.parent / arm_a_slug, arm_a_slug)
            if a_server:
                out["server_mc_arm_a"] = a_server
        return out
    name = "reading_scores_bidlqa_val" if dataset == "bidlqa_val" else "reading_scores"
    path = folder / f"{name}_{slug}.csv"
    if not path.exists():
        return None
    rows = read_csv_checked(path, required={"item_id", "em", "f1"}, label=f"{slug}/{dataset}")
    n = len(rows)
    em = sum(int(r["em"]) for r in rows)
    f1 = round(sum(float(r["f1"]) for r in rows) / n * 100, 2) if n else 0.0
    return {"n": n, "metric": "EM", "score": round(100.0 * em / n, 2) if n else 0.0,
            "correct": em, "blanks": 0, "char_f1": f1, "unit": "exact match"}


def arm_cost(folder: Path, datasets: list[str]) -> dict | None:
    """Cost + audit from the per-item ledgers of EVERY dataset the arm covered.

    Aggregating per arm (not per dataset) is what makes the totals column
    meaningful: 2 tool calls and 1 sandbox escape are invisible in a single
    dataset's ledger.
    """
    rows: list[dict] = []
    for dataset in datasets:
        for path in sorted(folder.glob(f"harness_ledger_{dataset}_*.csv")):
            with open(path, encoding="utf-8", newline="") as f:
                rows.extend(csv.DictReader(f))
    n = len(rows)
    if not n:
        return None
    return {
        "n": n,
        "datasets": len({r.get("dataset") for r in rows}),
        "wall_s_per_item": round(sum(float(r["wall_s"] or 0) for r in rows) / n, 2),
        "turns_per_item": round(sum(int(r["turns"] or 0) for r in rows) / n, 2),
        "failures": sum(1 for r in rows if r.get("failure")),
        "tool_use_items": sum(1 for r in rows if int(r.get("tool_calls") or 0) > 0),
        "net_attempt_items": sum(1 for r in rows if r.get("net_attempt")),
        "path_escape_items": sum(1 for r in rows if r.get("path_escape")),
        "reported_input_tokens": sum(int(r.get("input_tokens") or 0) for r in rows),
        "reported_cache_read": sum(int(r.get("cache_read_tokens") or 0) for r in rows),
        "completion_tokens": sum(int(r.get("output_tokens") or 0) for r in rows),
    }


def arm_speed(folder: Path) -> list[dict] | None:
    """Speed-probe rows of one arm's folder.

    The CSV's own `arm` column is the SIDE OF THE PAIR (`A_direct` / `B_omp_h2`,
    hardcoded in run_harness_eval._speed_summary) — NOT the arm identity. Five
    different arms (H1…H8clean) all ship `B_omp_h2` there, so it is projected to
    `side` here and the real arm name comes from the registry; historical CSVs
    are left untouched (they are run artifacts, not display state).
    """
    files = sorted(folder.glob("speed_summary_*_main_*.csv")) or \
        sorted(folder.glob("speed_summary_*.csv"))
    if not files:
        return None
    out = []
    for path in files:
        for row in read_csv_checked(path, required={"arm", "n", "wall_p50_s", "wall_mean_s",
                                                    "prompt_tok_per_item",
                                                    "completion_tok_per_item",
                                                    "overhead_s_per_item"},
                                    label=f"speed {folder.name}"):
            side = row["arm"]
            row = dict(row)
            row["side"] = "direct" if side == "A_direct" else "omp"
            out.append(row)
    return out or None


def build_ladder(results_dir: Path, arms: list = ARMS) -> tuple[list[dict], list[dict]]:
    """(rows for the display table, per-arm cost rows) — all read from artifacts.

    The direct-prompt arm is the BASELINE: it has no paired compare of its own,
    so its rows carry `role: "baseline"` and empty paired statistics. Every
    harness arm must have one, or the builder aborts (a per-item file with no
    compare would otherwise be silently displayed as if it were scored).
    """
    rows: list[dict] = []
    costs: list[dict] = []
    # The direct baseline of each model, so a harness arm can be scored against
    # its OWN arm A — never against another model's.
    baseline_slug = {ARM_MODEL[short]: slug for _k, slug, short, _l, _c in arms
                     if short in BASELINE_SHORTS}
    for _key, slug, short, label, card in arms:
        folder = results_dir / slug
        if not folder.exists():
            continue
        baseline = short in BASELINE_SHORTS
        model = ARM_MODEL[short]
        for dataset in datasets_for(slug):
            own = arm_metrics(folder, dataset, ARM_A[dataset], slug,
                              arm_a_slug=baseline_slug.get(model))
            if not own:
                if slug not in ARM_DATASETS:
                    continue      # undeclared coverage: nothing promised here
                # The registry says this arm covers this dataset, so a missing
                # per-item file is an incomplete RUN, not a dataset to skip. Left
                # unchecked, a half-finished arm quietly shrinks the table — the
                # one failure mode this builder exists to prevent.
                raise SystemExit(
                    f"Error: {slug} declares dataset {dataset} but no per-item metrics "
                    f"could be read from {folder}. Finish the run (or drop the dataset "
                    f"from ARM_DATASETS['{slug}']) before rebuilding the block.")

            base = {"arm": short, "arm_slug": slug, "label": label, "card": card,
                    "model": model,
                    "dataset": dataset, "dataset_label": DATASET_LABEL[dataset],
                    "metric": own["metric"], "n": own["n"],
                    "arm_b": own["score"], "char_f1": own.get("char_f1"),
                    "blanks": own["blanks"]}
            # Only emit the server trio when a snapshot exists: a `null` here would
            # read as "present" to the TS validator (`null !== undefined`).
            if own.get("server_score") is not None:
                base.update({"server_score": own["server_score"],
                             "server_correct": own["server_correct"],
                             "server_total": own["server_total"]})
            # V-Bench MC's real accuracy rides beside its agreement. Named
            # `server_mc_*`, NOT `server_*`: the latter is the agentic track's
            # trio, and reusing the name would let a reader compare a 12-domain
            # MC accuracy against a function-calling accuracy as if one scale.
            if own.get("server_mc") is not None:
                base.update({"server_mc_score": own["server_mc"]["score"],
                             "server_mc_correct": own["server_mc"]["correct"],
                             "server_mc_total": own["server_mc"]["total"],
                             "server_mc_domains": own["server_mc"]["domains"]})
            a_mc = own.get("server_mc_arm_a")
            if a_mc:
                base.update({"arm_a_server_mc_score": a_mc["score"],
                             "arm_a_server_mc_correct": a_mc["correct"],
                             "arm_a_server_mc_total": a_mc["total"]})
            if baseline:
                rows.append({**base, "role": "baseline", "arm_a": own["score"],
                             "delta": 0.0, "ci95_low": 0.0, "ci95_high": 0.0,
                             "mcnemar_p": "", "both": "", "a_only": "", "b_only": "",
                             "neither": ""})
                continue
            cmp_row = read_compare(folder, dataset)
            if cmp_row is None:
                raise SystemExit(f"Error: {folder.name}/{dataset} has per-item results but "
                                 f"no harness_compare_{dataset}_vsA_*.csv — run "
                                 f"`run_harness_eval.py compare --dataset {dataset} "
                                 f"--label {slug} --tag vsA` first")
            if int(cmp_row["n"]) != own["n"]:
                raise SystemExit(f"Error: {folder.name}/{dataset}: compare n={cmp_row['n']} "
                                 f"but per-item rows n={own['n']}")
            if abs(f2(cmp_row["arm_b"]) - own["score"]) > 0.01:
                raise SystemExit(f"Error: {folder.name}/{dataset}: compare arm_b="
                                 f"{cmp_row['arm_b']} but per-item recompute={own['score']}")
            lo, hi = f2(cmp_row["ci95_low"]), f2(cmp_row["ci95_high"])
            if lo > hi:
                raise SystemExit(f"Error: {folder.name}/{dataset}: CI inverted ({lo} > {hi})")
            rows.append({**base, "role": "harness", "arm_a": f2(cmp_row["arm_a"]),
                         "delta": f2(cmp_row["delta"]), "ci95_low": lo, "ci95_high": hi,
                         "mcnemar_p": cmp_row["mcnemar_p"],
                         # Some tracks leave the paired cells empty on purpose
                         # (V-Bench MC runs no McNemar and has no a_only/b_only
                         # split), so an empty cell is "" here, never a fake 0.
                         "both": _int_or_blank(cmp_row["both"]),
                         "a_only": _int_or_blank(cmp_row["a_only"]),
                         "b_only": _int_or_blank(cmp_row["b_only"]),
                         "neither": _int_or_blank(cmp_row["neither"])})
        cost = arm_cost(folder, datasets_for(slug))
        if cost:
            costs.append({"arm": short, "arm_slug": slug, "label": label,
                          "model": model, **cost})
    if not rows:
        raise SystemExit(f"Error: no harness artifacts under {results_dir}")
    return rows, costs


def stripped_answer(raw: str) -> str:
    """The model's answer with the harness's wrapper peeled off — SECONDARY ONLY.

    This exists to attribute a loss, never to replace it: the headline EM stays
    the frozen scorer's number computed on the verbatim reply. Rule (fixed, so
    two runs agree): drop fenced blocks, take the first line that still has
    content, drop list markers / markdown emphasis / a leading label
    ("Đáp án:", "Trả lời:", "Verdict:"), and score that with the same
    `score_pair`. A reply that is wrong stays wrong here too.
    """
    text = re.sub(r"```.*?```", " ", raw or "", flags=re.DOTALL)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*+]\s+|^\d+[.)]\s+", "", line)
        # Only a REAL label is peeled: it must be followed by a separator or end
        # the line ("Đáp án: A" yes, "Đáp án là A" no — stripping that one would
        # rewrite the model's sentence instead of its wrapper).
        line = re.sub(r"^\**\s*(?:đáp án|trả lời|verdict|answer)\s*\**\s*(?:[:：-]\s*|$)",
                      "", line, flags=re.IGNORECASE)
        line = line.replace("**", "").replace("`", "").strip()
        line = re.sub(r"^>\s?", "", line).strip()
        if line:
            return line
    return ""


def arg_credit(results_dir: Path, arms: list = ARMS) -> list[dict]:
    """Partial argument credit per arm (1.3): required-arg fill rate and
    supplied-arg precision beside the 0/1 validity the headline uses. Both
    rates are micro-averaged with their denominators shown — an unparseable
    reply contributes to neither rate and is counted openly as unparseable.
    Arms without a credit file (never ran the agentic track) are skipped."""
    out = []
    for _key, slug, short, label, _card in arms:
        paths = sorted((results_dir / slug).glob(f"vbench_arg_credit_{slug}.csv"))
        if not paths:
            continue
        rows = read_csv_checked(paths[-1], required={
            "n_items", "n_attempted", "n_required_slots", "n_required_ok",
            "required_fill_rate", "n_supplied", "n_supplied_ok",
            "arg_precision", "n_unparseable"}, label=f"arg_credit {slug}")
        if len(rows) != 1:
            raise SystemExit(f"Error: {paths[-1]} has {len(rows)} rows, want exactly 1")
        r = rows[0]
        n_items, n_attempted, n_unp = int(r["n_items"]), int(r["n_attempted"]), int(r["n_unparseable"])
        if n_attempted + n_unp != n_items:
            raise SystemExit(f"Error: {slug}: attempted {n_attempted} + unparseable {n_unp} "
                             f"!= n_items {n_items}")
        n_req, n_req_ok = int(r["n_required_slots"]), int(r["n_required_ok"])
        if n_req and abs(f2(r["required_fill_rate"]) - 100.0 * n_req_ok / n_req) > 0.02:
            raise SystemExit(f"Error: {slug}: required_fill_rate {r['required_fill_rate']} "
                             f"!= 100*{n_req_ok}/{n_req}")
        n_sup, n_sup_ok = int(r["n_supplied"]), int(r["n_supplied_ok"])
        if n_sup and abs(f2(r["arg_precision"]) - 100.0 * n_sup_ok / n_sup) > 0.02:
            raise SystemExit(f"Error: {slug}: arg_precision {r['arg_precision']} "
                             f"!= 100*{n_sup_ok}/{n_sup}")
        out.append({"arm": short, "arm_slug": slug, "label": label,
                    "model": ARM_MODEL[short], "n_items": n_items,
                    "n_attempted": n_attempted, "n_required_slots": n_req,
                    "n_required_ok": n_req_ok,
                    "required_fill_rate": f2(r["required_fill_rate"]),
                    "n_supplied": n_sup, "n_supplied_ok": n_sup_ok,
                    "arg_precision": f2(r["arg_precision"]), "n_unparseable": n_unp})
    return out


def breakdown(results_dir: Path, arms: list = ARMS) -> list[dict]:
    """Per-group paired deltas (1.2): the same predicates as the ALL row, cut by
    stratum. A group row is only meaningful beside its headline — the sum of
    group n must equal the compare ALL n, or the cut silently lost items.
    Arms/datasets without a breakdown file contribute nothing (their stratum
    is constant: legal, bidlqa_val, vbench_agentic)."""
    out = []
    for _key, slug, short, label, _card in arms:
        folder = results_dir / slug
        if not folder.exists():
            continue
        for dataset in datasets_for(slug):
            paths = sorted(folder.glob(f"harness_breakdown_{dataset}_vsA_{slug}.csv"))
            if not paths:
                continue
            rows = read_csv_checked(
                paths[-1],
                required={"metric", "group", "n", "arm_a", "arm_b", "delta",
                          "ci95_low", "ci95_high", "mcnemar_p"},
                label=f"breakdown {slug}/{dataset}")
            # V-Bench MC only: this arm's and its own arm A's per-domain server
            # accuracy. Both sides are needed — a group delta needs a baseline to
            # be a delta — and both live in the arm's OWN snapshot files.
            own_b = own_a = None
            if dataset == "vbench_mc":
                own_b = vbench_mc_server(folder, slug)
                base_slug = next((s for _k, s, sh, _l, _c in arms
                                  if sh in BASELINE_SHORTS and ARM_MODEL[sh] == ARM_MODEL[short]),
                                 None)
                if base_slug and base_slug != slug:
                    own_a = vbench_mc_server(folder.parent / base_slug, base_slug)
            groups = []
            for r in rows:
                lo, hi = f2(r["ci95_low"]), f2(r["ci95_high"])
                if lo > hi:
                    raise SystemExit(f"Error: {slug}/{dataset}/{r['group']}: "
                                     f"CI inverted ({lo} > {hi})")
                if abs(f2(r["delta"]) - (f2(r["arm_b"]) - f2(r["arm_a"]))) > 0.02:
                    raise SystemExit(f"Error: {slug}/{dataset}/{r['group']}: "
                                     f"delta {r['delta']} != arm_b - arm_a")
                g = {"group": r["group"], "n": int(r["n"]),
                     "arm_a": f2(r["arm_a"]), "arm_b": f2(r["arm_b"]),
                     "delta": f2(r["delta"]), "ci95_low": lo,
                     "ci95_high": hi, "mcnemar_p": r["mcnemar_p"]}
                # For V-Bench MC the group IS a domain, so the server accuracy for
                # that domain attaches to the group. Without it the domain table
                # shows only agreement, and a reader sees "-40,89 at logics" with
                # no way to learn the real delta was -4.88.
                if dataset == "vbench_mc":
                    dom = g["group"]
                    b_dom = (own_b or {}).get("domains", {}).get(dom)
                    a_dom = (own_a or {}).get("domains", {}).get(dom)
                    if b_dom is not None and a_dom is not None:
                        g["server_mc_arm_a"] = a_dom
                        g["server_mc_arm_b"] = b_dom
                        g["server_mc_delta"] = round(b_dom - a_dom, 2)
                groups.append(g)
            cmp_row = read_compare(folder, dataset)
            if cmp_row is not None and sum(g["n"] for g in groups) != int(cmp_row["n"]):
                raise SystemExit(f"Error: {slug}/{dataset}: breakdown groups sum to "
                                 f"{sum(g['n'] for g in groups)} but compare n={cmp_row['n']}")
            out.append({"arm": short, "arm_slug": slug, "label": label,
                        "model": ARM_MODEL[short], "dataset": dataset,
                        "dataset_label": DATASET_LABEL[dataset],
                        "metric": canonical_metric(rows[0]["metric"]),
                        "metric_raw": rows[0]["metric"], "groups": groups})
    return out


def secondary_metrics(results_dir: Path, arms: list = ARMS) -> list[dict]:
    """Per-arm EM on the verbatim reply vs EM on the stripped answer.

    The gap is the "đúng nội dung nhưng bị chấm 0" share — the number that says
    whether a scaffold's damage is formatting or capability. Reported as a
    clearly separate row; the headline column is untouched.
    """
    out = []
    for _key, slug, short, label, _card in arms:
        folder = results_dir / slug
        if not folder.exists():
            continue
        for dataset in datasets_for(slug):
            if ARM_A[dataset]["kind"] != "reading":
                continue
            led = sorted(folder.glob(f"harness_ledger_{dataset}_*.csv"))
            if not led:
                continue
            with open(led[-1], encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            if not rows or "gold" not in rows[0] or not rows[0]["gold"]:
                continue
            em_verbatim = stripped_em = 0
            for r in rows:
                gold = r["gold"]
                if not gold:
                    continue
                _, _, em, _ = score_pair(r["raw_response"], gold)
                _, _, em2, _ = score_pair(stripped_answer(r["raw_response"]), gold)
                em_verbatim += int(em)
                stripped_em += int(em2)
            n = sum(1 for r in rows if r["gold"])
            if not n:
                continue
            out.append({
                "arm": short, "label": label, "dataset": dataset,
                "dataset_label": DATASET_LABEL[dataset], "n": n,
                "em_verbatim": round(100.0 * em_verbatim / n, 2),
                "em_stripped": round(100.0 * stripped_em / n, 2),
                "wrapper_cost": round(100.0 * (stripped_em - em_verbatim) / n, 2),
            })
    return out


def repeatability(results_dir: Path, arms: list = ARMS) -> list[dict]:
    """How much a cell MOVES between identical runs — the noise floor.

    Repeating the same condition cannot shrink the item-sampling CI, but it does
    expose the other half of the uncertainty: the arm's own run-to-run spread at
    temperature 0 (MC-18 saw 13/20 items flip). A factorial contrast smaller
    than this spread is not a result. Runs are grouped by (cell, n) and NEVER
    pooled across n — r1 used 100 items, r2/r3 use 146, and averaging those would
    be a made-up number.
    """
    rows = []
    # Registry arms first, then any REPEAT slug on disk (`ompH5clean_r2_…`) —
    # they are the whole point of this table and are deliberately absent from
    # ARMS so they can never leak into the headline ladder.
    by_slug = {slug: (short, label, card) for _k, slug, short, label, card in arms}
    slugs = list(by_slug)
    for pattern in ("ompH*_r[0-9]*_*", "ompT65r[0-9]*_*"):
        for folder in sorted(results_dir.glob(pattern)):
            if folder.is_dir() and folder.name not in by_slug:
                slugs.append(folder.name)
    for slug in slugs:
        folder = results_dir / slug
        if not folder.exists():
            continue
        # `clean?` would REQUIRE the literal "clea" (the ? binds to n only), so
        # ompH1…ompH4 silently fell back to the full slug as the cell name.
        # The 65K family needs its own branch: `ompT65r2` has no underscore before
        # the repeat number, and the F-cells are not ompH* at all. Without both, each
        # 65K repeat becomes its own one-run cell and the 65K noise floor is never
        # computed — a measurement that exists on disk and is invisible in the UI.
        match = re.match(r"(ompH\d+(?:clean)?)(?:_r(\d+))?_Qwen", slug) or \
            re.match(r"(ompF\d+clean)(?:_r(\d+))?_Qwen", slug) or \
            re.match(r"(ompT65)(?:_?r(\d+))?_Qwen", slug)
        if match and match.group(1) == "ompT65" and match.group(2) is None:
            # The ORIGINAL T65 arm is its own cell, never pooled with its repeats:
            # its proxy log shows a 690-char system prompt where the repeats show
            # 745, so a "run-to-run spread" across them would be measuring a
            # prompt-shape change and calling it noise — the exact pooling MC-47
            # refused, and the reason its shape is still an open item.
            cell = "ompT65orig"
        else:
            cell = match.group(1) if match else slug
        repeat = int(match.group(2)) if (match and match.group(2)) else 1
        if slug in by_slug:
            short, label, card = by_slug[slug]
        else:  # a repeat: inherit the label of the cell it repeats
            base = (by_slug.get(f"{cell}_Qwen3_5-9B-28K")
                    or by_slug.get(f"{cell}_Qwen3_5-9B-65K"))
            short, label, card = (f"{cell}·r{repeat}", f"{base[1]} — lặp {repeat}" if base
                                  else slug, base[2] if base else None)
        for dataset in datasets_for(slug):
            cmp_row = read_compare(folder, dataset)
            if cmp_row is None:
                continue
            rows.append({
                "cell": cell,
                "repeat": repeat,
                "arm": short, "label": label, "card": card,
                "dataset": dataset, "dataset_label": DATASET_LABEL[dataset],
                "n": int(cmp_row["n"]), "arm_a": round(f2(cmp_row["arm_a"]), 2),
                "arm_b": round(f2(cmp_row["arm_b"]), 2),
                "delta": round(f2(cmp_row["delta"]), 2),
                "ci95_low": round(f2(cmp_row["ci95_low"]), 2),
                "ci95_high": round(f2(cmp_row["ci95_high"]), 2),
                "mcnemar_p": cmp_row["mcnemar_p"],
            })
    # per (cell, n): mean and spread, only where there is more than one run
    groups: dict[tuple[str, int], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["cell"], r["n"]), []).append(r)
    for runs in groups.values():
        if len(runs) < 2:
            continue
        values = [r["arm_b"] for r in runs]
        for r in runs:
            r["cell_n"] = len(runs)
            r["cell_mean"] = round(sum(values) / len(values), 2)
            r["cell_spread"] = round(max(values) - min(values), 2)
            r["cell_min"] = min(values)
            r["cell_max"] = max(values)
    return sorted(rows, key=lambda r: (r["cell"], r["n"], r["repeat"]))


def insight(ladder: list[dict], secondary: list[dict], reps: list[dict],
            speed_rows: list[dict]) -> dict:
    """Lớp diễn giải: mọi con số đều NỘI SUY từ artifact, không gõ tay.

    Một câu diễn giải viết tay về một số đo sẽ hỏng ngay khi có run mới, và không
    ai nhận ra. Vì vậy ở đây không có con số nào gõ tay: mỗi luận điểm dựng từ
    chính các dòng mà block đã mang, và luận điểm thiếu dữ liệu thì BỎ QUA chứ
    không in ra chỗ trống.

    Văn phong: tiếng Việt học thuật; thuật ngữ chuyên ngành không dịch được thì
    giữ nguyên tiếng Anh — chúng được giải thích ở mục "Thuật ngữ" của trang.
    """
    clean_by_model: dict[str, list[dict]] = {}
    for r in ladder:
        if r["role"] != "harness" or r["arm"] not in CLEAN_ARMS:
            continue
        if r["dataset"] == "vbench_agentic":     # validity, not accuracy: never mixed in
            continue
        # Agreement ("did the agent change the answer?") is not a score either, so
        # it must not stretch a range the sentence calls "điểm" (MC-30). The row
        # still appears in the comparison table, where its own note reads it.
        if r["metric"] == "agreement":
            continue
        clean_by_model.setdefault(r.get("model", ""), []).append(r)
    claims: list[dict] = []

    # The noise floor per model, from the repeated cells (>=2 runs at a fixed n).
    # A contrast smaller than this is not a result, so any claim about a small
    # difference must name it rather than assert the difference.
    spread_by_model: dict[str, float] = {}
    for row in reps:
        value = row.get("cell_spread")
        if value in (None, ""):
            continue
        # A repeatability row carries no `model`; the cell name does. Reading it off
        # the registry instead would miss every DISCOVERED repeat (ompH5clean·r2),
        # so the 28K floor would silently never be cited.
        cell = str(row.get("cell", ""))
        model = ("Qwen3.5-9B-65K" if cell.startswith(("ompT65", "ompF"))
                 else "MiMo V2.5" if cell.startswith("ompM")
                 else "Qwen3.5-9B-28K" if cell.startswith("ompH") else "")
        if not model:
            continue
        spread_by_model[model] = max(spread_by_model.get(model, 0.0), float(value))
    rep_spread = None

    # 1. Phạt của việc đi qua tiến trình agent — TÍNH RIÊNG cho từng model.
    # Một dải min…max đi ngang hai model sẽ là con số vô nghĩa: đó là so hai
    # condition khác nhau chứ không phải một hiệu ứng.
    for model, rows_m in sorted(clean_by_model.items()):
        deltas = sorted(r["delta"] for r in rows_m)
        ds = sorted({r["dataset_label"].split(" (")[0] for r in rows_m})
        excl0 = sum(1 for r in rows_m if r["ci95_high"] < 0 or r["ci95_low"] > 0)
        trend = "mọi phép so đều giảm điểm" if deltas[-1] < 0 else "chưa thấy mức giảm nhất quán"
        claims.append({
            "id": f"penalty:{model}",
            "title": f"{model}: kết quả khi dùng scaffold sạch",
            "points": [
                {"label": "Kết quả", "text": (
                    f"Δ từ {vi_delta(deltas[0])} đến {vi_delta(deltas[-1])} điểm trên "
                    f"{vi_int(len(ds))} tập; {trend}."
                )},
                {"label": "Độ tin cậy", "text": (
                    f"CI 95% không chứa 0 ở {excl0}/{len(rows_m)} phép so."
                )},
                {"label": "Cỡ mẫu", "text": f"n nhỏ nhất là {vi_int(min(r['n'] for r in rows_m))}."},
            ],
        })

    # 1c. WHICH configuration costs, per model. The sentence the 28K factorial
    # supported — "the range does not move with the configuration" — is false on 65K,
    # where the minimal scaffold cell is indistinguishable from arm A and the
    # tool+persona cell is clearly worse. So the claim is derived rather than asserted:
    # a model whose clean arms on ONE dataset straddle 0 gets a claim naming the arms,
    # and a model whose arms all sit on one side of 0 does not.
    for model, rows_m in sorted(clean_by_model.items()):
        rep_spread = spread_by_model.get(model)
        by_ds: dict[str, list[dict]] = {}
        for r in rows_m:
            by_ds.setdefault(r["dataset_label"].split(" (")[0], []).append(r)
        for ds_label, group in sorted(by_ds.items()):
            clear = [r for r in group if r["ci95_high"] < 0 or r["ci95_low"] > 0]
            flat = [r for r in group if r not in clear]
            if not (clear and flat):
                continue
            flat.sort(key=lambda r: r["delta"], reverse=True)
            clear.sort(key=lambda r: r["delta"])
            claims.append({
                "id": f"configuration:{model}:{ds_label}",
                "title": f"{model} trên {ds_label}: hiệu ứng thay đổi theo cấu hình",
                "points": [
                    {"label": f"Arm {flat[0]['arm']}", "text": (
                        f"Δ {vi_delta(flat[0]['delta'])} điểm; CI 95% từ "
                        f"{vi_delta(flat[0]['ci95_low'])} đến {vi_delta(flat[0]['ci95_high'])}, "
                        "còn chứa 0."
                    )},
                    {"label": f"Arm {clear[0]['arm']}", "text": (
                        f"Δ {vi_delta(clear[0]['delta'])} điểm; CI 95% từ "
                        f"{vi_delta(clear[0]['ci95_low'])} đến {vi_delta(clear[0]['ci95_high'])}, "
                        "không chứa 0."
                    )},
                    {"label": "Cách đọc", "text": (
                        "Hai arm khác cấu hình; đối chiếu nhãn của từng arm trong bảng."
                    )},
                ] + ([{"label": "Sàn nhiễu", "text": (
                    f"{vi_num(rep_spread)} điểm; chênh lệch nhỏ hơn mức này chưa thể đọc rõ."
                )}] if rep_spread is not None else []),
            })
            break        # one claim per model: the widest dataset is enough to make it

    # 2. V-Bench: thống kê cục bộ gợi ý nhẹ hơn thực tế 3,4 lần
    models_seen = []
    for model in sorted({r.get("model", "") for r in ladder}):
        vb_pair = [r for r in ladder if r["dataset"] == "vbench_agentic" and r.get("model") == model]
        v_a = next((r for r in vb_pair if r["role"] == "baseline"), None)
        v_b = next((r for r in vb_pair if r["role"] == "harness"), None)
        # The server grade exists only where a snapshot was recorded; without it
        # the locally computable number is validity alone, which understates the
        # damage several-fold — so the claim is skipped, never approximated.
        if not (v_a and v_b and v_b.get("server_score") is not None):
            continue
        models_seen.append(model)
        vdelta = v_b["server_score"] - v_a["server_score"]
        ratio = abs(vdelta / v_b["delta"]) if v_b["delta"] else float("nan")
        claims.append({
            "id": f"vbench:{model}",
            "title": f"{model}: điểm máy chủ giảm nhiều hơn schema validity",
            "points": [
                {"label": "Schema validity", "text": (
                    f"{vi_num(v_a['arm_b'])}% → {vi_num(v_b['arm_b'])}%; "
                    f"Δ {vi_delta(v_b['delta'])} điểm."
                )},
                {"label": "Điểm máy chủ", "text": (
                    f"{vi_num(v_a['server_score'])}% → {vi_num(v_b['server_score'])}%; "
                    f"Δ {vi_delta(vdelta)} điểm."
                )},
                {"label": "Cách đọc", "text": (
                    f"Mức giảm điểm máy chủ lớn gấp {vi_num(ratio, 1)} lần validity; "
                    "lời gọi hợp lệ vẫn có thể chọn sai hàm hoặc tham số."
                    if v_b["delta"] else
                    "Không thể so tỷ lệ khi Δ validity bằng 0."
                )},
                {"label": "Cỡ mẫu", "text": f"{vi_int(v_b['n'])} câu gọi hàm."},
            ],
        })

    # 3. Mức sàn nhiễu: phạt thì vững, còn tương tác persona x tool thì không
    spreads = {r["cell"]: r["cell_spread"] for r in reps if r.get("cell_spread") is not None}
    means = {r["cell"]: r["cell_mean"] for r in reps if r.get("cell_mean") is not None}
    if {"ompH5clean", "ompH8clean"} <= set(means) and spreads:
        noise = max(spreads.values())
        contrast = means["ompH8clean"] - means["ompH5clean"]
        # Ngưỡng nhiễu chỉ đo được trên legal-MC, nên chỉ Δ của legal-MC mới đem ra so
        # The repeats that produced those spreads are the Qwen factorial cells, so
        # only that model's clean legal-MC deltas are comparable against them.
        noise_model = ARM_MODEL["H5"]
        matched = [r for r in clean_by_model.get(noise_model, [])
                   if r["dataset"] == "legal_mc"]
        if matched:
            worst = min(abs(r["delta"]) for r in matched)
            best = max(abs(r["delta"]) for r in matched)
            claims.append({
                "id": "noise",
                "title": "Mức giảm scaffold vượt nhiễu; tương tác chưa tách được",
                "points": [
                    {"label": "Dao động khi lặp", "text": (
                        f"{vi_num(min(spreads.values()))}–{vi_num(noise)} điểm qua 2–3 lượt "
                        "trên legal-MC ở temperature 0."
                    )},
                    {"label": "Mức giảm scaffold", "text": (
                        f"{vi_num(worst)}–{vi_num(best)} điểm, lớn hơn mức nhiễu "
                        f"{vi_num(worst / noise, 1)}–{vi_num(best / noise, 1)} lần."
                    )},
                    {"label": "Persona và công cụ", "text": (
                        f"Δ {vi_delta(contrast)} điểm, nhỏ hơn dao động trong một ô; "
                        "chưa thể kết luận về tương tác."
                    )},
                ],
            })

    # 4. Vỏ câu trả lời: thuộc cấu hình, không thuộc omp
    w = {(m["arm"], m["dataset"]): m for m in secondary}
    leak_r = [k for k in w if k[0] == "H2"]
    clean_r = [k for k in w if k[0] == "H5"]
    if leak_r and clean_r:
        ds = sorted({k[1] for k in leak_r} & {k[1] for k in clean_r})
        if ds:
            d = ds[0]
            a, b = w[("H2", d)], w[("H5", d)]
            label = a["dataset_label"].split(" (")[0]
            claims.append({
                "id": "wrapper",
                "title": "Rò cấu hình giải thích phần lớn chi phí lớp bọc",
                "points": [
                    {"label": "Sau khi bóc lớp bọc", "text": (
                        f"{label}, n={vi_int(a['n'])}: cấu hình bị rò tăng "
                        f"{vi_delta(a['wrapper_cost'])} điểm; cấu hình sạch tăng "
                        f"{vi_delta(b['wrapper_cost'])} điểm."
                    )},
                    {"label": "Nguyên nhân", "text": (
                        "PI_CODING_AGENT_DIR không cô lập được cấu hình; omp vẫn nạp "
                        "~/.omp/agent/APPEND_SYSTEM.md."
                    )},
                ],
            })

    # 5. Hai cơ chế chi phí là hai loại tiền khác nhau
    def probe(arm: str, field: str) -> float | None:
        for r in speed_rows:
            if r.get("arm") == arm and r.get("side") == "omp" and r.get("n") == "24":
                return float(r[field])
        return None

    leak = tools = None
    if all(probe(a, "prompt_tok_per_item") is not None for a in ("H5", "H4")):
        leak = {"tok": probe("H4", "prompt_tok_per_item") - probe("H5", "prompt_tok_per_item"),
                "s": probe("H4", "overhead_s_per_item") - probe("H5", "overhead_s_per_item"),
                "out_a": probe("H5", "completion_tok_per_item"),
                "out_b": probe("H4", "completion_tok_per_item")}
    if all(probe(a, "prompt_tok_per_item") is not None for a in ("H4", "H3")):
        tools = {"tok": probe("H3", "prompt_tok_per_item") - probe("H4", "prompt_tok_per_item"),
                 "s": probe("H3", "overhead_s_per_item") - probe("H4", "overhead_s_per_item")}
    if leak and tools and leak["out_a"] and leak["out_b"]:
        completion_ratio = leak["out_b"] / leak["out_a"]
        claims.append({
            "id": "cost",
            "title": "Rò cấu hình và menu công cụ tạo hai loại chi phí",
            "points": [
                {"label": "Rò cấu hình", "text": (
                    f"{vi_delta(leak['tok'], 0)} prompt token và {vi_delta(leak['s'])} giây mỗi câu; "
                    f"completion token tăng từ {vi_int(leak['out_a'])} lên {vi_int(leak['out_b'])} "
                    f"gần {vi_num(completion_ratio, 0)} lần."
                )},
                {"label": "Menu công cụ", "text": (
                    f"{vi_delta(tools['tok'], 0)} prompt token và {vi_delta(tools['s'])} giây mỗi câu."
                )},
                {"label": "Hàm ý", "text": (
                    "Muốn giảm độ trễ, rút gọn hướng dẫn tạo câu trả lời dài trước khi bỏ công cụ."
                )},
            ],
        })

    # Bảng so sánh trực tiếp "không dùng harness" vs "dùng harness", mỗi tập một
    # dòng: lấy cấu hình sạch làm đại diện (H5, tức trung tính × không công cụ).
    comparison = []
    for r in ladder:
        if r["role"] != "baseline" or r["dataset"] == "vbench_agentic":
            continue
        rep = REPRESENTATIVE.get(r.get("model", ""))
        arm_b = next((x for x in ladder if x["role"] == "harness" and x["dataset"] == r["dataset"]
                      and x["arm"] == rep), None)
        if arm_b is None:
            continue
        comparison.append({
            "model": r.get("model", ""),
            "dataset": r["dataset"], "dataset_label": r["dataset_label"], "metric": r["metric"],
            "n": r["n"], "no_harness": round(r["arm_a"], 2), "with_harness": round(arm_b["arm_b"], 2),
            "delta": round(arm_b["delta"], 2),
            # Trống/unparseable của mỗi phía (1.1): số chữ cái trích được.
            # Ngữ nghĩa theo metric — accuracy/EM mới hiện ở trang.
            "a_blanks": r.get("blanks", ""), "b_blanks": arm_b.get("blanks", ""),
        })
        # V-Bench MC: a SECOND row carrying the real accuracy, so the agreement
        # row above can never be the only number a reader sees for this cell.
        # MiMo's two rows disagree in SIGN (-22.39 agreement vs +2.13 accuracy),
        # which is precisely why one row without the other misleads.
        server_a = (r.get("arm_a_server_mc_score") if r.get("arm_a_server_mc_score") is not None
                      else r.get("server_mc_score"))
        if (server_a is not None and arm_b.get("server_mc_score") is not None):
            comparison.append({
                "model": r.get("model", ""),
                "dataset": "vbench_mc_accuracy",
                "dataset_label": "V-Bench MC 12 domain — điểm máy chủ",
                "metric": "server_accuracy", "n": arm_b.get("server_mc_total", r["server_mc_total"]),
                "no_harness": round(server_a, 2),
                "with_harness": round(arm_b["server_mc_score"], 2),
                "delta": round(arm_b["server_mc_score"] - server_a, 2),
                # `a_blanks` is OMITTED, not blanked: the validator treats a blank
                # string as a malformed integer, and an absent key is the honest
                # reading anyway — arm A had no unparsed rows to count. b_blanks
                # IS reported: those items were not submitted and the server scored
                # them wrong, so the reader must see them inside the delta.
                "b_blanks": arm_b.get("blanks", ""),
                "server_scored": True,
            })
    for model in models_seen:
        vb_pair = [r for r in ladder if r["dataset"] == "vbench_agentic" and r.get("model") == model]
        vb = next((r for r in vb_pair if r["role"] == "harness"), None)
        vb_a = next((r for r in vb_pair if r["role"] == "baseline"), None)
        if not (vb and vb_a and vb.get("server_score") is not None):
            continue
        comparison.append({
            "model": model,
            "dataset": "vbench_agentic", "dataset_label": "V-Bench function-calling (điểm máy chủ)",
            # server-scored, no local gold — same caveat as `vbench_mc_accuracy`,
            # so it carries the same metric key rather than the optimistic one.
            "metric": "server_accuracy", "n": vb["n"],
            "no_harness": round(vb_a["server_score"], 2), "with_harness": round(vb["server_score"], 2),
            "delta": round(vb["server_score"] - vb_a["server_score"], 2),
            "a_blanks": vb_a.get("blanks", ""), "b_blanks": vb.get("blanks", ""),
        })
    # Never mixed across models, and an AGREEMENT row never sorts as if it were a
    # quality loss: agreement measures "did the agent change the answer", not
    # "is the answer better", so putting it at the top of a worst-first table
    # would read as a 22-point accuracy drop that does not exist.
    comparison.sort(key=lambda c: (c["model"], c["metric"] == "agreement", c["delta"]))

    if clean_by_model and len(clean_by_model) > 1:
        scored_datasets = sorted({
            r["dataset_label"].split(" (")[0]
            for rs in clean_by_model.values()
            for r in rs
        })
        verdict = (
            f"Tác động của scaffold khác theo model. Dải Δ gồm "
            f"{vi_int(len(scored_datasets))} tập có gold cục bộ; không dùng để xếp hạng."
        )
    elif clean_by_model:
        only = next(iter(clean_by_model))
        verdict = f"Kết quả trên {only} chỉ áp dụng trong các điều kiện được đo."
    else:
        verdict = ""
    return {"verdict": verdict, "claims": claims, "comparison": comparison}


def build_block(results_dir: Path, arms: list = ARMS) -> dict:
    ladder, costs = build_ladder(results_dir, arms)
    speed_rows: list[dict] = []
    for _key, slug, short, label, _card in arms:
        folder = results_dir / slug
        if not folder.exists():
            continue
        rows = arm_speed(folder)
        if rows:
            for row in rows:
                # `arm` here is the REGISTRY name (H1/H2/H5clean…); the probe's
                # own pair id is projected to `side`. Never let the CSV overwrite
                # the arm identity — that is how five arms once displayed as H2.
                speed_rows.append({**row, "arm": short, "label": label})
    secondary = secondary_metrics(results_dir, arms)
    reps = repeatability(results_dir, arms)
    groups = breakdown(results_dir, arms)
    credit = arg_credit(results_dir, arms)
    totals = {
        "items_harness": sum(c["n"] for c in costs),
        "failures": sum(c["failures"] for c in costs),
        "tool_use_items": sum(c["tool_use_items"] for c in costs),
        "net_attempt_items": sum(c["net_attempt_items"] for c in costs),
        "path_escape_items": sum(c["path_escape_items"] for c in costs),
    }
    return {
        "benchmark_name": "Harness arm — mỗi model so với chính nó",
        "date": "2026-09-26 → 2026-10-05",
        "model_id": "Qwen3.5-9B-28K · MiMo V2.5 · Qwen3.5-9B-65K",
        "endpoint": ("Qwen 28K: https://llmapi.iec-uit.com/v1, đã dừng · "
                     "MiMo: https://opencode.ai/zen/go/v1 · "
                     "Qwen 65K: http://llmapi.iec/v1, nội bộ qua VPN"),
        "harness": "omp, Oh My Pi, v18.2.7",
        "condition": ("Prompt giữ nguyên so với arm A của cùng model; seed 42; bộ chấm cố định. "
                      "Arm A gọi trực tiếp ở temperature 0. Proxy ghim temperature 0 cho MiMo và "
                      "Qwen-65K, đồng thời tắt reasoning cho MiMo. Sandbox đặt ngoài repo nên "
                      "AGENTS.md không được nạp. Tham khảo MC-29 và MC-30."),
        "measurement_card": "MC-15…MC-48",
        "measurement_card_hash": measurement_card_hash(),
        "scorer": "extract_answer cho trắc nghiệm; score_reading_eval.py cho EM và char-F1; bộ chấm giữ nguyên",
        "ladder": ladder,
        "secondary_metrics": secondary,
        "repeatability": reps,
        "breakdown": groups,
        "arg_credit": credit,
        # Both spellings present on purpose: a block written before canonical_metric
        # existed carries `agreement_with_arm_A`, and the page must still find its note.
        "metric_note": {**METRIC_NOTE,
                        **{a: METRIC_NOTE[c] for a, c in METRIC_ALIASES.items()
                           if c in METRIC_NOTE}},
        "insight": insight(ladder, secondary, reps, speed_rows),
        "cost": costs,
        "speed": speed_rows,
        "totals": totals,
        "leak": {
            "what": "Tệp ~/.omp/agent/APPEND_SYSTEM.md được nạp vào mọi arm dù đã đặt PI_CODING_AGENT_DIR.",
            "evidence": "capture_scaffold.py xác nhận tệp này xuất hiện trong system prompt.",
            "fix": "Ghi đè HOME bằng thư mục riêng; chỉ tạo agent dir rỗng là chưa đủ.",
            "guard": "Runner hiển thị cảnh báo rò cấu hình trước mỗi lần chạy.",
        },
        "caveat_sections": [
            {
                "title": "Điều kiện chạy",
                "items": [
                    "Các arm H* ở MC-15–MC-21 gồm cả luật trả lời cá nhân bị rò; đọc kèm MC-22, không xem như omp trần.",
                    "Ở n=100, persona và công cụ chưa tách được khi còn rò; xem scaffold sạch ở MC-23.",
                    "Đến MC-28, sandbox trong repo làm omp nạp AGENTS.md gồm 27.501 ký tự. Ablation MiMo thêm 7.003 token mỗi câu; Δ điểm là +0,68.",
                    "Các lần chạy cũ không ghim được temperature và reasoning_effort cho arm B; MiMo được ghim qua proxy.",
                    "Arm 65K đổi endpoint sau 1.275 câu đầu vì lỗi chứng chỉ; 2.866 câu còn lại dùng endpoint nội bộ.",
                    "T65 gốc có prompt 690 ký tự, hai lần lặp có 745; không gộp vì cấu hình gốc chưa xác định.",
                ],
            },
            {
                "title": "Dữ liệu và metric",
                "items": [
                    "cacheRead của gateway IEC tích lũy theo thời gian và làm ledger phình token khoảng 8 lần; dùng capture_scaffold.py để kiểm tra request.",
                    "temperature 0 vẫn đổi đáp án ở 13/20 item trong MC-18; Δ phản ánh cả dao động giữa lần chạy.",
                    "Metric phụ bóc lớp bọc chỉ dùng để quy nguyên nhân; điểm chính vẫn chấm câu trả lời nguyên văn.",
                    "Hash arm A ghi measurement card trước các cập nhật được thêm sau khi chấm.",
                    "agreement đo tỉ lệ giữ nguyên đáp án, không đo độ đúng. MiMo giảm 22,39 điểm agreement nhưng tăng 2,13 điểm accuracy.",
                    "valid_rate chỉ kiểm tra schema; MC-28 ghi Δ validity −2,60 và Δ điểm server −8,90 do lỗi tham số.",
                ],
            },
            {
                "title": "Cỡ mẫu và độ tin cậy",
                "items": [
                    "Bảng speed chỉ so n=24 và workers=4; cost probe H2 có n=40 nên không cùng tập ở MC-25.",
                    "Sàn nhiễu 65K dựa trên hai lượt lặp, còn 28K dựa trên ba; chênh lệch nhỏ hơn sàn chưa thể đọc rõ.",
                    "F5, F7, F8 và T65r2/T65r3 chỉ đo legal-MC với n=146; không suy rộng thành kết quả trên 58 môn.",
                ],
            },
            {
                "title": "Phạm vi nghiên cứu",
                "items": [
                    "Calibration MC-44 đo độ tin cậy theo môn, không phải phép so ghép cặp; xem kết quả ở /benchmark.",
                ],
            },
        ],
        "sources": {
            "runner": "code_benchmark/run_harness_eval.py (run | compare | speed)",
            "capture": "code_benchmark/capture_scaffold.py",
            "report": "report/2026-09-26/report_omp_harness_qwen35.md",
            "docs": "docs/omp-harness-qwen35.md",
        },
    }


# ── static HTML report (offline, no build step) ─────────────────────────
def render_html(block: dict) -> str:
    e = html.escape

    def tr(cells: list[str], cls: str = "") -> str:
        klass = f' class="{cls}"' if cls else ""
        return "<tr{}>{}</tr>".format(klass, "".join(f"<td>{c}</td>" for c in cells))

    def server_cell(r: dict) -> str:
        """Server accuracy (a DIFFERENT measurement from `arm_b`), never merged into it."""
        if r.get("server_score") is None:
            return "—"
        return (f'<b title="điểm server {r["server_correct"]}/{r["server_total"]}, khác validity">'
                f'{r["server_score"]:.2f}%</b>')

    ladder_rows = []
    for r in block["ladder"]:
        delta_cls = "neg" if r["delta"] < 0 else "pos"
        f1 = f'{r["char_f1"]:.2f}' if r.get("char_f1") is not None else "—"
        if r["role"] == "baseline":
            ladder_rows.append(tr([
                e(r["label"]), e(r["dataset_label"]), str(r["n"]), e(r["metric"]),
                f'{r["arm_a"]:.2f}%', "—", f1, server_cell(r), "—", "—", "—", "—", e(r["card"] or "—"),
            ], cls="base"))
            continue
        ladder_rows.append(tr([
            e(r["label"]), e(r["dataset_label"]), str(r["n"]), e(r["metric"]),
            f'{r["arm_a"]:.2f}%', f'<b>{r["arm_b"]:.2f}%</b>', f1,
            f'<span class="{delta_cls}">{r["delta"]:+.2f}</span>', server_cell(r),
            f'{r["ci95_low"]:+.2f}..{r["ci95_high"]:+.2f}',
            e(r["mcnemar_p"]), f'{r["both"]}/{r["a_only"]}/{r["b_only"]}/{r["neither"]}',
            e(r["card"] or "—"),
        ]))
    cost_rows = [tr([e(c["label"]), str(c["n"]), str(c["datasets"]),
                    f'{c["wall_s_per_item"]:.2f}s', f'{c["turns_per_item"]:.2f}',
                    str(c["completion_tokens"]), str(c["failures"]), str(c["tool_use_items"]),
                    str(c["net_attempt_items"]), str(c["path_escape_items"])])
                 for c in block["cost"]]
    speed_rows = []
    for s in block.get("speed", []):
        # side is shown first: the pair id in the CSV is what made five arms
        # render as H2 (see arm_speed's docstring).
        speed_rows.append(tr([e(s["arm"]), e(s["side"]), e(s.get("dataset", "")),
                              str(s["n"]), e(s["workers"]),
                              f'{s["wall_p50_s"]}s', f'{s["prompt_tok_per_item"]}',
                              f'{s["completion_tok_per_item"]}',
                              f'{s["total_tok_per_item"]}',
                              "— gốc" if s.get("side") == "direct" else f'+{s["overhead_s_per_item"]}s'],
                             cls="omp" if s.get("side") == "omp" else ""))
    secondary_rows = [tr([e(m["arm"]), e(m["label"]), e(m["dataset_label"]), str(m["n"]),
                          f'{m["em_verbatim"]:.2f}%', f'<b>{m["em_stripped"]:.2f}%</b>',
                          f'<span class="neg">+{m["wrapper_cost"]:.2f}</span>'
                          if m["wrapper_cost"] > 0.5 else f'{m["wrapper_cost"]:+.2f}'])
                     for m in block.get("secondary_metrics", [])]
    ins = block.get("insight", {"verdict": "", "claims": []})
    claim_rows = []
    for claim in ins["claims"]:
        points = claim.get("points") or [{"label": "Tóm tắt", "text": claim.get("body", "")}]
        point_rows = "".join(
            f'<li><b>{e(point["label"])}:</b> {e(point["text"])}</li>'
            for point in points
        )
        claim_rows.append(
            f'<div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px">'
            f'<b>{e(claim["title"])}</b><ul>{point_rows}</ul></div>'
        )
    ins_html = "".join(claim_rows)
    if block.get("caveat_sections"):
        caveat_html = "".join(
            f'<section><h3>{e(section["title"])}</h3><ul>'
            + "".join(f"<li>{e(item)}</li>" for item in section["items"])
            + "</ul></section>"
            for section in block["caveat_sections"]
        )
    else:
        caveat_html = "<ul>" + "".join(
            f"<li>{e(item)}</li>" for item in block.get("caveats", [])
        ) + "</ul>"
    leak_html = "".join(
        f'<li><b>{e(label)}:</b> {e(block["leak"][field])}</li>'
        for label, field in (("Hiện tượng", "what"), ("Bằng chứng", "evidence"),
                             ("Khắc phục", "fix"), ("Kiểm soát", "guard"))
    )
    t = block["totals"]
    return f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harness arm — Qwen3.5-9B-28K qua omp</title>
<style>
 body{{font-family:'Segoe UI',system-ui,sans-serif;margin:0;padding:32px;background:#f8fafc;color:#0f172a}}
 h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:32px 0 8px}}
 .sub{{color:#64748b;font-size:13px;margin-bottom:20px}}
 table{{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;overflow:hidden;
        box-shadow:0 1px 3px rgba(0,0,0,.08);font-size:13px}}
 th{{background:#0f172a;color:#fff;text-align:left;padding:9px 10px;font-weight:600}}
 td{{padding:8px 10px;border-top:1px solid #e2e8f0;vertical-align:top}}
 tr:nth-child(even) td{{background:#f8fafc}}
 tr.base td{{color:#475569;font-style:italic}}
 tr.omp td{{background:#fff7ed}}
 .neg{{color:#b91c1c;font-weight:600}} .pos{{color:#15803d;font-weight:600}}
 .box{{background:#fff;border-left:4px solid #f59e0b;padding:14px 16px;border-radius:8px;
       margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
 .box b{{color:#b45309}} code{{background:#f1f5f9;padding:1px 5px;border-radius:4px;font-size:12px}}
 ul{{font-size:13px;color:#334155;line-height:1.7}} .tally{{font-size:13px;color:#475569;margin-top:8px}}
</style></head><body>
<h1>{e(block["benchmark_name"])}</h1>
<div class="sub">model <b>{e(block["model_id"])}</b> @ {e(block["endpoint"])} ·
 harness <b>{e(block["harness"])}</b> · {e(block["condition"])} ·
 card {e(block["measurement_card"])} · hash <code>{e(block["measurement_card_hash"][:16])}…</code></div>

<div class="box"><b>Rò cấu hình</b><ul>{leak_html}</ul></div>

<h2>Nhận xét chính</h2>
<ul><li><b>{e(ins["verdict"])}</b></li></ul>
<div style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))">{ins_html}</div>

<h2>Bảng chính — paired, cùng tập item</h2>
<table><tr><th>Arm</th><th>Tập</th><th>n</th><th>Metric</th><th>Arm A</th><th>Arm B</th>
<th>char-F1</th><th>Δ</th><th>Server</th><th>CI 95%</th><th>p</th><th>both/A-only/B-only/neither</th><th>Card</th></tr>
{"".join(ladder_rows)}</table>
<p class="sub"><b>Server</b> = accuracy thật từ vbench.ai, khác hẳn validity ở tập V-Bench: ở
function-calling hai thứ lệch nhau <b>gấp 3,4 lần</b> (validity −2,60đ, accuracy −8,90đ) ⇒ phần lớn
lỗi là <b>gọi đúng hàm sai tham số</b>. Mẫu số 1.000 (26 dòng invalid không nộp được tính sai).</p>
<div class="tally">Tổng item harness đo: {t["items_harness"]} · lỗi {t["failures"]} ·
 item dùng tool {t["tool_use_items"]} · gọi mạng {t["net_attempt_items"]} ·
 trốn sandbox {t["path_escape_items"]} (0 lần thành công)</div>

<h2>Chi phí theo arm (gộp mọi tập, từ ledger per-item)</h2>
<table><tr><th>Arm</th><th>item</th><th>tập</th><th>wall/item</th><th>lượt/item</th>
<th>completion tok</th><th>lỗi</th><th>dùng tool</th><th>gọi mạng</th><th>trốn sandbox</th></tr>
{"".join(cost_rows)}</table>

<h2>Cost probe — cặp trực tiếp vs cùng item trong omp (speed_summary_*.csv)</h2>
<p class="sub">Mỗi tập có hai dòng: <b>direct</b> = lời gọi HTTP của arm A, <b>omp</b> = cùng item đó qua
agent. <code>prompt tok</code> của dòng omp <b>đã bao gồm</b> system prompt + tool schemas.
<b>Không dùng <code>input + cacheRead</code> làm kích thước request</b> — bộ đếm cache của gateway
IEC tích luỹ, làm MC-19 phình ~8× (xem <code>capture_scaffold.py</code>).</p>
<table><tr><th>Arm</th><th>Bên</th><th>Tập</th><th>n</th><th>workers</th><th>wall p50</th>
<th>prompt tok</th><th>completion tok</th><th>tổng tok</th><th>overhead/item</th></tr>
{"".join(speed_rows) or "<tr><td colspan=10>chưa có cost probe</td></tr>"}</table>
<p class="sub">Chỉ các ô <b>n=24, workers=4</b> mới so sánh được với nhau (ô H2 của cost probe là
n=40 — khác subset, MC-25). Tách cơ chế: rò <code>APPEND_SYSTEM.md</code> = <b>+140 prompt tok</b>
nhưng <b>+4,00s</b> overhead và completion tok ×117; tool menu = <b>+4.737 prompt tok</b> mà
<b>≈0</b> độ trễ.</p>

<h2>Metric phụ — EM nguyên văn vs EM sau khi cắt vỏ (KHÔNG thay số chính)</h2>
<p class="sub">Cùng một câu trả lời, chấm hai lần: nguyên văn (đúng cách arm A được chấm) và sau khi
bóc vỏ (<code>**</code>, nhãn <code>Đáp án:</code>, block code, dòng hỏi lại) bằng <b>đúng</b> scorer
đóng băng. Chênh lệch = phần <i>đúng nội dung nhưng bị chấm 0</i>. Câu sai vẫn sai.</p>
<table><tr><th>Arm</th><th>Cấu hình</th><th>Tập</th><th>n</th><th>EM nguyên văn</th>
<th>EM sau cắt vỏ</th><th>Giá của vỏ</th></tr>
{"".join(secondary_rows) or "<tr><td colspan=7>chưa có metric phụ</td></tr>"}</table>
<p class="sub">Arm sạch (H5) cắt vỏ được <b>+0,00</b> ở cả hai tập: câu trả lời của nó vốn đã trần.
Toàn bộ chi phí vỏ nằm ở arm bị rò cấu hình — cơ chế MC-22, giờ đã có số.</p>

<h2>Giới hạn khi diễn giải</h2>
{caveat_html}
<p class="sub">Nguồn: {e(block["sources"]["report"])} · {e(block["sources"]["docs"])} ·
 scorer {e(block["scorer"])}</p>
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Persist the harness-arm results for display.")
    ap.add_argument("--dashboard", type=Path, default=DASHBOARD)
    ap.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    ap.add_argument("--html-out", type=Path, default=HTML_OUT)
    ap.add_argument("--no-html", action="store_true")
    args = ap.parse_args()

    block = build_block(args.results_dir)
    args.html_out.write_text(render_html(block), encoding="utf-8")
    print(f"wrote {args.html_out}")

    if not args.dashboard.exists():
        raise SystemExit(f"Error: {args.dashboard} not found — refusing to create a blob "
                         "with only the harness block")
    blob = json.loads(args.dashboard.read_text(encoding="utf-8"))
    before = {k: v for k, v in blob.items() if k != "harness"}
    blob["harness"] = block
    args.dashboard.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    after = {k: v for k, v in json.loads(args.dashboard.read_text(encoding="utf-8")).items()
             if k != "harness"}
    if after != before:
        raise SystemExit("Error: patch touched keys outside 'harness' — restoring is manual; "
                         "check the diff before committing")
    print(f"patched {args.dashboard} [.harness] — {len(block['ladder'])} paired rows, "
          f"{len(block['cost'])} arms with cost, {len(block['speed'])} speed rows")
    print(f"  measurement_card_hash={block['measurement_card_hash']}")


if __name__ == "__main__":
    main()
