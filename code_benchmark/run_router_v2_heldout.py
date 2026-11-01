"""Run the router v2 held-out phase (openspec change: diagnostic-router-v2; card MC-94).

From the repo root:
  .venv/bin/python -m code_benchmark.run_router_v2_heldout                    # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_router_v2_heldout --execute [--resume] [--tunnel-dns 172.16.30.1]

The 600 held-out items (data/diagnostic_router_v2/heldout_v1.json) run with arms B and S, two draws each, on the
engine, guards and scoring of the prospective campaign (run_diagnostic_prospective, MC-93). `--execute` fails
closed unless the MC-94 heading and detail card exist, the held-out protocol, campaign protocol, templates and
manifest carry the registered SHA-256 values, the endpoint is the campaign's, and router_v2.json carries the
registered SHA-256. The registered limits (4 in flight, breaker after 4 network failures) apply by default and
other values are refused.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import dotenv_values
from openai import OpenAI

try:
    from code_benchmark import diagnostic_heldout as dh
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_router as router
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_heldout as dh
    import diagnostic_prospective as dp
    import diagnostic_router as router
    import run_diagnostic_prospective as pr
    import vi_multimodel as v1

ROOT = dp.ROOT
OUTPUT_ROOT = ROOT / "all_res" / "diagnostic_router_v2" / dh.PHASE
Gate = pr.Gate


def load_registration(path: Path = dh.REGISTRATION_PATH) -> dict[str, Any]:
    try:
        registration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read the held-out registration {path}: {exc}") from exc
    for key in ("card_ids", "card_files", "frozen", "router", "heldout"):
        if key not in registration:
            raise SystemExit(f"Error: the held-out registration lacks {key}")
    return registration


def evaluate_gates(campaign: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                   env: dict[str, str | None], *, card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    card_id = (registration.get("card_ids") or {}).get(dh.PHASE)
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    gates = [Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md")]
    card_file = (registration.get("card_files") or {}).get(dh.PHASE)
    gates.append(Gate("detail_card", bool(card_file) and (root / str(card_file)).is_file(),
                      str(card_file or "no detail card file recorded")))
    frozen = registration.get("frozen") or {}
    differing = [name for name in ("heldout_protocol_sha256", "campaign_protocol_sha256", "prompt_templates_sha256",
                                   "manifest_sha256") if frozen.get(name) != manifest.get(name)]
    gates.append(Gate("frozen_hashes", not differing, "all match" if not differing else f"differ: {differing}"))
    endpoint, model = urlsplit(env.get("OPENAI_BASE_URL") or ""), campaign["model"]
    identity = (endpoint.hostname == model["endpoint_host"]
                and endpoint.path.rstrip("/") == model["endpoint_path"].rstrip("/")
                and env.get("OPENAI_MODEL") == model["requested_id"] and bool(env.get("OPENAI_API_KEY")))
    gates.append(Gate("endpoint_identity", identity, f"model={env.get('OPENAI_MODEL')} (campaign expects "
                                                     f"{model['requested_id']})"))
    gates.append(rule_gate(campaign, registration, root))
    return gates


def rule_gate(campaign: dict[str, Any], registration: dict[str, Any], root: Path = ROOT) -> Gate:
    entry = registration.get("router") or {}
    try:
        rule, digest = router.load_rule(root / dh.RULE_PATH.relative_to(ROOT), campaign["datasets"])
    except SystemExit as exc:
        return Gate("router_rule", False, str(exc))
    if "probe" not in rule:
        return Gate("router_rule", False, f"{rule['router_id']} declares no probe")
    ok = entry.get("rule_sha256") == digest
    return Gate("router_rule", ok, f"{rule['router_id']} as registered" if ok else "rule differs from the registered sha256")


def build_condition(campaign: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    endpoint: str, templates_version: str) -> dict[str, Any]:
    transport, model = campaign["transport"], campaign["model"]
    return {
        "protocol_id": dh.PROTOCOL_ID, "protocol_version": 1, "phase": dh.PHASE,
        "measurement_card_id": registration["card_ids"][dh.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][dh.PHASE]),
        "manifest_sha256": manifest["manifest_sha256"], "heldout_protocol_sha256": manifest["heldout_protocol_sha256"],
        "campaign_protocol_sha256": manifest["campaign_protocol_sha256"],
        "prompt_templates_sha256": manifest["prompt_templates_sha256"], "prompt_version": templates_version,
        "router_rule_sha256": registration["router"]["rule_sha256"], "operational": registration["heldout"]["operational"],
        "dataset_counts": manifest["dataset_counts"], "arm_counts": manifest["arm_counts"],
        "model_id": model["requested_id"], "self_reported_model_id": model["self_reported_id"],
        "profile_id": model["profile_id"], "provider": model["provider"], "transport": "direct-api",
        "api_protocol": transport["api_protocol"], "endpoint_host": urlsplit(endpoint).hostname,
        "base_url_sha256": v1.sha256_bytes(endpoint.encode()), "temperature_requested": transport["temperature"],
        "temperature_effective": None, "reasoning_effort_sent": None, "seed_sent": None, "tools": "none",
        "system_prompt": transport["system_prompt"], "max_tokens": transport["max_output_tokens"],
        "campaign_cap_tokens": campaign["budget"]["campaign_cap_tokens"],
        "request_timeout_seconds": transport["timeout_seconds"], "sdk_retries": transport["sdk_retries"],
        "workers": transport["shards"] * transport["lanes"],
        "final_segment_rule_id": campaign["scoring"]["final_segment_rule_id"],
        "scorer_sha256": v1.sha256_file(ROOT / "code_benchmark" / "score_vi_multimodel.py"),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)),
        "engine_sha256": v1.sha256_file(Path(pr.__file__)),
        "runner_sha256": v1.sha256_file(Path(__file__)),
    }


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
        pr.base.atomic_json(output / "summary.json", {
            "protocol_id": dh.PROTOCOL_ID, "phase": dh.PHASE, "measurement_card_id": card_id,
            "model_id": pr.base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": pr.base.now(),
            "expected_n": len(manifest["items"]),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "cost_usd": None, "cost_basis": "IEC tariff not supplied; reported usage retained per attempt",
        })
    return score


def record_launch(output: Path, *, resume: bool, max_in_flight: int | None, stop_after_timeouts: int | None,
                  note: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    event = {"at": pr.base.now(), "phase": dh.PHASE, "resume": resume, "runner_sha256": v1.sha256_file(Path(__file__)),
             "max_in_flight": max_in_flight, "stop_after_timeouts": stop_after_timeouts, "note": note}
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(event, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="resume only unfinished technical requests")
    ap.add_argument("--tunnel-dns", default=None, help="in-tunnel DNS server for the endpoint host (this process only)")
    ap.add_argument("--max-in-flight", type=int, default=None, metavar="N")
    ap.add_argument("--stop-after-timeouts", type=int, default=None, metavar="N")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    campaign, registration = dp.load_protocol(), load_registration()
    operational = registration["heldout"].get("operational") or {}
    for flag in ("max_in_flight", "stop_after_timeouts"):  # the registered limits apply; others are refused
        value = getattr(args, flag)
        if value is not None and operational.get(flag) not in (None, value):
            ap.error(f"--{flag.replace('_', '-')} {value} differs from the {operational[flag]} registered for MC-94")
        if value is None:
            setattr(args, flag, operational.get(flag))
    manifest, rebuilt = dh.build_manifest()
    if manifest != dh.load_frozen_manifest():
        raise SystemExit("Error: the rebuilt held-out manifest differs from the frozen heldout_v1.json")
    items = dp.verify_manifest_rows(manifest, rebuilt)
    env = dotenv_values(ROOT / ".env")
    gates = evaluate_gates(campaign, manifest, registration, env)
    print(f"phase={dh.PHASE} protocol={dh.PROTOCOL_ID} items={manifest['item_count']} attempts={manifest['n']} "
          f"datasets={manifest['dataset_counts']} arms={manifest['arm_counts']}")
    print(f"manifest_sha256={manifest['manifest_sha256']}")
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
    endpoint, key = str(env["OPENAI_BASE_URL"]), str(env["OPENAI_API_KEY"])
    if args.tunnel_dns:
        address = pr.install_resolver_shim(urlsplit(endpoint).hostname or "", args.tunnel_dns)
        print(f"resolver shim (this process only): {urlsplit(endpoint).hostname} -> {address} via {args.tunnel_dns}")
    card_id = str(registration["card_ids"][dh.PHASE])
    output = OUTPUT_ROOT / campaign["model"]["profile_id"]
    output.parent.mkdir(parents=True, exist_ok=True)
    condition = pr.reconcile_resume(output, build_condition(campaign, manifest, registration, endpoint,
                                                            dp.load_templates()["version"]), args.resume)
    guard = pr.BudgetGuard(campaign["budget"]["campaign_cap_tokens"], pr.existing_usage(output))
    pr.configure_engine(campaign, dh.PHASE, card_id, guard, outage=pr.OutageGuard(args.stop_after_timeouts or 0),
                        max_in_flight=args.max_in_flight)
    pr.base.PROTOCOL = dh.PROTOCOL_ID  # rows carry the held-out protocol id
    record_launch(output, resume=args.resume, max_in_flight=args.max_in_flight,
                  stop_after_timeouts=args.stop_after_timeouts, note=args.note)
    print(f"operational limits: max_in_flight={args.max_in_flight} stop_after_timeouts={args.stop_after_timeouts}",
          flush=True)
    transport = campaign["transport"]
    with OpenAI(base_url=endpoint, api_key=key, timeout=transport["timeout_seconds"],
                max_retries=transport["sdk_retries"], default_headers=transport["gateway_header"]) as client:
        pr.base.execute(output, manifest, rebuilt, items, condition, client, args.resume,
                        score_callback=score_callback(card_id), runner_path=Path(__file__))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
