"""Run the prospective diagnostic campaign (openspec change: diagnostic-prospective-campaign).

From the repo root:
  .venv/bin/python -m code_benchmark.run_diagnostic_prospective --phase wide
  .venv/bin/python -m code_benchmark.run_diagnostic_prospective --phase core --oracle-evidence <jsonl> \
      [--retrieved-evidence <jsonl>]
  .venv/bin/python -m code_benchmark.run_diagnostic_prospective --phase wide --execute [--resume] [--tunnel-dns 172.16.30.1]

The default is an offline preflight: inputs, hashes, counts and gates are reported and
`endpoint_calls=0` is printed. `--execute` fails closed unless the measurement card is
pre-registered (registration.json + measurement_card.md) and, for core, diagnostic readiness
reports inference_ready and the router rule and cue lexicon on disk carry the SHA-256 values of the
registration's router entry (design Decision 11). The engine, condition freeze and resume rules are
those of MC-80/82/83; completed attempts, including truncated or unparsed ones, are never retried
automatically.
Arms K and KS appear with --retrieved-evidence (corpus v0 records, task 7.3); each of their rows carries the
retrieval trace: corpus and configuration hashes, the ranked chunks with their scores and the evidence-block hash.

Operational options, off by default so that the registered condition is what runs. Every launch is appended
to <output>/operator_events.jsonl with the options used and the runner hash:
  --max-in-flight N        cap simultaneous requests below the registered lane count (a deviation to report)
  --stop-after-timeouts N  pause the run after N consecutive network failures instead of timing out item by item
  --note TEXT              why this launch differs from the previous one
"""
from __future__ import annotations

import argparse
import json
import random
import re
import socket
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import dotenv_values
from openai import OpenAI

try:
    from code_benchmark import diagnostic
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_router as router
    from code_benchmark import run_muse13_direct_mc80 as base
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic
    import diagnostic_prospective as dp
    import diagnostic_router as router
    import run_muse13_direct_mc80 as base
    import vi_multimodel as v1

ROOT = dp.ROOT
OUTPUT_ROOT = ROOT / "all_res" / "diagnostic_prospective"
MEASUREMENT_CARD = ROOT / "measurement_card.md"
PILOT_DIR = ROOT / "all_res" / "diagnostic_v1" / "pilot-review-v4"
IMPLEMENTATION_FIELDS = {"runner_sha256", "wrapper_sha256", "measurement_card_hash"}
HEADLINE_KEYS = ("accuracy", "correct", "ci95", "accuracy_rows", "by_gold", "by_group", "em", "em_count",
                 "em_ci95", "token_f1", "token_f1_ci95", "legacy_raw_em", "legacy_raw_char_f1",
                 "legacy_final_em", "legacy_final_char_f1")


@dataclass(frozen=True)
class Gate:
    name: str
    ok: bool
    detail: str


# ---------------------------------------------------------------- gates

