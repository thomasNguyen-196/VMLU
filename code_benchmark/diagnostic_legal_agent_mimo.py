"""MC-116 inputs (openspec change diagnostic-legal-agent-mimo), offline: the protocol, MiMo's two harness
specifications and the manifest of MC-115's agent arms and baselines on the same 646 items, two draws, with
MiMo-V2.6-Flash in place of Qwen3.5-9B.

The tasks are copied, not rebuilt: MC-112's, MC-113's and MC-114's manifests are rebuilt with their own modules and
must equal their frozen files (MC-115's own path, `diagnostic_legal_agent_draws.source_manifests`); each attempt is the
frozen draw-1 item of its arm with replicate id `-r1` or `-r2`, and must send exactly MC-115's task of that item and arm.

The harness specifications are MC-112's (dsh) and MC-113's (omp) protocols with only the model route replaced: the
dsh profile and omp configuration in data/diagnostic_legal_agent_mimo/, the per-response cap, omp's model argument,
request shape and system-prompt hash, and the proxy's timeout and response-model pin.

From the repo root:
  .venv/bin/python -m code_benchmark.diagnostic_legal_agent_mimo manifest            # build and print counts
  .venv/bin/python -m code_benchmark.diagnostic_legal_agent_mimo manifest --write    # freeze manifest_v1.json
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_agent_draws as ld
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import run_legal_agent_omp as rlo
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_draws as ld  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import run_legal_agent_omp as rlo  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = la.ROOT
DATA_DIR = ROOT / "data" / "diagnostic_legal_agent_mimo"
WORK_ROOT = ROOT / "all_res" / "diagnostic_legal_agent_mimo"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
MANIFEST_PATH = DATA_DIR / "manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-legal-agent-mimo"
PHASE = "legal-agent-mimo"
DRAWS = (1, 2)
PART_ARMS = ld.PART_ARMS  # M: DSHF, OMPF, B; S: DSHF, OMPF, C
PART_SIZES = ld.PART_SIZES
MODEL_ID = "mimo-v2.6-flash"
PROTOCOL_KEYS = ("protocol_id", "protocol_version", "change", "purpose", "model", "parts", "draws", "corpora",
                 "workdir", "sources", "mc115", "harnesses", "direct", "reference", "scoring", "operational", "smoke",
                 "analysis")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _sha_checked(path: Path, sha256: str, label: str) -> str:
    if not path.is_file() or v1.sha256_file(path) != sha256:
        raise _fail(f"{label} {path} is missing or differs from its registered SHA-256")
    return sha256


# ---------------------------------------------------------------- protocol

def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict) or set(protocol) != set(PROTOCOL_KEYS):
        raise _fail(f"the legal-agent-mimo protocol must have exactly the keys {list(PROTOCOL_KEYS)}")
    if (protocol["protocol_id"], protocol["protocol_version"]) != (PROTOCOL_ID, 1):
        raise _fail("unsupported legal-agent-mimo protocol id or version")
    if {name: tuple(spec.get("arms") or ()) for name, spec in protocol["parts"].items()} != PART_ARMS:
        raise _fail(f"the legal-agent-mimo protocol must run parts {PART_ARMS}")
    if tuple(protocol["draws"]) != DRAWS:
        raise _fail(f"the legal-agent-mimo protocol must run draws {DRAWS}")
    if set(protocol["sources"]) != set(ld.SOURCES):
        raise _fail(f"the protocol must name the source manifests {ld.SOURCES}")
    if protocol["model"]["model_id"] != MODEL_ID:
        raise _fail(f"the legal-agent-mimo protocol must run {MODEL_ID}")
    if set(protocol["harnesses"]) != {"dsh", "omp"} or tuple(protocol["direct"]["arms"]) != ("B", "C"):
        raise _fail("the protocol must specify dsh (DSHF), omp (OMPF) and the direct arms B and C")
    return protocol


def harness_protocols(protocol: dict[str, Any], root: Path = ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    """MC-112's dsh protocol and MC-113's omp protocol, each read by its registered SHA-256, with MC-116's model route
    laid over their `harness` and `proxy` blocks. Everything else in them (tools, sandbox, limits) stays as it was."""
    specs = protocol["harnesses"]
    _sha_checked(root / specs["dsh"]["base_protocol"], specs["dsh"]["base_protocol_sha256"], "MC-112 protocol")
    _sha_checked(root / specs["omp"]["base_protocol"], specs["omp"]["base_protocol_sha256"], "MC-113 protocol")
    dsh = copy.deepcopy(la.load_protocol(root / specs["dsh"]["base_protocol"]))
    omp = copy.deepcopy(rlo.load_protocol(root / specs["omp"]["base_protocol"]))
    _sha_checked(root / specs["dsh"]["harness"]["profile"], specs["dsh"]["harness"]["profile_sha256"], "MiMo dsh profile")
    _sha_checked(root / specs["omp"]["harness"]["config"], specs["omp"]["harness"]["config_sha256"], "MiMo omp config")
    for base, spec in ((dsh, specs["dsh"]), (omp, specs["omp"])):
        base["harness"].update(copy.deepcopy(spec["harness"]))
        base["proxy"].update(copy.deepcopy(spec["proxy"]))
    if MODEL_ID not in " ".join(omp["harness"]["argv"]):
        raise _fail("omp's argument list must name the MiMo model")
    return dsh, omp


# ---------------------------------------------------------------- the manifest

def expand(parts: dict[str, list[tuple[str, dict[str, v1.EvalItem]]]]) -> list[v1.EvalItem]:
    """Item-major: per item, draw 1 then draw 2, the part's arms in order. Only the replicate id changes."""
    out = []
    for part in ("M", "S"):
        for _, arms in parts[part]:
            for draw in DRAWS:
                for arm in PART_ARMS[part]:
                    out.append(dataclasses.replace(arms[arm], replicate_id=f"{arm}-r{draw}"))
    return out


