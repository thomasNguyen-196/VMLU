#!/usr/bin/env python3
import os, glob, sqlite3, json, csv, re
from collections import defaultdict
import sys

# Insert current dir for extract imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import parse_conversation

ISSUE10_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "all_res", "antigravity_gemini")
ISSUE10_DIR = os.path.normpath(ISSUE10_DIR)
CONV_DIR = os.path.expanduser("~/.gemini/antigravity/conversations")

csv_files = sorted(glob.glob(os.path.join(ISSUE10_DIR, "results_batch_*.csv")))

batch_to_cids = defaultdict(list)
for p in sorted(glob.glob(os.path.join(CONV_DIR, "*.db"))):
    cid = os.path.basename(p)[:-3]
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        r0 = con.execute("SELECT step_payload FROM steps WHERE idx=0").fetchone()
        con.close()
        if r0 and r0[0]:
            txt = r0[0].decode("utf-8", "ignore")
            m = re.search(r"results_batch_([a-z0-9_]+)\.csv", txt)
            if m:
                batch_to_cids[m.group(1)].append(cid)
    except Exception:
        pass

conv_for_batch = {}
for f in csv_files:
    bname = os.path.basename(f).replace("results_batch_", "").replace(".csv", "")
    candidates = batch_to_cids.get(bname, [])
    if candidates:
        best = max(candidates, key=lambda c: os.path.getmtime(os.path.join(CONV_DIR, f"{c}.db")))
        conv_for_batch[bname] = best

domain_stats = defaultdict(lambda: defaultdict(int))
domain_tools = defaultdict(lambda: defaultdict(int))
total_stats = defaultdict(int)
tool_counts = defaultdict(int)

batch_questions = {}
for f in csv_files:
    bname = os.path.basename(f).replace("results_batch_", "").replace(".csv", "")
    with open(f, encoding="utf-8") as fh:
        batch_questions[bname] = sum(1 for _ in csv.DictReader(fh))

for bname, cid in conv_for_batch.items():
    pdb = os.path.join(CONV_DIR, f"{cid}.db")
    res = parse_conversation(pdb)
    n_q = batch_questions[bname]
    
    dom = bname.rsplit("_", 1)[0]
    if dom.startswith("vmlu_"):
        canonical_dom = dom
    elif dom == "cs":
        canonical_dom = "cs"
    elif dom in ["math", "mathematics"]:
        canonical_dom = "math"
    elif dom in ["logic", "logics"]:
        canonical_dom = "logics"
    elif dom == "elem_math":
        canonical_dom = "vmlu_elem_math"
    elif dom == "humanities":
        canonical_dom = "vmlu_humanities"
    else:
        canonical_dom = dom
        
    calls = res["calls"]
    fresh = sum(c["fresh_input"] for c in calls)
    cache = sum(c["cache_read"] for c in calls)
    out = sum(c["output"] for c in calls)
    thinking = sum(c["thinking"] for c in calls)
    resp = sum(c["response_out"] for c in calls)
    
    starts = [st["start_s"] for st in res["steps"] if st["start_s"]]
    wall_span = (int(os.path.getmtime(pdb)) - min(starts)) if starts else 0
    
    con = sqlite3.connect(f"file:{pdb}?mode=ro", uri=True)
    step_rows = con.execute("SELECT step_payload FROM steps WHERE step_payload IS NOT NULL").fetchall()
    con.close()
    
    for srow in step_rows:
        blob = srow[0]
        for tname in ["run_command", "search_web", "view_file", "replace_file_content", "write_to_file", "ask_question"]:
            if tname.encode("utf-8") in blob:
                tool_counts[tname] += 1
                domain_tools[canonical_dom][tname] += 1

    domain_stats[canonical_dom]["questions"] += n_q
    domain_stats[canonical_dom]["batches"] += 1
    domain_stats[canonical_dom]["calls"] += len(calls)
    domain_stats[canonical_dom]["fresh_input"] += fresh
    domain_stats[canonical_dom]["cache_read"] += cache
    domain_stats[canonical_dom]["output"] += out
    domain_stats[canonical_dom]["thinking"] += thinking
    domain_stats[canonical_dom]["response_out"] += resp
    domain_stats[canonical_dom]["wall_span_s"] += wall_span
    
    total_stats["questions"] += n_q
    total_stats["batches"] += 1
    total_stats["calls"] += len(calls)
    total_stats["fresh_input"] += fresh
    total_stats["cache_read"] += cache
    total_stats["output"] += out
    total_stats["thinking"] += thinking
    total_stats["response_out"] += resp
    total_stats["wall_span_s"] += wall_span

