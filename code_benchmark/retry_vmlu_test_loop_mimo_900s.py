"""MC-110b: send MC-110's timed-out attempts again with a 900 s wait.

MC-110 (MiMo V2.6 Flash, the self-improvement loop on the 9,833 VMLU test items) finished on 2026-11-10 with 183
attempts read as empty answers under its amendment 2: each had timed out three times, every time at the registered
300 s wait (amendment 4's 900 s applied to attempts sent from launch 47 on, after these were capped). This recovery
asks those attempts again with a 900 s wait, round by round under MC-110's unchanged rule, so an attempt the rule
no longer needs once an earlier one has an answer is not sent. Everything else is MC-110's request.

MC-110's outputs are read, never written: the recovery checks MC-110's final ledger by its hash, writes its own
ledger, and overlays only the retried attempts. The rule reads a retried attempt from the recovery ledger once it
completes, as an empty answer once it has timed out three times here, and as missing otherwise (so it is asked).

From the repository root:
  .venv/bin/python -m code_benchmark.retry_vmlu_test_loop_mimo_900s                       # offline preflight
  .venv/bin/python -m code_benchmark.retry_vmlu_test_loop_mimo_900s --execute [--resume]
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
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_self_loop as rsl
from code_benchmark import run_vmlu_test_loop as rvt
from code_benchmark import vi_multimodel as v1
from code_benchmark.common import write_csv_atomic

ROOT = rvt.ROOT
base = rvt.base
Gate = rvt.Gate

CARD_ID = "MC-110b"
PARENT_CARD_ID = "MC-110"
CARD_FILE = "docs/measurement_cards/MC-110b-diagnostic-vmlu-test-loop-mimo-retry900.md"
PARENT = rvt.OUTPUT_ROOT / "mimo-v2-6-flash"
OUTPUT = rvt.OUTPUT_ROOT / "mimo-v2-6-flash-retry900"
# MC-110's final state (launch 48 finished 2026-11-10 10:08 +07); the recovery refuses any other.
PARENT_LEDGER_SHA256 = "1e6b9e80c95958b37b71abe02defce14a09c425d59553f15a453661d23e9d290"
PARENT_CONDITION_SHA256 = "e1d5f3315040b1bd8158818c7329debb426a88e2fb336e1bb19087f842c3a048"
PARENT_SUBMISSIONS = {"submission_before.csv": "f9c03983d5650d546f5a84fef987fab6a05b4234c85f7c2cf9b25924fb9e7035",
                      "submission_loop.csv": "92ee823acbe7a6e5390028f5a7a6e3a2f95561cc4f415415d0b64a8016235b5c"}
PARENT_CAPPED = 183

TIMEOUT_SECONDS = 900
MAX_TIMEOUTS = 3
TIMEOUT_ERRORS = ("APITimeoutError",)
MAX_IN_FLIGHT = 12
BUDGET_TOKENS = 5_000_000
MAX_PASSES = 12


# ---------------------------------------------------------------- MC-110's final state

def parent_state(manifest: dict[str, Any], registration: dict[str, Any],
                 parent: Path = PARENT) -> tuple[dict[str, Any], list[str]]:
    """(MC-110's latest row per attempt, its capped run keys), read through MC-110's own amendment 2."""
    rows = base.load_rows(parent, manifest)
    capped = rvt.with_timeout_terminals(parent, rows, rvt.timeout_cap_amendment(registration))[1]
    return rows, capped


def recovery_view(parent_rows: dict[str, Any], recovery: dict[str, Any], timeouts: Counter[str],
                  capped: set[str] | frozenset[str]) -> tuple[dict[str, Any], list[str]]:
    """(rows the rule reads, retried keys capped again). MC-110's rows for every attempt but the capped ones; a capped
    attempt is the recovery's completed row, an empty answer after MAX_TIMEOUTS timeouts here, or missing."""
    view = {key: row for key, row in parent_rows.items() if key not in capped}
    again = []
    for key in sorted(capped):
        row = recovery.get(key)
        if row is not None and row.get("status") == "complete":
            view[key] = row
        elif timeouts[key] >= MAX_TIMEOUTS:
            view[key] = {**(row or parent_rows[key]), "status": "complete", "raw_response": "",
                         "terminal": f"{CARD_ID}: {timeouts[key]} timeouts at {TIMEOUT_SECONDS} s"}
            again.append(key)
    return view, again


def _recovery_rows(output: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return base.load_rows(output, manifest) if (output / "attempts.jsonl").is_file() else {}


def _ledger_rows(output: Path) -> list[dict[str, Any]]:
    path = output / "attempts.jsonl"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _answer(row: dict[str, Any]) -> str:
    return vt.b_prediction(row) if str(row["replicate_id"]).startswith("B") else vt.s_prediction(row)


# ---------------------------------------------------------------- outputs

def writer(item_ids: list[str], parent_rows: dict[str, Any], capped: list[str], parent_loop: dict[str, Any]):
    """After each pass: loop.jsonl and summary.json from the overlaid rows; the two submissions once every item is
    final. `parent_loop` is MC-110's loop.jsonl by item, for the changes against MC-110."""
    capped_set = frozenset(capped)

    def write(output: Path, manifest: dict[str, Any], rebuilt: dict[str, Any], rows: dict[str, Any],
              meta: dict[str, Any]) -> None:
        timeouts = rvt.timeouts_by_attempt(output, TIMEOUT_ERRORS)
        view, again = recovery_view(parent_rows, rows, timeouts, capped_set)
        states = vt.plan(item_ids, view, None, "mimo")
        records = [{"item_id": s.item_id, "final_replicate": s.final, "rounds": s.rounds, "answer": s.answer,
                    "before": s.predictions.get("B-r1"), "confidence": None, "predictions": s.predictions,
                    "needed": list(s.needed), "mc110_answer": parent_loop[s.item_id]["answer"],
                    "mc110_before": parent_loop[s.item_id]["before"]} for s in states]
        v1.write_jsonl_atomic(output / "loop.jsonl", records)
        decided = [s for s in states if s.final is not None]
        retried = {key: row for key, row in rows.items() if key in capped_set}
        complete = [row for row in retried.values() if row.get("status") == "complete"]
        tokens = [dp.reported_tokens(row) for row in complete]
        summary: dict[str, Any] = {
            "protocol_id": vt.PROTOCOL_ID, "phase": vt.PHASE, "student": "mimo", "measurement_card_id": CARD_ID,
            "recovery_of": PARENT_CARD_ID, "parent_ledger_sha256": PARENT_LEDGER_SHA256,
            "model_id": base.MODEL, "manifest_sha256": manifest["manifest_sha256"],
            "condition_sha256": meta["condition_sha256"], "generated_at": base.now(),
            "timeout_seconds": TIMEOUT_SECONDS, "max_timeouts": MAX_TIMEOUTS,
            "retry_candidates": len(capped),
            "retry_candidates_by_replicate": dict(sorted(Counter(k.rsplit(":", 1)[1] for k in capped).items())),
            "sent": len(retried),
            "ledger_rows": len(_ledger_rows(output)),
            "completed": len(complete),
            "completed_by_finish": dict(sorted(Counter(str(row.get("finish_reason")) for row in complete).items())),
            "completed_with_answer": sum(bool(_answer(row)) for row in complete),
            "capped_again": again,
            "never_needed": sorted(k for k in capped if k not in rows and k not in
                                   {f"{vt.DATASET}:{s.item_id}:{r}" for s in states for r in s.needed}),
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
                 condition: dict[str, Any], client, resume: bool, *, parent_rows: dict[str, Any], capped: list[str],
                 score_callback, max_passes: int = MAX_PASSES, execute=None) -> str:
    """Send what MC-110's rule needs among the capped attempts, pass after pass. Returns complete, paused, stalled
    or incomplete. A pass whose rows neither complete nor time out (say every reply is a 429) stalls the run."""
    execute = execute or base.execute
    capped_set = frozenset(capped)
    resume_next = resume

    def states_now() -> tuple[dict[str, Any], list[vt.ItemState]]:
        recovery = _recovery_rows(output, manifest)
        view = recovery_view(parent_rows, recovery, rvt.timeouts_by_attempt(output, TIMEOUT_ERRORS), capped_set)[0]
        return recovery, vt.plan(item_ids, view, None, "mimo")

    for number in range(1, max_passes + 1):
        recovery, states = states_now()
        keys = [f"{vt.DATASET}:{s.item_id}:{r}" for s in states for r in s.needed]
        if len(set(keys)) != len(keys) or any(key not in capped_set for key in keys) \
                or any((recovery.get(key) or {}).get("status") == "complete" for key in keys):
            raise SystemExit("Error: a pass would send an attempt MC-110 did not cap, one twice, or a completed one")
        print(f"pass {number}: final {sum(s.final is not None for s in states)}/{len(states)}; sending {len(keys)} "
              f"{dict(sorted(Counter(k.rsplit(':', 1)[1] for k in keys).items()))}", flush=True)
        if not keys:
            return "complete"
        written = len(_ledger_rows(output))
        execute(output, manifest, rebuilt, [rebuilt[key] for key in keys], condition, client, resume_next,
                score_callback=score_callback, runner_path=Path(__file__), work_stealing=True)
        resume_next = True
        if json.loads((output / "run.json").read_text(encoding="utf-8")).get("status") == "paused":
            return "paused"
        new = _ledger_rows(output)[written:]
        if not any(row.get("status") == "complete" or row.get("error_type") in TIMEOUT_ERRORS for row in new):
            return "stalled"
    return "complete" if all(s.final is not None for s in states_now()[1]) else "incomplete"


# ---------------------------------------------------------------- gates, condition, main

def evaluate_gates(manifest: dict[str, Any], capped: list[str], route_ok: bool, route_detail: str, *,
                   parent: Path = PARENT, card_text: str | None = None, root: Path = ROOT) -> list[Gate]:
    text = pr.MEASUREMENT_CARD.read_text(encoding="utf-8") if card_text is None else card_text
    gates = [Gate("card_registered", re.search(rf"^#{{2,3}} {re.escape(CARD_ID)}\b", text, re.MULTILINE) is not None,
                  f"{CARD_ID} heading in measurement_card.md"),
             Gate("detail_card", (root / CARD_FILE).is_file(), CARD_FILE)]
    ledger = parent / "attempts.jsonl"
    gates.append(Gate("parent_ledger", ledger.is_file() and v1.sha256_file(ledger) == PARENT_LEDGER_SHA256,
                      f"{PARENT_CARD_ID} final ledger sha256 {PARENT_LEDGER_SHA256[:12]}"))
    try:
        summary = json.loads((parent / "summary.json").read_text(encoding="utf-8"))
        run = json.loads((parent / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        summary, run = {}, {}
    final = (isinstance(summary.get("final_items"), int)
             and summary.get("final_items") == summary.get("items") == manifest.get("item_count")
             and summary.get("submissions") == PARENT_SUBMISSIONS
             and run.get("condition_sha256") == PARENT_CONDITION_SHA256
             and summary.get("manifest_sha256") == manifest["manifest_sha256"])
    gates.append(Gate("parent_final", final, f"{PARENT_CARD_ID} complete, same manifest and submissions"))
    listed = (summary.get("timeout_cap") or {}).get("capped_run_keys")
    gates.append(Gate("retry_candidates", listed == capped and len(capped) == PARENT_CAPPED,
                      f"{len(capped)} capped attempts, as {PARENT_CARD_ID}'s summary lists ({PARENT_CAPPED})"))
    gates.append(Gate("route_identity", route_ok, route_detail))
    return gates


def build_condition(config: dict[str, Any], manifest: dict[str, Any], registration: dict[str, Any],
                    route: dict[str, Any], capped: list[str]) -> dict[str, Any]:
    condition = rvt.build_condition("mimo", config, manifest, registration, route)
    condition.update({
        "measurement_card_id": CARD_ID, "card_sha256": v1.sha256_file(ROOT / CARD_FILE),
        "recovery": {"parent_card_id": PARENT_CARD_ID, "parent_ledger_sha256": PARENT_LEDGER_SHA256,
                     "parent_condition_sha256": PARENT_CONDITION_SHA256,
                     "retry_candidates": len(capped),
                     "retry_candidates_sha256": v1.sha256_bytes("\n".join(capped).encode("utf-8")),
                     "timeout_seconds": TIMEOUT_SECONDS, "max_timeouts": MAX_TIMEOUTS,
                     "timeout_errors": list(TIMEOUT_ERRORS), "max_in_flight": MAX_IN_FLIGHT,
                     "budget_tokens": BUDGET_TOKENS, "max_passes": MAX_PASSES,
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
    parent_rows, capped = parent_state(manifest, registration)
    gates = evaluate_gates(manifest, capped, route_ok, route_detail)
    recovery = _recovery_rows(OUTPUT, manifest)
    view = recovery_view(parent_rows, recovery, rvt.timeouts_by_attempt(OUTPUT, TIMEOUT_ERRORS), frozenset(capped))[0]
    needed = [f"{vt.DATASET}:{s.item_id}:{r}" for s in vt.plan(item_ids, view, None, "mimo") for r in s.needed]
    print(f"card={CARD_ID} recovery_of={PARENT_CARD_ID} retry_candidates={len(capped)} "
          f"{dict(sorted(Counter(k.rsplit(':', 1)[1] for k in capped).items()))} "
          f"items={len({k.split(':')[1] for k in capped})}")
    print(f"timeout={TIMEOUT_SECONDS}s max_timeouts={MAX_TIMEOUTS} max_in_flight={MAX_IN_FLIGHT} "
          f"budget_tokens={BUDGET_TOKENS:,} max_passes={MAX_PASSES} output={OUTPUT}")
    print(f"next pass would send {len(needed)} {dict(sorted(Counter(k.rsplit(':', 1)[1] for k in needed).items()))}"
          f"; recovery ledger rows={len(_ledger_rows(OUTPUT))}")
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
    condition = pr.reconcile_resume(OUTPUT, build_condition(config, manifest, registration, route, capped),
                                    args.resume)
    guard = pr.BudgetGuard(BUDGET_TOKENS, pr.existing_usage(OUTPUT))
    transient = rvt.transient_400_amendment(registration)
    bad_request = rvt.BadRequestRule(transient, rvt.attempts_with_400(OUTPUT) if transient else frozenset())
    base.request = rvt.make_mimo_request({**student, "max_in_flight": MAX_IN_FLIGHT}, CARD_ID, guard,
                                         pr.OutageGuard(student["stop_after_timeouts"]),
                                         rvt.ModelPin(student["model_identity"]), bad_request)
    with (PARENT / "loop.jsonl").open(encoding="utf-8") as handle:
        parent_loop = {row["item_id"]: row for row in map(json.loads, handle)}
    print(f"budget guard {BUDGET_TOKENS:,} reported tokens; already used {guard.used:,}", flush=True)
    record_launch(OUTPUT, resume=args.resume, note=args.note)
    with OpenAI(base_url=endpoint, api_key=key, timeout=TIMEOUT_SECONDS, max_retries=student["sdk_retries"]) as client:
        status = run_recovery(OUTPUT, manifest, rebuilt, item_ids, condition, client, args.resume,
                              parent_rows=parent_rows, capped=capped,
                              score_callback=writer(item_ids, parent_rows, capped, parent_loop))
    print(f"recovery_status={status} output={OUTPUT}", flush=True)
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
