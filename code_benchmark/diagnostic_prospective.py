"""Contract for the prospective diagnostic campaign (openspec change: diagnostic-prospective-campaign).

Arm-aware manifests, prompt builders, scoring wrapper and evidence validator for arms
B (frozen prompt), S (stepwise), O (oracle evidence), K (retrieved evidence) and KS.
Offline only: nothing here contacts an endpoint. The frozen prompts, extractors and scorers of
vi_multimodel.py / score_vi_multimodel.py are reused unchanged.

Run keys keep the frozen `dataset:item:replicate` shape; the arm lives in the replicate id
(`S-r2`), so the MC-80/82/83 engine, the manifest equality check and the ledger identity
triple keep working.
"""
from __future__ import annotations

import dataclasses
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import vi_multimodel as v1
    from code_benchmark.score_vi_multimodel import score_rows
except ImportError:  # executed from code_benchmark/
    import vi_multimodel as v1
    from score_vi_multimodel import score_rows

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "diagnostic_prospective_v1"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
TEMPLATES_PATH = DATA_DIR / "prompt_templates_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-prospective-v1"
ARMS = ("B", "S", "O", "K", "KS")
REASONING_ARMS = frozenset({"S", "KS"})
EVIDENCE_ARMS = frozenset({"O", "K", "KS"})
PHASES = ("core", "wide")
MAIN_REPLICATE = "main-000"

# Frozen main-v1 prompt skeletons. Duplicated on purpose: they are a byte contract with the
# historical prompts and are checked against every item by the tests.
MC_HEAD = "Chỉ đưa ra chữ cái đứng trước câu trả lời đúng (A, B, C, D hoặc E) của câu hỏi trắc nghiệm sau: \n"
MC_TAIL = "\nĐáp án: "
RD_HEAD = ("Đọc đoạn văn dưới đây và trả lời câu hỏi bằng một cụm từ hoặc số ngắn gọn, "
           "lấy nguyên văn trong đoạn văn khi có thể.\n\n")
RD_QUESTION = "\n\nCâu hỏi: "
RD_TAIL = "\nTrả lời: "

TEMPLATE_KEYS = ("version", "s_mc_head", "s_reading_head", "evidence_header", "evidence_item",
                 "evidence_separator", "evidence_trailer")
EVIDENCE_PLACEHOLDERS = ("{index}", "{doc_title}", "{locator}", "{text}")
PROVISION_KEYS = ("doc_id", "doc_title", "locator", "text", "text_sha256", "source_ref")
ORACLE_KEYS = ("dataset_id", "item_id", "provisions", "reviewer_id", "review_export_sha256", "eligibility")
FORBIDDEN_EVIDENCE_KEYS = frozenset({
    "answer", "gold", "gold_answer", "option", "option_letter", "choice", "rationale", "solution", "explanation",
})
_LEAK = re.compile(r"(?:đáp án|answer)\s*[:：]\s*[A-Ea-e]\b|lời giải|giải thích", re.IGNORECASE)
_MARKDOWN = re.compile(r"[*`]|^\s*#")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
# Same label pattern the frozen reading extractor uses (vi_multimodel.extract_final_answer).
_FINAL_LABEL = v1._FINAL_LABEL_RE  # noqa: SLF001 - frozen contract object, same package


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise _fail(f"{label} must be a JSON object: {path}")
    return value


def run_key(row: dict[str, Any]) -> str:
    return f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"


def item_key(dataset_id: str, item_id: str) -> str:
    return f"{dataset_id}:{item_id}"


def arm_of_replicate(replicate_id: str) -> str:
    arm, separator, number = str(replicate_id).partition("-r")
    if not separator or arm not in ARMS or not number.isdigit():
        raise _fail(f"replicate id {replicate_id!r} is not <ARM>-r<k>")
    return arm


# ---------------------------------------------------------------- protocol and templates

