"""Run MC-114 (openspec change diagnostic-legal-agent-v2): MC-112's dsh arms (DSH, DSHF), MC-113's omp arm (OMPF) and
the direct arms (B, C, O) over corpus_v2, on the 112 VMLU law items (part M) and 400 closed-book ViBidLQA items (part S).

From the repo root:
  .venv/bin/python -m code_benchmark.run_legal_agent_v2                    # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_legal_agent_v2 --selftest         # both harnesses against fake servers
  .venv/bin/python -m code_benchmark.run_legal_agent_v2 --smoke --execute  # design §10, needs the VPN
  .venv/bin/python -m code_benchmark.run_legal_agent_v2 --execute [--resume] [--tunnel-dns <in-tunnel DNS server>]

Agent attempts reuse MC-112's and MC-113's code unchanged: the sandbox (no network, a fresh home, an empty
environment, corpus_v2 mounted read-only at /work/van-ban-phap-luat), the relay, the per-attempt proxy (temperature
1.0, the key, every request recorded, 30 requests and 300 s per request), omp's request-shape checks, and both
status mappings. Direct arms send the campaign request of MC-90 to MC-111. One gate keeps at most `max_in_flight`
attempts of any kind in flight; the budget guard and the outage guard are shared.

Scoring: part M by the frozen MC scorer; part S by vi-reading-v3 (token-F1 primary), with the v2 values kept beside.
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
    from code_benchmark import diagnostic_legal_agent_v2 as l2
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import dsh_proxy as px
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_legal_agent as rla
    from code_benchmark import run_legal_agent_omp as rlo
    from code_benchmark import vi_multimodel as v1
    from code_benchmark import vi_reading_v3 as v3
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import dsh_proxy as px  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import run_diagnostic_prospective as pr  # type: ignore[no-redef]
    import run_legal_agent as rla  # type: ignore[no-redef]
    import run_legal_agent_omp as rlo  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]
    import vi_reading_v3 as v3  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = l2.WORK_ROOT / "run"
SMOKE_ROOT = l2.WORK_ROOT / "smoke"
SMOKE_PATH = l2.DATA_DIR / "smoke_questions_v2.json"
PROFILE_ID = "qwen3-5-9b-65k-legal-agent-v2"
CARD_ID = "MC-114"
DSH_ARMS = ("DSH", "DSHF")
OMP_ARMS = ("OMPF",)
DIRECT_ARMS = ("B", "C", "O")
SELFTEST_FILE = rlo.SELFTEST_FILE


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def part_of(item: v1.EvalItem) -> str:
    return "M" if item.task == "multiple_choice" else "S"


def harness_of(arm: str) -> str:
    if arm in DSH_ARMS:
        return "dsh"
    if arm in OMP_ARMS:
        return "omp"
    if arm in DIRECT_ARMS:
        return "direct"
    raise _fail(f"arm {arm!r} has no path in MC-114")


# ---------------------------------------------------------------- reused protocols, pins and the folder

def harness_protocols(protocol: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """MC-112's and MC-113's protocols, each read from the file whose SHA-256 this protocol registers."""
    specs = protocol["harnesses"]
    for name in ("dsh", "omp"):
        l2._sha_checked(ROOT / specs[name]["protocol"], specs[name]["protocol_sha256"], f"{name} protocol")  # noqa: SLF001
    return la.load_protocol(ROOT / specs["dsh"]["protocol"]), rlo.load_protocol(ROOT / specs["omp"]["protocol"])


def check_harnesses(dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any]
                    ) -> tuple[rla.Harness, rlo.Harness, list[str]]:
    dsh, dsh_problems = rla.check_harness(dsh_protocol)
    omp, omp_problems = rlo.check_harness(omp_protocol)
    return dsh, omp, [*(f"dsh: {p}" for p in dsh_problems), *(f"omp: {p}" for p in omp_problems)]


def check_folder(protocol: dict[str, Any], *, rebuild: bool = True) -> tuple[Path, list[str]]:
    """corpus_v2's docs directory, and what differs: its listing hash, a fresh rebuild's hash, the provisions."""
    docs = ROOT / protocol["corpus"]["folder"] / "docs"
    expected = protocol["corpus"]["folder_sha256"]
    problems = []
    if not docs.is_dir() or rla.listing_sha256(docs) != expected:
        problems.append(f"{docs} does not hash to the registered folder SHA-256")
    if rebuild:
        with tempfile.TemporaryDirectory(prefix="mc114-rebuild-") as tmp:
            built = l2.build_corpus(Path(tmp) / "f")
            if built["folder_sha256"] != expected:
                problems.append(f"a fresh rebuild hashes to {built['folder_sha256'][:12]}, not {expected[:12]}")
    if docs.is_dir() and l2.PROVISIONS_PATH.is_file():
        problems += [f"provisions: {p}" for p in la.check_provisions(list(l2.load_provisions().values()), docs)[:5]]
    elif not l2.PROVISIONS_PATH.is_file():
        problems.append(f"{l2.PROVISIONS_PATH.name} is not written yet (it needs the owner's spot-check labels)")
    return docs, problems


# ---------------------------------------------------------------- one attempt

@dataclass
class AttemptContext:
    """Everything an attempt needs besides its item: passed to the engine as its `client`."""
    dsh: rla.Harness
    omp: rlo.Harness
    docs: Path
    output: Path
    dsh_proxy: px.ProxyConfig
    omp_proxy: px.ProxyConfig
    dsh_protocol: dict[str, Any]
    omp_protocol: dict[str, Any]
    client: Any = None  # the OpenAI client of the direct arms


def proxy_config(spec: dict[str, Any], endpoint: str, key: str, campaign: dict[str, Any]) -> px.ProxyConfig:
    return px.ProxyConfig(upstream=endpoint, api_key=key, model=campaign["model"]["requested_id"],
                          expected_response_model=spec["expected_response_model"], temperature=spec["temperature"],
                          extra_headers=dict(campaign["transport"]["gateway_header"]),
                          request_timeout=spec["request_timeout_seconds"], request_cap=spec["request_cap"])


def run_agent(context: AttemptContext, item: v1.EvalItem, harness: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """One sandboxed attempt through MC-112's (dsh) or MC-113's (omp) path: (result, verdict, attempt dir)."""
    base_dir = context.output / "attempts" / rla.safe_key(item.run_key)
    tries = len(list(base_dir.glob("try-*"))) if base_dir.is_dir() else 0
    attempt_dir = base_dir / f"try-{tries + 1}"
    if harness == "dsh":
        result = rla.run_sandboxed(context.dsh, context.docs, attempt_dir, item.prompt, context.dsh_proxy,
                                   context.dsh_protocol["proxy"]["wall_clock_seconds"])
        return result, rla.classify(result), attempt_dir
    result = rlo.run_sandboxed(context.omp, context.docs, attempt_dir, item.prompt, context.omp_proxy,
                               rlo.rules_for(context.omp_protocol, item.prompt),
                               context.omp_protocol["proxy"]["wall_clock_seconds"])
    return result, rlo.classify(result), attempt_dir


def agent_row(item: v1.EvalItem, context: AttemptContext, harness: str, shard: int, lane: int) -> dict[str, Any]:
    spec = (context.dsh_protocol if harness == "dsh" else context.omp_protocol)["harness"]
    proxy = context.dsh_proxy if harness == "dsh" else context.omp_proxy
    return {
        "run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
        "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
        "part": part_of(item), "harness": harness, "phase": l2.PHASE, "profile_id": PROFILE_ID,
        "protocol_id": l2.PROTOCOL_ID, "measurement_card_id": CARD_ID, "model_id": proxy.model,
        "transport": "dsh-headless" if harness == "dsh" else "omp-json", "api_protocol": spec["api_protocol"],
        "shard": shard, "lane": lane, "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")),
        "raw_prompt": item.prompt, "raw_response": "", "temperature_sent": proxy.temperature,
        "reasoning_effort_sent": None, "seed_sent": None,
        "max_tokens": spec.get("max_tokens") or spec.get("max_completion_tokens"),
    }


def finish_agent_row(row: dict[str, Any], result: dict[str, Any], verdict: dict[str, Any], attempt_dir: Path,
                     output: Path) -> dict[str, Any]:
    seen = verdict.pop("proxy")
    models = seen["response_models"]
    row.update({
        "status": verdict["status"], "outcome": verdict["outcome"], "raw_response": verdict["raw_response"],
        "error_type": verdict["error_type"], "fatal": verdict["fatal"], "final_reason": verdict["final_reason"],
        "finish_reason": "stop" if verdict["outcome"] == "complete" else verdict["outcome"],
        "attempt_dir": str(attempt_dir.relative_to(output)), "harness_exit": result["exit_code"],
        "latency_s": result["wall_s"], "finished_at": pr.base.now(), "requests": seen["requests"],
        "requests_forwarded": seen.get("forwarded"), "proxy_outcomes": seen["outcomes"],
        "tool_calls": rla.tool_counts(result["records"]), "prompt_tokens": seen["prompt_tokens"],
        "completion_tokens": seen["completion_tokens"], "total_tokens": seen["total_tokens"],
        "response_model_id": models[0] if len(models) == 1 else models or None,
    })
    return row


def make_request(campaign: dict[str, Any], card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard,
                 max_in_flight: int, direct: Any = None):
    """The engine's request function: one gate over all paths, the shared guards, then the arm's path."""
    gate = threading.BoundedSemaphore(max_in_flight)
    halt = threading.Event()
    direct = direct or pr.make_request(campaign, l2.PHASE, card_id, guard, outage=outage)

    def request(context: AttemptContext, item: v1.EvalItem, shard: int, lane: int) -> dict[str, Any]:
        harness = harness_of(dp.arm_of_replicate(item.replicate_id))
        with gate:  # waiting here is not part of the measured time
            for blocked, error_type in ((guard.exhausted(), "budget_cap"), (outage.tripped(), "endpoint_unresponsive"),
                                        (halt.is_set(), "halted_before_send")):
                if blocked:
                    halt.set()
                    return {"run_key": item.run_key, "dataset_id": item.dataset_id, "item_id": item.item_id,
                            "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
                            "part": part_of(item), "harness": harness, "phase": l2.PHASE,
                            "prompt_sha256": v1.sha256_bytes(item.prompt.encode("utf-8")), "raw_response": "",
                            "status": "request_error", "finish_reason": "error", "error_type": error_type,
                            "fatal": True, "latency_s": 0.0, "started_at": pr.base.now(), "finished_at": pr.base.now()}
            if harness == "direct":
                row = {**direct(context.client, item, shard, lane), "part": part_of(item), "harness": harness}
                if row.get("fatal"):
                    halt.set()
                return row  # the campaign request has already counted tokens and outages
            row = agent_row(item, context, harness, shard, lane)
            row["started_at"] = pr.base.now()
            result, verdict, attempt_dir = run_agent(context, item, harness)
        row = finish_agent_row(row, result, verdict, attempt_dir, context.output)
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

def token_recall(prediction: str, gold: str) -> float:
    """Share of the gold's tokens present in the prediction (vi-reading tokens): descriptive only."""
    expected = Counter(v1.tokenize_vi(v3.strip_marks(gold)))
    if not expected:
        return 1.0
    overlap = Counter(v1.tokenize_vi(prediction)) & expected
    return sum(overlap.values()) / sum(expected.values())


