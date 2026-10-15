#!/usr/bin/env python3
"""Citation-condition reading runner (metrics group 2.2, cards MC-37/MC-38).

The SAME reading-400 items as MC-3/MC-31, answered under a NEW pre-registered
condition: the model must return a short answer AND a verbatim citation of the
supporting passage text, in two labelled fields:

    Trả lời: <câu trả lời>
    Trích dẫn: <đoạn trích nguyên văn>

The frozen reading pipeline is NOT touched: `build_reading_prompt` and the
scoring math in `score_reading_eval.py` keep their bytes; this module imports
the manifest join helpers and `score_pair`, and owns only the new prompt +
extraction + file names. One condition, one label namespace — never mixed with
`reading_result_*` / `reading_answers_*` of the frozen condition.

Subcommands (run from repo root):

    .venv/bin/python code_benchmark/run_reading_cite_eval.py run   [--limit N] [--resume]
    .venv/bin/python code_benchmark/run_reading_cite_eval.py score

Outputs under all_res/ollama_result/<model>/ (label defaults to
`<sanitized-model>-cite`):

    reading_cite_result_<n>_<label>.csv    checkpoints (resume only for this label)
    reading_cite_answers_<label>.csv       raw_response + extracted answer/citation
    reading_cite_scores_<label>.csv        per-item EM/char-F1 on the answer field
    reading_cite_summary_<label>.csv       per-source + ALL summary, card hash
"""

from __future__ import annotations

import argparse
import csv
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import (sanitize_model, resolve_endpoint, model_dirs,
                                       MANIFEST_DEFAULT, SQUAD_DEFAULT, DROP_DEFAULT,
                                       GOLD_REVIEW_DEFAULT, read_csv_checked,
                                       write_csv_atomic, add_endpoint_args,
                                       setup_logging, item_key)
    from code_benchmark.checkpoint import (READING_CITE_PREFIX, checkpoint_name,
                                           find_latest_checkpoint)
    from code_benchmark.llm import build_client, verify_credentials, call_model_with_retry
    from code_benchmark.run_reading_eval import load_manifest, index_sources, join_manifest
    from code_benchmark.score_reading_eval import score_pair, measurement_card_hash
except ImportError:  # direct run from code_benchmark/
    from common import (sanitize_model, resolve_endpoint, model_dirs,
                        MANIFEST_DEFAULT, SQUAD_DEFAULT, DROP_DEFAULT,
                        GOLD_REVIEW_DEFAULT, read_csv_checked,
                        write_csv_atomic, add_endpoint_args,
                        setup_logging, item_key)
    from checkpoint import READING_CITE_PREFIX, checkpoint_name, find_latest_checkpoint
    from llm import build_client, verify_credentials, call_model_with_retry
    from run_reading_eval import load_manifest, index_sources, join_manifest
    from score_reading_eval import score_pair, measurement_card_hash

load_dotenv()

ANSWER_LABEL = "Trả lời:"
CITATION_LABEL = "Trích dẫn:"

ANSWER_COLS = ["dataset", "item_id", "stratum", "question", "context_words",
               "raw_response", "answer", "citation"]
SCORE_COLS = ["dataset", "item_id", "stratum", "gold_answer", "raw_response",
              "answer", "citation", "prediction", "em", "f1", "exact_raw"]
SUMMARY_COLS = ["dataset", "n", "em_count", "em", "char_f1", "exact_raw_count",
                "compliant_count", "compliance", "blank_answer", "blank_citation",
                "measurement_card_hash"]


def build_citation_prompt(context: str, question: str) -> str:
    """The citation condition's prompt — bytes pre-registered in MC-37.

    NOT a variant of `build_reading_prompt`: that function is byte-frozen and
    this is a different elicitation condition, which is exactly why it lives in
    its own module. Changing this string after MC-37 was committed is a new
    condition (new card), never an edit.
    """
    return (
        "Đọc đoạn văn dưới đây và trả lời câu hỏi bằng một cụm từ hoặc số ngắn gọn, "
        "lấy nguyên văn trong đoạn văn khi có thể.\n"
        "Sau đó trích dẫn nguyên văn một đoạn ngắn trong bài chứa câu trả lời.\n"
        "Trả lời theo đúng hai dòng:\n"
        "Trả lời: <câu trả lời>\n"
        "Trích dẫn: <đoạn trích>\n\n"
        + context.strip()
        + "\n\nCâu hỏi: " + question + "\nTrả lời: "
    )


