"""Run MC-118 (openspec change diagnostic-reading-agent) for one model: DSHF (dsh), OMPF and OMPS (omp, OMPS with
`--system-prompt <dsh's system prompt for the model>`), and the direct arms C and O, two draws each, on the 400
Reading-400 items, the agent finding each passage in the long-file reading corpus.

From the repo root:
  .venv/bin/python -m code_benchmark.run_reading_agent --model qwen|mimo              # offline preflight
  .venv/bin/python -m code_benchmark.run_reading_agent --model M --selftest            # scripted server + paging check
  .venv/bin/python -m code_benchmark.run_reading_agent --model qwen --smoke --execute --tunnel-dns 172.16.30.1
  .venv/bin/python -m code_benchmark.run_reading_agent --model mimo --smoke --execute
  .venv/bin/python -m code_benchmark.run_reading_agent --model M --execute [--resume] [--tunnel-dns ...]

Routes are the registered ones: Qwen as MC-115 (IEC Qwen3.5-9B-65K over the VPN; the campaign request for C and O),
MiMo as MC-116 (OpenCode Go, its headers, one routing session per try, its provider-error rules and direct request).
The sandbox, relay and proxy are MC-112's and MC-113's, unchanged; their module constant WORKDIR (the folder's mount
point) and omp's `--cwd` are set to /work/bai-viet in this process only. MC-117's stall rule and halted-row identity
apply to every agent arm.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import re
import shutil
import tempfile
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import dotenv_values

try:
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_agent_draws as ld
    from code_benchmark import diagnostic_legal_agent_mimo as lm
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_reading_agent as ra
    from code_benchmark import dsh_proxy as px
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_legal_agent as rla
    from code_benchmark import run_legal_agent_mimo as rlm
    from code_benchmark import run_legal_agent_omp as rlo
    from code_benchmark import run_legal_agent_omp_prompt as rlp
    from code_benchmark import run_legal_agent_v2 as rl2
    from code_benchmark import run_weakness_map as rwm
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_reading_v3 as v3
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_draws as ld  # type: ignore[no-redef]
    import diagnostic_legal_agent_mimo as lm  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import diagnostic_reading_agent as ra  # type: ignore[no-redef]
    import dsh_proxy as px  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import run_diagnostic_prospective as pr  # type: ignore[no-redef]
    import run_legal_agent as rla  # type: ignore[no-redef]
    import run_legal_agent_mimo as rlm  # type: ignore[no-redef]
    import run_legal_agent_omp as rlo  # type: ignore[no-redef]
    import run_legal_agent_omp_prompt as rlp  # type: ignore[no-redef]
    import run_legal_agent_v2 as rl2  # type: ignore[no-redef]
    import run_weakness_map as rwm  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]
    import vi_reading_v3 as v3  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ra.WORK_ROOT / "run"
SMOKE_ROOT = ra.WORK_ROOT / "smoke"
SELFTEST_ROOT = ra.WORK_ROOT / "selftest"
CARD_ID = "MC-118"
HARNESS_OF = {"DSHF": "dsh", "OMPF": "omp", "OMPS": "omp", "C": "direct", "O": "direct"}
SYSTEM_PROMPT_FLAG = "--system-prompt"
LEGAL_WORKDIR = "/work/van-ban-phap-luat"
OMP_SHOWN = re.compile(r"\[Showing lines (\d+)-(\d+)(?: and (\d+)-(\d+))? of ([\d,]+)")
DSH_CAPPED = re.compile(r"\(Output capped\. Showing lines (\d+)-(\d+)\.")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def harness_of(arm: str) -> str:
    if arm not in HARNESS_OF:
        raise _fail(f"arm {arm!r} has no path in MC-118")
    return HARNESS_OF[arm]


def session_id(model: str, run_key: str, attempt: int) -> str:
    """One routing session per try of an agent attempt (sent only on MiMo's route)."""
    return f"vmlu-mc118-{model}-{v1.sha256_bytes(run_key.encode('utf-8'))[:16]}-t{attempt}"


# ---------------------------------------------------------------- the work directory and the harness specifications

def set_workdir(path: str = ra.WORKDIR) -> None:
    """Mount point of the folder in MC-112's and MC-113's sandboxes, and the base of MC-112's path normalisation."""
    la.WORKDIR = rla.WORKDIR = rlo.WORKDIR = path


def with_cwd(argv: list[str], workdir: str) -> list[str]:
    if argv.count("--cwd") != 1:
        raise _fail("omp's argument list must set --cwd exactly once")
    out = list(argv)
    out[out.index("--cwd") + 1] = workdir
    return out


def base_protocol(protocol: dict[str, Any], model: str, root: Path = ROOT) -> dict[str, Any]:
    spec = ra.model_spec(protocol, model)
    path = root / spec["base_protocol"]
    ra._sha_checked(path, spec["base_protocol_sha256"], f"{spec['route_card']} protocol")  # noqa: SLF001
    return ld.load_protocol(path) if model == "qwen" else lm.load_protocol(path)


def omps_prompt(protocol: dict[str, Any], model: str, root: Path = ROOT) -> str:
    spec = ra.model_spec(protocol, model)
    path = root / spec["omps_prompt_file"]
    ra._sha_checked(path, spec["omps_prompt_sha256"], f"{model} OMPS prompt")  # noqa: SLF001
    return path.read_bytes().decode("utf-8")


def harness_protocols(protocol: dict[str, Any], model: str, root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """{"dsh", "OMPF", "OMPS"}: the model's registered DSHF and OMPF specifications (MC-115's for Qwen, MC-116's for
    MiMo) with omp's `--cwd` set to this card's work directory and this card's system-prompt pins; OMPS is OMPF with
    `--system-prompt <dsh's prompt>` appended. Nothing else changes."""
    base = base_protocol(protocol, model, root)
    dsh, omp = rl2.harness_protocols(base) if model == "qwen" else lm.harness_protocols(base, root)
    dsh, ompf = copy.deepcopy(dsh), copy.deepcopy(omp)
    pins = ra.model_spec(protocol, model)["pins"]
    ompf["harness"]["argv"] = with_cwd(ompf["harness"]["argv"], protocol["workdir"])
    ompf["harness"]["invocation"] = str(ompf["harness"].get("invocation", "")).replace(LEGAL_WORKDIR, protocol["workdir"])
    ompf["proxy"]["system_prompt_sha256"] = pins["ompf_system_sha256"]
    omps = copy.deepcopy(ompf)
    if SYSTEM_PROMPT_FLAG in omps["harness"]["argv"]:
        raise _fail(f"the {model} OMPF argument list already sets {SYSTEM_PROMPT_FLAG}")
    omps["harness"]["argv"] = [*omps["harness"]["argv"], SYSTEM_PROMPT_FLAG, omps_prompt(protocol, model, root)]
    omps["harness"]["system_prompt_file"] = ra.model_spec(protocol, model)["omps_prompt_file"]
    omps["proxy"]["system_prompt_sha256"] = pins["omps_system_sha256"]
    return {"dsh": dsh, "OMPF": ompf, "OMPS": omps}


def check_harnesses(protocols: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    """{"dsh": rla.Harness, "OMPF"/"OMPS": rlo.Harness} and what differs from the pins."""
    dsh, dsh_problems = rla.check_harness(protocols["dsh"])
    ompf, ompf_problems = rlo.check_harness(protocols["OMPF"])
    omps, omps_problems = rlo.check_harness(protocols["OMPS"])
    return {"dsh": dsh, "OMPF": ompf, "OMPS": omps}, [*(f"dsh: {p}" for p in dsh_problems),
                                                      *(f"omp: {p}" for p in ompf_problems),
                                                      *(f"omp (OMPS): {p}" for p in omps_problems if p not in ompf_problems)]


def check_folder(protocol: dict[str, Any], *, rebuild: bool = True, root: Path = ROOT) -> tuple[Path, list[str]]:
    """The corpus docs directory, and what differs: its listing hash, and a fresh rebuild's hash."""
    docs = root / protocol["corpus"]["folder"] / "docs"
    expected = protocol["corpus"]["folder_sha256"]
    problems = []
    if not docs.is_dir() or rla.listing_sha256(docs) != expected:
        problems.append(f"{docs} does not hash to the registered folder SHA-256")
    if rebuild:
        with tempfile.TemporaryDirectory(prefix="mc118-rebuild-") as tmp:
            built = ra.build_corpus(Path(tmp) / "f")
            if built["folder_sha256"] != expected:
                problems.append(f"a fresh rebuild hashes to {built['folder_sha256'][:12]}, not {expected[:12]}")
    return docs, problems


# ---------------------------------------------------------------- the route

@dataclass
class Route:
    endpoint: str
    key: str
    proxies: dict[str, px.ProxyConfig]
    session_header: str | None
    problems: list[str]
    base: dict[str, Any]


def resolve_route(protocol: dict[str, Any], model: str, protocols: dict[str, dict[str, Any]], *,
                  resolve: bool) -> Route:
    """Qwen as MC-115 (IEC, .env, the campaign's gateway header), MiMo as MC-116 (OpenCode Go, the shared resolver,
    resolved only when `resolve`). Keys stay in memory."""
    spec = ra.model_spec(protocol, model)
    if model == "qwen":
        env = dotenv_values(ROOT / ".env")
        endpoint, key = str(env.get("OPENAI_BASE_URL") or ""), str(env.get("OPENAI_API_KEY") or "")
        campaign = dp.load_protocol()
        problems = [] if endpoint and key else ["no IEC endpoint or key in .env"]
        if campaign["model"]["requested_id"] != spec["model_id"]:
            problems.append(f"the campaign model {campaign['model']['requested_id']} is not {spec['model_id']}")
        proxies = {name: rl2.proxy_config(p["proxy"], endpoint, key, campaign) for name, p in protocols.items()}
        return Route(endpoint, key, proxies, None, problems, campaign)
    base = base_protocol(protocol, model)
    endpoint, key, problems = rlm.mimo_route(base) if resolve else ("", "", ["not resolved offline"])
    proxies = {name: rlm.proxy_config(base, p["proxy"], endpoint, key) for name, p in protocols.items()}
    return Route(endpoint, key, proxies, base["model"]["session_header"], problems, base)


def direct_client_settings(model: str, route: Route) -> dict[str, Any]:
    """The OpenAI client settings of the direct arms: the campaign transport's (Qwen) or MC-116's (MiMo)."""
    if model == "qwen":
        spec = ra.model_spec(ra.load_protocol(), model)["direct"]
        return {"timeout": spec["timeout_seconds"], "max_retries": spec["sdk_retries"],
                "default_headers": dict(route.base["transport"]["gateway_header"])}
    return {"timeout": route.base["direct"]["timeout_seconds"], "max_retries": route.base["direct"]["sdk_retries"],
            "default_headers": dict(route.base["model"]["extra_headers"])}


# ---------------------------------------------------------------- one attempt

@dataclass
class AttemptContext:
    """Everything an attempt needs besides its item: passed to the engine as its `client`."""
    model: str
    harnesses: dict[str, Any]          # "dsh" -> rla.Harness; "OMPF", "OMPS" -> rlo.Harness
    protocols: dict[str, dict[str, Any]]
    docs: Path
    output: Path
    proxies: dict[str, px.ProxyConfig]
    session_header: str | None
    profile_id: str
    card_id: str
    client: Any = None                 # the OpenAI client of the direct arms
    model_id: str = ""                 # the engine's model id, carried by every row (amendment 3)


def spec_key(arm: str) -> str:
    return "dsh" if arm == "DSHF" else arm


def run_agent(context: AttemptContext, item: v1.EvalItem, arm: str) -> tuple[dict[str, Any], dict[str, Any], Path, int]:
    """One sandboxed attempt on the corpus: (result, verdict, attempt dir, stalls). Stalls are marked before the
    attempt is classified (MC-117)."""
    base_dir = context.output / "attempts" / rla.safe_key(item.run_key)
    tries = len(list(base_dir.glob("try-*"))) if base_dir.is_dir() else 0
    attempt_dir = base_dir / f"try-{tries + 1}"
    key = spec_key(arm)
    config = context.proxies[key]
    if context.session_header:
        config = rlm.with_session(config, context.session_header, session_id(context.model, item.run_key, tries + 1))
    spec = context.protocols[key]
    if arm == "DSHF":
        result = rla.run_sandboxed(context.harnesses["dsh"], context.docs, attempt_dir, item.prompt, config,
                                   spec["proxy"]["wall_clock_seconds"])
        stalls = rlp.mark_stalls(result["records"])
        return result, rla.classify(result), attempt_dir, stalls
    result = rlo.run_sandboxed(context.harnesses[key], context.docs, attempt_dir, item.prompt, config,
                               rlo.rules_for(spec, item.prompt), spec["proxy"]["wall_clock_seconds"])
    stalls = rlp.mark_stalls(result["records"])
    return result, rlo.classify(result), attempt_dir, stalls


def identity_row(item: v1.EvalItem, context: AttemptContext, arm: str, shard: int, lane: int) -> dict[str, Any]:
    harness = harness_of(arm)
    row = {"run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
           "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": arm, "part": "S", "harness": harness,
           "phase": ra.PHASE, "profile_id": context.profile_id, "protocol_id": ra.PROTOCOL_ID,
           "measurement_card_id": context.card_id, "shard": shard, "lane": lane,
           "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")), "raw_prompt": item.prompt,
           "raw_response": ""}
    if harness == "direct":
        # amendment 3: a direct row written without a request carries the model id the engine checks on resume
        row.update({"model_id": context.model_id, "transport": "direct-api"})
    else:
        spec, proxy = context.protocols[spec_key(arm)]["harness"], context.proxies[spec_key(arm)]
        row.update({"model_id": proxy.model, "transport": "dsh-headless" if harness == "dsh" else "omp-json",
                    "api_protocol": spec["api_protocol"], "temperature_sent": proxy.temperature,
                    "reasoning_effort_sent": None, "seed_sent": None,
                    "max_tokens": spec.get("max_tokens") or spec.get("max_completion_tokens")})
    return row


def blocked_row(item: v1.EvalItem, context: AttemptContext, arm: str, shard: int, lane: int,
                error_type: str) -> dict[str, Any]:
    """A row written without a request, with every identity field the engine and `--resume` read (MC-117)."""
    now = pr.base.now()
    return {**identity_row(item, context, arm, shard, lane), "status": "request_error", "outcome": "technical",
            "finish_reason": "error", "error_type": error_type, "fatal": True, "latency_s": 0.0,
            "started_at": now, "finished_at": now}


HALTING_STATUSES = frozenset({401, 402, 403, 404})


def make_chat_direct(spec: dict[str, Any], model_id: str, card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard):
    """Qwen's direct request (C and O) on IEC's chat completions (protocol models.qwen.direct): the campaign's system
    prompt, temperature and cap, the response model pinned. An HTTP 5xx or a network error is technical; an
    authentication error or a different response model is fatal."""

    def request(client: Any, item: v1.EvalItem, shard: int, lane: int) -> dict[str, Any]:
        cap = spec["max_completion_tokens"]
        row: dict[str, Any] = {
            "run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
            "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
            "phase": ra.PHASE, "measurement_card_id": card_id, "model_id": model_id, "transport": "direct-api",
            "api_protocol": spec["api_protocol"], "shard": shard, "lane": lane,
            "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")), "raw_prompt": item.prompt,
            "raw_response": "", "temperature_sent": spec["temperature"], "reasoning_effort_sent": None,
            "seed_sent": None, "max_tokens": cap, "started_at": pr.base.now()}
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=model_id, messages=[{"role": "system", "content": spec["system_prompt"]},
                                          {"role": "user", "content": item.prompt}],
                max_completion_tokens=cap, temperature=spec["temperature"], stream=False)
            if not response.choices:
                raise ValueError("no_choices")
            choice, usage = response.choices[0], response.usage
            finish = str(choice.finish_reason or "unknown")
            tools = getattr(choice.message, "tool_calls", None) or []
            row.update({
                "raw_response": choice.message.content or "", "finish_reason": finish,
                "response_model_id": response.model, "request_id": response.id,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
                "reasoning_tokens": getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None),
                "tool_call_n": len(tools),
                "outcome": "complete" if finish == "stop" else "answer_cap" if finish == "length" else finish,
                "status": "complete" if finish in ("stop", "length") and not tools else "request_error"})
            if row["status"] == "complete" and response.model != spec["expected_response_model"]:
                row.update({"status": "request_error", "error_type": "model_identity_drift", "fatal": True})
            elif row["status"] != "complete":
                row.update({"error_type": "unexpected_finish_or_tool_call", "fatal": bool(tools)})
        except Exception as exc:  # noqa: BLE001 - never serialize SDK messages: they can echo upstream data
            status = getattr(exc, "status_code", None)
            row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                        "http_status": status, "outcome": "technical", "fatal": status in HALTING_STATUSES})
        row.update({"latency_s": round(time.monotonic() - start, 4), "finished_at": pr.base.now()})
        if row["status"] == "complete":
            guard.add(dp.reported_tokens(row))
        elif not row.get("fatal"):
            row["retry_wait_seconds"] = 30 if (row.get("http_status") or 0) >= 500 else 5
        outage.record(row)
        return row

    return request