def rescore(row: dict[str, Any]) -> dict[str, Any]:
    """A part S row with vi-reading-v3 values (em, token_f1, prediction), the v2 values beside, and the recall."""
    if "token_f1" not in row:
        return row
    out = {**v3.rescore_row(row), "em_v2": row["em"], "token_f1_v2": row["token_f1"], "prediction_v2": row.get("prediction")}
    out["token_recall"] = token_recall(str(out.get("prediction") or ""), str(row["gold_answer"]))
    return out


def summarize(scored: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in scored:
        groups.setdefault((str(row.get("part")), str(row.get("arm"))), []).append(row)
    out = {}
    for (part, arm), rows in sorted(groups.items()):
        metric = "correct" if part == "M" else "token_f1"
        values = [float(row.get(metric) or 0.0) for row in rows]
        out[f"{part}:{arm}"] = {"n": len(rows), "metric": metric if part == "M" else "token_f1 (vi-reading-v3)",
                                "mean_points": round(100 * sum(values) / len(values), 2) if values else None}
    return out


def score_callback(card_id: str):
    def score(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        scored, summaries = dp.score_arm_rows(manifest, rows, rebuilt)
        final = []
        for row in scored:
            source = rows.get(dp.run_key(row)) or {}
            row.update({key: source.get(key) for key in ("part", "harness", "outcome", "attempt_dir", "requests",
                                                       "requests_forwarded", "tool_calls")})
            final.append(rescore(row))
        v1.write_jsonl_atomic(output / "scores.jsonl", final)
        outcomes = Counter((str(row.get("arm")), str(row.get("outcome"))) for row in rows.values())
        pr.base.atomic_json(output / "summary.json", {
            "protocol_id": l2.PROTOCOL_ID, "phase": l2.PHASE, "measurement_card_id": card_id,
            "model_id": pr.base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": pr.base.now(),
            "expected_n": len(manifest["items"]), "by_part_arm": summarize(final),
            "arms": {arm: list(by_dataset.values()) for arm, by_dataset in summaries.items()},
            "outcomes": {f"{arm}:{outcome}": count for (arm, outcome), count in sorted(outcomes.items())},
            "cost_usd": None, "cost_basis": "IEC tariff not supplied; reported usage retained per attempt",
        })
    return score


# ---------------------------------------------------------------- registration and condition

def hash_keys(manifest: dict[str, Any]) -> list[str]:
    return sorted(key for key in manifest if key.endswith("_sha256"))


def load_registration(path: Path = l2.REGISTRATION_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def evaluate_gates(protocol: dict[str, Any], dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any],
                   manifest: dict[str, Any], registration: dict[str, Any], env: dict[str, str | None],
                   problems: list[str]) -> list[pr.Gate]:
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8")
    card_id = (registration.get("card_ids") or {}).get(l2.PHASE)
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    card_file = (registration.get("card_files") or {}).get(l2.PHASE)
    frozen = registration.get("frozen") or {}
    differing = [name for name in hash_keys(manifest) if frozen.get(name) != manifest.get(name)]
    campaign = dp.load_protocol()["model"]
    endpoint = urlsplit(env.get("OPENAI_BASE_URL") or "")
    identity = (endpoint.hostname == campaign["endpoint_host"]
                and endpoint.path.rstrip("/") == campaign["endpoint_path"].rstrip("/")
                and env.get("OPENAI_MODEL") == campaign["requested_id"] and bool(env.get("OPENAI_API_KEY")))
    models = [dsh_protocol["proxy"].get("expected_response_model"), omp_protocol["proxy"].get("expected_response_model"),
              omp_protocol["proxy"].get("system_prompt_sha256")]
    return [
        pr.Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md"),
        pr.Gate("detail_card", bool(card_file) and (ROOT / str(card_file)).is_file(), str(card_file or "none")),
        pr.Gate("frozen_hashes", bool(frozen) and not differing, "all match" if frozen and not differing
                else f"differ: {differing[:6]}"),
        pr.Gate("endpoint_identity", identity, f"model={env.get('OPENAI_MODEL')} (expects {campaign['requested_id']})"),
        pr.Gate("budget_set", isinstance(protocol["operational"].get("budget_tokens"), int),
                "budget_tokens is set from the smoke test"),
        pr.Gate("reused_pins_set", all(models), "MC-112's and MC-113's response models and omp's system prompt"),
        pr.Gate("harness_and_folder", not problems, "; ".join(problems) or "pins, folder and provisions match"),
    ]


def build_condition(protocol: dict[str, Any], dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any],
                    manifest: dict[str, Any], registration: dict[str, Any], endpoint: str) -> dict[str, Any]:
    module = Path(__file__).resolve().parent
    campaign = dp.load_protocol()
    return {
        "protocol_id": l2.PROTOCOL_ID, "protocol_version": 1, "phase": l2.PHASE,
        "measurement_card_id": registration["card_ids"][l2.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][l2.PHASE]),
        **{name: manifest[name] for name in hash_keys(manifest)},
        "arm_counts": manifest["arm_counts"], "dataset_counts": manifest["dataset_counts"],
        "operational": protocol["operational"], "model_id": campaign["model"]["requested_id"], "profile_id": PROFILE_ID,
        "dsh": {"harness": dsh_protocol["harness"], "proxy": dsh_protocol["proxy"]},
        "omp": {"harness": omp_protocol["harness"], "proxy": omp_protocol["proxy"]},
        "direct": {"api_protocol": campaign["transport"]["api_protocol"],
                   "system_prompt": campaign["transport"]["system_prompt"],
                   "temperature": campaign["transport"]["temperature"],
                   "max_output_tokens": campaign["transport"]["max_output_tokens"],
                   "expected_response_model": campaign["model"]["self_reported_id"]},
        "endpoint_host": urlsplit(endpoint).hostname, "base_url_sha256": v1.sha256_bytes(endpoint.encode()),
        "workdir": protocol["corpus"]["workdir"],
        "scorer_sha256": v1.sha256_file(module / "score_vi_multimodel.py"),
        "reading_v3_sha256": v1.sha256_file(Path(v3.__file__)),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)), "engine_sha256": v1.sha256_file(Path(pr.__file__)),
        "legal_agent_module_sha256": v1.sha256_file(Path(la.__file__)),
        "legal_agent_v2_module_sha256": v1.sha256_file(Path(l2.__file__)),
        "trajectory_sha256": v1.sha256_file(Path(str(ot.__file__))), "proxy_sha256": v1.sha256_file(Path(px.__file__)),
        "relay_sha256": v1.sha256_file(rla.RELAY), "mc112_runner_sha256": v1.sha256_file(Path(rla.__file__)),
        "mc113_runner_sha256": v1.sha256_file(Path(rlo.__file__)), "runner_sha256": v1.sha256_file(Path(__file__)),
    }


