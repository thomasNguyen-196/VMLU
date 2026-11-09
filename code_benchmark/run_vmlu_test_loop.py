"""Run a student's self-improvement loop on VMLU test, round by round (openspec change diagnostic-router-loop, tasks
2.9 and 2.10; cards MC-109 for Qwen and MC-110 for MiMo).

From the repo root:
  .venv/bin/python -m code_benchmark.run_vmlu_test_loop --student qwen          # offline preflight, endpoint_calls=0
  .venv/bin/python -m code_benchmark.run_vmlu_test_loop --student qwen --execute [--resume] [--tunnel-dns <in-tunnel DNS server>]
  .venv/bin/python -m code_benchmark.run_vmlu_test_loop --student mimo --execute [--resume]

The requests are MC-105's. Qwen: B-r1 is the MC-43 letter probe, S the campaign transport, all behind one gate. MiMo:
the MC-103 route (OpenCode Go chat completions, one routing session per attempt) for B and S alike.
What changes is the item set (the 9,833 VMLU test items, gold withheld) and the schedule: instead of asking every
attempt, each pass sends the attempts the loop's rule needs given the completed ones (`diagnostic_vmlu_test_loop.plan`):
for Qwen the probe for every item, S-r1 for the unsure ones, S-r2 and S-r3 where S-r1 disagrees; for MiMo B-r1 and
B-r2 for every item, S-r1 where they disagree, S-r2 and S-r3 where S-r1 agrees with neither. An attempt without a
completed response is sent again in the next pass. A launch stops after the registered number of passes, after a pass
that completes nothing, or at a fatal row (authentication, model-identity drift, budget, endpoint breaker); `--resume`
continues from the ledger. An HTTP 400 is fatal too, except for MiMo under MC-110 amendment 1 (`BadRequestRule`). When every item has a final answer, the two vmlu.ai submissions are written.
`--execute` fails closed unless the student's card heading and detail card exist, the configuration and the rebuilt
manifest carry the registered SHA-256 values, and the route is the registered one.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import dotenv_values
from openai import OpenAI

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_router as router
    from code_benchmark import diagnostic_table_loop as tl
    from code_benchmark import diagnostic_vmlu_test_loop as vt
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_self_loop as rsl
    from code_benchmark import vi_multimodel as v1
    from code_benchmark.common import write_csv_atomic
    from code_benchmark.run_mc_calibration_eval import letter_probs
    from code_benchmark.run_mc_eval import extract_answer
    from code_benchmark.run_weakness_map import COMPLETE_FINISHES, ModelPin
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_router as router
    import diagnostic_table_loop as tl
    import diagnostic_vmlu_test_loop as vt
    import run_diagnostic_prospective as pr
    import run_self_loop as rsl
    import vi_multimodel as v1
    from common import write_csv_atomic
    from run_mc_calibration_eval import letter_probs
    from run_mc_eval import extract_answer
    from run_weakness_map import COMPLETE_FINISHES, ModelPin

ROOT = dp.ROOT
OUTPUT_ROOT = ROOT / "all_res" / "diagnostic_router_loop" / "vmlu_test_loop"
base = pr.base
Gate = pr.Gate


def load_registration(path: Path = vt.REGISTRATION_PATH) -> dict[str, Any]:
    try:
        registration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read the VMLU test loop registration {path}: {exc}") from exc
    for key in ("card_ids", "card_files", "frozen", "analysis"):
        if key not in registration:
            raise SystemExit(f"Error: the VMLU test loop registration lacks {key}")
    return registration


def evaluate_gates(student: str, manifest: dict[str, Any], registration: dict[str, Any], route_ok: bool,
                   route_detail: str, *, card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    card_id = (registration.get("card_ids") or {}).get(vt.PHASE)
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    heading = bool(card_id) and re.search(rf"^#{{2,3}} {re.escape(str(card_id))}\b", text, re.MULTILINE) is not None
    gates = [Gate("card_registered", heading, f"{card_id or 'no card id assigned'} heading in measurement_card.md")]
    card_file = (registration.get("card_files") or {}).get(vt.PHASE)
    gates.append(Gate("detail_card", bool(card_file) and (root / str(card_file)).is_file(),
                      str(card_file or "no detail card file recorded")))
    frozen = registration.get("frozen") or {}
    differing = [name for name, ok in (("config", frozen.get("config_sha256") == manifest["config_sha256"]),
                                       ("manifest", (frozen.get("manifest_sha256") or {}).get(student)
                                        == manifest["manifest_sha256"])) if not ok]
    gates.append(Gate("frozen_hashes", not differing, "all match" if not differing else f"differ: {differing}"))
    gates.append(Gate("route_identity", route_ok, route_detail))
    return gates


# ---------------------------------------------------------------- requests (MC-105's, with this card's rows)

def _base_row(item, card_id: str, shard: int, lane: int, api_protocol: str) -> dict[str, Any]:
    return {"run_key": item.run_key, "item_key": f"{item.dataset_id}:{item.item_id}", "dataset_id": item.dataset_id,
            "item_id": item.item_id, "replicate_id": item.replicate_id, "arm": dp.arm_of_replicate(item.replicate_id),
            "phase": vt.PHASE, "profile_id": base.PROFILE, "protocol_id": base.PROTOCOL, "measurement_card_id": card_id,
            "model_id": base.MODEL, "transport": "direct-api", "api_protocol": api_protocol, "shard": shard,
            "lane": lane, "prompt_sha256": v1.sha256_bytes(item.prompt.encode()), "raw_prompt": item.prompt,
            "raw_response": "", "started_at": base.now()}


def is_probe(item) -> bool:
    return item.replicate_id == "B-r1"


def unreadable_probes(items: list) -> list[str]:
    return [item.item_id for item in items if is_probe(item) and len(rsl.readable_letters(item.prompt)) < 2]


def make_probe(probe: dict[str, Any], expected_models: set[str], card_id: str, guard: pr.BudgetGuard,
               outage: pr.OutageGuard, halt: threading.Event):
    """MC-105's MC-43 letter probe."""
    def request(client, item, shard: int, lane: int) -> dict[str, Any]:
        row = _base_row(item, card_id, shard, lane, probe["api_protocol"])
        row.update({"temperature_sent": probe["temperature"], "seed_sent": probe["seed"], "max_tokens": probe["max_tokens"],
                    "top_logprobs_requested": probe["top_logprobs"], "probe": probe["condition_source"]})
        if rsl._blocked(row, guard, outage, halt):  # noqa: SLF001 - MC-104's guard, shared on purpose
            return row
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=base.MODEL, messages=[{"role": "user", "content": item.prompt}], temperature=probe["temperature"],
                seed=probe["seed"], max_tokens=probe["max_tokens"], logprobs=True, top_logprobs=probe["top_logprobs"])
            if not response.choices:
                raise ValueError("no_choices")
            choice = response.choices[0]
            content = choice.message.content or ""
            logprobs = getattr(choice, "logprobs", None)
            first = logprobs.content[0] if logprobs is not None and logprobs.content else None
            top = [{"token": entry.token, "logprob": entry.logprob} for entry in (first.top_logprobs or [])] if first else []
            offered = rsl.readable_letters(item.prompt)
            probs, off = letter_probs(top, offered)
            answer, found = extract_answer(content), sum(1 for letter in offered if probs[letter] > 0)
            usage, finish = response.usage, str(choice.finish_reason or "unknown")
            row.update({
                "raw_response": content, "finish_reason": finish, "response_model_id": response.model,
                "request_id": response.id, "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None), "first_token": first.token if first else "",
                "top_logprobs": top, "letter_probs": {letter: round(p, 6) for letter, p in probs.items()},
                "off_options_mass": round(off, 6), "letters_found": found,
                "confidence": round(probs[answer], 6) if answer in probs and found >= 2 else None,
                "status": "complete" if finish in ("stop", "length") else "request_error"})
            if row["status"] == "complete" and response.model and response.model not in expected_models:
                row.update({"status": "request_error", "error_type": "model_identity_drift", "fatal": True})
            elif row["status"] != "complete":
                row.update({"error_type": "unexpected_finish", "fatal": False})
        except Exception as exc:  # noqa: BLE001 - never serialize SDK messages: they can echo upstream data
            status_code = getattr(exc, "status_code", None)
            row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                        "http_status": status_code, "fatal": status_code in {400, 401, 402, 403, 404}})
        return rsl._settle(row, start, guard, outage)  # noqa: SLF001
    return request


