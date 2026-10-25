"""Run Muse Spark 1.2 via 9ROUTER with frozen OMP prompts and scorers.

Derive a new model condition without changing the historical v1/v2 rosters.
Run from root: .venv/bin/python -m code_benchmark.run_muse_router_matched --execute
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
import sys
import threading
from collections import Counter
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    from code_benchmark import run_vi_multimodel_eval as v1_runner
    from code_benchmark import run_vi_multimodel_expansion as v2_runner
    from code_benchmark import score_vi_multimodel as v1_scorer
    from code_benchmark import score_vi_multimodel_expansion as v2_scorer
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_multimodel_expansion as v2
except ImportError:
    import run_vi_multimodel_eval as v1_runner
    import run_vi_multimodel_expansion as v2_runner
    import score_vi_multimodel as v1_scorer
    import score_vi_multimodel_expansion as v2_scorer
    import vi_multimodel as v1
    import vi_multimodel_expansion as v2

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "muse-spark-1-2-contributor"
OUTPUT_ROOT = ROOT / "all_res/muse_router_matched"
CARDS = {"main": "MC-73", "vmlu": "MC-74", "vbench": "MC-75"}
OMP_CAP_LABEL = "maxTokens in OMP model config"
MAIN_COUNTS = {
    "vi-multimodel-v1-legal-mc-146": 146,
    "vi-multimodel-v1-legal-nli-150": 150,
    "vi-multimodel-v1-vi-squad-200": 200,
    "vi-multimodel-v1-vi-drop-200": 200,
    "vi-multimodel-v1-bidlqa-test": 603,
}
BASE_WRITE_AGENT_CONFIG = v1_runner._write_agent_config
BASE_RUN_OMP_REQUEST = v1_runner._run_omp_request


@contextmanager
def sampling_relay():
    """Pin temperature at the wire boundary while preserving OMP auto reasoning.

    OMP can omit sampling settings on its initial auto reasoning request. No
    prompt, output cap, reasoning field or response is changed by this relay.
    """
    endpoint, api_key, _, _ = v1_runner._resolve_model(router_profile())

    class Relay(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if "seed" in payload or payload.get("tools"):
                self.send_error(400, "Seed/tools violate registered condition")
                return
            payload["temperature"] = 1.0
            request = Request(
                endpoint + self.path,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
            )
            try:
                with urlopen(request, timeout=300) as response:  # nosec B310 # endpoint validated as http(s)
                    content_type = response.headers.get("Content-Type", "application/json")
                    self.send_response(response.status)
                    self.send_header("Content-Type", content_type)
                    self.end_headers()
                    while chunk := response.read1(65536):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    return
            except HTTPError as exc:
                body, status, content_type = exc.read(), exc.code, "application/json"
            except (BrokenPipeError, ConnectionResetError):
                return  # OMP may close a stream during its auto reasoning fallback.
            except OSError:
                self.send_error(502, "Router transport failed")
                return
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Relay)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request_through_relay(**kwargs):
        kwargs["endpoint"] = f"http://127.0.0.1:{server.server_port}"
        return BASE_RUN_OMP_REQUEST(**kwargs)

    try:
        with patch.object(v1_runner, "_run_omp_request", request_through_relay), patch.object(v2_runner, "_run_omp_request", request_through_relay):
            yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def write_router_agent_config(agent_dir: Path, **kwargs) -> None:
    """Set OMP's sampling setting; model options alone do not send temperature."""
    BASE_WRITE_AGENT_CONFIG(agent_dir, **kwargs)
    path = agent_dir / "config.yml"
    config = json.loads(path.read_text())
    config["temperature"] = 1.0
    path.write_text(json.dumps(config) + "\n")