# ---------------------------------------------------------------- self-test and smoke test

def selftest_cases(prompts: dict[str, Any], mc_prompt: str) -> list[tuple[str, str, str, list[dict[str, Any]], str]]:
    """(label, harness, task, script, expected final text): an MC task and a span task through each harness."""
    span = l2.agent_task("DSHF", l2.closed_book_prompt("Hội phí hằng năm của câu lạc bộ là bao nhiêu?", prompts),
                         prompts)
    mc = l2.agent_task("DSHF", mc_prompt, prompts)
    dsh_steps = [{"tool": "grep", "arguments": {"pattern": "hội phí"}},
                 {"tool": "read", "arguments": {"file_path": SELFTEST_FILE}}]
    omp_steps = [{"tool": "grep", "arguments": {"i": "Finding the fee", "pattern": "hội phí"}},
                 {"tool": "read", "arguments": {"i": "Reading the rules", "path": SELFTEST_FILE}}]
    return [("dsh-mc", "dsh", mc, [*dsh_steps, {"text": "Đáp án: B"}], "Đáp án: B"),
            ("dsh-span", "dsh", span, [*dsh_steps, {"text": "Trả lời: 100.000 đồng"}], "Trả lời: 100.000 đồng"),
            ("omp-mc", "omp", mc, [*omp_steps, {"text": "Đáp án: B"}], "Đáp án: B"),
            ("omp-span", "omp", span, [*omp_steps, {"text": "Trả lời: 100.000 đồng"}], "Trả lời: 100.000 đồng")]


