"""Quality-versus-cost figures for the thesis (chapter 4): score against mean tokens per item, one panel per item set.

Reads only frozen analysis outputs (registered reports of MC-93 to MC-96, MC-111 scores, MC-114's report and the
post-hoc loop Pareto report); calls no model. Writes three SVG figures, a CSV of every plotted point and a JSON of the
input SHA-256s. Stdlib only, so it runs without a plotting library.

Every panel compares policies on the same items. Tokens are the mean reported tokens per item (prompt and completion,
summed over every request the policy needs), so the x positions are comparable within a panel, not across panels.

Run from the repo root:  .venv/bin/python -m code_benchmark.plot_cost_quality [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
from html import escape
import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "vmlu_docs" / "01_thesis_and_proposals" / "kltn_draft" / "hinh"
RES = ROOT / "all_res"
SOURCES = {
    "mc93": RES / "diagnostic_prospective/core/qwen3-5-9b-65k-prospective/analysis/router_report.json",
    "mc94": RES / "diagnostic_router_v2/heldout/qwen3-5-9b-65k-prospective/analysis/router_v2_report.json",
    "mc95": RES / "diagnostic_router_v3/heldout/qwen3-5-9b-65k-prospective/analysis/router_v3_report.json",
    "mc96": RES / "diagnostic_k2/heldout/qwen3-5-9b-65k-prospective/analysis/k2_report.json",
    "pareto": RES / "diagnostic_router_loop/pareto/loop_pareto_report.json",
    "mc111_round1": RES / "diagnostic_legal_select/run/qwen3-5-9b-65k-prospective/round1/scores.jsonl",
    "mc111_round2": RES / "diagnostic_legal_select/run/qwen3-5-9b-65k-prospective/round2/scores.jsonl",
    "mc111_report": RES / "diagnostic_legal_select/run/qwen3-5-9b-65k-prospective/analysis/legal_select_report.json",
    "mc114": RES / "diagnostic_legal_agent_v2/run/qwen3-5-9b-65k-legal-agent-v2/analysis/legal_agent_v2_report.json",
}

# Three categorical slots of the reference palette (validated all-pairs on white): identity = the policy's family.
FAMILIES = {
    "fixed": ("#2a78d6", "Cách hỏi cố định"),
    "per_item": ("#eb6834", "Quyết định theo từng câu (router, vòng tự sửa, tự chọn bằng chứng)"),
    "agent": ("#1baf7a", "Agent tự tra văn bản"),
}
INK, INK_2, INK_3, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e8e7e2", "#ffffff"
FONT = "Inter, 'Noto Sans', 'DejaVu Sans', Arial, sans-serif"


@dataclass
class Point:
    label: str
    family: str
    tokens: float
    score: float
    oracle: bool = False  # a ceiling that needs the gold-aware evidence; drawn hollow, kept off the Pareto line


@dataclass
class Panel:
    title: str
    subtitle: str
    y_label: str
    card: str
    points: list[Point]
    reference: tuple[float, str] | None = None  # a horizontal reference line (value, label)
    notes: list[str] = field(default_factory=list)


def _json(name: str) -> dict:
    return json.loads(SOURCES[name].read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- the panels

def router_panels() -> list[Panel]:
    mc93 = _json("mc93")["primary"]["policies"]
    p93 = [Point("B", "fixed", mc93["always_B"]["mean_total_tokens"], 100 * mc93["always_B"]["accuracy"]),
           Point("S", "fixed", mc93["always_S"]["mean_total_tokens"], 100 * mc93["always_S"]["accuracy"]),
           Point("Router v1", "per_item", mc93["router"]["mean_total_tokens"], 100 * mc93["router"]["accuracy"])]
    ceiling = 100 * _json("mc93")["deployable_ceiling"]["observed"]
    v2 = _json("mc94")
    pol94 = v2["families"][v2["primary_family"]]["rotations"][str(v2["primary_rotation"])]["policies"]
    p94 = [Point("B", "fixed", pol94["always_B"]["mean_total_tokens"], 100 * pol94["always_B"]["accuracy"]),
           Point("S", "fixed", pol94["always_S"]["mean_total_tokens"], 100 * pol94["always_S"]["accuracy"]),
           Point("Router v2", "per_item", pol94["v2"]["mean_total_tokens"], 100 * pol94["v2"]["accuracy"])]
    v3 = _json("mc95")
    pol95 = v3["families"][v3["primary_family"]]["rotations"][str(v3["primary_rotation"])]["policies"]
    p95 = [Point("B", "fixed", pol95["always_B"]["mean_total_tokens"], 100 * pol95["always_B"]["accuracy"]),
           Point("S", "fixed", pol95["always_S"]["mean_total_tokens"], 100 * pol95["always_S"]["accuracy"]),
           Point("Router v2", "per_item", pol95["v2"]["mean_total_tokens"], 100 * pol95["v2"]["accuracy"]),
           Point("Router v3", "per_item", pol95["v3"]["mean_total_tokens"], 100 * pol95["v3"]["accuracy"])]
    k2 = _json("mc96")
    pol96 = k2["rotations"][str(k2["primary_rotation"])]["policies"]
    f1 = lambda name: 100 * pol96[name]["mean_token_f1"]  # noqa: E731
    p96 = [Point("B", "fixed", pol96["always_B"]["mean_total_tokens"], f1("always_B")),
           Point("K", "fixed", pol96["always_K"]["mean_total_tokens"], f1("always_K")),
           Point("KS", "fixed", pol96["always_KS"]["mean_total_tokens"], f1("always_KS")),
           Point("K hai lần → KS", "per_item", pol96["k_cascade"]["mean_total_tokens"], f1("k_cascade")),
           Point("O (trần)", "fixed", pol96["O"]["mean_total_tokens"], f1("O"), oracle=True)]
    return [
        Panel("60 câu neo", "core, đọc hiểu và trắc nghiệm", "Câu đúng (%)", "MC-93", p93,
              reference=(ceiling, f"trần định tuyến {ceiling:.1f}".replace(".", ","))),
        Panel("VMLU valid, 300 câu mới", "trắc nghiệm", "Độ chính xác (%)", "MC-94", p94),
        Panel("VMLU và VM14K, 600 câu mới", "trắc nghiệm", "Độ chính xác (%)", "MC-95", p95),
        Panel("ViBidLQA, 300 câu không kèm đoạn văn", "trả lời bằng đoạn trích", "Token-F1", "MC-96", p96),
    ]


POLICY_NAMES = {"always_B": ("B", "fixed"), "gate_S": ("2 vòng", "per_item"), "loop": ("3 vòng (đăng ký)", "per_item"),
                "always_S": ("S", "fixed"), "always_vote": ("Bỏ phiếu 3 S", "fixed")}


def loop_panels() -> list[Panel]:
    report = _json("pareto")
    sources = [("mc104_fresh_items", "{m}", "Trắc nghiệm, 603 câu mới", "VMLU dev và VM14K", "MC-104"),
               ("mc105_table_suite", "{m}:multiple_choice", "Trắc nghiệm, 1.040 câu", "VMLU valid, Legal MC, Legal NLI",
                "MC-105"),
               ("mc105_table_suite", "{m}:reading", "Đọc hiểu, 1.003 câu", "Vi-SQuAD, Vi-DROP, ViBidLQA test",
                "MC-105")]
    models = (("qwen", "Qwen3.5-9B"), ("mimo", "MiMo V2.6 Flash"))
    out = []
    for source, key, title, subtitle, card in sources:
        for model, model_name in models:
            block = report[source]["pooled"][key.format(m=model)]
            metric = "Độ chính xác (%)" if "Trắc" in title else "Token-F1 (v3)"
            points = [Point(POLICY_NAMES[name][0], POLICY_NAMES[name][1], value["mean_tokens"], value["score"])
                      for name, value in block["policies"].items()]
            out.append(Panel(f"{model_name}: {title}", subtitle, metric, card, points))
    return out


def evidence_panels() -> list[Panel]:
    cells: dict[str, dict[str, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    tokens: dict[str, list[float]] = collections.defaultdict(list)
    for name in ("mc111_round1", "mc111_round2"):
        for line in SOURCES[name].read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                arm = row["replicate_id"].split("-r")[0]
                cells[arm][row["item_id"]].append(float(row.get("correct") or 0.0))
                tokens[arm].append(float(row.get("total_tokens") or 0.0))
    report = _json("mc111_report")
    if round(_mean_items(cells["B"]), 2) != report["replication"]["this_run"]["pool_B"]:
        raise SystemExit("Error: MC-111 scores do not reproduce the report's pool B")
    pick_tokens = report["descriptive"]["mean_tokens"]["PICK"]["total"]
    p111 = [Point("B", "fixed", statistics.fmean(tokens["B"]), _mean_items(cells["B"])),
            Point("K (2 điều)", "fixed", statistics.fmean(tokens["K"]), _mean_items(cells["K"])),
            Point("K10 (10 điều)", "fixed", statistics.fmean(tokens["K10"]), _mean_items(cells["K10"])),
            Point("Chọn rồi trả lời", "per_item", statistics.fmean(tokens["SEL"]) + pick_tokens,
                  _mean_items(cells["SEL"]))]
    mc114 = _json("mc114")
    beh_m, beh_s = mc114["behaviour"]["M"], mc114["behaviour"]["S"]
    against_b = mc114["part_M_description"]["against_B"]
    m_score = {"B": against_b["DSH"]["B"], **{arm: against_b[arm][arm] for arm in ("DSH", "DSHF", "OMPF")}}
    p114m = [Point("B", "fixed", beh_m["B"]["mean_reported_tokens"], m_score["B"])] + [
        Point(arm, "agent", beh_m[arm]["mean_reported_tokens"], m_score[arm]) for arm in ("DSH", "DSHF", "OMPF")]
    means = mc114["part_S_description"]["means"]
    p114s = [Point("C", "fixed", beh_s["C"]["mean_reported_tokens"], means["C"]),
             Point("O (trần)", "fixed", beh_s["O"]["mean_reported_tokens"], means["O"], oracle=True)] + [
        Point(arm, "agent", beh_s[arm]["mean_reported_tokens"], means[arm]) for arm in ("DSH", "DSHF", "OMPF")]
    return [
        Panel("Legal MC, 134 câu", "trắc nghiệm luật", "Độ chính xác (%)", "MC-111", p111),
        Panel("Luật VMLU, 112 câu mới", "trắc nghiệm luật", "Độ chính xác (%)", "MC-114", p114m),
        Panel("ViBidLQA, 400 câu không kèm đoạn văn", "trả lời bằng đoạn trích", "Token-F1 (v3)", "MC-114", p114s),
    ]


def _mean_items(by_item: dict[str, list[float]]) -> float:
    return 100 * statistics.fmean(statistics.fmean(v) for v in by_item.values())


# ---------------------------------------------------------------- geometry

def pareto(points: list[Point]) -> list[Point]:
    """Deployable points that no other deployable point beats on both score and tokens, by tokens ascending."""
    usable = sorted((p for p in points if not p.oracle), key=lambda p: (p.tokens, -p.score))
    out: list[Point] = []
    for p in usable:
        if not out or p.score > out[-1].score:
            out.append(p)
    return out


def nice_step(span: float, target: int = 4) -> float:
    raw = span / target
    magnitude = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 2.5, 5, 10):
        if raw <= factor * magnitude:
            return factor * magnitude
    return 10 * magnitude


def vn_number(value: float, decimals: int = 0) -> str:
    """Vietnamese formatting: dot for thousands, comma for decimals."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def text_width(text: str, size: float) -> float:
    """A rough width for label placement (Inter averages about half an em per character)."""
    return 0.53 * size * len(text)


