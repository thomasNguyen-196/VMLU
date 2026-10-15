"""Publish evidence-backed condition -> benchmark -> comment -> note reports.

This is a reporting projection, not a scorer: published metrics retain their
arm, gold source, and denominator. Missing historical controls remain unknown.
Run from the repository root: .venv/bin/python code_benchmark/build_benchmark_reports.py
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from code_benchmark.migrate_results_to_mongo import MIGRATION_PLAN, runner_config
    from code_benchmark.seed_registries import MODELS
except ImportError:
    from migrate_results_to_mongo import MIGRATION_PLAN, runner_config
    from seed_registries import MODELS

ROOT = Path(__file__).resolve().parents[1]
SCORE_CSV = "docs/research/vi-multimodel-all-results-2026-10-09.csv"
UNKNOWN = "Chưa ghi nhận trong artifact/card"
PROFILES = ("muse-spark-1-3-contributor", "mimo-v2-6-flash", "mimo-v2-5", "qwen3-5-9b-65k")
FIELD_LABELS = {
    "date": "Thời gian chạy", "harness": "Harness / phiên bản / mode", "provider": "Provider / API / route",
    "temperature": "Temperature gửi / hiệu lực", "thinking": "Thinking / reasoning level", "seed": "Seed",
    "tools": "Tools", "prompt": "System / user prompt", "context": "Ngữ cảnh / dữ liệu đầu vào",
    "session": "History / session / sandbox", "output_cap": "Giới hạn output", "workers": "Workers / batch",
    "timeout": "Timeout", "retry": "Retry / recovery", "gold": "Gold / cách chấm", "identity": "Model / quantization",
}
METRIC_LABELS = dict([
    ("accuracy", "Accuracy"), ("server_accuracy", "Server accuracy"), ("em", "EM"), ("token_f1", "Token-F1"),
    ("char_f1", "Char-F1"), ("valid_rate", "Schema validity"), ("agreement", "Agreement với arm A"),
    ("function_exact", "Function + arguments exact"),
    ("server_macro", "Server macro (domain mean)"),
])


def read_json(root: Path, path: str) -> dict:
    try:
        return json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read {path}: {exc}") from exc


def read_csv(root: Path, path: str) -> list[dict]:
    with (root / path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: object) -> float | None:
    if value in (None, ""):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise SystemExit(f"Error: non-finite metric {value}")
    return result


def count(value: object) -> int | None:
    result = number(value)
    if result is not None and (result < 0 or result != int(result)):
        raise SystemExit(f"Error: invalid count {value}")
    return int(result) if result is not None else None


def card_index(root: Path) -> dict[str, dict]:
    text = (root / "measurement_card.md").read_text(encoding="utf-8")
    headings = list(re.finditer(r"^#{2,3} (MC-\d+[a-z]?)\s+[^\n]*", text, re.M))
    cards = {}
    for i, heading in enumerate(headings):
        body = text[heading.end():headings[i + 1].start() if i + 1 < len(headings) else len(text)]
        fields = {}
        for line in body.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if line.startswith("| `") and len(cells) == 2:
                fields[cells[0].replace("`", "").strip()] = cells[1].replace("**", "").replace("`", "")
        cards[heading.group(1)] = {"title": heading.group(0).lstrip("# "), "fields": fields,
                                   "line": text[:heading.start()].count("\n") + 1}
    return cards


def field(card: dict, *keys: str) -> str:
    values = card["fields"]
    return next((values[key] for key in keys if key in values), UNKNOWN)


def source(path: str, label: str = "Artifact") -> dict:
    return {"path": path, "label": label}


def row(condition_id: str, dataset_id: str, dataset: str, metric: str, value: object, *,
        level: str = "dataset", category: str = "", n: object = None, correct: object = None,
        ci: list | None = None, gold: str = "local", truncated: object = None, source_path: str = "",
        delta: object = None, delta_ci: list | None = None) -> dict:
    return {"condition_id": condition_id, "dataset_id": dataset_id, "dataset": dataset, "level": level,
            "category": category, "metric": metric, "score": number(value), "n": count(n), "correct": count(correct),
            "ci_low": number(ci[0]) if ci else None, "ci_high": number(ci[1]) if ci else None,
            "gold": gold, "truncated": count(truncated), "source": source_path,
            "delta": number(delta), "delta_ci_low": number(delta_ci[0]) if delta_ci else None,
            "delta_ci_high": number(delta_ci[1]) if delta_ci else None}


def signature(meta: dict, caps: dict) -> tuple | None:
    """Known nominal controls only; missing thinking/seed evidence cannot match."""
    keys = ("omp_version", "omp_mode", "omp_tools", "omp_system_prompt", "omp_thinking", "omp_reasoning",
            "temperature_effective", "workers", "omp_max_time_seconds", "omp_session_policy", "sdk_retries",
            "seed_sent", "manifest_sha256")
    if any(meta.get(key) is None for key in keys):
        return None
    if not caps or (meta["seed_sent"] and meta.get("seed_requested") is None):
        return None
    seed = meta.get("seed_requested") if meta["seed_sent"] else "omitted"
    return tuple(meta[key] for key in keys[:-2]) + (seed, meta["manifest_sha256"], tuple(sorted(caps.items())))


def modern_condition(root: Path, path: str, profile: dict, protocol: dict, phase: str) -> tuple[dict, tuple | None]:
    meta = read_json(root, path)
    version2 = protocol["protocol_version"] == 2
    caps = protocol["phases"][phase]["max_completion_tokens"] if version2 else protocol[phase]["max_completion_tokens"]
    thinking = meta.get("omp_thinking")
    if thinking is None:
        # Pilot V1 did not serialize this field; its preregistered card/profile does.
        thinking = profile.get("omp_thinking", "auto")
    caps = {**caps, **({"multiple_choice": meta["max_tokens_mc"]} if "max_tokens_mc" in meta else {}),
            **({"reading": meta["max_tokens_reading"]} if "max_tokens_reading" in meta else {})}
    normalized = {**meta, "omp_thinking": thinking, "omp_reasoning": meta.get("omp_reasoning", thinking == "auto"),
                  "omp_session_policy": meta.get("omp_session_policy", protocol.get("omp_session_policy")),
                  "sdk_retries": meta.get("sdk_retries", meta.get("max_retries", 0))}
    requested = meta.get("temperature_requested")
    if version2 and profile["profile_id"] == "qwen3-5-9b-65k":
        requested = meta["temperature_effective"]
    sent = "không gửi" if requested is None else str(requested)
    card = meta["measurement_card_id"]
    condition = {
        "id": f"{protocol['protocol_id']}-{phase}-{profile['profile_id']}", "model": profile["display_name"],
        "card": card, "comparison_group": None,
        "fields": {
            "date": f"{meta.get('started_at', UNKNOWN)} → {meta.get('finished_at', UNKNOWN)}",
            "harness": f"{meta['transport']} · {meta.get('omp_version', UNKNOWN)} · mode {meta.get('omp_mode', UNKNOWN)}",
            "provider": f"{meta.get('provider', profile['provider'])} · {meta.get('api_protocol', profile['api_protocol'])} · {meta.get('endpoint_host', UNKNOWN)}",
            "temperature": f"gửi {sent}; hiệu lực theo metadata {meta.get('temperature_effective', UNKNOWN)}; {meta.get('temperature_policy', UNKNOWN)}",
            "thinking": f"{thinking}; {('reasoning bật' if meta.get('omp_reasoning', thinking == 'auto') else 'reasoning tắt')}; effort không ghim mức low/medium/high" + (" (pilot: theo card/profile)" if "omp_thinking" not in meta else ""),
            "seed": f"gửi {meta.get('seed_requested', UNKNOWN)}" if meta.get("seed_sent") else "không gửi; seed sample và seed inference là hai cấu hình riêng",
            "tools": meta.get("omp_tools", UNKNOWN), "prompt": f"System: {meta.get('omp_system_prompt', UNKNOWN)}; user prompt đóng băng theo manifest",
            "context": "MC: câu hỏi + lựa chọn; reading: context trong prompt; gold không gửi cho model" if not version2 else "VMLU: câu hỏi + lựa chọn" + ("; synthetic agentic: schema" if phase == "pilot" else "") + "; gold không gửi cho model",
            "session": meta.get("omp_session_policy", protocol.get("omp_session_policy", "một process/item; không history")),
            "output_cap": "; ".join(f"{key}: {value} token" for key, value in caps.items()) + "; cap do benchmark đặt, có thể bao gồm reasoning",
            "workers": f"{meta.get('workers', UNKNOWN)} worker; queue chia sẻ" ,
            "timeout": f"{meta.get('omp_max_time_seconds', UNKNOWN)} giây/item",
            "retry": f"SDK {meta.get('sdk_retries', meta.get('max_retries', UNKNOWN))}; technical attempts {meta.get('max_technical_attempts', 'resume cùng cấu hình')}",
            "gold": "V1: MC source gold; reading-400 user-reviewed; ViBidLQA file gold" if not version2 else "Dev/Valid: local gold; Test: withheld, server grade do người dùng cung cấp; pilot synthetic có gold",
            "identity": meta.get("model_ref", meta["model_id"]) + "; quantization không công bố trong metadata",
        },
        "sources": [source(path, "Run metadata"), source("measurement_card.md", card),
                    source(f"data/vi_multimodel_protocol_v{protocol['protocol_version']}.json", "Protocol / caps")],
        "manifest_sha256": meta.get("manifest_sha256"), "measurement_card_hash": meta.get("measurement_card_hash"),
        "controls": {
            "profile_id": profile["profile_id"], "transport": meta["transport"],
            "harness_version": meta.get("omp_version"), "tools": meta.get("omp_tools"),
            "temperature_requested": requested, "temperature_effective": meta.get("temperature_effective"),
            "thinking": thinking, "seed_sent": meta.get("seed_sent"), "seed_requested": meta.get("seed_requested"),
            "output_caps": caps, "workers": meta.get("workers"), "system_prompt": meta.get("omp_system_prompt"),
            "prompt_version": protocol.get("prompt_version", protocol["protocol_id"]),
        },
    }
    return condition, signature(normalized, caps)


def csv_score_rows(records: list[dict], conditions: dict[str, str]) -> list[dict]:
    result = []
    for record in records:
        if record["record_type"] not in {"dataset", "breakdown", "server_breakdown", "historical_server_score"}:
            continue
        profile = record["profile_id"]
        if profile not in conditions:
            raise SystemExit(f"Error: score without condition for {profile}")
        level = record.get("breakdown_level") or "dataset"
        # Group is the V1 reading partition; leave it explicit, not a VMLU category.
        level = level if level in {"dataset", "category", "subject"} else "subject"
        label = record["dataset_label"]
        category = record.get("breakdown_name", "")
        if category.startswith("("):
            try:
                parsed = ast.literal_eval(category)
                if isinstance(parsed, tuple) and len(parsed) == 3:
                    category = str(parsed[1])
            except (ValueError, SyntaxError):
                raise SystemExit(f"Error: malformed subject identity {category}") from None
        for metric, column, low, high in (
            ("accuracy", "accuracy_pct", "accuracy_ci95_lower_pct", "accuracy_ci95_upper_pct"),
            ("server_accuracy", "server_accuracy_pct", "", ""),
            ("em", "em_pct", "em_ci95_lower_pct", "em_ci95_upper_pct"),
            ("token_f1", "token_f1_pct", "token_f1_ci95_lower_pct", "token_f1_ci95_upper_pct"),
        ):
            if record.get(column, "") == "":
                continue
            reported_metric = "function_exact" if metric == "accuracy" and "agentic-synthetic" in record["dataset_id"] else metric
            result.append(row(conditions[profile], record["dataset_id"], label, reported_metric, record[column],
                              level=level, category=category, n=record.get("expected_n"),
                              correct=record.get("correct") if metric == "accuracy" else None,
                              ci=[record[low], record[high]] if low and record.get(low) and record.get(high) else None,
                              gold=record.get("gold_status", "local"), truncated=record.get("truncated_n"), source_path=SCORE_CSV))
    return result


def comments_for(report: dict) -> list[str]:
    conditions = {c["id"]: c for c in report["conditions"]}
    comparisons = defaultdict(list)
    for r in report["benchmarks"]:
        group = conditions[r["condition_id"]]["comparison_group"]
        if group and r["level"] in {"dataset", "category"} and r["metric"] not in {"valid_rate", "agreement"}:
            comparisons[(group, r["dataset_id"], r["category"], r["metric"])].append(r)
    comments = []
    for (_group, _dataset, category, metric), rows in comparisons.items():
        if len(rows) < 2:
            continue
        if len({r["n"] for r in rows}) != 1:
            continue
        ordered = sorted(rows, key=lambda r: r["score"], reverse=True)
        best, second = ordered[:2]
        name = conditions[best["condition_id"]]["model"]
        other = conditions[second["condition_id"]]["model"]
        measured = "khớp gold" if metric in {"em", "token_f1", "char_f1"} else "điểm trên mẫu này"
        comments.append(f"{best['dataset']}{' / ' + category if category else ''} · {METRIC_LABELS[metric]}: {name} {best['score']:.2f}%, {other} {second['score']:.2f}% (chênh {best['score'] - second['score']:.2f} pp); đây là {measured}, trong nhóm cấu hình danh nghĩa khớp.")
    if not comments:
        comments.append("Đây là kết quả của condition riêng. Dữ liệu hiện có chưa tạo thành bảng xếp hạng các model dưới cùng cấu hình đầy đủ.")
    comments.append("Suy luận về hiểu tiếng Việt cần đọc cùng dạng bài: MC kết hợp hiểu câu hỏi với kiến thức và suy luận; EM/F1 đo khớp văn bản. Các điểm này chưa trực tiếp đo chất lượng hội thoại hoặc mức đúng về ngữ nghĩa của câu trả lời tự do.")
    return comments


def matched_qwen_main(root: Path, protocol: dict, profiles: list[dict]) -> tuple[dict, tuple, list[dict]] | None:
    """Publish MC-72 only after verifying its subset against every Go run's prompts."""
    run_path = "all_res/qwen_matched_mc72/main/qwen3-5-9b-65k/run.json"
    if not (root / run_path).exists():
        return None
    meta = read_json(root, run_path)
    if meta.get("status") != "complete":
        return None
    controls = {"transport": "omp", "omp_tools": "none", "temperature_effective": 1.0,
                "omp_thinking": "auto", "omp_reasoning": True, "seed_sent": False,
                "workers": 4, "max_tokens_mc": 4096, "max_tokens_reading": 2048}
    if any(meta.get(key) != value for key, value in controls.items()):
        raise SystemExit("Error: MC-72 sampling/tools/budget differ from the registered matched condition")
    summary_path = run_path.replace("run.json", "summary.json")
    summary = read_json(root, summary_path)
    manifest = read_json(root, "all_res/qwen_matched_mc72/condition_manifest.jsonl")
    parent = read_json(root, "data/vi_multimodel_v1/main_v1.json")
    expected = {
        "vi-multimodel-v1-legal-mc-146": 146, "vi-multimodel-v1-legal-nli-150": 150,
        "vi-multimodel-v1-vi-squad-200": 200, "vi-multimodel-v1-vi-drop-200": 200,
        "vi-multimodel-v1-bidlqa-test": 603,
    }
    if (meta.get("measurement_card_id") != "MC-72" or summary.get("measurement_card_id") != "MC-72"
            or meta.get("manifest_sha256") != manifest.get("manifest_sha256")
            or summary.get("manifest_sha256") != manifest.get("manifest_sha256")
            or manifest.get("parent_manifest_sha256") != parent.get("manifest_sha256")):
        raise SystemExit("Error: MC-72 run/summary/parent identity mismatch")
    refs = {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}": r for r in manifest["items"]}
    parent_refs = {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}": r
                   for r in parent["items"] if r["dataset_id"] in expected}
    if refs != parent_refs or len(refs) != 1299 or len(refs) != len(manifest["items"]):
        raise SystemExit("Error: MC-72 is not the exact five-dataset main-v1 subset")
    for pid in PROFILES:
        path = run_path.replace("run.json", "predictions.jsonl") if pid == PROFILES[-1] else f"all_res/vi_multimodel_v1/main/{pid}/predictions.jsonl"
        predictions = [json.loads(line) for line in (root / path).read_text(encoding="utf-8").splitlines() if line.strip()]
        selected = [r for r in predictions if r["run_key"] in refs]
        if len(selected) != len(refs) or len({r["run_key"] for r in selected}) != len(refs):
            raise SystemExit(f"Error: missing/duplicate comparison prompts for {pid}")
        if any(r["status"] != "complete" or r["prompt_sha256"] != refs[r["run_key"]]["prompt_sha256"] for r in selected):
            raise SystemExit(f"Error: MC-72 comparison prompt drift/incomplete requests for {pid}")
    profile = next(p for p in profiles if p["profile_id"] == PROFILES[-1])
    condition, _ = modern_condition(root, run_path, profile, protocol, "main")
    condition["id"] += "-mc72"
    condition["sources"].append(source(summary_path, "MC-72 scores and confidence intervals"))
    # The run keeps its derived manifest hash. Only the comparison signature uses
    # the verified parent identity, allowing this exact subset to join Go peers.
    normalized = {**meta, "manifest_sha256": parent["manifest_sha256"],
                  "omp_session_policy": protocol["omp_session_policy"], "sdk_retries": meta["max_retries"]}
    caps = condition["controls"]["output_caps"]
    sig = signature(normalized, caps)
    if sig is None or meta.get("complete_items") != 1299:
        raise SystemExit("Error: MC-72 controls or coverage incomplete")
    rows = []
    datasets = summary["datasets"]
    if len(datasets) != len(expected) or {d["dataset_id"]: d["expected_n"] for d in datasets} != expected:
        raise SystemExit("Error: MC-72 summary dataset coverage mismatch")
    for dataset in datasets:
        if dataset["status"] != "complete" or dataset["completed_n"] != dataset["expected_n"]:
            raise SystemExit("Error: MC-72 summary is incomplete")
        label = next(d["label"] for d in protocol["datasets"] if d["id"] == dataset["dataset_id"])
        for metric in ("accuracy", "em", "token_f1"):
            if metric not in dataset:
                continue
            ci_key = "ci95" if metric == "accuracy" else f"{metric}_ci95"
            rows.append(row(condition["id"], dataset["dataset_id"], label, metric, dataset[metric],
                            n=dataset["expected_n"], correct=dataset.get("correct") if metric == "accuracy" else None,
                            ci=dataset.get(ci_key), truncated=dataset.get("truncated_n"), source_path=summary_path))
    return condition, sig, rows


