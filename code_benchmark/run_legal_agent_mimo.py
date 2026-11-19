"""Run MC-116 (openspec change diagnostic-legal-agent-mimo): MC-115's forced-search agent arms (DSHF in dsh, OMPF in
omp) and each part's no-tool baseline (B on Part M, C on Part S) on the same 646 items and folders, two draws, with
MiMo-V2.6-Flash through OpenCode Go in place of Qwen3.5-9B through IEC.

From the repo root:
  .venv/bin/python -m code_benchmark.run_legal_agent_mimo                    # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_legal_agent_mimo --selftest         # both harnesses against scripted servers
  .venv/bin/python -m code_benchmark.run_legal_agent_mimo --smoke --execute  # design §6: smoke questions, no VPN
  .venv/bin/python -m code_benchmark.run_legal_agent_mimo --execute [--resume]

Agent attempts go through MC-112's (dsh) and MC-113's (omp) sandboxes and proxy unchanged; only the model route
differs (lm.harness_protocols): the dsh profile and omp configuration name MiMo, the per-response cap is 16,000, and
the proxy forwards to OpenCode Go with the provider's headers and one routing session per try. Direct arms send MiMo's
direct request of MC-103 to MC-110 (chat completions, "Answer the user's question.") with this card's cap.

Provider errors (design §5): an HTTP 429 (rate or usage limit) halts the launch and its attempt is re-run by
`--resume`; 401/402/403/404 halt; a 400 whose error does not name a content policy is technical (re-run by --resume),
and more than 20 attempts with such a 400 halt the run; a 400 naming a policy is terminal (scored 0, as MC-112's
`upstream_4xx`). Everything else follows MC-115: terminal outcomes score 0 and stay in the denominator.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import tempfile
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_agent_draws as ld
    from code_benchmark import diagnostic_legal_agent_mimo as lm
    from code_benchmark import diagnostic_legal_agent_v2 as l2
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import dsh_proxy as px
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_legal_agent as rla
    from code_benchmark import run_legal_agent_draws as rld
    from code_benchmark import run_legal_agent_omp as rlo
    from code_benchmark import run_legal_agent_v2 as rl2
    from code_benchmark import run_router_labels as labels
    from code_benchmark import run_weakness_map as rwm
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_multimodel_expansion as v2
    from code_benchmark import vi_reading_v3 as v3
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_draws as ld  # type: ignore[no-redef]
    import diagnostic_legal_agent_mimo as lm  # type: ignore[no-redef]
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import dsh_proxy as px  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import run_diagnostic_prospective as pr  # type: ignore[no-redef]
    import run_legal_agent as rla  # type: ignore[no-redef]
    import run_legal_agent_draws as rld  # type: ignore[no-redef]
    import run_legal_agent_omp as rlo  # type: ignore[no-redef]
    import run_legal_agent_v2 as rl2  # type: ignore[no-redef]
    import run_router_labels as labels  # type: ignore[no-redef]
    import run_weakness_map as rwm  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]
    import vi_multimodel_expansion as v2  # type: ignore[no-redef]
    import vi_reading_v3 as v3  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = lm.WORK_ROOT / "run"
SMOKE_ROOT = lm.WORK_ROOT / "smoke"
PROFILE_ID = "mimo-v2-6-flash-legal-agent"
CARD_ID = "MC-116"
HARNESS_OF = {"DSHF": "dsh", "OMPF": "omp", "B": "direct", "C": "direct"}
POLICY_WORDS = ("content", "policy", "safety", "filter", "moderation")
HALTING_STATUSES = frozenset({401, 402, 403, 404, 429})
MAX_ATTEMPTS_WITH_400 = 20


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def harness_of(arm: str) -> str:
    if arm not in HARNESS_OF:
        raise _fail(f"arm {arm!r} has no path in MC-116")
    return HARNESS_OF[arm]


def session_id(run_key: str, attempt: int | None = None) -> str:
    """One OpenCode Go routing session per try of an agent attempt (direct attempts: one per attempt)."""
    tail = f"-t{attempt}" if attempt is not None else ""
    return f"vmlu-mc116-{v1.sha256_bytes(run_key.encode('utf-8'))[:16]}{tail}"


# ---------------------------------------------------------------- the route

def mimo_route(protocol: dict[str, Any]) -> tuple[str, str, list[str]]:
    """(API root, key, what differs from the protocol's model block). The key comes from the shared resolver and stays
    in memory."""
    model = protocol["model"]
    try:
        endpoint, key, model_id, _ = labels.resolve_route({"route": {"profile_id": model["profile_id"]}})
    except SystemExit as exc:
        return "", "", [f"route: {exc}"]
    problems = []
    if endpoint.rstrip("/") != model["endpoint_root"].rstrip("/"):
        problems.append(f"route endpoint {urlsplit(endpoint).hostname} is not {model['endpoint_root']}")
    if model_id != model["model_id"]:
        problems.append(f"route model {model_id} is not {model['model_id']}")
    if not key:
        problems.append("no OpenCode Go credential")
    return endpoint, key, problems


def proxy_config(protocol: dict[str, Any], spec: dict[str, Any], endpoint: str, key: str) -> px.ProxyConfig:
    """MC-112's proxy settings (temperature 1.0, request cap 30) with MiMo's route, headers, timeout and pin."""
    return px.ProxyConfig(upstream=endpoint, api_key=key, model=protocol["model"]["model_id"],
                          expected_response_model=spec["expected_response_model"], temperature=spec["temperature"],
                          extra_headers=dict(protocol["model"]["extra_headers"]),
                          request_timeout=spec["request_timeout_seconds"], request_cap=spec["request_cap"])


def with_session(config: px.ProxyConfig, header: str, session: str) -> px.ProxyConfig:
    return dataclasses.replace(config, extra_headers={**config.extra_headers, header: session})


# ---------------------------------------------------------------- provider errors

def policy_named(text: str) -> bool:
    return any(word in text.lower() for word in POLICY_WORDS)


def provider_error(records: list[dict[str, Any]]) -> int | None:
    """The HTTP status that decides an unfinished attempt: a halting status first, else a 400 that names no policy."""
    failed = [(record.get("status"), str(record.get("error_body") or "")) for record in records
              if record.get("outcome") == "upstream_4xx"]
    for status, _ in failed:
        if status in HALTING_STATUSES:
            return int(status)
    for status, body in failed:
        if status == 400 and not policy_named(body):
            return 400
    return None


@dataclass
class BadRequests:
    """Attempts that met a technical 400, over the launch (design §5)."""
    seen: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, run_key: str) -> bool:
        """Record one; True when the run has now passed the cap and must halt."""
        with self._lock:
            self.seen.add(run_key)
            return len(self.seen) > MAX_ATTEMPTS_WITH_400


def provider_verdict(verdict: dict[str, Any], records: list[dict[str, Any]], run_key: str,
                     bad: BadRequests) -> dict[str, Any]:
    """MC-112's verdict, with OpenCode Go's errors read by design §5. Only an attempt that ended on a provider error
    (outcome `upstream_4xx`) changes."""
    if verdict["outcome"] != "upstream_4xx":
        return verdict
    status = provider_error(records)
    if status is None:
        return verdict  # a 400 naming a content policy: terminal, as MC-112's upstream_4xx
    if status in HALTING_STATUSES:
        kind = "rate_limited" if status == 429 else "provider_refused"
        return {**verdict, "status": "request_error", "outcome": "technical", "error_type": f"{kind}_{status}",
                "fatal": True}
    halt = bad.add(run_key)
    return {**verdict, "status": "request_error", "outcome": "technical", "error_type": "provider_400", "fatal": halt}


def usage_details(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Reasoning and cached-prompt tokens summed over an attempt's answered requests, and the largest completion."""
    reasoning, cached, largest = [], [], 0
    for record in records:
        usage = ((record.get("response") or {}).get("usage") or {}) if record.get("outcome") == "ok" else {}
        detail = usage.get("completion_tokens_details") or {}
        prompt_detail = usage.get("prompt_tokens_details") or {}
        if isinstance(detail.get("reasoning_tokens"), int):
            reasoning.append(detail["reasoning_tokens"])
        if isinstance(prompt_detail.get("cached_tokens"), int):
            cached.append(prompt_detail["cached_tokens"])
        if isinstance(usage.get("completion_tokens"), int):
            largest = max(largest, usage["completion_tokens"])
    return {"reasoning_tokens": sum(reasoning) if reasoning else None,
            "cached_prompt_tokens": sum(cached) if cached else None, "max_completion_tokens_used": largest or None}


# ---------------------------------------------------------------- one attempt

@dataclass
class AttemptContext:
    """Everything an attempt needs besides its item: passed to the engine as its `client`."""
    dsh: rla.Harness
    omp: rlo.Harness
    docs: dict[str, Path]          # corpus name -> docs directory
    corpus_of: dict[str, str]      # item key -> corpus name
    output: Path
    dsh_proxy: px.ProxyConfig
    omp_proxy: px.ProxyConfig
    dsh_protocol: dict[str, Any]
    omp_protocol: dict[str, Any]
    session_header: str
    client: Any = None  # the OpenAI client of the direct arms

    def docs_for(self, item: v1.EvalItem) -> Path:
        key = f"{item.dataset_id}:{item.item_id}"
        if key not in self.corpus_of:
            raise _fail(f"{key} has no corpus in the manifest")
        return self.docs[self.corpus_of[key]]


def run_agent(context: AttemptContext, item: v1.EvalItem, harness: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """One sandboxed attempt through MC-112's (dsh) or MC-113's (omp) path, on the item's folder, with a fresh
    routing session."""
    base_dir = context.output / "attempts" / rla.safe_key(item.run_key)
    tries = len(list(base_dir.glob("try-*"))) if base_dir.is_dir() else 0
    attempt_dir = base_dir / f"try-{tries + 1}"
    docs = context.docs_for(item)
    session = session_id(item.run_key, tries + 1)
    if harness == "dsh":
        config = with_session(context.dsh_proxy, context.session_header, session)
        result = rla.run_sandboxed(context.dsh, docs, attempt_dir, item.prompt, config,
                                   context.dsh_protocol["proxy"]["wall_clock_seconds"])
        return result, rla.classify(result), attempt_dir
    config = with_session(context.omp_proxy, context.session_header, session)
    result = rlo.run_sandboxed(context.omp, docs, attempt_dir, item.prompt, config,
                               rlo.rules_for(context.omp_protocol, item.prompt),
                               context.omp_protocol["proxy"]["wall_clock_seconds"])
    return result, rlo.classify(result), attempt_dir


def agent_row(item: v1.EvalItem, context: AttemptContext, harness: str, shard: int, lane: int,
              card_id: str) -> dict[str, Any]:
    row = rld.agent_row(item, context, harness, shard, lane)  # type: ignore[arg-type]  # same fields it reads
    row.update({"phase": lm.PHASE, "profile_id": PROFILE_ID, "protocol_id": lm.PROTOCOL_ID,
                "measurement_card_id": card_id})
    return row


def _blocked_row(item: v1.EvalItem, harness: str, error_type: str) -> dict[str, Any]:
    return {"run_key": item.run_key, "dataset_id": item.dataset_id, "item_id": item.item_id,
            "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
            "part": rl2.part_of(item), "harness": harness, "phase": lm.PHASE,
            "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")), "raw_response": "",
            "status": "request_error", "finish_reason": "error", "error_type": error_type,
            "fatal": True, "latency_s": 0.0, "started_at": pr.base.now(), "finished_at": pr.base.now()}