def make_qwen_request(student: dict[str, Any], campaign: dict[str, Any], card_id: str, guard: pr.BudgetGuard,
                      outage: pr.OutageGuard):
    """The probe for B-r1 and the campaign request for S, behind one gate of `max_in_flight`."""
    halt = threading.Event()  # set by any fatal row; lanes queued at the gate then send nothing
    campaign_request = pr.make_request(campaign, vt.PHASE, card_id, guard, outage=outage, max_in_flight=None)
    probe = make_probe(student["probe"], {campaign["model"]["self_reported_id"], campaign["model"]["requested_id"]},
                       card_id, guard, outage, halt)
    gate = threading.BoundedSemaphore(student["max_in_flight"])

    def limited(client, item, shard: int, lane: int) -> dict[str, Any]:
        with gate:  # waiting here is not part of the measured latency: each clock starts inside its request
            if halt.is_set():
                row = _base_row(item, card_id, shard, lane, "none")
                rsl._blocked(row, guard, outage, halt)  # noqa: SLF001
                return row
            row = (probe if is_probe(item) else campaign_request)(client, item, shard, lane)
            if row.get("fatal"):
                halt.set()
            return row
    return limited


_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:\-]{1,64}")
TRANSIENT_400_WAIT_SECONDS = 30  # the lane's back-off after a technical HTTP 400, as after a 503
TRANSIENT_400_KEYS = ("id", "rule", "decided_on", "decided_by", "applies_from", "refusal_words",
                      "max_attempts_with_400", "text")


