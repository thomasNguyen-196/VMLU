"""Router signals from a System One model (openspec change diagnostic-router-signals; card MC-99).

Jev 1.13 answers typed questions about each of the 967 wide reading items:

* J1, pre-hoc: one request per item. The state is the passage and question of the frozen reading prompt; the
  questions are the six MC-98 groups as a Choice and seven yes/no (Noul) statements.
* J2, post-hoc: two requests per item. The state adds the answer B actually gave on its wide draw 1 (MC-90) or
  draw 2 (MC-91), the scored prediction; the questions are four yes/no statements about that answer.

No state carries a gold answer, a score or an audit field. Offline: this module builds and freezes the manifest; the
runner is run_router_signals.py.

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_router_signals            # rebuild and compare with the frozen manifest
  .venv/bin/python -m code_benchmark.diagnostic_router_signals --write    # freeze it (once)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_llm_router as llm_router
    from code_benchmark import diagnostic_menu as menu
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_llm_router as llm_router
    import diagnostic_menu as menu
    import diagnostic_prospective as dp
    import vi_multimodel as v1

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "diagnostic_router_signals"
CONFIG_PATH = DATA_DIR / "jev_signals_v1.json"
MANIFEST_PATH = DATA_DIR / "jev_signals_manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-router-signals"
PHASE = "signals"
CONFIG_KEYS = ("signals_id", "protocol_id", "protocol_version", "change", "purpose", "items", "answer_sources",
               "requests", "route", "analysis")
ROUTE_KEYS = ("endpoint_host", "path", "model_id", "credential", "session_header", "user_agent", "timeout_seconds",
              "max_in_flight", "stop_after_network_failures", "retry_statuses", "max_retries", "retry_wait_seconds",
              "require_free_billing")
DRAWS = ("B1", "B2")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _read_json_bytes(path: Path, label: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        return json.loads(raw), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the {label} {path}: {exc}") from exc


def _check_questions(questions: Any, where: str) -> None:
    if not isinstance(questions, dict) or not questions:
        raise _fail(f"{where} needs a non-empty question map")
    for qid, question in questions.items():
        kind = question.get("type") if isinstance(question, dict) else None
        if kind not in {"choice", "noul"} or not str(question.get("instructions", "")).strip():
            raise _fail(f"{where}.{qid} must be a choice or noul question with instructions")
        if kind == "choice" and (not isinstance(question.get("criteria"), dict) or len(question["criteria"]) < 2):
            raise _fail(f"{where}.{qid} needs at least two criteria")
        if kind == "noul" and set(question) != {"type", "instructions"}:
            raise _fail(f"{where}.{qid}: a noul question takes only type and instructions")


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or set(config) != set(CONFIG_KEYS):
        raise _fail(f"the signals configuration must have exactly the keys {list(CONFIG_KEYS)}")
    if config["protocol_id"] != PROTOCOL_ID or config["protocol_version"] != 1:
        raise _fail("unsupported signals configuration id/version")
    if config["items"].get("dataset_counts") != menu.DATASET_COUNTS:
        raise _fail(f"the signals cover the menu reading items {menu.DATASET_COUNTS}")
    if set(config["answer_sources"]) != set(DRAWS):
        raise _fail(f"the answer sources are {list(DRAWS)}")
    if set(config["route"]) != set(ROUTE_KEYS):
        raise _fail(f"the route must have exactly the keys {list(ROUTE_KEYS)}")
    pre, post = config["requests"].get("pre"), config["requests"].get("post")
    if not pre or not post or set(config["requests"]) != {"pre", "post"}:
        raise _fail("the requests are exactly pre and post")
    _check_questions(pre.get("questions"), "requests.pre")
    _check_questions(post.get("questions"), "requests.post")
    if pre["state_fields"] != ["passage", "question"] or post["state_fields"] != ["passage", "question", "proposed_answer"]:
        raise _fail("unexpected state fields")
    if set(post["replicate_ids"]) != set(DRAWS):
        raise _fail(f"post replicate ids are keyed by {list(DRAWS)}")
    groups = pre["questions"].get("group", {})
    mc98, _ = llm_router.load_config()
    if groups.get("type") != "choice" or list(groups.get("criteria", {})) != llm_router.group_ids(mc98):
        raise _fail("the group question must offer exactly the six MC-98 groups, in their order")
    return config


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    config, digest = _read_json_bytes(path, "signals configuration")
    return validate_config(config), digest


def load_answers(config: dict[str, Any]) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """({draw: {dataset:item -> scored B prediction}}, {draw: SHA-256 of its scores file})."""
    answers: dict[str, dict[str, str]] = {}
    hashes: dict[str, str] = {}
    for draw, source in config["answer_sources"].items():
        path = ROOT / source["path"]
        if not path.is_file():
            raise _fail(f"answer source {draw} is missing: {path}")
        hashes[draw] = v1.sha256_file(path)
        found: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("replicate_id") != source["replicate_id"] or row.get("dataset_id") not in menu.DATASET_COUNTS:
                continue
            key = dp.item_key(row["dataset_id"], row["item_id"])
            if key in found:
                raise _fail(f"answer source {draw} holds {key} twice")
            found[key] = str(row.get(source["field"]) or "")
        answers[draw] = found
    return answers, hashes


def state_for(item: v1.EvalItem, answer: str | None = None) -> dict[str, str]:
    """The state Jev sees: passage and question, plus the proposed answer for a post-hoc request. Never the gold."""
    parts = dp.parse_frozen_prompt(item)
    if parts.kind != "reading":
        raise _fail(f"signals read reading items; {item.run_key} is {item.task}")
    state = {"passage": parts.body.strip(), "question": parts.question}
    if answer is not None:
        state["proposed_answer"] = answer
    return state


def request_body(state: dict[str, str], questions: dict[str, Any], model: str) -> dict[str, Any]:
    return {"model": model, "state": state, "questions": questions}


def body_sha256(body: dict[str, Any]) -> str:
    """SHA-256 of the canonical request body without the model field."""
    return v1.sha256_bytes(v1.canonical_json({key: value for key, value in body.items() if key != "model"}))


def build_requests(config: dict[str, Any], items: list[v1.EvalItem] | None = None,
                   answers: dict[str, dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """Every request in manifest order: per item the pre-hoc request, then the post-hoc ones for B1 and B2."""
    items = items if items is not None else menu.design_items()
    answers = answers if answers is not None else load_answers(config)[0]
    model = config["route"]["model_id"]
    pre, post = config["requests"]["pre"], config["requests"]["post"]
    rows: list[dict[str, Any]] = []
    for item in items:
        key = dp.item_key(item.dataset_id, item.item_id)
        plans: list[tuple[str, str, str | None, str | None]] = [("pre", pre["replicate_id"], None, None)]
        for draw in DRAWS:
            if key not in answers[draw]:
                raise _fail(f"answer source {draw} has no prediction for {key}")
            plans.append(("post", post["replicate_ids"][draw], draw, answers[draw][key]))
        for kind, replicate, draw, answer in plans:
            state = state_for(item, answer)
            body = request_body(state, pre["questions"] if kind == "pre" else post["questions"], model)
            rows.append({"dataset_id": item.dataset_id, "item_id": item.item_id, "replicate_id": replicate,
                         "kind": kind, "answer_draw": draw, "passage_id": item.passage_id,
                         "state_sha256": v1.sha256_bytes(v1.canonical_json(state)),
                         "request_sha256": body_sha256(body), "body": body})
    return rows


def build_manifest(config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config, digest = load_config(config_path)
    answers, answer_hashes = load_answers(config)
    requests = build_requests(config, answers=answers)
    keys = [dp.run_key(row) for row in requests]
    if len(keys) != len(set(keys)):
        raise _fail("duplicate signal run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "signals_id": config["signals_id"],
        "config_sha256": digest, "menu_manifest_self_sha256": menu.load_frozen_manifest()["manifest_sha256"],
        "answer_source_sha256": answer_hashes, "n": len(requests),
        "kind_counts": dict(sorted(Counter(row["kind"] for row in requests).items())),
        "dataset_counts": dict(sorted(Counter(row["dataset_id"] for row in requests if row["kind"] == "pre").items())),
        "items": [{key: row[key] for key in ("dataset_id", "item_id", "replicate_id", "kind", "answer_draw",
                                             "passage_id", "state_sha256", "request_sha256")} for row in requests],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, requests


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest, _ = _read_json_bytes(path, "frozen signals manifest")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the router-signals manifest (offline).")
    ap.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    manifest, _ = build_manifest()
    print(f"signals manifest {manifest['manifest_sha256']}: {manifest['n']} requests {manifest['kind_counts']}, "
          f"datasets {manifest['dataset_counts']}")
    if args.write:
        if MANIFEST_PATH.exists():
            raise _fail(f"{MANIFEST_PATH} is frozen; delete it deliberately to rebuild")
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"frozen -> {MANIFEST_PATH}")
    elif MANIFEST_PATH.exists():
        same = load_frozen_manifest() == manifest
        print(f"frozen manifest {'matches' if same else 'DIFFERS'}")
        return 0 if same else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