def evaluate_gates(phase: str, protocol: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                   env: dict[str, str | None], *, card_text: str | None = None, readiness=None,
                   root: Path = ROOT) -> list[Gate]:
    gates: list[Gate] = []
    card_id = (registration.get("card_ids") or {}).get(phase)
    text = MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    gates.append(Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md"))
    card_file = (registration.get("card_files") or {}).get(phase)
    gates.append(Gate("detail_card", bool(card_file) and (root / str(card_file)).is_file(),
                      str(card_file or "no detail card file recorded")))
    frozen = registration.get("frozen") or {}
    differing = [name for name, ok in (
        ("protocol", frozen.get("protocol_sha256") == manifest["campaign_protocol_sha256"]),
        ("prompt_templates", frozen.get("prompt_templates_sha256") == manifest["prompt_templates_sha256"]),
        ("manifest", (frozen.get("manifest_sha256") or {}).get(phase) == manifest["manifest_sha256"]),
        ("evidence", (frozen.get("evidence_sha256") or {}).get(phase, {}) == manifest["evidence_sha256"]),
    ) if not ok]
    gates.append(Gate("frozen_hashes", not differing, "all match" if not differing else f"differ: {differing}"))
    endpoint = urlsplit(env.get("OPENAI_BASE_URL") or "")
    model = protocol["model"]
    identity = (endpoint.hostname == model["endpoint_host"]
                and endpoint.path.rstrip("/") == model["endpoint_path"].rstrip("/")
                and env.get("OPENAI_MODEL") == model["requested_id"] and bool(env.get("OPENAI_API_KEY")))
    gates.append(Gate("endpoint_identity", identity,
                      f"host={endpoint.hostname} model={env.get('OPENAI_MODEL')} (card expects "
                      f"{model['endpoint_host']} / {model['requested_id']})"))
    if protocol["phases"][phase]["requires_inference_ready"]:
        controls = diagnostic.CONTROLS_PATH if diagnostic.CONTROLS_PATH.is_file() else None
        try:
            report = (readiness or (lambda: diagnostic.readiness_report(audit_dir=PILOT_DIR, controls_path=controls)))()
        except diagnostic.DiagnosticError as exc:
            report = {"inference_ready": False, "inference_blockers": [str(exc)]}
        blockers = "; ".join(report.get("inference_blockers", []))[:300]
        gates.append(Gate("inference_ready", bool(report.get("inference_ready")),
                          blockers or f"ready (controls sha256 {str(report.get('controls_sha256'))[:12]})"))
    if phase == "core":
        gates.append(router_gate(protocol, registration, root))
    return gates


def router_gate(protocol: dict[str, Any], registration: dict[str, Any], root: Path = ROOT) -> Gate:
    """The rule the core run is evaluated with is frozen before the first core request (design Decision 11)."""
    entry = registration.get("router")
    if not isinstance(entry, dict):
        return Gate("router_rule", False, "the registration has no router entry")
    try:
        lexicon, lexicon_sha256 = router.load_lexicon(root / router.LEXICON_PATH.relative_to(ROOT))
        rule, rule_sha256 = router.load_rule(root / router.RULE_PATH.relative_to(ROOT), protocol["datasets"], lexicon)
    except SystemExit as exc:
        return Gate("router_rule", False, str(exc))
    differing = [name for name, actual in (("rule", rule_sha256), ("cue_lexicon", lexicon_sha256))
                 if entry.get(f"{name}_sha256") != actual]
    return Gate("router_rule", not differing, f"{rule['router_id']} as registered" if not differing
                else f"{differing} differ from the registered sha256")


# ---------------------------------------------------------------- process-local DNS shim

def tunnel_a_record(name: str, server: str, timeout: float = 4.0) -> str:
    """Ask the in-tunnel DNS server for an A record (stdlib only; nothing on the host is reconfigured)."""
    header = struct.pack(">HHHHHH", random.randint(0, 0xFFFF), 0x0100, 1, 0, 0, 0)
    question = b"".join(bytes([len(part)]) + part.encode() for part in name.split(".")) + b"\x00" + struct.pack(">HH", 1, 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(header + question, (server, 53))
        data, _ = sock.recvfrom(1500)
    finally:
        sock.close()
    _, flags, _, answers, _, _ = struct.unpack(">HHHHHH", data[:12])
    if flags & 0xF:
        raise RuntimeError(f"dns_rcode_{flags & 0xF}")
    position = 12
    while data[position] != 0:
        position += data[position] + 1
    position += 5
    for _ in range(answers):
        if data[position] & 0xC0 == 0xC0:
            position += 2
        else:
            while data[position] != 0:
                position += data[position] + 1
            position += 1
        rtype, _, _, length = struct.unpack(">HHIH", data[position:position + 10])
        position += 10
        rdata = data[position:position + length]
        position += length
        if rtype == 1 and length == 4:
            return socket.inet_ntoa(rdata)
    raise RuntimeError("no_a_record")


def install_resolver_shim(host: str, server: str) -> str:
    """Map `host` to the in-tunnel DNS answer for THIS process only; Host header and system resolver untouched."""
    address = tunnel_a_record(host, server)
    original = socket.getaddrinfo

    def patched(name, *args, **kwargs):
        return original(address if name == host else name, *args, **kwargs)

    socket.getaddrinfo = patched
    return address


# ---------------------------------------------------------------- budget guard and request

class BudgetGuard:
    """Cumulative reported-token guard. Attempts with unreported usage are not counted (unknown, not zero)."""

    def __init__(self, cap: int, used: int = 0):
        self.cap = cap
        self.used = used
        self._lock = threading.Lock()

    def exhausted(self) -> bool:
        with self._lock:
            return self.used >= self.cap

    def add(self, tokens: int | None) -> None:
        if isinstance(tokens, int):
            with self._lock:
                self.used += tokens


NETWORK_ERRORS = frozenset({"APITimeoutError", "ReadTimeout", "ConnectTimeout", "APIConnectionError",
                            "ConnectError", "RemoteProtocolError"})


class OutageGuard:
    """Opt-in circuit breaker. After `threshold` consecutive network-level failures (any success resets the count)
    the next request is fatal, so the engine pauses the run and the items stay resumable. 0 disables it."""

    def __init__(self, threshold: int = 0):
        self.threshold = threshold
        self.consecutive = 0
        self._lock = threading.Lock()

    def tripped(self) -> bool:
        with self._lock:
            return 0 < self.threshold <= self.consecutive

    def record(self, row: dict[str, Any]) -> None:
        with self._lock:
            if row.get("status") == "complete":
                self.consecutive = 0
            elif row.get("error_type") in NETWORK_ERRORS:
                self.consecutive += 1


def existing_usage(output: Path) -> int:
    """Tokens already spent by completed attempts of an interrupted run (latest row per run key)."""
    path = output / "attempts.jsonl"
    if not path.is_file():
        return 0
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            latest[row["run_key"]] = row
    return sum(dp.reported_tokens(row) or 0 for row in latest.values() if row.get("status") == "complete")


def make_request(protocol: dict[str, Any], phase: str, card_id: str, guard: BudgetGuard, *,
                 outage: OutageGuard | None = None, max_in_flight: int | None = None,
                 retrieval_traces: dict[str, dict[str, Any]] | None = None):
    transport = protocol["transport"]
    retrieval_traces = retrieval_traces or {}
    expected_model = protocol["model"]["self_reported_id"]
    outage = outage or OutageGuard(0)
    gate = threading.BoundedSemaphore(max_in_flight) if max_in_flight else None
    halt = threading.Event()  # set by any fatal row; with a cap, lanes queued at the gate then send nothing

    def request(client, item, shard: int, lane: int) -> dict[str, Any]:
        cap = transport["max_output_tokens"]
        row: dict[str, Any] = {
            "run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}",
            "dataset_id": item.dataset_id, "item_id": item.item_id, "replicate_id": item.replicate_id,
            "arm": dp.arm_of_replicate(item.replicate_id), "phase": phase,
            "profile_id": base.PROFILE, "protocol_id": base.PROTOCOL, "measurement_card_id": card_id,
            "model_id": base.MODEL, "transport": "direct-api", "api_protocol": transport["api_protocol"],
            "shard": shard, "lane": lane, "prompt_sha256": v1.sha256_bytes(item.prompt.encode()),
            "raw_prompt": item.prompt, "raw_response": "", "temperature_sent": transport["temperature"],
            "reasoning_effort_sent": None, "seed_sent": None, "max_tokens": cap, "started_at": base.now(),
        }
        if row["arm"] in dp.RETRIEVAL_ARMS:
            row["retrieval"] = retrieval_traces[row["item_key"]]
        for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                    (gate is not None and halt.is_set(), "halted_before_send")):
            if blocked:
                row.update({"status": "request_error", "finish_reason": "error", "error_type": error_type,
                            "fatal": True, "latency_s": 0.0, "finished_at": base.now()})
                halt.set()
                return row
        start = time.monotonic()
        stream = None
        try:
            stream = client.responses.create(
                model=base.MODEL,
                input=[{"role": "system", "content": transport["system_prompt"]},
                       {"role": "user", "content": item.prompt}],
                temperature=transport["temperature"], max_output_tokens=cap, stream=True,
            )
            terminal = None
            pieces: list[str] = []
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
                       for part in output.get("content", [])
                       if part.get("type") == "output_text" and isinstance(part.get("text"), str)]
            text = "".join(visible) if visible else "".join(pieces)
            status = terminal.get("status")
            reason = (terminal.get("incomplete_details") or {}).get("reason")
            length = status == "incomplete" and reason == "max_output_tokens"
            tools = sum(output.get("type") == "function_call" for output in terminal.get("output", []))
            usage = terminal.get("usage") or {}
            row.update({
                "raw_response": text, "response_status": status, "incomplete_reason": reason,
                "finish_reason": "length" if length else "stop" if status == "completed" else "error",
                "status": "complete" if (status == "completed" or length) and not tools else "request_error",
                "response_model_id": terminal.get("model"), "request_id": terminal.get("id"), "tool_call_n": tools,
                "prompt_tokens": usage.get("input_tokens"), "completion_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cached_prompt_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens"),
                "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens"),
            })
            if row["status"] == "complete" and terminal.get("model") != expected_model:
                row.update({"status": "request_error", "error_type": "model_identity_drift", "fatal": True})
            elif row["status"] != "complete":
                code = str((terminal.get("error") or {}).get("code") or "unknown")
                permanent = code in {"invalid_api_key", "authentication_error", "permission_denied",
                                     "insufficient_quota", "billing_not_active", "model_not_found",
                                     "invalid_request_error"}
                row.update({"error_type": "provider_terminal_failure", "provider_error_code": code,
                            "fatal": bool(tools) or permanent})
        except Exception as exc:  # noqa: BLE001 - never serialize SDK messages: they can echo upstream data
            status_code = getattr(exc, "status_code", None)
            row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                        "http_status": status_code, "fatal": status_code in {400, 401, 402, 403, 404}})
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception as exc:  # noqa: BLE001
                    row["stream_close_error"] = type(exc).__name__
        row.update({"latency_s": round(time.monotonic() - start, 4), "finished_at": base.now()})
        if row["status"] == "complete":
            guard.add(dp.reported_tokens(row))
        elif not row.get("fatal"):
            row["retry_wait_seconds"] = 60 if row.get("http_status") == 429 else 30 if row.get("http_status") == 503 else 5
        outage.record(row)
        if row.get("fatal"):
            halt.set()
        return row

    if gate is None:
        return request

    def limited(client, item, shard: int, lane: int) -> dict[str, Any]:
        with gate:  # waiting here is not part of the measured latency: the clock starts inside `request`
            return request(client, item, shard, lane)

    return limited


