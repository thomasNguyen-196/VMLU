"""Run the weakness-map calibration of an API student (openspec change diagnostic-router-loop, Phase 2; card MC-103).

From the repo root:
  .venv/bin/python -m code_benchmark.run_weakness_map                 # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_weakness_map --execute [--resume]

MiMo V2.6 Flash answers the 600 attempts of data/diagnostic_router_loop/weakness_manifest_v1.json: the 180 MC-95
calibration items, with B twice and S once on each, and Q once on the ViBidLQA items. Requests go to the direct OpenCode
Go chat-completions route, with the credential resolved from the local OpenCode auth store and never written out. Each
attempt carries its own `x-opencode-session` header, which the route requires (as MC-98 and MC-102). The
shared engine of the direct campaigns (run_muse13_direct_mc80.execute) schedules the attempts and keeps attempts.jsonl;
the frozen per-arm scorer then scores the run. `--execute` fails closed unless:
* the MC-103 heading and detail card exist;
* the configuration and the manifest carry the registered SHA-256 values;
* the route resolves to the registered host and model.
The registered limits apply: 4 requests in flight, a breaker after 4 consecutive network failures, and a guard of
6,000,000 reported tokens. The run halts when the provider reports a model id without "mimo", or a model id different
from the first one it reported. A completed response, including a truncated one, is terminal; `--resume` re-sends only
attempts without one, under an identical condition.
"""
from __future__ import annotations

import argparse
import json
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from openai import OpenAI

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_weakness_map as wm
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_router_labels as labels
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_weakness_map as wm
    import run_diagnostic_prospective as pr
    import run_router_labels as labels
    import vi_multimodel as v1

ROOT = dp.ROOT
OUTPUT_ROOT = ROOT / "all_res" / "diagnostic_router_loop" / wm.PHASE
FROZEN_KEYS = ("weakness_config_sha256", "manifest_sha256")
COMPLETE_FINISHES = frozenset({"stop", "length", "content_filter"})
SESSION_HEADER = "x-opencode-session"
Gate = pr.Gate
base = pr.base


def session_id(run_key: str) -> str:
    """One routing session per attempt, so B's two draws of an item never share one."""
    return f"vmlu-mc103-{v1.sha256_bytes(run_key.encode('utf-8'))[:16]}"


def load_registration(path: Path = wm.REGISTRATION_PATH) -> dict[str, Any]:
    try:
        registration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read the weakness-map registration {path}: {exc}") from exc
    for key in ("card_ids", "card_files", "frozen", "analysis"):
        if key not in registration:
            raise SystemExit(f"Error: the weakness-map registration lacks {key}")
    return registration


def evaluate_gates(config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                   route: tuple[str, str, bool], *, card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    """route = (endpoint, model, credential present)."""
    card_id = (registration.get("card_ids") or {}).get(wm.PHASE)
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    gates = [Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md")]
    card_file = (registration.get("card_files") or {}).get(wm.PHASE)
    gates.append(Gate("detail_card", bool(card_file) and (root / str(card_file)).is_file(),
                      str(card_file or "no detail card file recorded")))
    frozen = registration.get("frozen") or {}
    differing = [name for name in FROZEN_KEYS if frozen.get(name) != manifest.get(name)]
    gates.append(Gate("frozen_hashes", not differing, "all match" if not differing else f"differ: {differing}"))
    endpoint, model, has_key = route
    student = config["student"]
    identity = urlsplit(endpoint).hostname == student["endpoint_host"] and model == student["model_id"] and has_key
    gates.append(Gate("route_identity", identity, f"model={model} (registered {student['model_id']})"))
    return gates


def build_condition(config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any], endpoint: str,
                    model: str, credential_source: str) -> dict[str, Any]:
    student = config["student"]
    return {
        "protocol_id": wm.PROTOCOL_ID, "protocol_version": 1, "phase": wm.PHASE, "map_id": config["map_id"],
        "measurement_card_id": registration["card_ids"][wm.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][wm.PHASE]),
        "weakness_config_sha256": manifest["weakness_config_sha256"], "manifest_sha256": manifest["manifest_sha256"],
        "source_manifest_self_sha256": manifest["source_manifest_self_sha256"],
        "campaign_protocol_sha256": manifest["campaign_protocol_sha256"],
        "prompt_templates_sha256": manifest["prompt_templates_sha256"],
        "q_protocol_sha256": manifest["q_protocol_sha256"],
        "dataset_counts": manifest["dataset_counts"], "arm_counts": manifest["arm_counts"],
        "profile_id": student["profile_id"], "model_id": model, "provider": student["provider"],
        "endpoint_host": urlsplit(endpoint).hostname, "base_url_sha256": v1.sha256_bytes(endpoint.encode()),
        "credential_source": credential_source, "transport": "direct-api", "api_protocol": student["api_protocol"],
        "stream": student["stream"], "system_prompt": student["system_prompt"], "temperature_sent": None,
        "temperature_effective": "provider default (thinking mode; profile lists 1.0)", "reasoning_effort_sent": None,
        "seed_sent": None, "tools": "none", "max_completion_tokens": student["max_completion_tokens"],
        "request_timeout_seconds": student["timeout_seconds"], "sdk_retries": student["sdk_retries"],
        "max_in_flight": student["max_in_flight"], "stop_after_timeouts": student["stop_after_timeouts"],
        "budget_tokens": student["budget_tokens"], "model_identity": student["model_identity"],
        "scorer_sha256": v1.sha256_file(ROOT / "code_benchmark" / "score_vi_multimodel.py"),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)), "engine_sha256": v1.sha256_file(Path(base.__file__)),
        "module_sha256": v1.sha256_file(Path(wm.__file__)), "runner_sha256": v1.sha256_file(Path(__file__)),
    }


