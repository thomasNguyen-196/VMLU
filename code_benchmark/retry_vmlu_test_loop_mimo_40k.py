"""MC-110c: ask MC-110's unanswered attempts again with a 40,000-token cap and an 1,800 s wait.

MC-110 (MiMo V2.6 Flash, the self-improvement loop on the 9,833 VMLU test items) finished on 2026-11-10 with 89
empty final answers. Two causes left an attempt without an answer:
  - 183 attempts timed out three times at 300 s (read as empty under MC-110's amendment 2);
  - 355 attempts were cut by the 20,000-token cap before any visible text (finish reason `length`).
MC-110b re-asked the 183 with a 900 s wait and the same 20,000-token cap. The owner stopped it during its first
pass (94 of 101 rows: 77 cut by the cap again, 17 answered below it) and asked for a 40,000-token cap.

This card re-asks all 538 attempts with max_completion_tokens 40,000 and an 1,800 s wait, round by round under
MC-110's unchanged rule; an attempt the rule no longer needs is not sent. A reply that stopped below 20,000 tokens is
a reply the 40,000 cap would have allowed too, so MC-110b's 17 stopped rows are reused, not re-asked; its rows cut
by the cap are not.

MC-110's and MC-110b's outputs are read through hash gates, never written. The rule reads a candidate attempt from
this card's ledger once it completes, from MC-110b's stopped row when there is one, as an empty answer once it has
timed out three times here, and as missing otherwise (so it is asked).

From the repository root:
  .venv/bin/python -m code_benchmark.retry_vmlu_test_loop_mimo_40k                       # offline preflight
  .venv/bin/python -m code_benchmark.retry_vmlu_test_loop_mimo_40k --execute [--resume]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from openai import OpenAI

from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_vmlu_test_loop as vt
from code_benchmark import retry_vmlu_test_loop_mimo_900s as mc110b
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_self_loop as rsl
from code_benchmark import run_vmlu_test_loop as rvt
from code_benchmark import vi_multimodel as v1
from code_benchmark.common import write_csv_atomic

ROOT = rvt.ROOT
base = rvt.base
Gate = rvt.Gate

CARD_ID = "MC-110c"
PARENT_CARD_ID = "MC-110"
SIBLING_CARD_ID = "MC-110b"
CARD_FILE = "docs/measurement_cards/MC-110c-diagnostic-vmlu-test-loop-mimo-40k.md"
PARENT = mc110b.PARENT
SIBLING = mc110b.OUTPUT
OUTPUT = rvt.OUTPUT_ROOT / "mimo-v2-6-flash-40k"
# MC-110b's ledger as the owner's stop left it (2026-11-10 11:56 +07, 94 rows); the recovery refuses any other.
SIBLING_LEDGER_SHA256 = "1f89125b975137c7bf8fda5f0140f59a18835ab8b66d3112a49aac058e2caf21"
CANDIDATES = {"timeout": 183, "length": 355}
REUSED = 17

MAX_COMPLETION_TOKENS = 40_000
TIMEOUT_SECONDS = 1800
MAX_TIMEOUTS = 3
TIMEOUT_ERRORS = ("APITimeoutError",)
MAX_IN_FLIGHT = 12
BUDGET_TOKENS = 20_000_000
MAX_PASSES = 12


def request_settings(student: dict[str, Any]) -> dict[str, Any]:
    """MC-110's student settings for the request; only the token cap and the gate differ."""
    return {**student, "max_completion_tokens": MAX_COMPLETION_TOKENS, "max_in_flight": MAX_IN_FLIGHT}


def answer(row: dict[str, Any]) -> str:
    return vt.b_prediction(row) if str(row["replicate_id"]).startswith("B") else vt.s_prediction(row)


# ---------------------------------------------------------------- MC-110's and MC-110b's final state

def candidates(parent_rows: dict[str, Any], capped: list[str]) -> dict[str, str]:
    """Run key -> why it has no answer in MC-110: `timeout` (capped by amendment 2) or `length` (cut by the cap)."""
    found = dict.fromkeys(capped, "timeout")
    for key, row in parent_rows.items():
        if key not in found and row.get("status") == "complete" and row.get("finish_reason") == "length":
            found[key] = "length"
    return dict(sorted(found.items()))


