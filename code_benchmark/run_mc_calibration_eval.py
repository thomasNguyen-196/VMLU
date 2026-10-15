#!/usr/bin/env python3
"""MC calibration runner (metrics group 3.1, cards MC-41/MC-42).

The IEC gateway returns `logprobs` (probed 2026-10-04), so the frozen MC
condition can be re-run with the answer-token distribution captured. The
frozen prompt/parser (`build_prompt`/`extract_answer`) are reused untouched;
the ONLY difference from the MC-31 arm-A condition is `logprobs=true` +
`top_logprobs=20` on the request — a read-only option, so generation should not
move (and the report checks the accuracy against the stored baseline).

Subcommands (repo root):

    .venv/bin/python code_benchmark/run_mc_calibration_eval.py run   --dataset legal_mc
    .venv/bin/python code_benchmark/run_mc_calibration_eval.py report --dataset legal_mc

Outputs under all_res/ollama_result/<model>/:

    mc_calibration_items_<dataset>_<label>.csv       per item: p_A..p_E, conf
    mc_calibration_summary_<dataset>_<label>.csv     accuracy/ECE/Brier/over-conf
    mc_calibration_reliability_<dataset>_<label>.csv reliability bins
"""

from __future__ import annotations

import argparse
import json
import math
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import (sanitize_model, resolve_endpoint, model_dirs,
                                       write_csv_atomic, read_csv_checked, setup_logging,
                                       add_endpoint_args)
    from code_benchmark.llm import build_client, verify_credentials, call_logprobs_with_retry
    from code_benchmark.run_mc_eval import (extract_answer, build_prompt,
                                            detect_scorable, subject_category)
    from code_benchmark.run_harness_eval import load_legal_mc, load_legal_nli
    from code_benchmark.run_legal_arm_a import DEFAULT_PARITY_SLUG
    from code_benchmark.score_reading_eval import measurement_card_hash
except ImportError:  # direct run from code_benchmark/
    from common import (sanitize_model, resolve_endpoint, model_dirs,
                        write_csv_atomic, read_csv_checked, setup_logging,
                        add_endpoint_args)
    from llm import build_client, verify_credentials, call_logprobs_with_retry
    from run_mc_eval import (extract_answer, build_prompt,
                             detect_scorable, subject_category)
    from run_harness_eval import load_legal_mc, load_legal_nli
    from run_legal_arm_a import DEFAULT_PARITY_SLUG
    from score_reading_eval import measurement_card_hash

load_dotenv()

LETTERS = "ABCDE"
TOP_LOGPROBS = 20          # all offered letters fit comfortably; the rest is a safety margin
MQA_ALL_GOLD = Path("vmlu_mqa_v1.5/all_gold.jsonl")
DATASETS = ("legal_mc", "legal_nli", "vmlu_mqa_all_gold")
ITEM_COLS = ["id", "gold", "answer", "correct", "first_token", "n_choices",
             "n_letters_found", "off_options_mass", "p_A", "p_B", "p_C", "p_D",
             "p_E", "confidence"]
SUMMARY_COLS = ["dataset", "n", "n_usable", "accuracy", "mean_confidence", "ece",
                "brier_confidence", "brier_multiclass", "overconfidence", "card_hash"]
RELIABILITY_COLS = ["dataset", "bin_lo", "bin_hi", "n", "mean_confidence", "accuracy"]
BREAKDOWN_COLS = ["dataset", "level", "name", "n", "n_usable", "accuracy",
                  "mean_confidence", "ece", "overconfidence"]
CKPT_EVERY = 100

_OPTION_RE = re.compile(r"^([A-E])\.\s")


def offered_letters(prompt: str) -> str:
    """The option letters THIS prompt actually offers, e.g. "ABCD" for a 4-choice row.

    Anchored at the end of the option block (`Đáp án: ` split, then walk the lines
    backwards) and read off the `A. ` prefixes the frozen `build_prompt` contract
    requires — so the letter set cannot drift from what the model actually saw, and
    it works for the legal sets (whose choices carry no letters in the source) and
    for VMLU (whose choices already do) with one rule. A gap or an out-of-order
    letter fails fast: a malformed option block would otherwise silently become a
    wrong letter set.
    """
    head = prompt.rsplit("\nĐáp án: ", 1)[0]
    reversed_letters = ""
    for line in reversed(head.splitlines()):
        m = _OPTION_RE.match(line)
        if m is None:
            if reversed_letters:
                break            # the option block ended
            continue             # still inside the question text
        reversed_letters += m.group(1)
    letters = reversed_letters[::-1]
    if not letters or LETTERS[: len(letters)] != letters:
        raise SystemExit(f"Error: prompt option block is not an A.. prefix "
                         f"(got {letters!r})")
    return letters


