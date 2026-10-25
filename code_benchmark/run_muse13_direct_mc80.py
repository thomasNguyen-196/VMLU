"""MC-80: direct 9Router requests over the frozen six-dataset main manifest.

Keeps the OMP inputs/scorers reusable while recording a separate HTTP condition.
Run from root: .venv/bin/python code_benchmark/run_muse13_direct_mc80.py --execute
Resume only missing/technical failures: add --resume. Completed outputs, including
unparsed and length-limited answers, are never retried automatically.
"""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import queue
import threading
import time
from urllib.parse import urlsplit

from dotenv import dotenv_values
from openai import OpenAI

try:
    from code_benchmark import vi_multimodel as v1
    from code_benchmark.score_vi_multimodel import score_rows
except ImportError:
    import vi_multimodel as v1
    from score_vi_multimodel import score_rows

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "all_res/muse13_direct_mc80/main/muse-spark-1-3-contributor-ocg"
CARD = ROOT / "docs/measurement_cards/MC-80-muse13-direct-default.md"
MODEL = "ocg/muse-spark-1.3-contributor"
PROTOCOL = "muse13-direct-default-mc80-v1"
CARD_ID = "MC-80"
PROFILE = "muse13-ocg-direct-default"
SYSTEM = "Answer the user's question."
SHARDS = 4
LANES = 3


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(v1.canonical_json(value) + b"\n")
    tmp.replace(path)


def inputs() -> tuple[dict, dict, list]:
    manifest = v1.load_manifest("main")
    rebuilt = v1.rebuild_items("main")
    items = [v1.item_from_manifest_row(ref, rebuilt) for ref in manifest["items"]]
    if len(items) != 2043 or len({item.run_key for item in items}) != 2043:
        raise SystemExit("Error: MC-80 requires 2,043 unique frozen main items")
    return manifest, rebuilt, items


def assignments(items: list) -> list[list]:
    quotient, remainder = divmod(len(items), SHARDS)
    batches, start = [], 0
    for shard in range(SHARDS):
        stop = start + quotient + int(shard < remainder)
        batches.append(items[start:stop])
        start = stop
    return batches


def request(client: OpenAI, item, shard: int, lane: int) -> dict:
    cap = 4096 if item.task == "multiple_choice" else 2048
    row = {
        "run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}",
        "dataset_id": item.dataset_id, "item_id": item.item_id,
        "replicate_id": item.replicate_id, "profile_id": PROFILE,
        "measurement_card_id": CARD_ID, "protocol_id": PROTOCOL,
        "model_id": MODEL, "transport": "direct-api", "shard": shard, "lane": lane,
        "prompt_sha256": v1.sha256_bytes(item.prompt.encode()), "raw_prompt": item.prompt,
        "temperature_sent": 1.0, "reasoning_effort_sent": None, "seed_sent": None,
        "max_tokens": cap, "started_at": now(), "raw_response": "",
    }
    start = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": item.prompt}],
            temperature=1.0, max_tokens=cap, stream=False,
        )
        if not response.choices:
            raise ValueError("no_choices")
        choice = response.choices[0]
        usage = response.usage
        detail = getattr(usage, "completion_tokens_details", None)
        prompt_detail = getattr(usage, "prompt_tokens_details", None)
        finish = str(choice.finish_reason or "unknown")
        text = choice.message.content or ""
        tools = getattr(choice.message, "tool_calls", None) or []
        row.update({
            "raw_response": text, "finish_reason": finish,
            "response_model_id": response.model, "request_id": response.id,
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "service_tier": getattr(response, "service_tier", None),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "reasoning_tokens": getattr(detail, "reasoning_tokens", None),
            "cached_prompt_tokens": getattr(prompt_detail, "cached_tokens", None),
            "tool_call_n": len(tools),
            "status": "complete" if finish in {"stop", "length", "content_filter"} and not tools else "request_error",
        })
        if row["status"] != "complete":
            row["error_type"] = "unexpected_finish_or_tool_call"
            row["fatal"] = bool(tools)
    except Exception as exc:
        # Never serialize SDK exception strings: they can contain upstream data.
        status = getattr(exc, "status_code", None)
        row.update({"status": "request_error", "finish_reason": "error",
                    "error_type": type(exc).__name__, "http_status": status,
                    "fatal": status in {400, 401, 402, 403, 404, 429}})
    row.update({"latency_s": round(time.monotonic() - start, 4), "finished_at": now()})
    return row


