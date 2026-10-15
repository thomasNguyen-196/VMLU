"""Freeze item IDs, prompt hashes and gold hashes for benchmark v1.

The manifest stores IDs and hashes only; it never copies the reviewed answers.
Run from repo root:
  .venv/bin/python code_benchmark/make_vi_multimodel_manifest.py --phase pilot
  .venv/bin/python code_benchmark/make_vi_multimodel_manifest.py --phase main
"""
from __future__ import annotations

import argparse

try:
    from code_benchmark.vi_multimodel import PILOT_PHASES, save_manifest
except ImportError:
    from vi_multimodel import PILOT_PHASES, save_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze one Vietnamese multi-model item manifest.")
    parser.add_argument("--phase", choices=(*sorted(PILOT_PHASES), "main"), required=True)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing manifest before any model run has used it",
    )
    args = parser.parse_args()
    print(f"wrote {save_manifest(args.phase, overwrite=args.overwrite)}")


if __name__ == "__main__":
    main()
