"""Run one Muse student's attempts of the self-improvement loop on the /table suite (openspec change
diagnostic-router-loop, decision 12; card MC-108).

From the repo root:
  .venv/bin/python -m code_benchmark.run_table_loop_muse --student muse13           # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_table_loop_muse --student muse13 --execute [--resume]
  .venv/bin/python -m code_benchmark.run_table_loop_muse --student muse12 --execute [--resume]

Both students are on the direct OpenCode Go route of MC-98 and MC-102 (Responses API, not streamed, one routing
session per attempt), with the system prompt and the 20,000-token cap of MC-105's MiMo route. Temperature, seed and
reasoning effort are not sent. The engine, the guards and the scoring are MC-105's. `--execute` fails closed unless
the MC-108 heading and detail card exist, the configuration and this student's manifest carry the registered
SHA-256 values, and the route is the registered one.
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
    from code_benchmark import diagnostic_table_loop_muse as tm
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_router_labels as labels
    from code_benchmark import run_self_loop as rsl
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_reading_v3
    from code_benchmark.run_weakness_map import ModelPin
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_table_loop_muse as tm
    import run_diagnostic_prospective as pr
    import run_router_labels as labels
    import run_self_loop as rsl
    import vi_multimodel as v1
    import vi_reading_v3
    from run_weakness_map import ModelPin

ROOT = dp.ROOT
OUTPUT_ROOT = ROOT / "all_res" / "diagnostic_router_loop" / "table_loop_muse"
base = pr.base
Gate = pr.Gate
SESSION_HEADER = rsl.SESSION_HEADER
# Provider error codes that no re-send can fix; they stop the run (as the campaign engine does).
PERMANENT_CODES = frozenset({"invalid_api_key", "authentication_error", "permission_denied", "insufficient_quota",
                             "billing_not_active", "model_not_found", "invalid_request_error"})


def load_registration(path: Path = tm.REGISTRATION_PATH) -> dict[str, Any]:
    try:
        registration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read the Muse table-loop registration {path}: {exc}") from exc
    for key in ("card_ids", "card_files", "frozen", "analysis"):
        if key not in registration:
            raise SystemExit(f"Error: the Muse table-loop registration lacks {key}")
    return registration


def evaluate_gates(student: str, manifest: dict[str, Any], registration: dict[str, Any], route_ok: bool,
                   route_detail: str, *, card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    card_id = (registration.get("card_ids") or {}).get(tm.PHASE)
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    gates = [Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md")]
    card_file = (registration.get("card_files") or {}).get(tm.PHASE)
    gates.append(Gate("detail_card", bool(card_file) and (root / str(card_file)).is_file(),
                      str(card_file or "no detail card file recorded")))
    frozen = registration.get("frozen") or {}
    differing = [name for name, ok in (("config", frozen.get("config_sha256") == manifest["config_sha256"]),
                                       ("manifest", (frozen.get("manifest_sha256") or {}).get(student)
                                        == manifest["manifest_sha256"])) if not ok]
    gates.append(Gate("frozen_hashes", not differing, "all match" if not differing else f"differ: {differing}"))
    gates.append(Gate("route_identity", route_ok, route_detail))
    return gates


def muse_route(student: dict[str, Any]) -> tuple[str, str, str, bool, str]:
    """(endpoint, key, credential source, ok, detail). Both students use the API root and credential of the
    registered Muse Spark 1.3 profile; the model id is the configuration's, sent as it is."""
    endpoint, key, _, credential_source = labels.resolve_route({"route": {"profile_id": student["route_profile"]}})
    ok = urlsplit(endpoint).hostname == student["endpoint_host"] and bool(key)
    return endpoint, key, credential_source, ok, f"{urlsplit(endpoint).hostname} {student['model_id']}"


def session_id(run_key: str) -> str:
    """One routing session per attempt, so two draws of an item never share one."""
    return f"vmlu-mc108-{v1.sha256_bytes(run_key.encode('utf-8'))[:16]}"


def _base_row(item: v1.EvalItem, card_id: str, shard: int, lane: int, api_protocol: str) -> dict[str, Any]:
    return {"run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
            "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
            "phase": tm.PHASE, "profile_id": base.PROFILE, "protocol_id": base.PROTOCOL, "measurement_card_id": card_id,
            "model_id": base.MODEL, "transport": "direct-api", "api_protocol": api_protocol, "shard": shard,
            "lane": lane, "prompt_sha256": v1.sha256_bytes(item.prompt.encode()), "raw_prompt": item.prompt,
            "raw_response": "", "started_at": base.now()}


