"""Run MiMo V2.6 Flash through the MC-82 Responses adapter with separate MC-85 provenance.

From root: .venv/bin/python -m code_benchmark.run_mimo26_direct_20k_mc85 [--execute]
Uses the same API root as MC-82 and pins one MiMo V2.6 Flash route. Frozen prompts,
scorers, historical outputs, and completed generations remain unchanged.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from dotenv import dotenv_values
from openai import OpenAI

from code_benchmark import run_muse13_direct_mc80 as base
from code_benchmark import run_muse13_direct_20k_mc82 as adapter
from code_benchmark import run_muse13_direct_remaining_vmlu_mc81 as rest

ROOT = base.ROOT
MODEL = "ocg/mimo-v2.6-flash"
PROFILE = "mimo-v2-6-flash-direct-20k"
PROTOCOL = "mimo26-direct-default-20k-mc85-v1"
CARD_ID = "MC-85"
CARD = ROOT / "docs/measurement_cards/MC-85-mimo26-direct-20k.md"
OUTPUT = ROOT / "all_res/mimo26_direct_mc85"
BUDGET = 20000
SCHEDULER = "lane-work-stealing-v1"


def inputs():
    main_manifest, main_rebuilt, main_items = base.inputs()
    manifest, rebuilt, items, parent = rest.inputs()
    manifest = {**manifest, "protocol_id": PROTOCOL}
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = base.v1.sha256_bytes(base.v1.canonical_json(manifest))
    if len(main_items) != 2043 or len(items) != 10136:
        raise SystemExit("Error: MC-85 coverage drift")
    return [("main", main_manifest, main_rebuilt, main_items), ("vmlu", manifest, rebuilt, items)], parent


def condition(phase, manifest, endpoint):
    host = urlsplit(endpoint).hostname
    reference = json.loads((ROOT / "all_res/muse13_direct_mc82/vmlu/muse-spark-1-3-contributor-ocg-20k/condition.json").read_text())
    if base.v1.sha256_bytes(endpoint.encode()) != reference["base_url_sha256"]:
        raise SystemExit("Error: MC-85 API root differs from MC-82")
    value = {
        "model_id": MODEL, "model_ref": MODEL, "profile_id": PROFILE, "provider": "API Direct",
        "protocol_id": PROTOCOL, "protocol_version": 1, "phase": phase, "measurement_card_id": CARD_ID,
        "manifest_sha256": manifest["manifest_sha256"], "parent_manifest_sha256": manifest.get("parent_manifest_sha256"),
        "source_sha256": manifest["source_sha256"], "dataset_counts": manifest["dataset_counts"],
        "measurement_card_hash": base.v1.sha256_file(ROOT / "measurement_card.md"),
        "card_sha256": base.v1.sha256_file(CARD), "runner_sha256": base.v1.sha256_file(Path(__file__)),
        "shared_runner_sha256": base.v1.sha256_file(Path(base.__file__)),
        "request_adapter_sha256": base.v1.sha256_file(Path(adapter.__file__)),
        "base_url_sha256": base.v1.sha256_bytes(endpoint.encode()), "endpoint_host": host,
        "transport": "direct-api", "api_protocol": "openai-responses", "temperature_requested": 1.0,
        "temperature_effective": None, "reasoning_effort_sent": None,
        "reasoning_policy": "field omitted; provider default; effective effort unknown", "seed_sent": None,
        "tools": "none", "system_prompt": base.SYSTEM, "prompt_version": "vi-multimodel-prompt-v1",
        "max_tokens_mc": BUDGET, "max_tokens_reading": BUDGET, "request_timeout_seconds": 300,
        "sdk_retries": 0, "workers": 12, "shards": 4, "workers_per_shard": 3,
        "gateway_optout": {"header_name": "x-9router-token-saver", "value": "off"},
        "scorer_sha256": base.v1.sha256_file(ROOT / "code_benchmark" / (
            "score_vi_multimodel.py" if phase == "main" else "score_vi_multimodel_expansion.py")),
    }
    saved = OUTPUT / phase / PROFILE / "condition.json"
    if saved.exists():
        old = json.loads(saved.read_text())
        implementation = {"runner_sha256", "shared_runner_sha256", "request_adapter_sha256", "measurement_card_hash"}
        if {k: v for k, v in old.items() if k not in implementation} != {k: v for k, v in value.items() if k not in implementation}:
            raise SystemExit("Error: MC-85 resume would change frozen controls or sources")
        return old
    return value


def configure():
    base.MODEL, base.PROFILE, base.PROTOCOL, base.CARD_ID = MODEL, PROFILE, PROTOCOL, CARD_ID
    adapter.PROFILE, adapter.PROTOCOL = PROFILE, PROTOCOL
    base.request = request
    rest.PROFILE, rest.PROTOCOL = PROFILE, PROTOCOL


def request(client, item, shard, lane):
    row = adapter.response_request(client, item, shard, lane)
    row["measurement_card_id"] = CARD_ID
    return row


def score_main(output, manifest, rebuilt, rows, meta):
    base.score(output, manifest, rebuilt, rows, meta)
    summary = json.loads((output / "summary.json").read_text())
    summary["measurement_card_id"] = CARD_ID
    summary["cost_usd"] = None
    summary["cost_basis"] = "API tariff not supplied; reported usage retained"
    base.atomic_json(output / "summary.json", summary)


def source_valid(parent):
    folder = OUTPUT / "main" / PROFILE
    meta = json.loads((folder / "run.json").read_text())
    if meta["status"] != "complete" or meta["model_id"] != MODEL or meta["max_tokens_mc"] != BUDGET:
        raise SystemExit("Error: complete MC-85 main before VMLU")
    rows = {r["item_id"]: r for r in [json.loads(s) for s in (folder / "predictions.jsonl").read_text().splitlines()]
            if r["dataset_id"].endswith("-vmlu-valid")}
    refs = [r for r in parent["items"] if r["dataset_id"].endswith("-valid")]
    if len(rows) != 744 or any(r["item_id"] not in rows or rows[r["item_id"]]["status"] != "complete"
                             or rows[r["item_id"]]["prompt_sha256"] != r["prompt_sha256"] for r in refs):
        raise SystemExit("Error: MC-85 Valid coverage/prompt drift")
    return rows, meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    phases, _ = inputs()
    env = dotenv_values(ROOT / ".env")
    endpoint, key = env.get("9ROUTER_BASE_URL"), env.get("9ROUTER_API_KEY")
    if not endpoint or not key:
        raise SystemExit("Error: API endpoint credentials missing")
    configs = {phase: condition(phase, manifest, endpoint) for phase, manifest, _, _ in phases}
    print(f"preflight passed: ocg/mimo-v2.6-flash MC-85 12179 items 12 workers budget=20000 temperature=1 effort/seed=omitted scheduler={SCHEDULER}", flush=True)
    if not args.execute:
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / ".campaign.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Error: MC-85 campaign already running") from None
        configure()
        rest.source_valid = source_valid
        state = {"pid": os.getpid(), "status": "running", "started_at": base.now(), "steps": [],
                 "model_id": MODEL, "output_budget": BUDGET, "expected_n": 12179,
                 "execution_scheduler": SCHEDULER}
        base.atomic_json(OUTPUT / "campaign.json", state)
        with OpenAI(base_url=endpoint, api_key=key, timeout=300, max_retries=0,
                    default_headers={"x-9router-token-saver": "off"}) as client:
            for phase, manifest, rebuilt, items in phases:
                output = OUTPUT / phase / PROFILE
                for attempt in range(3):
                    saved = output / "run.json"
                    existing = json.loads(saved.read_text()) if saved.exists() else None
                    if existing and existing["status"] == "complete":
                        result = existing
                        break
                    state.update({"phase": phase, "recovery_pass": attempt, "updated_at": base.now(), "status": "running"})
                    if attempt:
                        state["status"] = "recovering"
                        base.atomic_json(OUTPUT / "campaign.json", state)
                        time.sleep(60)
                        state["status"] = "running"
                    base.atomic_json(OUTPUT / "campaign.json", state)
                    sources = output / "runner_sources"
                    sources.mkdir(parents=True, exist_ok=True)
                    adapter_hash = base.v1.sha256_file(Path(adapter.__file__))
                    (sources / f"{adapter_hash}.py").write_bytes(Path(adapter.__file__).read_bytes())
                    base.execute(output, manifest, rebuilt, items, configs[phase], client, bool(existing),
                                 score_callback=score_main if phase == "main" else rest.score,
                                 runner_path=Path(__file__), work_stealing=True)
                    result = json.loads(saved.read_text())
                    state["steps"].append({"phase": phase, "pass": attempt, "complete": result["complete_items"],
                                           "errors": result["request_error_items"], "at": base.now()})
                    if result["status"] in {"complete", "paused"}:
                        break
                if result["status"] != "complete":
                    state.update({"status": "needs_attention", "finished_at": base.now()})
                    base.atomic_json(OUTPUT / "campaign.json", state)
                    return
        state.update({"status": "complete", "finished_at": base.now()})
        base.atomic_json(OUTPUT / "campaign.json", state)


if __name__ == "__main__":
    main()
