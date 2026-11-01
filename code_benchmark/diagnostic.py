"""Offline VMLU diagnostic protocol, artifact ledger and human audit tools.

This module reads frozen V1 benchmark artifacts; it never calls a model or edits
benchmark inputs. Run commands from the repository root, for example:
  .venv/bin/python code_benchmark/diagnostic.py readiness
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "diagnostic_v1"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
REGISTRY_PATH = DATA_DIR / "source_registry.json"
TAXONOMY_PATH = DATA_DIR / "taxonomy.json"
REVIEW_SCHEMA_PATH = DATA_DIR / "review_schema.json"
# The prospective controls are resolved in their own file, bound to the protocol by its SHA-256, so that
# protocol.json keeps its bytes and the pilot, the review page and the frozen wide manifests keep theirs.
CONTROLS_PATH = DATA_DIR / "readiness_controls_v1.json"
CONTROLS_KEYS = {"controls_id", "protocol_sha256", "registered_on", "note", "readiness_controls",
                 "future_experiment_contract"}
EXPERIMENT_CONTROLS = ("campaign_controls", "split_manifest", "corpus_version", "budget_policy",
                       "replicate_pairing_and_stability", "verification_policy")
OUTPUT_ROOT = ROOT / "all_res" / "diagnostic_v1"
DIAGNOSTIC_LABELS = {'reading_representation_gap', 'retrieval_gap', 'reasoning_gap', 'instruction_gap', 'parametric_knowledge_error', 'harness_gap', 'parser_gap', 'parametric_knowledge_gap', 'measurement_gap', 'generator_evidence_use_gap', 'context_assembly_gap', 'external_evidence_gap', 'run_instability'}
OBSERVED_ISSUES = {'output_truncation', 'retrieval_miss', 'wrong_entity_relation', 'parser_mismatch', 'answer_mismatch', 'other', 'calculation_error', 'instruction_violation', 'gold_metric_issue', 'factual_conflict', 'run_variation', 'context_assembly_issue', 'missing_input_evidence'}
AUDIT_EVIDENCE_KINDS = {"input_span", "source_comparison", "derivation", "raw_output", "parser_replay", "unavailable"}
INPUT_EVIDENCE_SUFFICIENCY = {"sufficient", "insufficient", "unassessable", "not_applicable"}
CORPUS_AVAILABILITY = {"not_assessed", "present", "absent", "not_applicable"}
ATTRIBUTION_STATUSES = {"hypothesis", "contrast_supported"}
DIAGNOSTIC_OUTCOMES = {"no_observed_issue", "issue_observed", "unresolved"}
REVIEW_SCHEMA_VERSION = "diagnostic-review-v4"
RUBRIC_VERSION = "diagnostic-rubric-v3"
ANNOTATION_REVISION = 4
SUGGESTION_SCHEMA_VERSION = "diagnostic-assistant-suggestion-v2"
HUMAN_ONLY_ATTESTATION = "I attest that these are my independent human judgments."
AI_ASSISTED_ATTESTATION = "I reviewed the AI suggestions and affirm my final human judgments."
BLIND_ATTESTATION = "I have not seen AI suggestions or other reviewer judgments for this pilot."
REVIEW_ASSISTANCE_MODES = {"human_only", "ai_assisted"}
ACTION_LABELS = {"direct", "reasoning", "retrieval", "retrieval_reasoning", "unknown"}
EXPECTED_ANCHOR_COUNTS = {
    "vi-multimodel-v1-legal-mc-146": 146,
    "vi-multimodel-v1-legal-nli-150": 150,
    "vi-multimodel-v1-vi-squad-200": 200,
    "vi-multimodel-v1-vi-drop-200": 200,
    "vi-multimodel-v1-bidlqa-test": 603,
    "vi-multimodel-v1-vmlu-valid": 744,
}
CAMPAIGN_ADAPTER = "campaign-arms-v1"  # prospective-campaign runs, built by diagnostic_campaign_ledger.py
CAMPAIGN_FAMILY = "diagnostic-prospective-v1"
SOURCE_ADAPTERS = {"v1-main-v1", "v1-main-subset-v1", CAMPAIGN_ADAPTER}
SOURCE_FAMILIES = {"vi-multimodel-v1-main", "qwen-mc72", CAMPAIGN_FAMILY}
SOURCE_METADATA_ALLOWLIST = {
    "status", "model_id", "model_ref", "profile_id", "measurement_card_id",
    "measurement_card_hash", "protocol_id", "protocol_sha256", "manifest_sha256",
    "config_sha256", "transport", "omp_version", "omp_mode", "omp_tools",
    "omp_thinking", "temperature_effective", "temperature_requested",
    "seed_sent", "seed_policy", "workers", "max_tokens_mc", "max_tokens_reading",
    "phase",
}
INPUT_SCORE_FIELDS = {
    "prediction", "gold_answer", "prompt_sha256", "finish_reason", "source_dataset",
    "stratum", "passage_id", "correct", "em", "token_f1", "legacy_raw_em",
    "legacy_raw_char_f1", "legacy_final_em", "legacy_final_char_f1",
    "prompt_tokens", "cached_prompt_tokens", "completion_tokens", "reasoning_tokens",
    "total_tokens", "latency_s", "response_model_id", "system_fingerprint", "service_tier",
}
REVIEW_IMMUTABLE_COLUMNS = [
    "observation_key", "item_key", "dataset_id", "item_id", "replicate_id",
    "source_run_id", "source_manifest_sha256", "prompt_sha256", "task_mode",
    "question", "rendered_input", "raw_response", "prediction", "source_gold",
    "source_metrics", "finish_reason", "passage_group", "selection_reason", "exposure",
    "protocol_sha256", "rubric_version", "packet_sha256",
]
REVIEW_JUDGMENT_COLUMNS = ['annotator_id', 'review_scope', 'review_assistance_mode', 'semantic_correctness', 'gold_validity', 'input_evidence_sufficiency', 'corpus_evidence_availability', 'corpus_evidence_reference', 'diagnostic_outcome', 'observed_issues', 'audit_evidence_kind', 'evidence_reference', 'diagnostic_labels', 'diagnostic_support', 'rationale', 'reviewer_attestation', 'blind_review_attestation', 'review_status']
REVIEW_COLUMNS = REVIEW_IMMUTABLE_COLUMNS + REVIEW_JUDGMENT_COLUMNS
SCHEMA_VERSION = 1


class DiagnosticError(SystemExit):
    """A user-actionable validation or provenance error."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise DiagnosticError(f"Error: required source file is missing: {path}")
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagnosticError(f"Error: cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DiagnosticError(f"Error: expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    lines: dict[str, int] = {}
    try:
        with path.open(encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                row = json.loads(raw)
                if not isinstance(row, dict):
                    raise DiagnosticError(f"Error: expected object at {path}:{line_no}")
                rows.append(row)
                key = _identity(row)
                if key in lines:
                    raise DiagnosticError(f"Error: duplicate row identity {key} in {path}:{line_no}")
                lines[key] = line_no
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagnosticError(f"Error: cannot read JSONL {path}: {exc}") from exc
    return rows, lines


def _identity(row: dict[str, Any]) -> str:
    required = ("dataset_id", "item_id", "replicate_id")
    if any(row.get(name) is None or str(row[name]) == "" for name in required):
        raise DiagnosticError(f"Error: row missing identity fields: {required}")
    return f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"


def _file_map_hashes(paths: list[Path]) -> dict[str, str]:
    return {str(path.relative_to(ROOT)): _sha256_file(path) for path in sorted(paths)}


def load_protocol(path: Path = PROTOCOL_PATH) -> tuple[dict[str, Any], str]:
    protocol = _read_json(path)
    if protocol.get("protocol_id") != "vmlu-diagnostic-v1" or protocol.get("protocol_version") != 1:
        raise DiagnosticError("Error: unsupported diagnostic protocol id/version")
    if protocol.get("schema_version") != SCHEMA_VERSION or protocol.get("rubric_version") != RUBRIC_VERSION or protocol.get("annotation_revision") != ANNOTATION_REVISION:
        raise DiagnosticError("Error: unsupported diagnostic schema/rubric version")
    assistance = protocol.get("assistant_preannotation", {})
    if assistance.get("schema_version") != SUGGESTION_SCHEMA_VERSION or assistance.get("suggestions_are_not_reviews") is not True:
        raise DiagnosticError("Error: unsupported assistant suggestion provenance policy")
    if set(protocol.get("diagnostic_labels", [])) != DIAGNOSTIC_LABELS:
        raise DiagnosticError("Error: protocol diagnostic labels do not match the versioned taxonomy contract")
    if set(protocol.get("diagnostic_outcomes", [])) != DIAGNOSTIC_OUTCOMES:
        raise DiagnosticError("Error: protocol diagnostic outcomes do not match annotation revision 4")
    for field, expected in (("observed_issues", OBSERVED_ISSUES), ("attribution_statuses", ATTRIBUTION_STATUSES),
                            ("audit_evidence_kinds", AUDIT_EVIDENCE_KINDS), ("input_evidence_sufficiency", INPUT_EVIDENCE_SUFFICIENCY),
                            ("corpus_evidence_availability", CORPUS_AVAILABILITY)):
        if set(protocol.get(field, [])) != expected:
            raise DiagnosticError(f"Error: protocol {field} does not match revision-4 contract")
    if not set(protocol.get("action_labels", [])) == ACTION_LABELS:
        raise DiagnosticError("Error: protocol action labels do not match the supported contract")
    arms = protocol.get("future_arms", {})
    if not {"B", "S", "K", "KS", "oracle_evidence", "harness_contrast"} <= set(arms):
        raise DiagnosticError("Error: protocol omits one or more declared future arms")
    pilot = protocol.get("pilot", {})
    if sum(pilot.get("dataset_counts", {}).values()) != 60 or pilot.get("second_reviewer_count") != 15:
        raise DiagnosticError("Error: pilot quotas must total 60 with a 15-item second-review subset")
    taxonomy_path = path.parent / protocol.get("taxonomy_file", "")
    taxonomy = _read_json(taxonomy_path)
    if taxonomy.get("version") != protocol["rubric_version"] or {row.get("id") for row in taxonomy.get("labels", [])} != DIAGNOSTIC_LABELS:
        raise DiagnosticError("Error: taxonomy file and protocol rubric version/labels differ")
    review_schema = _read_json(path.parent / protocol.get("review_schema", ""))
    if review_schema.get("version") != REVIEW_SCHEMA_VERSION or review_schema.get("empty_means") != "unreviewed_row":
        raise DiagnosticError("Error: unsupported diagnostic review schema")
    if review_schema.get("judgment_columns") != REVIEW_JUDGMENT_COLUMNS or review_schema.get("immutable_source_columns") != REVIEW_IMMUTABLE_COLUMNS:
        raise DiagnosticError("Error: diagnostic review schema column drift")
    if set(review_schema.get("enums", {}).get("diagnostic_outcome", [])) != DIAGNOSTIC_OUTCOMES:
        raise DiagnosticError("Error: diagnostic review outcome enum drift")
    if set(review_schema.get("enums", {}).get("review_assistance_mode", [])) != REVIEW_ASSISTANCE_MODES:
        raise DiagnosticError("Error: diagnostic review assistance enum drift")
    if set(review_schema.get("enums", {}).get("reviewer_attestation", [])) != {HUMAN_ONLY_ATTESTATION, AI_ASSISTED_ATTESTATION}:
        raise DiagnosticError("Error: diagnostic review attestation enum drift")
    return protocol, _sha256_file(path)


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    value = _read_json(path)
    if value.get("version") != 1 or not isinstance(value.get("sources"), list):
        raise DiagnosticError("Error: unsupported diagnostic source registry")
    sources = value["sources"]
    by_id = {str(source.get("source_run_id")): source for source in sources}
    if len(by_id) != len(sources) or "None" in by_id:
        raise DiagnosticError("Error: source registry has missing or duplicate source_run_id")
    for source in sources:
        if source.get("adapter") not in SOURCE_ADAPTERS:
            raise DiagnosticError(f"Error: unsupported source adapter for {source.get('source_run_id')}")
        if source.get("family") not in SOURCE_FAMILIES:
            raise DiagnosticError(f"Error: unsupported source family for {source.get('source_run_id')}")
        if not source.get("datasets") or len(source["datasets"]) != len(set(source["datasets"])):
            raise DiagnosticError(f"Error: invalid dataset allowlist for {source.get('source_run_id')}")
        if (source["adapter"] == CAMPAIGN_ADAPTER) != (source["family"] == CAMPAIGN_FAMILY):
            raise DiagnosticError(f"Error: {source.get('source_run_id')}: adapter {CAMPAIGN_ADAPTER} goes with family {CAMPAIGN_FAMILY} only")
        if source["adapter"] == CAMPAIGN_ADAPTER:
            evidence = source.get("evidence") or {}
            if (source.get("phase") not in {"wide", "core"} or "supplement_id" not in source
                    or not source.get("parent_manifest_path") or not source.get("expected_parent_manifest_sha256")
                    or not isinstance(evidence, dict) or not set(evidence) <= {"O", "K"}
                    or not all(isinstance(path, str) and path for path in evidence.values())):
                raise DiagnosticError(f"Error: {source.get('source_run_id')}: a campaign source needs phase, supplement_id, "
                                      "the parent manifest and its hash, and evidence paths for O or K only")
    return by_id


def _source_paths(source: dict[str, Any]) -> dict[str, Path]:
    return {
        "run": ROOT / source["run_dir"] / "run.json",
        "predictions": ROOT / source["run_dir"] / "predictions.jsonl",
        "scores": ROOT / source["run_dir"] / "scores.jsonl",
        "summary": ROOT / source["run_dir"] / "summary.json",
        "manifest": ROOT / source["manifest_path"],
    }


def _check_source_hashes(manifest: dict[str, Any], source_id: str) -> dict[str, str]:
    expected = manifest.get("source_sha256")
    if not isinstance(expected, dict):
        raise DiagnosticError(f"Error: {source_id}: manifest has no source hash map")
    actual: dict[str, str] = {}
    for relative, digest in expected.items():
        path = ROOT / relative
        seen = _sha256_file(path)
        if seen != digest:
            raise DiagnosticError(f"Error: {source_id}: preregistered input hash mismatch for {relative}")
        actual[relative] = seen
    return actual


def _check_manifest(manifest: dict[str, Any], source: dict[str, Any]) -> str:
    claimed = manifest.get("manifest_sha256")
    unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    computed = _sha256_bytes(_canonical_json(unhashed))
    if claimed != computed or claimed != source.get("expected_manifest_sha256"):
        raise DiagnosticError(f"Error: {source['source_run_id']}: manifest identity/hash mismatch")
    if manifest.get("protocol_id") != "vi-multimodel-v1" or manifest.get("phase") != "main":
        raise DiagnosticError(f"Error: {source['source_run_id']}: unsupported manifest protocol/phase")
    if manifest.get("n") != source.get("expected_n") or len(manifest.get("items", [])) != source.get("expected_n"):
        raise DiagnosticError(f"Error: {source['source_run_id']}: manifest coverage count mismatch")
    ids = [_identity(row) for row in manifest["items"]]
    if len(ids) != len(set(ids)):
        raise DiagnosticError(f"Error: {source['source_run_id']}: duplicate manifest identities")
    dataset_counts = Counter(str(row["dataset_id"]) for row in manifest["items"])
    declared = {str(k): int(v) for k, v in manifest.get("dataset_counts", {}).items()}
    if dict(dataset_counts) != declared:
        raise DiagnosticError(f"Error: {source['source_run_id']}: manifest dataset coverage mismatch")
    if set(dataset_counts) != set(source["datasets"]):
        raise DiagnosticError(f"Error: {source['source_run_id']}: manifest dataset allowlist mismatch")
    if source["adapter"] == "v1-main-subset-v1":
        if manifest.get("parent_manifest_sha256") != source.get("expected_parent_manifest_sha256"):
            raise DiagnosticError("Error: MC-72 parent-manifest identity mismatch")
        parent_path = ROOT / source["parent_manifest_path"]
        parent = _read_json(parent_path)
        parent_claimed = parent.get("manifest_sha256")
        if _sha256_bytes(_canonical_json({k: v for k, v in parent.items() if k != "manifest_sha256"})) != parent_claimed:
            raise DiagnosticError("Error: parent manifest hash mismatch")
        if parent_claimed != source["expected_parent_manifest_sha256"]:
            raise DiagnosticError("Error: parent manifest differs from declared MC-72 source")
        parent_rows = {_identity(row): row for row in parent["items"]}
        for row in manifest["items"]:
            peer = parent_rows.get(_identity(row))
            if peer is None or peer.get("prompt_sha256") != row.get("prompt_sha256"):
                raise DiagnosticError(f"Error: MC-72 item is not prompt-identical to parent: {_identity(row)}")
    return str(claimed)


def _check_metadata(run: dict[str, Any], summary: dict[str, Any], source: dict[str, Any], manifest_sha: str) -> None:
    if run.get("status") != "complete" or run.get("complete_items") != source["expected_n"]:
        raise DiagnosticError(f"Error: {source['source_run_id']}: source run is not complete")
    if run.get("model_id") != source.get("model_identity"):
        raise DiagnosticError(f"Error: {source['source_run_id']}: model identity mismatch")
    if run.get("measurement_card_id") != source.get("measurement_card_id"):
        raise DiagnosticError(f"Error: {source['source_run_id']}: measurement card mismatch")
    if run.get("manifest_sha256") != manifest_sha or summary.get("manifest_sha256") != manifest_sha:
        raise DiagnosticError(f"Error: {source['source_run_id']}: run/summary manifest identity mismatch")
    if summary.get("model_id") != source["model_identity"]:
        raise DiagnosticError(f"Error: {source['source_run_id']}: summary model identity mismatch")
    if summary.get("protocol_id") != "vi-multimodel-v1":
        raise DiagnosticError(f"Error: {source['source_run_id']}: unsupported summary protocol")
    frozen_protocol = _read_json(ROOT / "data" / "vi_multimodel_protocol_v1.json")
    if frozen_protocol.get("protocol_id") != "vi-multimodel-v1" or frozen_protocol.get("protocol_version") != 1:
        raise DiagnosticError("Error: unsupported frozen V1 source protocol")
    reading_scorer = frozen_protocol.get("scorer_version")
    for dataset in summary.get("datasets", []):
        if dataset.get("dataset_id", "").endswith(("vi-squad-200", "vi-drop-200", "bidlqa-test")):
            if dataset.get("scorer_version") != reading_scorer:
                raise DiagnosticError(f"Error: unsupported reading scorer for {dataset.get('dataset_id')}")


def _summary_map(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    datasets = summary.get("datasets")
    if not isinstance(datasets, list):
        raise DiagnosticError("Error: source summary datasets must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in datasets:
        dataset = str(row.get("dataset_id", ""))
        if not dataset or dataset in result:
            raise DiagnosticError("Error: source summary has missing or duplicate dataset id")
        result[dataset] = row
    return result


def _metric_equal(left: Any, right: Any, *, rounded: bool = False) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return round(float(left), 2) == round(float(right), 2) if rounded else math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-12)
    return left == right


def _line_map(rows: list[dict[str, Any]], path: Path) -> dict[str, int]:
    _, line_map = _read_jsonl(path)
    if len(rows) != len(line_map):
        raise DiagnosticError(f"Error: row count changed while reading {path}")
    return line_map


def _validate_summary_parity(source_id: str, supplied: dict[str, dict[str, Any]], derived: dict[str, dict[str, Any]]) -> list[str]:
    if set(supplied) != set(derived):
        raise DiagnosticError(f"Error: {source_id}: summary dataset set differs from frozen scorer")
    incomplete: list[str] = []
    for dataset, actual in derived.items():
        expected = supplied[dataset]
        if expected.get("status") != "complete":
            incomplete.append(f"source summary marks {dataset} incomplete")
        if expected.get("expected_n") != actual.get("expected_n"):
            raise DiagnosticError(f"Error: {source_id}: expected denominator mismatch for {dataset}")
        if expected.get("completed_n") != actual.get("completed_n"):
            incomplete.append(f"artifact coverage differs from recorded summary for {dataset}")
            continue
        for metric in ("accuracy", "em", "token_f1", "truncated_n", "unparsed_n", "empty_answer_n"):
            if metric in actual and not _metric_equal(expected.get(metric), actual.get(metric), rounded=True):
                raise DiagnosticError(f"Error: {source_id}: {metric} summary parity failure for {dataset}")
        count_metric = "correct" if actual.get("accuracy") is not None else "em_count"
        if count_metric in actual and expected.get(count_metric) != actual.get(count_metric):
            raise DiagnosticError(f"Error: {source_id}: {count_metric} parity failure for {dataset}")
    return incomplete


def _source_annotations(source: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    metadata = {key: run[key] for key in sorted(SOURCE_METADATA_ALLOWLIST) if key in run}
    return {
        "source_run_id": source["source_run_id"],
        "source_family": source["family"],
        "model_identity": source["model_identity"],
        "measurement_card_id": source["measurement_card_id"],
        "adapter": source["adapter"],
        "condition": metadata,
    }


def build_source_ledger(source: dict[str, Any], *, protocol_path: Path = PROTOCOL_PATH) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if source.get("adapter") == CAMPAIGN_ADAPTER:
        try:
            from code_benchmark import diagnostic_campaign_ledger as campaign
        except ImportError:
            import diagnostic_campaign_ledger as campaign
        return campaign.build_source_ledger(source, protocol_path=protocol_path)
    protocol, protocol_sha = load_protocol(protocol_path)
    paths = _source_paths(source)
    for label, path in paths.items():
        if not path.is_file():
            raise DiagnosticError(f"Error: {source['source_run_id']}: missing {label} artifact: {path}")
    manifest = _read_json(paths["manifest"])
    manifest_sha = _check_manifest(manifest, source)
    parent = _read_json(ROOT / source["parent_manifest_path"]) if source.get("parent_manifest_path") else None
    source_hashes = _check_source_hashes(manifest, source["source_run_id"])
    if parent:
        parent_hashes = _check_source_hashes(parent, source["source_run_id"])
        if source_hashes != parent_hashes:
            raise DiagnosticError("Error: MC-72 derived and parent source checksum maps differ")
    actual_inputs = _file_map_hashes(list(paths.values()) + ([ROOT / source["parent_manifest_path"]] if source.get("parent_manifest_path") else []))
    run, summary = _read_json(paths["run"]), _read_json(paths["summary"])
    _check_metadata(run, summary, source, manifest_sha)

    prediction_rows, prediction_lines = _read_jsonl(paths["predictions"])
    score_rows, score_lines = _read_jsonl(paths["scores"])
    manifest_rows = manifest["items"]
    expected_by_key = {_identity(row): row for row in manifest_rows}
    predictions = {_identity(row): row for row in prediction_rows}
    scores = {_identity(row): row for row in score_rows}
    unknown = (set(predictions) | set(scores)) - set(expected_by_key)
    if unknown:
        raise DiagnosticError(f"Error: {source['source_run_id']}: artifact rows outside manifest: {sorted(unknown)[:4]}")

    try:
        from code_benchmark.vi_multimodel import manifest_item, rebuild_items
        from code_benchmark.score_vi_multimodel import score_rows as frozen_score_rows
    except ImportError:
        from vi_multimodel import manifest_item, rebuild_items
        from score_vi_multimodel import score_rows as frozen_score_rows
    items = rebuild_items("main")
    selected_keys = set(expected_by_key)
    missing_items = selected_keys - set(items)
    if missing_items:
        raise DiagnosticError(f"Error: {source['source_run_id']}: cannot rebuild source item {sorted(missing_items)[:3]}")
    for key, ref in expected_by_key.items():
        rebuilt = manifest_item(items[key])
        if rebuilt != ref:
            differing = [field for field in set(rebuilt) | set(ref) if rebuilt.get(field) != ref.get(field)]
            raise DiagnosticError(f"Error: {source['source_run_id']}: frozen item mismatch {key}: {sorted(differing)}")

    prediction_map: dict[str, dict[str, Any]] = {}
    for key, row in predictions.items():
        if key != str(row.get("run_key")):
            raise DiagnosticError(f"Error: {source['source_run_id']}: prediction run_key mismatch {key}")
        prediction_map[key] = row
        ref = expected_by_key[key]
        if row.get("prompt_sha256") != ref.get("prompt_sha256"):
            raise DiagnosticError(f"Error: {source['source_run_id']}: prompt hash mismatch for {key}")
        if row.get("status") == "complete" and not isinstance(row.get("raw_response"), str):
            raise DiagnosticError(f"Error: {source['source_run_id']}: completed row lacks raw response {key}")
    derived_scores, derived_summaries = frozen_score_rows(manifest, prediction_map, items)
    derived_by_key = {_identity(row): row for row in derived_scores}
    for key, row in scores.items():
        if key not in derived_by_key:
            raise DiagnosticError(f"Error: {source['source_run_id']}: supplied score has no completed derived score: {key}")
        derived = derived_by_key[key]
        prediction = predictions.get(key, {})
        if str(row.get("raw_response", "")) != str(prediction.get("raw_response", "")):
            raise DiagnosticError(f"Error: {source['source_run_id']}: response mismatch between prediction/score {key}")
        for field in ("prediction", "gold_answer", "prompt_sha256", "correct", "em", "token_f1", "legacy_raw_em", "legacy_raw_char_f1", "legacy_final_em", "legacy_final_char_f1"):
            if field in derived and not _metric_equal(row.get(field), derived.get(field)):
                raise DiagnosticError(f"Error: {source['source_run_id']}: {field} scorer parity failure for {key}")
        if row.get("prompt_sha256") != expected_by_key[key].get("prompt_sha256"):
            raise DiagnosticError(f"Error: {source['source_run_id']}: score prompt hash mismatch {key}")
    supplied_summary = _summary_map(summary)
    incomplete_reasons = _validate_summary_parity(source["source_run_id"], supplied_summary, derived_summaries)
    if len(scores) != len(derived_scores):
        incomplete_reasons.append(f"scored-row coverage {len(scores)}/{len(derived_scores)} differs from frozen recomputation")

    prediction_line_map = prediction_lines
    score_line_map = score_lines
    run_metadata = _source_annotations(source, run)
    result: list[dict[str, Any]] = []
    per_dataset: dict[str, Counter[str]] = defaultdict(Counter)
    for key, ref in expected_by_key.items():
        request = predictions.get(key)
        scored = scores.get(key)
        derived = derived_by_key.get(key)
        item = items[key]
        complete = bool(request and request.get("status") == "complete" and request.get("finish_reason") not in {"error", "failed", "aborted"})
        finish = str((request or {}).get("finish_reason", ""))
        if not request:
            status = "missing_request"
        elif not complete:
            status = str(request.get("status")) if request.get("status") != "complete" else f"finish_{finish or 'failed'}"
        elif not scored:
            status = "completed_unscored"
        else:
            status = "scored"
        dataset = str(ref["dataset_id"])
        counts = per_dataset[dataset]
        counts[status] += 1
        if finish == "length":
            counts["truncated"] += 1
        metric_fields = {name: (scored or {}).get(name) for name in (
            "correct", "em", "token_f1", "legacy_raw_em", "legacy_raw_char_f1",
            "legacy_final_em", "legacy_final_char_f1",
        ) if name in (scored or {})}
        flags: list[str] = []
        if status != "scored":
            flags.append(status)
        if complete and item.task == "multiple_choice" and not str((scored or {}).get("prediction", "")):
            flags.append("unparsed")
            counts["unparsed"] += 1
        if finish == "length":
            flags.append("truncated")
        if item.task == "multiple_choice" and scored and scored.get("correct") == 0:
            flags.append("incorrect_frozen_score")
        if item.task == "reading" and scored and scored.get("em") == 0:
            flags.append("em_zero_lexical_only")
            if float(scored.get("token_f1") or 0) >= 0.8:
                flags.append("em_zero_f1_high_review_candidate")
        row = {
            "observation_key": f"{source['source_run_id']}|{key}",
            "item_key": f"{dataset}:{ref['item_id']}",
            "source_run_id": source["source_run_id"],
            "source_manifest_sha256": manifest_sha,
            "model_identity": source["model_identity"],
            "measurement_card_id": source["measurement_card_id"],
            "condition": run_metadata["condition"],
            "protocol_sha256": protocol_sha,
            "adapter_version": source["adapter"],
            "dataset_id": dataset,
            "source_dataset": ref.get("source_dataset"),
            "item_id": str(ref["item_id"]),
            "replicate_id": str(ref["replicate_id"]),
            "task_mode": "multiple_choice" if ref.get("task") == "multiple_choice" else "open_book_reading",
            "stratum": ref.get("stratum"),
            "passage_group": ref.get("passage_id"),
            "question": item.question,
            "rendered_input": item.prompt,
            "raw_prompt": (request or {}).get("raw_prompt"),
            "prompt_sha256": ref["prompt_sha256"],
            "raw_response": (request or {}).get("raw_response"),
            "prediction": (scored or {}).get("prediction"),
            "source_gold": (scored or {}).get("gold_answer", item.gold_answer),
            "source_metrics": metric_fields,
            "execution_status": status,
            "request_status": (request or {}).get("status"),
            "finish_reason": finish or None,
            "attempts": (request or {}).get("attempts"),
            "tool_calls": (request or {}).get("tool_calls"),
            "resources": {name: (request or {}).get(name) for name in (
                "prompt_tokens", "cached_prompt_tokens", "completion_tokens", "reasoning_tokens",
                "total_tokens", "latency_s", "reserved_cost_usd",
            )},
            "flags": flags,
            "diagnostic_annotations": [],
            "action_label": None,
            "artifact_refs": {
                "prediction": {"path": str(paths["predictions"].relative_to(ROOT)), "line": prediction_line_map.get(key)},
                "score": {"path": str(paths["scores"].relative_to(ROOT)), "line": score_line_map.get(key)},
                "manifest": {"path": str(paths["manifest"].relative_to(ROOT)), "index": len(result)},
            },
        }
        if complete and not scored:
            row["flags"].append("score_row_missing")
        result.append(row)
    summary_details = {
        dataset: {"expected": source_counts, "supplied_summary": supplied_summary[dataset]}
        for dataset, source_counts in sorted(per_dataset.items())
    }
    provenance = {
        "source_run_id": source["source_run_id"],
        "family": source["family"],
        "model_identity": source["model_identity"],
        "measurement_card_id": source["measurement_card_id"],
        "manifest_sha256": manifest_sha,
        "parent_manifest_sha256": source.get("expected_parent_manifest_sha256"),
        "protocol_sha256": protocol_sha,
        "source_file_sha256": actual_inputs,
        "frozen_input_sha256": source_hashes,
        "run_metadata": run_metadata,
        "coverage": summary_details,
        "expected_observations": len(expected_by_key),
        "prediction_observations": len(predictions),
        "score_observations": len(scores),
        "parity": {
            "item_score_parity": True,
            "summary_parity": not incomplete_reasons,
            "incomplete_reasons": sorted(set(incomplete_reasons)),
        },
        "ledger_status": "complete" if not incomplete_reasons else "source_incomplete",
    }
    return result, provenance


def _read_registry_source(source_id: str, registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    sources = load_registry(registry_path)
    try:
        return sources[source_id]
    except KeyError as exc:
        raise DiagnosticError(f"Error: unknown declared source run {source_id!r}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(_canonical_json(value) + b"\n")
    os.replace(tmp, path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in columns})
    os.replace(tmp, path)


def _read_records_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    try:
        with path.open(encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise DiagnosticError(f"Error: expected object at {path}:{line_no}")
                records.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagnosticError(f"Error: cannot read records {path}: {exc}") from exc
    return records


def _write_records_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _content_hash(files: list[Path]) -> str:
    return _sha256_bytes(_canonical_json({p.name: _sha256_file(p) for p in sorted(files)}))


def build_ledger(source_id: str, *, output_dir: Path | None = None) -> dict[str, Any]:
    source = _read_registry_source(source_id)
    rows, provenance = build_source_ledger(source)
    provenance["ledger_sha256"] = _sha256_bytes(b"".join(_canonical_json(row) + b"\n" for row in rows))
    base = (output_dir or OUTPUT_ROOT / "sources")
    dest = base / source_id
    source_root = (ROOT / source["run_dir"]).resolve()
    if dest.resolve() == source_root or source_root in dest.resolve().parents or dest.resolve() in source_root.parents:
        raise DiagnosticError("Error: ledger output may not overlap a source run directory")
    with tempfile.TemporaryDirectory(prefix=f".{source_id}-", dir=base.parent if base.parent.exists() else ROOT / "all_res") as tmp_name:
        temp = Path(tmp_name) / source_id
        temp.mkdir(parents=True)
        _write_jsonl(temp / "ledger.jsonl", rows)
        failure_rows = [row for row in rows if row["flags"]]
        _write_jsonl(temp / "failures.jsonl", failure_rows)
        _write_json(temp / "provenance.json", provenance)
        _write_json(temp / "coverage.json", {
            "source_run_id": source_id,
            "expected": len(rows),
            "completed": sum(row["execution_status"] in {"scored", "completed_unscored"} for row in rows),
            "scored": sum(row["execution_status"] == "scored" for row in rows),
            "failures_view_rows": len(failure_rows),
            "datasets": provenance["coverage"],
        })
        _write_json(temp / "parity-report.json", {
            "source_run_id": source_id, "manifest_verified": True,
            "source_hashes_verified": True,
            "item_score_parity": provenance["parity"]["item_score_parity"],
            "summary_parity": provenance["parity"]["summary_parity"],
            "incomplete_reasons": provenance["parity"]["incomplete_reasons"],
            "ledger_status": provenance["ledger_status"],
            "rebuild_sha256": provenance["ledger_sha256"],
        })
        if dest.exists():
            old = dest / "provenance.json"
            if not old.is_file() or _read_json(old).get("ledger_sha256") != provenance["ledger_sha256"]:
                raise DiagnosticError(f"Error: destination exists with different provenance; choose a new output label: {dest}")
            for path in temp.iterdir():
                target = dest / path.name
                if not target.is_file() or _sha256_file(target) != _sha256_file(path):
                    raise DiagnosticError(f"Error: existing snapshot differs at {target}")
            return provenance
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp, dest)
    return provenance


def load_controls(path: Path, protocol: dict[str, Any], protocol_sha: str) -> tuple[dict[str, Any], str]:
    """The controls file and its SHA-256. It must name the current protocol and resolve exactly the controls
    the protocol leaves unset, each with a value, and declare the experiment contract preregistered."""
    controls = _read_json(path)
    if set(controls) != CONTROLS_KEYS:
        raise DiagnosticError(f"Error: controls file {path} must have exactly the keys {sorted(CONTROLS_KEYS)}")
    if controls["protocol_sha256"] != protocol_sha:
        raise DiagnosticError("Error: the controls file was written for another protocol revision")
    unset = sorted(key for key, value in protocol["readiness_controls"].items() if value in (None, ""))
    experiment = protocol.get("future_experiment_contract", {})
    unset_experiment = sorted(field for field in EXPERIMENT_CONTROLS if not experiment.get(field))
    resolved, contract = controls["readiness_controls"], controls["future_experiment_contract"]
    if not isinstance(resolved, dict) or sorted(resolved) != unset:
        raise DiagnosticError(f"Error: the controls file must resolve exactly the unset readiness controls {unset}")
    if (not isinstance(contract, dict) or sorted(set(contract) - {"status"}) != unset_experiment
            or contract.get("status") != "preregistered"):
        raise DiagnosticError(f"Error: the controls file must resolve exactly {unset_experiment} "
                              "and set the experiment status preregistered")
    empty = [key for key, value in {**resolved, **contract}.items() if not isinstance(value, str) or not value.strip()]
    if empty:
        raise DiagnosticError(f"Error: controls without a value: {empty}")
    return controls, _sha256_file(path)


def readiness_report(*, ledger_dirs: list[Path] | None = None, audit_dir: Path | None = None,
                     controls_path: Path | None = None) -> dict[str, Any]:
    protocol, protocol_sha = load_protocol()
    registry = load_registry()
    ledgers: dict[str, Any] = {}
    for directory in (ledger_dirs or []):
        prov = _read_json(directory / "provenance.json")
        parity = _read_json(directory / "parity-report.json")
        ledgers[str(prov["source_run_id"])] = {
            "ledger_sha256": prov.get("ledger_sha256"),
            "manifest_sha256": prov.get("manifest_sha256"),
            "source_rows": prov.get("expected_observations"),
            "parity_passed": bool(parity.get("item_score_parity") and parity.get("summary_parity")),
        }
    readiness_controls = dict(protocol["readiness_controls"])
    experiment = dict(protocol.get("future_experiment_contract", {}))
    controls_sha = None
    if controls_path is not None:
        controls, controls_sha = load_controls(controls_path, protocol, protocol_sha)
        readiness_controls.update(controls["readiness_controls"])
        experiment.update(controls["future_experiment_contract"])
    unresolved = {key: value for key, value in readiness_controls.items() if value in (None, "")}
    experiment_blockers = [f"unregistered prospective control: {field}" for field in EXPERIMENT_CONTROLS
                           if not experiment.get(field)]
    if experiment.get("status") != "preregistered":
        experiment_blockers.append("prospective intervention protocol is not preregistered")
    audit_complete = False
    audit_reasons = ["human reviews have not completed; dual-review agreement remains pending"]
    audit: dict[str, Any] = {"completed": False, "reasons": audit_reasons}
    if audit_dir and (audit_dir / "audit-report.json").is_file():
        audit = _read_json(audit_dir / "audit-report.json")
        audit_complete = bool(audit.get("audit_complete"))
    prep_ready = bool(ledgers) and all(value["parity_passed"] for value in ledgers.values())
    return {
        "protocol_id": protocol["protocol_id"], "protocol_sha256": protocol_sha, "controls_sha256": controls_sha,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "declared_sources": sorted(registry), "built_ledgers": ledgers,
        "preparation_ready": prep_ready,
        "audit_complete": audit_complete,
        "inference_ready": bool(audit_complete and not unresolved and not experiment_blockers),
        "inference_blockers": [f"unresolved control: {key}" for key in sorted(unresolved)] + experiment_blockers + ([] if audit_complete else ["completed and independently reviewed pilot audit required"]),
        "audit": audit,
        "notes": ["Readiness is a project gate, not a model-performance score.", "No inference or endpoint request is performed by this module."],
    }


def _manifest_rows_from_ledger(ledger_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, _ = _read_jsonl(ledger_path)
    by_key = {_identity({"dataset_id": row["dataset_id"], "item_id": row["item_id"], "replicate_id": row["replicate_id"]}): row for row in rows}
    if len(by_key) != len(rows):
        raise DiagnosticError("Error: duplicate source observation identity in ledger")
    provenance = _read_json(ledger_path.parent / "provenance.json")
    if not provenance.get("ledger_sha256"):
        raise DiagnosticError("Error: ledger has no immutable content digest")
    digest = _sha256_bytes(b"".join(_canonical_json(row) + b"\n" for row in rows))
    if digest != provenance["ledger_sha256"]:
        raise DiagnosticError("Error: ledger content checksum mismatch")
    return rows, provenance


def _read_pilot(pilot_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, _ = _read_jsonl(pilot_dir / "pilot.jsonl")
    selection = _read_json(pilot_dir / "selection.json")
    if len(rows) != selection.get("item_count") or len(rows) != 60:
        raise DiagnosticError("Error: pilot item count differs from the locked selection")
    content_rows = [{key: value for key, value in row.items() if key != "packet_sha256"} for row in rows]
    digest = _sha256_bytes(b"".join(_canonical_json(row) + b"\n" for row in content_rows))
    if digest != selection.get("pilot_content_sha256"):
        raise DiagnosticError("Error: pilot packet content checksum mismatch")
    if selection.get("pilot_file_sha256") != _sha256_file(pilot_dir / "pilot.jsonl"):
        raise DiagnosticError("Error: pilot file checksum mismatch")
    if selection.get("review_schema_version") != REVIEW_SCHEMA_VERSION or selection.get("annotation_revision") != ANNOTATION_REVISION:
        raise DiagnosticError("Error: pilot belongs to a previous annotation revision; prepare a new review snapshot")
    protocol, protocol_sha = load_protocol()
    if selection.get("protocol_sha256") != protocol_sha:
        raise DiagnosticError("Error: pilot was prepared under a different protocol revision")
    if any(row.get("protocol_sha256") != protocol_sha or row.get("rubric_version") != protocol["rubric_version"] for row in rows):
        raise DiagnosticError("Error: pilot rows have inconsistent protocol/rubric provenance")
    return rows, selection


def revise_pilot_review(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Rebind a verified locked pilot to the current review revision without resampling or inference."""
    rows, _ = _read_jsonl(source_dir / "pilot.jsonl")
    previous = _read_json(source_dir / "selection.json")
    old_revision = previous.get("annotation_revision")
    if old_revision not in {1, 2, 3}:
        raise DiagnosticError("Error: unsupported source annotation revision for locked-pilot rebinding")
    archive = DATA_DIR / "revisions" / f"review-v{old_revision}"
    old_protocol = _read_json(archive / "protocol.json")
    old_rubric = str(old_protocol.get("rubric_version", ""))
    if previous.get("protocol_sha256") != _sha256_file(archive / "protocol.json"):
        raise DiagnosticError(f"Error: old pilot does not match the archived annotation-v{old_revision} protocol")
    content = [{key: value for key, value in row.items() if key != "packet_sha256"} for row in rows]
    digest = _sha256_bytes(b"".join(_canonical_json(row) + b"\n" for row in content))
    keys = [row["observation_key"] for row in rows]
    second = previous.get("second_review_keys", [])
    if (len(rows) != 60 or previous.get("item_count") != 60 or len(set(keys)) != 60
            or digest != previous.get("pilot_content_sha256")
            or _sha256_file(source_dir / "pilot.jsonl") != previous.get("pilot_file_sha256")
            or any(row.get("packet_sha256") != digest or row.get("protocol_sha256") != previous["protocol_sha256"]
                   or row.get("rubric_version") != old_rubric for row in rows)
            or len(second) != 15 or len(set(second)) != 15 or not set(second) <= set(keys)):
        raise DiagnosticError("Error: old pilot integrity or locked item/subset coverage failed")
    protocol, protocol_sha = load_protocol()
    revised = [dict(row, protocol_sha256=protocol_sha, rubric_version=RUBRIC_VERSION) for row in content]
    revised_sha = _sha256_bytes(b"".join(_canonical_json(row) + b"\n" for row in revised))
    for row in revised:
        row["packet_sha256"] = revised_sha
    previous_revisions = [{"annotation_revision": old_revision, "pilot_content_sha256": digest,
                            "protocol_sha256": previous["protocol_sha256"],
                            "review_schema_version": previous["review_schema_version"]}]
    if previous.get("previous_revisions"):
        previous_revisions.extend(previous["previous_revisions"])
    elif isinstance(previous.get("revision_of"), dict):
        previous_revisions.append(previous["revision_of"])
    selection = dict(previous, protocol_sha256=protocol_sha, rubric_version=RUBRIC_VERSION,
                     annotation_revision=ANNOTATION_REVISION, review_schema_version=REVIEW_SCHEMA_VERSION,
                     pilot_content_sha256=revised_sha,
                     revision_of={"pilot_content_sha256": digest, "protocol_sha256": previous["protocol_sha256"],
                                  "annotation_revision": old_revision,
                                  "review_schema_version": previous["review_schema_version"]},
                     previous_revisions=previous_revisions)
    existed = output_dir.exists()
    _publish_pilot(output_dir, revised, selection, protocol)
    if existed:
        return selection
    _write_jsonl(output_dir / "assistant_suggestions.jsonl", [])
    _write_json(output_dir / "assistant-suggestions.json", {
        "schema_version": SUGGESTION_SCHEMA_VERSION, "status": "pending",
        "pilot_content_sha256": revised_sha, "protocol_sha256": protocol_sha,
        "file_sha256": _sha256_file(output_dir / "assistant_suggestions.jsonl"),
        "item_count": 0, "note": "AI suggestions are not human judgments and cannot be imported as reviews.",
    })
    return selection


def _stable_rank(seed: int, identity: str) -> str:
    return _sha256_bytes(f"{seed}\t{identity}".encode("utf-8"))


def select_pilot(ledger_path: Path, *, output_dir: Path | None = None) -> dict[str, Any]:
    protocol, protocol_sha = load_protocol()
    rows, provenance = _manifest_rows_from_ledger(ledger_path)
    anchor = protocol["pilot"]["anchor_source"]
    if provenance.get("source_run_id") != anchor:
        raise DiagnosticError(f"Error: pilot anchor must be {anchor}; received {provenance.get('source_run_id')}")
    expected_counts = protocol["pilot"]["dataset_counts"]
    selected: list[dict[str, Any]] = []
    allocation: dict[str, Any] = {}
    seed = int(protocol["pilot"]["seed"])
    for dataset, quota in expected_counts.items():
        candidates = [row for row in rows if row["dataset_id"] == dataset and row["execution_status"] == "scored"]
        if len(candidates) < quota:
            raise DiagnosticError(f"Error: pilot dataset {dataset} has {len(candidates)} eligible local-gold rows; needs {quota}")
        task = candidates[0]["task_mode"]
        scored_ok = [row for row in candidates if row["source_metrics"].get("correct") in {0, 1}] if task == "multiple_choice" else [row for row in candidates if row["source_metrics"].get("em") in {0, 1}]
        if len(scored_ok) != len(candidates):
            raise DiagnosticError(f"Error: pilot dataset {dataset} includes unscored/invalid correctness values")
        strata: dict[str, list[dict[str, Any]]]
        if task == "multiple_choice":
            strata = {
                "correct": [row for row in candidates if row["source_metrics"].get("correct") == 1],
                "incorrect": [row for row in candidates if row["source_metrics"].get("correct") == 0],
            }
        else:
            strata = {
                "em": [row for row in candidates if row["source_metrics"].get("em") == 1],
                "non_em": [row for row in candidates if row["source_metrics"].get("em") == 0],
            }
        goals = {key: int(value) for key, value in (protocol["pilot"]["correctness_quotas"]["multiple_choice" if task == "multiple_choice" else "reading"]).items()}
        chosen: list[dict[str, Any]] = []
        reasons: dict[str, int] = {}
        f1_config = protocol["pilot"].get("reading_f1_disagreement", {})
        for stratum, goal in goals.items():
            pool = list(strata[stratum])
            priority: list[dict[str, Any]] = []
            if task == "reading" and stratum == "non_em":
                priority = [row for row in pool if float(row["source_metrics"].get("token_f1") or 0) >= float(f1_config.get("token_f1_gte", 0.8))]
                priority.sort(key=lambda row: (_stable_rank(seed, row["observation_key"]), row["item_id"]))
                priority = priority[: int(f1_config.get("priority_up_to", 3))]
            priority_keys = {row["observation_key"] for row in priority}
            rest = sorted((row for row in pool if row["observation_key"] not in priority_keys), key=lambda row: (_stable_rank(seed, row["observation_key"]), row["item_id"]))
            picked = priority[:goal]
            picked += rest[:max(0, goal - len(picked))]
            reason_default = f"stratum:{stratum}"
            for row in picked:
                row = dict(row)
                row["selection_reason"] = "reading_em_zero_token_f1_high_priority" if row["observation_key"] in priority_keys else reason_default
                chosen.append(row)
                reasons[row["selection_reason"]] = reasons.get(row["selection_reason"], 0) + 1
            if len(picked) < goal:
                remainder = goal - len(picked)
                other = "incorrect" if stratum == "correct" else "correct" if stratum == "incorrect" else "non_em" if stratum == "em" else "em"
                already = {row["observation_key"] for row in chosen}
                fallback = sorted((row for row in strata[other] if row["observation_key"] not in already), key=lambda row: (_stable_rank(seed, row["observation_key"]), row["item_id"]))[:remainder]
                for row in fallback:
                    copy = dict(row)
                    copy["selection_reason"] = f"fallback:{other}:shortage:{stratum}"
                    chosen.append(copy)
                    reasons[copy["selection_reason"]] = reasons.get(copy["selection_reason"], 0) + 1
                if len(fallback) != remainder:
                    raise DiagnosticError(f"Error: pilot {dataset} could not fill quota for {stratum}")
        if len(chosen) != quota:
            raise DiagnosticError(f"Error: pilot allocation wrong for {dataset}: {len(chosen)} != {quota}")
        allocation[dataset] = {"target": quota, "selected": len(chosen), "reasons": reasons, "available_strata": {k: len(v) for k, v in strata.items()}}
        selected.extend(chosen)
    seen = [row["item_key"] for row in selected]
    if len(seen) != 60 or len(set(seen)) != 60:
        raise DiagnosticError("Error: pilot must contain exactly 60 unique item keys")
    selected.sort(key=lambda row: (row["dataset_id"], row["item_id"]))
    second_review = []
    for dataset in expected_counts:
        pool = [row for row in selected if row["dataset_id"] == dataset]
        second_review.extend(sorted(pool, key=lambda row: (_stable_rank(seed + 1009, row["observation_key"]), row["item_id"]))[:3])
    def packet_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "observation_key": row["observation_key"], "item_key": row["item_key"],
            "dataset_id": row["dataset_id"], "item_id": row["item_id"], "replicate_id": row["replicate_id"],
            "source_run_id": row["source_run_id"], "source_manifest_sha256": row["source_manifest_sha256"],
            "prompt_sha256": row["prompt_sha256"], "task_mode": row["task_mode"],
            "question": row["question"], "rendered_input": row["rendered_input"],
            "raw_response": row["raw_response"], "prediction": row["prediction"],
            "source_gold": row["source_gold"], "source_metrics": row["source_metrics"],
            "finish_reason": row["finish_reason"], "passage_group": row["passage_group"],
            "selection_reason": row["selection_reason"], "exposure": "development-audit",
            "protocol_sha256": protocol_sha, "rubric_version": protocol["rubric_version"],
        }
    selected = [packet_row(row) for row in selected]
    second_ids = {row["observation_key"] for row in second_review}
    second_review = [row for row in selected if row["observation_key"] in second_ids]
    pilot_content_sha = _sha256_bytes(b"".join(_canonical_json(row) + b"\n" for row in selected))
    for row in selected:
        row["packet_sha256"] = pilot_content_sha
    second_review = [row for row in selected if row["observation_key"] in second_ids]
    selection = {
        "protocol_id": protocol["protocol_id"], "protocol_sha256": protocol_sha,
        "rubric_version": protocol["rubric_version"], "source_run_id": provenance["source_run_id"],
        "source_manifest_sha256": provenance["manifest_sha256"], "source_ledger_sha256": provenance["ledger_sha256"],
        "anchor_condition": provenance.get("run_metadata"), "selection_seed": seed,
        "exposure": "development-audit; previously evaluated outputs/datasets; not pristine held-out",
        "pilot_content_sha256": pilot_content_sha, "item_count": len(selected),
        "second_review_count": len(second_review), "second_review_keys": [row["observation_key"] for row in second_review],
        "allocation": allocation, "population_estimate": False,
    }
    selection["review_schema_version"] = REVIEW_SCHEMA_VERSION
    selection["annotation_revision"] = ANNOTATION_REVISION
    dest = output_dir or OUTPUT_ROOT / "pilot-review-v4"
    _publish_pilot(dest, selected, selection, protocol)
    prep_report = readiness_report(ledger_dirs=[ledger_path.parent], audit_dir=dest)
    _write_json(dest / "readiness-report.json", prep_report)
    return selection


def _publish_pilot(dest: Path, rows: list[dict[str, Any]], selection: dict[str, Any], protocol: dict[str, Any]) -> None:
    dest = dest.resolve()
    if ROOT / "all_res" not in dest.parents:
        raise DiagnosticError("Error: pilot output must remain under all_res/diagnostic_v1")
    pilot_bytes = b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n" for row in rows)
    selection["pilot_file_sha256"] = _sha256_bytes(pilot_bytes)
    if dest.exists():
        old = _read_json(dest / "selection.json") if (dest / "selection.json").is_file() else {}
        if old.get("pilot_content_sha256") != selection["pilot_content_sha256"] or old.get("pilot_file_sha256") != selection["pilot_file_sha256"]:
            raise DiagnosticError(f"Error: pilot output exists with different content; choose a new label: {dest}")
        _write_audit_report(dest, rows)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pilot-", dir=dest.parent) as tmp_name:
        temp = Path(tmp_name)
        _write_json(temp / "selection.json", selection)
        _write_json(temp / "readiness.json", {"preparation_ready": True, "audit_complete": False, "inference_ready": False,
                                                  "blockers": ["human audit and independent second review pending", "runtime endpoint, corpus, and budget unresolved"]})
        _write_records_jsonl(temp / "adjudications.jsonl", [])
        _write_records_jsonl(temp / "contrasts.jsonl", [])
        _write_jsonl(temp / "pilot.jsonl", rows)
        blind_rows = [{key: value for key, value in row.items() if key in REVIEW_IMMUTABLE_COLUMNS} | {key: "" for key in REVIEW_JUDGMENT_COLUMNS} for row in rows]
        _write_csv(temp / "review_A.csv", blind_rows, REVIEW_COLUMNS)
        _write_csv(temp / "review_B.csv", blind_rows, REVIEW_COLUMNS)
        second_keys = set(selection["second_review_keys"])
        _write_csv(temp / "review_B_second_subset.csv", [row for row in blind_rows if row["observation_key"] in second_keys], REVIEW_COLUMNS)
        lines = ["# Diagnostic pilot — development audit", "", "Đây là mẫu có chủ đích để kiểm tra rubric/pipeline; không ước lượng tỷ lệ lỗi toàn bộ benchmark và không phải held-out sạch.", "", f"Protocol SHA256: `{selection['protocol_sha256']}`", f"Source ledger SHA256: `{selection['source_ledger_sha256']}`", f"Items: {len(rows)}", f"Reviewer B subset: {len(second_keys)} (3 per dataset)", "", "Model answers and source gold are visible. This is a diagnostic review, not a blind gold-construction pass.", "", "| Dataset | Selected | Allocation/notes |", "|---|---:|---|"]
        for dataset, info in selection["allocation"].items():
            lines.append(f"| {dataset} | {info['selected']} | `{json.dumps(info['reasons'], sort_keys=True)}` |")
        for index, row in enumerate(rows, 1):
            lines += ["", f"## {index}. {row['dataset_id']} · `{row['item_id']}`", "", f"Selection: `{row['selection_reason']}`; source gold: `{row['source_gold']}`; source metrics: `{json.dumps(row['source_metrics'], ensure_ascii=False, sort_keys=True)}`", "", "**Question**", "", str(row.get("question", "")), "", "**Rendered input (passage/choices retained)**", "", "```text", str(row.get("rendered_input", "")), "```", "", "**Model answer**", "", "```text", str(row.get("raw_response", "")), "```"]
        (temp / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        _write_audit_report(temp, rows)
        os.replace(temp, dest)


def _parse_review_field(row: dict[str, str], name: str, allowed: set[str]) -> str:
    value = str(row.get(name, "")).strip()
    if value and value not in allowed:
        raise DiagnosticError(f"Error: invalid {name}={value!r}")
    return value


def _immutable_packet_sha(row: dict[str, str]) -> str:
    values = {name: row.get(name, "") for name in REVIEW_IMMUTABLE_COLUMNS if name != "packet_sha256"}
    return _sha256_bytes(_canonical_json(values))


def _read_contrasts(pilot_dir: Path) -> dict[str, dict[str, Any]]:
    records = _read_records_jsonl(pilot_dir / "contrasts.jsonl")
    selection = _read_json(pilot_dir / "selection.json")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        identity = str(record.get("contrast_id", ""))
        if not identity or identity in result:
            raise DiagnosticError("Error: missing/duplicate contrast_id")
        artifact = Path(str(record.get("evidence_artifact", "")))
        if not artifact.is_absolute():
            artifact = pilot_dir / artifact
        if (record.get("pilot_content_sha256") != selection["pilot_content_sha256"]
                or record.get("label") not in DIAGNOSTIC_LABELS or not record.get("observation_key")
                or record.get("kind") not in {"controlled_model_contrast", "deterministic_replay"}
                or record.get("verified") is not True or record.get("other_conditions_controlled") is not True
                or record.get("supports_hypothesis") is not True
                or not record.get("reviewer_id") or not record.get("rationale")
                or not record.get("baseline_condition_id") or not record.get("intervention_condition_id")
                or record.get("baseline_condition_id") == record.get("intervention_condition_id")
                or not artifact.is_file() or _sha256_file(artifact) != record.get("evidence_artifact_sha256")):
            raise DiagnosticError(f"Error: contrast {identity} lacks verified controlled evidence/artifact hash")
        result[identity] = record
    return result


def _validate_support(labels: list[str], supports: list[dict[str, Any]], row: dict[str, Any], contrasts: dict[str, dict[str, Any]]) -> None:
    if not isinstance(supports, list) or any(not isinstance(value, dict) for value in supports):
        raise DiagnosticError("Error: diagnostic_support must be an array of per-hypothesis objects")
    if any(not all(isinstance(value.get(field), str) for field in ("label", "status", "evidence_reference", "contrast_id")) for value in supports):
        raise DiagnosticError("Error: diagnostic_support values must be strings")
    if sorted(value.get("label", "") for value in supports) != sorted(labels) or len(labels) != len(set(labels)):
        raise DiagnosticError("Error: diagnostic_support must match every selected hypothesis exactly once")
    for support in supports:
        if set(support) != {"label", "status", "evidence_reference", "contrast_id"}:
            raise DiagnosticError("Error: diagnostic_support fields differ from revision-4 schema")
        label = support["label"]
        if label not in DIAGNOSTIC_LABELS or support["status"] not in ATTRIBUTION_STATUSES or not str(support["evidence_reference"]).strip():
            raise DiagnosticError("Error: hypothesis needs a controlled label, support status and evidence reference")
        if support["status"] == "hypothesis":
            if support["contrast_id"]:
                raise DiagnosticError("Error: hypothesis cannot assert an unverified contrast_id")
            continue
        contrast = contrasts.get(support["contrast_id"])
        if not contrast or contrast.get("observation_key") != row["observation_key"] or contrast.get("label") != label:
            raise DiagnosticError("Error: contrast_supported requires matching registered observation/label evidence")
        if label in {"reasoning_gap", "reading_representation_gap", "instruction_gap", "generator_evidence_use_gap"} and row["input_evidence_sufficiency"] != "sufficient":
            raise DiagnosticError("Error: this hypothesis requires verified sufficient input premises")
        if label in {"retrieval_gap", "context_assembly_gap"} and row["corpus_evidence_availability"] != "present":
            raise DiagnosticError("Error: retrieval/assembly attribution requires corpus evidence present")
        if contrast["kind"] == "deterministic_replay" and label not in {"external_evidence_gap", "parser_gap", "measurement_gap", "context_assembly_gap"}:
            raise DiagnosticError("Error: parametric knowledge/reasoning attribution requires controlled model probes; deterministic replay supports only declared component/evidence labels")
        if label == "external_evidence_gap" and row["input_evidence_sufficiency"] != "insufficient":
            raise DiagnosticError("Error: external evidence gap requires documented insufficient input")


def _validate_diagnostic_outcome(row: dict[str, Any], contrasts: dict[str, dict[str, Any]]) -> None:
    outcome, issues, labels = row["diagnostic_outcome"], row["observed_issues"], row["diagnostic_labels"]
    if any(value not in OBSERVED_ISSUES for value in issues) or len(issues) != len(set(issues)):
        raise DiagnosticError("Error: unknown/duplicate observed issue")
    if outcome == "no_observed_issue":
        if issues or labels or row["diagnostic_support"] or row["semantic_correctness"] != "correct" or row["gold_validity"] != "valid" or row["review_status"] != "reviewed":
            raise DiagnosticError("Error: no_observed_issue requires correct semantics, valid gold, reviewed and no issue/cause labels")
    elif outcome == "issue_observed":
        if not issues or row["review_status"] != "reviewed":
            raise DiagnosticError("Error: issue_observed requires an observed issue and reviewed status; unknown cause may stay empty")
    elif outcome == "unresolved":
        if issues or labels or row["diagnostic_support"] or row["review_status"] != "deferred":
            raise DiagnosticError("Error: unresolved outcome requires deferred status and no forced issue/cause")
    if outcome != "unresolved" and row["audit_evidence_kind"] == "unavailable":
        raise DiagnosticError("Error: completed answer audit requires available audit evidence")
    if row["corpus_evidence_availability"] in {"present", "absent"} and not row["corpus_evidence_reference"].strip():
        raise DiagnosticError("Error: corpus availability requires its own scoped evidence reference")
    _validate_support(labels, row["diagnostic_support"], row, contrasts)


def import_review(pilot_dir: Path, review_path: Path, *, annotator_id: str) -> dict[str, Any]:
    if not annotator_id.strip():
        raise DiagnosticError("Error: annotator_id must be a non-empty human-provided identifier")
    pilot_rows, selection = _read_pilot(pilot_dir)
    pilot_map = {row["observation_key"]: row for row in pilot_rows}
    contrasts = _read_contrasts(pilot_dir)
    seen: set[str] = set()
    imported: list[dict[str, Any]] = []
    with review_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REVIEW_COLUMNS:
            raise DiagnosticError(f"Error: diagnostic review columns/order do not match {REVIEW_SCHEMA_VERSION}; old CSVs require their original snapshot/tooling")
        for line_no, raw in enumerate(reader, 2):
            key = raw.get("observation_key", "")
            if key not in pilot_map or key in seen:
                raise DiagnosticError(f"Error: unknown observation key or duplicate review key at row {line_no}: {key}")
            seen.add(key)
            if raw.get("annotator_id", "").strip() and raw["annotator_id"].strip() != annotator_id:
                raise DiagnosticError("Error: annotator_id differs from importer identity")
            for column in REVIEW_IMMUTABLE_COLUMNS:
                expected = pilot_map[key].get(column)
                actual = raw.get(column, "")
                if column == "source_metrics":
                    try:
                        same = json.loads(actual) == expected
                    except json.JSONDecodeError:
                        same = False
                else:
                    same = actual == ("" if expected is None else str(expected))
                if not same:
                    raise DiagnosticError(f"Error: review row {line_no} edited immutable field {column}")
            row = {"observation_key": key, "annotator_id": annotator_id}
            enum_fields = {"review_scope": {"primary-60", "independent-15"}, "review_assistance_mode": REVIEW_ASSISTANCE_MODES,
                           "semantic_correctness": {"correct", "incorrect", "uncertain"}, "gold_validity": {"valid", "suspect", "unassessable"},
                           "input_evidence_sufficiency": INPUT_EVIDENCE_SUFFICIENCY, "corpus_evidence_availability": CORPUS_AVAILABILITY,
                           "audit_evidence_kind": AUDIT_EVIDENCE_KINDS, "diagnostic_outcome": DIAGNOSTIC_OUTCOMES,
                           "review_status": {"reviewed", "deferred"}}
            for field, allowed in enum_fields.items():
                row[field] = _parse_review_field(raw, field, allowed)
            for field in ("evidence_reference", "corpus_evidence_reference", "rationale", "reviewer_attestation", "blind_review_attestation"):
                row[field] = str(raw.get(field, "")).strip()
            for field, allowed in (("diagnostic_labels", DIAGNOSTIC_LABELS), ("observed_issues", OBSERVED_ISSUES)):
                row[field] = [value.strip() for value in str(raw.get(field, "")).split(";") if value.strip()]
                if any(value not in allowed for value in row[field]) or len(set(row[field])) != len(row[field]):
                    raise DiagnosticError(f"Error: unknown diagnostic label/observed issue or duplicate {field}")
            try:
                row["diagnostic_support"] = json.loads(raw.get("diagnostic_support") or "[]")
            except json.JSONDecodeError as exc:
                raise DiagnosticError("Error: invalid diagnostic_support JSON") from exc
            judged = any(str(raw.get(field, "")).strip() for field in REVIEW_JUDGMENT_COLUMNS if field not in {"annotator_id", "review_scope"})
            if judged:
                required = set(enum_fields) | {"evidence_reference", "rationale", "reviewer_attestation"}
                if any(not row[field] for field in required):
                    raise DiagnosticError("Error: partially filled review; complete audit fields or leave all judgments blank")
                expected_attestation = AI_ASSISTED_ATTESTATION if row["review_assistance_mode"] == "ai_assisted" else HUMAN_ONLY_ATTESTATION
                if row["reviewer_attestation"] != expected_attestation:
                    raise DiagnosticError("Error: attestation does not match assistance provenance")
                if row["review_scope"] == "independent-15":
                    if row["review_assistance_mode"] != "human_only" or row["blind_review_attestation"] != BLIND_ATTESTATION:
                        raise DiagnosticError("Error: independent review requires human_only and blind self-attestation")
                elif row["blind_review_attestation"]:
                    raise DiagnosticError("Error: primary review cannot claim blind-independent attestation")
                _validate_diagnostic_outcome(row, contrasts)
            row.update(review_schema_version=REVIEW_SCHEMA_VERSION, review_source_sha256=_sha256_file(review_path), review_row=line_no,
                       pilot_content_sha256=selection["pilot_content_sha256"], imported_at_utc=datetime.now(timezone.utc).isoformat())
            imported.append(row)
    scopes = {row["review_scope"] for row in imported if row["review_scope"]}
    if len(scopes) > 1:
        raise DiagnosticError("Error: packet mixes review scopes")
    if scopes:
        scope = next(iter(scopes))
        expected_keys = set(selection["second_review_keys"]) if scope == "independent-15" else set(pilot_map)
        if seen != expected_keys:
            raise DiagnosticError("Error: packet coverage differs from its declared scope")
        previous = [row for row in _read_review_exports(pilot_dir) if row.get("review_status") and row["annotator_id"] == annotator_id]
        if any(row["review_scope"] != scope for row in previous):
            raise DiagnosticError("Error: a primary identity cannot also be the independent reviewer")
    out = pilot_dir / "reviews" / f"{_safe_label(annotator_id)}.jsonl"
    if out.exists():
        raise DiagnosticError(f"Error: review import is append-only; destination exists: {out}")
    _write_jsonl(out, imported)
    _write_audit_report(pilot_dir, pilot_rows)
    return {"annotator_id": annotator_id, "rows": len(imported), "reviewed": sum(bool(row["review_status"]) for row in imported), "destination": str(out)}


def _safe_label(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    normalized = "-".join(piece for piece in normalized.split("-") if piece)
    if not normalized:
        raise DiagnosticError("Error: empty filename label")
    return normalized[:80]


def add_adjudication(pilot_dir: Path, *, observation_key: str, reviewer_id: str, decision: str, rationale: str) -> dict[str, Any]:
    allowed = {"resolved", "deferred"}
    if decision not in allowed or not reviewer_id.strip() or not rationale.strip():
        raise DiagnosticError("Error: adjudication requires reviewer, resolved/deferred decision and rationale")
    pilot_rows, selection = _read_pilot(pilot_dir)
    if observation_key not in {row["observation_key"] for row in pilot_rows}:
        raise DiagnosticError(f"Error: unknown pilot observation {observation_key}")
    path = pilot_dir / "adjudications.jsonl"
    decisions = _read_records_jsonl(path)
    decisions.append({"observation_key": observation_key, "reviewer_id": reviewer_id, "decision": decision, "rationale": rationale.strip(), "pilot_content_sha256": selection["pilot_content_sha256"], "created_at_utc": datetime.now(timezone.utc).isoformat()})
    _write_records_jsonl(path, decisions)
    _write_audit_report(pilot_dir, pilot_rows)
    return {"decisions": decisions}


def _read_review_exports(pilot_dir: Path) -> list[dict[str, Any]]:
    result = []
    review_dir = pilot_dir / "reviews"
    if not review_dir.is_dir():
        return result
    for path in sorted(review_dir.glob("*.jsonl")):
        result.extend(_read_records_jsonl(path))
    return result


def _agreement(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        value = row.get(field)
        if value:
            grouped[str(row["observation_key"])].append(str(value))
    paired = [values for values in grouped.values() if len(values) >= 2]
    agreements = sum(1 for values in paired if len(set(values)) == 1)
    return {"metric": "raw_exact_agreement", "field": field, "paired_n": len(paired), "agreement_n": agreements, "agreement": agreements / len(paired) if paired else None}


def _write_audit_report(pilot_dir: Path, pilot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    pilot_rows, selection = _read_pilot(pilot_dir)
    reviews = _read_review_exports(pilot_dir)
    completed = [row for row in reviews if row.get("review_status")]
    contrasts = _read_contrasts(pilot_dir)
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in completed:
        expected = AI_ASSISTED_ATTESTATION if review.get("review_assistance_mode") == "ai_assisted" else HUMAN_ONLY_ATTESTATION
        if (review.get("review_schema_version") != REVIEW_SCHEMA_VERSION or review.get("review_scope") not in {"primary-60", "independent-15"}
                or review.get("review_assistance_mode") not in REVIEW_ASSISTANCE_MODES or review.get("reviewer_attestation") != expected
                or (review.get("review_scope") == "independent-15" and (review.get("review_assistance_mode") != "human_only" or review.get("blind_review_attestation") != BLIND_ATTESTATION))):
            raise DiagnosticError("Error: saved review schema/scope/assistance/blinding provenance is invalid")
        if review.get("review_scope") == "independent-15" and review["observation_key"] not in selection["second_review_keys"]:
            raise DiagnosticError("Error: saved independent review is outside the fixed subset")
        _validate_diagnostic_outcome(review, contrasts)
        by_key[review["observation_key"]].append(review)
    second = set(selection["second_review_keys"])
    def is_blind(row: dict[str, Any]) -> bool:
        return row.get("review_scope") == "independent-15" and row.get("review_assistance_mode") == "human_only" and row.get("blind_review_attestation") == BLIND_ATTESTATION
    pairs = {}
    for key in second:
        primary = [r for r in by_key[key] if r.get("review_scope") == "primary-60"]
        blind = [r for r in by_key[key] if is_blind(r)]
        if primary and blind and any(a["annotator_id"] != b["annotator_id"] for a in primary for b in blind):
            pairs[key] = primary + blind
    primary_keys = {key for key, values in by_key.items() if any(r.get("review_scope") == "primary-60" for r in values)}
    fields = ("semantic_correctness", "gold_validity", "input_evidence_sufficiency", "corpus_evidence_availability", "diagnostic_outcome")
    conflicts = {key for key, values in by_key.items() if any(len({r.get(field) for r in values}) > 1 for field in fields)
                 or len({tuple(sorted(r.get("observed_issues", []))) for r in values}) > 1
                 or len({tuple(sorted(r.get("diagnostic_labels", []))) for r in values}) > 1}
    adjudications = _read_records_jsonl(pilot_dir / "adjudications.jsonl")
    adjudicated = {r["observation_key"]: r for r in adjudications}
    handled = all(adjudicated.get(key, {}).get("decision") in {"resolved", "deferred"} for key in conflicts)
    eligible_by_label: dict[str, list[str]] = {label: [] for label in sorted(DIAGNOSTIC_LABELS)}
    ineligible: dict[str, int] = Counter()
    controls = []
    for item in pilot_rows:
        key = item["observation_key"]; values = by_key.get(key, [])
        reason = None
        if not values: reason = "not_reviewed"
        elif key in conflicts: reason = "conflict_needs_final_consistent_judgment"
        elif any(r["review_status"] == "deferred" or r["diagnostic_outcome"] == "unresolved" for r in values): reason = "assessment_unresolved_or_deferred"
        elif all(r["diagnostic_outcome"] == "no_observed_issue" for r in values):
            controls.append(key); reason = "no_issue_control_not_causal_positive"
        elif any(r["gold_validity"] != "valid" or r["semantic_correctness"] == "uncertain" for r in values): reason = "audit_unresolved"
        else:
            common = set(values[0]["diagnostic_labels"])
            for r in values[1:]: common.intersection_update(r["diagnostic_labels"])
            qualified = [label for label in common if all(any(e["label"] == label and e["status"] == "contrast_supported" for e in r["diagnostic_support"]) for r in values)]
            if qualified:
                for label in qualified: eligible_by_label[label].append(key)
            else: reason = "no_verified_contrast_supported_hypothesis"
        if reason: ineligible[reason] += 1
    eligible = sorted({key for keys in eligible_by_label.values() for key in keys})
    paired_rows = [r for values in pairs.values() for r in values]
    paired_issues = {key: values for key, values in pairs.items() if all(r["diagnostic_outcome"] == "issue_observed" for r in values)}
    report = {
        "protocol_id": selection["protocol_id"], "protocol_sha256": selection["protocol_sha256"], "pilot_content_sha256": selection["pilot_content_sha256"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "selected_n": len(pilot_rows), "reviewed_anchor_n": len(primary_keys),
        "reviewer_count": len({r["annotator_id"] for r in completed}), "reviewers": sorted({r["annotator_id"] for r in completed}),
        "review_assistance_counts": dict(Counter(r["review_assistance_mode"] for r in completed)),
        "independent_subset_n": len(second), "independent_subset_paired_n": len(pairs), "independence_basis": "self-attested person/scope/blinding; browser IDs are not authentication",
        "paired_review_assistance_modes": dict(Counter("|".join(sorted({r["review_assistance_mode"] for r in values})) for values in pairs.values())),
        "agreement_design": "report AI-assisted-primary versus blind-human separately from human-only-primary versus blind-human",
        "semantic_correctness_agreement": _agreement(paired_rows, "semantic_correctness"), "gold_validity_agreement": _agreement(paired_rows, "gold_validity"),
        "input_evidence_sufficiency_agreement": _agreement(paired_rows, "input_evidence_sufficiency"), "corpus_evidence_availability_agreement": _agreement(paired_rows, "corpus_evidence_availability"), "diagnostic_outcome_agreement": _agreement(paired_rows, "diagnostic_outcome"),
        "diagnostic_label_agreement": {"metric": "exact_hypothesis_set_agreement", "denominator": "scope_valid_primary_blind_pairs_issue_observed", "paired_n": len(paired_issues),
            "agreement_n": sum(len({tuple(sorted(r["diagnostic_labels"])) for r in values}) == 1 for values in paired_issues.values())},
        "hypothesis_support_agreement": {label: {
            "paired_n": sum(all(label in r["diagnostic_labels"] for r in values) for values in pairs.values()),
            "agreement_n": sum(len({next(v["status"] for v in r["diagnostic_support"] if v["label"] == label) for r in values}) == 1
                               for values in pairs.values() if all(label in r["diagnostic_labels"] for r in values))
        } for label in sorted(DIAGNOSTIC_LABELS)},
        "diagnostic_outcome_counts": {"denominator": "completed_reviewer_judgments", "n": len(completed), "counts": dict(Counter(r["diagnostic_outcome"] for r in completed))},
        "deferred_judgment_n": sum(r["review_status"] == "deferred" for r in completed),
        "unresolved_conflict_keys": sorted(key for key in conflicts if adjudicated.get(key, {}).get("decision") != "resolved"),
        "resolved_conflict_keys": sorted(key for key in conflicts if adjudicated.get(key, {}).get("decision") == "resolved"),
        "deferred_conflict_keys": sorted(key for key in conflicts if adjudicated.get(key, {}).get("decision") == "deferred"), "adjudication_count": len(adjudications),
        "reviewed_no_issue_control_n": len(controls), "reviewed_no_issue_control_keys": sorted(controls), "diagnostic_negative_control_keys": sorted(controls),
        "diagnostic_supervision_role": "per-label verified controlled attribution; no-issue controls are separately available as negative data",
        "diagnostic_supervision_eligible_n": len(eligible), "diagnostic_supervision_eligible_keys": eligible, "diagnostic_supervision_by_label": eligible_by_label,
        "diagnostic_supervision_ineligible_reasons": dict(ineligible), "action_supervision_n": 0,
        "audit_complete": len(primary_keys) == 60 and len(pairs) == 15 and handled, "preparation_ready": len(pilot_rows) == 60 and len(second) == 15, "inference_ready": False,
        "blockers": (["complete all 60 primary human reviews"] if len(primary_keys) != 60 else []) + (["complete the 15-item blind-human subset with distinct primary identity"] if len(pairs) != 15 else []) + (["resolve/defer all audit conflicts"] if not handled else []) + ["prospective baseline, splits, corpus, budget, stability and verifier controls are not preregistered"],
        "population_estimate": False, "clean_heldout": False,
    }
    _write_json(pilot_dir / "audit-report.json", report)
    return report


def _write_protocol_docs() -> None:
    protocol, digest = load_protocol()
    taxonomy = _read_json(TAXONOMY_PATH)
    text = f"""# Diagnostic protocol v1 · annotation revision 4

Protocol: `{protocol['protocol_id']}` · SHA256 `{digest}` · `{REVIEW_SCHEMA_VERSION}` · `{RUBRIC_VERSION}`.

## Phạm vi và ba gate
Đo thiếu hụt và khả năng phục hồi trên tác vụ tiếng Việt. Không tự suy thành thiếu hụt do ngôn ngữ hoặc tri thức riêng Việt Nam. Đối chiếu ngôn ngữ cần task variant mới và bản dịch được kiểm tra.
`preparation_ready` là công cụ/packet offline; `audit_complete` là quy trình review/adjudication thật; `inference_ready` cần protocol prospective đã preregister đầy đủ. Chưa chạy inference từ module này.

## Audit đáp án và giả thuyết nguyên nhân
Bỏ trường Observation/Supported chung. Semantic correctness, gold validity và diagnostic outcome là phán đoán audit. `audit_evidence_kind` + `evidence_reference` ghi bằng chứng cho audit. `input_evidence_sufficiency` xét input model nhận; `corpus_evidence_availability` + tham chiếu riêng xét corpus được kiểm tra, không suy từ input.
`observed_issues` mô tả điều thấy trong artifact; `diagnostic_labels` là giả thuyết tùy chọn. Nguyên nhân chưa rõ có tập giả thuyết rỗng, không ép unknown; mixed được suy từ nhiều giả thuyết.
Mỗi giả thuyết có `diagnostic_support` riêng: hypothesis hoặc contrast_supported, tham chiếu và contrast_id. Human review/AI confidence không nâng cấp giả thuyết. contrast_supported chỉ được import khi contrast/replay đã đăng ký, khớp item/label và hash artifact được xác minh. Không phát hiện vấn đề có tập issue/cause rỗng, không phải chọn mức bằng chứng nguyên nhân.

## Review và provenance
Primary-60 có AI proposals trong draft riêng, không tự ký hoặc đặt trạng thái. Independent-15 không tải AI suggestions; cần human_only và blind self-attestation, reviewer khác primary. Báo cáo agreement ghi rõ AI-assisted-primary versus blind-human hay human-only-primary versus blind-human. ID browser là tự khai báo, không xác minh danh tính.
No-issue controls được giữ làm negative/control data riêng. Deferred/suspect/conflicting judgments không tạo causal supervision. Eligibility theo từng label: input thiếu không loại external_evidence_gap; reasoning cần đủ premises; retrieval cần corpus có evidence. Một adjudication 'resolved' không tự tạo nhãn huấn luyện mới.

## Prospective experiment trước khi inference
Historical B chỉ là audit anchor. Chạy B mới trong cùng campaign và model/control với S/K/KS. Tách đối chiếu cô lập nguyên nhân khỏi so sánh pipeline deployment. Khóa content/length/position controls; prompt/tool/compute controls; corpus; group splits; budget; replicate pairing; stability và verifier policy trước khi chạy.
Router dự đoán quality/cost để chọn arm; causal diagnosis là phân tích offline riêng. Đăng ký threshold, tie-break theo cost/latency và all-arm-failure/abstain; không ép action khi không arm thành công. 60*4*3 = 720 arm attempts, có thể nhiều hơn 720 model calls. Ba lần lặp chỉ là pilot; không tự chứng minh ổn định.
Verification phải nêu grounding/calculation/format scope, đánh giá false-accept/reject và coverage/abstention, tính tất cả chi phí probe/retrieval/tools/retries/verification; offline grading có thể dùng gold, runtime verifier không được dùng gold.

## Revision và vận hành
Giữ v1/v2/v3 snapshots, draft keys và human records. Revision 4 giữ 60 ordered anchors và 15 keys; không tự chuyển outcome/attestation cũ. Zustand store mới riêng v4; draft cũ của cùng reviewer/scope có thể tải để review lại.

```bash
.venv/bin/python code_benchmark/diagnostic.py revise-pilot-review --source-dir all_res/diagnostic_v1/pilot-review-v3 --output-dir all_res/diagnostic_v1/pilot-review-v4
.venv/bin/python code_benchmark/diagnostic.py import-review --pilot-dir all_res/diagnostic_v1/pilot-review-v4 --file <review-v4.csv> --annotator <reviewer-id>
```

Scorer, gold, prompt, denominators và source condition lịch sử bất biến. Corpus/endpoint/budget/splits/stability/verifier chưa chốt vẫn là blocker; không tạo con số bằng cách đoán.
"""
    (ROOT / "docs/research/diagnostic-v1-protocol.md").write_text(text, encoding="utf-8")
    lines = ["# Diagnostic annotation rubric v3 · review revision 4", "", "Audit đáp án dùng evidence kind/reference; giả thuyết nguyên nhân dùng support riêng. Observation/Supported không còn là dropdown chung.", "", "## Biểu hiện quan sát"]
    lines += [f"- `{r['id']}`: {r['name_vi']}" for r in taxonomy["observed_issues"]]
    lines += ["", "## Giả thuyết nguyên nhân"]
    for label in taxonomy["labels"]:
        lines += [f"### {label['id']}", label["definition"], f"**Contrast support requires:** {label['support_requires']}", label["caveat"], ""]
    lines += ["## Hướng dẫn quyết định", "", "- No observed issue: correct, gold valid, bằng chứng audit cụ thể; issue/cause/support rỗng. Không suy model không có latent gaps.", "- Issue observed: ít nhất một biểu hiện; có thể chưa có giả thuyết nguyên nhân. Mỗi giả thuyết có reference riêng, mặc định hypothesis.", "- Unresolved: deferred, giải thích bằng chứng thiếu/xung đột, không ép nhãn.", "- Input sufficiency và corpus availability khác nhau; corpus present/absent cần tham chiếu corpus riêng.", "- contrast_supported cần matching registered contrast, reviewed controls và hash artifact, không suy từ human signoff hoặc độ tự tin AI.", "- Reference nên ghi chính xác đoạn/câu hoặc phép tính; không xem prediction/gold match đơn thuần là causal evidence."]
    (ROOT / "docs/research/diagnostic-v1-rubric.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def _cmd_build(args: argparse.Namespace) -> None:
    report = build_ledger(args.source, output_dir=Path(args.output_root) if args.output_root else None)
    print(json.dumps({key: report.get(key) for key in (
        "source_run_id", "model_identity", "measurement_card_id", "manifest_sha256",
        "expected_observations", "prediction_observations", "score_observations",
        "ledger_status", "parity", "ledger_sha256",
    )}, ensure_ascii=False, indent=2))


def _cmd_pilot(args: argparse.Namespace) -> None:
    result = select_pilot(Path(args.ledger), output_dir=Path(args.output_dir) if args.output_dir else None)
    _write_protocol_docs()
    print(json.dumps({key: result.get(key) for key in (
        "protocol_id", "protocol_sha256", "source_run_id", "source_manifest_sha256",
        "source_ledger_sha256", "item_count", "second_review_count", "pilot_content_sha256",
        "population_estimate", "allocation",
    )}, ensure_ascii=False, indent=2))


def _cmd_revise_pilot(args: argparse.Namespace) -> None:
    selection = revise_pilot_review(Path(args.source_dir), Path(args.output_dir))
    _write_protocol_docs()
    print(json.dumps(selection, ensure_ascii=False, indent=2))


def _cmd_docs(args: argparse.Namespace) -> None:
    _write_protocol_docs()
    print(json.dumps({"protocol_guide": "docs/research/diagnostic-v1-protocol.md",
                      "rubric": "docs/research/diagnostic-v1-rubric.md"}, ensure_ascii=False, indent=2))


def _cmd_import(args: argparse.Namespace) -> None:
    result = import_review(Path(args.pilot_dir), Path(args.file), annotator_id=args.annotator)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_adjudicate(args: argparse.Namespace) -> None:
    result = add_adjudication(Path(args.pilot_dir), observation_key=args.observation_key, reviewer_id=args.reviewer,
                              decision=args.decision, rationale=args.rationale)
    print(json.dumps({"decision_count": len(result["decisions"]), "last_decision": result["decisions"][-1]}, ensure_ascii=False, indent=2))


def _cmd_report(args: argparse.Namespace) -> None:
    pilot_rows, _ = _read_pilot(Path(args.pilot_dir))
    report = _write_audit_report(Path(args.pilot_dir), pilot_rows)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _cmd_readiness(args: argparse.Namespace) -> None:
    dirs = [OUTPUT_ROOT / "sources" / value for value in args.source]
    report = readiness_report(ledger_dirs=dirs, audit_dir=Path(args.pilot_dir) if args.pilot_dir else None,
                              controls_path=Path(args.controls) if args.controls else None)
    if args.output:
        _write_json(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-ledger", help="Validate and project one declared source run offline")
    build.add_argument("--source", required=True)
    build.add_argument("--output-root")
    build.set_defaults(func=_cmd_build)
    pilot = commands.add_parser("prepare-pilot", help="Select the registered pilot from the anchor ledger")
    pilot.add_argument("--ledger", required=True)
    pilot.add_argument("--output-dir")
    pilot.set_defaults(func=_cmd_pilot)
    revise = commands.add_parser("revise-pilot-review", help="Preserve locked items while preparing the current annotation revision")
    revise.add_argument("--source-dir", required=True)
    revise.add_argument("--output-dir", required=True)
    revise.set_defaults(func=_cmd_revise_pilot)
    docs = commands.add_parser("write-docs", help="Generate the versioned protocol and Vietnamese annotation guide")
    docs.set_defaults(func=_cmd_docs)
    imp = commands.add_parser("import-review", help="Validate and append a human review CSV")
    imp.add_argument("--pilot-dir", required=True)
    imp.add_argument("--file", required=True)
    imp.add_argument("--annotator", required=True)
    imp.set_defaults(func=_cmd_import)
    adjudicate = commands.add_parser("adjudicate", help="Append an identified conflict resolution/deferment")
    adjudicate.add_argument("--pilot-dir", required=True)
    adjudicate.add_argument("--observation-key", required=True)
    adjudicate.add_argument("--reviewer", required=True)
    adjudicate.add_argument("--decision", choices=("resolved", "deferred"), required=True)
    adjudicate.add_argument("--rationale", required=True)
    adjudicate.set_defaults(func=_cmd_adjudicate)
    report = commands.add_parser("audit-report", help="Recompute audit coverage, agreement and readiness")
    report.add_argument("--pilot-dir", required=True)
    report.set_defaults(func=_cmd_report)
    readiness = commands.add_parser("readiness", help="Report preparation, audit, and inference gates")
    readiness.add_argument("--source", action="append", default=[])
    readiness.add_argument("--pilot-dir")
    readiness.add_argument("--controls", help=f"resolved prospective controls, e.g. {CONTROLS_PATH.relative_to(ROOT)}")
    readiness.add_argument("--output")
    readiness.set_defaults(func=_cmd_readiness)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (DiagnosticError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