def load_rows(output: Path, manifest: dict) -> dict:
    path = output / "attempts.jsonl"
    expected = {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}": r for r in manifest["items"]}
    rows = {}
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            key = row.get("run_key")
            if key not in expected or row.get("prompt_sha256") != expected[key]["prompt_sha256"]:
                raise SystemExit("Error: checkpoint identity or prompt drift")
            if row.get("model_id") != MODEL or row.get("protocol_id") != PROTOCOL:
                raise SystemExit("Error: checkpoint condition drift")
            if key in rows and rows[key].get("status") == "complete":
                raise SystemExit("Error: completed item was attempted again")
            rows[key] = row
    return rows


def snapshot(output: Path, rows: dict, meta: dict) -> None:
    v1.write_jsonl_atomic(output / "predictions.jsonl", list(rows.values()))
    meta.update({"updated_at": now(), "complete_items": sum(r["status"] == "complete" for r in rows.values()),
                 "request_error_items": sum(r["status"] != "complete" for r in rows.values()),
                 "remaining_items": meta["expected_n"] - sum(r["status"] == "complete" for r in rows.values())})
    atomic_json(output / "run.json", meta)


def score(output: Path, manifest: dict, rebuilt: dict, rows: dict, meta: dict) -> None:
    scored, summaries = score_rows(manifest, rows, rebuilt)
    # Preserve frozen score computation; withhold headline metrics on partial data.
    for value in summaries.values():
        if value["status"] != "complete":
            for key in ("accuracy", "correct", "ci95", "accuracy_rows", "by_gold", "by_group", "em", "em_count",
                        "em_ci95", "token_f1", "token_f1_ci95", "legacy_raw_em", "legacy_raw_char_f1",
                        "legacy_final_em", "legacy_final_char_f1"):
                value.pop(key, None)
    v1.write_jsonl_atomic(output / "scores.jsonl", scored)
    atomic_json(output / "summary.json", {
        "protocol_id": PROTOCOL, "measurement_card_id": "MC-80", "model_id": MODEL,
        "transport": "direct-api", "manifest_sha256": manifest["manifest_sha256"],
        "condition_sha256": meta["condition_sha256"], "generated_at": now(),
        "expected_n": len(manifest["items"]), "datasets": list(summaries.values()),
        "cost_usd": None, "cost_basis": "9Router tariff unknown; token usage retained per attempt",
    })


