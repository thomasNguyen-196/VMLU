"""Run one student's attempts of the self-improvement loop (openspec change diagnostic-router-loop, decision 11;
card MC-104).

From the repo root:
  .venv/bin/python -m code_benchmark.run_self_loop --student qwen          # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_self_loop --student qwen --execute [--resume] [--tunnel-dns <in-tunnel DNS server>]
  .venv/bin/python -m code_benchmark.run_self_loop --student mimo --execute [--resume]

Qwen (IEC endpoint): every arm uses the campaign transport and guards (run_diagnostic_prospective, as MC-93 to MC-96)
except the multiple-choice B, which is the MC-43 probe: one chat-completions request at temperature 0 and seed 42, 4
output tokens, and the top 20 log-probabilities of the first token. Its row keeps the letter probabilities and the
confidence of the parsed letter. One gate bounds every request in flight, and a fatal row stops every lane.
MiMo (OpenCode Go): the direct route of MC-103 for every arm, one routing session per attempt.
`--execute` fails closed unless the MC-104 heading and detail card exist, the configuration and this student's
manifest carry the registered SHA-256 values, and the route is the registered one.
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

from dotenv import dotenv_values
from openai import OpenAI

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_self_loop as sl
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_router_labels as labels
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_reading_v3
    from code_benchmark.run_mc_calibration_eval import letter_probs, offered_letters
    from code_benchmark.run_mc_eval import extract_answer
    from code_benchmark.run_weakness_map import COMPLETE_FINISHES, ModelPin
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_self_loop as sl
    import run_diagnostic_prospective as pr
    import run_router_labels as labels
    import vi_multimodel as v1
    import vi_reading_v3
    from run_mc_calibration_eval import letter_probs, offered_letters
    from run_mc_eval import extract_answer
    from run_weakness_map import COMPLETE_FINISHES, ModelPin

ROOT = dp.ROOT
OUTPUT_ROOT = ROOT / "all_res" / "diagnostic_router_loop" / "self_loop"
SESSION_HEADER = "x-opencode-session"
base = pr.base
Gate = pr.Gate


def load_registration(path: Path = sl.REGISTRATION_PATH) -> dict[str, Any]:
    try:
        registration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read the self-loop registration {path}: {exc}") from exc
    for key in ("card_ids", "card_files", "frozen", "analysis"):
        if key not in registration:
            raise SystemExit(f"Error: the self-loop registration lacks {key}")
    return registration


def evaluate_gates(student: str, manifest: dict[str, Any], registration: dict[str, Any], route_ok: bool,
                   route_detail: str, *, card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    card_id = (registration.get("card_ids") or {}).get(sl.PHASE)
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    gates = [Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md")]
    card_file = (registration.get("card_files") or {}).get(sl.PHASE)
    gates.append(Gate("detail_card", bool(card_file) and (root / str(card_file)).is_file(),
                      str(card_file or "no detail card file recorded")))
    frozen = registration.get("frozen") or {}
    differing = [name for name, ok in (("config", frozen.get("config_sha256") == manifest["config_sha256"]),
                                       ("manifest", (frozen.get("manifest_sha256") or {}).get(student)
                                        == manifest["manifest_sha256"])) if not ok]
    gates.append(Gate("frozen_hashes", not differing, "all match" if not differing else f"differ: {differing}"))
    gates.append(Gate("route_identity", route_ok, route_detail))
    return gates


def qwen_route(campaign: dict[str, Any], env: dict[str, str | None]) -> tuple[bool, str]:
    """Whether .env names the campaign endpoint and model; the host is not printed."""
    endpoint, model = urlsplit(env.get("OPENAI_BASE_URL") or ""), campaign["model"]
    ok = (endpoint.hostname == model["endpoint_host"] and endpoint.path.rstrip("/") == model["endpoint_path"].rstrip("/")
          and env.get("OPENAI_MODEL") == model["requested_id"] and bool(env.get("OPENAI_API_KEY")))
    return ok, f"campaign endpoint and model {env.get('OPENAI_MODEL')} (expects {model['requested_id']})"


def mimo_route(student: dict[str, Any]) -> tuple[str, str, str, str, bool, str]:
    endpoint, key, model, credential_source = labels.resolve_route({"route": {"profile_id": student["profile_id"]}})
    ok = urlsplit(endpoint).hostname == student["endpoint_host"] and model == student["model_id"] and bool(key)
    return endpoint, key, model, credential_source, ok, f"{urlsplit(endpoint).hostname} {model}"


def _base_row(item: v1.EvalItem, card_id: str, shard: int, lane: int, api_protocol: str) -> dict[str, Any]:
    return {"run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
            "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
            "phase": sl.PHASE, "profile_id": base.PROFILE, "protocol_id": base.PROTOCOL, "measurement_card_id": card_id,
            "model_id": base.MODEL, "transport": "direct-api", "api_protocol": api_protocol, "shard": shard,
            "lane": lane, "prompt_sha256": v1.sha256_bytes(item.prompt.encode()), "raw_prompt": item.prompt,
            "raw_response": "", "started_at": base.now()}


def _blocked(row: dict[str, Any], guard: pr.BudgetGuard, outage: pr.OutageGuard, halt: threading.Event) -> bool:
    for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                (halt.is_set(), "halted_before_send")):
        if blocked:
            row.update({"status": "request_error", "finish_reason": "error", "error_type": error_type, "fatal": True,
                        "latency_s": 0.0, "finished_at": base.now()})
            return True
    return False


def _settle(row: dict[str, Any], start: float, guard: pr.BudgetGuard, outage: pr.OutageGuard) -> dict[str, Any]:
    row.update({"latency_s": round(time.monotonic() - start, 4), "finished_at": base.now()})
    if row["status"] == "complete":
        guard.add(dp.reported_tokens(row))
    elif not row.get("fatal"):
        row["retry_wait_seconds"] = 60 if row.get("http_status") == 429 else 30 if row.get("http_status") == 503 else 5
    outage.record(row)
    return row


def is_probe(item: v1.EvalItem) -> bool:
    return item.dataset_id in (sl.VMLU, sl.VM14K) and item.replicate_id == "B-r1"


def readable_letters(prompt: str) -> str:
    """The option letters of a probed prompt, or "" when its option block cannot be read; the confidence is then
    missing and the loop treats the answer as unsure."""
    try:
        return offered_letters(prompt)
    except SystemExit:  # an option broken across lines ends the MC-43 option block early
        return ""


def unreadable_probes(items: list[v1.EvalItem]) -> list[str]:
    return [item.item_id for item in items if is_probe(item) and len(readable_letters(item.prompt)) < 2]


def make_probe(probe: dict[str, Any], expected_models: set[str], card_id: str, guard: pr.BudgetGuard,
               outage: pr.OutageGuard, halt: threading.Event):
    """The MC-43 letter probe: one temperature-0 request whose first-token log-probabilities give the confidence."""
    def request(client, item, shard: int, lane: int) -> dict[str, Any]:
        row = _base_row(item, card_id, shard, lane, probe["api_protocol"])
        row.update({"temperature_sent": probe["temperature"], "seed_sent": probe["seed"], "max_tokens": probe["max_tokens"],
                    "top_logprobs_requested": probe["top_logprobs"], "probe": probe["condition_source"]})
        if _blocked(row, guard, outage, halt):
            return row
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=base.MODEL, messages=[{"role": "user", "content": item.prompt}], temperature=probe["temperature"],
                seed=probe["seed"], max_tokens=probe["max_tokens"], logprobs=True, top_logprobs=probe["top_logprobs"])
            if not response.choices:
                raise ValueError("no_choices")
            choice = response.choices[0]
            content = choice.message.content or ""
            logprobs = getattr(choice, "logprobs", None)
            first = logprobs.content[0] if logprobs is not None and logprobs.content else None
            top = [{"token": entry.token, "logprob": entry.logprob} for entry in (first.top_logprobs or [])] if first else []
            offered = readable_letters(item.prompt)
            probs, off = letter_probs(top, offered)
            answer, found = extract_answer(content), sum(1 for letter in offered if probs[letter] > 0)
            usage, finish = response.usage, str(choice.finish_reason or "unknown")
            row.update({
                "raw_response": content, "finish_reason": finish, "response_model_id": response.model,
                "request_id": response.id, "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None), "first_token": first.token if first else "",
                "top_logprobs": top, "letter_probs": {letter: round(p, 6) for letter, p in probs.items()},
                "off_options_mass": round(off, 6), "letters_found": found,
                "confidence": round(probs[answer], 6) if answer in probs and found >= 2 else None,
                "status": "complete" if finish in ("stop", "length") else "request_error"})
            if row["status"] == "complete" and response.model and response.model not in expected_models:
                row.update({"status": "request_error", "error_type": "model_identity_drift", "fatal": True})
            elif row["status"] != "complete":
                row.update({"error_type": "unexpected_finish", "fatal": False})
        except Exception as exc:  # noqa: BLE001 - never serialize SDK messages: they can echo upstream data
            status_code = getattr(exc, "status_code", None)
            row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                        "http_status": status_code, "fatal": status_code in {400, 401, 402, 403, 404}})
        return _settle(row, start, guard, outage)
    return request


def make_qwen_request(config: dict[str, Any], campaign: dict[str, Any], card_id: str, guard: pr.BudgetGuard,
                      outage: pr.OutageGuard, traces: dict[str, dict[str, Any]]):
    """The probe for the multiple-choice B, the campaign request for every other arm, behind one shared gate."""
    student = config["students"]["qwen"]
    halt = threading.Event()  # set by any fatal row; lanes queued at the gate then send nothing
    campaign_request = pr.make_request(campaign, sl.PHASE, card_id, guard, outage=outage, max_in_flight=None,
                                       retrieval_traces=traces)
    probe = make_probe(student["probe"], {campaign["model"]["self_reported_id"], campaign["model"]["requested_id"]},
                       card_id, guard, outage, halt)
    gate = threading.BoundedSemaphore(student["max_in_flight"])

    def limited(client, item, shard: int, lane: int) -> dict[str, Any]:
        with gate:  # waiting here is not part of the measured latency: each clock starts inside its request
            if halt.is_set():
                row = _base_row(item, card_id, shard, lane, "none")
                _blocked(row, guard, outage, halt)
                return row
            row = (probe if is_probe(item) else campaign_request)(client, item, shard, lane)
            if row.get("fatal"):
                halt.set()
            return row
    return limited


def session_id(run_key: str) -> str:
    """One routing session per attempt, so two draws of an item never share one."""
    return f"vmlu-mc104-{v1.sha256_bytes(run_key.encode('utf-8'))[:16]}"


def make_mimo_request(student: dict[str, Any], card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard,
                      pin: ModelPin):
    """The MC-103 request: direct chat completions, no streaming, one routing session per attempt."""
    gate = threading.BoundedSemaphore(student["max_in_flight"])
    halt = threading.Event()

    def request(client, item, shard: int, lane: int) -> dict[str, Any]:
        cap = student["max_completion_tokens"]
        row = _base_row(item, card_id, shard, lane, student["api_protocol"])
        row.update({"temperature_sent": None, "reasoning_effort_sent": None, "seed_sent": None, "max_tokens": cap})
        if _blocked(row, guard, outage, halt):
            halt.set()
            return row
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=base.MODEL, messages=[{"role": "system", "content": student["system_prompt"]},
                                            {"role": "user", "content": item.prompt}],
                max_completion_tokens=cap, stream=False, extra_headers={SESSION_HEADER: session_id(item.run_key)})
            if not response.choices:
                raise ValueError("no_choices")
            choice, usage = response.choices[0], response.usage
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
                "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else None, "tool_call_n": len(tools),
                "status": "complete" if finish in COMPLETE_FINISHES and not tools else "request_error"})
            drift = pin.check(response.model) if row["status"] == "complete" else None
            if drift:
                row.update({"status": "request_error", "error_type": drift, "fatal": True})
            elif row["status"] != "complete":
                row.update({"error_type": "unexpected_finish_or_tool_call", "fatal": bool(tools)})
        except Exception as exc:  # noqa: BLE001 - never serialize SDK messages: they can echo upstream data
            status_code = getattr(exc, "status_code", None)
            row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                        "http_status": status_code, "fatal": status_code in {400, 401, 402, 403, 404}})
        _settle(row, start, guard, outage)
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
        "protocol_id": sl.PROTOCOL_ID, "protocol_version": 1, "phase": sl.PHASE, "student": student,
        "measurement_card_id": registration["card_ids"][sl.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][sl.PHASE]),
        "config_sha256": manifest["config_sha256"], "manifest_sha256": manifest["manifest_sha256"],
        **{key: manifest[key] for key in ("campaign_protocol_sha256", "prompt_templates_sha256", "k2_protocol_sha256",
                                         "retrieval_config_sha256", "corpus_sha256", "excluded_manifest_sha256",
                                         "source_sha256", "dataset_counts", "arm_counts")},
        "loop": config["loop"], "student_config": config["students"][student], **route,
        "scorer_sha256": v1.sha256_file(ROOT / "code_benchmark" / "score_vi_multimodel.py"),
        "reading_v3_sha256": v1.sha256_file(Path(vi_reading_v3.__file__)),
        "module_sha256": v1.sha256_file(Path(sl.__file__)),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)),
        "engine_sha256": v1.sha256_file(Path(pr.__file__)),
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
            probe = rows.get(dp.run_key(row)) or {}
            if "letter_probs" in probe:
                row = {**row, "confidence": probe.get("confidence"), "letter_probs": probe.get("letter_probs")}
            final.append(row)
        for by_dataset in summaries.values():
            for summary in by_dataset.values():
                if summary["status"] != "complete":  # withhold headline metrics on partial data
                    for key in pr.HEADLINE_KEYS:
                        summary.pop(key, None)
        v1.write_jsonl_atomic(output / "scores.jsonl", final)
        base.atomic_json(output / "summary.json", {
            "protocol_id": sl.PROTOCOL_ID, "phase": sl.PHASE, "student": student, "measurement_card_id": card_id,
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
    event = {"at": base.now(), "phase": sl.PHASE, "student": student, "resume": resume,
             "runner_sha256": v1.sha256_file(Path(__file__)), "note": note}
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(event, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--student", choices=sl.STUDENTS, required=True)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="resume only unfinished technical requests")
    ap.add_argument("--tunnel-dns", default=None, help="in-tunnel DNS server for the Qwen endpoint host (this process only)")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    if args.tunnel_dns and args.student != "qwen":
        ap.error("--tunnel-dns applies to the Qwen endpoint only")
    config, _ = sl.load_config()
    registration = load_registration()
    student = config["students"][args.student]
    manifest, rebuilt = sl.build_manifest(args.student)
    if manifest != sl.load_frozen_manifest(args.student):
        raise SystemExit(f"Error: the rebuilt {args.student} manifest differs from the frozen one")
    items = dp.verify_manifest_rows(manifest, rebuilt)
    campaign = dp.load_protocol()
    env = dotenv_values(ROOT / ".env")
    endpoint = key = model = credential_source = ""
    if args.student == "qwen":
        route_ok, route_detail = qwen_route(campaign, env)
    else:
        endpoint, key, model, credential_source, route_ok, route_detail = mimo_route(student)
    gates = evaluate_gates(args.student, manifest, registration, route_ok, route_detail)
    if args.student == "qwen":
        unreadable = unreadable_probes(items)
        print(f"probed prompts whose option letters cannot be read (confidence missing, so unsure): "
              f"{len(unreadable)} {unreadable}")
    print(f"student={args.student} phase={sl.PHASE} items={manifest['item_count']} attempts={manifest['n']} "
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
    card_id = str(registration["card_ids"][sl.PHASE])
    if args.student == "qwen":
        endpoint, key = str(env["OPENAI_BASE_URL"]), str(env["OPENAI_API_KEY"])
        if args.tunnel_dns:
            address = pr.install_resolver_shim(urlsplit(endpoint).hostname or "", args.tunnel_dns)
            print(f"resolver shim (this process only) -> {address} via {args.tunnel_dns}")
        transport, model = campaign["transport"], campaign["model"]
        output = OUTPUT_ROOT / model["profile_id"]
        route = {"model_id": model["requested_id"], "self_reported_model_id": model["self_reported_id"],
                 "profile_id": model["profile_id"], "provider": model["provider"], "endpoint_host": urlsplit(endpoint).hostname,
                 "base_url_sha256": v1.sha256_bytes(endpoint.encode()), "transport": transport}
        condition = pr.reconcile_resume(output, build_condition(args.student, config, manifest, registration, route),
                                        args.resume)
        guard = pr.BudgetGuard(campaign["budget"]["campaign_cap_tokens"], pr.existing_usage(output))
        if (base.SHARDS, base.LANES) != (transport["shards"], transport["lanes"]):
            raise SystemExit("Error: engine shard/lane constants differ from the campaign protocol")
        base.MODEL, base.PROFILE, base.PROTOCOL, base.CARD_ID = model["requested_id"], model["profile_id"], sl.PROTOCOL_ID, card_id
        base.request = make_qwen_request(config, campaign, card_id, guard, pr.OutageGuard(student["stop_after_timeouts"]),
                                         sl.request_traces(manifest, rebuilt))
        record_launch(output, args.student, resume=args.resume, note=args.note)
        with OpenAI(base_url=endpoint, api_key=key, timeout=transport["timeout_seconds"],
                    max_retries=transport["sdk_retries"], default_headers=transport["gateway_header"]) as client:
            base.execute(output, manifest, rebuilt, items, condition, client, args.resume,
                         score_callback=score_callback(args.student, card_id), runner_path=Path(__file__))
        return 0
    output = OUTPUT_ROOT / student["profile_id"]
    route = {"model_id": model, "credential_source": credential_source, "endpoint_host": urlsplit(endpoint).hostname,
             "base_url_sha256": v1.sha256_bytes(endpoint.encode())}
    condition = pr.reconcile_resume(output, build_condition(args.student, config, manifest, registration, route),
                                    args.resume)
    guard = pr.BudgetGuard(student["budget_tokens"], pr.existing_usage(output))
    base.MODEL, base.PROFILE, base.PROTOCOL, base.CARD_ID = model, student["profile_id"], sl.PROTOCOL_ID, card_id
    base.request = make_mimo_request(student, card_id, guard, pr.OutageGuard(student["stop_after_timeouts"]),
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