q_tot = total_stats["questions"]
calls_tot = total_stats["calls"]
fresh_tot = total_stats["fresh_input"]
cache_tot = total_stats["cache_read"]
out_tot = total_stats["output"]
think_tot = total_stats["thinking"]
resp_tot = total_stats["response_out"]
net_tot = fresh_tot + out_tot
wall_tot = total_stats["wall_span_s"]
cache_hit_tot = cache_tot / (cache_tot + fresh_tot) * 100 if (cache_tot + fresh_tot) else 0

print("\n=== AGGREGATE RESOURCE USAGE (SOLVING - 79 BATCHES / 1,589 QUESTIONS) ===")
print(f"Total Questions : {q_tot:,}")
print(f"Total Batches   : {total_stats['batches']}")
print(f"Total LLM Calls : {calls_tot:,}")
print(f"Fresh Input     : {fresh_tot:,}")
print(f"Cache Read      : {cache_tot:,}")
print(f"Output Tokens   : {out_tot:,} (Thinking: {think_tot:,} = {think_tot/out_tot*100:.1f}%, Resp: {resp_tot:,})")
print(f"NET Tokens      : {net_tot:,}")
print(f"Net Tokens / Q  : {net_tot / q_tot:.1f} tokens/q")
print(f"Cache Hit Rate  : {cache_hit_tot:.2f}%")
print(f"Wall Clock Span : {wall_tot / 3600:.2f} hours ({wall_tot / q_tot:.1f} s/q)")

print("\n=== TOOL USAGE BREAKDOWN ===")
for t, c in sorted(tool_counts.items(), key=lambda x: -x[1]):
    print(f"  {t:20}: {c:5} calls")

print("\n=== PER-DOMAIN ROLLUP ===")
print(f"{'Domain':18} | {'N_q':>4} | {'Calls':>5} | {'Fresh/q':>8} | {'Cache/q':>8} | {'Out/q':>6} | {'Net/q':>8} | {'CacheHit':>8} | {'Wall(s/q)':>9}")
print("-" * 90)

domain_rows = []
for d, s in sorted(domain_stats.items()):
    nq = s["questions"]
    fr_q = s["fresh_input"] / nq
    ca_q = s["cache_read"] / nq
    ou_q = s["output"] / nq
    net_q = (s["fresh_input"] + s["output"]) / nq
    chit = s["cache_read"] / (s["cache_read"] + s["fresh_input"]) * 100 if (s["cache_read"] + s["fresh_input"]) else 0
    w_q = s["wall_span_s"] / nq
    print(f"{d:18} | {nq:4} | {s['calls']:5} | {fr_q:8.0f} | {ca_q:8.0f} | {ou_q:6.0f} | {net_q:8.0f} | {chit:7.2f}% | {w_q:8.1f}s")
    domain_rows.append({
        "domain": d,
        "issue10_n_questions": nq,
        "sessions": s["batches"],
        "n_llm_calls": s["calls"],
        "fresh_input": s["fresh_input"],
        "cache_read": s["cache_read"],
        "output": s["output"],
        "thinking": s["thinking"],
        "response_out": s["response_out"],
        "wall_span_s": s["wall_span_s"],
        "fresh_per_question": round(fr_q),
        "cache_per_question": round(ca_q),
        "output_per_question": round(ou_q),
        "cache_hit_pct": round(chit, 2),
        "net_per_question": round(net_q)
    })

# Export to all_res/antigravity_resource_ledger/domains.csv
ledger_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "all_res", "antigravity_resource_ledger")
dom_csv_path = os.path.join(ledger_dir, "domains.csv")
with open(dom_csv_path, "w", newline="", encoding="utf-8") as f:
    cols = list(domain_rows[0].keys())
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(domain_rows)
print(f"\nUpdated {dom_csv_path} with {len(domain_rows)} domains.")