def modern_report(root: Path, records: list[dict], *, version: int, phase: str, report_id: str, title: str,
                  selectors: set[str], surface: str) -> dict:
    protocol = read_json(root, f"data/vi_multimodel_protocol_v{version}.json")
    profiles = read_json(root, "data/vi_multimodel_profiles.json" if version == 1 else "data/vi_multimodel_profiles_v2.json")["profiles"]
    chosen = [r for r in records if r["condition"] in selectors]
    used = {r["profile_id"] for r in chosen}
    conditions, profile_to_condition, signatures = [], {}, {}
    for profile in profiles:
        pid = profile["profile_id"]
        if pid not in used:
            continue
        actual_phase = "pilot_omp" if version == 1 and phase == "pilot" and pid == "qwen3-5-9b-65k" else phase
        path = f"all_res/vi_multimodel_v{version}/{actual_phase}/{pid}/run.json"
        cond, sig = modern_condition(root, path, profile, protocol, actual_phase)
        conditions.append(cond); profile_to_condition[pid] = cond["id"]; signatures[cond["id"]] = sig
    extra_scores = []
    if version == 1 and phase == "main":
        matched = matched_qwen_main(root, protocol, profiles)
        if matched is not None:
            cond, sig, extra_scores = matched
            conditions.append(cond)
            signatures[cond["id"]] = sig
    groups = defaultdict(list)
    for cid, sig in signatures.items():
        if sig is not None:
            groups[sig].append(cid)
    for i, ids in enumerate(groups.values()):
        if len(ids) > 1:
            for cond in conditions:
                if cond["id"] in ids:
                    cond["comparison_group"] = f"{report_id}-nominal-{i}"
    report = {"id": report_id, "surface": surface, "title": title, "protocol": protocol["protocol_id"],
              "scope": "So sánh theo cấu hình danh nghĩa; API và cách provider diễn giải auto vẫn khác. Nhóm suy luận/sampling khác có condition riêng.",
              "conditions": conditions, "benchmarks": csv_score_rows(chosen, profile_to_condition) + extra_scores, "comments": [],
              "notes": ["CI95 lower và upper nằm ở cột riêng. Khoảng cách điểm chưa phải kết quả kiểm định ghép đôi.",
                        "Truncation: phản hồi kết thúc do length; cap do benchmark đặt. Mẫu số giữ các câu không parse được."]}
    if version == 1:
        report["notes"].append("Reading-400 có gold user-reviewed, trong đó có đáp án kế thừa từ output model; EM/Token-F1 là lexical metrics, cần human/semantic-judge evaluation để kết luận mức đúng về nghĩa.")
        if phase == "main":
            report["notes"].append("Qwen MC-56 dùng temp 0 / thinking off / seed 42; không cùng nhóm ranking với ba OpenCode Go temp hiệu lực 1 / auto / không seed. Điểm Qwen vẫn là kết quả hợp lệ của condition riêng.")
            if extra_scores:
                report["notes"].append("Qwen MC-72 hoàn tất 1.299 câu ở năm dataset ngoài VMLU: temp 1 / auto / không seed. Prompt hashes đã đối chiếu với từng run Go; giữ MC-56 riêng, không trộn điểm giữa hai condition.")
    if version == 2:
        report["notes"] += ["VMLU Test server grade do người dùng cung cấp; Test không có local gold. Không suy correct count/CI từ tỷ lệ đã làm tròn; category/subject chưa có mẫu số riêng.",
                            "MC-70 dùng temp 1 / auto / không seed; MC-65 đã bị hủy và không được trộn vào bảng. V-Bench vẫn deferred theo yêu cầu người dùng."]
    if phase == "pilot":
        report["notes"].append("Pilot là diagnostics, số câu nhỏ và có repeat requests riêng; các lượt lặp không thuộc mẫu số accuracy/EM. Không dùng làm leaderboard hoặc so trực tiếp với main.")
    for record in chosen:
        if record["record_type"] == "phase_summary":
            diagnostics = [f"{label}: {record[key]}" for key, label in (("request_completed_n", "request complete"), ("request_expected_n", "request expected"), ("request_error_n", "request errors cuối"), ("truncated_n", "truncation tổng")) if record.get(key, "") != ""]
            if diagnostics:
                report["notes"].append(record["model_name"] + " · " + "; ".join(diagnostics) + ". Truncation xuất hiện ở nhiều metric của cùng dataset không được cộng lặp.")
        if record["record_type"] == "dataset" and record["dataset_id"].endswith("vmlu-test") and number(record.get("unparsed_n")):
            report["notes"].append(f"{record['model_name']} · Test có {record['unparsed_n']} output không parse được/blank. Đây là diagnostic của output; server grade đã được ghi riêng.")
    report["comments"] = comments_for(report)
    if version == 1 and phase == "main":
        matched = {c["id"]: c for c in conditions if c["comparison_group"]}
        metric_rows = defaultdict(list)
        for score in report["benchmarks"]:
            if score["condition_id"] in matched and score["level"] == "dataset":
                metric_rows[(score["dataset"], score["metric"])].append(score)
        wins = defaultdict(int)
        for scores in metric_rows.values():
            best = max(scores, key=lambda s: s["score"])
            wins[matched[best["condition_id"]]["model"]] += 1
        report["comments"].insert(0, "Trong nhóm cấu hình khớp, số metric dataset đứng đầu: " + "; ".join(f"{model}: {n}/{len(metric_rows)}" for model, n in wins.items()) + ". Kết quả phân biệt khả năng trả lời khớp reference ở đọc hiểu và làm MC/NLI; không tạo điểm tổng hợp ngôn ngữ.")
        report["comments"].insert(1, "Các cột đọc hiểu cho biết model tái hiện được nội dung tham chiếu từ context đến mức nào. EM thấp nhưng F1 cao có thể là diễn đạt khác hoặc trả lời dài; muốn phân biệt với sai nội dung cần semantic/human judging. Legal MC và NLI cần đọc riêng vì đo dạng suy luận khác nhau.")
    if version == 2 and phase == "vmlu":
        report["comments"].insert(0, "Category VMLU mô tả việc trả lời câu hỏi tiếng Việt gắn với kiến thức STEM, xã hội, nhân văn và nghiệp vụ. Ưu thế trải trên nhiều category hỗ trợ nhận định model làm tốt nhiều dạng MC trong condition này; phép đo chưa tách riêng hiểu ngôn ngữ, kiến thức nhớ được và reasoning.")
        for cond in conditions:
            cats = [r for r in report["benchmarks"] if r["condition_id"] == cond["id"] and r["metric"] == "server_accuracy" and r["level"] == "category"]
            if cats:
                high, low = max(cats, key=lambda r: r["score"]), min(cats, key=lambda r: r["score"])
                report["comments"].insert(-1, f"Profile {cond['model']}: {high['category']} {high['score']:.2f}% cao nhất, {low['category']} {low['score']:.2f}% thấp nhất trong bốn nhóm Test. Đây là mô tả domain của run; độ khó/số câu giữa category chưa được kiểm soát như nhau.")
        categories = {r["category"]: {} for r in report["benchmarks"] if r["level"] == "category" and r["metric"] == "server_accuracy"}
        for r in report["benchmarks"]:
            if r["level"] == "category" and r["metric"] == "server_accuracy":
                categories[r["category"]][next(c["model"] for c in conditions if c["id"] == r["condition_id"])] = r["score"]
        differences = [f"{category} {values['MiMo V2.6 Flash'] - values['MiMo V2.5']:+.2f} pp" for category, values in categories.items() if "MiMo V2.6 Flash" in values and "MiMo V2.5" in values]
        if differences:
            report["comments"].insert(-1, "MiMo V2.6 Flash so với MiMo V2.5 ở Test: " + "; ".join(differences) + ". Chênh lệch nhỏ cần repeat/paired analysis trước khi kết luận khác biệt ổn định.")
    return report