# ---------------------------------------------------------------- condition, scoring, execution

def supplement_registration_view(registration: dict[str, Any], supplement: dict[str, Any], phase: str) -> dict[str, Any]:
    """The registration record as the gates and the condition read it, for one registered supplement: its own card
    and manifest hash, the protocol and template hashes of the phase it supplements."""
    frozen = registration["frozen"]
    return {
        "status": registration.get("status"),
        "card_ids": {phase: supplement.get("card_id")},
        "card_files": {phase: supplement.get("card_file")},
        "frozen": {
            "protocol_sha256": frozen["protocol_sha256"],
            "prompt_templates_sha256": frozen["prompt_templates_sha256"],
            "manifest_sha256": {phase: (supplement.get("frozen") or {}).get("manifest_sha256")},
            "evidence_sha256": {phase: {}},
        },
    }


def build_condition(phase: str, protocol: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    endpoint: str, templates_version: str, runner_path: Path, *,
                    supplement: dict[str, Any] | None = None,
                    retrieval: dict[str, str] | None = None) -> dict[str, Any]:
    transport, model = protocol["transport"], protocol["model"]
    extra: dict[str, Any] = {}
    if supplement is not None:  # a registered supplement freezes its own operational limits with the condition
        extra = {"supplement_id": supplement["supplement_id"], "supplement_design": manifest["supplement_design"],
                 "operational": supplement.get("operational") or {}}
    if retrieval is not None:  # only a run with arms K and KS has a corpus and a retrieval configuration
        extra["retrieval"] = retrieval
    return {**extra,
        "protocol_id": dp.PROTOCOL_ID, "protocol_version": 1, "phase": phase,
        "measurement_card_id": registration["card_ids"][phase],
        "measurement_card_hash": v1.sha256_file(MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][phase]),
        "manifest_sha256": manifest["manifest_sha256"], "parent_manifest_sha256": manifest["parent_manifest_sha256"],
        "campaign_protocol_sha256": manifest["campaign_protocol_sha256"],
        "prompt_templates_sha256": manifest["prompt_templates_sha256"], "prompt_version": templates_version,
        "evidence_sha256": manifest["evidence_sha256"], "pilot_content_sha256": manifest["pilot_content_sha256"],
        "dataset_counts": manifest["dataset_counts"], "arm_counts": manifest["arm_counts"],
        "model_id": model["requested_id"], "model_ref": model["requested_id"],
        "self_reported_model_id": model["self_reported_id"], "profile_id": model["profile_id"],
        "provider": model["provider"], "transport": "direct-api", "api_protocol": transport["api_protocol"],
        "endpoint_host": urlsplit(endpoint).hostname, "base_url_sha256": v1.sha256_bytes(endpoint.encode()),
        "temperature_requested": transport["temperature"], "temperature_effective": None,
        "reasoning_effort_sent": None,
        "reasoning_policy": "field omitted; provider default; the endpoint reports no reasoning tokens",
        "seed_sent": None, "tools": "none", "system_prompt": transport["system_prompt"],
        "gateway_optout": {"header_name": "x-9router-token-saver", "value": "off"},
        "max_tokens": transport["max_output_tokens"], "campaign_cap_tokens": protocol["budget"]["campaign_cap_tokens"],
        "request_timeout_seconds": transport["timeout_seconds"], "sdk_retries": transport["sdk_retries"],
        "workers": transport["shards"] * transport["lanes"], "shards": transport["shards"],
        "workers_per_shard": transport["lanes"],
        "final_segment_rule_id": protocol["scoring"]["final_segment_rule_id"],
        "scorer_sha256": v1.sha256_file(ROOT / "code_benchmark" / "score_vi_multimodel.py"),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)),
        "runner_sha256": v1.sha256_file(runner_path),
    }


