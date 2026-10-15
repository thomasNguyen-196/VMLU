#!/usr/bin/env python3
"""Adapter: legal_mc source order -> deterministic shuffled MC-runner input.

Source (`v_legal_slsp/legal_slm/multichoice.jsonl`, sha pinned in
`data/legal_slm_multichoice_manifest.json`) carries `{question, choices[]
(raw texts, NO letters), answer (0-based index), answer_choice_letter}`.
The frozen runner (`run_mc_eval.py`) wants `{id, question, choices[],
answer}` with `A. `-prefixed choices and a letter gold — the same shape the
arm-A adapter (`load_legal_mc`) produces, except the choice order is
permuted. The runner is NOT touched.

Pre-registration: `SHUFFLE_SEED` is fixed below and the shuffle manifest pins
the source sha256 + shuffled-input sha256 BEFORE any inference. Commit the
manifest first, then run the wrapper (`run_shuffled_mc.py`).

Shuffle rule (order-independent, resume-safe): the permutation of each item
comes from `random.Random(f"{SHUFFLE_SEED}:{item_id}")`, so it never depends
on input row order. Gold is remapped by TEXT identity (the gold text keeps
its gold status wherever it lands); an item with duplicate choice texts
aborts instead of guessing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

SHUFFLE_SEED = 1234
DATA_SEED = 42
LETTERS = "ABCDE"  # the frozen prompt contract is A-E (mirrors load_legal_mc)
ORIG_MANIFEST_DEFAULT = "data/legal_slm_multichoice_manifest.json"


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


def item_rng(shuffle_seed: int, item_id: str) -> random.Random:
    """Per-item deterministic RNG — independent of input row order."""
    return random.Random(f"{shuffle_seed}:{item_id}")


def shuffle_choices(
    texts: list[str], gold_idx: int, rng: random.Random, item_id: str
) -> tuple[list[str], int, list[int]]:
    """Permute choice texts; return (shuffled, new gold idx, perm).

    `perm[new_position] = old_position`. Gold follows its text. Duplicate
    texts make the remap ambiguous -> hard fail (spec: never guess).
    """
    n = len(texts)
    if len(set(texts)) != n:
        raise SystemExit(f"Error: {item_id}: duplicate choice texts — remap ambiguous")
    if not isinstance(gold_idx, int) or not (0 <= gold_idx < n):
        raise SystemExit(f"Error: {item_id}: bad gold index {gold_idx!r} for {n} choices")
    perm = list(range(n))
    rng.shuffle(perm)
    shuffled = [texts[p] for p in perm]
    new_gold = perm.index(gold_idx)
    return shuffled, new_gold, perm


def build(
    rows: list[dict], gold_by_id: dict[str, str], shuffle_seed: int
) -> tuple[list[dict], list[dict]]:
    """Map source rows onto (shuffled runner input rows, manifest items).

    Fail-fast on: row-count/gold mismatch with the orig manifest, source
    answer fields disagreeing with each other or with the manifest gold,
    choice counts outside the A-E contract, duplicate choice texts.
    """
    input_rows: list[dict] = []
    items: list[dict] = []

    for i, r in enumerate(rows, 1):
        item_id = f"LG-{i:04d}"
        texts = r.get("choices")
        if not isinstance(texts, list) or len(texts) < 2:
            raise SystemExit(f"Error: {item_id}: missing/empty choices")
        n = len(texts)
        if n > len(LETTERS):
            raise SystemExit(f"Error: {item_id}: {n} choices exceeds A-E contract")

        gold_old = gold_by_id.get(item_id)
        if not gold_old:
            raise SystemExit(f"Error: no orig-manifest gold for {item_id}")

        # Cross-check the source's own answer fields against each other and
        # against the orig manifest: three witnesses, no silent drift.
        answer_idx = r.get("answer")
        answer_letter = str(r.get("answer_choice_letter", "")).strip().upper()
        if not isinstance(answer_idx, int) or not (0 <= answer_idx < n):
            raise SystemExit(f"Error: {item_id}: bad source answer index {answer_idx!r}")
        if not answer_letter or LETTERS.find(answer_letter) != answer_idx:
            raise SystemExit(
                f"Error: {item_id}: source answer {answer_idx!r} disagrees with "
                f"answer_choice_letter {answer_letter!r}"
            )
        if answer_letter != gold_old:
            raise SystemExit(
                f"Error: {item_id}: source letter {answer_letter!r} != "
                f"orig-manifest gold {gold_old!r}"
            )

        question = r.get("question")
        if not isinstance(question, str) or not question:
            raise SystemExit(f"Error: {item_id}: missing question")

        rng = item_rng(shuffle_seed, item_id)
        shuffled, new_gold_idx, perm = shuffle_choices(list(texts), answer_idx, rng, item_id)
        lettered = [f"{LETTERS[j]}. {t}" for j, t in enumerate(shuffled)]
        gold_new = LETTERS[new_gold_idx]

        input_rows.append(
            {"id": item_id, "question": question, "choices": lettered, "answer": gold_new}
        )
        items.append({"id": item_id, "gold_new": gold_new, "gold_old": gold_old, "perm": perm})

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
    parser.add_argument("--manifest", default=ORIG_MANIFEST_DEFAULT,
                        help="orig legal_mc manifest (source path + sha + golds)")
    parser.add_argument("--input-out",
                        default="data/legal_slm_multichoice_shuffled_s1234_input.jsonl",
                        help="shuffled frozen-runner input JSONL to write")
    parser.add_argument("--shuffle-manifest-out",
                        default="data/legal_slm_multichoice_shuffled_s1234_manifest.json",
                        help="pre-register shuffle manifest to write (commit before inference)")
    parser.add_argument("--seed", type=int, default=SHUFFLE_SEED,
                        help="shuffle seed (default: %(default)s; changing it is a new condition)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.seed != SHUFFLE_SEED:
        print(f"  note: --seed {args.seed} != pre-registered SHUFFLE_SEED {SHUFFLE_SEED} "
              f"— output is a DIFFERENT condition; do not label it s1234", file=sys.stderr)
    man_path = Path(args.manifest)
    if not man_path.exists():
        raise SystemExit(f"Error: orig manifest not found: {man_path}")
    man = json.loads(man_path.read_text(encoding="utf-8"))

    source = Path(man["source_file"])
    if not source.exists():
        raise SystemExit(f"Error: source not found: {source}")
    digest = sha256_file(source)
    if digest != man["source_sha256"]:
        raise SystemExit(
            f"Error: sha256 mismatch for {source}\n  expected {man['source_sha256']}\n"
            f"  got      {digest}"
        )
    rows = load_rows(source)
    if len(rows) != man["n"]:
        raise SystemExit(f"Error: source has {len(rows)} rows, manifest says {man['n']}")

    gold_by_id = {it["id"]: it["gold"] for it in man["items"]}
    input_rows, items = build(rows, gold_by_id, args.seed)

    input_out = Path(args.input_out)
    write_jsonl_atomic(input_out, input_rows)
    input_sha = sha256_file(input_out)

    manifest = {
        "benchmark": man.get("benchmark", ""),
        "split": man.get("split", ""),
        "variant": f"shuffled-s{args.seed}",
        "n": len(items),
        "seed": man.get("seed", DATA_SEED),
        "shuffle_seed": args.seed,
        "source_file": str(source),
        "source_sha256": digest,
        "input_file": str(input_out),
        "input_sha256": input_sha,
        "items": items,
    }
    write_json_atomic(Path(args.shuffle_manifest_out), manifest)

    old = Counter(it["gold_old"] for it in items)
    new = Counter(it["gold_new"] for it in items)
    top_old, top_old_n = old.most_common(1)[0]
    top_new, top_new_n = new.most_common(1)[0]
    print(f"source    {source}  sha256 OK ({len(rows)} rows)")
    print(f"gold_old  {dict(sorted(old.items()))}  majority {top_old} "
          f"{top_old_n}/{len(items)} = {100.0 * top_old_n / len(items):.2f}%")
    print(f"gold_new  {dict(sorted(new.items()))}  majority {top_new} "
          f"{top_new_n}/{len(items)} = {100.0 * top_new_n / len(items):.2f}%")
    print(f"input     {input_out}")
    print(f"manifest  {args.shuffle_manifest_out}  (commit BEFORE inference)")


if __name__ == "__main__":
    main()
