#!/usr/bin/env python3
"""Antigravity local-telemetry resource ledger extractor (Arm A ground truth).

Converts the raw Antigravity conversation SQLite files (per-step LLM usage
protobufs) into the frozen 3-axis resource ledger of the thesis:

  Axis 1 tokens : gen_metadata protobuf — field 2 fresh_input, 5 cache_read,
                  3 output, 9 thinking, 10 response_text (Gemini API metadata
                  recorded verbatim by Antigravity; aux fields 1/6 unidentified).
  Axis 2 latency: gen_metadata field1.field12.field2 = per-LLM-call duration (µs)
                  + steps.metadata {1:{1:start_epoch_s, 2:end_epoch_s}}.
  Axis 3 tools  : steps rows + executor_metadata rows per session (proxy counts).

Deterministic: same conversations/*.db input -> byte-identical CSVs.
Fail-fast repo style: unparsable blobs are COUNTED and REPORTED, never dropped
silently. Attribution filters the campaign window (2026-09-14..21) + VMLU
workspace + expert-agent persona; every excluded session is listed with its
reason (contamination audit) instead of being merged away silently.

Run from repo root (stdlib only, works on system python3):
  python3 tools/antigravity_ledger/extract.py
Outputs: all_res/antigravity_resource_ledger/{llm_calls,sessions,batches,excluded_sessions}.csv
"""
from __future__ import annotations

import csv
import glob
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
CONV_DIR = f"{HOME}/.gemini/antigravity/conversations"
SUMMARIES_DB = f"{HOME}/.gemini/antigravity/conversation_summaries.db"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                       "all_res", "antigravity_resource_ledger")
OUT_DIR = os.path.normpath(OUT_DIR)
ISSUE10_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                           "all_res", "antigravity_gemini")
ISSUE10_DIR = os.path.normpath(ISSUE10_DIR)

CAMPAIGN_FIRST_DAY = "2026-09-14"   # Issue #10 rollout window (15–20/09 + slack)
CAMPAIGN_LAST_DAY = "2026-09-21"

# ── Minimal protobuf wire-format reader (self-contained, stdlib) ────────────

