"""Ledger adapter for the outputs of the prospective diagnostic campaign (openspec change
diagnostic-prospective-campaign, task 8.3).

`diagnostic.py build-ledger --source <id>` hands sources with adapter `campaign-arms-v1` to this module: the wide
run (MC-90), its two supplements (MC-91, MC-92) and the core run (MC-93). Offline: it never calls a model.

A ledger is written only when the source passes every check:

* The manifest's self-hash equals the registered hash. A fresh build of the same phase or supplement reproduces the
  manifest exactly, from the frozen main-v1 items, the campaign protocol, the prompt templates, the pilot anchors and,
  for core, the oracle and retrieved evidence.
* The parent main-v1 manifest and its frozen input files carry their registered hashes.
* run.json and summary.json name the registered card, model, manifest, phase and supplement, and the run is complete.
* Every prediction and score row belongs to the manifest and carries its prompt hash, and the prompt that was sent
  hashes to it. K and KS rows carry the retrieval trace that the evidence file gives.
* Re-scoring with the campaign scorer (`diagnostic_prospective.score_arm_rows`) reproduces every supplied score row
  and, per arm and dataset, the supplied summary at its recorded rounding.

Rows keep the fields of the V1 ledger and add the arm, the final-label scoring details and, for K and KS, the
retrieval trace. Two flags are added: `format_not_ok` (a final-label arm without a usable final-answer line) and
`at_token_cap` (the output used all of max_tokens; the endpoint still reports finish reason `stop` then).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic as diag
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic as diag
    import diagnostic_prospective as dp
    import vi_multimodel as v1

ROOT = diag.ROOT
METADATA_ALLOWLIST = diag.SOURCE_METADATA_ALLOWLIST | {
    "supplement_id", "max_tokens", "prompt_version", "final_segment_rule_id", "reasoning_policy", "api_protocol",
    "system_prompt", "tools", "campaign_protocol_sha256", "prompt_templates_sha256", "pilot_content_sha256",
    "evidence_sha256", "retrieval", "condition_sha256", "runner_sha256", "wrapper_sha256", "scorer_sha256",
    "started_at", "finished_at",
}
SCORE_FIELDS = ("prediction", "gold_answer", "prompt_sha256", "correct", "em", "token_f1", "legacy_raw_em",
                "legacy_raw_char_f1", "legacy_final_em", "legacy_final_char_f1", "arm", "format_ok",
                "markdown_final_line", "scoring_source", "scoring_response")
FORMAT_METRICS = ("format_ok_n", "format_compliance_pct", "markdown_final_line_n")
FROZEN_SCORER = ROOT / "code_benchmark" / "score_vi_multimodel.py"


def _error(source: dict[str, Any], message: str) -> diag.DiagnosticError:
    return diag.DiagnosticError(f"Error: {source['source_run_id']}: {message}")


def _self_hash_ok(manifest: dict[str, Any]) -> bool:
    unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return manifest.get("manifest_sha256") == v1.sha256_bytes(v1.canonical_json(unhashed))


def _check_manifest(manifest: dict[str, Any], source: dict[str, Any]) -> str:
    if not _self_hash_ok(manifest) or manifest["manifest_sha256"] != source["expected_manifest_sha256"]:
        raise _error(source, "manifest identity/hash mismatch")
    if manifest.get("protocol_id") != dp.PROTOCOL_ID or manifest.get("protocol_version") != 1:
        raise _error(source, "unsupported manifest protocol")
    if manifest.get("phase") != source["phase"] or manifest.get("supplement_id") != source["supplement_id"]:
        raise _error(source, "manifest phase or supplement differs from the registry")
    if manifest.get("parent_manifest_sha256") != source["expected_parent_manifest_sha256"]:
        raise _error(source, "parent manifest identity mismatch")
    rows = manifest.get("items", [])
    if manifest.get("n") != source["expected_n"] or len(rows) != source["expected_n"]:
        raise _error(source, "manifest coverage count mismatch")
    if len({diag._identity(row) for row in rows}) != len(rows):
        raise _error(source, "duplicate manifest identities")
    counts = Counter(str(row["dataset_id"]) for row in rows)
    if dict(counts) != {str(key): int(value) for key, value in manifest.get("dataset_counts", {}).items()}:
        raise _error(source, "manifest dataset coverage mismatch")
    if set(counts) != set(source["datasets"]):
        raise _error(source, "manifest dataset allowlist mismatch")
    return str(manifest["manifest_sha256"])


def _check_parent(source: dict[str, Any]) -> dict[str, str]:
    parent = diag._read_json(ROOT / source["parent_manifest_path"])
    if not _self_hash_ok(parent) or parent["manifest_sha256"] != source["expected_parent_manifest_sha256"]:
        raise _error(source, "parent manifest hash mismatch")
    return diag._check_source_hashes(parent, source["source_run_id"])


def _check_metadata(run: dict[str, Any], summary: dict[str, Any], source: dict[str, Any], manifest_sha: str) -> None:
    if run.get("status") != "complete" or run.get("complete_items") != source["expected_n"]:
        raise _error(source, "source run is not complete")
    registered = {"model_id": source["model_identity"], "measurement_card_id": source["measurement_card_id"],
                  "manifest_sha256": manifest_sha, "protocol_id": dp.PROTOCOL_ID, "phase": source["phase"],
                  "supplement_id": source["supplement_id"]}
    for name, value in registered.items():
        if run.get(name) != value or summary.get(name) != value:
            raise _error(source, f"run/summary {name} differs from the registered source")


def _rebuild(source: dict[str, Any], manifest: dict[str, Any]
             ) -> tuple[dict[str, v1.EvalItem], dict[str, dict[str, Any]], dict[str, Path]]:
    """Build the phase again from frozen inputs: (items by run key, K/KS traces by item key, evidence files)."""
    protocol = dp.load_protocol()
    templates = dp.load_templates()
    main_items = v1.rebuild_items(protocol["parent"]["manifest_phase"])
    files = {arm: ROOT / path for arm, path in (source.get("evidence") or {}).items()}
    evidence: dict[str, dict[str, list[dict[str, Any]]]] = {}
    traces: dict[str, dict[str, Any]] = {}
    if "O" in files:
        evidence["O"] = dp.load_oracle_evidence(files["O"], protocol, main_items)
    if "K" in files:
        evidence["K"], traces = dp.load_retrieved_evidence(files["K"], protocol, main_items)
        for key, trace in traces.items():
            block = dp.render_evidence_block(evidence["K"][key], templates)
            trace["evidence_block_sha256"] = v1.sha256_bytes(block.encode("utf-8"))
    supplement = (dp.load_supplement(dp.load_registration(), source["supplement_id"], protocol)
                  if source["supplement_id"] else None)
    rebuilt_manifest, items = dp.build_manifest(source["phase"], evidence_by_arm=evidence, main_items=main_items,
                                                supplement=supplement)
    if rebuilt_manifest != manifest:
        differing = sorted(key for key in set(rebuilt_manifest) | set(manifest)
                           if rebuilt_manifest.get(key) != manifest.get(key))
        raise _error(source, f"a fresh build of the phase differs from the frozen manifest in {differing}")
    dp.verify_manifest_rows(manifest, items)
    return items, traces, files


def _check_predictions(source: dict[str, Any], expected: dict[str, dict[str, Any]],
                       predictions: dict[str, dict[str, Any]], traces: dict[str, dict[str, Any]]) -> None:
    for key, row in predictions.items():
        if key != str(row.get("run_key")):
            raise _error(source, f"prediction run_key mismatch {key}")
        prompt_sha = expected[key]["prompt_sha256"]
        if row.get("prompt_sha256") != prompt_sha:
            raise _error(source, f"prompt hash mismatch for {key}")
        if row.get("status") == "complete":
            if not isinstance(row.get("raw_response"), str):
                raise _error(source, f"completed row lacks raw response {key}")
            if not isinstance(row.get("raw_prompt"), str) or v1.sha256_bytes(row["raw_prompt"].encode("utf-8")) != prompt_sha:
                raise _error(source, f"the prompt sent for {key} does not hash to its manifest prompt")
        arm = dp.arm_of_replicate(str(row["replicate_id"]))
        if row.get("arm") not in (None, arm):
            raise _error(source, f"row arm differs from its replicate id {key}")
        if arm in dp.RETRIEVAL_ARMS:
            if row.get("retrieval") != traces.get(dp.item_key(row["dataset_id"], row["item_id"])):
                raise _error(source, f"retrieval trace differs from the evidence file for {key}")
        elif row.get("retrieval") is not None:
            raise _error(source, f"retrieval trace on arm {arm} {key}")


def _check_scores(source: dict[str, Any], scores: dict[str, dict[str, Any]], predictions: dict[str, dict[str, Any]],
                  derived: dict[str, dict[str, Any]]) -> None:
    for key, row in scores.items():
        if key not in derived:
            raise _error(source, f"supplied score has no completed derived score: {key}")
        if str(row.get("raw_response", "")) != str(predictions.get(key, {}).get("raw_response", "")):
            raise _error(source, f"response mismatch between prediction/score {key}")
        for field in SCORE_FIELDS:
            if field in derived[key] and not diag._metric_equal(row.get(field), derived[key].get(field)):
                raise _error(source, f"{field} scorer parity failure for {key}")


def _check_summaries(source: dict[str, Any], summary: dict[str, Any],
                     derived: dict[str, dict[str, dict[str, Any]]], reading: set[str]
                     ) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str]]:
    """Per arm, the supplied dataset summaries and the reasons the source is incomplete; a mismatch fails."""
    supplied_arms = summary.get("arms")
    if not isinstance(supplied_arms, dict) or set(supplied_arms) != set(derived):
        raise _error(source, "summary arms differ from the frozen scorer")
    reading_scorer = diag._read_json(ROOT / "data" / "vi_multimodel_protocol_v1.json").get("scorer_version")
    supplied: dict[str, dict[str, dict[str, Any]]] = {}
    incomplete: list[str] = []
    for arm, by_dataset in derived.items():
        supplied[arm] = diag._summary_map({"datasets": supplied_arms[arm]})
        for dataset, row in supplied[arm].items():
            if row.get("arm") != arm:
                raise _error(source, f"summary of arm {arm} names arm {row.get('arm')} for {dataset}")
            if dataset in reading and row.get("scorer_version") != reading_scorer:
                raise _error(source, f"unsupported reading scorer for arm {arm} {dataset}")
        reasons = diag._validate_summary_parity(f"{source['source_run_id']} arm {arm}", supplied[arm], by_dataset)
        incomplete += [f"arm {arm}: {reason}" for reason in reasons]
        for dataset, actual in by_dataset.items():
            expected = supplied[arm][dataset]
            if expected.get("completed_n") != actual.get("completed_n"):
                continue  # already reported as incomplete
            for metric in FORMAT_METRICS:
                if not diag._metric_equal(expected.get(metric), actual.get(metric), rounded=True):
                    raise _error(source, f"{metric} summary parity failure for arm {arm} {dataset}")
    return supplied, incomplete


def build_source_ledger(source: dict[str, Any], *, protocol_path: Path = diag.PROTOCOL_PATH
                        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _, protocol_sha = diag.load_protocol(protocol_path)
    paths = diag._source_paths(source)
    for label, path in paths.items():
        if not path.is_file():
            raise _error(source, f"missing {label} artifact: {path}")
    manifest = diag._read_json(paths["manifest"])
    manifest_sha = _check_manifest(manifest, source)
    frozen_inputs = _check_parent(source)
    run, summary = diag._read_json(paths["run"]), diag._read_json(paths["summary"])
    _check_metadata(run, summary, source, manifest_sha)
    items, traces, evidence_files = _rebuild(source, manifest)
    recorded_records = (run.get("retrieval") or {}).get("records_sha256")
    if "K" in evidence_files and recorded_records != v1.sha256_file(evidence_files["K"]):
        raise _error(source, "the retrieved evidence file differs from the one the run recorded")

    prediction_rows, prediction_lines = diag._read_jsonl(paths["predictions"])
    score_rows, score_lines = diag._read_jsonl(paths["scores"])
    expected = {diag._identity(row): row for row in manifest["items"]}
    predictions = {diag._identity(row): row for row in prediction_rows}
    scores = {diag._identity(row): row for row in score_rows}
    unknown = (set(predictions) | set(scores)) - set(expected)
    if unknown:
        raise _error(source, f"artifact rows outside manifest: {sorted(unknown)[:4]}")
    _check_predictions(source, expected, predictions, traces)
    derived_rows, derived_summaries = dp.score_arm_rows(manifest, predictions, items)
    derived = {diag._identity(row): row for row in derived_rows}
    _check_scores(source, scores, predictions, derived)
    reading = {item.dataset_id for item in items.values() if item.task == "reading"}
    supplied, incomplete_reasons = _check_summaries(source, summary, derived_summaries, reading)
    if len(scores) != len(derived_rows):
        incomplete_reasons.append(f"scored-row coverage {len(scores)}/{len(derived_rows)} differs from frozen recomputation")

    condition = {key: run[key] for key in sorted(METADATA_ALLOWLIST) if key in run}
    result: list[dict[str, Any]] = []
    counts: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    for key, ref in expected.items():
        request = predictions.get(key)
        scored = scores.get(key)
        item = items[key]
        arm = dp.arm_of_replicate(str(ref["replicate_id"]))
        dataset = str(ref["dataset_id"])
        finish = str((request or {}).get("finish_reason", ""))
        complete = bool(request and request.get("status") == "complete" and finish not in {"error", "failed", "aborted"})
        if not request:
            status = "missing_request"
        elif not complete:
            status = str(request.get("status")) if request.get("status") != "complete" else f"finish_{finish or 'failed'}"
        elif not scored:
            status = "completed_unscored"
        else:
            status = "scored"
        tally = counts[dataset][arm]
        tally[status] += 1
        flags: list[str] = []
        if status != "scored":
            flags.append(status)
        if complete and item.task == "multiple_choice" and not str((scored or {}).get("prediction", "")):
            flags.append("unparsed")
        if finish == "length":
            flags.append("truncated")
        used, cap = (request or {}).get("completion_tokens"), (request or {}).get("max_tokens")
        if complete and isinstance(used, int) and isinstance(cap, int) and used >= cap:
            flags.append("at_token_cap")
        if scored and scored.get("format_ok") is False:
            flags.append("format_not_ok")
        if item.task == "multiple_choice" and scored and scored.get("correct") == 0:
            flags.append("incorrect_frozen_score")
        if item.task == "reading" and scored and scored.get("em") == 0:
            flags.append("em_zero_lexical_only")
            if float(scored.get("token_f1") or 0) >= 0.8:
                flags.append("em_zero_f1_high_review_candidate")
        if complete and not scored:
            flags.append("score_row_missing")
        for flag in ("unparsed", "truncated", "at_token_cap", "format_not_ok"):
            tally[flag] += flag in flags
        result.append({
            "observation_key": f"{source['source_run_id']}|{key}",
            "item_key": f"{dataset}:{ref['item_id']}",
            "source_run_id": source["source_run_id"],
            "source_manifest_sha256": manifest_sha,
            "model_identity": source["model_identity"],
            "measurement_card_id": source["measurement_card_id"],
            "condition": condition,
            "protocol_sha256": protocol_sha,
            "adapter_version": source["adapter"],
            "dataset_id": dataset,
            "source_dataset": ref.get("source_dataset"),
            "item_id": str(ref["item_id"]),
            "replicate_id": str(ref["replicate_id"]),
            "arm": arm,
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
            "source_metrics": {name: scored[name] for name in (
                "correct", "em", "token_f1", "legacy_raw_em", "legacy_raw_char_f1",
                "legacy_final_em", "legacy_final_char_f1",
            ) if scored and name in scored},
            "scoring": None if not scored else {
                "source": scored.get("scoring_source"), "format_ok": scored.get("format_ok"),
                "markdown_final_line": scored.get("markdown_final_line"),
                "final_segment": scored.get("scoring_response") if scored.get("scoring_source") == "final_segment" else None,
            },
            "retrieval": (request or {}).get("retrieval"),
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
                "prediction": {"path": str(paths["predictions"].relative_to(ROOT)), "line": prediction_lines.get(key)},
                "score": {"path": str(paths["scores"].relative_to(ROOT)), "line": score_lines.get(key)},
                "manifest": {"path": str(paths["manifest"].relative_to(ROOT)), "index": len(result)},
            },
        })
    coverage = {dataset: {arm: {"expected": dict(tally), "supplied_summary": supplied[arm].get(dataset)}
                          for arm, tally in sorted(by_arm.items())}
                for dataset, by_arm in sorted(counts.items())}
    input_files = [*paths.values(), ROOT / source["parent_manifest_path"], *evidence_files.values()]
    provenance = {
        "source_run_id": source["source_run_id"],
        "family": source["family"],
        "adapter": source["adapter"],
        "model_identity": source["model_identity"],
        "measurement_card_id": source["measurement_card_id"],
        "phase": source["phase"],
        "supplement_id": source["supplement_id"],
        "manifest_sha256": manifest_sha,
        "parent_manifest_sha256": source["expected_parent_manifest_sha256"],
        "protocol_sha256": protocol_sha,
        "campaign": {
            "protocol_sha256": manifest["campaign_protocol_sha256"],
            "prompt_templates_sha256": manifest["prompt_templates_sha256"],
            "pilot_content_sha256": manifest["pilot_content_sha256"],
            "evidence_sha256": manifest["evidence_sha256"],
            "manifest_rebuilt_from_frozen_inputs": True,
        },
        "scorer": {
            "frozen_scorer_sha256_at_run": run.get("scorer_sha256"),
            "frozen_scorer_sha256_now": v1.sha256_file(FROZEN_SCORER),
            "campaign_module_sha256_at_run": run.get("wrapper_sha256"),
            "campaign_module_sha256_now": v1.sha256_file(Path(dp.__file__)),
        },
        "source_file_sha256": diag._file_map_hashes(input_files),
        "frozen_input_sha256": frozen_inputs,
        "run_metadata": {
            "source_run_id": source["source_run_id"], "source_family": source["family"],
            "model_identity": source["model_identity"], "measurement_card_id": source["measurement_card_id"],
            "adapter": source["adapter"], "condition": condition,
        },
        "coverage": coverage,
        "expected_observations": len(expected),
        "prediction_observations": len(predictions),
        "score_observations": len(scores),
        "arm_observations": dict(sorted(Counter(row["arm"] for row in result).items())),
        "parity": {
            "item_score_parity": True,
            "summary_parity": not incomplete_reasons,
            "incomplete_reasons": sorted(set(incomplete_reasons)),
        },
        "ledger_status": "complete" if not incomplete_reasons else "source_incomplete",
    }
    return result, provenance
