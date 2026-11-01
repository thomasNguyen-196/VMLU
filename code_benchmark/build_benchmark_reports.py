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
    from code_benchmark import vi_reading_v3
    from code_benchmark.migrate_results_to_mongo import MIGRATION_PLAN, runner_config
    from code_benchmark.score_vi_multimodel import clustered_mean_interval
    from code_benchmark.seed_registries import MODELS
except ImportError:
    import vi_reading_v3
    from migrate_results_to_mongo import MIGRATION_PLAN, runner_config
    from score_vi_multimodel import clustered_mean_interval
    from seed_registries import MODELS

ROOT = Path(__file__).resolve().parents[1]
SCORE_CSV = "docs/research/vi-multimodel-all-results-2026-10-09.csv"
UNKNOWN = "Chưa ghi nhận trong artifact/card"
# Internal endpoint hosts never reach the published reports (web/data, web/public, docs/research).
INTERNAL_HOST = re.compile(r"(?:https?://)?llmapi\.iec(?:-uit\.com)?(?:/v1)?", re.IGNORECASE)
INTERNAL_HOST_LABEL = "IEC (host ẩn)"
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
    ("em_v3", "EM · v3 (bỏ dấu Markdown, chấm lại sau)"), ("token_f1_v3", "Token-F1 · v3 (bỏ dấu Markdown, chấm lại sau)"),
])
# vi-reading-v3 beside the registered vi-reading-v2 metrics (openspec diagnostic-router-loop, decision 10).
V3_METRICS = {"em": "em_v3", "token_f1": "token_f1_v3"}  # nosec B105 — metric names, not an auth token
V3_NOTE = ("EM · v3 và Token-F1 · v3 được chấm lại sau khi đã xem dữ liệu, bằng vi-reading-v3: bỏ dấu * và backtick khỏi "
           "câu trả lời rồi chấm như v2 (openspec diagnostic-router-loop, quyết định 10). Số đăng ký vẫn là EM và Token-F1 "
           "(v2); v2 trừ điểm câu trả lời in đậm dù đúng chữ.")


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


