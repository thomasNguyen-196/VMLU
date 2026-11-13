"""Run MC-113: MC-112's forced-search task (DSHF) inside omp 18.0.0 over the same legal corpus folder (openspec
change diagnostic-legal-agent-omp).

From the repo root:
  .venv/bin/python -m code_benchmark.run_legal_agent_omp                       # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_legal_agent_omp --freeze-manifest     # write manifest_v1.json (offline)
  .venv/bin/python -m code_benchmark.run_legal_agent_omp --selftest            # omp end to end, scripted server
  .venv/bin/python -m code_benchmark.run_legal_agent_omp --smoke --execute     # smoke-1 to smoke-4 on IEC (§10)
  .venv/bin/python -m code_benchmark.run_legal_agent_omp --execute [--resume] [--tunnel-dns <in-tunnel DNS server>]

Each attempt runs `omp -p --mode json` in its own bubblewrap sandbox: no network, a fresh home holding only the
registered `config.yml` and `models.yml`, an empty environment, only system directories, the pinned omp binary and
the relay visible, and the corpus folder mounted read-only as the working directory `/work/van-ban-phap-luat`. The
relay inside forwards to this process's per-attempt proxy: MC-112's proxy (temperature 1.0 added, key swapped, every
request recorded) with omp's request-shape checks on top (design §5). omp's session stays in the attempt's home; the
native libraries omp unpacks into it (about 300 MB, identical every time) are deleted after the attempt.

Attempt statuses (design §7): `complete` when omp exits 0 and its last assistant message stopped with `stop` and has
text (scored on that text); `request_cap`, `upstream_4xx`, `answer_cap` and `harness_end` are complete rows with no
answer (scored wrong, never retried); network errors, timeouts, gateway 5xx and the wall clock (omp's --max-time or
the runner's kill) are technical failures that `--resume` re-runs from scratch. A refused request, a changed
response model id or a sandbox that never reached the proxy pauses the run.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess  # nosec B404 - bwrap and omp --version only, with argument lists built here
import tempfile
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_legal_retrieval as lr
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import dsh_proxy as px
    from code_benchmark import fake_chat_upstream as fu
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_legal_agent as rla
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_oracle as lo  # type: ignore[no-redef]
    import diagnostic_legal_retrieval as lr  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import dsh_proxy as px  # type: ignore[no-redef]
    import fake_chat_upstream as fu  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import run_diagnostic_prospective as pr  # type: ignore[no-redef]
    import run_legal_agent as rla  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "diagnostic_legal_agent_omp"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
CONFIG_PATH = DATA_DIR / "omp_config_v1.json"
SMOKE_PATH = DATA_DIR / "smoke_questions_v1.json"
MANIFEST_PATH = DATA_DIR / "manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
WORK_ROOT = ROOT / "all_res" / "diagnostic_legal_agent_omp"
OUTPUT_ROOT = WORK_ROOT / "run"
SMOKE_ROOT = WORK_ROOT / "smoke"
PROTOCOL_ID = "vmlu-diagnostic-legal-agent-omp"
PHASE = "legal-agent-omp"
ARM = "OMPF"
ARMS = (ARM,)
INSTRUCTION_ARM = "DSHF"  # MC-112's instruction, byte for byte
PROFILE_ID = "qwen3-5-9b-65k-omp"
CARD_ID = "MC-113"
HOME = rla.HOME
WORKDIR = rla.WORKDIR
AGENT_DIR = f"{HOME}/.omp/agent"
REUSED_KEYS = ("agent_prompts_sha256", "provisions_sha256", "added_documents_sha256", "offsite_documents_sha256",
               "mc101_sources_sha256", "mc101_corpus_sha256", "oracle_evidence_sha256", "folder_sha256",
               "mc111_scores_sha256")
HASH_KEYS = ("legal_agent_omp_protocol_sha256", "omp_config_sha256", "omp_binary_sha256", *REUSED_KEYS,
             "mc112_manifest_file_sha256", "mc112_scores_sha256")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


# ---------------------------------------------------------------- protocol and configuration

def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported legal-agent-omp protocol id or version")
    if tuple(protocol.get("arms") or ()) != ARMS or protocol.get("draws") != 2:
        raise _fail(f"the legal-agent-omp protocol must run {ARMS} with two draws")
    if protocol.get("instruction_arm") != INSTRUCTION_ARM:
        raise _fail(f"the task must be MC-112's {INSTRUCTION_ARM} task")
    return protocol


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if set(config) != {"version", "config.yml", "models.yml"}:
        raise _fail("omp_config_v1.json must hold version, config.yml and models.yml")
    return config


@dataclass(frozen=True)
class Harness:
    """The pinned omp binary, its registered configuration, its argument list and the bwrap binary."""
    binary: Path
    config: dict[str, Any]
    argv: tuple[str, ...]
    bwrap: str = "/usr/bin/bwrap"
    python: str = "/usr/bin/python3"


def omp_version(binary: Path) -> str | None:
    """`omp --version`, run with an empty temporary home (it writes nothing there)."""
    with tempfile.TemporaryDirectory(prefix="omp-version-") as home:
        try:
            return subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=60,  # nosec B603
                                  check=False, cwd=home, env={"HOME": home, "PATH": "/usr/bin:/bin"}).stdout.strip()
        except OSError:
            return None


def check_harness(protocol: dict[str, Any]) -> tuple[Harness, list[str]]:
    """The pinned harness, and what differs from the protocol: binary hash, version, configuration hash, bwrap."""
    spec = protocol["harness"]
    binary = rla.expand(spec["binary"])
    problems = []
    if not binary.is_file() or v1.sha256_file(binary) != spec["binary_sha256"]:
        problems.append(f"omp binary {binary} differs from {spec['binary_sha256'][:12]}")
    elif (version := omp_version(binary)) != spec["version"]:
        problems.append(f"omp version {version} is not {spec['version']}")
    config_path = ROOT / spec["config"]
    if v1.sha256_file(config_path) != spec["config_sha256"]:
        problems.append(f"{spec['config']} differs from {spec['config_sha256'][:12]}")
    if not shutil.which("bwrap"):
        problems.append("bwrap is not installed")
    return Harness(binary=binary, config=load_config(config_path), argv=tuple(spec["argv"])), problems


# ---------------------------------------------------------------- the sandbox

def sandbox_command(harness: Harness, docs: Path, home: Path, socket_dir: Path, task: str) -> list[str]:
    """The bwrap argument list of one attempt: MC-112's sandbox with the omp binary in place of node and dsh."""
    args = [harness.bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/sbin", "/sbin",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/work", "--tmpfs", "/run"]  # nosec B108 - fresh tmpfs mounts inside the sandbox, not the host /tmp
    for name in rla._SYSTEM_ETC:  # noqa: SLF001 - MC-112's list, reused unchanged
        if Path("/etc", name).exists():
            args += ["--ro-bind", f"/etc/{name}", f"/etc/{name}"]
    args += ["--ro-bind", str(harness.binary), "/opt/omp", "--ro-bind", str(rla.RELAY), "/opt/relay/dsh_relay.py",
             "--bind", str(socket_dir), "/run/proxy", "--bind", str(home), HOME, "--ro-bind", str(docs), WORKDIR,
             "--chdir", WORKDIR]
    env = {"PATH": "/usr/bin:/bin", "HOME": HOME, "PI_CODING_AGENT_DIR": AGENT_DIR, "IEC_API_KEY": px.DUMMY_KEY,
           "LANG": "C.UTF-8", "TMPDIR": "/tmp"}  # nosec B108 - the sandbox's own tmpfs
    for key, value in env.items():
        args += ["--setenv", key, value]
    script = (f'{harness.python} -I /opt/relay/dsh_relay.py {rla.RELAY_PORT} /run/proxy/proxy.sock /run/relay.ready & '
              'n=0; while [ ! -e /run/relay.ready ]; do n=$((n+1)); [ $n -gt 200 ] && exit 97; sleep 0.05; done; '
              'exec /opt/omp "$@"')
    return [*args, "/bin/sh", "-c", script, "omp-attempt", *harness.argv, task]