def error_code(exc: Exception) -> str | None:
    """The provider's error code (or type) when it is a bare identifier. The message is never kept: it can echo
    upstream data."""
    for value in (getattr(exc, "code", None), getattr(exc, "type", None)):
        if isinstance(value, str) and _IDENTIFIER.fullmatch(value):
            return value
    return None


def transient_400_amendment(registration: dict[str, Any]) -> dict[str, Any] | None:
    """The registration's amendment with rule `transient_400` (MC-110 amendment 1), checked, or None."""
    found = [a for a in registration.get("amendments") or [] if isinstance(a, dict) and a.get("rule") == "transient_400"]
    if not found:
        return None
    amendment = found[0]
    if (len(found) > 1 or set(amendment) != set(TRANSIENT_400_KEYS) or not amendment["refusal_words"]
            or not all(isinstance(w, str) and w for w in amendment["refusal_words"])
            or not isinstance(amendment["max_attempts_with_400"], int) or amendment["max_attempts_with_400"] < 1):
        raise SystemExit("Error: the transient_400 amendment must appear once with exactly the keys "
                         f"{list(TRANSIENT_400_KEYS)}, non-empty refusal words and a positive cap")
    return amendment


def attempts_with_400(output: Path) -> set[str]:
    """Run keys of the ledger's attempts that ever got an HTTP 400."""
    path = output / "attempts.jsonl"
    if not path.is_file():
        return set()
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return {str(row["run_key"]) for row in rows if str(row.get("http_status")) == "400"}


class BadRequestRule:
    """Whether an HTTP 400 halts the run. Registered rule: always, as a permanent provider error. With MC-110
    amendment 1 (rule `transient_400`) a 400 is a technical failure, sent again in the next pass, unless its error code
    names a refusal (one of the amendment's words), the attempt already had a 400 (in the ledger or in this launch), or
    more than `max_attempts_with_400` attempts of the run have had one."""

    def __init__(self, amendment: dict[str, Any] | None = None, earlier: set[str] | frozenset[str] = frozenset()):
        self.amendment = amendment
        self.seen = set(earlier)
        self._lock = threading.Lock()

    def fatal(self, run_key: str, code: str | None) -> str | None:
        """None when this 400 is a technical failure, else why it halts the run."""
        if self.amendment is None:
            return "registered halt: HTTP 400"
        name = f"amendment {self.amendment['id']}"
        with self._lock:
            again = run_key in self.seen
            self.seen.add(run_key)
            if code and any(word.lower() in code.lower() for word in self.amendment["refusal_words"]):
                return f"{name}: the error code {code} names a refusal"
            if again:
                return f"{name}: a second HTTP 400 on this attempt"
            if len(self.seen) > self.amendment["max_attempts_with_400"]:
                return f"{name}: more than {self.amendment['max_attempts_with_400']} attempts had an HTTP 400"
            return None


TIMEOUT_CAP_KEYS = ("id", "rule", "decided_on", "decided_by", "applies_from", "max_timeouts", "timeout_errors", "text")


def timeout_cap_amendment(registration: dict[str, Any]) -> dict[str, Any] | None:
    """The registration's amendment with rule `timeout_cap` (MC-110 amendment 2), checked, or None."""
    found = [a for a in registration.get("amendments") or [] if isinstance(a, dict) and a.get("rule") == "timeout_cap"]
    if not found:
        return None
    amendment = found[0]
    if (len(found) > 1 or set(amendment) != set(TIMEOUT_CAP_KEYS) or not amendment["timeout_errors"]
            or not all(isinstance(e, str) and e for e in amendment["timeout_errors"])
            or not isinstance(amendment["max_timeouts"], int) or isinstance(amendment["max_timeouts"], bool)
            or amendment["max_timeouts"] < 1):
        raise SystemExit("Error: the timeout_cap amendment must appear once with exactly the keys "
                         f"{list(TIMEOUT_CAP_KEYS)}, non-empty timeout error types and a positive cap")
    return amendment


