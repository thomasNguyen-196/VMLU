"""Run MC-112: Qwen3.5-9B in DeepSeek Harness over the legal corpus folder (openspec change diagnostic-legal-agent).

From the repo root:
  .venv/bin/python -m code_benchmark.run_legal_agent                      # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_legal_agent --selftest            # dsh end to end against a fake server
  .venv/bin/python -m code_benchmark.run_legal_agent --smoke --execute     # 3 synthetic questions on IEC (design §10)
  .venv/bin/python -m code_benchmark.run_legal_agent --execute [--resume] [--tunnel-dns <in-tunnel DNS server>]

Each attempt runs dsh headless in its own bubblewrap sandbox: no network, a fresh home, an empty environment, only
system directories, node, the dsh install and the relay visible, and the corpus folder mounted read-only as the
working directory `/work/van-ban-phap-luat`. The relay inside forwards to this process's per-attempt proxy
(`dsh_proxy`), which adds temperature 1.0 and the endpoint key and records every request.

Attempt statuses (design §7): `complete` when dsh emits `final` with reason `completed` (scored on its text); the
terminal outcomes `request_cap`, `upstream_4xx`, `answer_cap` and `harness_end` are complete rows with no answer
(scored wrong, never retried); network errors, timeouts, gateway 5xx and the wall clock are technical failures that
`--resume` re-runs from scratch. A refused temperature, model, path or credential, a changed response model id or a
sandbox that never reached the proxy pauses the run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess  # nosec B404 - bwrap and node --version only, with argument lists built here
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
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import dsh_proxy as px
    from code_benchmark import fake_chat_upstream as fu
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import dsh_proxy as px  # type: ignore[no-redef]
    import fake_chat_upstream as fu  # type: ignore[no-redef]
    import run_diagnostic_prospective as pr  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = la.WORK_ROOT / "run"
SMOKE_ROOT = la.WORK_ROOT / "smoke"
SMOKE_PATH = la.DATA_DIR / "smoke_questions_v1.json"
PROFILE_ID = "qwen3-5-9b-65k-dsh"
CARD_ID = "MC-112"
RELAY = Path(__file__).resolve().parent / "dsh_relay.py"
WORKDIR = "/work/van-ban-phap-luat"
HOME = "/home/agent"
RELAY_PORT = 18080
_SYSTEM_ETC = ("ld.so.cache", "passwd", "group", "nsswitch.conf", "localtime", "hosts")


@dataclass(frozen=True)
class Harness:
    """The pinned dsh install, node, the profile patch and the bwrap binary."""
    install: Path
    node: Path
    profile: Path
    bwrap: str = "/usr/bin/bwrap"
    python: str = "/usr/bin/python3"


def sandbox_command(harness: Harness, docs: Path, home: Path, socket_dir: Path, task: str) -> list[str]:
    """The bwrap argument list of one attempt. Only what dsh needs is visible; everything is read-only except the
    attempt's own home and /tmp."""
    args = [harness.bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/sbin", "/sbin",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/work", "--tmpfs", "/run"]  # nosec B108 - fresh tmpfs mounts inside the sandbox, not the host /tmp
    for name in _SYSTEM_ETC:
        if Path("/etc", name).exists():
            args += ["--ro-bind", f"/etc/{name}", f"/etc/{name}"]
    args += ["--ro-bind", str(harness.node), "/opt/node", "--ro-bind", str(harness.install), "/opt/dsh",
             "--ro-bind", str(RELAY), "/opt/relay/dsh_relay.py", "--bind", str(socket_dir), "/run/proxy",
             "--bind", str(home), HOME, "--ro-bind", str(docs), WORKDIR, "--chdir", WORKDIR]
    env = {"PATH": "/opt/node/bin:/usr/bin:/bin", "HOME": HOME, "DSH_HOME": f"{HOME}/.dsh",
           "DSH_TELEMETRY_DISABLED": "1", "DSH_PERMISSION_MODE": "read-only", "IEC_API_KEY": px.DUMMY_KEY,
           "LANG": "C.UTF-8"}
    for key, value in env.items():
        args += ["--setenv", key, value]
    script = (f'{harness.python} -I /opt/relay/dsh_relay.py {RELAY_PORT} /run/proxy/proxy.sock /run/relay.ready & '
              'n=0; while [ ! -e /run/relay.ready ]; do n=$((n+1)); [ $n -gt 200 ] && exit 97; sleep 0.05; done; '
              'exec /opt/node/bin/node /opt/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js '
              '--profile headless --json "$1"')
    return [*args, "/bin/sh", "-c", script, "dsh-attempt", task]