def _varint(b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        if not x & 0x80:
            return r, i
        s += 7


def walk(b: bytes) -> list[tuple[int, int | bytes]]:
    """Top-level fields of one protobuf message: [(field_no, value)].
    Malformed tails stop the walk; the caller counts blobs that look short."""
    i, out, n = 0, [], len(b)
    while i < n:
        try:
            tag, i = _varint(b, i)
        except (IndexError, ValueError):
            break
        fn, wt = tag >> 3, tag & 7
        if fn == 0 or fn > 100000:
            break
        try:
            if wt == 0:
                v, i = _varint(b, i)
                out.append((fn, v))
            elif wt == 2:
                ln, i = _varint(b, i)
                if ln < 0 or i + ln > n:
                    break
                out.append((fn, b[i:i + ln]))
                i += ln
            elif wt == 5:
                i += 4
            elif wt == 1:
                i += 8
            else:
                break
        except (IndexError, ValueError):
            break
    return out


def sub(blob: bytes, field: int) -> list[bytes]:
    return [v for fn, v in walk(blob) if fn == field and isinstance(v, bytes)]


def varints(msg: bytes) -> dict[int, int]:
    return {fn: v for fn, v in walk(msg) if isinstance(v, int)}


def strings(msg: bytes) -> dict[int, str]:
    out = {}
    for fn, v in walk(msg):
        if isinstance(v, bytes):
            try:
                out.setdefault(fn, v.decode("utf-8"))
            except UnicodeDecodeError:
                pass
    return out


# ── Attribution: which conversations belong to the Issue #10 campaign ───────
# Ordered patterns: first match wins. English + Vietnamese phrasings both
# appear (main agents say "Expert Agent thuộc Antigravity", sub-agents say
# "Subagent chuyên trách...", some personas are fully English).

PERSONA_PATTERNS = [
    (r"Agentic Function Calling", "agentic"),
    (r"Formal Logic|suy luận logic|\bLogics\b", "logics"),
    (r"Math Expert|\bMath\b|Toán", "math"),
    (r"Numerical Reading Comprehension", "drop"),
    (r"SQuAD", "squad"),
    (r"Reading Comprehension", "reading_mixed"),   # DROP/SQuAD phrasing without a hint
    (r"DROP", "drop"),
    (r"Physics|Vật lý", "physics"),
    (r"Dialect|Phương ngữ", "dialect"),
    (r"Chemistry|Hóa học", "chemistry"),
    (r"Medical Sciences|Medicine|Y học|Dược", "medicine"),
    (r"Computer Science|\bCS\b", "cs"),
    (r"Kiến thức Nghề nghiệp", "vmlu_other"),
    (r"Dialect|Phương ngữ", "dialect"),
    (r"Pháp luật|Laws", "LAWS_OR_LEGAL"),          # disambiguated by V-Bench/VMLU keyword
    (r"Legal", "vmlu_legal"),
]
BATCH_RE = re.compile(r"Batch\s*(\d+)", re.IGNORECASE)
ORCHESTRATION_RE = re.compile(
    r"Report Synthesizer|Issue Drafter|Điều phối|Tổng hợp|orchestrat|tiến độ|trạng thái|Dự Án",
    re.IGNORECASE)


def parse_persona(preview: str, agent_name: str) -> tuple[str | None, int | None]:
    text = f"{agent_name} {preview}"
    if ORCHESTRATION_RE.search(text):
        return "orchestration", None
    for pat, tag in PERSONA_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            if tag == "LAWS_OR_LEGAL":
                if re.search(r"VMLU|valid", text, re.IGNORECASE):
                    tag = "vmlu_legal"
                elif re.search(r"V-Bench|vbench", text, re.IGNORECASE):
                    tag = "laws"
                else:
                    tag = "legal_ambiguous"
            elif tag == "reading_mixed":
                if re.search(r"SQuAD", text, re.IGNORECASE):
                    tag = "squad"
                elif re.search(r"DROP", text, re.IGNORECASE):
                    tag = "drop"
            m = BATCH_RE.search(text)
            return tag, (int(m.group(1)) if m else None)
    return None, None


def in_campaign_window(*timestamps: str) -> bool:
    for ts in timestamps:
        day = (ts or "")[:10]
        if CAMPAIGN_FIRST_DAY <= day <= CAMPAIGN_LAST_DAY:
            return True
    return False


def campaign_workspace(ws: str) -> bool:
    """VMLU workspace, or empty (sub-conversations inherit their parent's)."""
    ws = (ws or "").strip()
    return not ws or "VMLU" in ws.upper()


# ── Issue #10 batch reference (question counts per results_batch_<tag>_<n>) ──

ISSUE10_TAG = {
    "math": "math", "logic": "logics", "drop": "drop", "agentic": "agentic",
    "physics": "physics", "other": "vmlu_other", "legal": "vmlu_legal",
    "laws": "laws", "dialect": "dialect", "squad": "squad",
    "chemistry": "chemistry", "medicine": "medicine", "cs": "cs",
}


def issue10_batch_counts() -> dict[tuple[str, int], int]:
    """(ledger_tag, batch_no) -> n_questions from the frozen Issue #10 CSVs."""
    counts: dict[tuple[str, int], int] = {}
    for f in sorted(glob.glob(os.path.join(ISSUE10_DIR, "results_batch_*.csv"))):
        m = re.match(r"results_batch_([a-z_]+?)_(\d+)\.csv$", os.path.basename(f))
        if not m:
            continue
        tag = ISSUE10_TAG.get(m.group(1), m.group(1))
        with open(f, encoding="utf-8") as fh:
            counts[(tag, int(m.group(2)))] = sum(1 for _ in csv.DictReader(fh))
    return counts


# ── Extraction ───────────────────────────────────────────────────────────────

def load_summaries() -> dict[str, dict]:
    con = sqlite3.connect(f"file:{SUMMARIES_DB}?mode=ro", uri=True)
    cols = [r[1] for r in con.execute("PRAGMA table_info(conversation_summaries)")]
    out = {}
    for row in con.execute("SELECT * FROM conversation_summaries"):
        rec = dict(zip(cols, row))
        out[rec["conversation_id"]] = rec
    con.close()
    return out


def parse_conversation(path: str) -> dict:
    """One conversations/<id>.db -> usage records + step timing."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    meta_rows = [r[0] for r in con.execute("SELECT data FROM gen_metadata")]
    step_rows = con.execute("SELECT idx, step_type, metadata FROM steps").fetchall()
    n_exec = con.execute("SELECT COUNT(*) FROM executor_metadata").fetchone()[0]
    con.close()

    calls = []
    unparsable = 0
    for idx, blob in enumerate(meta_rows):
        try:
            f1 = sub(blob, 1)[0]
        except IndexError:
            unparsable += 1
            continue
        usage = {}
        for f4 in sub(f1, 4):
            usage = varints(f4)
        model = strings(f1).get(19, "")
        aux_f12 = None
        for f12 in sub(f1, 12):
            aux_f12 = varints(f12).get(2)
        u = usage
        calls.append({
            "call_idx": idx,
            "model": model,
            "fresh_input": u.get(2, 0),
            "cache_read": u.get(5, 0),
            "output": u.get(3, 0),
            "thinking": u.get(9, 0),
            "response_out": u.get(10, 0),
            "aux_f1": u.get(1, 0),
            "aux_f6": u.get(6, 0),
            "aux_f12": aux_f12,
        })
    steps_out = []
    for idx, step_type, meta in step_rows:
        start_s = None
        if meta:
            for f1 in sub(meta, 1):
                start_s = varints(f1).get(1)  # epoch seconds — verified against file mtime
        steps_out.append({"step_idx": idx, "step_type": step_type, "start_s": start_s})
    return {"calls": calls, "steps": steps_out, "n_executor": n_exec,
            "unparsable_meta": unparsable}


def load_manifest_questions(repo_root: str) -> tuple[list[str], list[str]]:
    """(drop_questions, squad_questions) from the pre-registered manifest."""
    mpath = os.path.join(repo_root, "data", "eval_set_manifest.csv")
    drop, squad = [], []
    if not os.path.exists(mpath):
        return drop, squad
    with open(mpath, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["dataset"] == "drop":
                drop.append(r["question"])
            elif r["dataset"] == "squad":
                squad.append(r["question"])
    return drop, squad


def resolve_reading_mixed(path: str, drop_qs: list[str], squad_qs: list[str]) -> str:
    """reading_mixed sessions: count manifest-question prefixes found in the
    step payloads; the majority dataset wins (deterministic, no guessing)."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    blobs = [r[0] for r in con.execute(
        "SELECT step_payload FROM steps WHERE step_payload IS NOT NULL")]
    con.close()
    text = " ".join(b.decode("utf-8", "ignore") for b in blobs)
    d = sum(1 for q in drop_qs if q[:45] in text)
    s = sum(1 for q in squad_qs if q[:45] in text)
    if d > s:
        return "drop"
    if s > d:
        return "squad"
    return "reading_mixed"