def load_mqa_all_gold(path: Path = MQA_ALL_GOLD) -> list[dict]:
    """VMLU MCQA with gold (1047 rows, 58 subjects) — frozen `build_prompt` +
    `detect_scorable`, no adapter: this file's choices already carry their letters,
    which is exactly the `A. B. C.` contract the frozen prompt needs.

    Fail-fast on a missing file, a duplicate id, a choice count outside the A–E
    contract, and — via the frozen all-or-none gate — a partial-gold file, which
    must never be scored as if it were complete.
    """
    if not path.exists():
        raise SystemExit(f"Error: {path} not found (gitignored dataset; unpack "
                         f"vmlu_datasets.zip or re-download)")
    records = []
    seen: set[str] = set()
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"Error: {path}:{lineno}: bad JSON: {e}") from e
        rid = str(rec.get("id", "")).strip()
        if not rid:
            raise SystemExit(f"Error: {path}:{lineno}: empty id")
        if rid in seen:
            raise SystemExit(f"Error: {path}:{lineno}: duplicate id {rid!r}")
        seen.add(rid)
        choices = rec.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise SystemExit(f"Error: {rid}: missing/empty choices")
        if len(choices) > len(LETTERS):
            raise SystemExit(f"Error: {rid}: {len(choices)} choices exceeds A-E contract")
        records.append(rec)
    scorable, gold_by_id = detect_scorable(records)
    if not scorable:
        raise SystemExit(f"Error: {path} is not all-gold — the frozen scorer is "
                         f"all-or-none, so no score may be computed from it")
    return [{"dataset": "vmlu_mqa_all_gold", "item_id": str(r["id"]),
             "question": str(r.get("question", "")),
             "prompt": build_prompt(str(r["question"]), r["choices"]),
             "gold": gold_by_id[str(r["id"])],
             "n_choices": len(r["choices"])}
            for r in records]


def load_dataset(dataset: str) -> list[dict]:
    """Every dataset reaches the frozen prompt with its own letter set derived from
    that prompt (see `offered_letters`), so the calibration rule is one rule."""
    if dataset == "legal_mc":
        return load_legal_mc(DEFAULT_PARITY_SLUG)
    if dataset == "legal_nli":
        return load_legal_nli(DEFAULT_PARITY_SLUG)
    if dataset == "vmlu_mqa_all_gold":
        return load_mqa_all_gold()
    raise SystemExit(f"Error: --dataset must be one of {list(DATASETS)}")


def letter_probs(top_logprobs: list[dict], offered: str) -> tuple[dict[str, float], float]:
    """(P(offered), off_options_mass) from the first token's top logprobs.

    Renormalized over the letters the row OFFERS, never over a fixed A–E: the
    option block is often 4-wide, and the model still puts mass on the absent E
    (legal_mc: mean 1.3%, max 9.4%). An un-offered letter is not a candidate, so
    it is dropped from the distribution and its share is reported separately as
    `off_options_mass` — measured against the visible (top-N) mass, which is all
    the endpoint returns. Absent offered letters score 0; nothing is invented.
    """
    raw = {t["token"]: math.exp(t["logprob"]) for t in top_logprobs
           if t.get("token") in offered}
    total = sum(raw.values())
    visible = sum(math.exp(t["logprob"]) for t in top_logprobs)
    off = max(0.0, 1.0 - total / visible) if visible > 0 else 0.0
    if total <= 0:
        return {c: 0.0 for c in offered}, off
    return {c: raw.get(c, 0.0) / total for c in offered}, off


def ece_and_reliability(confs: list[float], corrects: list[int], bins: int = 10):
    """(ece, rows). Bin index = min(int(conf*bins), bins-1); ECE = Σ n_b/N·|acc_b−conf_b|."""
    n = len(confs)
    rows = []
    ece = 0.0
    for b in range(bins):
        idx = [i for i, c in enumerate(confs) if min(int(c * bins), bins - 1) == b]
        if not idx:
            rows.append({"bin_lo": f"{b / bins:.1f}", "bin_hi": f"{(b + 1) / bins:.1f}",
                         "n": 0, "mean_confidence": "", "accuracy": ""})
            continue
        mc = sum(confs[i] for i in idx) / len(idx)
        ac = sum(corrects[i] for i in idx) / len(idx)
        ece += len(idx) / n * abs(ac - mc)
        rows.append({"bin_lo": f"{b / bins:.1f}", "bin_hi": f"{(b + 1) / bins:.1f}",
                     "n": len(idx), "mean_confidence": f"{mc:.4f}", "accuracy": f"{ac:.4f}"})
    return ece, rows


