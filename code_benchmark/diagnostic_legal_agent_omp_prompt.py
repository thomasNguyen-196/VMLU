"""MC-117 inputs (openspec change diagnostic-legal-agent-omp-prompt), offline: the protocol, each model's OMPS
specification (its registered OMPF specification with `--system-prompt <dsh's system prompt for the model>`), and
the manifest of OMPS on MC-115's 646 items, draws 1 and 2.

The tasks are copied, not rebuilt: MC-112's, MC-113's and MC-114's manifests are rebuilt with their own modules and
must equal their frozen files (MC-115's path, `diagnostic_legal_agent_draws.source_manifests`); each attempt is the
frozen draw-1 OMPF item with replicate id `OMPS-r1` or `OMPS-r2`, and must send exactly MC-115's OMPF task of that item.
One manifest serves both models: the items and tasks do not depend on the model.

The OMPS specifications:
  qwen  MC-115's omp protocol (MC-113's, read through MC-115's registered protocol) - IEC Qwen3.5-9B-65K;
  mimo  MC-116's omp protocol (MC-113's with MiMo's route) - OpenCode Go mimo-v2.6-flash;
each with dsh's system prompt for that model appended to the argument list, read from a file by its SHA-256.

From the repo root:
  .venv/bin/python -m code_benchmark.diagnostic_legal_agent_omp_prompt manifest            # build and print counts
  .venv/bin/python -m code_benchmark.diagnostic_legal_agent_omp_prompt manifest --write    # freeze manifest_v1.json
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
    from code_benchmark import diagnostic_legal_agent_mimo as lm
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import run_legal_agent_v2 as rl2
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_agent_draws as ld  # type: ignore[no-redef]
    import diagnostic_legal_agent_mimo as lm  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import run_legal_agent_v2 as rl2  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = la.ROOT
DATA_DIR = ROOT / "data" / "diagnostic_legal_agent_omp_prompt"
WORK_ROOT = ROOT / "all_res" / "diagnostic_legal_agent_omp_prompt"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
MANIFEST_PATH = DATA_DIR / "manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-legal-agent-omp-prompt"
PHASE = "legal-agent-omp-prompt"
ARM, SOURCE_ARM = "OMPS", "OMPF"
DRAWS = (1, 2)
MODELS = ("qwen", "mimo")
SYSTEM_PROMPT_FLAG = "--system-prompt"
PROTOCOL_KEYS = ("protocol_id", "protocol_version", "change", "purpose", "arm", "parts", "draws", "corpora", "workdir",
                 "sources", "mc115", "models", "reference", "scoring", "operational", "smoke", "analysis")
MODEL_KEYS = ("model_id", "profile_id", "route_card", "base_protocol", "base_protocol_sha256", "route", "prompt_file",
              "prompt_sha256", "offline_capture_system_sha256", "system_prompt_sha256", "budget_tokens")


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
        raise _fail(f"the legal-agent-omp-prompt protocol must have exactly the keys {list(PROTOCOL_KEYS)}")
    if (protocol["protocol_id"], protocol["protocol_version"]) != (PROTOCOL_ID, 1):
        raise _fail("unsupported legal-agent-omp-prompt protocol id or version")
    if protocol["arm"] != ARM or tuple(protocol["draws"]) != DRAWS or set(protocol["parts"]) != {"M", "S"}:
        raise _fail(f"the protocol must run {ARM} at draws {DRAWS} on parts M and S")
    if set(protocol["models"]) != set(MODELS) or any(set(spec) != set(MODEL_KEYS) for spec in protocol["models"].values()):
        raise _fail(f"the protocol must specify the models {MODELS}, each with the keys {list(MODEL_KEYS)}")
    if set(protocol["sources"]) != set(ld.SOURCES):
        raise _fail(f"the protocol must name the source manifests {ld.SOURCES}")
    return protocol


def model_spec(protocol: dict[str, Any], model: str) -> dict[str, Any]:
    if model not in protocol["models"]:
        raise _fail(f"unknown model {model!r}; expected one of {MODELS}")
    return protocol["models"][model]


def prompt_text(protocol: dict[str, Any], model: str, root: Path = ROOT) -> str:
    """dsh's system prompt for the model, byte for byte as dsh sent it, read by its registered SHA-256."""
    spec = model_spec(protocol, model)
    path = root / spec["prompt_file"]
    _sha_checked(path, spec["prompt_sha256"], f"{model} dsh system prompt")
    return path.read_bytes().decode("utf-8")