def router_profile() -> dict:
    return {
        "profile_id": PROFILE_ID,
        "display_name": "Muse Spark 1.2 Contributor",
        "provider": "9ROUTER / CMC",
        "provider_tier": "configured local router",
        "billing_mode": "router-no-declared-tariff",
        "model_id": "cmc/meta/muse-spark-1.2-contributor",
        "model_ref": "router9/cmc/meta/muse-spark-1.2-contributor",
        "omp_provider": "router9",
        "api_protocol": "openai-completions",
        "base_url": "",
        "base_url_env": "9ROUTER_BASE_URL",
        "api_key_env": "9ROUTER_API_KEY",
        "omp_options": {"temperature": 1.0},
        "temperature": 1.0,
        "temperature_effective": 1.0,
        "temperature_policy": "explicit requested 1.0; upstream effective value not exposed",
        "omp_reasoning": True,
        "omp_thinking": "auto",
        "send_seed": False,
        "seed_policy": "omitted",
        "token_limit_parameter": OMP_CAP_LABEL,
        "input_price_usd_per_million": 0.0,
        "output_price_usd_per_million": 0.0,
        "cached_input_price_usd_per_million": 0.0,
        "cost_basis": "no router tariff supplied; zero equivalent is not a cost estimate",
        "measurement_card_ids": {"main": CARDS["main"]},
        "measurement_card_ids_v2": {phase: CARDS[phase] for phase in ("vmlu", "vbench")},
    }


def inputs_for(phase: str) -> tuple[dict, dict, dict]:
    contract = v1 if phase == "main" else v2
    # Validate original frozen sources and rosters before deriving a new identity.
    parent = contract.load_manifest(phase)
    protocol = copy.deepcopy(v1.load_protocol() if phase == "main" else v2._protocol())
    profiles = {PROFILE_ID: router_profile()}
    manifest = copy.deepcopy(parent)
    if phase == "main":
        manifest["items"] = [row for row in parent["items"] if row["dataset_id"] in MAIN_COUNTS]
        counts = dict(Counter(row["dataset_id"] for row in manifest["items"]))
        if counts != MAIN_COUNTS:
            raise SystemExit(f"Error: derived main coverage changed: {counts}")
        protocol["main"]["measurement_card_ids"] = {PROFILE_ID: CARDS[phase]}
        manifest["protocol_sha256"] = v1.protocol_phase_hash(protocol, phase)
    else:
        settings = protocol["phases"][phase]
        settings["measurement_card_ids"] = {PROFILE_ID: CARDS[phase]}
        settings["budget_guard_usd_equivalent"] = {PROFILE_ID: 1.0}
        protocol["probe_max_tokens"] = 256
        manifest["protocol_sha256"] = v1.sha256_bytes(v1.canonical_json(settings))
        manifest["profile_file_sha256"] = v1.sha256_bytes(v1.canonical_json(profiles))
    manifest["n"] = len(manifest["items"])
    manifest["item_count"] = manifest["n"]
    manifest["dataset_counts"] = dict(Counter(row["dataset_id"] for row in manifest["items"]))
    manifest["parent_manifest_sha256"] = parent["manifest_sha256"]
    manifest["condition_id"] = CARDS[phase]
    manifest["profile_roster_sha256"] = v1.sha256_bytes(v1.canonical_json(profiles))
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    rebuilt = contract.rebuild_items(phase)
    for row in manifest["items"]:
        contract.item_from_manifest_row(row, rebuilt)
    return profiles, protocol, manifest


def invoke(module, phase: str, argv: list[str], inputs: tuple[dict, dict, dict]) -> None:
    profiles, protocol, manifest = inputs
    patches = {
        "OUTPUT_DIR": OUTPUT_ROOT,
        "load_model_profiles" if phase == "main" else "load_profiles": lambda: profiles,
        "load_manifest": lambda selected: manifest if selected == phase else None,
    }
    if phase == "main":
        patches["load_protocol"] = lambda: protocol
        if module is v1_runner:
            patches["_PROBE_MAX_TOKENS"] = 256
    elif module is v2_runner:
        patches["_read_protocol"] = lambda: protocol
    with ExitStack() as stack:
        if module in (v1_runner, v2_runner):
            stack.enter_context(patch.object(v1_runner, "_write_agent_config", write_router_agent_config))
        for name, value in patches.items():
            stack.enter_context(patch.object(module, name, value))
        stack.enter_context(patch.object(sys, "argv", [__file__, *argv]))
        try:
            module.main()
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise


