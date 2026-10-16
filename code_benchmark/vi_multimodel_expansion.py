"""Versioned VMLU + V-Bench expansion data contract.

VMLU test has withheld answers; V-Bench has server-scored tracks. Keep those
references explicit and keep protocol v1 immutable. Run from repo root.
"""
from __future__ import annotations

import hashlib
import json
import random
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

try:
    from code_benchmark.run_mc_eval import build_prompt, extract_answer, subject_category
    from code_benchmark.run_vbench_eval import (
        extract_function_call,
        extract_mc_answer,
        load_vbench,
        prepare_prompt,
    )
    from code_benchmark.vi_multimodel import canonical_json, sha256_bytes
except ImportError:
    from run_mc_eval import build_prompt, extract_answer, subject_category
    from run_vbench_eval import extract_function_call, extract_mc_answer, load_vbench, prepare_prompt
    from vi_multimodel import canonical_json, sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "vi_multimodel_v2"
PROTOCOL_PATH = ROOT / "data" / "vi_multimodel_protocol_v2.json"
PROFILE_PATH = ROOT / "data" / "vi_multimodel_profiles_v2.json"
OUTPUT_DIR = ROOT / "all_res" / "vi_multimodel_v2"
PROTOCOL_ID = "vi-multimodel-expansion-v2"
PROFILE_IDS = (
    "muse-spark-1-3-contributor",
    "mimo-v2-6-flash",
    "mimo-v2-5",
    "qwen3-5-9b-65k",
)
VMLU_COUNTS = {"valid": 744, "dev": 303, "test": 9833}
VBENCH_COUNTS = {"mc": 4141, "agentic": 1000, "safety_skipped": 4000}


@dataclass(frozen=True)
class ExpandedItem:
    """One versioned request and a reference that may be withheld."""

    dataset_id: str
    item_id: str
    replicate_id: str
    task: str
    stratum: str | tuple[int, str, str]
    source_split: str
    question: str
    prompt: str
    gold_status: str
    gold_answer: str | None = None
    choices: tuple[str, ...] = ()
    functions: tuple[dict[str, Any], ...] = ()

    @property
    def run_key(self) -> str:
        return f"{self.dataset_id}:{self.item_id}:{self.replicate_id}"


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"Error: required source is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_question(text: str) -> str:
    value = unicodedata.normalize("NFC", str(text or "")).casefold()
    return " ".join(value.split())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: invalid JSONL in {path}: {exc}") from exc


def _dataset_id(source: str, split: str) -> str:
    if source == "vmlu":
        return f"vi-multimodel-v2-vmlu-{split}"
    if source == "vbench":
        return f"vi-multimodel-v2-vbench-{split}"
    if source == "synthetic":
        return "vi-multimodel-v2-pilot-agentic-synthetic"
    raise SystemExit(f"Error: unknown expansion source {source!r}")


def _vmlu_items(split: str) -> list[ExpandedItem]:
    if split not in VMLU_COUNTS:
        raise SystemExit(f"Error: invalid VMLU split {split!r}")
    path = ROOT / "vmlu_mqa_v1.5" / f"{split}.jsonl"
    expected = VMLU_COUNTS[split]
    rows = _read_jsonl(path)
    if len(rows) != expected:
        raise SystemExit(f"Error: VMLU {split} has n={len(rows)}, expected {expected}")
    out = []
    seen: set[str] = set()
    for row in rows:
        item_id = str(row.get("id", "")).strip()
        question = str(row.get("question", "")).strip()
        choices = row.get("choices")
        if not item_id or item_id in seen or not question or not isinstance(choices, list) or not choices:
            raise SystemExit(f"Error: malformed or duplicate VMLU {split} row {item_id!r}")
        seen.add(item_id)
        gold_raw = row.get("answer")
        if split == "test":
            if gold_raw not in (None, ""):
                raise SystemExit(f"Error: VMLU test unexpectedly contains a local answer: {item_id}")
            gold_status = "withheld"
            gold_answer = None
        else:
            gold_answer = str(gold_raw or "").strip().upper()
            if gold_answer not in {"A", "B", "C", "D", "E"}:
                raise SystemExit(f"Error: VMLU {split} has an invalid gold answer: {item_id}")
            gold_status = "local"
        out.append(ExpandedItem(
            dataset_id=_dataset_id("vmlu", split),
            item_id=item_id,
            replicate_id="main-000",
            task="multiple_choice",
            stratum=subject_category(item_id),
            source_split=f"vmlu_mqa_v1.5/{split}.jsonl",
            question=question,
            prompt=build_prompt(question, choices),
            gold_status=gold_status,
            gold_answer=gold_answer,
            choices=tuple(str(choice) for choice in choices),
        ))
    return out