def timeouts_by_attempt(output: Path, errors: list[str] | tuple[str, ...]) -> Counter[str]:
    """How many times each attempt of the ledger timed out (rows whose error type is one of `errors`)."""
    path = output / "attempts.jsonl"
    if not path.is_file():
        return Counter()
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return Counter(str(row["run_key"]) for row in rows
                   if row.get("status") != "complete" and row.get("error_type") in errors)


def with_timeout_terminals(output: Path, rows: dict[str, Any],
                           amendment: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """(rows for the loop rule, capped run keys). With MC-110 amendment 2 (rule `timeout_cap`), an attempt without a
    completed response that has timed out `max_timeouts` times or more is read by the rule as a completed attempt with
    an empty answer, as a reply truncated at the token cap is; it is never sent again. The ledger is not changed."""
    if amendment is None:
        return rows, []
    counts = timeouts_by_attempt(output, amendment["timeout_errors"])
    capped = sorted(key for key, n in counts.items() if n >= amendment["max_timeouts"]
                    and key in rows and rows[key].get("status") != "complete")
    if not capped:
        return rows, []
    view = dict(rows)
    for key in capped:
        view[key] = {**rows[key], "status": "complete", "raw_response": "",
                     "terminal": f"amendment {amendment['id']}: {counts[key]} timeouts"}
    return view, capped


IN_FLIGHT_KEYS = ("id", "rule", "decided_on", "decided_by", "applies_from", "max_in_flight", "text")


def in_flight_amendment(registration: dict[str, Any]) -> dict[str, Any] | None:
    """The registration's amendment with rule `max_in_flight` (MC-110 amendment 3), checked, or None. The value is at
    most the engine's lanes (shards x lanes)."""
    found = [a for a in registration.get("amendments") or [] if isinstance(a, dict) and a.get("rule") == "max_in_flight"]
    if not found:
        return None
    amendment = found[0]
    value = amendment.get("max_in_flight")
    if (len(found) > 1 or set(amendment) != set(IN_FLIGHT_KEYS) or not isinstance(value, int)
            or isinstance(value, bool) or not 1 <= value <= base.SHARDS * base.LANES):
        raise SystemExit("Error: the max_in_flight amendment must appear once with exactly the keys "
                         f"{list(IN_FLIGHT_KEYS)} and a value from 1 to {base.SHARDS * base.LANES}")
    return amendment


def gated_student(student: dict[str, Any], amendment: dict[str, Any] | None) -> dict[str, Any]:
    """The student settings the request gate reads. With MC-110 amendment 3 only `max_in_flight` differs; the frozen
    configuration, its hash and the condition keep the registered value."""
    return student if amendment is None else {**student, "max_in_flight": amendment["max_in_flight"]}


TIMEOUT_KEYS = ("id", "rule", "decided_on", "decided_by", "applies_from", "timeout_seconds", "text")
TIMEOUT_RANGE = (60, 1800)


def timeout_amendment(registration: dict[str, Any]) -> dict[str, Any] | None:
    """The registration's amendment with rule `timeout_seconds` (MC-110 amendment 4), checked, or None. The value is a
    whole number of seconds within TIMEOUT_RANGE."""
    found = [a for a in registration.get("amendments") or [] if isinstance(a, dict) and a.get("rule") == "timeout_seconds"]
    if not found:
        return None
    amendment = found[0]
    value = amendment.get("timeout_seconds")
    if (len(found) > 1 or set(amendment) != set(TIMEOUT_KEYS) or not isinstance(value, int)
            or isinstance(value, bool) or not TIMEOUT_RANGE[0] <= value <= TIMEOUT_RANGE[1]):
        raise SystemExit("Error: the timeout_seconds amendment must appear once with exactly the keys "
                         f"{list(TIMEOUT_KEYS)} and a value from {TIMEOUT_RANGE[0]} to {TIMEOUT_RANGE[1]} seconds")
    return amendment


def request_timeout(student: dict[str, Any], amendment: dict[str, Any] | None) -> int:
    """Seconds the client waits for one response. With MC-110 amendment 4 only this wait differs; the frozen
    configuration, its hash and the condition keep the registered value."""
    return student["timeout_seconds"] if amendment is None else amendment["timeout_seconds"]


def session_id(card_id: str, run_key: str) -> str:
    """One OpenCode Go routing session per attempt, named by this card (MC-105 used vmlu-mc105-...)."""
    return f"vmlu-{card_id.lower().replace('-', '')}-{v1.sha256_bytes(run_key.encode('utf-8'))[:16]}"


def make_mimo_request(student: dict[str, Any], card_id: str, guard: pr.BudgetGuard, outage: pr.OutageGuard,
                      pin: ModelPin, bad_request: BadRequestRule | None = None):
    """MC-105's MiMo request (the MC-103 route): direct chat completions, no streaming, one routing session per
    attempt, behind one gate of `max_in_flight`; a fatal row halts every lane. `bad_request` decides an HTTP 400."""
    gate = threading.BoundedSemaphore(student["max_in_flight"])
    halt = threading.Event()
    bad_request = bad_request or BadRequestRule()

    def request(client, item, shard: int, lane: int) -> dict[str, Any]:
        cap = student["max_completion_tokens"]
        row = _base_row(item, card_id, shard, lane, student["api_protocol"])
        row.update({"temperature_sent": None, "reasoning_effort_sent": None, "seed_sent": None, "max_tokens": cap})
        if rsl._blocked(row, guard, outage, halt):  # noqa: SLF001
            halt.set()
            return row
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=base.MODEL, messages=[{"role": "system", "content": student["system_prompt"]},
                                            {"role": "user", "content": item.prompt}],
                max_completion_tokens=cap, stream=False,
                extra_headers={rsl.SESSION_HEADER: session_id(card_id, item.run_key)})
            if not response.choices:
                raise ValueError("no_choices")
            choice, usage = response.choices[0], response.usage
            detail = getattr(usage, "completion_tokens_details", None)
            prompt_detail = getattr(usage, "prompt_tokens_details", None)
            finish = str(choice.finish_reason or "unknown")
            tools = getattr(choice.message, "tool_calls", None) or []
            reasoning = getattr(choice.message, "reasoning_content", None)
            row.update({
                "raw_response": choice.message.content or "", "finish_reason": finish,
                "response_model_id": response.model, "request_id": response.id,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
                "reasoning_tokens": getattr(detail, "reasoning_tokens", None),
                "cached_prompt_tokens": getattr(prompt_detail, "cached_tokens", None),
                "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else None, "tool_call_n": len(tools),
                "status": "complete" if finish in COMPLETE_FINISHES and not tools else "request_error"})
            drift = pin.check(response.model) if row["status"] == "complete" else None
            if drift:
                row.update({"status": "request_error", "error_type": drift, "fatal": True})
            elif row["status"] != "complete":
                row.update({"error_type": "unexpected_finish_or_tool_call", "fatal": bool(tools)})
        except Exception as exc:  # noqa: BLE001 - never serialize SDK messages: they can echo upstream data
            status_code = getattr(exc, "status_code", None)
            row.update({"status": "request_error", "finish_reason": "error", "error_type": type(exc).__name__,
                        "http_status": status_code, "fatal": status_code in {400, 401, 402, 403, 404}})
            if status_code == 400:
                code = error_code(exc)
                reason = bad_request.fatal(item.run_key, code)
                row.update({"error_code": code, "fatal": reason is not None})
                if reason:
                    row["fatal_reason"] = reason
                elif bad_request.amendment is not None:
                    row["technical_400"] = f"amendment {bad_request.amendment['id']}"
        rsl._settle(row, start, guard, outage)  # noqa: SLF001
        if row.get("technical_400"):
            row["retry_wait_seconds"] = TRANSIENT_400_WAIT_SECONDS
        if row.get("fatal"):
            halt.set()
        return row

    def limited(client, item, shard: int, lane: int) -> dict[str, Any]:
        with gate:  # waiting here is not part of the measured latency: the clock starts inside `request`
            return request(client, item, shard, lane)
    return limited