class ModelPin:
    """The first model id the provider reports is pinned; an id without the identity token, or a later different id,
    is a fatal drift. A response that reports no id is recorded as such and not checked."""

    def __init__(self, token: str):
        self.token = token.lower()
        self.pinned: str | None = None
        self._lock = threading.Lock()

    def check(self, reported: str | None) -> str | None:
        """None when the id is acceptable, else the error type."""
        if not reported:
            return None
        with self._lock:
            if self.token not in reported.lower():
                return "unexpected_model"
            if self.pinned is None:
                self.pinned = reported
            return None if reported == self.pinned else "model_identity_drift"


def make_request(student: dict[str, Any], card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard,
                 pin: ModelPin):
    gate = threading.BoundedSemaphore(student["max_in_flight"])
    halt = threading.Event()  # set by any fatal row; lanes queued at the gate then send nothing

    def request(client, item, shard: int, lane: int) -> dict[str, Any]:
        cap = student["max_completion_tokens"]
        row: dict[str, Any] = {
            "run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}",
            "dataset_id": item.dataset_id, "item_id": item.item_id, "replicate_id": item.replicate_id,
            "arm": dp.arm_of_replicate(item.replicate_id), "phase": wm.PHASE,
            "profile_id": base.PROFILE, "protocol_id": base.PROTOCOL, "measurement_card_id": card_id,
            "model_id": base.MODEL, "transport": "direct-api", "api_protocol": student["api_protocol"],
            "shard": shard, "lane": lane, "prompt_sha256": v1.sha256_bytes(item.prompt.encode()),
            "raw_prompt": item.prompt, "raw_response": "", "temperature_sent": None,
            "reasoning_effort_sent": None, "seed_sent": None, "max_tokens": cap, "started_at": base.now(),
        }
        for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                    (halt.is_set(), "halted_before_send")):
            if blocked:
                row.update({"status": "request_error", "finish_reason": "error", "error_type": error_type,
                            "fatal": True, "latency_s": 0.0, "finished_at": base.now()})
                halt.set()
                return row
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=base.MODEL,
                messages=[{"role": "system", "content": student["system_prompt"]},
                          {"role": "user", "content": item.prompt}],
                max_completion_tokens=cap, stream=False, extra_headers={SESSION_HEADER: session_id(item.run_key)},
            )
            if not response.choices:
                raise ValueError("no_choices")
            choice = response.choices[0]
            usage = response.usage
            detail = getattr(usage, "completion_tokens_details", None)
            prompt_detail = getattr(usage, "prompt_tokens_details", None)
            finish = str(choice.finish_reason or "unknown")
            tools = getattr(choice.message, "tool_calls", None) or []
            reasoning = getattr(choice.message, "reasoning_content", None)
            row.update({
                "raw_response": choice.message.content or "", "finish_reason": finish,
                "response_model_id": response.model, "request_id": response.id,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
                "reasoning_tokens": getattr(detail, "reasoning_tokens", None),
                "cached_prompt_tokens": getattr(prompt_detail, "cached_tokens", None),
                "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else None,
                "tool_call_n": len(tools),
                "status": "complete" if finish in COMPLETE_FINISHES and not tools else "request_error",
            })
            drift = pin.check(response.model) if row["status"] == "complete" else None
            if drift:
                row.update({"status": "request_error", "error_type": drift, "fatal": True})
            elif row["status"] != "complete":
                row.update({"error_type": "unexpected_finish_or_tool_call", "fatal": bool(tools)})
        except Exception as exc:  # noqa: BLE001 - never serialize SDK messages: they can echo upstream data
            status_code = getattr(exc, "status_code", None)
            row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                        "http_status": status_code, "fatal": status_code in {400, 401, 402, 403, 404}})
        row.update({"latency_s": round(time.monotonic() - start, 4), "finished_at": base.now()})
        if row["status"] == "complete":
            guard.add(dp.reported_tokens(row))
        elif not row.get("fatal"):
            row["retry_wait_seconds"] = 60 if row.get("http_status") == 429 else 30 if row.get("http_status") == 503 else 5
        outage.record(row)
        if row.get("fatal"):
            halt.set()
        return row

    def limited(client, item, shard: int, lane: int) -> dict[str, Any]:
        with gate:  # waiting here is not part of the measured latency: the clock starts inside `request`
            return request(client, item, shard, lane)

    return limited


