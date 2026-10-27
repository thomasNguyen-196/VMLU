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
    from code_benchmark import diagnostic
    from code_benchmark import vi_multimodel as v1
    from code_benchmark.score_vi_multimodel import score_rows
except ImportError:  # executed from code_benchmark/
    import diagnostic
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
RETRIEVED_KEYS = ("dataset_id", "item_id", "provisions", "ranking", "query_sha256", "corpus_sha256",
                  "retrieval_config_sha256", "eligibility")
RANKING_KEYS = ("chunk_id", "score", "text_sha256")
RETRIEVAL_ARMS = frozenset({"K", "KS"})
FORBIDDEN_EVIDENCE_KEYS = frozenset({
    "answer", "gold", "gold_answer", "option", "option_letter", "choice", "rationale", "solution", "explanation",
})
ANSWER_KEY = re.compile(r"(?:đáp án|answer)\s*[:：]\s*[A-Ea-e]\b", re.IGNORECASE)
_LEAK = re.compile(ANSWER_KEY.pattern + r"|lời giải|giải thích", re.IGNORECASE)
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


def validate_supplement(supplement_id: str, supplement: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """A supplement re-runs arms of a registered phase under further replicate numbers. It adds no arm, no
    evidence and no item, and its replicate numbers never collide with those the phase registered."""
    missing = [key for key in ("base_phase", "arms", "first_replicate", "replicates") if key not in supplement]
    if missing:
        raise _fail(f"supplement {supplement_id!r} lacks {missing}")
    phase = supplement["base_phase"]
    if phase not in protocol["phases"]:
        raise _fail(f"supplement {supplement_id!r} names an unknown base phase {phase!r}")
    config = protocol["phases"][phase]
    arms = supplement["arms"]
    if not isinstance(arms, list) or not arms or not set(arms) <= set(config["arms"]):
        raise _fail(f"supplement {supplement_id!r} arms must be a non-empty subset of the arms of phase {phase}")
    if set(arms) & EVIDENCE_ARMS:
        raise _fail(f"supplement {supplement_id!r} cannot carry evidence arms")
    first, count = supplement["first_replicate"], supplement["replicates"]
    if not (isinstance(first, int) and isinstance(count, int) and count >= 1 and first > config["replicates"]):
        raise _fail(f"supplement {supplement_id!r} replicate numbers must start after the {config['replicates']} "
                    f"replicate(s) registered for phase {phase}")
    return supplement


def load_supplement(registration: dict[str, Any], supplement_id: str,
                    protocol: dict[str, Any] | None = None) -> dict[str, Any]:
    supplements = registration.get("supplements") or {}
    if supplement_id not in supplements:
        raise _fail(f"unknown supplement {supplement_id!r}; registered: {sorted(supplements)}")
    supplement = validate_supplement(supplement_id, supplements[supplement_id], protocol or load_protocol())
    return {**supplement, "supplement_id": supplement_id}


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


def validate_provisions(provisions: Any, where: str, *, verbatim_source: bool = False) -> list[dict[str, Any]]:
    """Shape, text hash and leakage of evidence provisions. Text copied verbatim from a corpus article is
    checked for answer-key lines only, since statutes legitimately say "giải thích" ("Giải thích từ ngữ")."""
    leak = ANSWER_KEY if verbatim_source else _LEAK
    if not isinstance(provisions, list) or not provisions:
        raise _fail(f"{where}: provisions must be a non-empty list")
    for index, provision in enumerate(provisions, 1):
        if not isinstance(provision, dict) or set(provision) != set(PROVISION_KEYS):
            raise _fail(f"{where}: provision {index} must have exactly the keys {list(PROVISION_KEYS)}")
        if not all(isinstance(provision[key], str) and provision[key].strip() for key in PROVISION_KEYS):
            raise _fail(f"{where}: provision {index} has an empty field")
        if v1.sha256_bytes(provision["text"].encode("utf-8")) != provision["text_sha256"]:
            raise _fail(f"{where}: provision {index} text hash mismatch")
        if leak.search(provision["text"]):
            raise _fail(f"{where}: provision {index} looks like an answer or an explanation")
    return provisions


def _evidence_rows(path: Path, label: str) -> list[Any]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read {label} {path}: {exc}") from exc


def _evidence_key(row: Any, where: str, keys: tuple[str, ...], protocol: dict[str, Any],
                  main_items: dict[str, v1.EvalItem], seen: dict[str, Any]) -> str:
    """Checks every evidence record shares: exact keys, no answer-bearing key, an eligible frozen item."""
    if not isinstance(row, dict):
        raise _fail(f"{where}: record must be an object")
    leaked = FORBIDDEN_EVIDENCE_KEYS & set(row)
    if leaked:
        raise _fail(f"{where}: record carries forbidden answer-bearing keys {sorted(leaked)}")
    if set(row) != set(keys):
        raise _fail(f"{where}: record must have exactly the keys {list(keys)}")
    key = item_key(row["dataset_id"], row["item_id"])
    if key in seen:
        raise _fail(f"{where}: duplicate evidence for {key}")
    if row["dataset_id"] not in protocol["evidence"]["eligible_datasets"]:
        raise _fail(f"{where}: {key} is not an evidence-eligible dataset")
    if f"{key}:{MAIN_REPLICATE}" not in main_items:
        raise _fail(f"{where}: {key} is not a frozen main-v1 item")
    required = protocol["evidence"]["required_input_evidence_sufficiency"]
    if row["eligibility"] != {"input_evidence_sufficiency": required}:
        raise _fail(f"{where}: eligibility must state input_evidence_sufficiency={required}")
    return key


def load_oracle_evidence(path: Path, protocol: dict[str, Any],
                         main_items: dict[str, v1.EvalItem]) -> dict[str, list[dict[str, Any]]]:
    """Return {dataset:item -> provisions}. Fails closed on leakage, ineligibility or hash drift."""
    result: dict[str, list[dict[str, Any]]] = {}
    for number, row in enumerate(_evidence_rows(path, "oracle evidence"), 1):
        where = f"{path.name}:{number}"
        key = _evidence_key(row, where, ORACLE_KEYS, protocol, main_items, result)
        if not isinstance(row["reviewer_id"], str) or not row["reviewer_id"].strip():
            raise _fail(f"{where}: reviewer_id is empty")
        if not isinstance(row["review_export_sha256"], str) or not _SHA256_HEX.match(row["review_export_sha256"]):
            raise _fail(f"{where}: review_export_sha256 is not a SHA-256 hex digest")
        result[key] = validate_provisions(row["provisions"], where)
    return result


def load_retrieved_evidence(path: Path, protocol: dict[str, Any], main_items: dict[str, v1.EvalItem]
                            ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    """Return ({dataset:item -> provisions}, {dataset:item -> retrieval trace}) for arms K and KS.

    Every provision must be the ranked corpus chunk whose hash it carries, scores must not increase down the
    ranking, and all records must come from one corpus and one retrieval configuration."""
    result: dict[str, list[dict[str, Any]]] = {}
    traces: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(_evidence_rows(path, "retrieved evidence"), 1):
        where = f"{path.name}:{number}"
        key = _evidence_key(row, where, RETRIEVED_KEYS, protocol, main_items, result)
        for field in ("query_sha256", "corpus_sha256", "retrieval_config_sha256"):
            if not isinstance(row[field], str) or not _SHA256_HEX.match(row[field]):
                raise _fail(f"{where}: {field} is not a SHA-256 hex digest")
        provisions = validate_provisions(row["provisions"], where, verbatim_source=True)
        ranking = row["ranking"]
        if (not isinstance(ranking, list) or len(ranking) != len(provisions)
                or any(not isinstance(entry, dict) or set(entry) != set(RANKING_KEYS) for entry in ranking)):
            raise _fail(f"{where}: ranking must list {list(RANKING_KEYS)} for each provision")
        if any(entry["text_sha256"] != provision["text_sha256"]
               for entry, provision in zip(ranking, provisions, strict=True)):
            raise _fail(f"{where}: a provision differs from the ranked chunk it stands for")
        scores = [entry["score"] for entry in ranking]
        if (any(isinstance(s, bool) or not isinstance(s, (int, float)) for s in scores)
                or scores != sorted(scores, reverse=True)):
            raise _fail(f"{where}: ranking scores must be numbers in non-increasing order")
        result[key] = provisions
        traces[key] = {field: row[field] for field in ("corpus_sha256", "retrieval_config_sha256", "query_sha256")}
        traces[key]["ranking"] = ranking
    sources = {(trace["corpus_sha256"], trace["retrieval_config_sha256"]) for trace in traces.values()}
    if len(sources) > 1:
        raise _fail(f"{path.name}: records come from {len(sources)} corpus/configuration pairs, not one")
    return result, traces


# A reviewer's note at the end of a drafted locator, e.g. "(kèm câu dẫn của khoản)"; never part of the prompt.
_LOCATOR_NOTE = re.compile(r"\s*\([^()]*\)\s*$")


def oracle_records(review_rows: list[dict[str, Any]], provisions: list[dict[str, Any]],
                   protocol: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Oracle evidence records from one imported review and the drafted provisions (design Decision 11).

    An anchor of the evidence-eligible dataset gets a record when its audited input evidence has the required
    sufficiency and its gold is valid; the dataset's other anchors come back as {item key: reason}. Fails closed
    on labels from more than one review export, a provisional or unattached provision, or an evidence anchor
    without a provision."""
    eligible = protocol["evidence"]["eligible_datasets"]
    required = protocol["evidence"]["required_input_evidence_sufficiency"]
    if len(eligible) != 1:
        raise _fail("drafted provisions carry no dataset id, so exactly one evidence-eligible dataset is supported")
    dataset_id = eligible[0]
    sources = {(row.get("annotator_id"), row.get("review_source_sha256")) for row in review_rows}
    if len(sources) != 1:
        raise _fail(f"labels must come from exactly one imported review export, found {len(sources)}")
    (reviewer_id, export_sha256), = sources
    reasons: dict[str, str | None] = {}
    for row in review_rows:
        row_dataset, rest = str(row["observation_key"]).split("|", 1)[-1].split(":", 1)
        item_id = rest.rsplit(":", 1)[0]
        if row_dataset != dataset_id:
            continue
        if item_id in reasons:
            raise _fail(f"two label rows for {item_key(dataset_id, item_id)}")
        if row["input_evidence_sufficiency"] != required:
            reasons[item_id] = f"input_evidence_sufficiency={row['input_evidence_sufficiency']}"
        elif row["gold_validity"] != "valid":
            reasons[item_id] = f"gold_validity={row['gold_validity']}"
        else:
            reasons[item_id] = None
    drafted: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for provision in provisions:
        if provision.get("item_id") not in reasons:
            raise _fail(f"provision for {provision.get('item_id')!r}, which is not an anchor of {dataset_id}")
        drafted[provision["item_id"]].append(provision)
    records = []
    for item_id in sorted(key for key, reason in reasons.items() if reason is None):
        if not drafted[item_id]:
            raise _fail(f"evidence anchor {item_id} has no drafted provision")
        if any(p.get("provisional") for p in drafted[item_id]):
            raise _fail(f"evidence anchor {item_id} has a provisional provision; verify it against the source first")
        cleaned = [{key: _LOCATOR_NOTE.sub("", p[key]) if key == "locator" else p[key] for key in PROVISION_KEYS}
                   for p in drafted[item_id]]
        records.append({"dataset_id": dataset_id, "item_id": item_id,
                        "provisions": validate_provisions(cleaned, item_key(dataset_id, item_id)),
                        "reviewer_id": reviewer_id, "review_export_sha256": export_sha256,
                        "eligibility": {"input_evidence_sufficiency": required}})
    excluded = {item_key(dataset_id, item_id): reason for item_id, reason in sorted(reasons.items()) if reason}
    return records, excluded


# ---------------------------------------------------------------- anchor diagnosis (design Decision 12)

ANCHOR_DIAGNOSIS_KEYS = ("dataset_id", "item_id", "judgment_source", "reviewers", "semantic_correctness",
                         "gold_validity", "input_evidence_sufficiency", "corpus_evidence_availability",
                         "diagnostic_outcome", "observed_issues", "diagnostic_labels", "hypothesis_status")
JUDGMENT_FIELDS = ("semantic_correctness", "gold_validity", "input_evidence_sufficiency",
                   "corpus_evidence_availability", "diagnostic_outcome")
JUDGMENT_SETS = ("observed_issues", "diagnostic_labels")


def judgment_vocabulary() -> dict[str, frozenset[str]]:
    """Allowed values of every final-judgment field, from the frozen review schema and the audit taxonomy."""
    enums = _read_json(diagnostic.REVIEW_SCHEMA_PATH, "review schema")["enums"]
    vocabulary = {field: frozenset(enums[field]) for field in JUDGMENT_FIELDS}
    vocabulary["observed_issues"] = frozenset(diagnostic.OBSERVED_ISSUES)
    vocabulary["diagnostic_labels"] = frozenset(diagnostic.DIAGNOSTIC_LABELS)
    return vocabulary


def anchor_of_observation(observation_key: str) -> str:
    """`source|dataset:item:replicate` -> `dataset:item`."""
    return str(observation_key).split("|", 1)[-1].rsplit(":", 1)[0]


def final_judgment(rationale: str, vocabulary: dict[str, frozenset[str]]) -> dict[str, Any]:
    """The final labels an adjudication records as `FINAL field=value | ... || reason`. Every judgment field
    appears exactly once; the two set fields are `;`-separated and may be empty."""
    head, separator, _ = str(rationale).partition("||")
    if not head.startswith("FINAL ") or not separator:
        raise _fail("adjudication rationale lacks a `FINAL field=value | ... || reason` block")
    judgment: dict[str, Any] = {}
    for part in head[len("FINAL "):].split("|"):
        name, equals, value = part.strip().partition("=")
        if not equals or name not in vocabulary or name in judgment:
            raise _fail(f"adjudication field {name!r} is unknown, malformed or repeated")
        value = value.strip()
        if name in JUDGMENT_SETS:
            values = [entry.strip() for entry in value.split(";") if entry.strip()]
            if len(values) != len(set(values)) or not set(values) <= vocabulary[name]:
                raise _fail(f"adjudication {name}={value!r} repeats a value or names one outside the vocabulary")
            judgment[name] = sorted(values)
        elif value in vocabulary[name]:
            judgment[name] = value
        else:
            raise _fail(f"adjudication {name}={value!r} is outside the vocabulary")
    missing = sorted(set(vocabulary) - set(judgment))
    if missing:
        raise _fail(f"adjudication lacks the final {missing}")
    return judgment


def _review_judgment(row: dict[str, Any]) -> dict[str, Any]:
    return {**{field: row[field] for field in JUDGMENT_FIELDS},
            **{field: sorted(row[field]) for field in JUDGMENT_SETS}}


def anchor_diagnosis(pilot_dir: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """The final audit judgment of every anchor (design Decision 12), in pilot order: the judgment every imported
    review agrees on, or the FINAL block of the anchor's latest resolved adjudication. Fails closed on an anchor
    without a review, on reviews that disagree without a resolved adjudication and on an unreadable final block.
    Returns the records and the SHA-256 of each input file."""
    anchors, _ = anchor_item_keys(pilot_dir)
    vocabulary = judgment_vocabulary()
    inputs: dict[str, str] = {}
    reviews: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted((pilot_dir / "reviews").glob("*.jsonl")):
        inputs[f"reviews/{path.name}"] = v1.sha256_file(path)
        for row in _evidence_rows(path, "imported review"):
            if row.get("review_status"):
                reviews[anchor_of_observation(row["observation_key"])].append(row)
    adjudicated: dict[str, dict[str, Any]] = {}
    path = pilot_dir / "adjudications.jsonl"
    if path.is_file():
        inputs["adjudications.jsonl"] = v1.sha256_file(path)
        adjudicated = {anchor_of_observation(row["observation_key"]): row
                       for row in _evidence_rows(path, "adjudications")}
    stray = sorted(set(reviews) - set(anchors))
    if stray:
        raise _fail(f"reviews for items outside the pilot anchors: {stray[:3]}")
    records = []
    for key in anchors:
        rows = reviews.get(key)
        if not rows:
            raise _fail(f"anchor {key} has no imported review")
        views = [_review_judgment(row) for row in rows]
        decision = adjudicated.get(key, {})
        if decision.get("decision") == "resolved":
            judgment, source = final_judgment(decision["rationale"], vocabulary), "adjudicated"
        elif all(view == views[0] for view in views):
            judgment, source = views[0], "agreed" if len(rows) > 1 else "single_review"
        else:
            raise _fail(f"the reviews of {key} disagree and no resolved adjudication records the final judgment")
        primary = next((row for row in rows if row.get("review_scope") == "primary-60"), rows[0])
        status = {support["label"]: support["status"] for support in primary.get("diagnostic_support", [])}
        dataset_id, item_id = key.split(":", 1)
        records.append({"dataset_id": dataset_id, "item_id": item_id, "judgment_source": source,
                        "reviewers": sorted({str(row["annotator_id"]) for row in rows}), **judgment,
                        "hypothesis_status": {label: status.get(label, "hypothesis")
                                              for label in judgment["diagnostic_labels"]}})
    return records, inputs


def load_anchor_diagnosis(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    """{dataset:item: final judgment} and the SHA-256 of the file (the value the core registration records)."""
    vocabulary = judgment_vocabulary()
    mapping: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(_evidence_rows(path, "anchor diagnosis"), 1):
        where = f"{path.name}:{number}"
        if not isinstance(row, dict) or set(row) != set(ANCHOR_DIAGNOSIS_KEYS):
            raise _fail(f"{where}: record must have exactly the keys {list(ANCHOR_DIAGNOSIS_KEYS)}")
        key = item_key(row["dataset_id"], row["item_id"])
        if key in mapping:
            raise _fail(f"{where}: duplicate diagnosis for {key}")
        if (any(row[field] not in vocabulary[field] for field in JUDGMENT_FIELDS)
                or any(not isinstance(row[field], list) or not set(row[field]) <= vocabulary[field]
                       for field in JUDGMENT_SETS)
                or not isinstance(row["hypothesis_status"], dict)
                or set(row["hypothesis_status"]) != set(row["diagnostic_labels"])
                or not set(row["hypothesis_status"].values()) <= diagnostic.ATTRIBUTION_STATUSES):
            raise _fail(f"{where}: {key} has a value outside the audit vocabulary")
        mapping[key] = row
    return mapping, v1.sha256_file(path)


def reported_tokens(row: dict[str, Any]) -> int | None:
    """Total tokens the endpoint reported for an attempt; None when it reported none (unknown, never zero)."""
    total = row.get("total_tokens")
    if isinstance(total, int):
        return total
    prompt, completion = row.get("prompt_tokens"), row.get("completion_tokens")
    if isinstance(prompt, int) and isinstance(completion, int):
        return prompt + completion
    return None


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
                evidence_by_arm: dict[str, dict[str, list[dict[str, Any]]]], *, arms: list[str] | None = None,
                first_replicate: int = 1, replicates: int | None = None) -> list[v1.EvalItem]:
    """Item-major expansion: item, then replicate, then arm, so one item's attempts sit together.
    The keyword options select a supplement; without them the registered phase design is expanded."""
    config = protocol["phases"][phase]
    arm_list = config["arms"] if arms is None else arms
    count = config["replicates"] if replicates is None else replicates
    expanded: list[v1.EvalItem] = []
    for item in base_items:
        key = item_key(item.dataset_id, item.item_id)
        for replicate in range(first_replicate, first_replicate + count):
            for arm in arm_list:
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
                   protocol_path: Path = PROTOCOL_PATH, templates_path: Path = TEMPLATES_PATH,
                   supplement: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """Return (manifest, rebuilt run-key map). The manifest is self-hashed like the main-v1 one.
    With `supplement` (from load_supplement) the items are the phase's items under the supplement's arms and
    replicate numbers; the manifest then also records the supplement, and without it no key is added."""
    protocol = load_protocol(protocol_path)
    templates = load_templates(templates_path)
    if supplement is not None:
        validate_supplement(str(supplement.get("supplement_id")), supplement, protocol)
        if supplement["base_phase"] != phase:
            raise _fail(f"supplement {supplement['supplement_id']!r} belongs to phase {supplement['base_phase']}, not {phase}")
        if evidence_by_arm:
            raise _fail("a supplement takes no evidence")
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
    if {"O", "K"} <= set(evidence_by_arm) and set(evidence_by_arm["O"]) != set(evidence_by_arm["K"]):
        differ = sorted(set(evidence_by_arm["O"]) ^ set(evidence_by_arm["K"]))
        raise _fail(f"oracle and retrieved evidence must cover the same items; they differ on {differ[:3]}")
    if supplement is None:
        items = expand_arms(base_items, phase, protocol, templates, evidence_by_arm)
    else:
        items = expand_arms(base_items, phase, protocol, templates, {}, arms=list(supplement["arms"]),
                            first_replicate=supplement["first_replicate"], replicates=supplement["replicates"])
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
    if supplement is not None:
        manifest["supplement_id"] = supplement["supplement_id"]
        manifest["supplement_design"] = {key: supplement[key] for key in
                                         ("base_phase", "arms", "first_replicate", "replicates")}
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def verify_manifest_rows(manifest: dict[str, Any], rebuilt: dict[str, v1.EvalItem]) -> list[v1.EvalItem]:
    """Strict equality of every row with the rebuilt item (prompt, input and gold hashes)."""
    claimed = manifest.get("manifest_sha256")
    unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if claimed != v1.sha256_bytes(v1.canonical_json(unhashed)):
        raise _fail("campaign manifest hash mismatch")
    return [v1.item_from_manifest_row(row, rebuilt) for row in manifest["items"]]


def save_manifest(name: str, manifest: dict[str, Any], *, overwrite: bool = False) -> Path:
    """Freeze a manifest as data/diagnostic_prospective_v1/<name>_v1.json (name = a phase or a supplement id)."""
    path = DATA_DIR / f"{name}_v1.json"
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
