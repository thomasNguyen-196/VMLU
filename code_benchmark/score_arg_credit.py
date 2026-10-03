"""Partial argument credit for V-Bench agentic arms (metric group 1.3).

For every arm with per-item agentic replies — direct checkpoints
(`vbench_result_*`) and harness ledgers (`harness_ledger_vbench_agentic_*`) —
grade each reply with run_vbench_eval.grade_agentic_args and write one summary
row per arm: `vbench_arg_credit_<slug>.csv`.

Two rates, both micro-averaged, both shown side by side (excluding the
unparseable from a denominator is honest only when the exclusion is visible):
  required_fill = enum-valid required args present / required args, over
                  items with an identifiable call
  arg_precision = schema-legal supplied args / supplied args, over items
                  with >= 1 supplied arg
plus n_unparseable (no identifiable call: contributes to neither rate).

Offline and deterministic: same raw_response + same schema always gives the
same row. Never rewrites any existing artifact.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import read_csv_checked, write_csv_atomic
    from code_benchmark.run_vbench_eval import grade_agentic_args, load_vbench
    from code_benchmark.score_reading_eval import measurement_card_hash
except ImportError:
    from common import read_csv_checked, write_csv_atomic
    from run_vbench_eval import grade_agentic_args, load_vbench
    from score_reading_eval import measurement_card_hash

RESULTS_DIR = Path("all_res/ollama_result")
VBENCH_DEFAULT = Path("v_bench/public-test.jsonl")
CREDIT_COLS = ["n_items", "n_attempted", "n_required_slots", "n_required_ok",
               "required_fill_rate", "n_supplied", "n_supplied_ok",
               "arg_precision", "n_unparseable", "measurement_card_hash"]


def _direct_rows(folder: Path, slug: str) -> list[tuple[str, str]]:
    """(id, raw_response) of the agentic track from the arm's own checkpoint."""
    cands = sorted(folder.glob(f"vbench_result_*_{slug}.csv"))
    best: list[tuple[str, str]] = []
    for path in cands:
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows or "raw_response" not in rows[0]:
            continue
        if "track" in rows[0]:
            rows = [r for r in rows if r.get("track") == "agentic"]
        if len(rows) > len(best):
            best = [(str(r["id"]), r["raw_response"] or "") for r in rows]
    return best


def _ledger_rows(folder: Path, slug: str) -> list[tuple[str, str]]:
    path = folder / f"harness_ledger_vbench_agentic_{slug}.csv"
    if not path.exists():
        return []
    rows = read_csv_checked(path, required={"item_id", "raw_response"},
                            label="harness ledger")
    return [(str(r["item_id"]), r["raw_response"] or "") for r in rows]


def summarize(pairs: list[tuple[str, str]], functions: dict) -> dict:
    n_required = n_required_ok = n_supplied = n_supplied_ok = 0
    n_attempted = n_unparseable = 0
    seen: set[str] = set()
    for iid, raw in pairs:
        if iid in seen:
            raise SystemExit(f"Error: duplicate id {iid} — refusing to double-count")
        seen.add(iid)
        try:
            fid = int(iid)
        except (ValueError, TypeError):
            raise SystemExit(f"Error: id {iid!r} is not numeric — wrong join") from None
        fns = functions.get(fid)
        if not fns:
            raise SystemExit(f"Error: id {iid} has no agentic schema — wrong join")
        g = grade_agentic_args(raw, fns)
        if not g["parseable"]:
            n_unparseable += 1
            continue
        n_attempted += 1
        n_required += g["n_required"]
        n_required_ok += g["n_required_ok"]
        n_supplied += g["n_supplied"]
        n_supplied_ok += g["n_supplied_ok"]
    return {
        "n_items": len(pairs),
        "n_attempted": n_attempted,
        "n_required_slots": n_required,
        "n_required_ok": n_required_ok,
        "required_fill_rate": round(100.0 * n_required_ok / n_required, 2) if n_required else 0.0,
        "n_supplied": n_supplied,
        "n_supplied_ok": n_supplied_ok,
        "arg_precision": round(100.0 * n_supplied_ok / n_supplied, 2) if n_supplied else 0.0,
        "n_unparseable": n_unparseable,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    ap.add_argument("--vbench", type=Path, default=VBENCH_DEFAULT)
    ap.add_argument("--slugs", nargs="*", default=None,
                    help="only these arm folders (default: every folder with agentic rows)")
    args = ap.parse_args()
    functions = {r["id"]: r["function"] for r in load_vbench(args.vbench)
                 if r["track"] == "agentic"}
    card_hash = measurement_card_hash()
    folders = sorted(p for p in args.results_dir.iterdir() if p.is_dir())
    if args.slugs:
        folders = [p for p in folders if p.name in args.slugs]
    wrote = 0
    for folder in folders:
        slug = folder.name
        pairs = _ledger_rows(folder, slug) or _direct_rows(folder, slug)
        if not pairs:
            continue
        summary = summarize(pairs, functions) | {"measurement_card_hash": card_hash}
        write_csv_atomic(folder / f"vbench_arg_credit_{slug}.csv",
                         [summary], CREDIT_COLS)
        print(f"{slug}: n={summary['n_items']} attempted={summary['n_attempted']} "
              f"required_fill={summary['required_fill_rate']:.2f}% "
              f"({summary['n_required_ok']}/{summary['n_required_slots']}) "
              f"precision={summary['arg_precision']:.2f}% "
              f"({summary['n_supplied_ok']}/{summary['n_supplied']}) "
              f"unparseable={summary['n_unparseable']}")
        wrote += 1
    if not wrote:
        raise SystemExit(f"Error: no agentic per-item rows under {args.results_dir}")


if __name__ == "__main__":
    main()