def make_direct(model: str, route: Route, card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard,
                bad: rlm.BadRequests, protocol: dict[str, Any] | None = None):
    """The direct request of the model's route: chat completions on IEC (Qwen, protocol models.qwen.direct) or
    MC-116's (MiMo)."""
    if model == "qwen":
        spec = ra.model_spec(protocol or ra.load_protocol(), model)
        return make_chat_direct(spec["direct"], spec["model_id"], card_id, guard, outage)
    return rlm.make_direct_request(route.base, card_id, guard, outage, rwm.ModelPin(route.base["model"]["model_identity"]),
                                   bad, str(route.session_header))


def make_request(model: str, card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard, max_in_flight: int,
                 bad: rlm.BadRequests, direct: Any):
    """The engine's request function: one gate over all paths, the shared guards, then the arm's path."""
    gate = threading.BoundedSemaphore(max_in_flight)
    halt = threading.Event()

    def request(context: AttemptContext, item: v1.EvalItem, shard: int, lane: int) -> dict[str, Any]:
        arm = dp.arm_of_replicate(item.replicate_id)
        with gate:  # waiting here is not part of the measured time
            for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                        (halt.is_set(), "halted_before_send")):
                if blocked:
                    halt.set()
                    return blocked_row(item, context, arm, shard, lane, error_type)
            if harness_of(arm) == "direct":
                row = {**direct(context.client, item, shard, lane), "part": "S", "harness": "direct", "arm": arm,
                       "phase": ra.PHASE, "profile_id": context.profile_id, "protocol_id": ra.PROTOCOL_ID,
                       "measurement_card_id": card_id}
                if row.get("fatal"):
                    halt.set()
                return row  # the direct request has already counted tokens and outages
            row = identity_row(item, context, arm, shard, lane)
            row["started_at"] = pr.base.now()
            result, verdict, attempt_dir, stalls = run_agent(context, item, arm)
        if model == "mimo":
            verdict = rlm.provider_verdict(verdict, result["records"], item.run_key, bad)
        row = rl2.finish_agent_row(row, result, verdict, attempt_dir, context.output)
        row.update({**rlm.usage_details(result["records"]), "stalls": stalls, "measurement_card_id": card_id})
        if row["status"] == "complete":
            guard.add(dp.reported_tokens(row))
        elif not row["fatal"]:
            row["retry_wait_seconds"] = 30 if row["error_type"] == "upstream_5xx" else 5
        outage.record(row)
        if row["fatal"]:
            halt.set()
        return row

    return request