def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = _read_json(path, "campaign protocol")
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported prospective protocol id/version")
    if set(protocol.get("arms", {})) != set(ARMS):
        raise _fail("protocol arms differ from B/S/O/K/KS")
    if set(protocol.get("phases", {})) != set(PHASES):
        raise _fail("protocol phases differ from core/wide")
    for name, phase in protocol["phases"].items():
        arms = phase.get("arms", [])
        if not set(arms) <= set(ARMS) or "B" not in arms:
            raise _fail(f"phase {name} must use known arms and include B")
        if not isinstance(phase.get("replicates"), int) or phase["replicates"] < 1:
            raise _fail(f"phase {name} needs a positive replicate count")
    datasets = protocol.get("datasets")
    if not isinstance(datasets, list) or not datasets or len(datasets) != len(set(datasets)):
        raise _fail("protocol datasets must be a unique non-empty list")
    if not set(protocol.get("evidence", {}).get("eligible_datasets", [])) <= set(datasets):
        raise _fail("evidence-eligible datasets must be campaign datasets")
    cap = protocol.get("transport", {}).get("max_output_tokens")
    if not isinstance(cap, int) or cap < 1:
        raise _fail("protocol needs a positive max_output_tokens")
    return protocol


def load_templates(path: Path = TEMPLATES_PATH) -> dict[str, str]:
    templates = _read_json(path, "prompt templates")
    if set(templates) != set(TEMPLATE_KEYS):
        raise _fail(f"prompt templates must have exactly the keys {sorted(TEMPLATE_KEYS)}")
    if not all(isinstance(templates[key], str) and templates[key] for key in TEMPLATE_KEYS):
        raise _fail("every prompt template must be a non-empty string")
    if not all(token in templates["evidence_item"] for token in EVIDENCE_PLACEHOLDERS):
        raise _fail("evidence_item template lacks a placeholder")
    return templates


def load_registration(path: Path = REGISTRATION_PATH) -> dict[str, Any]:
    registration = _read_json(path, "registration record")
    for key in ("status", "card_ids", "card_files", "frozen"):
        if key not in registration:
            raise _fail(f"registration record lacks {key}")
    return registration


# ---------------------------------------------------------------- frozen prompt surgery

@dataclasses.dataclass(frozen=True)
class FrozenParts:
    kind: str       # "mc" or "reading"
    body: str       # mc: question plus options block; reading: the passage
    question: str   # reading only


def parse_frozen_prompt(item: v1.EvalItem) -> FrozenParts:
    """Split a frozen main-v1 prompt; any unexpected skeleton stops the run (never guess)."""
    prompt = item.prompt
    if item.task == "multiple_choice":
        if prompt.startswith(MC_HEAD) and prompt.endswith(MC_TAIL) and len(prompt) > len(MC_HEAD) + len(MC_TAIL):
            return FrozenParts("mc", prompt[len(MC_HEAD):len(prompt) - len(MC_TAIL)], "")
    elif item.task == "reading":
        if prompt.startswith(RD_HEAD) and prompt.endswith(RD_TAIL):
            inner = prompt[len(RD_HEAD):len(prompt) - len(RD_TAIL)]
            context, marker, question = inner.rpartition(RD_QUESTION)
            if marker:
                return FrozenParts("reading", context, question)
    raise _fail(f"unexpected frozen prompt skeleton for {item.run_key}")


def render_evidence_block(provisions: list[dict[str, Any]], templates: dict[str, str]) -> str:
    if not provisions:
        raise _fail("an evidence block needs at least one provision")
    rendered = [
        templates["evidence_item"].format(index=index, doc_title=p["doc_title"], locator=p["locator"], text=p["text"])
        for index, p in enumerate(provisions, 1)
    ]
    return templates["evidence_header"] + templates["evidence_separator"].join(rendered) + templates["evidence_trailer"]


def build_arm_prompt(item: v1.EvalItem, arm: str, templates: dict[str, str],
                     provisions: list[dict[str, Any]] | None = None) -> str:
    if arm not in ARMS:
        raise _fail(f"unknown arm {arm!r}")
    needs_evidence = arm in EVIDENCE_ARMS
    if needs_evidence != bool(provisions):
        raise _fail(f"arm {arm} {'requires' if needs_evidence else 'forbids'} evidence for {item.run_key}")
    parts = parse_frozen_prompt(item)
    if arm in REASONING_ARMS:
        if parts.kind == "mc":
            core = templates["s_mc_head"] + parts.body
        else:
            core = templates["s_reading_head"] + parts.body + RD_QUESTION + parts.question + "\n"
    else:
        core = item.prompt
    return (render_evidence_block(provisions, templates) if provisions else "") + core


