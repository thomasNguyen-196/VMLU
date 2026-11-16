"""MC-115 inputs (openspec change diagnostic-legal-agent-draws), offline: the protocol and the manifest of draws 3 and 4
of DSHF, OMPF and each part's no-tool baseline on MC-114's 646 analysis items, each in its earlier condition.

The manifest is copied, not rebuilt from scratch: MC-112's, MC-113's and MC-114's manifests are rebuilt with their own
modules and must equal their frozen files; each new attempt is the frozen draw-1 item of its arm with only the
replicate id changed. B on the 134 Legal MC items uses the frozen MC prompt, which MC-112's build checks against the
prompt MC-111's B sent.

From the repo root:
  .venv/bin/python -m code_benchmark.diagnostic_legal_agent_draws manifest            # build and print counts
  .venv/bin/python -m code_benchmark.diagnostic_legal_agent_draws manifest --write    # freeze manifest_v1.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

try:
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_agent_v2 as l2
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import run_legal_agent_omp as rlo
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]
    import diagnostic_legal_oracle as lo  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import run_legal_agent_omp as rlo  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = la.ROOT
DATA_DIR = ROOT / "data" / "diagnostic_legal_agent_draws"
WORK_ROOT = ROOT / "all_res" / "diagnostic_legal_agent_draws"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
MANIFEST_PATH = DATA_DIR / "manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-legal-agent-draws"
PHASE = "legal-agent-draws"
LEGAL_MC = lo.DATASET
NEW_DRAWS = (3, 4)
PART_ARMS = {"M": ("DSHF", "OMPF", "B"), "S": ("DSHF", "OMPF", "C")}
AGENT_ARMS = ("DSHF", "OMPF")
PART_SIZES = {"M": 246, "S": 400}
SOURCES = ("mc112", "mc113", "mc114")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported legal-agent-draws protocol id or version")
    parts = protocol.get("parts") or {}
    if {name: tuple(spec.get("arms") or ()) for name, spec in parts.items()} != PART_ARMS:
        raise _fail(f"the legal-agent-draws protocol must run parts {PART_ARMS}")
    if tuple(protocol.get("draws") or ()) != NEW_DRAWS:
        raise _fail(f"the legal-agent-draws protocol must run draws {NEW_DRAWS}")
    if set(protocol.get("sources") or {}) != set(SOURCES):
        raise _fail(f"the protocol must name the source manifests {SOURCES}")
    return protocol


def _sha_checked(path: Path, sha256: str, label: str) -> str:
    if not path.is_file() or v1.sha256_file(path) != sha256:
        raise _fail(f"{label} {path} is missing or differs from its registered SHA-256")
    return sha256


# ---------------------------------------------------------------- folders

def corpus_of(protocol: dict[str, Any], dataset_id: str) -> str:
    """The corpus name ("v1" or "v2") an item's agent attempts run on: the folder its draws 1-2 used."""
    corpora = protocol["corpora"]
    named = [name for name, spec in corpora.items() if dataset_id in (spec.get("datasets") or [])]
    if len(named) > 1:
        raise _fail(f"{dataset_id} is listed under more than one corpus")
    if named:
        return named[0]
    fallback = [name for name, spec in corpora.items() if spec.get("datasets") == "other"]
    if len(fallback) != 1:
        raise _fail("exactly one corpus must take the other datasets")
    return fallback[0]


def docs_dir(protocol: dict[str, Any], name: str, root: Path = ROOT) -> Path:
    return root / protocol["corpora"][name]["folder"] / "docs"


# ---------------------------------------------------------------- the manifest

Builder = Callable[[], tuple[dict[str, Any], dict[str, v1.EvalItem]]]


def _builders() -> dict[str, tuple[Builder, Callable[[], dict[str, Any]], Path]]:
    return {"mc112": (la.build_manifest, la.load_frozen_manifest, la.MANIFEST_PATH),
            "mc113": (rlo.build_manifest, rlo.load_frozen_manifest, rlo.MANIFEST_PATH),
            "mc114": (l2.build_manifest, l2.load_frozen_manifest, l2.MANIFEST_PATH)}


def source_manifests(protocol: dict[str, Any], builders: dict[str, Any] | None = None
                     ) -> dict[str, dict[str, v1.EvalItem]]:
    """Each earlier card's rebuilt run-key map, after its manifest rebuilds to its frozen file and that file hashes
    as this protocol registers."""
    out = {}
    for name, (build, frozen, path) in (builders or _builders()).items():
        _sha_checked(path, protocol["sources"][name]["manifest_file_sha256"], f"{name} manifest")
        manifest, rebuilt = build()
        if manifest != frozen():
            raise _fail(f"{name}'s manifest no longer rebuilds to its frozen file")
        out[name] = rebuilt
    return out


def _draw_one(rebuilt: dict[str, v1.EvalItem], dataset_id: str, item_id: str, arm: str, label: str) -> v1.EvalItem:
    key = f"{dataset_id}:{item_id}:{arm}-r1"
    if key not in rebuilt:
        raise _fail(f"{label} has no {arm}-r1 attempt for {dataset_id}:{item_id}")
    second = rebuilt.get(f"{dataset_id}:{item_id}:{arm}-r2")
    if second is None or second.prompt != rebuilt[key].prompt:
        raise _fail(f"{label}'s two draws of {arm} on {dataset_id}:{item_id} do not send the same task")
    return rebuilt[key]