def base_omp_protocol(protocol: dict[str, Any], model: str, root: Path = ROOT) -> dict[str, Any]:
    """The model's registered OMPF specification: MC-113's omp protocol as MC-115 read it (Qwen), or MC-116's
    overlay of it (MiMo)."""
    spec = model_spec(protocol, model)
    path = root / spec["base_protocol"]
    _sha_checked(path, spec["base_protocol_sha256"], f"{spec['route_card']} protocol")
    if model == "qwen":
        return copy.deepcopy(rl2.harness_protocols(ld.load_protocol(path))[1])
    return copy.deepcopy(lm.harness_protocols(lm.load_protocol(path), root)[1])


def omp_protocol(protocol: dict[str, Any], model: str, root: Path = ROOT) -> dict[str, Any]:
    """OMPS: the model's OMPF specification with `--system-prompt <dsh's prompt>` appended and the system-prompt pin
    of this card (None until the smoke test sets it). Nothing else changes."""
    spec = model_spec(protocol, model)
    out = base_omp_protocol(protocol, model, root)
    argv = list(out["harness"]["argv"])
    if SYSTEM_PROMPT_FLAG in argv:
        raise _fail(f"the {model} OMPF argument list already sets {SYSTEM_PROMPT_FLAG}")
    out["harness"]["argv"] = [*argv, SYSTEM_PROMPT_FLAG, prompt_text(protocol, model, root)]
    out["harness"]["system_prompt_file"] = spec["prompt_file"]
    out["harness"]["system_prompt_file_sha256"] = spec["prompt_sha256"]
    out["proxy"]["system_prompt_sha256"] = spec["system_prompt_sha256"]
    if spec["model_id"] not in out["harness"]["argv"][out["harness"]["argv"].index("--model") + 1]:
        raise _fail(f"the {model} OMPS argument list does not name {spec['model_id']}")
    return out


# ---------------------------------------------------------------- the manifest

def expand(parts: dict[str, list[tuple[str, dict[str, v1.EvalItem]]]]) -> list[v1.EvalItem]:
    """Item-major: per item, draw 1 then draw 2 of OMPS, each the frozen draw-1 OMPF item with a new replicate id."""
    return [dataclasses.replace(arms[SOURCE_ARM], replicate_id=f"{ARM}-r{draw}")
            for part in ("M", "S") for _, arms in parts[part] for draw in DRAWS]


def check_against_mc115(items: list[v1.EvalItem], mc115: dict[str, Any]) -> None:
    """Every OMPS attempt must carry MC-115's OMPF task, input and gold of the same item, and every MC-115 OMPF item
    must appear."""
    fields = ("prompt_sha256", "input_sha256", "gold_sha256", "task")
    theirs = {f"{row['dataset_id']}:{row['item_id']}": tuple(row[name] for name in fields)
              for row in mc115["items"] if dp.arm_of_replicate(row["replicate_id"]) == SOURCE_ARM}
    ours = set()
    for item in items:
        key = f"{item.dataset_id}:{item.item_id}"
        mine = v1.manifest_item(item)
        if theirs.get(key) != tuple(mine[name] for name in fields):
            raise _fail(f"{key}: the OMPS task differs from MC-115's OMPF task")
        ours.add(key)
    if ours != set(theirs):
        raise _fail("MC-117's items are not MC-115's OMPF items")


def input_hashes(protocol: dict[str, Any], root: Path = ROOT, protocol_path: Path = PROTOCOL_PATH) -> dict[str, str]:
    hashes = {"legal_agent_omp_prompt_protocol_sha256": v1.sha256_file(protocol_path)}
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
    for model in MODELS:
        spec = model_spec(protocol, model)
        hashes[f"{model}_base_protocol_sha256"] = _sha_checked(root / spec["base_protocol"], spec["base_protocol_sha256"],
                                                               f"{model} base protocol")
        hashes[f"{model}_prompt_sha256"] = _sha_checked(root / spec["prompt_file"], spec["prompt_sha256"],
                                                        f"{model} prompt")
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
        raise _fail("duplicate legal-agent-omp-prompt run keys")
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
    parser = argparse.ArgumentParser(description="MC-117 inputs, offline: the OMPS manifest and specifications.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("manifest", help="build the manifest and print its counts")
    build.add_argument("--write", action="store_true", help="freeze it to manifest_v1.json")
    args = parser.parse_args(argv)
    protocol = load_protocol()
    for model in MODELS:  # fails on a changed base protocol, configuration or prompt file
        omp_protocol(protocol, model)
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