def prepare_home(home: Path, profile: Path) -> None:
    """A fresh HOME holding only DSH_HOME's headless profile patch."""
    target = home / ".dsh" / "profiles" / "headless"
    target.mkdir(parents=True)
    shutil.copyfile(profile, target / "cordis.patch.yml")


def run_sandboxed(harness: Harness, docs: Path, attempt_dir: Path, task: str, config: px.ProxyConfig,
                  wall_clock: float) -> dict[str, Any]:
    """Run one dsh attempt and return what happened: dsh's exit, its events, the proxy's records."""
    attempt_dir.mkdir(parents=True, exist_ok=False)
    home = attempt_dir / "home"
    prepare_home(home, harness.profile)
    socket_dir = Path(tempfile.mkdtemp(prefix="dshp-"))  # short path: a Unix socket path holds 107 bytes at most
    events_path, stderr_path = attempt_dir / "events.jsonl", attempt_dir / "stderr.txt"
    start = time.monotonic()
    exit_code: int | None = None
    timed_out = False
    try:
        with px.AttemptProxy(config, socket_dir / "proxy.sock", attempt_dir / "proxy_log.jsonl") as proxy:
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
    events = []
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "unparsed_line", "text": line[:500]})
    return {"exit_code": exit_code, "timed_out": timed_out, "wall_s": round(time.monotonic() - start, 3),
            "events": events, "records": records}


# ---------------------------------------------------------------- pins and frozen inputs

def expand(path: str) -> Path:
    return Path(os.path.expanduser(path))


def check_harness(protocol: dict[str, Any]) -> tuple[Harness, list[str]]:
    """The pinned harness, and what differs from the protocol: lockfile hash, dsh version, node version, bwrap."""
    spec = protocol["harness"]
    install, node = expand(spec["install"]), expand(spec["node"])
    problems = []
    lock = install / "package-lock.json"
    if not lock.is_file() or v1.sha256_file(lock) != spec["lockfile_sha256"]:
        problems.append(f"dsh lockfile {lock} differs from {spec['lockfile_sha256'][:12]}")
    package = install / "node_modules" / "@deepseek-ai" / "dsh" / "package.json"
    version = json.loads(package.read_text(encoding="utf-8")).get("version") if package.is_file() else None
    if version != spec["version"]:
        problems.append(f"dsh version {version} is not {spec['version']}")
    node_bin = node / "bin" / "node"
    try:
        node_version = subprocess.run([str(node_bin), "--version"], capture_output=True, text=True,  # nosec B603
                                      timeout=30, check=False).stdout.strip()
    except OSError:
        node_version = None
    if node_version != spec["node_version"]:
        problems.append(f"node version {node_version} is not {spec['node_version']}")
    if not shutil.which("bwrap"):
        problems.append("bwrap is not installed")
    return Harness(install=install, node=node, profile=ROOT / spec["profile"]), problems


def listing_sha256(docs: Path) -> str:
    """The folder hash `build_folder` reports: SHA-256 of the sorted `sha256  file` listing."""
    names = sorted(path.name for path in docs.iterdir())
    return v1.sha256_bytes("".join(f"{v1.sha256_file(docs / name)}  {name}\n" for name in names).encode("utf-8"))