def make_direct_request(protocol: dict[str, Any], card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard,
                        pin: rwm.ModelPin, bad: BadRequests, header: str):
    """MiMo's direct request (MC-103 to MC-110's route) with this card's cap and temperature; no gate of its own."""
    spec = protocol["direct"]

    def request(client: Any, item: v1.EvalItem, shard: int, lane: int) -> dict[str, Any]:
        cap = spec["max_completion_tokens"]
        row: dict[str, Any] = {
            "run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
            "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
            "phase": lm.PHASE, "profile_id": PROFILE_ID, "protocol_id": lm.PROTOCOL_ID, "measurement_card_id": card_id,
            "model_id": protocol["model"]["model_id"], "transport": "direct-api", "api_protocol": spec["api_protocol"],
            "shard": shard, "lane": lane, "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")),
            "raw_prompt": item.prompt, "raw_response": "", "temperature_sent": spec["temperature"],
            "reasoning_effort_sent": None, "seed_sent": None, "max_tokens": cap, "started_at": pr.base.now()}
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=protocol["model"]["model_id"],
                messages=[{"role": "system", "content": spec["system_prompt"]}, {"role": "user", "content": item.prompt}],
                max_completion_tokens=cap, temperature=spec["temperature"], stream=False,
                extra_headers={header: session_id(item.run_key)})
            if not response.choices:
                raise ValueError("no_choices")
            choice, usage = response.choices[0], response.usage
            detail = getattr(usage, "completion_tokens_details", None)
            prompt_detail = getattr(usage, "prompt_tokens_details", None)
            finish = str(choice.finish_reason or "unknown")
            tools = getattr(choice.message, "tool_calls", None) or []
            row.update({
                "raw_response": choice.message.content or "", "finish_reason": finish,
                "response_model_id": response.model, "request_id": response.id,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
                "reasoning_tokens": getattr(detail, "reasoning_tokens", None),
                "cached_prompt_tokens": getattr(prompt_detail, "cached_tokens", None), "tool_call_n": len(tools),
                "outcome": "complete" if finish == "stop" else "answer_cap" if finish == "length" else finish,
                "status": "complete" if finish in rwm.COMPLETE_FINISHES and not tools else "request_error"})
            drift = pin.check(response.model) if row["status"] == "complete" else None
            if drift:
                row.update({"status": "request_error", "error_type": drift, "fatal": True})
            elif row["status"] != "complete":
                row.update({"error_type": "unexpected_finish_or_tool_call", "fatal": bool(tools)})
        except Exception as exc:  # noqa: BLE001 - never serialize SDK messages: they can echo upstream data
            status = getattr(exc, "status_code", None)
            row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                        "http_status": status, "outcome": "technical", "fatal": status in HALTING_STATUSES})
            if status == 400:
                body = getattr(exc, "body", None)
                code = " ".join(str(body.get(name) or "") for name in ("code", "type")) if isinstance(body, dict) else ""
                if policy_named(code):
                    row.update({"status": "complete", "outcome": "upstream_4xx", "fatal": False})
                else:
                    row.update({"error_type": "provider_400", "fatal": bad.add(item.run_key)})
        row.update({"latency_s": round(time.monotonic() - start, 4), "finished_at": pr.base.now()})
        if row["status"] == "complete":
            guard.add(dp.reported_tokens(row))
        elif not row.get("fatal"):
            row["retry_wait_seconds"] = 30 if row.get("http_status") == 503 else 5
        outage.record(row)
        return row

    return request