def _box_left(x: float, anchor: str, width: float) -> float:
    return x if anchor == "start" else x - width if anchor == "end" else x - width / 2


# ---------------------------------------------------------------- SVG

PANEL_W, PANEL_H = 380, 270
PAD_L, PAD_R, PAD_T, PAD_B = 58, 22, 52, 42
LEGEND_H, FOOT_H, GAP = 78, 34, 18


def panel_svg(panel: Panel, x0: float, y0: float, x_range: tuple[float, float]) -> list[str]:
    left, right = x0 + PAD_L, x0 + PANEL_W - PAD_R
    top, bottom = y0 + PAD_T, y0 + PANEL_H - PAD_B
    lo_x, hi_x = (math.log10(v) for v in x_range)
    values = [p.score for p in panel.points] + ([panel.reference[0]] if panel.reference else [])
    step = nice_step(max(values) - min(values) or 1.0)
    lo_y = math.floor((min(values) - 0.15 * step) / step) * step
    hi_y = math.ceil((max(values) + 0.15 * step) / step) * step

    def sx(tokens: float) -> float:
        return left + (math.log10(tokens) - lo_x) / (hi_x - lo_x) * (right - left)

    def sy(score: float) -> float:
        return bottom - (score - lo_y) / (hi_y - lo_y) * (bottom - top)

    out = ['<g class="panel">',
           f'<text x="{x0 + 8}" y="{y0 + 18}" font-size="13" font-weight="600" fill="{INK}">{escape(panel.title)}</text>',
           f'<text x="{x0 + 8}" y="{y0 + 35}" font-size="11" fill="{INK_2}">{escape(panel.subtitle)} · '
           f'{escape(panel.card)}</text>']
    # recessive grid and axes
    y = lo_y
    while y <= hi_y + 1e-9:
        py = sy(y)
        out.append(f'<line x1="{left}" y1="{py:.1f}" x2="{right}" y2="{py:.1f}" stroke="{GRID}" stroke-width="1"/>')
        decimals = 0 if step >= 1 else 1
        out.append(f'<text x="{left - 6}" y="{py + 3.5:.1f}" font-size="10.5" fill="{INK_2}" '
                   f'text-anchor="end">{vn_number(y, decimals)}</text>')
        y += step
    for exponent in range(int(math.floor(lo_x)), int(math.ceil(hi_x)) + 1):
        for mult in (1, 3):
            tick = mult * 10 ** exponent
            if not (x_range[0] <= tick <= x_range[1]):
                continue
            px = sx(tick)
            out.append(f'<line x1="{px:.1f}" y1="{bottom}" x2="{px:.1f}" y2="{bottom + 4}" stroke="{INK_3}"/>')
            out.append(f'<text x="{px:.1f}" y="{bottom + 16}" font-size="10.5" fill="{INK_2}" '
                       f'text-anchor="middle">{vn_number(tick)}</text>')
    out.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{INK_3}" stroke-width="1"/>')
    out.append(f'<text transform="translate({x0 + 14},{(top + bottom) / 2:.1f}) rotate(-90)" font-size="10.5" '
               f'fill="{INK_2}" text-anchor="middle">{escape(panel.y_label)}</text>')
    # reference line
    if panel.reference:
        value, label = panel.reference
        py = sy(value)
        out.append(f'<line x1="{left}" y1="{py:.1f}" x2="{right}" y2="{py:.1f}" stroke="{INK_3}" stroke-width="1.5" '
                   f'stroke-dasharray="5 4"/>')
        out.append(f'<text x="{right}" y="{py - 5:.1f}" font-size="10.5" fill="{INK_2}" '
                   f'text-anchor="end">{escape(label)}</text>')
    # Pareto line behind the marks
    front = pareto(panel.points)
    if len(front) > 1:
        coords = " ".join(f"{sx(p.tokens):.1f},{sy(p.score):.1f}" for p in front)
        out.append(f'<polyline points="{coords}" fill="none" stroke="{INK_3}" stroke-width="1.5"/>')
    # marks: 10 px dots with a 2 px surface ring; oracle hollow
    placed: list[tuple[float, float, float, float]] = []
    marks = [(sx(p.tokens), sy(p.score)) for p in panel.points]
    for (px, py), p in zip(marks, panel.points, strict=True):
        color = FAMILIES[p.family][0]
        if p.oracle:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{SURFACE}" stroke="{color}" stroke-width="2"/>')
        else:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5.5" fill="{color}" stroke="{SURFACE}" '
                       f'stroke-width="2"/>')
    # direct labels, greedy placement avoiding marks, other labels and the panel edges
    for (px, py), p in sorted(zip(marks, panel.points, strict=True), key=lambda item: item[0][0]):
        width, height = text_width(p.label, 11), 12
        # right, above, below, left, then the four diagonals; above and below are centred on the mark
        candidates = [(px + 9, py + 4, "start"), (px, py - 10, "middle"), (px, py + 19, "middle"),
                      (px - 9, py + 4, "end"), (px + 7, py - 9, "start"), (px + 7, py + 16, "start"),
                      (px - 7, py - 9, "end"), (px - 7, py + 16, "end")]
        chosen = candidates[0]
        for cx, cy, anchor in candidates:
            bx = _box_left(cx, anchor, width)
            box = (bx, cy - height + 2, bx + width, cy + 2)
            inside = box[0] >= left - 4 and box[2] <= right + 4 and box[1] >= top - 6 and box[3] <= bottom - 2
            hits_label = any(not (box[2] < q[0] or box[0] > q[2] or box[3] < q[1] or box[1] > q[3]) for q in placed)
            hits_mark = any(box[0] - 6 < mx < box[2] + 6 and box[1] - 6 < my < box[3] + 6 for mx, my in marks)
            if inside and not hits_label and not hits_mark:
                chosen = (cx, cy, anchor)
                break
        cx, cy, anchor = chosen
        bx = _box_left(cx, anchor, width)
        placed.append((bx, cy - height + 2, bx + width, cy + 2))
        out.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="11" fill="{INK}" text-anchor="{anchor}" '
                   f'paint-order="stroke" stroke="{SURFACE}" stroke-width="3" stroke-linejoin="round">'
                   f'{escape(p.label)}</text>')
    out.append("</g>")
    return out


