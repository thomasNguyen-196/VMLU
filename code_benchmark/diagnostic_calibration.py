"""Router v3: a frozen calibration procedure (openspec change diagnostic-router-v3, spec
`diagnostic-calibrated-router`).

Router v3 is not a fixed rule. For each dataset it scores three policies on a small labelled calibration sample
and keeps the best; the choices are written as a rule in the closed grammar of `diagnostic_router`, so the
dataset's other items are routed by the same code as router v1 and v2.

* candidates: always-B; the v2 cascade (B answers twice and the item goes to S when the two parsed answers differ
  under normalized-answer-v1, otherwise the first B answer stands); always-S;
* on an item, a candidate returns what deployment would return in one rotation: the answering B draw, the second
  B draw for the probe, the S draw. Calibrating a dataset therefore costs B twice and S once per item;
* score: accuracy for multiple choice, mean token-F1 for reading (exact match mostly rewards answer formatting:
  34 of the 50 ViBidLQA answers that lost on exact match in MC-94 were right in meaning);
* the highest score wins; an exact tie goes to fewer mean reported tokens, then to the order always-B, v2 cascade,
  always-S (cheapest first).

Usage (repo root): .venv/bin/python -m code_benchmark.diagnostic_calibration [--procedure <json>]
prints the procedure's SHA-256.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Iterable

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_router as router
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_router as router
    import vi_multimodel as v1

DATA_DIR = dp.ROOT / "data" / "diagnostic_router_v3"
PROCEDURE_PATH = DATA_DIR / "procedure_v3.json"
PROCEDURE_KEYS = ("procedure_id", "description", "candidates", "calibration_items", "score", "tie", "probe")
CANDIDATES = ("always_B", "v2_cascade", "always_S")
SCORES = {"multiple_choice": "accuracy", "reading": "mean_token_f1"}
TIE = ["fewer_mean_reported_tokens", "candidate_order"]
S_TARGETS = sorted(router.ADDRESSABLE["S"])


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


# ---------------------------------------------------------------- the frozen procedure

def validate_procedure(procedure: Any) -> dict[str, Any]:
    if not isinstance(procedure, dict) or set(procedure) != set(PROCEDURE_KEYS):
        raise _fail(f"the procedure must have exactly the keys {list(PROCEDURE_KEYS)}")
    if not isinstance(procedure["procedure_id"], str) or not procedure["procedure_id"].strip():
        raise _fail("the procedure lacks a procedure_id")
    if not isinstance(procedure["description"], str):
        raise _fail("the procedure description must be text")
    if procedure["candidates"] != list(CANDIDATES):
        raise _fail(f"the candidates must be exactly {list(CANDIDATES)}, in this order")
    size = procedure["calibration_items"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise _fail("calibration_items must be a positive integer")
    if procedure["score"] != SCORES:
        raise _fail(f"the score must be {SCORES} (exact match is not a reading score here)")
    if procedure["tie"] != TIE:
        raise _fail(f"the tie rule must be {TIE}")
    router._check_probe(procedure["probe"])  # noqa: SLF001  # the probe of router v2
    if procedure["probe"]["arm"] != "B":
        raise _fail("the v2 cascade probes arm B")
    return procedure


def load_procedure(path: Path = PROCEDURE_PATH) -> tuple[dict[str, Any], str]:
    """The validated procedure and the SHA-256 of its bytes (the value the registration records)."""
    try:
        raw = path.read_bytes()
        procedure = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the calibration procedure {path}: {exc}") from exc
    return validate_procedure(procedure), v1.sha256_bytes(raw)


# ---------------------------------------------------------------- one item, one rotation

def score_of(row: dict[str, Any], task: str) -> float:
    if task == "reading":
        return float(row.get("token_f1") or 0.0)
    return 1.0 if bool(row.get("correct")) else 0.0


def _tokens(*rows: dict[str, Any]) -> int | None:
    values = [dp.reported_tokens(row) for row in rows]
    return None if any(value is None for value in values) else sum(values)  # type: ignore[arg-type]


def outcome(candidate: str, b: dict[str, Any], b2: dict[str, Any], s: dict[str, Any], task: str
            ) -> tuple[dict[str, Any], int | None]:
    """(the attempt the candidate returns, its reported tokens with the probe) for one item and rotation."""
    if candidate == "always_B":
        return b, _tokens(b)
    if candidate == "always_S":
        return s, _tokens(s)
    if candidate != "v2_cascade":
        raise _fail(f"unknown candidate {candidate!r}")
    agree = router.answers_agree(str(b.get("prediction") or ""), str(b2.get("prediction") or ""), task)
    return (b, _tokens(b, b2)) if agree else (s, _tokens(b, b2, s))


# ---------------------------------------------------------------- the choice per dataset

def choose(procedure: dict[str, Any], cells: Iterable[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
           task: str) -> dict[str, Any]:
    """Score the candidates on a dataset's calibration cells (b, b2, s per item, one rotation) and choose."""
    cells = list(cells)
    if len(cells) != procedure["calibration_items"]:
        raise _fail(f"a calibration sample has {procedure['calibration_items']} items, not {len(cells)}")
    if task not in SCORES:
        raise _fail(f"unknown task {task!r}")
    scores: dict[str, float] = {}
    tokens: dict[str, float | None] = {}
    for candidate in CANDIDATES:
        returned = [outcome(candidate, b, b2, s, task) for b, b2, s in cells]
        scores[candidate] = statistics.fmean(score_of(row, task) for row, _ in returned)
        known = [spent for _, spent in returned if spent is not None]
        tokens[candidate] = statistics.fmean(known) if len(known) == len(returned) else None

    def order(candidate: str) -> tuple[float, float, int]:
        spent = tokens[candidate]
        return (-scores[candidate], float("inf") if spent is None else spent, CANDIDATES.index(candidate))

    return {"items": len(cells), "score": SCORES[task], "scores": scores, "mean_tokens": tokens,
            "choice": min(CANDIDATES, key=order)}