def read_response(response: Any) -> dict[str, Any]:
    """The fields a row keeps from a non-streamed Responses API reply. A reply cut at the token cap is complete
    (scored as it is); any other unfinished reply, or one with a tool call, is a request error."""
    output = list(getattr(response, "output", None) or [])
    tools = sum(getattr(entry, "type", None) == "function_call" for entry in output)
    visible = [part.text for entry in output if getattr(entry, "type", None) == "message"
               for part in (getattr(entry, "content", None) or [])
               if getattr(part, "type", None) == "output_text" and isinstance(getattr(part, "text", None), str)]
    status = getattr(response, "status", None)
    incomplete = getattr(response, "incomplete_details", None)
    reason = getattr(incomplete, "reason", None) if incomplete is not None else None
    length = status == "incomplete" and reason == "max_output_tokens"
    usage = getattr(response, "usage", None)
    details = getattr(usage, "output_tokens_details", None)
    prompt_details = getattr(usage, "input_tokens_details", None)
    return {
        "raw_response": "".join(visible), "response_status": status, "incomplete_reason": reason,
        "finish_reason": "length" if length else "stop" if status == "completed" else "error",
        "status": "complete" if (status == "completed" or length) and not tools else "request_error",
        "response_model_id": getattr(response, "model", None), "request_id": getattr(response, "id", None),
        "tool_call_n": tools, "prompt_tokens": getattr(usage, "input_tokens", None),
        "completion_tokens": getattr(usage, "output_tokens", None), "total_tokens": getattr(usage, "total_tokens", None),
        "cached_prompt_tokens": getattr(prompt_details, "cached_tokens", None),
        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        "provider_error_code": str(getattr(getattr(response, "error", None), "code", None) or "") or None,
    }


def make_muse_request(student: dict[str, Any], card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard,
                      pin: ModelPin):
    """One non-streamed Responses API request per attempt, behind one gate of the registered size."""
    gate = threading.BoundedSemaphore(student["max_in_flight"])
    halt = threading.Event()  # set by any fatal row; lanes queued at the gate then send nothing

    def request(client, item, shard: int, lane: int) -> dict[str, Any]:
        cap = student["max_output_tokens"]
        row = _base_row(item, card_id, shard, lane, student["api_protocol"])
        row.update({"temperature_sent": None, "reasoning_effort_sent": None, "seed_sent": None, "max_tokens": cap})
        if rsl._blocked(row, guard, outage, halt):  # noqa: SLF001 - MC-104's guard, shared on purpose
            halt.set()
            return row
        start = time.monotonic()
        try:
            response = client.responses.create(
                model=base.MODEL, input=[{"role": "system", "content": student["system_prompt"]},
                                         {"role": "user", "content": item.prompt}],
                max_output_tokens=cap, stream=False, extra_headers={SESSION_HEADER: session_id(item.run_key)})
            row.update(read_response(response))
            drift = pin.check(row["response_model_id"]) if row["status"] == "complete" else None
            if drift:
                row.update({"status": "request_error", "error_type": drift, "fatal": True})
            elif row["status"] != "complete":
                row.update({"error_type": "unexpected_finish_or_tool_call",
                            "fatal": bool(row["tool_call_n"]) or row["provider_error_code"] in PERMANENT_CODES})
        except Exception as exc:  # noqa: BLE001 - never serialize SDK messages: they can echo upstream data
            status_code = getattr(exc, "status_code", None)
            row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                        "http_status": status_code, "fatal": status_code in {400, 401, 402, 403, 404}})
        rsl._settle(row, start, guard, outage)  # noqa: SLF001
        if row.get("fatal"):
            halt.set()
        return row

    def limited(client, item, shard: int, lane: int) -> dict[str, Any]:
        with gate:  # waiting here is not part of the measured latency: the clock starts inside `request`
            return request(client, item, shard, lane)
    return limited


