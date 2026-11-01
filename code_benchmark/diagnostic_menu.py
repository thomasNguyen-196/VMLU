"""Arm Q and the menu design set of the LLM router (openspec change diagnostic-llm-router, spec `diagnostic-quote-arm`;
card MC-97).

* Arm Q ("trích rồi đáp"): the model first copies the part of the passage that answers the question, on a line
  `Trích dẫn: …`, then gives the shortest phrase or number in it that answers what is asked, on a last line
  `Trả lời: …`. The prompt is the protocol's Q head followed by the passage and question of the item's frozen main-v1
  reading prompt, in the layout of the S reading prompt. It is scored from the text after the last final-answer
  label, as S is on reading.
* Items: every wide-phase item of ViBidLQA test, Vi-DROP and Vi-SQuAD (the B-r1 rows of wide_v1.json, in manifest
  order), 967 items. Each item's frozen reading prompt must hash to its MC-90 B prompt.
* Two draws of Q per item, 1,934 attempts. B and S already have two draws on the same items (MC-90 to MC-92).

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_menu            # build the manifest and compare it with the frozen one
  .venv/bin/python -m code_benchmark.diagnostic_menu --write    # freeze data/diagnostic_llm_router/menu_q_v1.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import vi_multimodel as v1

DATA_DIR = dp.ROOT / "data" / "diagnostic_llm_router"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
MANIFEST_PATH = DATA_DIR / "menu_q_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
SOURCE_MANIFEST = dp.DATA_DIR / "wide_v1.json"
PROTOCOL_ID = "vmlu-diagnostic-llm-router"
PHASE = "menu"
ARM = "Q"
DATASET_COUNTS = {"vi-multimodel-v1-bidlqa-test": 591, "vi-multimodel-v1-vi-drop-200": 188,
                  "vi-multimodel-v1-vi-squad-200": 188}
DATASETS = tuple(DATASET_COUNTS)
INHERITED = ("model", "transport", "scoring", "budget")
PARENT = {"campaign_protocol": "data/diagnostic_prospective_v1/protocol.json",
          "source_manifest": "data/diagnostic_prospective_v1/wide_v1.json"}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _read_json_bytes(path: Path, label: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        return json.loads(raw), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the {label} {path}: {exc}") from exc


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    """The menu protocol. Its model, transport, scoring and budget come from the campaign protocol, never a copy."""
    protocol, _ = _read_json_bytes(path, "LLM-router protocol")
    if not isinstance(protocol, dict) or protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported LLM-router protocol id/version")
    parent = protocol.get("parent") or {}
    if any(parent.get(key) != value for key, value in PARENT.items()) or parent.get("inherited_blocks") != list(INHERITED):
        raise _fail(f"the LLM-router protocol must name the parents {PARENT} and inherit {list(INHERITED)}")
    copied = [block for block in INHERITED if block in protocol]
    if copied:
        raise _fail(f"the LLM-router protocol must not copy the inherited blocks {copied}")
    if protocol.get("datasets") != list(DATASETS):
        raise _fail(f"the menu set covers exactly the datasets {list(DATASETS)}")
    if protocol.get("phases") != {PHASE: {"arms": [ARM], "replicates": 2}}:
        raise _fail(f"the menu phase runs arm {ARM} with 2 replicates")
    q = (protocol.get("prompts") or {}).get(ARM) or {}
    if set(q) != {"head", "question", "tail"} or not all(isinstance(q[key], str) and q[key] for key in q):
        raise _fail("the Q prompt needs a head, a question label and a tail")
    if q["question"] != dp.RD_QUESTION or q["tail"] != "\n" or not q["head"].endswith("\n\n"):
        raise _fail("the Q prompt keeps the layout of the S reading prompt (question label, final newline)")
    return protocol


def q_prompt(item: v1.EvalItem, protocol: dict[str, Any]) -> str:
    """Head + the passage of the frozen reading prompt + question label + question + tail. No gold."""
    parts = dp.parse_frozen_prompt(item)
    if parts.kind != "reading":
        raise _fail(f"arm Q is a reading arm; {item.run_key} is {item.task}")
    q = protocol["prompts"][ARM]
    return q["head"] + parts.body + q["question"] + parts.question + q["tail"]


def load_source_manifest(path: Path = SOURCE_MANIFEST) -> dict[str, Any]:
    source, _ = _read_json_bytes(path, "wide manifest")
    unhashed = {key: value for key, value in source.items() if key != "manifest_sha256"}
    if source.get("manifest_sha256") != v1.sha256_bytes(v1.canonical_json(unhashed)):
        raise _fail("the wide manifest's self-hash does not match its content")
    return source


def design_items(main_items: dict[str, v1.EvalItem] | None = None,
                 source: dict[str, Any] | None = None) -> list[v1.EvalItem]:
    """The wide-phase reading items, one per question in wide-manifest order. Each is the frozen main-v1 item, and its
    prompt must hash to the item's MC-90 B prompt."""
    source = source or load_source_manifest()
    main = main_items if main_items is not None else v1.rebuild_items("main")
    items: list[v1.EvalItem] = []
    for row in source["items"]:
        if row["replicate_id"] != "B-r1" or row["dataset_id"] not in DATASET_COUNTS:
            continue
        item = main.get(f"{row['dataset_id']}:{row['item_id']}:{dp.MAIN_REPLICATE}")
        if item is None:
            raise _fail(f"wide item {row['dataset_id']}:{row['item_id']} is not a frozen main-v1 item")
        if v1.sha256_bytes(item.prompt.encode("utf-8")) != row["prompt_sha256"]:
            raise _fail(f"the frozen prompt of {item.run_key} differs from its MC-90 B prompt")
        items.append(item)
    counts = dict(sorted(Counter(item.dataset_id for item in items).items()))
    if counts != DATASET_COUNTS:
        raise _fail(f"the wide reading items are {counts}, not {DATASET_COUNTS}")
    return items


def build_manifest(protocol: dict[str, Any] | None = None, protocol_path: Path = PROTOCOL_PATH
                   ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed like the campaign manifests. Item-major: item, then draw."""
    protocol = protocol or load_protocol(protocol_path)
    source = load_source_manifest()
    base = design_items(source=source)
    replicates = protocol["phases"][PHASE]["replicates"]
    items = [dataclasses.replace(item, replicate_id=f"{ARM}-r{draw}", prompt=q_prompt(item, protocol))
             for item in base for draw in range(1, replicates + 1)]
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate menu run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE,
        "menu_protocol_sha256": v1.sha256_file(protocol_path),
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "source_manifest_sha256": v1.sha256_file(SOURCE_MANIFEST),
        "source_manifest_self_sha256": source["manifest_sha256"],
        "n": len(items), "item_count": len(base),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in base).items())),
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest, _ = _read_json_bytes(path, "frozen menu manifest")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the menu (arm Q) manifest (offline).")
    ap.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    manifest, _ = build_manifest()
    print(f"menu manifest {manifest['manifest_sha256']}: {manifest['item_count']} items, {manifest['n']} attempts, "
          f"datasets {manifest['dataset_counts']}, arms {manifest['arm_counts']}")
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