def _omp_web_search_usage(root: Path, paths: list[str]) -> dict:
    """Summarize web_search calls while keeping missing historical outcomes explicit."""
    dataset_labels = {
        "vi-multimodel-v1-vmlu-valid": "VMLU Valid",
        "vi-multimodel-v1-legal-nli-150": "Legal NLI",
        "vi-multimodel-v1-vi-squad-200": "Vi-SQuAD",
        "vi-multimodel-v1-vi-drop-200": "Vi-DROP",
        "vi-multimodel-v1-bidlqa-test": "ViBidLQA Test",
        "vi-multimodel-v2-vmlu-dev": "VMLU Dev",
        "vi-multimodel-v2-vmlu-test": "VMLU Test",
    }
    events = []
    for path in paths:
        if "muse12_omp_mc87" in path:
            source_label = "MC-87-R3" if "recovery_mc87_r3" in path else "MC-87-R2" if "recovery_mc87_r2" in path else "MC-87"
        elif "qwen_omp_mc88" in path:
            source_label = "MC-88"
        elif "mimo26_omp_mc89" in path:
            source_label = (
                "MC-89-R2" if "recovery_mc89_r2" in path
                else "MC-89-R1" if "recovery_mc89_1800s" in path
                else "MC-89"
            )
        else:
            source_label = "MC-86-R2" if "recovery_mc86_r2" in path else "MC-86"
        source_path = root / path
        if not source_path.is_file():
            raise SystemExit(f"Error: missing OMP tool attempt log {path}")
        for line_number, line in enumerate(source_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                attempt = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Error: invalid JSON in {path}:{line_number}") from exc
            names = attempt.get("tool_names") if isinstance(attempt.get("tool_names"), list) else []
            expected = sum(name == "web_search" for name in names)
            detailed = attempt.get("web_search_events")
            detailed = [event for event in detailed if isinstance(event, dict)
                        and event.get("tool_name") == "web_search"] if isinstance(detailed, list) else []
            calls = detailed if detailed else [None] * expected
            if detailed and len(detailed) < expected:
                calls = [*detailed, *([None] * (expected - len(detailed)))]
            for index, call in enumerate(calls, start=1):
                status = call.get("status") if call else "unrecorded"
                if status not in {"success", "failure", "unrecorded"}:
                    status = "unrecorded"
                dataset_id = str(attempt.get("dataset_id") or "unknown")
                run_key = str(attempt.get("run_key") or f"{dataset_id}:{attempt.get('item_id', 'unknown')}")
                attempt_number = int(attempt.get("attempt") or 1)
                events.append({
                    "event_id": f"{source_label}:{run_key}:{attempt_number}:web-search-{index}",
                    "source": source_label,
                    "dataset_id": dataset_id,
                    "dataset": dataset_labels.get(dataset_id, dataset_id),
                    "item_id": str(attempt.get("item_id") or "unknown"),
                    "phase": str(attempt.get("phase") or "unknown"),
                    "attempt": attempt_number,
                    "worker_id": attempt.get("worker_id") if isinstance(attempt.get("worker_id"), int) else None,
                    "call_index": index,
                    "tool_call_id": str(call.get("tool_call_id") or "") if call else "",
                    "status": status,
                    "status_source": str(call.get("status_source") or "attempt_summary_only") if call else "attempt_summary_only",
                    "started_at": str(attempt.get("started_at") or ""),
                    "finished_at": str(attempt.get("finished_at") or ""),
                })
    events.sort(key=lambda event: (event["started_at"], event["event_id"]), reverse=True)
    counts = {status: sum(event["status"] == status for event in events)
              for status in ("success", "failure", "unrecorded")}
    if sum(counts.values()) != len(events):
        raise SystemExit("Error: OMP web_search status counts do not reconcile")
    return {
        "total_calls": len(events),
        "succeeded": counts["success"],
        "failed": counts["failure"],
        "unrecorded": counts["unrecorded"],
        "events": events,
    }


def muse13_omp_full_tools_report(root: Path) -> tuple[dict, dict]:
    """Publish MC-86/R2 full-tools scores, keeping the Test grade server-sourced."""
    import hashlib

    base = "all_res/muse13_omp_mc86"
    profile = "muse-spark-1-3-contributor-omp-full-tools-mc86"
    main_dir = f"{base}/main/{profile}"
    vmlu_dir = f"{base}/vmlu/{profile}"
    grade_path = "docs/research/muse13-omp-vmlu-test-server-grade-mc86-r2-2026-10-17.json"
    submission_path = "submissions/vi_multimodel_v2/muse-spark-1-3-contributor/submission_vmlu_test_muse-spark-1-3-contributor_MC-86-R2.csv"
    submission_manifest_path = submission_path.replace(".csv", ".manifest.json")
    grade = read_json(root, grade_path)
    submission_meta = read_json(root, submission_manifest_path)
    condition_meta = read_json(root, f"{base}/condition.json")
    campaign = read_json(root, f"{base}/campaign.json")
    main_run = read_json(root, f"{main_dir}/run.json")
    vmlu_run = read_json(root, f"{vmlu_dir}/run.json")
    main_summary = read_json(root, f"{main_dir}/summary.json")
    vmlu_summary = read_json(root, f"{vmlu_dir}/summary.json")
    recovery1 = read_json(root, f"{base}/recovery_mc86_r1.json")
    recovery2 = read_json(root, f"{base}/recovery_mc86_r2/recovery.json")
    tool_attempt_paths = [f"{base}/attempts.jsonl", f"{base}/recovery_mc86_r2/attempts.jsonl"]
    web_search_usage = _omp_web_search_usage(root, tool_attempt_paths)
    runner_snapshot_path = f"{base}/runner-snapshots/run_muse13_omp_mc86.{condition_meta['runner_sha256']}.py"
    runner_snapshot = root / runner_snapshot_path
    if (not runner_snapshot.is_file()
            or hashlib.sha256(runner_snapshot.read_bytes()).hexdigest() != condition_meta["runner_sha256"]):
        raise SystemExit("Error: MC-86 original runner snapshot does not match frozen runner hash")
    submission_bytes = (root / submission_path).read_bytes()
    submission_hash = hashlib.sha256(submission_bytes).hexdigest()

    if (campaign.get("status") != "complete" or campaign.get("complete_items") != 12033
            or campaign.get("request_error_items") != 0):
        raise SystemExit("Error: MC-86 campaign is not complete")
    if (main_run.get("status") != "complete" or main_run.get("complete_items") != 1897
            or main_run.get("request_error_items") != 0 or main_summary.get("condition_sha256") != main_run.get("condition_sha256")):
        raise SystemExit("Error: MC-86 main coverage/summary mismatch")
    if (vmlu_run.get("status") != "complete" or vmlu_run.get("complete_items") != 10136
            or vmlu_run.get("request_error_items") != 0 or vmlu_summary.get("condition_sha256") != vmlu_run.get("condition_sha256")):
        raise SystemExit("Error: MC-86 VMLU coverage/summary mismatch")
    if recovery1.get("status") != "complete" or recovery1.get("successful_retries") != 13:
        raise SystemExit("Error: MC-86-R1 technical recovery is incomplete")
    if (recovery2.get("status") != "complete" or recovery2.get("selected_n") != 8
            or recovery2.get("parse_valid_n") != 8 or recovery2.get("blank_answer_n") != 0):
        raise SystemExit("Error: MC-86-R2 answer recovery is incomplete")
    if (grade.get("server_score_status") != "scored_user_provided" or grade.get("item_count") != 9833
            or grade.get("correct") is not None or grade.get("ci95") is not None
            or grade.get("condition_sha256") != main_run.get("condition_sha256")
            or grade.get("condition_sha256") != vmlu_run.get("condition_sha256")
            or grade.get("manifest_sha256") != vmlu_run.get("manifest_sha256")
            or grade.get("submission_sha256") != submission_hash
            or submission_meta.get("sha256") != submission_hash
            or submission_meta.get("recovery_id") != "MC-86-R2"):
        raise SystemExit("Error: MC-86-R2 server grade/submission provenance mismatch")

    cid = "muse13-omp-full-tools-mc86-r2"
    expected_main = {
        "vi-multimodel-v1-vmlu-valid": ("VMLU Valid", 744),
        "vi-multimodel-v1-legal-nli-150": ("Legal NLI", 150),
        "vi-multimodel-v1-vi-squad-200": ("Vi-SQuAD", 200),
        "vi-multimodel-v1-vi-drop-200": ("Vi-DROP", 200),
        "vi-multimodel-v1-bidlqa-test": ("ViBidLQA Test", 603),
    }
    main_datasets = {dataset["dataset_id"]: dataset for dataset in main_summary["datasets"]}
    if set(main_datasets) != set(expected_main):
        raise SystemExit("Error: MC-86 main dataset set changed")

    scores = []
    summary_datasets = []
    route = condition_meta["model_ref"]
    for dataset_id, (label, expected_n) in expected_main.items():
        dataset = main_datasets[dataset_id]
        n = int(dataset.get("expected_n", expected_n))
        if dataset.get("status") != "complete" or n != expected_n or dataset.get("completed_n") != expected_n:
            raise SystemExit(f"Error: incomplete MC-86 main dataset {dataset_id}")
        if "accuracy" in dataset:
            overall = next((item for item in dataset.get("accuracy_rows", []) if item.get("level") == "overall"), {})
            correct = dataset.get("correct", overall.get("correct"))
            ci = dataset.get("ci95")
            scores.append(row(cid, dataset_id, label, "accuracy", dataset["accuracy"], n=n,
                              correct=correct, ci=ci, source_path=f"{main_dir}/summary.json"))
        for metric, ci_key in (("em", "em_ci95"), ("token_f1", "token_f1_ci95")):
            if metric in dataset:
                scores.append(row(cid, dataset_id, label, metric, dataset[metric], n=n,
                                  ci=dataset.get(ci_key), source_path=f"{main_dir}/summary.json"))
        summary_datasets.append({
            "dataset_id": dataset_id, "dataset": label, "gold": "local",
            "request_completed": expected_n, "total_items": expected_n, "request_errors": 0,
            "coverage_pct": 100.0, "accuracy": dataset.get("accuracy"),
            "correct": dataset.get("correct"), "ci_low": None, "ci_high": None,
            "server_accuracy": None, "server_grade_source": None, "server_breakdown": [],
            "route_breakdown": [{"condition_id": cid, "route": route, "item_count": expected_n}],
        })

    vmlu_datasets = {dataset["dataset_id"]: dataset for dataset in vmlu_summary["datasets"]}
    dev_id, test_id = "vi-multimodel-v2-vmlu-dev", "vi-multimodel-v2-vmlu-test"
    dev = vmlu_datasets.get(dev_id)
    test = vmlu_datasets.get(test_id)
    if (dev is None or dev.get("status") != "complete_local_score" or dev.get("expected_n") != 303
            or dev.get("correct") != 275 or test is None or test.get("status") != "complete_awaiting_server_score"
            or test.get("request_completed_n") != 9833):
        raise SystemExit("Error: MC-86 Dev/Test summary mismatch")
    dev_label, test_label = "VMLU Dev", "VMLU Test"
    scores.append(row(cid, dev_id, dev_label, "accuracy", dev["accuracy"], n=303,
                      correct=dev["correct"], ci=dev.get("accuracy_ci95_wilson"),
                      truncated=dev.get("truncated_n"), source_path=f"{vmlu_dir}/summary.json"))
    scores.append(row(cid, test_id, test_label, "server_accuracy", grade["total"], n=9833,
                      gold="withheld", truncated=test.get("truncated_n", 0), source_path=grade_path))

    category_labels = {"stem": "STEM", "humanity": "Humanity", "social_science": "Social Science", "other": "Other"}
    server_breakdown = []
    for category_key in ("stem", "humanity", "social_science", "other"):
        category = grade["categories"][category_key]
        category_label = category_labels[category_key]
        scores.append(row(cid, test_id, test_label, "server_accuracy", category["total"],
                          level="category", category=category_label, gold="withheld", source_path=grade_path))
        server_breakdown.append({"category": category_label, "subject": None, "score": category["total"]})
        for subject, value in category["subjects"].items():
            subject_label = subject.replace("_", " ")
            scores.append(row(cid, test_id, test_label, "server_accuracy", value,
                              level="subject", category=f"{category_label} · {subject_label}",
                              gold="withheld", source_path=grade_path))
            server_breakdown.append({"category": category_label, "subject": subject, "score": value})

    condition = {
        "id": cid,
        "model": "Muse Spark 1.3 Contributor",
        "card": "MC-86 / R2",
        "comparison_group": None,
        "fields": {
            "date": f"{campaign['started_at']} → {campaign['finished_at']}",
            "harness": f"OMP · {condition_meta['omp_version']} · {condition_meta['omp_mode']} mode",
            "provider": f"{condition_meta['provider']} · Responses",
            "temperature": "requested 1.0; effective provider value not verified",
            "thinking": "auto; reasoning effort not pinned",
            "seed": "not sent",
            "tools": "all; OMP default full tool menu; auto-approve",
            "prompt": "OMP default coding-agent system prompt; MC-85 user prompts are frozen",
            "context": "question and choices; model does not receive gold",
            "session": "isolated process and scratch per item; no history; Bubblewrap sandbox",
            "output_cap": "20,000 tokens per assistant turn",
            "workers": "12 workers; global manifest-ordered queue; peak concurrency 12",
            "timeout": "MC-86: 300 seconds/item; R2: 600 seconds for 8 VMLU Test items",
            "retry": "13 terminal OMP errors retried once; 8 unparsed Test replies retried once under R2",
            "gold": "local for Main/Dev; VMLU Test gold withheld and scored by server",
            "identity": f"{condition_meta['model_ref']}; quantization not reported",
        },
        "sources": [
            source(f"{base}/condition.json", "MC-86 frozen condition"),
            source(runner_snapshot_path, "MC-86 runner source matching frozen SHA"),
            source(tool_attempt_paths[0], "MC-86 per-item tool attempt log"),
            source(tool_attempt_paths[1], "MC-86-R2 per-item tool attempt log"),
            source(f"{main_dir}/summary.json", "MC-86 Main local scores"),
            source(f"{vmlu_dir}/summary.json", "MC-86 Dev local score and Test coverage"),
            source(f"{base}/recovery_mc86_r1.json", "MC-86-R1 technical recovery"),
            source(f"{base}/recovery_mc86_r2/recovery.json", "MC-86-R2 timeout recovery"),
            source(grade_path, "User-provided VMLU Test server grade"),
            source(submission_path, "MC-86-R2 Test submission"),
        ],
        "manifest_sha256": vmlu_run["manifest_sha256"],
        "measurement_card_hash": condition_meta["measurement_card_sha256"],
        "controls": {
            "profile_id": profile,
            "transport": "omp",
            "harness_version": condition_meta["omp_version"],
            "tools": "all",
            "temperature_requested": condition_meta["temperature_requested"],
            "temperature_effective": condition_meta["temperature_effective"],
            "thinking": condition_meta["thinking"],
            "seed_sent": False,
            "seed_requested": None,
            "output_caps": {"multiple_choice": 20000, "reading": 20000},
            "workers": 12,
            "system_prompt": condition_meta["omp_system_prompt"],
            "prompt_version": condition_meta["protocol_id"],
        },
    }
    report = {
        "id": cid,
        "surface": "v2",
        "title": "Muse Spark 1.3 Contributor · OMP full tools · MC-86/R2",
        "protocol": condition_meta["protocol_id"],
        "scope": "MC-86: 12,033 Main/Dev/Test items, excluding the 146 Legal MC items covered by MC-71; R2 replaces 8 blank Test answers.",
        "conditions": [condition],
        "benchmarks": scores,
        "comments": [
            f"VMLU Test đạt {grade['total']:.2f}% theo server grade; Dev đạt {dev['accuracy']:.2f}% theo gold cục bộ.",
            "Bảng mô tả MC-86/R2; không ghép vào ranking OMP không-tools hoặc API Direct.",
        ],
        "notes": [
            "OMP dùng full tool menu và OMP coding-agent system prompt mặc định; tool access không đồng nghĩa model gọi tool trên từng câu.",
            "R2 dùng timeout 600 giây cho 8 câu VMLU Test; các câu còn lại giữ timeout 300 giây của MC-86.",
            "VMLU Test dùng server grade do người dùng cung cấp; không có per-item gold, số câu đúng hay CI95 để suy ra.",
        ],
    }
    if web_search_usage["unrecorded"]:
        report["notes"].append(
            f"Web search được gọi {web_search_usage['total_calls']} lượt; {web_search_usage['unrecorded']} lượt "
            "không có trạng thái kết quả trong attempt artifact cũ nên được giữ là chưa ghi nhận."
        )

    run_summary = {
        "id": cid,
        "title": "Muse Spark 1.3 · OMP full tools · MC-86/R2",
        "model": "Muse Spark 1.3 Contributor",
        "condition": "OMP · full tools · 12 workers · 20.000 tokens/turn; R2 timeout 600s cho 8 Test items",
        "status": "complete",
        "completed_items": 12033,
        "total_items": 12033,
        "request_errors": 0,
        "shards": 1,
        "workers_per_shard": 12,
        "total_workers": 12,
        "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 12033}],
        "datasets": [*summary_datasets,
            {"dataset_id": dev_id, "dataset": dev_label, "gold": "local", "request_completed": 303,
             "total_items": 303, "request_errors": 0, "coverage_pct": 100.0,
             "accuracy": dev["accuracy"], "correct": dev["correct"],
             "ci_low": dev["accuracy_ci95_wilson"][0], "ci_high": dev["accuracy_ci95_wilson"][1],
             "server_accuracy": None, "server_grade_source": None, "server_breakdown": [],
             "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 303}]},
            {"dataset_id": test_id, "dataset": test_label, "gold": "withheld", "request_completed": 9833,
             "total_items": 9833, "request_errors": 0, "coverage_pct": 100.0,
             "accuracy": None, "correct": None, "ci_low": None, "ci_high": None,
             "server_accuracy": grade["total"], "server_grade_source": grade_path,
             "server_breakdown": server_breakdown,
             "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 9833}]},
        ],
        "source": f"{base}/campaign.json",
        "web_search": web_search_usage,
        "notes": [
            "One shared global dataset queue, no fixed dataset ownership.",
            "Eight VMLU Test items use the MC-86-R2 600-second timeout override; all remaining items use 300 seconds.",
            "The VMLU Test server score has no locally available correct count or CI95.",
        ],
    }
    return report, run_summary


def muse12_omp_full_tools_report(root: Path) -> tuple[dict, dict]:
    """Publish MC-87/R3 full-tools scores, keeping the Test grade server-sourced."""
    import hashlib

    parent_base = "all_res/muse12_omp_mc87"
    base = f"{parent_base}/recovery_mc87_r3"
    profile = "muse-spark-1-2-contributor-omp-full-tools-mc87"
    main_dir = f"{base}/main/{profile}"
    vmlu_dir = f"{base}/vmlu/{profile}"
    grade_path = "docs/research/muse12-omp-vmlu-test-server-grade-mc87-r3-2026-10-19.json"
    submission_path = "submissions/muse-spark-1-2-contributor-omp-full-tools-mc87/submission.csv"
    submission_manifest_path = str(Path(submission_path).parent / "provenance.json")
    grade = read_json(root, grade_path)
    submission_meta = read_json(root, submission_manifest_path)
    condition_meta = read_json(root, f"{parent_base}/condition.json")
    campaign = read_json(root, f"{base}/campaign.json")
    main_run = read_json(root, f"{main_dir}/run.json")
    vmlu_run = read_json(root, f"{vmlu_dir}/run.json")
    main_summary = read_json(root, f"{main_dir}/summary.json")
    vmlu_summary = read_json(root, f"{vmlu_dir}/summary.json")
    recovery1 = read_json(root, f"{parent_base}/recovery_mc87_r1.json")
    recovery2 = read_json(root, f"{parent_base}/recovery_mc87_r2/recovery.json")
    recovery3 = read_json(root, f"{base}/recovery.json")
    tool_attempt_paths = [f"{parent_base}/attempts.jsonl", f"{parent_base}/recovery_mc87_r2/attempts.jsonl", f"{base}/attempts.jsonl"]
    web_search_usage = _omp_web_search_usage(root, tool_attempt_paths)
    runner_snapshot_path = f"{parent_base}/runner-snapshots/run_muse12_omp_mc87.{condition_meta['runner_sha256']}.py"
    runner_snapshot = root / runner_snapshot_path
    if (not runner_snapshot.is_file()
            or hashlib.sha256(runner_snapshot.read_bytes()).hexdigest() != condition_meta["runner_sha256"]):
        raise SystemExit("Error: MC-87 original runner snapshot does not match frozen runner hash")
    submission_bytes = (root / submission_path).read_bytes()
    submission_hash = hashlib.sha256(submission_bytes).hexdigest()

    if (campaign.get("status") != "complete" or campaign.get("complete_items") != 12033
            or campaign.get("request_error_items") != 0):
        raise SystemExit("Error: MC-87 campaign is not complete")
    if (main_run.get("status") != "complete" or main_run.get("complete_items") != 1897
            or main_run.get("request_error_items") != 0 or main_summary.get("condition_sha256") != main_run.get("condition_sha256")):
        raise SystemExit("Error: MC-87 main coverage/summary mismatch")
    if (vmlu_run.get("status") != "complete" or vmlu_run.get("complete_items") != 10136
            or vmlu_run.get("request_error_items") != 0 or vmlu_summary.get("condition_sha256") != vmlu_run.get("condition_sha256")):
        raise SystemExit("Error: MC-87 VMLU coverage/summary mismatch")
    if (recovery1.get("status") != "incomplete" or recovery1.get("successful_retries") != 46
            or recovery1.get("remaining_errors") != 30):
        raise SystemExit("Error: MC-87-R1 recovery provenance changed")
    if (recovery2.get("status") != "incomplete" or recovery2.get("selected_n") != 30
            or recovery2.get("successful_retries") != 26 or recovery2.get("remaining_errors") != 4):
        raise SystemExit("Error: MC-87-R2 recovery provenance changed")
    if (recovery3.get("status") != "complete" or recovery3.get("selected_n") != 4
            or recovery3.get("successful_retries") != 4 or recovery3.get("remaining_errors") != 0):
        raise SystemExit("Error: MC-87-R3 recovery is incomplete")
    frozen_hash = hashlib.sha256((root / f"{parent_base}/condition.json").read_bytes().strip()).hexdigest()
    if recovery3.get("parent_condition_sha256") != frozen_hash:
        raise SystemExit("Error: MC-87 parent condition hash mismatch")
    r2_ledger_hash = hashlib.sha256((root / tool_attempt_paths[1]).read_bytes()).hexdigest()
    parent_ledger_hash = hashlib.sha256((root / tool_attempt_paths[0]).read_bytes()).hexdigest()
    effective_hash = hashlib.sha256((root / f"{base}/condition.json").read_bytes().strip()).hexdigest()
    if (recovery3.get("parent_ledger_sha256") != parent_ledger_hash
            or recovery3.get("previous_recovery_ledger_sha256") != r2_ledger_hash
            or recovery3.get("recovery_condition_sha256") != effective_hash
            or main_run.get("condition_sha256") != effective_hash
            or vmlu_run.get("condition_sha256") != effective_hash
            or hashlib.sha256((root / f"{vmlu_dir}/submission_vmlu_test.csv").read_bytes()).hexdigest() != submission_hash):
        raise SystemExit("Error: MC-87/R3 ledger, effective condition or submission changed")
    latest = {}
    for path in tool_attempt_paths:
        for line in (root / path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                attempt = json.loads(line)
                latest[attempt["run_key"]] = attempt
    if len(latest) != 12033 or any(r.get("status") != "complete" or r.get("parse_valid") is False
                                  or not str(r.get("raw_response") or "").strip() for r in latest.values()):
        raise SystemExit("Error: MC-87/R3 overlay is not fully parsed and complete")
    if (grade.get("server_score_status") != "scored_user_provided" or grade.get("item_count") != 9833
            or grade.get("correct") is not None or grade.get("ci95") is not None
            or grade.get("condition_sha256") != main_run.get("condition_sha256")
            or grade.get("condition_sha256") != vmlu_run.get("condition_sha256")
            or grade.get("manifest_sha256") != vmlu_run.get("manifest_sha256")
            or grade.get("submission_sha256") != submission_hash
            or submission_meta.get("submission_sha256") != submission_hash
            or submission_meta.get("recovery_r3_condition_sha256") != grade.get("condition_sha256")):
        raise SystemExit("Error: MC-87-R2 server grade/submission provenance mismatch")

    cid = "muse12-omp-full-tools-mc87-r3"
    expected_main = {
        "vi-multimodel-v1-vmlu-valid": ("VMLU Valid", 744),
        "vi-multimodel-v1-legal-nli-150": ("Legal NLI", 150),
        "vi-multimodel-v1-vi-squad-200": ("Vi-SQuAD", 200),
        "vi-multimodel-v1-vi-drop-200": ("Vi-DROP", 200),
        "vi-multimodel-v1-bidlqa-test": ("ViBidLQA Test", 603),
    }
    main_datasets = {dataset["dataset_id"]: dataset for dataset in main_summary["datasets"]}
    if set(main_datasets) != set(expected_main):
        raise SystemExit("Error: MC-87 main dataset set changed")

    scores = []
    summary_datasets = []
    route = condition_meta["model_ref"]
    for dataset_id, (label, expected_n) in expected_main.items():
        dataset = main_datasets[dataset_id]
        n = int(dataset.get("expected_n", expected_n))
        if dataset.get("status") != "complete" or n != expected_n or dataset.get("completed_n") != expected_n:
            raise SystemExit(f"Error: incomplete MC-87 main dataset {dataset_id}")
        if "accuracy" in dataset:
            overall = next((item for item in dataset.get("accuracy_rows", []) if item.get("level") == "overall"), {})
            correct = dataset.get("correct", overall.get("correct"))
            ci = dataset.get("ci95")
            scores.append(row(cid, dataset_id, label, "accuracy", dataset["accuracy"], n=n,
                              correct=correct, ci=ci, source_path=f"{main_dir}/summary.json"))
        for metric, ci_key in (("em", "em_ci95"), ("token_f1", "token_f1_ci95")):
            if metric in dataset:
                scores.append(row(cid, dataset_id, label, metric, dataset[metric], n=n,
                                  ci=dataset.get(ci_key), source_path=f"{main_dir}/summary.json"))
        summary_datasets.append({
            "dataset_id": dataset_id, "dataset": label, "gold": "local",
            "request_completed": expected_n, "total_items": expected_n, "request_errors": 0,
            "coverage_pct": 100.0, "accuracy": dataset.get("accuracy"),
            "correct": dataset.get("correct"), "ci_low": None, "ci_high": None,
            "server_accuracy": None, "server_grade_source": None, "server_breakdown": [],
            "route_breakdown": [{"condition_id": cid, "route": route, "item_count": expected_n}],
        })

    vmlu_datasets = {dataset["dataset_id"]: dataset for dataset in vmlu_summary["datasets"]}
    dev_id, test_id = "vi-multimodel-v2-vmlu-dev", "vi-multimodel-v2-vmlu-test"
    dev = vmlu_datasets.get(dev_id)
    test = vmlu_datasets.get(test_id)
    if (dev is None or dev.get("status") != "complete_local_score" or dev.get("expected_n") != 303
            or dev.get("correct") != 278 or test is None or test.get("status") != "complete_awaiting_server_score"
            or test.get("request_completed_n") != 9833):
        raise SystemExit("Error: MC-87 Dev/Test summary mismatch")
    dev_label, test_label = "VMLU Dev", "VMLU Test"
    scores.append(row(cid, dev_id, dev_label, "accuracy", dev["accuracy"], n=303,
                      correct=dev["correct"], ci=dev.get("accuracy_ci95_wilson"),
                      truncated=dev.get("truncated_n"), source_path=f"{vmlu_dir}/summary.json"))
    scores.append(row(cid, test_id, test_label, "server_accuracy", grade["total"], n=9833,
                      gold="withheld", truncated=test.get("truncated_n", 0), source_path=grade_path))

    category_labels = {"stem": "STEM", "humanity": "Humanity", "social_science": "Social Science", "other": "Other"}
    server_breakdown = []
    for category_key in ("stem", "humanity", "social_science", "other"):
        category = grade["categories"][category_key]
        category_label = category_labels[category_key]
        scores.append(row(cid, test_id, test_label, "server_accuracy", category["total"],
                          level="category", category=category_label, gold="withheld", source_path=grade_path))
        server_breakdown.append({"category": category_label, "subject": None, "score": category["total"]})
        for subject, value in category["subjects"].items():
            subject_label = subject.replace("_", " ")
            scores.append(row(cid, test_id, test_label, "server_accuracy", value,
                              level="subject", category=f"{category_label} · {subject_label}",
                              gold="withheld", source_path=grade_path))
            server_breakdown.append({"category": category_label, "subject": subject, "score": value})

    condition = {
        "id": cid,
        "model": "Muse Spark 1.2 Contributor",
        "card": "MC-87 / R3",
        "comparison_group": None,
        "fields": {
            "date": f"{campaign['started_at']} → {campaign['finished_at']}",
            "harness": f"OMP · {condition_meta['omp_version']} · {condition_meta['omp_mode']} mode",
            "provider": f"{condition_meta['provider']} · Responses",
            "temperature": "requested 1.0; effective provider value not verified",
            "thinking": "auto; reasoning effort not pinned",
            "seed": "not sent",
            "tools": "all; OMP default full tool menu; auto-approve",
            "prompt": "OMP default coding-agent system prompt; MC-85 user prompts are frozen",
            "context": "question and choices; model does not receive gold",
            "session": "isolated process and scratch per item; no history; Bubblewrap sandbox",
            "output_cap": "20,000 tokens per assistant turn",
            "workers": "12 workers; global manifest-ordered queue; peak concurrency 12",
            "timeout": "300s/item; R2: 30 retries at 600s; R3: 4 retries at 900s (final: 26 items at 600s, 4 at 900s)",
            "retry": "R1: 74 request errors + 2 parse errors at 300s; R2: 30 errors at 600s; R3: 4 errors at 900s",
            "gold": "local for Main/Dev; VMLU Test gold withheld and scored by server",
            "identity": f"{condition_meta['model_ref']}; quantization not reported",
        },
        "sources": [
            source(f"{parent_base}/condition.json", "MC-87 frozen condition"),
            source(runner_snapshot_path, "MC-87 runner source matching frozen SHA"),
            source(tool_attempt_paths[0], "MC-87 per-item tool attempt log"),
            source(tool_attempt_paths[1], "MC-87-R2 per-item tool attempt log"),
            source(tool_attempt_paths[2], "MC-87-R3 per-item tool attempt log"),
            source(f"{base}/recovery.json", "MC-87-R3 timeout recovery"),
            source(f"{base}/condition.json", "MC-87-R3 timeout override"),
            source(f"{main_dir}/summary.json", "MC-87 Main local scores"),
            source(f"{vmlu_dir}/summary.json", "MC-87 Dev local score and Test coverage"),
            source(f"{parent_base}/recovery_mc87_r1.json", "MC-87-R1 technical recovery"),
            source(f"{parent_base}/recovery_mc87_r2/recovery.json", "MC-87-R2 timeout recovery"),
            source(grade_path, "User-provided VMLU Test server grade"),
            source(submission_path, "MC-87-R2 Test submission"),
        ],
        "manifest_sha256": vmlu_run["manifest_sha256"],
        "measurement_card_hash": condition_meta["measurement_card_sha256"],
        "controls": {
            "profile_id": profile,
            "transport": "omp",
            "harness_version": condition_meta["omp_version"],
            "tools": "all",
            "temperature_requested": condition_meta["temperature_requested"],
            "temperature_effective": condition_meta["temperature_effective"],
            "thinking": condition_meta["thinking"],
            "seed_sent": False,
            "seed_requested": None,
            "output_caps": {"multiple_choice": 20000, "reading": 20000},
            "workers": 12,
            "system_prompt": condition_meta["omp_system_prompt"],
            "prompt_version": condition_meta["protocol_id"],
        },
    }
    report = {
        "id": cid,
        "surface": "v2",
        "title": "Muse Spark 1.2 Contributor · OMP full tools · MC-87/R3",
        "protocol": condition_meta["protocol_id"],
        "scope": "MC-87: same 12,033-item scope as MC-86, excluding Legal MC 146; R2/R3 overlay remaining failures with 600s/900s retries.",
        "conditions": [condition],
        "benchmarks": scores,
        "comments": [
            f"VMLU Test đạt {grade['total']:.2f}% theo server grade; Dev đạt {dev['accuracy']:.2f}% theo gold cục bộ.",
            "Bảng mô tả MC-87/R3; không ghép vào ranking OMP không-tools hoặc API Direct.",
        ],
        "notes": [
            "OMP dùng full tool menu và OMP coding-agent system prompt mặc định; tool access không đồng nghĩa model gọi tool trên từng câu.",
            "R2 thử lại 30 câu với 600 giây; R3 thử lại 4 câu còn lỗi với 900 giây. Kết quả cuối gồm 26 câu ở 600s, 4 câu ở 900s, còn lại 300s.",
            "VMLU Test dùng server grade do người dùng cung cấp; không có per-item gold, số câu đúng hay CI95 để suy ra.",
        ],
    }
    if web_search_usage["unrecorded"]:
        report["notes"].append(
            f"Web search được gọi {web_search_usage['total_calls']} lượt; {web_search_usage['unrecorded']} lượt "
            "không có trạng thái kết quả trong attempt artifact cũ nên được giữ là chưa ghi nhận."
        )

    run_summary = {
        "id": cid,
        "title": "Muse Spark 1.2 · OMP full tools · MC-87/R3",
        "model": "Muse Spark 1.2 Contributor",
        "condition": "OMP · full tools · 12 workers · 20.000 tokens/turn; R2 600s cho 30 câu, R3 900s cho 4 câu",
        "status": "complete",
        "completed_items": 12033,
        "total_items": 12033,
        "request_errors": 0,
        "shards": 1,
        "workers_per_shard": 12,
        "total_workers": 12,
        "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 12033}],
        "datasets": [*summary_datasets,
            {"dataset_id": dev_id, "dataset": dev_label, "gold": "local", "request_completed": 303,
             "total_items": 303, "request_errors": 0, "coverage_pct": 100.0,
             "accuracy": dev["accuracy"], "correct": dev["correct"],
             "ci_low": dev["accuracy_ci95_wilson"][0], "ci_high": dev["accuracy_ci95_wilson"][1],
             "server_accuracy": None, "server_grade_source": None, "server_breakdown": [],
             "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 303}]},
            {"dataset_id": test_id, "dataset": test_label, "gold": "withheld", "request_completed": 9833,
             "total_items": 9833, "request_errors": 0, "coverage_pct": 100.0,
             "accuracy": None, "correct": None, "ci_low": None, "ci_high": None,
             "server_accuracy": grade["total"], "server_grade_source": grade_path,
             "server_breakdown": server_breakdown,
             "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 9833}]},
        ],
        "source": f"{base}/campaign.json",
        "web_search": web_search_usage,
        "notes": [
            "One shared global dataset queue, no fixed dataset ownership.",
            "Final predictions overlay 26 successful 600s results and four 900s results; all remaining results use 300s.",
            "The VMLU Test server score has no locally available correct count or CI95.",
        ],
    }
    return report, run_summary


def qwen_omp_full_tools_report(root: Path) -> tuple[dict, dict]:
    """Publish MC-88 full-tools scores for the IEC Qwen model, keeping the Test grade server-sourced."""
    import hashlib

    base = "all_res/qwen_omp_mc88"
    profile = "qwen3-5-9b-65k-omp-full-tools-mc88"
    main_dir = f"{base}/main/{profile}"
    vmlu_dir = f"{base}/vmlu/{profile}"
    grade_path = "docs/research/qwen-omp-vmlu-test-server-grade-mc88-2026-10-19.json"
    submission_path = "submissions/qwen3-5-9b-65k-omp-full-tools-mc88/submission.csv"
    submission_manifest_path = str(Path(submission_path).parent / "provenance.json")
    grade = read_json(root, grade_path)
    submission_meta = read_json(root, submission_manifest_path)
    condition_meta = read_json(root, f"{base}/condition.json")
    campaign = read_json(root, f"{base}/campaign.json")
    main_run = read_json(root, f"{main_dir}/run.json")
    vmlu_run = read_json(root, f"{vmlu_dir}/run.json")
    main_summary = read_json(root, f"{main_dir}/summary.json")
    vmlu_summary = read_json(root, f"{vmlu_dir}/summary.json")
    tool_attempt_paths = [f"{base}/attempts.jsonl"]
    web_search_usage = _omp_web_search_usage(root, tool_attempt_paths)
    runner_snapshot_path = f"{base}/runner-snapshots/run_qwen_omp_mc88.{condition_meta['runner_sha256']}.py"
    runner_snapshot = root / runner_snapshot_path
    if (not runner_snapshot.is_file()
            or hashlib.sha256(runner_snapshot.read_bytes()).hexdigest() != condition_meta["runner_sha256"]):
        raise SystemExit("Error: MC-88 runner snapshot does not match frozen runner hash")
    submission_bytes = (root / submission_path).read_bytes()
    submission_hash = hashlib.sha256(submission_bytes).hexdigest()

    if (campaign.get("status") != "complete" or campaign.get("complete_items") != 12033
            or campaign.get("request_error_items") != 0):
        raise SystemExit("Error: MC-88 campaign is not complete")
    if (main_run.get("status") != "complete" or main_run.get("complete_items") != 1897
            or main_run.get("request_error_items") != 0 or main_summary.get("condition_sha256") != main_run.get("condition_sha256")):
        raise SystemExit("Error: MC-88 main coverage/summary mismatch")
    if (vmlu_run.get("status") != "complete" or vmlu_run.get("complete_items") != 10136
            or vmlu_run.get("request_error_items") != 0 or vmlu_summary.get("condition_sha256") != vmlu_run.get("condition_sha256")):
        raise SystemExit("Error: MC-88 VMLU coverage/summary mismatch")
    if (condition_meta.get("max_time_seconds_per_item") != 900
            or condition_meta.get("timeout_override", {}).get("parent_mc_86_87_seconds") != 300):
        raise SystemExit("Error: MC-88 timeout override provenance changed")
    latest = {}
    for path in tool_attempt_paths:
        for line in (root / path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                attempt = json.loads(line)
                latest[attempt["run_key"]] = attempt
    if len(latest) != 12033 or any(r.get("status") != "complete" for r in latest.values()):
        raise SystemExit("Error: MC-88 attempt ledger is not fully complete")
    if any(not str(r.get("raw_response") or "").strip() for r in latest.values()):
        raise SystemExit("Error: MC-88 ledger contains empty responses")
    unparsed = sum(r.get("parse_valid") is False for r in latest.values())
    if unparsed != 3:
        raise SystemExit(f"Error: MC-88 unparsed count changed ({unparsed})")
    if hashlib.sha256((root / f"{vmlu_dir}/submission_vmlu_test.csv").read_bytes()).hexdigest() != submission_hash:
        raise SystemExit("Error: MC-88 VMLU Test submission differs from the archived one")
    if (grade.get("server_score_status") != "scored_user_provided" or grade.get("item_count") != 9833
            or grade.get("correct") is not None or grade.get("ci95") is not None
            or grade.get("condition_sha256") != main_run.get("condition_sha256")
            or grade.get("condition_sha256") != vmlu_run.get("condition_sha256")
            or grade.get("manifest_sha256") != vmlu_run.get("manifest_sha256")
            or grade.get("submission_sha256") != submission_hash
            or submission_meta.get("submission_sha256") != submission_hash
            or submission_meta.get("condition_sha256") != grade.get("condition_sha256")):
        raise SystemExit("Error: MC-88 server grade/submission provenance mismatch")

    cid = "qwen-omp-full-tools-mc88"
    expected_main = {
        "vi-multimodel-v1-vmlu-valid": ("VMLU Valid", 744),
        "vi-multimodel-v1-legal-nli-150": ("Legal NLI", 150),
        "vi-multimodel-v1-vi-squad-200": ("Vi-SQuAD", 200),
        "vi-multimodel-v1-vi-drop-200": ("Vi-DROP", 200),
        "vi-multimodel-v1-bidlqa-test": ("ViBidLQA Test", 603),
    }
    main_datasets = {dataset["dataset_id"]: dataset for dataset in main_summary["datasets"]}
    if set(main_datasets) != set(expected_main):
        raise SystemExit("Error: MC-88 main dataset set changed")

    scores = []
    summary_datasets = []
    route = condition_meta["model_ref"]
    for dataset_id, (label, expected_n) in expected_main.items():
        dataset = main_datasets[dataset_id]
        n = int(dataset.get("expected_n", expected_n))
        if dataset.get("status") != "complete" or n != expected_n or dataset.get("completed_n") != expected_n:
            raise SystemExit(f"Error: incomplete MC-88 main dataset {dataset_id}")
        if "accuracy" in dataset:
            overall = next((item for item in dataset.get("accuracy_rows", []) if item.get("level") == "overall"), {})
            correct = dataset.get("correct", overall.get("correct"))
            ci = dataset.get("ci95")
            scores.append(row(cid, dataset_id, label, "accuracy", dataset["accuracy"], n=n,
                              correct=correct, ci=ci, source_path=f"{main_dir}/summary.json"))
        for metric, ci_key in (("em", "em_ci95"), ("token_f1", "token_f1_ci95")):
            if metric in dataset:
                scores.append(row(cid, dataset_id, label, metric, dataset[metric], n=n,
                                  ci=dataset.get(ci_key), source_path=f"{main_dir}/summary.json"))
        summary_datasets.append({
            "dataset_id": dataset_id, "dataset": label, "gold": "local",
            "request_completed": expected_n, "total_items": expected_n, "request_errors": 0,
            "coverage_pct": 100.0, "accuracy": dataset.get("accuracy"),
            "correct": dataset.get("correct"), "ci_low": None, "ci_high": None,
            "server_accuracy": None, "server_grade_source": None, "server_breakdown": [],
            "route_breakdown": [{"condition_id": cid, "route": route, "item_count": expected_n}],
        })

    vmlu_datasets = {dataset["dataset_id"]: dataset for dataset in vmlu_summary["datasets"]}
    dev_id, test_id = "vi-multimodel-v2-vmlu-dev", "vi-multimodel-v2-vmlu-test"
    dev = vmlu_datasets.get(dev_id)
    test = vmlu_datasets.get(test_id)
    if (dev is None or dev.get("status") != "complete_local_score" or dev.get("expected_n") != 303
            or dev.get("correct") != 169 or test is None or test.get("status") != "complete_awaiting_server_score"
            or test.get("request_completed_n") != 9833):
        raise SystemExit("Error: MC-88 Dev/Test summary mismatch")
    dev_label, test_label = "VMLU Dev", "VMLU Test"
    scores.append(row(cid, dev_id, dev_label, "accuracy", dev["accuracy"], n=303,
                      correct=dev["correct"], ci=dev.get("accuracy_ci95_wilson"),
                      truncated=dev.get("truncated_n"), source_path=f"{vmlu_dir}/summary.json"))
    scores.append(row(cid, test_id, test_label, "server_accuracy", grade["total"], n=9833,
                      gold="withheld", truncated=test.get("truncated_n", 0), source_path=grade_path))

    category_labels = {"stem": "STEM", "humanity": "Humanity", "social_science": "Social Science", "other": "Other"}
    server_breakdown = []
    for category_key in ("stem", "humanity", "social_science", "other"):
        category = grade["categories"][category_key]
        category_label = category_labels[category_key]
        scores.append(row(cid, test_id, test_label, "server_accuracy", category["total"],
                          level="category", category=category_label, gold="withheld", source_path=grade_path))
        server_breakdown.append({"category": category_label, "subject": None, "score": category["total"]})
        for subject, value in category["subjects"].items():
            subject_label = subject.replace("_", " ")
            scores.append(row(cid, test_id, test_label, "server_accuracy", value,
                              level="subject", category=f"{category_label} · {subject_label}",
                              gold="withheld", source_path=grade_path))
            server_breakdown.append({"category": category_label, "subject": subject, "score": value})

    condition = {
        "id": cid,
        "model": "Qwen3.5-9B-65K (IEC)",
        "card": "MC-88",
        "comparison_group": None,
        "fields": {
            "date": f"{campaign['started_at']} → {campaign['finished_at']}",
            "harness": f"OMP · {condition_meta['omp_version']} · {condition_meta['omp_mode']} mode",
            "provider": f"{condition_meta['provider']} · openai-completions",
            "temperature": "requested 1.0; effective provider value not verified",
            "thinking": "auto; non-reasoning model entry; reasoning effort not pinned",
            "seed": "not sent",
            "tools": "all; OMP default full tool menu; auto-approve",
            "prompt": "OMP default coding-agent system prompt; MC-85 user prompts are frozen",
            "context": "question and choices; model does not receive gold",
            "session": "isolated process and scratch per item; no history; Bubblewrap sandbox",
            "output_cap": "20,000 tokens per assistant turn",
            "workers": "12 workers; global manifest-ordered queue; peak concurrency 12",
            "timeout": "900s/item for all 12,033 items (user override vs MC-86/87 nominal 300s)",
            "retry": "none needed; single pass 12,033/12,033 with zero request errors",
            "gold": "local for Main/Dev; VMLU Test gold withheld and scored by server",
            "identity": f"{condition_meta['model_ref']}; shared IEC gateway deployment; quantization not reported",
        },
        "sources": [
            source(f"{base}/condition.json", "MC-88 frozen condition"),
            source(runner_snapshot_path, "MC-88 runner source matching frozen SHA"),
            source(tool_attempt_paths[0], "MC-88 per-item tool attempt log"),
            source(f"{main_dir}/summary.json", "MC-88 Main local scores"),
            source(f"{vmlu_dir}/summary.json", "MC-88 Dev local score and Test coverage"),
            source(grade_path, "User-provided VMLU Test server grade"),
            source(submission_path, "MC-88 Test submission"),
        ],
        "manifest_sha256": vmlu_run["manifest_sha256"],
        "measurement_card_hash": condition_meta["measurement_card_sha256"],
        "controls": {
            "profile_id": profile,
            "transport": "omp",
            "harness_version": condition_meta["omp_version"],
            "tools": "all",
            "temperature_requested": condition_meta["temperature_requested"],
            "temperature_effective": condition_meta["temperature_effective"],
            "thinking": condition_meta["thinking"],
            "seed_sent": False,
            "seed_requested": None,
            "output_caps": {"multiple_choice": 20000, "reading": 20000},
            "workers": 12,
            "system_prompt": condition_meta["omp_system_prompt"],
            "prompt_version": condition_meta["protocol_id"],
        },
    }
    report = {
        "id": cid,
        "surface": "v2",
        "title": "Qwen3.5-9B-65K (IEC) · OMP full tools · MC-88",
        "protocol": condition_meta["protocol_id"],
        "scope": "MC-88: same 12,033-item scope as MC-86/R2 and MC-87; a single 900s pass without recovery overlay.",
        "conditions": [condition],
        "benchmarks": scores,
        "comments": [
            f"VMLU Test đạt {grade['total']:.2f}% theo server grade; Dev đạt {dev['accuracy']:.2f}% theo gold cục bộ.",
            "Bảng mô tả MC-88; không ghép vào ranking OMP không-tools hoặc API Direct. Lượt full-tools này thấp hơn lượt Qwen direct MC-83 (62,94% Test); hai scaffold khác nhau nên không suy ưu thế model.",
        ],
        "notes": [
            "OMP dùng full tool menu và OMP coding-agent system prompt mặc định; model trả lời trực tiếp gần như toàn bộ (3 tool call: 2 read, 1 write; không có web_search).",
            "Toàn bộ 12.033 câu chạy ở 900 giây/item (user override; MC-86/87 gốc 300 giây) — giữ khác biệt này khi so sánh.",
            "VMLU Test dùng server grade do người dùng cung cấp; không có per-item gold, số câu đúng hay CI95 để suy ra. 3 câu Test không trích xuất được đáp án nằm trong denominator.",
        ],
    }
    if web_search_usage["unrecorded"]:
        report["notes"].append(
            f"Web search được gọi {web_search_usage['total_calls']} lượt; {web_search_usage['unrecorded']} lượt "
            "không có trạng thái kết quả trong attempt artifact nên được giữ là chưa ghi nhận."
        )

    run_summary = {
        "id": cid,
        "title": "Qwen3.5-9B-65K (IEC) · OMP full tools · MC-88",
        "model": "Qwen3.5-9B-65K (IEC)",
        "condition": "OMP · full tools · 12 workers · 20.000 tokens/turn · 900s/item cho toàn bộ 12.033 câu",
        "status": "complete",
        "completed_items": 12033,
        "total_items": 12033,
        "request_errors": 0,
        "shards": 1,
        "workers_per_shard": 12,
        "total_workers": 12,
        "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 12033}],
        "datasets": [*summary_datasets,
            {"dataset_id": dev_id, "dataset": dev_label, "gold": "local", "request_completed": 303,
             "total_items": 303, "request_errors": 0, "coverage_pct": 100.0,
             "accuracy": dev["accuracy"], "correct": dev["correct"],
             "ci_low": dev["accuracy_ci95_wilson"][0], "ci_high": dev["accuracy_ci95_wilson"][1],
             "server_accuracy": None, "server_grade_source": None, "server_breakdown": [],
             "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 303}]},
            {"dataset_id": test_id, "dataset": test_label, "gold": "withheld", "request_completed": 9833,
             "total_items": 9833, "request_errors": 0, "coverage_pct": 100.0,
             "accuracy": None, "correct": None, "ci_low": None, "ci_high": None,
             "server_accuracy": grade["total"], "server_grade_source": grade_path,
             "server_breakdown": server_breakdown,
             "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 9833}]},
        ],
        "source": f"{base}/campaign.json",
        "web_search": web_search_usage,
        "notes": [
            "One shared global manifest-ordered queue, no fixed dataset ownership.",
            "All 12,033 items ran at the 900s user-override timeout; MC-86/87 nominal was 300s.",
            "The VMLU Test server score has no locally available correct count or CI95.",
        ],
    }
    return report, run_summary


def mimo26_omp_full_tools_report(root: Path) -> tuple[dict, dict]:
    """Publish MC-89 full-tools scores for MiMo V2.6 Flash, keeping the Test grade server-sourced."""
    import hashlib

    parent_base = "all_res/mimo26_omp_mc89"
    final_base = f"{parent_base}/final"
    profile = "mimo-v2-6-flash-omp-full-tools-mc89"
    main_dir = f"{final_base}/main/{profile}"
    vmlu_dir = f"{final_base}/vmlu/{profile}"
    grade_path = "docs/research/mimo-omp-vmlu-test-server-grade-mc89-2026-10-21.json"
    submission_path = "submissions/mimo-v2-6-flash-omp-full-tools-mc89/submission.csv"
    submission_manifest_path = str(Path(submission_path).parent / "provenance.json")
    grade = read_json(root, grade_path)
    submission_meta = read_json(root, submission_manifest_path)
    condition_meta = read_json(root, f"{parent_base}/condition.json")
    campaign = read_json(root, f"{parent_base}/campaign.json")
    finalization = read_json(root, f"{final_base}/finalization.json")
    main_run = read_json(root, f"{main_dir}/run.json")
    vmlu_run = read_json(root, f"{vmlu_dir}/run.json")
    main_summary = read_json(root, f"{main_dir}/summary.json")
    vmlu_summary = read_json(root, f"{vmlu_dir}/summary.json")
    tool_attempt_paths = [
        f"{parent_base}/attempts.jsonl",
        f"{parent_base}/recovery_mc89_1800s/attempts.jsonl",
        f"{parent_base}/recovery_mc89_r2/attempts.jsonl",
    ]
    web_search_usage = _omp_web_search_usage(root, tool_attempt_paths)
    runner_snapshot_path = f"{parent_base}/runner-snapshots/run_mimo26_omp_mc89.{condition_meta['runner_sha256']}.py"
    runner_snapshot = root / runner_snapshot_path
    if (not runner_snapshot.is_file()
            or hashlib.sha256(runner_snapshot.read_bytes()).hexdigest() != condition_meta["runner_sha256"]):
        raise SystemExit("Error: MC-89 runner snapshot does not match frozen runner hash")
    submission_bytes = (root / submission_path).read_bytes()
    submission_hash = hashlib.sha256(submission_bytes).hexdigest()

    coverage = finalization["coverage"]
    if campaign.get("status") != "incomplete":
        raise SystemExit(f"Error: MC-89 parent campaign is not terminal ({campaign.get('status')})")
    if (coverage.get("complete") != 11987 or coverage.get("failed") != 46
            or coverage.get("failed_test") != 45 or finalization["submission"]["rows"] != 9833
            or finalization["submission"]["empty_rows"] != 65
            or finalization["submission"]["sha256"] != submission_hash):
        raise SystemExit("Error: MC-89 finalization coverage/submission mismatch")
    if (main_run.get("status") != "incomplete" or main_run.get("complete_items") != 1896
            or main_run.get("request_error_items") != 1
            or main_summary.get("condition_sha256") != main_run.get("condition_sha256")):
        raise SystemExit("Error: MC-89 Main coverage/summary mismatch")
    if (vmlu_run.get("status") != "incomplete" or vmlu_run.get("complete_items") != 10091
            or vmlu_run.get("request_error_items") != 45
            or vmlu_summary.get("condition_sha256") != vmlu_run.get("condition_sha256")):
        raise SystemExit("Error: MC-89 VMLU coverage/summary mismatch")
    if (grade.get("server_score_status") != "scored_user_provided" or grade.get("item_count") != 9833
            or grade.get("correct") is not None or grade.get("ci95") is not None
            or grade.get("condition_sha256") != main_run.get("condition_sha256")
            or grade.get("condition_sha256") != vmlu_run.get("condition_sha256")
            or grade.get("manifest_sha256") != vmlu_run.get("manifest_sha256")
            or grade.get("submission_sha256") != submission_hash
            or grade.get("recovery_condition_sha256") != finalization.get("recovery_condition_sha256")
            or submission_meta.get("submission_sha256") != submission_hash
            or submission_meta.get("rows") != 9833
            or submission_meta.get("empty_answer_rows") != 65):
        raise SystemExit("Error: MC-89 server grade/submission provenance mismatch")

    cid = "mimo-omp-full-tools-mc89"
    expected_main = {
        "vi-multimodel-v1-vmlu-valid": ("VMLU Valid", 744),
        "vi-multimodel-v1-legal-nli-150": ("Legal NLI", 150),
        "vi-multimodel-v1-vi-squad-200": ("Vi-SQuAD", 200),
        "vi-multimodel-v1-vi-drop-200": ("Vi-DROP", 200),
        "vi-multimodel-v1-bidlqa-test": ("ViBidLQA Test", 603),
    }
    main_datasets = {dataset["dataset_id"]: dataset for dataset in main_summary["datasets"]}
    if set(main_datasets) != set(expected_main):
        raise SystemExit("Error: MC-89 main dataset set changed")

    scores = []
    summary_datasets = []
    route = condition_meta["model_ref"]
    for dataset_id, (label, expected_n) in expected_main.items():
        dataset = main_datasets[dataset_id]
        n = int(dataset.get("expected_n", expected_n))
        completed = int(dataset.get("completed_n", 0))
        if n != expected_n or completed > expected_n:
            raise SystemExit(f"Error: incomplete MC-89 main dataset {dataset_id}")
        if "accuracy" in dataset:
            overall = next((item for item in dataset.get("accuracy_rows", []) if item.get("level") == "overall"), {})
            correct = dataset.get("correct", overall.get("correct"))
            ci = dataset.get("ci95")
            scores.append(row(cid, dataset_id, label, "accuracy", dataset["accuracy"], n=completed,
                              correct=correct, ci=ci, source_path=f"{main_dir}/summary.json"))
        for metric, ci_key in (("em", "em_ci95"), ("token_f1", "token_f1_ci95")):
            if metric in dataset:
                scores.append(row(cid, dataset_id, label, metric, dataset[metric], n=completed,
                                  ci=dataset.get(ci_key), source_path=f"{main_dir}/summary.json"))
        summary_datasets.append({
            "dataset_id": dataset_id, "dataset": label, "gold": "local",
            "request_completed": completed, "total_items": expected_n,
            "request_errors": expected_n - completed,
            "coverage_pct": round(100.0 * completed / expected_n, 2), "accuracy": dataset.get("accuracy"),
            "correct": dataset.get("correct"), "ci_low": None, "ci_high": None,
            "server_accuracy": None, "server_grade_source": None, "server_breakdown": [],
            "route_breakdown": [{"condition_id": cid, "route": route, "item_count": completed}],
        })

    vmlu_datasets = {dataset["dataset_id"]: dataset for dataset in vmlu_summary["datasets"]}
    dev_id, test_id = "vi-multimodel-v2-vmlu-dev", "vi-multimodel-v2-vmlu-test"
    dev = vmlu_datasets.get(dev_id)
    test = vmlu_datasets.get(test_id)
    if (dev is None or dev.get("status") != "complete_local_score" or dev.get("expected_n") != 303
            or dev.get("correct") != 251 or test is None
            or test.get("status") != "incomplete_awaiting_server_score"
            or test.get("request_completed_n") != 9788 or test.get("expected_n") != 9833):
        raise SystemExit("Error: MC-89 Dev/Test summary mismatch")
    dev_label, test_label = "VMLU Dev", "VMLU Test"
    scores.append(row(cid, dev_id, dev_label, "accuracy", dev["accuracy"], n=303,
                      correct=dev["correct"], ci=dev.get("accuracy_ci95_wilson"),
                      truncated=dev.get("truncated_n"), source_path=f"{vmlu_dir}/summary.json"))
    scores.append(row(cid, test_id, test_label, "server_accuracy", grade["total"], n=9833,
                      gold="withheld", truncated=test.get("truncated_n", 0), source_path=grade_path))

    category_labels = {"stem": "STEM", "humanity": "Humanity", "social_science": "Social Science", "other": "Other"}
    server_breakdown = []
    for category_key in ("stem", "humanity", "social_science", "other"):
        category = grade["categories"][category_key]
        category_label = category_labels[category_key]
        scores.append(row(cid, test_id, test_label, "server_accuracy", category["total"],
                          level="category", category=category_label, gold="withheld", source_path=grade_path))
        server_breakdown.append({"category": category_label, "subject": None, "score": category["total"]})
        for subject, value in category["subjects"].items():
            subject_label = subject.replace("_", " ")
            scores.append(row(cid, test_id, test_label, "server_accuracy", value,
                              level="subject", category=f"{category_label} · {subject_label}",
                              gold="withheld", source_path=grade_path))
            server_breakdown.append({"category": category_label, "subject": subject, "score": value})

    condition = {
        "id": cid,
        "model": "MiMo V2.6 Flash",
        "card": "MC-89",
        "comparison_group": None,
        "fields": {
            "date": f"{campaign['started_at']} → {grade['recorded_at']}",
            "harness": f"OMP · {condition_meta['omp_version']} · {condition_meta['omp_mode']} mode",
            "provider": f"{condition_meta['provider']} · Chat Completions",
            "temperature": "requested 1.0; thinking-mode provider default may apply",
            "thinking": "auto; reasoning by provider default",
            "seed": "not sent",
            "tools": "all; OMP default full tool menu; auto-approve",
            "prompt": "OMP default coding-agent system prompt; MC-85 user prompts are frozen",
            "context": "question and choices; model does not receive gold",
            "session": "isolated process and scratch per item; per-item x-opencode-session routing header",
            "output_cap": "20,000 tokens per assistant turn; R2 output-cap group used 32,768",
            "workers": "12; R2-C1 rerun used 8 after a systemd-oomd kill",
            "timeout": "900s parent; 1800s R1/C1; 3600s R2 tool-loop group; final policy: unfinished items count as failed",
            "retry": "attempt 1 parent; attempt 2 R1/C1; attempt 3 R2/C1; 46 failed keys submitted as empty answers",
            "gold": "local for Main/Dev; VMLU Test gold withheld and scored by server",
            "identity": f"{condition_meta['model_ref']}; shared OpenCode Go deployment",
        },
        "sources": [
            source(f"{parent_base}/condition.json", "MC-89 frozen condition"),
            source(runner_snapshot_path, "MC-89 runner source matching frozen SHA"),
            source(tool_attempt_paths[0], "MC-89 per-item attempt log"),
            source(tool_attempt_paths[1], "MC-89-R1 per-item attempt log"),
            source(tool_attempt_paths[2], "MC-89-R2 per-item attempt log"),
            source(f"{parent_base}/recovery_mc89_1800s/recovery.json", "MC-89-R1 1800s recovery"),
            source(f"{parent_base}/recovery_mc89_r2/recovery.json", "MC-89-R2 per-group overrides"),
            source(f"{final_base}/finalization.json", "MC-89 final coverage and empty-answer policy"),
            source(f"{main_dir}/summary.json", "MC-89 Main local scores"),
            source(f"{vmlu_dir}/summary.json", "MC-89 Dev local score and Test coverage"),
            source(grade_path, "User-provided VMLU Test server grade"),
            source(submission_path, "MC-89 Test submission"),
        ],
        "manifest_sha256": vmlu_run["manifest_sha256"],
        "measurement_card_hash": condition_meta["measurement_card_sha256"],
        "controls": {
            "profile_id": profile,
            "transport": "omp",
            "harness_version": condition_meta["omp_version"],
            "tools": "all",
            "temperature_requested": condition_meta["temperature_requested"],
            "temperature_effective": condition_meta["temperature_effective"],
            "thinking": condition_meta["thinking"],
            "seed_sent": False,
            "seed_requested": None,
            "output_caps": {"multiple_choice": 20000, "reading": 20000},
            "workers": 12,
            "system_prompt": condition_meta["omp_system_prompt"],
            "prompt_version": condition_meta["protocol_id"],
        },
    }
    report = {
        "id": cid,
        "surface": "v2",
        "title": "MiMo V2.6 Flash · OMP full tools · MC-89",
        "protocol": condition_meta["protocol_id"],
        "scope": "MC-89: same 12,033-item scope as MC-86/87/88; parent 900 s, R1 1800 s, R2 per-group overrides; 46 failed keys submitted as empty answers (99.62% complete).",
        "conditions": [condition],
        "benchmarks": scores,
        "comments": [
            f"VMLU Test đạt {grade['total']:.2f}% theo server grade trên 9.833 dòng (9.788 câu có đáp án; 65 dòng rỗng); Dev đạt {dev['accuracy']:.2f}% theo gold cục bộ.",
            "Bảng mô tả MC-89; không ghép vào ranking OMP không-tools hoặc API Direct. MiMo dùng tool nhiều nhất trong nhóm full-tools.",
        ],
        "notes": [
            "MiMo V2.6 Flash là arm dùng tool mạnh nhất: 8.907 tool call (read/bash/web_search); các lỗi tập trung ở cụm môn luật/hành chính do model tự loop tool.",
            "Theo chỉ đạo 2026-10-21: câu không hoàn tất trong ngân sách 1.800 s bị đánh failed và ghi đáp án rỗng; 46 câu failed (45 ở Test) + 20 câu complete-nhưng-không-parse-được = 65 dòng rỗng trong submission, sẽ tính sai khi chấm server.",
            "Một số câu đã hoàn tất nhưng chạy quá 1.800 s (7 câu) vẫn được giữ; danh sách nằm trong finalization.json.",
            "49 lỗi AttributeError của pass gốc là bug parser `_reasoning_tokens` (message dạng string); đã vá trong driver recovery.",
        ],
    }

    run_summary = {
        "id": cid,
        "title": "MiMo V2.6 Flash · OMP full tools · MC-89",
        "model": "MiMo V2.6 Flash",
        "condition": "OMP · full tools · 12 workers (R2-C1: 8) · 20.000 tokens/turn (nhóm 20k: 32.768); parent 900 s, R1 1800 s, R2 3600 s cho nhóm tool-loop",
        "status": "partial",
        "completed_items": 11987,
        "total_items": 12033,
        "request_errors": 46,
        "shards": 1,
        "workers_per_shard": 12,
        "total_workers": 12,
        "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 11987}],
        "datasets": [
            *summary_datasets,
            {"dataset_id": dev_id, "dataset": dev_label, "gold": "local", "request_completed": 303,
             "total_items": 303, "request_errors": 0, "coverage_pct": 100.0,
             "accuracy": dev["accuracy"], "correct": dev["correct"],
             "ci_low": dev["accuracy_ci95_wilson"][0], "ci_high": dev["accuracy_ci95_wilson"][1],
             "server_accuracy": None, "server_grade_source": None, "server_breakdown": [],
             "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 303}]},
            {"dataset_id": test_id, "dataset": test_label, "gold": "withheld", "request_completed": 9788,
             "total_items": 9833, "request_errors": 45, "coverage_pct": 99.54,
             "accuracy": None, "correct": None, "ci_low": None, "ci_high": None,
             "server_accuracy": grade["total"], "server_grade_source": grade_path,
             "server_breakdown": server_breakdown,
             "route_breakdown": [{"condition_id": cid, "route": route, "item_count": 9788}]},
        ],
        "source": f"{final_base}/finalization.json",
        "web_search": web_search_usage,
        "notes": [
            "One shared global manifest-ordered queue; R2-C1 used 8 workers to avoid another OOM kill.",
            "Failed keys are submitted as empty answers and score wrong server-side; 65 empty rows in total.",
            "The VMLU Test server score has no locally available correct count or CI95.",
        ],
    }
    return report, run_summary


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


def muse12_main_reports(root: Path) -> list[dict]:
    """Publish MC-73's already-completed Legal/reading run from its own artifacts."""
    base = "all_res/muse_router_matched/main"
    run_dir = f"{base}/muse-spark-1-2-contributor"
    if not (root / f"{run_dir}/run.json").is_file():
        return []
    meta = read_json(root, f"{run_dir}/run.json")
    summary = read_json(root, f"{run_dir}/summary.json")
    manifest = read_json(root, f"{base}/condition_manifest.json")
    protocol = read_json(root, f"{base}/condition_protocol.json")
    profile = read_json(root, f"{base}/condition_profiles.json")["muse-spark-1-2-contributor"]
    expected = {"vi-multimodel-v1-legal-mc-146": ("Legal MC", 146),
                "vi-multimodel-v1-legal-nli-150": ("Legal NLI", 150),
                "vi-multimodel-v1-vi-squad-200": ("Vi-SQuAD", 200),
                "vi-multimodel-v1-vi-drop-200": ("Vi-DROP", 200),
                "vi-multimodel-v1-bidlqa-test": ("ViBidLQA Test", 603)}
    if meta.get("status") != "complete" or meta.get("measurement_card_id") != "MC-73":
        raise SystemExit("Error: Muse 1.2 MC-73 is not a completed main run")
    if any(doc.get("manifest_sha256") != manifest["manifest_sha256"] for doc in (meta, summary)):
        raise SystemExit("Error: MC-73 manifest differs from its scored summary/run")
    refs = {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}": r for r in manifest["items"]}
    predictions = [json.loads(line) for line in (root / f"{run_dir}/predictions.jsonl").read_text().splitlines() if line.strip()]
    if len(predictions) != 1299 or len({r["run_key"] for r in predictions}) != 1299 or set(refs) != {r["run_key"] for r in predictions}:
        raise SystemExit("Error: MC-73 complete unique coverage differs from its 1,299-item manifest")
    for prediction in predictions:
        if (prediction.get("status") != "complete" or prediction.get("tool_calls", 0) != 0
                or prediction.get("prompt_sha256") != refs[prediction["run_key"]]["prompt_sha256"]):
            raise SystemExit("Error: MC-73 incomplete prediction, tool use, or prompt drift")
    condition, _ = modern_condition(root, f"{run_dir}/run.json", profile, protocol, "main")
    condition["id"] = "muse12-main-mc73"
    condition["fields"]["temperature"] = "requested 1.0, pinned by sampling relay; metadata 1.0; upstream effective value not exposed"
    condition["sources"] += [source(f"{base}/condition_manifest.json", "MC-73 frozen input"), source(f"{run_dir}/summary.json", "MC-73 scored summary")]
    scores = []
    datasets = {d["dataset_id"]: d for d in summary["datasets"]}
    if set(datasets) != set(expected):
        raise SystemExit("Error: MC-73 dataset set drift")
    for dataset_id, (label, n) in expected.items():
        dataset = datasets[dataset_id]
        if dataset.get("status") != "complete" or dataset.get("request_completed_n") != n or dataset.get("expected_n") != n:
            raise SystemExit(f"Error: MC-73 incomplete dataset {dataset_id}")
        for metric, ci_key in (("accuracy", "ci95"), ("em", "em_ci95"), ("token_f1", "token_f1_ci95")):
            if metric not in dataset:
                continue
            scores.append(row(condition["id"], dataset_id, label, metric, dataset[metric], n=n,
                              correct=dataset.get("correct") if metric == "accuracy" else None,
                              ci=dataset.get(ci_key), truncated=dataset.get("truncated_n"),
                              source_path=f"{run_dir}/summary.json"))
    return [{"id": "muse12-main-mc73", "surface": "v1", "title": "Muse 1.2 · Legal và reading · MC-73",
             "protocol": protocol["protocol_id"], "scope": "MC-73: 1,299 items, CMC route, 4 workers, OMP/no tools/temp 1/auto/seed omitted.",
             "conditions": [condition], "benchmarks": scores,
             "comments": ["Local scores come from the stored MC-73 responses; no new inference was performed."],
             "notes": ["MC-73 timeout is 300 seconds/item; keep it explicit alongside the other models' controls."]}]


def muse12_vmlu_run_summaries(root: Path) -> list[dict]:
    """Expose completed Muse 1.2 coverage without turning withheld test into a score."""
    artifact_root = "all_res/muse12_ocg_vmlu_mc79"
    provenance_path = f"{artifact_root}/combined_provenance.json"
    if not (root / provenance_path).is_file():
        return []

    provenance = read_json(root, provenance_path)
    continuation_path = f"{artifact_root}/vmlu/muse-spark-1-2-contributor-ocg"
    continuation_run = read_json(root, f"{continuation_path}/run.json")
    continuation_summary = read_json(root, f"{continuation_path}/summary.json")
    source_path = "all_res/muse_router_matched/vmlu/muse-spark-1-2-contributor"
    source_run = read_json(root, f"{source_path}/run.json")
    source_summary = read_json(root, f"{source_path}/summary.json")
    grade_path = "docs/research/muse12-vmlu-test-server-grade-2026-10-12.json"
    server_grade = read_json(root, grade_path) if (root / grade_path).is_file() else None

    expected_routes = {
        "cmc/meta/muse-spark-1.2-contributor": 7504,
        "ocg/muse-spark-1.2-contributor": 3376,
    }
    expected_datasets = {
        "vi-multimodel-v2-vmlu-valid": ("VMLU Valid", "local", 744),
        "vi-multimodel-v2-vmlu-dev": ("VMLU Dev", "local", 303),
        "vi-multimodel-v2-vmlu-test": ("VMLU Test", "withheld", 9833),
    }
    if provenance.get("mixed_routes") is not True or provenance.get("homogeneous_model_score_allowed") is not False:
        raise SystemExit("Error: Muse 1.2 combined artifact is not explicitly marked as mixed-route")
    if continuation_run.get("status") != "complete" or continuation_run.get("complete_items") != 3376:
        raise SystemExit("Error: MC-79 continuation is not complete")
    if continuation_summary.get("request_complete_n") != 3376 or continuation_summary.get("request_error_n") != 0:
        raise SystemExit("Error: MC-79 summary does not confirm a clean completion")
    if source_run.get("measurement_card_id") != "MC-74" or source_run.get("complete_items") != 7504:
        raise SystemExit("Error: MC-74 source run differs from the documented continuation")
    if source_summary.get("manifest_sha256") != provenance.get("source_manifest_sha256"):
        raise SystemExit("Error: MC-74 scored summary does not match the combined manifest")

    prediction_path = root / f"{artifact_root}/combined_predictions_mixed_routes.jsonl"
    rows_by_dataset: dict[str, list[dict]] = defaultdict(list)
    route_counts: dict[str, int] = defaultdict(int)
    condition_counts: dict[str, int] = defaultdict(int)
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    seen: set[tuple[str, str]] = set()
    for line_no, line in enumerate(prediction_path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Error: invalid Muse 1.2 combined prediction at line {line_no}") from exc
        key = (str(item.get("dataset_id", "")), str(item.get("item_id", "")))
        if not all(key) or key in seen:
            raise SystemExit(f"Error: blank/duplicate Muse 1.2 combined item at line {line_no}")
        seen.add(key)
        dataset_id, item_id = key
        if dataset_id not in expected_datasets or item.get("status") != "complete":
            raise SystemExit(f"Error: incomplete or unexpected Muse 1.2 prediction {dataset_id}:{item_id}")
        route = str(item.get("source_route", ""))
        condition_id = str(item.get("source_condition_id", ""))
        if not route or not condition_id:
            raise SystemExit(f"Error: missing Muse 1.2 route provenance for {dataset_id}:{item_id}")
        rows_by_dataset[dataset_id].append(item)
        route_counts[route] += 1
        condition_counts[condition_id] += 1
        pair_counts[(condition_id, route)] += 1

    if len(seen) != provenance.get("item_count") or route_counts != provenance.get("counts_by_route"):
        raise SystemExit("Error: Muse 1.2 predictions differ from route provenance counts")
    if condition_counts != provenance.get("counts_by_condition"):
        raise SystemExit("Error: Muse 1.2 predictions differ from condition provenance counts")
    if route_counts != expected_routes or set(rows_by_dataset) != set(expected_datasets):
        raise SystemExit("Error: Muse 1.2 VMLU dataset/route coverage drift")

    test_condition_counts = {
        condition_id: sum(
            item.get("source_condition_id") == condition_id
            for item in rows_by_dataset["vi-multimodel-v2-vmlu-test"]
        )
        for condition_id in ("MC-74", "MC-79")
    }
    server_accuracy = None
    server_grade_source = None
    server_breakdown = []
    if server_grade is not None:
        if (server_grade.get("dataset_id") != "vi-multimodel-v2-vmlu-test"
                or server_grade.get("condition_ids") != ["MC-74", "MC-79"]
                or server_grade.get("item_count") != expected_datasets["vi-multimodel-v2-vmlu-test"][2]
                or server_grade.get("route_counts_by_condition") != test_condition_counts):
            raise SystemExit("Error: Muse 1.2 server grade scope differs from the mixed-route Test run")
        server_grade_source = str(server_grade.get("source", "")).strip()
        if not server_grade_source:
            raise SystemExit("Error: Muse 1.2 server grade source is missing")
        server_accuracy = number(server_grade.get("total"))
        if server_accuracy is None or not 0 <= server_accuracy <= 100:
            raise SystemExit("Error: invalid Muse 1.2 overall server grade")
        categories = server_grade.get("categories")
        expected_category_counts = {"humanity": 18, "social_science": 10, "other": 9, "stem": 21}
        category_labels = {"humanity": "Humanity", "social_science": "Social Science", "other": "Other", "stem": "STEM"}
        if not isinstance(categories, dict) or set(categories) != set(expected_category_counts):
            raise SystemExit("Error: Muse 1.2 server-grade category set drift")
        subject_count = 0
        for category_id, label in category_labels.items():
            category = categories[category_id]
            if not isinstance(category, dict) or not isinstance(category.get("subjects"), dict):
                raise SystemExit(f"Error: malformed Muse 1.2 server-grade category {category_id}")
            category_score = number(category.get("total"))
            subjects = category["subjects"]
            if category_score is None or not 0 <= category_score <= 100 or len(subjects) != expected_category_counts[category_id]:
                raise SystemExit(f"Error: invalid Muse 1.2 server-grade total/subject count for {category_id}")
            server_breakdown.append({"category": label, "subject": None, "score": category_score})
            subject_count += len(subjects)
            for subject, value in subjects.items():
                score = number(value)
                if not subject or score is None or not 0 <= score <= 100:
                    raise SystemExit(f"Error: invalid Muse 1.2 subject grade {category_id}/{subject}")
                server_breakdown.append({"category": label, "subject": subject, "score": score})
        if subject_count != 58:
            raise SystemExit(f"Error: expected 58 VMLU subject grades, got {subject_count}")

    scored_datasets = {item["dataset_id"]: item for item in source_summary.get("datasets", [])}
    dataset_results = []
    for dataset_id, (label, gold, expected_n) in expected_datasets.items():
        rows = rows_by_dataset[dataset_id]
        if len(rows) != expected_n or {item.get("gold_status") for item in rows} != {gold}:
            raise SystemExit(f"Error: Muse 1.2 {label} count/gold status drift")
        route_breakdown = []
        for condition_id, route in sorted(pair_counts):
            route_n = sum(
                item.get("source_condition_id") == condition_id and item.get("source_route") == route
                for item in rows
            )
            if route_n:
                route_breakdown.append({"condition_id": condition_id, "route": route, "item_count": route_n})
        score = scored_datasets.get(dataset_id, {}) if gold == "local" else {}
        accuracy = score.get("accuracy") if score.get("status") == "complete_local_score" else None
        correct = score.get("correct") if accuracy is not None else None
        if gold == "withheld" and (accuracy is not None or correct is not None):
            raise SystemExit("Error: local accuracy must not be attached to VMLU Test withheld gold")
        dataset_results.append({
            "dataset_id": dataset_id,
            "dataset": label,
            "gold": gold,
            "request_completed": len(rows),
            "total_items": expected_n,
            "request_errors": 0,
            "accuracy": accuracy,
            "correct": correct,
            "ci_low": score.get("accuracy_ci95_wilson", [None, None])[0] if gold == "local" else None,
            "ci_high": score.get("accuracy_ci95_wilson", [None, None])[1] if gold == "local" else None,
            "server_accuracy": server_accuracy if dataset_id == "vi-multimodel-v2-vmlu-test" else None,
            "server_grade_source": server_grade_source if dataset_id == "vi-multimodel-v2-vmlu-test" else None,
            "server_breakdown": server_breakdown if dataset_id == "vi-multimodel-v2-vmlu-test" else [],
            "route_breakdown": route_breakdown,
        })

    completed = sum(len(rows) for rows in rows_by_dataset.values())
    total_items = int(provenance["item_count"])
    route_breakdown = [
        {"condition_id": condition_id, "route": route, "item_count": item_count}
        for (condition_id, route), item_count in sorted(pair_counts.items())
    ]
    return [{
        "id": "muse12-vmlu-mc74-mc79",
        "title": "Muse Spark 1.2 · VMLU · MC-74 + MC-79",
        "model": "Muse Spark 1.2 Contributor",
        "condition": "OMP · không tools · Temperature 1,0 · thinking auto · seed không gửi",
        "status": "complete" if completed == total_items else "partial",
        "completed_items": completed,
        "total_items": total_items,
        "request_errors": 0,
        "shards": 4,
        "workers_per_shard": 3,
        "total_workers": 12,
        "route_breakdown": route_breakdown,
        "datasets": dataset_results,
        "source": provenance_path,
        "notes": [
            "VMLU Valid/Dev local accuracy uses only the MC-74 CMC route; VMLU Test predictions combine MC-74 CMC and MC-79 OCG.",
            (f"VMLU Test server grade is {server_accuracy:.2f}% ({server_grade_source}); correct count and confidence interval were not supplied."
             if server_accuracy is not None else "VMLU Test gold is withheld. Accuracy and confidence intervals await an official server grade."),
            "The mixed-route aggregate is a coverage record, not one homogeneous provider-route score.",
        ],
    }]


def muse13_direct_reports(root: Path) -> list[dict]:
    """Project completed direct results while preserving per-dataset budget provenance."""
    base = "all_res/muse13_direct_mc82"
    phase = f"{base}/vmlu/muse-spark-1-3-contributor-ocg-20k"
    grade_path = "docs/research/muse13-vmlu-test-server-grade-mc82-2026-10-14.json"
    if not (root / grade_path).is_file():
        return []
    meta = read_json(root, f"{phase}/run.json")
    summary = read_json(root, f"{phase}/summary.json")
    grade = read_json(root, grade_path)
    original_path = "all_res/muse13_direct_mc80/main/muse-spark-1-3-contributor-ocg/condition.json"
    original = read_json(root, original_path)
    combined = read_json(root, f"{base}/mc80_combined_summary.json")
    if (meta.get("status") != "complete" or meta.get("complete_items") != 10136
            or meta.get("model_id") != "ocg/muse-spark-1.3-contributor"
            or meta.get("max_tokens_mc") != 20000 or grade.get("condition_ids") != ["MC-82"]
            or grade.get("item_count") != 9833 or grade.get("model_id") != meta["model_id"]
            or grade.get("manifest_sha256") != meta["manifest_sha256"]
            or grade.get("condition_sha256") != meta["condition_sha256"]):
        raise SystemExit("Error: Muse direct run/server grade provenance mismatch")
    import hashlib
    if hashlib.sha256((root / f"{phase}/submission_vmlu_test.csv").read_bytes()).hexdigest() != grade["submission_sha256"]:
        raise SystemExit("Error: Muse direct server grade submission hash mismatch")
    conditions = []
    for cid, card, control, cap, evidence in [
        ("muse13-direct-mc82", "MC-82", meta, "20.000 tokens cho Dev/Test", f"{phase}/summary.json"),
        ("muse13-direct-mc80", "MC-80", original, "4.096 tokens cho Valid", f"{base}/mc80_combined_summary.json"),
        ("muse13-direct-recovery", "MC-80 + MC-82", original,
         "MC 4.096; reading 2.048; 7 câu recovery dùng 20.000 tokens", f"{base}/mc80_combined_summary.json"),
    ]:
        conditions.append({
            "id": cid, "model": "Muse Spark 1.3 Contributor", "card": card, "comparison_group": None,
            "fields": {
                "date": f"{meta['started_at']} → {meta['finished_at']}", "harness": "API Direct · Responses",
                "provider": "API Direct", "temperature": "1,0 gửi trong request; hiệu lực upstream không công bố",
                "thinking": "Reasoning mặc định; không gửi effort, không ghim low/medium/high",
                "seed": "không gửi", "tools": "none", "prompt": "System tối giản; user prompt đóng băng",
                "context": "MC: câu hỏi và lựa chọn; reading: passage trong prompt; gold không gửi cho model",
                "session": "Mỗi request độc lập; không history", "output_cap": cap,
                "workers": "12 workers · 4 shards × 3 lanes", "timeout": "300 giây/request",
                "retry": "SDK 0; technical recovery; câu hoàn tất/truncated không chạy lại",
                "gold": "Dev/Valid/Legal/reading: gold cục bộ; Test: server grade",
                "identity": "Muse Spark 1.3 Contributor",
            },
            "sources": [source(original_path, "Original controls"), source(f"{phase}/run.json", "Run metadata"),
                        source(evidence, "Scored summary"), source(grade_path, "Server grade")],
            "manifest_sha256": control.get("manifest_sha256"), "measurement_card_hash": control.get("measurement_card_hash"),
            "controls": {"profile_id": "muse-spark-1-3-contributor", "transport": "direct", "harness_version": None,
                         "tools": "none", "temperature_requested": 1.0, "temperature_effective": None,
                         "thinking": None, "seed_sent": False, "seed_requested": None,
                         "output_caps": {"multiple_choice": control["max_tokens_mc"], "reading": control["max_tokens_reading"]},
                         "workers": 12, "system_prompt": control["system_prompt"], "prompt_version": control["prompt_version"]},
        })
    scores = []
    labels = {"vmlu-valid": "VMLU Valid", "legal-mc-146": "Legal MC", "legal-nli-150": "Legal NLI",
              "vi-squad-200": "Vi-SQuAD", "vi-drop-200": "Vi-DROP", "bidlqa-test": "ViBidLQA Test"}
    if len(combined.get("datasets", [])) != 6:
        raise SystemExit("Error: Muse direct main dataset coverage mismatch")
    for dataset in combined["datasets"]:
        dataset_id = dataset["dataset_id"]
        suffix = dataset_id.removeprefix("vi-multimodel-v1-")
        if suffix not in labels or dataset["status"] != "complete" or dataset["expected_n"] != dataset["request_completed_n"]:
            raise SystemExit("Error: Muse direct incomplete main dataset")
        cid = "muse13-direct-mc80" if suffix == "vmlu-valid" else "muse13-direct-recovery"
        for metric, ci_key in [("accuracy", "ci95"), ("em", "em_ci95"), ("token_f1", "token_f1_ci95")]:
            if metric in dataset:
                scores.append(row(cid, dataset_id, labels[suffix], metric, dataset[metric], n=dataset["expected_n"],
                                  correct=dataset.get("correct") if metric == "accuracy" else None,
                                  ci=dataset.get(ci_key), truncated=dataset.get("truncated_n"),
                                  source_path=f"{base}/mc80_combined_summary.json"))
    datasets = {d["dataset_id"]: d for d in summary["datasets"]}
    for split, expected in [("dev", 303), ("test", 9833)]:
        dataset_id = f"vi-multimodel-v2-vmlu-{split}"
        d = datasets[dataset_id]
        if d["expected_n"] != expected or d["request_completed_n"] != expected or d["request_error_n"] or d["missing_n"]:
            raise SystemExit("Error: Muse direct incomplete Dev/Test")
        scores.append(row("muse13-direct-mc82", dataset_id, f"VMLU {split.title()}",
                          "server_accuracy" if split == "test" else "accuracy", grade["total"] if split == "test" else d["accuracy"],
                          n=expected, correct=None if split == "test" else d["correct"],
                          ci=None if split == "test" else d.get("accuracy_ci95_wilson"),
                          gold="withheld" if split == "test" else "local", truncated=d["truncated_n"],
                          source_path=grade_path if split == "test" else f"{phase}/summary.json"))
    for category, data in grade["categories"].items():
        for level, label, score in [("category", category, data["total"]),
                                    *[("subject", key, value) for key, value in data["subjects"].items()]]:
            scores.append(row("muse13-direct-mc82", "vi-multimodel-v2-vmlu-test", "VMLU Test", "server_accuracy", score,
                              level=level, category=label, gold="withheld", source_path=grade_path))
    return [{"id": "muse13-direct", "surface": "v2", "title": "Muse Spark 1.3 Contributor · API Direct",
             "protocol": meta["protocol_id"], "scope": "Kết quả direct trên VMLU, Legal và reading; điều kiện ghi riêng theo dataset.",
             "conditions": conditions, "benchmarks": scores,
             "comments": ["VMLU Test đạt 88,41% theo server grade; Dev đạt 92,41% theo gold cục bộ."],
             "notes": ["Dev/Test: budget 20.000 tokens; Valid: 4.096; Legal/reading giữ budget gốc và 7 câu recovery 20.000.",
                       "Reasoning dùng mặc định provider; temperature gửi 1,0, hiệu lực upstream không công bố.",
                       "Test chỉ có phần trăm server; chưa có correct count hoặc CI95. Các câu không parse được giữ trong mẫu chấm."]}]


def qwen_direct_reports(root: Path) -> list[dict]:
    """Expose MC-83 scores and user-supplied grade without guessing withheld counts."""
    base = "all_res/qwen_direct_mc83"
    profile = "qwen3-5-9b-65k-direct-20k"
    grade_path = "docs/research/qwen-vmlu-test-server-grade-mc83-2026-10-14.json"
    if not (root / grade_path).is_file():
        return []
    grade = read_json(root, grade_path)
    test_run = read_json(root, f"{base}/vmlu/{profile}/run.json")
    import hashlib
    submission = root / f"{base}/vmlu/{profile}/submission_vmlu_test.csv"
    if (grade.get("condition_ids") != ["MC-83"] or grade.get("model_id") != "Qwen3.5-9B-65K"
            or grade.get("item_count") != 9833 or grade.get("manifest_sha256") != test_run["manifest_sha256"]
            or grade.get("condition_sha256") != test_run["condition_sha256"]
            or grade.get("submission_sha256") != hashlib.sha256(submission.read_bytes()).hexdigest()):
        raise SystemExit("Error: MC-83 server grade/submission provenance mismatch")
    conditions, scores = [], []
    labels = {"vmlu-valid": "VMLU Valid", "vmlu-dev": "VMLU Dev", "vmlu-test": "VMLU Test",
              "legal-mc-146": "Legal MC", "legal-nli-150": "Legal NLI", "vi-squad-200": "Vi-SQuAD",
              "vi-drop-200": "Vi-DROP", "bidlqa-test": "ViBidLQA Test"}
    for phase, expected in [("main", 2043), ("vmlu", 10136)]:
        folder = f"{base}/{phase}/{profile}"
        meta = read_json(root, f"{folder}/run.json")
        summary = read_json(root, f"{folder}/summary.json")
        if (meta.get("status") != "complete" or meta.get("complete_items") != expected
                or meta.get("measurement_card_id") != "MC-83" or meta.get("model_id") != grade["model_id"]
                or meta.get("max_tokens_mc") != 20000 or meta.get("max_tokens_reading") != 20000
                or summary.get("manifest_sha256") != meta["manifest_sha256"]):
            raise SystemExit("Error: MC-83 completed coverage/controls mismatch")
        cid = f"qwen-direct-mc83-{phase}"
        fields = {key: UNKNOWN for key in FIELD_LABELS}
        fields.update({"date": f"{meta['started_at']} → {meta['finished_at']}", "harness": "API Direct · Responses",
                       "provider": "API Direct", "temperature": "1,0 gửi trong request; hiệu lực upstream không công bố",
                       "thinking": "Reasoning mặc định; không gửi effort, không ghim low/medium/high",
                       "seed": "không gửi", "tools": "none", "prompt": "System tối giản; user prompt đóng băng",
                       "context": "MC: câu hỏi và lựa chọn; reading: passage trong prompt; gold không gửi cho model",
                       "session": "Mỗi request độc lập; không history", "output_cap": "20.000 tokens cho cả MC và reading",
                       "workers": "12 workers · 4 shards × 3 lanes", "timeout": "300 giây/request",
                       "retry": "SDK 0; technical recovery; câu hoàn tất/truncated không chạy lại",
                       "gold": "Gold cục bộ; riêng VMLU Test do server chấm",
                       "identity": "Qwen3.5-9B-65K · weights Qwen3.5-9B-Q4_K_M.gguf"})
        conditions.append({"id": cid, "model": "Qwen3.5-9B-65K · Q4_K_M", "card": "MC-83", "comparison_group": None,
                           "fields": fields, "sources": [source(f"{folder}/run.json", "Run metadata"),
                           source(f"{folder}/summary.json", "Scored summary"), source(grade_path, "Server grade")],
                           "manifest_sha256": meta["manifest_sha256"], "measurement_card_hash": meta["measurement_card_hash"],
                           "controls": {"profile_id": profile, "transport": "direct", "harness_version": None,
                           "tools": "none", "temperature_requested": 1.0, "temperature_effective": None, "thinking": None,
                           "seed_sent": False, "seed_requested": None, "output_caps": {"multiple_choice": 20000, "reading": 20000},
                           "workers": 12, "system_prompt": meta["system_prompt"], "prompt_version": meta["prompt_version"]}})
        for d in summary["datasets"]:
            if d["request_completed_n"] != d["expected_n"]:
                raise SystemExit("Error: MC-83 incomplete scored dataset")
            dataset_id = d["dataset_id"]
            suffix = dataset_id.split("-", 3)[-1]
            label = labels[suffix]
            if suffix == "vmlu-test":
                scores.append(row(cid, dataset_id, label, "server_accuracy", grade["total"], n=9833, gold="withheld",
                                  truncated=d["truncated_n"], source_path=grade_path))
            else:
                for metric, ci_key in [("accuracy", "ci95" if phase == "main" else "accuracy_ci95_wilson"),
                                       ("em", "em_ci95"), ("token_f1", "token_f1_ci95")]:
                    if metric in d:
                        scores.append(row(cid, dataset_id, label, metric, d[metric], n=d["expected_n"],
                                          correct=d.get("correct") if metric == "accuracy" else None, ci=d.get(ci_key),
                                          truncated=d.get("truncated_n"), source_path=f"{folder}/summary.json"))
    for category, data in grade["categories"].items():
        for level, label, score in [("category", category, data["total"]),
                                    *[("subject", key, value) for key, value in data["subjects"].items()]]:
            scores.append(row("qwen-direct-mc83-vmlu", "vi-multimodel-v2-vmlu-test", "VMLU Test", "server_accuracy", score,
                              level=level, category=label, gold="withheld", source_path=grade_path))
    return [{"id": "qwen-direct-mc83", "surface": "v2", "title": "Qwen3.5-9B-65K · API Direct · MC-83",
             "protocol": test_run["protocol_id"], "scope": "12.179 câu trên VMLU, Legal và reading; không V-Bench.",
             "conditions": conditions, "benchmarks": scores,
             "comments": ["VMLU Test đạt 62,94% theo server grade; Dev đạt 69,97% theo gold cục bộ."],
             "notes": ["Qwen MC-83 dùng budget 20.000 tokens cho mọi dataset; weights Q4_K_M theo response model ID.",
                       "Temperature gửi 1,0; reasoning mặc định, không ghim effort; tools/seed không gửi.",
                       "Test chỉ có phần trăm server, không suy ra correct count hoặc CI95; giữ 2 câu không parse được trong mẫu chấm."]}]


def muse12_direct_reports(root: Path) -> list[dict]:
    """Expose MC-84 scores and user-supplied grade without guessing withheld counts."""
    base = "all_res/muse12_direct_mc84"
    profile = "muse-spark-1-2-contributor-direct-20k"
    grade_path = "docs/research/muse12-vmlu-test-server-grade-mc84-2026-10-14.json"
    if not (root / grade_path).is_file():
        return []
    grade = read_json(root, grade_path)
    test_run = read_json(root, f"{base}/vmlu/{profile}/run.json")
    import hashlib
    submission = root / f"{base}/vmlu/{profile}/submission_vmlu_test.csv"
    if (grade.get("condition_ids") != ["MC-84"] or grade.get("model_id") != "ocg/muse-spark-1.2-contributor"
            or grade.get("item_count") != 9833 or grade.get("manifest_sha256") != test_run["manifest_sha256"]
            or grade.get("condition_sha256") != test_run["condition_sha256"]
            or grade.get("submission_sha256") != hashlib.sha256(submission.read_bytes()).hexdigest()):
        raise SystemExit("Error: MC-84 server grade/submission provenance mismatch")
    conditions, scores = [], []
    labels = {"vmlu-valid": "VMLU Valid", "vmlu-dev": "VMLU Dev", "vmlu-test": "VMLU Test",
              "legal-mc-146": "Legal MC", "legal-nli-150": "Legal NLI", "vi-squad-200": "Vi-SQuAD",
              "vi-drop-200": "Vi-DROP", "bidlqa-test": "ViBidLQA Test"}
    for phase, expected in [("main", 2043), ("vmlu", 10136)]:
        folder = f"{base}/{phase}/{profile}"
        meta = read_json(root, f"{folder}/run.json")
        summary = read_json(root, f"{folder}/summary.json")
        if (meta.get("status") != "complete" or meta.get("complete_items") != expected
                or meta.get("measurement_card_id") != "MC-84" or meta.get("model_id") != grade["model_id"]
                or meta.get("max_tokens_mc") != 20000 or meta.get("max_tokens_reading") != 20000
                or summary.get("manifest_sha256") != meta["manifest_sha256"]):
            raise SystemExit("Error: MC-84 completed coverage/controls mismatch")
        cid = f"muse12-direct-mc84-{phase}"
        fields = {key: UNKNOWN for key in FIELD_LABELS}
        fields.update({"date": f"{meta['started_at']} → {meta['finished_at']}", "harness": "API Direct · Responses",
                       "provider": "API Direct", "temperature": "1,0 gửi trong request; hiệu lực upstream không công bố",
                       "thinking": "Reasoning mặc định; không gửi effort, không ghim low/medium/high",
                       "seed": "không gửi", "tools": "none", "prompt": "System tối giản; user prompt đóng băng",
                       "context": "MC: câu hỏi và lựa chọn; reading: passage trong prompt; gold không gửi cho model",
                       "session": "Mỗi request độc lập; không history", "output_cap": "20.000 tokens cho cả MC và reading",
                       "workers": "12 workers · 4 shards × 3 lanes", "timeout": "300 giây/request",
                       "retry": "SDK 0; technical recovery; câu hoàn tất/truncated không chạy lại",
                       "gold": "Gold cục bộ; riêng VMLU Test do server chấm",
                       "identity": "Muse Spark 1.2 Contributor; quantization không công bố"})
        conditions.append({"id": cid, "model": "Muse Spark 1.2 Contributor", "card": "MC-84", "comparison_group": None,
                           "fields": fields, "sources": [source(f"{folder}/run.json", "Run metadata"),
                           source(f"{folder}/summary.json", "Scored summary"), source(grade_path, "Server grade")],
                           "manifest_sha256": meta["manifest_sha256"], "measurement_card_hash": meta["measurement_card_hash"],
                           "controls": {"profile_id": profile, "transport": "direct", "harness_version": None,
                           "tools": "none", "temperature_requested": 1.0, "temperature_effective": None, "thinking": None,
                           "seed_sent": False, "seed_requested": None, "output_caps": {"multiple_choice": 20000, "reading": 20000},
                           "workers": 12, "system_prompt": meta["system_prompt"], "prompt_version": meta["prompt_version"]}})
        for d in summary["datasets"]:
            if d["request_completed_n"] != d["expected_n"]:
                raise SystemExit("Error: MC-84 incomplete scored dataset")
            dataset_id = d["dataset_id"]
            suffix = dataset_id.split("-", 3)[-1]
            label = labels[suffix]
            if suffix == "vmlu-test":
                scores.append(row(cid, dataset_id, label, "server_accuracy", grade["total"], n=9833, gold="withheld",
                                  truncated=d["truncated_n"], source_path=grade_path))
            else:
                for metric, ci_key in [("accuracy", "ci95" if phase == "main" else "accuracy_ci95_wilson"),
                                       ("em", "em_ci95"), ("token_f1", "token_f1_ci95")]:
                    if metric in d:
                        scores.append(row(cid, dataset_id, label, metric, d[metric], n=d["expected_n"],
                                          correct=d.get("correct") if metric == "accuracy" else None, ci=d.get(ci_key),
                                          truncated=d.get("truncated_n"), source_path=f"{folder}/summary.json"))
    for category, data in grade["categories"].items():
        for level, label, score in [("category", category, data["total"]),
                                    *[("subject", key, value) for key, value in data["subjects"].items()]]:
            scores.append(row("muse12-direct-mc84-vmlu", "vi-multimodel-v2-vmlu-test", "VMLU Test", "server_accuracy", score,
                              level=level, category=label, gold="withheld", source_path=grade_path))
    return [{"id": "muse12-direct-mc84", "surface": "v2", "title": "Muse Spark 1.2 Contributor · API Direct · MC-84",
             "protocol": test_run["protocol_id"], "scope": "12.179 câu trên VMLU, Legal và reading; không V-Bench.",
             "conditions": conditions, "benchmarks": scores,
             "comments": ["VMLU Test đạt 87,49% theo server grade; Dev đạt 90,76% theo gold cục bộ."],
             "notes": ["Muse Spark 1.2 MC-84 dùng budget 20.000 tokens cho mọi dataset; cố định một route model.",
                       "Temperature gửi 1,0; reasoning mặc định, không ghim effort; tools/seed không gửi.",
                       "Test chỉ có phần trăm server, không suy ra correct count hoặc CI95; giữ 10 câu không parse được trong mẫu chấm."]}]

def mimo26_direct_reports(root: Path) -> list[dict]:
    """Expose MC-85 scores and user-supplied grade without guessing withheld counts."""
    base = "all_res/mimo26_direct_mc85"
    profile = "mimo-v2-6-flash-direct-20k"
    grade_path = "docs/research/mimo26-vmlu-test-server-grade-mc85-2026-10-15.json"
    if not (root / grade_path).is_file():
        return []
    grade = read_json(root, grade_path)
    test_run = read_json(root, f"{base}/vmlu/{profile}/run.json")
    import hashlib
    submission = root / f"{base}/vmlu/{profile}/submission_vmlu_test.csv"
    if (grade.get("condition_ids") != ["MC-85"] or grade.get("model_id") != "ocg/mimo-v2.6-flash"
            or grade.get("item_count") != 9833 or grade.get("manifest_sha256") != test_run["manifest_sha256"]
            or grade.get("condition_sha256") != test_run["condition_sha256"]
            or grade.get("submission_sha256") != hashlib.sha256(submission.read_bytes()).hexdigest()):
        raise SystemExit("Error: MC-85 server grade/submission provenance mismatch")
    conditions, scores = [], []
    labels = {"vmlu-valid": "VMLU Valid", "vmlu-dev": "VMLU Dev", "vmlu-test": "VMLU Test",
              "legal-mc-146": "Legal MC", "legal-nli-150": "Legal NLI", "vi-squad-200": "Vi-SQuAD",
              "vi-drop-200": "Vi-DROP", "bidlqa-test": "ViBidLQA Test"}
    for phase, expected in [("main", 2043), ("vmlu", 10136)]:
        folder = f"{base}/{phase}/{profile}"
        meta = read_json(root, f"{folder}/run.json")
        summary = read_json(root, f"{folder}/summary.json")
        if (meta.get("status") != "complete" or meta.get("complete_items") != expected
                or meta.get("measurement_card_id") != "MC-85" or meta.get("model_id") != grade["model_id"]
                or meta.get("max_tokens_mc") != 20000 or meta.get("max_tokens_reading") != 20000
                or summary.get("manifest_sha256") != meta["manifest_sha256"]):
            raise SystemExit("Error: MC-85 completed coverage/controls mismatch")
        cid = f"mimo26-direct-mc85-{phase}"
        fields = {key: UNKNOWN for key in FIELD_LABELS}
        fields.update({"date": f"{meta['started_at']} → {meta['finished_at']}", "harness": "API Direct · Responses",
                       "provider": "API Direct", "temperature": "1,0 gửi trong request; hiệu lực upstream không công bố",
                       "thinking": "Reasoning mặc định; không gửi effort, không ghim low/medium/high",
                       "seed": "không gửi", "tools": "none", "prompt": "System tối giản; user prompt đóng băng",
                       "context": "MC: câu hỏi và lựa chọn; reading: passage trong prompt; gold không gửi cho model",
                       "session": "Mỗi request độc lập; không history", "output_cap": "20.000 tokens cho cả MC và reading",
                       "workers": "12 workers · 4 shards × 3 lanes; VMLU đổi sang work stealing sau 9.102 câu hoàn tất" if phase == "vmlu" else "12 workers · 4 shards × 3 lanes cố định", "timeout": "300 giây/request",
                       "retry": "SDK 0; technical recovery; câu hoàn tất/truncated không chạy lại",
                       "gold": "Gold cục bộ; riêng VMLU Test do server chấm",
                       "identity": "MiMo V2.6 Flash; quantization không công bố"})
        conditions.append({"id": cid, "model": "MiMo V2.6 Flash", "card": "MC-85", "comparison_group": None,
                           "fields": fields, "sources": [source(f"{folder}/run.json", "Run metadata"),
                           source(f"{folder}/summary.json", "Scored summary"), source(grade_path, "Server grade"),
                           source("docs/research/mc85-work-stealing-2026-10-15.md", "Scheduler amendment")],
                           "manifest_sha256": meta["manifest_sha256"], "measurement_card_hash": meta["measurement_card_hash"],
                           "controls": {"profile_id": profile, "transport": "direct", "harness_version": None,
                           "tools": "none", "temperature_requested": 1.0, "temperature_effective": None, "thinking": None,
                           "seed_sent": False, "seed_requested": None, "output_caps": {"multiple_choice": 20000, "reading": 20000},
                           "workers": 12, "system_prompt": meta["system_prompt"], "prompt_version": meta["prompt_version"]}})
        for d in summary["datasets"]:
            if d["request_completed_n"] != d["expected_n"]:
                raise SystemExit("Error: MC-85 incomplete scored dataset")
            dataset_id = d["dataset_id"]
            suffix = dataset_id.split("-", 3)[-1]
            label = labels[suffix]
            if suffix == "vmlu-test":
                scores.append(row(cid, dataset_id, label, "server_accuracy", grade["total"], n=9833, gold="withheld",
                                  truncated=d["truncated_n"], source_path=grade_path))
            else:
                for metric, ci_key in [("accuracy", "ci95" if phase == "main" else "accuracy_ci95_wilson"),
                                       ("em", "em_ci95"), ("token_f1", "token_f1_ci95")]:
                    if metric in d:
                        scores.append(row(cid, dataset_id, label, metric, d[metric], n=d["expected_n"],
                                          correct=d.get("correct") if metric == "accuracy" else None, ci=d.get(ci_key),
                                          truncated=d.get("truncated_n"), source_path=f"{folder}/summary.json"))
    for category, data in grade["categories"].items():
        for level, label, score in [("category", category, data["total"]),
                                    *[("subject", key, value) for key, value in data["subjects"].items()]]:
            scores.append(row("mimo26-direct-mc85-vmlu", "vi-multimodel-v2-vmlu-test", "VMLU Test", "server_accuracy", score,
                              level=level, category=label, gold="withheld", source_path=grade_path))
    return [{"id": "mimo26-direct-mc85", "surface": "v2", "title": "MiMo V2.6 Flash · API Direct · MC-85",
             "protocol": test_run["protocol_id"], "scope": "12.179 câu trên VMLU, Legal và reading; không V-Bench.",
             "conditions": conditions, "benchmarks": scores,
             "comments": ["VMLU Test đạt 77,68% theo server grade; Dev đạt 81,85% theo gold cục bộ."],
             "notes": ["MiMo V2.6 Flash MC-85 dùng budget 20.000 tokens cho mọi dataset; cố định một route model.",
                       "Lịch chạy gồm fixed lanes rồi lane-work-stealing-v1; xem scheduler amendment, không coi toàn campaign đồng nhất scheduler.",
                       "Temperature gửi 1,0; reasoning mặc định, không ghim effort; tools/seed không gửi.",
                       "Test chỉ có phần trăm server, không suy ra correct count hoặc CI95; giữ 156 câu không parse được/blank trong mẫu chấm."]}]


def redact_hosts(value: object) -> object:
    """The same value with every internal endpoint host replaced by INTERNAL_HOST_LABEL, at any depth."""
    if isinstance(value, str):
        return INTERNAL_HOST.sub(INTERNAL_HOST_LABEL, value)
    if isinstance(value, list):
        return [redact_hosts(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_hosts(item) for key, item in value.items()}
    return value


def reading_means(rows: list[dict]) -> dict[str, float]:
    """EM and token-F1 in points, with the arithmetic of score_vi_multimodel's reading summary."""
    n = len(rows)
    return {"em": round(100 * sum(int(r["em"]) for r in rows) / n, 2),
            "token_f1": round(100 * (sum(float(r["token_f1"]) for r in rows) / n), 2)}


def reading_scores_path(root: Path, score: dict, condition: dict) -> str | None:
    """The scored rows behind a vi-reading-v2 score: <prefix>scores.jsonl beside its <prefix>summary.json, else the
    scores.jsonl of the condition's run folder. None for scores without per-item rows (the Reading-400 history)."""
    candidates = []
    if score["source"].endswith("summary.json"):
        candidates.append(score["source"].removesuffix("summary.json") + "scores.jsonl")
    candidates += [str(Path(entry["path"]).parent / "scores.jsonl") for entry in condition["sources"]
                   if entry["label"] == "Run metadata"]
    return next((path for path in candidates if (root / path).is_file()), None)


def reading_v3_rows(root: Path, report: dict, cache: dict[str, list[dict]]) -> list[dict]:
    """em_v3 / token_f1_v3 beside every dataset-level vi-reading-v2 score, from the same scored rows.

    Fails closed unless the rows reproduce the reported v2 score, n and CI95, so a v3 number can only sit next to
    the v2 number it re-scores."""
    conditions = {condition["id"]: condition for condition in report["conditions"]}
    added = []
    for score in report["benchmarks"]:
        if score["level"] != "dataset" or score["metric"] not in V3_METRICS:
            continue
        path = reading_scores_path(root, score, conditions[score["condition_id"]])
        if path is None:
            continue
        if path not in cache:
            cache[path] = [json.loads(line) for line in (root / path).read_text(encoding="utf-8").splitlines()
                           if line.strip()]
        rows = [r for r in cache[path] if r.get("dataset_id") == score["dataset_id"] and "token_f1" in r
                and not str(r.get("replicate_id", "")).startswith("repeat-")]
        if not rows:
            continue
        metric = score["metric"]
        ci = clustered_mean_interval(rows, value_key=metric, cluster_key="passage_id")
        if (len(rows) != score["n"] or reading_means(rows)[metric] != score["score"]
                or (score["ci_low"] is not None and [score["ci_low"], score["ci_high"]] != list(ci or []))):
            raise SystemExit(f"Error: {path} does not reproduce {score['condition_id']} {score['dataset_id']} {metric}")
        rescored = [vi_reading_v3.rescore_row(r) for r in rows]
        ci_v3 = clustered_mean_interval(rescored, value_key=metric, cluster_key="passage_id")
        added.append(row(score["condition_id"], score["dataset_id"], score["dataset"], V3_METRICS[metric],
                         reading_means(rescored)[metric], n=score["n"], ci=list(ci_v3) if ci_v3 else None,
                         gold=score["gold"], truncated=score["truncated"], source_path=path))
    return added


def build(root: Path = ROOT) -> dict:
    records = read_csv(root, SCORE_CSV); cards = card_index(root)
    omp_full_tools_report, omp_full_tools_run_summary = muse13_omp_full_tools_report(root)
    muse12_full_tools_report, muse12_full_tools_run_summary = muse12_omp_full_tools_report(root)
    qwen_full_tools_report, qwen_full_tools_run_summary = qwen_omp_full_tools_report(root)
    mimo_full_tools_report, mimo_full_tools_run_summary = mimo26_omp_full_tools_report(root)
    reports = [
        modern_report(root, records, version=1, phase="main", report_id="main-v1", title="Main V1 · sáu dataset tiếng Việt", selectors={"main_v1"}, surface="v1"),
        modern_report(root, records, version=1, phase="pilot", report_id="pilot-v1", title="Pilot V1 · diagnostics", selectors={"pilot", "pilot_omp"}, surface="v1"),
        modern_report(root, records, version=2, phase="vmlu", report_id="vmlu-v2", title="VMLU V2 · Dev / Valid / Test server", selectors={"vmlu_v2", "vmlu_v2_server_scored"}, surface="v2"),
        modern_report(root, records, version=2, phase="pilot", report_id="pilot-v2", title="Pilot V2 · VMLU + synthetic agentic", selectors={"pilot_v2"}, surface="v2"),
        full_tools_report(root, cards),
        omp_full_tools_report,
        muse12_full_tools_report,
        qwen_full_tools_report,
        mimo_full_tools_report,
        *muse12_main_reports(root),
        *muse13_direct_reports(root),
        *qwen_direct_reports(root),
        *muse12_direct_reports(root),
        *mimo26_direct_reports(root),
        *legacy_direct_reports(root, cards),
        *legacy_harness_reports(root, cards, read_json(root, "web/public/benchmark-data.json")["harness"]),
    ]
    scored_rows: dict[str, list[dict]] = {}
    for report in reports:
        v3_rows = reading_v3_rows(root, report, scored_rows)
        report["benchmarks"] += v3_rows
        report["notes"] = list(dict.fromkeys(report["notes"] + ([V3_NOTE] if v3_rows else [])))
        validate(report)
    data = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "field_labels": FIELD_LABELS,
            "metric_labels": METRIC_LABELS, "reports": reports,
            "run_summaries": [*muse12_vmlu_run_summaries(root), omp_full_tools_run_summary, muse12_full_tools_run_summary, qwen_full_tools_run_summary, mimo_full_tools_run_summary]}
    return redact_hosts(data)  # type: ignore[return-value]


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
    if INTERNAL_HOST.search(json.dumps(data, ensure_ascii=False)):
        raise SystemExit("Error: an internal endpoint host would be published; redact it first")
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