def build_report(items: list[dict], dataset: str, card_hash: str, *, bins: int = 10):
    usable = [r for r in items if int(r["n_letters_found"]) >= 2 and r["confidence"] != ""]
    confs = [float(r["confidence"]) for r in usable]
    corrects = [int(r["correct"]) for r in usable]
    n = len(items)
    nu = len(usable)
    accuracy = sum(int(r["correct"]) for r in items) / n if n else float("nan")
    mean_conf = sum(confs) / nu if nu else float("nan")
    ece, rows = ece_and_reliability(confs, corrects, bins=bins)
    brier_conf = sum((c - y) ** 2 for c, y in zip(confs, corrects, strict=True)) / nu if nu else float("nan")
    brier_mc = 0.0
    for r in usable:
        y = r["gold"]
        offered = LETTERS[: int(r["n_choices"])]
        brier_mc += sum((float(r[f"p_{c}"]) - (1.0 if c == y else 0.0)) ** 2 for c in offered)
    brier_mc = brier_mc / nu if nu else float("nan")
    summary = {"dataset": dataset, "n": n, "n_usable": nu,
               "accuracy": f"{accuracy * 100:.2f}",
               "mean_confidence": f"{mean_conf * 100:.2f}" if nu else "",
               "ece": f"{ece * 100:.2f}" if nu else "",
               "brier_confidence": f"{brier_conf:.4f}" if nu else "",
               "brier_multiclass": f"{brier_mc:.4f}" if nu else "",
               "overconfidence": f"{(mean_conf - accuracy) * 100:+.2f}" if nu else "",
               "card_hash": card_hash}
    return summary, rows


def build_breakdown(items: list[dict], dataset: str, *, bins: int = 10) -> list[dict]:
    """Accuracy / mean confidence / ECE per overall, per category, per subject.

    The subject key is the frozen `subject_category` (id prefix `XX-YYYY` → the
    official SUBJECTS map), so a row here and a row in the MC finals' accuracy
    table mean the same thing. Datasets whose ids are not `XX-YYYY` (legal_mc's
    `LG-0001`) land in an explicit `unknown` bucket instead of being dropped.
    """
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in items:
        num, name, cat = subject_category(r["id"])
        buckets[("overall", "overall")].append(r)
        buckets[("category", cat)].append(r)
        buckets[("subject", f"{num:02d} {name}" if num else "unknown")].append(r)
    rows = []
    for (level, name), group in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        usable = [r for r in group
                  if int(r["n_letters_found"]) >= 2 and r["confidence"] != ""]
        n, nu = len(group), len(usable)
        accuracy = sum(int(r["correct"]) for r in group) / n
        confs = [float(r["confidence"]) for r in usable]
        corrects = [int(r["correct"]) for r in usable]
        mean_conf = sum(confs) / nu if nu else float("nan")
        ece, _ = ece_and_reliability(confs, corrects, bins=bins) if nu else (float("nan"), [])
        rows.append({"dataset": dataset, "level": level, "name": name, "n": n,
                     "n_usable": nu, "accuracy": f"{accuracy * 100:.2f}",
                     "mean_confidence": f"{mean_conf * 100:.2f}" if nu else "",
                     "ece": f"{ece * 100:.2f}" if nu else "",
                     "overconfidence": f"{(mean_conf - accuracy) * 100:+.2f}" if nu else ""})
    return rows


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="capture the letter distribution on a gold MC set")
    run.add_argument("--dataset", default="legal_mc", choices=list(DATASETS))
    run.add_argument("--label", default=None, help="default: <sanitized-model>-cal")
    add_endpoint_args(run, max_tokens_default=4, max_tokens_help="MC letter budget (default: 4)",
                      resume_help="resume from an existing mc_calibration_items_<dataset>_<label>.csv")
    rep = sub.add_parser("report", help="ECE/Brier/reliability from the captured items")
    rep.add_argument("--dataset", default="legal_mc")
    rep.add_argument("--label", required=True)
    rep.add_argument("--model", required=True)
    rep.add_argument("--bins", type=int, default=10)
    return ap.parse_args()


