#!/usr/bin/env python3
"""Adapter: VM14K public release -> frozen MC-runner input + pre-register manifest.

Source (HF `venera-ai/VietnameseMedBench`, downloaded 2026-09-21, hashes pinned in
`v_med_vm14k/README.md`) ships
`{id, question, options[], option_map[], answer, answer_index, difficulty_level, medical_topic[]}`.
The frozen runner (`run_mc_eval.py`) wants `{id, question, choices[], answer}` with
`A. `-prefixed choices and a letter gold — the same shape the VLSP2025-LegalSLM adapter
produced. The runner is NOT touched.

Pre-registration: the manifest pins the source sha256 + seed BEFORE any inference.
Commit `data/vm14k_manifest.json` first, then run:

    .venv/bin/python code_benchmark/run_mc_eval.py \
        --folder v_med_vm14k --file vm14k_input.jsonl --workers 4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

SEED = 42
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

try:
    from code_benchmark.vm14k_taxonomy import category_of, primary_topic
except ImportError:
    from vm14k_taxonomy import category_of, primary_topic

# Pinned by v_med_vm14k/README.md (downloaded 2026-09-21). Drift = wrong file.
SHA256 = {
    "data-processed-shuffled0.jsonl": "688218341055536f032806beb7f3b6d552d5429eebe4620a581e9c861e05aef4",
    "data-processed-shuffled1.jsonl": "ad031b1cff18b0b6a635449806def2d12bdb8de3e2c72f9aa26587c6c04dd551",
    "data-processed-shuffled2.jsonl": "c3e8e71776f32ba07152607b767bfb2915a189782e0fde7d5a4183a6434098ba",
}
SOURCE_URL = (
    "https://huggingface.co/datasets/venera-ai/VietnameseMedBench/resolve/main/tests/{name}"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Error: {path}:{lineno}: invalid JSON ({exc})") from exc
    if not rows:
        raise SystemExit(f"Error: {path} has no rows")
    return rows


def build(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Map source rows onto (runner input rows, manifest items). Fail-fast on drift."""
    input_rows: list[dict] = []
    items: list[dict] = []
    seen: set[str] = set()
    empty_question = 0
    placeholder_rows = 0

    for i, r in enumerate(rows, 1):
        rid = str(r.get("id", "")).strip()
        if not rid:
            raise SystemExit(f"Error: row {i}: empty id")
        if rid in seen:
            raise SystemExit(f"Error: row {i}: duplicate id {rid!r}")
        seen.add(rid)

        options = r.get("options")
        if not isinstance(options, list) or not options:
            raise SystemExit(f"Error: row {i} ({rid}): missing/empty options")
        n = len(options)
        if n > len(LETTERS):
            raise SystemExit(f"Error: row {i} ({rid}): {n} options > {len(LETTERS)}")

        option_map = r.get("option_map")
        if not isinstance(option_map, list) or sorted(option_map) != list(range(n)):
            raise SystemExit(f"Error: row {i} ({rid}): option_map is not a permutation of 0..{n - 1}")

        answer = str(r.get("answer", "")).strip().upper()
        answer_index = r.get("answer_index")
        if not isinstance(answer_index, int) or not (0 <= answer_index < n):
            raise SystemExit(f"Error: row {i} ({rid}): bad answer_index {answer_index!r}")
        if answer != LETTERS[answer_index]:
            raise SystemExit(
                f"Error: row {i} ({rid}): answer {answer!r} != LETTERS[{answer_index}] "
                f"({LETTERS[answer_index]!r})"
            )

        question = str(r.get("question", "")).strip()
        if not question:
            empty_question += 1
        if any(str(o).strip().lower().startswith("option") for o in options):
            placeholder_rows += 1

        choices = [f"{LETTERS[j]}. {str(o).strip()}" for j, o in enumerate(options)]
        input_rows.append({"id": rid, "question": question, "choices": choices, "answer": answer})
        topics = r.get("medical_topic")
        items.append({
            "id": rid,
            "gold": answer,
            "n_choices": n,
            "difficulty_level": r.get("difficulty_level", ""),
            "primary_topic": primary_topic(topics),
            "category": category_of(topics),
        })

    if empty_question or placeholder_rows:
        print(
            f"  warning: source quirks kept as-is — {empty_question} row(s) with empty question, "
            f"{placeholder_rows} row(s) with placeholder option text",
            file=sys.stderr,
        )
    return input_rows, items


def write_jsonl_atomic(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="v_med_vm14k/data-processed-shuffled0.jsonl",
                        help="VM14K source JSONL (default: shuffled0)")
    parser.add_argument("--input-out", default="v_med_vm14k/vm14k_input.jsonl",
                        help="frozen-runner input JSONL to write")
    parser.add_argument("--manifest-out", default="data/vm14k_manifest.json",
                        help="pre-register manifest to write (commit before inference)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"Error: source not found: {source}")
    if source.name not in SHA256:
        raise SystemExit(
            f"Error: {source.name!r} is not a pinned VM14K artifact "
            f"(pinned: {', '.join(sorted(SHA256))})"
        )

    digest = sha256_file(source)
    expected = SHA256[source.name]
    if digest != expected:
        raise SystemExit(
            f"Error: sha256 mismatch for {source}\n  expected {expected}\n  got      {digest}"
        )

    rows = load_rows(source)
    input_rows, items = build(rows)

    manifest = {
        "benchmark": "VM14K (Vietnamese medical MCQ, public release)",
        "split": "public",
        "variant": source.stem.replace("data-processed-", ""),
        "n": len(items),
        "seed": SEED,
        "source_file": str(source),
        "source_sha256": digest,
        "source_url": SOURCE_URL.format(name=source.name),
        "items": items,
    }

    write_jsonl_atomic(Path(args.input_out), input_rows)
    write_json_atomic(Path(args.manifest_out), manifest)

    gold = Counter(it["gold"] for it in items)
    n_choices = Counter(it["n_choices"] for it in items)
    top_letter, top_n = gold.most_common(1)[0]
    print(f"source    {source}  sha256 OK")
    print(f"rows      {len(items)}  (unique ids)")
    print(f"choices   {dict(sorted(n_choices.items()))}")
    print(f"gold      {dict(sorted(gold.items()))}  majority {top_letter} {top_n}/{len(items)}"
          f" = {100.0 * top_n / len(items):.2f}%")
    print(f"input     {args.input_out}")
    print(f"manifest  {args.manifest_out}  (commit BEFORE inference)")


if __name__ == "__main__":
    main()
