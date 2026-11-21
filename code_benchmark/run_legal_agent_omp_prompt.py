"""Run MC-117 (openspec change diagnostic-legal-agent-omp-prompt) for one model: OMPS, omp 18.0.0 exactly as that
model's registered OMPF with `--system-prompt <dsh's system prompt for the model>`, on MC-115's 646 items, draws 1-2.

From the repo root:
  .venv/bin/python -m code_benchmark.run_legal_agent_omp_prompt --model qwen|mimo              # offline preflight
  .venv/bin/python -m code_benchmark.run_legal_agent_omp_prompt --model M --selftest            # scripted server
  .venv/bin/python -m code_benchmark.run_legal_agent_omp_prompt --model qwen --smoke --execute --tunnel-dns 172.16.30.1
  .venv/bin/python -m code_benchmark.run_legal_agent_omp_prompt --model mimo --smoke --execute
  .venv/bin/python -m code_benchmark.run_legal_agent_omp_prompt --model M --execute [--resume] [--tunnel-dns ...]

Routes are the registered ones: Qwen as MC-115 (IEC Qwen3.5-9B-65K over the VPN, MC-115's omp proxy settings), MiMo
as MC-116 (OpenCode Go, its headers, one routing session per try, its provider-error rules). The sandbox, relay and
proxy are MC-112's and MC-113's, unchanged.

Two fixes apply to this card only (design §4): a row written without a request carries its identity fields, so a
halt pauses the run instead of crashing it and `--resume` can load the row; and a proxied stream that ends with no
chunk naming a model (a provider stall) is read as `network` (`stream_stalled`) before the attempt is classified, so
it is technical, not fatal. A response that names another model still halts the run.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import tempfile
import threading
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
    from code_benchmark import diagnostic_legal_agent_omp_prompt as lp
    from code_benchmark import diagnostic_legal_agent_v2 as l2
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import dsh_proxy as px
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_legal_agent as rla
    from code_benchmark import run_legal_agent_draws as rld
    from code_benchmark import run_legal_agent_mimo as rlm
    from code_benchmark import run_legal_agent_omp as rlo
    from code_benchmark import run_legal_agent_v2 as rl2
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_reading_v3 as v3
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_draws as ld  # type: ignore[no-redef]
    import diagnostic_legal_agent_mimo as lm  # type: ignore[no-redef]
    import diagnostic_legal_agent_omp_prompt as lp  # type: ignore[no-redef]
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import dsh_proxy as px  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import run_diagnostic_prospective as pr  # type: ignore[no-redef]
    import run_legal_agent as rla  # type: ignore[no-redef]
    import run_legal_agent_draws as rld  # type: ignore[no-redef]
    import run_legal_agent_mimo as rlm  # type: ignore[no-redef]
    import run_legal_agent_omp as rlo  # type: ignore[no-redef]
    import run_legal_agent_v2 as rl2  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]
    import vi_reading_v3 as v3  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = lp.WORK_ROOT / "run"
SMOKE_ROOT = lp.WORK_ROOT / "smoke"
CARD_ID = "MC-117"
STALL = "stream_stalled"


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def session_id(model: str, run_key: str, attempt: int) -> str:
    """One routing session per try of an attempt (sent only on MiMo's route)."""
    return f"vmlu-mc117-{model}-{v1.sha256_bytes(run_key.encode('utf-8'))[:16]}-t{attempt}"


# ---------------------------------------------------------------- the route

@dataclass
class Route:
    endpoint: str
    key: str
    proxy: px.ProxyConfig
    session_header: str | None
    problems: list[str]


def resolve_route(protocol: dict[str, Any], model: str, omp_protocol: dict[str, Any], *, resolve: bool) -> Route:
    """The model's registered route: Qwen as MC-115 (IEC, .env), MiMo as MC-116 (OpenCode Go, the shared resolver,
    resolved only when `resolve`). Keys stay in memory."""
    spec = lp.model_spec(protocol, model)
    if model == "qwen":
        env = dotenv_values(ROOT / ".env")
        endpoint, key = str(env.get("OPENAI_BASE_URL") or ""), str(env.get("OPENAI_API_KEY") or "")
        campaign = dp.load_protocol()
        problems = [] if endpoint and key else ["no IEC endpoint or key in .env"]
        if campaign["model"]["requested_id"] != spec["model_id"]:
            problems.append(f"the campaign model {campaign['model']['requested_id']} is not {spec['model_id']}")
        return Route(endpoint, key, rl2.proxy_config(omp_protocol["proxy"], endpoint, key, campaign), None, problems)
    base = lm.load_protocol(ROOT / spec["base_protocol"])
    endpoint, key, problems = rlm.mimo_route(base) if resolve else ("", "", ["not resolved offline"])
    return Route(endpoint, key, rlm.proxy_config(base, omp_protocol["proxy"], endpoint, key),
                 base["model"]["session_header"], problems)


# ---------------------------------------------------------------- one attempt

def mark_stalls(records: list[dict[str, Any]]) -> int:
    """A `model_drift` record whose stream named no model at all is a provider stall: read it as `network`
    (`stream_stalled`). A record that names another model keeps `model_drift` and stays fatal."""
    stalls = 0
    for record in records:
        response = record.get("response") if isinstance(record.get("response"), dict) else {}
        if record.get("outcome") == "model_drift" and not (response or {}).get("model"):
            record.update({"outcome": "network", "error_type": STALL, "stall": True})
            stalls += 1
    return stalls


@dataclass
class AttemptContext:
    """Everything an attempt needs besides its item: passed to the engine as its `client`."""
    model: str
    omp: rlo.Harness
    omp_protocol: dict[str, Any]
    docs: dict[str, Path]          # corpus name -> docs directory
    corpus_of: dict[str, str]      # item key -> corpus name
    output: Path
    proxy: px.ProxyConfig
    session_header: str | None
    profile_id: str
    card_id: str

    def docs_for(self, item: v1.EvalItem) -> Path:
        key = f"{item.dataset_id}:{item.item_id}"
        if key not in self.corpus_of:
            raise _fail(f"{key} has no corpus in the manifest")
        return self.docs[self.corpus_of[key]]


def run_agent(context: AttemptContext, item: v1.EvalItem) -> tuple[dict[str, Any], dict[str, Any], Path, int]:
    """One sandboxed OMPS attempt on the item's folder: (result, verdict, attempt dir, stalls)."""
    base_dir = context.output / "attempts" / rla.safe_key(item.run_key)
    tries = len(list(base_dir.glob("try-*"))) if base_dir.is_dir() else 0
    attempt_dir = base_dir / f"try-{tries + 1}"
    config = context.proxy
    if context.session_header:
        config = rlm.with_session(config, context.session_header, session_id(context.model, item.run_key, tries + 1))
    result = rlo.run_sandboxed(context.omp, context.docs_for(item), attempt_dir, item.prompt, config,
                               rlo.rules_for(context.omp_protocol, item.prompt),
                               context.omp_protocol["proxy"]["wall_clock_seconds"])
    stalls = mark_stalls(result["records"])
    return result, rlo.classify(result), attempt_dir, stalls


def agent_row(item: v1.EvalItem, context: AttemptContext, shard: int, lane: int) -> dict[str, Any]:
    spec, proxy = context.omp_protocol["harness"], context.proxy
    key = f"{item.dataset_id}:{item.item_id}"
    return {
        "run_key": item.run_key, "item_key": key, "dataset_id": item.dataset_id, "item_id": item.item_id,
        "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id), "part": rl2.part_of(item),
        "harness": "omp", "corpus": context.corpus_of.get(key), "phase": lp.PHASE, "profile_id": context.profile_id,
        "protocol_id": lp.PROTOCOL_ID, "measurement_card_id": context.card_id, "model_id": proxy.model,
        "transport": "omp-json", "api_protocol": spec["api_protocol"], "shard": shard, "lane": lane,
        "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")), "raw_prompt": item.prompt, "raw_response": "",
        "temperature_sent": proxy.temperature, "reasoning_effort_sent": None, "seed_sent": None,
        "max_tokens": spec.get("max_completion_tokens") or spec.get("max_tokens"),
    }