def check_folder(protocol: dict[str, Any], *, rebuild: bool = True) -> tuple[Path, list[str]]:
    """The corpus folder's docs directory, and what differs: its own listing hash, a fresh rebuild's hash, and the
    provisions' anchor lines."""
    docs = ROOT / protocol["corpus"]["folder"] / "docs"
    expected = protocol["corpus"]["folder_sha256"]
    problems = []
    if not docs.is_dir() or listing_sha256(docs) != expected:
        problems.append(f"{docs} does not hash to the registered folder SHA-256")
    if rebuild:
        with tempfile.TemporaryDirectory(prefix="mc112-rebuild-") as tmp:
            built = la.build_folder(la.load_documents(), la.load_mc101_articles(), la.pool_items(), Path(tmp) / "f")
            if built["folder_sha256"] != expected:
                problems.append(f"a fresh rebuild hashes to {built['folder_sha256'][:12]}, not {expected[:12]}")
    if docs.is_dir():
        rows = list(la.load_provisions().values())
        problems += [f"provisions: {p}" for p in la.check_provisions(rows, docs)[:5]]
    return docs, problems


# ---------------------------------------------------------------- one attempt

def _network_type(records: list[dict[str, Any]]) -> str:
    last = next((r for r in reversed(records) if r.get("outcome") in px.TECHNICAL), {})
    if last.get("outcome") == "upstream_5xx":
        return "upstream_5xx"
    name = str(last.get("error_type") or "")
    return "APITimeoutError" if "imeout" in name or name == "timeout" else "APIConnectionError"


def classify(result: dict[str, Any]) -> dict[str, Any]:
    """Status, outcome and answer of one finished sandbox run (design §7)."""
    seen = px.attempt_outcome(result["records"])
    final = next((e for e in reversed(result["events"]) if e.get("type") == "final"), None)
    completed = final is not None and (final.get("reason") or {}).get("kind") == "completed"
    out: dict[str, Any] = {"proxy": seen, "final_reason": (final or {}).get("reason"), "raw_response": "",
                           "fatal": False, "error_type": None}
    if seen["fatal"]:
        return {**out, "status": "request_error", "outcome": "fatal", "error_type": seen["fatal"][0], "fatal": True}
    if completed:
        return {**out, "status": "complete", "outcome": "complete", "raw_response": str(final.get("text") or "")}
    if result["timed_out"]:
        return {**out, "status": "request_error", "outcome": "technical", "error_type": "wall_clock"}
    if seen["technical"]:
        return {**out, "status": "request_error", "outcome": "technical", "error_type": _network_type(result["records"])}
    if seen["requests"] == 0:
        return {**out, "status": "request_error", "outcome": "fatal", "error_type": "sandbox_start", "fatal": True}
    for flag, outcome in (("request_cap", "request_cap"), ("upstream_4xx", "upstream_4xx")):
        if seen[flag]:
            return {**out, "status": "complete", "outcome": outcome}
    if seen["last_finish_reason"] == "length":
        return {**out, "status": "complete", "outcome": "answer_cap"}
    return {**out, "status": "complete", "outcome": "harness_end"}


def tool_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    """Tool calls the model requested, by tool name, from the proxy's assembled responses."""
    names = Counter(call["name"] for record in records if record.get("outcome") == "ok"
                    for call in record["response"]["tool_calls"])
    return dict(sorted(names.items()))


