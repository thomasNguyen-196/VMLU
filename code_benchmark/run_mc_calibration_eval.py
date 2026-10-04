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
import math

from dotenv import load_dotenv

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import (sanitize_model, resolve_endpoint, model_dirs,
                                       write_csv_atomic, read_csv_checked, setup_logging,
                                       add_endpoint_args)
    from code_benchmark.llm import build_client, verify_credentials
    from code_benchmark.run_mc_eval import extract_answer
    from code_benchmark.run_harness_eval import load_legal_mc, load_legal_nli
    from code_benchmark.run_legal_arm_a import DEFAULT_PARITY_SLUG
    from code_benchmark.score_reading_eval import measurement_card_hash
except ImportError:  # direct run from code_benchmark/
    from common import (sanitize_model, resolve_endpoint, model_dirs,
                        write_csv_atomic, read_csv_checked, setup_logging,
                        add_endpoint_args)
    from llm import build_client, verify_credentials
    from run_mc_eval import extract_answer
    from run_harness_eval import load_legal_mc, load_legal_nli
    from run_legal_arm_a import DEFAULT_PARITY_SLUG
    from score_reading_eval import measurement_card_hash

load_dotenv()

LETTERS = "ABCDE"
TOP_LOGPROBS = 20          # all five letters fit comfortably; the rest is a safety margin
ITEM_COLS = ["id", "gold", "answer", "correct", "first_token", "n_letters_found",
             "p_A", "p_B", "p_C", "p_D", "p_E", "confidence"]
SUMMARY_COLS = ["dataset", "n", "n_usable", "accuracy", "mean_confidence", "ece",
                "brier_confidence", "brier_multiclass", "overconfidence", "card_hash"]
RELIABILITY_COLS = ["dataset", "bin_lo", "bin_hi", "n", "mean_confidence", "accuracy"]


def letter_probs(top_logprobs: list[dict]) -> dict[str, float]:
    """P(A..E) from the first-token top_logprobs, renormalized over the letters
    actually present. A token counts only if it is exactly one uppercase letter
    (the probe showed the first token is the bare letter); anything else (a
    leading space, punctuation, a word) is ignored, and missing letters simply
    carry the residual — reported via `n_letters_found`, never invented."""
    raw = {}
    for t in top_logprobs:
        tok = t.get("token")
        if tok in LETTERS:
            raw[tok] = math.exp(t["logprob"])
    total = sum(raw.values())
    if total <= 0:
        return {c: 0.0 for c in LETTERS}
    return {c: raw.get(c, 0.0) / total for c in LETTERS}


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
        brier_mc += sum((float(r[f"p_{c}"]) - (1.0 if c == y else 0.0)) ** 2 for c in LETTERS)
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


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="capture the letter distribution on a gold MC set")
    run.add_argument("--dataset", default="legal_mc", choices=["legal_mc", "legal_nli"])
    run.add_argument("--label", default=None, help="default: <sanitized-model>-cal")
    add_endpoint_args(run, max_tokens_default=4, max_tokens_help="MC letter budget (default: 4)",
                      resume_help="unused (single small run; re-run overwrites)")
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

    items = (load_legal_mc(DEFAULT_PARITY_SLUG) if args.dataset == "legal_mc"
             else load_legal_nli(DEFAULT_PARITY_SLUG))
    print(f"[cal] {args.dataset} n={len(items)} model={model} label={label}")
    client = build_client(base_url, api_key)
    verify_credentials(client, model)

    rows = []
    for it in items:
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": it["prompt"]}],
            max_tokens=args.max_tokens, temperature=args.temperature, seed=args.seed,
            logprobs=True, top_logprobs=TOP_LOGPROBS)
        ch = resp.choices[0]
        raw = ch.message.content or ""
        answer = extract_answer(raw)
        lp = ch.logprobs
        top = []
        if lp is not None and lp.content:
            top = [{"token": t.token, "logprob": t.logprob} for t in (lp.content[0].top_logprobs or [])]
        probs = letter_probs(top)
        found = sum(1 for c in LETTERS if probs[c] > 0)
        conf = f"{probs[answer]:.6f}" if answer in LETTERS else ""
        rows.append({"id": it["item_id"], "gold": it["gold"], "answer": answer,
                     "correct": int(bool(answer) and answer == it["gold"]),
                     "first_token": (lp.content[0].token if (lp and lp.content) else ""),
                     "n_letters_found": found,
                     **{f"p_{c}": f"{probs[c]:.6f}" for c in LETTERS},
                     "confidence": conf})

    write_csv_atomic(folder / f"mc_calibration_items_{args.dataset}_{label}.csv", rows, ITEM_COLS)
    acc = sum(r["correct"] for r in rows)
    print(f"[cal] wrote {len(rows)} items | accuracy {acc}/{len(rows)} = {acc/len(rows)*100:.2f}%")
    print(f"-> {folder / f'mc_calibration_items_{args.dataset}_{label}.csv'}")


def cmd_report(args: argparse.Namespace) -> None:
    folder = model_dirs(args.model)[0]
    items = read_csv_checked(folder / f"mc_calibration_items_{args.dataset}_{args.label}.csv",
                             required=set(ITEM_COLS), label="calibration items")
    summary, rows = build_report(items, args.dataset, measurement_card_hash(), bins=args.bins)
    write_csv_atomic(folder / f"mc_calibration_summary_{args.dataset}_{args.label}.csv",
                     [summary], SUMMARY_COLS)
    write_csv_atomic(folder / f"mc_calibration_reliability_{args.dataset}_{args.label}.csv",
                     rows, RELIABILITY_COLS)
    print(f"n={summary['n']} usable={summary['n_usable']} accuracy={summary['accuracy']}% "
          f"mean_conf={summary['mean_confidence']}% ECE={summary['ece']} "
          f"Brier(conf)={summary['brier_confidence']} over={summary['overconfidence']}")
    for r in rows:
        if r["n"]:
            print(f"  [{r['bin_lo']},{r['bin_hi']}) n={r['n']} conf={r['mean_confidence']} acc={r['accuracy']}")


def main() -> None:
    args = parse_args()
    (cmd_run if args.cmd == "run" else cmd_report)(args)


if __name__ == "__main__":
    main()
