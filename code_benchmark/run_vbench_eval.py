"""V-Bench public-test runner (vbench.ai, release v2026.03.28).

Third runner in the pipeline family. Consumes the downloaded public test
({id:int, question, choices[], function[], domain}) and produces a
submission.jsonl uploadable at https://vbench.ai/submission. There are NO
gold answers — scoring is server-side and returns only an aggregate, so the
local contract is "parse + validate every row that leaves the checkpoint".

Valid vs correct (gate 1.3) are TWO SEPARATE logs, never one table:
  local   vbench_valid_summary_<model>.csv — syntactic validity per
          (track, domain), recomputed from raw_response; carries
          measurement_card_hash. Written automatically by every run.
  server  vbench_server_scores_<model>.csv — hand-copied official grades
          (the ONLY place a `correct` number may appear), recorded via
          --record-server-scores + --server-source with its own
          measurement_card_hash. The runner never joins the two; any table
          showing both cites both files.

Tracks (confirmed against the Submission & Scoring Spec on the site):
  mc      choices[] non-empty  -> answer is a letter A..E, CLAMPED to the
            actual number of choices on the row (frozen build_prompt /
            extract_answer imported from run_mc_eval, never re-copied).
  agentic function[] non-empty -> answer is [{"<fn_name>": {args}}] picked
            from the row's own schemas; required fields present, enum values
            verbatim. Invalid calls are NEVER shipped — they are dropped and
            counted.
  safety  both empty (hatespeech/politics) -> the current release ignores
            them; skipped at load.

Checkpoints follow the per-model convention (vbench_result_<count>_<slug>.csv)
in all_res/ollama_result/; --resume/--submission-only reuse them.

Run from repo root:
  .venv/bin/python code_benchmark/run_vbench_eval.py --workers 4 [--resume]
  .venv/bin/python code_benchmark/run_vbench_eval.py --submission-only   # rebuild jsonl from latest checkpoint
  .venv/bin/python code_benchmark/run_vbench_eval.py --record-server-scores grades.csv \
      --server-source "vbench.ai grading page v2026.03.28, screenshot 2026-09-04" --model <slug>
"""
import csv
import hashlib
import os
import re
import json
import time
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock
from pathlib import Path

import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import (resolve_endpoint, add_endpoint_args,
                                       parse_endpoint_args, setup_logging,
                                       RESULTS_DIR, sanitize_model, write_csv_atomic)
    from code_benchmark.llm import build_client, verify_credentials, call_model_with_retry
    from code_benchmark.checkpoint import find_latest_checkpoint, checkpoint_name, VBENCH_PREFIX
    from code_benchmark.run_mc_eval import build_prompt, extract_answer
except ImportError:
    from common import (resolve_endpoint, add_endpoint_args,
                        parse_endpoint_args, setup_logging,
                        RESULTS_DIR, sanitize_model, write_csv_atomic)
    from llm import build_client, verify_credentials, call_model_with_retry
    from checkpoint import find_latest_checkpoint, checkpoint_name, VBENCH_PREFIX
    from run_mc_eval import build_prompt, extract_answer

load_dotenv()

VB_FILE_DEFAULT = Path("v_bench/public-test.jsonl")
# Coverage of the v2026.03.28 release (4141 mc + 1000 agentic). Not a hard
# gate — rules change per release — but a mismatch means the local file is
# from another version, exactly the drift the pipeline fails on elsewhere.
VB_SCORED_EXPECTED = 5141

CHECKPOINT_COLS = ["id", "domain", "track", "question", "raw_response", "answer"]

_MC_LETTERS = "ABCDE"
MEASUREMENT_CARD = Path("measurement_card.md")

# Gate 1.3 column contracts — the two logs share NO data column except the
# join keys (track, domain) and the provenance hash. A `correct`/`score`
# column in the valid summary (or a `valid` column in the server snapshot)
# is a layering bug, asserted by the unit tests.
VALID_SUMMARY_COLS = ["track", "domain", "n", "valid", "valid_rate", "measurement_card_hash"]
SERVER_INPUT_COLS = ["domain", "track", "score", "correct", "total"]
SERVER_SCORES_COLS = ["domain", "track", "score", "correct", "total",
                      "measurement_card_hash", "server_source", "recorded_at"]