# ---------------------------------------------------------------- condition, loop outputs

def build_condition(student: str, config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    route: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_id": vt.PROTOCOL_ID, "protocol_version": 1, "phase": vt.PHASE, "student": student,
        "measurement_card_id": registration["card_ids"][vt.PHASE],
        "measurement_card_hash": v1.sha256_file(pr.MEASUREMENT_CARD),
        "card_sha256": v1.sha256_file(ROOT / registration["card_files"][vt.PHASE]),
        "config_sha256": manifest["config_sha256"], "manifest_sha256": manifest["manifest_sha256"],
        **{key: manifest[key] for key in ("vmlu_manifest_sha256", "campaign_protocol_sha256", "prompt_templates_sha256",
                                         "source_sha256", "dataset_counts", "arm_counts")},
        "schedule": config["schedule"], "loop": config["loop"], "student_config": config["students"][student], **route,
        "module_sha256": v1.sha256_file(Path(vt.__file__)),
        "loop_module_sha256": v1.sha256_file(Path(tl.__file__)),
        "router_sha256": v1.sha256_file(Path(router.__file__)),
        "wrapper_sha256": v1.sha256_file(Path(dp.__file__)),
        "engine_sha256": v1.sha256_file(Path(pr.__file__)),
        "base_engine_sha256": v1.sha256_file(Path(base.__file__)),
        "shared_runner_sha256": v1.sha256_file(Path(rsl.__file__)),
        "runner_sha256": v1.sha256_file(Path(__file__)),
    }


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def loop_callback(student: str, card_id: str, item_ids: list[str], threshold: float | None,
                  timeout_cap: dict[str, Any] | None = None):
    """After each pass: loop.jsonl and summary.json; the two submissions once every item has a final answer. The
    before is B-r1 for both students; the probe confidence exists for Qwen only. With MC-110 amendment 2 the rule
    reads capped attempts as empty answers, and the summary lists them; the counts of completed attempts do not."""
    def write(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        view, capped = with_timeout_terminals(output, rows, timeout_cap)
        states = vt.plan(item_ids, view, threshold, student)
        complete = [row for row in rows.values() if row.get("status") == "complete"]
        records = [{"item_id": s.item_id, "final_replicate": s.final, "rounds": s.rounds, "answer": s.answer,
                    "before": s.predictions.get("B-r1"), "confidence": s.confidence, "predictions": s.predictions,
                    "needed": list(s.needed)} for s in states]
        v1.write_jsonl_atomic(output / "loop.jsonl", records)
        decided = [s for s in states if s.final is not None]
        tokens = [dp.reported_tokens(row) for row in complete]
        summary = {
            "protocol_id": vt.PROTOCOL_ID, "phase": vt.PHASE, "student": student, "measurement_card_id": card_id,
            "model_id": base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": base.now(),
            "items": len(states), "final_items": len(decided),
            "rounds": dict(sorted(Counter(s.rounds for s in decided).items())),
            "still_needed": dict(sorted(Counter(r for s in states for r in s.needed).items())),
            "complete_attempts": dict(sorted(Counter(str(row["replicate_id"]) for row in complete).items())),
            "failed_rows_latest": sum(row.get("status") != "complete" for row in rows.values()),
            "final_differs_from_before": sum(s.answer != s.predictions.get("B-r1") for s in decided),
            "empty_before": sum(not s.predictions.get("B-r1") for s in states if "B-r1" in s.predictions),
            "empty_final": sum(not s.answer for s in decided),
            "confidence_missing": sum(s.confidence is None for s in states if "B-r1" in s.predictions)
            if student == "qwen" else None,
            "reported_tokens": sum(t for t in tokens if isinstance(t, int)),
            "reported_tokens_per_final_item": round(sum(t for t in tokens if isinstance(t, int)) / len(decided), 1)
            if decided and len(decided) == len(states) else None,
            "latency_s_mean": {arm: _mean([float(row["latency_s"]) for row in complete if row.get("arm") == arm
                                           and row.get("latency_s") is not None]) for arm in ("B", "S")},
            "gold": "withheld; accuracy comes only from vmlu.ai",
        }
        if timeout_cap is not None:
            summary["timeout_cap"] = {"amendment": timeout_cap["id"], "max_timeouts": timeout_cap["max_timeouts"],
                                      "capped_attempts": len(capped),
                                      "capped_by_replicate": dict(sorted(Counter(k.rsplit(":", 1)[1]
                                                                                 for k in capped).items())),
                                      "capped_run_keys": capped}
        if len(decided) == len(states):
            write_csv_atomic(output / "submission_before.csv",
                             [{"id": s.item_id, "answer": s.predictions["B-r1"]} for s in states], ["id", "answer"])
            write_csv_atomic(output / "submission_loop.csv",
                             [{"id": s.item_id, "answer": s.answer or ""} for s in states], ["id", "answer"])
            summary["submissions"] = {name: v1.sha256_file(output / name)
                                      for name in ("submission_before.csv", "submission_loop.csv")}
        base.atomic_json(output / "summary.json", summary)
    return write


def run_passes(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], item_ids: list[str],
               condition: dict[str, Any], client, resume: bool, *, max_passes: int, threshold: float | None,
               score_callback, runner_path: Path, execute=None, student: str = "qwen",
               timeout_cap: dict[str, Any] | None = None) -> str:
    """Send what the rule needs, pass after pass. Returns complete, paused, stalled or incomplete. With MC-110
    amendment 2 the rule reads capped attempts as empty answers (`with_timeout_terminals`), so they are not sent."""
    execute = execute or base.execute
    resume_next = resume

    def view() -> tuple[dict[str, Any], dict[str, Any]]:
        rows = base.load_rows(output, manifest)
        return rows, with_timeout_terminals(output, rows, timeout_cap)[0]

    for number in range(1, max_passes + 1):
        rows, ruled = view()
        states = vt.plan(item_ids, ruled, threshold, student)
        send = [rebuilt[f"{vt.DATASET}:{s.item_id}:{r}"] for s in states for r in s.needed]
        keys = [item.run_key for item in send]
        if len(set(keys)) != len(keys) or any((rows.get(key) or {}).get("status") == "complete" for key in keys):
            raise SystemExit("Error: a pass would send one attempt twice or re-send a completed one")
        done = sum(row.get("status") == "complete" for row in ruled.values())
        print(f"pass {number}: final {sum(s.final is not None for s in states)}/{len(states)}; sending {len(send)} "
              f"{dict(sorted(Counter(item.replicate_id for item in send).items()))}", flush=True)
        if not send:
            return "complete"
        execute(output, manifest, rebuilt, send, condition, client, resume_next, score_callback=score_callback,
                runner_path=runner_path, work_stealing=True)
        resume_next = True
        if json.loads((output / "run.json").read_text(encoding="utf-8")).get("status") == "paused":
            return "paused"
        if sum(row.get("status") == "complete" for row in view()[1].values()) == done:
            return "stalled"
    states = vt.plan(item_ids, view()[1], threshold, student)
    return "complete" if all(s.final is not None for s in states) else "incomplete"