def execute(output: Path, manifest: dict, rebuilt: dict, items: list, condition: dict, client: OpenAI, resume: bool,
            *, score_callback=None, runner_path: Path | None = None, work_stealing: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".run.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Error: another campaign owns this output") from None
        condition_hash = v1.sha256_bytes(v1.canonical_json(condition))
        old_path = output / "run.json"
        if old_path.exists():
            old = json.loads(old_path.read_text())
            if not resume or old.get("condition_sha256") != condition_hash:
                raise SystemExit("Error: existing run requires --resume and identical condition")
            meta = old
        else:
            meta = {**condition, "condition_sha256": condition_hash, "started_at": now()}
        source_path = runner_path or Path(__file__)
        source_hash = v1.sha256_file(source_path)
        source_dir = output / "runner_sources"
        source_dir.mkdir(exist_ok=True)
        (source_dir / f"{source_hash}.py").write_bytes(source_path.read_bytes())
        shared_hash = v1.sha256_file(Path(__file__))
        (source_dir / f"{shared_hash}.py").write_bytes(Path(__file__).read_bytes())
        history = meta.setdefault("execution_history", [])
        if resume and not history:
            history.append({"started_at": meta["started_at"], "runner_sha256": condition["runner_sha256"],
                            "reason": "initial execution"})
        history.append({"started_at": now(), "runner_sha256": source_hash,
                        "scheduler": "lane-work-stealing-v1" if work_stealing else "fixed-lanes-v1",
                        "shared_runner_sha256": shared_hash,
                        "reason": "resume; unfinished gateway replies are retained as technical failures without stopping other items" if resume else "initial execution"})
        atomic_json(output / "condition.json", condition)
        atomic_json(output / "source_manifest.json", manifest)
        rows = load_rows(output, manifest)
        meta.pop("finished_at", None)
        meta.pop("pause_reason", None)
        meta.pop("paused_at", None)
        meta.update({"status": "running", "pid": os.getpid(), "expected_n": len(items)})
        snapshot(output, rows, meta)
        batches = assignments(items)
        atomic_json(output / "fixed_shards.json", {"shards": [
            {"shard": i, "run_keys": [item.run_key for item in batch], "lanes": LANES}
            for i, batch in enumerate(batches)]})
        stop = threading.Event()
        results = queue.Queue()
        completed_keys = {key for key, row in rows.items() if row["status"] == "complete"}
        pending = {(shard, lane): deque(item for item in batch[lane::LANES]
                                       if item.run_key not in completed_keys)
                   for shard, batch in enumerate(batches) for lane in range(LANES)}
        claim_lock = threading.Lock()
        meta["execution_scheduler"] = "lane-work-stealing-v1" if work_stealing else "fixed-lanes-v1"
        snapshot(output, rows, meta)

        def claim(shard: int, lane: int):
            with claim_lock:
                if stop.is_set():
                    return None
                origin = (shard, lane)
                if not pending[origin] and work_stealing:
                    origin = max(pending, key=lambda key: len(pending[key]))
                if not pending[origin]:
                    return None
                return origin, pending[origin].popleft()

        def worker(shard: int, lane: int, batch: list) -> None:
            consecutive_errors = 0
            try:
                while True:
                    claimed = claim(shard, lane)
                    if claimed is None:
                        break
                    (origin_shard, origin_lane), item = claimed
                    row = request(client, item, origin_shard, origin_lane)
                    if work_stealing:
                        row.update({"worker_shard": shard, "worker_lane": lane,
                                    "scheduler": "lane-work-stealing-v1"})
                    if row.get("fatal"):
                        stop.set()
                    results.put(row)
                    if row["status"] == "complete":
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                        delay = float(row.get("retry_wait_seconds", 0))
                        if delay and not row.get("fatal"):
                            # Save the failed attempt before waiting; back off this lane
                            # while other lanes remain free to complete their requests.
                            stop.wait(min(300, delay * 2 ** min(consecutive_errors - 1, 6)))
            finally:
                results.put(None)

        done = 0
        with (output / "attempts.jsonl").open("a", encoding="utf-8") as ledger:
            with ThreadPoolExecutor(max_workers=SHARDS * LANES) as pool:
                futures = [pool.submit(worker, shard, lane, batch)
                           for shard, batch in enumerate(batches) for lane in range(LANES)]
                while done < SHARDS * LANES:
                    row = results.get()
                    if row is None:
                        done += 1
                        continue
                    key = row["run_key"]
                    row["attempts"] = int(rows.get(key, {}).get("attempts", 0)) + 1
                    ledger.write(json.dumps(row, ensure_ascii=False) + "\n")
                    ledger.flush()
                    os.fsync(ledger.fileno())
                    rows[key] = row
                    if row.get("fatal"):
                        meta["pause_reason"] = f"fatal request {key}: {row.get('error_type', 'unknown')}"
                        meta["paused_at"] = row.get("finished_at", now())
                    snapshot(output, rows, meta)
                    print(f"complete={meta['complete_items']}/{len(items)} errors={meta['request_error_items']} "
                          f"shard={row['shard']} lane={row['lane']} status={row['status']}", flush=True)
                for future in futures:
                    future.result()
        meta["status"] = "complete" if all(item.run_key in rows and rows[item.run_key]["status"] == "complete" for item in items) else "paused" if stop.is_set() else "incomplete"
        meta["finished_at"] = now()
        snapshot(output, rows, meta)
        (score_callback or score)(output, manifest, rebuilt, rows, meta)
        print(f"status={meta['status']} complete={meta['complete_items']}/{len(items)} output={output}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    manifest, rebuilt, items = inputs()
    values = dotenv_values(ROOT / ".env")
    endpoint, key = values.get("9ROUTER_BASE_URL"), values.get("9ROUTER_API_KEY")
    if not endpoint or not key:
        raise SystemExit("Error: missing 9ROUTER_BASE_URL or 9ROUTER_API_KEY")
    parts = urlsplit(endpoint)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.query or parts.username:
        raise SystemExit("Error: invalid base URL")
    if parts.path.rstrip("/").endswith(("/chat/completions", "/responses")):
        raise SystemExit("Error: base URL must name the API root, not an inference route")
    condition = {
        "protocol_id": PROTOCOL, "protocol_version": 1, "phase": "main",
        "measurement_card_id": "MC-80", "measurement_card_hash": v1.sha256_file(ROOT / "measurement_card.md"),
        "card_sha256": v1.sha256_file(CARD), "manifest_sha256": manifest["manifest_sha256"],
        "parent_protocol_id": manifest["protocol_id"], "source_sha256": manifest["source_sha256"],
        "dataset_counts": manifest["dataset_counts"], "model_id": MODEL,
        "model_ref": MODEL, "provider": "9Router / OpenCode Go", "transport": "direct-api",
        "api_protocol": "openai-chat-completions", "endpoint_host": parts.hostname,
        "base_url_sha256": v1.sha256_bytes(endpoint.encode()),
        "temperature_requested": 1.0, "temperature_effective": None,
        "reasoning_effort_sent": None, "reasoning_policy": "field omitted; provider default; effective effort unknown",
        "router_thinking_override": "unverified; settings API denies read access",
        "seed_sent": None, "tools": "none", "system_prompt": SYSTEM,
        "gateway_optout": {"header_name": "x-9router-token-saver", "value": "off"},
        "prompt_version": "vi-multimodel-prompt-v1", "scorer_version": "vi-reading-v2",
        "workers": 12, "shards": SHARDS, "workers_per_shard": LANES,
        "max_tokens_mc": 4096, "max_tokens_reading": 2048,
        "request_timeout_seconds": 300, "sdk_retries": 0,
        "runner_sha256": v1.sha256_file(Path(__file__)),
        "scorer_sha256": v1.sha256_file(ROOT / "code_benchmark/score_vi_multimodel.py"),
    }
    if args.resume and (OUT / "condition.json").is_file():
        frozen = json.loads((OUT / "condition.json").read_text())
        # Scheduler repairs may change implementation provenance without changing
        # any inference setting. Every executed source is archived and hashed.
        implementation_fields = {"runner_sha256", "measurement_card_hash"}
        current_rules = {k: v for k, v in condition.items() if k not in implementation_fields}
        frozen_rules = {k: v for k, v in frozen.items() if k not in implementation_fields}
        if current_rules != frozen_rules:
            raise SystemExit("Error: resume would change the frozen inference condition")
        condition = frozen
    print(f"preflight=passed items={len(items)} workers=12 shards=4 lanes=3 endpoint_calls=0", flush=True)
    if args.execute:
        with OpenAI(base_url=endpoint, api_key=key, timeout=300.0, max_retries=0,
                    default_headers={"x-9router-token-saver": "off"}) as client:
            execute(OUT, manifest, rebuilt, items, condition, client, args.resume)


if __name__ == "__main__":
    main()
