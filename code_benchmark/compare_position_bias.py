#!/usr/bin/env python3
"""Paired position-bias comparison: source-order arm A vs shuffled run (MC-35/36).

Joins two per-item files of the SAME model and the SAME frozen scorer:

  orig      full_evaluation_legal_<slug>.csv                  (MC-31 arm A)
  shuffled  full_evaluation_shuffled_s1234_<slug>.csv         (MC-35 run)

and answers: does accuracy depend on WHERE the gold answer sits?

Outputs (under the model folder):
  position_bias_compare_legal_mc_s1234.csv    one summary row (stats family of
                                              the harness compare, + blanks/flips)
  position_bias_items_legal_mc_s1234.csv      per-item audit rows (gold text
                                              per side, flips, both correctness)
  position_bias_breakdown_legal_mc_s1234.csv  long format: accuracy by gold
                                              letter + answer histograms

Fail-fast (a wrong pairing must never print a number):
  * id sets must match each other AND the pre-registered shuffle manifest;
  * each file's `gold_answer` must match the manifest's gold_old/gold_new;
  * the choice-text multiset of the two prompts must be identical per item,
    and the gold TEXT must be the same on both sides (gold follows its text —
    this is the cross-artifact check that makes the shuffle honest);
  * the recomputed original accuracy must be the pre-registered MC-31 value
    (130/146) unless overridden explicitly.

Statistics: borrowed from `run_harness_eval` — same paired-bootstrap
(seed 42) and exact-McNemar family every MC card in this repo uses.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

try:
    from code_benchmark.common import read_csv_checked, sanitize_model, write_csv_atomic
    from code_benchmark.run_harness_eval import _mcnemar_p, _paired_bootstrap
    from code_benchmark.run_mc_eval import build_prompt
    from code_benchmark.score_reading_eval import measurement_card_hash
except ImportError:  # direct run from code_benchmark/
    from common import read_csv_checked, sanitize_model, write_csv_atomic
    from run_harness_eval import _mcnemar_p, _paired_bootstrap
    from run_mc_eval import build_prompt
    from score_reading_eval import measurement_card_hash

MODEL_DEFAULT = "Qwen3.5-9B-65K"
TAG_DEFAULT = "s1234"
EXPECTED_ORIG = (130, 146)  # MC-31 arm A, legal_mc — pre-registered gate
SUMMARY_COLS = ["n", "acc_orig", "acc_shuffled", "delta", "ci95_low", "ci95_high",
                "mcnemar_p", "both", "a_only", "b_only", "neither", "flipped",
                "blanks_orig", "blanks_shuffled", "measurement_card_hash"]
ITEM_COLS = ["id", "gold_old", "gold_new", "gold_text", "answer_orig",
             "answer_shuffled", "correct_orig", "correct_shuffled", "flipped"]
BREAKDOWN_COLS = ["section", "side", "key", "n", "correct", "accuracy"]
LETTERS = "ABCDE"


def prompt_affixes() -> tuple[str, str]:
    """The frozen build_prompt's fixed wrapper, derived from a probe call —
    never re-typed. If the byte-frozen contract ever changes shape, parsing
    stored prompts fails loudly instead of mis-slicing them."""
    q = "\x00Q\x00"
    ch = "A. \x00C\x00"
    probe = build_prompt(q, [ch])
    pre, sep, rest = probe.partition(q)
    if not sep or not rest.startswith("\n\n" + ch):
        raise SystemExit("Error: frozen build_prompt no longer embeds the question "
                         "and choices verbatim — refusing to parse stored prompts")
    return pre, rest[len("\n\n") + len(ch):]


def parse_choices(prompt: str, question: str, item_id: str,
                  affixes: tuple[str, str]) -> list[str]:
    pre, suf = affixes
    if not prompt.startswith(pre) or not prompt.endswith(suf):
        raise SystemExit(f"Error: {item_id}: stored prompt does not match the frozen "
                         f"build_prompt wrapper")
    body = prompt[len(pre):len(prompt) - len(suf)] if suf else prompt[len(pre):]
    if not body.startswith(question + "\n\n"):
        raise SystemExit(f"Error: {item_id}: prompt body does not start with the "
                         f"stored question — wrong pairing?")
    lines = body[len(question) + 2:].split("\n")
    if not lines or len(lines) > len(LETTERS):
        raise SystemExit(f"Error: {item_id}: {len(lines)} choice lines outside A-E")
    choices = []
    for j, line in enumerate(lines):
        pref = f"{LETTERS[j]}. "
        if not line.startswith(pref):
            raise SystemExit(f"Error: {item_id}: choice line {j} lacks the '{pref}' "
                             f"contract — wrong pairing?")
        choices.append(line[len(pref):])
    return choices


def load_side(path: Path, label: str) -> dict[str, dict]:
    rows = read_csv_checked(path, required={"id", "question", "prompt", "answer",
                                            "gold_answer", "correct"}, label=label)
    return {str(r["id"]): r for r in rows}


def compare(orig_rows: dict[str, dict], shuff_rows: dict[str, dict],
            manifest: dict, *, expected_orig: tuple[int, int] = EXPECTED_ORIG) -> dict:
    """All integrity checks + every number the card needs. Pure (no I/O)."""
    affixes = prompt_affixes()
    man = {it["id"]: it for it in manifest["items"]}
    ids_o, ids_s, ids_m = set(orig_rows), set(shuff_rows), set(man)
    for label, ids in (("orig", ids_o), ("shuffled", ids_s)):
        if ids != ids_m:
            missing = sorted(ids_m - ids)[:3]
            extra = sorted(ids - ids_m)[:3]
            raise SystemExit(f"Error: {label} id set != manifest id set "
                             f"(missing {missing}, extra {extra})")

    n = len(ids_m)
    paired = []
    for k in sorted(ids_m):
        o, s = orig_rows[k], shuff_rows[k]
        gold_old, gold_new = man[k]["gold_old"], man[k]["gold_new"]
        if o["gold_answer"] != gold_old or s["gold_answer"] != gold_new:
            raise SystemExit(f"Error: {k}: file gold ({o['gold_answer']}/{s['gold_answer']}) "
                             f"!= manifest ({gold_old}/{gold_new})")
        if o["question"] != s["question"]:
            raise SystemExit(f"Error: {k}: question text differs between files")
        oc = parse_choices(o["prompt"], o["question"], k, affixes)
        sc = parse_choices(s["prompt"], s["question"], k, affixes)
        if len(oc) != len(sc) or Counter(oc) != Counter(sc):
            raise SystemExit(f"Error: {k}: choice-text multiset differs between the "
                             f"two prompts — the shuffle did not preserve choices")
        gold_text_o = oc[LETTERS.index(gold_old)]
        gold_text_s = sc[LETTERS.index(gold_new)]
        if gold_text_o != gold_text_s:
            raise SystemExit(f"Error: {k}: gold text moved under the gold letter "
                             f"('{gold_text_o}' vs '{gold_text_s}')")
        c_o = 1 if str(o["correct"]).strip() == "1" else 0
        c_s = 1 if str(s["correct"]).strip() == "1" else 0
        pair = {"id": k, "gold_old": gold_old, "gold_new": gold_new,
                "gold_text": gold_text_o,
                "answer_orig": str(o["answer"]).strip().upper(),
                "answer_shuffled": str(s["answer"]).strip().upper(),
                "correct_orig": c_o, "correct_shuffled": c_s,
                "flipped": int(str(o["answer"]).strip().upper()
                               != str(s["answer"]).strip().upper())}
        paired.append(pair)

    correct_o = sum(p["correct_orig"] for p in paired)
    correct_s = sum(p["correct_shuffled"] for p in paired)
    if (correct_o, n) != expected_orig:
        raise SystemExit(f"Error: recomputed orig accuracy {correct_o}/{n} != pre-registered "
                         f"{expected_orig[0]}/{expected_orig[1]} (MC-31) — wrong orig file?")

    both = sum(p["correct_orig"] and p["correct_shuffled"] for p in paired)
    a_only = sum(p["correct_orig"] and not p["correct_shuffled"] for p in paired)
    b_only = sum(not p["correct_orig"] and p["correct_shuffled"] for p in paired)
    neither = sum(not p["correct_orig"] and not p["correct_shuffled"] for p in paired)
    diffs = [p["correct_shuffled"] - p["correct_orig"] for p in paired]
    lo, hi = _paired_bootstrap(diffs)
    delta = 100.0 * (correct_s - correct_o) / n
    p_val = _mcnemar_p(a_only, b_only)

    by_gold = []
    for side, key in (("orig", "gold_old"), ("shuffled", "gold_new")):
        letters = sorted({p[key] for p in paired})
        for letter in letters:
            grp = [p for p in paired if p[key] == letter]
            c = (sum(x["correct_orig"] for x in grp) if side == "orig"
                 else sum(x["correct_shuffled"] for x in grp))
            by_gold.append({"section": "by_gold_letter", "side": side, "key": letter,
                            "n": len(grp), "correct": c,
                            "accuracy": f"{100.0 * c / len(grp):.2f}"})

    hist = []
    for side, key in (("orig", "answer_orig"), ("shuffled", "answer_shuffled")):
        counts = Counter(p[key] if p[key] in LETTERS else "blank" for p in paired)
        for letter in list(LETTERS) + ["blank"]:
            hist.append({"section": "answer_letter", "side": side, "key": letter,
                         "n": counts.get(letter, 0), "correct": "", "accuracy": ""})

    return {
        "summary": {
            "n": n,
            "acc_orig": f"{100.0 * correct_o / n:.2f}",
            "acc_shuffled": f"{100.0 * correct_s / n:.2f}",
            "delta": f"{delta:+.2f}",
            "ci95_low": f"{lo:.2f}", "ci95_high": f"{hi:.2f}",
            "mcnemar_p": f"{p_val:.4g}",
            "both": both, "a_only": a_only, "b_only": b_only, "neither": neither,
            "flipped": sum(p["flipped"] for p in paired),
            "blanks_orig": sum(1 for p in paired if p["answer_orig"] not in LETTERS),
            "blanks_shuffled": sum(1 for p in paired if p["answer_shuffled"] not in LETTERS),
        },
        "paired": paired,
        "breakdown": by_gold + hist,
        "correct_orig": correct_o, "correct_shuffled": correct_s,
        "expected_orig": expected_orig,
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=MODEL_DEFAULT,
                    help="model tag (default: %(default)s — MC-35 condition)")
    ap.add_argument("--tag", default=TAG_DEFAULT, help="shuffle tag (default: %(default)s)")
    ap.add_argument("--orig-file", type=Path, default=None,
                    help="arm-A per-item CSV (default: full_evaluation_legal_<slug>.csv)")
    ap.add_argument("--shuffled-file", type=Path, default=None,
                    help="shuffled per-item CSV (default: full_evaluation_shuffled_<tag>_<slug>.csv)")
    ap.add_argument("--manifest", type=Path,
                    default=Path("data/legal_slm_multichoice_shuffled_s1234_manifest.json"),
                    help="pre-registered shuffle manifest (default: %(default)s)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="output directory (default: the model result folder)")
    ap.add_argument("--expected-orig-correct", type=int, default=EXPECTED_ORIG[0],
                    help="pre-registered orig correct count gate (default: %(default)s)")
    ap.add_argument("--expected-orig-n", type=int, default=EXPECTED_ORIG[1],
                    help="pre-registered orig n gate (default: %(default)s)")
    return ap.parse_args()


def main() -> None:
    import json

    args = parse_args()
    slug = sanitize_model(args.model)
    folder = Path("all_res/ollama_result") / slug
    orig_path = args.orig_file or folder / f"full_evaluation_legal_{slug}.csv"
    shuff_path = args.shuffled_file or folder / f"full_evaluation_shuffled_{args.tag}_{slug}.csv"
    out_dir = args.out_dir or folder
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    res = compare(load_side(orig_path, "orig"), load_side(shuff_path, "shuffled"), manifest,
                  expected_orig=(args.expected_orig_correct, args.expected_orig_n))

    stem = f"position_bias_legal_mc_{args.tag}"
    summary = dict(res["summary"], measurement_card_hash=measurement_card_hash())
    write_csv_atomic(out_dir / f"{stem}_compare.csv", [summary], SUMMARY_COLS)
    write_csv_atomic(out_dir / f"{stem}_items.csv", res["paired"], ITEM_COLS)
    write_csv_atomic(out_dir / f"{stem}_breakdown.csv", res["breakdown"], BREAKDOWN_COLS)

    s = res["summary"]
    print(f"n={s['n']}  orig {res['correct_orig']}/{s['n']} = {s['acc_orig']}%  "
          f"shuffled {res['correct_shuffled']}/{s['n']} = {s['acc_shuffled']}%")
    print(f"delta {s['delta']}  CI95 [{s['ci95_low']}, {s['ci95_high']}]  "
          f"McNemar p={s['mcnemar_p']}")
    print(f"2x2: both {s['both']} · orig-only {s['a_only']} · shuffled-only {s['b_only']} · "
          f"neither {s['neither']}")
    print(f"flipped {s['flipped']}/{s['n']} · blanks orig {s['blanks_orig']} / "
          f"shuffled {s['blanks_shuffled']}")
    print("accuracy by gold letter:")
    for row in res["breakdown"]:
        if row["section"] == "by_gold_letter":
            print(f"  {row['side']:<8} {row['key']}: {row['correct']}/{row['n']} = {row['accuracy']}%")
    print(f"-> {out_dir / f'{stem}_compare.csv'}\n-> {out_dir / f'{stem}_items.csv'}"
          f"\n-> {out_dir / f'{stem}_breakdown.csv'}")


if __name__ == "__main__":
    main()
