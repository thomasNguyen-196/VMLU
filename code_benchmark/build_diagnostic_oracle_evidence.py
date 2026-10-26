#!/usr/bin/env python3
"""Build the oracle evidence records of arm O for the prospective diagnostic campaign (task 7.1).

    .venv/bin/python -m code_benchmark.build_diagnostic_oracle_evidence \
        --review all_res/diagnostic_v1/pilot-review-v4/reviews/<annotator>.jsonl \
        --provisions all_res/diagnostic_prospective/oracle_draft/legal_mc_provisions_draft.json

Evidence anchors follow design Decision 11 of openspec/changes/diagnostic-prospective-campaign:
Legal MC anchors whose audited input evidence is insufficient and whose gold is valid. The labels
come from one imported review export, whose annotator and SHA-256 go into every record; rebuild
with --overwrite after the independent review is adjudicated. The output stays under the ignored
all_res/ and is checked with the same loader the runner uses for --oracle-evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import vi_multimodel as v1

DEFAULT_OUT = dp.ROOT / "all_res" / "diagnostic_prospective" / "oracle" / "oracle_evidence_v1.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Error: cannot read {path}: {exc}") from exc


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the arm-O oracle evidence records (offline).")
    ap.add_argument("--review", type=Path, required=True,
                    help="imported review JSONL of one annotator (the pilot's reviews/ folder)")
    ap.add_argument("--provisions", type=Path, required=True, help='drafted provisions JSON ({"provisions": [...]})')
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output JSONL (default: {DEFAULT_OUT})")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace an existing output; only before the core manifest that binds it is frozen")
    args = ap.parse_args()
    if args.out.exists() and not args.overwrite:
        raise SystemExit(f"Error: {args.out} exists; pass --overwrite to rebuild it")
    try:
        provisions = json.loads(args.provisions.read_text(encoding="utf-8"))["provisions"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SystemExit(f"Error: cannot read provisions from {args.provisions}: {exc}") from exc
    protocol = dp.load_protocol()
    records, excluded = dp.oracle_records(read_jsonl(args.review), provisions, protocol)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records),
                   encoding="utf-8")
    loaded = dp.load_oracle_evidence(tmp, protocol, v1.rebuild_items(protocol["parent"]["manifest_phase"]))
    tmp.replace(args.out)
    print(f"{len(loaded)} oracle records -> {args.out}")
    for key, provisions_of_item in loaded.items():
        print(f"  {key}: {len(provisions_of_item)} provision(s)")
    print(f"evidence_sha256 (O) {dp.evidence_digest(loaded)}")
    for key, reason in excluded.items():
        print(f"  no evidence arm: {key} ({reason})")


if __name__ == "__main__":
    main()