def blocked_row(item: v1.EvalItem, context: AttemptContext, shard: int, lane: int, error_type: str) -> dict[str, Any]:
    """A row written without a request, with every identity field the engine and `--resume` read."""
    now = pr.base.now()
    return {**agent_row(item, context, shard, lane), "status": "request_error", "outcome": "technical",
            "finish_reason": "error", "error_type": error_type, "fatal": True, "latency_s": 0.0,
            "started_at": now, "finished_at": now}


def make_request(card_id: str, model: str, guard: pr.BudgetGuard, outage: pr.OutageGuard, max_in_flight: int,
                 bad: rlm.BadRequests):
    """The engine's request function: one gate, the shared guards, then one OMPS attempt."""
    gate = threading.BoundedSemaphore(max_in_flight)
    halt = threading.Event()

    def request(context: AttemptContext, item: v1.EvalItem, shard: int, lane: int) -> dict[str, Any]:
        with gate:  # waiting here is not part of the measured time
            for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                        (halt.is_set(), "halted_before_send")):
                if blocked:
                    halt.set()
                    return blocked_row(item, context, shard, lane, error_type)
            row = agent_row(item, context, shard, lane)
            row["started_at"] = pr.base.now()
            result, verdict, attempt_dir, stalls = run_agent(context, item)
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
            row.update({key: source.get(key) for key in ("part", "harness", "corpus", "outcome", "attempt_dir",
                                                       "requests", "requests_forwarded", "tool_calls", "stalls",
                                                       "reasoning_tokens", "cached_prompt_tokens",
                                                       "max_completion_tokens_used")})
            final.append(rl2.rescore(row))
        v1.write_jsonl_atomic(output / "scores.jsonl", final)
        outcomes = Counter((str(row.get("arm")), str(row.get("outcome"))) for row in rows.values())
        summary = {
            "protocol_id": lp.PROTOCOL_ID, "phase": lp.PHASE, "measurement_card_id": card_id, "model": model,
            "model_id": pr.base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": pr.base.now(),
            "expected_n": len(manifest["items"]), "by_part_arm": rl2.summarize(final),
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

def load_registration(path: Path = lp.REGISTRATION_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


BUDGET_AMENDMENT_KEYS = frozenset({"id", "rule", "date", "budget_tokens", "basis", "authorized"})


def budget_tokens(spec: dict[str, Any], registration: dict[str, Any], model: str) -> int:
    """The model's budget guard: the protocol's, or the registration's `budget_tokens` amendment (MC-117 amendment 1).
    The guard only decides when a run stops; it is not part of the inference condition, so the condition file keeps the
    protocol's value and `--resume` is not refused. An amendment may only raise a model's budget."""
    found = [a for a in registration.get("amendments") or [] if isinstance(a, dict) and a.get("rule") == "budget_tokens"]
    if not found:
        return int(spec["budget_tokens"])
    amendment = found[0]
    value = (amendment.get("budget_tokens") or {}).get(model) if isinstance(amendment.get("budget_tokens"), dict) else None
    if (len(found) > 1 or set(amendment) != BUDGET_AMENDMENT_KEYS or not isinstance(value, int)
            or isinstance(value, bool) or value < int(spec["budget_tokens"])):
        raise _fail(f"the budget_tokens amendment must appear once with exactly the keys {sorted(BUDGET_AMENDMENT_KEYS)} "
                    f"and an integer budget for {model} no lower than the protocol's {spec['budget_tokens']}")
    return value


def smoke_problems(protocol: dict[str, Any], model: str, root: Path = ROOT) -> list[str]:
    """The model's registered smoke reports: each hashes as registered, every attempt completed, and the first
    system message matched the model's pin."""
    reports = protocol["smoke"]["reports"].get(model) or []
    if not reports:
        return [f"no {model} smoke report is registered"]
    pin = lp.model_spec(protocol, model)["system_prompt_sha256"]
    problems = []
    for spec in reports:
        path = root / spec["path"]
        if not path.is_file() or v1.sha256_file(path) != spec["sha256"]:
            problems.append(f"smoke report {path} is missing or differs from its registered SHA-256")
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row["status"] != "complete" or row.get("system_prompt_sha256") != [pin]:
                problems.append(f"smoke {row['id']}: status {row['status']}, system prompt "
                                f"{row.get('system_prompt_sha256')} against the pin {pin}")
    return problems


def evaluate_gates(protocol: dict[str, Any], model: str, omp_protocol: dict[str, Any], manifest: dict[str, Any],
                   registration: dict[str, Any], route_problems: list[str], problems: list[str]) -> list[pr.Gate]:
    spec = lp.model_spec(protocol, model)
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8")
    card_id = (registration.get("card_ids") or {}).get(lp.PHASE)
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    card_file = (registration.get("card_files") or {}).get(lp.PHASE)
    frozen = registration.get("frozen") or {}
    differing = [name for name in rl2.hash_keys(manifest) if frozen.get(name) != manifest.get(name)]
    smoke = smoke_problems(protocol, model)
    pins = [omp_protocol["proxy"].get("expected_response_model"), omp_protocol["proxy"].get("system_prompt_sha256")]
    return [
        pr.Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md"),
        pr.Gate("detail_card", bool(card_file) and (ROOT / str(card_file)).is_file(), str(card_file or "none")),
        pr.Gate("frozen_hashes", bool(frozen) and not differing, "all match" if frozen and not differing
                else f"differ: {differing[:6]}"),
        pr.Gate("endpoint_identity", not route_problems, "; ".join(route_problems) or f"{model}: {spec['model_id']}"),
        pr.Gate("budget_set", isinstance(spec.get("budget_tokens"), int), f"{model} budget_tokens is set"),
        pr.Gate("smoke_passed", not smoke, "; ".join(smoke[:3]) or f"every registered {model} smoke attempt completed"),
        pr.Gate("pins_set", all(pins), "omp's response model and the OMPS system prompt"),
        pr.Gate("harness_and_folders", not problems, "; ".join(problems) or "pins, folders and manifest match"),
    ]


def build_condition(protocol: dict[str, Any], model: str, omp_protocol: dict[str, Any], manifest: dict[str, Any],
                    registration: dict[str, Any], endpoint: str) -> dict[str, Any]:
    module = Path(__file__).resolve().parent
    return {
        "protocol_id": lp.PROTOCOL_ID, "protocol_version": 1, "phase": lp.PHASE, "model": model,
        "measurement_card_id": registration["card_ids"][lp.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][lp.PHASE]),
        **{name: manifest[name] for name in rl2.hash_keys(manifest)},
        "arm_counts": manifest["arm_counts"], "dataset_counts": manifest["dataset_counts"],
        "corpora": {name: spec["folder_sha256"] for name, spec in protocol["corpora"].items()},
        "operational": protocol["operational"], "model_spec": lp.model_spec(protocol, model),
        "omp": {"harness": omp_protocol["harness"], "proxy": omp_protocol["proxy"]},
        "endpoint_host": urlsplit(endpoint).hostname, "base_url_sha256": v1.sha256_bytes(endpoint.encode()),
        "workdir": protocol["workdir"],
        "scorer_sha256": v1.sha256_file(module / "score_vi_multimodel.py"),
        "reading_v3_sha256": v1.sha256_file(Path(str(v3.__file__))),
        "wrapper_sha256": v1.sha256_file(Path(str(dp.__file__))), "engine_sha256": v1.sha256_file(Path(str(pr.__file__))),
        "legal_agent_module_sha256": v1.sha256_file(Path(str(la.__file__))),
        "legal_agent_v2_module_sha256": v1.sha256_file(Path(str(l2.__file__))),
        "legal_agent_draws_module_sha256": v1.sha256_file(Path(str(ld.__file__))),
        "legal_agent_mimo_module_sha256": v1.sha256_file(Path(str(lm.__file__))),
        "legal_agent_omp_prompt_module_sha256": v1.sha256_file(Path(str(lp.__file__))),
        "trajectory_sha256": v1.sha256_file(Path(str(ot.__file__))), "proxy_sha256": v1.sha256_file(Path(str(px.__file__))),
        "relay_sha256": v1.sha256_file(rla.RELAY), "mc112_runner_sha256": v1.sha256_file(Path(str(rla.__file__))),
        "mc113_runner_sha256": v1.sha256_file(Path(str(rlo.__file__))),
        "mc114_runner_sha256": v1.sha256_file(Path(str(rl2.__file__))),
        "mc115_runner_sha256": v1.sha256_file(Path(str(rld.__file__))),
        "mc116_runner_sha256": v1.sha256_file(Path(str(rlm.__file__))), "runner_sha256": v1.sha256_file(Path(__file__)),
    }


# ---------------------------------------------------------------- self-test and smoke test

def first_system(records: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """The first request's system message text, and its SHA-256 as the proxy computes it."""
    bodies = [json.loads(r["body_received"]) for r in records if r.get("body_received")][:1]
    if not bodies:
        return "", []
    messages = bodies[0].get("messages") or []
    text = str(messages[0].get("content") or "") if messages and messages[0].get("role") == "system" else ""
    return text, sorted({str(rlo.system_sha256(messages))})


def selftest(protocol: dict[str, Any], model: str, omp_protocol: dict[str, Any], omp: rlo.Harness) -> bool:
    """OMPS end to end against a scripted server, offline: an MC task and a span task. The first system message must
    begin with dsh's prompt and keep omp's <critical> block; every request carries the model's cap."""
    smoke = json.loads(rla.SMOKE_PATH.read_text(encoding="utf-8"))
    prompts = l2.load_prompts()
    text = lp.prompt_text(protocol, model)
    cap = omp_protocol["harness"]["max_completion_tokens"]
    provision = {"file": rl2.SELFTEST_FILE, "anchor_line": "Điều 2. Hội viên"}
    ok = True
    with tempfile.TemporaryDirectory(prefix="mc117-selftest-") as tmp:
        docs = Path(tmp) / "docs"
        docs.mkdir()
        for name, body in smoke["synthetic_folder"].items():
            (docs / name).write_text(body, encoding="utf-8")
        cases = [case for case in rl2.selftest_cases(prompts, smoke["questions"][0]["prompt"]) if case[1] == "omp"]
        for label, _, task, script, expected in cases:
            with rlo.ScriptedUpstream(script) as upstream:
                config = px.ProxyConfig(upstream=upstream.url, api_key="selftest-key",
                                        model=lp.model_spec(protocol, model)["model_id"],
                                        expected_response_model="fake-model.gguf", request_cap=30,
                                        extra_headers={"x-opencode-session": "selftest"})
                rules = dataclasses.replace(rlo.rules_for(omp_protocol, task), system_sha256=None)
                result = rlo.run_sandboxed(omp, docs, Path(tmp) / label, task, config, rules, 300)
                verdict, observations = rlo.classify(result), ot.omp_observations(result["records"])
                sent = list(upstream.requests)
            system, digest = first_system(result["records"])
            hits = la.provision_hits(observations, [provision])[0]
            caps = {body.get("max_completion_tokens") for body in sent}
            good = ((verdict["status"], verdict["outcome"], verdict["raw_response"]) == ("complete", "complete", expected)
                    and system.startswith(text) and "<critical>" in system and caps == {cap} and all(hits.values()))
            if label.endswith("span"):
                good &= v3.score_reading(verdict["raw_response"], "100.000 đồng")["token_f1"] == 1.0
            ok &= good
            print(f"selftest {model} {label}: status={verdict['status']} requests={len(result['records'])} "
                  f"system_chars={len(system)} system_sha256={digest} caps={sorted(caps, key=str)} hits={hits} "
                  f"{'PASS' if good else 'FAIL'}", flush=True)
    return ok


def smoke_test(protocol: dict[str, Any], model: str, omp_protocol: dict[str, Any], omp: rlo.Harness,
               docs: dict[str, Path], route: Route) -> Path:
    """Each registered smoke question once with OMPS. No score. It records what sets the pin and the budget: the
    first system message's SHA-256, response models, body keys, statuses, stalls and tokens."""
    prompts = l2.load_prompts()
    out = SMOKE_ROOT / model / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True)
    bad = rlm.BadRequests()
    report = []
    for question, corpus in rld.load_smoke(protocol):
        task = rld.smoke_task(question, prompts)
        config = route.proxy
        if route.session_header:
            config = rlm.with_session(config, route.session_header, session_id(model, f"smoke:{question['id']}", 1))
        rules = dataclasses.replace(rlo.rules_for(omp_protocol, task), system_sha256=None)
        result = rlo.run_sandboxed(omp, docs[corpus], out / question["id"], task, config, rules,
                                   omp_protocol["proxy"]["wall_clock_seconds"])
        stalls = mark_stalls(result["records"])
        verdict = rlo.classify(result)
        if model == "mimo":
            verdict = rlm.provider_verdict(verdict, result["records"], f"smoke:{question['id']}", bad)
        seen = px.attempt_outcome(result["records"])
        received = [json.loads(r["body_received"]) for r in result["records"] if r.get("body_received")]
        system, digest = first_system(result["records"])
        report.append({
            "id": question["id"], "kind": question.get("kind", "mc"), "corpus": corpus, "arm": lp.ARM, "model": model,
            "status": verdict["status"], "outcome": verdict["outcome"], "error_type": verdict["error_type"],
            "final_text": verdict["raw_response"], "wall_s": result["wall_s"], "requests": seen["requests"],
            "proxy_outcomes": seen["outcomes"], "stalls": stalls,
            "http_statuses": sorted({str(r.get("status")) for r in result["records"]}),
            "tool_calls": rla.tool_counts(result["records"]),
            "hits": la.provision_hits(ot.omp_observations(result["records"]), question.get("provisions") or []),
            "system_prompt_sha256": digest, "system_chars": len(system),
            "system_starts_with_dsh_prompt": system.startswith(lp.prompt_text(protocol, model)),
            "offline_capture_matches": digest == [lp.model_spec(protocol, model)["offline_capture_system_sha256"]],
            "body_keys": sorted({key for body in received for key in body}),
            "response_models": seen["response_models"], "prompt_tokens": seen["prompt_tokens"],
            "completion_tokens": seen["completion_tokens"], "total_tokens": seen["total_tokens"],
            **rlm.usage_details(result["records"]),
        })
    (out / "smoke_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, choices=lp.MODELS)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="re-run only attempts with technical failures")
    ap.add_argument("--selftest", action="store_true", help="OMPS end to end against a scripted server")
    ap.add_argument("--smoke", action="store_true", help="with --execute: the smoke test of design §5")
    ap.add_argument("--no-rebuild", action="store_true", help="preflight and smoke only: skip corpus_v2's fresh rebuild")
    ap.add_argument("--tunnel-dns", default="", help="Qwen: resolve the IEC host through this in-tunnel DNS server")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    if args.no_rebuild and args.execute and not args.smoke:
        ap.error("--no-rebuild is for the preflight and the smoke test only")
    model = args.model
    protocol = lp.load_protocol()
    spec = lp.model_spec(protocol, model)
    omp_protocol = lp.omp_protocol(protocol, model)
    omp, harness_problems = rlo.check_harness(omp_protocol)
    problems = [f"omp: {p}" for p in harness_problems]
    if args.selftest:
        if problems:
            raise _fail("; ".join(problems))
        return 0 if selftest(protocol, model, omp_protocol, omp) else 1
    docs, folder_problems = rld.check_folders(protocol, rebuild=not args.no_rebuild)
    problems += folder_problems
    route = resolve_route(protocol, model, omp_protocol, resolve=args.execute)
    if args.execute and model == "qwen" and args.tunnel_dns:
        host = urlsplit(route.endpoint).hostname or ""
        print(f"resolver shim (this process only): {host} -> {pr.install_resolver_shim(host, args.tunnel_dns)} "
              f"via {args.tunnel_dns}", flush=True)
    if args.smoke:
        if not args.execute:
            ap.error("--smoke requires --execute")
        if problems or route.problems:
            raise _fail("the smoke test needs the pinned harness, both folders and the route: "
                        + "; ".join(problems + route.problems))
        out = smoke_test(protocol, model, omp_protocol, omp, docs, route)
        print(f"smoke test -> {out / 'smoke_report.json'}")
        return 0
    manifest, rebuilt = lp.build_manifest(protocol)
    if lp.MANIFEST_PATH.is_file() and lp.load_frozen_manifest() != manifest:
        problems.append("the rebuilt manifest differs from manifest_v1.json")
    elif not lp.MANIFEST_PATH.is_file():
        problems.append("manifest_v1.json is not frozen yet")
    dp.verify_manifest_rows(manifest, rebuilt)
    registration = load_registration()
    gates = evaluate_gates(protocol, model, omp_protocol, manifest, registration,
                           route.problems if args.execute else [p for p in route.problems if "offline" not in p],
                           problems)
    print(f"phase={lp.PHASE} model={model} items={manifest['item_count']} attempts={manifest['n']} "
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
    card_id = str(registration["card_ids"][lp.PHASE])
    output = OUTPUT_ROOT / spec["profile_id"]
    resume = bool(args.resume) and (output / "condition.json").is_file()
    condition = pr.reconcile_resume(output, build_condition(protocol, model, omp_protocol, manifest, registration,
                                                            route.endpoint), resume)
    budget = budget_tokens(spec, registration, model)
    guard = pr.BudgetGuard(budget, pr.existing_usage(output))
    print(f"budget_tokens={budget} used={guard.used} model={model}", flush=True)
    outage = pr.OutageGuard(operational["stop_after_timeouts"])
    pr.base.MODEL, pr.base.PROFILE, pr.base.PROTOCOL, pr.base.CARD_ID = (
        route.proxy.model, spec["profile_id"], lp.PROTOCOL_ID, card_id)
    pr.base.request = make_request(card_id, model, guard, outage, operational["max_in_flight"], rlm.BadRequests())
    output.mkdir(parents=True, exist_ok=True)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": pr.base.now(), "model": model, "resume": resume,
                                 "runner_sha256": v1.sha256_file(Path(__file__)), "operational": operational,
                                 "budget_tokens": budget, "note": args.note}, ensure_ascii=False) + "\n")
    items = dp.verify_manifest_rows(manifest, rebuilt)
    context = AttemptContext(model=model, omp=omp, omp_protocol=omp_protocol, docs=docs,
                             corpus_of=manifest["corpus_of"], output=output, proxy=route.proxy,
                             session_header=route.session_header, profile_id=spec["profile_id"], card_id=card_id)
    # the engine hands `context` to the request function as its client, as in MC-114's to MC-116's runners
    pr.base.execute(output, manifest, rebuilt, items, condition, context,  # pyright: ignore[reportArgumentType]
                    resume, score_callback=score_callback(card_id, model), runner_path=Path(__file__))
    status = json.loads((output / "run.json").read_text(encoding="utf-8"))["status"]
    print(f"status={status} model={model} output={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
