"""Run the Legal MC "chọn rồi trả lời" test (openspec change: diagnostic-legal-select; card MC-111).

From the repo root:
  .venv/bin/python -m code_benchmark.run_legal_select                    # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_legal_select --execute [--resume] [--tunnel-dns <in-tunnel DNS server>]

Round 1 (data/diagnostic_legal_select/manifest_round1_v1.json) runs B, K, K10, PICK and O, two draws each, on the
engine, guards and route of MC-101. Round 2 (SEL) starts in the same launch only when every round-1 attempt is
complete: its manifest is built from the round-1 rows by the registered rule, written beside the run on first build
and rebuilt and compared on every later launch. `--execute` fails closed unless the MC-111 heading and detail card
exist, every frozen input carries its registered SHA-256 and the endpoint is the campaign's. The registered limits
(4 in flight, breaker after 4 network failures, 8,000,000 tokens) apply by default and other values are refused.
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
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_legal_retrieval as lr
    from code_benchmark import diagnostic_legal_select as ls
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_retrieval as dr
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_oracle as lo
    import diagnostic_legal_retrieval as lr
    import diagnostic_legal_select as ls
    import diagnostic_prospective as dp
    import diagnostic_retrieval as dr
    import run_diagnostic_prospective as pr
    import vi_multimodel as v1

ROOT = dp.ROOT
OUTPUT_ROOT = ls.WORK_ROOT / "run"
FROZEN_KEYS = (*ls.HASH_KEYS, "manifest_sha256")
ROUND2_MANIFEST = "manifest_round2.json"
Gate = pr.Gate


def load_registration(path: Path = ls.REGISTRATION_PATH) -> dict[str, Any]:
    try:
        registration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read the legal-select registration {path}: {exc}") from exc
    for key in ("card_ids", "card_files", "frozen"):
        if key not in registration:
            raise SystemExit(f"Error: the legal-select registration lacks {key}")
    return registration


def evaluate_gates(campaign: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                   env: dict[str, str | None], *, card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    card_id = (registration.get("card_ids") or {}).get(ls.PHASE)
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    gates = [Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md")]
    card_file = (registration.get("card_files") or {}).get(ls.PHASE)
    gates.append(Gate("detail_card", bool(card_file) and (root / str(card_file)).is_file(),
                      str(card_file or "no detail card file recorded")))
    frozen = registration.get("frozen") or {}
    differing = [name for name in FROZEN_KEYS if frozen.get(name) != manifest.get(name)]
    gates.append(Gate("frozen_hashes", not differing, "all match" if not differing else f"differ: {differing}"))
    endpoint, model = urlsplit(env.get("OPENAI_BASE_URL") or ""), campaign["model"]
    identity = (endpoint.hostname == model["endpoint_host"]
                and endpoint.path.rstrip("/") == model["endpoint_path"].rstrip("/")
                and env.get("OPENAI_MODEL") == model["requested_id"] and bool(env.get("OPENAI_API_KEY")))
    gates.append(Gate("endpoint_identity", identity, f"model={env.get('OPENAI_MODEL')} (campaign expects "
                                                     f"{model['requested_id']})"))
    return gates


def build_condition(campaign: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    endpoint: str, operational: dict[str, Any], round_number: int) -> dict[str, Any]:
    """The frozen inference condition of one round. Round 2 adds its own manifest hash and round 1's."""
    transport, model = campaign["transport"], campaign["model"]
    extra = ({"round1_manifest_sha256": manifest["round1_manifest_sha256"]} if round_number == 2 else {})
    return {
        "protocol_id": ls.PROTOCOL_ID, "protocol_version": 1, "phase": ls.PHASE, "round": round_number, **extra,
        "measurement_card_id": registration["card_ids"][ls.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][ls.PHASE]),
        **{name: manifest[name] for name in FROZEN_KEYS},
        "prompt_version": dp.load_templates()["version"], "select_prompt_version": ls.load_template()["version"],
        "operational": operational,
        "dataset_counts": manifest["dataset_counts"], "arm_counts": manifest["arm_counts"],
        "model_id": model["requested_id"], "self_reported_model_id": model["self_reported_id"],
        "profile_id": model["profile_id"], "provider": model["provider"], "transport": "direct-api",
        "api_protocol": transport["api_protocol"], "endpoint_host": urlsplit(endpoint).hostname,
        "base_url_sha256": v1.sha256_bytes(endpoint.encode()), "temperature_requested": transport["temperature"],
        "temperature_effective": None, "reasoning_effort_sent": None, "seed_sent": None, "tools": "none",
        "system_prompt": transport["system_prompt"], "max_tokens": transport["max_output_tokens"],
        "budget_tokens": operational["budget_tokens"],
        "request_timeout_seconds": transport["timeout_seconds"], "sdk_retries": transport["sdk_retries"],
        "workers": transport["shards"] * transport["lanes"],
        "scorer_sha256": v1.sha256_file(ROOT / "code_benchmark" / "score_vi_multimodel.py"),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)),
        "engine_sha256": v1.sha256_file(Path(pr.__file__)),
        "legal_select_module_sha256": v1.sha256_file(Path(ls.__file__)),
        "legal_retrieval_module_sha256": v1.sha256_file(Path(lr.__file__)),
        "legal_oracle_module_sha256": v1.sha256_file(Path(lo.__file__)),
        "retrieval_module_sha256": v1.sha256_file(Path(dr.__file__)),
        "runner_sha256": v1.sha256_file(Path(__file__)),
    }