def _vbench_items() -> tuple[list[ExpandedItem], int]:
    source_path = ROOT / "v_bench" / "public-test.jsonl"
    rows = load_vbench(source_path)
    counts = Counter(row["track"] for row in rows)
    if dict(counts) != {"mc": VBENCH_COUNTS["mc"], "agentic": VBENCH_COUNTS["agentic"]}:
        raise SystemExit(f"Error: V-Bench scorable tracks differ from v2026.03.28: {dict(counts)}")
    all_rows = _read_jsonl(source_path)
    safety_n = sum(not row.get("choices") and not row.get("function") for row in all_rows)
    if safety_n != VBENCH_COUNTS["safety_skipped"]:
        raise SystemExit(f"Error: V-Bench skipped safety/open row count changed: {safety_n}")
    items = []
    for row in rows:
        track = str(row["track"])
        items.append(ExpandedItem(
            dataset_id=_dataset_id("vbench", track),
            item_id=str(row["id"]),
            replicate_id="main-000",
            task="multiple_choice" if track == "mc" else "function_call",
            stratum=str(row["domain"]),
            source_split=f"v_bench/public-test.jsonl:{track}",
            question=str(row["question"]),
            prompt=prepare_prompt(row, style="minimal"),
            gold_status="server",
            choices=tuple(str(choice) for choice in row.get("choices") or []),
            functions=tuple(row.get("function") or []),
        ))
    return items, safety_n


def _pilot_vmlu_items() -> list[ExpandedItem]:
    dev = _vmlu_items("dev")
    heldout = _vmlu_items("valid") + _vmlu_items("test")
    heldout_questions = {normalized_question(item.question) for item in heldout}
    candidates = [item for item in dev if normalized_question(item.question) not in heldout_questions]
    if len(candidates) < 100:
        raise SystemExit(f"Error: only {len(candidates)} disjoint VMLU dev prompts; need 100")
    by_subject: dict[str, list[ExpandedItem]] = defaultdict(list)
    for item in candidates:
        by_subject[item.stratum].append(item)
    rng = random.Random(42)
    subject_rows = {key: list(rows) for key, rows in by_subject.items()}
    for rows in subject_rows.values():
        rng.shuffle(rows)
    selected: list[ExpandedItem] = []
    subject_names = sorted(subject_rows)
    while len(selected) < 100:
        made_progress = False
        for subject in subject_names:
            if subject_rows[subject] and len(selected) < 100:
                selected.append(subject_rows[subject].pop())
                made_progress = True
        if not made_progress:
            break
    if len(selected) != 100:
        raise SystemExit(f"Error: VMLU dev pilot selection stopped at {len(selected)}")
    return [replace(item, replicate_id=f"pilot-{index + 1:03d}") for index, item in enumerate(selected)]


