#!/usr/bin/env python3
"""Calibrate the TRUE Gemini token count of every distilled answer (Issue #10).

Replaces the k-convention denominator (~195.6K, word-count × assumed coefficient)
with measured numbers: each of the 1,389 distilled answers is sent back to the
same model through commandcode.ai as a user message, and the tokenizer's own
count is recovered as

    tokens(text) = prompt_tokens(text) − C

where C (the chat-template frame: role markers, special tokens) is calibrated
once per run and verified with a linearity check. Cache cannot interfere
(tiny prompts, far below the 4.096 implicit-cache threshold) and the input
side carries no reasoning tokens.

Run from repo root (stdlib only, ~0.2 credits, ~10-15 min):
  .venv/bin/python tools/antigravity_ledger/calibrate_k.py
Outputs: all_res/antigravity_resource_ledger/answer_tokens.csv + summary table.
Resume-safe: finished answers are skipped (checkpoint rewritten every 100).
"""
from __future__ import annotations

import csv
import glob
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ISSUE10_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "all_res", "antigravity_gemini"))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "all_res", "antigravity_resource_ledger"))
OUT_CSV = os.path.join(OUT_DIR, "answer_tokens.csv")
ENV_PATH = os.path.normpath(os.path.join(HERE, "..", "probe_token_usage", ".env"))

# file tag -> ledger domain tag (same vocabulary as extract.py)
ISSUE10_TAG = {
    "math": "math", "logic": "logics", "drop": "drop", "agentic": "agentic",
    "physics": "physics", "other": "vmlu_other", "legal": "vmlu_legal",
    "laws": "laws", "dialect": "dialect", "squad": "squad",
    "chemistry": "chemistry", "medicine": "medicine", "cs": "cs",
}
CONVENTION_DISTILLED = 195_630      # Issue #10 §4.1 estimate (for the delta line)
NET_TOTAL = 59_066_768              # campaign-wide net (ledger)
NET_SOLVING = 41_694_408            # solving-only net (ledger)
WORKERS = 8
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def load_env() -> tuple[str, str]:
    env = {}
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    base = env.get("COMMANDCODE_BASE_URL", "").rstrip("/")
    key = env.get("COMMANDCODE_API_KEY", "")
    if not base or not key:
        raise SystemExit(f"Error: COMMANDCODE_BASE_URL/API_KEY missing in {ENV_PATH}")
    return base, key


BASE, API_KEY = load_env()
CTX = ssl._create_unverified_context()


def api_prompt_tokens(content: str, timeout: int = 90) -> int:
    """One chat request; returns prompt_tokens as reported by the provider."""
    body = json.dumps({"model": "google/gemini-3.8-flash", "max_tokens": 1,
                       "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request(
        BASE + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json",
                 "User-Agent": UA, "Accept": "application/json"})
    last = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                d = json.load(r)
            return int(d["usage"]["prompt_tokens"])
        except urllib.error.HTTPError as e:
            code = e.code
            if code in (401, 403):
                raise SystemExit(f"Error: auth rejected ({code}) — check the API key.")
            last = f"HTTP {code}: {e.read()[:120]!r}"
            time.sleep(30 if code == 429 else 5 * attempt)
        except Exception as e:
            last = str(e)[:150]
            time.sleep(5 * attempt)
    raise RuntimeError(f"prompt_tokens failed after 3 attempts: {last}")


def calibrate_accounting() -> int:
    """Establish the content-token accounting. Empirically this gateway reports
    prompt_tokens WITHOUT the chat-template frame (" "→1, "D"→1, "24,10%"→6),
    so C = 0 and tokens(text) = prompt_tokens(text) directly. Fail loudly if a
    frame ever appears (accounting change would invalidate the whole run)."""
    probes = {" ": 1, "D": 1, "PONG": 2, "24,10%": 6}
    for content, expect_max in probes.items():
        got = api_prompt_tokens(content)
        if got > expect_max:
            raise SystemExit(f"Error: prompt accounting has a frame now — "
                             f"prompt({content!r})={got}, expected ≤{expect_max}. "
                             "Re-calibrate before trusting any count.")
    print(f"[calibration] frame-free accounting confirmed (\" \"→1, \"D\"→1, "
          f"\"24,10%\"→6) → C = 0")
    return 0


def linearity_check(C: int, texts: list[str]) -> None:
    """T(a+SEP+b) must equal T(a) + T(SEP) + T(b) — tokenization is additive."""
    a, b = texts[0], texts[1]
    sep = "\n"
    ta, tb, tsep = api_prompt_tokens(a), api_prompt_tokens(b), api_prompt_tokens(sep)
    tab = api_prompt_tokens(a + sep + b)
    delta = tab - (ta + tsep + tb)
    print(f"[calibration] linearity: T(a)={ta} T(b)={tb} T(sep)={tsep} T(a+sep+b)={tab} "
          f"delta={delta:+d} ({'OK' if abs(delta) <= 2 else 'SUSPECT'})")