# ---------------------------------------------------------------- scoring

def score_callback(card_id: str, model: str):
    def score(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        scored, summaries = dp.score_arm_rows(manifest, rows, rebuilt)
        final = []
        for row in scored:
            source = rows.get(dp.run_key(row)) or {}
            row.update({key: source.get(key) for key in ("part", "harness", "outcome", "attempt_dir", "requests",
                                                       "requests_forwarded", "tool_calls", "stalls",
                                                       "reasoning_tokens", "cached_prompt_tokens",
                                                       "max_completion_tokens_used")})
            row["passage"] = manifest["passage_of"].get(f"{row['dataset_id']}:{row['item_id']}")
            final.append(rl2.rescore(row))
        v1.write_jsonl_atomic(output / "scores.jsonl", final)
        outcomes = Counter((str(row.get("arm")), str(row.get("outcome"))) for row in rows.values())
        by_arm: dict[str, dict[str, Any]] = {}
        for arm in ra.ARMS:
            subset = [row for row in final if row.get("arm") == arm]
            if subset:
                by_arm[arm] = {"n": len(subset),
                               "token_recall_points": round(100 * sum(float(r.get("token_recall") or 0) for r in subset)
                                                            / len(subset), 2),
                               "token_f1_points": round(100 * sum(float(r.get("token_f1") or 0) for r in subset)
                                                        / len(subset), 2)}
        summary = {
            "protocol_id": ra.PROTOCOL_ID, "phase": ra.PHASE, "measurement_card_id": card_id, "model": model,
            "model_id": pr.base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": pr.base.now(),
            "expected_n": len(manifest["items"]), "by_arm": by_arm,
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "outcomes": {f"{arm}:{outcome}": count for (arm, outcome), count in sorted(outcomes.items())},
            "stalls": sum(int(row.get("stalls") or 0) for row in rows.values()),
        }
        if model == "mimo":
            summary.update({"cost_usd": rlm.cost_usd(list(rows.values()), rlm.prices()),
                            "cost_basis": "estimate at OpenCode Go's listed MiMo prices; the provider's meter is "
                                          "authoritative"})
        pr.base.atomic_json(output / "summary.json", summary)
    return score


# ---------------------------------------------------------------- registration, gates and condition

def load_registration(path: Path = ra.REGISTRATION_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def budget_tokens(spec: dict[str, Any], registration: dict[str, Any], model: str) -> int:
    """MC-117's amendment hook, for a sequence of amendments (MC-118 amendment 2): the protocol's budget, or the last
    registered `budget_tokens` amendment. Each must have exactly MC-117's keys and an integer budget for the model no
    lower than the protocol's or the previous amendment's."""
    if not isinstance(spec.get("budget_tokens"), int):
        raise _fail(f"no {model} budget_tokens is set")
    budget = int(spec["budget_tokens"])
    for amendment in [a for a in registration.get("amendments") or []
                      if isinstance(a, dict) and a.get("rule") == "budget_tokens"]:
        value = (amendment.get("budget_tokens") or {}).get(model) if isinstance(amendment.get("budget_tokens"), dict) \
            else None
        if (set(amendment) != rlp.BUDGET_AMENDMENT_KEYS or not isinstance(value, int) or isinstance(value, bool)
                or value < budget):
            raise _fail(f"budget_tokens amendment {amendment.get('id')!r} must have exactly the keys "
                        f"{sorted(rlp.BUDGET_AMENDMENT_KEYS)} and an integer budget for {model} no lower than {budget}")
        budget = value
    return budget


def smoke_problems(protocol: dict[str, Any], model: str, root: Path = ROOT) -> list[str]:
    """The model's registered smoke reports, in order: each hashes as registered; a later report's attempt replaces an
    earlier one for the same question and arm; every final attempt completed; and omp paged a corpus file."""
    reports = protocol["smoke"]["reports"].get(model) or []
    if not reports:
        return [f"no {model} smoke report is registered"]
    problems, final, paged = [], {}, False
    for spec in reports:
        path = root / spec["path"]
        if not path.is_file() or v1.sha256_file(path) != spec["sha256"]:
            problems.append(f"smoke report {path} is missing or differs from its registered SHA-256")
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        final.update({(row["id"], row["arm"]): row for row in report["attempts"]})
        paged |= bool(report.get("paging", {}).get("omp_paged"))
    problems += [f"smoke {qid} {arm}: status {row['status']}" for (qid, arm), row in sorted(final.items())
                 if row["status"] != "complete"]
    if {arm for _, arm in final} != set(ra.ARMS):
        problems.append(f"the {model} smoke reports do not cover every arm")
    if not paged:
        problems.append(f"no {model} smoke report shows omp paging a corpus file")
    return problems


def evaluate_gates(protocol: dict[str, Any], model: str, protocols: dict[str, dict[str, Any]], manifest: dict[str, Any],
                   registration: dict[str, Any], route_problems: list[str], problems: list[str]) -> list[pr.Gate]:
    spec = ra.model_spec(protocol, model)
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8")
    card_id = (registration.get("card_ids") or {}).get(ra.PHASE)
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    card_file = (registration.get("card_files") or {}).get(ra.PHASE)
    frozen = registration.get("frozen") or {}
    differing = [name for name in rl2.hash_keys(manifest) if frozen.get(name) != manifest.get(name)]
    smoke = smoke_problems(protocol, model)
    pins = [*spec["pins"].values(), *(p["proxy"].get("expected_response_model") for p in protocols.values())]
    return [
        pr.Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md"),
        pr.Gate("detail_card", bool(card_file) and (ROOT / str(card_file)).is_file(), str(card_file or "none")),
        pr.Gate("frozen_hashes", bool(frozen) and not differing, "all match" if frozen and not differing
                else f"differ: {differing[:6]}"),
        pr.Gate("endpoint_identity", not route_problems, "; ".join(route_problems) or f"{model}: {spec['model_id']}"),
        pr.Gate("budget_set", isinstance(spec.get("budget_tokens"), int), f"{model} budget_tokens is set"),
        pr.Gate("smoke_passed", not smoke, "; ".join(smoke[:3]) or f"every registered {model} smoke attempt completed"),
        pr.Gate("pins_set", all(pins), "response models and the three system-prompt pins"),
        pr.Gate("harness_and_folder", not problems, "; ".join(problems) or "pins, folder and manifest match"),
    ]


def build_condition(protocol: dict[str, Any], model: str, protocols: dict[str, dict[str, Any]],
                    manifest: dict[str, Any], registration: dict[str, Any], route: Route) -> dict[str, Any]:
    module = Path(__file__).resolve().parent
    direct = (ra.model_spec(protocol, model)["direct"] if model == "qwen"
              else {key: route.base["direct"][key] for key in ("api_protocol", "system_prompt", "temperature",
                                                               "max_completion_tokens")})
    return {
        "protocol_id": ra.PROTOCOL_ID, "protocol_version": 1, "phase": ra.PHASE, "model": model,
        "measurement_card_id": registration["card_ids"][ra.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][ra.PHASE]),
        **{name: manifest[name] for name in rl2.hash_keys(manifest)},
        "arm_counts": manifest["arm_counts"], "dataset_counts": manifest["dataset_counts"],
        "corpus_folder_sha256": protocol["corpus"]["folder_sha256"], "workdir": protocol["workdir"],
        "operational": protocol["operational"], "model_spec": {k: v for k, v in ra.model_spec(protocol, model).items()
                                                               if k != "budget_tokens"},
        "harnesses": {name: {"harness": p["harness"], "proxy": p["proxy"]} for name, p in protocols.items()},
        "direct": direct, "endpoint_host": urlsplit(route.endpoint).hostname,
        "base_url_sha256": v1.sha256_bytes(route.endpoint.encode()),
        "scorer_sha256": v1.sha256_file(module / "score_vi_multimodel.py"),
        "reading_v3_sha256": v1.sha256_file(Path(str(v3.__file__))),
        "wrapper_sha256": v1.sha256_file(Path(str(dp.__file__))), "engine_sha256": v1.sha256_file(Path(str(pr.__file__))),
        "reading_agent_module_sha256": v1.sha256_file(Path(str(ra.__file__))),
        "legal_agent_module_sha256": v1.sha256_file(Path(str(la.__file__))),
        "trajectory_sha256": v1.sha256_file(Path(str(ot.__file__))), "proxy_sha256": v1.sha256_file(Path(str(px.__file__))),
        "relay_sha256": v1.sha256_file(rla.RELAY), "mc112_runner_sha256": v1.sha256_file(Path(str(rla.__file__))),
        "mc113_runner_sha256": v1.sha256_file(Path(str(rlo.__file__))),
        "mc114_runner_sha256": v1.sha256_file(Path(str(rl2.__file__))),
        "mc116_runner_sha256": v1.sha256_file(Path(str(rlm.__file__))),
        "mc117_runner_sha256": v1.sha256_file(Path(str(rlp.__file__))), "runner_sha256": v1.sha256_file(Path(__file__)),
    }


# ---------------------------------------------------------------- self-test, paging and smoke test

def first_system(records: list[dict[str, Any]]) -> tuple[str, str | None]:
    """The first request's system message text and its SHA-256 as the proxy computes it."""
    bodies = [json.loads(r["body_received"]) for r in records if r.get("body_received")][:1]
    if not bodies:
        return "", None
    messages = bodies[0].get("messages") or []
    text = str(messages[0].get("content") or "") if messages and messages[0].get("role") == "system" else ""
    return text, rlo.system_sha256(messages)


def tool_texts(records: list[dict[str, Any]]) -> list[str]:
    """Every distinct tool-result text the model was sent, in order."""
    seen: list[str] = []
    for record in records:
        if not record.get("body_received"):
            continue
        for message in json.loads(record["body_received"]).get("messages") or []:
            if message.get("role") == "tool":
                text = rlo._text(message.get("content"))  # noqa: SLF001 - MC-113's text reader
                if text not in seen:
                    seen.append(text)
    return seen


def paging(records: list[dict[str, Any]], file_lines: int | None = None) -> dict[str, Any]:
    """Whether a read result was cut by omp: `[Showing lines a-b of N]` with b < N, or with a second range (elided)."""
    pages = []
    for text in tool_texts(records):
        for match in OMP_SHOWN.finditer(text):
            first, last, total = int(match.group(1)), int(match.group(2)), int(match.group(5).replace(",", ""))
            pages.append({"first": first, "last": last, "total": total, "elided": bool(match.group(3))})
    cut = [p for p in pages if p["elided"] or p["last"] < p["total"]]
    capped = [[int(m.group(1)), int(m.group(2))] for text in tool_texts(records) for m in DSH_CAPPED.finditer(text)]
    return {"pages": pages, "omp_paged": bool(cut), "dsh_capped": capped, "file_lines": file_lines}


def passage_read(records: list[dict[str, Any]], passage_text: str) -> bool:
    """Whether a tool result held the passage's first 80 normalised characters (design §7)."""
    head = v1.normalized_key(passage_text)[:80]
    return any(head in v1.normalized_key(text) for text in tool_texts(records))


def selftest_steps(harness: str, word: str, file_name: str) -> list[dict[str, Any]]:
    if harness == "dsh":
        return [{"tool": "grep", "arguments": {"pattern": word}},
                {"tool": "read", "arguments": {"file_path": file_name}}, {"text": "Trả lời: Kiểm tra"}]
    return [{"tool": "grep", "arguments": {"i": "Finding the passage", "pattern": word}},
            {"tool": "read", "arguments": {"i": "Reading the file", "path": file_name}}, {"text": "Trả lời: Kiểm tra"}]


def selftest(protocol: dict[str, Any], model: str, protocols: dict[str, dict[str, Any]],
             harnesses: dict[str, Any], docs_source: Path) -> bool:
    """Each agent arm end to end against a scripted server on two real corpus files, offline. The model reads a file
    without offset or limit, which is the paging check (design §1): omp must cut or elide the page. OMPS's first
    system message must begin with dsh's prompt; every request carries the arm's cap. Writes a paging report."""
    prompts = ra.load_prompts()
    task = ra.agent_task("Câu hỏi kiểm tra?", prompts)
    file_name = ra.FILE_NAME.format(1)
    word = next(w for w in (docs_source / file_name).read_text(encoding="utf-8").split() if len(w) > 4)
    file_lines = (docs_source / file_name).read_text(encoding="utf-8").count("\n")
    ok, report = True, {"model": model, "file": file_name, "file_lines": file_lines, "arms": {}}
    with tempfile.TemporaryDirectory(prefix="mc118-selftest-") as tmp:
        docs = Path(tmp) / "docs"
        docs.mkdir()
        for name in (file_name, ra.FILE_NAME.format(2)):
            shutil.copy(docs_source / name, docs / name)
        for arm in ra.AGENT_ARMS:
            key = spec_key(arm)
            spec = protocols[key]
            cap = spec["harness"].get("max_completion_tokens") or spec["harness"].get("max_tokens")
            with rlo.ScriptedUpstream(selftest_steps(harness_of(arm), word, file_name)) as upstream:
                config = px.ProxyConfig(upstream=upstream.url, api_key="selftest-key",
                                        model=ra.model_spec(protocol, model)["model_id"],
                                        expected_response_model="fake-model.gguf", request_cap=30,
                                        extra_headers={"x-opencode-session": "selftest"})
                if arm == "DSHF":
                    result = rla.run_sandboxed(harnesses["dsh"], docs, Path(tmp) / arm, task, config, 300)
                    verdict = rla.classify(result)
                else:
                    rules = dataclasses.replace(rlo.rules_for(spec, task), system_sha256=None)
                    result = rlo.run_sandboxed(harnesses[key], docs, Path(tmp) / arm, task, config, rules, 300)
                    verdict = rlo.classify(result)
                sent = list(upstream.requests)
            system, digest = first_system(result["records"])
            caps = {body.get("max_completion_tokens") or body.get("max_tokens") for body in sent}
            pages = paging(result["records"], file_lines)
            read_whole = any("## Đoạn 0050" in text for text in tool_texts(result["records"]))
            good = ((verdict["status"], verdict["raw_response"]) == ("complete", "Trả lời: Kiểm tra")
                    and caps == {cap} and bool(tool_texts(result["records"])))
            if arm == "OMPS":
                good &= system.startswith(omps_prompt(protocol, model))
            if arm != "DSHF":
                good &= f"--cwd {protocol['workdir']}" in " ".join(spec["harness"]["argv"])
            ok &= good
            report["arms"][arm] = {"status": verdict["status"], "requests": len(result["records"]),
                                   "system_chars": len(system), "system_sha256": digest, "caps": sorted(caps, key=str),
                                   "omp_paged": pages["omp_paged"], "pages": pages["pages"],
                                   "dsh_capped": pages["dsh_capped"],
                                   "whole_file_seen": read_whole, "pass": good}
            print(f"selftest {model} {arm}: status={verdict['status']} requests={len(result['records'])} "
                  f"system_chars={len(system)} caps={sorted(caps, key=str)} omp_paged={pages['omp_paged']} "
                  f"whole_file_seen={read_whole} {'PASS' if good else 'FAIL'}", flush=True)
    report["omp_paged"] = all(report["arms"][arm]["omp_paged"] for arm in ("OMPF", "OMPS"))
    report["dsh_capped"] = bool(report["arms"]["DSHF"]["dsh_capped"])
    SELFTEST_ROOT.mkdir(parents=True, exist_ok=True)
    (SELFTEST_ROOT / f"paging_{model}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                                        encoding="utf-8")
    print(f"paging check {model}: omp_paged={report['omp_paged']} (a False here stops the card for the owner)")
    return ok


def smoke_items(protocol: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """[(question, passage text)] from the registered smoke file."""
    path = ROOT / protocol["smoke"]["questions"]
    ra._sha_checked(path, protocol["smoke"]["questions_sha256"], "smoke questions")  # noqa: SLF001
    texts = {v1.sha256_bytes(key.encode("utf-8")): entry["text"] for key, entry in ra.load_passages().items()}
    return [(q, texts[q["passage_id"]]) for q in json.loads(path.read_text(encoding="utf-8"))["questions"]]


def smoke_test(protocol: dict[str, Any], model: str, protocols: dict[str, dict[str, Any]], harnesses: dict[str, Any],
               docs: Path, route: Route, client: Any, arms: tuple[str, ...] = ra.ARMS) -> Path:
    """Each smoke question once per arm: 20 attempts per model. No score. It records what sets the pins and the
    budget: first system messages (saved as text) and their SHA-256, paging, response models, body keys, statuses,
    stalls and tokens."""
    prompts = ra.load_prompts()
    out = SMOKE_ROOT / model / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True)
    bad = rlm.BadRequests()
    guard, outage = pr.BudgetGuard(10**12, 0), pr.OutageGuard(10**6)
    direct = make_direct(model, route, "MC-118-smoke", guard, outage, bad, protocol)
    attempts, systems, all_pages = [], {}, []
    for question, passage in smoke_items(protocol):
        for arm in arms:
            prompt = (ra.agent_task(question["question"], prompts) if arm in ra.AGENT_ARMS
                      else ra.l2.closed_book_prompt(question["question"], prompts) if arm == "C"
                      else v1.build_reading_prompt(passage, question["question"]))
            item = v1.EvalItem(dataset_id="smoke", source_dataset=question["source"], item_id=question["item_id"],
                               replicate_id=f"{arm}-r1", task="reading", stratum="smoke", question=question["question"],
                               passage_id=question["passage_id"], prompt=prompt, gold_answer="")
            if harness_of(arm) == "direct":
                row = direct(client, item, 0, 0)
                attempts.append({"id": question["id"], "arm": arm, "status": row["status"],
                                 "outcome": row.get("outcome"), "error_type": row.get("error_type"),
                                 "final_text": row.get("raw_response"), "response_models": [row.get("response_model_id")],
                                 "prompt_tokens": row.get("prompt_tokens"), "completion_tokens": row.get("completion_tokens"),
                                 "total_tokens": row.get("total_tokens"), "reasoning_tokens": row.get("reasoning_tokens"),
                                 "latency_s": row.get("latency_s")})
                continue
            key = spec_key(arm)
            config = route.proxies[key]
            if route.session_header:
                config = rlm.with_session(config, route.session_header, session_id(model, f"smoke:{question['id']}:{arm}", 1))
            spec = protocols[key]
            if arm == "DSHF":
                result = rla.run_sandboxed(harnesses["dsh"], docs, out / f"{question['id']}-{arm}", prompt, config,
                                           spec["proxy"]["wall_clock_seconds"])
                stalls = rlp.mark_stalls(result["records"])
                verdict = rla.classify(result)
            else:
                rules = dataclasses.replace(rlo.rules_for(spec, prompt), system_sha256=None)
                result = rlo.run_sandboxed(harnesses[key], docs, out / f"{question['id']}-{arm}", prompt, config,
                                           rules, spec["proxy"]["wall_clock_seconds"])
                stalls = rlp.mark_stalls(result["records"])
                verdict = rlo.classify(result)
            if model == "mimo":
                verdict = rlm.provider_verdict(verdict, result["records"], f"smoke:{question['id']}:{arm}", bad)
            seen = px.attempt_outcome(result["records"])
            received = [json.loads(r["body_received"]) for r in result["records"] if r.get("body_received")]
            system, digest = first_system(result["records"])
            if system:
                systems.setdefault(arm, {})[digest] = system
            pages = paging(result["records"])
            all_pages.append(pages["omp_paged"] if arm != "DSHF" else None)
            attempts.append({
                "id": question["id"], "arm": arm, "status": verdict["status"], "outcome": verdict["outcome"],
                "error_type": verdict["error_type"], "final_text": verdict["raw_response"], "wall_s": result["wall_s"],
                "requests": seen["requests"], "proxy_outcomes": seen["outcomes"], "stalls": stalls,
                "http_statuses": sorted({str(r.get("status")) for r in result["records"]}),
                "tool_calls": rla.tool_counts(result["records"]), "system_prompt_sha256": digest,
                "system_chars": len(system), "omp_paged": pages["omp_paged"] if arm != "DSHF" else None,
                "passage_read": passage_read(result["records"], passage),
                "body_keys": sorted({key for body in received for key in body}),
                "response_models": seen["response_models"], "prompt_tokens": seen["prompt_tokens"],
                "completion_tokens": seen["completion_tokens"], "total_tokens": seen["total_tokens"],
                **rlm.usage_details(result["records"]),
            })
    for arm, texts in systems.items():
        for digest, text in texts.items():
            (out / f"system_{arm}_{str(digest)[:12]}.txt").write_text(text, encoding="utf-8")
    report = {"model": model, "arms": list(arms), "attempts": attempts,
              "systems": {arm: sorted(str(d) for d in texts) for arm, texts in systems.items()},
              "dsh_matches_omps_file": [v1.sha256_bytes(t.encode("utf-8")) for t in systems.get("DSHF", {}).values()]
              == [ra.model_spec(protocol, model)["omps_prompt_sha256"]],
              "paging": {"omp_paged": any(p for p in all_pages if p)}}
    (out / "smoke_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    from openai import OpenAI

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, choices=ra.MODELS)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="re-run only attempts with technical failures")
    ap.add_argument("--selftest", action="store_true", help="the agent arms against a scripted server; paging check")
    ap.add_argument("--smoke", action="store_true", help="with --execute: the smoke test of design §5")
    ap.add_argument("--no-rebuild", action="store_true", help="preflight and smoke only: skip the corpus rebuild")
    ap.add_argument("--smoke-arms", default=",".join(ra.ARMS), help="with --smoke: the arms to run (default all five)")
    ap.add_argument("--tunnel-dns", default="", help="Qwen: resolve the IEC host through this in-tunnel DNS server")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    if args.no_rebuild and args.execute and not args.smoke:
        ap.error("--no-rebuild is for the preflight and the smoke test only")
    model = args.model
    protocol = ra.load_protocol()
    spec = ra.model_spec(protocol, model)
    set_workdir(protocol["workdir"])
    protocols = harness_protocols(protocol, model)
    harnesses, problems = check_harnesses(protocols)
    docs, folder_problems = check_folder(protocol, rebuild=not args.no_rebuild and not args.selftest)
    if args.selftest:
        if problems or folder_problems:
            raise _fail("; ".join(problems + folder_problems))
        return 0 if selftest(protocol, model, protocols, harnesses, docs) else 1
    problems += folder_problems
    route = resolve_route(protocol, model, protocols, resolve=args.execute)
    if args.execute and model == "qwen" and args.tunnel_dns:
        host = urlsplit(route.endpoint).hostname or ""
        print(f"resolver shim (this process only): {host} -> {pr.install_resolver_shim(host, args.tunnel_dns)} "
              f"via {args.tunnel_dns}", flush=True)
    if args.smoke:
        if not args.execute:
            ap.error("--smoke requires --execute")
        paged = SELFTEST_ROOT / f"paging_{model}.json"
        if not paged.is_file() or not json.loads(paged.read_text(encoding="utf-8")).get("omp_paged"):
            raise _fail(f"the paging check has not passed for {model} (run --selftest; a whole-file read stops the card "
                        "for the owner)")
        if problems or route.problems:
            raise _fail("the smoke test needs the pinned harnesses, the folder and the route: "
                        + "; ".join(problems + route.problems))
        with OpenAI(base_url=route.endpoint, api_key=route.key, **direct_client_settings(model, route)) as client:
            arms = tuple(arm for arm in args.smoke_arms.split(",") if arm)
            if not arms or any(arm not in ra.ARMS for arm in arms):
                ap.error(f"--smoke-arms must name arms among {ra.ARMS}")
            out = smoke_test(protocol, model, protocols, harnesses, docs, route, client, arms)
        print(f"smoke test -> {out / 'smoke_report.json'}")
        return 0
    manifest, rebuilt = ra.build_manifest(protocol)
    if ra.MANIFEST_PATH.is_file() and ra.load_frozen_manifest() != manifest:
        problems.append("the rebuilt manifest differs from manifest_v1.json")
    elif not ra.MANIFEST_PATH.is_file():
        problems.append("manifest_v1.json is not frozen yet")
    dp.verify_manifest_rows(manifest, rebuilt)
    registration = load_registration()
    gates = evaluate_gates(protocol, model, protocols, manifest, registration,
                           route.problems if args.execute else [p for p in route.problems if "offline" not in p],
                           problems)
    print(f"phase={ra.PHASE} model={model} items={manifest['item_count']} attempts={manifest['n']} "
          f"arms={manifest['arm_counts']} manifest_sha256={manifest['manifest_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    if not args.execute:
        print(f"preflight done model={model} attempts={manifest['n']} endpoint_calls=0", flush=True)
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise _fail("execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    operational = protocol["operational"]
    card_id = str(registration["card_ids"][ra.PHASE])
    output = OUTPUT_ROOT / spec["profile_id"]
    resume = bool(args.resume) and (output / "condition.json").is_file()
    condition = pr.reconcile_resume(output, build_condition(protocol, model, protocols, manifest, registration, route),
                                    resume)
    budget = budget_tokens(spec, registration, model)
    guard = pr.BudgetGuard(budget, pr.existing_usage(output))
    print(f"budget_tokens={budget} used={guard.used} model={model}", flush=True)
    outage = pr.OutageGuard(operational["stop_after_timeouts"])
    bad = rlm.BadRequests()
    pr.base.MODEL, pr.base.PROFILE, pr.base.PROTOCOL, pr.base.CARD_ID = (
        spec["model_id"], spec["profile_id"], ra.PROTOCOL_ID, card_id)
    direct = make_direct(model, route, card_id, guard, outage, bad, protocol)
    pr.base.request = make_request(model, card_id, guard, outage, operational["max_in_flight"], bad, direct)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": pr.base.now(), "model": model, "resume": resume,
                                 "runner_sha256": v1.sha256_file(Path(__file__)), "operational": operational,
                                 "budget_tokens": budget, "workdir": protocol["workdir"], "note": args.note},
                                ensure_ascii=False) + "\n")
    items = dp.verify_manifest_rows(manifest, rebuilt)
    with OpenAI(base_url=route.endpoint, api_key=route.key, **direct_client_settings(model, route)) as client:
        context = AttemptContext(model=model, harnesses=harnesses, protocols=protocols, docs=docs, output=output,
                                 proxies=route.proxies, session_header=route.session_header,
                                 profile_id=spec["profile_id"], card_id=card_id, client=client,
                                 model_id=spec["model_id"])
        # the engine hands `context` to the request function as its client, as in MC-114's to MC-117's runners
        pr.base.execute(output, manifest, rebuilt, items, condition, context,  # pyright: ignore[reportArgumentType]
                        resume, score_callback=score_callback(card_id, model), runner_path=Path(__file__))
    status = json.loads((output / "run.json").read_text(encoding="utf-8"))["status"]
    print(f"status={status} model={model} output={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
