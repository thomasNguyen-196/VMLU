"""Direct-prompt baseline (arm A) for the legal MC / NLI sets — the missing producer.

Why this file exists: the two legal baselines every harness card compares against
(`full_evaluation_legal_<model>.csv`, `full_evaluation_nli_<model>.csv`) have no
runner in the repo — `run_mc_eval.py` writes `full_evaluation_<model>.csv` and
nothing writes the legal infix. So a *second* model could not be brought into the
harness arm at all: `--arm-a-slug` needs that model’s own baseline, and without
it the ladder would silently become a comparison between two different models
instead of a measurement of the harness. That is the one thing the ladder may
never be.

Nothing here re-derives the question: `load_legal_mc` / `load_legal_nli` are
imported from the harness runner, so the prompt bytes are the FROZEN ones — the
very bytes arm B sends through omp. `--parity-against` then re-checks them
against an already-measured baseline (default the Qwen arm) and refuses on any
drift, so a baseline for model B is provably built from the same question as
model A's.

Output contract (identical header to the Qwen baseline, so both arms are the
same shape on the comparison side):
  all_res/ollama_result/<model>/full_evaluation_{legal|nli}_<model>.csv
  columns: id, question, prompt, raw_response, answer, gold_answer, correct
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from code_benchmark.common import (add_endpoint_args, parse_endpoint_args,
                                       read_csv_checked, resolve_endpoint, sanitize_model,
                                       setup_logging, write_csv_atomic)
    from code_benchmark.checkpoint import checkpoint_name, find_latest_checkpoint
    from code_benchmark.llm import build_client, call_model_with_retry, verify_credentials
    from code_benchmark.run_harness_eval import ARM_A, load_legal_mc, load_legal_nli
    from code_benchmark.run_mc_eval import extract_answer
except ImportError:
    from common import (add_endpoint_args, parse_endpoint_args, read_csv_checked,
                        resolve_endpoint, sanitize_model, setup_logging, write_csv_atomic)
    from checkpoint import checkpoint_name, find_latest_checkpoint
    from llm import build_client, call_model_with_retry, verify_credentials
    from run_harness_eval import ARM_A, load_legal_mc, load_legal_nli
    from run_mc_eval import extract_answer

RESULTS_DIR = Path("all_res/ollama_result")
LOGS_DIR = Path("logs")
FINAL_COLS = ["id", "question", "prompt", "raw_response", "answer", "gold_answer", "correct"]
DATASETS = ("legal_mc", "legal_nli")
# Checkpoints are dataset-scoped (`raw_result_legal_mc_25_<slug>.csv`, the shape
# the harness arm already uses). The bare MC prefix has no dataset in it, so two
# legal sets run for one slug would fight over the same file.
CKPT_PREFIX = "raw_result_{dataset}_"
# The measured Qwen baseline every card's arm-A column came from. Used as the
# prompt-parity reference by default: a new model's baseline must be built from
# the same bytes, or the pair is not a pair.
DEFAULT_PARITY_SLUG = "Qwen3_5-9B-28K"

lock = threading.Lock()


def load(dataset: str) -> list[dict]:
    if dataset == "legal_mc":
        return load_legal_mc(DEFAULT_PARITY_SLUG)
    if dataset == "legal_nli":
        return load_legal_nli(DEFAULT_PARITY_SLUG)
    raise SystemExit(f"Error: --dataset must be one of {list(DATASETS)}")


def final_path(dataset: str, slug: str) -> Path:
    """The exact filename `--arm-a-slug` and `_verify_prompt_parity` look for.

    ARM_A's `eval` template is the contract; deriving it from the spec instead of
    re-typing the string is what keeps this writer and the reader from drifting.
    """
    return RESULTS_DIR / slug / ARM_A[dataset]["eval"].format(a=slug)


def assert_prompt_parity(items: list[dict], dataset: str, reference: str) -> None:
    """Hard-fail unless every prompt is byte-identical to an existing baseline.

    The loaders already verify themselves against the Qwen file; this repeats the
    check explicitly for the record, and refuses when the reference is absent —
    an unverifiable baseline must not be written, because a wrong prompt here
    would show up much later as a "harness effect" that is really two questions.
    """
    path = final_path(dataset, reference)
    if not path.exists():
        raise SystemExit(f"Error: parity reference {path} not found — refusing to write a "
                         f"baseline whose prompt bytes cannot be proven identical")
    ref = {str(r["id"]): r["prompt"] for r in read_csv_checked(path, label=f"parity {reference}")}
    for it in items:
        got = ref.get(it["item_id"])
        if got is None:
            raise SystemExit(f"Error: {it['item_id']} missing from {path}")
        if got != it["prompt"]:
            raise SystemExit(f"Error: prompt drift for {it['item_id']} vs {reference} — the "
                             f"adapter no longer reproduces the reference baseline's bytes")
    print(f"[ok] prompt parity vs {reference}: {len(items)}/{len(items)} byte-identical")


def load_checkpoint(path: Path) -> dict[str, dict]:
    rows = read_csv_checked(path, required={"id", "answer"}, label="checkpoint")
    out = {}
    for r in rows:
        rid = str(r["id"])
        if rid:
            out[rid] = {c: r.get(c, "") for c in FINAL_COLS}
            # Rehydrate the one numeric column: read_csv_checked hands back strings,
            # and a resumed row mixed into `final` broke `sum(r["correct"] …)` with
            # a str+int TypeError after the file was already written.
            out[rid]["correct"] = int(r.get("correct") or 0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Direct-prompt baseline (arm A) for legal MC / NLI, frozen prompts.")
    ap.add_argument("--dataset", required=True, choices=list(DATASETS))
    ap.add_argument("--parity-against", default=DEFAULT_PARITY_SLUG,
                    help=f"baseline slug whose prompt bytes must match exactly "
                         f"(default: {DEFAULT_PARITY_SLUG})")
    add_endpoint_args(ap, max_tokens_default=4,
                      max_tokens_help="Max new tokens (default: 4 — the frozen MC-10 "
                                      "budget; the prompt asks for one letter)",
                      resume_help="Resume from the newest raw_result_<count>_<model>.csv")
    args = parse_endpoint_args(ap)
    base_url, api_key, model = resolve_endpoint(args)
    slug = sanitize_model(model)
    result_folder = RESULTS_DIR / slug
    result_folder.mkdir(parents=True, exist_ok=True)
    setup_logging(LOGS_DIR / slug / f"legal_arm_a_{args.dataset}_{slug}.log")

    client = build_client(base_url, api_key)
    verify_credentials(client, model)          # one 1-token call: auth/model fail-fast

    items = load(args.dataset)
    assert_prompt_parity(items, args.dataset, args.parity_against)
    if args.limit:
        items = items[: args.limit]
    n_expected = ARM_A[args.dataset]["n"]
    if not args.limit and len(items) != n_expected:
        raise SystemExit(f"Error: {args.dataset} has {len(items)} items, card says {n_expected}")
    print(f"{args.dataset}: n={len(items)} | model={model} | slug={slug} | "
          f"max_tokens={args.max_tokens} | temperature={args.temperature} | seed={args.seed}")

    ckpt_prefix = CKPT_PREFIX.format(dataset=args.dataset)
    done: dict[str, dict] = {}
    if args.resume:
        latest = find_latest_checkpoint(result_folder, slug, ckpt_prefix)
        if latest:
            done = load_checkpoint(latest)
            print(f"resumed {len(done)} answers from {latest}")

    remaining = [it for it in items if it["item_id"] not in done]
    print(f"remaining {len(remaining)}/{len(items)}")

    def one(item: dict) -> dict:
        raw = call_model_with_retry(client=client, model=model, prompt=item["prompt"],
                                    temperature=args.temperature, seed=args.seed,
                                    max_tokens=args.max_tokens)
        letter = extract_answer(raw)
        return {"id": item["item_id"], "question": item["question"], "prompt": item["prompt"],
                "raw_response": raw, "answer": letter, "gold_answer": item["gold"],
                "correct": int(bool(letter) and letter == item["gold"])}

    if remaining:
        start = time.time()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(one, it): it for it in remaining}
            for i, fut in enumerate(as_completed(futures), start=1):
                row = fut.result()
                with lock:
                    # `done` is CUMULATIVE — resumed rows plus this leg's — so the
                    # newest checkpoint is always the union of everything answered.
                    # Writing only this leg's rows made a second --resume lose the
                    # first leg: find_latest_checkpoint picks the highest count, and
                    # after a resume that file held fewer answers than the one it
                    # replaced. The reading/MC runners both write the union.
                    done[str(row["id"])] = row
                    if i % 25 == 0 or i == len(remaining):
                        write_csv_atomic(
                            result_folder / checkpoint_name(slug, len(done), ckpt_prefix),
                            list(done.values()), FINAL_COLS)
        print(f"inference {time.time() - start:.1f}s")

    by_id = dict(done)
    final = [by_id[it["item_id"]] for it in items if it["item_id"] in by_id]
    if len(final) != len(items):
        missing = [it["item_id"] for it in items if it["item_id"] not in by_id]
        raise SystemExit(f"Error: {len(missing)} items unanswered, first={missing[:5]} — "
                         f"nothing is written; re-run with --resume")

    out = final_path(args.dataset, slug)
    if args.limit:
        # A truncated set must never sit at the name `--arm-a-slug` reads: a
        # 2-row "baseline" would compare the arms on 2 items and look legitimate.
        out = out.with_name(f"{out.stem}.smoke{args.limit}{out.suffix}")
    write_csv_atomic(out, final, FINAL_COLS)
    n_correct = sum(r["correct"] for r in final)
    n_blank = sum(1 for r in final if not r["answer"])
    print(f"wrote {out}")
    print(f"accuracy {n_correct}/{len(final)} = {100 * n_correct / len(final):.2f}%  "
          f"(unparseable {n_blank}, counted wrong, still in the denominator)")


if __name__ == "__main__":
    sys.exit(main())