def reconcile_resume(output: Path, condition: dict[str, Any], resume: bool) -> dict[str, Any]:
    saved = output / "condition.json"
    if not saved.is_file():
        return condition
    if not resume:
        raise SystemExit("Error: existing run requires --resume and an identical condition")
    frozen = json.loads(saved.read_text(encoding="utf-8"))
    current = {key: value for key, value in condition.items() if key not in IMPLEMENTATION_FIELDS}
    if current != {key: value for key, value in frozen.items() if key not in IMPLEMENTATION_FIELDS}:
        raise SystemExit("Error: resume would change the frozen inference condition")
    return frozen


def make_score_callback(phase: str, card_id: str, supplement_id: str | None = None):
    def score(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        scored, summaries = dp.score_arm_rows(manifest, rows, rebuilt)
        for by_dataset in summaries.values():
            for summary in by_dataset.values():
                if summary["status"] != "complete":  # withhold headline metrics on partial data
                    for key in HEADLINE_KEYS:
                        summary.pop(key, None)
        v1.write_jsonl_atomic(output / "scores.jsonl", scored)
        base.atomic_json(output / "summary.json", {
            "protocol_id": dp.PROTOCOL_ID, "phase": phase, "supplement_id": supplement_id,
            "measurement_card_id": card_id, "model_id": base.MODEL,
            "transport": "direct-api", "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": base.now(),
            "expected_n": len(manifest["items"]),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "cost_usd": None, "cost_basis": "IEC tariff not supplied; reported usage retained per attempt",
        })
    return score


def configure_engine(protocol: dict[str, Any], phase: str, card_id: str, guard: BudgetGuard, *,
                     outage: OutageGuard | None = None, max_in_flight: int | None = None,
                     retrieval_traces: dict[str, dict[str, Any]] | None = None) -> None:
    transport = protocol["transport"]
    if (base.SHARDS, base.LANES) != (transport["shards"], transport["lanes"]):
        raise SystemExit("Error: engine shard/lane constants differ from the campaign protocol")
    base.MODEL = protocol["model"]["requested_id"]
    base.PROFILE = protocol["model"]["profile_id"]
    base.PROTOCOL = dp.PROTOCOL_ID
    base.CARD_ID = card_id
    base.request = make_request(protocol, phase, card_id, guard, outage=outage, max_in_flight=max_in_flight,
                                retrieval_traces=retrieval_traces)


def record_launch(output: Path, phase: str, *, resume: bool, max_in_flight: int | None,
                  stop_after_timeouts: int | None, note: str, lanes: int, supplement_id: str | None = None) -> None:
    """Append-only operator record of how this launch differs from the registered condition (if it does)."""
    output.mkdir(parents=True, exist_ok=True)
    event = {"at": base.now(), "phase": phase, "supplement_id": supplement_id, "resume": resume,
             "runner_sha256": v1.sha256_file(Path(__file__)),
             "lanes_configured": lanes, "max_in_flight": max_in_flight, "stop_after_timeouts": stop_after_timeouts,
             "note": note}
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(event, ensure_ascii=False) + "\n")