def cmd_run(args: argparse.Namespace) -> None:
    base_url, api_key, model = resolve_endpoint(args)
    label = args.label or f"{sanitize_model(model)}-cal"
    folder, _, logs = model_dirs(model)
    setup_logging(logs / f"mc_calibration_{sanitize_model(label)}.log")
    out_path = folder / f"mc_calibration_items_{args.dataset}_{label}.csv"

    items = load_dataset(args.dataset)
    done: dict[str, dict] = {}
    if args.resume:
        if out_path.exists():
            done = {str(r["id"]): r for r in read_csv_checked(out_path, exact=ITEM_COLS,
                                                             label="calibration items")}
            print(f"[cal] resume: {len(done)} items already captured")
        else:
            print("[cal] --resume with no checkpoint yet; starting fresh")
    todo = [it for it in items if it["item_id"] not in done]
    print(f"[cal] {args.dataset} n={len(items)} todo={len(todo)} model={model} "
          f"label={label} workers={args.workers}")

    client = build_client(base_url, api_key)
    verify_credentials(client, model)

    lock = threading.Lock()
    rows: list[dict] = [dict(r) for r in done.values()]

    def one(it: dict) -> dict:
        offered = offered_letters(it["prompt"])
        content, first_token, top = call_logprobs_with_retry(
            client, model, it["prompt"], args.temperature, args.seed,
            args.max_tokens, TOP_LOGPROBS)
        answer = extract_answer(content)
        probs, off = letter_probs(top, offered)
        found = sum(1 for c in offered if probs[c] > 0)
        return {"id": it["item_id"], "gold": it["gold"], "answer": answer,
                "correct": int(bool(answer) and answer == it["gold"]),
                "first_token": first_token, "n_choices": len(offered),
                "n_letters_found": found, "off_options_mass": f"{off:.6f}",
                **{f"p_{c}": f"{probs.get(c, 0.0):.6f}" for c in LETTERS},
                "confidence": (f"{probs[answer]:.6f}"
                               if (answer in probs and found >= 2) else "")}

    def flush() -> None:
        ordered = {str(r["id"]): r for r in rows}
        write_csv_atomic(out_path, [ordered[str(it["item_id"])] for it in items
                                    if str(it["item_id"]) in ordered], ITEM_COLS)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, row in enumerate(pool.map(one, todo), 1):
            with lock:
                rows.append(row)
                if i % CKPT_EVERY == 0:
                    flush()
                    print(f"[cal] checkpoint {i}/{len(todo)}", flush=True)
    flush()

    ordered = {str(r["id"]): r for r in rows}
    final = [ordered[str(it["item_id"])] for it in items if str(it["item_id"]) in ordered]
    acc = sum(int(r["correct"]) for r in final)
    print(f"[cal] wrote {len(final)} items | accuracy {acc}/{len(final)} = "
          f"{acc / len(final) * 100:.2f}%")
    print(f"-> {out_path}")


def cmd_report(args: argparse.Namespace) -> None:
    folder = model_dirs(args.model)[0]
    items = read_csv_checked(folder / f"mc_calibration_items_{args.dataset}_{args.label}.csv",
                             exact=ITEM_COLS, label="calibration items")
    summary, rows = build_report(items, args.dataset, measurement_card_hash(), bins=args.bins)
    breakdown = build_breakdown(items, args.dataset, bins=args.bins)
    write_csv_atomic(folder / f"mc_calibration_summary_{args.dataset}_{args.label}.csv",
                     [summary], SUMMARY_COLS)
    write_csv_atomic(folder / f"mc_calibration_reliability_{args.dataset}_{args.label}.csv",
                     rows, RELIABILITY_COLS)
    write_csv_atomic(folder / f"mc_calibration_breakdown_{args.dataset}_{args.label}.csv",
                     breakdown, BREAKDOWN_COLS)
    off = sum(float(r["off_options_mass"]) for r in items) / len(items)
    print(f"n={summary['n']} usable={summary['n_usable']} accuracy={summary['accuracy']}% "
          f"mean_conf={summary['mean_confidence']}% ECE={summary['ece']} "
          f"Brier(conf)={summary['brier_confidence']} over={summary['overconfidence']} "
          f"mean_off_options_mass={off:.4f}")
    for r in rows:
        if r["n"]:
            print(f"  [{r['bin_lo']},{r['bin_hi']}) n={r['n']} conf={r['mean_confidence']} acc={r['accuracy']}")
    print("-- by category --")
    for r in breakdown:
        if r["level"] == "category":
            print(f"  {r['name']:<15} n={r['n']:<5} acc={r['accuracy']:<6} "
                  f"conf={r['mean_confidence'] or '-':<7} ECE={r['ece'] or '-':<6} over={r['overconfidence'] or '-'}")


def main() -> None:
    args = parse_args()
    (cmd_run if args.cmd == "run" else cmd_report)(args)


if __name__ == "__main__":
    main()
