"""Run MC-115 (openspec change diagnostic-legal-agent-draws): draws 3 and 4 of DSHF, OMPF and each part's no-tool
baseline (B on Part M, C on Part S) on MC-114's 646 analysis items, each in the condition of its draws 1-2.

From the repo root:
  .venv/bin/python -m code_benchmark.run_legal_agent_draws                    # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_legal_agent_draws --selftest         # both harnesses against fake servers
  .venv/bin/python -m code_benchmark.run_legal_agent_draws --smoke --execute  # design §5, needs the VPN
  .venv/bin/python -m code_benchmark.run_legal_agent_draws --execute [--resume] [--tunnel-dns <in-tunnel DNS server>]

Agent attempts go through MC-112's (dsh) and MC-113's (omp) code unchanged, as MC-114 used it; the only difference
from MC-114's runner is the folder, chosen per item: corpus_v1 for the Legal MC items (as MC-112/113 ran them),
corpus_v2 for the others (as MC-114 ran them). Direct arms send the campaign request of MC-90 to MC-114.

Scoring: Part M by the frozen MC scorer; Part S by vi-reading-v3 (token-F1 primary), with the v2 values kept beside.
Terminal outcomes score 0 and stay in the denominator; only technical failures are re-run, by `--resume`.
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

try:
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_agent_draws as ld
    from code_benchmark import diagnostic_legal_agent_v2 as l2
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import dsh_proxy as px
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_legal_agent as rla
    from code_benchmark import run_legal_agent_omp as rlo
    from code_benchmark import run_legal_agent_v2 as rl2
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_reading_v3 as v3
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_draws as ld  # type: ignore[no-redef]
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import dsh_proxy as px  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import run_diagnostic_prospective as pr  # type: ignore[no-redef]
    import run_legal_agent as rla  # type: ignore[no-redef]
    import run_legal_agent_omp as rlo  # type: ignore[no-redef]
    import run_legal_agent_v2 as rl2  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]
    import vi_reading_v3 as v3  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ld.WORK_ROOT / "run"
SMOKE_ROOT = ld.WORK_ROOT / "smoke"
PROFILE_ID = "qwen3-5-9b-65k-legal-agent-draws"
CARD_ID = "MC-115"
HARNESS_OF = {"DSHF": "dsh", "OMPF": "omp", "B": "direct", "C": "direct"}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def harness_of(arm: str) -> str:
    if arm not in HARNESS_OF:
        raise _fail(f"arm {arm!r} has no path in MC-115")
    return HARNESS_OF[arm]


# ---------------------------------------------------------------- folders

def check_folders(protocol: dict[str, Any], *, rebuild: bool = True, root: Path = ROOT) -> tuple[dict[str, Path], list[str]]:
    """{corpus name: docs directory}, and what differs: each listing hash, and corpus_v2's fresh rebuild."""
    docs, problems = {}, []
    for name, spec in protocol["corpora"].items():
        path = ld.docs_dir(protocol, name, root)
        docs[name] = path
        if not path.is_dir() or rla.listing_sha256(path) != spec["folder_sha256"]:
            problems.append(f"corpus {name}: {path} does not hash to the registered folder SHA-256")
        if rebuild and spec.get("rebuild"):
            with tempfile.TemporaryDirectory(prefix="mc115-rebuild-") as tmp:
                built = l2.build_corpus(Path(tmp) / "f")
                if built["folder_sha256"] != spec["folder_sha256"]:
                    problems.append(f"corpus {name}: a fresh rebuild hashes to {built['folder_sha256'][:12]}")
    return docs, problems


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
    client: Any = None  # the OpenAI client of the direct arms

    def docs_for(self, item: v1.EvalItem) -> Path:
        key = f"{item.dataset_id}:{item.item_id}"
        if key not in self.corpus_of:
            raise _fail(f"{key} has no corpus in the manifest")
        return self.docs[self.corpus_of[key]]