def score_callback(card_id: str):
    def score(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        scored, summaries = dp.score_arm_rows(manifest, rows, rebuilt)
        for by_dataset in summaries.values():
            for summary in by_dataset.values():
                if summary["status"] != "complete":  # withhold headline metrics on partial data
                    for key in pr.HEADLINE_KEYS:
                        summary.pop(key, None)
        v1.write_jsonl_atomic(output / "scores.jsonl", scored)
        base.atomic_json(output / "summary.json", {
            "protocol_id": wm.PROTOCOL_ID, "phase": wm.PHASE, "measurement_card_id": card_id,
            "model_id": base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": base.now(),
            "expected_n": len(manifest["items"]),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "cost_usd": None, "cost_basis": "OpenCode Go subscription; list-price estimate in the analysis",
        })
    return score


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="send student requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="re-send only attempts without a completed response")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    config, _ = wm.load_config()
    student = config["student"]
    registration = load_registration()
    manifest, rebuilt = wm.build_manifest()
    if manifest != wm.load_frozen_manifest():
        raise SystemExit("Error: the rebuilt weakness-map manifest differs from the frozen weakness_manifest_v1.json")
    items = [v1.item_from_manifest_row(row, rebuilt) for row in manifest["items"]]
    endpoint, key, model, credential_source = labels.resolve_route({"route": {"profile_id": student["profile_id"]}})
    gates = evaluate_gates(config, manifest, registration, (endpoint, model, bool(key)))
    print(f"phase={wm.PHASE} protocol={wm.PROTOCOL_ID} attempts={manifest['n']} items={manifest['item_count']} "
          f"arms={manifest['arm_counts']} route={urlsplit(endpoint).hostname}/{model} credential={credential_source}")
    print(f"manifest_sha256={manifest['manifest_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    print(f"preflight=passed attempts={manifest['n']} endpoint_calls=0", flush=True)
    if not args.execute:
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise SystemExit("Error: execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    card_id = registration["card_ids"][wm.PHASE]
    output = OUTPUT_ROOT / student["profile_id"]
    condition = pr.reconcile_resume(output, build_condition(config, manifest, registration, endpoint, model,
                                                            credential_source), args.resume)
    guard = pr.BudgetGuard(student["budget_tokens"], pr.existing_usage(output))
    base.MODEL, base.PROFILE, base.PROTOCOL, base.CARD_ID = model, student["profile_id"], wm.PROTOCOL_ID, card_id
    base.request = make_request(student, card_id, guard, pr.OutageGuard(student["stop_after_timeouts"]),
                                ModelPin(student["model_identity"]))
    output.mkdir(parents=True, exist_ok=True)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as events:
        events.write(json.dumps({"at": base.now(), "phase": wm.PHASE, "resume": args.resume,
                                 "max_in_flight": student["max_in_flight"],
                                 "stop_after_timeouts": student["stop_after_timeouts"],
                                 "runner_sha256": v1.sha256_file(Path(__file__)), "note": args.note},
                                ensure_ascii=False) + "\n")
    with OpenAI(base_url=endpoint, api_key=key, timeout=student["timeout_seconds"],
                max_retries=student["sdk_retries"]) as client:
        base.execute(output, manifest, rebuilt, items, condition, client, args.resume,
                     score_callback=score_callback(card_id), runner_path=Path(__file__), work_stealing=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