def score_callback(card_id: str, round_number: int):
    """Frozen MC scoring of every answer arm; PICK rows are parsed into selections (picks.jsonl), never scored."""
    def score(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        answers = [ref for ref in manifest["items"] if dp.arm_of_replicate(ref["replicate_id"]) != "PICK"]
        scored, summaries = dp.score_arm_rows({**manifest, "items": answers}, rows, rebuilt)
        for by_dataset in summaries.values():
            for summary in by_dataset.values():
                if summary["status"] != "complete":  # withhold headline metrics on partial data
                    for key in pr.HEADLINE_KEYS:
                        summary.pop(key, None)
        v1.write_jsonl_atomic(output / "scores.jsonl", scored)
        picks = []
        for ref in manifest["items"]:
            key = dp.run_key(ref)
            if dp.arm_of_replicate(ref["replicate_id"]) == "PICK" and rows.get(key, {}).get("status") == "complete":
                row = rows[key]
                picks.append({"run_key": key, "item_id": ref["item_id"], "replicate_id": ref["replicate_id"],
                              **ls.parse_pick(str(row.get("raw_response") or "")),
                              "prompt_tokens": row.get("prompt_tokens"), "completion_tokens": row.get("completion_tokens"),
                              "total_tokens": row.get("total_tokens")})
        if picks:
            v1.write_jsonl_atomic(output / "picks.jsonl", picks)
        pr.base.atomic_json(output / "summary.json", {
            "protocol_id": ls.PROTOCOL_ID, "phase": ls.PHASE, "round": round_number, "measurement_card_id": card_id,
            "model_id": pr.base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": pr.base.now(),
            "expected_n": len(manifest["items"]),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "selection_counts": {status: sum(p["status"] == status for p in picks) for status in ls.SELECTION_STATUSES},
            "cost_usd": None, "cost_basis": "IEC tariff not supplied; reported usage retained per attempt",
        })
    return score


def record_launch(output: Path, *, resume: bool, max_in_flight: int | None, stop_after_timeouts: int | None,
                  note: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    event = {"at": pr.base.now(), "phase": ls.PHASE, "resume": resume, "runner_sha256": v1.sha256_file(Path(__file__)),
             "max_in_flight": max_in_flight, "stop_after_timeouts": stop_after_timeouts, "note": note}
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(event, ensure_ascii=False) + "\n")


def round1_complete(output: Path, manifest: dict[str, Any]) -> tuple[bool, dict[str, dict[str, Any]]]:
    """(every round-1 attempt complete, latest row per run key) from the round-1 ledger. A row whose key or prompt
    is not the manifest's fails closed, as the engine's own loader does."""
    path = output / "attempts.jsonl"
    if not path.is_file():
        return False, {}
    expected = {dp.run_key(ref): ref["prompt_sha256"] for ref in manifest["items"]}
    rows: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if expected.get(row.get("run_key")) != row.get("prompt_sha256"):
            raise SystemExit(f"Error: round-1 ledger row {row.get('run_key')} is not in the frozen manifest")
        rows[row["run_key"]] = row
    return all(rows.get(key, {}).get("status") == "complete" for key in expected), rows


def round2_manifest(output: Path, round1: dict[str, Any], rows: dict[str, dict[str, Any]],
                    inputs: ls.Inputs | None = None) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """Build round 2 from the round-1 rows; write it on first build, otherwise refuse any difference."""
    built, rebuilt = ls.build_round2(round1, rows, inputs)
    path = output / ROUND2_MANIFEST
    if path.is_file():
        if json.loads(path.read_text(encoding="utf-8")) != built:
            raise SystemExit(f"Error: the rebuilt round-2 manifest differs from {path}")
    else:
        output.mkdir(parents=True, exist_ok=True)
        pr.base.atomic_json(path, built)
    return built, rebuilt


def run_round(campaign: dict[str, Any], manifest: dict[str, Any], rebuilt: dict[str, v1.EvalItem],
              registration: dict[str, Any], endpoint: str, key: str, operational: dict[str, Any], output: Path,
              round_number: int, args: argparse.Namespace) -> str:
    card_id = str(registration["card_ids"][ls.PHASE])
    items = dp.verify_manifest_rows(manifest, rebuilt)
    resume = bool(args.resume) and (output / "condition.json").is_file()  # a round's first launch starts fresh
    condition = pr.reconcile_resume(output, build_condition(campaign, manifest, registration, endpoint,
                                                            operational, round_number), resume)
    guard = pr.BudgetGuard(operational["budget_tokens"], pr.existing_usage(output.parent / "round1")
                           + (pr.existing_usage(output) if round_number == 2 else 0))
    traces = lr.retrieval_traces({"pool": manifest["pool"]}) if round_number == 1 else {}
    pr.configure_engine(campaign, ls.PHASE, card_id, guard, outage=pr.OutageGuard(args.stop_after_timeouts or 0),
                        max_in_flight=args.max_in_flight, retrieval_traces=traces)
    pr.base.PROTOCOL = ls.PROTOCOL_ID  # rows carry the legal-select protocol id
    record_launch(output, resume=resume, max_in_flight=args.max_in_flight,
                  stop_after_timeouts=args.stop_after_timeouts, note=f"round {round_number}; {args.note}")
    transport = campaign["transport"]
    with OpenAI(base_url=endpoint, api_key=key, timeout=transport["timeout_seconds"],
                max_retries=transport["sdk_retries"], default_headers=transport["gateway_header"]) as client:
        pr.base.execute(output, manifest, rebuilt, items, condition, client, resume,
                        score_callback=score_callback(card_id, round_number), runner_path=Path(__file__))
    return json.loads((output / "run.json").read_text(encoding="utf-8"))["status"]


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
    campaign, protocol, registration = dp.load_protocol(), ls.load_protocol(), load_registration()
    card = registration["card_ids"].get(ls.PHASE, "the card")
    operational = protocol.get("operational") or {}
    for flag in ("max_in_flight", "stop_after_timeouts"):  # the registered limits apply; others are refused
        value = getattr(args, flag)
        if value is not None and operational.get(flag) not in (None, value):
            ap.error(f"--{flag.replace('_', '-')} {value} differs from the {operational[flag]} registered for {card}")
        if value is None:
            setattr(args, flag, operational.get(flag))
    inputs = ls.load_inputs()
    manifest, rebuilt = ls.build_round1(inputs)
    if manifest != ls.load_frozen_round1():
        raise SystemExit("Error: the rebuilt round-1 manifest differs from the frozen manifest_round1_v1.json")
    dp.verify_manifest_rows(manifest, rebuilt)
    env = dotenv_values(ROOT / ".env")
    gates = evaluate_gates(campaign, manifest, registration, env)
    print(f"phase={ls.PHASE} protocol={ls.PROTOCOL_ID} items={manifest['item_count']} round1_attempts={manifest['n']} "
          f"arms={manifest['arm_counts']} round2_attempts={manifest['item_count'] * protocol['draws']} (SEL)")
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
    base_dir = OUTPUT_ROOT / campaign["model"]["profile_id"]
    round1_dir, round2_dir = base_dir / "round1", base_dir / "round2"
    print(f"operational limits: max_in_flight={args.max_in_flight} stop_after_timeouts={args.stop_after_timeouts} "
          f"budget_tokens={operational['budget_tokens']}", flush=True)
    done, rows = round1_complete(round1_dir, manifest)
    if not done:
        status = run_round(campaign, manifest, rebuilt, registration, endpoint, key, operational, round1_dir, 1, args)
        done, rows = round1_complete(round1_dir, manifest)
        if not done:
            print(f"round 1 status={status}; round 2 waits until every round-1 attempt is complete (rerun with "
                  f"--execute --resume)", flush=True)
            return 0
    second, rebuilt2 = round2_manifest(round2_dir, manifest, rows, inputs)
    print(f"round 2: {second['n']} SEL attempts, manifest {second['manifest_sha256']}, "
          f"selections {second['selection_counts']}", flush=True)
    status = run_round(campaign, second, rebuilt2, registration, endpoint, key, operational, round2_dir, 2, args)
    print(f"round 2 status={status}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