def check_against_mc115(items: list[v1.EvalItem], mc115: dict[str, Any]) -> None:
    """Every MC-116 attempt must carry MC-115's task, input and gold of the same item and arm (MC-115 copied the same
    draw-1 items), and every MC-115 item and arm must appear here."""
    fields = ("prompt_sha256", "input_sha256", "gold_sha256", "task")
    theirs: dict[tuple[str, str], tuple[Any, ...]] = {}
    for row in mc115["items"]:
        theirs[(f"{row['dataset_id']}:{row['item_id']}", dp.arm_of_replicate(row["replicate_id"]))] = \
            tuple(row[name] for name in fields)
    ours = set()
    for item in items:
        key = (f"{item.dataset_id}:{item.item_id}", dp.arm_of_replicate(item.replicate_id))
        mine = v1.manifest_item(item)
        if theirs.get(key) != tuple(mine[name] for name in fields):
            raise _fail(f"{key[0]} {key[1]}: the task differs from MC-115's")
        ours.add(key)
    if ours != set(theirs):
        raise _fail("MC-116's items and arms are not MC-115's")


def input_hashes(protocol: dict[str, Any], root: Path = ROOT, protocol_path: Path = PROTOCOL_PATH) -> dict[str, str]:
    hashes = {"legal_agent_mimo_protocol_sha256": v1.sha256_file(protocol_path)}
    for name, spec in protocol["sources"].items():
        for key in ("protocol", "registration"):
            hashes[f"{name}_{key}_sha256"] = _sha_checked(root / spec[key], spec[f"{key}_sha256"], f"{name} {key}")
        hashes[f"{name}_manifest_file_sha256"] = spec["manifest_file_sha256"]
    mc115 = protocol["mc115"]
    hashes["mc115_protocol_sha256"] = _sha_checked(root / mc115["protocol"], mc115["protocol_sha256"], "MC-115 protocol")
    hashes["mc115_manifest_file_sha256"] = _sha_checked(root / mc115["manifest"], mc115["manifest_file_sha256"],
                                                        "MC-115 manifest")
    for name, spec in protocol["corpora"].items():
        hashes[f"corpus_{name}_folder_sha256"] = spec["folder_sha256"]
    for name, spec in protocol["reference"].items():
        hashes[f"{name}_sha256"] = _sha_checked(root / spec["path"], spec["sha256"], name)
    hashes["dsh_profile_sha256"] = protocol["harnesses"]["dsh"]["harness"]["profile_sha256"]
    hashes["omp_config_sha256"] = protocol["harnesses"]["omp"]["harness"]["config_sha256"]
    return hashes


def build_manifest(protocol: dict[str, Any] | None = None, rebuilt: dict[str, dict[str, v1.EvalItem]] | None = None,
                   legal_frozen: dict[str, v1.EvalItem] | None = None, mc115: dict[str, Any] | None = None,
                   root: Path = ROOT) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed."""
    protocol = protocol or load_protocol()
    rebuilt = ld.source_manifests(protocol) if rebuilt is None else rebuilt
    parts = ld.base_items(rebuilt, legal_frozen)
    items = expand(parts)
    reference = mc115 if mc115 is not None else json.loads((root / protocol["mc115"]["manifest"]).read_text(
        encoding="utf-8"))
    check_against_mc115(items, reference)
    out = {item.run_key: item for item in items}
    if len(out) != len(items):
        raise _fail("duplicate legal-agent-mimo run keys")
    keys = [key for part in ("M", "S") for key, _ in parts[part]]
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, **input_hashes(protocol, root),
        "parts": {part: [key for key, _ in rows] for part, rows in parts.items()},
        "corpus_of": {key: ld.corpus_of(protocol, key.split(":", 1)[0]) for key in keys},
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
    parser = argparse.ArgumentParser(description="MC-116 inputs, offline: the manifest of MiMo's two draws.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("manifest", help="build the manifest and print its counts")
    build.add_argument("--write", action="store_true", help="freeze it to manifest_v1.json")
    args = parser.parse_args(argv)
    protocol = load_protocol()
    harness_protocols(protocol)  # fails on a changed base protocol, profile or configuration
    manifest, _ = build_manifest(protocol)
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