def load_answers() -> list[dict]:
    rows = []
    for f in sorted(glob.glob(os.path.join(ISSUE10_DIR, "results_batch_*.csv"))):
        name = os.path.basename(f)
        tag = name.split("_")[2]
        domain = ISSUE10_TAG.get(tag, tag)
        batch = int(name.rsplit("_", 1)[1].split(".")[0])
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                ans = (r.get("answer") or "").strip()
                if not ans:
                    raise SystemExit(f"Error: empty answer in {name} id={r.get('id') or r.get('item_id')}")
                rows.append({"domain": domain, "batch": batch,
                             "item_id": str(r.get("id") or r.get("item_id")),
                             "answer": ans, "words": len(ans.split())})
    return rows


def main() -> None:
    answers = load_answers()
    print(f"[load] {len(answers)} answers from {ISSUE10_DIR}")
    C = calibrate_accounting()
    linearity_check(C, [a["answer"] for a in answers])

    # resume support
    done: dict[str, tuple[int, int]] = {}
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                done[r["answer"]] = (int(r["prompt_tokens"]), int(r["true_tokens"]))
        print(f"[resume] {len(done)} answers already measured")
    todo = [a for a in answers if a["answer"] not in done]
    print(f"[run] {len(todo)} to measure (workers={WORKERS})")

    fields = ["domain", "batch", "item_id", "words", "prompt_tokens", "true_tokens", "answer"]
    failures: list[str] = []
    measured = 0

    def measure(ans: str) -> tuple[int, int]:
        pt = api_prompt_tokens(ans)
        return pt, pt - C

    def flush() -> None:
        rows = []
        for a in answers:
            if a["answer"] in done:
                pt, tt = done[a["answer"]]
                rows.append({**{k: a[k] for k in ("domain", "batch", "item_id", "words")},
                             "prompt_tokens": pt, "true_tokens": tt, "answer": a["answer"]})
        tmp = OUT_CSV + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, OUT_CSV)

    if todo:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(measure, a["answer"]): a for a in todo}
            for fut in as_completed(futs):
                a = futs[fut]
                try:
                    done[a["answer"]] = fut.result()
                    measured += 1
                except Exception as e:
                    failures.append(f"{a['domain']}:{a['item_id']} {str(e)[:80]}")
                if (measured % 100 == 0 and measured > 0) or measured + len(failures) == len(todo):
                    flush()
                    print(f"  [{measured + len(failures)}/{len(todo)}] measured")
    flush()

    # summary: per-domain true k + corrected denominators/leverage
    per_dom = defaultdict(lambda: [0, 0])
    for a in answers:
        if a["answer"] in done:
            per_dom[a["domain"]][0] += done[a["answer"]][1]
            per_dom[a["domain"]][1] += a["words"]
    print(f"\n{'domain':<13}{'Σtrue_tok':>11}{'Σwords':>9}{'k_true':>8}{'k_conv':>8}")
    conv = {"math": 1.45, "logics": 1.35, "drop": 1.30, "agentic": 1.45, "physics": 1.45,
            "vmlu_other": 1.30, "vmlu_legal": 1.30, "laws": 1.30, "dialect": 1.30,
            "squad": 1.30, "chemistry": 1.35, "medicine": 1.30, "cs": 1.35}
    total_true = 0
    for dom in sorted(per_dom):
        tt, ww = per_dom[dom]
        total_true += tt
        kt = tt / ww if ww else 0
        print(f"{dom:<13}{tt:>11,}{ww:>9,}{kt:>8.3f}{conv.get(dom, 0):>8.2f}")
    print(f"\ndistilled TRUE : {total_true:,} tokens (n={sum(1 for a in answers if a['answer'] in done)}, "
          f"failures={len(failures)})")
    print(f"distilled conv : {CONVENTION_DISTILLED:,} (Δ {total_true - CONVENTION_DISTILLED:+,})")
    if failures:
        print(f"WARNING: {len(failures)} failed answers (excluded from sums): {failures[:3]}")
    if total_true:
        print(f"leverage total  : 1 : {NET_TOTAL / total_true:.0f}   (trước: 1 : {NET_TOTAL / CONVENTION_DISTILLED:.0f})")
        print(f"leverage solving: 1 : {NET_SOLVING / total_true:.0f}   (trước: 1 : {NET_SOLVING / CONVENTION_DISTILLED:.0f})")
    print(f"output -> {OUT_CSV}")


if __name__ == "__main__":
    main()