def build_condition(student: str, config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    route: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_id": tm.PROTOCOL_ID, "protocol_version": 1, "phase": tm.PHASE, "student": student,
        "measurement_card_id": registration["card_ids"][tm.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][tm.PHASE]),
        "config_sha256": manifest["config_sha256"], "manifest_sha256": manifest["manifest_sha256"],
        **{key: manifest[key] for key in ("main_manifest_sha256", "campaign_protocol_sha256", "prompt_templates_sha256",
                                         "earlier_manifest_sha256", "source_sha256", "dataset_counts", "arm_counts")},
        "loop": config["loop"], "student_config": config["students"][student], **route,
        "scorer_sha256": v1.sha256_file(ROOT / "code_benchmark" / "score_vi_multimodel.py"),
        "reading_v3_sha256": v1.sha256_file(Path(vi_reading_v3.__file__)),
        "module_sha256": v1.sha256_file(Path(tm.__file__)),
        "table_loop_module_sha256": v1.sha256_file(Path(tm.tl.__file__)),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)),
        "engine_sha256": v1.sha256_file(Path(pr.__file__)),
        "shared_runner_sha256": v1.sha256_file(Path(rsl.__file__)),
        "runner_sha256": v1.sha256_file(Path(__file__)),
    }


def score_callback(student: str, card_id: str):
    def score(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        scored, summaries = dp.score_arm_rows(manifest, rows, rebuilt)
        final = []
        for row in scored:
            if "token_f1" in row:  # reading: vi-reading-v3 is primary, v2 is kept beside it
                row = {**vi_reading_v3.rescore_row(row), "em_v2": row["em"], "token_f1_v2": row["token_f1"],
                       "prediction_v2": row["prediction"]}
            final.append(row)
        for by_dataset in summaries.values():
            for summary in by_dataset.values():
                if summary["status"] != "complete":  # withhold headline metrics on partial data
                    for key in pr.HEADLINE_KEYS:
                        summary.pop(key, None)
        v1.write_jsonl_atomic(output / "scores.jsonl", final)
        base.atomic_json(output / "summary.json", {
            "protocol_id": tm.PROTOCOL_ID, "phase": tm.PHASE, "student": student, "measurement_card_id": card_id,
            "model_id": base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": base.now(),
            "expected_n": len(manifest["items"]),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "reading_scorer": "vi-reading-v3 in scores.jsonl (em, token_f1); vi-reading-v2 beside it (em_v2, token_f1_v2); "
                              "the arm summaries above are v2",
        })
    return score


def record_launch(output: Path, student: str, *, resume: bool, note: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    event = {"at": base.now(), "phase": tm.PHASE, "student": student, "resume": resume,
             "runner_sha256": v1.sha256_file(Path(__file__)), "note": note}
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(event, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--student", choices=tm.STUDENTS, required=True)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="resume only unfinished technical requests")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    config, _ = tm.load_config()
    registration = load_registration()
    student = config["students"][args.student]
    manifest, rebuilt = tm.build_manifest(args.student)
    if manifest != tm.load_frozen_manifest(args.student):
        raise SystemExit(f"Error: the rebuilt {args.student} manifest differs from the frozen one")
    items = dp.verify_manifest_rows(manifest, rebuilt)
    endpoint, key, credential_source, route_ok, route_detail = muse_route(student)
    gates = evaluate_gates(args.student, manifest, registration, route_ok, route_detail)
    print(f"student={args.student} phase={tm.PHASE} items={manifest['item_count']} attempts={manifest['n']} "
          f"datasets={manifest['dataset_counts']}")
    print(f"manifest_sha256={manifest['manifest_sha256']} config_sha256={manifest['config_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    print(f"preflight=passed items={manifest['item_count']} attempts={manifest['n']} endpoint_calls=0", flush=True)
    if not args.execute:
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise SystemExit("Error: execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    card_id = str(registration["card_ids"][tm.PHASE])
    output = OUTPUT_ROOT / student["profile_id"]
    route = {"model_id": student["model_id"], "credential_source": credential_source,
             "endpoint_host": urlsplit(endpoint).hostname, "base_url_sha256": v1.sha256_bytes(endpoint.encode())}
    condition = pr.reconcile_resume(output, build_condition(args.student, config, manifest, registration, route),
                                    args.resume)
    guard = pr.BudgetGuard(student["budget_tokens"], pr.existing_usage(output))
    base.MODEL, base.PROFILE, base.PROTOCOL, base.CARD_ID = student["model_id"], student["profile_id"], tm.PROTOCOL_ID, card_id
    base.request = make_muse_request(student, card_id, guard, pr.OutageGuard(student["stop_after_timeouts"]),
                                     ModelPin(student["model_identity"]))
    record_launch(output, args.student, resume=args.resume, note=args.note)
    with OpenAI(base_url=endpoint, api_key=key, timeout=student["timeout_seconds"],
                max_retries=student["sdk_retries"]) as client:
        base.execute(output, manifest, rebuilt, items, condition, client, args.resume,
                     score_callback=score_callback(args.student, card_id), runner_path=Path(__file__),
                     work_stealing=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
