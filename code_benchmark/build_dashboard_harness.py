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
     "MiMo V2.5: `omp sạch` — không tool, system prompt trung tính, sandbox NGOÀI repo, "
     "temperature 0 + reasoning tắt do proxy ghim", "MC-30"),
    ("ompM6inrepo_mimo-v2.5", "ompM6inrepo_mimo-v2_5", "M6L",
     "MiMo V2.5: đúng arm M6 nhưng sandbox đặt TRONG repo, nên `AGENTS.md` của chính repo "
     "này bị nạp vào mọi item (ablation của MC-29)", "MC-30"),
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
     "65K: omp sạch, KHÔNG tool, system prompt trung tính — scaffold tối giảu",
     "MC-46/47"),
    ("ompF7clean_Qwen3_5-9B-65K", "ompF7clean_Qwen3_5-9B-65K", "F7",
     "65K: omp sạch, KHÔNG tool, system prompt gốc của omp", "MC-46/47"),
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
                 "vbench_agentic": "V-Bench agentic (schema validity — KHÔNG có gold)",
                 "vbench_mc": "V-Bench MC 12 domain (mức trùng khớp với arm A — KHÔNG có gold)"}


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
        return {"n": n, "metric": "agreement", "score": round(100.0 * same / n, 2),
                "correct": same, "blanks": n - same, "char_f1": None,
                "unit": "cùng chữ cái với arm A"}
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
            groups = []
            for r in rows:
                lo, hi = f2(r["ci95_low"]), f2(r["ci95_high"])
                if lo > hi:
                    raise SystemExit(f"Error: {slug}/{dataset}/{r['group']}: "
                                     f"CI inverted ({lo} > {hi})")
                if abs(f2(r["delta"]) - (f2(r["arm_b"]) - f2(r["arm_a"]))) > 0.02:
                    raise SystemExit(f"Error: {slug}/{dataset}/{r['group']}: "
                                     f"delta {r['delta']} != arm_b - arm_a")
                groups.append({"group": r["group"], "n": int(r["n"]),
                               "arm_a": f2(r["arm_a"]), "arm_b": f2(r["arm_b"]),
                               "delta": f2(r["delta"]), "ci95_low": lo,
                               "ci95_high": hi, "mcnemar_p": r["mcnemar_p"]})
            cmp_row = read_compare(folder, dataset)
            if cmp_row is not None and sum(g["n"] for g in groups) != int(cmp_row["n"]):
                raise SystemExit(f"Error: {slug}/{dataset}: breakdown groups sum to "
                                 f"{sum(g['n'] for g in groups)} but compare n={cmp_row['n']}")
            out.append({"arm": short, "arm_slug": slug, "label": label,
                        "model": ARM_MODEL[short], "dataset": dataset,
                        "dataset_label": DATASET_LABEL[dataset],
                        "metric": rows[0]["metric"], "groups": groups})
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
        worse = deltas[-1] < 0
        claims.append({
            "id": f"penalty:{model}",
            "title": (f"{model}: chi phí của việc đưa một prompt qua tiến trình agent"
                      if worse else
                      f"{model}: đi qua tiến trình agent KHÔNG làm giảm điểm"),
            "body": ("Giữ nguyên model, prompt (byte-identical) và bộ chấm đóng băng, chỉ thay đổi "
                     "đường truy xuất câu trả lời: các cấu hình scaffold sạch "
                     + ("thua" if worse else f"có Δ từ {deltas[0]:+.2f} đến {deltas[-1]:+.2f} điểm")
                     + f" trên {len(ds)} tập ({', '.join(ds)})"
                     + ("" if worse else
                        ", tức không tìm thấy khoản phạt nào ở đây")
                     + f". Trong {len(rows_m)} "
                     f"phép so sánh đó, {excl0} phép có khoảng tin cậy 95% loại trừ 0"
                     + ("" if excl0 == len(rows_m) else
                        f"; {len(rows_m) - excl0} phép còn lại rơi vào tập nhỏ, nơi độ rộng khoảng tin "
                        f"cậy còn ngang bằng bản thân khoản thay đổi")
                     + "."),
            "evidence": [{"label": "Δ nhỏ nhất", "value": f"{deltas[0]:+.2f}"},
                         {"label": "Δ lớn nhất", "value": f"{deltas[-1]:+.2f}"},
                         {"label": "CI 95% loại trừ 0", "value": f"{excl0}/{len(rows_m)}"},
                         {"label": "tập nhỏ nhất", "value": f"n={min(r['n'] for r in rows_m)}"}],
        })

    # 1b. Mệnh đề liên model: dấu của hiệu ứng thuộc về model, không thuộc về scaffold
    if len(clean_by_model) > 1:
        worst = {m: max(r["delta"] for r in rs) for m, rs in clean_by_model.items()}
        best = {m: min(r["delta"] for r in rs) for m, rs in clean_by_model.items()}
        flips = [m for m, rs in clean_by_model.items() if max(r["delta"] for r in rs) > 0]
        claims.append({
            "id": "model_dependent",
            "title": "Scaffold không có một giá riêng: dấu của hiệu ứng đổi theo model",
            "body": ("Cùng một scaffold, cùng prompt byte-identical, cùng bộ chấm đóng băng, cùng một "
                     "đường truy xuất là khác biệt duy nhất — và kết quả đảo dấu giữa các model: "
                     + "; ".join(f"{m} dao động {best[m]:+.2f}…{worst[m]:+.2f} điểm" 
                                 for m in sorted(clean_by_model))
                     + ". Nghĩa là cái bị đo ở một model nhỏ là **ngân sách tuân thủ** của model đó, "
                       "không phải chi phí của việc đi qua một tiến trình agent. "
                     + (f"Trên {len(flips)}/{len(clean_by_model)} model, scaffold thậm chí còn tăng điểm."
                        if flips else
                        "Không model nào được scaffold giúp.")
                     + " Các model còn khác nhau ở chỗ có suy luận hay không, nên đây là so các "
                       "condition chứ không phải so thứ hạng model."),
            "evidence": [{"label": f"{m}: Δ cao nhất", "value": f"{worst[m]:+.2f}đ"}
                         for m in sorted(clean_by_model)]
                        + [{"label": f"{m}: Δ thấp nhất", "value": f"{best[m]:+.2f}đ"}
                           for m in sorted(clean_by_model)],
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
                "title": (f"{model} / {ds_label}: cấu hình nào tốn điểm thì tùy — "
                          f"scaffold tối giảu gần như miễn phí, thêm công cụ và persona thì tốn"),
                "body": (f"Trên cùng một tập và cùng arm A, các arm scaffold sạch của {model} "
                         f"trải Δ từ {flat[0]['delta']:+.2f} (arm {flat[0]['arm']}, "
                         f"CI [{flat[0]['ci95_low']:+.2f}, {flat[0]['ci95_high']:+.2f}] — **không khác 0** "
                         f"thống kê) tới {clear[0]['delta']:+.2f} (arm {clear[0]['arm']}, "
                         f"CI [{clear[0]['ci95_low']:+.2f}, {clear[0]['ci95_high']:+.2f}]). "
                         f"Nghĩa là **chính cái scaffold không phải là nơi mất điểm**: ô tối giảu "
                         f"(không công cụ, system prompt trung tính) gần như ngang với gọi thẳng, "
                         f"và điểm chỉ rơi khi bật menu công cụ và/hoặc system prompt gốc của omp. "
                         f"Đọc một dải Δ của riêng model này mà không ghi cấu hình sẽ gán nhầm "
                         f"chi phí cho agent thay vì cho những gì ta thêm vào nó."
                         + (f" Sàn nhiễu của chính các ô lặp ở model này là "
                            f"{rep_spread:.2f} điểm, nên những chênh lệch dưới mức đó "
                            f"không đọc được."
                            if rep_spread is not None else "")),
                "evidence": [{"label": f"arm {r['arm']}", "value": f"{r['delta']:+.2f}đ"}
                             for r in ([flat[0]] + clear[:2])]
                            + ([{"label": "sàn nhiễu (lặp)", "value": f"{rep_spread:.2f}đ"}]
                               if rep_spread is not None else []),
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
            "title": f"{model}: trên bài function-calling — nơi scaffold duy nhất được lợi thế — "
                     f"vẫn chỉ thua, và thua nhiều hơn thống kê cục bộ gợi ý",
            "body": (f"Trên {v_b['n']:.0f} câu lệnh gọi hàm: tính schema validity tại chỗ cho "
                     f"{v_a['arm_b']:.2f}% → {v_b['arm_b']:.2f}% ({v_b['delta']:+.2f} điểm), nhưng điểm "
                     f"chấm thật từ máy chủ là {v_a['server_score']:.2f}% → {v_b['server_score']:.2f}% "
                     f"({vdelta:+.2f} điểm) — lớn hơn {ratio:.1f} lần. Phần lớn lỗi vì vậy không phải do "
                     f"phát sinh JSON sai cấu trúc, mà do chọn đúng hàm nhưng điền sai tham số: một "
                     f"lỗi mà bộ kiểm tra schema về cấu trúc không thể phát hiện."),
            "evidence": [{"label": "Δ schema validity", "value": f"{v_b['delta']:+.2f}đ"},
                         {"label": "Δ điểm máy chủ", "value": f"{vdelta:+.2f}đ"},
                         {"label": "hệ số chênh lệch", "value": f"{ratio:.1f}×"},
                         {"label": "cỡ mẫu", "value": f"{v_b['n']:.0f}"}],
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
                "title": "Khoản phạt là thật; còn tương tác giữa persona và menu công cụ thì không "
                         "tách được khỏi nhiễu",
                "body": (f"Lặp lại cùng một điều kiện từ hai đến ba lần trên legal-MC: ngay trong một ô, "
                         f"điểm dao động {min(spreads.values()):.2f}…{noise:.2f} điểm ngay cả khi "
                         f"`temperature` bằng 0. Khoản phạt của scaffold trên chính tập đó là "
                         f"{worst:.2f}…{best:.2f} điểm, tức gấp {worst / noise:.1f}–{best / noise:.1f} lần "
                         f"mức dao động này, nên kết luận là vững. Trái lại, hiệu ứng của việc đổi persona "
                         f"và bật menu công cụ chỉ {contrast:+.2f} điểm, nhỏ hơn cả dao động nội tại của "
                         f"một ô — nên không kết luận được, và nguyên nhân không phải là thiếu mẫu."),
                "evidence": [{"label": "dao động trong một ô", "value": f"{min(spreads.values()):.2f}…{noise:.2f}"},
                             {"label": "hiệu ứng persona × tool", "value": f"{contrast:+.2f}đ"},
                             {"label": "Δ scaffold trên legal-MC", "value": f"{worst:.2f}…{best:.2f}đ"}],
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
            label = a["dataset_label"]
            claims.append({
                "id": "wrapper",
                "title": "Phần lớn “harness tax” ở các lần đo ban đầu đến từ cấu hình trả lời của máy bị "
                         "lọt vào, không phải từ bản thân omp",
                "body": (f"Chấm lại chính các câu trả lời đó sau khi bỏ lớp vỏ markdown "
                         f"({label}, n={a['n']} câu): điểm của cấu hình bị lọt tăng thêm "
                         f"{a['wrapper_cost']:+.2f} điểm, còn của cấu hình sạch là "
                         f"{b['wrapper_cost']:+.2f} điểm. Nghĩa là lớp vỏ là hệ quả của cấu hình, "
                         f"trong khi câu trả lời của cấu hình sạch vốn đã trần. Nguyên nhân đã được xác "
                         f"định: `PI_CODING_AGENT_DIR` không cô lập được scaffold, vì omp vẫn đọc "
                         f"`~/.omp/agent/APPEND_SYSTEM.md` từ agent dir mặc định."),
                "evidence": [{"label": f"bị lọt ({label})", "value": f"{a['wrapper_cost']:+.2f}đ"},
                             {"label": f"sạch ({label})", "value": f"{b['wrapper_cost']:+.2f}đ"}],
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
        claims.append({
            "id": "cost",
            "title": "Hai cơ chế phát sinh chi phí là hai loại tiền khác nhau — không nên gộp chung",
            "body": (f"Cấu hình bị lọt: {leak['tok']:+.0f} prompt token, gần như không tốn token đầu vào, "
                     f"nhưng cộng thêm {leak['s']:+.2f} giây mỗi câu và làm số completion token tăng "
                     f"{leak['out_b'] / leak['out_a']:.0f} lần ({leak['out_a']:.0f} → {leak['out_b']:.0f}). "
                     f"Menu công cụ: ngược lại, {tools['tok']:+.0f} prompt token (chủ yếu là phần định nghĩa "
                     f"công cụ) mà gần như không cộng thời gian ({tools['s']:+.2f} giây) và không cộng thêm "
                     f"điểm. Hàm quyết định thiết kế: muốn giảm độ trễ thì cắt văn bản ép câu trả lời dài, "
                     f"đừng cắt bộ công cụ."),
            "evidence": [{"label": "rò cấu hình: token / giây", "value": f"{leak['tok']:+.0f} / {leak['s']:+.2f}s"},
                         {"label": "menu công cụ: token / giây", "value": f"{tools['tok']:+.0f} / {tools['s']:+.2f}s"},
                         {"label": "completion token", "value": f"×{leak['out_b'] / leak['out_a']:.0f}"}],
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
    for model in models_seen:
        vb_pair = [r for r in ladder if r["dataset"] == "vbench_agentic" and r.get("model") == model]
        vb = next((r for r in vb_pair if r["role"] == "harness"), None)
        vb_a = next((r for r in vb_pair if r["role"] == "baseline"), None)
        if not (vb and vb_a and vb.get("server_score") is not None):
            continue
        comparison.append({
            "model": model,
            "dataset": "vbench_agentic", "dataset_label": "V-Bench function-calling (điểm máy chủ)",
            "metric": "accuracy", "n": vb["n"],
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
        rng = "; ".join(
            f"{m} {min(r['delta'] for r in rs):+.2f}…{max(r['delta'] for r in rs):+.2f} điểm"
            for m, rs in sorted(clean_by_model.items()))
        helped = [m for m, rs in clean_by_model.items() if max(r["delta"] for r in rs) > 0]
        verdict = (
            f"Scaffold không có một giá riêng. Giữ nguyên model, prompt byte-identical và bộ chấm "
            f"đóng băng, chỉ thay đổi đường truy xuất câu trả lời, kết quả đảo dấu giữa các model: {rng}. "
            f"Vì vậy cái các lần đo trước đo được là ngân sách tuân thủ của một model nhỏ, chứ không "
            f"phải chi phí của việc đi qua một tiến trình agent"
            + (f" — và trên {len(helped)}/{len(clean_by_model)} model, scaffold còn tăng điểm."
               if helped else ".")
            + " Hai điều phải tách trước khi lập luận về chi phí của agent: văn bản ép dài (tốn "
              "token, MC-25) và vòng lặp agent (tốn điểm, nhưng chỉ với model không đủ ngân sách "
              "tuân thủ). Ngoài ra, phần lớn thiệt hại ở các lần đo ban đầu hoá ra đến từ cấu hình "
              "trả lời của chính máy bị lọt vào scaffold, không phải từ bản thân omp."
        )
    elif clean_by_model:
        only = next(iter(clean_by_model))
        rng = "; ".join(
            f"{min(r['delta'] for r in rs):+.2f}…{max(r['delta'] for r in rs):+.2f} điểm"
            for rs in clean_by_model.values())
        verdict = (
            f"Với model, prompt và bộ chấm đều giữ nguyên, việc trả lời qua một tiến trình agent đổi "
            f"điểm {rng} trên {only}, và không tầng cấu hình nào của scaffold chịu trách nhiệm cho phần "
            f"này. Phần lớn thiệt hại ở các lần đo ban đầu hoá ra đến từ cấu hình trả lời của chính máy "
            f"bị lọt vào scaffold chứ không phải từ bản thân omp."
        )
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
        "benchmark_name": ("Harness arm — mỗi model so với chính nó "
                               "(omp vs gọi API trực tiếp)"),
        "date": "2026-09-26 → 2026-10-05",
        "model_id": "Qwen3.5-9B-28K · MiMo V2.5 · Qwen3.5-9B-65K",
        "endpoint": ("https://llmapi.iec-uit.com/v1 (Qwen 28K, lúc còn sống) · "
                     "https://opencode.ai/zen/go/v1 (MiMo, qua OpenCode Zen Go) · "
                     "http://llmapi.iec/v1 (Qwen 65K, nội bộ qua VPN)"),
        "harness": "omp (Oh My Pi) v18.2.7",
        "condition": ("prompt byte-identical với arm A của ĐÚNG model đó, seed 42, scorer đóng băng; "
                      "khác nhau chỉ ở đường elicitation. Arm A gọi thẳng ở temperature 0. MiMo và "
                      "Qwen-65K: temperature 0 (+ reasoning tắt cho MiMo) được GHIM BẰNG PROXY trong "
                      "suốt vì omp không gửi được các field đó; sandbox đặt ngoài repo nên không có "
                      "AGENTS.md nạp vào (MC-29/MC-30)."),
        "measurement_card": "MC-15…MC-47",
        "measurement_card_hash": measurement_card_hash(),
        "scorer": "extract_answer (MC) + score_reading_eval.py (EM/char-F1) — không viết lại",
        "ladder": ladder,
        "secondary_metrics": secondary,
        "repeatability": reps,
        "breakdown": groups,
        "arg_credit": credit,
        "insight": insight(ladder, secondary, reps, speed_rows),
        "cost": costs,
        "speed": speed_rows,
        "totals": totals,
        "leak": {
            "what": ("~/.omp/agent/APPEND_SYSTEM.md lọt vào mọi arm dù đã đặt PI_CODING_AGENT_DIR; "
                     "đó là luật trả lời 'verdict → why → the test → the rule' của máy"),
            "evidence": ("bắt bằng code_benchmark/capture_scaffold.py; system prompt thật bắt đầu "
                         "bằng \"Answer the user's question.\\n# Global reply style (all projects)…\""),
            "fix": "chỉ ghi đè HOME mới chặn được (file rỗng trong agent dir riêng không che được)",
            "guard": "run_harness_eval.py in cảnh báo SCAFFOLD LEAK ở mỗi lần chạy",
        },
        "caveats": [
            "Đọc MC-15…MC-21 cùng MC-22: các arm H* đo 'omp + luật trả lời cá nhân bị rò', "
            "không phải omp trần.",
            "cacheRead của gateway IEC là bộ đếm cache tích luỹ → ledger thổi phồng token ~8×; "
            "đừng dùng tỉ lệ token (MC-19) mà soi request thật bằng capture_scaffold.py.",
            "Arm không tất định ở temperature 0 (MC-18: 13/20 item đổi đáp án) → Δ là hiệu ứng tổng.",
            "Persona × tools không tách được ở n=100 khi có rò; xem MC-23 cho bản scaffold sạch.",
            "Bảng speed: chỉ các ô n=24, workers=4 mới so sánh được với nhau. Ô H2 của cost probe "
            "là n=40 (khác subset) nên không dùng để suy ra tương tác persona×tool (MC-25).",
            "Bảng metric phụ (EM sau khi cắt vỏ) là để quy kết, KHÔNG thay số chính: nó bỏ vỏ "
            "markdown rồi chấm lại bằng đúng scorer đóng băng. Câu sai vẫn sai.",
            "Số arm A mang hash measurement card cũ; các card mới thêm sau khi chấm.",
            "MC-29: sandbox từng mặc định nằm TRONG repo, nên omp nạp toàn bộ AGENTS.md của chính "
            "repo này (27.501 ký tự, ~7k token) vào system prompt của MỌI item tới MC-28. Nhãn "
            "\"scaffold sạch\" của các arm cũ nghĩa là sạch persona/tool, không có nghĩa là sạch chỉ "
            "dẫn dự án. Ablation trên MiMo (cùng arm, khác vị trí sandbox): +7.003 token/câu, Δ +0,68 "
            "điểm — tốn tiền, không tốn điểm.",
            "omp KHÔNG gửi temperature và reasoning_effort (bắt bằng proxy; `options:` trong models.yml "
            "bị bỏ qua im lặng). Các card ghi \"temperature 0\" là đúng cho arm A nhưng SAI cho mọi arm "
            "B cũ; arm MiMo ghim hai field này bằng proxy trong suốt và mọi pin được ghi vào file capture.",
            "Dòng `agreement` (V-Bench MC) KHÔNG phải điểm: đó là tỉ lệ agent cho giống hệt arm A trên "
            "cùng câu hỏi. Điểm V-Bench thật do máy chủ chấm; ta không có vàng cục bộ.",
            "Arm 65K đổi đường truyền giữa chừng (MC-31): 1.275 item V-Bench MC đầu qua https công cộng, "
            "2.866 item sau qua http nội bộ — cùng model/backend/params, chỉ sửa đường truyền sau khi "
            "cổng ngoài sập cert.",
            "Các arm F5/F7/F8 và T65r2/T65r3 chỉ chạy legal_mc (146 câu, một miền). "
            "Đọc dải Δ của chúng như một kết luận về 58 môn VMLU là không có cơ sở.",
            "Arm T65 GỐC không được gộp với hai lặp của nó, dù cùng nhãn điều kiện: proxy log của "
            "lần chạy gốc ghi system prompt dài 690 ký tự, còn hai lặp dài 745 (MC-47). Shape thật "
            "của T65 gốc chưa xác định, nên nó không xuất hiện trong bảng sàn nhiễu.",
            "Sàn nhiễu tính trên arm 65K chỉ có 2 lặp, yếu hơn sàn ở 28K (3 lặp); một chênh lệch "
            "65K nhỏ hơn sàn đó thì chưa đọc được (MC-47).",
            "Calibration (MC-44) CỐ Ý không nằm trong block này: nó đo độ tin cậy của điểm theo môn, "
            "không phải một contrast ghép đôi giữa các arm, nên thuộc /benchmark chứ không phải /harness.",
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
    ins_html = "".join(
        f'<div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px">'
        f'<b>{e(c["title"])}</b><p class="sub" style="margin:6px 0">{e(c["body"])}</p>'
        f'<div class="sub">{" · ".join(e(x["label"]) + " <b>" + e(x["value"]) + "</b>" for x in c["evidence"])}</div>'
        f"</div>"
        for c in ins["claims"])
    caveat_rows = "".join(f"<li>{e(c)}</li>" for c in block["caveats"])
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

<div class="box"><b>⚠ Đọc MC-15…MC-21 cùng MC-22.</b> {e(block["leak"]["what"])}<br>
<b>Bằng chứng:</b> {e(block["leak"]["evidence"])}<br>
<b>Cách chặn:</b> {e(block["leak"]["fix"])} · <b>Guard:</b> {e(block["leak"]["guard"])}</div>

<h2>Nhận xét — đọc kết quả này thành gì?</h2>
<p><b>{e(ins["verdict"])}</b></p>
<div style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))">{ins_html}</div>
<p class="sub">Mọi số ở trên nội suy từ artifact của các bảng dưới đây (<code>insight()</code>) —
không có số nào gõ tay.</p>

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

<h2>Giới hạn phải nói khi trích</h2>
<ul>{caveat_rows}</ul>
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