def _synthetic_pilot_examples() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Create 80 deterministic, gold-known function calls for adapter probing."""
    cities = (
        ("Hà Nội", "Ha Noi"), ("Đà Nẵng", "Da Nang"), ("Cần Thơ", "Can Tho"),
        ("Huế", "Hue"), ("Nha Trang", "Nha Trang"), ("Đà Lạt", "Da Lat"),
        ("Hải Phòng", "Hai Phong"), ("Vinh", "Vinh"), ("Quy Nhơn", "Quy Nhon"),
        ("Biên Hòa", "Bien Hoa"),
    )
    amount_cases = ((10, 5), (21, 9), (100, 25), (7, 8), (32, 11), (999, 1), (43, 57), (1200, 300), (0, 6), (88, 12))
    schemas: list[dict[str, Any]] = [
        {"name": "tra_cuu_thoi_tiet", "description": "Tra cứu thời tiết tại thành phố.", "parameters": {"type": "object", "properties": {"thanh_pho": {"type": "string"}}, "required": ["thanh_pho"]}},
        {"name": "tinh_tong", "description": "Cộng hai số nguyên.", "parameters": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]}},
        {"name": "dat_lich", "description": "Tạo lịch hẹn.", "parameters": {"type": "object", "properties": {"ngay": {"type": "string"}, "gio": {"type": "string"}, "su_kien": {"type": "string"}}, "required": ["ngay", "gio", "su_kien"]}},
        {"name": "tra_cuu_don_hang", "description": "Tra cứu đơn hàng.", "parameters": {"type": "object", "properties": {"ma_don": {"type": "string"}}, "required": ["ma_don"]}},
        {"name": "tim_phuong_tien", "description": "Tìm phương tiện di chuyển.", "parameters": {"type": "object", "properties": {"loai": {"type": "string", "enum": ["xe_buyt", "tau_hoa", "may_bay"]}, "diem_den": {"type": "string"}}, "required": ["loai", "diem_den"]}},
        {"name": "gui_email", "description": "Soạn email.", "parameters": {"type": "object", "properties": {"nguoi_nhan": {"type": "string"}, "chu_de": {"type": "string"}, "noi_dung": {"type": "string"}}, "required": ["nguoi_nhan", "chu_de", "noi_dung"]}},
        {"name": "bat_den", "description": "Bật đèn trong phòng.", "parameters": {"type": "object", "properties": {"phong": {"type": "string", "enum": ["khach", "ngu", "bep"]}, "do_sang": {"type": "integer"}}, "required": ["phong"]}},
        {"name": "doi_tien", "description": "Đổi tiền theo mã tiền tệ.", "parameters": {"type": "object", "properties": {"so_tien": {"type": "number"}, "tu_te": {"type": "string"}, "sang_te": {"type": "string"}}, "required": ["so_tien", "tu_te", "sang_te"]}},
    ]
    out = []
    for index in range(80):
        group = index // 10
        slot = index % 10
        schema = schemas[group]
        if group == 0:
            city_vi, city_value = cities[slot]
            question = f"Tra cứu thời tiết cho thành phố {city_vi} giúp tôi."
            args = {"thanh_pho": city_value}
        elif group == 1:
            a, b = amount_cases[slot]
            question = f"Tính tổng của {a} và {b}."
            args = {"a": a, "b": b}
        elif group == 2:
            day = slot + 1
            question = f"Đặt lịch họp nhóm vào ngày 2026-10-{day:02d}, lúc 09:30, tên sự kiện là họp nhóm {slot + 1}."
            args = {"ngay": f"2026-10-{day:02d}", "gio": "09:30", "su_kien": f"họp nhóm {slot + 1}"}
        elif group == 3:
            code = f"DH-{202600 + slot:06d}"
            question = f"Kiểm tra giúp tôi tình trạng đơn hàng mã {code}."
            args = {"ma_don": code}
        elif group == 4:
            modes = (("xe_buyt", "xe buýt"), ("tau_hoa", "tàu hỏa"), ("may_bay", "máy bay"))
            mode, mode_vi = modes[slot % len(modes)]
            destination = cities[slot][0]
            question = f"Tìm {mode_vi} đến {destination}."
            args = {"loai": mode, "diem_den": destination}
        elif group == 5:
            question = f"Gửi email cho lan{slot + 1}@example.vn, chủ đề lịch họp, nội dung là xác nhận lịch ngày mai."
            args = {"nguoi_nhan": f"lan{slot + 1}@example.vn", "chu_de": "lịch họp", "noi_dung": "xác nhận lịch ngày mai"}
        elif group == 6:
            room = (("khach", "phòng khách"), ("ngu", "phòng ngủ"), ("bep", "nhà bếp"))[slot % 3]
            question = f"Bật đèn ở {room[1]}."
            args = {"phong": room[0]}
            if slot % 2:
                args["do_sang"] = 70
                question = f"Bật đèn ở {room[1]} với độ sáng 70%."
        else:
            value = amount_cases[slot][0] + 0.5
            question = f"Đổi {value} USD sang VND."
            args = {"so_tien": value, "tu_te": "USD", "sang_te": "VND"}
        item = {"id": f"syn-{index + 1:03d}", "domain": f"synthetic_{schema['name']}", "track": "agentic",
                "question": question, "choices": [], "function": [schema]}
        gold = {"id": item["id"], "answer": [{schema["name"]: args}]}
        out.append((item, gold))
    return out


def write_synthetic_sources() -> tuple[Path, Path]:
    input_path = DATA_DIR / "pilot_agentic_synthetic_input.jsonl"
    gold_path = DATA_DIR / "pilot_agentic_synthetic_gold.jsonl"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    generated = _synthetic_pilot_examples()
    for path, rows in (
        (input_path, [item for item, _ in generated]),
        (gold_path, [gold for _, gold in generated]),
    ):
        payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
        if path.exists():
            if path.read_text(encoding="utf-8") != payload:
                raise SystemExit(f"Error: synthetic pilot source changed after freeze: {path}")
        else:
            path.write_text(payload, encoding="utf-8")
    return input_path, gold_path


def _synthetic_items() -> list[ExpandedItem]:
    input_path, gold_path = write_synthetic_sources()
    inputs = _read_jsonl(input_path)
    gold_by_id = {str(row["id"]): row["answer"] for row in _read_jsonl(gold_path)}
    items = []
    for row in inputs:
        item_id = str(row["id"])
        if item_id not in gold_by_id:
            raise SystemExit(f"Error: synthetic pilot gold missing for {item_id}")
        gold_json = json.dumps(gold_by_id[item_id], ensure_ascii=False, separators=(",", ":"))
        items.append(ExpandedItem(
            dataset_id=_dataset_id("synthetic", "agentic"),
            item_id=item_id,
            replicate_id="pilot-000",
            task="function_call",
            stratum=str(row["domain"]),
            source_split="synthetic-pilot-v1",
            question=str(row["question"]),
            prompt=prepare_prompt(row, style="minimal"),
            gold_status="local",
            gold_answer=gold_json,
            functions=tuple(row["function"]),
        ))
    return items


def build_items(phase: str) -> list[ExpandedItem]:
    if phase == "vmlu":
        items = _vmlu_items("valid") + _vmlu_items("dev") + _vmlu_items("test")
        expected = {
            _dataset_id("vmlu", "valid"): 744,
            _dataset_id("vmlu", "dev"): 303,
            _dataset_id("vmlu", "test"): 9833,
        }
    elif phase == "vbench":
        vbench_items, _ = _vbench_items()
        items = vbench_items
        expected = {
            _dataset_id("vbench", "mc"): 4141,
            _dataset_id("vbench", "agentic"): 1000,
        }
    elif phase == "pilot":
        vmlu = _pilot_vmlu_items()
        synthetic = _synthetic_items()
        rng = random.Random(42)
        repeats = rng.sample(vmlu, 10) + rng.sample(synthetic, 10)
        items = [
            replace(item, replicate_id=f"pilot-{index + 1:03d}")
            for index, item in enumerate(vmlu)
        ] + synthetic
        items.extend(
            replace(item, replicate_id=f"repeat-{index + 1:02d}")
            for index, item in enumerate(repeats)
        )
        expected = {
            _dataset_id("vmlu", "dev"): 100,
            _dataset_id("synthetic", "agentic"): 80,
        }
    else:
        raise SystemExit(f"Error: unsupported expansion phase {phase!r}")
    keys = [item.run_key for item in items]
    if len(keys) != len(set(keys)):
        raise SystemExit("Error: duplicate expanded run keys")
    counts = Counter(
        item.dataset_id for item in items if not item.replicate_id.startswith("repeat-")
    )
    if dict(counts) != expected:
        raise SystemExit(f"Error: expansion item counts differ: {dict(counts)} != {expected}")
    expected_n = {"pilot": 200, "vmlu": 10880, "vbench": 5141}[phase]
    if len(items) != expected_n:
        raise SystemExit(f"Error: expansion {phase} must contain {expected_n} requests, got {len(items)}")
    return items


def _item_manifest(item: ExpandedItem) -> dict[str, Any]:
    input_payload = {
        "dataset_id": item.dataset_id,
        "item_id": item.item_id,
        "prompt": item.prompt,
        "choices": item.choices,
        "functions": item.functions,
    }
    row: dict[str, Any] = {
        "dataset_id": item.dataset_id,
        "item_id": item.item_id,
        "replicate_id": item.replicate_id,
        "task": item.task,
        "stratum": list(item.stratum) if isinstance(item.stratum, tuple) else item.stratum,
        "source_split": item.source_split,
        "gold_status": item.gold_status,
        "prompt_sha256": sha256_bytes(item.prompt.encode("utf-8")),
        "input_sha256": sha256_bytes(canonical_json(input_payload)),
        "schema_sha256": sha256_bytes(canonical_json(item.functions)) if item.functions else "",
    }
    if item.gold_status == "local":
        if item.gold_answer is None:
            raise SystemExit(f"Error: local gold missing for {item.run_key}")
        row["gold_sha256"] = sha256_bytes(item.gold_answer.encode("utf-8"))
    elif item.gold_answer is not None:
        raise SystemExit(f"Error: withheld/server item carries gold: {item.run_key}")
    return row


def _profile_roster_hash() -> str:
    profiles = load_profiles()
    roster = [
        {"profile_id": key, "model_id": value["model_id"], "model_ref": value["model_ref"]}
        for key, value in sorted(profiles.items())
    ]
    return sha256_bytes(canonical_json(roster))


def load_profiles() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read expansion profiles {PROFILE_PATH}: {exc}") from exc
    rows = data.get("profiles")
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"Error: expansion profile registry is empty: {PROFILE_PATH}")
    profiles = {str(row.get("profile_id", "")): row for row in rows}
    if "" in profiles or len(profiles) != len(rows) or set(profiles) != set(PROFILE_IDS):
        raise SystemExit(f"Error: expansion profile IDs differ from roster: {sorted(profiles)}")
    return profiles


def _protocol() -> dict[str, Any]:
    try:
        data = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read expansion protocol: {exc}") from exc
    if data.get("protocol_id") != PROTOCOL_ID or data.get("protocol_version") != 2:
        raise SystemExit("Error: invalid expansion protocol identity")
    if set(data.get("phases", {})) != {"pilot", "vmlu", "vbench"}:
        raise SystemExit("Error: expansion protocol phases differ from pilot/vmlu/vbench")
    return data


def _profile_file_hash() -> str:
    return sha256_file(PROFILE_PATH)


def source_hashes() -> dict[str, str]:
    write_synthetic_sources()
    paths = [
        ROOT / "vmlu_mqa_v1.5" / f"{split}.jsonl"
        for split in ("dev", "valid", "test", "all_gold")
    ]
    paths.extend([
        ROOT / "v_bench" / "public-test.jsonl",
        DATA_DIR / "pilot_agentic_synthetic_input.jsonl",
        DATA_DIR / "pilot_agentic_synthetic_gold.jsonl",
    ])
    return {str(path.relative_to(ROOT)): sha256_file(path) for path in paths}


def build_manifest(phase: str) -> dict[str, Any]:
    protocol = _protocol()
    items = build_items(phase)
    payload: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": 2,
        "phase": phase,
        "protocol_sha256": sha256_bytes(canonical_json(protocol["phases"][phase])),
        "profile_roster_sha256": _profile_roster_hash(),
        "profile_file_sha256": _profile_file_hash(),
        "source_sha256": source_hashes(),
        "n": len(items),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in items).items())),
        "safety_rows_skipped": VBENCH_COUNTS["safety_skipped"] if phase == "vbench" else 0,
        "items": [_item_manifest(item) for item in items],
    }
    payload["manifest_sha256"] = sha256_bytes(canonical_json(payload))
    return payload


def save_manifest(phase: str, *, overwrite: bool = False) -> Path:
    build_items(phase)
    path = DATA_DIR / f"{phase}_v2.json"
    if path.exists() and not overwrite:
        raise SystemExit(f"Error: {path} already exists; refuse to replace a frozen manifest")
    output_root = OUTPUT_DIR / phase
    if overwrite and output_root.exists():
        raise SystemExit(f"Error: refusing to replace a used manifest; artifacts exist under {output_root}")
    data = build_manifest(phase)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(canonical_json(data) + b"\n")
    tmp.replace(path)
    return path


def load_manifest(phase: str) -> dict[str, Any]:
    path = DATA_DIR / f"{phase}_v2.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read frozen expansion manifest {path}: {exc}") from exc
    claimed = data.get("manifest_sha256")
    unhashed = {key: value for key, value in data.items() if key != "manifest_sha256"}
    if claimed != sha256_bytes(canonical_json(unhashed)):
        raise SystemExit(f"Error: manifest hash mismatch: {path}")
    if data.get("protocol_id") != PROTOCOL_ID or data.get("phase") != phase:
        raise SystemExit(f"Error: wrong expansion protocol/phase in {path}")
    protocol = _protocol()
    if data.get("protocol_sha256") != sha256_bytes(canonical_json(protocol["phases"][phase])):
        raise SystemExit(f"Error: expansion phase settings changed after freeze: {path}")
    if data.get("profile_file_sha256") != _profile_file_hash() or data.get("profile_roster_sha256") != _profile_roster_hash():
        raise SystemExit(f"Error: model profiles changed after freeze: {path}")
    if data.get("source_sha256") != source_hashes():
        raise SystemExit(f"Error: an expansion source changed after freeze: {path}")
    if len(data.get("items", [])) != data.get("n"):
        raise SystemExit(f"Error: manifest item count mismatch: {path}")
    return data


def rebuild_items(phase: str) -> dict[str, ExpandedItem]:
    items = build_items(phase)
    mapping = {item.run_key: item for item in items}
    if len(mapping) != len(items):
        raise SystemExit("Error: duplicate expanded run keys")
    return mapping


def item_from_manifest_row(row: dict[str, Any], items: dict[str, ExpandedItem]) -> ExpandedItem:
    key = f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"
    item = items.get(key)
    if item is None or _item_manifest(item) != row:
        raise SystemExit(f"Error: frozen expansion prompt/schema/gold mismatch for {key}")
    return item


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)


def parse_expanded_answer(item: ExpandedItem, raw: str) -> dict[str, Any]:
    if item.task == "multiple_choice":
        answer = (
            extract_mc_answer(raw, list(item.choices))
            if item.source_split.startswith("v_bench/")
            else extract_answer(raw)
        )
        valid = answer in {"A", "B", "C", "D", "E"}
        correct = None if item.gold_answer is None else int(valid and answer == item.gold_answer.upper())
        return {"prediction": answer, "parse_valid": valid, "correct": correct}
    parsed = extract_function_call(raw, [dict(fn) for fn in item.functions])
    valid = bool(parsed)
    correct: int | None = None
    if valid and item.gold_answer is not None:
        actual = json.loads(parsed)
        expected = json.loads(item.gold_answer)
        correct = int(canonical_json(actual) == canonical_json(expected))
    elif item.gold_answer is not None:
        correct = 0
    return {"prediction": parsed, "parse_valid": valid, "correct": correct}
