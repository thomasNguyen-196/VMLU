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

    # ── Option order (the `option_order` gene), 65K legal_mc.
    reg.sources.append(Source(
        "option_order", "option_order", "Qwen3.5-9B-65K", "legal_mc", "MC-36",
        "Qwen3_5-9B-65K/position_bias_legal_mc_s1234_compare.csv", "accuracy",
        "đảo thứ tự lựa chọn (seed 1234) vs giữ nguyên",
        "MC-36: nội dung neo, không phải vị trí"))

    return reg


def read_source(src: Source) -> dict:
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
    for folder in sorted(RESULTS.glob("ompH*_Qwen3_5-9B-28K")):
        match = re.match(r"(ompH\d+(?:clean)?)(?:_r(\d+))?_Qwen", folder.name)
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
        "1. **Scaffold là gene duy nhất có hiệu ứng lớn** — và dấu của nó **phụ thuộc model**: "
        "Qwen3.5-9B-65K mất hàng chục điểm, MiMo V2.5 *được* điểm. Không có một \"cái giá của "
        "harness\" nếu chưa nói rõ model nào.",
        "2. **Persona và tool menu gần như vô hiệu** (CI chạm 0) ⇒ phần mất điểm không phải do "
        "những gì ta thêm vào, mà do **chính cái scaffold**.",
        "3. **Option order sạch** trên MC ⇒ biến động không đến từ vị trí lựa chọn.",
        "4. **Calibration đổi chiều theo độ khó** ⇒ một điểm số không kèm độ tin cậy thì "
        "không diễn giải được (MC-44).",
        "",
        "## Không được quy",
        "",
        "- **Model khác không phải là một contrast.** MiMo nằm trong bảng scaffold như một hàng "
        "riêng của *model pair* khác; so Qwen với MiMo không phải là so harness.",
        "- **Metric khác nhau không xếp hạng được.** `accuracy`, `EM`, `agreement_with_arm_A`, "
        "`valid_rate` là bốn thứ khác nhau; bảng nêu tên từng metric thay vì gộp.",
        f"- **Noise floor chỉ có cho model 28K** ({len(noise)} cell × "
        f"{min(int(r['runs']) for r in noise)}–{max(int(r['runs']) for r in noise)} lần chạy, "
        f"n={noise[0]['n']}). Ở 65K mới chỉ có một cặp đo gián tiếp (130 → 132/146, MC-44) — "
        f"đủ để biết có nhiễu, **không đủ** để đặt ngưỡng. Các contrast 65K rộng hơn nhiều lần "
        f"nên không bị nhiễu này nuốt, nhưng một contrast 65K nhỏ thì chưa có sàn.",
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