def print_preflight(phase: str, manifest: dict[str, Any], protocol: dict[str, Any], gates: list[Gate]) -> None:
    transport = protocol["transport"]
    print(f"phase={phase} protocol={dp.PROTOCOL_ID} items={manifest['item_count']} attempts={manifest['n']} "
          f"arms={manifest['arm_counts']}")
    if "supplement_id" in manifest:
        print(f"supplement={manifest['supplement_id']} design={manifest['supplement_design']}")
    print(f"manifest_sha256={manifest['manifest_sha256']}")
    print(f"prompt_templates_sha256={manifest['prompt_templates_sha256']} "
          f"campaign_protocol_sha256={manifest['campaign_protocol_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    print(f"preflight=passed items={manifest['item_count']} attempts={manifest['n']} "
          f"workers={transport['shards'] * transport['lanes']} endpoint_calls=0", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phase", choices=dp.PHASES, required=True)
    parser.add_argument("--oracle-evidence", type=Path, help="oracle evidence JSONL for arm O (core only)")
    parser.add_argument("--retrieved-evidence", type=Path,
                        help="retrieved-evidence JSONL for arms K and KS (core only)")
    parser.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    parser.add_argument("--resume", action="store_true", help="resume only unfinished technical requests")
    parser.add_argument("--tunnel-dns", default=None,
                        help="in-tunnel DNS server used to resolve the endpoint host inside this process only")
    parser.add_argument("--max-in-flight", type=int, default=None, metavar="N",
                        help="operational cap on simultaneous requests (default: none, every registered lane sends)")
    parser.add_argument("--stop-after-timeouts", type=int, default=None, metavar="N",
                        help="pause the run after N consecutive network failures (default: off)")
    parser.add_argument("--note", default="", help="free text recorded with this launch in operator_events.jsonl")
    parser.add_argument("--supplement", default=None, metavar="ID",
                        help="a supplement of --phase registered in registration.json (for example a further "
                             "replicate of one arm), with its own card, manifest hash and operational limits")
    args = parser.parse_args(argv)
    if args.resume and not args.execute:
        parser.error("--resume requires --execute")
    for flag in ("oracle_evidence", "retrieved_evidence"):
        if getattr(args, flag) and args.supplement:
            parser.error(f"--{flag.replace('_', '-')} cannot be combined with --supplement")
        if getattr(args, flag) and args.phase != "core":
            parser.error(f"--{flag.replace('_', '-')} applies to the core phase only")
    for flag in ("max_in_flight", "stop_after_timeouts"):
        if getattr(args, flag) is not None and getattr(args, flag) < 1:
            parser.error(f"--{flag.replace('_', '-')} must be a positive integer")

    protocol = dp.load_protocol()
    templates = dp.load_templates()
    registration = dp.load_registration()
    supplement = dp.load_supplement(registration, args.supplement, protocol) if args.supplement else None
    if supplement and supplement["base_phase"] != args.phase:
        parser.error(f"supplement {args.supplement} belongs to phase {supplement['base_phase']}, not {args.phase}")
    registered = supplement_registration_view(registration, supplement, args.phase) if supplement else registration
    # registered limits (a supplement's, or the core entry's) apply by default and other values are refused
    operational = ((supplement or {}).get("operational") if supplement
                   else (registration.get(args.phase) or {}).get("operational")) or {}
    for flag in ("max_in_flight", "stop_after_timeouts"):
        value = getattr(args, flag)
        if value is not None and operational.get(flag) not in (None, value):
            parser.error(f"--{flag.replace('_', '-')} {value} differs from the {operational[flag]} registered "
                         f"for {args.supplement or args.phase}")
        if value is None:
            setattr(args, flag, operational.get(flag))
    evidence_by_arm: dict[str, dict[str, list[dict[str, Any]]]] = {}
    main_items = v1.rebuild_items(protocol["parent"]["manifest_phase"])
    if args.oracle_evidence:
        evidence_by_arm["O"] = dp.load_oracle_evidence(args.oracle_evidence, protocol, main_items)
    traces: dict[str, dict[str, Any]] = {}
    retrieval = None
    if args.retrieved_evidence:
        evidence_by_arm["K"], traces = dp.load_retrieved_evidence(args.retrieved_evidence, protocol, main_items)
        if not traces:
            parser.error(f"--retrieved-evidence {args.retrieved_evidence} holds no records")
        for key, trace in traces.items():
            block = dp.render_evidence_block(evidence_by_arm["K"][key], templates)
            trace["evidence_block_sha256"] = v1.sha256_bytes(block.encode("utf-8"))
        first = next(iter(traces.values()))
        retrieval = {"corpus_sha256": first["corpus_sha256"],
                     "retrieval_config_sha256": first["retrieval_config_sha256"],
                     "records_sha256": v1.sha256_file(args.retrieved_evidence)}
    manifest, rebuilt = dp.build_manifest(args.phase, evidence_by_arm=evidence_by_arm, main_items=main_items,
                                          supplement=supplement)
    items = dp.verify_manifest_rows(manifest, rebuilt)
    env = dotenv_values(ROOT / ".env")
    gates = evaluate_gates(args.phase, protocol, manifest, registered, env)
    print_preflight(args.phase, manifest, protocol, gates)
    if not args.execute:
        return 0

    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise SystemExit("Error: execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    endpoint, key = str(env["OPENAI_BASE_URL"]), str(env["OPENAI_API_KEY"])
    if args.tunnel_dns:
        address = install_resolver_shim(urlsplit(endpoint).hostname or "", args.tunnel_dns)
        print(f"resolver shim (this process only): {urlsplit(endpoint).hostname} -> {address} via {args.tunnel_dns}")
    card_id = str(registered["card_ids"][args.phase])
    profile = protocol["model"]["profile_id"]
    output = (OUTPUT_ROOT / f"{args.phase}-supplements" / supplement["supplement_id"] / profile if supplement
              else OUTPUT_ROOT / args.phase / profile)
    output.parent.mkdir(parents=True, exist_ok=True)
    condition = reconcile_resume(
        output, build_condition(args.phase, protocol, manifest, registered, endpoint, templates["version"],
                                Path(__file__), supplement=supplement, retrieval=retrieval), args.resume)
    guard = BudgetGuard(protocol["budget"]["campaign_cap_tokens"], existing_usage(output))
    transport = protocol["transport"]
    configure_engine(protocol, args.phase, card_id, guard, outage=OutageGuard(args.stop_after_timeouts or 0),
                     max_in_flight=args.max_in_flight, retrieval_traces=traces)
    record_launch(output, args.phase, resume=args.resume, max_in_flight=args.max_in_flight,
                  stop_after_timeouts=args.stop_after_timeouts, note=args.note,
                  lanes=transport["shards"] * transport["lanes"],
                  supplement_id=supplement["supplement_id"] if supplement else None)
    if args.max_in_flight or args.stop_after_timeouts:
        print(f"operational options: max_in_flight={args.max_in_flight} stop_after_timeouts={args.stop_after_timeouts} "
              f"(registered lanes: {transport['shards'] * transport['lanes']})", flush=True)
    with OpenAI(base_url=endpoint, api_key=key, timeout=transport["timeout_seconds"],
                max_retries=transport["sdk_retries"], default_headers=transport["gateway_header"]) as client:
        base.execute(output, manifest, rebuilt, items, condition, client, args.resume,
                     score_callback=make_score_callback(args.phase, card_id,
                                                        supplement["supplement_id"] if supplement else None),
                     runner_path=Path(__file__))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