def extract_citation_answer(raw: str) -> tuple[str, str]:
    """(answer, citation) from the two-field reply; fail-soft, never repairs.

    Handles both continuation styles a chat model produces after a prompt that
    ends with `Trả lời: ` — repeating the labels ("Trả lời: 1999\\nTrích dẫn: …")
    or continuing directly ("1999\\nTrích dẫn: …"). The answer is the text before
    the LAST citation label, from the LAST answer label if present, else the
    continuation itself; first non-empty line. Missing citation label, or an
    empty answer, is unparsed -> ("", "") and stays counted, never reconstructed.
    """
    if not raw:
        return "", ""
    text = raw.strip()
    ic = text.rfind(CITATION_LABEL)
    if ic == -1:
        return "", ""
    prefix = text[:ic]
    ia = prefix.rfind(ANSWER_LABEL)
    answer_block = prefix[ia + len(ANSWER_LABEL):] if ia != -1 else prefix
    answer = next((ln.strip() for ln in answer_block.splitlines() if ln.strip()), "")
    citation = text[ic + len(CITATION_LABEL):].strip()
    return answer, citation


def default_label(model: str) -> str:
    return f"{sanitize_model(model)}-cite"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="call the model on the citation condition")
    run.add_argument("--manifest", type=Path, default=MANIFEST_DEFAULT)
    run.add_argument("--squad-file", type=Path, default=SQUAD_DEFAULT)
    run.add_argument("--drop-file", type=Path, default=DROP_DEFAULT)
    run.add_argument("--label", default=None,
                     help="condition label for output names (default: <sanitized-model>-cite)")
    add_endpoint_args(run, max_tokens_default=128,
                      max_tokens_help="answer + citation budget (default: 128)",
                      resume_help="continue from the newest reading_cite_result_<n>_<label>.csv")

    score = sub.add_parser("score", help="EM/char-F1 on the extracted answer field")
    score.add_argument("--label", required=True)
    score.add_argument("--model", required=True, help="endpoint model tag (folder name)")
    score.add_argument("--gold", type=Path, default=GOLD_REVIEW_DEFAULT)
    return ap.parse_args()


def cmd_run(args: argparse.Namespace) -> None:
    base_url, api_key, model = resolve_endpoint(args)
    label = args.label or default_label(model)
    result_folder, _, logs_folder = model_dirs(model)
    setup_logging(logs_folder / f"reading_cite_{sanitize_model(label)}.log")

    logging.info(f"[cite] model={model} label={label} @ {base_url} | workers={args.workers} "
                 f"temp={args.temperature} seed={args.seed} max_tokens={args.max_tokens}")

    manifest = load_manifest(args.manifest)
    idx = index_sources(args.squad_file, args.drop_file)
    items = join_manifest(manifest, idx)
    if args.limit:
        items = items[: args.limit]
    total = len(items)
    logging.info(f"[cite] Joined {total} manifest rows "
                 f"({sum(r['dataset'] == 'squad' for r in items)} squad / "
                 f"{sum(r['dataset'] == 'drop' for r in items)} drop)")

    client = build_client(base_url, api_key)
    logging.info("[cite] Verifying endpoint connectivity and credentials...")
    verify_credentials(client, model)

    existing: dict[str, dict] = {}
    if args.resume:
        cp = find_latest_checkpoint(result_folder, label, prefix=READING_CITE_PREFIX)
        if cp:
            logging.info(f"[cite] Resuming from checkpoint: {cp}")
            with open(cp, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing[item_key(row)] = row

    results: list[dict | None] = [None] * total
    to_process = []
    for i, item in enumerate(items):
        k = item_key(item)
        if k in existing:
            results[i] = existing[k]
        else:
            to_process.append((i, item))
    logging.info(f"[cite] Remaining to evaluate: {len(to_process)}/{total}")

    lock = Lock()
    completed = len(existing)

    def process(index: int, item: dict) -> int:
        nonlocal completed
        raw = call_model_with_retry(
            client=client, model=model,
            prompt=build_citation_prompt(item["context"], item["question"]),
            temperature=args.temperature, seed=args.seed, max_tokens=args.max_tokens)
        answer, citation = extract_citation_answer(raw)
        row = {"dataset": item["dataset"], "item_id": item["item_id"],
               "stratum": item["stratum"], "question": item["question"],
               "context_words": len(item["context"].split()),
               "raw_response": raw.strip(), "answer": answer, "citation": citation}
        with lock:
            results[index] = row
            completed += 1
            done = [r for r in results if r is not None]
            if completed % 100 == 0 or completed == total:
                write_csv_atomic(
                    result_folder / checkpoint_name(label, len(done), prefix=READING_CITE_PREFIX),
                    done, ANSWER_COLS)
        return index

    start = time.time()
    if to_process:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process, i, it): i for i, it in to_process}
            for fut in as_completed(futs):
                fut.result()
    dur = time.time() - start
    logging.info(f"[cite] Time taken: {dur:.1f}s ({dur/60:.2f} mins)")

    done = [r for r in results if r is not None]
    out_path = result_folder / f"reading_cite_answers_{label}.csv"
    write_csv_atomic(out_path, done, ANSWER_COLS)
    blank_a = sum(1 for r in done if not r["answer"])
    blank_c = sum(1 for r in done if not r["citation"])
    logging.info(f"[cite] Wrote {len(done)} answers -> {out_path} | "
                 f"blank answer: {blank_a} | blank citation: {blank_c}")


