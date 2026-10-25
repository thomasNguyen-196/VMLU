"""Build audited VMLU and V-Bench upload files from expansion-v2 checkpoints.

No score is inferred locally for withheld-gold tracks. Run from repo root:
  .venv/bin/python code_benchmark/export_vi_multimodel_submissions.py --profile <id> [--only-vmlu]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from code_benchmark.vi_multimodel import canonical_json, write_jsonl_atomic
    from code_benchmark.vi_multimodel_expansion import OUTPUT_DIR, load_manifest, load_profiles
except ImportError:
    from vi_multimodel import canonical_json, write_jsonl_atomic
    from vi_multimodel_expansion import OUTPUT_DIR, load_manifest, load_profiles

ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_profile(profile_id: str, *, only_vmlu: bool = False) -> Path:
    profiles = load_profiles()
    if profile_id not in profiles:
        raise SystemExit(f"Error: unknown profile {profile_id}")
    vmlu_manifest = load_manifest("vmlu")
    vbench_manifest = None if only_vmlu else load_manifest("vbench")
    vmlu_dir = OUTPUT_DIR / "vmlu" / profile_id
    vbench_dir = OUTPUT_DIR / "vbench" / profile_id
    output_dir = ROOT / "submissions" / "vi_multimodel_v2" / profile_id
    output_dir.mkdir(parents=True, exist_ok=True)

    missing_predictions = []
    local_invalid = []
    vmlu_rows = []
    vmlu_predictions = {
        str(row["item_id"]): row
        for row in (json.loads(line) for line in (vmlu_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
        if row.get("dataset_id") == "vi-multimodel-v2-vmlu-test"
    }
    test_refs = [row for row in vmlu_manifest["items"] if row["dataset_id"] == "vi-multimodel-v2-vmlu-test"]
    for ref in test_refs:
        item_id = str(ref["item_id"])
        prediction = vmlu_predictions.get(item_id)
        if not prediction or prediction.get("status") != "complete":
            missing_predictions.append({"benchmark": "vmlu_test", "id": item_id, "reason": "request_incomplete"})
            answer = ""
        else:
            answer = str(prediction.get("prediction", "")).strip().upper()
            if answer not in {"A", "B", "C", "D", "E"}:
                local_invalid.append({"benchmark": "vmlu_test", "id": item_id, "reason": "unparsed_or_invalid_letter"})
                answer = ""
        vmlu_rows.append({"id": item_id, "answer": answer})
    if len(vmlu_rows) != 9833:
        raise SystemExit(f"Error: VMLU test export must preserve all 9,833 IDs, got {len(vmlu_rows)}")
    vmlu_path = output_dir / "submission_vmlu_test.csv"
    _write_csv(vmlu_path, vmlu_rows, ["id", "answer"])

    if only_vmlu:
        audit_path = output_dir / "omitted_items.csv"
        _write_csv(audit_path, missing_predictions + local_invalid, ["benchmark", "id", "reason"])
        run_vmlu = json.loads((vmlu_dir / "run.json").read_text(encoding="utf-8"))
        metadata = {
            "protocol_id": "vi-multimodel-expansion-v2",
            "profile_id": profile_id,
            "vmlu_manifest_sha256": vmlu_manifest["manifest_sha256"],
            "vmlu_card_id": run_vmlu.get("measurement_card_id"),
            "vmlu_card_hash": run_vmlu.get("measurement_card_hash"),
            "vmlu_expected_test_n": len(test_refs),
            "vmlu_submission_n": len(vmlu_rows),
            "vmlu_blank_n": sum(not row["answer"] for row in vmlu_rows),
            "files": {
                vmlu_path.name: _file_hash(vmlu_path),
                audit_path.name: _file_hash(audit_path),
            },
            "submission_ready": not missing_predictions,
            "missing_prediction_n": len(missing_predictions),
            "model_invalid_n": len(local_invalid),
            "server_score_status": "not_submitted",
        }
        manifest_path = output_dir / "submission_manifest.json"
        tmp = manifest_path.with_suffix(".json.tmp")
        tmp.write_bytes(canonical_json(metadata) + b"\n")
        tmp.replace(manifest_path)
        print(f"wrote VMLU-only upload files under {output_dir}")
        print(f"vmlu_test={len(vmlu_rows)} rows, blank={metadata['vmlu_blank_n']}")
        print(f"submission_ready={metadata['submission_ready']}; server_score_status=not_submitted")
        return output_dir

    vbench_predictions = {
        str(row["item_id"]): row
        for row in (json.loads(line) for line in (vbench_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    }
    vbench_expected = len(vbench_manifest["items"])
    submissions: dict[str, list[dict[str, Any]]] = {"mc": [], "agentic": []}
    for ref in vbench_manifest["items"]:
        item_id = str(ref["item_id"])
        prediction = vbench_predictions.get(item_id)
        track = str(ref["dataset_id"]).rsplit("-", 1)[-1]
        if not prediction or prediction.get("status") != "complete":
            missing_predictions.append({"benchmark": f"vbench_{track}", "id": item_id, "reason": "request_incomplete"})
            continue
        answer = prediction.get("prediction", "")
        if not prediction.get("parse_valid") or not answer:
            local_invalid.append({"benchmark": f"vbench_{track}", "id": item_id, "reason": "model_output_unparseable_or_schema_invalid"})
            continue
        if track == "mc":
            value: Any = str(answer)
        elif track == "agentic":
            try:
                value = json.loads(str(answer))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Error: scored agentic prediction is not JSON for V-Bench id={item_id}") from exc
        else:
            raise SystemExit(f"Error: unexpected V-Bench dataset track in manifest: {track}")
        submissions[track].append({"id": int(item_id), "answer": value})

    vbench_paths = {}
    for track, rows in submissions.items():
        rows.sort(key=lambda row: row["id"])
        path = output_dir / f"submission_vbench_{track}.jsonl"
        write_jsonl_atomic(path, rows)
        vbench_paths[track] = path
    combined = sorted(submissions["mc"] + submissions["agentic"], key=lambda row: row["id"])
    combined_path = output_dir / "submission_vbench_all.jsonl"
    write_jsonl_atomic(combined_path, combined)

    audit_path = output_dir / "omitted_items.csv"
    omitted = missing_predictions + local_invalid
    _write_csv(audit_path, omitted, ["benchmark", "id", "reason"])
    run_vmlu = json.loads((vmlu_dir / "run.json").read_text(encoding="utf-8"))
    run_vbench = json.loads((vbench_dir / "run.json").read_text(encoding="utf-8"))
    metadata = {
        "protocol_id": "vi-multimodel-expansion-v2",
        "profile_id": profile_id,
        "vmlu_manifest_sha256": vmlu_manifest["manifest_sha256"],
        "vmlu_card_id": run_vmlu.get("measurement_card_id"),
        "vmlu_card_hash": run_vmlu.get("measurement_card_hash"),
        "vmlu_expected_test_n": len(test_refs),
        "vmlu_submission_n": len(vmlu_rows),
        "vmlu_blank_n": sum(not row["answer"] for row in vmlu_rows),
        "vbench_manifest_sha256": vbench_manifest["manifest_sha256"],
        "vbench_card_id": run_vbench.get("measurement_card_id"),
        "vbench_card_hash": run_vbench.get("measurement_card_hash"),
        "vbench_expected_scorable_n": vbench_expected,
        "vbench_parse_valid_n": len(combined),
        "vbench_omitted_n": vbench_expected - len(combined),
        "files": {
            vmlu_path.name: _file_hash(vmlu_path),
            **{path.name: _file_hash(path) for path in vbench_paths.values()},
            combined_path.name: _file_hash(combined_path),
            audit_path.name: _file_hash(audit_path),
        },
        "submission_ready": not missing_predictions,
        "missing_prediction_n": len(missing_predictions),
        "model_invalid_n": len(local_invalid),
        "server_score_status": "not_submitted",
    }
    manifest_path = output_dir / "submission_manifest.json"
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_bytes(canonical_json(metadata) + b"\n")
    tmp.replace(manifest_path)
    print(f"wrote upload files under {output_dir}")
    print(f"vmlu_test={len(vmlu_rows)} rows, blank={metadata['vmlu_blank_n']}")
    print(f"vbench_scorable={vbench_expected}, uploadable={len(combined)}, omitted={metadata['vbench_omitted_n']}")
    print(f"submission_ready={metadata['submission_ready']}; server_score_status=not_submitted")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Export expansion-v2 submission files for one model profile.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--only-vmlu", action="store_true",
                        help="export only the withheld-gold VMLU test CSV; do not read or write V-Bench files")
    args = parser.parse_args()
    export_profile(args.profile, only_vmlu=args.only_vmlu)


if __name__ == "__main__":
    main()
