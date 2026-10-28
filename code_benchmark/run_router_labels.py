"""Run the Muse router's design-stage check (openspec change: diagnostic-llm-router; card MC-98).

From the repo root:
  .venv/bin/python -m code_benchmark.run_router_labels                 # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_router_labels --execute [--resume]

Muse Spark 1.3 reads the passage and question of each of the 591 ViBidLQA design items once
(data/diagnostic_llm_router/router_labels_v1.json) and returns one group. The route is the direct OpenCode Go
Responses API of MC-86, with the credential resolved from the local OpenCode auth store and never written out. No
student-model request is sent. `--execute` fails closed unless the MC-98 heading and detail card exist, the router
configuration and manifest carry the registered SHA-256 values, and the route resolves to the registered host and
model. The registered limits (4 in flight, breaker after 4 consecutive network failures, 3,000,000 reported tokens)
apply. Completed responses, including truncated or unrecognised ones, are terminal; `--resume` re-sends only items
without a completed response under an identical condition.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

try:
    from code_benchmark import diagnostic_llm_router as router
    from code_benchmark import run_vi_multimodel_eval as route_runtime
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_multimodel_expansion as v2
except ImportError:  # executed from code_benchmark/
    import diagnostic_llm_router as router
    import run_vi_multimodel_eval as route_runtime
    import vi_multimodel as v1
    import vi_multimodel_expansion as v2

ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_CARD = ROOT / "measurement_card.md"
OUTPUT_ROOT = ROOT / "all_res" / "diagnostic_llm_router" / router.PHASE
FROZEN_KEYS = ("router_config_sha256", "manifest_sha256")


@dataclasses.dataclass(frozen=True)
class Gate:
    name: str
    ok: bool
    detail: str


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registration(path: Path = router.REGISTRATION_PATH) -> dict[str, Any]:
    try:
        registration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read the router-labels registration {path}: {exc}") from exc
    for key in ("card_ids", "card_files", "frozen", router.PHASE):
        if key not in registration:
            raise SystemExit(f"Error: the router-labels registration lacks {key}")
    return registration


def resolve_route(config: dict[str, Any]) -> tuple[str, str, str, str]:
    """(endpoint, api key, model, credential source) of the registered profile; the key stays in memory."""
    profiles = v2.load_profiles()
    profile_id = config["route"]["profile_id"]
    if profile_id not in profiles:
        raise SystemExit(f"Error: route profile {profile_id} is not in the registry")
    return route_runtime._resolve_model(dict(profiles[profile_id]))  # noqa: SLF001 - the shared route resolver


def evaluate_gates(config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                   route: tuple[str, str, bool], *, card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    """route = (endpoint, model, credential present)."""
    card_id = (registration.get("card_ids") or {}).get(router.PHASE)
    text = MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    gates = [Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md")]
    card_file = (registration.get("card_files") or {}).get(router.PHASE)
    gates.append(Gate("detail_card", bool(card_file) and (root / str(card_file)).is_file(),
                      str(card_file or "no detail card file recorded")))
    frozen = registration.get("frozen") or {}
    differing = [name for name in FROZEN_KEYS if frozen.get(name) != manifest.get(name)]
    gates.append(Gate("frozen_hashes", not differing, "all match" if not differing else f"differ: {differing}"))
    endpoint, model, has_key = route
    expected = config["route"]
    identity = urlsplit(endpoint).hostname == expected["endpoint_host"] and model == expected["model_id"] and has_key
    gates.append(Gate("route_identity", identity, f"model={model} (registered {expected['model_id']})"))
    return gates


def build_condition(config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any], endpoint: str,
                    model: str, credential_source: str) -> dict[str, Any]:
    route = config["route"]
    return {
        "protocol_id": router.PROTOCOL_ID, "protocol_version": 1, "phase": router.PHASE,
        "router_id": config["router_id"], "measurement_card_id": registration["card_ids"][router.PHASE],
        "measurement_card_hash": v1.sha256_file(MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][router.PHASE]),
        "router_config_sha256": manifest["router_config_sha256"], "manifest_sha256": manifest["manifest_sha256"],
        "menu_manifest_self_sha256": manifest["menu_manifest_self_sha256"], "dataset_counts": manifest["dataset_counts"],
        "profile_id": route["profile_id"], "model_id": model, "endpoint_host": urlsplit(endpoint).hostname,
        "base_url_sha256": v1.sha256_bytes(endpoint.encode()), "credential_source": credential_source,
        "api_protocol": route["api_protocol"], "stream": route["stream"], "temperature_sent": None,
        "reasoning_effort_sent": None, "system_prompt": route["system_prompt"],
        "max_output_tokens": route["max_output_tokens"], "timeout_seconds": route["timeout_seconds"],
        "sdk_retries": route["sdk_retries"], "max_in_flight": route["max_in_flight"],
        "stop_after_timeouts": route["stop_after_timeouts"], "budget_tokens": route["budget_tokens"],
        "router_module_sha256": v1.sha256_file(Path(router.__file__)),
        "runner_sha256": v1.sha256_file(Path(__file__)),
    }


def session_id(run_key: str) -> str:
    return f"vmlu-mc98-{v1.sha256_bytes(run_key.encode('utf-8'))[:16]}"


def call_router(client: Any, item: v1.EvalItem, config: dict[str, Any], model: str) -> dict[str, Any]:
    route = config["route"]
    row: dict[str, Any] = {"run_key": item.run_key, "dataset_id": item.dataset_id, "item_id": item.item_id,
                           "replicate_id": item.replicate_id, "prompt_sha256": v1.sha256_bytes(item.prompt.encode()),
                           "model_id": model, "started_at": now()}
    start = time.monotonic()
    try:
        response = client.responses.create(model=model, input=item.prompt, max_output_tokens=route["max_output_tokens"],
                                           extra_headers={route["session_header"]: session_id(item.run_key)})
        text = response.output_text or ""
        usage = response.usage
        details = getattr(usage, "output_tokens_details", None)
        group, format_ok = router.parse_group(text, config)
        incomplete = getattr(response, "incomplete_details", None)
        row.update({
            "status": "complete", "response_status": response.status,
            "incomplete_reason": getattr(incomplete, "reason", None) if incomplete else None,
            "raw_response": text, "group": group, "format_ok": format_ok,
            "input_tokens": getattr(usage, "input_tokens", None), "output_tokens": getattr(usage, "output_tokens", None),
            "reasoning_tokens": getattr(details, "reasoning_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "response_model_id": response.model, "request_id": response.id,
        })
    except (APIConnectionError, APITimeoutError) as exc:
        row.update({"status": "network_error", "error_type": type(exc).__name__})
    except APIStatusError as exc:
        row.update({"status": "request_error", "error_type": type(exc).__name__, "http_status": exc.status_code,
                    "fatal": exc.status_code in (401, 403)})
    row.update({"latency_s": round(time.monotonic() - start, 3), "finished_at": now()})
    return row


def read_attempts(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                latest[row["run_key"]] = row
    return latest


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


def execute(output: Path, items: list[v1.EvalItem], config: dict[str, Any], client: Any, model: str) -> dict[str, Any]:
    route = config["route"]
    ledger = output / "attempts.jsonl"
    done = {key for key, row in read_attempts(ledger).items() if row.get("status") == "complete"}
    pending = [item for item in items if item.run_key not in done]
    spent = sum(row.get("total_tokens") or 0 for row in read_attempts(ledger).values() if row.get("status") == "complete")
    halt, lock = threading.Event(), threading.Lock()
    state: dict[str, Any] = {"network_failures": 0, "spent": spent, "reason": None, "complete": len(done)}

    def work(item: v1.EvalItem) -> dict[str, Any] | None:
        if halt.is_set():
            return None
        return call_router(client, item, config, model)

    with ThreadPoolExecutor(max_workers=route["max_in_flight"]) as pool:
        futures = [pool.submit(work, item) for item in pending]
        for future in as_completed(futures):
            row = future.result()
            if row is None:
                continue
            with lock:
                with ledger.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                state["network_failures"] = state["network_failures"] + 1 if row["status"] == "network_error" else 0
                state["spent"] += row.get("total_tokens") or 0
                state["complete"] += row["status"] == "complete"
                stop = None
                if row.get("fatal"):
                    stop = "fatal_request_error"
                elif row["status"] == "complete" and row.get("response_model_id") != model:
                    stop = "model_id_changed"
                elif state["network_failures"] >= route["stop_after_timeouts"]:
                    stop = "endpoint_unresponsive"
                elif state["spent"] >= route["budget_tokens"]:
                    stop = "budget_cap"
                if stop and not halt.is_set():
                    state["reason"] = stop
                    halt.set()
                print(f"complete={state['complete']}/{len(items)} status={row['status']} group={row.get('group')}",
                      flush=True)
    latest = read_attempts(ledger)
    labels = [{key: latest[item.run_key].get(key) for key in ("run_key", "dataset_id", "item_id", "group", "format_ok",
                                                              "response_status", "incomplete_reason", "input_tokens",
                                                              "output_tokens", "reasoning_tokens", "total_tokens",
                                                              "latency_s")}
              for item in items if latest.get(item.run_key, {}).get("status") == "complete"]
    v1.write_jsonl_atomic(output / "labels.jsonl", labels)
    summary = {"status": "complete" if len(labels) == len(items) else "incomplete", "halt_reason": state["reason"],
               "complete": len(labels), "expected": len(items), "reported_tokens": state["spent"], "finished_at": now()}
    (output / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="send router requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="re-send only items without a completed response")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    config, _ = router.load_config()
    registration = load_registration()
    manifest, rebuilt = router.build_manifest()
    if manifest != router.load_frozen_manifest():
        raise SystemExit("Error: the rebuilt router-labels manifest differs from the frozen router_labels_v1.json")
    items = [v1.item_from_manifest_row(row, rebuilt) for row in manifest["items"]]
    endpoint, key, model, credential_source = resolve_route(config)
    gates = evaluate_gates(config, manifest, registration, (endpoint, model, bool(key)))
    print(f"phase={router.PHASE} protocol={router.PROTOCOL_ID} router={config['router_id']} calls={manifest['n']} "
          f"route={urlsplit(endpoint).hostname}/{model} credential={credential_source}")
    print(f"manifest_sha256={manifest['manifest_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    print(f"preflight=passed calls={manifest['n']} endpoint_calls=0", flush=True)
    if not args.execute:
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise SystemExit("Error: execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    output = OUTPUT_ROOT / config["route"]["profile_id"]
    reconcile(output, build_condition(config, manifest, registration, endpoint, model, credential_source), args.resume)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as events:
        events.write(json.dumps({"at": now(), "phase": router.PHASE, "resume": args.resume,
                                 "runner_sha256": v1.sha256_file(Path(__file__)), "note": args.note},
                                ensure_ascii=False) + "\n")
    route = config["route"]
    with OpenAI(base_url=endpoint, api_key=key, timeout=route["timeout_seconds"], max_retries=route["sdk_retries"]) as client:
        summary = execute(output, items, config, client, model)
    print(f"status={summary['status']} complete={summary['complete']}/{summary['expected']} "
          f"halt={summary['halt_reason']} tokens={summary['reported_tokens']} output={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