def safe_key(run_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", run_key)


@dataclass
class AttemptContext:
    """Everything an attempt needs besides its item: passed to the engine as its `client`."""
    harness: Harness
    docs: Path
    output: Path
    proxy: px.ProxyConfig
    wall_clock: float


def make_request(protocol: dict[str, Any], guard: pr.BudgetGuard, outage: pr.OutageGuard, max_in_flight: int):
    gate = threading.BoundedSemaphore(max_in_flight)
    halt = threading.Event()
    harness_spec = protocol["harness"]

    def request(context: AttemptContext, item: v1.EvalItem, shard: int, lane: int) -> dict[str, Any]:
        row: dict[str, Any] = {
            "run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
            "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
            "phase": la.PHASE, "profile_id": PROFILE_ID, "protocol_id": la.PROTOCOL_ID, "measurement_card_id": CARD_ID,
            "model_id": context.proxy.model, "transport": "dsh-headless", "api_protocol": harness_spec["api_protocol"],
            "shard": shard, "lane": lane, "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")),
            "raw_prompt": item.prompt, "raw_response": "", "temperature_sent": context.proxy.temperature,
            "reasoning_effort_sent": None, "seed_sent": None, "max_tokens": harness_spec["max_tokens"],
        }
        with gate:  # waiting here is not part of the measured time
            row["started_at"] = pr.base.now()
            for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                        (halt.is_set(), "halted_before_send")):
                if blocked:
                    halt.set()
                    return {**row, "status": "request_error", "finish_reason": "error", "error_type": error_type,
                            "fatal": True, "latency_s": 0.0, "finished_at": pr.base.now()}
            base_dir = context.output / "attempts" / safe_key(item.run_key)
            tries = len(list(base_dir.glob("try-*"))) if base_dir.is_dir() else 0
            attempt_dir = base_dir / f"try-{tries + 1}"
            result = run_sandboxed(context.harness, context.docs, attempt_dir, item.prompt, context.proxy,
                                   context.wall_clock)
        verdict = classify(result)
        seen = verdict.pop("proxy")
        models = seen["response_models"]
        row.update({
            "status": verdict["status"], "outcome": verdict["outcome"], "raw_response": verdict["raw_response"],
            "error_type": verdict["error_type"], "fatal": verdict["fatal"], "final_reason": verdict["final_reason"],
            "finish_reason": "stop" if verdict["outcome"] == "complete" else verdict["outcome"],
            "attempt_dir": str(attempt_dir.relative_to(context.output)), "dsh_exit": result["exit_code"],
            "latency_s": result["wall_s"], "finished_at": pr.base.now(), "requests": seen["requests"],
            "proxy_outcomes": seen["outcomes"], "tool_calls": tool_counts(result["records"]),
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

def load_registration(path: Path = la.REGISTRATION_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_gates(protocol: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                   env: dict[str, str | None], problems: list[str]) -> list[pr.Gate]:
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8")
    card_id = (registration.get("card_ids") or {}).get(la.PHASE)
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    card_file = (registration.get("card_files") or {}).get(la.PHASE)
    frozen = registration.get("frozen") or {}
    differing = [name for name in (*la.HASH_KEYS, "manifest_sha256") if frozen.get(name) != manifest.get(name)]
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
        pr.Gate("harness_and_folder", not problems, "; ".join(problems) or "pins, folder and provisions match"),
    ]


def build_condition(protocol: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    endpoint: str) -> dict[str, Any]:
    harness, proxy = protocol["harness"], protocol["proxy"]
    module = Path(__file__).resolve().parent
    return {
        "protocol_id": la.PROTOCOL_ID, "protocol_version": 1, "phase": la.PHASE,
        "measurement_card_id": registration["card_ids"][la.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][la.PHASE]),
        **{name: manifest[name] for name in (*la.HASH_KEYS, "manifest_sha256")},
        "arm_counts": manifest["arm_counts"], "dataset_counts": manifest["dataset_counts"],
        "operational": protocol["operational"], "model_id": dp.load_protocol()["model"]["requested_id"],
        "expected_response_model": proxy["expected_response_model"], "profile_id": PROFILE_ID,
        "transport": "dsh-headless", "harness": {key: harness[key] for key in ("name", "version", "lockfile_sha256",
                                                                             "node_version", "profile_id", "tools")},
        "api_protocol": harness["api_protocol"], "endpoint_host": urlsplit(endpoint).hostname,
        "base_url_sha256": v1.sha256_bytes(endpoint.encode()), "temperature_requested": proxy["temperature"],
        "temperature_effective": None, "reasoning_effort_sent": None, "seed_sent": None,
        "max_tokens": harness["max_tokens"], "context_window": harness["context_window"],
        "request_timeout_seconds": proxy["request_timeout_seconds"], "request_cap": proxy["request_cap"],
        "wall_clock_seconds": proxy["wall_clock_seconds"], "workdir": protocol["corpus"]["workdir"],
        "scorer_sha256": v1.sha256_file(module / "score_vi_multimodel.py"),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)), "engine_sha256": v1.sha256_file(Path(pr.__file__)),
        "legal_agent_module_sha256": v1.sha256_file(Path(la.__file__)),
        "proxy_sha256": v1.sha256_file(Path(px.__file__)), "relay_sha256": v1.sha256_file(RELAY),
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
            row.update({key: source.get(key) for key in ("outcome", "attempt_dir", "requests", "tool_calls")})
        v1.write_jsonl_atomic(output / "scores.jsonl", scored)
        outcomes = Counter((str(row.get("arm")), str(row.get("outcome"))) for row in rows.values())
        pr.base.atomic_json(output / "summary.json", {
            "protocol_id": la.PROTOCOL_ID, "phase": la.PHASE, "measurement_card_id": card_id,
            "model_id": pr.base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": pr.base.now(),
            "expected_n": len(manifest["items"]),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "outcomes": {f"{arm}:{outcome}": count for (arm, outcome), count in sorted(outcomes.items())},
            "cost_usd": None, "cost_basis": "IEC tariff not supplied; reported usage retained per attempt",
        })
    return score


