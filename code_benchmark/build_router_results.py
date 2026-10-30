"""Publish the router and diagnosis experiments (MC-90 to MC-103) for the /table page.

NO NUMBER IS TYPED HERE. Every score, interval and p-value is read from the registered analysis report of its card
(under the gitignored all_res/), and each report's SHA-256 is published beside the numbers it gave. The wording
(question, verdict text) is editorial and written for a known outcome: each verdict's status is computed from the
report's own fields, and the build stops if a report no longer supports the published wording.

Each experiment ran on its own items, so the page shows one table per experiment, never one matrix across them.

  .venv/bin/python code_benchmark/build_router_results.py   ->  web/data/router-results.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("web/data/router-results.json")
ALPHA = 0.05
STATUSES = ("met", "partial", "not_met", "descriptive")
ROLES = ("candidate", "baseline", "ceiling", "reference")
QWEN = "Qwen3.5-9B-65K (IEC)"
REPORTS = {
    "wide": "all_res/diagnostic_prospective/wide/qwen3-5-9b-65k-prospective/analysis/report.json",
    "wide_s2": ("all_res/diagnostic_prospective/wide-supplements/wide-s-r2/qwen3-5-9b-65k-prospective/analysis/"
                "s_noise_report.json"),
    "core": "all_res/diagnostic_prospective/core/qwen3-5-9b-65k-prospective/analysis/router_report.json",
    "v2": "all_res/diagnostic_router_v2/heldout/qwen3-5-9b-65k-prospective/analysis/router_v2_report.json",
    "v3": "all_res/diagnostic_router_v3/heldout/qwen3-5-9b-65k-prospective/analysis/router_v3_report.json",
    "k2": "all_res/diagnostic_k2/heldout/qwen3-5-9b-65k-prospective/analysis/k2_report.json",
    "menu": "all_res/diagnostic_llm_router/menu/qwen3-5-9b-65k-prospective/analysis/menu_report.json",
    "labels": "all_res/diagnostic_llm_router/labels/muse-spark-1-3-contributor/analysis/router_labels_report.json",
    "oracle": "all_res/diagnostic_legal_oracle/run/qwen3-5-9b-65k-prospective/analysis/legal_oracle_report.json",
    "retrieval": ("all_res/diagnostic_legal_retrieval/run/qwen3-5-9b-65k-prospective/analysis/"
                  "legal_retrieval_report.json"),
    "critic": "all_res/diagnostic_router_loop/critic/muse-spark-1-3-contributor/analysis/router_critic_report.json",
    "weakness": "all_res/diagnostic_router_loop/weakness_map/mimo-v2-6-flash/analysis/weakness_map_report.json",
    "reading_v3": "all_res/diagnostic_router_loop/reading_v3/reading_v3_report.json",
}
ARM_LABELS = {"always_B": "luôn B", "always_S": "luôn S", "v2_cascade": "router v2", "B": "B", "S": "S", "Q": "Q"}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


class Sources:
    """Reads each registered report once and remembers the SHA-256 of the bytes it read."""

    def __init__(self, root: Path) -> None:
        self.root, self.data, self.hashes = root, {}, {}

    def __call__(self, key: str) -> dict[str, Any]:
        if key not in self.data:
            path = self.root / REPORTS[key]
            if not path.is_file():
                raise _fail(f"missing registered report {REPORTS[key]}")
            raw = path.read_bytes()
            self.data[key] = json.loads(raw)
            self.hashes[key] = hashlib.sha256(raw).hexdigest()
        return self.data[key]

    def refs(self, *keys: str) -> list[dict[str, str]]:
        return [{"path": REPORTS[key], "sha256": self.hashes[key]} for key in keys]


def expect(card: str, report: dict[str, Any], **fields: Any) -> None:
    for key, value in fields.items():
        if report.get(key) != value:
            raise _fail(f"{card}: report field {key} is {report.get(key)!r}, expected {value!r}")


def pts(value: float) -> float:
    return round(100 * value, 2)


def cell(score: float, ci: list[float] | None = None, tokens: float | None = None) -> dict[str, Any]:
    return {"score": round(score, 2), "ci": [round(ci[0], 2), round(ci[1], 2)] if ci else None,
            "tokens": round(tokens, 1) if tokens is not None else None}


def column(column_id: str, label: str, metric: str, n: int) -> dict[str, Any]:
    return {"id": column_id, "label": label, "metric": metric, "n": n}


def row(row_id: str, label: str, role: str, cells: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"id": row_id, "label": label, "role": role, "cells": cells}


def table(title: str, columns: list[dict[str, Any]], rows: list[dict[str, Any]], note: str = "") -> dict[str, Any]:
    return {"title": title, "columns": columns, "rows": rows, "note": note}


def test(label: str, *, diff: float | None = None, ci: list[float] | None = None, p: float | None = None,
         p_kind: str = "", note: str = "", primary: bool = False) -> dict[str, Any]:
    return {"label": label, "diff": round(diff, 2) if diff is not None else None,
            "ci": [round(ci[0], 2), round(ci[1], 2)] if ci else None, "p": p, "p_kind": p_kind, "note": note,
            "primary": primary}


def settle(card: str, computed: str, published: str) -> str:
    """The published wording was written for one outcome; stop if the report now says otherwise."""
    if computed != published:
        raise _fail(f"{card}: the report gives status {computed}, the published wording says {published}")
    return computed


def better(p_holm: float, gain: float) -> bool:
    return p_holm < ALPHA and gain > 0


# ---------------------------------------------------------------- experiments

def wide(src: Sources) -> dict[str, Any]:
    report, s2 = src("wide"), src("wide_s2")
    expect("MC-90", report, phase="wide", plan_id="diagnostic-prospective-analysis-v1")
    arms = {family: report["families"][family]["arms"]["S"] for family in ("mc", "reading")}
    stable = {family: s2["families"][family]["stable_wins"] for family in ("mc", "reading")}
    columns = [column("mc", "Legal MC + Legal NLI", "Tỷ lệ đúng", arms["mc"]["n_pairs"]),
               column("reading", "ViBidLQA, Vi-DROP, Vi-SQuAD", "EM", arms["reading"]["n_pairs"])]
    rows = [row("B", "B: hỏi thẳng", "baseline",
                {family: cell(100 * arm["baseline_correct"] / arm["n_pairs"]) for family, arm in arms.items()}),
            row("S", "S: suy luận từng bước", "candidate",
                {family: cell(100 * (arm["both_correct"] + arm["rescues"]) / arm["n_pairs"])
                 for family, arm in arms.items()})]
    tests = [test(f"S so với B, {label}, một lượt", diff=100 * arms[family]["net_gain"],
                  ci=arms[family]["net_gain_ci95_pct"], p=arms[family]["mcnemar_p_holm"], p_kind="McNemar, Holm")
             for family, label in (("reading", "đọc hiểu"), ("mc", "trắc nghiệm luật"))]
    tests += [test(f"S hơn B ổn định qua hai lượt, {label} (MC-92)", p=stable[family]["sign_test_p_holm"],
                   p_kind="dấu, Holm", primary=True,
                   note=f"S thắng ở cả hai lượt {stable[family]['s_stable_better']} câu, "
                        f"B thắng ở cả hai lượt {stable[family]['b_stable_better']} câu")
              for family, label in (("reading", "đọc hiểu"), ("mc", "trắc nghiệm luật"))]
    systematic = any(better(entry["sign_test_p_holm"], entry["s_stable_better"] - entry["b_stable_better"])
                     for entry in stable.values())
    return {"id": "mc-90-92", "cards": "MC-90, MC-91, MC-92", "title": "B và S trên tập wide",
            "question": "Bảo Qwen suy luận từng bước (S) có hơn hỏi thẳng (B) không?",
            "student": QWEN, "items": "1.239 câu wide, mỗi cách hỏi hai lượt; dùng để thiết kế router",
            "status": settle("MC-90", "met" if systematic else "not_met", "not_met"),
            "verdict": ("Trong một lượt, S hơn B ở đọc hiểu, còn ở trắc nghiệm luật thì không. Phép thử đã đăng ký "
                        "\"S hơn B ổn định qua hai lượt\" không đạt, nên chưa gọi được là hơn có hệ thống."),
            "tables": [table("Điểm của lượt đầu", columns, rows)], "tests": tests,
            "notes": ["Tỷ lệ đúng của đọc hiểu tính bằng EM (khớp hoàn toàn), theo protocol của chiến dịch."],
            "sources": src.refs("wide", "wide_s2")}


def core(src: Sources) -> dict[str, Any]:
    report = src("core")
    expect("MC-93", report, rule_id="router-c1-drop-s")
    primary = report["primary"]
    policies = primary["policies"]
    labels = {"router": ("Router v1: Vi-DROP dùng S, còn lại B", "candidate"), "always_B": ("Luôn B", "baseline"),
              "always_S": ("Luôn S", "baseline")}
    columns = [column("core", "60 câu core (5 bộ)", "Tỷ lệ đúng", primary["anchors"])]
    rows = [row(name, label, role, {"core": cell(pts(policies[name]["accuracy"]), policies[name]["accuracy_ci95_pct"],
                                                 policies[name]["mean_total_tokens"])})
            for name, (label, role) in labels.items()]
    tests = [test(f"Router v1 so với {label}", diff=pts(policies["router"]["accuracy"] - policies[other]["accuracy"]),
                  p=primary["tests"][key]["mcnemar_p_holm"], p_kind="McNemar, Holm", primary=True,
                  note=f"cứu {primary['tests'][key]['rescues']} câu, làm hỏng {primary['tests'][key]['regressions']} câu")
             for key, other, label in (("router_vs_always_B", "always_B", "luôn B"),
                                       ("router_vs_always_S", "always_S", "luôn S"))]
    wins = [better(primary["tests"][key]["mcnemar_p_holm"], policies["router"]["accuracy"] - policies[other]["accuracy"])
            for key, other in (("router_vs_always_B", "always_B"), ("router_vs_always_S", "always_S"))]
    computed = "met" if all(wins) else "partial" if any(wins) else "not_met"
    return {"id": "mc-93", "cards": "MC-93", "title": "Router v1 trên core",
            "question": "Luật viết tay \"câu Vi-DROP dùng S, còn lại dùng B\" có hơn một cách cố định không?",
            "student": QWEN, "items": "60 câu core đã audit, đánh giá đúng một lần",
            "status": settle("MC-93", computed, "not_met"),
            "verdict": "Router đúng nhiều câu hơn cả luôn B và luôn S nhưng chưa đủ chắc: 60 câu quá ít để tách các cách.",
            "tables": [table("Kết quả", columns, rows)], "tests": tests, "notes": [],
            "sources": src.refs("core")}


def router_v2(src: Sources) -> dict[str, Any]:
    report = src("v2")
    expect("MC-94", report, plan_id="diagnostic-router-v2-heldout-v1", primary_family="mc", primary_rotation=1)
    mc, reading = (report["families"][family]["rotations"]["1"] for family in ("mc", "reading"))
    labels = {"v2": ("Router v2: hỏi B hai lần, lệch thì S", "candidate"),
              "always_B": ("Luôn B (= router v1 trên tập này)", "baseline"), "always_S": ("Luôn S", "baseline")}
    columns = [column("vmlu", "VMLU valid", "Tỷ lệ đúng", mc["items"]),
               column("bidlqa", "ViBidLQA val", "Token-F1", reading["items"])]
    rows = [row(name, label, role, {
        "vmlu": cell(pts(mc["policies"][name]["accuracy"]), mc["policies"][name]["accuracy_ci95_pct"],
                     mc["policies"][name]["mean_total_tokens"]),
        "bidlqa": cell(pts(reading["mean_token_f1"][name]), None, reading["policies"][name]["mean_total_tokens"])})
        for name, (label, role) in labels.items()]
    gain = {other: mc["policies"]["v2"]["accuracy"] - mc["policies"][other]["accuracy"] for other in ("always_B", "always_S")}
    tests = [test(f"Router v2 so với {ARM_LABELS[other]}, VMLU", diff=pts(gain[other]),
                  p=mc["tests"][f"v2_vs_{other}"]["mcnemar_p_holm"], p_kind="McNemar, Holm", primary=True)
             for other in ("always_B", "always_S")]
    wins = [better(mc["tests"][f"v2_vs_{other}"]["mcnemar_p_holm"], gain[other]) for other in ("always_B", "always_S")]
    computed = "met" if all(wins) else "partial" if any(wins) else "not_met"
    return {"id": "mc-94", "cards": "MC-94", "title": "Router v2 trên câu mới",
            "question": "Thêm tín hiệu \"hỏi B hai lần, lệch thì chuyển sang S\" có làm router tốt hơn không?",
            "student": QWEN, "items": "600 câu chưa router nào thấy; phép thử chính là trắc nghiệm, vòng 1",
            "status": settle("MC-94", computed, "partial"),
            "verdict": ("Router v2 hơn luôn B rõ ràng, tốn khoảng một nửa token so với luôn S, "
                        "nhưng vẫn kém luôn S trên VMLU."),
            "tables": [table("Kết quả vòng 1", columns, rows)], "tests": tests,
            "notes": [f"Tỷ lệ câu chuyển sang S: VMLU {pts(mc['escalated_share']):.0f}%, "
                      f"ViBidLQA {pts(reading['escalated_share']):.0f}%."],
            "sources": src.refs("v2")}


def router_v3(src: Sources) -> dict[str, Any]:
    report = src("v3")
    expect("MC-95", report, primary_family="mc", primary_rotation=1)
    mc, reading = (report["families"][family]["rotations"]["1"] for family in ("mc", "reading"))
    vmlu, vm14k = mc["by_dataset"]["vi-multimodel-v1-vmlu-valid"], mc["by_dataset"]["vm14k-4-options"]
    bidlqa = reading["by_dataset"]["bidlqa-train"]
    labels = {"v3": ("Router v3: tự chọn cách cho mỗi bộ", "candidate"), "v2": ("Router v2", "baseline"),
              "always_B": ("Luôn B", "baseline"), "always_S": ("Luôn S", "baseline")}
    columns = [column("vmlu", "VMLU valid", "Tỷ lệ đúng", vmlu["test_items"]),
               column("vm14k", "VM14K", "Tỷ lệ đúng", vm14k["test_items"]),
               column("mc", "Trắc nghiệm gộp", "Tỷ lệ đúng", mc["items"]),
               column("bidlqa", "ViBidLQA train", "Token-F1", bidlqa["test_items"])]
    rows = [row(name, label, role, {
        "vmlu": cell(pts(vmlu["scores"][name]), None, vmlu["mean_tokens"][name]),
        "vm14k": cell(pts(vm14k["scores"][name]), None, vm14k["mean_tokens"][name]),
        "mc": cell(pts(mc["policies"][name]["accuracy"]), mc["policies"][name]["accuracy_ci95_pct"],
                   mc["policies"][name]["mean_total_tokens"]),
        "bidlqa": cell(pts(bidlqa["scores"][name]), None, bidlqa["mean_tokens"][name])})
        for name, (label, role) in labels.items()]
    gain = {other: mc["policies"]["v3"]["accuracy"] - mc["policies"][other]["accuracy"] for other in ("v2", "always_S")}
    tests = [test(f"Router v3 so với {ARM_LABELS.get(other, 'router v2')}, trắc nghiệm gộp", diff=pts(gain[other]),
                  p=mc["tests"][f"v3_vs_{other}"]["mcnemar_p_holm"], p_kind="McNemar, Holm", primary=True)
             for other in ("v2", "always_S")]
    wins = [better(mc["tests"][f"v3_vs_{other}"]["mcnemar_p_holm"], gain[other]) for other in ("v2", "always_S")]
    computed = "met" if all(wins) else "partial" if any(wins) else "not_met"
    choices = report["calibration"]["1"]["choices"]
    return {"id": "mc-95", "cards": "MC-95", "title": "Router v3 trên câu mới thứ hai",
            "question": "Để router tự chọn cách tốt nhất cho mỗi bộ từ 60 câu hiệu chỉnh có được không?",
            "student": QWEN, "items": "1.080 câu chưa router nào thấy (60 câu hiệu chỉnh + 300 câu kiểm tra mỗi bộ)",
            "status": settle("MC-95", computed, "not_met"),
            "verdict": ("Không hơn router v2 và kém luôn S. 60 câu hiệu chỉnh chọn sai cách cho VM14K: "
                        "hai cách chỉ chênh nhau vài điểm thì 60 câu không đủ để tách."),
            "tables": [table("Kết quả vòng 1 (300 câu kiểm tra mỗi bộ)", columns, rows)], "tests": tests,
            "notes": ["Hiệu chỉnh vòng 1 chọn: " + ", ".join(
                f"{label} → {ARM_LABELS.get(choices[key], choices[key])}"
                for key, label in (("vi-multimodel-v1-vmlu-valid", "VMLU valid"), ("vm14k-4-options", "VM14K"),
                                   ("bidlqa-train", "ViBidLQA train"))) + "."],
            "sources": src.refs("v3")}


def k2(src: Sources) -> dict[str, Any]:
    report = src("k2")
    expect("MC-96", report, primary_rotation=1)
    rotation = report["rotations"]["1"]
    policies = rotation["policies"]
    labels = {"router": ("Router: hỏi K hai lần, lệch thì KS", "candidate"),
              "always_K": ("Luôn K: 2 đoạn BM25 tự tìm", "baseline"),
              "always_KS": ("Luôn KS: K và suy luận từng bước", "baseline"),
              "always_B": ("B không kèm đoạn văn", "baseline"), "O": ("O: đoạn văn gốc (trần)", "ceiling")}
    columns = [column("bidlqa", "ViBidLQA train, không kèm đoạn văn gốc", "Token-F1", rotation["test_items"])]
    rows = [row(name, label, role, {"bidlqa": cell(pts(policies[name]["mean_token_f1"]),
                                                   policies[name]["token_f1_ci95_pct"],
                                                   policies[name]["mean_total_tokens"])})
            for name, (label, role) in labels.items()]
    groups = rotation["by_retrieval"]
    by_hit = [column(name, label, "Token-F1", groups[name]["items"])
              for name, label in (("own_passage_in_top_2", "BM25 tìm trúng đoạn gốc"),
                                  ("own_passage_missed", "BM25 tìm trượt"))]
    hit_rows = [row(name, labels[key][0], labels[key][1],
                    {group["id"]: cell(pts(groups[group["id"]][name])) for group in by_hit})
                for name, key in (("always_K", "always_K"), ("always_KS", "always_KS"), ("always_B", "always_B"),
                                  ("O", "O"))]
    tests = [test(f"Router so với {label}", diff=pts(rotation["tests"][key]["mean_token_f1_difference"]),
                  p=rotation["tests"][key]["sign_flip_p_holm"], p_kind="đổi dấu, Holm", primary=True)
             for key, label in (("router_vs_always_K", "luôn K"), ("router_vs_always_KS", "luôn KS"))]
    wins = [better(rotation["tests"][key]["sign_flip_p_holm"], rotation["tests"][key]["mean_token_f1_difference"])
            for key in ("router_vs_always_K", "router_vs_always_KS")]
    computed = "met" if all(wins) else "partial" if any(wins) else "not_met"
    return {"id": "mc-96", "cards": "MC-96", "title": "K2: tự tìm đoạn văn bằng BM25",
            "question": "Bỏ đoạn văn gốc, để BM25 tự tìm 2 đoạn: trả lời được đến đâu, và router có giúp không?",
            "student": QWEN, "items": "360 câu ViBidLQA train (60 hiệu chỉnh + 300 kiểm tra)",
            "status": settle("MC-96", computed, "not_met"),
            "verdict": ("Khi BM25 tìm trúng, trả lời tốt ngang có đoạn gốc; khi tìm trượt thì tụt mạnh. Router không "
                        "hơn luôn K hay luôn KS mà tốn nhiều token hơn."),
            "tables": [table("Kết quả vòng 1", columns, rows),
                       table("Theo kết quả tìm kiếm", by_hit, hit_rows)],
            "tests": tests, "notes": [], "sources": src.refs("k2")}


def menu(src: Sources) -> dict[str, Any]:
    report = src("menu")
    expect("MC-97", report, card_id="MC-97", plan_id="diagnostic-menu-q-v1")
    keys = (("vi-multimodel-v1-vi-squad-200", "squad", "Vi-SQuAD"), ("vi-multimodel-v1-vi-drop-200", "drop", "Vi-DROP"),
            ("vi-multimodel-v1-bidlqa-test", "bidlqa", "ViBidLQA test"))
    blocks = {short: report["datasets"][key] for key, short, _ in keys} | {"pooled": report["pooled"]}
    columns = [column(short, label, "Token-F1", report["datasets"][key]["items"]) for key, short, label in keys]
    columns.append(column("pooled", "Gộp", "Token-F1", report["pooled"]["items"]))
    labels = {"B": ("B: hỏi thẳng", "baseline"), "Q": ("Q: trích câu trong đoạn rồi đáp", "candidate"),
              "S": ("S: suy luận từng bước", "baseline")}
    rows = [row(arm, label, role, {name: cell(block["arms"][arm]["token_f1"], None,
                                              block["arms"][arm].get("mean_reported_tokens"))
                                   for name, block in blocks.items()})
            for arm, (label, role) in labels.items()]
    tests = [test(f"Q so với {other}, {label}", diff=report["datasets"][key]["pairwise"][f"Q_vs_{other}"]["mean_difference"])
             for key, _, label in keys for other in ("B", "S")]
    q_best = any(report["datasets"][key]["best_fixed_arm"] == "Q" for key, _, _ in keys)
    best = ", ".join(f"{label} {report['datasets'][key]['best_fixed_arm']}" for key, _, label in keys)
    return {"id": "mc-97", "cards": "MC-97", "title": "Cách hỏi Q (trích rồi đáp)",
            "question": "Bắt model trích câu trong đoạn văn trước rồi mới trả lời (Q) có tốt hơn B hay S không?",
            "student": QWEN, "items": "967 câu đọc hiểu của wide, dùng để thiết kế",
            "status": settle("MC-97", "met" if q_best else "descriptive", "descriptive"),
            "verdict": f"Q không là cách tốt nhất ở bộ nào. Cách cố định tốt nhất mỗi bộ: {best}.",
            "tables": [table("Token-F1 theo bộ", columns, rows)], "tests": tests, "notes": [],
            "sources": src.refs("menu")}


def muse_router(src: Sources) -> dict[str, Any]:
    report = src("labels")
    expect("MC-98", report, card_id="MC-98", plan_id="diagnostic-router-labels-v1")
    routing = report["routing"]
    labels = {"muse_grouping": ("Router Muse: đọc đoạn văn và câu hỏi, chia 6 nhóm", "candidate"),
              "keyword_grouping": ("Chia nhóm bằng từ khóa", "baseline"), "always_S": ("Luôn S", "baseline"),
              "always_B": ("Luôn B", "baseline"), "always_Q": ("Luôn Q", "baseline"),
              "per_item_bound": ("Trần: chọn đúng cách cho từng câu", "ceiling")}
    columns = [column("bidlqa", "ViBidLQA test (câu thiết kế)", "Token-F1", report["items"])]
    rows = [row(name, label, role, {"bidlqa": cell(routing[name])}) for name, (label, role) in labels.items()]
    tests = [test(f"Router Muse so với {label}", diff=report[key]["mean_points"], ci=report[key]["ci95_points"],
                  p=report[key]["sign_flip_p"], p_kind="đổi dấu", primary=True)
             for key, label in (("muse_minus_always_S", "luôn S"), ("muse_minus_keywords", "chia bằng từ khóa"))]
    return {"id": "mc-98", "cards": "MC-98", "title": "Router LLM (Muse Spark 1.3)",
            "question": "Một LLM mạnh hơn đọc đoạn văn và câu hỏi rồi chọn cách hỏi cho Qwen có tốt hơn không?",
            "student": QWEN, "items": "591 câu ViBidLQA dùng để thiết kế",
            "status": settle("MC-98", "met" if report["reading_rule"]["promising"] else "not_met", "not_met"),
            "verdict": ("Router Muse chỉ ngang luôn S và ngang cách chia bằng từ khóa, nên không đạt quy tắc ghi trước "
                        "(hơn luôn S ít nhất 1 điểm) và dừng ở bước thiết kế."),
            "tables": [table("Token-F1", columns, rows)], "tests": tests,
            "notes": [f"Mỗi câu, router tốn thêm khoảng {report['router_cost']['total_tokens']:.0f} token của Muse."],
            "sources": src.refs("labels")}


def legal_oracle(src: Sources) -> dict[str, Any]:
    report = src("oracle")
    expect("MC-100", report, card_id="MC-100", plan_id="diagnostic-legal-oracle-v1")
    groups = report["primary"]
    columns = [column("wrong", "Câu Qwen từng sai", "Tỷ lệ đúng", groups["wrong"]["n"]),
               column("right", "Câu Qwen vốn đúng", "Tỷ lệ đúng", groups["right"]["n"])]
    rows = [row("B", "B: hỏi như cũ, không kèm luật", "baseline",
                {name: cell(groups[name]["B"]) for name in ("wrong", "right")}),
            row("O", "O: kèm đúng điều luật", "candidate", {name: cell(groups[name]["O"]) for name in ("wrong", "right")})]
    tests = [test(f"O so với B, {label}", diff=groups[name]["O_versus_B"]["mean_points"],
                  ci=groups[name]["O_versus_B"]["ci95_points"], p=groups[name]["O_versus_B"]["sign_flip_p"],
                  p_kind="đổi dấu", primary=True)
             for name, label in (("wrong", "câu từng sai"), ("right", "câu vốn đúng"))]
    rule = report["reading_rule"]
    return {"id": "mc-100", "cards": "MC-100", "title": "Legal MC: đưa sẵn đúng điều luật",
            "question": "Nếu đưa sẵn đúng điều luật, Qwen có sửa được câu từng sai mà không làm hỏng câu đang đúng?",
            "student": QWEN, "items": "56 câu Legal MC có nhãn điều luật",
            "status": settle("MC-100", "met" if rule["fixes_enough"] and rule["harmless_enough"] else "not_met", "met"),
            "verdict": ("Đạt: ở các câu từng sai, đúng điều luật tăng tỷ lệ đúng lên rất nhiều, và không làm hại câu "
                        "vốn đúng. Thiếu điều luật là nguyên nhân thật của phần lớn lỗi."),
            "tables": [table("Kết quả", columns, rows)], "tests": tests,
            "notes": ["O là trần: điều luật do người và AI chọn sẵn, chưa dùng được ngoài thực tế."],
            "sources": src.refs("oracle")}


def legal_retrieval(src: Sources) -> dict[str, Any]:
    report = src("retrieval")
    expect("MC-101", report, card_id="MC-101", plan_id="diagnostic-legal-retrieval-v1")
    primary, wrong, outside = report["primary"], report["mc100_strata"]["wrong"], report["outside_mc100"]
    columns = [column("all", "Cả bộ Legal MC", "Tỷ lệ đúng", primary["n"]),
               column("wrong", "Câu từng sai (nhóm MC-100)", "Tỷ lệ đúng", wrong["K_vs_B"]["n"]),
               column("outside", "Câu ngoài MC-100", "Tỷ lệ đúng", outside["n"])]
    rows = [row("B", "B: hỏi như cũ", "baseline", {"all": cell(primary["B"]), "wrong": cell(wrong["K_vs_B"]["B"]),
                                                   "outside": cell(outside["B"])}),
            row("K", "K: kèm 2 điều luật BM25 tự tìm", "candidate",
                {"all": cell(primary["K"]), "wrong": cell(wrong["K_vs_B"]["K"]), "outside": cell(outside["K"])}),
            row("O", "O: kèm đúng điều luật (trần)", "ceiling", {"wrong": cell(wrong["O_vs_B"]["O"])})]
    tests = [test("K so với B, cả bộ", diff=primary["K_versus_B"]["mean_points"], ci=primary["K_versus_B"]["ci95_points"],
                  p=primary["K_versus_B"]["sign_flip_p"], p_kind="đổi dấu", primary=True),
             test("K so với B, câu từng sai", diff=wrong["K_vs_B"]["K_versus_B"]["mean_points"],
                  ci=wrong["K_vs_B"]["K_versus_B"]["ci95_points"], p=wrong["K_vs_B"]["K_versus_B"]["sign_flip_p"],
                  p_kind="đổi dấu")]
    return {"id": "mc-101", "cards": "MC-101", "title": "Legal MC: tự tìm điều luật",
            "question": "Để BM25 tự tìm điều luật trong kho luật rồi đưa vào câu hỏi: \"luôn tra luật\" có hơn \"luôn hỏi như cũ\"?",
            "student": QWEN, "items": "134 câu Legal MC",
            "status": settle("MC-101", "met" if report["reading_rule"]["k_beats_b"] else "not_met", "not_met"),
            "verdict": ("Không đạt: trên cả bộ, tra luật ngang hỏi như cũ. K có giúp ở nhóm câu từng sai nhưng chỉ lấy lại "
                        "một phần nhỏ phần lợi của O, và làm hỏng chút ít ở câu vốn đúng. Legal MC giữ B."),
            "tables": [table("Kết quả", columns, rows)], "tests": tests,
            "notes": [f"Ở nhóm câu từng sai, K giữ lại {pts(wrong['share_of_O_gain_kept_by_K']):.0f}% phần lợi của O."],
            "sources": src.refs("retrieval")}


def critic(src: Sources) -> dict[str, Any]:
    report = src("critic")
    expect("MC-102", report, card_id="MC-102", plan_id="diagnostic-router-critic-v1")
    keys = (("vi-multimodel-v1-vi-drop-200", "drop", "Vi-DROP"), ("vi-multimodel-v1-vi-squad-200", "squad", "Vi-SQuAD"),
            ("pooled", "pooled", "Gộp"))
    columns = [column(short, label, "Token-F1", report["by_dataset"][key]["always_B"]["n"]) for key, short, label in keys]
    labels = {"critic_loop": ("Vòng lặp có Muse chấm câu trả lời", "candidate"),
              "rule_loop": ("Vòng lặp đơn giản: B hai lần, lệch thì S", "baseline"),
              "always_B": ("Luôn B", "baseline"), "always_S": ("Luôn S", "baseline"), "always_Q": ("Luôn Q", "baseline"),
              "muse_alone": ("Muse tự trả lời (MC-80/81, tham khảo)", "reference"),
              "bound": ("Trần: chọn đúng cách cho từng câu", "ceiling")}
    rows = [row(name, label, role, {short: cell(report["by_dataset"][key][name]["token_f1"]) for key, short, _ in keys})
            for name, (label, role) in labels.items()]
    versus = report["primary"]["critic_versus_rule"]
    tests = [test("Vòng lặp có Muse chấm so với vòng lặp đơn giản", diff=versus["mean_points"], ci=versus["ci95_points"],
                  p=versus["sign_flip_p"], p_kind="đổi dấu", primary=True)]
    detector = report["detector"]["pooled"]
    return {"id": "mc-102", "cards": "MC-102", "title": "Muse chấm câu trả lời của Qwen",
            "question": "Một LLM mạnh hơn chấm câu trả lời đầu tiên của Qwen rồi chọn cách sửa: có hơn vòng lặp đơn giản?",
            "student": QWEN, "items": "376 câu Vi-DROP và Vi-SQuAD dùng để thiết kế; phát lại bằng câu trả lời đã lưu",
            "status": settle("MC-102", "met" if report["reading_rule"]["critic_goes_on"] else "not_met", "not_met"),
            "verdict": ("Không đạt: hơn vòng lặp đơn giản khoảng 1 điểm nhưng chưa chắc. Muse bắt được nhiều câu sai ở "
                        "Vi-DROP, nhưng ở đó luôn S cũng đạt cùng mức; ở Vi-SQuAD Muse báo nhầm nhiều hơn số câu bắt được."),
            "tables": [table("Token-F1", columns, rows)], "tests": tests,
            "notes": [f"Muse bắt được {detector['caught']}/{detector['b1_wrong']} câu B sai "
                      f"(tỷ lệ bắt {pts(detector['recall']):.0f}%, tỷ lệ báo đúng {pts(detector['precision']):.0f}%)."],
            "sources": src.refs("critic")}


def weakness_map(src: Sources) -> dict[str, Any]:
    report, rescored = src("weakness"), src("reading_v3")
    expect("MC-103", report, card_id="MC-103", plan_id="weakness-map-v1")
    expect("MC-103 v3", rescored, plan_id="reading-v3-rescore-v1")
    keys = (("vi-multimodel-v1-vmlu-valid", "vmlu", "VMLU valid", "Tỷ lệ đúng"),
            ("vm14k-4-options", "vm14k", "VM14K", "Tỷ lệ đúng"),
            ("bidlqa-train", "bidlqa", "ViBidLQA train (bộ chấm v2)", "Token-F1"))
    v3_block = rescored["mc103"]["by_dataset"]["bidlqa-train"]["v3"]
    columns = [column(short, label, metric, report["by_dataset"][key]["student"]["n"]) for key, short, label, metric in keys]
    columns.append(column("bidlqa_v3", "ViBidLQA train (bộ chấm v3, chấm lại sau)", "Token-F1",
                          v3_block["student"]["n"]))
    def value(block: dict[str, Any], name: str) -> float:
        return block["rule_loop"] if name == "rule_loop" else block["means"][name]

    rows = []
    for side, model in (("student", "MiMo V2.6 Flash"), ("reference", "Qwen3.5-9B")):
        for name, label, role in (("B1", "B", "baseline"), ("S1", "S", "candidate"),
                                  ("rule_loop", "vòng lặp đơn giản", "baseline")):
            cells = {short: cell(value(report["by_dataset"][key][side], name)) for key, short, _, _ in keys}
            cells["bidlqa_v3"] = cell(value(v3_block[side], name))
            rows.append(row(f"{side}-{name}", f"{model} · {label}", role, cells))
    tests = [test(f"Tương tác: lợi của S ở MiMo trừ lợi của S ở Qwen, {label}",
                  diff=report["by_dataset"][key]["interaction_S"]["mean_points"],
                  ci=report["by_dataset"][key]["interaction_S"]["ci95_points"],
                  p=report["by_dataset"][key]["interaction_S"]["sign_flip_p"], p_kind="đổi dấu")
             for key, _, label, _ in keys]
    tests.append(test("Tương tác, ViBidLQA train (bộ chấm v3, chấm lại sau)", diff=v3_block["interaction_S"]["mean_points"],
                      ci=v3_block["interaction_S"]["ci95_points"], p=v3_block["interaction_S"]["sign_flip_p"],
                      p_kind="đổi dấu"))
    maps = report["maps"]
    notes = ["Bản đồ (điểm / chắc chắn): " + "; ".join(
        f"{model}: " + ", ".join(f"{label} {maps[side][key]['point']} / {maps[side][key]['reliable']}"
                                 for key, _, label, _ in keys[:2]) + f", ViBidLQA {maps[side]['bidlqa-train']['point']} / "
        f"{maps[side]['bidlqa-train']['reliable']}"
        for side, model in (("student", "MiMo"), ("reference", "Qwen"))) + ".",
             "Vòng lặp đơn giản: hỏi B hai lần, nếu hai câu trả lời khác nhau thì dùng S."]
    return {"id": "mc-103", "cards": "MC-103", "title": "Bản đồ điểm yếu: MiMo so với Qwen",
            "question": "Cách sửa giúp được Qwen có giúp được một model khác (MiMo V2.6 Flash, tự suy nghĩ) không?",
            "student": "MiMo V2.6 Flash (OpenCode Go), so với Qwen3.5-9B trên cùng câu",
            "items": "180 câu hiệu chỉnh của MC-95 (60 mỗi bộ)",
            "status": "descriptive",
            "verdict": ("Ở VMLU, S giúp Qwen nhiều nhưng không giúp MiMo, vì MiMo vốn tự suy nghĩ. Ở ViBidLQA, khác biệt "
                        "ban đầu chủ yếu do MiMo in đậm câu trả lời; chấm lại bằng v3 thì S giúp hai model như nhau."),
            "tables": [table("Điểm lượt đầu", columns, rows)], "tests": tests, "notes": notes,
            "sources": src.refs("weakness", "reading_v3")}


EXPERIMENTS = (wide, core, router_v2, router_v3, k2, menu, muse_router, legal_oracle, legal_retrieval, critic,
               weakness_map)


def validate(data: dict[str, Any]) -> None:
    """The same contract web/lib/router-results.ts enforces, checked before anything is written."""
    seen = set()
    for experiment in data["experiments"]:
        name = experiment["id"]
        if name in seen or experiment["status"] not in STATUSES:
            raise _fail(f"{name}: duplicate id or unknown status")
        seen.add(name)
        for block in experiment["tables"]:
            ids = [entry["id"] for entry in block["columns"]]
            for entry in block["rows"]:
                if entry["role"] not in ROLES or set(entry["cells"]) - set(ids):
                    raise _fail(f"{name}: row {entry['id']} has an unknown role or column")
                for value in entry["cells"].values():
                    if not math.isfinite(value["score"]) or (value["ci"] and value["ci"][0] > value["ci"][1]):
                        raise _fail(f"{name}: invalid cell in row {entry['id']}")
        for entry in experiment["tests"]:
            if entry["p"] is not None and not 0 <= entry["p"] <= 1:
                raise _fail(f"{name}: p outside [0, 1] in {entry['label']}")


def build(root: Path = ROOT) -> dict[str, Any]:
    src = Sources(root)
    data = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "alpha": ALPHA,
            "experiments": [make(src) for make in EXPERIMENTS]}
    validate(data)
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    data = build(args.root)
    out = args.root / OUT
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out)
    for experiment in data["experiments"]:
        print(f"{experiment['cards']:<20} {experiment['status']:<12} {experiment['title']}")
    print(f"wrote {out.relative_to(args.root)} ({len(data['experiments'])} experiments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