def selftest(dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any], dsh: rla.Harness, omp: rlo.Harness) -> bool:
    """Both harnesses end to end on this card's task layouts, against scripted servers, offline. The omp cases keep
    MC-113's registered system-prompt check, so a host change that alters omp's system prompt fails here."""
    smoke = json.loads(rla.SMOKE_PATH.read_text(encoding="utf-8"))
    prompts = l2.load_prompts()
    provision = {"file": SELFTEST_FILE, "anchor_line": "Điều 2. Hội viên"}
    ok = True
    with tempfile.TemporaryDirectory(prefix="mc114-selftest-") as tmp:
        docs = Path(tmp) / "docs"
        docs.mkdir()
        for name, text in smoke["synthetic_folder"].items():
            (docs / name).write_text(text, encoding="utf-8")
        for label, harness, task, script, expected in selftest_cases(prompts, smoke["questions"][0]["prompt"]):
            with rlo.ScriptedUpstream(script) as upstream:
                config = px.ProxyConfig(upstream=upstream.url, api_key="selftest-key", model="Qwen3.5-9B-65K",
                                        expected_response_model="fake-model.gguf", request_cap=30,
                                        extra_headers=dict(dp.load_protocol()["transport"]["gateway_header"]))
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
            good = ((verdict["status"], verdict["outcome"], verdict["raw_response"]) == ("complete", "complete", expected)
                    and temps <= {dsh_protocol["proxy"]["temperature"]} and all(hits.values()))
            if label.endswith("span"):
                good &= v3.score_reading(verdict["raw_response"], "100.000 đồng")["token_f1"] == 1.0
            ok &= good
            print(f"selftest {label}: status={verdict['status']} outcome={verdict['outcome']} "
                  f"requests={len(result['records'])} temperatures={sorted(temps, key=str)} hits={hits} "
                  f"{'PASS' if good else 'FAIL'}", flush=True)
    return ok


