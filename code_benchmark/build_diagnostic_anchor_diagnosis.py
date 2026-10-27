#!/usr/bin/env python3
"""Build the anchor-diagnosis file of the prospective diagnostic campaign (task 9.5, design Decision 12).

    .venv/bin/python -m code_benchmark.build_diagnostic_anchor_diagnosis \
        [--pilot-dir all_res/diagnostic_v1/pilot-review-v4] [--out <jsonl>] [--overwrite]

One record per audit anchor with its final judgment: the judgment every imported review agrees on, or the
FINAL block of the anchor's resolved adjudication. The router evaluation reads it to score detection and to
drop gold-not-valid anchors, and the recovery-by-hypothesis analysis groups the anchors by it; neither ever
feeds it to the router. Its SHA-256 goes into the core registration. The output stays under the ignored
all_res/ and is re-read with the loader the analyses use; a manifest next to it records the input hashes.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from code_benchmark import diagnostic_prospective as dp
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp

DEFAULT_PILOT = dp.ROOT / "all_res" / "diagnostic_v1" / "pilot-review-v4"
DEFAULT_OUT = dp.ROOT / "all_res" / "diagnostic_prospective" / "audit" / "anchor_diagnosis_v1.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the final audit judgment of every anchor (offline).")
    ap.add_argument("--pilot-dir", type=Path, default=DEFAULT_PILOT, help=f"pilot packet (default: {DEFAULT_PILOT})")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output JSONL (default: {DEFAULT_OUT})")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace an existing output; only before the core registration records its hash")
    args = ap.parse_args()
    if args.out.exists() and not args.overwrite:
        raise SystemExit(f"Error: {args.out} exists; pass --overwrite to rebuild it")
    records, inputs = dp.anchor_diagnosis(args.pilot_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records),
                   encoding="utf-8")
    loaded, digest = dp.load_anchor_diagnosis(tmp)
    tmp.replace(args.out)
    _, pilot_content = dp.anchor_item_keys(args.pilot_dir)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "anchor_diagnosis_sha256": digest,
        "pilot_content_sha256": pilot_content, "inputs_sha256": inputs, "anchors": len(loaded),
        "judgment_source": dict(Counter(r["judgment_source"] for r in records)),
        "diagnostic_outcome": dict(Counter(r["diagnostic_outcome"] for r in records)),
        "diagnostic_labels": dict(Counter(label for r in records for label in r["diagnostic_labels"])),
        "gold_not_valid": [dp.item_key(r["dataset_id"], r["item_id"]) for r in records if r["gold_validity"] != "valid"],
    }
    manifest_path = args.out.with_name(args.out.stem + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("anchor_diagnosis_sha256", "anchors", "judgment_source",
                                                      "diagnostic_outcome", "diagnostic_labels")},
                     ensure_ascii=False, indent=2))
    print(f"{len(loaded)} anchor judgments -> {args.out}")


if __name__ == "__main__":
    main()
