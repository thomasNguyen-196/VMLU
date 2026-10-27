"""Held-out set of router v3 (openspec change: diagnostic-router-v3, spec `diagnostic-router-v3-heldout`).

Three datasets that no router has used, each with 60 calibration items and 300 test items:
* VMLU valid outside MC-94 (444 items), drawn per VMLU category in proportion to its size;
* VM14K four-option items of the shuffled0 variant, in the format of `make_vm14k_input` (rows with an empty
  question or placeholder options left out), drawn per category of the frozen VM14K manifest in proportion;
* ViBidLQA train items whose question appears once across the train, val and test splits, drawn at random.
Items are ranked by sha256(seed, dataset:item), so the draw needs no random generator; inside a dataset the
calibration items are the lowest ranks of each stratum, in proportion, and the manifest records them. Prompts come
from the frozen main-v1 builders, and arms B and S run with two draws each under the model, transport, scoring and
budget blocks of the prospective campaign protocol, which the protocol copies and this module checks.

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_heldout_v3            # build the manifest and compare it with the frozen one
  .venv/bin/python -m code_benchmark.diagnostic_heldout_v3 --write    # freeze data/diagnostic_router_v3/heldout_v3.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_calibration as cal
    from code_benchmark import diagnostic_heldout as dh
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import make_vm14k_input as vm14k
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_calibration as cal
    import diagnostic_heldout as dh
    import diagnostic_prospective as dp
    import make_vm14k_input as vm14k
    import vi_multimodel as v1

DATA_DIR = cal.DATA_DIR
PROTOCOL_PATH = DATA_DIR / "protocol.json"
MANIFEST_PATH = DATA_DIR / "heldout_v3.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-router-v3-heldout"
PHASE = "heldout"
MIRRORED = dh.MIRRORED
VMLU, VM14K, BIDLQA = dh.VMLU, "vm14k-4-options", "bidlqa-train"
VMLU_REMAINING = 444
VM14K_SOURCE = dp.ROOT / "v_med_vm14k" / "data-processed-shuffled0.jsonl"
VM14K_MANIFEST = dp.ROOT / "data" / "vm14k_manifest.json"
BIDLQA_TRAIN_SOURCE = dp.ROOT / "v_legal_slsp" / "bidlqa" / "ViBidLQA_train.jsonl"
PINNED = {  # v_med_vm14k/README.md, data/vm14k_manifest.json, v_legal_slsp/README.md
    VM14K_SOURCE: "688218341055536f032806beb7f3b6d552d5429eebe4620a581e9c861e05aef4",
    VM14K_MANIFEST: "ffbc536b84c0166b5d479342adf0194d8b11d90aaa9e147378a59a930341133b",
    BIDLQA_TRAIN_SOURCE: "f4b8c1cebfac4dfe0d429c3071d51111b0a1a99a82c7313dda2bbe8e2325bf51",
}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pinned(path: Path) -> None:
    digest = v1.sha256_file(path)
    if digest != PINNED[path]:
        raise _fail(f"source drift for {path}: sha256 {digest} is not the pinned {PINNED[path]}")


# ---------------------------------------------------------------- sources

def load_vmlu() -> list[v1.EvalItem]:
    """VMLU valid without the 300 items of MC-94."""
    used = {dp.item_key(item.dataset_id, item.item_id) for item in dh.sample_items(dh.load_protocol())}
    items = [item for item in v1._load_vmlu("valid")  # noqa: SLF001
             if dp.item_key(item.dataset_id, item.item_id) not in used]
    if len(items) != VMLU_REMAINING:
        raise _fail(f"VMLU valid outside MC-94 has {len(items)} items, not {VMLU_REMAINING}")
    return items


def load_vm14k() -> list[v1.EvalItem]:
    """Four-option VM14K items (shuffled0), choices as `make_vm14k_input` writes them, category from the frozen
    VM14K manifest; rows with an empty question or placeholder options are left out."""
    for path in (VM14K_SOURCE, VM14K_MANIFEST):
        _pinned(path)
    source = vm14k.load_rows(VM14K_SOURCE)
    rows, _ = vm14k.build(source)
    category = {entry["id"]: entry["category"] for entry in json.loads(VM14K_MANIFEST.read_text(encoding="utf-8"))["items"]}
    items = []
    for original, row in zip(source, rows, strict=True):
        options = [str(option).strip() for option in original["options"]]
        if len(options) != 4 or not row["question"] or any(option.lower().startswith("option") for option in options):
            continue
        items.append(v1.EvalItem(
            dataset_id=VM14K, source_dataset="vm14k-shuffled0", item_id=row["id"], replicate_id=dp.MAIN_REPLICATE,
            task="multiple_choice", stratum=category[row["id"]], question=row["question"],
            passage_id=category[row["id"]], prompt=v1.build_prompt(row["question"], row["choices"]),
            gold_answer=row["answer"]))
    return items


def load_bidlqa_train() -> list[v1.EvalItem]:
    """ViBidLQA train items whose question appears once across train, val and test; ids number the source lines."""
    _pinned(BIDLQA_TRAIN_SOURCE)
    train = v1.load_bidlqa_source(BIDLQA_TRAIN_SOURCE, PINNED[BIDLQA_TRAIN_SOURCE])
    others = []
    for split in ("val", "test"):
        config = v1.bidlqa_split_config(split)
        others.extend(v1.load_bidlqa_source(dp.ROOT / config["source"], config["sha"]))
    counts = Counter(v1.normalized_key(str(row["question"])) for row in [*train, *others])
    items = []
    for number, row in enumerate(train, 1):
        context, question = str(row["context"]), str(row["question"]).strip()
        if counts[v1.normalized_key(question)] != 1:
            continue
        items.append(v1.EvalItem(
            dataset_id=BIDLQA, source_dataset="bidlqa", item_id=f"BIDLQA-TR-{number:04d}",
            replicate_id=dp.MAIN_REPLICATE, task="reading", stratum="all", question=question,
            passage_id=v1.sha256_bytes(v1.normalized_key(context).encode("utf-8")),
            prompt=v1.build_reading_prompt(context, question), gold_answer=str(row["answer"]).strip()))
    return items


SOURCES = {VMLU: load_vmlu, VM14K: load_vm14k, BIDLQA: load_bidlqa_train}


# ---------------------------------------------------------------- protocol, sample and manifest

def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    try:
        protocol = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the held-out v3 protocol {path}: {exc}") from exc
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported held-out v3 protocol id/version")
    campaign = dp.load_protocol()
    differing = [block for block in MIRRORED if protocol.get(block) != campaign.get(block)]
    if differing:
        raise _fail(f"the held-out v3 protocol's {differing} differ from the campaign protocol")
    phase = (protocol.get("phases") or {}).get(PHASE) or {}
    if phase.get("arms") != ["B", "S"] or phase.get("replicates") != 2:
        raise _fail("the held-out v3 phase runs arms B and S with 2 replicates")
    sampling = protocol.get("sampling") or {}
    if set(sampling) != set(SOURCES) or set(protocol.get("datasets") or []) != set(SOURCES):
        raise _fail(f"the held-out v3 datasets must be {sorted(SOURCES)}")
    if set(SOURCES) & set(campaign["datasets"]):
        raise _fail("a held-out v3 dataset is a campaign dataset")
    size = cal.load_procedure()[0]["calibration_items"]
    for dataset_id, spec in sampling.items():
        if spec.get("calibration") != size or not spec.get("n", 0) > size:
            raise _fail(f"{dataset_id}: the sample must hold the procedure's {size} calibration items and test items")
    return protocol


def sample_items(protocol: dict[str, Any]) -> tuple[list[v1.EvalItem], dict[str, list[str]]]:
    """(the sampled items, {dataset: calibration item keys}). Inside a dataset the calibration items are the
    lowest-ranked of each stratum, allocated in proportion to the stratum's share of the sample."""
    chosen: list[v1.EvalItem] = []
    calibration: dict[str, list[str]] = {}
    for dataset_id in sorted(protocol["sampling"]):
        spec = protocol["sampling"][dataset_id]
        items = SOURCES[dataset_id]()
        if any(item.dataset_id != dataset_id or item.replicate_id != dp.MAIN_REPLICATE for item in items):
            raise _fail(f"{dataset_id}: the source builder returned an unexpected item")
        strata: dict[str, list[v1.EvalItem]] = defaultdict(list)
        for item in items:
            strata[item.stratum if spec["strata"] == "category" else "all"].append(item)
        counts = v1._allocate_counts({name: len(group) for name, group in strata.items()}, spec["n"])  # noqa: SLF001
        picked = {name: dh._ranked(strata[name], spec["seed"])[:counts.get(name, 0)] for name in sorted(strata)}  # noqa: SLF001
        shares = v1._allocate_counts({name: len(group) for name, group in picked.items() if group},  # noqa: SLF001
                                     spec["calibration"])
        calibration[dataset_id] = [dp.item_key(item.dataset_id, item.item_id)
                                   for name in sorted(picked) for item in picked[name][:shares.get(name, 0)]]
        chosen.extend(item for name in sorted(picked) for item in picked[name])
    return chosen, calibration


def build_manifest(protocol: dict[str, Any] | None = None, protocol_path: Path = PROTOCOL_PATH
                   ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed like the campaign manifests."""
    protocol = protocol or load_protocol(protocol_path)
    base, calibration = sample_items(protocol)
    items = dp.expand_arms(base, PHASE, protocol, dp.load_templates(), {})
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate held-out v3 run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE,
        "heldout_protocol_sha256": v1.sha256_file(protocol_path),
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "source_sha256": {str(path.relative_to(dp.ROOT)): digest for path, digest in PINNED.items()},
        "n": len(items), "item_count": len(base),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in base).items())),
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "calibration_items": calibration,
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the frozen held-out v3 manifest {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the router v3 held-out manifest (offline).")
    ap.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    manifest, _ = build_manifest()
    calibration = {dataset: len(keys) for dataset, keys in manifest["calibration_items"].items()}
    print(f"held-out v3 manifest {manifest['manifest_sha256']}: {manifest['item_count']} items, {manifest['n']} attempts, "
          f"datasets {manifest['dataset_counts']}, calibration {calibration}, arms {manifest['arm_counts']}")
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
