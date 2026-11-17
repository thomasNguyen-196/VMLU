"""Post-hoc, exploratory: what the B (direct) and S (step-by-step) attempts already logged say about the models'
Vietnamese ability. No request is sent and no registered result is replaced. It reads:

- MC-109's vmlu.ai grades (Qwen, before and loop, per subject) and MC-85's (MiMo);
- MC-105's /table attempts and MC-104's fresh VMLU dev / VM14K attempts (both students);
- MC-100's oracle report and MC-96's retrieval report (Qwen).

  .venv/bin/python -m code_benchmark.analyze_model_capability [--markdown <file>]

The report is docs/research/vietnamese-ability-from-loop-results-2026-11-08.md.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOOP = ROOT / "all_res" / "diagnostic_router_loop"
GRADES = ROOT / "docs" / "research"
FOLDERS = {"Qwen3.5-9B": "qwen3-5-9b-65k-prospective", "MiMo V2.6 Flash": "mimo-v2-6-flash"}
NAMES = {"vi-multimodel-v1-vmlu-valid": "VMLU valid", "vi-multimodel-v1-legal-mc-146": "Legal MC",
         "vi-multimodel-v1-legal-nli-150": "Legal NLI", "vi-multimodel-v1-vi-squad-200": "Vi-SQuAD",
         "vi-multimodel-v1-vi-drop-200": "Vi-DROP", "vi-multimodel-v1-bidlqa-test": "ViBidLQA test",
         "vmlu-mqa-dev": "VMLU dev (MC-104)", "vm14k-4-options": "VM14K (MC-104)"}
FRESH = ("vmlu-mqa-dev", "vm14k-4-options")
CATEGORIES = {"humanity": "Nhân văn", "other": "Khác", "social_science": "Khoa học xã hội", "stem": "STEM"}
# Our grouping of the 58 VMLU subjects (not vmlu.ai's): computation-heavy and Vietnam-specific knowledge.
COMPUTATION = ("elementary_mathematics", "middle_school_mathematics", "high_school_mathematics", "discrete_mathematics",
               "statistics_and_probability", "introduction_to_physics", "middle_school_physics", "high_school_physics",
               "introduction_to_chemistry", "middle_school_chemistry", "high_school_chemistry", "computer_architecture",
               "electrical_engineering")
VIETNAM = ("vietnamese_language_and_literature", "high_school_literature", "middle_school_literature",
           "administrative_law", "business_law", "civil_law", "criminal_law", "economic_law", "education_law",
           "introduction_to_laws", "elementary_history", "middle_school_history", "high_school_history",
           "introduction_to_vietnam_culture", "ho_chi_minh_ideology",
           "revolutionary_policy_of_the_vietnamese_commununist_part", "high_school_geography",
           "middle_school_geography", "middle_school_civil_education", "high_school_civil_education",
           "idealogical_and_moral_cultivation")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def is_reading(row: dict[str, Any]) -> bool:
    return "token_f1" in row


def score(row: dict[str, Any]) -> float:
    return float(row["token_f1"]) if is_reading(row) else float(row["correct"])


def pct(values: list[float]) -> float | None:
    return round(100 * statistics.fmean(values), 1) if values else None


def fmt(value: Any) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    return str(value)


def table(header: list[str], rows: list[list[Any]]) -> str:
    lines = ["", "| " + " | ".join(header) + " |", "|" + "|".join("---" if i < 2 else "---:" for i in range(len(header))) + "|"]
    lines += ["| " + " | ".join(fmt(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def attempts(folder: str) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    rows = load_jsonl(LOOP / "table_loop" / folder / "scores.jsonl")
    rows += [r for r in load_jsonl(LOOP / "self_loop" / folder / "scores.jsonl") if r["dataset_id"] in FRESH]
    items: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        items[(row["dataset_id"], row["item_id"])][row["replicate_id"]] = row
    return items


# ---------------------------------------------------------------- 1. VMLU test per subject (vmlu.ai grades)

def subjects(grade: dict[str, Any]) -> dict[str, float]:
    return {name: value for category in grade["categories"].values() for name, value in category["subjects"].items()}


def vmlu_test() -> dict[str, Any]:
    before = json.loads((GRADES / "qwen-vmlu-test-server-grade-mc109-before-2026-11-07.json").read_text())
    loop = json.loads((GRADES / "qwen-vmlu-test-server-grade-mc109-loop-2026-11-07.json").read_text())
    mimo = json.loads((GRADES / "mimo26-vmlu-test-server-grade-mc85-2026-10-15.json").read_text())
    b, lp, m = subjects(before), subjects(loop), subjects(mimo)
    missing = [s for s in COMPUTATION + VIETNAM if s not in b]
    if missing or len(b) != 58:
        raise SystemExit(f"Error: unexpected VMLU subjects: {missing or len(b)}")
    rest = tuple(s for s in b if s not in COMPUTATION + VIETNAM)
    groups = {}
    for name, members in (("computation", COMPUTATION), ("vietnam", VIETNAM), ("rest", rest)):
        groups[name] = {"subjects": len(members), "before": round(statistics.fmean(b[s] for s in members), 2),
                        "loop": round(statistics.fmean(lp[s] for s in members), 2),
                        "mimo": round(statistics.fmean(m[s] for s in members), 2),
                        "gain_at_most_2": sum(lp[s] - b[s] <= 2 for s in members)}
    categories = {c: {"before": before["categories"][c]["total"], "loop": loop["categories"][c]["total"],
                      "mimo": mimo["categories"][c]["total"]} for c in before["categories"]}
    ranked = sorted(b, key=lambda s: lp[s])
    return {"total": {"before": before["total"], "loop": loop["total"], "mimo": mimo["total"]},
            "categories": categories, "groups": groups,
            "lowest_after_loop": [{"subject": s, "before": b[s], "loop": lp[s], "mimo": m[s]} for s in ranked[:8]],
            "largest_gain": [{"subject": s, "before": b[s], "loop": lp[s], "mimo": m[s]}
                             for s in sorted(b, key=lambda s: b[s] - lp[s])[:6]]}


# ---------------------------------------------------------------- 2. B against S, item by item

def b_versus_s(items) -> list[dict[str, Any]]:
    cells: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"B": [], "S": [], "rescued": 0, "broken": 0})
    for (dataset, _), reps in items.items():
        if "B-r1" not in reps or "S-r1" not in reps:
            continue
        b, s = score(reps["B-r1"]), score(reps["S-r1"])
        for key in ((dataset, "all"), (dataset, str(reps["B-r1"].get("stratum")))):
            cell = cells[key]
            cell["B"].append(b)
            cell["S"].append(s)
            # MC: a wrong letter made right, or the reverse; reading: token-F1 moved by half or more
            cell["rescued"] += (s - b >= 0.5) if is_reading(reps["B-r1"]) else (b == 0 and s == 1)
            cell["broken"] += (b - s >= 0.5) if is_reading(reps["B-r1"]) else (b == 1 and s == 0)
    out = []
    for (dataset, stratum), cell in cells.items():
        if stratum != "all" and dataset not in ("vi-multimodel-v1-vmlu-valid", "vi-multimodel-v1-vi-drop-200"):
            continue
        b, s = pct(cell["B"]), pct(cell["S"])
        out.append({"dataset": dataset, "stratum": stratum, "n": len(cell["B"]), "B": b, "S": s,
                    "S_minus_B": round(s - b, 1) if b is not None and s is not None else None,
                    "rescued": cell["rescued"], "broken": cell["broken"]})
    order = list(NAMES)
    return sorted(out, key=lambda r: (order.index(r["dataset"]), r["stratum"] != "all", r["stratum"]))


def confidence_bins(items) -> list[dict[str, Any]]:
    """Qwen only: B-r1 is the letter probe, whose confidence is the chosen letter's probability."""
    bins: dict[str, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for reps in items.values():
        b = reps.get("B-r1")
        if not b or "S-r1" not in reps or is_reading(b) or b.get("confidence") in (None, "None", ""):
            continue
        value = float(b["confidence"])
        key = "< 0,5" if value < 0.5 else "0,5–0,8" if value < 0.8 else "0,8–0,9" if value < 0.9 else "≥ 0,9"
        bins[key][0].append(score(b))
        bins[key][1].append(score(reps["S-r1"]))
    out = []
    for key in ("< 0,5", "0,5–0,8", "0,8–0,9", "≥ 0,9"):
        b_scores, s_scores = bins[key]
        b, s = pct(b_scores), pct(s_scores)
        out.append({"confidence": key, "n": len(b_scores), "B": b, "S": s,
                    "S_minus_B": round(s - b, 1) if b is not None and s is not None else None})
    return out


# ---------------------------------------------------------------- 3. reading: format against content

def _norm(text: Any) -> str:
    text = unicodedata.normalize("NFC", str(text or "")).lower().replace("*", "").replace("`", "")
    text = re.sub(r"[.,](?=\s|$)", " ", re.sub(r"[^\w\s%.,]", " ", text))
    return " " + re.sub(r"\s+", " ", text).strip() + " "


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def reading_format(items) -> list[dict[str, Any]]:
    """Token-F1 and exact match (the registered scorer) beside two lenient checks: the normalized gold appears as a
    whole phrase in the prediction, and, for Vi-DROP golds that are one bare number, the prediction's first number."""
    cells: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (dataset, _), reps in items.items():
        if "B-r1" not in reps or "S-r1" not in reps or not is_reading(reps["B-r1"]):
            continue
        for arm in ("B", "S"):
            row = reps[f"{arm}-r1"]
            gold, prediction = _norm(row["gold_answer"]), _norm(row["prediction"])
            cells[dataset][f"{arm}_f1"].append(float(row["token_f1"]))
            cells[dataset][f"{arm}_em"].append(float(row["em"]))
            cells[dataset][f"{arm}_contains"].append(float(bool(gold.strip()) and gold in prediction))
            cells[dataset][f"{arm}_chars"].append(len(str(row.get("prediction") or "")))
            if dataset.endswith("vi-drop-200") and re.fullmatch(r"\s*\d+(?:[.,]\d+)?\s*", str(row["gold_answer"])):
                found = _NUMBER.findall(str(row.get("prediction") or ""))
                cells[dataset][f"{arm}_first_number"].append(
                    float(bool(found) and found[0] == _NUMBER.findall(str(row["gold_answer"]))[0]))
    out = []
    for dataset, cell in cells.items():
        row = {"dataset": dataset, "n": len(cell["B_f1"])}
        for key, values in cell.items():
            row[key] = round(statistics.fmean(values)) if key.endswith("chars") else pct(values)
        row["first_number_n"] = len(cell.get("B_first_number", []))
        out.append(row)
    return sorted(out, key=lambda r: list(NAMES).index(r["dataset"]))


# ---------------------------------------------------------------- 4. reasoning length and agreement

def quartiles(items, replicate: str, field: str) -> list[dict[str, Any]]:
    out = []
    for dataset in NAMES:
        pairs = sorted((int(reps[replicate].get(field) or 0), score(reps[replicate]))
                       for (d, _), reps in items.items() if d == dataset and replicate in reps)
        if len(pairs) < 40:
            continue
        size = len(pairs) // 4
        parts = [pairs[i * size:(i + 1) * size] if i < 3 else pairs[3 * size:] for i in range(4)]
        out.append({"dataset": dataset, "quartiles": [{"score": pct([s for _, s in part]),
                                                       "median_tokens": statistics.median(t for t, _ in part)}
                                                      for part in parts]})
    return out


def agreement(items) -> list[dict[str, Any]]:
    groups: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (dataset, _), reps in items.items():
        if not all(k in reps for k in ("S-r1", "S-r2", "S-r3")) or is_reading(reps["S-r1"]):
            continue
        top = Counter(reps[k].get("prediction") for k in ("S-r1", "S-r2", "S-r3")).most_common(1)[0][1]
        groups[dataset][top].append(score(reps["S-r1"]))
    out = []
    for dataset in NAMES:
        if dataset not in groups:
            continue
        total = sum(len(v) for v in groups[dataset].values())
        out.append({"dataset": dataset, **{f"agree_{k}": {"share": round(100 * len(groups[dataset][k]) / total),
                                                         "S_r1": pct(groups[dataset][k])}
                                          for k in (3, 2, 1) if groups[dataset][k]}})
    return out


# ---------------------------------------------------------------- 5. evidence (MC-100, MC-96)

def evidence() -> dict[str, Any]:
    oracle = json.loads(next((ROOT / "all_res" / "diagnostic_legal_oracle" / "run").glob(
        "*/analysis/legal_oracle_report.json")).read_text())
    k2 = json.loads(next((ROOT / "all_res" / "diagnostic_k2" / "heldout").glob("*/analysis/k2_report.json")).read_text())
    by = k2["rotations"]["1"]["by_retrieval"]
    return {"mc100": {stratum: {key: oracle["primary"][stratum][key] for key in ("n", "B", "O")}
                      | {"p": oracle["primary"][stratum]["O_versus_B"]["sign_flip_p"]} for stratum in ("wrong", "right")},
            "mc96": {name: {"items": cell["items"], **{arm: round(100 * cell[arm], 1)
                                                      for arm in ("always_B", "always_K", "O")}}
                     for name, cell in by.items()}}


def build() -> dict[str, Any]:
    report: dict[str, Any] = {"vmlu_test": vmlu_test(), "evidence": evidence(), "students": {}}
    for name, folder in FOLDERS.items():
        items = attempts(folder)
        report["students"][name] = {
            "b_versus_s": b_versus_s(items), "reading_format": reading_format(items),
            "s_length": quartiles(items, "S-r1", "completion_tokens"), "agreement": agreement(items),
            "confidence_bins": confidence_bins(items) if name.startswith("Qwen") else None,
            "b_thinking_length": quartiles(items, "B-r1", "reasoning_tokens") if name.startswith("MiMo") else None}
    return report


def markdown(report: dict[str, Any]) -> str:
    t = report["vmlu_test"]
    parts = ["### VMLU test (vmlu.ai): Qwen trước và sau vòng lặp (MC-109), MiMo hỏi thẳng (MC-85)",
             table(["Nhóm", "Số môn", "Qwen hỏi thẳng", "Qwen vòng lặp", "Tăng", "MiMo hỏi thẳng", "Số môn tăng ≤ 2 điểm"],
                   [[label, g["subjects"], float(g["before"]), float(g["loop"]), round(g["loop"] - g["before"], 1),
                     float(g["mimo"]), g["gain_at_most_2"]]
                    for label, g in (("Tính toán", t["groups"]["computation"]),
                                     ("Kiến thức đặc thù Việt Nam", t["groups"]["vietnam"]),
                                     ("Còn lại", t["groups"]["rest"]))]),
             "", table(["Nhóm của vmlu.ai", "Qwen hỏi thẳng", "Qwen vòng lặp", "MiMo hỏi thẳng"],
                       [[CATEGORIES.get(c, c), float(v["before"]), float(v["loop"]), float(v["mimo"])] for c, v in t["categories"].items()]
                       + [["Tổng", float(t["total"]["before"]), float(t["total"]["loop"]), float(t["total"]["mimo"])]]),
             "", "Tám môn thấp nhất sau vòng lặp:", "",
             table(["Môn", "Qwen hỏi thẳng", "Qwen vòng lặp", "MiMo hỏi thẳng"],
                   [[r["subject"], float(r["before"]), float(r["loop"]), float(r["mimo"])] for r in t["lowest_after_loop"]])]
    for name, s in report["students"].items():
        parts += ["", f"### {name}: hỏi thẳng (B-r1) và từng bước (S-r1) trên cùng câu",
                  table(["Bộ", "Nhóm", "Số câu", "B", "S", "S − B", "Sai → đúng", "Đúng → sai"],
                        [[NAMES[r["dataset"]], "cả bộ" if r["stratum"] == "all" else r["stratum"], r["n"], r["B"], r["S"],
                          r["S_minus_B"], r["rescued"], r["broken"]] for r in s["b_versus_s"]]),
                  "", f"### {name}: đọc hiểu, thước chấm chính và hai cách chấm nới lỏng",
                  table(["Bộ", "Số câu", "B F1", "B EM", "B chứa đáp án", "B số đầu tiên (Vi-DROP)", "S F1", "S EM", "S chứa đáp án",
                         "S số đầu tiên (Vi-DROP)", "Độ dài B (ký tự)", "Độ dài S (ký tự)"],
                        [[NAMES[r["dataset"]], r["n"], r["B_f1"], r["B_em"], r["B_contains"], r.get("B_first_number"),
                          r["S_f1"], r["S_em"], r["S_contains"], r.get("S_first_number"), r["B_chars"], r["S_chars"]]
                         for r in s["reading_format"]]),
                  "", f"### {name}: điểm của S-r1 theo độ dài lời giải (tứ phân vị token sinh ra trong mỗi bộ)",
                  table(["Bộ", "Ngắn nhất", "Thứ 2", "Thứ 3", "Dài nhất"],
                        [[NAMES[r["dataset"]]] + [f"{fmt(q['score'])} ({fmt(int(q['median_tokens']))} token)"
                                                  for q in r["quartiles"]] for r in s["s_length"]])]
        if s["b_thinking_length"]:
            parts += ["", f"### {name}: điểm của B-r1 theo độ dài phần suy nghĩ ẩn (reasoning token)",
                      table(["Bộ", "Ngắn nhất", "Thứ 2", "Thứ 3", "Dài nhất"],
                            [[NAMES[r["dataset"]]] + [f"{fmt(q['score'])} ({fmt(int(q['median_tokens']))} token)"
                                                      for q in r["quartiles"]] for r in s["b_thinking_length"]])]
        if s["confidence_bins"]:
            parts += ["", f"### {name}: trắc nghiệm, theo độ tự tin của lần hỏi thẳng",
                      table(["Độ tự tin của B", "Số câu", "B", "S", "S − B"],
                            [[r["confidence"], r["n"], r["B"], r["S"], r["S_minus_B"]] for r in s["confidence_bins"]])]
        parts += ["", f"### {name}: trắc nghiệm, ba lần S có trả lời giống nhau không",
                  table(["Bộ", "3/3 giống: tỷ lệ câu", "3/3: S-r1 đúng", "2/3 giống: tỷ lệ câu", "2/3: S-r1 đúng"],
                        [[NAMES[r["dataset"]], f"{r['agree_3']['share']}%", r["agree_3"]["S_r1"],
                          f"{r.get('agree_2', {}).get('share', 0)}%", r.get("agree_2", {}).get("S_r1")]
                         for r in s["agreement"]])]
    e = report["evidence"]
    parts += ["", "### Khi được đưa đúng văn bản (Qwen)",
              table(["Thí nghiệm", "Nhóm câu", "Số câu", "Không có văn bản", "Có văn bản đúng"],
                    [["MC-100 Legal MC", "B từng sai", e["mc100"]["wrong"]["n"], e["mc100"]["wrong"]["B"], e["mc100"]["wrong"]["O"]],
                     ["MC-100 Legal MC", "B luôn đúng", e["mc100"]["right"]["n"], e["mc100"]["right"]["B"], e["mc100"]["right"]["O"]]]),
              "", table(["MC-96 ViBidLQA (token-F1)", "Số câu", "Không văn bản (B)", "Văn bản tự tìm (K)", "Văn bản đúng (O)"],
                        [[("tìm trúng đoạn của câu" if k == "own_passage_in_top_2" else "tìm trượt"), v["items"],
                          v["always_B"], v["always_K"], v["O"]] for k, v in e["mc96"].items()])]
    return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--markdown", type=Path, help="write the tables as Markdown to this file")
    args = parser.parse_args(argv)
    report = build()
    if args.markdown:
        args.markdown.write_text(markdown(report), encoding="utf-8")
        print(f"wrote {args.markdown}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
