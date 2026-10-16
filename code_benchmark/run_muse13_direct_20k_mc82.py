"""MC-82: 20,000 output tokens, native terminal-state handling, then full VMLU.

Run from root: .venv/bin/python -m code_benchmark.run_muse13_direct_20k_mc82 --execute
Keeps original MC-80 answers immutable; larger-budget recovery is a new condition.
"""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import time

from dotenv import dotenv_values
from openai import OpenAI

from code_benchmark import run_muse13_direct_mc80 as base
from code_benchmark import run_muse13_direct_remaining_vmlu_mc81 as rest

ROOT = base.ROOT
SOURCE = base.OUT
PROFILE = "muse-spark-1-3-contributor-ocg-20k"
PROTOCOL = "muse13-direct-default-20k-mc82-v1"
CARD = ROOT / "docs/measurement_cards/MC-82-muse13-direct-20k.md"
OUTPUT = ROOT / "all_res/muse13_direct_mc82"
BUDGET = 20000


def response_request(client, item, shard: int, lane: int) -> dict:
    row = {"run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}",
           "dataset_id": item.dataset_id, "item_id": item.item_id, "replicate_id": item.replicate_id,
           "profile_id": PROFILE, "protocol_id": PROTOCOL, "measurement_card_id": "MC-82",
           "model_id": base.MODEL, "transport": "direct-api", "api_protocol": "openai-responses",
           "shard": shard, "lane": lane, "prompt_sha256": base.v1.sha256_bytes(item.prompt.encode()),
           "raw_prompt": item.prompt, "raw_response": "", "temperature_sent": 1.0,
           "reasoning_effort_sent": None, "seed_sent": None, "max_tokens": BUDGET, "started_at": base.now()}
    start = time.monotonic()
    stream = None
    try:
        stream = client.responses.create(
            model=base.MODEL,
            input=[{"role": "system", "content": base.SYSTEM}, {"role": "user", "content": item.prompt}],
            temperature=1.0, max_output_tokens=BUDGET, stream=True,
        )
        terminal = None
        pieces = []
        for event in stream:
            data = event.model_dump()
            kind = data.get("type")
            if kind == "response.output_text.delta":
                pieces.append(data.get("delta") or "")
            if kind in {"response.completed", "response.incomplete", "response.failed"}:
                terminal = data.get("response")
                break
        if not isinstance(terminal, dict):
            raise ValueError("missing_terminal_event")
        visible = [part["text"] for output in terminal.get("output", []) if output.get("type") == "message"
                   for part in output.get("content", []) if part.get("type") == "output_text" and isinstance(part.get("text"), str)]
        text = "".join(visible) if visible else "".join(pieces)
        status = terminal.get("status")
        reason = (terminal.get("incomplete_details") or {}).get("reason")
        length = status == "incomplete" and reason == "max_output_tokens"
        tools = sum(output.get("type") == "function_call" for output in terminal.get("output", []))
        usage = terminal.get("usage") or {}
        row.update({"raw_response": text, "response_status": status, "incomplete_reason": reason,
                    "finish_reason": "length" if length else "stop" if status == "completed" else "error",
                    "status": "complete" if (status == "completed" or length) and not tools else "request_error",
                    "response_model_id": terminal.get("model"), "request_id": terminal.get("id"),
                    "tool_call_n": tools, "prompt_tokens": usage.get("input_tokens"),
                    "completion_tokens": usage.get("output_tokens"), "total_tokens": usage.get("total_tokens"),
                    "cached_prompt_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens"),
                    "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens")})
        if row["status"] != "complete":
            # Keep isolated upstream failures retryable. Never retain error messages:
            # upstream messages may contain credentials or echoed request data.
            code = str((terminal.get("error") or {}).get("code") or "unknown")
            permanent = code in {"invalid_api_key", "authentication_error", "permission_denied",
                                 "insufficient_quota", "billing_not_active", "model_not_found", "invalid_request_error"}
            row.update({"error_type": "provider_terminal_failure", "provider_error_code": code,
                        "fatal": bool(tools) or permanent})
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                    "http_status": status, "fatal": status in {400, 401, 402, 403, 404}})
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception as exc:
                row["stream_close_error"] = type(exc).__name__
    row.update({"latency_s": round(time.monotonic() - start, 4), "finished_at": base.now()})
    if row["status"] != "complete" and not row.get("fatal"):
        row["retry_wait_seconds"] = 60 if row.get("http_status") == 429 else 30 if row.get("http_status") == 503 else 5
    return row