# ---------------------------------------------------------------- self-test and smoke test

def selftest(protocol: dict[str, Any], harness: Harness) -> bool:
    """dsh end to end against the fake server, offline: a normal attempt, the request cap and a gateway failure."""
    smoke = json.loads(SMOKE_PATH.read_text(encoding="utf-8"))
    cases = [
        ("answer", [{"tool": "grep", "arguments": {"pattern": "hội phí"}},
                    {"tool": "read", "arguments": {"file_path": "quy-che-clb-co-tuong-hoa-binh.txt"}},
                    {"text": "Đáp án: B"}], 30, ("complete", "complete")),
        ("cap", [{"tool": "glob", "arguments": {"pattern": "*.txt"}}] * 3, 2, ("complete", "request_cap")),
        ("gateway", [{"status": 503}], 30, ("request_error", "technical")),
    ]
    provision = {"file": "quy-che-clb-co-tuong-hoa-binh.txt", "anchor_line": "Điều 2. Hội viên"}
    ok = True
    with tempfile.TemporaryDirectory(prefix="mc112-selftest-") as tmp:
        docs = Path(tmp) / "docs"
        docs.mkdir()
        for name, text in smoke["synthetic_folder"].items():
            (docs / name).write_text(text, encoding="utf-8")
        for label, script, cap, expected in cases:
            with fu.FakeUpstream(script) as upstream:
                config = px.ProxyConfig(upstream=upstream.url, api_key="selftest-key", model="Qwen3.5-9B-65K",
                                        expected_response_model="fake-model.gguf", request_cap=cap,
                                        extra_headers=dict(dp.load_protocol()["transport"]["gateway_header"]))
                result = run_sandboxed(harness, docs, Path(tmp) / label, smoke["questions"][0]["prompt"], config, 300)
                sent = list(upstream.requests)
            verdict = classify(result)
            hits = la.provision_hits(la.model_observations(result["records"]), [provision])[0]
            temps = {body.get("temperature") for body in sent}
            good = ((verdict["status"], verdict["outcome"]) == expected and temps <= {protocol["proxy"]["temperature"]}
                    and (label != "answer" or (verdict["raw_response"] == "Đáp án: B" and all(hits.values()))))
            ok &= good
            print(f"selftest {label}: status={verdict['status']} outcome={verdict['outcome']} "
                  f"requests={len(result['records'])} temperatures={sorted(temps)} hits={hits} "
                  f"{'PASS' if good else 'FAIL'}", flush=True)
    return ok


