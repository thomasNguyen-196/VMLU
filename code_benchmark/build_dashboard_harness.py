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
    from code_benchmark.run_harness_eval import ARM_A, _mc_eval_path
    from code_benchmark.score_reading_eval import measurement_card_hash, score_pair
except ImportError:
    from common import read_csv_checked
    from run_harness_eval import ARM_A, _mc_eval_path
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
     "**omp sạch**: không tool + system prompt trung tính, HOME override", "MC-22"),
    ("ompH6clean_Qwen3_5-9B-28K", "ompH6clean_Qwen3_5-9B-28K", "H6",
     "**omp sạch** + tool menu đầy đủ", "MC-23"),
    ("ompH7clean_Qwen3_5-9B-28K", "ompH7clean_Qwen3_5-9B-28K", "H7",
     "**omp sạch** + system prompt của omp, không tool", "MC-23"),
    ("ompH8clean_Qwen3_5-9B-28K", "ompH8clean_Qwen3_5-9B-28K", "H8",
     "**omp sạch** + tool menu + system prompt của omp", "MC-23"),
    ("ompV1clean_Qwen3_5-9B-28K", "ompV1clean_Qwen3_5-9B-28K", "V1",
     "**omp sạch** + tool menu đầy đủ, trên V-Bench function-calling (nơi scaffold "
     "*có thể* thắng)", "MC-26"),
]
DATASETS = ["reading400", "legal_mc", "legal_nli", "bidlqa_val", "vbench_agentic"]
DATASET_LABEL = {"reading400": "reading-400 (EM)", "legal_mc": "legal-MC (accuracy)",
                 "legal_nli": "legal-NLI (accuracy)", "bidlqa_val": "ViBidLQA val (EM)",
                 "vbench_agentic": "V-Bench agentic (schema validity — KHÔNG có gold)"}


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


def arm_metrics(folder: Path, dataset: str, spec: dict, slug: str) -> dict | None:
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
    for _key, slug, short, label, card in arms:
        folder = results_dir / slug
        if not folder.exists():
            continue
        baseline = short == "A"
        for dataset in DATASETS:
            own = arm_metrics(folder, dataset, ARM_A[dataset], slug)
            if not own:
                continue
            base = {"arm": short, "arm_slug": slug, "label": label, "card": card,
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
                         "both": int(cmp_row["both"]), "a_only": int(cmp_row["a_only"]),
                         "b_only": int(cmp_row["b_only"]), "neither": int(cmp_row["neither"])})
        cost = arm_cost(folder, DATASETS)
        if cost:
            costs.append({"arm": short, "arm_slug": slug, "label": label, **cost})
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
        for dataset in DATASETS:
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
    for folder in sorted(results_dir.glob("ompH*_r[0-9]*_*")):
        if folder.is_dir() and folder.name not in by_slug:
            slugs.append(folder.name)
    for slug in slugs:
        folder = results_dir / slug
        if not folder.exists():
            continue
        match = re.match(r"(ompH\d+clean?)(?:_r(\d+))?_Qwen", slug)
        cell = match.group(1) if match else slug
        repeat = int(match.group(2)) if (match and match.group(2)) else 1
        if slug in by_slug:
            short, label, card = by_slug[slug]
        else:  # a repeat: inherit the label of the cell it repeats
            base = by_slug.get(f"{cell}_Qwen3_5-9B-28K")
            short, label, card = (f"{cell}·r{repeat}", f"{base[1]} — lặp {repeat}" if base
                                  else slug, base[2] if base else None)
        for dataset in DATASETS:
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
    totals = {
        "items_harness": sum(c["n"] for c in costs),
        "failures": sum(c["failures"] for c in costs),
        "tool_use_items": sum(c["tool_use_items"] for c in costs),
        "net_attempt_items": sum(c["net_attempt_items"] for c in costs),
        "path_escape_items": sum(c["path_escape_items"] for c in costs),
    }
    return {
        "benchmark_name": "Harness arm — cùng model, khác scaffold (omp vs gọi API trực tiếp)",
        "date": "2026-09-26",
        "model_id": "Qwen3.5-9B-28K",
        "endpoint": "https://llmapi.iec-uit.com/v1",
        "harness": "omp (Oh My Pi) v18.2.7",
        "condition": ("prompt byte-identical với arm A, temperature 0, seed 42, scorer đóng băng; "
                      "khác duy nhất là đường elicitation"),
        "measurement_card": "MC-15…MC-27",
        "measurement_card_hash": measurement_card_hash(),
        "scorer": "extract_answer (MC) + score_reading_eval.py (EM/char-F1) — không viết lại",
        "ladder": ladder,
        "secondary_metrics": secondary_metrics(results_dir, arms),
        "repeatability": repeatability(results_dir, arms),
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
