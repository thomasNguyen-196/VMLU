"""Run Muse Spark 1.3 with OMP full tools on MC-85 items not covered by MC-71.

From the repository root:
  .venv/bin/python -m code_benchmark.run_muse13_omp_mc86                 # local preflight only
  .venv/bin/python -m code_benchmark.run_muse13_omp_mc86 --execute       # OMP probe + evaluation
  .venv/bin/python -m code_benchmark.run_muse13_omp_mc86 --execute --resume

The worker pool shares one manifest-ordered queue, so workers continue into
the next dataset as soon as they finish an item. The benchmark request prompt
and frozen scorer are taken from the MC-85 V1/V2 inputs; OMP adds its own
full-tools agent system and may call the model more than once per item.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http.client import HTTPSConnection, HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import subprocess  # nosec B404 — fixed OMP argv, no shell
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from code_benchmark import run_harness_eval as harness
from code_benchmark import run_mimo26_direct_20k_mc85 as mc85
from code_benchmark import run_vi_multimodel_eval as omp_runtime
from code_benchmark import score_vi_multimodel as main_scorer
from code_benchmark import score_vi_multimodel_expansion as vmlu_scorer
from code_benchmark import vi_multimodel as v1
from code_benchmark import vi_multimodel_expansion as v2
from code_benchmark.common import write_csv_atomic


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ID = "muse13-omp-full-tools-remaining-mc85-mc86-v1"
CARD_ID = "MC-86"
CARD_PATH = ROOT / "docs/measurement_cards/MC-86-muse13-omp-full-tools-remaining.md"
ROOT_CARD_PATH = ROOT / "measurement_card.md"
OUTPUT_ROOT = ROOT / "all_res/muse13_omp_mc86"
LOG_PATH = ROOT / "logs/muse13_omp_mc86.log"
PROFILE = "muse-spark-1-3-contributor-omp-full-tools-mc86"
MODEL_REF = "zen-go/muse-spark-1.3-contributor"
MODEL_ID = "muse-spark-1.3-contributor"
BASE_AGENT_DIR = ROOT / ".omp-muse-spark-full"
OMP_BIN = "omp"
BWRAP_BIN = "bwrap"
BWRAP_BIN = "bwrap"
OMP_VERSION_REQUIRED = "omp/18.0.0"
WORKERS = 12
MAX_OUTPUT_TOKENS_PER_TURN = 20_000
MAX_TIME_SECONDS = 300
TIMEOUT_SLACK_SECONDS = 60
MAX_ATTEMPTS = 3
CHECKPOINT_EVERY = 25
LEGAL_MC_ID = "vi-multimodel-v1-legal-mc-146"
MC71_LEDGER = ROOT / (
    "all_res/ollama_result/muse-spark-1-3-contributor-h2-legal-mc-full-tools-auto/"
    "harness_ledger_legal_mc_muse-spark-1-3-contributor-h2-legal-mc-full-tools-auto.csv"
)
MC85_MAIN_RUN = ROOT / "all_res/mimo26_direct_mc85/main/mimo-v2-6-flash-direct-20k"
MC85_VMLU_RUN = ROOT / "all_res/mimo26_direct_mc85/vmlu/mimo-v2-6-flash-direct-20k"
MAIN_OUT = OUTPUT_ROOT / "main" / PROFILE
VMLU_OUT = OUTPUT_ROOT / "vmlu" / PROFILE
AGENT_ROOT = OUTPUT_ROOT / "omp_workers"
RELAY_API_KEY_ENV = "MC86_RELAY_API_KEY"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(v1.canonical_json(value) + b"\n")
    temporary.replace(path)


def report(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{now()} {message}\n")
    print(message, flush=True)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    v1.write_jsonl_atomic(path, rows)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _dataset_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(item["dataset_id"] for item in items).items()))


def _phase_manifest(phase: str, parent: dict[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": 1,
        "phase": phase,
        "n": len(refs),
        "parent_manifest_sha256": parent["manifest_sha256"],
        "source_sha256": parent["source_sha256"],
        "dataset_counts": dict(sorted(Counter(row["dataset_id"] for row in refs).items())),
        "items": refs,
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest


def _item_request(item: Any, ref: dict[str, Any], phase: str) -> dict[str, Any]:
    prompt_hash = v1.sha256_bytes(item.prompt.encode("utf-8"))
    if prompt_hash != ref["prompt_sha256"]:
        raise SystemExit(f"Error: prompt hash drift for {item.run_key}")
    task = str(item.task)
    if task not in {"multiple_choice", "reading"}:
        raise SystemExit(f"Error: unsupported task {task!r} for {item.run_key}")
    gold_status = str(getattr(item, "gold_status", "local"))
    gold = getattr(item, "gold_answer", None)
    if gold_status == "withheld" and gold is not None:
        raise SystemExit(f"Error: withheld Test gold present for {item.run_key}")
    return {
        "run_key": item.run_key,
        "phase": phase,
        "dataset_id": item.dataset_id,
        "item_id": item.item_id,
        "replicate_id": item.replicate_id,
        "task": task,
        "kind": "mc" if task == "multiple_choice" else "reading",
        "question": item.question,
        "prompt": item.prompt,
        "prompt_sha256": prompt_hash,
        "input_sha256": ref["input_sha256"],
        "gold_status": gold_status,
        "gold_answer": gold,
        "source_split": str(getattr(item, "source_split", "main")),
        "stratum": item.stratum,
    }


def _load_inputs() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    phases, _parent = mc85.inputs()
    main_parent, main_rebuilt, main_objects = phases[0][1], phases[0][2], phases[0][3]
    vmlu_parent, vmlu_rebuilt, vmlu_objects = phases[1][1], phases[1][2], phases[1][3]
    main_ref_by_key = {
        f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}": row
        for row in main_parent["items"]
    }
    vmlu_ref_by_key = {
        f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}": row
        for row in vmlu_parent["items"]
    }
    excluded = [item for item in main_objects if item.dataset_id == LEGAL_MC_ID]
    included_main = [item for item in main_objects if item.dataset_id != LEGAL_MC_ID]
    if len(main_objects) != 2043 or len(excluded) != 146 or len(included_main) != 1897:
        raise SystemExit("Error: MC-85 main coverage drift")
    if len(vmlu_objects) != 10136:
        raise SystemExit("Error: MC-85 Dev/Test coverage drift")
    excluded_ids = {item.item_id for item in excluded}
    if len(excluded_ids) != 146:
        raise SystemExit("Error: MC-71 exclusion has duplicate item IDs")

    try:
        with MC71_LEDGER.open("r", newline="", encoding="utf-8") as handle:
            old_rows = list(__import__("csv").DictReader(handle))
    except OSError as exc:
        raise SystemExit(f"Error: MC-71 ledger unavailable ({type(exc).__name__})") from exc
    old_by_id = {row["item_id"]: row["prompt_sha256"] for row in old_rows}
    expected_by_id = {
        item.item_id: v1.sha256_bytes(item.prompt.encode("utf-8")) for item in excluded
    }
    if len(old_rows) != 146 or set(old_by_id) != set(expected_by_id):
        raise SystemExit("Error: MC-71 does not cover the exact Legal MC exclusion set")
    if any(old_by_id[item_id] != prompt_hash for item_id, prompt_hash in expected_by_id.items()):
        raise SystemExit("Error: MC-71 prompt hashes differ from the MC-85 Legal MC inputs")

    main_refs = [main_ref_by_key[item.run_key] for item in included_main]
    vmlu_refs = [vmlu_ref_by_key[item.run_key] for item in vmlu_objects]
    main_manifest = _phase_manifest("main", main_parent, main_refs)
    vmlu_manifest = _phase_manifest("vmlu", vmlu_parent, vmlu_refs)
    requests = [
        _item_request(item, main_ref_by_key[item.run_key], "main") for item in included_main
    ] + [
        _item_request(item, vmlu_ref_by_key[item.run_key], "vmlu") for item in vmlu_objects
    ]
    expected = {
        "vi-multimodel-v1-vmlu-valid": 744,
        "vi-multimodel-v1-legal-nli-150": 150,
        "vi-multimodel-v1-vi-squad-200": 200,
        "vi-multimodel-v1-vi-drop-200": 200,
        "vi-multimodel-v1-bidlqa-test": 603,
        "vi-multimodel-v2-vmlu-dev": 303,
        "vi-multimodel-v2-vmlu-test": 9833,
    }
    if _dataset_counts(requests) != dict(sorted(expected.items())):
        raise SystemExit(f"Error: MC-86 item coverage drift: {_dataset_counts(requests)}")
    if len(requests) != 12033 or len({item["run_key"] for item in requests}) != 12033:
        raise SystemExit("Error: MC-86 requires 12,033 unique items")
    if any(item["dataset_id"] == LEGAL_MC_ID for item in requests):
        raise SystemExit("Error: MC-71 Legal MC items must not be rerun")

    combined = {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": 1,
        "n": len(requests),
        "excluded_mc71": {
            "dataset_id": LEGAL_MC_ID,
            "n": len(excluded),
            "ledger_sha256": sha256_file(MC71_LEDGER),
            "id_prompt_parity": "exact",
        },
        "mc85_parent_manifests": {
            "main": main_parent["manifest_sha256"],
            "vmlu": vmlu_parent["manifest_sha256"],
        },
        "dataset_counts": _dataset_counts(requests),
        "items": [
            {"phase": item["phase"], "run_key": item["run_key"],
             "dataset_id": item["dataset_id"], "item_id": item["item_id"],
             "replicate_id": item["replicate_id"], "prompt_sha256": item["prompt_sha256"],
             "input_sha256": item["input_sha256"], "gold_status": item["gold_status"]}
            for item in requests
        ],
    }
    combined["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(combined))
    data = {
        "main_manifest": main_manifest,
        "main_rebuilt": main_rebuilt,
        "main_objects": included_main,
        "vmlu_manifest": vmlu_manifest,
        "vmlu_rebuilt": vmlu_rebuilt,
        "vmlu_objects": vmlu_objects,
        "requests": requests,
        "combined_manifest": combined,
        "main_parent": main_parent,
        "vmlu_parent": vmlu_parent,
        "expected": expected,
    }
    return data, main_rebuilt, vmlu_rebuilt, requests


def _omp_version(omp_bin: str) -> str:
    resolved = shutil.which(omp_bin)
    if not resolved:
        raise SystemExit("Error: OMP executable not found on PATH")
    result = subprocess.run([resolved, "--version"], capture_output=True, text=True,
                            timeout=15, check=False)  # nosec B603 — fixed --version probe
    if result.returncode != 0:
        raise SystemExit(f"Error: OMP version command failed ({result.returncode})")
    version = (result.stdout or result.stderr).strip()
    if version != OMP_VERSION_REQUIRED:
        raise SystemExit(f"Error: OMP version drift: expected {OMP_VERSION_REQUIRED}, got {version}")
    return resolved


def _bwrap_version(bwrap_bin: str) -> tuple[str, str]:
    resolved = shutil.which(bwrap_bin)
    if not resolved:
        raise SystemExit("Error: Bubblewrap executable not found; refusing to run full tools without item isolation")
    result = subprocess.run([resolved, "--version"], capture_output=True, text=True,
                            timeout=15, check=False)  # nosec B603 — fixed --version probe
    if result.returncode != 0:
        raise SystemExit(f"Error: Bubblewrap version command failed ({result.returncode})")
    return resolved, (result.stdout or result.stderr).strip()


def _model_configuration() -> tuple[dict[str, Any], str, str, str, str]:
    profiles = v2.load_profiles()
    profile = profiles.get("muse-spark-1-3-contributor")
    if profile is None:
        raise SystemExit("Error: Muse Spark 1.3 OMP profile unavailable")
    endpoint, api_key, request_model, credential_source = omp_runtime._resolve_model(profile)
    model_ref = str(profile.get("model_ref", ""))
    if model_ref != MODEL_REF or request_model != MODEL_ID:
        raise SystemExit("Error: Muse Spark 1.3 route differs from MC-86")
    return profile, endpoint, api_key, request_model, credential_source


def _start_credential_relay(endpoint: str, upstream_key: str) -> tuple[ThreadingHTTPServer, threading.Thread, str, str]:
    """Keep the OpenCode credential in this parent process, outside OMP tools."""
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("Error: invalid OpenCode Go endpoint for credential relay")
    upstream_prefix = parsed.path.rstrip("/")
    relay_key = secrets.token_urlsafe(32)

    class RelayHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args: Any) -> None:
            return

        def do_POST(self) -> None:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {relay_key}":
                self.send_error(401)
                return
            if not self.path.startswith(upstream_prefix + "/"):
                self.send_error(404)
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(411)
                return
            if content_length <= 0 or content_length > 20_000_000:
                self.send_error(413)
                return
            body = self.rfile.read(content_length)
            connection_class = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
            conn = connection_class(parsed.hostname, parsed.port, timeout=MAX_TIME_SECONDS + TIMEOUT_SLACK_SECONDS)
            headers = {
                "Authorization": f"Bearer {upstream_key}",
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Accept": self.headers.get("Accept", "text/event-stream, application/json"),
                "Accept-Encoding": "identity",
                "User-Agent": self.headers.get("User-Agent", "VMLU-MC-86-secure-relay"),
            }
            hop_by_hop = {
                "host", "authorization", "content-length", "transfer-encoding", "connection",
                "proxy-connection", "keep-alive", "te", "trailer", "upgrade", "accept-encoding",
                "cookie", "x-api-key",
            }
            for name, value in self.headers.items():
                if name.lower() not in hop_by_hop:
                    headers[name] = value
            try:
                conn.request("POST", self.path, body=body, headers=headers)
                response = conn.getresponse()
                self.send_response(response.status, response.reason)
                for name, value in response.getheaders():
                    if name.lower() in {
                        "content-type", "content-encoding", "cache-control", "retry-after",
                        "x-request-id", "openai-processing-ms", "openai-version",
                        "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
                        "x-ratelimit-reset-requests", "x-ratelimit-limit-tokens",
                        "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens",
                    }:
                        self.send_header(name, value)
                self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    chunk = response.read1(65_536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                response.close()
            except Exception:
                # Do not return upstream exception text; it may contain request or auth details.
                if not self.wfile.closed:
                    try:
                        self.close_connection = True
                    except OSError:
                        pass
            finally:
                conn.close()

    server = ThreadingHTTPServer(("127.0.0.1", 0), RelayHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="mc86-credential-relay", daemon=True)
    thread.start()
    port = int(server.server_address[1])
    local_base_url = f"http://127.0.0.1:{port}{upstream_prefix}"
    return server, thread, local_base_url, relay_key


def _read_agent_template() -> tuple[dict[str, Any], dict[str, Any], bytes]:
    try:
        config_bytes = (BASE_AGENT_DIR / "config.yml").read_bytes()
        models_bytes = (BASE_AGENT_DIR / "models.yml").read_bytes()
        append_bytes = (BASE_AGENT_DIR / "APPEND_SYSTEM.md").read_bytes()
        config = json.loads(config_bytes)
        models = json.loads(models_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read isolated MC-71 OMP profile ({type(exc).__name__})") from exc
    providers = models.get("providers", {})
    zen_go = providers.get("zen-go", {})
    entries = zen_go.get("models", [])
    matching = [entry for entry in entries if entry.get("id") == MODEL_ID]
    if len(matching) != 1 or zen_go.get("api") != "openai-responses":
        raise SystemExit("Error: OMP profile does not pin the expected Muse Responses route")
    if str(zen_go.get("baseUrl", "")).rstrip("/") != str(
        v2.load_profiles()["muse-spark-1-3-contributor"].get("base_url", "")
    ).rstrip("/"):
        raise SystemExit("Error: OMP profile endpoint differs from Muse OMP profile registry")
    if append_bytes.strip():
        raise SystemExit("Error: MC-71 profile has appended system text; inspect before reuse")
    return config, models, append_bytes


def _prepare_agent_dirs(config: dict[str, Any], models: dict[str, Any], append: bytes,
                        local_base_url: str) -> tuple[list[Path], dict[str, Any]]:
    agent_dirs = []
    runtime_models = deepcopy(models)
    runtime_provider = runtime_models["providers"]["zen-go"]
    runtime_provider["baseUrl"] = local_base_url
    runtime_provider["apiKey"] = RELAY_API_KEY_ENV
    runtime_model = runtime_provider["models"][0]
    runtime_model["maxTokens"] = MAX_OUTPUT_TOKENS_PER_TURN
    for worker_id in range(1, WORKERS + 1):
        path = AGENT_ROOT / f"worker-{worker_id:02d}"
        path.mkdir(parents=True, exist_ok=True)
        worker_config = deepcopy(config)
        worker_config["temperature"] = 1.0
        (path / "config.yml").write_text(
            json.dumps(worker_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        worker_models = deepcopy(runtime_models)
        model = worker_models["providers"]["zen-go"]["models"][0]
        model.setdefault("headers", {}).setdefault("x-opencode-session", "")
        (path / "models.yml").write_text(
            json.dumps(worker_models, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (path / "APPEND_SYSTEM.md").write_bytes(append)
        agent_dirs.append(path.resolve())
    return agent_dirs, runtime_models


def _make_condition(data: dict[str, Any], version: str, sandbox_version: str, endpoint: str,
                    credential_source: str, config: dict[str, Any], models: dict[str, Any],
                    append: bytes) -> dict[str, Any]:
    endpoint_host = urlsplit(endpoint).hostname
    condition = {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": 1,
        "measurement_card_id": CARD_ID,
        "measurement_card_sha256": sha256_file(CARD_PATH),
        "measurement_card_registry_sha256": sha256_file(ROOT_CARD_PATH),
        "runner_sha256": sha256_file(Path(__file__)),
        "harness_runner_sha256": sha256_file(Path(harness.__file__)),
        "main_scorer_sha256": sha256_file(Path(main_scorer.__file__)),
        "vmlu_scorer_sha256": sha256_file(Path(vmlu_scorer.__file__)),
        "model_id": MODEL_ID,
        "model_ref": MODEL_REF,
        "provider": "OpenCode Go",
        "credential_source": credential_source,
        "endpoint_host": endpoint_host,
        "transport": "omp",
        "omp_version": version,
        "sandbox": "bubblewrap isolated item filesystem; no host home/repo/data mounts; network namespace shared for relay/tools",
        "bubblewrap_version": sandbox_version,
        "omp_mode": "json",
        "omp_tools": "all; OMP default full tool menu",
        "omp_system_prompt": "OMP coding-agent default; no custom appended system text",
        "omp_auto_approve": True,
        "omp_session_policy": "no session/title; one isolated process and scratch directory per item",
        "temperature_requested": 1.0,
        "temperature_effective": None,
        "temperature_policy": "set to 1.0 in isolated OMP config; provider effective value unverified",
        "thinking": "auto",
        "seed_sent": None,
        "max_tokens_per_turn": MAX_OUTPUT_TOKENS_PER_TURN,
        "max_time_seconds_per_item": MAX_TIME_SECONDS,
        "hard_timeout_seconds_per_item": MAX_TIME_SECONDS + TIMEOUT_SLACK_SECONDS,
        "max_attempts_for_transient_failures": MAX_ATTEMPTS,
        "workers": WORKERS,
        "scheduler": "one global manifest-ordered dataset queue; workers claim next pending item",
        "expected_n": len(data["requests"]),
        "dataset_counts": data["combined_manifest"]["dataset_counts"],
        "excluded_mc71": data["combined_manifest"]["excluded_mc71"],
        "mc85_parent_manifest_sha256": data["combined_manifest"]["mc85_parent_manifests"],
        "mc85_main_condition_sha256": json.loads((MC85_MAIN_RUN / "run.json").read_text())["condition_sha256"],
        "mc85_vmlu_condition_sha256": json.loads((MC85_VMLU_RUN / "run.json").read_text())["condition_sha256"],
        "manifest_sha256": data["combined_manifest"]["manifest_sha256"],
        "main_manifest_sha256": data["main_manifest"]["manifest_sha256"],
        "vmlu_manifest_sha256": data["vmlu_manifest"]["manifest_sha256"],
        "mc71_ledger_sha256": data["combined_manifest"]["excluded_mc71"]["ledger_sha256"],
        "omp_template_config_sha256": hashlib.sha256(v1.canonical_json(config)).hexdigest(),
        "omp_template_models_sha256": hashlib.sha256(v1.canonical_json(models)).hexdigest(),
        "omp_template_append_system_sha256": hashlib.sha256(append).hexdigest(),
        "credential_boundary": "parent-resolved OpenCode Go key; loopback streaming relay; only an ephemeral relay key enters OMP/tools",
        "relay_policy": "ephemeral 127.0.0.1 listener; transparent Responses streaming; no request/response body logging",
        "gold_policy": "local gold is never written to item.json; VMLU Test gold withheld",
        "test_grade_policy": "no local Test accuracy; local submission only after full coverage; no upload",
        "cost_usd": None,
        "cost_basis": "OpenCode Go tariff unavailable; preserve reported usage, do not infer dollars",
    }
    return condition


def _configure_item_profile(agent_dir: Path, models: dict[str, Any], run_key: str, attempt: int) -> str:
    profile = deepcopy(models)
    model = profile["providers"]["zen-go"]["models"][0]
    model["maxTokens"] = MAX_OUTPUT_TOKENS_PER_TURN
    session = hashlib.sha256(f"{PROTOCOL_ID}:{run_key}:{attempt}".encode()).hexdigest()[:32]
    model.setdefault("headers", {})["x-opencode-session"] = session
    payload = json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
    path = agent_dir / "models.yml"
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _redact(text: str, api_key: str) -> tuple[str, int]:
    if not api_key:
        return text, 0
    count = text.count(api_key)
    return text.replace(api_key, "[REDACTED]"), count


def _sandbox_argv(*, bwrap_bin: str, omp_bin: str, item: dict[str, Any],
                  workdir: Path, agent_dir: Path, home: Path, relay_key: str) -> list[str]:
    omp_argv = harness.build_argv(
        omp_bin="/opt/omp",
        model=MODEL_REF,
        prompt=item["prompt"],
        workdir=Path("/workspace"),
        tools="all",
        max_time=MAX_TIME_SECONDS,
        thinking="auto",
        system_prompt=None,
    )
    return [
        bwrap_bin,
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-uts",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--dir", "/opt",
        "--dir", "/etc",
        "--dir", "/etc/ssl",
        "--ro-bind", "/etc/ssl/certs", "/etc/ssl/certs",
        "--ro-bind", "/etc/hosts", "/etc/hosts",
        "--ro-bind", str(Path("/etc/resolv.conf").resolve()), "/etc/resolv.conf",
        "--ro-bind", "/etc/nsswitch.conf", "/etc/nsswitch.conf",
        "--ro-bind", "/etc/passwd", "/etc/passwd",
        "--ro-bind", "/etc/group", "/etc/group",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",  # nosec B108 - path inside the bwrap sandbox (fresh tmpfs), not the host /tmp
        "--dir", "/home",
        "--bind", str(home), "/home/bench",
        "--bind", str(workdir), "/workspace",
        "--bind", str(agent_dir.resolve()), "/omp-agent",
        "--ro-bind", omp_bin, "/opt/omp",
        "--setenv", "HOME", "/home/bench",
        "--setenv", "PI_CODING_AGENT_DIR", "/omp-agent",
        "--setenv", RELAY_API_KEY_ENV, relay_key,
        "--setenv", "PATH", "/opt:/usr/bin:/bin",
        "--setenv", "TMPDIR", "/tmp",  # nosec B108 - path inside the bwrap sandbox (fresh tmpfs), not the host /tmp
        "--setenv", "LANG", "C.UTF-8",
        "--chdir", "/workspace",
        "--",
        *omp_argv,
    ]


def _classify_error(exit_code: int, stop_reason: str, error_blob: str, raw_response: str) -> tuple[str, bool, bool, int | None]:
    lower = error_blob.lower()
    status_match = re.search(r"(?:http(?: status)?|status code|status)\s*[:=]?\s*(\d{3})", lower)
    http_status = int(status_match.group(1)) if status_match else None
    fatal_tokens = (
        "401", "402", "403", "404", "invalid_api_key", "unauthorized", "authentication",
        "permission denied", "insufficient_quota", "billing", "model_not_found", "invalid_request",
    )
    if http_status in {400, 401, 402, 403, 404} or any(token in lower for token in fatal_tokens):
        return "permanent_provider_or_config_error", True, False, http_status
    transient_tokens = (
        "429", "500", "502", "503", "504", "timeout", "temporarily unavailable",
        "connection reset", "connection refused", "econnreset", "etimedout", "rate_limit",
        "overloaded", "network is unreachable", "temporary failure in name resolution",
    )
    if exit_code != 0 or stop_reason.lower() in {"error", "failed", "aborted"} or not raw_response.strip():
        retryable = any(token in lower for token in transient_tokens)
        error = "timeout" if "timeout" in lower else "omp_exit" if exit_code else "omp_turn_error"
        return error, False, retryable, http_status
    return "", False, False, http_status


def _web_search_events(events: list[dict[str, Any]], tool_names: list[str]) -> list[dict[str, Any]]:
    """Capture one status row per web_search invocation without storing result content."""
    calls: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") == "message_end":
            message = event.get("message") or {}
            if message.get("role") != "assistant":
                continue
            for block in message.get("content") or []:
                if block.get("type") != "toolCall":
                    continue
                name = str(block.get("name") or (block.get("arguments") or {}).get("name") or "")
                if name != "web_search":
                    continue
                calls.append({
                    "tool_name": name,
                    "tool_call_id": str(block.get("id") or block.get("toolCallId") or ""),
                    "status": "unrecorded",
                    "status_source": "tool_call_without_execution_end",
                })
            continue

        if event.get("type") != "tool_execution_end":
            continue
        name = str(event.get("toolName") or event.get("tool_name") or "")
        call_id = str(event.get("toolCallId") or event.get("tool_call_id") or "")
        is_error = event.get("isError", event.get("is_error"))
        status = "failure" if is_error is True else "success" if is_error is False else "unrecorded"
        if name and name != "web_search":
            continue

        match = next((call for call in calls if call_id and call["tool_call_id"] == call_id), None)
        if match is None and name == "web_search":
            match = next((call for call in calls if call["status"] == "unrecorded"), None)
        if match is None:
            if name != "web_search":
                continue
            match = {"tool_name": "web_search", "tool_call_id": call_id}
            calls.append(match)
        elif call_id and not match.get("tool_call_id"):
            match["tool_call_id"] = call_id
        match["status"] = status
        match["status_source"] = "tool_execution_end"

    expected = sum(name == "web_search" for name in tool_names)
    while len(calls) < expected:
        calls.append({
            "tool_name": "web_search",
            "tool_call_id": "",
            "status": "unrecorded",
            "status_source": "attempt_summary_only",
        })
    for index, call in enumerate(calls, start=1):
        call["call_index"] = index
    return calls


def _run_item(item: dict[str, Any], *, worker_id: int, attempt: int, agent_dir: Path,
              base_models: dict[str, Any], relay_key: str, omp_bin: str, bwrap_bin: str, home: Path,
              scratch_root: Path) -> dict[str, Any]:
    started_at = now()
    started = time.monotonic()
    model_profile_sha = _configure_item_profile(agent_dir, base_models, item["run_key"], attempt)
    workdir = Path(tempfile.mkdtemp(prefix="mc86-item-", dir=scratch_root)).resolve()
    exit_code = -9
    stderr = ""
    stdout = ""
    events: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    response_text = ""
    timeout = False
    try:
        sandbox = {"id": item["item_id"], "kind": "mc" if item["task"] == "multiple_choice" else "reading",
                   "prompt": item["prompt"]}
        (workdir / "item.json").write_text(
            json.dumps(sandbox, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        harness.assert_no_project_instructions(workdir, allow=False)
        argv = _sandbox_argv(
            bwrap_bin=bwrap_bin,
            omp_bin=omp_bin,
            item=item,
            workdir=workdir,
            agent_dir=agent_dir,
            home=home,
            relay_key=relay_key,
        )
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True,
                timeout=MAX_TIME_SECONDS + TIMEOUT_SLACK_SECONDS,
                env=env, cwd=workdir, check=False,
            )  # nosec B603 — fixed argv, isolated cwd, no shell
            stdout, stderr, exit_code = proc.stdout or "", proc.stderr or "", proc.returncode
        except subprocess.TimeoutExpired as exc:
            timeout = True
            out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stdout = out
            stderr = "hard timeout after configured item limit"
            exit_code = -9
        redacted_stdout, stdout_redactions = _redact(stdout, relay_key)
        redacted_stderr, stderr_redactions = _redact(stderr, relay_key)
        events, response_text, stats = harness.parse_transcript(redacted_stdout.splitlines())
        network_attempt, path_escape = harness.audit_transcript(events)
        stop_reason = str(stats.get("stop_reason") or "")
        event_error = str(harness._event_error_detail(events)) if hasattr(harness, "_event_error_detail") else ""
        event_error, event_redactions = _redact(event_error, relay_key)
        error_blob = redacted_stderr + "\n" + stop_reason + "\n" + event_error
        error_type, fatal, retryable, http_status = _classify_error(
            exit_code, stop_reason, error_blob, response_text
        )
        if timeout:
            error_type, fatal, retryable = "timeout", False, True
        if not error_type:
            status = "complete"
            finish_reason = "length" if stop_reason.lower() in {"length", "max_tokens", "max_output_tokens"} else (stop_reason or "stop")
        else:
            status = "request_error"
            finish_reason = "error"
        parse_valid: bool
        if item["task"] == "multiple_choice":
            if item["phase"] == "vmlu":
                parsed = v2.parse_expanded_answer(
                    data_item_from_key(item), response_text
                )
                parse_valid = bool(parsed["parse_valid"])
            else:
                parse_valid = bool(harness.extract_answer(response_text))
        else:
            parse_valid = bool(response_text.strip())
        tool_names = list(stats.get("tool_names", []))
        web_search_events = _web_search_events(events, tool_names)
        message_events = [
            event.get("message", {}) for event in events
            if event.get("type") == "message_end" and event.get("message", {}).get("role") == "assistant"
        ]
        final_message = message_events[-1] if message_events else {}
        input_tokens = int(stats.get("input_tokens") or 0)
        cached_tokens = int(stats.get("cache_read_tokens") or 0)
        output_tokens = int(stats.get("output_tokens") or 0)
        row = {
            "run_key": item["run_key"],
            "protocol_id": PROTOCOL_ID,
            "measurement_card_id": CARD_ID,
            "profile_id": PROFILE,
            "model_id": MODEL_ID,
            "model_ref": MODEL_REF,
            "phase": item["phase"],
            "dataset_id": item["dataset_id"],
            "item_id": item["item_id"],
            "replicate_id": item["replicate_id"],
            "task": item["task"],
            "gold_status": item["gold_status"],
            "prompt_sha256": item["prompt_sha256"],
            "input_sha256": item["input_sha256"],
            "status": status,
            "finish_reason": finish_reason,
            "raw_response": response_text,
            "parse_valid": parse_valid,
            "worker_id": worker_id,
            "scheduler": "global-dataset-queue-v1",
            "attempt": attempt,
            "started_at": started_at,
            "finished_at": now(),
            "latency_s": round(time.monotonic() - started, 4),
            "tool_calls": int(stats.get("tool_calls") or 0),
            "tool_names": tool_names,
            "web_search_events": web_search_events,
            "network_attempt": network_attempt,
            "path_escape": path_escape,
            "prompt_tokens": input_tokens + cached_tokens,
            "uncached_prompt_tokens": input_tokens,
            "cached_prompt_tokens": cached_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + cached_tokens + output_tokens,
            "reasoning_tokens": _reasoning_tokens(events),
            "response_model_id": str(final_message.get("model") or ""),
            "request_id": str(final_message.get("id") or ""),
            "exit_code": exit_code,
            "http_status": http_status,
            "error_type": error_type,
            "fatal": fatal,
            "retryable": retryable,
            "model_profile_sha256": model_profile_sha,
            "credential_redactions": stdout_redactions + stderr_redactions + event_redactions,
        }
        return row
    except Exception as exc:
        safe_type = type(exc).__name__
        return {
            "run_key": item["run_key"], "protocol_id": PROTOCOL_ID,
            "measurement_card_id": CARD_ID, "profile_id": PROFILE, "model_id": MODEL_ID,
            "model_ref": MODEL_REF, "phase": item["phase"], "dataset_id": item["dataset_id"],
            "item_id": item["item_id"], "replicate_id": item["replicate_id"],
            "task": item["task"], "gold_status": item["gold_status"],
            "prompt_sha256": item["prompt_sha256"], "input_sha256": item["input_sha256"],
            "status": "request_error", "finish_reason": "error", "raw_response": "",
            "parse_valid": False, "worker_id": worker_id, "scheduler": "global-dataset-queue-v1",
            "attempt": attempt, "started_at": started_at, "finished_at": now(),
            "latency_s": round(time.monotonic() - started, 4), "tool_calls": 0, "tool_names": [],
            "web_search_events": _web_search_events(events, list(stats.get("tool_names", []))),
            "network_attempt": "", "path_escape": "", "prompt_tokens": 0,
            "uncached_prompt_tokens": 0, "cached_prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "reasoning_tokens": 0, "response_model_id": "", "request_id": "",
            "exit_code": exit_code, "http_status": None, "error_type": safe_type,
            "fatal": False, "retryable": False, "model_profile_sha256": model_profile_sha,
            "credential_redactions": 0,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _reasoning_tokens(events: list[dict[str, Any]]) -> int:
    total = 0
    for event in events:
        message = event.get("message", {})
        usage = message.get("usage") or {}
        details = usage.get("output_tokens_details") or usage.get("outputDetails") or {}
        total += int(details.get("reasoning_tokens") or details.get("reasoning") or 0)
    return total


def data_item_from_key(item: dict[str, Any]) -> Any:
    """Resolve the frozen V2 item by its global run key for answer parsing."""
    value = ACTIVE_V2_REBUILT.get(item["run_key"])
    if value is None:
        raise SystemExit(f"Error: V2 item cannot be rebuilt: {item['run_key']}")
    return value


ACTIVE_V2_REBUILT: dict[str, Any] = {}


def _write_phase_snapshot(phase: str, rows: dict[str, dict[str, Any]], ordered_keys: list[str],
                          manifest: dict[str, Any], condition_hash: str, status: str) -> None:
    output = MAIN_OUT if phase == "main" else VMLU_OUT
    output.mkdir(parents=True, exist_ok=True)
    phase_rows = [rows[key] for key in ordered_keys if key in rows and rows[key]["phase"] == phase]
    write_jsonl(output / "predictions.jsonl", phase_rows)
    atomic_json(output / "source_manifest.json", manifest)
    complete = sum(row.get("status") == "complete" for row in phase_rows)
    errors = sum(row.get("status") == "request_error" for row in phase_rows)
    atomic_json(output / "run.json", {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": 1,
        "phase": phase,
        "profile_id": PROFILE,
        "model_id": MODEL_ID,
        "model_ref": MODEL_REF,
        "measurement_card_id": CARD_ID,
        "condition_sha256": condition_hash,
        "manifest_sha256": manifest["manifest_sha256"],
        "expected_n": manifest["n"],
        "complete_items": complete,
        "request_error_items": errors,
        "remaining_items": manifest["n"] - complete,
        "status": status,
        "updated_at": now(),
    })


def _write_campaign_snapshot(rows: dict[str, dict[str, Any]], requests: list[dict[str, Any]],
                             condition_hash: str, status: str, state: dict[str, Any]) -> None:
    complete = sum(row.get("status") == "complete" for row in rows.values())
    errors = sum(row.get("status") == "request_error" for row in rows.values())
    latest_by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows.values():
        latest_by_dataset[row["dataset_id"]].append(row)
    dataset_progress = {}
    for dataset_id, expected in _dataset_counts(requests).items():
        dataset_rows = latest_by_dataset.get(dataset_id, [])
        count_complete = sum(row.get("status") == "complete" for row in dataset_rows)
        dataset_progress[dataset_id] = {
            "expected": expected,
            "complete": count_complete,
            "request_errors": sum(row.get("status") == "request_error" for row in dataset_rows),
            "remaining": expected - count_complete,
            "tool_calls": sum(int(row.get("tool_calls") or 0) for row in dataset_rows),
        }
    state.update({
        "protocol_id": PROTOCOL_ID,
        "protocol_version": 1,
        "measurement_card_id": CARD_ID,
        "profile_id": PROFILE,
        "model_ref": MODEL_REF,
        "expected_n": len(requests),
        "complete_items": complete,
        "request_error_items": errors,
        "remaining_items": len(requests) - complete,
        "dataset_progress": dataset_progress,
        "updated_at": now(),
        "status": status,
        "condition_sha256": condition_hash,
    })
    atomic_json(OUTPUT_ROOT / "campaign.json", state)


def _score_outputs(data: dict[str, Any], rows: dict[str, dict[str, Any]], condition_hash: str) -> dict[str, Any]:
    main_predictions = {
        row["run_key"]: row for row in rows.values() if row["phase"] == "main"
    }
    scored_main, main_summaries = main_scorer.score_rows(
        data["main_manifest"], main_predictions, data["main_rebuilt"]
    )
    write_jsonl(MAIN_OUT / "scores.jsonl", scored_main)
    main_summary = {
        "protocol_id": PROTOCOL_ID,
        "measurement_card_id": CARD_ID,
        "model_id": MODEL_REF,
        "transport": "omp",
        "manifest_sha256": data["main_manifest"]["manifest_sha256"],
        "condition_sha256": condition_hash,
        "expected_n": data["main_manifest"]["n"],
        "datasets": list(main_summaries.values()),
        "cost_usd": None,
        "cost_basis": "OpenCode Go tariff unavailable; usage retained",
    }
    atomic_json(MAIN_OUT / "summary.json", main_summary)

    vmlu_scorer.OUTPUT_DIR = OUTPUT_ROOT
    vmlu_scorer.PROTOCOL_ID = PROTOCOL_ID
    vmlu_scorer.load_manifest = lambda phase: data["vmlu_manifest"]
    vmlu_scorer.load_profiles = lambda: {PROFILE: {"model_id": MODEL_REF}}
    vmlu_scorer.rebuild_items = lambda phase: data["vmlu_rebuilt"]
    vmlu_summary = vmlu_scorer.score_profile("vmlu", PROFILE, allow_incomplete=True)
    vmlu_summary.update({
        "measurement_card_id": CARD_ID,
        "transport": "omp",
        "condition_sha256": condition_hash,
        "cost_usd": None,
        "cost_basis": "OpenCode Go tariff unavailable; usage retained",
    })
    atomic_json(VMLU_OUT / "summary.json", vmlu_summary)

    test_rows = [
        row for row in rows.values()
        if row["dataset_id"] == "vi-multimodel-v2-vmlu-test" and row["status"] == "complete"
    ]
    if len(test_rows) == 9833:
        answers = [
            {"id": row["item_id"],
             "answer": v2.parse_expanded_answer(
                 data["vmlu_rebuilt"][row["run_key"]], row["raw_response"]
             )["prediction"]}
            for row in sorted(test_rows, key=lambda value: value["item_id"])
        ]
        if len({row["id"] for row in answers}) != 9833:
            raise SystemExit("Error: duplicate VMLU Test submission IDs")
        write_csv_atomic(VMLU_OUT / "submission_vmlu_test.csv", answers, ["id", "answer"])

    result = {
        "protocol_id": PROTOCOL_ID,
        "measurement_card_id": CARD_ID,
        "condition_sha256": condition_hash,
        "expected_n": len(data["requests"]),
        "main": main_summary,
        "vmlu": vmlu_summary,
        "tool_calls": sum(int(row.get("tool_calls") or 0) for row in rows.values()),
        "total_input_tokens": sum(int(row.get("prompt_tokens") or 0) for row in rows.values()),
        "total_output_tokens": sum(int(row.get("completion_tokens") or 0) for row in rows.values()),
        "completed_n": sum(row.get("status") == "complete" for row in rows.values()),
        "request_error_n": sum(row.get("status") == "request_error" for row in rows.values()),
    }
    atomic_json(OUTPUT_ROOT / "summary.json", result)
    return result


def _run_pool(pending_items: list[dict[str, Any]], rows: dict[str, dict[str, Any]],
              attempts_by_key: Counter[str], data: dict[str, Any], condition_hash: str,
              state: dict[str, Any], agent_dirs: list[Path], base_models: dict[str, Any],
              relay_key: str, omp_bin: str, bwrap_bin: str, home: Path, scratch_root: Path,
              pass_number: int) -> bool:
    if not pending_items:
        return False
    pending = deque(pending_items)
    pending_lock = threading.Lock()
    active = 0
    peak_active = 0
    worker_assignments: Counter[str] = Counter(state.get("worker_assignments", {}))
    results: queue.Queue[dict[str, Any] | None] = queue.Queue()
    stop = threading.Event()
    sentinel_count = 0
    started_at = time.monotonic()

    def worker(worker_id: int) -> None:
        nonlocal active, peak_active
        try:
            while not stop.is_set():
                with pending_lock:
                    if not pending:
                        break
                    item = pending.popleft()
                    active += 1
                    peak_active = max(peak_active, active)
                attempt = int(attempts_by_key[item["run_key"]]) + 1
                row = _run_item(
                    item, worker_id=worker_id, attempt=attempt,
                    agent_dir=agent_dirs[worker_id - 1], base_models=base_models,
                    relay_key=relay_key, omp_bin=omp_bin, bwrap_bin=bwrap_bin,
                    home=home, scratch_root=scratch_root,
                )
                row["pass"] = pass_number
                with pending_lock:
                    active -= 1
                    worker_assignments[f"{worker_id}:{item['dataset_id']}"] += 1
                attempts_by_key[item["run_key"]] += 1
                results.put(row)
                if row.get("fatal"):
                    stop.set()
        finally:
            results.put(None)

    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="mc86-omp") as pool:
        futures = [pool.submit(worker, worker_id) for worker_id in range(1, WORKERS + 1)]
        processed = 0
        while sentinel_count < WORKERS:
            row = results.get()
            if row is None:
                sentinel_count += 1
                continue
            key = row["run_key"]
            rows[key] = row
            attempts_path = OUTPUT_ROOT / "attempts.jsonl"
            attempts_path.parent.mkdir(parents=True, exist_ok=True)
            with attempts_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            processed += 1
            if processed % CHECKPOINT_EVERY == 0 or row.get("fatal"):
                _write_phase_snapshot("main", rows, list(data["main_keys"]),
                                      data["main_manifest"], condition_hash, "running")
                _write_phase_snapshot("vmlu", rows, list(data["vmlu_keys"]),
                                      data["vmlu_manifest"], condition_hash, "running")
                state["pass"] = pass_number
                state["worker_assignments"] = dict(worker_assignments)
                state["peak_concurrent_items"] = max(int(state.get("peak_concurrent_items", 0)), peak_active)
                state["current_pass_progress"] = processed
                state["current_pass_total"] = len(pending_items)
                state["elapsed_seconds"] = round(time.monotonic() - started_at, 2)
                _write_campaign_snapshot(rows, data["requests"], condition_hash,
                                         "needs_attention" if row.get("fatal") else "running", state)
            if processed % 25 == 0 or processed == len(pending_items):
                rate = processed / max(time.monotonic() - started_at, 0.001)
                total_complete = sum(value.get("status") == "complete" for value in rows.values())
                report(
                    f"MC-86 pass={pass_number} pass_done={processed}/{len(pending_items)} "
                    f"total_complete={total_complete}/{len(data['requests'])} "
                    f"rate={rate:.2f}/s active_peak={peak_active}"
                )
        for future in futures:
            future.result()

    state["worker_assignments"] = dict(worker_assignments)
    state["peak_concurrent_items"] = max(int(state.get("peak_concurrent_items", 0)), peak_active)
    _write_phase_snapshot("main", rows, list(data["main_keys"]),
                          data["main_manifest"], condition_hash, "running")
    _write_phase_snapshot("vmlu", rows, list(data["vmlu_keys"]),
                          data["vmlu_manifest"], condition_hash, "running")
    return stop.is_set()


def _run_preflight(*, omp_bin: str, bwrap_bin: str, profile: dict[str, Any], endpoint: str, relay_key: str,
                   base_models: dict[str, Any], agent_dir: Path, home: Path,
                   scratch_root: Path) -> dict[str, Any]:
    item = {
        "run_key": f"{PROTOCOL_ID}:__preflight__",
        "phase": "preflight",
        "dataset_id": "__preflight__",
        "item_id": "__preflight__",
        "replicate_id": "preflight-000",
        "task": "multiple_choice",
        "kind": "mc",
        "question": "Reply with exactly READY. Do not use tools.",
        "prompt": "Reply with exactly READY. Do not use tools.",
        "prompt_sha256": hashlib.sha256(b"Reply with exactly READY. Do not use tools.").hexdigest(),
        "input_sha256": "",
        "gold_status": "none",
        "gold_answer": None,
        "source_split": "preflight",
        "stratum": "preflight",
    }
    row = _run_item(item, worker_id=1, attempt=1, agent_dir=agent_dir,
                    base_models=base_models, relay_key=relay_key, omp_bin=omp_bin,
                    bwrap_bin=bwrap_bin,
                    home=home, scratch_root=scratch_root)
    safe = {
        "started_at": row["started_at"], "finished_at": row["finished_at"],
        "status": row["status"], "response_model_id": row["response_model_id"],
        "request_id": row["request_id"], "finish_reason": row["finish_reason"],
        "tool_calls": row["tool_calls"], "prompt_tokens": row["prompt_tokens"],
        "completion_tokens": row["completion_tokens"], "latency_s": row["latency_s"],
        "error_type": row["error_type"], "credential_redactions": row["credential_redactions"],
        "endpoint_host": urlsplit(endpoint).hostname,
        "model_ref": profile.get("model_ref"),
    }
    atomic_json(OUTPUT_ROOT / "preflight.json", safe)
    if row["status"] != "complete" or row["raw_response"].strip() != "READY":
        raise SystemExit(f"Error: OMP preflight failed ({row['error_type'] or 'unexpected reply'}); no items started")
    return safe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run OMP preflight and benchmark items")
    parser.add_argument("--resume", action="store_true", help="resume only missing or retryable technical failures")
    parser.add_argument("--omp-bin", default=OMP_BIN)
    parser.add_argument("--bwrap-bin", default=BWRAP_BIN)
    args = parser.parse_args()

    data, _main_rebuilt, vmlu_rebuilt, requests = _load_inputs()
    global ACTIVE_V2_REBUILT
    ACTIVE_V2_REBUILT = vmlu_rebuilt
    omp_bin = _omp_version(args.omp_bin)
    bwrap_bin, sandbox_version = _bwrap_version(args.bwrap_bin)
    profile, endpoint, api_key, _request_model, credential_source = _model_configuration()
    base_config, base_models, append_system = _read_agent_template()
    if urlsplit(endpoint).hostname != "opencode.ai":
        raise SystemExit("Error: unexpected OpenCode Go endpoint host")
    condition = _make_condition(data, OMP_VERSION_REQUIRED, sandbox_version, endpoint, credential_source,
                                base_config, base_models, append_system)
    condition_hash = v1.sha256_bytes(v1.canonical_json(condition))
    message = (
        f"preflight=passed protocol={PROTOCOL_ID} items={len(requests)} "
        f"datasets={data['combined_manifest']['dataset_counts']} workers={WORKERS} "
        f"queue=global tools=all cap_per_turn={MAX_OUTPUT_TOKENS_PER_TURN} "
        f"timeout={MAX_TIME_SECONDS}s sandbox={sandbox_version} endpoint_calls=0 credential={credential_source}"
    )
    print(message, flush=True)
    if not args.execute:
        print("preflight only; no model endpoint was called", flush=True)
        return

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ROOT.joinpath("campaign.json").exists() and not args.resume:
        raise SystemExit("Error: MC-86 output already exists; use --resume after checking the condition")
    if args.resume and OUTPUT_ROOT.joinpath("condition.json").is_file():
        old = json.loads((OUTPUT_ROOT / "condition.json").read_text(encoding="utf-8"))
        old_hash = v1.sha256_bytes(v1.canonical_json(old))
        if old_hash != condition_hash:
            raise SystemExit("Error: MC-86 resume would change the frozen condition")
    else:
        atomic_json(OUTPUT_ROOT / "condition.json", condition)
        atomic_json(OUTPUT_ROOT / "source_manifest.json", data["combined_manifest"])
        shutil.copyfile(CARD_PATH, OUTPUT_ROOT / "measurement_card_snapshot.md")

    relay_server, relay_thread, local_base_url, relay_key = _start_credential_relay(endpoint, api_key)
    agent_dirs, runtime_models = _prepare_agent_dirs(base_config, base_models, append_system, local_base_url)
    home = Path(tempfile.mkdtemp(prefix="vmlu-mc86-home-")).resolve()
    scratch_root = Path(tempfile.mkdtemp(prefix="vmlu-mc86-scratch-")).resolve()
    state_path = OUTPUT_ROOT / "campaign.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "pid": os.getpid(), "started_at": now(), "status": "configured",
        "worker_assignments": {}, "peak_concurrent_items": 0,
    }
    rows: dict[str, dict[str, Any]] = {}
    attempts_by_key: Counter[str] = Counter()
    for output, phase_keys in ((MAIN_OUT, [item["run_key"] for item in requests if item["phase"] == "main"]),
                               (VMLU_OUT, [item["run_key"] for item in requests if item["phase"] == "vmlu"])):
        for row in read_jsonl(output / "predictions.jsonl"):
            if row.get("run_key") in phase_keys:
                rows[row["run_key"]] = row
    persisted_worker_assignments: Counter[str] = Counter()
    for attempt in read_jsonl(OUTPUT_ROOT / "attempts.jsonl"):
        if attempt.get("run_key"):
            attempts_by_key[attempt["run_key"]] += 1
            rows[attempt["run_key"]] = attempt
            persisted_worker_assignments[f"{attempt.get('worker_id')}:{attempt.get('dataset_id')}"] += 1
    if persisted_worker_assignments:
        state["worker_assignments"] = dict(persisted_worker_assignments)

    data["main_keys"] = [item["run_key"] for item in requests if item["phase"] == "main"]
    data["vmlu_keys"] = [item["run_key"] for item in requests if item["phase"] == "vmlu"]
    for phase, manifest in (("main", data["main_manifest"]), ("vmlu", data["vmlu_manifest"])):
        _write_phase_snapshot(phase, rows, list(data[f"{phase}_keys"]), manifest,
                              condition_hash, "configured")
    _write_campaign_snapshot(rows, requests, condition_hash, "configured", state)

    preflight_path = OUTPUT_ROOT / "preflight.json"
    if not preflight_path.exists():
        _run_preflight(omp_bin=omp_bin, bwrap_bin=bwrap_bin, profile=profile,
                       endpoint=endpoint, relay_key=relay_key,
                       base_models=runtime_models, agent_dir=agent_dirs[0], home=home,
                       scratch_root=scratch_root)
    else:
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        if preflight.get("status") != "complete":
            raise SystemExit("Error: saved MC-86 preflight is not successful")

    fatal = False
    for pass_number in range(1, MAX_ATTEMPTS + 1):
        pending_items = []
        for item in requests:
            latest = rows.get(item["run_key"])
            if latest and latest.get("status") == "complete":
                continue
            if latest and latest.get("status") == "request_error" and not latest.get("retryable"):
                continue
            if attempts_by_key[item["run_key"]] >= MAX_ATTEMPTS:
                continue
            pending_items.append(item)
        if not pending_items:
            break
        if pass_number > 1:
            report(f"MC-86 recovery pass {pass_number} begins after 60s cooldown")
            time.sleep(60)
        state["pid"] = os.getpid()
        state["pass"] = pass_number
        state["status"] = "running"
        _write_campaign_snapshot(rows, requests, condition_hash, "running", state)
        fatal = _run_pool(
            pending_items, rows, attempts_by_key, data, condition_hash, state,
            agent_dirs, runtime_models, relay_key, omp_bin, bwrap_bin, home, scratch_root, pass_number,
        )
        if fatal:
            break

    for phase, manifest in (("main", data["main_manifest"]), ("vmlu", data["vmlu_manifest"])):
        _write_phase_snapshot(phase, rows, list(data[f"{phase}_keys"]), manifest,
                              condition_hash, "complete" if all(rows.get(key, {}).get("status") == "complete"
                                                                 for key in data[f"{phase}_keys"]) else "incomplete")
    result = _score_outputs(data, rows, condition_hash)
    missing = [item["run_key"] for item in requests if rows.get(item["run_key"], {}).get("status") != "complete"]
    state.update({
        "finished_at": now(),
        "status": "needs_attention" if fatal else "complete" if not missing else "incomplete",
        "missing_or_failed_keys_n": len(missing),
        "missing_or_failed_keys_sample": missing[:20],
        "total_tool_calls": result["tool_calls"],
        "total_input_tokens": result["total_input_tokens"],
        "total_output_tokens": result["total_output_tokens"],
    })
    _write_campaign_snapshot(rows, requests, condition_hash, state["status"], state)
    shutil.rmtree(home, ignore_errors=True)
    shutil.rmtree(scratch_root, ignore_errors=True)
    relay_server.shutdown()
    relay_server.server_close()
    relay_thread.join(timeout=2)
    report(
        f"MC-86 status={state['status']} complete={state['complete_items']}/{len(requests)} "
        f"errors={state['request_error_items']} tool_calls={result['tool_calls']} "
        f"peak_workers={state.get('peak_concurrent_items', 0)} output={OUTPUT_ROOT}"
    )


if __name__ == "__main__":
    main()