def run_agent(context: AttemptContext, item: v1.EvalItem, harness: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """One sandboxed attempt through MC-112's (dsh) or MC-113's (omp) path, on the item's folder."""
    base_dir = context.output / "attempts" / rla.safe_key(item.run_key)
    tries = len(list(base_dir.glob("try-*"))) if base_dir.is_dir() else 0
    attempt_dir = base_dir / f"try-{tries + 1}"
    docs = context.docs_for(item)
    if harness == "dsh":
        result = rla.run_sandboxed(context.dsh, docs, attempt_dir, item.prompt, context.dsh_proxy,
                                   context.dsh_protocol["proxy"]["wall_clock_seconds"])
        return result, rla.classify(result), attempt_dir
    result = rlo.run_sandboxed(context.omp, docs, attempt_dir, item.prompt, context.omp_proxy,
                               rlo.rules_for(context.omp_protocol, item.prompt),
                               context.omp_protocol["proxy"]["wall_clock_seconds"])
    return result, rlo.classify(result), attempt_dir


def agent_row(item: v1.EvalItem, context: AttemptContext, harness: str, shard: int, lane: int) -> dict[str, Any]:
    spec = (context.dsh_protocol if harness == "dsh" else context.omp_protocol)["harness"]
    proxy = context.dsh_proxy if harness == "dsh" else context.omp_proxy
    return {
        "run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
        "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
        "part": rl2.part_of(item), "harness": harness, "corpus": context.corpus_of[f"{item.dataset_id}:{item.item_id}"],
        "phase": ld.PHASE, "profile_id": PROFILE_ID, "protocol_id": ld.PROTOCOL_ID, "measurement_card_id": CARD_ID,
        "model_id": proxy.model, "transport": "dsh-headless" if harness == "dsh" else "omp-json",
        "api_protocol": spec["api_protocol"], "shard": shard, "lane": lane,
        "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")), "raw_prompt": item.prompt, "raw_response": "",
        "temperature_sent": proxy.temperature, "reasoning_effort_sent": None, "seed_sent": None,
        "max_tokens": spec.get("max_tokens") or spec.get("max_completion_tokens"),
    }


def make_request(campaign: dict[str, Any], card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard,
                 max_in_flight: int, direct: Any = None):
    """The engine's request function: one gate over all paths, the shared guards, then the arm's path."""
    gate = threading.BoundedSemaphore(max_in_flight)
    halt = threading.Event()
    direct = direct or pr.make_request(campaign, ld.PHASE, card_id, guard, outage=outage)

    def request(context: AttemptContext, item: v1.EvalItem, shard: int, lane: int) -> dict[str, Any]:
        harness = harness_of(dp.arm_of_replicate(item.replicate_id))
        with gate:  # waiting here is not part of the measured time
            for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                        (halt.is_set(), "halted_before_send")):
                if blocked:
                    halt.set()
                    return {"run_key": item.run_key, "dataset_id": item.dataset_id, "item_id": item.item_id,
                            "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
                            "part": rl2.part_of(item), "harness": harness, "phase": ld.PHASE,
                            "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")), "raw_response": "",
                            "status": "request_error", "finish_reason": "error", "error_type": error_type,
                            "fatal": True, "latency_s": 0.0, "started_at": pr.base.now(), "finished_at": pr.base.now()}
            if harness == "direct":
                row = {**direct(context.client, item, shard, lane), "part": rl2.part_of(item), "harness": harness}
                if row.get("fatal"):
                    halt.set()
                return row  # the campaign request has already counted tokens and outages
            row = agent_row(item, context, harness, shard, lane)
            row["started_at"] = pr.base.now()
            result, verdict, attempt_dir = run_agent(context, item, harness)
        row = rl2.finish_agent_row(row, result, verdict, attempt_dir, context.output)
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

