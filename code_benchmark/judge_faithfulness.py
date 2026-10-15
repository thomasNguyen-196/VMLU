#!/usr/bin/env python3
"""Faithfulness judge for the citation condition (metrics group 2.2, MC-37/38).

The judge is a MEASUREMENT INSTRUMENT, not an oracle: before any full pass it
must clear a human-validation gate on a pre-registered sample (sheet ->
human labels -> `validate`). If the gate fails twice, the measurement stops and
the instrument failure is the result — no faithfulness score is published.

Subcommands (repo root):

    sheet    generate the blind human-label sheet (pre-registered sampling)
    run      judge items through the judge endpoint (--sheet to judge only the
             validation sample; default judges every item)
    validate agreement + Cohen's kappa vs the committed human labels + gate
    metrics  join scores + judge verdicts into the final summary table

The judge endpoint is configured independently of the main pipeline:
`JUDGE_BASE_URL` / `JUDGE_API_KEY` / `JUDGE_MODEL` / `JUDGE_HEADERS` env vars
(or --judge-* flags). Every row records the judge model + raw response.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
from collections import Counter
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import (model_dirs, read_csv_checked, write_csv_atomic,
                                       MANIFEST_DEFAULT, SQUAD_DEFAULT, DROP_DEFAULT,
                                       setup_logging, item_key)
    from code_benchmark.llm import extra_headers, verify_credentials, call_model_with_retry
    from code_benchmark.run_reading_eval import load_manifest, index_sources, join_manifest
    from code_benchmark.score_reading_eval import normalize_answer, measurement_card_hash
except ImportError:  # direct run from code_benchmark/
    from common import (model_dirs, read_csv_checked, write_csv_atomic,
                        MANIFEST_DEFAULT, SQUAD_DEFAULT, DROP_DEFAULT,
                        setup_logging, item_key)
    from llm import extra_headers, verify_credentials, call_model_with_retry
    from run_reading_eval import load_manifest, index_sources, join_manifest
    from score_reading_eval import normalize_answer, measurement_card_hash

load_dotenv()

# Pre-registered sampling rule (MC-37): 60 items = 15 per (dataset × EM) cell,
# seed 42, deterministic; a short cell tops up from the other EM cell of the
# same dataset, then from the other dataset — the exact order below.
SHEET_SEED = 42
SHEET_PER_CELL = 15
GATE_AGREEMENT = 0.80
GATE_KAPPA = 0.60

SHEET_COLS = ["dataset", "item_id", "question", "context", "answer", "citation"]
LABEL_COLS = ["dataset", "item_id", "human_supports", "note"]
JUDGE_COLS = ["dataset", "item_id", "judge_model", "verdict", "reason",
              "citation_verbatim", "judge_error", "raw_judge_response"]
VALID_COLS = ["label", "n", "agree", "agreement", "kappa", "gate_pass",
              "unlabeled", "judge_model", "measurement_card_hash"]
METRIC_COLS = ["dataset", "n", "compliant_count", "compliance", "em", "char_f1",
               "citation_verbatim_count", "citation_verbatim_rate",
               "judged", "judge_errors", "supported", "supported_rate",
               "correct_and_supported", "correct_unsupported",
               "incorrect_supported", "incorrect_unsupported",
               "judge_model", "measurement_card_hash"]


def build_judge_prompt(context: str, question: str, answer: str, citation: str) -> str:
    """The judge prompt — pre-registered in MC-37 (v1), revised ONCE per the
    MC-37 gate rule (v2, MC-38) to close defects the human validation exposed:
    unchecked arithmetic ("gần đúng" accepted), answer-type mismatch (a bare
    number where the question asks which one), a verdict contradicting its own
    reason, and no rule for a correct "not in the passage" answer. Still one
    frozen string; any further change is a new instrument version."""
    return (
        "Bạn là giám khảo cho bài đọc hiểu. Cho đoạn văn, câu hỏi, câu trả lời "
        "của mô hình và đoạn trích dẫn của mô hình.\n"
        "Đánh giá: đoạn trích dẫn có trực tiếp chống đỡ câu trả lời như một câu "
        "trả lời cho câu hỏi không?\n"
        "Quy tắc:\n"
        "- Đoạn trích phải chứa thông tin trả lời, hoặc cho phép suy ra trực tiếp "
        "bằng đúng một bước từ chính các con số/dữ kiện trong đoạn trích.\n"
        "- Câu trả lời phải đúng loại thông tin mà câu hỏi hỏi. Nếu câu hỏi hỏi "
        "\"cái nào / tỷ lệ nào / năm nào\" mà câu trả lời chỉ là một con số không "
        "kèm lựa chọn, thì coi là unsupported, trừ khi đoạn trích tự nêu rõ lựa chọn.\n"
        "- Nếu câu trả lời là kết quả một phép tính, tự tính lại từ các con số trong "
        "đoạn trích; chỉ supported khi kết quả khớp chính xác (gần đúng không tính).\n"
        "- Câu trả lời mâu thuẫn với đoạn trích thì unsupported.\n"
        "- Đoạn trích đúng chủ đề nhưng không mang thông tin trả lời thì unsupported.\n"
        "- Nếu câu trả lời nói không có thông tin trong đoạn văn và đoạn trích thật "
        "sự không chứa thông tin câu hỏi hỏi thì supported.\n"
        "- Lý do phải nhất quán với kết luận.\n"
        "Chỉ trả về JSON đúng định dạng:\n"
        '{"verdict": "supported" hoặc "unsupported", "reason": "<một câu ngắn>"}\n\n'
        "Đoạn văn:\n" + context.strip()
        + "\n\nCâu hỏi: " + question
        + "\nCâu trả lời: " + (answer or "(trống)")
        + "\nTrích dẫn: " + (citation or "(trống)")
    )


_VERDICT_RE = re.compile(r'"verdict"\s*:\s*"(supported|unsupported)"', re.IGNORECASE)


def parse_judge_verdict(raw: str) -> tuple[str, str, bool]:
    """(verdict, reason, judge_error) from the judge reply.

    Strict-but-safe: a bare JSON object, or the first {...} block in a chatty
    reply, wins; if a reasoning judge emitted prose (or nested braces) that
    breaks JSON extraction, fall back to the LAST explicit `"verdict"` field —
    the final answer, not a mention inside the reasoning. Anything without a
    valid verdict is a judge_error — counted, never guessed (no keyword fallback).
    """
    if not raw:
        return "", "", True
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    obj = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                obj = None
    if isinstance(obj, dict):
        verdict = str(obj.get("verdict", "")).strip().lower()
        if verdict in ("supported", "unsupported"):
            return verdict, str(obj.get("reason", "")).strip(), False
    matches = _VERDICT_RE.findall(raw)
    if matches:
        return matches[-1].lower(), "", False
    return "", "", True


def judge_once(call, prompt: str, *, retries: int) -> tuple[str, str, bool, str]:
    """Ask the judge, re-asking only when the reply does not PARSE (format), up
    to `retries` extra times. A valid verdict from any attempt is returned; all
    attempts failing -> judge_error. Never infers a verdict from keywords."""
    raw = ""
    for _ in range(retries + 1):
        raw = call(prompt)
        verdict, reason, err = parse_judge_verdict(raw)
        if not err:
            return verdict, reason, err, raw
    return "", "", True, raw


def citation_verbatim(citation: str, context: str) -> bool:
    """Mechanical companion check: the citation appears verbatim in the context
    (after the frozen scorer's own normalization: casefold + whitespace +
    trailing punctuation). No judge involved; reported separately."""
    c = normalize_answer(citation)
    return bool(c) and c in normalize_answer(context)


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float:
    """Cohen's kappa for two binary raters. Degenerate marginals (pe == 1)
    return 1.0 on full agreement, else 0.0 — never NaN silently."""
    n = len(pairs)
    if not n:
        return float("nan")
    po = sum(a == b for a, b in pairs) / n
    pa1 = sum(a for a, _ in pairs) / n
    pb1 = sum(b for _, b in pairs) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def sample_sheet(rows: list[dict], *, per_cell: int = SHEET_PER_CELL,
                 seed: int = SHEET_SEED) -> list[dict]:
    """The pre-registered sample: `per_cell` from each (dataset × em) cell
    (phase 1), then top-ups from the same dataset's remaining items, squad
    before drop (phase 2). Deterministic: sorted ids + one seeded shuffle."""
    rng = random.Random(seed)
    by_cell: dict[tuple[str, int], list[dict]] = {}
    for r in rows:
        by_cell.setdefault((r["dataset"], int(r["em"])), []).append(r)
    for v in by_cell.values():
        v.sort(key=lambda r: str(r["item_id"]))
        rng.shuffle(v)

    picked: list[dict] = []
    seen: set[str] = set()

    def take(pool: list[dict], k: int) -> None:
        for r in pool:
            if k <= 0:
                return
            kk = item_key(r)
            if kk in seen:
                continue
            seen.add(kk)
            picked.append(r)
            k -= 1

    cells = [("squad", 1), ("squad", 0), ("drop", 1), ("drop", 0)]
    for key in cells:
        take(by_cell.get(key, []), per_cell)
    target = per_cell * len(cells)
    for ds in ("squad", "drop"):
        if len(picked) >= target:
            break
        take([r for r in by_cell.get((ds, 1), []) + by_cell.get((ds, 0), [])
              if item_key(r) not in seen], target - len(picked))
    return picked


def gate_passes(n: int, agreement: float, kappa: float) -> bool:
    """The pre-registered gate (MC-37): both thresholds, no rounding mercy."""
    return bool(n) and agreement >= GATE_AGREEMENT and kappa >= GATE_KAPPA


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--model", required=True, help="model tag (result folder name)")
        p.add_argument("--label", required=True, help="condition label (file suffix)")

    sh = sub.add_parser("sheet", help="blind human-label sheet (pre-registered sample)")
    common(sh)
    sh.add_argument("--seed", type=int, default=SHEET_SEED)
    sh.add_argument("--per-cell", type=int, default=SHEET_PER_CELL)
    sh.add_argument("--exclude", type=Path, default=None,
                    help="CSV (sheet or labels) whose dataset:item_id keys are excluded — "
                         "test-set hygiene: never validate a judge on the sample it was tuned on")
    sh.add_argument("--out", type=Path, default=None,
                    help="output sheet CSV (default: faithfulness_sheet_<label>.csv)")

    rn = sub.add_parser("run", help="judge items through the judge endpoint")
    common(rn)
    rn.add_argument("--judge-model", default=None, help="default: JUDGE_MODEL env")
    rn.add_argument("--judge-base-url", default=None, help="default: JUDGE_BASE_URL env")
    rn.add_argument("--judge-api-key", default=None, help="default: JUDGE_API_KEY env")
    rn.add_argument("--judge-reasoning-effort", default="",
                    help="reasoning_effort sent to the judge; empty (default) = omit the field, "
                         "letting the provider default stand (a reasoning judge needs it)")
    rn.add_argument("--judge-max-tokens", type=int, default=1500,
                    help="judge reply budget; reasoning judges emit long traces before the JSON "
                         "(default: %(default)s)")
    rn.add_argument("--judge-retries", type=int, default=2,
                    help="re-ask an item whose reply does not parse (format only, never a "
                         "guessed verdict; default: %(default)s)")
    rn.add_argument("--sheet", type=Path, default=None,
                    help="judge only the items in this sheet (validation pass)")
    rn.add_argument("--out", type=Path, default=None,
                    help="output CSV (default: faithfulness_judge_<label>.csv)")
    rn.add_argument("--workers", type=int, default=4)
    rn.add_argument("--limit", type=int, default=None, help="first N items (smoke)")

    va = sub.add_parser("validate", help="agreement + kappa vs human labels + gate")
    common(va)
    va.add_argument("--labels", type=Path, required=True,
                    help="committed human labels CSV (data/faithfulness_labels_<label>.csv)")
    va.add_argument("--judge", type=Path, required=True, help="judge CSV of the sheet items")
    va.add_argument("--out", type=Path, default=None,
                    help="validation summary CSV (default: faithfulness_validation_<label>.csv)")
    va.add_argument("--skip-unlabeled", action="store_true",
                    help="drop rows with a blank human_supports and report the count "
                         "(partial coverage); default: fail on a blank label")

    me = sub.add_parser("metrics", help="final summary: scores + judge + verbatim")
    common(me)
    me.add_argument("--judge", type=Path, default=None,
                    help="full judge CSV (default: faithfulness_judge_<label>.csv)")
    me.add_argument("--out", type=Path, default=None,
                    help="summary CSV (default: faithfulness_summary_<label>.csv)")
    return ap.parse_args()


def _contexts(args: argparse.Namespace) -> dict[tuple[str, str], str]:
    manifest = load_manifest(MANIFEST_DEFAULT)
    idx = index_sources(SQUAD_DEFAULT, DROP_DEFAULT)
    return {(r["dataset"], str(r["item_id"])): r["context"]
            for r in join_manifest(manifest, idx)}


def cmd_sheet(args: argparse.Namespace) -> None:
    folder = model_dirs(args.model)[0]
    scores = read_csv_checked(folder / f"reading_cite_scores_{args.label}.csv",
                              required={"dataset", "item_id", "em"}, label="cite scores")
    if args.exclude:
        ex_keys = {item_key(r) for r in read_csv_checked(
            args.exclude, required={"dataset", "item_id"}, label="exclude")}
        before = len(scores)
        scores = [r for r in scores if item_key(r) not in ex_keys]
        print(f"excluded {before - len(scores)} items present in {args.exclude.name}")
    answers = {item_key(r): r for r in read_csv_checked(
        folder / f"reading_cite_answers_{args.label}.csv",
        required={"dataset", "item_id", "question", "answer", "citation"},
        label="cite answers")}
    ctx = _contexts(args)
    picked = sample_sheet(scores, per_cell=args.per_cell, seed=args.seed)
    if not picked:
        raise SystemExit("Error: no items to sample — run the citation condition first")
    rows = []
    for r in picked:
        key = item_key(r)
        a = answers[key]
        # The sheet is BLIND: no gold, no em, no judge verdict — only what a
        # human needs to judge support.
        rows.append({"dataset": r["dataset"], "item_id": str(r["item_id"]),
                     "question": a["question"], "context": ctx[(r["dataset"], str(r["item_id"]))],
                     "answer": a["answer"], "citation": a["citation"]})
    out = args.out or folder / f"faithfulness_sheet_{args.label}.csv"
    write_csv_atomic(out, rows, SHEET_COLS)
    cells = Counter((r["dataset"], int(r["em"])) for r in picked)
    print(f"sheet n={len(rows)} seed={args.seed} per_cell={args.per_cell} cells={dict(cells)}")
    print(f"-> {out}\nLabels go to data/faithfulness_labels_{args.label}.csv "
          f"(columns: {LABEL_COLS}) and must be committed BEFORE judging the sheet.")


def cmd_run(args: argparse.Namespace) -> None:
    folder = model_dirs(args.model)[0]
    judge_model = args.judge_model or os.environ.get("JUDGE_MODEL")
    base_url = args.judge_base_url or os.environ.get("JUDGE_BASE_URL")
    api_key = args.judge_api_key or os.environ.get("JUDGE_API_KEY")
    if not judge_model or not base_url or not api_key:
        raise SystemExit("Error: judge endpoint not configured — set JUDGE_MODEL/"
                         "JUDGE_BASE_URL/JUDGE_API_KEY (or --judge-* flags)")
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=120.0,
                    default_headers=extra_headers("JUDGE_HEADERS"))
    logging.info("[judge] endpoint=%s model=%s", base_url, judge_model)
    verify_credentials(client, judge_model)

    answers = read_csv_checked(folder / f"reading_cite_answers_{args.label}.csv",
                               required={"dataset", "item_id", "question",
                                         "answer", "citation"}, label="cite answers")
    if args.sheet:
        wanted = {item_key(r) for r in read_csv_checked(args.sheet,
                    required={"dataset", "item_id"}, label="sheet")}
        answers = [r for r in answers if item_key(r) in wanted]
        missing = wanted - {item_key(r) for r in answers}
        if missing:
            raise SystemExit(f"Error: sheet items missing from answers: {sorted(missing)[:5]}")
    if args.limit:
        answers = answers[: args.limit]

    ctx = _contexts(args)
    out_path = args.out or folder / f"faithfulness_judge_{args.label}.csv"
    lock = Lock()
    rows: list[dict] = []

    def one(r: dict) -> dict:
        key = (r["dataset"], str(r["item_id"]))
        prompt = build_judge_prompt(ctx[key], r["question"], r["answer"], r["citation"])
        extra = ({"reasoning_effort": args.judge_reasoning_effort}
                 if args.judge_reasoning_effort else None)

        def ask(prompt: str) -> str:
            return call_model_with_retry(
                client=client, model=judge_model, prompt=prompt,
                temperature=0.0, seed=42, max_tokens=args.judge_max_tokens,
                extra_body=extra)

        verdict, reason, err, raw = judge_once(ask, prompt, retries=args.judge_retries)
        return {"dataset": key[0], "item_id": key[1], "judge_model": judge_model,
                "verdict": verdict, "reason": reason,
                "citation_verbatim": int(citation_verbatim(r["citation"], ctx[key])),
                "judge_error": int(err), "raw_judge_response": raw.strip()}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(one, r) for r in answers]
        for fut in as_completed(futs):
            row = fut.result()
            with lock:
                rows.append(row)
    order = {item_key(r): i for i, r in enumerate(answers)}
    rows.sort(key=lambda r: order[item_key(r)])
    write_csv_atomic(out_path, rows, JUDGE_COLS)
    errs = sum(r["judge_error"] for r in rows)
    print(f"judged n={len(rows)} judge_errors={errs} model={judge_model}")
    print(f"-> {out_path}")


def build_validation_pairs(labels: list[dict], judge: dict[str, dict],
                           *, skip_unlabeled: bool) -> tuple[list[tuple[bool, bool]], int, str]:
    """(pairs, unlabeled_count, judge_model) for the gate.

    A blank `human_supports` is a hard error unless `skip_unlabeled` — partial
    coverage is normal in human labeling, but silently dropping an item would
    shrink the exam, so it must be explicit and counted. A `judge_error` on a
    labeled item always aborts (never score what the judge could not answer).
    """
    pairs: list[tuple[bool, bool]] = []
    unlabeled = 0
    judge_model = ""
    for r in labels:
        val = str(r["human_supports"]).strip().lower()
        if val == "" and skip_unlabeled:
            unlabeled += 1
            continue
        if val not in ("yes", "no"):
            raise SystemExit(f"Error: {item_key(r)}: human_supports must be yes/no, got {val!r}")
        j = judge.get(item_key(r))
        if j is None:
            raise SystemExit(f"Error: no judge row for labeled item {item_key(r)}")
        if int(j["judge_error"] or 0):
            raise SystemExit(f"Error: judge_error on labeled item {item_key(r)} — "
                             f"resolve before validating (never guess)")
        judge_model = judge_model or j["judge_model"]
        pairs.append((val == "yes", j["verdict"] == "supported"))
    return pairs, unlabeled, judge_model


def cmd_validate(args: argparse.Namespace) -> None:
    folder = model_dirs(args.model)[0]
    labels = read_csv_checked(args.labels, required={"dataset", "item_id", "human_supports"},
                              label="human labels")
    judge = {item_key(r): r for r in read_csv_checked(
        args.judge, required={"dataset", "item_id", "verdict", "judge_error"},
        label="judge")}
    pairs, unlabeled, judge_model = build_validation_pairs(
        labels, judge, skip_unlabeled=args.skip_unlabeled)
    n = len(pairs)
    agree = sum(a == b for a, b in pairs)
    agreement = agree / n if n else float("nan")
    kappa = cohen_kappa(pairs)
    gate = gate_passes(n, agreement, kappa)
    out = args.out or folder / f"faithfulness_validation_{args.label}.csv"
    write_csv_atomic(out, [{"label": args.label, "n": n, "agree": agree,
                            "agreement": f"{agreement:.4f}", "kappa": f"{kappa:.4f}",
                            "gate_pass": int(gate), "unlabeled": unlabeled,
                            "judge_model": judge_model,
                            "measurement_card_hash": measurement_card_hash()}],
                     VALID_COLS)
    print(f"n={n} (unlabeled {unlabeled}) agree={agree}/{n} agreement={agreement:.4f} "
          f"kappa={kappa:.4f} gate={'PASS' if gate else 'FAIL'} "
          f"(need ≥{GATE_AGREEMENT:.2f} và κ≥{GATE_KAPPA:.2f})")
    print(f"-> {out}")
    if not gate:
        raise SystemExit("Error: judge did NOT pass the validation gate — one documented "
                         "prompt iteration may follow; a second failure STOPS the measurement "
                         "(no faithfulness score is published).")


def cmd_metrics(args: argparse.Namespace) -> None:
    folder = model_dirs(args.model)[0]
    scores = read_csv_checked(folder / f"reading_cite_scores_{args.label}.csv",
                              required={"dataset", "item_id", "em", "f1", "answer", "citation"},
                              label="cite scores")
    judge_path = args.judge or folder / f"faithfulness_judge_{args.label}.csv"
    judge = {item_key(r): r for r in read_csv_checked(
        judge_path, required={"dataset", "item_id", "verdict", "judge_error",
                              "citation_verbatim"}, label="judge")}
    ctx = _contexts(args)
    judge_model = next(iter(judge.values()))["judge_model"] if judge else ""
    card_hash = measurement_card_hash()

    rows = []
    for r in scores:
        key = item_key(r)
        j = judge.get(key)
        if j is None:
            raise SystemExit(f"Error: no judge row for {key} — run the full judge pass first")
        em = int(r["em"])
        verbatim = citation_verbatim(r["citation"], ctx[(r["dataset"], str(r["item_id"]))])
        if int(j["judge_error"] or 0):
            verdict = ""
        else:
            verdict = j["verdict"]
        rows.append({**r, "em": em, "verbatim": int(verbatim), "verdict": verdict,
                     "judge_error": int(j["judge_error"] or 0)})

    summary = []
    groups: list[tuple[str, list[dict]]] = [(ds, [r for r in rows if r["dataset"] == ds])
                                            for ds in ("squad", "drop")]
    groups.append(("ALL", rows))
    for ds, sub in groups:
        n = len(sub)
        if not n:
            continue
        judged = [r for r in sub if not r["judge_error"]]
        supported = sum(1 for r in judged if r["verdict"] == "supported")
        c_sup = sum(1 for r in judged if r["em"] == 1 and r["verdict"] == "supported")
        c_uns = sum(1 for r in judged if r["em"] == 1 and r["verdict"] != "supported")
        i_sup = sum(1 for r in judged if r["em"] == 0 and r["verdict"] == "supported")
        i_uns = sum(1 for r in judged if r["em"] == 0 and r["verdict"] != "supported")
        compliant = sum(1 for r in sub if r["answer"] and r["citation"])
        verbatim = sum(r["verbatim"] for r in sub)
        summary.append({
            "dataset": ds, "n": n,
            "compliant_count": compliant, "compliance": f"{compliant / n * 100:.2f}",
            "em": f"{sum(r['em'] for r in sub) / n * 100:.2f}",
            "char_f1": f"{sum(float(r['f1']) for r in sub) / n * 100:.2f}",
            "citation_verbatim_count": verbatim,
            "citation_verbatim_rate": f"{verbatim / n * 100:.2f}",
            "judged": len(judged), "judge_errors": n - len(judged),
            "supported": supported,
            "supported_rate": f"{supported / len(judged) * 100:.2f}" if judged else "",
            "correct_and_supported": c_sup, "correct_unsupported": c_uns,
            "incorrect_supported": i_sup, "incorrect_unsupported": i_uns,
            "judge_model": judge_model, "measurement_card_hash": card_hash,
        })
    out = args.out or folder / f"faithfulness_summary_{args.label}.csv"
    write_csv_atomic(out, summary, METRIC_COLS)
    for s in summary:
        print(f"{s['dataset']:<6} n={s['n']:<4} EM={s['em']:<6} compliance={s['compliance']}% "
              f"verbatim={s['citation_verbatim_rate']}% supported={s['supported_rate']}% "
              f"correct∧supported={s['correct_and_supported']} "
              f"correct∧¬sup={s['correct_unsupported']}")
    print(f"-> {out}")


def main() -> None:
    args = parse_args()
    setup_logging(Path("logs") / "legacy" / "judge_faithfulness.log")
    {"sheet": cmd_sheet, "run": cmd_run,
     "validate": cmd_validate, "metrics": cmd_metrics}[args.cmd](args)


if __name__ == "__main__":
    main()
