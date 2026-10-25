"""MC-81: remaining VMLU Dev/Test after MC-80 Valid, same direct API controls.

Run from root with .venv/bin/python -m code_benchmark.run_muse13_direct_remaining_vmlu_mc81.
Use --execute after MC-80 is complete; --resume preserves every completed answer.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from dotenv import dotenv_values
from openai import OpenAI

from code_benchmark import run_muse13_direct_mc80 as direct
from code_benchmark import score_vi_multimodel_expansion as scorer
from code_benchmark import vi_multimodel_expansion as v2
from code_benchmark.common import write_csv_atomic

ROOT = direct.ROOT
SOURCE = direct.OUT
PROFILE = "muse-spark-1-3-contributor-ocg"
OUT = ROOT / "all_res/muse13_direct_mc81/vmlu" / PROFILE
PROTOCOL = "muse13-direct-default-remaining-vmlu-mc81-v1"
CARD = ROOT / "docs/measurement_cards/MC-81-muse13-direct-remaining-vmlu.md"


def inputs() -> tuple[dict, dict, list, dict]:
    parent = v2.load_manifest("vmlu")
    rebuilt = v2.rebuild_items("vmlu")
    all_items = [v2.item_from_manifest_row(row, rebuilt) for row in parent["items"]]
    previous = {item.item_id: item for item in direct.inputs()[2] if item.dataset_id.endswith("-vmlu-valid")}
    valid = [item for item in all_items if item.dataset_id.endswith("-valid")]
    if len(valid) != 744 or {item.item_id for item in valid} != set(previous):
        raise SystemExit("Error: MC-80 and V2 Valid identities differ")
    if any(item.prompt != previous[item.item_id].prompt for item in valid):
        raise SystemExit("Error: MC-80 and V2 Valid prompt bytes differ")
    items = [item for item in all_items if not item.dataset_id.endswith("-valid")]
    counts = dict(Counter(item.dataset_id for item in items))
    if counts != {"vi-multimodel-v2-vmlu-dev": 303, "vi-multimodel-v2-vmlu-test": 9833}:
        raise SystemExit("Error: remaining VMLU must be Dev 303 + Test 9,833")
    refs = [row for row in parent["items"] if not row["dataset_id"].endswith("-valid")]
    manifest = {"protocol_id": PROTOCOL, "phase": "vmlu", "n": len(items), "dataset_counts": counts,
                "parent_manifest_sha256": parent["manifest_sha256"], "source_sha256": parent["source_sha256"], "items": refs}
    manifest["manifest_sha256"] = direct.v1.sha256_bytes(direct.v1.canonical_json(manifest))
    return manifest, rebuilt, items, parent


def source_valid(parent: dict) -> tuple[dict, dict]:
    meta = json.loads((SOURCE / "run.json").read_text())
    if meta.get("status") != "complete" or meta.get("complete_items") != 2043:
        raise SystemExit("Error: finish MC-80 before starting remaining VMLU")
    if meta.get("model_id") != direct.MODEL or meta.get("temperature_requested") != 1.0 or meta.get("reasoning_effort_sent") is not None:
        raise SystemExit("Error: MC-80 source controls differ")
    rows = {r["item_id"]: r for r in [json.loads(s) for s in (SOURCE / "predictions.jsonl").read_text().splitlines()]
            if r["dataset_id"].endswith("-vmlu-valid")}
    refs = [r for r in parent["items"] if r["dataset_id"].endswith("-valid")]
    if len(rows) != 744 or any(r["item_id"] not in rows or rows[r["item_id"]]["status"] != "complete"
                             or rows[r["item_id"]]["prompt_sha256"] != r["prompt_sha256"] for r in refs):
        raise SystemExit("Error: MC-80 Valid coverage/prompt provenance is incomplete")
    return rows, meta


def score(output: Path, manifest: dict, rebuilt: dict, rows: dict, meta: dict) -> None:
    # Reuse the frozen V2 scorer via its existing phase/profile boundary.
    scorer.OUTPUT_DIR = output.parent.parent
    scorer.PROTOCOL_ID = PROTOCOL
    scorer.load_manifest = lambda phase: manifest
    scorer.load_profiles = lambda: {PROFILE: {"model_id": direct.MODEL}}
    scorer.rebuild_items = lambda phase: rebuilt
    summary = scorer.score_profile("vmlu", PROFILE, allow_incomplete=True)
    summary.update({"protocol_version": meta["protocol_version"], "scorer_protocol_version": 2,
                    "transport": "direct-api", "condition_sha256": meta["condition_sha256"],
                    "cost_usd": None, "cost_basis": "9Router tariff unknown; token usage retained"})
    direct.atomic_json(output / "summary.json", summary)
    parent = v2.load_manifest("vmlu")
    valid, source_meta = source_valid(parent)
    combined = []
    for ref in parent["items"]:
        key = f"{ref['dataset_id']}:{ref['item_id']}:{ref['replicate_id']}"
        if ref["dataset_id"].endswith("-valid"):
            original = valid[ref["item_id"]]
            row = {**original, "source_run_key": original["run_key"], "run_key": key,
                   "dataset_id": ref["dataset_id"], "source_condition_sha256": source_meta["condition_sha256"]}
        else:
            row = rows.get(key, {"run_key": key, "dataset_id": ref["dataset_id"], "item_id": ref["item_id"],
                                 "replicate_id": ref["replicate_id"], "status": "missing"})
        combined.append(row)
    direct.v1.write_jsonl_atomic(output / "vmlu_full_predictions.jsonl", combined)
    test = [r for r in combined if r["dataset_id"].endswith("-test")]
    if len(test) == 9833 and all(r["status"] == "complete" for r in test):
        answers = [{"id": r["item_id"], "answer": v2.parse_expanded_answer(rebuilt[r["run_key"]], r["raw_response"])["prediction"]}
                   for r in test]
        write_csv_atomic(output / "submission_vmlu_test.csv", answers, ["id", "answer"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    manifest, rebuilt, items, parent = inputs()
    print("preflight=passed Valid parity=744 remaining=10136 Dev=303 Test=9833 workers=12 endpoint_calls=0", flush=True)
    if not args.execute:
        return
    _, source_meta = source_valid(parent)
    direct.PROTOCOL, direct.CARD_ID, direct.PROFILE = PROTOCOL, "MC-81", PROFILE
    condition = json.loads((SOURCE / "condition.json").read_text())
    condition.update({"protocol_id": PROTOCOL, "phase": "vmlu", "profile_id": PROFILE, "measurement_card_id": "MC-81",
                      "measurement_card_hash": direct.v1.sha256_file(ROOT / "measurement_card.md"),
                      "card_sha256": direct.v1.sha256_file(CARD), "manifest_sha256": manifest["manifest_sha256"],
                      "parent_protocol_id": parent["protocol_id"], "parent_manifest_sha256": parent["manifest_sha256"],
                      "source_sha256": parent["source_sha256"], "dataset_counts": manifest["dataset_counts"],
                      "source_mc80_condition_sha256": source_meta["condition_sha256"],
                      "source_mc80_predictions_sha256": direct.v1.sha256_file(SOURCE / "predictions.jsonl"),
                      "runner_sha256": direct.v1.sha256_file(Path(__file__)),
                      "shared_runner_sha256": direct.v1.sha256_file(Path(direct.__file__)),
                      "scorer_sha256": direct.v1.sha256_file(Path(scorer.__file__))})
    if args.resume and (OUT / "condition.json").exists():
        frozen = json.loads((OUT / "condition.json").read_text())
        ignored = {"runner_sha256", "shared_runner_sha256", "measurement_card_hash"}
        if {k: v for k, v in condition.items() if k not in ignored} != {k: v for k, v in frozen.items() if k not in ignored}:
            raise SystemExit("Error: MC-81 resume changes inference/input controls")
        condition = frozen
    env = dotenv_values(ROOT / ".env")
    endpoint, key = env.get("9ROUTER_BASE_URL"), env.get("9ROUTER_API_KEY")
    if not endpoint or not key or direct.v1.sha256_bytes(endpoint.encode()) != condition["base_url_sha256"]:
        raise SystemExit("Error: endpoint missing or differs from MC-80")
    with OpenAI(base_url=endpoint, api_key=key, timeout=300.0, max_retries=0,
                default_headers={"x-9router-token-saver": "off"}) as client:
        direct.execute(OUT, manifest, rebuilt, items, condition, client, args.resume,
                       score_callback=score, runner_path=Path(__file__))


if __name__ == "__main__":
    main()