def historical_condition(root: Path, cards: dict, cid: str, model: str, card_ids: list[str], *, config: dict | None = None,
                         harness: bool = False, arm: str = "", label: str = "") -> dict:
    if any(card not in cards for card in card_ids):
        raise SystemExit(f"Error: missing historical card {card_ids}")
    card = cards[card_ids[0]]
    meta = config or {}
    qwen28 = "28K" in model
    pinned = arm in {"M6", "M6L", "T65", "F5", "F7", "F8", "T65r2", "T65r3"}
    tools = "none (gọi API trực tiếp)" if not harness else (
        "read,bash,edit,write,grep,glob; không tự suy là có search" if arm in {"H2", "H3", "H6", "H8", "V1"}
        else "all / OMP default menu" if arm in {"T65", "F8", "T65r2", "T65r3"} else "none")
    thinking = field(card, "reasoning / sampling", "reasoning", "cot")
    if not harness and qwen28:
        thinking = "non-thinking backend theo MC-4; no-CoT trong user prompt"
    elif harness and arm in {"M6", "M6L"}:
        thinking = 'reasoning_effort="none" ghim bằng proxy (MC-29/30)'
    elif harness and arm in {"H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "V1"}:
        thinking = "--thinking off theo condition MC-15/22; mức reasoning nội bộ không có telemetry độc lập"
    elif harness:
        thinking = "Level thinking chính xác chưa ghi lại trong artifact; reasoning native không ghim (xem card)"
    elif thinking == "không":
        thinking = "User prompt không yêu cầu CoT; native thinking/effort chưa ghi nhận"
    fields = {
        "date": field(card, "ngay_chay", "trạng_thái"),
        "harness": (field(card, "harness") if "harness" in card["fields"] else "OMP JSON; snapshot lịch sử ghi v18.2.7, version riêng từng run chưa ghi đầy đủ") if harness else "OpenAI-compatible API trực tiếp; không qua agent harness",
        "provider": field(card, "endpoint", "model_id / endpoint", "model", "model_id"),
        "temperature": "0.0 ghim proxy (MC-29+)" if pinned else (
            "0.0 requested theo card; hiệu lực chưa xác minh vì OMP từng bỏ temperature (MC-29)" if harness
            else f"{meta.get('temperature', field(card, 'temperature', 'temperature / seed'))} gửi theo runner; không khẳng định endpoint deterministic"),
        "thinking": thinking,
        "seed": "OMP không gửi seed; seed 42 trong card không đảm bảo được truyền" if harness else f"{meta.get('seed', field(card, 'seed', 'temperature / seed'))} theo runner",
        "tools": tools,
        "prompt": label if harness else field(card, "prompt_style", "prompt / scoring", "prompt"),
        "context": "User prompt giữ nguyên của arm A cùng model; context có sẵn cho reading, MC closed-book" if harness else field(card, "benchmark", "sample", "tap"),
        "session": "scratch/item, no session; H1–H4 có APPEND_SYSTEM.md; M6L có repo AGENTS.md; các arm clean ở /tmp" if harness else "Mỗi câu một request; chưa ghi model history ngoài request",
        "output_cap": "OMP/provider-managed; historical output cap chưa ghi đủ; không dùng cap 4096 của V1 để gán lại" if harness else f"{meta['max_tokens']} token do runner đặt" if "max_tokens" in meta else field(card, "max_tokens", "max_completion_tokens"),
        "workers": str(meta.get("workers", field(card, "workers"))),
        "timeout": "180 giây/item theo card harness" if harness else field(card, "timeout", "max_time"),
        "retry": field(card, "retry", "scoring / retry"),
        "gold": field(card, "scoring", "prompt / scoring", "metric"),
        "identity": model + "; " + field(card, "quantization"),
    }
    # Keep per-card metadata in full, without inferring inherited controls.
    for key in ("dieu_kien", "harness / prompt", "prompt", "system_prompt", "max_time", "workers", "4_o"):
        if key in card["fields"]:
            fields[f"recorded:{key}"] = card["fields"][key]
    controls = {
        "profile_id": model, "transport": "omp" if harness else "direct", "harness_version": None,
        "tools": "none" if not harness else None, "temperature_requested": meta.get("temperature"),
        "temperature_effective": None, "thinking": "off" if not harness and (qwen28 or model == "qwen38-nothink") else None,
        "seed_sent": True if not harness and "seed" in meta else None, "seed_requested": meta.get("seed"),
        "output_caps": ({"reading" if meta.get("prompt_style") == "build_reading_prompt" else "multiple_choice": meta["max_tokens"]} if "max_tokens" in meta else {}),
        "workers": meta.get("workers"), "system_prompt": "user prompt only" if not harness else None,
        "prompt_version": meta.get("prompt_style"),
    }
    return {"id": cid, "model": model, "card": ", ".join(card_ids), "comparison_group": None, "fields": fields,
            "sources": [source(f"measurement_card.md#L{cards[id]['line']}", id) for id in card_ids],
            "manifest_sha256": None, "measurement_card_hash": None, "controls": controls}


def vbench_scores(cid: str, dataset: str, records: list[dict], path: str, *, reported_macro: float | None = None) -> list[dict]:
    """Domain mean and item-weighted micro are distinct reported metrics."""
    if not records:
        raise SystemExit("Error: empty V-Bench server score source")
    total = sum(int(r["total"]) for r in records)
    correct = sum(int(r["correct"]) for r in records)
    macro = reported_macro if reported_macro is not None else sum(float(r["score"]) for r in records) / len(records)
    scores = [row(cid, dataset, "V-Bench · micro", "server_accuracy", round(100 * correct / total, 2), n=total, correct=correct, gold="server", source_path=path),
              row(cid, dataset, "V-Bench · macro", "server_macro", round(macro, 2), gold="server", source_path=path)]
    for a in records:
        scores.append(row(cid, dataset, "V-Bench domain", "server_accuracy", a["score"], level="category", category=f"{a['track']} / {a['domain']}", n=a["total"], correct=a["correct"], gold="server", source_path=path))
    return scores


def historical_vmlu_test(root: Path, cid: str, dataset: str) -> list[dict]:
    path = "docs/vmlu-leaderboard-qwen35.md"
    text = (root / path).read_text(encoding="utf-8")
    overall = re.search(r"## Overall: ([\d,]+)%", text)
    if overall is None:
        raise SystemExit("Error: missing MC-7 official overall score")
    scores = [row(cid, dataset, "VMLU Test cũ", "server_accuracy", overall.group(1).replace(",", "."), n=9833, gold="withheld", source_path=path)]
    categories = {"STEM", "Social Science", "Humanity", "Other"}
    for name, score in re.findall(r"^\| ([\w ]+) \| ([\d,]+) \|$", text, re.M):
        scores.append(row(cid, dataset, "VMLU Test cũ", "server_accuracy", score.replace(",", "."), level="category" if name in categories else "subject", category=name, gold="withheld", source_path=path))
    if len(scores) != 63:
        raise SystemExit(f"Error: MC-7 server breakdown drift: {len(scores)} records")
    return scores


def legacy_direct_reports(root: Path, cards: dict) -> list[dict]:
    models = {m["_id"]: m["display_name"] for m in MODELS}
    model_meta = {m["_id"]: m for m in MODELS}
    reports = []
    for slug, model_id, files in MIGRATION_PLAN:
        report = {"id": f"history-direct-{model_id}", "surface": "history", "title": f"Lịch sử · {models[model_id]} · API trực tiếp",
                  "protocol": "measurement-card-history", "scope": "Các condition và bộ câu cũ; không xếp hạng chéo với V1/V2 hoặc model khác khi budget/thinking/gold khác.",
                  "conditions": [], "benchmarks": [], "comments": [], "notes": ["Metadata thiếu được hiển thị rõ; ngày và condition lấy theo từng card, không lấy model_info chung của snapshot cũ."]}
        for filename, dataset, card_id, kind in files:
            if slug == "Qwen3_5-9B-28K" and dataset == "reading-400":
                card_id = "MC-3b"
            config = runner_config(card_id if card_id != "MC-3b" else "MC-3", dataset)
            cid = f"{report['id']}-{dataset}"
            cond = historical_condition(root, cards, cid, models[model_id], [card_id], config=config)
            info = model_meta[model_id]
            cond["fields"]["identity"] = f"{info['display_name']} · {info['params']} · quantization {info.get('quantization') or 'không công bố'}"
            if model_id == "qwen38-nothink":
                cond["fields"]["thinking"] = "Ollama Modelfile think false theo registry/MC-6; user prompt no-CoT"
            if card_id == "MC-8":
                report["notes"].append("V-Bench MC-8 submission gồm 14 agentic rows gọi lại bằng guided prompt. Grade này có treatment khác ở 14 rows; không gộp thành baseline minimal đồng nhất.")
            artifact = f"all_res/ollama_result/{slug}/{filename}"
            cond["sources"].append(source(artifact, "Final artifact")); report["conditions"].append(cond)
            if not (root / artifact).is_file():
                raise SystemExit(f"Error: missing published historical artifact {artifact}")
            if dataset == "vmlu-mqa-test":
                report["benchmarks"].extend(historical_vmlu_test(root, cid, dataset))
                continue
            if kind == "mc":
                records = read_csv(root, artifact)
                if any("correct" not in r for r in records):
                    raise SystemExit(f"Error: MC artifact without correctness {artifact}")
                correct = sum(int(float(r["correct"])) for r in records)
                report["benchmarks"].append(row(cid, dataset, dataset, "accuracy", round(100 * correct / len(records), 2), n=len(records), correct=correct, source_path=artifact))
                accuracy_name = filename.replace("full_evaluation", "accuracy")
                apath = f"all_res/ollama_result/{slug}/{accuracy_name}"
                if (root / apath).is_file():
                    for a in read_csv(root, apath):
                        if a.get("level") == "category":
                            report["benchmarks"].append(row(cid, dataset, dataset, "accuracy", a["accuracy"], level="category", category=a["name"], n=a["n"], correct=a["correct"], source_path=apath))
            elif kind == "reading":
                summary = f"all_res/ollama_result/{slug}/{filename.replace('reading_scores', 'reading_summary')}"
                for a in read_csv(root, summary):
                    level = "dataset" if a["dataset"] == "ALL" or dataset != "reading-400" else "category"
                    for metric in ("em", "char_f1"):
                        report["benchmarks"].append(row(cid, dataset, dataset, metric, a[metric], level=level, category="" if level == "dataset" else a["dataset"], n=a["n"], source_path=summary))
                report["notes"].append("Reading-400: gold có đáp án kế thừa từ model được người duyệt chấp nhận; các lexical score cần đọc cùng thiên lệch reference. ViBidLQA dùng file-gold upstream, chưa review lại tại repo.")
            else:
                server = f"all_res/ollama_result/{slug}/vbench_server_scores_{slug}.csv"
                if (root / server).is_file():
                    report["benchmarks"].extend(vbench_scores(cid, dataset, read_csv(root, server), server))
                    report["notes"].append("V-Bench macro là trung bình domain; micro là tỷ lệ đúng theo item. Cột Correct/n thuộc micro/domain, không phải numerator của macro.")
                elif card_id == "MC-2":
                    snapshot = read_json(root, "web/public/benchmark-data.json")["vbench"]
                    report["benchmarks"].extend(vbench_scores(cid, dataset, snapshot["domains"], "web/public/benchmark-data.json", reported_macro=snapshot["macro_score"]))
                    report["notes"].append("MC-2 V-Bench lấy từ snapshot công bố và card MC-2; không gán model_info chung cho các block khác. Macro và micro giữ metric riêng.")
                else:
                    report["notes"].append(f"Chưa có server score artifact cho {dataset}; không thay bằng schema validity.")
        report["comments"] = comments_for(report)
        for cond in report["conditions"]:
            categories = [r for r in report["benchmarks"] if r["condition_id"] == cond["id"] and r["level"] == "category" and r["metric"] == "accuracy"]
            if categories:
                high, low = max(categories, key=lambda r: r["score"]), min(categories, key=lambda r: r["score"])
                report["comments"].insert(0, f"Trong {cond['model']} / {high['dataset']}, {high['category']} đạt {high['score']:.2f}%, {low['category']} đạt {low['score']:.2f}%. Đây là mô tả category của cùng run; bộ câu và kích thước category khác nhau.")
        reports.append(report)
    return reports


def legacy_harness_reports(root: Path, cards: dict, block: dict) -> list[dict]:
    groups = defaultdict(list)
    for r in block["ladder"]:
        groups[(r["model"], r["arm"], r["arm_slug"])].append(r)
    reports = []
    for (model, arm, slug), scores in groups.items():
        # Baselines use dataset-specific cards rather than attributing everything to one run.
        baseline_cards = {"reading400": "MC-3b", "legal_mc": "MC-10", "legal_nli": "MC-13", "bidlqa_val": "MC-12", "vbench_agentic": "MC-8"}
        card_ids = sorted(set(re.findall(r"MC-\d+[a-z]?", str(scores[0].get("card") or ""))))
        if scores[0].get("card") == "MC-15/16/17": card_ids = ["MC-15", "MC-16", "MC-17"]
        if scores[0].get("card") == "MC-31/32": card_ids = ["MC-31", "MC-32"]
        if scores[0].get("card") == "MC-46/47": card_ids = ["MC-46", "MC-47"]
        if not card_ids:
            card_ids = sorted({baseline_cards[r["dataset"]] for r in scores}) if arm == "A" else ["MC-30" if arm == "A2" else "MC-31"]
        cid = f"history-{slug.lower()}"
        cond = historical_condition(root, cards, cid, model, card_ids, harness=arm not in {"A", "A2", "A3"}, arm=arm, label=scores[0]["label"])
        if arm in {"A", "A2", "A3"}:
            cond["fields"]["temperature"] = "0.0 gửi theo card/runner; hiệu lực tùy API"
            cond["fields"]["seed"] = "42 gửi theo card/runner"
            cond["fields"]["output_cap"] = "MC: 4 token; reading: 48 token; V-Bench theo card riêng, không tự suy cap cho mọi track"
            cond["fields"]["context"] = "MC closed-book; reading có context trong prompt; V-Bench có schema ở từng item"
            cond["fields"]["prompt"] = scores[0]["label"] + "; build_prompt / build_reading_prompt / V-Bench minimal theo từng dataset"
        cond["sources"].append(source("web/public/benchmark-data.json", "Published harness ladder"))
        report = {"id": cid, "surface": "history", "title": f"{model} · {arm} · {scores[0]['label']}", "protocol": "historical-harness-arm",
                  "scope": "Ablation so với arm A của chính model, trên dataset/n ghi ở từng dòng. Cấu hình thay đổi có chủ đích; không dùng delta này làm ranking giữa model.",
                  "conditions": [cond], "benchmarks": [], "comments": [], "notes": ["CI ở cột Δ thuộc chênh lệch với arm A; không dùng làm CI cho điểm của arm B.",
                                                                                          "Agreement và schema validity là diagnostics; server accuracy được giữ thành metric riêng."]}
        if arm in {"H1", "H2", "H3", "H4"}:
            report["notes"].append("MC-22 phát hiện APPEND_SYSTEM.md lọt vào các run này. Kết quả đo cả cấu hình máy; không quy nguyên nhân chỉ cho OMP.")
        if arm == "M6L": report["notes"].append("Sandbox trong repo nạp AGENTS.md; đây là điều kiện khác M6 clean.")
        for a in scores:
            metric = a["metric"]
            report["benchmarks"].append(row(cid, a["dataset"], a["dataset_label"], metric.lower() if metric == "EM" else metric, a["arm_b"], n=a["n"], gold="none" if metric in {"valid_rate", "agreement"} else "local", source_path="web/public/benchmark-data.json", delta=a.get("delta") if a.get("role") != "baseline" else None,
                                            delta_ci=[a["ci95_low"], a["ci95_high"]] if a.get("role") != "baseline" else None))
            if a.get("char_f1") is not None:
                report["benchmarks"].append(row(cid, a["dataset"], a["dataset_label"], "char_f1", a["char_f1"], n=a["n"], source_path="web/public/benchmark-data.json"))
            if a.get("server_score") is not None:
                report["benchmarks"].append(row(cid, a["dataset"], a["dataset_label"], "server_accuracy", a["server_score"], n=a.get("server_total"), correct=a.get("server_correct"), gold="server", source_path="web/public/benchmark-data.json"))
            if a.get("role") != "baseline" and metric in {"EM", "accuracy"}:
                report["comments"].append(f"{a['dataset_label']}: {a['arm_b']:.2f}% ở arm {arm}, {a['arm_a']:.2f}% ở arm A cùng model; Δ {a['delta']:+.2f} pp. Diễn giải theo toàn bộ thay đổi system/tools/budget/sampling đã ghi trong condition.")
        if not report["comments"]: report["comments"] = comments_for(report)
        if any(a["metric"] == "EM" for a in scores):
            report["comments"].append("EM thay đổi ở arm harness còn chịu ảnh hưởng độ dài/cách trình bày câu trả lời và output budget. Không suy trực tiếp rằng hiểu nội dung giảm/tăng chỉ từ mức khớp chuỗi này.")
        reports.append(report)
    return reports


def full_tools_report(root: Path, cards: dict) -> dict:
    slug = "muse-spark-1-3-contributor-h2-legal-mc-full-tools-auto"
    path = f"all_res/ollama_result/{slug}/harness_ledger_legal_mc_{slug}.csv"
    records = read_csv(root, path)
    if len(records) != 146 or len({r["item_id"] for r in records}) != 146:
        raise SystemExit("Error: MC-71 ledger coverage drift")
    cid = "muse-full-tools-mc71"
    card = cards["MC-71"]
    cond = {"id": cid, "model": "Muse Spark 1.3 Contributor", "card": "MC-71", "comparison_group": None,
            "fields": {"date": field(card, "trạng_thái"), "harness": field(card, "harness"), "provider": field(card, "model / API"),
                       "temperature": "không gửi; hiệu lực theo provider default 1.0", "thinking": "auto; reasoning level không ghim low/medium/high",
                       "seed": "không gửi", "tools": field(card, "tools / persona"), "prompt": "OMP coding-agent system prompt mặc định; user prompt/parser legal-MC đóng băng",
                       "context": field(card, "dataset"), "session": "process/scratch riêng mỗi item; không history/repo instructions", "output_cap": field(card, "output cap / timeout"),
                       "workers": field(card, "workers / sandbox"), "timeout": "180 giây/item", "retry": "Lỗi ghi trong ledger; 0 failure trên lượt này",
                       "gold": field(card, "scoring"), "identity": "zen-go/muse-spark-1.3-contributor; quantization không công bố"},
            "sources": [source(path, "Full-tools ledger"), source("measurement_card.md", "MC-71")], "manifest_sha256": None, "measurement_card_hash": None}
    correct = sum(int(float(r["correct"])) for r in records)
    return {"id": cid, "surface": "v2", "title": "Muse · full OMP tools · legal-MC (MC-71)", "protocol": "MC-71-full-harness",
            "scope": "Một model trong condition tools all + OMP system prompt + auto. Các run tools-none hoặc temp 0 không thuộc cùng bảng ranking.",
            "conditions": [cond], "benchmarks": [row(cid, "legal_mc", "Legal MC", "accuracy", round(correct / 146 * 100, 2), n=146, correct=correct, source_path=path)],
            "comments": [f"Muse trả đúng {correct}/146 ({correct / 146 * 100:.2f}%) câu Legal MC trong full harness. Điểm phản ánh cả model và công cụ được phép; chưa có model thứ hai trong cùng condition để kết luận ưu thế model.",
                         "36 item có tool call, 39 calls gồm 37 web_search và 2 read (audit MC-71). Quyền có tool và việc thực sự gọi tool được ghi riêng."],
            "notes": ["4 shard cố định 37/37/36/36 chạy đồng thời; timeout/output cap do benchmark đặt.", "0 failure, 0 blank, 1 network-attempt audit; chưa có repeat run hoặc paired significance test."]}


def validate(report: dict) -> None:
    conditions = {c["id"] for c in report["conditions"]}
    if len(conditions) != len(report["conditions"]) or not conditions:
        raise SystemExit(f"Error: duplicate/empty conditions in {report['id']}")
    seen = set()
    for r in report["benchmarks"]:
        key = (r["condition_id"], r["dataset_id"], r["level"], r["category"], r["metric"])
        if key in seen: raise SystemExit(f"Error: duplicate report metric {key}")
        seen.add(key)
        if r["condition_id"] not in conditions or r["score"] is None or not 0 <= r["score"] <= 100:
            raise SystemExit(f"Error: invalid report metric {key}")
        if r["metric"] == "accuracy" and r["gold"] in {"withheld", "server"}:
            raise SystemExit(f"Error: local accuracy on withheld gold {key}")
        if r["gold"] == "withheld" and (r["correct"] is not None or r["ci_low"] is not None or r["ci_high"] is not None):
            raise SystemExit(f"Error: inferred withheld-gold count/CI {key}")


def build(root: Path = ROOT) -> dict:
    records = read_csv(root, SCORE_CSV); cards = card_index(root)
    reports = [
        modern_report(root, records, version=1, phase="main", report_id="main-v1", title="Main V1 · sáu dataset tiếng Việt", selectors={"main_v1"}, surface="v1"),
        modern_report(root, records, version=1, phase="pilot", report_id="pilot-v1", title="Pilot V1 · diagnostics", selectors={"pilot", "pilot_omp"}, surface="v1"),
        modern_report(root, records, version=2, phase="vmlu", report_id="vmlu-v2", title="VMLU V2 · Dev / Valid / Test server", selectors={"vmlu_v2", "vmlu_v2_server_scored"}, surface="v2"),
        modern_report(root, records, version=2, phase="pilot", report_id="pilot-v2", title="Pilot V2 · VMLU + synthetic agentic", selectors={"pilot_v2"}, surface="v2"),
        full_tools_report(root, cards),
        *legacy_direct_reports(root, cards),
        *legacy_harness_reports(root, cards, read_json(root, "web/public/benchmark-data.json")["harness"]),
    ]
    for report in reports:
        report["notes"] = list(dict.fromkeys(report["notes"]))
        validate(report)
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "field_labels": FIELD_LABELS,
            "metric_labels": METRIC_LABELS, "reports": reports}


