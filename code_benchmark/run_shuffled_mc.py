#!/usr/bin/env python3
"""Wrapper: run the BYTE-FROZEN MC runner over the pre-registered shuffled input.

The condition is pre-registered in MC-35 (measurement_card.md): same model,
same frozen `build_prompt`/`extract_answer`/scorer, same inference flags as
MC-31 arm A — the ONLY difference is the input file (choices shuffled, gold
remapped by text). Nothing here touches `run_mc_eval.py`.

Why a wrapper instead of a flag on the runner:
  * the runner's output names (`full_evaluation_<slug>.csv`, `accuracy_<slug>.csv`,
    count-only `raw_result_<n>_<slug>.csv`) are the arm-A names this model
    folder already uses for OTHER conditions; renaming after the run is the one
    point where "same code, different condition" stops colliding.
  * `--resume` must never cross conditions: the wrapper refuses to run when any
    same-namespace artifact of a previous run is still present, and never
    passes `--resume` down.

Run from repo root:

    PYTHONPATH=/tmp/opencode/pyshim .venv/bin/python code_benchmark/run_shuffled_mc.py

(the PYTHONPATH shim is the MC-32 DNS workaround for the internal IEC URL,
not part of the condition).
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404 — fixed local argv, shell=False, no user string
import sys
from pathlib import Path

try:
    from code_benchmark.common import model_dirs, sanitize_model
except ImportError:  # direct run from code_benchmark/
    from common import model_dirs, sanitize_model

MODEL_DEFAULT = "Qwen3.5-9B-65K"
TAG_DEFAULT = "s1234"
INPUT_DEFAULT = "legal_slm_multichoice_shuffled_s1234_input.jsonl"
FOLDER_DEFAULT = "data"
RUNNER = Path("code_benchmark/run_mc_eval.py")
# MC-31 arm-A inference flags, pre-registered in MC-35. Never varied here.
FROZEN = {"temperature": "0.0", "seed": "42", "max_tokens": "4", "workers": "4"}


def count_checkpoints(folder: Path, slug: str) -> list[Path]:
    """Count-only MC checkpoints (`raw_result_<n>_<slug>.csv`) — the exact
    namespace run_mc_eval's `--resume` would pick up. Dataset-scoped files
    (`raw_result_legal_mc_*`) are a DIFFERENT namespace and not listed."""
    pat = re.compile(rf"^raw_result_\d+_{re.escape(slug)}\.csv$")
    return sorted(p for p in folder.glob(f"raw_result_*_{slug}.csv") if pat.match(p.name))


def unrenamed_finals(folder: Path, slug: str) -> list[Path]:
    names = [f"full_evaluation_{slug}.csv", f"accuracy_{slug}.csv"]
    return [folder / n for n in names if (folder / n).exists()]


def shuffled_outputs(folder: Path, slug: str, tag: str) -> list[Path]:
    return [folder / f"full_evaluation_shuffled_{tag}_{slug}.csv",
            folder / f"accuracy_shuffled_{tag}_{slug}.csv"]


def conflicts(folder: Path, slug: str, tag: str) -> list[str]:
    """Everything that makes this run unsafe or dishonest to start."""
    out: list[str] = []
    for p in count_checkpoints(folder, slug):
        out.append(f"count-only checkpoint still present: {p.name} "
                   f"(a previous --resume namespace; move it away deliberately)")
    for p in unrenamed_finals(folder, slug):
        out.append(f"unrenamed final still present: {p.name} "
                   f"(previous run never reached the rename step)")
    existing = [p.name for p in shuffled_outputs(folder, slug, tag) if p.exists()]
    if existing:
        out.append(f"shuffled output already exists: {', '.join(existing)} "
                   f"(re-running would overwrite a measurement — move/delete first)")
    return out


def build_runner_argv(*, python: str, folder: str, file: str, model: str,
                      submission_out: Path, runner: Path = RUNNER) -> list[str]:
    """The exact frozen-runner invocation. No `--resume` — ever."""
    return [python, str(runner),
            "--folder", folder, "--file", file, "--model", model,
            "--temperature", FROZEN["temperature"], "--seed", FROZEN["seed"],
            "--max-tokens", FROZEN["max_tokens"], "--workers", FROZEN["workers"],
            "--submission-out", str(submission_out)]


def plan_renames(folder: Path, slug: str, tag: str) -> list[tuple[Path, Path]]:
    """Post-run moves: (source, destination). Sources are validated by the
    caller; destinations are checked collision-free by `execute_renames`."""
    src_final = folder / f"full_evaluation_{slug}.csv"
    src_acc = folder / f"accuracy_{slug}.csv"
    dst_final = folder / f"full_evaluation_shuffled_{tag}_{slug}.csv"
    dst_acc = folder / f"accuracy_shuffled_{tag}_{slug}.csv"
    return [(src_final, dst_final), (src_acc, dst_acc)]


def execute_renames(pairs: list[tuple[Path, Path]]) -> None:
    for src, dst in pairs:
        if not src.exists():
            raise SystemExit(f"Error: expected fresh output missing after the run: {src} "
                             f"(runner naming changed? nothing was renamed)")
        if dst.exists():
            raise SystemExit(f"Error: refusing to overwrite {dst}")
        src.rename(dst)


def park_checkpoints(folder: Path, slug: str, tag: str) -> list[Path]:
    """Move count-only checkpoints into `shuffled_checkpoints/` so the arm-A
    namespace stays clean. Collision -> hard stop (never overwrite)."""
    cps = count_checkpoints(folder, slug)
    if not cps:
        return []
    park = folder / "shuffled_checkpoints"
    park.mkdir(exist_ok=True)
    moved = []
    for cp in cps:
        target = park / cp.name
        if target.exists():
            raise SystemExit(f"Error: {target} already exists in the park dir — "
                             f"resolve by hand, nothing else was moved")
        cp.rename(target)
        moved.append(target)
    return moved


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=MODEL_DEFAULT,
                    help="model tag (default: %(default)s — MC-35 condition)")
    ap.add_argument("--folder", default=FOLDER_DEFAULT,
                    help="folder holding the shuffled input (default: %(default)s)")
    ap.add_argument("--file", default=INPUT_DEFAULT,
                    help="shuffled input JSONL (default: %(default)s)")
    ap.add_argument("--tag", default=TAG_DEFAULT,
                    help="shuffle tag used in output names (default: %(default)s)")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter for the runner subprocess (default: this one)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the conflict check, argv and rename plan; touch nothing")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    slug = sanitize_model(args.model)
    folder, subs, _logs = model_dirs(args.model)

    problems = conflicts(folder, slug, args.tag)
    if problems:
        raise SystemExit("Error: refusing to start — condition collision:\n  - "
                         + "\n  - ".join(problems))

    submission_out = subs / f"submission_shuffled_{args.tag}.csv"
    argv = build_runner_argv(python=args.python, folder=args.folder, file=args.file,
                             model=args.model, submission_out=submission_out)
    renames = plan_renames(folder, slug, args.tag)

    if args.dry_run:
        print("clean: no condition collision")
        print("argv:", " ".join(argv))
        for src, dst in renames:
            print(f"rename: {src.name} -> {dst.name}")
        print(f"park:   raw_result_*_{slug}.csv -> shuffled_checkpoints/")
        return

    print("clean: no condition collision")
    print("running:", " ".join(argv))
    proc = subprocess.run(argv, check=False)  # nosec B603 — fixed local argv
    if proc.returncode != 0:
        raise SystemExit(f"Error: runner exited {proc.returncode} — outputs left "
                         f"in place for inspection; wrapper did NOT rename anything")

    execute_renames(renames)
    moved = park_checkpoints(folder, slug, args.tag)
    print(f"renamed: {renames[0][1].name}, {renames[1][1].name}")
    print(f"parked:  {len(moved)} checkpoint(s) -> shuffled_checkpoints/")
    print(f"submission: {submission_out}")
    print("next: compare_position_bias.py")


if __name__ == "__main__":
    main()