# ---------------------------------------------------------------- the emitted rule

def emit_rule(procedure: dict[str, Any], choices: dict[str, str], datasets: Iterable[str], rule_id: str
              ) -> dict[str, Any]:
    """The choices as a rule of the closed grammar: always-B or always-S is one condition on the dataset; the
    v2 cascade is a probe condition (disagree -> S) followed by the dataset alone (-> B). Default B."""
    conditions: list[dict[str, Any]] = []
    for dataset in sorted(choices):
        choice = choices[dataset]
        if choice == "always_S":
            conditions.append({"arm": "S", "targets": S_TARGETS, "when": {"dataset": [dataset]},
                               "note": "calibration chose always-S"})
        elif choice == "always_B":
            conditions.append({"arm": "B", "targets": [], "when": {"dataset": [dataset]},
                               "note": "calibration chose always-B"})
        elif choice == "v2_cascade":
            conditions.append({"arm": "S", "targets": S_TARGETS, "when": {"dataset": [dataset], "probe": "disagree"},
                               "note": "calibration chose the v2 cascade: the two B answers differ"})
            conditions.append({"arm": "B", "targets": [], "when": {"dataset": [dataset]},
                               "note": "calibration chose the v2 cascade: the two B answers agree"})
        else:
            raise _fail(f"{dataset}: unknown choice {choice!r}")
    rule: dict[str, Any] = {"router_id": rule_id,
                            "description": f"emitted by {procedure['procedure_id']} from its calibration samples"}
    if "v2_cascade" in choices.values():
        rule["probe"] = dict(procedure["probe"])
    rule["conditions"] = conditions
    rule["default"] = {"arm": "B", "targets": []}
    return router.validate_rule(rule, datasets)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print the SHA-256 of the router v3 calibration procedure.")
    ap.add_argument("--procedure", type=Path, default=PROCEDURE_PATH, help=f"default: {PROCEDURE_PATH}")
    args = ap.parse_args(argv)
    procedure, digest = load_procedure(args.procedure)
    print(f"{procedure['procedure_id']}  sha256 {digest}  candidates {procedure['candidates']}  "
          f"calibration items {procedure['calibration_items']}  score {procedure['score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