def smoke_test(protocol: dict[str, Any], harness: Harness, docs: Path, endpoint: str, key: str) -> Path:
    """Design §10: the three synthetic questions once each through the full path. No score is computed."""
    smoke = json.loads(SMOKE_PATH.read_text(encoding="utf-8"))
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
    report = []
    for question in smoke["questions"]:
        folder = synthetic if question["folder"] == "synthetic" else docs
        task = la.arm_task(question["prompt"], question["arm"], la.load_prompts())
        result = run_sandboxed(harness, folder, out / question["id"], task, config,
                               protocol["proxy"]["wall_clock_seconds"])
        verdict = classify(result)
        observations = la.model_observations(result["records"])
        seen = px.attempt_outcome(result["records"])
        sent = [json.loads(r["body_sent"]) for r in result["records"] if r.get("body_sent")]
        report.append({
            "id": question["id"], "arm": question["arm"], "status": verdict["status"], "outcome": verdict["outcome"],
            "error_type": verdict["error_type"], "final_text": verdict["raw_response"], "wall_s": result["wall_s"],
            "requests": seen["requests"], "proxy_outcomes": seen["outcomes"], "tool_calls": tool_counts(result["records"]),
            "observations": [{key: o[key] for key in ("tool", "arguments", "status", "read_file", "chars")}
                             for o in observations],
            "temperatures_sent": sorted({body.get("temperature") for body in sent}),
            "fields_sent": sorted({key for body in sent for key in body}),
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
    ap.add_argument("--selftest", action="store_true", help="dsh end to end against a fake server (offline)")
    ap.add_argument("--smoke", action="store_true", help="with --execute: the smoke test of design §10")
    ap.add_argument("--no-rebuild", action="store_true", help="preflight only: skip the fresh folder rebuild")
    ap.add_argument("--tunnel-dns", default=None, help="in-tunnel DNS server for the endpoint host (this process only)")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    if args.no_rebuild and args.execute and not args.smoke:
        ap.error("--no-rebuild is for the preflight and the smoke test only")
    protocol = la.load_protocol()
    harness, problems = check_harness(protocol)
    if args.selftest:
        if problems:
            raise SystemExit("Error: " + "; ".join(problems))
        return 0 if selftest(protocol, harness) else 1
    docs, folder_problems = check_folder(protocol, rebuild=not args.no_rebuild)
    problems += folder_problems
    manifest, rebuilt = la.build_manifest(protocol)
    frozen_path = la.MANIFEST_PATH
    if frozen_path.is_file() and la.load_frozen_manifest(frozen_path) != manifest:
        problems.append("the rebuilt manifest differs from manifest_v1.json")
    elif not frozen_path.is_file():
        problems.append("manifest_v1.json is not frozen yet")
    dp.verify_manifest_rows(manifest, rebuilt)
    env = dotenv_values(ROOT / ".env")
    registration = load_registration()
    gates = evaluate_gates(protocol, manifest, registration, env, problems)
    print(f"phase={la.PHASE} protocol={la.PROTOCOL_ID} items={manifest['item_count']} attempts={manifest['n']} "
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
        campaign["model"]["requested_id"], PROFILE_ID, la.PROTOCOL_ID, CARD_ID)
    pr.base.request = make_request(protocol, guard, outage, operational["max_in_flight"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": pr.base.now(), "resume": resume, "runner_sha256": v1.sha256_file(Path(__file__)),
                                 "operational": operational, "note": args.note}, ensure_ascii=False) + "\n")
    context = AttemptContext(
        harness=harness, docs=docs, output=output, wall_clock=proxy_spec["wall_clock_seconds"],
        proxy=px.ProxyConfig(upstream=endpoint, api_key=key, model=campaign["model"]["requested_id"],
                             expected_response_model=proxy_spec["expected_response_model"],
                             temperature=proxy_spec["temperature"],
                             extra_headers=dict(transport["gateway_header"]),
                             request_timeout=proxy_spec["request_timeout_seconds"],
                             request_cap=proxy_spec["request_cap"]))
    items = dp.verify_manifest_rows(manifest, rebuilt)
    pr.base.execute(output, manifest, rebuilt, items, condition, context, resume,
                    score_callback=score_callback(CARD_ID), runner_path=Path(__file__))
    status = json.loads((output / "run.json").read_text(encoding="utf-8"))["status"]
    print(f"status={status} output={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