def record_launch(output: Path, student: str, *, resume: bool, note: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    event = {"at": base.now(), "phase": vt.PHASE, "student": student, "resume": resume,
             "runner_sha256": v1.sha256_file(Path(__file__)), "note": note}
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(event, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--student", choices=vt.STUDENTS, required=True)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="continue from the ledger")
    ap.add_argument("--tunnel-dns", default=None, help="in-tunnel DNS server for the Qwen endpoint host (this process only)")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    if args.tunnel_dns and args.student != "qwen":
        ap.error("--tunnel-dns applies to the Qwen endpoint only")
    config, _ = vt.load_config(vt.CONFIG_PATHS[args.student])
    registration = load_registration(vt.REGISTRATION_PATHS[args.student])
    student = config["students"][args.student]
    manifest, rebuilt = vt.build_manifest(args.student)
    items = vt.verify_rows(manifest, rebuilt)
    campaign = dp.load_protocol()
    env = dotenv_values(ROOT / ".env")
    endpoint = key = model_id = credential_source = ""
    if args.student == "qwen":
        route_ok, route_detail = rsl.qwen_route(campaign, env)
    else:
        endpoint, key, model_id, credential_source, route_ok, route_detail = rsl.mimo_route(student)
    gates = evaluate_gates(args.student, manifest, registration, route_ok, route_detail)
    amendment = transient_400_amendment(registration) if args.student == "mimo" else None
    if args.student == "mimo":
        print(f"HTTP 400: {'amendment ' + str(amendment['id']) + ' (transient_400)' if amendment else 'registered halt'}")
    if args.student == "qwen":
        unreadable = unreadable_probes(items)
        print(f"probed prompts whose option letters cannot be read (confidence missing, so unsure): {len(unreadable)} "
              f"{unreadable[:20]}")
    print(f"student={args.student} phase={vt.PHASE} items={manifest['item_count']} possible_attempts={manifest['n']} "
          f"arms={manifest['arm_counts']} max_in_flight={student['max_in_flight']} "
          f"max_passes={config['schedule']['max_passes']}")
    print(f"manifest_sha256={manifest['manifest_sha256']} config_sha256={manifest['config_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    print(f"preflight=passed items={manifest['item_count']} endpoint_calls=0", flush=True)
    if not args.execute:
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise SystemExit("Error: execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    card_id = str(registration["card_ids"][vt.PHASE])
    item_ids = [item.item_id for item in items if item.replicate_id == "B-r1"]
    threshold = float(config["loop"]["threshold"]) if args.student == "qwen" else None
    max_passes = int(config["schedule"]["max_passes"])
    if args.student == "mimo":
        output = OUTPUT_ROOT / student["profile_id"]
        route = {"model_id": model_id, "credential_source": credential_source,
                 "endpoint_host": urlsplit(endpoint).hostname, "base_url_sha256": v1.sha256_bytes(endpoint.encode())}
        condition = pr.reconcile_resume(output, build_condition(args.student, config, manifest, registration, route),
                                        args.resume)
        guard = pr.BudgetGuard(student["budget_tokens"], pr.existing_usage(output))
        bad_request = BadRequestRule(amendment, attempts_with_400(output) if amendment else frozenset())
        if amendment:
            print(f"amendment {amendment['id']} (transient_400): attempts with an earlier HTTP 400: "
                  f"{len(bad_request.seen)} of at most {amendment['max_attempts_with_400']}", flush=True)
        base.MODEL, base.PROFILE, base.PROTOCOL, base.CARD_ID = model_id, student["profile_id"], vt.PROTOCOL_ID, card_id
        timeout_cap = timeout_cap_amendment(registration)
        if timeout_cap:
            capped = with_timeout_terminals(output, base.load_rows(output, manifest), timeout_cap)[1] \
                if (output / "attempts.jsonl").is_file() else []
            print(f"amendment {timeout_cap['id']} (timeout_cap): attempts read as empty answers after "
                  f"{timeout_cap['max_timeouts']} timeouts: {len(capped)}", flush=True)
        in_flight = in_flight_amendment(registration)
        if in_flight:
            print(f"amendment {in_flight['id']} (max_in_flight): requests in flight {student['max_in_flight']} -> "
                  f"{in_flight['max_in_flight']}", flush=True)
        base.request = make_mimo_request(gated_student(student, in_flight), card_id, guard,
                                         pr.OutageGuard(student["stop_after_timeouts"]),
                                         ModelPin(student["model_identity"]), bad_request)
        wait = timeout_amendment(registration)
        if wait:
            print(f"amendment {wait['id']} (timeout_seconds): request timeout {student['timeout_seconds']} s -> "
                  f"{wait['timeout_seconds']} s", flush=True)
        record_launch(output, args.student, resume=args.resume, note=args.note)
        with OpenAI(base_url=endpoint, api_key=key, timeout=request_timeout(student, wait),
                    max_retries=student["sdk_retries"]) as client:
            status = run_passes(output, manifest, rebuilt, item_ids, condition, client, args.resume,
                                max_passes=max_passes, threshold=None, student="mimo",
                                score_callback=loop_callback(args.student, card_id, item_ids, None, timeout_cap),
                                runner_path=Path(__file__), timeout_cap=timeout_cap)
        print(f"loop_status={status} output={output}", flush=True)
        return 0 if status == "complete" else 1
    endpoint, key = str(env["OPENAI_BASE_URL"]), str(env["OPENAI_API_KEY"])
    if args.tunnel_dns:
        address = pr.install_resolver_shim(urlsplit(endpoint).hostname or "", args.tunnel_dns)
        print(f"resolver shim (this process only) -> {address} via {args.tunnel_dns}")
    transport, model = campaign["transport"], campaign["model"]
    output = OUTPUT_ROOT / model["profile_id"]
    route = {"model_id": model["requested_id"], "self_reported_model_id": model["self_reported_id"],
             "profile_id": model["profile_id"], "provider": model["provider"], "endpoint_host": urlsplit(endpoint).hostname,
             "base_url_sha256": v1.sha256_bytes(endpoint.encode()), "transport": transport}
    condition = pr.reconcile_resume(output, build_condition(args.student, config, manifest, registration, route),
                                    args.resume)
    guard = pr.BudgetGuard(student["budget_tokens"], pr.existing_usage(output))
    if (base.SHARDS, base.LANES) != (transport["shards"], transport["lanes"]):
        raise SystemExit("Error: engine shard/lane constants differ from the campaign protocol")
    base.MODEL, base.PROFILE, base.PROTOCOL, base.CARD_ID = model["requested_id"], model["profile_id"], vt.PROTOCOL_ID, card_id
    base.request = make_qwen_request(student, campaign, card_id, guard, pr.OutageGuard(student["stop_after_timeouts"]))
    record_launch(output, args.student, resume=args.resume, note=args.note)
    with OpenAI(base_url=endpoint, api_key=key, timeout=transport["timeout_seconds"],
                max_retries=transport["sdk_retries"], default_headers=transport["gateway_header"]) as client:
        status = run_passes(output, manifest, rebuilt, item_ids, condition, client, args.resume,
                            max_passes=max_passes, threshold=threshold,
                            score_callback=loop_callback(args.student, card_id, item_ids, threshold),
                            runner_path=Path(__file__))
    print(f"loop_status={status} output={output}", flush=True)
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