def load_smoke(path: Path = SMOKE_PATH) -> list[dict[str, Any]]:
    smoke = json.loads(path.read_text(encoding="utf-8"))
    if smoke.get("version") != "diagnostic-legal-agent-v2-smoke" or len(smoke.get("questions") or []) != 3:
        raise _fail("smoke_questions_v2.json must hold this card's three smoke questions")
    return smoke["questions"]


def smoke_test(dsh_protocol: dict[str, Any], omp_protocol: dict[str, Any], dsh: rla.Harness, omp: rlo.Harness,
               docs: Path, endpoint: str, key: str) -> Path:
    """Design §10: each smoke question once with DSHF and once with OMPF on corpus_v2. No score is computed; omp's
    system-prompt hash is recorded and checked against MC-113's."""
    prompts = l2.load_prompts()
    campaign = dp.load_protocol()
    out = SMOKE_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True)
    configs = {"dsh": proxy_config(dsh_protocol["proxy"], endpoint, key, campaign),
               "omp": proxy_config(omp_protocol["proxy"], endpoint, key, campaign)}
    report = []
    for question in load_smoke():
        item_prompt = question["prompt"] if question["kind"] == "mc" else l2.closed_book_prompt(question["question"],
                                                                                               prompts)
        task = l2.agent_task("DSHF", item_prompt, prompts)
        for harness in ("dsh", "omp"):
            attempt = out / f"{question['id']}-{harness}"
            if harness == "dsh":
                result = rla.run_sandboxed(dsh, docs, attempt, task, configs["dsh"],
                                           dsh_protocol["proxy"]["wall_clock_seconds"])
                verdict, observations = rla.classify(result), la.model_observations(result["records"])
            else:
                rules = dataclasses.replace(rlo.rules_for(omp_protocol, task), system_sha256=None)
                result = rlo.run_sandboxed(omp, docs, attempt, task, configs["omp"], rules,
                                           omp_protocol["proxy"]["wall_clock_seconds"])
                verdict, observations = rlo.classify(result), ot.omp_observations(result["records"])
            seen = px.attempt_outcome(result["records"])
            received = [json.loads(r["body_received"]) for r in result["records"] if r.get("body_received")]
            hits = la.provision_hits(observations, question.get("provisions") or [])
            system = sorted({str(rlo.system_sha256(body.get("messages") or [])) for body in received[:1]})
            report.append({
                "id": question["id"], "kind": question["kind"], "harness": harness, "status": verdict["status"],
                "outcome": verdict["outcome"], "error_type": verdict["error_type"],
                "final_text": verdict["raw_response"], "wall_s": result["wall_s"], "requests": seen["requests"],
                "proxy_outcomes": seen["outcomes"], "tool_calls": rla.tool_counts(result["records"]), "hits": hits,
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
    ap.add_argument("--smoke", action="store_true", help="with --execute: the smoke test of design §10")
    ap.add_argument("--no-rebuild", action="store_true", help="preflight and smoke only: skip the fresh folder rebuild")
    ap.add_argument("--tunnel-dns", default=None, help="in-tunnel DNS server for the endpoint host (this process only)")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    if args.no_rebuild and args.execute and not args.smoke:
        ap.error("--no-rebuild is for the preflight and the smoke test only")
    protocol = l2.load_protocol()
    dsh_protocol, omp_protocol = harness_protocols(protocol)
    dsh, omp, problems = check_harnesses(dsh_protocol, omp_protocol)
    if args.selftest:
        if problems:
            raise _fail("; ".join(problems))
        return 0 if selftest(dsh_protocol, omp_protocol, dsh, omp) else 1
    docs, folder_problems = check_folder(protocol, rebuild=not args.no_rebuild)
    problems += folder_problems
    env = dotenv_values(ROOT / ".env")
    endpoint, key = str(env.get("OPENAI_BASE_URL") or ""), str(env.get("OPENAI_API_KEY") or "")
    if args.smoke:
        if not args.execute:
            ap.error("--smoke requires --execute")
        if args.tunnel_dns:
            pr.install_resolver_shim(urlsplit(endpoint).hostname or "", args.tunnel_dns)
        if [p for p in problems if not p.startswith("provisions") and "spot-check" not in p]:
            raise _fail("the smoke test needs the pinned harnesses and corpus_v2: " + "; ".join(problems))
        out = smoke_test(dsh_protocol, omp_protocol, dsh, omp, docs, endpoint, key)
        print(f"smoke test -> {out / 'smoke_report.json'}")
        return 0
    manifest, rebuilt = l2.build_manifest(protocol)
    if l2.MANIFEST_PATH.is_file() and l2.load_frozen_manifest() != manifest:
        problems.append("the rebuilt manifest differs from manifest_v1.json")
    elif not l2.MANIFEST_PATH.is_file():
        problems.append("manifest_v1.json is not frozen yet")
    dp.verify_manifest_rows(manifest, rebuilt)
    registration = load_registration()
    gates = evaluate_gates(protocol, dsh_protocol, omp_protocol, manifest, registration, env, problems)
    print(f"phase={l2.PHASE} protocol={l2.PROTOCOL_ID} items={manifest['item_count']} attempts={manifest['n']} "
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
    card_id = str(registration["card_ids"][l2.PHASE])
    output = OUTPUT_ROOT / PROFILE_ID
    resume = bool(args.resume) and (output / "condition.json").is_file()
    condition = pr.reconcile_resume(output, build_condition(protocol, dsh_protocol, omp_protocol, manifest,
                                                            registration, endpoint), resume)
    guard = pr.BudgetGuard(operational["budget_tokens"], pr.existing_usage(output))
    outage = pr.OutageGuard(operational["stop_after_timeouts"])
    if (pr.base.SHARDS, pr.base.LANES) != (transport["shards"], transport["lanes"]):
        raise _fail("engine shard/lane constants differ from the campaign protocol")
    pr.base.MODEL, pr.base.PROFILE, pr.base.PROTOCOL, pr.base.CARD_ID = (
        campaign["model"]["requested_id"], PROFILE_ID, l2.PROTOCOL_ID, card_id)
    pr.base.request = make_request(campaign, card_id, guard, outage, operational["max_in_flight"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": pr.base.now(), "resume": resume, "runner_sha256": v1.sha256_file(Path(__file__)),
                                 "operational": operational, "note": args.note}, ensure_ascii=False) + "\n")
    items = dp.verify_manifest_rows(manifest, rebuilt)
    with OpenAI(base_url=endpoint, api_key=key, timeout=transport["timeout_seconds"],
                max_retries=transport["sdk_retries"], default_headers=transport["gateway_header"]) as client:
        context = AttemptContext(dsh=dsh, omp=omp, docs=docs, output=output,
                                 dsh_proxy=proxy_config(dsh_protocol["proxy"], endpoint, key, campaign),
                                 omp_proxy=proxy_config(omp_protocol["proxy"], endpoint, key, campaign),
                                 dsh_protocol=dsh_protocol, omp_protocol=omp_protocol, client=client)
        pr.base.execute(output, manifest, rebuilt, items, condition, context, resume,
                        score_callback=score_callback(card_id), runner_path=Path(__file__))
    status = json.loads((output / "run.json").read_text(encoding="utf-8"))["status"]
    print(f"status={status} output={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