def prepare_home(home: Path, config: dict[str, Any]) -> None:
    """A fresh HOME holding only omp's agent directory with the registered config.yml and models.yml."""
    agent = home / ".omp" / "agent"
    agent.mkdir(parents=True)
    for name in ("config.yml", "models.yml"):
        (agent / name).write_text(json.dumps(config[name], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class ShapeRules:
    """omp's registered request shape (design §5). Every request: keys within the registered set, and an answer cap
    of at most `max_completion_tokens`, exactly that when the request offers tools. omp's compaction requests fit
    this (offline: the handoff request adds `tool_choice: none` and keeps the cap; the short-summary fallback has no
    tools and a cap of 512). `system_sha256` and `task` apply to an attempt's first request; None skips that check
    (the smoke test, which records the hash instead)."""
    body_keys: frozenset[str]
    max_completion_tokens: int
    system_sha256: str | None = None
    task: str | None = None

    def problem(self, n: int, body: dict[str, Any]) -> str | None:
        extra = sorted(set(body) - self.body_keys)
        if extra:
            return f"body keys outside the registered set: {extra}"
        cap = body.get("max_completion_tokens")
        if not isinstance(cap, int) or cap > self.max_completion_tokens or (
                "tools" in body and cap != self.max_completion_tokens):
            return f"max_completion_tokens {cap!r}"
        if n != 1:
            return None
        messages = body.get("messages") or []
        if self.system_sha256 is not None and system_sha256(messages) != self.system_sha256:
            return f"system prompt sha256 {system_sha256(messages)} is not the registered one"
        if self.task is not None and last_user_text(messages) != self.task:
            return "the task differs from the manifest task"
        return None


def _text(content: Any) -> str:
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content or "")


def system_sha256(messages: list[dict[str, Any]]) -> str | None:
    first = messages[0] if messages else {}
    return v1.sha256_bytes(_text(first.get("content")).encode("utf-8")) if first.get("role") == "system" else None


def last_user_text(messages: list[dict[str, Any]]) -> str | None:
    """The last text part of the last user message: where omp puts the task, after its date reminder."""
    user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
    if user is None:
        return None
    content = user.get("content")
    if isinstance(content, list):
        texts = [part.get("text") for part in content if isinstance(part, dict) and part.get("type") == "text"]
        return texts[-1] if texts else None
    return str(content)


AFTER_FAILURE = "refused_after_failure"


class OmpProxy(px.AttemptProxy):
    """MC-112's proxy, unchanged, plus two things for omp:

    * the request-shape checks of design §5: a failed check is refused before anything is forwarded, as
      `refused_body` (a fatal outcome);
    * no request after a technical failure. omp 18.0.0 retries a 5xx or a dropped connection by itself even with
      `retry.enabled: false` (seen offline: four retries of a 503). Once a request of the attempt has failed
      technically, every later request is refused with 503 (`refused_after_failure`), so the attempt ends as a
      technical failure that `--resume` re-runs from scratch, as dsh's attempts did in MC-112.
    """

    def __init__(self, config: px.ProxyConfig, rules: ShapeRules, socket_path: Path, log_path: Path):
        super().__init__(config, socket_path, log_path)
        self.rules = rules
        self._active = 0
        self._idle = threading.Condition()

    def _failed(self) -> bool:
        with self._idle:  # a request still in progress records its outcome first
            self._idle.wait_for(lambda: self._active == 0, timeout=10)
        with self._lock:
            return any(record.get("outcome") in px.TECHNICAL for record in self.records)

    def _forward(self, handler: Any, n: int, received: str, sent: dict[str, Any]) -> None:
        if self._failed():
            return self.refuse(handler, AFTER_FAILURE, 503, "an earlier request of this attempt failed", n, received)
        problem = self.rules.problem(n, json.loads(received))
        if problem:
            return self.refuse(handler, "refused_body", 400, problem, n, received)
        with self._idle:
            self._active += 1
        try:
            return super()._forward(handler, n, received, sent)
        finally:
            with self._idle:
                self._active -= 1
                self._idle.notify_all()


def run_sandboxed(harness: Harness, docs: Path, attempt_dir: Path, task: str, config: px.ProxyConfig,
                  rules: ShapeRules, wall_clock: float) -> dict[str, Any]:
    """Run one omp attempt and return what happened: omp's exit, its events, the proxy's records."""
    attempt_dir.mkdir(parents=True, exist_ok=False)
    home = attempt_dir / "home"
    prepare_home(home, harness.config)
    socket_dir = Path(tempfile.mkdtemp(prefix="ompp-"))  # short path: a Unix socket path holds 107 bytes at most
    events_path, stderr_path = attempt_dir / "events.jsonl", attempt_dir / "stderr.txt"
    start = time.monotonic()
    exit_code: int | None = None
    timed_out = False
    try:
        with OmpProxy(config, rules, socket_dir / "proxy.sock", attempt_dir / "proxy_log.jsonl") as proxy:
            with events_path.open("wb") as out, stderr_path.open("wb") as err:
                process = subprocess.Popen(  # nosec B603 - fixed bwrap argument list, no shell on the host
                    sandbox_command(harness, docs, home, socket_dir, task), stdout=out, stderr=err,
                    stdin=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin"}, start_new_session=True)
                try:
                    exit_code = process.wait(timeout=wall_clock)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(process.pid, 9)
                    process.wait()
        records = list(proxy.records)  # after the proxy stopped: every request in progress is recorded
    finally:
        shutil.rmtree(socket_dir, ignore_errors=True)
        shutil.rmtree(home / ".omp" / "natives", ignore_errors=True)  # unpacked from the pinned binary each time
    events = []
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "unparsed_line", "text": line[:500]})
    return {"exit_code": exit_code, "timed_out": timed_out, "wall_s": round(time.monotonic() - start, 3),
            "events": events, "records": records}