def make_request(card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard, max_in_flight: int, bad: BadRequests,
                 direct: Any):
    """The engine's request function: one gate over all paths, the shared guards, then the arm's path."""
    gate = threading.BoundedSemaphore(max_in_flight)
    halt = threading.Event()

    def request(context: AttemptContext, item: v1.EvalItem, shard: int, lane: int) -> dict[str, Any]:
        harness = harness_of(dp.arm_of_replicate(item.replicate_id))
        with gate:  # waiting here is not part of the measured time
            for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                        (halt.is_set(), "halted_before_send")):
                if blocked:
                    halt.set()
                    return _blocked_row(item, harness, error_type)
            if harness == "direct":
                row = {**direct(context.client, item, shard, lane), "part": rl2.part_of(item), "harness": harness}
                if row.get("fatal"):
                    halt.set()
                return row  # the direct request has already counted tokens and outages
            row = agent_row(item, context, harness, shard, lane, card_id)
            row["started_at"] = pr.base.now()
            result, verdict, attempt_dir = run_agent(context, item, harness)
        verdict = provider_verdict(verdict, result["records"], item.run_key, bad)
        row = rl2.finish_agent_row(row, result, verdict, attempt_dir, context.output)
        row.update(usage_details(result["records"]))
        if row["status"] == "complete":
            guard.add(dp.reported_tokens(row))
        elif not row["fatal"]:
            row["retry_wait_seconds"] = 30 if row["error_type"] == "upstream_5xx" else 5
        outage.record(row)
        if row["fatal"]:
            halt.set()
        return row

    return request