# ---------------------------------------------------------------- evidence

def evidence_digest(evidence: dict[str, list[dict[str, Any]]]) -> str:
    return v1.sha256_bytes(v1.canonical_json(evidence))


def validate_provisions(provisions: Any, where: str) -> list[dict[str, Any]]:
    if not isinstance(provisions, list) or not provisions:
        raise _fail(f"{where}: provisions must be a non-empty list")
    for index, provision in enumerate(provisions, 1):
        if not isinstance(provision, dict) or set(provision) != set(PROVISION_KEYS):
            raise _fail(f"{where}: provision {index} must have exactly the keys {list(PROVISION_KEYS)}")
        if not all(isinstance(provision[key], str) and provision[key].strip() for key in PROVISION_KEYS):
            raise _fail(f"{where}: provision {index} has an empty field")
        if v1.sha256_bytes(provision["text"].encode("utf-8")) != provision["text_sha256"]:
            raise _fail(f"{where}: provision {index} text hash mismatch")
        if _LEAK.search(provision["text"]):
            raise _fail(f"{where}: provision {index} looks like an answer or an explanation")
    return provisions


def load_oracle_evidence(path: Path, protocol: dict[str, Any],
                         main_items: dict[str, v1.EvalItem]) -> dict[str, list[dict[str, Any]]]:
    """Return {dataset:item -> provisions}. Fails closed on leakage, ineligibility or hash drift."""
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read oracle evidence {path}: {exc}") from exc
    eligible = set(protocol["evidence"]["eligible_datasets"])
    required = protocol["evidence"]["required_input_evidence_sufficiency"]
    result: dict[str, list[dict[str, Any]]] = {}
    for number, row in enumerate(rows, 1):
        where = f"{path.name}:{number}"
        if not isinstance(row, dict):
            raise _fail(f"{where}: record must be an object")
        leaked = FORBIDDEN_EVIDENCE_KEYS & set(row)
        if leaked:
            raise _fail(f"{where}: record carries forbidden answer-bearing keys {sorted(leaked)}")
        if set(row) != set(ORACLE_KEYS):
            raise _fail(f"{where}: record must have exactly the keys {list(ORACLE_KEYS)}")
        key = item_key(row["dataset_id"], row["item_id"])
        if key in result:
            raise _fail(f"{where}: duplicate evidence for {key}")
        if row["dataset_id"] not in eligible:
            raise _fail(f"{where}: {key} is not an evidence-eligible dataset")
        if f"{key}:{MAIN_REPLICATE}" not in main_items:
            raise _fail(f"{where}: {key} is not a frozen main-v1 item")
        if row["eligibility"] != {"input_evidence_sufficiency": required}:
            raise _fail(f"{where}: eligibility must state input_evidence_sufficiency={required}")
        if not isinstance(row["reviewer_id"], str) or not row["reviewer_id"].strip():
            raise _fail(f"{where}: reviewer_id is empty")
        if not isinstance(row["review_export_sha256"], str) or not _SHA256_HEX.match(row["review_export_sha256"]):
            raise _fail(f"{where}: review_export_sha256 is not a SHA-256 hex digest")
        result[key] = validate_provisions(row["provisions"], where)
    return result


# ---------------------------------------------------------------- manifests

def anchor_item_keys(pilot_dir: Path) -> tuple[list[str], str]:
    """The 60 ordered audit anchors and the pilot content hash, verified against the packet bytes."""
    selection = _read_json(pilot_dir / "selection.json", "pilot selection")
    try:
        pilot_bytes = (pilot_dir / "pilot.jsonl").read_bytes()
    except OSError as exc:
        raise _fail(f"cannot read pilot packet in {pilot_dir}: {exc}") from exc
    if selection.get("pilot_file_sha256") != v1.sha256_bytes(pilot_bytes):
        raise _fail("pilot.jsonl does not match selection.json")
    rows = [json.loads(line) for line in pilot_bytes.decode("utf-8").splitlines() if line.strip()]
    keys = [item_key(row["dataset_id"], row["item_id"]) for row in rows]
    if len(keys) != 60 or len(set(keys)) != 60:
        raise _fail(f"the pilot must hold 60 unique anchors, found {len(set(keys))}")
    return keys, str(selection["pilot_content_sha256"])