# ---------------------------------------------------------------- one attempt's status

def final_assistant(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """omp's last assistant message: from `agent_end` when omp emitted it, else from the last `message_end`."""
    for event in reversed(events):
        if event.get("type") == "agent_end":
            messages = [m for m in event.get("messages") or [] if isinstance(m, dict) and m.get("role") == "assistant"]
            return messages[-1] if messages else None
    for event in reversed(events):
        message = event.get("message")
        if event.get("type") == "message_end" and isinstance(message, dict) and message.get("role") == "assistant":
            return message
    return None


def answer_text(message: dict[str, Any] | None) -> str:
    if not message:
        return ""
    content = message.get("content")
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
    return str(content or "")


def classify(result: dict[str, Any]) -> dict[str, Any]:
    """Status, outcome and answer of one finished sandbox run (design §7)."""
    seen = px.attempt_outcome(result["records"])
    message = final_assistant(result["events"])
    stop = (message or {}).get("stopReason")
    text = answer_text(message)
    out: dict[str, Any] = {"proxy": seen, "final_reason": stop, "raw_response": "", "fatal": False, "error_type": None}
    if seen["fatal"]:
        return {**out, "status": "request_error", "outcome": "fatal", "error_type": seen["fatal"][0], "fatal": True}
    if result["exit_code"] == 0 and stop == "stop" and text.strip():
        return {**out, "status": "complete", "outcome": "complete", "raw_response": text}
    if result["timed_out"] or stop == "aborted":
        return {**out, "status": "request_error", "outcome": "technical", "error_type": "wall_clock"}
    if seen["technical"]:
        return {**out, "status": "request_error", "outcome": "technical", "error_type": rla._network_type(result["records"])}  # noqa: SLF001
    if seen["requests"] == 0:
        return {**out, "status": "request_error", "outcome": "fatal", "error_type": "sandbox_start", "fatal": True}
    for flag in ("request_cap", "upstream_4xx"):
        if seen[flag]:
            return {**out, "status": "complete", "outcome": flag}
    if stop == "length" or seen["last_finish_reason"] == "length":
        return {**out, "status": "complete", "outcome": "answer_cap"}
    return {**out, "status": "complete", "outcome": "harness_end"}


# ---------------------------------------------------------------- manifest

def mc112_inputs(protocol: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """MC-112's registration and frozen manifest, each checked against what this protocol registers."""
    spec = protocol["mc112"]
    manifest_path = ROOT / spec["manifest"]
    if v1.sha256_file(manifest_path) != spec["manifest_file_sha256"]:
        raise _fail(f"MC-112's manifest {manifest_path} differs from its registered SHA-256")
    scores = ROOT / spec["scores"]
    if not scores.is_file() or v1.sha256_file(scores) != spec["scores_sha256"]:
        raise _fail(f"MC-112's score file {scores} is missing or differs from its registered SHA-256")
    registration = json.loads((ROOT / spec["registration"]).read_text(encoding="utf-8"))
    return registration, json.loads(manifest_path.read_text(encoding="utf-8"))


def build_manifest(protocol: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed. Item-major: OMPF-r1 then OMPF-r2 for each item. Each task is
    MC-112's DSHF task for the item, and its SHA-256 must equal the one in MC-112's manifest."""
    protocol = protocol or load_protocol()
    mc112_registration, mc112_manifest = mc112_inputs(protocol)
    mc112_protocol = la.load_protocol()
    prompts = la.load_prompts()
    pool = lr.pool_ids(lr.load_protocol())
    if len(pool) != protocol["pool_size"] or pool != mc112_manifest["pool"]:
        raise _fail("the pool differs from MC-112's")
    dshf = {ref["item_id"]: ref["prompt_sha256"] for ref in mc112_manifest["items"]
            if ref["replicate_id"] == f"{INSTRUCTION_ARM}-r1"}
    frozen = lo.legal_items()
    provisions = la.load_provisions()
    items: list[v1.EvalItem] = []
    for item_id in pool:
        base = frozen[item_id]
        task = la.arm_task(base.prompt, INSTRUCTION_ARM, prompts)
        if v1.sha256_bytes(task.encode("utf-8")) != dshf.get(item_id):
            raise _fail(f"{item_id}: the task differs from MC-112's {INSTRUCTION_ARM} task")
        for draw in range(1, protocol["draws"] + 1):
            items.append(dataclasses.replace(base, replicate_id=f"{ARM}-r{draw}", prompt=task))
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate legal-agent-omp run keys")
    reused = {
        "agent_prompts_sha256": v1.sha256_file(la.PROMPTS_PATH), "provisions_sha256": v1.sha256_file(la.PROVISIONS_PATH),
        "added_documents_sha256": v1.sha256_file(la.ADDED_PATH), "offsite_documents_sha256": v1.sha256_file(la.OFFSITE_PATH),
        "mc101_sources_sha256": la.MC101_SOURCES_SHA256, "mc101_corpus_sha256": la.MC101_CORPUS_SHA256,
        "oracle_evidence_sha256": v1.sha256_file(lo.EVIDENCE_PATH),
        "folder_sha256": mc112_protocol["corpus"]["folder_sha256"],
        "mc111_scores_sha256": mc112_protocol["reference"]["scores_sha256"],
    }
    differing = [key for key in REUSED_KEYS if reused[key] != mc112_registration["frozen"].get(key)]
    if differing or protocol["corpus"] != mc112_protocol["corpus"] or protocol["reference"]["scores_sha256"] != \
            mc112_protocol["reference"]["scores_sha256"]:
        raise _fail(f"inputs reused from MC-112 differ from its registration: {differing or 'corpus or reference'}")
    hashes = {
        "legal_agent_omp_protocol_sha256": v1.sha256_file(PROTOCOL_PATH),
        "omp_config_sha256": v1.sha256_file(ROOT / protocol["harness"]["config"]),
        "omp_binary_sha256": protocol["harness"]["binary_sha256"], **reused,
        "mc112_manifest_file_sha256": protocol["mc112"]["manifest_file_sha256"],
        "mc112_scores_sha256": protocol["mc112"]["scores_sha256"],
    }
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, **hashes,
        "pool": pool, "support": {item_id: provisions[item_id]["support"] for item_id in pool},
        "n": len(items), "item_count": len(pool), "dataset_counts": {lo.DATASET: len(pool)},
        "arm_counts": {ARM: len(items)}, "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the engine's request function

def rules_for(protocol: dict[str, Any], task: str | None) -> ShapeRules:
    spec = protocol["harness"]
    return ShapeRules(body_keys=frozenset(spec["body_keys"]), max_completion_tokens=spec["max_completion_tokens"],
                      system_sha256=protocol["proxy"]["system_prompt_sha256"], task=task)


@dataclass
class AttemptContext:
    """Everything an attempt needs besides its item: passed to the engine as its `client`."""
    harness: Harness
    docs: Path
    output: Path
    proxy: px.ProxyConfig
    protocol: dict[str, Any]
    wall_clock: float


def make_request(protocol: dict[str, Any], guard: pr.BudgetGuard, outage: pr.OutageGuard, max_in_flight: int):
    gate = threading.BoundedSemaphore(max_in_flight)
    halt = threading.Event()
    harness_spec = protocol["harness"]

    def request(context: AttemptContext, item: v1.EvalItem, shard: int, lane: int) -> dict[str, Any]:
        row: dict[str, Any] = {
            "run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
            "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
            "phase": PHASE, "profile_id": PROFILE_ID, "protocol_id": PROTOCOL_ID, "measurement_card_id": CARD_ID,
            "model_id": context.proxy.model, "transport": "omp-json", "api_protocol": harness_spec["api_protocol"],
            "shard": shard, "lane": lane, "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")),
            "raw_prompt": item.prompt, "raw_response": "", "temperature_sent": context.proxy.temperature,
            "reasoning_effort_sent": None, "seed_sent": None, "max_tokens": harness_spec["max_completion_tokens"],
        }
        with gate:  # waiting here is not part of the measured time
            row["started_at"] = pr.base.now()
            for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                        (halt.is_set(), "halted_before_send")):
                if blocked:
                    halt.set()
                    return {**row, "status": "request_error", "finish_reason": "error", "error_type": error_type,
                            "fatal": True, "latency_s": 0.0, "finished_at": pr.base.now()}
            base_dir = context.output / "attempts" / rla.safe_key(item.run_key)
            tries = len(list(base_dir.glob("try-*"))) if base_dir.is_dir() else 0
            attempt_dir = base_dir / f"try-{tries + 1}"
            result = run_sandboxed(context.harness, context.docs, attempt_dir, item.prompt, context.proxy,
                                   rules_for(context.protocol, item.prompt), context.wall_clock)
        verdict = classify(result)
        seen = verdict.pop("proxy")
        models = seen["response_models"]
        row.update({
            "status": verdict["status"], "outcome": verdict["outcome"], "raw_response": verdict["raw_response"],
            "error_type": verdict["error_type"], "fatal": verdict["fatal"], "final_reason": verdict["final_reason"],
            "finish_reason": "stop" if verdict["outcome"] == "complete" else verdict["outcome"],
            "attempt_dir": str(attempt_dir.relative_to(context.output)), "omp_exit": result["exit_code"],
            "latency_s": result["wall_s"], "finished_at": pr.base.now(), "requests": seen["requests"],
            "requests_forwarded": seen["forwarded"], "proxy_outcomes": seen["outcomes"],
            "tool_calls": rla.tool_counts(result["records"]),
            "prompt_tokens": seen["prompt_tokens"], "completion_tokens": seen["completion_tokens"],
            "total_tokens": seen["total_tokens"], "response_model_id": models[0] if len(models) == 1 else models or None,
        })
        if row["status"] == "complete":
            guard.add(dp.reported_tokens(row))
        elif not row["fatal"]:
            row["retry_wait_seconds"] = 30 if row["error_type"] == "upstream_5xx" else 5
        outage.record(row)
        if row["fatal"]:
            halt.set()
        return row

    return request


# ---------------------------------------------------------------- registration, condition and scoring

def load_registration(path: Path = REGISTRATION_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def evaluate_gates(protocol: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                   env: dict[str, str | None], problems: list[str]) -> list[pr.Gate]:
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8")
    card_id = (registration.get("card_ids") or {}).get(PHASE)
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    card_file = (registration.get("card_files") or {}).get(PHASE)
    frozen = registration.get("frozen") or {}
    differing = [name for name in (*HASH_KEYS, "manifest_sha256") if frozen.get(name) != manifest.get(name)]
    campaign = dp.load_protocol()["model"]
    endpoint = urlsplit(env.get("OPENAI_BASE_URL") or "")
    identity = (endpoint.hostname == campaign["endpoint_host"]
                and endpoint.path.rstrip("/") == campaign["endpoint_path"].rstrip("/")
                and env.get("OPENAI_MODEL") == campaign["requested_id"] and bool(env.get("OPENAI_API_KEY")))
    proxy = protocol["proxy"]
    return [
        pr.Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md"),
        pr.Gate("detail_card", bool(card_file) and (ROOT / str(card_file)).is_file(), str(card_file or "none")),
        pr.Gate("frozen_hashes", bool(frozen) and not differing, "all match" if frozen and not differing
                else f"differ: {differing}"),
        pr.Gate("endpoint_identity", identity, f"model={env.get('OPENAI_MODEL')} (expects {campaign['requested_id']})"),
        pr.Gate("budget_set", isinstance(protocol["operational"].get("budget_tokens"), int),
                "budget_tokens is set from the smoke test"),
        pr.Gate("response_model_set", bool(proxy.get("expected_response_model")),
                "expected_response_model is set from the smoke test"),
        pr.Gate("system_prompt_set", bool(proxy.get("system_prompt_sha256")),
                "system_prompt_sha256 is set from the smoke test"),
        pr.Gate("harness_and_folder", not problems, "; ".join(problems) or "pins, folder and provisions match"),
    ]


def build_condition(protocol: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    endpoint: str) -> dict[str, Any]:
    harness, proxy = protocol["harness"], protocol["proxy"]
    module = Path(__file__).resolve().parent
    return {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE,
        "measurement_card_id": registration["card_ids"][PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][PHASE]),
        **{name: manifest[name] for name in (*HASH_KEYS, "manifest_sha256")},
        "arm_counts": manifest["arm_counts"], "dataset_counts": manifest["dataset_counts"],
        "operational": protocol["operational"], "model_id": dp.load_protocol()["model"]["requested_id"],
        "expected_response_model": proxy["expected_response_model"],
        "system_prompt_sha256": proxy["system_prompt_sha256"], "profile_id": PROFILE_ID, "transport": "omp-json",
        "harness": {key: harness[key] for key in ("name", "version", "binary_sha256", "config_sha256", "argv",
                                                  "tools", "body_keys")},
        "api_protocol": harness["api_protocol"], "endpoint_host": urlsplit(endpoint).hostname,
        "base_url_sha256": v1.sha256_bytes(endpoint.encode()), "temperature_requested": proxy["temperature"],
        "temperature_effective": None, "reasoning_effort_sent": None, "seed_sent": None,
        "max_completion_tokens": harness["max_completion_tokens"], "context_window": harness["context_window"],
        "request_timeout_seconds": proxy["request_timeout_seconds"], "request_cap": proxy["request_cap"],
        "wall_clock_seconds": proxy["wall_clock_seconds"], "workdir": protocol["corpus"]["workdir"],
        "scorer_sha256": v1.sha256_file(module / "score_vi_multimodel.py"),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)), "engine_sha256": v1.sha256_file(Path(pr.__file__)),
        "legal_agent_module_sha256": v1.sha256_file(Path(la.__file__)),
        "trajectory_sha256": v1.sha256_file(Path(str(ot.__file__))), "proxy_sha256": v1.sha256_file(Path(px.__file__)),
        "relay_sha256": v1.sha256_file(rla.RELAY), "mc112_runner_sha256": v1.sha256_file(Path(rla.__file__)),
        "runner_sha256": v1.sha256_file(Path(__file__)),
    }


def score_callback(card_id: str):
    def score(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        scored, summaries = dp.score_arm_rows(manifest, rows, rebuilt)
        for by_dataset in summaries.values():
            for summary in by_dataset.values():
                if summary["status"] != "complete":
                    for key in pr.HEADLINE_KEYS:
                        summary.pop(key, None)
        for row in scored:
            source = rows.get(dp.run_key(row)) or {}
            row.update({key: source.get(key) for key in ("outcome", "attempt_dir", "requests",
                                                   "requests_forwarded", "tool_calls")})
        v1.write_jsonl_atomic(output / "scores.jsonl", scored)
        outcomes = Counter((str(row.get("arm")), str(row.get("outcome"))) for row in rows.values())
        pr.base.atomic_json(output / "summary.json", {
            "protocol_id": PROTOCOL_ID, "phase": PHASE, "measurement_card_id": card_id,
            "model_id": pr.base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": pr.base.now(),
            "expected_n": len(manifest["items"]),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "outcomes": {f"{arm}:{outcome}": count for (arm, outcome), count in sorted(outcomes.items())},
            "cost_usd": None, "cost_basis": "IEC tariff not supplied; reported usage retained per attempt",
        })
    return score


# ---------------------------------------------------------------- self-test and smoke test

class ScriptedUpstream(fu.FakeUpstream):
    """MC-112's scripted server with three more step keys: `finish` (the finish reason of a text step), `prompt_tokens`
    (the reported prompt usage) and `sleep` (seconds before the response)."""

    def events(self, step: dict[str, Any], index: int) -> list[str]:
        if step.get("sleep"):
            time.sleep(float(step["sleep"]))
        out = []
        for line in super().events(step, index):
            if line == "[DONE]":
                out.append(line)
                continue
            chunk = json.loads(line)
            for choice in chunk.get("choices") or []:
                if choice.get("finish_reason") and step.get("finish"):
                    choice["finish_reason"] = step["finish"]
            usage = chunk.get("usage")
            if isinstance(usage, dict) and step.get("prompt_tokens"):
                usage["prompt_tokens"] = int(step["prompt_tokens"])
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
            out.append(json.dumps(chunk, ensure_ascii=False))
        return out


def load_smoke() -> dict[str, Any]:
    smoke = json.loads(SMOKE_PATH.read_text(encoding="utf-8"))
    base_path = ROOT / smoke["base"]
    if v1.sha256_file(base_path) != smoke["base_sha256"]:
        raise _fail(f"{smoke['base']} differs from the SHA-256 the omp smoke file registers")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    by_id = {question["id"]: question for question in base["questions"]}
    questions = [{**by_id[qid], "instruction": smoke["instruction_arm"]} for qid in smoke["questions"]]
    questions.append({**smoke["cap_check"], "instruction": None})
    return {"synthetic_folder": base["synthetic_folder"], "questions": questions}


SELFTEST_FILE = "quy-che-clb-co-tuong-hoa-binh.txt"


def selftest_cases() -> list[tuple[str, list[dict[str, Any]], int, dict[str, Any], tuple[str, str]]]:
    """(label, script, request cap, rule overrides, expected (status, outcome)) of the offline self-test."""
    read = {"tool": "read", "arguments": {"i": "Reading the rules", "path": SELFTEST_FILE}}
    grep = {"tool": "grep", "arguments": {"i": "Finding the fee", "pattern": "hội phí"}}
    return [
        ("answer", [grep, read, {"text": "Đáp án: B"}], 30, {}, ("complete", "complete")),
        ("cap", [{"tool": "glob", "arguments": {"i": "Listing files", "path": "*.txt"}}] * 3, 2, {},
         ("complete", "request_cap")),
        ("gateway", [{"status": 503}, {"text": "Đáp án: B"}], 30, {}, ("request_error", "technical")),
        ("client_error", [{"status": 400}], 30, {}, ("complete", "upstream_4xx")),
        ("length", [{"text": "Đáp án: " + "x" * 40, "finish": "length"}], 30, {}, ("complete", "answer_cap")),
        ("shape", [{"text": "Đáp án: B"}], 30, {"system_sha256": "0" * 64}, ("request_error", "fatal")),
    ]


def selftest(protocol: dict[str, Any], harness: Harness) -> bool:
    """omp end to end against the scripted server, offline (no model, no network)."""
    smoke = load_smoke()
    task = la.arm_task(smoke["questions"][0]["prompt"], INSTRUCTION_ARM, la.load_prompts())
    provision = {"file": SELFTEST_FILE, "anchor_line": "Điều 2. Hội viên"}
    ok = True
    with tempfile.TemporaryDirectory(prefix="mc113-selftest-") as tmp:
        docs = Path(tmp) / "docs"
        docs.mkdir()
        for name, text in smoke["synthetic_folder"].items():
            (docs / name).write_text(text, encoding="utf-8")
        for label, script, cap, overrides, expected in selftest_cases():
            with ScriptedUpstream(script) as upstream:
                config = px.ProxyConfig(upstream=upstream.url, api_key="selftest-key", model="Qwen3.5-9B-65K",
                                        expected_response_model="fake-model.gguf", request_cap=cap,
                                        extra_headers=dict(dp.load_protocol()["transport"]["gateway_header"]))
                rules = dataclasses.replace(rules_for(protocol, task), **overrides)
                if rules.system_sha256 is None and not overrides:
                    rules = dataclasses.replace(rules, system_sha256=protocol["harness"]["probe_system_prompt_sha256"])
                result = run_sandboxed(harness, docs, Path(tmp) / label, task, config, rules, 300)
                sent = list(upstream.requests)
            verdict = classify(result)
            hits = la.provision_hits(ot.omp_observations(result["records"]), [provision])[0]
            temps = {body.get("temperature") for body in sent}
            good = ((verdict["status"], verdict["outcome"]) == expected and temps <= {protocol["proxy"]["temperature"]}
                    and (label != "answer" or (verdict["raw_response"] == "Đáp án: B" and all(hits.values())))
                    and (label != "gateway" or [r.get("outcome") for r in result["records"]][:2]
                         == ["upstream_5xx", AFTER_FAILURE]))
            ok &= good
            print(f"selftest {label}: status={verdict['status']} outcome={verdict['outcome']} "
                  f"requests={len(result['records'])} temperatures={sorted(temps, key=str)} hits={hits} "
                  f"{'PASS' if good else 'FAIL'}", flush=True)
    return ok


def smoke_test(protocol: dict[str, Any], harness: Harness, docs: Path, endpoint: str, key: str) -> Path:
    """Design §10: smoke-1 to smoke-3 with the OMPF instruction and smoke-4 (the answer cap), once each through the
    full path. No score is computed; the system-prompt hash is recorded, not checked."""
    smoke = load_smoke()
    out = SMOKE_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True)
    synthetic = out / "synthetic_docs"
    synthetic.mkdir()
    for name, text in smoke["synthetic_folder"].items():
        (synthetic / name).write_text(text, encoding="utf-8")
    campaign = dp.load_protocol()
    config = px.ProxyConfig(upstream=endpoint, api_key=key, model=campaign["model"]["requested_id"],
                            expected_response_model=None, temperature=protocol["proxy"]["temperature"],
                            extra_headers=dict(campaign["transport"]["gateway_header"]),
                            request_timeout=protocol["proxy"]["request_timeout_seconds"],
                            request_cap=protocol["proxy"]["request_cap"])
    prompts = la.load_prompts()
    report = []
    for question in smoke["questions"]:
        folder = synthetic if question["folder"] == "synthetic" else docs
        task = la.arm_task(question["prompt"], question["instruction"], prompts) if question["instruction"] \
            else question["prompt"]
        rules = dataclasses.replace(rules_for(protocol, task), system_sha256=None)
        result = run_sandboxed(harness, folder, out / question["id"], task, config, rules,
                               protocol["proxy"]["wall_clock_seconds"])
        verdict = classify(result)
        observations = ot.omp_observations(result["records"])
        seen = px.attempt_outcome(result["records"])
        received = [json.loads(r["body_received"]) for r in result["records"] if r.get("body_received")]
        sent = [json.loads(r["body_sent"]) for r in result["records"] if r.get("body_sent")]
        responses = [r.get("response") or {} for r in result["records"]]
        report.append({
            "id": question["id"], "instruction": question["instruction"], "status": verdict["status"],
            "outcome": verdict["outcome"], "error_type": verdict["error_type"], "final_text": verdict["raw_response"],
            "final_reason": verdict["final_reason"], "wall_s": result["wall_s"], "requests": seen["requests"],
            "proxy_outcomes": seen["outcomes"], "tool_calls": rla.tool_counts(result["records"]),
            "observations": [{key: o[key] for key in ("tool", "arguments", "status", "read_file", "chars", "source")}
                             for o in observations],
            "system_prompt_sha256": sorted({str(system_sha256(body.get("messages") or [])) for body in received[:1]}),
            "task_arrived_unchanged": bool(received) and last_user_text(received[0].get("messages") or []) == task,
            "temperatures_sent": sorted({body.get("temperature") for body in sent}),
            "fields_received": sorted({key for body in received for key in body}),
            "reasoning_chars": sum(len(r.get("reasoning") or "") for r in responses),
            "finish_reasons": [r.get("finish_reason") for r in responses],
            "completion_tokens_per_request": [(r.get("usage") or {}).get("completion_tokens") for r in responses],
            "response_models": seen["response_models"], "prompt_tokens": seen["prompt_tokens"],
            "completion_tokens": seen["completion_tokens"], "total_tokens": seen["total_tokens"],
            "latency_per_request_s": [r.get("latency_s") for r in result["records"]],
        })
    (out / "smoke_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    from dotenv import dotenv_values

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="re-run only attempts with technical failures")
    ap.add_argument("--selftest", action="store_true", help="omp end to end against a scripted server (offline)")
    ap.add_argument("--smoke", action="store_true", help="with --execute: the smoke test of design §10")
    ap.add_argument("--freeze-manifest", action="store_true", help="write manifest_v1.json from the current inputs")
    ap.add_argument("--no-rebuild", action="store_true", help="preflight only: skip the fresh folder rebuild")
    ap.add_argument("--tunnel-dns", default=None, help="in-tunnel DNS server for the endpoint host (this process only)")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    if args.no_rebuild and args.execute and not args.smoke:
        ap.error("--no-rebuild is for the preflight and the smoke test only")
    protocol = load_protocol()
    harness, problems = check_harness(protocol)
    if args.selftest:
        if problems:
            raise SystemExit("Error: " + "; ".join(problems))
        return 0 if selftest(protocol, harness) else 1
    manifest, rebuilt = build_manifest(protocol)
    if args.freeze_manifest:
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"manifest -> {MANIFEST_PATH} manifest_sha256={manifest['manifest_sha256']} "
              f"file_sha256={v1.sha256_file(MANIFEST_PATH)}")
        return 0
    docs, folder_problems = rla.check_folder(protocol, rebuild=not args.no_rebuild)
    problems += folder_problems
    if MANIFEST_PATH.is_file() and load_frozen_manifest() != manifest:
        problems.append("the rebuilt manifest differs from manifest_v1.json")
    elif not MANIFEST_PATH.is_file():
        problems.append("manifest_v1.json is not frozen yet")
    dp.verify_manifest_rows(manifest, rebuilt)
    env = dotenv_values(ROOT / ".env")
    registration = load_registration()
    gates = evaluate_gates(protocol, manifest, registration, env, problems)
    print(f"phase={PHASE} protocol={PROTOCOL_ID} items={manifest['item_count']} attempts={manifest['n']} "
          f"arms={manifest['arm_counts']} manifest_sha256={manifest['manifest_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    if not args.execute:
        print(f"preflight done items={manifest['item_count']} attempts={manifest['n']} endpoint_calls=0", flush=True)
        return 0
    endpoint, key = str(env.get("OPENAI_BASE_URL") or ""), str(env.get("OPENAI_API_KEY") or "")
    if args.tunnel_dns:
        address = pr.install_resolver_shim(urlsplit(endpoint).hostname or "", args.tunnel_dns)
        print(f"resolver shim (this process only): {urlsplit(endpoint).hostname} -> {address} via {args.tunnel_dns}")
    if args.smoke:
        identity = next(gate for gate in gates if gate.name == "endpoint_identity")
        if problems or not identity.ok:
            raise SystemExit("Error: the smoke test needs the pinned harness, the folder and the campaign endpoint")
        out = smoke_test(protocol, harness, docs, endpoint, key)
        print(f"smoke test -> {out / 'smoke_report.json'}")
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise SystemExit("Error: execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    campaign = dp.load_protocol()
    operational, proxy_spec = protocol["operational"], protocol["proxy"]
    output = OUTPUT_ROOT / PROFILE_ID
    resume = bool(args.resume) and (output / "condition.json").is_file()
    condition = pr.reconcile_resume(output, build_condition(protocol, manifest, registration, endpoint), resume)
    guard = pr.BudgetGuard(operational["budget_tokens"], pr.existing_usage(output))
    outage = pr.OutageGuard(operational["stop_after_timeouts"])
    transport = campaign["transport"]
    if (pr.base.SHARDS, pr.base.LANES) != (transport["shards"], transport["lanes"]):
        raise SystemExit("Error: engine shard/lane constants differ from the campaign protocol")
    pr.base.MODEL, pr.base.PROFILE, pr.base.PROTOCOL, pr.base.CARD_ID = (
        campaign["model"]["requested_id"], PROFILE_ID, PROTOCOL_ID, CARD_ID)
    pr.base.request = make_request(protocol, guard, outage, operational["max_in_flight"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": pr.base.now(), "resume": resume, "runner_sha256": v1.sha256_file(Path(__file__)),
                                 "operational": operational, "note": args.note}, ensure_ascii=False) + "\n")
    context = AttemptContext(
        harness=harness, docs=docs, output=output, protocol=protocol, wall_clock=proxy_spec["wall_clock_seconds"],
        proxy=px.ProxyConfig(upstream=endpoint, api_key=key, model=campaign["model"]["requested_id"],
                             expected_response_model=proxy_spec["expected_response_model"],
                             temperature=proxy_spec["temperature"],
                             extra_headers=dict(transport["gateway_header"]),
                             request_timeout=proxy_spec["request_timeout_seconds"],
                             request_cap=proxy_spec["request_cap"]))
    items = dp.verify_manifest_rows(manifest, rebuilt)
    pr.base.execute(output, manifest, rebuilt, items, condition, context, resume,  # pyright: ignore[reportArgumentType]
                    score_callback=score_callback(CARD_ID), runner_path=Path(__file__))
    status = json.loads((output / "run.json").read_text(encoding="utf-8"))["status"]
    print(f"status={status} output={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