def figure_svg(title: str, panels: list[Panel], columns: int, footnote: str) -> str:
    rows = math.ceil(len(panels) / columns)
    width = columns * PANEL_W + (columns - 1) * GAP + 2 * GAP
    height = LEGEND_H + rows * PANEL_H + (rows - 1) * GAP + FOOT_H
    tokens = [p.tokens for panel in panels for p in panel.points]
    x_range = (10 ** math.floor(math.log10(min(tokens))), 10 ** math.ceil(math.log10(max(tokens))))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           f'font-family="{FONT}" role="img" aria-label="{escape(title)}">',
           f'<title>{escape(title)}</title>',
           f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>']
    # legend: the families present, the hollow ceiling mark if any, the Pareto line
    used = [key for key in FAMILIES if any(p.family == key and not p.oracle for panel in panels for p in panel.points)]
    lx, ly = GAP, 26
    for key in used:
        color, name = FAMILIES[key]
        out.append(f'<circle cx="{lx + 6}" cy="{ly - 4}" r="5.5" fill="{color}"/>')
        out.append(f'<text x="{lx + 17}" y="{ly}" font-size="11.5" fill="{INK}">{escape(name)}</text>')
        lx += 17 + text_width(name, 11.5) + 22
        if lx > width - 260:
            lx, ly = GAP, ly + 20
    if any(p.oracle for panel in panels for p in panel.points):
        out.append(f'<circle cx="{lx + 6}" cy="{ly - 4}" r="5" fill="{SURFACE}" stroke="{FAMILIES["fixed"][0]}" '
                   f'stroke-width="2"/>')
        out.append(f'<text x="{lx + 17}" y="{ly}" font-size="11.5" fill="{INK}">Trần: bằng chứng đúng do người duyệt '
                   f'chọn</text>')
        lx += 17 + text_width("Trần: bằng chứng đúng do người duyệt chọn", 11.5) + 22
        if lx > width - 160:
            lx, ly = GAP, ly + 20
    out.append(f'<line x1="{lx}" y1="{ly - 4}" x2="{lx + 22}" y2="{ly - 4}" stroke="{INK_3}" stroke-width="1.5"/>')
    out.append(f'<text x="{lx + 28}" y="{ly}" font-size="11.5" fill="{INK}">Biên Pareto</text>')
    out.append(f'<text x="{GAP}" y="{LEGEND_H - 12}" font-size="11" fill="{INK_2}">Trục hoành: token trung bình mỗi '
               f'câu, thang log, cùng thang cho mọi ô. Mỗi ô so các chính sách trên cùng một tập câu.</text>')
    for index, panel in enumerate(panels):
        row, col = divmod(index, columns)
        x0 = GAP + col * (PANEL_W + GAP)
        y0 = LEGEND_H + row * (PANEL_H + GAP)
        out.extend(panel_svg(panel, x0, y0, x_range))
    out.append(f'<text x="{GAP}" y="{height - 12}" font-size="10.5" fill="{INK_2}">{escape(footnote)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


FIGURES = (
    ("hinh_4_1_router_chat_luong_chi_phi.svg", "Hình 4.1. Chất lượng theo chi phí của các router đã đăng ký",
     router_panels, 2, "Nguồn: report đã đăng ký của MC-93 đến MC-96 (lượt chính). Trần định tuyến của MC-93 không có "
                       "số token."),
    ("hinh_4_2_vong_tu_sua_chat_luong_chi_phi.svg", "Hình 4.2. Hỏi bao nhiêu lần: điểm theo token của năm chính sách",
     loop_panels, 2, "Nguồn: phân tích sau (thăm dò) trên các lượt đã ghi của MC-104 và MC-105; 3 vòng là chính sách đã "
                     "đăng ký."),
    ("hinh_4_3_bang_chung_luat_chat_luong_chi_phi.svg",
     "Hình 4.3. Bằng chứng pháp luật và agent: điểm theo token", evidence_panels, 3,
     "Nguồn: MC-111 (điểm tính lại từ scores, khớp report), report đã đăng ký của MC-114. Chọn rồi trả lời gồm cả "
     "lượt chọn."),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quality-versus-cost figures for chapter 4 (stdlib SVG).")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    missing = [str(path) for path in SOURCES.values() if not path.is_file()]
    if missing:
        raise SystemExit(f"Error: missing inputs {missing}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for file_name, title, build, columns, footnote in FIGURES:
        panels = build()
        (args.out_dir / file_name).write_text(figure_svg(title, panels, columns, footnote), encoding="utf-8")
        for panel in panels:
            front = {id(p) for p in pareto(panel.points)}
            for p in panel.points:
                rows.append({"figure": file_name, "panel": panel.title, "card": panel.card, "metric": panel.y_label,
                             "policy": p.label, "family": p.family, "oracle": p.oracle,
                             "mean_tokens_per_item": round(p.tokens, 1), "score": round(p.score, 2),
                             "on_pareto": id(p) in front})
        print(f"wrote {args.out_dir / file_name}")
    with (args.out_dir / "chat_luong_chi_phi.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    sources = {name: {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)} for name, path in SOURCES.items()}
    (args.out_dir / "chat_luong_chi_phi_sources.json").write_text(json.dumps(sources, indent=2) + "\n",
                                                                  encoding="utf-8")
    print(f"wrote {len(rows)} points to {args.out_dir / 'chat_luong_chi_phi.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