def main() -> None:
    files = sorted(glob.glob(os.path.join(CONV_DIR, "*.db")))
    if not files:
        raise SystemExit(f"Error: no conversation DBs under {CONV_DIR}")
    summaries = load_summaries()
    ref_counts = issue10_batch_counts()
    manifest_drop, manifest_squad = load_manifest_questions(
        os.path.dirname(os.path.dirname(ISSUE10_DIR)))

    call_rows, session_rows, excluded_rows = [], [], []
    unparsable_total = 0

    for path in files:
        cid = os.path.basename(path)[:-3]
        s = summaries.get(cid, {})
        preview = str(s.get("preview") or "")
        agent_name = str(s.get("agent_name") or "")
        workspaces = str(s.get("workspace_uris") or "")
        mod_time = str(s.get("last_modified_time") or "")
        user_time = str(s.get("last_user_input_time") or "")
        domain, batch_no = parse_persona(preview, agent_name)

        reason = None
        if not in_campaign_window(mod_time, user_time):
            reason = f"outside_window({(mod_time or user_time)[:10] or '?'})"
        elif not campaign_workspace(workspaces):
            reason = f"workspace_not_vmlu({workspaces[:60]})"
        elif domain is None:
            reason = "no_campaign_persona"
        if reason:
            excluded_rows.append({"conversation_id": cid, "reason": reason,
                                  "last_modified": mod_time[:19],
                                  "preview": preview[:120]})
            continue

        data = parse_conversation(path)
        if domain == "reading_mixed":
            domain = resolve_reading_mixed(path, manifest_drop, manifest_squad)
        unparsable_total += data["unparsable_meta"]
        n_calls = len(data["calls"])
        tot = defaultdict(int)
        for c in data["calls"]:
            for k in ("fresh_input", "cache_read", "output", "thinking",
                      "response_out", "aux_f1", "aux_f6", "aux_f12"):
                tot[k] += c[k] or 0
            call_rows.append({"conversation_id": cid, "domain": domain,
                              "batch": batch_no if batch_no is not None else "",
                              **c})
        starts = [st["start_s"] for st in data["steps"] if st["start_s"]]
        wall_start_s = min(starts) if starts else ""
        wall_end_s = int(os.path.getmtime(path))  # verified proxy: DB last write ≈ session close
        wall_span_s = (wall_end_s - wall_start_s) if wall_start_s else 0
        session_rows.append({
            "conversation_id": cid,
            "domain": domain,
            "batch": batch_no if batch_no is not None else "",
            "attribution": "persona+batch" if batch_no is not None else
                           ("persona_only" if domain else "unattributed"),
            "n_llm_calls": n_calls,
            "n_steps": len(data["steps"]),
            "n_executor": data["n_executor"],
            "fresh_input": tot["fresh_input"], "cache_read": tot["cache_read"],
            "output": tot["output"], "thinking": tot["thinking"],
            "response_out": tot["response_out"],
            "aux_f1": tot["aux_f1"], "aux_f6": tot["aux_f6"], "aux_f12": tot["aux_f12"],
            "wall_start_s": wall_start_s, "wall_end_s": wall_end_s,
            "wall_span_s": wall_span_s if wall_span_s > 0 else 0,
            "last_modified": mod_time[:19],
            "preview": preview[:120],
            "unparsable_meta": data["unparsable_meta"],
        })

    if unparsable_total:
        print(f"WARNING: {unparsable_total} gen_metadata blobs unparsable (counted, not dropped)")

    # batches.csv: rollup + join with Issue #10 question counts
    by_batch = defaultdict(lambda: defaultdict(int))
    for s in session_rows:
        key = (s["domain"], s["batch"] if s["batch"] != "" else None)
        for k in ("n_llm_calls", "fresh_input", "cache_read", "output",
                  "thinking", "response_out", "aux_f1", "aux_f6", "n_executor",
                  "wall_span_s"):
            by_batch[key][k] += s[k]
        by_batch[key]["sessions"] += 1
    batch_rows = []
    for (domain, batch_no), agg in sorted(by_batch.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        n_q = ref_counts.get((domain, batch_no)) if batch_no is not None else None
        row = {"domain": domain, "batch": batch_no if batch_no is not None else "?",
               "issue10_n_questions": n_q if n_q is not None else "",
               "sessions": agg["sessions"], "n_llm_calls": agg["n_llm_calls"],
               "fresh_input": agg["fresh_input"], "cache_read": agg["cache_read"],
               "output": agg["output"], "thinking": agg["thinking"],
               "response_out": agg["response_out"], "aux_f1": agg["aux_f1"],
               "aux_f6": agg["aux_f6"], "n_executor": agg["n_executor"],
               "wall_span_s": agg["wall_span_s"]}
        if n_q:
            row["fresh_per_question"] = round(agg["fresh_input"] / n_q)
            row["cache_per_question"] = round(agg["cache_read"] / n_q)
            row["output_per_question"] = round(agg["output"] / n_q)
            total_in = agg["fresh_input"] + agg["cache_read"]
            row["cache_hit_pct"] = round(agg["cache_read"] / total_in * 100, 2) if total_in else ""
            row["leverage_net_per_question"] = round(
                (agg["fresh_input"] + agg["output"]) / n_q)
            row["wall_per_question_s"] = round(agg["wall_span_s"] / n_q, 1)
        batch_rows.append(row)

    # domains.csv: thesis-table rollup (solving domains; orchestration kept separate)
    dom_nq = defaultdict(int)
    for (domain, _b), _n in ref_counts.items():
        dom_nq[domain] += _n
    by_domain = defaultdict(lambda: defaultdict(int))
    for s in session_rows:
        for k in ("n_llm_calls", "fresh_input", "cache_read", "output",
                  "thinking", "response_out", "aux_f1", "aux_f6", "n_executor",
                  "wall_span_s"):
            by_domain[s["domain"]][k] += s[k]
        by_domain[s["domain"]]["sessions"] += 1
    domain_rows = []
    for domain, agg in sorted(by_domain.items()):
        row = {"domain": domain, "issue10_n_questions": dom_nq.get(domain, ""),
               "sessions": agg["sessions"], "n_llm_calls": agg["n_llm_calls"],
               "fresh_input": agg["fresh_input"], "cache_read": agg["cache_read"],
               "output": agg["output"], "thinking": agg["thinking"],
               "response_out": agg["response_out"], "aux_f1": agg["aux_f1"],
               "aux_f6": agg["aux_f6"], "n_executor": agg["n_executor"],
               "wall_span_s": agg["wall_span_s"]}
        if dom_nq.get(domain):
            n_q = dom_nq[domain]
            row["fresh_per_question"] = round(agg["fresh_input"] / n_q)
            row["cache_per_question"] = round(agg["cache_read"] / n_q)
            row["output_per_question"] = round(agg["output"] / n_q)
            total_in = agg["fresh_input"] + agg["cache_read"]
            row["cache_hit_pct"] = round(agg["cache_read"] / total_in * 100, 2) if total_in else ""
            row["net_per_question"] = round((agg["fresh_input"] + agg["output"]) / n_q)
        domain_rows.append(row)

    # write CSVs
    os.makedirs(OUT_DIR, exist_ok=True)
    write_csv("llm_calls.csv", call_rows, list(call_rows[0].keys()) if call_rows else
              ["conversation_id", "domain", "batch", "call_idx", "model"])
    write_csv("sessions.csv", session_rows, list(session_rows[0].keys()) if session_rows else [])
    write_csv("batches.csv", batch_rows, list(batch_rows[0].keys()) if batch_rows else [])
    write_csv("domains.csv", domain_rows, list(domain_rows[0].keys()) if domain_rows else [])
    write_csv("excluded_sessions.csv", excluded_rows, list(excluded_rows[0].keys()) if excluded_rows else [])

    # integrity: three layers must agree
    tot_calls = sum(int(c[k]) for c in call_rows
                    for k in ("fresh_input", "cache_read", "output")) if call_rows else 0
    tot_sess = sum(int(s[k]) for s in session_rows
                   for k in ("fresh_input", "cache_read", "output")) if session_rows else 0
    tot_batch = sum(int(b[k]) for b in batch_rows
                    for k in ("fresh_input", "cache_read", "output")) if batch_rows else 0
    assert tot_calls == tot_sess == tot_batch, "integrity mismatch across ledger layers"

    net = sum(s["fresh_input"] + s["output"] for s in session_rows)
    cached = sum(s["cache_read"] for s in session_rows)
    print(f"\n=== ANTIMAGRAVITY RESOURCE LEDGER (campaign-filtered) ===")
    print(f"sessions kept: {len(session_rows)} | excluded: {len(excluded_rows)} "
          f"| llm_calls: {len(call_rows)}")
    print(f"fresh_input: {sum(s['fresh_input'] for s in session_rows):,}")
    print(f"cache_read : {cached:,}")
    print(f"output     : {sum(s['output'] for s in session_rows):,} "
          f"(thinking {sum(s['thinking'] for s in session_rows):,} + "
          f"response {sum(s['response_out'] for s in session_rows):,})")
    print(f"NET (fresh+output): {net:,} | cache_hit: "
          f"{cached / (cached + sum(s['fresh_input'] for s in session_rows)) * 100:.2f}%")
    print(f"outputs -> {OUT_DIR}")


def write_csv(name: str, rows: list[dict], cols: list[str]) -> None:
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows):>5} rows -> {path}")


if __name__ == "__main__":
    main()
