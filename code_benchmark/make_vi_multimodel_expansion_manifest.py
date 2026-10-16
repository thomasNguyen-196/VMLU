"""Freeze expanded VMLU and V-Bench item manifests.

The manifest stores IDs, input/schema hashes and local gold hashes only; it
does not copy withheld VMLU test or V-Bench references. Run from repo root:
  .venv/bin/python code_benchmark/make_vi_multimodel_expansion_manifest.py --phase pilot
"""
from __future__ import annotations

import argparse

try:
    from code_benchmark.vi_multimodel_expansion import save_manifest
except ImportError:
    from vi_multimodel_expansion import save_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze one expansion-v2 item manifest.")
    parser.add_argument("--phase", choices=("pilot", "vmlu", "vbench", "all"), required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    phases = ("pilot", "vmlu", "vbench") if args.phase == "all" else (args.phase,)
    for phase in phases:
        print(f"wrote {save_manifest(phase, overwrite=args.overwrite)}")


if __name__ == "__main__":
    main()