def phase_base_items(phase: str, protocol: dict[str, Any], main_items: dict[str, v1.EvalItem],
                     anchors: list[str]) -> list[v1.EvalItem]:
    datasets = set(protocol["datasets"])
    in_scope = [item for item in main_items.values() if item.dataset_id in datasets]
    by_key = {item_key(item.dataset_id, item.item_id): item for item in in_scope}
    if phase == "core":
        missing = [key for key in anchors if key not in by_key]
        if missing:
            raise _fail(f"anchors outside the campaign datasets: {missing[:3]}")
        return [by_key[key] for key in anchors]
    if phase == "wide":
        anchor_set = set(anchors)
        return [item for item in in_scope if item_key(item.dataset_id, item.item_id) not in anchor_set]
    raise _fail(f"unknown phase {phase!r}")


def expand_arms(base_items: list[v1.EvalItem], phase: str, protocol: dict[str, Any], templates: dict[str, str],
                evidence_by_arm: dict[str, dict[str, list[dict[str, Any]]]]) -> list[v1.EvalItem]:
    """Item-major expansion: item, then replicate, then arm, so one item's attempts sit together."""
    config = protocol["phases"][phase]
    expanded: list[v1.EvalItem] = []
    for item in base_items:
        key = item_key(item.dataset_id, item.item_id)
        for replicate in range(1, config["replicates"] + 1):
            for arm in config["arms"]:
                provisions = None
                if arm in EVIDENCE_ARMS:
                    provisions = evidence_by_arm.get("O" if arm == "O" else "K", {}).get(key)
                    if provisions is None:
                        continue  # evidence arms exist only where evidence exists
                prompt = build_arm_prompt(item, arm, templates, provisions)
                expanded.append(dataclasses.replace(item, replicate_id=f"{arm}-r{replicate}", prompt=prompt))
    return expanded


def build_manifest(phase: str, *, evidence_by_arm: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
                   pilot_dir: Path | None = None, main_items: dict[str, v1.EvalItem] | None = None,
                   protocol_path: Path = PROTOCOL_PATH,
                   templates_path: Path = TEMPLATES_PATH) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """Return (manifest, rebuilt run-key map). The manifest is self-hashed like the main-v1 one."""
    protocol = load_protocol(protocol_path)
    templates = load_templates(templates_path)
    evidence_by_arm = {arm: dict(mapping) for arm, mapping in (evidence_by_arm or {}).items() if mapping}
    parent = v1.load_manifest(protocol["parent"]["manifest_phase"])
    main_items = main_items or v1.rebuild_items(protocol["parent"]["manifest_phase"])
    anchors, pilot_content = anchor_item_keys(pilot_dir or ROOT / protocol["parent"]["pilot_dir"])
    base_items = phase_base_items(phase, protocol, main_items, anchors)
    base_keys = {item_key(item.dataset_id, item.item_id) for item in base_items}
    for arm, mapping in evidence_by_arm.items():
        if arm not in {"O", "K"}:
            raise _fail(f"evidence is supplied per source arm O or K, not {arm!r}")
        stray = sorted(set(mapping) - base_keys)
        if stray:
            raise _fail(f"evidence for items outside phase {phase}: {stray[:3]}")
    items = expand_arms(base_items, phase, protocol, templates, evidence_by_arm)
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate arm run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": 1,
        "phase": phase,
        "parent_protocol_id": parent["protocol_id"],
        "parent_manifest_sha256": parent["manifest_sha256"],
        "campaign_protocol_sha256": v1.sha256_file(protocol_path),
        "prompt_templates_sha256": v1.sha256_file(templates_path),
        "pilot_content_sha256": pilot_content,
        "evidence_sha256": {arm: evidence_digest(mapping) for arm, mapping in sorted(evidence_by_arm.items())},
        "n": len(items),
        "item_count": len(base_items),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in items).items())),
        "arm_counts": dict(sorted(Counter(arm_of_replicate(item.replicate_id) for item in items).items())),
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def verify_manifest_rows(manifest: dict[str, Any], rebuilt: dict[str, v1.EvalItem]) -> list[v1.EvalItem]:
    """Strict equality of every row with the rebuilt item (prompt, input and gold hashes)."""
    claimed = manifest.get("manifest_sha256")
    unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if claimed != v1.sha256_bytes(v1.canonical_json(unhashed)):
        raise _fail("campaign manifest hash mismatch")
    return [v1.item_from_manifest_row(row, rebuilt) for row in manifest["items"]]