def prepare() -> tuple[dict, dict, list, dict]:
    parent, rebuilt, items = base.inputs()
    source_rows = {r["run_key"]: r for r in [json.loads(s) for s in (SOURCE / "predictions.jsonl").read_text().splitlines()]}
    folder = OUTPUT / "recovery" / PROFILE
    saved = folder / "source_manifest.json"
    if saved.exists():
        manifest = json.loads(saved.read_text())
        claimed = manifest.get("manifest_sha256")
        if claimed != base.v1.sha256_bytes(base.v1.canonical_json({k: v for k, v in manifest.items() if k != "manifest_sha256"})):
            raise SystemExit("Error: recovery manifest hash drift")
        if manifest.get("parent_manifest_sha256") != parent["manifest_sha256"]:
            raise SystemExit("Error: recovery parent manifest drift")
        keys = {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}" for r in manifest["items"]}
    else:
        keys = {key for key, row in source_rows.items() if row["status"] != "complete"}
        refs = [ref for ref in parent["items"] if f"{ref['dataset_id']}:{ref['item_id']}:{ref['replicate_id']}" in keys]
        manifest = {"protocol_id": PROTOCOL, "phase": "recovery", "n": len(refs), "items": refs,
                    "parent_manifest_sha256": parent["manifest_sha256"], "source_sha256": parent["source_sha256"],
                    "dataset_counts": dict(Counter(r["dataset_id"] for r in refs))}
        manifest["manifest_sha256"] = base.v1.sha256_bytes(base.v1.canonical_json(manifest))
    if not keys or not keys.issubset(source_rows) or any(source_rows[key]["status"] == "complete" for key in keys):
        raise SystemExit("Error: recovery must target only original unfinished MC-80 keys")
    chosen = [item for item in items if item.run_key in keys]
    return manifest, rebuilt, chosen, parent


def condition(phase: str, manifest: dict) -> dict:
    value = json.loads((SOURCE / "condition.json").read_text())
    value.update({"protocol_id": PROTOCOL, "phase": phase, "profile_id": PROFILE, "measurement_card_id": "MC-82",
                  "measurement_card_hash": base.v1.sha256_file(ROOT / "measurement_card.md"),
                  "card_sha256": base.v1.sha256_file(CARD), "api_protocol": "openai-responses",
                  "max_tokens_mc": BUDGET, "max_tokens_reading": BUDGET, "manifest_sha256": manifest["manifest_sha256"],
                  "source_sha256": manifest["source_sha256"], "dataset_counts": manifest["dataset_counts"],
                  "parent_manifest_sha256": manifest.get("parent_manifest_sha256"),
                  "parent_protocol_id": "vi-multimodel-expansion-v2" if phase == "vmlu" else "vi-multimodel-v1",
                  "scorer_sha256": base.v1.sha256_file(Path(rest.scorer.__file__)) if phase == "vmlu" else base.v1.sha256_file(ROOT / "code_benchmark/score_vi_multimodel.py"),
                  "source_mc80_predictions_sha256": base.v1.sha256_file(SOURCE / "predictions.jsonl"),
                  "runner_sha256": base.v1.sha256_file(Path(__file__)),
                  "shared_runner_sha256": base.v1.sha256_file(Path(base.__file__))})
    output = OUTPUT / phase / PROFILE
    if (output / "condition.json").exists():
        old = json.loads((output / "condition.json").read_text())
        ignored = {"runner_sha256", "shared_runner_sha256", "measurement_card_hash"}
        if {k: v for k, v in value.items() if k not in ignored} != {k: v for k, v in old.items() if k not in ignored}:
            raise SystemExit("Error: larger-budget resume would change frozen inputs or controls")
        return old
    return value


def score_recovery(output: Path, manifest: dict, rebuilt: dict, rows: dict, meta: dict) -> None:
    scored, _ = base.score_rows(manifest, rows, rebuilt)
    base.v1.write_jsonl_atomic(output / "scores.jsonl", scored)
    base.atomic_json(output / "summary.json", {"protocol_id": PROTOCOL, "measurement_card_id": "MC-82",
                    "phase": "recovery", "expected_n": len(manifest["items"]),
                    "completed_n": sum(r["status"] == "complete" for r in rows.values()),
                    "truncated_n": sum(r.get("finish_reason") == "length" for r in rows.values()),
                    "selection": "previously unfinished MC-80 items; not a population score"})