def score_callback(card_id: str):
    def score(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        scored, summaries = dp.score_arm_rows(manifest, rows, rebuilt)
        final = []
        for row in scored:
            source = rows.get(dp.run_key(row)) or {}
            row.update({key: source.get(key) for key in ("part", "harness", "corpus", "outcome", "attempt_dir",
                                                       "requests", "requests_forwarded", "tool_calls")})
            final.append(rl2.rescore(row))
        v1.write_jsonl_atomic(output / "scores.jsonl", final)
        outcomes = Counter((str(row.get("arm")), str(row.get("outcome"))) for row in rows.values())
        pr.base.atomic_json(output / "summary.json", {
            "protocol_id": ld.PROTOCOL_ID, "phase": ld.PHASE, "measurement_card_id": card_id,
            "model_id": pr.base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": pr.base.now(),
            "expected_n": len(manifest["items"]), "by_part_arm": rl2.summarize(final),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "outcomes": {f"{arm}:{outcome}": count for (arm, outcome), count in sorted(outcomes.items())},
            "cost_usd": None, "cost_basis": "IEC tariff not supplied; reported usage retained per attempt",
        })
    return score


# ---------------------------------------------------------------- registration and condition

def load_registration(path: Path = ld.REGISTRATION_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def smoke_problems(protocol: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Registered smoke reports: each must hash as registered and every attempt in it must have completed with
    omp's registered system prompt."""
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
            if row["status"] != "complete" or row.get("system_prompt_matches_mc113") is False:
                problems.append(f"smoke {row['id']} {row['harness']}: status {row['status']}, "
                                f"omp system prompt match {row.get('system_prompt_matches_mc113')}")
    return problems


def evaluate_gates(protocol: dict[str, Any], dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any],
                   manifest: dict[str, Any], registration: dict[str, Any], env: dict[str, str | None],
                   problems: list[str]) -> list[pr.Gate]:
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8")
    card_id = (registration.get("card_ids") or {}).get(ld.PHASE)
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    card_file = (registration.get("card_files") or {}).get(ld.PHASE)
    frozen = registration.get("frozen") or {}
    differing = [name for name in rl2.hash_keys(manifest) if frozen.get(name) != manifest.get(name)]
    campaign = dp.load_protocol()["model"]
    endpoint = urlsplit(env.get("OPENAI_BASE_URL") or "")
    identity = (endpoint.hostname == campaign["endpoint_host"]
                and endpoint.path.rstrip("/") == campaign["endpoint_path"].rstrip("/")
                and env.get("OPENAI_MODEL") == campaign["requested_id"] and bool(env.get("OPENAI_API_KEY")))
    pins = [dsh_protocol["proxy"].get("expected_response_model"), omp_protocol["proxy"].get("expected_response_model"),
            omp_protocol["proxy"].get("system_prompt_sha256")]
    smoke = smoke_problems(protocol)
    return [
        pr.Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md"),
        pr.Gate("detail_card", bool(card_file) and (ROOT / str(card_file)).is_file(), str(card_file or "none")),
        pr.Gate("frozen_hashes", bool(frozen) and not differing, "all match" if frozen and not differing
                else f"differ: {differing[:6]}"),
        pr.Gate("endpoint_identity", identity, f"model={env.get('OPENAI_MODEL')} (expects {campaign['requested_id']})"),
        pr.Gate("budget_set", isinstance(protocol["operational"].get("budget_tokens"), int), "budget_tokens is set"),
        pr.Gate("smoke_passed", not smoke, "; ".join(smoke[:3]) or "every registered smoke attempt completed"),
        pr.Gate("reused_pins_set", all(pins), "MC-112's and MC-113's response models and omp's system prompt"),
        pr.Gate("harness_and_folders", not problems, "; ".join(problems) or "pins, folders and manifest match"),
    ]


def build_condition(protocol: dict[str, Any], dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any],
                    manifest: dict[str, Any], registration: dict[str, Any], endpoint: str) -> dict[str, Any]:
    module = Path(__file__).resolve().parent
    campaign = dp.load_protocol()
    return {
        "protocol_id": ld.PROTOCOL_ID, "protocol_version": 1, "phase": ld.PHASE,
        "measurement_card_id": registration["card_ids"][ld.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][ld.PHASE]),
        **{name: manifest[name] for name in rl2.hash_keys(manifest)},
        "arm_counts": manifest["arm_counts"], "dataset_counts": manifest["dataset_counts"],
        "corpora": {name: spec["folder_sha256"] for name, spec in protocol["corpora"].items()},
        "operational": protocol["operational"], "model_id": campaign["model"]["requested_id"], "profile_id": PROFILE_ID,
        "dsh": {"harness": dsh_protocol["harness"], "proxy": dsh_protocol["proxy"]},
        "omp": {"harness": omp_protocol["harness"], "proxy": omp_protocol["proxy"]},
        "direct": {"api_protocol": campaign["transport"]["api_protocol"],
                   "system_prompt": campaign["transport"]["system_prompt"],
                   "temperature": campaign["transport"]["temperature"],
                   "max_output_tokens": campaign["transport"]["max_output_tokens"],
                   "expected_response_model": campaign["model"]["self_reported_id"]},
        "endpoint_host": urlsplit(endpoint).hostname, "base_url_sha256": v1.sha256_bytes(endpoint.encode()),
        "workdir": protocol["workdir"],
        "scorer_sha256": v1.sha256_file(module / "score_vi_multimodel.py"),
        "reading_v3_sha256": v1.sha256_file(Path(v3.__file__)),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)), "engine_sha256": v1.sha256_file(Path(pr.__file__)),
        "legal_agent_module_sha256": v1.sha256_file(Path(la.__file__)),
        "legal_agent_v2_module_sha256": v1.sha256_file(Path(l2.__file__)),
        "legal_agent_draws_module_sha256": v1.sha256_file(Path(ld.__file__)),
        "trajectory_sha256": v1.sha256_file(Path(str(ot.__file__))), "proxy_sha256": v1.sha256_file(Path(px.__file__)),
        "relay_sha256": v1.sha256_file(rla.RELAY), "mc112_runner_sha256": v1.sha256_file(Path(rla.__file__)),
        "mc113_runner_sha256": v1.sha256_file(Path(rlo.__file__)),
        "mc114_runner_sha256": v1.sha256_file(Path(rl2.__file__)), "runner_sha256": v1.sha256_file(Path(__file__)),
    }