def freeze_inputs(phase: str, inputs: tuple[dict, dict, dict]) -> None:
    destination = OUTPUT_ROOT / phase
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in zip(("profiles", "protocol", "manifest"), inputs, strict=True):
        path = destination / f"condition_{name}.json"
        content = v1.canonical_json(value) + b"\n"
        if path.exists() and path.read_bytes() != content:
            raise SystemExit(f"Error: frozen derived input changed: {path}")
        if not path.exists():
            path.write_bytes(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--score", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fixed-shards", action="store_true", help="use a fixed part per worker for VMLU")
    parser.add_argument("--workers-per-shard", type=int, default=1, help="parallel OMP requests within each fixed VMLU part")
    parser.add_argument("--phase", choices=("all", "main", "vmlu", "vbench"), default="all")
    parser.add_argument("--omp-bin", default="omp")
    args = parser.parse_args()
    if args.resume and not args.execute:
        parser.error("--resume requires --execute")
    if args.workers_per_shard < 1:
        parser.error("--workers-per-shard must be positive")
    if args.workers_per_shard > 1 and (args.phase != "vmlu" or not args.fixed_shards):
        parser.error("--workers-per-shard > 1 requires --phase vmlu --fixed-shards")
    os.chdir(ROOT)
    phases = ("main", "vmlu", "vbench") if args.phase == "all" else (args.phase,)
    cancellation_path = OUTPUT_ROOT / "cancelled_phases.json"
    if cancellation_path.exists():
        cancelled = json.loads(cancellation_path.read_text())
        phases = tuple(phase for phase in phases if phase not in cancelled)
        if not phases:
            raise SystemExit("Selected phase was cancelled by the user; no requests sent")
    inputs = {phase: inputs_for(phase) for phase in phases}
    with ExitStack() as stack:
        if args.execute:
            OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
            lock = stack.enter_context((OUTPUT_ROOT / ".campaign.lock").open("a+"))
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SystemExit("Error: Muse router campaign already running") from exc
            # Freeze all condition inputs before the first dataset request.
            for phase in phases:
                freeze_inputs(phase, inputs[phase])
            stack.enter_context(sampling_relay())
        for phase in phases:
            schedule = (
                f"shards=4 workers_per_shard={args.workers_per_shard} total_workers={4 * args.workers_per_shard}"
                if phase == "vmlu" and args.fixed_shards else "workers=4"
            )
            print(f"condition={CARDS[phase]} model={PROFILE_ID} phase={phase} n={inputs[phase][2]['n']} tools=none temperature=1.0 thinking=auto seed=omitted {schedule}", flush=True)
            print(f"manifest_sha256={inputs[phase][2]['manifest_sha256']}", flush=True)
            base = ["--phase", phase, "--profile", PROFILE_ID]
            runner, scorer = (v1_runner, v1_scorer) if phase == "main" else (v2_runner, v2_scorer)
            if args.score:
                invoke(scorer, phase, base, inputs[phase])
                continue
            run_args = [*base, "--omp-bin", args.omp_bin, "--max-cost-usd", "1"]
            if phase == "vmlu" and args.fixed_shards:
                run_args.append("--fixed-shards")
                if args.workers_per_shard > 1:
                    run_args.extend(["--workers-per-shard", str(args.workers_per_shard)])
            if args.execute:
                run_args.append("--execute")
                if args.resume:
                    run_args.append("--resume")
            invoke(runner, phase, run_args, inputs[phase])
            if args.execute:
                invoke(scorer, phase, base, inputs[phase])


if __name__ == "__main__":
    main()