def markdown(data: dict) -> str:
    lines = ["# Báo cáo điều kiện và benchmark", "", "Nguồn: measurement_card.md và artifact từng run. Projection reporting v1; giữ metric/denominator lịch sử.", ""]
    for report in data["reports"]:
        lines += [f"## {report['title']}", "", report["scope"], "", "### Condition", ""]
        for cond in report["conditions"]:
            lines += [f"**{cond['model']} · {cond['card']}**", "", "| Trường | Giá trị |", "| --- | --- |"]
            for k, v in cond["fields"].items():
                lines.append(f"| {FIELD_LABELS.get(k, k)} | {str(v).replace('|', '/')} |")
            lines.append("")
        lines += ["### Benchmark", "", "| Model / card | Dataset/category | Metric | n | Correct | Score % | CI95 lower | CI95 upper | Δ pp | Δ CI lower | Δ CI upper |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        conditions = {c["id"]: c for c in report["conditions"]}
        for r in report["benchmarks"]:
            if r["level"] == "subject": continue
            c = conditions[r["condition_id"]]
            values = [r[k] for k in ("n", "correct", "score", "ci_low", "ci_high", "delta", "delta_ci_low", "delta_ci_high")]
            cells = ["—" if v is None else str(v) if i < 2 else f"{v:.2f}" for i, v in enumerate(values)]
            lines.append(f"| {c['model']} / {c['card']} | {r['dataset']}{' / ' + r['category'] if r['category'] else ''} | {METRIC_LABELS[r['metric']]} | " + " | ".join(cells) + " |")
        lines += ["", "### Comment", "", *[f"- {x}" for x in report["comments"]], "", "### Note", "", *[f"- {x}" for x in dict.fromkeys(report["notes"])], ""]
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(data: dict, root: Path) -> None:
    targets = {"web/data/benchmark-reports.json": json.dumps(data, ensure_ascii=False, indent=2) + "\n",
               "docs/research/benchmark-condition-reports.md": markdown(data)}
    for path, content in targets.items():
        dest = root / path; dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_suffix(dest.suffix + ".tmp"); temp.write_text(content, encoding="utf-8"); temp.replace(dest)
    dest = root / "docs/research/benchmark-condition-reports.csv"
    fields = ["report_id", "report_title", "condition_id", "model", "card", "comparison_group", "manifest_sha256", "measurement_card_hash", *FIELD_LABELS, "dataset_id", "dataset", "level", "category", "metric", "n", "correct", "score", "ci_low", "ci_high", "delta", "delta_ci_low", "delta_ci_high", "gold", "truncated", "source", "comment", "note"]
    with dest.with_suffix(".csv.tmp").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader()
        for report in data["reports"]:
            conditions = {c["id"]: c for c in report["conditions"]}
            for r in report["benchmarks"]:
                c = conditions[r["condition_id"]]
                writer.writerow({"report_id": report["id"], "report_title": report["title"], **{k:c.get(k) for k in ("model", "card", "comparison_group", "manifest_sha256", "measurement_card_hash")},
                                 **{k:c["fields"].get(k, UNKNOWN) for k in FIELD_LABELS}, **r,
                                 "comment": "\n".join(report["comments"]), "note": "\n".join(dict.fromkeys(report["notes"]))})
    dest.with_suffix(".csv.tmp").replace(dest)
    public = root / "web/public/benchmark-condition-reports.csv"
    public.parent.mkdir(parents=True, exist_ok=True)
    public_tmp = public.with_suffix(".csv.tmp")
    public_tmp.write_bytes(dest.read_bytes())
    public_tmp.replace(public)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(); data = build(args.root); write_outputs(data, args.root)
    print(f"wrote {len(data['reports'])} reports, {sum(len(r['benchmarks']) for r in data['reports'])} metric rows")


if __name__ == "__main__":
    main()
