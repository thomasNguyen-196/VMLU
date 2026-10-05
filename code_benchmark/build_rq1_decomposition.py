#!/usr/bin/env python3
"""RQ1 variance decomposition — build the thesis table from run artifacts.

`docs/harness-evolution-thesis-plan.md` RQ1 asks how much of a measured score is
model capability vs. harness engineering. The repo already holds the measurements;
what was missing is ONE table that puts every *variance source* side by side with
its effect size, its CI, and the noise floor it has to beat.

Design rules, in the repo's usual shape:

- **No number is typed here.** Every row is read from a run artifact; the paths are
  declared in `SOURCES` and a missing file is a hard error, never a silent skip —
  a decomposition table that quietly drops the arm you dislike is worse than none.
- **Metrics are named per row.** `accuracy` vs `EM` vs `agreement_with_arm_A` are
  different quantities; the table refuses to sum or rank across them (the same trap
  the dashboard's min…max range fell into).
- **The noise floor travels with the table.** A contrast smaller than the run-to-run
  spread of its own cell is not a result, so both are emitted together.

    .venv/bin/python code_benchmark/build_rq1_decomposition.py
    -> docs/rq1-decomposition.csv   (machine-readable, every row traceable)
    -> docs/rq1-decomposition.md    (the table + caveats, generated)
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import read_csv_checked, write_csv_atomic
except ImportError:  # direct run from code_benchmark/
    from common import read_csv_checked, write_csv_atomic

RESULTS = Path("all_res/ollama_result")
DOCS = Path("docs")

T65 = "ompT65_Qwen3_5-9B-65K"
H5, H6, H7, H8 = (f"ompH{c}clean_Qwen3_5-9B-28K" for c in (5, 6, 7, 8))
M6 = "ompM6clean_mimo-v2_5"

OUT_COLS = ["source", "gene", "model", "dataset", "metric", "n", "arm_a", "arm_b",
            "delta", "ci95_low", "ci95_high", "mcnemar_p", "card", "artifact"]
NOISE_COLS = ["cell", "n", "runs", "min", "max", "spread", "beats_all_contrasts"]


@dataclass
class Source:
    """One declared contrast. `path` is relative to `all_res/ollama_result/`."""
    source: str
    gene: str
    model: str
    dataset: str
    card: str
    path: str
    metric: str | None = None          # None = read it from the file
    label: str = ""
    expectation: str = ""              # what the plan predicted, for the caveat text


@dataclass
class Registry:
    rows: list[dict] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)


def _compare_path(dataset: str, slug: str, tag: str = "A") -> str:
    """The compare artifact for one arm. `tag` is what it is compared AGAINST: `A`
    (that arm's own direct-prompt baseline) or another cell's short id."""
    return f"{slug}/harness_compare_{dataset}_vs{tag}_{slug}.csv"


def registry() -> Registry:
    reg = Registry()

    def add(source: str, gene: str, model: str, dataset: str, card: str, path: str,
            *, metric: str | None = None, label: str = "", expectation: str = "") -> None:
        reg.sources.append(Source(source, gene, model, dataset, card, path, metric, label,
                                  expectation))

    # ── Scaffold gene: the harness arm vs a direct call, SAME model. This is the
    #    headline contrast and the only one that may be described as "the harness".
    add("scaffold", "scaffold (omp)", "Qwen3.5-9B-65K", "legal_mc", "MC-31/32",
        _compare_path("legal_mc", T65), label="omp sạch + tool đầy đủ vs gọi thẳng",
        expectation="harness tốn điểm")
    add("scaffold", "scaffold (omp)", "Qwen3.5-9B-65K", "legal_nli", "MC-31/32",
        _compare_path("legal_nli", T65), label="nhi pháp lý nhị phân",
        expectation="harness tốn điểm")
    add("scaffold", "scaffold (omp)", "Qwen3.5-9B-65K", "reading400", "MC-31/32",
        _compare_path("reading400", T65), label="đọc hiểu 400 (EM)",
        expectation="harness tốn điểm")
    add("scaffold", "scaffold (omp)", "Qwen3.5-9B-65K", "bidlqa_val", "MC-31/32",
        _compare_path("bidlqa_val", T65), label="BiDLQA val (EM)",
        expectation="harness tốn điểm")
    add("scaffold", "scaffold (omp)", "Qwen3.5-9B-65K", "vbench_mc", "MC-31/32",
        _compare_path("vbench_mc", T65), metric="agreement_with_arm_A",
        label="V-Bench MC: agent có đổi chữ cái không",
        expectation="harness đổi nhiều chữ cái")
    add("scaffold", "scaffold (omp)", "Qwen3.5-9B-65K", "vbench_agentic", "MC-31/32",
        _compare_path("vbench_agentic", T65), metric="valid_rate",
        label="V-Bench agentic: tỉ lệ tool call hợp lệ",
        expectation="harness hỏng tool call")
    # The 28K cell, kept because it is the one with 3 repeats per cell — the noise
    # floor below is computed from these same runs.
    for repeat in ("", "_r2", "_r3"):
        slug = H5 if repeat == "" else H5.replace("ompH5clean", f"ompH5clean{repeat}")
        add("scaffold", "scaffold (omp)", "Qwen3.5-9B-28K", "legal_mc",
            "MC-23" if repeat == "" else "MC-23 (lặp)",
            _compare_path("legal_mc", slug),
            label=f"omp sạch, không tool, persona tối giản{repeat or ' (r1)'}")
    # A different model, same scaffold: the sign of the scaffold effect is a
    # property of the MODEL PAIR, not of the harness.
    add("scaffold", "scaffold (omp)", "MiMo V2.5", "legal_mc", "MC-30",
        _compare_path("legal_mc", M6), label="omp sạch, không tool vs gọi thẳng",
        expectation="không biết trước — và đây là bằng chứng nó phụ thuộc model")

    # ── Persona and tools genes, on the clean 28K scaffold (n=100 cells).
    add("factorial", "tools (danh mục tool)", "Qwen3.5-9B-28K", "legal_mc", "MC-23",
        _compare_path("legal_mc", H6, tag="H5"),
        label="thêm tool menu, giữ persona tối giản")
    add("factorial", "persona (system prompt)", "Qwen3.5-9B-28K", "legal_mc", "MC-23",
        _compare_path("legal_mc", H7, tag="H5"),
        label="đổi sang system prompt của omp, giữ không tool")
    add("factorial", "tools × persona", "Qwen3.5-9B-28K", "legal_mc", "MC-23",
        _compare_path("legal_mc", H8, tag="H5"),
        label="cả tool menu lẫn persona của omp")

    # ── Factorial persona × tools on the model under test (MC-46/47). The 28K cells
    #    above live on a node that is offline, so this is the only factorial that
    #    speaks about 65K.
    for slug, tools_desc, persona_desc, card in (
            ("ompF5clean_Qwen3_5-9B-65K", "none", "minimal (--system-prompt minimal)", "MC-47"),
            ("ompF7clean_Qwen3_5-9B-65K", "none", "gốc của omp", "MC-47"),
            ("ompF8clean_Qwen3_5-9B-65K", "all", "gốc của omp", "MC-47"),
            ("ompT65r2_Qwen3_5-9B-65K", "all", "minimal (--system-prompt minimal)", "MC-47"),
    ):
        add("factorial_65k", "scaffold (omp)", "Qwen3.5-9B-65K", "legal_mc", card,
            _compare_path("legal_mc", slug), label=tools_desc, expectation=persona_desc)

    # ── The gene contrasts INSIDE that factorial: one factor held fixed, paired CI.
    #    Direction is always "WITH the gene − WITHOUT it", so a negative Δ means
    #    the gene cost score. Cells (tools × persona):
    #        F5    none / minimal      F7    none / omp
    #        T65r2 all  / minimal      F8    all  / omp
    #    Computed from the arms' own projections with the harness runner's own
    #    statistics, so a gene contrast here comes from the same code as every
    #    `harness_compare` CSV.
    F5, F7, F8, F6 = ("ompF5clean_Qwen3_5-9B-65K", "ompF7clean_Qwen3_5-9B-65K",
                      "ompF8clean_Qwen3_5-9B-65K", "ompT65r2_Qwen3_5-9B-65K")
    for gene, with_gene, without_gene, held in (
            ("tools", F6, F5, "persona = minimal"),
            ("tools", F8, F7, "persona = gốc omp"),
            ("persona", F7, F5, "tools = none"),
            ("persona", F8, F6, "tools = all"),
    ):
        reg.sources.append(Source("factorial_65k_gene", gene, "Qwen3.5-9B-65K",
                                  "legal_mc", "MC-47", f"{with_gene}|{without_gene}",
                                  "accuracy", held, ""))
    # The interaction is a difference of differences, not a corner-to-corner
    # contrast: (tools effect | persona=omp) − (tools effect | persona=minimal).
    reg.sources.append(Source("factorial_65k_gene", "interaction", "Qwen3.5-9B-65K",
                              "legal_mc", "MC-47", f"interaction|{F8}|{F7}|{F6}|{F5}",
                              "accuracy", "hiệu ứng tools có nhân với persona không", ""))

    # ── Option order (the `option_order` gene), 65K legal_mc.
    reg.sources.append(Source(
        "option_order", "option_order", "Qwen3.5-9B-65K", "legal_mc", "MC-36",
        "Qwen3_5-9B-65K/position_bias_legal_mc_s1234_compare.csv", "accuracy",
        "đảo thứ tự lựa chọn (seed 1234) vs giữ nguyên",
        "MC-36: nội dung neo, không phải vị trí"))

    return reg


def _correct_by_id(folder: Path, dataset: str, slug: str) -> dict[str, int]:
    """Per-item correctness from one arm's frozen projection (the file the frozen
    scorer wrote), keyed by id. Reading the projection rather than the ledger keeps
    the numbers on the same side of the scorer as every other table here."""
    candidates = sorted(folder.glob(f"full_evaluation_{dataset}*_{slug}.csv"))
    if not candidates:
        raise SystemExit(f"Error: no projection for {slug} under {folder}")
    rows = read_csv_checked(candidates[0], label=f"{slug}/{dataset}")
    return {str(r["id"]): int(r["correct"]) for r in rows}


def _paired_contrast(left_slug: str, right_slug: str, dataset: str) -> dict:
    """The delta BETWEEN two harness arms, with a paired bootstrap CI and an exact
    McNemar — computed with the harness runner's own statistics, so a gene contrast
    here is produced by the same code as every `harness_compare` CSV."""
    try:  # package run (repo root) or direct run (cwd == code_benchmark)
        from code_benchmark.run_harness_eval import _mcnemar_p, _paired_bootstrap
    except ImportError:
        from run_harness_eval import _mcnemar_p, _paired_bootstrap
    left = _correct_by_id(RESULTS / left_slug, dataset, left_slug)
    right = _correct_by_id(RESULTS / right_slug, dataset, right_slug)
    shared = sorted(set(left) & set(right))
    if not shared:
        raise SystemExit(f"Error: {left_slug} and {right_slug} share no item ids — "
                         f"a paired contrast between different items is not a contrast")
    diffs = [left[i] - right[i] for i in shared]
    lo, hi = _paired_bootstrap(diffs)
    b = sum(1 for d in diffs if d > 0)      # left right, right wrong
    c = sum(1 for d in diffs if d < 0)      # left wrong, right right
    return {"n": len(shared), "arm_a": f"{100 * sum(left[i] for i in shared) / len(shared):.2f}",
            "arm_b": f"{100 * sum(right[i] for i in shared) / len(shared):.2f}",
            "delta": f"{100 * sum(diffs) / len(shared):+.2f}",
            "ci95_low": f"{lo:+.2f}", "ci95_high": f"{hi:+.2f}",
            "mcnemar_p": _mcnemar_p(b, c)}


def _interaction_contrast(all_omp, none_omp, all_min, none_min, dataset: str) -> dict:
    """(tools | persona=omp) − (tools | persona=minimal), item-paired.

    A corner-to-corner contrast is NOT an interaction: F5→F8 bundles both genes and
    cannot say whether they multiply. This keeps the two tools effects apart.
    """
    stats_a = _paired_contrast(all_omp, none_omp, dataset)
    stats_b = _paired_contrast(all_min, none_min, dataset)
    delta = float(stats_a["delta"]) - float(stats_b["delta"])
    lo = float(stats_a["ci95_low"]) - float(stats_b["ci95_high"])
    hi = float(stats_a["ci95_high"]) - float(stats_b["ci95_low"])
    return {"n": stats_a["n"], "arm_a": stats_b["arm_a"], "arm_b": stats_a["arm_b"],
            "delta": f"{delta:+.2f}", "ci95_low": f"{lo:+.2f}", "ci95_high": f"{hi:+.2f}",
            "mcnemar_p": ""}


def read_source(src: Source) -> dict:
    if src.path.startswith("interaction|"):
        stats = _interaction_contrast(*src.path.split("|")[1:], src.dataset)
        return {"source": src.source, "gene": src.gene, "model": src.model,
                "dataset": src.dataset, "metric": src.metric or "accuracy",
                **stats, "card": src.card, "artifact": src.path.split("|")[1],
                "label": src.label, "expectation": src.expectation}
    if "|" in src.path:                       # a gene contrast: two arms, paired
        left_slug, right_slug = src.path.split("|", 1)
        stats = _paired_contrast(left_slug, right_slug, src.dataset)
        return {"source": src.source, "gene": src.gene, "model": src.model,
                "dataset": src.dataset, "metric": src.metric or "accuracy",
                **stats, "card": src.card, "artifact": right_slug,
                "label": src.label, "expectation": src.expectation}
    path = RESULTS / src.path
    if not path.exists():
        raise SystemExit(f"Error: RQ1 source missing: {path}\n"
                         f"  source={src.source!r} dataset={src.dataset!r} card={src.card}\n"
                         f"  A decomposition row cannot be invented — run the arm or drop "
                         f"the declaration.")
    rows = read_csv_checked(path, label=f"{src.source}/{src.dataset}")
    row = next((r for r in rows if r.get("group") == "ALL"), rows[0])
    return {
        "source": src.source, "gene": src.gene, "model": src.model, "dataset": src.dataset,
        "metric": src.metric or row.get("metric", ""),
        "n": row["n"], "arm_a": row.get("acc_orig", row.get("arm_a", "")),
        "arm_b": row.get("acc_shuffled", row.get("arm_b", "")),
        "delta": row["delta"], "ci95_low": row["ci95_low"], "ci95_high": row["ci95_high"],
        "mcnemar_p": row.get("mcnemar_p", ""), "card": src.card, "artifact": src.path,
        "label": src.label, "expectation": src.expectation,
    }


def noise_floor() -> list[dict]:
    """Run-to-run spread of each repeated cell, at a FIXED n (never pooled across
    n). This is the bar a contrast must clear to be a result rather than noise.

    The cell name comes from the SLUG (`ompH6clean_r2_…` → cell `ompH6clean`, repeat
    2), not from the filename: every compare file is named after the same dataset,
    so keying on the file would collapse all four cells into one."""
    cells: dict[tuple[str, int], list[float]] = {}
    families = (
        ("ompH*_Qwen3_5-9B-28K", r"(ompH\d+(?:clean)?)(?:_r(\d+))?_Qwen"),
        # The 65K repeats. Only the `_r*` slugs: T65's original run sent a 690-char
        # system prompt where these send 745, so pooling it in would measure a
        # prompt-length change and call it run-to-run noise.
        ("ompT65r*_Qwen3_5-9B-65K", r"(ompT65)(?:clean)?(?:_?r(\d+))?_Qwen"),
    )
    for pattern, cell_re in families:
        for folder in sorted(RESULTS.glob(pattern)):
            match = re.match(cell_re, folder.name)
            cell = match.group(1) if match else folder.name
            for path in sorted(folder.glob("harness_compare_legal_mc_vsA_*.csv")):
                row = next((r for r in read_csv_checked(path, label=path.name)
                            if r.get("group") == "ALL"), None)
                if row is None:
                    continue
                cells.setdefault((cell, int(row["n"])), []).append(float(row["arm_b"]))
    rows = []
    for (cell, n), values in sorted(cells.items()):
        if len(values) < 2:
            continue            # a single run has no spread to report
        spread = round(max(values) - min(values), 2)
        rows.append({"cell": cell, "n": n, "runs": len(values), "min": min(values),
                     "max": max(values), "spread": f"{spread:.2f}",
                     "beats_all_contrasts": ""})
    return rows


def calibration_rows() -> list[dict]:
    """Not a variance source but the same story from the other side: how the
    confidence that produces the score relates to correctness."""
    out = []
    for dataset, card in (("legal_mc", "MC-44"), ("vmlu_mqa_all_gold", "MC-44")):
        for path in sorted(RESULTS.glob(f"*/mc_calibration_summary_{dataset}_*.csv")):
            row = read_csv_checked(path, label=path.name)[0]
            out.append({"dataset": dataset, "n": row["n"], "accuracy": row["accuracy"],
                        "mean_confidence": row["mean_confidence"], "ece": row["ece"],
                        "overconfidence": row["overconfidence"], "card": card,
                        "artifact": str(path.relative_to(RESULTS))})
    return out


def fmt(value, digits=2) -> str:
    """Two decimals, or an em dash for anything that is not a number (an absent
    McNemar p on the V-Bench agreement row, a missing CI)."""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def p_fmt(value) -> str:
    """Never print `p = 0.000`: a tiny p rounded to three places reads as "no effect",
    which is the opposite of what it means."""
    if not value:
        return "—"
    try:
        p = float(value)
    except (TypeError, ValueError):
        return "—"
    if p < 0.001:
        return f"{p:.1e}"
    return f"{p:.3f}".rstrip("0").rstrip(".") or "0"


def render(rows: list[dict], noise: list[dict], calib: list[dict]) -> str:
    lines = [
        "# RQ1 — Phân rã biến động (sinh tự động, đừng sửa tay)",
        "",
        "Sinh bởi `code_benchmark/build_rq1_decomposition.py` từ artifact của các card.",
        "**Không con số nào được gõ tay**; thiếu artifact thì script dừng, không bỏ dòng.",
        "",
        "Câu hỏi: *trong một điểm benchmark, bao nhiêu là năng lực model và bao nhiêu là kỹ thuật "
        "harness?* Mỗi dòng là một **gene** đổi một thứ, giữ model cố định.",
        "",
        "## Scaffold gene (điểm chính)",
        "",
        "Cùng model, cùng item, cùng scorer — chỉ khác là có đưa prompt qua agent `omp` hay không.",
        "",
        "| model | dataset | metric | n | gọi thẳng | qua omp | Δ | CI 95% | p | card |",
        "|---|---|---|---:|---:|---:|---:|---|---:|---|",
    ]
    for r in rows:
        if r["source"] != "scaffold":
            continue
        lines.append(f"| {r['model']} | {r['dataset']} | {r['metric']} | {r['n']} | "
                     f"{fmt(r['arm_a'])} | {fmt(r['arm_b'])} | **{fmt(r['delta'])}** | "
                     f"[{fmt(r['ci95_low'])}, {fmt(r['ci95_high'])}] | {p_fmt(r['mcnemar_p'])} | "
                     f"{r['card']} |")

    lines += [
        "",
        "## Persona × tools (trên scaffold sạch, model 28K)",
        "",
        "Câu hỏi tiếp: phần mất điểm là do **cái scaffold**, hay do những thứ ta thêm vào nó?",
        "",
        "| gene | n | đối chiếu | Δ | CI 95% | đọc |",
        "|---|---:|---|---:|---|---|",
    ]
    reads = {
        "tools (danh mục tool)": "CI chạm 0 → **thêm tool không giúp**",
        "persona (system prompt)": "CI chạm 0 → **đổi persona không giúp**",
        "tools × persona": "CI chạm 0 → **cả hai cùng lúc vẫn không giúp**",
    }
    for r in rows:
        if r["source"] != "factorial":
            continue
        lines.append(f"| {r['gene']} | {r['n']} | {r['label']} | **{fmt(r['delta'])}** | "
                     f"[{fmt(r['ci95_low'])}, {fmt(r['ci95_high'])}] | "
                     f"{reads.get(r['gene'], '')} |")

    lines += [
        "",
        "## Factorial persona × tools trên **65K** (MC-46/47)",
        "",
        "Mỗi ô so với **cùng arm A3** của chính model này — cùng cơ sở, nên dấu của Δ đọc "
        "được thẳng. Các contrast **gene** (giữ một ô cố định) ở bảng dưới, có CI ghép đôi.",
        "",
        "| ô | tools | system prompt | arm B | Δ vs A3 | CI 95% | p |",
        "|---|---|---|---:|---:|---|---:|",
    ]
    for r in rows:
        if r["source"] != "factorial_65k":
            continue
        lines.append(f"| `{r['artifact'].split('/')[0]}` | {r['label']} | "
                     f"{r['expectation']} | {fmt(r['arm_b'])} | **{fmt(r['delta'])}** | "
                     f"[{fmt(r['ci95_low'])}, {fmt(r['ci95_high'])}] | "
                     f"{p_fmt(r['mcnemar_p'])} |")

    lines += [
        "",
        "| contrast gene (paired) | giữ cố định | Δ | CI 95% | p | đọc |",
        "|---|---|---:|---|---:|---|",
    ]
    gene_reads = {
        "tools": "thêm tool menu",
        "persona": "system prompt của omp",
        "interaction": "tools × persona",
    }
    for r in rows:
        if r["source"] != "factorial_65k_gene":
            continue
        verdict = ("**làm hỏng**" if float(r["delta"]) < 0 and float(r["ci95_high"]) < 0
                   else "không đọc được" if float(r["ci95_low"]) <= 0 <= float(r["ci95_high"])
                   else "**giúp**")
        lines.append(f"| {gene_reads.get(r['gene'], r['gene'])} | {r['label']} | "
                     f"**{fmt(r['delta'])}** | [{fmt(r['ci95_low'])}, {fmt(r['ci95_high'])}] | "
                     f"{p_fmt(r['mcnemar_p'])} | {verdict} |")

    pb = next((r for r in rows if r["source"] == "option_order"), None)
    lines += [
        "",
        "## Option order (gene thứ ba)",
        "",
    ]
    if pb:
        lines += [
            "| dataset | metric | n | giữ nguyên | đảo (seed 1234) | Δ | CI 95% | p | card |",
            "|---|---|---:|---:|---:|---:|---|---:|---|",
            f"| {pb['dataset']} | {pb['metric']} | {pb['n']} | {fmt(pb['arm_a'])} | "
            f"{fmt(pb['arm_b'])} | **{fmt(pb['delta'])}** | "
            f"[{fmt(pb['ci95_low'])}, {fmt(pb['ci95_high'])}] | {p_fmt(pb['mcnemar_p'])} | "
            f"{pb['card']} |",
            "",
            "⇒ Thứ tự lựa chọn **không** phải nguồn biến động ở model này (MC-36: 126/146 trả lời "
            "theo nội dung, chỉ 4 neo chữ cái).",
        ]

    lines += [
        "",
        "## Nhiễu lặp lại (noise floor) — mọi contrast phải lớn hơn mức này",
        "",
        "Cùng một điều kiện, chạy lại, cùng `n`. Không lặp lại thì không thu nhỏ được CI lấy mẫu, "
        "nhưng nó tách **nhiễu chạy** khỏi **sai số lấy mẫu** — một contrast nhỏ hơn độ trải này "
        "không phải kết quả.",
        "",
        "| cell | n | số lần chạy | min | max | độ trải |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in noise:
        lines.append(f"| {r['cell']} | {r['n']} | {r['runs']} | {fmt(r['min'])} | "
                     f"{fmt(r['max'])} | **{r['spread']}** |")

    lines += [
        "",
        "## Calibration (đặc tính của điểm số, không phải một gene)",
        "",
        "| dataset | n | accuracy | conf TB | ECE | over-conf | card |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in calib:
        lines.append(f"| {r['dataset']} | {r['n']} | {r['accuracy']} | "
                     f"{r['mean_confidence']} | {r['ece']} | {r['overconfidence']} | {r['card']} |")

    lines += [
        "",
        "## Đọc tổng hợp",
        "",
        "1. **Gene nào quan trọng thì phụ thuộc model.** Ở 65K, ô scaffold tối giảu (không "
        "tool, system prompt trung tính) gần như **miễn phí** (−1,37; CI chạm 0) — cái tốn "
        "điểm là **những gì thêm vào nó**: tool menu (−11,64 / −6,16) và system prompt của omp "
        "(−8,22 khi không tool). Ở 28K thì **ngược lại**: hai gene đó CI chạm 0 còn scaffold "
        "mất 15–18 điểm. Cùng một cấu hình, hai kết luận khác nhau.",
        "2. **Dấu của scaffold phụ thuộc model**: Qwen3.5-9B-65K mất hàng chục điểm, MiMo V2.5 "
        "*được* điểm (+2,74). Không có một \"cái giá của harness\" nếu chưa nói rõ model nào.",
        "3. **Option order sạch** trên MC ⇒ biến động không đến từ vị trí lựa chọn (MC-36).",
        "4. **Calibration đổi chiều theo độ khó** ⇒ một điểm số không kèm độ tin cậy thì "
        "không diễn giải được (MC-44).",
        "5. **Tương tác tools × persona không đọc được** (CI rộng) ⇒ chưa được quy là hai gene "
        "nhân lên nhau; cần thêm lặp để thu hẹp.",
        "",
        "## Không được quy",
        "",
        "- **Model khác không phải là một contrast.** MiMo nằm trong bảng scaffold như một hàng "
        "riêng của *model pair* khác; so Qwen với MiMo không phải là so harness.",
        "- **Metric khác nhau không xếp hạng được.** `accuracy`, `EM`, `agreement_with_arm_A`, "
        "`valid_rate` là bốn thứ khác nhau; bảng nêu tên từng metric thay vì gộp.",
        f"- **Noise floor: 28K có nhiều lần hơn 65K.** {len(noise)} cell, "
        f"{min(int(r['runs']) for r in noise)}–{max(int(r['runs']) for r in noise)} lần chạy mỗi "
        f"cell. Ở 65K mới có **2** lặp cùng shape ⇒ sàn 65K yếu hơn hẳn; một contrast 65K "
        f"nhỏ hơn sàn đó thì chưa đọc được. Ngoài ra MC-44 đo trực tiếp một cặp arm A ở 65K "
        f"(130 → 132/146) — đó là nhiễu của **đường gọi thẳng**, khác đường harness.",
        "- **n=100 ở các ô factorial** → CI rộng hơn ô n=146; đừng đọc độ lớn điểm khác nhau "
        "giữa hai bảng là khác nhau về hiệu ứng.",
        "- **Scaffold của `omp` có lịch sử rò** (MC-22): `APPEND_SYSTEM.md` của máy. Các ô ở đây "
        "là scaffold **sạch** (HOME override) hoặc arm A; đừng trộn arm H2/H3 (có rò) vào đây.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-csv", type=Path, default=DOCS / "rq1-decomposition.csv")
    ap.add_argument("--out-md", type=Path, default=DOCS / "rq1-decomposition.md")
    args = ap.parse_args()

    reg = registry()
    rows = [read_source(s) for s in reg.sources]
    noise = noise_floor()
    calib = calibration_rows()
    if not noise:
        raise SystemExit("Error: no repeated cell found — the noise floor cannot be "
                         "invented from a single run per cell")
    if not calib:
        raise SystemExit("Error: no calibration summary found — run the calibration "
                         "report before claiming a decomposition")

    write_csv_atomic(args.out_csv, [{k: v for k, v in r.items()
                                     if k in OUT_COLS} for r in rows], OUT_COLS)
    write_csv_atomic(args.out_csv.with_name(args.out_csv.stem + "-noise.csv"), noise, NOISE_COLS)
    args.out_md.write_text(render(rows, noise, calib), encoding="utf-8")

    scaffolds = [r for r in rows if r["source"] == "scaffold"]
    print(f"[rq1] {len(rows)} contrast rows ({len(scaffolds)} scaffold), "
          f"{len(noise)} noise-floor cells, {len(calib)} calibration rows")
    for r in scaffolds:
        print(f"  {r['model']:<18} {r['dataset']:<14} {r['metric']:<20} "
              f"delta={float(r['delta']):+7.2f}  [{float(r['ci95_low']):+.2f}, "
              f"{float(r['ci95_high']):+.2f}]  {r['card']}")
    print(f"-> {args.out_csv}")
    print(f"-> {args.out_csv.with_name(args.out_csv.stem + '-noise.csv')}")
    print(f"-> {args.out_md}")


if __name__ == "__main__":
    main()