def base_items(rebuilt: dict[str, dict[str, v1.EvalItem]], legal_frozen: dict[str, v1.EvalItem] | None = None
               ) -> dict[str, list[tuple[str, dict[str, v1.EvalItem]]]]:
    """{part: [(item key, {arm: the draw-1 item to copy})]} in manifest order: Legal MC, Part M VMLU, Part S."""
    mc112, mc113, mc114 = rebuilt["mc112"], rebuilt["mc113"], rebuilt["mc114"]
    legal_frozen = lo.legal_items() if legal_frozen is None else legal_frozen
    legal_ids = [item.item_id for item in mc112.values() if item.replicate_id == "DSHF-r1"]  # MC-112's pool order
    parts: dict[str, list[tuple[str, dict[str, v1.EvalItem]]]] = {"M": [], "S": []}
    for item_id in legal_ids:
        dshf = _draw_one(mc112, LEGAL_MC, item_id, "DSHF", "MC-112")
        omp = _draw_one(mc113, LEGAL_MC, item_id, "OMPF", "MC-113")
        if omp.prompt != dshf.prompt:
            raise _fail(f"MC-113's OMPF task differs from MC-112's DSHF task on {item_id}")
        if item_id not in legal_frozen:
            raise _fail(f"no frozen MC prompt for Legal MC item {item_id}")
        parts["M"].append((f"{LEGAL_MC}:{item_id}", {"DSHF": dshf, "OMPF": omp, "B": legal_frozen[item_id]}))
    # MC-114's manifest order is item-major, part M first
    for key in dict.fromkeys(f"{item.dataset_id}:{item.item_id}" for item in mc114.values()):
        dataset_id, item_id = key.split(":", 1)
        part = "M" if mc114[f"{key}:DSHF-r1"].task == "multiple_choice" else "S"
        arms = {arm: _draw_one(mc114, dataset_id, item_id, arm, "MC-114") for arm in PART_ARMS[part]}
        parts[part].append((key, arms))
    sizes = {part: len(rows) for part, rows in parts.items()}
    if sizes != PART_SIZES:
        raise _fail(f"part sizes {sizes}, not {PART_SIZES}")
    return parts


def expand(parts: dict[str, list[tuple[str, dict[str, v1.EvalItem]]]]) -> list[v1.EvalItem]:
    """Item-major: per item, draw 3 then draw 4, the part's arms in order. Only the replicate id changes."""
    out = []
    for part in ("M", "S"):
        for _, arms in parts[part]:
            for draw in NEW_DRAWS:
                for arm in PART_ARMS[part]:
                    out.append(dataclasses.replace(arms[arm], replicate_id=f"{arm}-r{draw}"))
    return out


def input_hashes(protocol: dict[str, Any], root: Path = ROOT) -> dict[str, str]:
    hashes = {"legal_agent_draws_protocol_sha256": v1.sha256_file(PROTOCOL_PATH)}
    for name, spec in protocol["sources"].items():
        for key in ("protocol", "registration"):
            hashes[f"{name}_{key}_sha256"] = _sha_checked(root / spec[key], spec[f"{key}_sha256"], f"{name} {key}")
        hashes[f"{name}_manifest_file_sha256"] = spec["manifest_file_sha256"]
    for name, spec in protocol["corpora"].items():
        hashes[f"corpus_{name}_folder_sha256"] = spec["folder_sha256"]
    for name, spec in protocol["reference"].items():
        hashes[f"{name}_sha256"] = _sha_checked(root / spec["path"], spec["sha256"], name)
    return hashes


def build_manifest(protocol: dict[str, Any] | None = None, rebuilt: dict[str, dict[str, v1.EvalItem]] | None = None,
                   legal_frozen: dict[str, v1.EvalItem] | None = None, root: Path = ROOT
                   ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed."""
    protocol = protocol or load_protocol()
    rebuilt = source_manifests(protocol) if rebuilt is None else rebuilt
    parts = base_items(rebuilt, legal_frozen)
    items = expand(parts)
    out = {item.run_key: item for item in items}
    if len(out) != len(items):
        raise _fail("duplicate legal-agent-draws run keys")
    keys = [key for part in ("M", "S") for key, _ in parts[part]]
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, **input_hashes(protocol, root),
        "parts": {part: [key for key, _ in rows] for part, rows in parts.items()},
        "corpus_of": {key: corpus_of(protocol, key.split(":", 1)[0]) for key in keys},
        "n": len(items), "item_count": len(keys),
        "dataset_counts": dict(sorted(Counter(key.split(":", 1)[0] for key in keys).items())),
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, out


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MC-115 inputs, offline: the manifest of draws 3 and 4.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("manifest", help="build the manifest and print its counts")
    build.add_argument("--write", action="store_true", help="freeze it to manifest_v1.json")
    args = parser.parse_args(argv)
    manifest, _ = build_manifest()
    print(f"items={manifest['item_count']} attempts={manifest['n']} arms={manifest['arm_counts']} "
          f"datasets={manifest['dataset_counts']} manifest_sha256={manifest['manifest_sha256']}")
    if args.write:
        if MANIFEST_PATH.is_file() and load_frozen_manifest() != manifest:
            raise _fail(f"{MANIFEST_PATH} exists and differs; a frozen manifest is never overwritten")
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {MANIFEST_PATH} sha256 {v1.sha256_file(MANIFEST_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