# ---------------------------------------------------------------- scoring and cost

def prices() -> dict[str, float]:
    """MiMo's OpenCode Go prices (USD per million tokens) from the model registry."""
    profile = v2.load_profiles()["mimo-v2-6-flash"]
    return {"input": float(profile["input_price_usd_per_million"]),
            "cached_input": float(profile["cached_input_price_usd_per_million"]),
            "output": float(profile["output_price_usd_per_million"])}


def cost_usd(rows: list[dict[str, Any]], rate: dict[str, float]) -> float:
    """An estimate from reported usage: uncached prompt, cached prompt and completion tokens at the listed prices."""
    total = 0.0
    for row in rows:
        prompt, cached = int(row.get("prompt_tokens") or 0), int(row.get("cached_prompt_tokens") or 0)
        total += ((prompt - cached) * rate["input"] + cached * rate["cached_input"]
                  + int(row.get("completion_tokens") or 0) * rate["output"]) / 1_000_000
    return round(total, 4)


def score_callback(card_id: str):
    def score(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        scored, summaries = dp.score_arm_rows(manifest, rows, rebuilt)
        final = []
        for row in scored:
            source = rows.get(dp.run_key(row)) or {}
            row.update({key: source.get(key) for key in ("part", "harness", "corpus", "outcome", "attempt_dir",
                                                       "requests", "requests_forwarded", "tool_calls",
                                                       "reasoning_tokens", "cached_prompt_tokens",
                                                       "max_completion_tokens_used")})
            final.append(rl2.rescore(row))
        v1.write_jsonl_atomic(output / "scores.jsonl", final)
        outcomes = Counter((str(row.get("arm")), str(row.get("outcome"))) for row in rows.values())
        pr.base.atomic_json(output / "summary.json", {
            "protocol_id": lm.PROTOCOL_ID, "phase": lm.PHASE, "measurement_card_id": card_id,
            "model_id": pr.base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": pr.base.now(),
            "expected_n": len(manifest["items"]), "by_part_arm": rl2.summarize(final),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "outcomes": {f"{arm}:{outcome}": count for (arm, outcome), count in sorted(outcomes.items())},
            "cost_usd": cost_usd(list(rows.values()), prices()),
            "cost_basis": "estimate: reported uncached prompt, cached prompt and completion tokens at OpenCode Go's "
                          "listed MiMo prices (model registry); the provider's own meter is authoritative",
        })
    return score


# ---------------------------------------------------------------- registration, gates and condition

def load_registration(path: Path = lm.REGISTRATION_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def smoke_problems(protocol: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Registered smoke reports: each must hash as registered, and every attempt in it must have completed, omp with
    the pinned system prompt."""
    reports = protocol["smoke"].get("reports") or []
    if not reports:
        return ["no smoke report is registered"]
    problems = []
    for spec in reports:
        path = root / spec["path"]
        if not path.is_file() or v1.sha256_file(path) != spec["sha256"]:
            problems.append(f"smoke report {path} is missing or differs from its registered SHA-256")
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row["status"] != "complete" or row.get("system_prompt_matches") is False:
                problems.append(f"smoke {row['id']} {row['arm']}: status {row['status']}, "
                                f"omp system prompt match {row.get('system_prompt_matches')}")
    return problems


def evaluate_gates(protocol: dict[str, Any], dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any],
                   manifest: dict[str, Any], registration: dict[str, Any], route_problems: list[str],
                   problems: list[str]) -> list[pr.Gate]:
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8")
    card_id = (registration.get("card_ids") or {}).get(lm.PHASE)
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    card_file = (registration.get("card_files") or {}).get(lm.PHASE)
    frozen = registration.get("frozen") or {}
    differing = [name for name in rl2.hash_keys(manifest) if frozen.get(name) != manifest.get(name)]
    pins = [dsh_protocol["proxy"].get("expected_response_model"), omp_protocol["proxy"].get("expected_response_model"),
            omp_protocol["proxy"].get("system_prompt_sha256"), protocol["model"].get("expected_response_model")]
    smoke = smoke_problems(protocol)
    return [
        pr.Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md"),
        pr.Gate("detail_card", bool(card_file) and (ROOT / str(card_file)).is_file(), str(card_file or "none")),
        pr.Gate("frozen_hashes", bool(frozen) and not differing, "all match" if frozen and not differing
                else f"differ: {differing[:6]}"),
        pr.Gate("endpoint_identity", not route_problems, "; ".join(route_problems) or
                f"{protocol['model']['endpoint_root']} {protocol['model']['model_id']}"),
        pr.Gate("budget_set", isinstance(protocol["operational"].get("budget_tokens"), int), "budget_tokens is set"),
        pr.Gate("smoke_passed", not smoke, "; ".join(smoke[:3]) or "every registered smoke attempt completed"),
        pr.Gate("pins_set", all(pins), "response models of dsh, omp and the direct arms, and omp's system prompt"),
        pr.Gate("harness_and_folders", not problems, "; ".join(problems) or "pins, folders and manifest match"),
    ]


def build_condition(protocol: dict[str, Any], dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any],
                    manifest: dict[str, Any], registration: dict[str, Any], endpoint: str) -> dict[str, Any]:
    module = Path(__file__).resolve().parent
    return {
        "protocol_id": lm.PROTOCOL_ID, "protocol_version": 1, "phase": lm.PHASE,
        "measurement_card_id": registration["card_ids"][lm.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][lm.PHASE]),
        **{name: manifest[name] for name in rl2.hash_keys(manifest)},
        "arm_counts": manifest["arm_counts"], "dataset_counts": manifest["dataset_counts"],
        "corpora": {name: spec["folder_sha256"] for name, spec in protocol["corpora"].items()},
        "operational": protocol["operational"], "model": protocol["model"], "profile_id": PROFILE_ID,
        "dsh": {"harness": dsh_protocol["harness"], "proxy": dsh_protocol["proxy"]},
        "omp": {"harness": omp_protocol["harness"], "proxy": omp_protocol["proxy"]},
        "direct": protocol["direct"],
        "endpoint_host": urlsplit(endpoint).hostname, "base_url_sha256": v1.sha256_bytes(endpoint.encode()),
        "workdir": protocol["workdir"],
        "scorer_sha256": v1.sha256_file(module / "score_vi_multimodel.py"),
        "reading_v3_sha256": v1.sha256_file(Path(str(v3.__file__))),
        "wrapper_sha256": v1.sha256_file(Path(str(dp.__file__))), "engine_sha256": v1.sha256_file(Path(str(pr.__file__))),
        "legal_agent_module_sha256": v1.sha256_file(Path(str(la.__file__))),
        "legal_agent_v2_module_sha256": v1.sha256_file(Path(str(l2.__file__))),
        "legal_agent_draws_module_sha256": v1.sha256_file(Path(str(ld.__file__))),
        "legal_agent_mimo_module_sha256": v1.sha256_file(Path(str(lm.__file__))),
        "trajectory_sha256": v1.sha256_file(Path(str(ot.__file__))), "proxy_sha256": v1.sha256_file(Path(str(px.__file__))),
        "relay_sha256": v1.sha256_file(rla.RELAY), "mc112_runner_sha256": v1.sha256_file(Path(str(rla.__file__))),
        "mc113_runner_sha256": v1.sha256_file(Path(str(rlo.__file__))),
        "mc114_runner_sha256": v1.sha256_file(Path(str(rl2.__file__))),
        "mc115_runner_sha256": v1.sha256_file(Path(str(rld.__file__))), "runner_sha256": v1.sha256_file(Path(__file__)),
    }


# ---------------------------------------------------------------- self-test (offline)

def selftest(dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any], dsh: rla.Harness, omp: rlo.Harness) -> bool:
    """Both harnesses end to end with MiMo's route configuration, against scripted servers, offline: an MC task and a
    span task each. omp's requests must pass the registered shape (keys, the 16,000 cap, the pinned system prompt);
    dsh's must carry the 16,000 cap in `max_completion_tokens`."""
    smoke = json.loads(rla.SMOKE_PATH.read_text(encoding="utf-8"))
    prompts = l2.load_prompts()
    provision = {"file": rl2.SELFTEST_FILE, "anchor_line": "Điều 2. Hội viên"}
    cap = dsh_protocol["harness"]["max_tokens"]
    ok = True
    with tempfile.TemporaryDirectory(prefix="mc116-selftest-") as tmp:
        docs = Path(tmp) / "docs"
        docs.mkdir()
        for name, text in smoke["synthetic_folder"].items():
            (docs / name).write_text(text, encoding="utf-8")
        for label, harness, task, script, expected in rl2.selftest_cases(prompts, smoke["questions"][0]["prompt"]):
            with rlo.ScriptedUpstream(script) as upstream:
                config = px.ProxyConfig(upstream=upstream.url, api_key="selftest-key", model=lm.MODEL_ID,
                                        expected_response_model="fake-model.gguf", request_cap=30,
                                        extra_headers={"x-opencode-session": "selftest"})
                if harness == "dsh":
                    result = rla.run_sandboxed(dsh, docs, Path(tmp) / label, task, config, 300)
                    verdict, observations = rla.classify(result), la.model_observations(result["records"])
                else:
                    result = rlo.run_sandboxed(omp, docs, Path(tmp) / label, task, config,
                                               rlo.rules_for(omp_protocol, task), 300)
                    verdict, observations = rlo.classify(result), ot.omp_observations(result["records"])
                sent = list(upstream.requests)
            hits = la.provision_hits(observations, [provision])[0]
            temps = {body.get("temperature") for body in sent}
            caps = {body.get("max_completion_tokens") for body in sent}
            good = ((verdict["status"], verdict["outcome"], verdict["raw_response"]) == ("complete", "complete", expected)
                    and temps <= {dsh_protocol["proxy"]["temperature"]} and caps == {cap} and all(hits.values()))
            if label.endswith("span"):
                good &= v3.score_reading(verdict["raw_response"], "100.000 đồng")["token_f1"] == 1.0
            ok &= good
            print(f"selftest {label}: status={verdict['status']} outcome={verdict['outcome']} "
                  f"requests={len(result['records'])} temperatures={sorted(temps, key=str)} caps={sorted(caps, key=str)} "
                  f"hits={hits} {'PASS' if good else 'FAIL'}", flush=True)
    return ok


# ---------------------------------------------------------------- smoke test (design §6)

def smoke_test(protocol: dict[str, Any], dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any],
               dsh: rla.Harness, omp: rlo.Harness, docs: dict[str, Path], endpoint: str, key: str) -> Path:
    """Each registered smoke question once with DSHF and OMPF on its folder, and once with its direct arm (B for the
    multiple-choice question, C for the span question). No score is computed. It records what sets the pins and the
    budget: response model ids, omp's system-prompt hash, tokens (reasoning and cached included) and the largest
    completion against the cap."""
    from openai import OpenAI

    prompts = l2.load_prompts()
    header = protocol["model"]["session_header"]
    out = SMOKE_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True)
    configs = {"dsh": proxy_config(protocol, dsh_protocol["proxy"], endpoint, key),
               "omp": proxy_config(protocol, omp_protocol["proxy"], endpoint, key)}
    bad = BadRequests()
    report = []
    direct = make_direct_request(protocol, "smoke", pr.BudgetGuard(10**9, 0), pr.OutageGuard(10**6),
                                 rwm.ModelPin(protocol["model"]["model_identity"]), bad, header)
    with OpenAI(base_url=endpoint, api_key=key, timeout=protocol["direct"]["timeout_seconds"],
                max_retries=protocol["direct"]["sdk_retries"], default_headers=dict(protocol["model"]["extra_headers"])
                ) as client:
        for question, corpus in rld.load_smoke(protocol):
            task = rld.smoke_task(question, prompts)
            for arm, harness in (("DSHF", "dsh"), ("OMPF", "omp")):
                attempt = out / f"{question['id']}-{harness}"
                config = with_session(configs[harness], header, session_id(f"smoke:{question['id']}:{arm}", 1))
                if harness == "dsh":
                    result = rla.run_sandboxed(dsh, docs[corpus], attempt, task, config,
                                               dsh_protocol["proxy"]["wall_clock_seconds"])
                    verdict, observations = rla.classify(result), la.model_observations(result["records"])
                else:
                    rules = dataclasses.replace(rlo.rules_for(omp_protocol, task), system_sha256=None)
                    result = rlo.run_sandboxed(omp, docs[corpus], attempt, task, config, rules,
                                               omp_protocol["proxy"]["wall_clock_seconds"])
                    verdict, observations = rlo.classify(result), ot.omp_observations(result["records"])
                verdict = provider_verdict(verdict, result["records"], f"smoke:{question['id']}:{arm}", bad)
                seen = px.attempt_outcome(result["records"])
                received = [json.loads(r["body_received"]) for r in result["records"] if r.get("body_received")]
                system = sorted({str(rlo.system_sha256(body.get("messages") or [])) for body in received[:1]})
                report.append({
                    "id": question["id"], "kind": question.get("kind", "mc"), "corpus": corpus, "arm": arm,
                    "harness": harness, "status": verdict["status"], "outcome": verdict["outcome"],
                    "error_type": verdict["error_type"], "final_text": verdict["raw_response"],
                    "wall_s": result["wall_s"], "requests": seen["requests"], "proxy_outcomes": seen["outcomes"],
                    "http_statuses": sorted({str(r.get("status")) for r in result["records"]}),
                    "error_bodies": [str(r.get("error_body"))[:300] for r in result["records"] if r.get("error_body")],
                    "tool_calls": rla.tool_counts(result["records"]),
                    "hits": la.provision_hits(observations, question.get("provisions") or []),
                    "system_prompt_sha256": system if harness == "omp" else None,
                    "system_prompt_matches": (system == [omp_protocol["proxy"]["system_prompt_sha256"]]
                                              if harness == "omp" else None),
                    "body_keys": sorted({key for body in received for key in body}),
                    "response_models": seen["response_models"], "prompt_tokens": seen["prompt_tokens"],
                    "completion_tokens": seen["completion_tokens"], "total_tokens": seen["total_tokens"],
                    **usage_details(result["records"]),
                })
            arm = "C" if question.get("kind") == "span" else "B"
            prompt = (l2.closed_book_prompt(question["question"], prompts) if arm == "C" else question["prompt"])
            item = v1.EvalItem(dataset_id="smoke", source_dataset="smoke", item_id=question["id"],
                               replicate_id=f"{arm}-r1", task="reading" if arm == "C" else "multiple_choice",
                               stratum="smoke", question=str(question.get("question") or ""), passage_id="",
                               prompt=prompt, gold_answer="")
            row = direct(client, item, 0, 0)
            report.append({
                "id": question["id"], "kind": question.get("kind", "mc"), "corpus": None, "arm": arm,
                "harness": "direct", "status": row["status"], "outcome": row.get("outcome"),
                "error_type": row.get("error_type"), "http_status": row.get("http_status"),
                "final_text": row["raw_response"], "wall_s": row["latency_s"], "finish_reason": row.get("finish_reason"),
                "response_models": [row.get("response_model_id")], "prompt_tokens": row.get("prompt_tokens"),
                "completion_tokens": row.get("completion_tokens"), "total_tokens": row.get("total_tokens"),
                "reasoning_tokens": row.get("reasoning_tokens"), "cached_prompt_tokens": row.get("cached_prompt_tokens"),
                "max_completion_tokens_used": row.get("completion_tokens"),
            })
    (out / "smoke_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- main

def check_harnesses(protocol: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], rla.Harness, rlo.Harness,
                                                       list[str]]:
    """MiMo's harness specifications, the pinned installs with MiMo's dsh profile and omp configuration and argument
    list, and what differs from the pins."""
    dsh_protocol, omp_protocol = lm.harness_protocols(protocol)
    dsh, dsh_problems = rla.check_harness(dsh_protocol)
    omp, omp_problems = rlo.check_harness(omp_protocol)
    return dsh_protocol, omp_protocol, dsh, omp, [*(f"dsh: {p}" for p in dsh_problems),
                                                  *(f"omp: {p}" for p in omp_problems)]


def main(argv: list[str] | None = None) -> int:
    from openai import OpenAI

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="re-run only attempts with technical failures")
    ap.add_argument("--selftest", action="store_true", help="both harnesses end to end against scripted servers")
    ap.add_argument("--smoke", action="store_true", help="with --execute: the smoke test of design §6")
    ap.add_argument("--no-rebuild", action="store_true", help="preflight and smoke only: skip corpus_v2's fresh rebuild")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    if args.no_rebuild and args.execute and not args.smoke:
        ap.error("--no-rebuild is for the preflight and the smoke test only")
    protocol = lm.load_protocol()
    dsh_protocol, omp_protocol, dsh, omp, problems = check_harnesses(protocol)
    if args.selftest:
        if problems:
            raise _fail("; ".join(problems))
        return 0 if selftest(dsh_protocol, omp_protocol, dsh, omp) else 1
    docs, folder_problems = rld.check_folders(protocol, rebuild=not args.no_rebuild)
    problems += folder_problems
    endpoint, key, route_problems = mimo_route(protocol) if args.execute else ("", "", ["not resolved offline"])
    if args.smoke:
        if not args.execute:
            ap.error("--smoke requires --execute")
        if problems or route_problems:
            raise _fail("the smoke test needs the pinned harnesses, both folders and the route: "
                        + "; ".join(problems + route_problems))
        out = smoke_test(protocol, dsh_protocol, omp_protocol, dsh, omp, docs, endpoint, key)
        print(f"smoke test -> {out / 'smoke_report.json'}")
        return 0
    manifest, rebuilt = lm.build_manifest(protocol)
    if lm.MANIFEST_PATH.is_file() and lm.load_frozen_manifest() != manifest:
        problems.append("the rebuilt manifest differs from manifest_v1.json")
    elif not lm.MANIFEST_PATH.is_file():
        problems.append("manifest_v1.json is not frozen yet")
    dp.verify_manifest_rows(manifest, rebuilt)
    registration = load_registration()
    gates = evaluate_gates(protocol, dsh_protocol, omp_protocol, manifest, registration,
                           [] if not args.execute else route_problems, problems)
    print(f"phase={lm.PHASE} protocol={lm.PROTOCOL_ID} items={manifest['item_count']} attempts={manifest['n']} "
          f"arms={manifest['arm_counts']} manifest_sha256={manifest['manifest_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    if not args.execute:
        print(f"preflight done items={manifest['item_count']} attempts={manifest['n']} endpoint_calls=0 "
              "(the route is resolved only with --execute)", flush=True)
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise _fail("execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    operational, direct_spec, header = protocol["operational"], protocol["direct"], protocol["model"]["session_header"]
    card_id = str(registration["card_ids"][lm.PHASE])
    output = OUTPUT_ROOT / PROFILE_ID
    resume = bool(args.resume) and (output / "condition.json").is_file()
    condition = pr.reconcile_resume(output, build_condition(protocol, dsh_protocol, omp_protocol, manifest,
                                                            registration, endpoint), resume)
    guard = pr.BudgetGuard(operational["budget_tokens"], pr.existing_usage(output))
    outage = pr.OutageGuard(operational["stop_after_timeouts"])
    bad = BadRequests()
    pr.base.MODEL, pr.base.PROFILE, pr.base.PROTOCOL, pr.base.CARD_ID = (
        protocol["model"]["model_id"], PROFILE_ID, lm.PROTOCOL_ID, card_id)
    direct = make_direct_request(protocol, card_id, guard, outage, rwm.ModelPin(protocol["model"]["model_identity"]),
                                 bad, header)
    pr.base.request = make_request(card_id, guard, outage, operational["max_in_flight"], bad, direct)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": pr.base.now(), "resume": resume, "runner_sha256": v1.sha256_file(Path(__file__)),
                                 "operational": operational, "note": args.note}, ensure_ascii=False) + "\n")
    items = dp.verify_manifest_rows(manifest, rebuilt)
    with OpenAI(base_url=endpoint, api_key=key, timeout=direct_spec["timeout_seconds"],
                max_retries=direct_spec["sdk_retries"], default_headers=dict(protocol["model"]["extra_headers"])
                ) as client:
        context = AttemptContext(dsh=dsh, omp=omp, docs=docs, corpus_of=manifest["corpus_of"], output=output,
                                 dsh_proxy=proxy_config(protocol, dsh_protocol["proxy"], endpoint, key),
                                 omp_proxy=proxy_config(protocol, omp_protocol["proxy"], endpoint, key),
                                 dsh_protocol=dsh_protocol, omp_protocol=omp_protocol, session_header=header,
                                 client=client)
        # the engine hands `context` to the request function as its client, as in MC-114's and MC-115's runners
        pr.base.execute(output, manifest, rebuilt, items, condition, context,  # pyright: ignore[reportArgumentType]
                        resume, score_callback=score_callback(card_id), runner_path=Path(__file__))
    status = json.loads((output / "run.json").read_text(encoding="utf-8"))["status"]
    print(f"status={status} output={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