def measurement_card_hash(path: Path = MEASUREMENT_CARD) -> str:
    """sha256 of the condition document (same rule as score_reading_eval:
    every output carries it; a missing card aborts instead of stamping
    untraceable numbers)."""
    if not path.exists():
        raise SystemExit(f"Error: {path} missing — every scored run must cite a measurement card")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_valid_summary(results: list[dict], card_hash: str) -> list[dict]:
    """Local syntactic validity per (track, domain): a row counts as valid
    when its stored `answer` is non-empty (parsed + schema-validated).
    Pure recompute from results — needs no endpoint, no gold. Carries no
    `correct`/`score` keys by construction."""
    stats: dict[tuple[str, str], list[int]] = {}
    for r in results:
        key = (str(r.get("track", "")), str(r.get("domain", "")))
        cell = stats.setdefault(key, [0, 0])
        cell[0] += 1
        if str(r.get("answer", "")).strip():
            cell[1] += 1
    rows = []
    for (track, domain) in sorted(stats):
        n, valid = stats[(track, domain)]
        rows.append({"track": track, "domain": domain, "n": n, "valid": valid,
                     "valid_rate": round(100.0 * valid / n, 2) if n else 0.0,
                     "measurement_card_hash": card_hash})
    return rows


def read_server_scores(path: Path) -> list[dict]:
    """Fail-fast read of the hand-copied server grade table: exact header
    domain,track,score,correct,total (per-domain rows — macro/micro averages
    are reporting recomputes, never stored rows). Each row must satisfy
    0 <= correct <= total and score == 100*correct/total (±0.05); anything
    else is a wrong-file pairing, never silently kept."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        if (rdr.fieldnames or []) != SERVER_INPUT_COLS:
            raise SystemExit(f"Error: server-scores {path} header mismatch — expected exactly "
                             f"{SERVER_INPUT_COLS}, got {rdr.fieldnames}")
        raw = list(rdr)
    if not raw:
        raise SystemExit(f"Error: empty server-scores {path}")
    grades = []
    seen: set[tuple[str, str]] = set()
    for lineno, r in enumerate(raw, 2):
        domain, track = str(r["domain"]).strip(), str(r["track"]).strip()
        if not domain or not track:
            raise SystemExit(f"Error: server-scores {path}:{lineno}: domain/track must be non-empty")
        try:
            correct = int(str(r["correct"]).strip())
            total = int(str(r["total"]).strip())
            score = float(str(r["score"]).strip())
        except ValueError as e:
            raise SystemExit(f"Error: server-scores {path}:{lineno}: "
                             "correct/total must be ints, score a float") from e
        if total <= 0 or not 0 <= correct <= total:
            raise SystemExit(f"Error: server-scores {path}:{lineno}: need 0 <= correct <= total, total > 0")
        if not 0.0 <= score <= 100.0:
            raise SystemExit(f"Error: server-scores {path}:{lineno}: score must be 0..100")
        if abs(score - 100.0 * correct / total) > 0.05:
            raise SystemExit(f"Error: server-scores {path}:{lineno}: score {score} != "
                             f"100*correct/total ({100.0 * correct / total:.2f}) — wrong table?")
        if (domain, track) in seen:
            raise SystemExit(f"Error: server-scores {path}:{lineno}: duplicate row for "
                             f"domain={domain} track={track}")
        seen.add((domain, track))
        grades.append({"domain": domain, "track": track, "score": score,
                       "correct": correct, "total": total})
    return grades


def write_server_snapshot(path: Path, grades: list[dict], card_hash: str, source: str) -> None:
    """Stamp validated server grades with provenance. The ONLY writer of a
    `correct` column in this pipeline; never called during inference."""
    if not source or not source.strip():
        raise SystemExit("Error: --server-source must be non-empty provenance "
                         "(e.g. 'vbench.ai grading page v2026.03.28, screenshot 2026-09-04')")
    stamped = [dict(g, measurement_card_hash=card_hash, server_source=source.strip(),
                    recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
               for g in grades]
    write_csv_atomic(path, stamped, SERVER_SCORES_COLS)


# ── Row classification (fail-fast on contract drift) ────────────────────────

def classify_track(row: dict) -> str:
    """'mc' | 'agentic' | 'safety' from one public-test row. A row carrying
    BOTH choices and function is contract drift (the release keeps tracks
    disjoint) and aborts the run."""
    has_choices = bool(row.get("choices"))
    has_function = bool(row.get("function"))
    if has_choices and has_function:
        raise SystemExit(f"Contract drift: item id={row.get('id')} carries both "
                         "choices and function — tracks must be disjoint.")
    if has_choices:
        return "mc"
    if has_function:
        return "agentic"
    return "safety"


def load_vbench(path: Path) -> list[dict]:
    """Read + validate public-test.jsonl, keep the scorable rows (mc/agentic),
    skip safety rows (counted and logged). Fail-fast on duplicate ids and
    missing required keys."""
    if not path.exists():
        raise SystemExit(f"Error: V-Bench public test not found at '{path}'. "
                         "Download it from https://vbench.ai/dataset.")
    rows: list[dict] = []
    seen: set[int] = set()
    n_safety = 0
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            missing = {"id", "question", "choices", "function", "domain"} - set(row)
            if missing:
                raise SystemExit(f"Malformed row at {path}:{lineno}: missing {sorted(missing)}")
            if row["id"] in seen:
                raise SystemExit(f"Duplicate id {row['id']} at {path}:{lineno}")
            seen.add(row["id"])
            row["track"] = classify_track(row)
            if row["track"] == "safety":
                n_safety += 1
                continue
            if row["track"] == "mc" and len(row["choices"]) > len(_MC_LETTERS):
                raise SystemExit(f"Item id={row['id']} has {len(row['choices'])} choices — "
                                 f"beyond the frozen {_MC_LETTERS[-1]}-letter extraction range.")
            rows.append(row)
    if not rows:
        raise SystemExit(f"Error: no scorable (mc/agentic) rows in {path}")
    logging.info(f"Loaded {len(rows)} scorable rows "
                 f"({sum(r['track'] == 'mc' for r in rows)} mc / "
                 f"{sum(r['track'] == 'agentic' for r in rows)} agentic); "
                 f"{n_safety} safety rows skipped (not scored in this release).")
    if len(rows) != VB_SCORED_EXPECTED:
        logging.warning(f"Release drift: expected {VB_SCORED_EXPECTED} scorable rows "
                        f"(v2026.03.28), found {len(rows)}. Update after checking the site.")
    return rows


# ── MC: frozen parser + per-row letter clamp ────────────────────────────────

def extract_mc_answer(raw_text: str, choices: list) -> str:
    """Frozen extract_answer, then clamp: a letter beyond the row's actual
    option count (e.g. 'E' on 4 choices) is NOT a valid submission value."""
    letter = extract_answer(raw_text)
    if not letter:
        return ""
    return letter if letter in _MC_LETTERS[:len(choices)] else ""


# ── Agentic: prompt + validated function-call extraction ────────────────────

def build_agentic_prompt(question: str, functions: list, style: str = "minimal") -> str:
    """`minimal` (default) sends the question + the row's own function schema
    plus ONLY the official answer-format line — no rule restatement, no
    format example, no 'do not explain' instruction. Anything more measures
    the prompt, not the model, and pre-empts the few-shot/CoT conditions we
    want to ablate ourselves. `detailed` keeps the full-guidance variant as
    an explicit comparison condition (used by the first full run)."""
    schema_json = json.dumps(functions, ensure_ascii=False, separators=(",", ":"))
    if style == "minimal":
        return (question
                + "\n\nDanh sách hàm (JSON):\n" + schema_json
                + "\n\nTrả lời duy nhất bằng JSON theo khuôn: "
                  "[{\"<tên_hàm>\": {\"<tham_số>\": <giá_trị>}}]\n")
    return (
        "Bạn là trợ lý AI có khả năng gọi hàm. Chọn ĐÚNG MỘT hàm phù hợp nhất "
        "với yêu cầu dưới đây và điền đầy đủ tham số theo sơ đồ của hàm đó.\n"
        "Quy tắc:\n"
        "- Chỉ được dùng tên hàm có trong danh sách hàm cho trước.\n"
        "- Mọi tham số bắt buộc (required) phải có mặt; tham số có enum phải "
        "dùng đúng một giá trị liệt kê trong enum.\n"
        "- Chỉ trả về duy nhất một mảng JSON một phần tử, mỗi phần tử là một "
        "object trong ngoặc nhọn, theo đúng khuôn: "
        "[{\"<tên_hàm>\": {\"<tham_số>\": \"<giá_trị>\"}}]. "
        "Ví dụ: [{\"tra_cuu_thoi_tiet\": {\"thanh_pho\": \"Ha Noi\"}}]. "
        "Không giải thích.\n\n"
        "Yêu cầu của người dùng:\n"
        + question
        + "\n\nDanh sách hàm (JSON):\n"
        + schema_json
        + "\n\nĐầu ra:\n"
    )


def _as_object(candidate):
    """Normalize a candidate (str | dict | list) to a parsed Python object."""
    if isinstance(candidate, str):
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            return None
    return candidate


def _iter_json_candidates(raw: str):
    """Yield parse attempts in confidence order: fenced ```json``` blocks
    first, then the whole text, then every substring that starts with [ or {
    (raw_decode scan). Never guesses across two candidate arrays."""
    text = raw.strip()
    if not text:
        return
    for m in re.finditer(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL):
        yield m.group(1)
    yield text
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = dec.raw_decode(text, i)
            except ValueError:
                continue
            yield obj


def _validate_call(call_obj, functions: list[dict]) -> list | None:
    """One candidate object -> [{"name": args}] (normalized) or None.
    Rejects: non-dict/single-key shapes, unknown names, non-dict args,
    missing required fields, extra fields outside the schema, and enum
    values not verbatim in the enum list. No coercion — the backend
    compares key/value after normalization, we ship exactly what validated."""
    if not isinstance(call_obj, dict) or len(call_obj) != 1:
        return None
    name, args = next(iter(call_obj.items()))
    schema = next((fn for fn in functions if fn.get("name") == name), None)
    if schema is None or not isinstance(args, dict):
        return None
    props: dict = (schema.get("parameters") or {}).get("properties") or {}
    required: list = (schema.get("parameters") or {}).get("required") or []
    if any(r not in args for r in required):
        return None
    if any(k not in props for k in args):
        return None
    for key, val in args.items():
        enum = props[key].get("enum")
        if enum is not None and val not in enum:
            return None
    return [{name: args}]


def extract_function_call(raw_text: str, functions: list[dict]) -> str:
    """Model output -> canonical compact JSON '[{"name":{...}}]' or '' when
    no candidate validates (never ship a malformed call). An array with
    several calls contributes its first element only."""
    for cand in _iter_json_candidates(raw_text or ""):
        obj = _as_object(cand)
        if isinstance(obj, dict):
            calls = [obj]
        elif isinstance(obj, list) and obj:
            calls = obj
        else:
            continue
        for call in calls:
            norm = _validate_call(call, functions)
            if norm is not None:
                return json.dumps(norm, ensure_ascii=False, separators=(",", ":"))
    return _repair_braceless_call(raw_text or "", functions)

def _repair_braceless_call(raw: str, functions: list[dict]) -> str:
    """Recover from the shape models actually emit here: '["<name>": {args}]'
    — a quoted call name with its braces dropped (968/1000 raw responses of
    the v2026.03.28 smoke run). Scan every '"token": {' position, raw_decode
    the args object that starts there, and validate {name: args} through the
    SAME _validate_call gate — a name not on this row's schema, a missing
    required field, or an off-enum value still returns ''. Truncated args
    fail raw_decode, so cut-off completions stay unparsed (correct)."""
    dec = json.JSONDecoder()
    for m in re.finditer(r'"([^\W"]{2,})"\s*:\s*(?=\{)', raw):
        try:
            args, _ = dec.raw_decode(raw, m.end())
        except ValueError:
            continue
        norm = _validate_call({m.group(1): args}, functions)
        if norm is not None:
            return json.dumps(norm, ensure_ascii=False, separators=(",", ":"))
    return ""


def diagnose_rejection(raw: str, functions: list[dict]) -> str:
    """Why did an agentic row end up unparsed? Never mutates the model's
    answer — this only labels it for the record: a readable call with a
    name off the row's schema is a MODEL ERROR (wrong function chosen),
    not a parser failure, and must be logged as such."""
    if extract_function_call(raw, functions):
        return ""
    dec = json.JSONDecoder()
    names = {fn.get("name") for fn in functions}
    saw_call_shape = False
    for m in re.finditer(r'"([^\W"]{2,})"\s*:\s*(?=\{)', raw or ""):
        saw_call_shape = True
        name = m.group(1)
        try:
            args, _ = dec.raw_decode(raw, m.end())
        except ValueError:
            return "truncated_output"
        if name not in names:
            return "unknown_function_name"
        norm = _validate_call({name: args}, functions)
        if norm is not None:
            return ""   # race-free: repaired elsewhere; keep consistent
        schema = next(fn for fn in functions if fn.get("name") == name)
        props = (schema.get("parameters") or {}).get("properties") or {}
        required = (schema.get("parameters") or {}).get("required") or []
        if any(r not in args for r in required):
            return "missing_required_arg"
        if any(k not in props for k in args):
            return "hallucinated_arg"
        if any(props[k].get("enum") is not None and args[k] not in props[k]["enum"]
               for k in args):
            return "off_enum_value"
        return "schema_violation"
    return "no_call_shape_found" if not saw_call_shape else "unparseable_output"


# ── Guided mode: numbered-question interview per agentic row ───────────────

_CHOICE_NUM = re.compile(r"(?<![\w.])(\d{1,2})(?![\w])(?!\.\d)")
_SKIP_ANSWERS = {"0", "-", "bo qua", "bỏ qua", "skip", "khong", "không"}


def parse_choice(raw: str, n: int) -> int | None:
    """Numbered-choice answer -> 1-based index: first standalone number in
    range wins ('2', 'Đáp án: 2', '2. …'). None when nothing in 1..n appears
    — we never default the model's selection."""
    for m in _CHOICE_NUM.finditer(raw or ""):
        v = int(m.group(1))
        if 1 <= v <= n:
            return v
    return None


def parse_value(raw: str, spec: dict):
    """Free-text typed answer -> JSON value, or None when absent/garbage.
    Only number/bool coercion of the model's own text; strings are kept
    verbatim (first line). Never invents a value."""
    s = (raw or "").strip().strip("`").strip()
    if not s:
        return None
    s = s.splitlines()[0].strip()
    t = spec.get("type")
    if t in ("number", "integer"):
        m = re.search(r"-?\d+(?:[.,]\d+)?", s)
        if not m:
            return None
        num = m.group(0).replace(",", ".")
        return int(num) if (t == "integer" or re.fullmatch(r"\d+", num)) else float(num)
    if t == "boolean":
        low = s.lower()
        if low.startswith(("true", "có", "co ", "đúng", "dong", "1")):
            return True
        if low.startswith(("false", "không", "khong", "sai", "0")):
            return False
        return None
    return s.strip("\"'”“’‘")


def _num_list(items: list[str]) -> str:
    return "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items))


def guided_call(item: dict, ask) -> tuple[str, list[str]]:
    """Ask one agentic row as a numbered interview (choose function, then one
    question per parameter — enums as lists, scalars type-hinted); returns
    (canonical validated answer or '', transcript). The model makes exactly
    the semantic decisions of free generation; the tool only supplies JSON
    syntax. The assembled call passes the SAME _validate_call gate; an
    unanswered required field leaves the row failed, marked
    [GUIDED-FAIL …] in the transcript — never filled in by us."""
    fns = item["function"]
    tr: list[str] = []

    def step(prompt: str, kind: str) -> str:
        raw = ask(prompt)
        tr.append(f"Q[{kind}]\n{prompt}\nA\n{raw}")
        return raw

    head = ("Hãy chọn ĐÚNG MỘT hàm phù hợp nhất với yêu cầu. "
            "Chỉ trả lời bằng SỐ của lựa chọn, không giải thích.\n\nYêu cầu:\n"
            + item["question"] + "\n\nCác lựa chọn:\n"
            + _num_list([f"{fn.get('name')} — {fn.get('description', '')}" for fn in fns])
            + "\n\nSố:")
    ch = parse_choice(step(head, "function"), len(fns))
    if ch is None:
        tr.append("[GUIDED-FAIL no_function_choice]")
        return "", tr
    schema = fns[ch - 1]
    params = schema.get("parameters") or {}
    props: dict = params.get("properties") or {}
    required: list = params.get("required") or []
    order = [k for k in required if k in props] + [k for k in props if k not in required]
    args: dict = {}
    for key in order:
        spec = props[key]
        is_req = key in required
        req_tag = "(bắt buộc)" if is_req else "(không bắt buộc — trả lời 0 để bỏ qua)"
        desc = spec.get("description") or spec.get("type") or ""
        enum: list = spec.get("enum") or []
        if enum:
            p = (f'Hàm "{schema["name"]}" — tham số "{key}" {req_tag}: {desc}\n'
                 "Chỉ trả lời bằng SỐ của lựa chọn.\n"
                 + _num_list([str(e) for e in enum]) + "\n\nSố:")
            c = parse_choice(step(p, f"arg:{key}"), len(enum))
            if c is None:
                if is_req:
                    tr.append(f"[GUIDED-FAIL unanswered_required:{key}]")
                    return "", tr
                continue
            args[key] = enum[c - 1]
        else:
            hint = {"number": "một số", "integer": "một số nguyên",
                    "boolean": "true hoặc false", "array": "một JSON mảng",
                    "object": "một JSON object"}.get(spec.get("type"), "một giá trị")
            p = (f'Hàm "{schema["name"]}" — tham số "{key}" {req_tag}: {desc}\n'
                 f"Chỉ trả lời bằng {hint}, không giải thích.\n\nGiá trị:")
            raw = step(p, f"arg:{key}")
            if not is_req and raw.strip().lower() in _SKIP_ANSWERS:
                continue
            v = parse_value(raw, spec)
            if v is None:
                if is_req:
                    tr.append(f"[GUIDED-FAIL unanswered_required:{key}]")
                    return "", tr
                continue
            args[key] = v
    norm = _validate_call({schema["name"]: args}, fns)
    if norm is None:
        tr.append("[GUIDED-FAIL schema_validation]")
        return "", tr
    tr.append(f"ASSEMBLED: {norm}")
    return json.dumps(norm, ensure_ascii=False, separators=(",", ":")), tr


def write_model_errors(path: Path, results: list[dict], by_id: dict[int, dict]) -> None:
    """Durable record of every row the model failed to answer validly. The
    submission contract forbids guessing an answer in place of a wrong one —
    but 'not shipped' must never mean 'not recorded': each rejected answer is
    preserved verbatim (raw_response) with a diagnosis label."""
    rows = []
    for r in results:
        if str(r.get("answer", "")).strip():
            continue
        item = by_id.get(int(r["id"]))
        reason = "parse_failure"
        if item and item["track"] == "agentic":
            gm = re.search(r"\[GUIDED-FAIL ([\w:]+)\]", r["raw_response"])
            reason = (f"guided_{gm.group(1)}" if gm
                      else diagnose_rejection(r["raw_response"], item["function"]))
        rows.append({"id": r["id"], "domain": r["domain"], "track": r["track"],
                     "reason": reason, "raw_response": r["raw_response"]})
    if not rows:
        path.unlink(missing_ok=True)   # stale ledger from an earlier pass must not survive
        return
    write_csv_atomic(path, rows, ["id", "domain", "track", "reason", "raw_response"])
    logging.warning(f"{len(rows)} model failure(s) recorded verbatim to {path} "
                    "(NOT auto-corrected — a wrong answer stays wrong):")
    for grp, n in pd.DataFrame(rows).groupby("reason").size().items():
        logging.warning(f"    {grp:<24} {n}")


def build_submission_rows(results: list[dict]) -> list[dict]:
    """Parsed checkpoint rows -> {id, answer} submission rows, id-sorted.
    MC answer stays a letter; agentic answer is re-parsed so the JSONL line
    carries a real array, not a string. Unparsed rows are dropped (missing id
    = no points server-side; a fabricated guess is not)."""
    rows = []
    for r in results:
        ans = str(r.get("answer", "")).strip()
        if not ans:
            continue
        if r["track"] == "agentic":
            ans = json.loads(ans)
        rows.append({"id": int(r["id"]), "answer": ans})
    return sorted(rows, key=lambda x: x["id"])


def write_submission_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


def log_track_stats(results: list[dict]) -> None:
    """Console-only mirror of the durable valid summary (syntax, not score).
    Correctness never appears here — see vbench_server_scores_*.csv."""
    df = pd.DataFrame(results)
    df["ok"] = df["answer"].astype(str) != ""
    for track, grp in df.groupby("track"):
        logging.info(f"[{track}] parsed {int(grp['ok'].sum())}/{len(grp)}")
        for domain, d in grp.groupby("domain"):
            logging.info(f"    {domain:<22} {int(d['ok'].sum()):>4}/{len(d)}")


# ── CLI + runner ────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Run models on the V-Bench public test and build an uploadable submission.")
    parser.add_argument("--file", type=Path, default=VB_FILE_DEFAULT,
                        help="public-test.jsonl path (default: v_bench/public-test.jsonl)")
    parser.add_argument("--track", choices=["all", "mc", "agentic"], default="all",
                        help="subset of scorable tracks to run (default: all)")
    parser.add_argument("--submission-out", type=Path, default=None,
                        help="submission jsonl path (default: data/submission_vbench_<model>.jsonl)")
    parser.add_argument("--submission-only", action="store_true",
                        help="skip inference; rebuild submission + stats from the latest checkpoint")
    parser.add_argument("--retry-unparsed", action="store_true",
                        help="with --resume: re-call only rows whose stored/raw response "
                             "does not parse under the CURRENT parser (correct model errors are "
                             "never touched)")
    parser.add_argument("--guided", action="store_true",
                        help="with --resume: re-ask agentic rows that have no valid answer as a "
                             "numbered interview (function, then one question per parameter); the "
                             "tool supplies JSON syntax only, the model makes every decision")
    parser.add_argument("--prompt-style", choices=["minimal", "detailed"], default="minimal",
                        help="agentic prompt condition: minimal = question + schema + official "
                             "format line only (default); detailed = full-guidance variant. Use a "
                             "distinct --model slug per condition to keep checkpoints separate")
    parser.add_argument("--record-server-scores", type=Path, default=None,
                        help="record a hand-copied server grade table and exit (no inference): CSV "
                             "with exact header domain,track,score,correct,total (per-domain rows; "
                             "macro/micro averages are reporting recomputes, never stored). Writes "
                             "vbench_server_scores_<model>.csv — the ONLY place `correct` may appear.")
    parser.add_argument("--server-source", type=str, default=None,
                        help="provenance label for --record-server-scores "
                             "(e.g. 'vbench.ai grading page v2026.03.28, screenshot 2026-09-04')")

    add_endpoint_args(parser,
                      max_tokens_default=512,
                      max_tokens_help="Completion cap; agentic calls need the room (default: 512).",
                      resume_help="Resume from the latest vbench_result_* checkpoint for THIS model.")
    return parse_endpoint_args(parser)


def prepare_prompt(item: dict, style: str = "minimal") -> str:
    if item["track"] == "mc":
        return build_prompt(item["question"], item["choices"])
    return build_agentic_prompt(item["question"], item["function"], style)


def parse_item(item: dict, raw_response: str) -> str:
    """Parsed submission value as string (letter, or compact JSON)."""
    if item["track"] == "mc":
        return extract_mc_answer(raw_response, item["choices"])
    return extract_function_call(raw_response, item["function"])


def load_checkpoint(path: Path, by_id: dict[int, dict] | None = None) -> list[dict]:
    """Checkpoint rows -> result dicts. When the source items are given, the
    `answer` is RE-DERIVED from raw_response with the current parser — the
    stored column is a snapshot of the parser at write time, so a fixed or
    improved extractor applies to an existing run without re-calling the
    endpoint (server scoring is aggregate-only; raw_response is the truth).
    Exception: GUIDED rows keep the stored answer — their raw_response is an
    interview transcript whose call only exists once assembled; re-parsing
    free text would silently delete guided results."""
    cp_df = pd.read_csv(path, dtype={"id": "int64"})
    rows = []
    for _, row in cp_df.iterrows():
        raw = row.get("raw_response", "")
        raw = "" if pd.isna(raw) else str(raw)
        item_id = int(row["id"])
        item = by_id.get(item_id) if by_id else None
        transcript = raw.startswith("Q[function]") or "[GUIDED-FAIL" in raw
        if item is not None and raw and not transcript:
            answer = parse_item(item, raw)
        else:
            answer = "" if pd.isna(row.get("answer")) else str(row["answer"])
        rows.append({
            "id": item_id,
            "domain": str(row["domain"]),
            "track": str(row["track"]),
            "question": str(row.get("question", "")),
            "raw_response": raw,
            "answer": answer,
        })
    return rows


def write_final_outputs(args, model, results, result_folder, by_id):
    sanitized = sanitize_model(model)
    card_hash = measurement_card_hash()
    out_path = args.submission_out or Path(f"data/submission_vbench_{sanitized}.jsonl")
    rows = build_submission_rows(results)
    write_submission_jsonl(out_path, rows)
    logging.info(f"Submission written to {out_path} ({len(rows)} rows)")
    pd.DataFrame(results)[CHECKPOINT_COLS].to_csv(
        result_folder / f"vbench_full_evaluation_{sanitized}.csv", index=False)
    valid_rows = build_valid_summary(results, card_hash)
    valid_path = result_folder / f"vbench_valid_summary_{sanitized}.csv"
    write_csv_atomic(valid_path, valid_rows, VALID_SUMMARY_COLS)
    logging.info(f"Valid summary written to {valid_path} "
                 f"({sum(r['valid'] for r in valid_rows)}/{sum(r['n'] for r in valid_rows)} locally valid; "
                 "syntax only — NOT correctness)")
    logging.info(f"measurement_card_hash={card_hash}")
    log_track_stats(results)
    write_model_errors(result_folder / f"vbench_failures_{sanitized}.csv", results, by_id)


def main():
    args = parse_args()
    if (args.retry_unparsed or args.guided) and not args.resume:
        raise SystemExit("Error: --retry-unparsed/--guided are --resume modifiers (they re-call "
                         "the unparsed rows of an existing checkpoint); add --resume.")
    result_folder = RESULTS_DIR
    result_folder.mkdir(parents=True, exist_ok=True)

    if args.record_server_scores is not None:
        if args.submission_only:
            raise SystemExit("Error: --record-server-scores and --submission-only are separate modes; pick one.")
        if not args.server_source or not args.server_source.strip():
            raise SystemExit("Error: --record-server-scores needs --server-source provenance "
                             "(e.g. 'vbench.ai grading page v2026.03.28, screenshot 2026-09-04').")
        model = args.model or os.environ.get("OPENAI_MODEL")
        if not model:
            raise SystemExit("Error: OPENAI_MODEL is not set. Provide --model so the snapshot stays per-model.")
        setup_logging(Path("logs") / f"vbench_{sanitize_model(model)}.log")
        card_hash = measurement_card_hash()
        grades = read_server_scores(args.record_server_scores)
        snap_path = result_folder / f"vbench_server_scores_{sanitize_model(model)}.csv"
        write_server_snapshot(snap_path, grades, card_hash, args.server_source)
        logging.info(f"Server snapshot recorded to {snap_path} ({len(grades)} domain rows; "
                     "correctness lives ONLY here, never in the valid summary).")
        return

    base_url, api_key, model = resolve_endpoint(args)
    sanitized_model = sanitize_model(model)
    setup_logging(Path("logs") / f"vbench_{sanitized_model}.log")
    logging.info(f"Model: {model} | Base URL: {base_url} | workers: {args.workers} "
                 f"| agentic prompt-style: {args.prompt_style}")

    data = load_vbench(args.file)
    if args.track != "all":
        data = [d for d in data if d["track"] == args.track]
    if args.limit:
        data = data[:args.limit]
    total = len(data)
    by_id = {d["id"]: d for d in data}

    if args.submission_only:
        latest = find_latest_checkpoint(result_folder, model, prefix=VBENCH_PREFIX)
        if not latest:
            raise SystemExit("Error: --submission-only needs a vbench_result_* "
                             f"checkpoint for model '{model}' in {result_folder}")
        logging.info(f"Rebuilding submission from checkpoint: {latest}")
        write_final_outputs(args, model, load_checkpoint(latest, by_id), result_folder, by_id)
        return

    for item in data:
        item["prompt"] = prepare_prompt(item, args.prompt_style)

    client = build_client(base_url, api_key)
    logging.info("Verifying endpoint connectivity and credentials...")
    verify_credentials(client, model)
    logging.info("Credentials verified successfully.")

    existing: dict[int, dict] = {}
    if args.resume:
        latest = find_latest_checkpoint(result_folder, model, prefix=VBENCH_PREFIX)
        if latest:
            logging.info(f"Resuming from checkpoint: {latest}")
            existing = {r["id"]: r for r in load_checkpoint(latest, by_id)}
            if args.retry_unparsed or args.guided:
                keep = {k: v for k, v in existing.items() if str(v["answer"]).strip()}
                logging.info(f"--{'guided' if args.guided else 'retry-unparsed'}: re-asking "
                             f"{len(existing) - len(keep)} unparsed row(s); {len(keep)} kept verbatim.")
                existing = keep
        else:
            logging.warning(f"No {VBENCH_PREFIX}*_{sanitized_model}.csv checkpoint found; "
                            "starting fresh.")

    results: list[dict | None] = [None] * total
    to_process = []
    for idx, item in enumerate(data):
        if item["id"] in existing:
            results[idx] = existing[item["id"]]
        else:
            to_process.append((idx, item))
    logging.info(f"Remaining to evaluate: {len(to_process)}/{total}")

    lock = Lock()
    completed = len(existing)
    start_time = time.time()

    def process_item(index: int, item: dict):
        nonlocal completed
        if args.guided and item["track"] == "agentic":
            def ask(prompt: str) -> str:
                return call_model_with_retry(
                    client=client, model=model, prompt=prompt,
                    temperature=args.temperature, seed=args.seed, max_tokens=64)
            ans, transcript = guided_call(item, ask)
            raw_ans, parsed = "\n\n---\n\n".join(transcript), ans
        else:
            raw_ans = call_model_with_retry(
                client=client, model=model, prompt=item["prompt"],
                temperature=args.temperature, seed=args.seed, max_tokens=args.max_tokens)
            parsed = parse_item(item, raw_ans)
        res = {
            "id": item["id"],
            "domain": item["domain"],
            "track": item["track"],
            "question": item["question"],
            "raw_response": raw_ans,
            "answer": parsed,
        }
        with lock:
            results[index] = res
            completed += 1
            if completed % 100 == 0 or completed == total:
                valid = [r for r in results if r is not None]
                pd.DataFrame(valid)[CHECKPOINT_COLS].to_csv(
                    result_folder / checkpoint_name(model, len(valid), prefix=VBENCH_PREFIX),
                    index=False)
        return index

    if to_process:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_item, idx, item): idx for idx, item in to_process}
            with tqdm(total=total, initial=len(existing), desc=f"V-Bench {model}") as pbar:
                for future in as_completed(futures):
                    future.result()
                    pbar.update(1)
    else:
        logging.info("All rows already resolved from checkpoint.")

    duration = time.time() - start_time
    logging.info(f"Inference time: {duration:.2f}s ({duration/60:.2f} mins)")
    write_final_outputs(args, model, [r for r in results if r is not None], result_folder, by_id)
    logging.info("Upload the submission at https://vbench.ai/submission")


if __name__ == "__main__":
    main()
