"""Collect the router signals of Jev 1.13 (openspec change diagnostic-router-signals; card MC-99).

From the repo root:
  .venv/bin/python -m code_benchmark.run_router_signals                 # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_router_signals --execute [--resume]

Sends the 2,901 requests of the frozen manifest (data/diagnostic_router_signals/jev_signals_manifest_v1.json) to the
OpenCode System One endpoint, model jev-1.13-free: one pre-hoc request per wide reading item and one post-hoc request
per B draw. No student-model request is sent. The credential comes from the local OpenCode auth store and is never
written out.

`--execute` fails closed unless the MC-99 heading and detail card exist, the configuration and manifest carry the
registered SHA-256 values, and the route is the registered one. The run halts on non-free billing, a changed response
model, an authentication error, or 4 consecutive network failures. 429 and 5xx responses are re-sent after the
Retry-After wait (30 s without one), at most 5 times, and every retry is recorded. Completed responses are terminal;
`--resume` re-sends only requests without a completed response under an identical condition.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_router_signals as sig
    from code_benchmark import run_vi_multimodel_eval as route_runtime
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_router_signals as sig
    import run_vi_multimodel_eval as route_runtime
    import vi_multimodel as v1

ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_CARD = ROOT / "measurement_card.md"
OUTPUT_ROOT = ROOT / "all_res" / "diagnostic_router_signals" / "jev"
FROZEN_KEYS = ("config_sha256", "manifest_sha256")
AUTH_PROVIDER = "opencode-go"
# (status, parsed JSON or None, raw text, response headers); raises OSError subclasses on network failures
Transport = Callable[[str, dict[str, Any], dict[str, str], float], tuple[int, Any, str, dict[str, str]]]


@dataclasses.dataclass(frozen=True)
class Gate:
    name: str
    ok: bool
    detail: str


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_transport(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float
                   ) -> tuple[int, Any, str, dict[str, str]]:
    if not url.startswith("https://"):
        raise ValueError("the signals route is https only")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - https only, checked above
            text = response.read().decode("utf-8")
            status, response_headers = response.status, dict(response.headers)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        status, response_headers = exc.code, dict(exc.headers or {})
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    return status, parsed, text, response_headers


def endpoint_url(route: dict[str, Any]) -> str:
    return f"https://{route['endpoint_host']}{route['path']}"


def session_id(run_key: str) -> str:
    return f"vmlu-mc99-{v1.sha256_bytes(run_key.encode('utf-8'))[:16]}"


def load_registration(path: Path = sig.REGISTRATION_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def evaluate_gates(config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any], has_key: bool,
                   *, card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    card_id = (registration.get("card_ids") or {}).get(sig.PHASE)
    text = MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    gates = [Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md")]
    card_file = (registration.get("card_files") or {}).get(sig.PHASE)
    gates.append(Gate("detail_card", bool(card_file) and (root / str(card_file)).is_file(),
                      str(card_file or "no detail card file recorded")))
    frozen = registration.get("frozen") or {}
    differing = [name for name in FROZEN_KEYS if frozen.get(name) != manifest.get(name)]
    gates.append(Gate("frozen_hashes", not differing, "all match" if not differing else f"differ: {differing}"))
    route = config["route"]
    registered = registration.get("route") or {}
    identity = (has_key and all(registered.get(name) == route[name] for name in ("endpoint_host", "path", "model_id")))
    gates.append(Gate("route_identity", identity, f"{endpoint_url(route)} model={route['model_id']}"))
    return gates


def call_signal(transport: Transport, row: dict[str, Any], body: dict[str, Any], route: dict[str, Any], key: str,
                sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """One request with registered technical retries; returns the attempt record (never the key)."""
    run_key = f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"
    record: dict[str, Any] = {"run_key": run_key, "dataset_id": row["dataset_id"], "item_id": row["item_id"],
                              "replicate_id": row["replicate_id"], "kind": row["kind"],
                              "answer_draw": row["answer_draw"], "request_sha256": row["request_sha256"],
                              "started_at": now(), "retries": []}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "User-Agent": route["user_agent"], route["session_header"]: session_id(run_key)}
    start = time.monotonic()
    for attempt in range(route["max_retries"] + 1):
        try:
            status, parsed, text, response_headers = transport(endpoint_url(route), body, headers,
                                                               route["timeout_seconds"])
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            record.update({"status": "network_error", "error_type": type(exc).__name__})
            break
        if status == 200 and isinstance(parsed, dict) and isinstance(parsed.get("answers"), dict):
            usage = parsed.get("usage") or {}
            billing = (usage.get("opencode") or {}).get("billing_source")
            record.update({"status": "complete", "http_status": status, "response_model": parsed.get("model"),
                           "answers": parsed["answers"], "input_tokens": usage.get("input_tokens"),
                           "output_tokens": usage.get("output_tokens"), "cost": usage.get("cost"),
                           "billing_source": billing})
            break
        if status in route["retry_statuses"] and attempt < route["max_retries"]:
            wait = route["retry_wait_seconds"]
            try:
                wait = max(float(response_headers.get("Retry-After") or wait), 1.0)
            except (TypeError, ValueError):
                pass
            record["retries"].append({"http_status": status, "wait_s": wait, "at": now()})
            sleep(wait)
            continue
        record.update({"status": "request_error", "http_status": status, "error_body": text[:500],
                       "fatal": status in (401, 403)})
        break
    record.update({"latency_s": round(time.monotonic() - start, 3), "finished_at": now()})
    return record


def halt_reason(record: dict[str, Any], route: dict[str, Any], network_failures: int) -> str | None:
    if record.get("fatal"):
        return "authentication_error"
    if record["status"] == "complete":
        if record.get("response_model") != route["model_id"]:
            return "model_id_changed"
        if route["require_free_billing"] and (record.get("billing_source") != "free" or (record.get("cost") or 0) > 0):
            return "non_free_billing"
    if network_failures >= route["stop_after_network_failures"]:
        return "endpoint_unresponsive"
    return None


def read_attempts(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                latest[record["run_key"]] = record
    return latest


def build_condition(config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    credential_source: str) -> dict[str, Any]:
    return {
        "protocol_id": sig.PROTOCOL_ID, "protocol_version": 1, "phase": sig.PHASE,
        "signals_id": config["signals_id"], "measurement_card_id": registration["card_ids"][sig.PHASE],
        "measurement_card_hash": v1.sha256_file(MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][sig.PHASE]),
        "config_sha256": manifest["config_sha256"], "manifest_sha256": manifest["manifest_sha256"],
        "answer_source_sha256": manifest["answer_source_sha256"], "kind_counts": manifest["kind_counts"],
        "route": {key: config["route"][key] for key in sig.ROUTE_KEYS if key != "credential"},
        "credential_source": credential_source,
        "runner_sha256": v1.sha256_file(Path(__file__)), "module_sha256": v1.sha256_file(Path(str(sig.__file__))),
    }


def reconcile(output: Path, condition: dict[str, Any], resume: bool) -> None:
    path = output / "condition.json"
    if (output / "attempts.jsonl").is_file() and not resume:
        raise SystemExit(f"Error: {output} already holds attempts; use --resume")
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        ignored = {"runner_sha256", "measurement_card_hash"}
        if {k: v for k, v in frozen.items() if k not in ignored} != {k: v for k, v in condition.items() if k not in ignored}:
            raise SystemExit("Error: the frozen condition differs from this launch; refusing to resume")
    else:
        output.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(condition, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def flatten(record: dict[str, Any]) -> dict[str, Any]:
    """The compact signal row: per question, the probability of yes (noul) or the choice and its probabilities."""
    row = {key: record.get(key) for key in ("run_key", "dataset_id", "item_id", "kind", "answer_draw")}
    for qid, answer in (record.get("answers") or {}).items():
        if answer.get("type") == "noul":
            row[qid] = answer.get("noul")
        elif answer.get("type") == "choice":
            row[qid] = answer.get("choice")
            row[f"{qid}_confidence"] = answer.get("confidence")
            row[f"{qid}_probabilities"] = answer.get("probabilities")
    return row


def execute(output: Path, requests: list[dict[str, Any]], config: dict[str, Any], key: str,
            transport: Transport = http_transport, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    route = config["route"]
    ledger = output / "attempts.jsonl"
    done = {run_key for run_key, record in read_attempts(ledger).items() if record.get("status") == "complete"}
    pending = [row for row in requests
               if f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}" not in done]
    halt, lock = threading.Event(), threading.Lock()
    state: dict[str, Any] = {"network_failures": 0, "reason": None, "complete": len(done)}

    def work(row: dict[str, Any]) -> dict[str, Any] | None:
        if halt.is_set():
            return None
        record = call_signal(transport, row, row["body"], route, key, sleep)
        if halt_reason(record, route, 0):  # billing, model or authentication: stop the next sends at once
            halt.set()
        return record

    with ThreadPoolExecutor(max_workers=route["max_in_flight"]) as pool:
        futures = [pool.submit(work, row) for row in pending]
        for future in as_completed(futures):
            record = future.result()
            if record is None:
                continue
            with lock:
                with ledger.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                state["network_failures"] = state["network_failures"] + 1 if record["status"] == "network_error" else 0
                state["complete"] += record["status"] == "complete"
                stop = halt_reason(record, route, state["network_failures"])
                if stop and state["reason"] is None:
                    state["reason"] = stop
                    halt.set()
                if state["complete"] % 100 == 0 or record["status"] != "complete":
                    print(f"complete={state['complete']}/{len(requests)} last={record['status']} "
                          f"retries={len(record['retries'])}", flush=True)
    latest = read_attempts(ledger)
    keys = [f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}" for row in requests]
    signals = [flatten(latest[run_key]) for run_key in keys if latest.get(run_key, {}).get("status") == "complete"]
    v1.write_jsonl_atomic(output / "signals.jsonl", signals)
    completed = [latest[run_key] for run_key in keys if latest.get(run_key, {}).get("status") == "complete"]
    summary = {"status": "complete" if len(signals) == len(requests) else "incomplete", "halt_reason": state["reason"],
               "complete": len(signals), "expected": len(requests),
               "input_tokens": sum(record.get("input_tokens") or 0 for record in completed),
               "output_tokens": sum(record.get("output_tokens") or 0 for record in completed),
               "reported_cost": sum(record.get("cost") or 0 for record in completed),
               "billing_sources": sorted({str(record.get("billing_source")) for record in completed}),
               "retries": sum(len(record.get("retries") or []) for record in latest.values()),
               "finished_at": now()}
    (output / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="send the requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="re-send only requests without a completed response")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    config, _ = sig.load_config()
    registration = load_registration()
    manifest, requests = sig.build_manifest()
    if manifest != sig.load_frozen_manifest():
        raise SystemExit("Error: the rebuilt signals manifest differs from the frozen jev_signals_manifest_v1.json")
    key, credential_source = route_runtime._resolve_credentials({"auth_provider": AUTH_PROVIDER})  # noqa: SLF001
    gates = evaluate_gates(config, manifest, registration, bool(key))
    route = config["route"]
    print(f"phase={sig.PHASE} protocol={sig.PROTOCOL_ID} signals={config['signals_id']} requests={manifest['n']} "
          f"{manifest['kind_counts']} route={route['endpoint_host']}{route['path']}/{route['model_id']} "
          f"credential={credential_source}")
    print(f"manifest_sha256={manifest['manifest_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    print(f"preflight=passed requests={manifest['n']} endpoint_calls=0", flush=True)
    if not args.execute:
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise SystemExit("Error: execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    output = OUTPUT_ROOT / route["model_id"]
    reconcile(output, build_condition(config, manifest, registration, credential_source), args.resume)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as events:
        events.write(json.dumps({"at": now(), "phase": sig.PHASE, "resume": args.resume,
                                 "runner_sha256": v1.sha256_file(Path(__file__)), "note": args.note},
                                ensure_ascii=False) + "\n")
    summary = execute(output, requests, config, key)
    print(f"status={summary['status']} complete={summary['complete']}/{summary['expected']} "
          f"halt={summary['halt_reason']} cost={summary['reported_cost']} billing={summary['billing_sources']} "
          f"retries={summary['retries']} output={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