def save_manifest(phase: str, manifest: dict[str, Any], *, overwrite: bool = False) -> Path:
    path = DATA_DIR / f"{phase}_v1.json"
    if path.exists() and not overwrite:
        raise _fail(f"{path} already exists; refusing to replace a frozen manifest")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_bytes(v1.canonical_json(manifest) + b"\n")
    temporary.replace(path)
    return path


# ---------------------------------------------------------------- scoring

def final_segment(raw: str) -> tuple[str, bool]:
    """Text on the line after the LAST final-answer label, and whether a label exists at all.

    Unlike the frozen extractor this never falls back to the whole response, so a multiple-choice
    answer cannot be read out of the reasoning text by the first-match parser."""
    text = str(raw or "").strip()
    matches = list(_FINAL_LABEL.finditer(text))
    if not matches:
        return "", False
    tail = text[matches[-1].end():].strip()
    return (tail.splitlines()[0].strip() if tail else ""), True


def score_arm_rows(manifest: dict[str, Any], predictions: dict[str, dict[str, Any]],
                   item_map: dict[str, v1.EvalItem]) -> tuple[list[dict[str, Any]], dict[str, dict[str, dict[str, Any]]]]:
    """Frozen scoring applied per arm; reasoning arms are scored from the final-answer segment.

    Returns (scored rows for all arms, {arm: {dataset_id: summary}}). Arms are never pooled."""
    refs_by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ref in manifest["items"]:
        refs_by_arm[arm_of_replicate(ref["replicate_id"])].append(ref)
    scored_all: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, dict[str, Any]]] = {}
    for arm in ARMS:
        refs = refs_by_arm.get(arm)
        if not refs:
            continue
        flags: dict[str, dict[str, Any]] = {}
        arm_predictions: dict[str, dict[str, Any]] = {}
        for ref in refs:
            key = run_key(ref)
            prediction = predictions.get(key)
            if prediction is None:
                continue
            if arm in REASONING_ARMS and prediction.get("status") == "complete":
                raw = str(prediction.get("raw_response", ""))
                segment, found = final_segment(raw)
                is_mc = item_map[key].task == "multiple_choice"
                flags[key] = {
                    "format_ok": bool(found and segment),
                    "markdown_final_line": None if is_mc else bool(_MARKDOWN.search(segment)),
                    "scoring_source": "final_segment" if is_mc else "raw_last_label",
                }
                prediction = {**prediction, "raw_response": segment if is_mc else raw}
            arm_predictions[key] = prediction
        scored, arm_summaries = score_rows({**manifest, "items": refs}, arm_predictions, item_map)
        for row in scored:
            key = run_key(row)
            flag = flags.get(key, {"format_ok": None, "markdown_final_line": None, "scoring_source": "raw"})
            row.update({"arm": arm, "scoring_response": row["raw_response"],
                        "raw_response": str(predictions[key].get("raw_response", "")), **flag})
        for dataset_id, summary in arm_summaries.items():
            subset = [row for row in scored if row["dataset_id"] == dataset_id]
            summary["arm"] = arm
            if arm in REASONING_ARMS:
                compliant = sum(bool(row["format_ok"]) for row in subset)
                summary.update({
                    "format_ok_n": compliant,
                    "format_compliance_pct": round(100 * compliant / len(subset), 2) if subset else None,
                    "markdown_final_line_n": sum(bool(row["markdown_final_line"]) for row in subset),
                })
            else:
                summary.update({"format_ok_n": None, "format_compliance_pct": None, "markdown_final_line_n": None})
        scored_all.extend(scored)
        summaries[arm] = arm_summaries
    return scored_all, summaries