def combined_mc80(parent: dict, rebuilt: dict) -> tuple[dict, dict]:
    old = {r["run_key"]: r for r in [json.loads(s) for s in (SOURCE / "predictions.jsonl").read_text().splitlines()]}
    output = OUTPUT / "recovery" / PROFILE
    recovery = {r["run_key"]: r for r in [json.loads(s) for s in (output / "predictions.jsonl").read_text().splitlines()]}
    merged = {**old, **recovery}
    if len(merged) != 2043 or any(r["status"] != "complete" for r in merged.values()):
        raise SystemExit("Error: remaining VMLU awaits complete recovery outcomes")
    base.v1.write_jsonl_atomic(OUTPUT / "mc80_combined_predictions.jsonl", list(merged.values()))
    scores, summaries = base.score_rows(parent, merged, rebuilt)
    base.v1.write_jsonl_atomic(OUTPUT / "mc80_combined_scores.jsonl", scores)
    base.atomic_json(OUTPUT / "mc80_combined_summary.json", {"conditions": ["MC-80", "MC-82"],
                    "mixed_output_budgets": True, "rank_eligible": False,
                    "note": "Original results plus selected 20k recovery; descriptive combined scores only",
                    "datasets": list(summaries.values()), "generated_at": base.now()})
    valid = {r["item_id"]: r for r in merged.values() if r["dataset_id"].endswith("-vmlu-valid")}
    if len(valid) != 744:
        raise SystemExit("Error: missing original Valid outputs")
    return valid, json.loads((SOURCE / "run.json").read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    recovery_manifest, recovery_map, recovery_items, parent = prepare()
    vmlu_manifest, vmlu_map, vmlu_items, _ = rest.inputs()
    vmlu_manifest = {**vmlu_manifest, "protocol_id": PROTOCOL}
    vmlu_manifest.pop("manifest_sha256")
    vmlu_manifest["manifest_sha256"] = base.v1.sha256_bytes(base.v1.canonical_json(vmlu_manifest))
    print(f"preflight passed: recovery={len(recovery_items)} remaining_vmlu=10136 output_budget=20000 workers=12", flush=True)
    if not args.execute:
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / ".campaign.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Error: MC-82 campaign already running") from None
        state = {"pid": os.getpid(), "status": "running", "started_at": base.now(), "output_budget": BUDGET, "steps": []}
        base.atomic_json(OUTPUT / "campaign.json", state)
        base.PROTOCOL, base.CARD_ID, base.PROFILE, base.request = PROTOCOL, "MC-82", PROFILE, response_request
        env = dotenv_values(ROOT / ".env")
        original = json.loads((SOURCE / "condition.json").read_text())
        endpoint, key = env.get("9ROUTER_BASE_URL"), env.get("9ROUTER_API_KEY")
        if not endpoint or not key or base.v1.sha256_bytes(endpoint.encode()) != original["base_url_sha256"]:
            raise SystemExit("Error: 9Router endpoint missing or changed")
        with OpenAI(base_url=endpoint, api_key=key, timeout=300.0, max_retries=0,
                    default_headers={"x-9router-token-saver": "off"}) as client:
            phases = [("recovery", recovery_manifest, recovery_map, recovery_items, score_recovery),
                      ("vmlu", vmlu_manifest, vmlu_map, vmlu_items, rest.score)]
            for phase, manifest, rebuilt, items, callback in phases:
                if phase == "vmlu":
                    valid, source_meta = combined_mc80(parent, recovery_map)
                    rest.PROTOCOL, rest.PROFILE = PROTOCOL, PROFILE
                    rest.source_valid = lambda parent, valid=valid, source_meta=source_meta: (valid, source_meta)
                output = OUTPUT / phase / PROFILE
                config = condition(phase, manifest)
                for attempt in range(3):
                    existing = json.loads((output / "run.json").read_text()) if (output / "run.json").exists() else None
                    if existing and existing["status"] == "complete":
                        result = existing
                        break
                    if attempt:
                        state.update({"status": "recovering", "retry_after_seconds": 60, "updated_at": base.now()})
                        base.atomic_json(OUTPUT / "campaign.json", state)
                        print("technical failures retained; recovery starts after 60 seconds", flush=True)
                        time.sleep(60)
                    state.pop("retry_after_seconds", None)
                    state["status"] = "running"
                    state.update({"phase": phase, "recovery_pass": attempt, "updated_at": base.now()})
                    base.atomic_json(OUTPUT / "campaign.json", state)
                    base.execute(output, manifest, rebuilt, items, config, client, bool(existing),
                                 score_callback=callback, runner_path=Path(__file__))
                    result = json.loads((output / "run.json").read_text())
                    state["steps"].append({"phase": phase, "pass": attempt, "complete": result["complete_items"],
                                           "errors": result["request_error_items"], "at": base.now()})
                    if result["status"] == "complete":
                        break
                    if result["status"] == "paused":
                        break
                if result["status"] != "complete":
                    state.update({"status": "needs_attention", "phase": phase, "finished_at": base.now()})
                    base.atomic_json(OUTPUT / "campaign.json", state)
                    return
            state.update({"status": "complete", "finished_at": base.now()})
            base.atomic_json(OUTPUT / "campaign.json", state)


if __name__ == "__main__":
    main()