def reusable(sibling_rows: dict[str, Any], cands: dict[str, str]) -> dict[str, Any]:
    """MC-110b's rows that stopped below the 20,000-token cap, on candidate attempts."""
    return {key: row for key, row in sibling_rows.items()
            if key in cands and row.get("status") == "complete" and row.get("finish_reason") == "stop"}


def recovery_view(parent_rows: dict[str, Any], reused: dict[str, Any], recovery: dict[str, Any],
                  timeouts: Counter[str], cands: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """(rows the rule reads, candidates capped again here). MC-110's rows for every attempt but the candidates; a
    candidate is MC-110b's stopped row, this card's completed row, an empty answer after MAX_TIMEOUTS timeouts here,
    or missing."""
    view = {key: row for key, row in parent_rows.items() if key not in cands}
    again = []
    for key in cands:
        row = recovery.get(key)
        if key in reused:
            view[key] = reused[key]
        elif row is not None and row.get("status") == "complete":
            view[key] = row
        elif timeouts[key] >= MAX_TIMEOUTS:
            view[key] = {**(row or parent_rows[key]), "status": "complete", "raw_response": "",
                         "terminal": f"{CARD_ID}: {timeouts[key]} timeouts at {TIMEOUT_SECONDS} s"}
            again.append(key)
    return view, again


def ledger_rows(output: Path) -> list[dict[str, Any]]:
    path = output / "attempts.jsonl"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def latest_rows(output: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return base.load_rows(output, manifest) if (output / "attempts.jsonl").is_file() else {}


# ---------------------------------------------------------------- outputs

def writer(item_ids: list[str], parent_rows: dict[str, Any], reused: dict[str, Any], cands: dict[str, str],
           parent_loop: dict[str, Any]):
    """After each pass: loop.jsonl and summary.json from the overlaid rows; the two submissions once every item is
    final. `parent_loop` is MC-110's loop.jsonl by item, for the changes against MC-110."""

    def write(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        timeouts = rvt.timeouts_by_attempt(output, TIMEOUT_ERRORS)
        view, again = recovery_view(parent_rows, reused, rows, timeouts, cands)
        states = vt.plan(item_ids, view, None, "mimo")
        needed = {f"{vt.DATASET}:{s.item_id}:{r}" for s in states for r in s.needed}
        records = [{"item_id": s.item_id, "final_replicate": s.final, "rounds": s.rounds, "answer": s.answer,
                    "before": s.predictions.get("B-r1"), "confidence": None, "predictions": s.predictions,
                    "needed": list(s.needed), "mc110_answer": parent_loop[s.item_id]["answer"],
                    "mc110_before": parent_loop[s.item_id]["before"]} for s in states]
        v1.write_jsonl_atomic(output / "loop.jsonl", records)
        decided = [s for s in states if s.final is not None]
        sent = {key: row for key, row in rows.items() if key in cands}
        complete = [row for row in sent.values() if row.get("status") == "complete"]
        read = [view[key] for key in cands if key in view and key not in again]
        tokens = [dp.reported_tokens(row) for row in complete]
        summary: dict[str, Any] = {
            "protocol_id": vt.PROTOCOL_ID, "phase": vt.PHASE, "student": "mimo", "measurement_card_id": CARD_ID,
            "recovery_of": PARENT_CARD_ID, "parent_ledger_sha256": mc110b.PARENT_LEDGER_SHA256,
            "reuses": SIBLING_CARD_ID, "sibling_ledger_sha256": SIBLING_LEDGER_SHA256,
            "model_id": base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": base.now(),
            "max_completion_tokens": MAX_COMPLETION_TOKENS, "timeout_seconds": TIMEOUT_SECONDS,
            "max_timeouts": MAX_TIMEOUTS,
            "candidates": len(cands), "candidates_by_cause": dict(sorted(Counter(cands.values()).items())),
            "candidates_by_replicate": dict(sorted(Counter(k.rsplit(":", 1)[1] for k in cands).items())),
            "reused_from_mc110b": len(reused),
            "sent": len(sent), "ledger_rows": len(ledger_rows(output)), "completed": len(complete),
            "completed_by_finish": dict(sorted(Counter(str(row.get("finish_reason")) for row in complete).items())),
            "completed_with_answer": sum(bool(answer(row)) for row in complete),
            "candidates_read_with_answer": sum(bool(answer(row)) for row in read),
            "capped_again": again,
            "never_needed": sorted(k for k in cands if k not in view and k not in needed),
            "items": len(states), "final_items": len(decided),
            "rounds": dict(sorted(Counter(s.rounds for s in decided).items())),
            "still_needed": dict(sorted(Counter(r for s in states for r in s.needed).items())),
            "final_differs_from_before": sum(s.answer != s.predictions.get("B-r1") for s in decided),
            "empty_before": sum(not s.predictions.get("B-r1") for s in states if "B-r1" in s.predictions),
            "empty_final": sum(not s.answer for s in decided),
            "changed_from_mc110": {
                "before": sum(s.predictions.get("B-r1") != parent_loop[s.item_id]["before"] for s in states
                              if "B-r1" in s.predictions),
                "loop": sum(s.answer != parent_loop[s.item_id]["answer"] for s in decided)},
            "reported_tokens": sum(t for t in tokens if isinstance(t, int)),
            "gold": "withheld; accuracy comes only from vmlu.ai",
        }
        if len(decided) == len(states):
            write_csv_atomic(output / "submission_before.csv",
                             [{"id": s.item_id, "answer": s.predictions["B-r1"]} for s in states], ["id", "answer"])
            write_csv_atomic(output / "submission_loop.csv",
                             [{"id": s.item_id, "answer": s.answer or ""} for s in states], ["id", "answer"])
            summary["submissions"] = {name: v1.sha256_file(output / name)
                                      for name in ("submission_before.csv", "submission_loop.csv")}
        base.atomic_json(output / "summary.json", summary)
    return write


# ---------------------------------------------------------------- passes

def run_recovery(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], item_ids: list[str],
                 condition: dict[str, Any], client, resume: bool, *, parent_rows: dict[str, Any],
                 reused: dict[str, Any], cands: dict[str, str], score_callback, max_passes: int = MAX_PASSES,
                 execute=None) -> str:
    """Send what MC-110's rule needs among the candidates, pass after pass. Returns complete, paused, stalled or
    incomplete. A pass whose rows neither complete nor time out (say every reply is a 429) stalls the run."""
    execute = execute or base.execute
    resume_next = resume

    def states_now() -> tuple[dict[str, Any], list[vt.ItemState]]:
        recovery = latest_rows(output, manifest)
        view = recovery_view(parent_rows, reused, recovery, rvt.timeouts_by_attempt(output, TIMEOUT_ERRORS),
                             cands)[0]
        return recovery, vt.plan(item_ids, view, None, "mimo")

    for number in range(1, max_passes + 1):
        recovery, states = states_now()
        keys = [f"{vt.DATASET}:{s.item_id}:{r}" for s in states for r in s.needed]
        if len(set(keys)) != len(keys) or any(key not in cands or key in reused for key in keys) \
                or any((recovery.get(key) or {}).get("status") == "complete" for key in keys):
            raise SystemExit("Error: a pass would send an attempt that is not a candidate, a reused one, one twice, "
                             "or a completed one")
        print(f"pass {number}: final {sum(s.final is not None for s in states)}/{len(states)}; sending {len(keys)} "
              f"{dict(sorted(Counter(k.rsplit(':', 1)[1] for k in keys).items()))}", flush=True)
        if not keys:
            return "complete"
        written = len(ledger_rows(output))
        execute(output, manifest, rebuilt, [rebuilt[key] for key in keys], condition, client, resume_next,
                score_callback=score_callback, runner_path=Path(__file__), work_stealing=True)
        resume_next = True
        if json.loads((output / "run.json").read_text(encoding="utf-8")).get("status") == "paused":
            return "paused"
        new = ledger_rows(output)[written:]
        if not any(row.get("status") == "complete" or row.get("error_type") in TIMEOUT_ERRORS for row in new):
            return "stalled"
    return "complete" if all(s.final is not None for s in states_now()[1]) else "incomplete"


# ---------------------------------------------------------------- gates, condition, main

def evaluate_gates(manifest: dict[str, Any], capped: list[str], cands: dict[str, str], reused: dict[str, Any],
                   route_ok: bool, route_detail: str, *, parent: Path = PARENT, sibling: Path = SIBLING,
                   card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    inherited = {g.name: g for g in mc110b.evaluate_gates(manifest, capped, route_ok, route_detail, parent=parent,
                                                          card_text=text, root=root)}
    gates = [Gate("card_registered", re.search(rf"^#{{2,3}} {re.escape(CARD_ID)}\b", text, re.MULTILINE) is not None,
                  f"{CARD_ID} heading in measurement_card.md"),
             Gate("detail_card", (root / CARD_FILE).is_file(), CARD_FILE),
             inherited["parent_ledger"], inherited["parent_final"], inherited["retry_candidates"]]
    ledger = sibling / "attempts.jsonl"
    gates.append(Gate("sibling_ledger", ledger.is_file() and v1.sha256_file(ledger) == SIBLING_LEDGER_SHA256,
                      f"{SIBLING_CARD_ID} ledger as stopped, sha256 {SIBLING_LEDGER_SHA256[:12]}"))
    gates.append(Gate("candidates", dict(Counter(cands.values())) == CANDIDATES and len(reused) == REUSED,
                      f"{len(cands)} candidates {dict(sorted(Counter(cands.values()).items()))}, {len(reused)} reused; "
                      f"registered {CANDIDATES}, {REUSED}"))
    gates.append(inherited["route_identity"])
    return gates


def build_condition(config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    route: dict[str, Any], cands: dict[str, str], reused: dict[str, Any]) -> dict[str, Any]:
    condition = rvt.build_condition("mimo", config, manifest, registration, route)
    condition.update({
        "measurement_card_id": CARD_ID, "card_sha256": v1.sha256_file(ROOT / CARD_FILE),
        "recovery": {"parent_card_id": PARENT_CARD_ID, "parent_ledger_sha256": mc110b.PARENT_LEDGER_SHA256,
                     "parent_condition_sha256": mc110b.PARENT_CONDITION_SHA256,
                     "reuses": SIBLING_CARD_ID, "sibling_ledger_sha256": SIBLING_LEDGER_SHA256,
                     "candidates": len(cands), "candidates_by_cause": dict(sorted(Counter(cands.values()).items())),
                     "candidates_sha256": v1.sha256_bytes("\n".join(cands).encode("utf-8")),
                     "reused": len(reused), "reused_sha256": v1.sha256_bytes("\n".join(sorted(reused)).encode("utf-8")),
                     "max_completion_tokens": MAX_COMPLETION_TOKENS, "timeout_seconds": TIMEOUT_SECONDS,
                     "max_timeouts": MAX_TIMEOUTS, "timeout_errors": list(TIMEOUT_ERRORS),
                     "max_in_flight": MAX_IN_FLIGHT, "budget_tokens": BUDGET_TOKENS, "max_passes": MAX_PASSES,
                     "transient_400": "MC-110 amendment 1, counted in this ledger"},
        "recovery_runner_sha256": v1.sha256_file(Path(__file__)),
    })
    return condition


def record_launch(output: Path, *, resume: bool, note: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    event = {"at": base.now(), "card_id": CARD_ID, "resume": resume,
             "runner_sha256": v1.sha256_file(Path(__file__)), "note": note}
    with (output / "operator_events.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(event, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="send requests (otherwise offline preflight only)")
    ap.add_argument("--resume", action="store_true", help="continue from this recovery's ledger")
    ap.add_argument("--note", default="", help="free text recorded with this launch")
    args = ap.parse_args(argv)
    if args.resume and not args.execute:
        ap.error("--resume requires --execute")
    config, _ = vt.load_config(vt.CONFIG_PATHS["mimo"])
    registration = rvt.load_registration(vt.REGISTRATION_PATHS["mimo"])
    student = config["students"]["mimo"]
    manifest, rebuilt = vt.build_manifest("mimo")
    items = vt.verify_rows(manifest, rebuilt)
    item_ids = [item.item_id for item in items if item.replicate_id == "B-r1"]
    endpoint, key, model_id, credential_source, route_ok, route_detail = rsl.mimo_route(student)
    base.MODEL, base.PROFILE, base.PROTOCOL, base.CARD_ID = student["model_id"], student["profile_id"], \
        vt.PROTOCOL_ID, CARD_ID
    parent_rows, capped = mc110b.parent_state(manifest, registration)
    cands = candidates(parent_rows, capped)
    reused = reusable(latest_rows(SIBLING, manifest), cands)
    gates = evaluate_gates(manifest, capped, cands, reused, route_ok, route_detail)
    recovery = latest_rows(OUTPUT, manifest)
    view = recovery_view(parent_rows, reused, recovery, rvt.timeouts_by_attempt(OUTPUT, TIMEOUT_ERRORS), cands)[0]
    needed = [f"{vt.DATASET}:{s.item_id}:{r}" for s in vt.plan(item_ids, view, None, "mimo") for r in s.needed]
    print(f"card={CARD_ID} recovery_of={PARENT_CARD_ID} candidates={len(cands)} "
          f"{dict(sorted(Counter(cands.values()).items()))} "
          f"{dict(sorted(Counter(k.rsplit(':', 1)[1] for k in cands).items()))} "
          f"items={len({k.split(':')[1] for k in cands})} reused_from_{SIBLING_CARD_ID}={len(reused)}")
    print(f"max_completion_tokens={MAX_COMPLETION_TOKENS:,} timeout={TIMEOUT_SECONDS}s max_timeouts={MAX_TIMEOUTS} "
          f"max_in_flight={MAX_IN_FLIGHT} budget_tokens={BUDGET_TOKENS:,} max_passes={MAX_PASSES} output={OUTPUT}")
    print(f"next pass would send {len(needed)} {dict(sorted(Counter(k.rsplit(':', 1)[1] for k in needed).items()))}"
          f"; recovery ledger rows={len(ledger_rows(OUTPUT))}")
    print(f"manifest_sha256={manifest['manifest_sha256']}")
    print("gates: " + " ".join(f"{gate.name}={'PASS' if gate.ok else 'FAIL'}" for gate in gates))
    for gate in gates:
        if not gate.ok:
            print(f"  - {gate.name}: {gate.detail}")
    print("preflight=passed endpoint_calls=0", flush=True)
    if not args.execute:
        return 0
    failed = [gate for gate in gates if not gate.ok]
    if failed:
        raise SystemExit("Error: execution gates failed: " + "; ".join(f"{g.name} ({g.detail})" for g in failed))
    if model_id != student["model_id"]:
        raise SystemExit("Error: the route resolves another model")
    route = {"model_id": model_id, "credential_source": credential_source,
             "endpoint_host": urlsplit(endpoint).hostname, "base_url_sha256": v1.sha256_bytes(endpoint.encode())}
    condition = pr.reconcile_resume(OUTPUT, build_condition(config, manifest, registration, route, cands, reused),
                                    args.resume)
    guard = pr.BudgetGuard(BUDGET_TOKENS, pr.existing_usage(OUTPUT))
    transient = rvt.transient_400_amendment(registration)
    bad_request = rvt.BadRequestRule(transient, rvt.attempts_with_400(OUTPUT) if transient else frozenset())
    base.request = rvt.make_mimo_request(request_settings(student), CARD_ID, guard,
                                         pr.OutageGuard(student["stop_after_timeouts"]),
                                         rvt.ModelPin(student["model_identity"]), bad_request)
    with (PARENT / "loop.jsonl").open(encoding="utf-8") as handle:
        parent_loop = {row["item_id"]: row for row in map(json.loads, handle)}
    print(f"budget guard {BUDGET_TOKENS:,} reported tokens; already used {guard.used:,}", flush=True)
    record_launch(OUTPUT, resume=args.resume, note=args.note)
    with OpenAI(base_url=endpoint, api_key=key, timeout=TIMEOUT_SECONDS, max_retries=student["sdk_retries"]) as client:
        status = run_recovery(OUTPUT, manifest, rebuilt, item_ids, condition, client, args.resume,
                              parent_rows=parent_rows, reused=reused, cands=cands,
                              score_callback=writer(item_ids, parent_rows, reused, cands, parent_loop))
    print(f"recovery_status={status} output={OUTPUT}", flush=True)
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
