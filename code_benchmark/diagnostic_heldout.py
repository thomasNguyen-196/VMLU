"""Held-out set of router v2 (openspec change: diagnostic-router-v2, spec `diagnostic-router-heldout`).

Items that no router has seen: 300 ViBidLQA val items and 300 VMLU valid items drawn per VMLU category in
proportion to its size, each ranked by sha256(seed, dataset:item) so the draw needs no random generator. The
items are rebuilt with the frozen main-v1 prompt builders, and arms B and S run with two draws each under the
model, transport, scoring and budget blocks of the prospective campaign protocol, which the held-out protocol
copies and this module checks.

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_heldout            # build the manifest and compare it with the frozen one
  .venv/bin/python -m code_benchmark.diagnostic_heldout --write    # freeze data/diagnostic_router_v2/heldout_v1.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import vi_multimodel as v1

DATA_DIR = dp.ROOT / "data" / "diagnostic_router_v2"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
MANIFEST_PATH = DATA_DIR / "heldout_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
RULE_PATH = DATA_DIR / "router_v2.json"
PROTOCOL_ID = "vmlu-diagnostic-router-v2-heldout"
PHASE = "heldout"
MIRRORED = ("model", "transport", "scoring", "budget")
VMLU, BIDLQA = "vi-multimodel-v1-vmlu-valid", "bidlqa-val"
SOURCES = {VMLU: lambda: v1._load_vmlu("valid"), BIDLQA: lambda: v1._load_bidlqa("val")}  # noqa: SLF001


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    try:
        protocol = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read held-out protocol {path}: {exc}") from exc
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported held-out protocol id/version")
    campaign = dp.load_protocol()
    differing = [block for block in MIRRORED if protocol.get(block) != campaign.get(block)]
    if differing:
        raise _fail(f"the held-out protocol's {differing} differ from the campaign protocol")
    phase = (protocol.get("phases") or {}).get(PHASE) or {}
    if phase.get("arms") != ["B", "S"] or phase.get("replicates") != 2:
        raise _fail("the held-out phase runs arms B and S with 2 replicates")
    if set(protocol.get("sampling") or {}) != set(SOURCES) or set(protocol.get("datasets") or []) != set(SOURCES):
        raise _fail(f"the held-out datasets must be {sorted(SOURCES)}")
    if set(SOURCES) & set(campaign["datasets"]):
        raise _fail("a held-out dataset is a campaign dataset")
    return protocol


def _ranked(items: list[v1.EvalItem], seed: int) -> list[v1.EvalItem]:
    def rank(item: v1.EvalItem) -> str:
        return hashlib.sha256(f"{seed}\t{dp.item_key(item.dataset_id, item.item_id)}".encode("utf-8")).hexdigest()
    return sorted(items, key=rank)


def sample_items(protocol: dict[str, Any]) -> list[v1.EvalItem]:
    chosen: list[v1.EvalItem] = []
    for dataset_id in sorted(protocol["sampling"]):
        spec = protocol["sampling"][dataset_id]
        items = SOURCES[dataset_id]()
        if any(item.dataset_id != dataset_id or item.replicate_id != dp.MAIN_REPLICATE for item in items):
            raise _fail(f"{dataset_id}: the source builder returned an unexpected item")
        strata: dict[str, list[v1.EvalItem]] = defaultdict(list)
        for item in items:
            strata[item.stratum if spec["strata"] == "category" else "all"].append(item)
        counts = v1._allocate_counts({name: len(group) for name, group in strata.items()}, spec["n"])  # noqa: SLF001
        for name in sorted(strata):
            chosen.extend(_ranked(strata[name], spec["seed"])[:counts[name]])
    return chosen


def build_manifest(protocol: dict[str, Any] | None = None, protocol_path: Path = PROTOCOL_PATH
                   ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed like the campaign manifests."""
    protocol = protocol or load_protocol(protocol_path)
    base = sample_items(protocol)
    items = dp.expand_arms(base, PHASE, protocol, dp.load_templates(), {})
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate held-out run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE,
        "heldout_protocol_sha256": v1.sha256_file(protocol_path),
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "n": len(items), "item_count": len(base),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in base).items())),
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the frozen held-out manifest {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the router v2 held-out manifest (offline).")
    ap.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    manifest, _ = build_manifest()
    print(f"held-out manifest {manifest['manifest_sha256']}: {manifest['item_count']} items, {manifest['n']} attempts, "
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