# ---------------------------------------------------------------- smoke test

def load_smoke(protocol: dict[str, Any], root: Path = ROOT) -> list[tuple[dict[str, Any], str]]:
    """[(question, corpus name)] from the registered smoke files, by id."""
    out = []
    for spec in protocol["smoke"]["questions"]:
        questions = json.loads((root / spec["file"]).read_text(encoding="utf-8"))["questions"]
        match = [q for q in questions if q["id"] == spec["id"]]
        if len(match) != 1:
            raise _fail(f"smoke question {spec['id']} is not in {spec['file']} exactly once")
        out.append((match[0], spec["corpus"]))
    return out


def smoke_task(question: dict[str, Any], prompts: dict[str, Any]) -> str:
    """DSHF's task for a smoke question (OMPF sends it byte for byte): MC-112's layout around the MC prompt, or
    around MC-96's closed-book prompt for a span question."""
    if question.get("kind") == "span":
        return l2.agent_task("DSHF", l2.closed_book_prompt(question["question"], prompts), prompts)
    return l2.agent_task("DSHF", question["prompt"], prompts)


def smoke_test(protocol: dict[str, Any], dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any],
               dsh: rla.Harness, omp: rlo.Harness, docs: dict[str, Path], endpoint: str, key: str) -> Path:
    """Design §5: each smoke question once with DSHF and once with OMPF on its folder. No score is computed; omp's
    system-prompt hash is recorded and compared with MC-113's."""
    prompts = l2.load_prompts()
    campaign = dp.load_protocol()
    out = SMOKE_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True)
    configs = {"dsh": rl2.proxy_config(dsh_protocol["proxy"], endpoint, key, campaign),
               "omp": rl2.proxy_config(omp_protocol["proxy"], endpoint, key, campaign)}
    report = []
    for question, corpus in load_smoke(protocol):
        task = smoke_task(question, prompts)
        for harness in ("dsh", "omp"):
            attempt = out / f"{question['id']}-{harness}"
            if harness == "dsh":
                result = rla.run_sandboxed(dsh, docs[corpus], attempt, task, configs["dsh"],
                                           dsh_protocol["proxy"]["wall_clock_seconds"])
                verdict, observations = rla.classify(result), la.model_observations(result["records"])
            else:
                rules = dataclasses.replace(rlo.rules_for(omp_protocol, task), system_sha256=None)
                result = rlo.run_sandboxed(omp, docs[corpus], attempt, task, configs["omp"], rules,
                                           omp_protocol["proxy"]["wall_clock_seconds"])
                verdict, observations = rlo.classify(result), ot.omp_observations(result["records"])
            seen = px.attempt_outcome(result["records"])
            received = [json.loads(r["body_received"]) for r in result["records"] if r.get("body_received")]
            system = sorted({str(rlo.system_sha256(body.get("messages") or [])) for body in received[:1]})
            report.append({
                "id": question["id"], "kind": question.get("kind", "mc"), "corpus": corpus, "harness": harness,
                "status": verdict["status"], "outcome": verdict["outcome"], "error_type": verdict["error_type"],
                "final_text": verdict["raw_response"], "wall_s": result["wall_s"], "requests": seen["requests"],
                "proxy_outcomes": seen["outcomes"], "tool_calls": rla.tool_counts(result["records"]),
                "hits": la.provision_hits(observations, question.get("provisions") or []),
                "system_prompt_sha256": system if harness == "omp" else None,
                "system_prompt_matches_mc113": (system == [omp_protocol["proxy"]["system_prompt_sha256"]]
                                                if harness == "omp" else None),
                "response_models": seen["response_models"], "prompt_tokens": seen["prompt_tokens"],
                "completion_tokens": seen["completion_tokens"], "total_tokens": seen["total_tokens"],
            })
    (out / "smoke_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    from dotenv import dotenv_values
    from openai import OpenAI

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="re-run only attempts with technical failures")
    ap.add_argument("--selftest", action="store_true", help="both harnesses end to end against fake servers")
    ap.add_argument("--smoke", action="store_true", help="with --execute: the smoke test of design §5")
    ap.add_argument("--no-rebuild", action="store_true", help="preflight and smoke only: skip corpus_v2's fresh rebuild")
    ap.add_argument("--tunnel-dns", default=None, help="in-tunnel DNS server for the endpoint host (this process only)")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    if args.no_rebuild and args.execute and not args.smoke:
        ap.error("--no-rebuild is for the preflight and the smoke test only")
    protocol = ld.load_protocol()
    dsh_protocol, omp_protocol = rl2.harness_protocols(protocol)
    dsh, omp, problems = rl2.check_harnesses(dsh_protocol, omp_protocol)
    if args.selftest:
        if problems:
            raise _fail("; ".join(problems))
        return 0 if rl2.selftest(dsh_protocol, omp_protocol, dsh, omp) else 1
    docs, folder_problems = check_folders(protocol, rebuild=not args.no_rebuild)
    problems += folder_problems
    env = dotenv_values(ROOT / ".env")
    endpoint, key = str(env.get("OPENAI_BASE_URL") or ""), str(env.get("OPENAI_API_KEY") or "")
    if args.smoke:
        if not args.execute:
            ap.error("--smoke requires --execute")
        if args.tunnel_dns:
            pr.install_resolver_shim(urlsplit(endpoint).hostname or "", args.tunnel_dns)
        if problems:
            raise _fail("the smoke test needs the pinned harnesses and both folders: " + "; ".join(problems))
        out = smoke_test(protocol, dsh_protocol, omp_protocol, dsh, omp, docs, endpoint, key)
        print(f"smoke test -> {out / 'smoke_report.json'}")
        return 0
    manifest, rebuilt = ld.build_manifest(protocol)
    if ld.MANIFEST_PATH.is_file() and ld.load_frozen_manifest() != manifest:
        problems.append("the rebuilt manifest differs from manifest_v1.json")
    elif not ld.MANIFEST_PATH.is_file():
        problems.append("manifest_v1.json is not frozen yet")
    dp.verify_manifest_rows(manifest, rebuilt)
    registration = load_registration()
    gates = evaluate_gates(protocol, dsh_protocol, omp_protocol, manifest, registration, env, problems)
    print(f"phase={ld.PHASE} protocol={ld.PROTOCOL_ID} items={manifest['item_count']} attempts={manifest['n']} "
          f"arms={manifest['arm_counts']} manifest_sha256={manifest['manifest_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    if not args.execute:
        print(f"preflight done items={manifest['item_count']} attempts={manifest['n']} endpoint_calls=0", flush=True)
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise _fail("execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    if args.tunnel_dns:
        address = pr.install_resolver_shim(urlsplit(endpoint).hostname or "", args.tunnel_dns)
        print(f"resolver shim (this process only): {urlsplit(endpoint).hostname} -> {address} via {args.tunnel_dns}")
    campaign = dp.load_protocol()
    operational, transport = protocol["operational"], campaign["transport"]
    card_id = str(registration["card_ids"][ld.PHASE])
    output = OUTPUT_ROOT / PROFILE_ID
    resume = bool(args.resume) and (output / "condition.json").is_file()
    condition = pr.reconcile_resume(output, build_condition(protocol, dsh_protocol, omp_protocol, manifest,
                                                            registration, endpoint), resume)
    guard = pr.BudgetGuard(operational["budget_tokens"], pr.existing_usage(output))
    outage = pr.OutageGuard(operational["stop_after_timeouts"])
    if (pr.base.SHARDS, pr.base.LANES) != (transport["shards"], transport["lanes"]):
        raise _fail("engine shard/lane constants differ from the campaign protocol")
    pr.base.MODEL, pr.base.PROFILE, pr.base.PROTOCOL, pr.base.CARD_ID = (
        campaign["model"]["requested_id"], PROFILE_ID, ld.PROTOCOL_ID, card_id)
    pr.base.request = make_request(campaign, card_id, guard, outage, operational["max_in_flight"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": pr.base.now(), "resume": resume, "runner_sha256": v1.sha256_file(Path(__file__)),
                                 "operational": operational, "note": args.note}, ensure_ascii=False) + "\n")
    items = dp.verify_manifest_rows(manifest, rebuilt)
    with OpenAI(base_url=endpoint, api_key=key, timeout=transport["timeout_seconds"],
                max_retries=transport["sdk_retries"], default_headers=transport["gateway_header"]) as client:
        context = AttemptContext(dsh=dsh, omp=omp, docs=docs, corpus_of=manifest["corpus_of"], output=output,
                                 dsh_proxy=rl2.proxy_config(dsh_protocol["proxy"], endpoint, key, campaign),
                                 omp_proxy=rl2.proxy_config(omp_protocol["proxy"], endpoint, key, campaign),
                                 dsh_protocol=dsh_protocol, omp_protocol=omp_protocol, client=client)
        # the engine hands `context` to the request function as its client, as in MC-114's runner
        pr.base.execute(output, manifest, rebuilt, items, condition, context,  # pyright: ignore[reportArgumentType]
                        resume, score_callback=score_callback(card_id), runner_path=Path(__file__))
    status = json.loads((output / "run.json").read_text(encoding="utf-8"))["status"]
    print(f"status={status} output={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
