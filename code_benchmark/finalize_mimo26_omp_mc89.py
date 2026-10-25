"""Finalize MC-89: overlay parent + R1 + R2 attempts, score, and write the full Test submission.

User directive (2026-10-21): stop escalating timeouts; failed questions are
treated as the model returning an empty answer. They stay in the denominator
and will score wrong on the VMLU server. The submission therefore always has
all 9,833 Test rows: parsed answers for completed items, empty strings for
failed ones.

Completed answers are retained as-is, including the seven items whose final
attempt ran slightly past 1,800 s (the 1,800 s cutoff governs *further
chasing*, not retroactive discarding). See the finalization record for counts.

From the repository root:
  .venv/bin/python code_benchmark/finalize_mimo26_omp_mc89.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from code_benchmark import run_mimo26_omp_mc89 as mc89


ROOT = mc89.ROOT
PARENT_ROOT = mc89.OUTPUT_ROOT
FINAL_DIR = PARENT_ROOT / "final"
FINAL_OUT = FINAL_DIR / "vmlu" / mc89.PROFILE
SUBMISSION_DIR = ROOT / "submissions/mimo-v2-6-flash-omp-full-tools-mc89"
SUBMISSION_PATH = SUBMISSION_DIR / "submission.csv"
LEDGERS = (
    PARENT_ROOT / "attempts.jsonl",
    PARENT_ROOT / "recovery_mc89_1800s/attempts.jsonl",
    PARENT_ROOT / "recovery_mc89_r2/attempts.jsonl",
)
DATASET_LABELS = {
    "vi-multimodel-v1-vmlu-valid": "VMLU Valid",
    "vi-multimodel-v1-legal-nli-150": "Legal NLI",
    "vi-multimodel-v1-vi-squad-200": "Vi-SQuAD",
    "vi-multimodel-v1-vi-drop-200": "Vi-DROP",
    "vi-multimodel-v1-bidlqa-test": "ViBidLQA Test",
    "vi-multimodel-v2-vmlu-dev": "VMLU Dev",
    "vi-multimodel-v2-vmlu-test": "VMLU Test",
}
TEST_ID = "vi-multimodel-v2-vmlu-test"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    data, _main_rebuilt, vmlu_rebuilt, requests = mc89._load_inputs()
    mc89.ACTIVE_V2_REBUILT = vmlu_rebuilt
    data["main_keys"] = [item["run_key"] for item in requests if item["phase"] == "main"]
    data["vmlu_keys"] = [item["run_key"] for item in requests if item["phase"] == "vmlu"]

    rows: dict[str, dict] = {}
    for ledger in LEDGERS:
        for row in mc89.read_jsonl(ledger):
            run_key = str(row.get("run_key", ""))
            if not run_key:
                raise SystemExit(f"Error: ledger row without run_key in {ledger}")
            rows[run_key] = row
    expected = {item["run_key"] for item in requests}
    if set(rows) != expected:
        missing = expected - set(rows)
        raise SystemExit(f"Error: combined ledger is incomplete ({len(missing)} keys missing)")

    complete = [row for row in rows.values() if row["status"] == "complete"]
    failed = [row for row in rows.values() if row["status"] != "complete"]
    failed_test = [row for row in failed if row["dataset_id"] == TEST_ID]
    over_1800 = [row for row in complete if float(row["latency_s"]) > 1800]

    by_dataset: dict[str, dict[str, int]] = {}
    for dataset_id, label in DATASET_LABELS.items():
        dataset_rows = [row for row in rows.values() if row["dataset_id"] == dataset_id]
        by_dataset[dataset_id] = {
            "label": label,
            "expected": len(dataset_rows),
            "complete": sum(row["status"] == "complete" for row in dataset_rows),
            "failed": sum(row["status"] != "complete" for row in dataset_rows),
        }

    parent_condition = json.loads((PARENT_ROOT / "condition.json").read_text(encoding="utf-8"))
    parent_hash = mc89.v1.sha256_bytes(mc89.v1.canonical_json(parent_condition))
    recovery_hashes = {}
    for name, path in (
        ("r1_1800s", PARENT_ROOT / "recovery_mc89_1800s/condition.json"),
        ("r2_overrides", PARENT_ROOT / "recovery_mc89_r2/condition.json"),
    ):
        if path.is_file():
            recovery_hashes[name] = mc89.v1.sha256_bytes(
                mc89.v1.canonical_json(json.loads(path.read_text(encoding="utf-8")))
            )

    mc89.OUTPUT_ROOT = FINAL_DIR
    mc89.MAIN_OUT = FINAL_DIR / "main" / mc89.PROFILE
    mc89.VMLU_OUT = FINAL_OUT
    for phase, manifest in (("main", data["main_manifest"]), ("vmlu", data["vmlu_manifest"])):
        keys = data[f"{phase}_keys"]
        status = "complete" if all(rows.get(key, {}).get("status") == "complete" for key in keys) else "incomplete"
        mc89._write_phase_snapshot(phase, rows, keys, manifest, parent_hash, status)
    result = mc89._score_outputs(data, rows, parent_hash)

    test_rows = sorted(
        (row for row in rows.values() if row["dataset_id"] == TEST_ID),
        key=lambda row: row["item_id"],
    )
    if len(test_rows) != 9833 or len({row["item_id"] for row in test_rows}) != 9833:
        raise SystemExit("Error: VMLU Test key set differs from 9,833 unique items")
    answers = []
    for row in test_rows:
        if row["status"] == "complete":
            parsed = mc89.v2.parse_expanded_answer(vmlu_rebuilt[row["run_key"]], row["raw_response"])
            answer = str(parsed["prediction"])
        else:
            answer = ""
        answers.append({"id": row["item_id"], "answer": answer})
    empty_rows = sum(not item["answer"] for item in answers)

    FINAL_OUT.mkdir(parents=True, exist_ok=True)
    mc89.write_csv_atomic(FINAL_OUT / "submission_vmlu_test.csv", answers, ["id", "answer"])
    SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)
    SUBMISSION_PATH.write_bytes((FINAL_OUT / "submission_vmlu_test.csv").read_bytes())
    submission_sha = sha256(SUBMISSION_PATH)

    provenance = {
        "model_ref": mc89.MODEL_REF,
        "measurement_card": mc89.CARD_ID,
        "composition": "Parent 900s run, overlay of R1/C1 (1800s) and R2/C1 (per-group overrides); failed keys are submitted as empty answers",
        "source": str((FINAL_OUT / "submission_vmlu_test.csv").relative_to(ROOT)),
        "rows": len(answers),
        "empty_answer_rows": empty_rows,
        "parent_condition_sha256": parent_hash,
        "recovery_condition_sha256": recovery_hashes,
        "submission_sha256": submission_sha,
        "external_submission_performed": False,
    }
    mc89.atomic_json(SUBMISSION_DIR / "provenance.json", provenance)
    finalization = {
        "measurement_card_id": mc89.CARD_ID,
        "model_ref": mc89.MODEL_REF,
        "policy": "User directive 2026-10-21: do not chase items beyond 1,800 s; failed items are submitted as empty answers and score wrong server-side.",
        "coverage": {
            "expected": len(requests),
            "complete": len(complete),
            "failed": len(failed),
            "failed_test": len(failed_test),
            "by_dataset": by_dataset,
        },
        "completed_over_1800s_retained": [
            {"run_key": row["run_key"], "latency_s": row["latency_s"]} for row in sorted(over_1800, key=lambda row: row["run_key"])
        ],
        "failed_keys": sorted(row["run_key"] for row in failed),
        "failed_by_dataset": {
            DATASET_LABELS[dataset_id]: count
            for dataset_id, count in (
                (dataset_id, sum(row["dataset_id"] == dataset_id for row in failed))
                for dataset_id in DATASET_LABELS
            )
            if count
        },
        "submission": {
            "path": str(SUBMISSION_PATH.relative_to(ROOT)),
            "rows": len(answers),
            "empty_rows": empty_rows,
            "sha256": submission_sha,
        },
        "local_scores": {
            "main_summary": str((FINAL_DIR / "main" / mc89.PROFILE / "summary.json").relative_to(ROOT)),
            "vmlu_summary": str((FINAL_OUT / "summary.json").relative_to(ROOT)),
            "completed_n": result["completed_n"],
            "request_error_n": result["request_error_n"],
        },
        "parent_condition_sha256": parent_hash,
        "recovery_condition_sha256": recovery_hashes,
    }
    mc89.atomic_json(FINAL_DIR / "finalization.json", finalization)

    print(
        f"MC-89 finalized: complete={len(complete)}/{len(requests)} failed={len(failed)} "
        f"(Test empty answers={empty_rows}) submission={SUBMISSION_PATH.relative_to(ROOT)} "
        f"sha256={submission_sha}"
    )
    print("failed by dataset:", finalization["failed_by_dataset"])
    print("submission rows:", len(answers), "| empty:", empty_rows)


if __name__ == "__main__":
    sys.exit(main())
