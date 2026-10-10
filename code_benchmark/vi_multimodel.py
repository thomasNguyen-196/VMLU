"""Versioned Vietnamese multi-model benchmark contract and item adapters.

The protocol builds immutable pilot/main manifests and never puts gold in a
model request. Legacy prompts and scorers remain separate. Run from repo root.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

try:
    from code_benchmark.common import (
        DROP_DEFAULT,
        GOLD_REVIEW_DEFAULT,
        MANIFEST_DEFAULT,
        RESULTS_DIR,
        SQUAD_DEFAULT,
        read_csv_checked,
    )
    from code_benchmark.run_bidlqa_eval import (
        load_source as load_bidlqa_source,
        split_config as bidlqa_split_config,
        verify_join as verify_bidlqa_join,
    )
    from code_benchmark.run_harness_eval import load_legal_mc, load_legal_nli
    from code_benchmark.run_mc_eval import build_prompt, subject_category
    from code_benchmark.run_reading_eval import build_reading_prompt, index_sources
except ImportError:
    from common import (
        DROP_DEFAULT,
        GOLD_REVIEW_DEFAULT,
        MANIFEST_DEFAULT,
        RESULTS_DIR,
        SQUAD_DEFAULT,
        read_csv_checked,
    )
    from run_bidlqa_eval import (
        load_source as load_bidlqa_source,
        split_config as bidlqa_split_config,
        verify_join as verify_bidlqa_join,
    )
    from run_harness_eval import load_legal_mc, load_legal_nli
    from run_mc_eval import build_prompt, subject_category
    from run_reading_eval import build_reading_prompt, index_sources

ROOT = Path(__file__).resolve().parents[1]
PROFILE_FILE = ROOT / "data" / "vi_multimodel_profiles.json"
PROTOCOL_FILE = ROOT / "data" / "vi_multimodel_protocol_v1.json"
MANIFEST_DIR = ROOT / "data" / "vi_multimodel_v1"
OUTPUT_DIR = ROOT / "all_res" / "vi_multimodel_v1"
PROTOCOL_ID = "vi-multimodel-v1"
PILOT_PHASES = {"pilot", "pilot_omp"}
PROFILE_IDS = (
    "muse-spark-1-3-contributor",
    "mimo-v2-6-flash",
    "mimo-v2-5",
    "qwen3-5-9b-65k",
)
MAIN_DATASET_IDS = (
    "vi-multimodel-v1-vmlu-valid",
    "vi-multimodel-v1-vi-squad-200",
    "vi-multimodel-v1-vi-drop-200",
    "vi-multimodel-v1-legal-mc-146",
    "vi-multimodel-v1-legal-nli-150",
    "vi-multimodel-v1-bidlqa-test",
)
_EM_EDGE_PUNCTUATION = "\"'“”‘’()[]{}.,;:!?"
_TOKEN_EDGE_OPEN = "\"'“”‘’([{<"  # nosec B105 — punctuation stripped from word tokens, not an auth token
_TOKEN_EDGE_CLOSE = "\"'“”‘’)]}>.,;:!?"  # nosec B105 — punctuation stripped from word tokens, not an auth token
_FINAL_LABEL_RE = re.compile(
    r"(?:đáp án cuối|đáp án|trả lời|final answer|answer)\s*[:：]\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvalItem:
    """One request and its private reference; gold never enters the request."""

    dataset_id: str
    source_dataset: str
    item_id: str
    replicate_id: str
    task: str
    stratum: str
    question: str
    passage_id: str
    prompt: str
    gold_answer: str

    @property
    def run_key(self) -> str:
        return f"{self.dataset_id}:{self.item_id}:{self.replicate_id}"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"Error: required benchmark input is missing: {path}")
    return sha256_bytes(path.read_bytes())


def normalized_key(text: str) -> str:
    value = unicodedata.normalize("NFC", str(text or "")).casefold()
    return " ".join(value.split())


def normalize_em_answer(text: str) -> str:
    """EM v2: NFC, casefold and whitespace only; keep accents, signs and units."""
    value = unicodedata.normalize("NFC", str(text or "")).casefold()
    return " ".join(value.split()).strip(_EM_EDGE_PUNCTUATION)


def tokenize_vi(text: str) -> list[str]:
    """Whitespace tokenization with edge punctuation removed, keeping units."""
    normalized = unicodedata.normalize("NFC", str(text or "")).casefold()
    tokens = []
    for token in normalized.split():
        token = token.strip(_TOKEN_EDGE_OPEN)
        token = token.rstrip(_TOKEN_EDGE_CLOSE)
        if token:
            tokens.append(token)
    return tokens


def score_token_f1(prediction: str, reference: str) -> float:
    predicted = Counter(tokenize_vi(prediction))
    expected = Counter(tokenize_vi(reference))
    if not predicted and not expected:
        return 1.0
    if not predicted or not expected:
        return 0.0
    overlap = sum((predicted & expected).values())
    if not overlap:
        return 0.0
    precision = overlap / sum(predicted.values())
    recall = overlap / sum(expected.values())
    return 2 * precision * recall / (precision + recall)


def score_vi_reading(prediction: str, reference: str) -> dict[str, float | int]:
    reference_norm = normalize_em_answer(reference)
    prediction_norm = normalize_em_answer(prediction)
    return {
        "em": int(bool(reference_norm) and prediction_norm == reference_norm),
        "token_f1": score_token_f1(prediction, reference),
    }


def extract_final_answer(raw_response: str) -> str:
    text = str(raw_response or "").strip()
    matches = list(_FINAL_LABEL_RE.finditer(text))
    if not matches:
        return text
    answer = text[matches[-1].end():].strip()
    return answer.splitlines()[0].strip() if answer else text


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: invalid JSONL at {path}: {exc}") from exc


def _load_reading400() -> list[EvalItem]:
    manifest = read_csv_checked(
        ROOT / MANIFEST_DEFAULT,
        required={"dataset", "item_id", "stratum", "passage_id", "question"},
        label="registered reading400 manifest",
    )
    gold_rows = read_csv_checked(
        ROOT / GOLD_REVIEW_DEFAULT,
        required={"dataset", "item_id", "gold_answer"},
        label="reviewed reading400 gold",
    )
    gold = {(row["dataset"], str(row["item_id"])): str(row["gold_answer"]).strip() for row in gold_rows}
    source_index = index_sources(ROOT / SQUAD_DEFAULT, ROOT / DROP_DEFAULT)
    out = []
    for row in manifest:
        source_dataset = str(row["dataset"])
        item_id = str(row["item_id"])
        key = (source_dataset, item_id)
        source = source_index.get(key)
        if source is None:
            raise SystemExit(f"Error: reading400 item missing from source: {key}")
        question = str(row["question"])
        if str(source.get("question", "")).strip() != question.strip():
            raise SystemExit(f"Error: question drift for reading400 item {key}")
        answer = gold.get(key, "")
        if not answer:
            raise SystemExit(f"Error: reviewed gold missing for reading400 item {key}")
        context = str(source.get("context", ""))
        dataset_id = (
            "vi-multimodel-v1-vi-squad-200"
            if source_dataset == "squad"
            else "vi-multimodel-v1-vi-drop-200"
        )
        out.append(EvalItem(
            dataset_id=dataset_id,
            source_dataset=source_dataset,
            item_id=item_id,
            replicate_id="main-000",
            task="reading",
            stratum=str(row["stratum"]),
            question=question,
            passage_id=sha256_bytes(normalized_key(context).encode("utf-8")),
            prompt=build_reading_prompt(context, question),
            gold_answer=answer,
        ))
    return out


def _load_vmlu(split: str) -> list[EvalItem]:
    path = ROOT / ("vmlu_mqa_v1.5/dev.jsonl" if split == "dev" else "vmlu_mqa_v1.5/valid.jsonl")
    dataset_id = "vmlu-mqa-dev" if split == "dev" else "vi-multimodel-v1-vmlu-valid"
    out = []
    for row in _read_jsonl(path):
        item_id = str(row.get("id", "")).strip()
        question = str(row.get("question", "")).strip()
        choices = row.get("choices")
        answer = str(row.get("answer", "")).strip().upper()
        if not item_id or not question or not isinstance(choices, list) or not answer:
            raise SystemExit(f"Error: malformed VMLU row in {path}: {item_id!r}")
        subject_number, subject, category = subject_category(item_id)
        out.append(EvalItem(
            dataset_id=dataset_id,
            source_dataset=split,
            item_id=item_id,
            replicate_id="main-000",
            task="multiple_choice",
            stratum=category,
            question=question,
            passage_id=(f"{subject_number:02d} {subject}" if subject_number else "unknown"),
            prompt=build_prompt(question, choices),
            gold_answer=answer,
        ))
    return out


def _load_legal(dataset_id: str) -> list[EvalItem]:
    if dataset_id in {"legal-mc-146", "vi-multimodel-v1-legal-mc-146"}:
        rows = load_legal_mc("Qwen3_5-9B-28K")
    elif dataset_id in {"legal-nli-150", "vi-multimodel-v1-legal-nli-150"}:
        rows = load_legal_nli("Qwen3_5-9B-28K")
    else:
        raise SystemExit(f"Error: unknown legal dataset: {dataset_id}")
    return [
        EvalItem(
            dataset_id=dataset_id,
            source_dataset="legal-slm",
            item_id=str(row["item_id"]),
            replicate_id="main-000",
            task="multiple_choice",
            stratum="legal",
            question=str(row["question"]),
            passage_id="legal",
            prompt=str(row["prompt"]),
            gold_answer=str(row["gold"]).strip().upper(),
        )
        for row in rows
    ]


def _load_bidlqa(split: str) -> list[EvalItem]:
    config = bidlqa_split_config(split)
    source_rows = load_bidlqa_source(config["source"], config["sha"])
    manifest = read_csv_checked(
        config["manifest"],
        required={"dataset", "item_id", "stratum", "question", "gold_answer"},
        label=f"ViBidLQA {split} manifest",
    )
    verify_bidlqa_join(manifest, source_rows, config["id_prefix"])
    dataset_id = "vi-multimodel-v1-bidlqa-test" if split == "test" else "bidlqa-val"
    return [
        EvalItem(
            dataset_id=dataset_id,
            source_dataset="bidlqa",
            item_id=str(manifest_row["item_id"]),
            replicate_id="main-000",
            task="reading",
            stratum=str(manifest_row.get("stratum", "auction")),
            question=str(manifest_row["question"]),
            passage_id=sha256_bytes(normalized_key(str(source_row["context"])).encode("utf-8")),
            prompt=build_reading_prompt(str(source_row["context"]), str(manifest_row["question"])),
            gold_answer=str(manifest_row["gold_answer"]).strip(),
        )
        for manifest_row, source_row in zip(manifest, source_rows, strict=True)
    ]


def _allocate_counts(sizes: dict[str, int], total: int) -> dict[str, int]:
    available = sum(sizes.values())
    if total > available or available == 0:
        raise SystemExit(f"Error: cannot sample {total} items from n={available}")
    exact = {key: total * size / available for key, size in sizes.items()}
    allocated = {key: int(value) for key, value in exact.items()}
    remainder = total - sum(allocated.values())
    order = sorted(sizes, key=lambda key: (exact[key] - allocated[key], key), reverse=True)
    for key in order[:remainder]:
        allocated[key] += 1
    return allocated


def ensure_unique_items(items: list[EvalItem], *, allow_replicates: bool = False) -> None:
    keys = [
        item.run_key if allow_replicates else f"{item.dataset_id}:{item.item_id}"
        for item in items
    ]
    if len(keys) != len(set(keys)):
        duplicates = [key for key, n in Counter(keys).items() if n > 1]
        raise SystemExit(f"Error: duplicate item identities: {duplicates[:5]}")


def load_main_items() -> list[EvalItem]:
    items = [
        *_load_vmlu("valid"),
        *_load_reading400(),
        *_load_legal("vi-multimodel-v1-legal-mc-146"),
        *_load_legal("vi-multimodel-v1-legal-nli-150"),
        *_load_bidlqa("test"),
    ]
    counts = Counter(item.dataset_id for item in items)
    expected = {
        "vi-multimodel-v1-vmlu-valid": 744,
        "vi-multimodel-v1-vi-squad-200": 200,
        "vi-multimodel-v1-vi-drop-200": 200,
        "vi-multimodel-v1-legal-mc-146": 146,
        "vi-multimodel-v1-legal-nli-150": 150,
        "vi-multimodel-v1-bidlqa-test": 603,
    }
    if dict(counts) != expected:
        raise SystemExit(f"Error: main sample counts differ from protocol v1: {dict(counts)}")
    ensure_unique_items(items)
    return items


def load_pilot_items() -> list[EvalItem]:
    main_vmlu = _load_vmlu("valid")
    main_questions = {normalized_key(item.question) for item in main_vmlu}
    candidates = [item for item in _load_vmlu("dev") if normalized_key(item.question) not in main_questions]
    if len(candidates) < 100:
        raise SystemExit(f"Error: only {len(candidates)} disjoint VMLU-dev items; need 100")

    rng = random.Random(42)
    by_category: dict[str, list[EvalItem]] = {}
    for item in candidates:
        by_category.setdefault(item.stratum, []).append(item)
    allocation = _allocate_counts({key: len(rows) for key, rows in by_category.items()}, 100)
    selected_ids: set[str] = set()
    for category, rows in by_category.items():
        selected_ids.update(item.item_id for item in rng.sample(rows, allocation.get(category, 0)))
    selected_vmlu = [item for item in candidates if item.item_id in selected_ids]

    test_items = _load_bidlqa("test")
    test_questions = {normalized_key(item.question) for item in test_items}
    test_passages = {item.passage_id for item in test_items}
    eligible_val = [
        item for item in _load_bidlqa("val")
        if normalized_key(item.question) not in test_questions and item.passage_id not in test_passages
    ]
    if len(eligible_val) < 80:
        raise SystemExit(f"Error: only {len(eligible_val)} disjoint ViBidLQA-val items; need 80")
    selected_val = rng.sample(eligible_val, 80)
    unique_items = selected_vmlu + selected_val
    repeated = rng.sample(selected_vmlu, 10) + rng.sample(selected_val, 10)
    pilot_items = [
        replace(item, replicate_id=f"pilot-{index + 1:03d}")
        for index, item in enumerate(unique_items)
    ]
    pilot_items.extend(
        replace(item, replicate_id=f"repeat-{index + 1:02d}")
        for index, item in enumerate(repeated)
    )
    if len(pilot_items) != 200:
        raise SystemExit(f"Error: pilot v1 has {len(pilot_items)} rows, expected 200")
    ensure_unique_items(pilot_items, allow_replicates=True)
    return pilot_items


def source_hashes() -> dict[str, str]:
    paths = (
        ROOT / "vmlu_mqa_v1.5" / "dev.jsonl",
        ROOT / "vmlu_mqa_v1.5" / "valid.jsonl",
        ROOT / MANIFEST_DEFAULT,
        ROOT / GOLD_REVIEW_DEFAULT,
        ROOT / "vmlu_squad_v1" / "vi_squad_benchmark_question_only.json",
        ROOT / "vmlu_drop_v1" / "vi_drop_benchmark_3309_question_only.json",
        ROOT / "data" / "legal_slm_multichoice_manifest.json",
        ROOT / "data" / "legal_nli_manifest.json",
        ROOT / "v_legal_slsp" / "legal_slm" / "multichoice.jsonl",
        ROOT / "v_legal_slsp" / "legal_slm" / "nli.jsonl",
        RESULTS_DIR / "Qwen3_5-9B-28K" / "full_evaluation_legal_Qwen3_5-9B-28K.csv",
        RESULTS_DIR / "Qwen3_5-9B-28K" / "full_evaluation_nli_Qwen3_5-9B-28K.csv",
        ROOT / "data" / "bidlqa_val_manifest.csv",
        ROOT / "data" / "bidlqa_test_manifest.csv",
        ROOT / "v_legal_slsp" / "bidlqa" / "ViBidLQA_val.jsonl",
        ROOT / "v_legal_slsp" / "bidlqa" / "ViBidLQA_test.jsonl",
    )
    absolute_paths = [path if path.is_absolute() else ROOT / path for path in paths]
    return {str(path.relative_to(ROOT)): sha256_file(path) for path in absolute_paths}


def manifest_item(item: EvalItem) -> dict[str, str]:
    prompt_hash = sha256_bytes(item.prompt.encode("utf-8"))
    return {
        "dataset_id": item.dataset_id,
        "source_dataset": item.source_dataset,
        "item_id": item.item_id,
        "replicate_id": item.replicate_id,
        "task": item.task,
        "stratum": item.stratum,
        "passage_id": item.passage_id,
        "prompt_sha256": prompt_hash,
        "input_sha256": sha256_bytes(canonical_json({
            "dataset_id": item.dataset_id,
            "item_id": item.item_id,
            "prompt": item.prompt,
        })),
        "gold_sha256": sha256_bytes(normalize_em_answer(item.gold_answer).encode("utf-8")),
    }


def profile_roster_hash() -> str:
    roster = [
        {"profile_id": row["profile_id"], "model_id": row["model_id"]}
        for row in load_model_profiles().values()
    ]
    roster.sort(key=lambda row: row["profile_id"])
    return sha256_bytes(canonical_json(roster))


def build_manifest(phase: str) -> dict[str, Any]:
    if phase not in PILOT_PHASES | {"main"}:
        raise SystemExit(f"Error: unsupported phase {phase!r}")
    protocol = load_protocol()
    items = load_pilot_items() if phase in PILOT_PHASES else load_main_items()
    data = {
        "protocol_id": PROTOCOL_ID,
        "phase": phase,
        "protocol_sha256": protocol_phase_hash(protocol, phase),
        "profile_roster_sha256": profile_roster_hash(),
        "source_sha256": source_hashes(),
        "n": len(items),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in items).items())),
        "items": [manifest_item(item) for item in items],
    }
    data["manifest_sha256"] = sha256_bytes(canonical_json(data))
    return data


def save_manifest(phase: str, *, overwrite: bool = False) -> Path:
    output = MANIFEST_DIR / f"{phase}_v1.json"
    if output.exists() and not overwrite:
        raise SystemExit(f"Error: {output} already exists; use --overwrite only before any run")
    phase_output_dir = OUTPUT_DIR / phase
    if overwrite and phase_output_dir.exists():
        raise SystemExit(
            f"Error: refusing to replace {output}; output artifacts already exist under {phase_output_dir}"
        )
    data = build_manifest(phase)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_bytes(canonical_json(data) + b"\n")
    tmp.replace(output)
    return output


def load_manifest(phase: str) -> dict[str, Any]:
    path = MANIFEST_DIR / f"{phase}_v1.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot load frozen manifest {path}: {exc}") from exc
    claimed = data.get("manifest_sha256")
    unhashed = {key: value for key, value in data.items() if key != "manifest_sha256"}
    if claimed != sha256_bytes(canonical_json(unhashed)):
        raise SystemExit(f"Error: manifest hash mismatch: {path}")
    if data.get("protocol_id") != PROTOCOL_ID or data.get("phase") != phase:
        raise SystemExit(f"Error: wrong protocol/phase in {path}")
    if data.get("protocol_sha256") != protocol_phase_hash(load_protocol(), phase):
        raise SystemExit(f"Error: protocol configuration changed after freeze: {path}")
    if data.get("profile_roster_sha256") != profile_roster_hash():
        raise SystemExit(f"Error: model roster changed after freeze: {path}")
    if data.get("source_sha256") != source_hashes():
        raise SystemExit(f"Error: source or gold changed after freeze: {path}")
    if data.get("n") != len(data.get("items", [])):
        raise SystemExit(f"Error: item count mismatch in {path}")
    return data


def rebuild_items(phase: str) -> dict[str, EvalItem]:
    if phase not in PILOT_PHASES | {"main"}:
        raise SystemExit(f"Error: invalid phase {phase!r}")
    rows = load_pilot_items() if phase in PILOT_PHASES else load_main_items()
    mapping = {item.run_key: item for item in rows}
    if len(mapping) != len(rows):
        raise SystemExit("Error: duplicate benchmark run keys")
    return mapping


def load_model_profiles() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read model profiles {PROFILE_FILE}: {exc}") from exc
    rows = data.get("profiles")
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"Error: model profile registry is empty: {PROFILE_FILE}")
    profiles = {str(row.get("profile_id", "")): row for row in rows}
    if "" in profiles or len(profiles) != len(rows) or set(profiles) != set(PROFILE_IDS):
        raise SystemExit(f"Error: profile IDs differ from protocol v1: {sorted(profiles)}")
    return profiles


def load_protocol() -> dict[str, Any]:
    try:
        protocol = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read protocol {PROTOCOL_FILE}: {exc}") from exc
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise SystemExit(f"Error: invalid protocol identity in {PROTOCOL_FILE}")
    return protocol


def protocol_phase_hash(protocol: dict[str, Any], phase: str) -> str:
    """Hash shared rules and one phase; main caps can be frozen after pilot."""
    if phase not in PILOT_PHASES | {"main"}:
        raise SystemExit(f"Error: invalid protocol phase {phase!r}")
    shared = {key: value for key, value in protocol.items() if key not in PILOT_PHASES | {"main"}}
    return sha256_bytes(canonical_json({"shared": shared, "phase": phase, "settings": protocol[phase]}))


def item_from_manifest_row(row: dict[str, str], items: dict[str, EvalItem]) -> EvalItem:
    key = f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"
    item = items.get(key)
    if item is None or manifest_item(item) != row:
        raise SystemExit(f"Error: frozen input/gold/prompt mismatch for {key}")
    return item


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)