def cmd_score(args: argparse.Namespace) -> None:
    folder = model_dirs(args.model)[0]
    answers_path = folder / f"reading_cite_answers_{args.label}.csv"
    if not answers_path.exists():
        raise SystemExit(f"Error: answers file not found: {answers_path}")
    if not args.gold.exists():
        raise SystemExit(f"Error: gold file not found: {args.gold}")

    gold = {(r["dataset"], str(r["item_id"])): r["gold_answer"]
            for r in read_csv_checked(args.gold, required={"dataset", "item_id", "gold_answer"},
                                      label="gold")}
    answers = read_csv_checked(answers_path,
                               required={"dataset", "item_id", "raw_response",
                                         "answer", "citation"},
                               label="cite answers")
    missing = [item_key(r) for r in answers if (r["dataset"], str(r["item_id"])) not in gold]
    if missing:
        raise SystemExit(f"Error: {len(missing)} answer rows have no gold, e.g. {missing[:5]}")
    unknown = sorted(set(gold) - {(r["dataset"], str(r["item_id"])) for r in answers})
    if unknown:
        raise SystemExit(f"Error: {len(unknown)} gold rows have no answer, e.g. {unknown[:5]}")

    card_hash = measurement_card_hash()
    rows = []
    for r in answers:
        key = (r["dataset"], str(r["item_id"]))
        pred, f1, em, exact_raw = score_pair(r.get("answer", ""), gold[key])
        rows.append({
            "dataset": key[0], "item_id": key[1], "stratum": r.get("stratum", ""),
            "gold_answer": gold[key], "raw_response": r.get("raw_response", ""),
            "answer": r.get("answer", ""), "citation": r.get("citation", ""),
            "prediction": pred, "em": int(em), "f1": f"{f1:.6f}",
            "exact_raw": int(exact_raw),
        })
    scores_path = folder / f"reading_cite_scores_{args.label}.csv"
    write_csv_atomic(scores_path, rows, SCORE_COLS)

    summary = []
    groups: list[tuple[str, list[dict]]] = [(ds, [r for r in rows if r["dataset"] == ds])
                                            for ds in ("squad", "drop")]
    groups.append(("ALL", rows))
    for ds, sub in groups:
        n = len(sub)
        if not n:
            continue
        compliant = sum(1 for r in sub if r["answer"] and r["citation"])
        summary.append({
            "dataset": ds, "n": n,
            "em_count": sum(r["em"] for r in sub),
            "em": f"{sum(r['em'] for r in sub) / n * 100:.2f}",
            "char_f1": f"{sum(float(r['f1']) for r in sub) / n * 100:.2f}",
            "exact_raw_count": sum(r["exact_raw"] for r in sub),
            "compliant_count": compliant,
            "compliance": f"{compliant / n * 100:.2f}",
            "blank_answer": sum(1 for r in sub if not r["answer"]),
            "blank_citation": sum(1 for r in sub if not r["citation"]),
            "measurement_card_hash": card_hash,
        })
    summary_path = folder / f"reading_cite_summary_{args.label}.csv"
    write_csv_atomic(summary_path, summary, SUMMARY_COLS)

    logging.info("[cite] Scored %d items, card hash %s", len(rows), card_hash)
    for s in summary:
        logging.info("  %-6s n=%-4s EM=%-6s char-F1=%-6s compliance=%s%% "
                     "(blank a/c %s/%s)", s["dataset"], s["n"], s["em"], s["char_f1"],
                     s["compliance"], s["blank_answer"], s["blank_citation"])
    print(f"-> {scores_path}\n-> {summary_path}")


def main() -> None:
    args = parse_args()
    if args.cmd == "run":
        cmd_run(args)
    else:
        cmd_score(args)


if __name__ == "__main__":
    main()
