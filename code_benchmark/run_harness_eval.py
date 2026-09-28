"""omp harness arm — re-run frozen benchmark items through the `omp` coding agent.

WHY THIS EXISTS
---------------
Arm A of every number in `measurement_card.md` is a *direct* API call: the
frozen `build_prompt` (MC) or `build_reading_prompt` (reading), one turn, a
4- or 48-token budget, no tools. This runner produces arm B: the SAME model
(`Qwen3.5-9B-28K` on the IEC gateway), the SAME endpoint, the SAME
temperature/seed, the SAME frozen parser — but delivered through the `omp`
(Oh My Pi) agent harness, which adds a coding-agent system prompt (~7.5k
tokens), a tool menu, and a multi-turn agentic loop.

The delta between the two arms is the *harness effect* (RQ1 in
docs/harness-evolution-thesis-plan.md): how much of a benchmark score is the
model and how much is the scaffold wrapped around it.

INVARIANTS (the same fail-fast discipline as the rest of the package)
---------------------------------------------------------------------
1. The item prompt is BYTE-IDENTICAL to arm A's. For the legal MC/NLI sets
   the adapter is re-derived from source and then checked byte-for-byte
   against the arm A checkpoint; for the reading sets it is built with the
   frozen `build_reading_prompt`.
2. The scorer is never re-implemented. MC answers go through the frozen
   `extract_answer`; reading answers are written in `ANSWER_COLS` shape so
   `score_reading_eval.py` scores them unchanged.
3. Answers are never repaired. `raw_response` is the verbatim last assistant
   text; an item the harness failed to answer is logged with its diagnosis,
   never re-asked into compliance.
4. Isolation: each item gets a fresh empty temp dir holding ONLY `item.json`
   (prompt, no gold, no dataset, no repo), and omp runs with `--cwd` on it and
   no `--add-dir`. The model cannot read the answers off the disk.
5. One condition per checkpoint namespace: the run label (default
   `ompH2_Qwen3.5-9B-28K`) becomes the model slug, so harness runs can never
   mix with the direct-prompt runs of the same model.
6. The measured harness is pinned by `PI_CODING_AGENT_DIR` (see `.omp-iec/`),
   which isolates omp's config, providers, roles and caches from the machine's
   everyday setup.

Usage (repo root):
  # inference
  .venv/bin/python code_benchmark/run_harness_eval.py run --dataset legal_mc --workers 4
  .venv/bin/python code_benchmark/run_harness_eval.py run --dataset reading400 --resume
  # reading sets: score with the FROZEN scorer, then compare against arm A
  .venv/bin/python code_benchmark/score_reading_eval.py --answers <answers file>
  .venv/bin/python code_benchmark/run_harness_eval.py compare --dataset reading400
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import random
import re
import shutil
import subprocess  # nosec B404 — the harness IS a subprocess; argv is built, never a shell string
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import (MANIFEST_DEFAULT, SQUAD_DEFAULT, DROP_DEFAULT,
                                       GOLD_REVIEW_DEFAULT, item_key, model_dirs,
                                       read_csv_checked, sanitize_model, setup_logging,
                                       write_csv_atomic)
    from code_benchmark.checkpoint import checkpoint_name, find_latest_checkpoint
    from code_benchmark.run_reading_eval import (ANSWER_COLS, build_reading_prompt,
                                                 index_sources, join_manifest)
    from code_benchmark.run_bidlqa_eval import (BIDLQA_VAL_MANIFEST,
                                                load_source as load_bidlqa_source,
                                                split_config as bidlqa_split_config,
                                                verify_join as verify_bidlqa_join)
    from code_benchmark.run_mc_eval import build_prompt, extract_answer
    from code_benchmark.llm import build_client, verify_credentials
    from code_benchmark.run_vbench_eval import (build_agentic_prompt, extract_function_call,
                                                extract_mc_answer, load_vbench)
    from code_benchmark.score_reading_eval import measurement_card_hash, score_pair
except ImportError:
    from common import (MANIFEST_DEFAULT, SQUAD_DEFAULT, DROP_DEFAULT,
                        GOLD_REVIEW_DEFAULT, item_key, model_dirs, read_csv_checked,
                        sanitize_model, setup_logging, write_csv_atomic)
    from checkpoint import checkpoint_name, find_latest_checkpoint
    from run_reading_eval import (ANSWER_COLS, build_reading_prompt,
                                  index_sources, join_manifest)
    from run_bidlqa_eval import (BIDLQA_VAL_MANIFEST,
                                 load_source as load_bidlqa_source,
                                 split_config as bidlqa_split_config,
                                 verify_join as verify_bidlqa_join)
    from run_mc_eval import build_prompt, extract_answer
    from llm import build_client, verify_credentials
    from run_vbench_eval import (build_agentic_prompt, extract_function_call,
                                  extract_mc_answer, load_vbench)
    from score_reading_eval import measurement_card_hash, score_pair

RESULTS_DIR = Path("all_res/ollama_result")
AGENT_DIR_DEFAULT = Path(".omp-iec")
DEFAULT_LABEL = "ompH2_Qwen3.5-9B-28K"
DEFAULT_OMP = "omp"
DEFAULT_MODEL = "iec/Qwen3.5-9B-28K"
DEFAULT_TOOLS = "read,bash,edit,write,grep,glob"
# The no-tool ablation condition: scaffolding without a tool menu. Maps to
# omp's own --no-tools (see build_argv).
NO_TOOLS = ("", "none", "--no-tools", "no_tools")
# The no-persona ablation condition (H3): a neutral one-line system prompt that
# says nothing about answering style, verbosity or output format. One source of
# truth so the card, the argv and the tests cannot drift apart. `--system-prompt
# minimal` resolves to this string; anything else is passed to omp verbatim.
MINIMAL_SYSTEM_PROMPT = "Answer the user's question."

# Arm A's outputs, per dataset (the direct-prompt baseline this arm is compared
# against). `scores` is the frozen scorer's per-item file, `eval` the MC runner's
# per-item file; `n` is asserted so a truncated baseline can never be compared.
ARM_A = {
    "legal_mc": {
        "kind": "mc", "n": 146,
        "eval": "full_evaluation_legal_{a}.csv",
        "scores": None,
    },
    "legal_nli": {
        "kind": "mc", "n": 150,
        "eval": "full_evaluation_nli_{a}.csv",
        "scores": None,
    },
    "reading400": {
        "kind": "reading", "n": 400,
        "eval": None,
        "scores": "reading_scores_{a}.csv",
    },
    "bidlqa_val": {
        "kind": "reading", "n": 482,
        "eval": None,
        "scores": "reading_scores_bidlqa_val_{a}.csv",
    },
    # V-Bench agentic (function calling). NO local gold: the only locally
    # computable metric is SCHEMA VALIDITY (did the reply contain a call that
    # validates against the row's own functions); accuracy is server-side, so
    # `compare` here measures validity and the run writes an uploadable
    # submission jsonl for vbench.ai.
    "vbench_agentic": {
        "kind": "vbench", "n": 1000,
        "eval": None,
        "scores": "vbench_valid_summary_{a}.csv",
    },
    # V-Bench MC (4.141, 12 domains). Also NO local gold, so accuracy is again
    # server-side; the only locally computable number is AGREEMENT WITH ARM A per
    # item (did routing the same prompt through the agent change the answer?) —
    # plus the blank rate. `compare` therefore reports agreement, never accuracy,
    # and never runs McNemar (arm A trivially "agrees" with itself, which would
    # make the test meaningless).
    "vbench_mc": {
        "kind": "vbench_mc", "n": 4141,
        "eval": None,
        "scores": None,
    },
}
VBENCH_SOURCE = Path("v_bench/public-test.jsonl")

# The ledger: one row per item, the single source of truth for a harness run.
# Everything the report needs is here; the arm-A-shaped answer files are
# projections of it, and the transcripts live beside it.
LEDGER_COLS = [
    "dataset", "item_id", "stratum", "kind", "question", "prompt_sha256",
    "raw_response", "answer", "gold", "correct", "em", "f1", "valid",
    "turns", "tool_calls", "tool_names", "net_attempt", "path_escape",
    "input_tokens", "output_tokens", "cache_read_tokens", "wall_s",
    "exit_code", "stop_reason", "failure",
]
COMPARE_COLS = ["metric", "group", "n", "arm_a", "arm_b", "delta",
                "ci95_low", "ci95_high", "mcnemar_p", "a_only", "b_only",
                "both", "neither", "arm_b_failures", "measurement_card_hash"]


# ── items ──────────────────────────────────────────────────────────────
def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _check_n(actual: list, expected: int, what: str) -> None:
    if len(actual) != expected:
        raise SystemExit(f"Error: {what} has {len(actual)} items, expected {expected}")


def _load_jsonl(path: Path, sha: str) -> list[dict]:
    """Read a jsonl source and verify its pinned sha256 (identity of the data)."""
    if not path.exists():
        raise SystemExit(f"Error: source not found: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha:
        raise SystemExit(f"Error: source drift for {path}: sha {digest} != pinned {sha}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _reading_gold() -> dict[tuple[str, str], str]:
    """Reviewed gold for the 400-item reading eval, as the frozen scorer reads it."""
    path = GOLD_REVIEW_DEFAULT
    if not path.exists():
        raise SystemExit(f"Error: reviewed gold not found: {path} "
                         "(regenerate with export_annotation_workbooks.py)")
    rows = read_csv_checked(path, required={"dataset", "item_id", "gold_answer"},
                            label="reading-gold")
    return {(r["dataset"], str(r["item_id"])): r["gold_answer"] for r in rows}


def load_reading400() -> list[dict]:
    """The pre-registered 400 (200 SQuAD + 200 DROP), MC-3 prompt, reviewed gold.

    `dataset` on each item is the SOURCE name (squad / drop) — the frozen scorer
    joins gold on (dataset, item_id), so renaming it here would break the join.
    """
    manifest = read_csv_checked(MANIFEST_DEFAULT,
                                required={"dataset", "item_id", "stratum", "question"},
                                label="manifest")
    items = join_manifest(manifest, index_sources(SQUAD_DEFAULT, DROP_DEFAULT))
    gold = _reading_gold()
    out = []
    for row in items:
        key = (row["dataset"], str(row["item_id"]))
        if key not in gold:
            raise SystemExit(f"Error: no reviewed gold for {key}")
        prompt = build_reading_prompt(row["context"], row["question"])
        out.append({"dataset": row["dataset"], "item_id": str(row["item_id"]),
                    "stratum": row["stratum"], "kind": "reading",
                    "question": row["question"], "prompt": prompt,
                    "prompt_sha256": _sha256_text(prompt), "gold": gold[key]})
    _check_n(out, 400, "reading400")
    return out


def load_bidlqa_val() -> list[dict]:
    """ViBidLQA val (482) — MC-3 prompt, source contexts, manifest gold."""
    cfg = bidlqa_split_config("val")
    src = load_bidlqa_source(cfg["source"], cfg["sha"])
    manifest = read_csv_checked(cfg["manifest"],
                                required={"dataset", "item_id", "stratum", "question",
                                          "gold_answer"},
                                label="bidlqa-manifest")
    verify_bidlqa_join(manifest, src, cfg["id_prefix"])
    out = []
    for m, s in zip(manifest, src, strict=True):
        prompt = build_reading_prompt(s["context"], m["question"])
        out.append({"dataset": m["dataset"], "item_id": str(m["item_id"]),
                    "stratum": m["stratum"], "kind": "reading",
                    "question": m["question"], "prompt": prompt,
                    "prompt_sha256": _sha256_text(prompt),
                    "gold": str(m["gold_answer"])})
    _check_n(out, 482, "bidlqa_val")
    return out


def _legal_manifest(name: str) -> dict:
    path = Path(f"data/{name}")
    if not path.exists():
        raise SystemExit(f"Error: legal manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_prompt_parity(items: list[dict], arm_a_csv: Path) -> None:
    """Hard-fail if a re-derived prompt differs from what arm A actually sent.

    The adapter for the legal sets lives in the manifest's `adapter` field, not
    in code; if that text ever stops reproducing arm A's bytes, the two arms
    would be measuring different questions and the comparison would be void.
    When the arm A file is absent (fresh clone) the check is skipped loudly.
    """
    if not arm_a_csv.exists():
        logging.warning("arm A file %s not found — prompt parity with arm A could "
                        "NOT be verified for this run", arm_a_csv)
        return
    arm_a = {str(r["id"]): r["prompt"] for r in read_csv_checked(arm_a_csv, label="arm A")}
    for it in items:
        got = arm_a.get(it["item_id"])
        if got is None:
            raise SystemExit(f"Error: {it['item_id']} missing from arm A file {arm_a_csv}")
        if got != it["prompt"]:
            raise SystemExit(f"Error: prompt drift for {it['item_id']} — the adapter no "
                             f"longer reproduces arm A's bytes; refusing to compare arms")


def load_legal_mc(arm_a_slug: str) -> list[dict]:
    """VLSP2025-LegalSLM multichoice (146) — frozen MC prompt, gold from manifest.

    The source choices carry no letters; the MC-10 run lettered them before
    calling the frozen `build_prompt` (whose `A. B. C.` contract the model needs).
    That detail lives only in arm A's stored prompts, which is why the parity
    check below is a hard gate and not a nicety.
    """
    man = _legal_manifest("legal_slm_multichoice_manifest.json")
    src = _load_jsonl(Path(man["source_file"]), man["source_sha256"])
    _check_n(src, man["n"], man["source_file"])
    gold = {it["id"]: it["gold"] for it in man["items"]}
    out = []
    for i, r in enumerate(src, start=1):
        item_id = f"LG-{i:04d}"
        if item_id not in gold:
            raise SystemExit(f"Error: no gold for {item_id}")
        letters = "ABCDE"[: len(r["choices"])]   # the frozen prompt contract is A-E
        if len(letters) != len(r["choices"]):
            raise SystemExit(f"Error: {item_id} has {len(r['choices'])} choices (max 5)")
        choices = [f"{letter}. {c}" for letter, c in zip(letters, r["choices"], strict=True)]
        prompt = build_prompt(r["question"], choices)
        out.append({"dataset": "legal_mc", "item_id": item_id, "stratum": "legal",
                    "kind": "mc", "question": r["question"], "prompt": prompt,
                    "prompt_sha256": _sha256_text(prompt), "gold": gold[item_id]})
    _verify_prompt_parity(out, RESULTS_DIR / arm_a_slug
                          / ARM_A["legal_mc"]["eval"].format(a=arm_a_slug))
    return out


def load_legal_nli(arm_a_slug: str) -> list[dict]:
    """VLSP2025-LegalSLM NLI (150) — binary Có/Không through the frozen MC prompt.

    Adapter (verbatim from data/legal_nli_manifest.json):
      question = legal_document + "\\n\\n" + specific_question + "\\n" + question
      choices  = ["A. Có", "B. Không"];  gold 0 -> A, 1 -> B
    """
    man = _legal_manifest("legal_nli_manifest.json")
    src = _load_jsonl(Path(man["source_file"]), man["source_sha256"])
    _check_n(src, man["n"], man["source_file"])
    gold = {it["id"]: it["gold"] for it in man["items"]}
    out = []
    for i, r in enumerate(src, start=1):
        item_id = f"LG-NLI-{i:04d}"
        if item_id not in gold:
            raise SystemExit(f"Error: no gold for {item_id}")
        question = (r["legal_document"].strip() + "\n\n"
                    + r["specific_question"].strip() + "\n"
                    + r["question"].strip())
        prompt = build_prompt(question, ["A. Có", "B. Không"])
        out.append({"dataset": "legal_nli", "item_id": item_id, "stratum": "legal-nli",
                    "kind": "mc", "question": question, "prompt": prompt,
                    "prompt_sha256": _sha256_text(prompt), "gold": gold[item_id]})
    _verify_prompt_parity(out, RESULTS_DIR / arm_a_slug
                          / ARM_A["legal_nli"]["eval"].format(a=arm_a_slug))
    return out


def load_vbench_agentic() -> list[dict]:
    """V-Bench agentic rows (1.000) with the FROZEN minimal agentic prompt.

    Reuses `load_vbench` (row validation, track classification, safety-skip) and
    `build_agentic_prompt` from run_vbench_eval, so the harness arm sends exactly
    what the direct-prompt arm sent (MC-8 condition). `gold` stays empty on
    purpose: this release is scored server-side; nothing local may pretend
    otherwise.
    """
    rows = [r for r in load_vbench(VBENCH_SOURCE) if r["track"] == "agentic"]
    if len(rows) != ARM_A["vbench_agentic"]["n"]:
        logging.warning("vbench agentic rows = %d, card says %d — check the release "
                        "(expected 1.000 for v2026.03.28)", len(rows),
                        ARM_A["vbench_agentic"]["n"])
    out = []
    for r in rows:
        prompt = build_agentic_prompt(r["question"], r["function"], "minimal")
        out.append({"dataset": "vbench_agentic", "item_id": str(r["id"]),
                    "stratum": "agentic", "kind": "vbench", "question": r["question"],
                    "prompt": prompt, "prompt_sha256": _sha256_text(prompt), "gold": "",
                    "functions": r["function"]})
    return out


def load_vbench_mc() -> list[dict]:
    """V-Bench MC rows (4.141) with the FROZEN MC prompt and no gold.

    Same prompt bytes as arm A used: `build_prompt(question, choices)`, the
    function the MC pipeline and every direct arm share. Parsing goes through
    `extract_mc_answer`, which is `extract_answer` plus the per-row letter clamp
    (a "E" on a 4-choice row is not a valid submission value).
    """
    rows = [r for r in load_vbench(VBENCH_SOURCE) if r["track"] == "mc"]
    if len(rows) != ARM_A["vbench_mc"]["n"]:
        logging.warning("vbench MC rows = %d, card says %d — check the release "
                        "(expected 4.141 for v2026.03.28)", len(rows),
                        ARM_A["vbench_mc"]["n"])
    out = []
    for r in rows:
        prompt = build_prompt(r["question"], r["choices"])
        out.append({"dataset": "vbench_mc", "item_id": str(r["id"]),
                    "stratum": r["domain"], "kind": "vbench_mc", "question": r["question"],
                    "prompt": prompt, "prompt_sha256": _sha256_text(prompt), "gold": "",
                    "choices": r["choices"], "domain": r["domain"]})
    return out


def load_items(dataset: str, arm_a_slug: str) -> list[dict]:
    loaders = {"reading400": lambda: load_reading400(),
               "bidlqa_val": lambda: load_bidlqa_val(),
               "vbench_agentic": lambda: load_vbench_agentic(),
               "vbench_mc": lambda: load_vbench_mc(),
               "legal_mc": lambda: load_legal_mc(arm_a_slug),
               "legal_nli": lambda: load_legal_nli(arm_a_slug)}
    if dataset not in loaders:
        raise SystemExit(f"Error: --dataset must be one of {sorted(loaders)}")
    return loaders[dataset]()


# ── the harness call ────────────────────────────────────────────────────
def build_argv(*, omp_bin: str, model: str, prompt: str, workdir: Path,
               tools: str, max_time: int, thinking: str,
               system_prompt: str | None = None) -> list[str]:
    """The exact argv for one item. Pure — the tests assert this shape.

    `tools` selects the tool condition; NO_TOOLS ("none") is the ablation arm that
    isolates the scaffolding from the tool menu, and it maps to omp's own
    `--no-tools` rather than an empty `--tools` list.

    `system_prompt` is the no-persona ablation arm (H3): it REPLACES omp's
    coding-agent system prompt with a neutral line, so the only variable that
    changes against the full-tool arm is the system prompt's content.

    Flags that would make the measurement unreproducible are all off: no
    session file, no auto title generation (a second model call), no user
    extensions/skills/rules, no LSP. `--auto-approve` is deliberately ON: the
    point of the full-tool arm is the full tool menu, and a harness that stops
    at every tool call is not the harness being measured.
    """
    tool_args = ["--no-tools"] if tools.strip().lower() in NO_TOOLS else ["--tools", tools]
    persona_args = (["--system-prompt", system_prompt] if system_prompt else [])
    return [
        omp_bin, "-p",
        "--model", model,
        "--mode", "json",
        *persona_args,
        *tool_args,
        "--auto-approve",
        "--thinking", thinking,
        "--max-time", str(max_time),
        "--no-session",
        "--no-title",
        "--no-extensions",
        "--no-skills",
        "--no-rules",
        "--no-lsp",
        "--cwd", str(workdir),
        prompt,
    ]


NETWORK_PATTERNS = ("curl", "wget", "http://", "https://", "huggingface", "requests.get",
                    "urllib.request", "nc -", "ping -", "git clone", "pip install")
# Filesystem escape is only meaningful in TOOL CALLS: prose may legitimately
# contain "../" or a URL, and the transcript's own argv carries the repo path.
PATH_ESCAPE_PATTERNS = ("/home/", "..", "/etc/", "/usr/", "vmlu_", "v_legal_slsp",
                        "v_med_vm14k", "all_res", "eval_set_manifest", "data/gold",
                        "reading_scores", "full_evaluation")


def audit_transcript(events: list[dict]) -> tuple[str, str]:
    """(network_attempt, path_escape) flags — the honesty audit of the H2 arm.

    The tool menu includes `bash`, and ViBidLQA / VLSP2025 are public datasets,
    so a model *could* in principle fetch the answers. The temp-dir isolation
    stops it reading them locally; this records whether it tried to go out to
    the network (model prose + tool arguments) or to reach outside its sandbox
    (tool arguments only), so the report quantifies the threat instead of
    assuming it away. A flag is a signal for review, not a verdict.
    """
    prose: list[str] = []
    calls: list[str] = []
    for ev in events:
        if ev.get("type") != "message_end" or ev.get("message", {}).get("role") != "assistant":
            continue
        for block in ev["message"].get("content") or []:
            if block.get("type") == "text":
                prose.append(block.get("text") or "")
            elif block.get("type") == "toolCall":
                calls.append(json.dumps(block, ensure_ascii=False))
    said = ("\n".join(prose) + "\n" + "\n".join(calls)).lower()
    called = "\n".join(calls).lower()
    net = "|".join(p for p in NETWORK_PATTERNS if p in said)
    esc = "|".join(p for p in PATH_ESCAPE_PATTERNS if p in called)
    return net, esc


def parse_transcript(lines: list[str]) -> tuple[list[dict], str, dict]:
    """omp --mode json stream -> (events, last assistant text, usage/tool stats).

    Also accumulates the per-call `duration` / `ttft` the stream reports, which is
    what lets the speed probe separate MODEL time from process overhead
    (wall - sum(duration) = spawn + config load + teardown).
    """
    events, text, stats = [], "", {"turns": 0, "tool_calls": 0, "tool_names": [],
                                   "input_tokens": 0, "output_tokens": 0,
                                   "cache_read_tokens": 0, "stop_reason": "",
                                   "model_ms": 0.0, "ttft_ms": 0.0, "calls": 0}
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            logging.debug("skipping non-JSON stdout line: %.120s", raw)
            continue
        events.append(ev)
        etype = ev.get("type")
        if etype == "turn_start":
            stats["turns"] += 1
        elif etype == "message_end" and ev.get("message", {}).get("role") == "assistant":
            msg = ev["message"]
            usage = msg.get("usage") or {}
            stats["input_tokens"] += int(usage.get("input") or 0)
            stats["output_tokens"] += int(usage.get("output") or 0)
            stats["cache_read_tokens"] += int(usage.get("cacheRead") or 0)
            stats["model_ms"] += float(msg.get("duration") or 0.0)
            stats["ttft_ms"] += float(msg.get("ttft") or 0.0)
            stats["calls"] += 1
            if msg.get("stopReason"):
                stats["stop_reason"] = str(msg["stopReason"])
            parts = []
            for block in msg.get("content") or []:
                btype = block.get("type")
                if btype == "text":
                    parts.append(block.get("text") or "")
                elif btype == "toolCall":
                    stats["tool_calls"] += 1
                    name = (block.get("name") or (block.get("arguments") or {}).get("name")
                            or "unknown")
                    stats["tool_names"].append(str(name))
            text = "\n".join(p for p in parts if p.strip())
    return events, text, stats


DEFAULT_SYSTEM_AGENT_DIR = Path.home() / ".omp" / "agent"
# Files omp reads from its DEFAULT agent dir even when PI_CODING_AGENT_DIR points
# somewhere else (measured 2026-09-26: an empty APPEND_SYSTEM.md in the custom
# agent dir does NOT shadow the global one; only overriding HOME does). Each of
# these silently changes the measured scaffold, so the runner shouts about it.
LEAKY_GLOBAL_FILES = ("APPEND_SYSTEM.md",)


def warn_about_scaffold_leaks(agent_dir: Path) -> list[str]:
    """Loud guard: personal config that reaches the measured harness anyway.

    Found the hard way — a `PI_CODING_AGENT_DIR` harness still received the
    machine's global `APPEND_SYSTEM.md` reply-style rules ("verdict first, why,
    the test, the rule"), which cost 14 accuracy points and 6x the output tokens
    (card MC-22). Isolation of config/providers is NOT isolation of the scaffold.
    """
    if agent_dir == DEFAULT_SYSTEM_AGENT_DIR.resolve():
        return []
    found = []
    for name in LEAKY_GLOBAL_FILES:
        path = DEFAULT_SYSTEM_AGENT_DIR / name
        if not path.exists():
            continue
        found.append(str(path))
        logging.warning(
            "SCAFFOLD LEAK: omp also reads %s from the DEFAULT agent dir, even though "
            "PI_CODING_AGENT_DIR=%s. That file is part of the measured condition; run "
            "this with HOME=<sandbox> to measure omp without it.", path, agent_dir)
    return found


def sandbox_payload(item: dict) -> dict:
    """What the harness is allowed to see on disk: the item, never the answer.

    Pure so the isolation invariant is unit-testable — the sandbox must not
    carry `gold`, or the model could read the answer key instead of thinking.
    """
    return {"id": item["item_id"], "kind": item["kind"], "prompt": item["prompt"]}


def run_item(item: dict, *, omp_bin: str, model: str, tools: str, max_time: int,
             thinking: str, agent_dir: Path, scratch: Path, arm: str,
             system_prompt: str | None = None, timeout_slack: int = 60) -> tuple[dict, dict]:
    """One item, one sandbox, one omp process.

    Returns (ledger row, timing). The timing dict is kept OUT of the ledger
    columns on purpose: LEDGER_COLS is a frozen artifact schema, and the speed
    probe must not change the shape of the files the 1.178-item run produced.
    """
    workdir = Path(tempfile.mkdtemp(prefix=f"{item['item_id']}-", dir=scratch))
    started = time.time()
    row = {c: "" for c in LEDGER_COLS}
    row.update({"dataset": item["dataset"], "item_id": item["item_id"],
                "stratum": item["stratum"], "kind": item["kind"],
                "question": item["question"], "prompt_sha256": item["prompt_sha256"],
                "gold": item["gold"]})
    # The sandbox holds the prompt and nothing else: no gold, no dataset, no repo.
    (workdir / "item.json").write_text(
        json.dumps(sandbox_payload(item), ensure_ascii=False, indent=2), encoding="utf-8")
    argv = build_argv(omp_bin=omp_bin, model=model, prompt=item["prompt"],
                      workdir=workdir, tools=tools, max_time=max_time,
                      thinking=thinking, system_prompt=system_prompt)
    env = {**os.environ, "PI_CODING_AGENT_DIR": str(agent_dir)}
    try:
        # nosec B603 — fixed argv (build_argv), shell=False, cwd pinned to the
        # item's own empty sandbox; no user string is ever interpreted by a shell.
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=max_time + timeout_slack,
                              env=env, cwd=workdir, check=False)  # nosec B603
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr, code = f"hard timeout after {max_time + timeout_slack}s", -9
    events, text, stats = parse_transcript(stdout.splitlines())
    net, esc = audit_transcript(events)
    row.update({
        "raw_response": text.strip(),
        "turns": stats["turns"],
        "tool_calls": stats["tool_calls"],
        "tool_names": ",".join(stats["tool_names"]),
        "net_attempt": net,
        "path_escape": esc,
        "input_tokens": stats["input_tokens"],
        "output_tokens": stats["output_tokens"],
        "cache_read_tokens": stats["cache_read_tokens"],
        "wall_s": f"{time.time() - started:.2f}",
        "exit_code": code,
        "stop_reason": stats["stop_reason"],
    })
    if item["kind"] == "mc":
        answer = extract_answer(text)
        row["answer"] = answer
        row["correct"] = int(bool(answer) and answer == item["gold"])
    elif item["kind"] == "vbench_mc":
        # Frozen MC parser + the row's own choice clamp. No gold locally, so there
        # is no `correct` — only the shipped letter and whether one was produced.
        answer = extract_mc_answer(text, item["choices"])
        row["answer"] = answer
        row["valid"] = int(bool(answer))
    elif item["kind"] == "vbench":
        # Frozen V-Bench parser: '' means NO candidate validated against the row's
        # own schema — that emptiness IS the locally computable metric (validity),
        # and it is also the value a submission ships for that row.
        answer = extract_function_call(text, item["functions"])
        row["answer"] = answer
        row["valid"] = int(bool(answer))
    else:
        pred, f1, em, _ = score_pair(text, item["gold"])
        row["answer"] = pred
        row["correct"] = int(em)
        row["em"] = int(em)
        row["f1"] = f"{f1:.6f}"
    failure = diagnose(row, stderr)
    row["failure"] = failure
    # Transcript kept verbatim next to the ledger: the audit trail for the report.
    # Named by the ARM dataset (not the source dataset) so it lines up with the
    # ledger/summary files of the same run.
    (scratch / "transcripts").mkdir(parents=True, exist_ok=True)
    (scratch / "transcripts" / f"{arm}_{item['item_id']}.json").write_text(
        json.dumps({"argv": argv[:-1] + ["<PROMPT>"], "item": {k: v for k, v in item.items()},
                    "events": events, "stderr": stderr[-4000:], "exit_code": code},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(workdir, ignore_errors=True)
    wall = time.time() - started
    timing = {
        "wall_s": wall,
        "model_s": stats["model_ms"] / 1000.0,
        "ttft_s": stats["ttft_ms"] / 1000.0,
        # everything the harness adds that is NOT the model call: bun startup,
        # provider/config load, transcript render, teardown
        "overhead_s": max(0.0, wall - stats["model_ms"] / 1000.0),
        "calls": stats["calls"],
        "prompt_tokens": stats["input_tokens"] + stats["cache_read_tokens"],
        "fresh_prompt_tokens": stats["input_tokens"],
        "cache_read_tokens": stats["cache_read_tokens"],
        "completion_tokens": stats["output_tokens"],
    }
    return row, timing


def diagnose(row: dict, stderr: str) -> str:
    """Why this item counts as a harness failure ('' = answered). Never repairs."""
    if row["exit_code"] != 0:
        return f"omp exit {row['exit_code']}: {stderr.strip()[-200:]}"
    if not row["raw_response"]:
        return "empty final assistant message"
    if row["kind"] == "mc" and not row["answer"]:
        return "unparsed MC answer"
    if row["kind"] == "reading" and not row["raw_response"].strip():
        return "empty reading answer"
    return ""


# ── writing the arm-A-shaped projections ────────────────────────────────
def write_projection(rows: list[dict], dataset: str, kind: str, slug: str,
                     folder: Path, items_by_id: dict[str, dict]) -> Path:
    """Project the ledger onto the file shape the FROZEN scorers already read."""
    if kind == "vbench_mc":
        # Server-side scoring, same as agentic: ship the letters, keep a local
        # answers file. The submission holds ONLY this arm's MC rows — never mixed
        # with arm A's, or the two arms' numbers would be indistinguishable.
        path = folder / f"vbench_mc_answers_{slug}.csv"
        write_csv_atomic(path, [{"id": r["item_id"], "domain": r["stratum"],
                                 "question": r["question"],
                                 "raw_response": r["raw_response"],
                                 "answer": r["answer"],
                                 "valid": int(bool(r["answer"]))} for r in rows],
                        ["id", "domain", "question", "raw_response", "answer", "valid"])
        sub_dir = Path("submissions") / slug
        sub_dir.mkdir(parents=True, exist_ok=True)
        with open(sub_dir / f"submission_vbench_mc_{slug}.jsonl", "w", encoding="utf-8") as f:
            for r in sorted(rows, key=lambda x: int(x["item_id"])):
                # compact separators: byte style of the official sample submission
                f.write(json.dumps({"id": int(r["item_id"]), "answer": r["answer"]},
                                   ensure_ascii=False, separators=(",", ":")) + "\n")
        return path
    if kind == "vbench":
        # No local gold: the arm-A-shaped artifact here is the VALIDITY summary
        # (same shape run_vbench_eval writes) plus the uploadable submission.
        n = len(rows)
        valid = sum(int(r.get("valid") or 0) for r in rows)
        summary = [{"track": "agentic", "domain": "agentic", "n": n, "valid": valid,
                    "valid_rate": f"{100.0 * valid / n:.2f}" if n else "0.00",
                    "measurement_card_hash": measurement_card_hash()}]
        path = folder / f"vbench_valid_summary_{slug}.csv"
        write_csv_atomic(path, summary, ["track", "domain", "n", "valid", "valid_rate",
                                         "measurement_card_hash"])
        sub_dir = Path("submissions") / slug
        sub_dir.mkdir(parents=True, exist_ok=True)
        sub_path = sub_dir / f"submission_vbench_{slug}.jsonl"
        with open(sub_path, "w", encoding="utf-8") as f:
            for r in sorted(rows, key=lambda x: int(x["item_id"])):
                value = json.loads(r["answer"]) if r["answer"] else ""
                f.write(json.dumps({"id": int(r["item_id"]), "answer": value},
                                   ensure_ascii=False) + "\n")
        return path
    if kind == "mc":
        # dataset-qualified: two MC arms in the same run would otherwise clobber
        # each other's projection (arm A's own convention: full_evaluation_legal_*, _nli_*)
        path = folder / f"full_evaluation_{dataset}_{slug}.csv"
        cols = ["id", "question", "prompt", "raw_response", "answer", "gold_answer", "correct"]
        out = [{"id": r["item_id"], "question": r["question"],
                "prompt": items_by_id[r["item_id"]]["prompt"],
                "raw_response": r["raw_response"], "answer": r["answer"],
                "gold_answer": r["gold"], "correct": r["correct"]} for r in rows]
    else:
        name = "reading_answers_bidlqa_val" if dataset == "bidlqa_val" else "reading_answers"
        path = folder / f"{name}_{slug}.csv"
        out = [{"dataset": r["dataset"], "item_id": r["item_id"], "stratum": r["stratum"],
                "question": r["question"],
                "context_words": len(items_by_id[r["item_id"]]["prompt"].split()),
                "raw_response": r["raw_response"]} for r in rows]
        cols = ANSWER_COLS
    write_csv_atomic(path, out, cols)
    return path


def write_failures(rows: list[dict], dataset: str, slug: str, folder: Path) -> Path | None:
    """The failure ledger: verbatim, with a diagnosis. Deleted on a clean pass."""
    path = folder / f"harness_failures_{dataset}_{slug}.csv"
    bad = [r for r in rows if r["failure"]]
    if not bad:
        path.unlink(missing_ok=True)
        return None
    write_csv_atomic(path, bad, LEDGER_COLS)
    return path


# ── run ─────────────────────────────────────────────────────────────────
def preflight_endpoint(timeout: float = 45.0) -> None:
    """One cheap direct call before spending a single item.

    A harness arm has no retry of its own: each item is one `omp` process, and a
    dead gateway turns every one of them into a 180-second timeout that would be
    recorded as a legitimate-looking failure. The IEC gateway was observed
    accepting TCP while never answering HTTP (2026-09-27), so "reachable" is
    exactly the wrong thing to check — ask the model, and abort loudly.
    """
    url, api_key, model = COST_BASE_URL, _agent_dir_token(DEFAULT_SYSTEM_AGENT_DIR), COST_MODEL
    key = os.environ.get("IEC_LLM_API_KEY") or api_key or os.environ.get("OPENAI_API_KEY") or ""
    if not key:
        logging.warning("preflight skipped: no API key found in the environment")
        return
    body = {"model": model, "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1, "temperature": 0}
    req = urllib.request.Request(f"{url}/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            resp.read()
    except urllib.error.HTTPError as exc:
        # The gateway is up and ANSWERING — just failing (502 from a dead upstream is
        # the common case, and it looks nothing like a timeout). Say which, because
        # "the endpoint is down" sends you down the wrong path.
        body = (exc.read() or b"")[:200].decode("utf-8", "replace").strip()
        raise SystemExit(
            f"Error: endpoint preflight returned HTTP {exc.code} {exc.reason} after "
            f"{time.time() - started:.0f}s.\n"
            f"  {url} IS answering, but the inference backend is failing — this is an "
            f"upstream outage, not a network problem.\n"
            f"  Body: {body or '(empty)'}\n"
            f"  Refusing to start: every item would be recorded as a model failure. "
            f"Re-run when the backend recovers (nothing is lost: --resume picks up "
            f"from the newest checkpoint).") from exc
    except Exception as exc:
        raise SystemExit(
            f"Error: endpoint preflight failed after {time.time() - started:.0f}s "
            f"({type(exc).__name__}: {exc}).\n"
            f"  {url} accepted the connection but did not answer a 1-token call.\n"
            f"  Refusing to start: a dead gateway would turn every item into a "
            f"--max-time timeout recorded as a model failure. Re-run when it is back "
            f"(nothing is lost: --resume picks up from the newest checkpoint).") from exc
    logging.info("preflight OK (%.1fs) — %s @ %s", time.time() - started, model, url)


def cmd_run(args) -> None:
    kind = ARM_A[args.dataset]["kind"]
    slug = sanitize_model(args.label)
    result_folder, _, logs_folder = model_dirs(args.label)
    setup_logging(logs_folder / f"harness_{args.dataset}_{slug}.log")
    # Must be ABSOLUTE: each item runs with cwd = its own sandbox, so a relative
    # PI_CODING_AGENT_DIR would resolve inside the sandbox and omp would start
    # with no provider config and no token.
    agent_dir = args.agent_dir.resolve()
    if not agent_dir.exists():
        raise SystemExit(f"Error: omp agent dir not found: {agent_dir} "
                         "(see .omp-iec/models.yml — it pins the measured harness)")
    warn_about_scaffold_leaks(agent_dir)
    scratch = Path(args.scratch) if args.scratch else result_folder / "harness_scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    scratch = scratch.resolve()

    preflight_endpoint()
    items = load_items(args.dataset, args.arm_a_slug)
    items_by_id = {it["item_id"]: it for it in items}
    if args.limit:
        items = items[: args.limit]
    total = len(items)

    logging.info("harness=%s label=%s omp=%s model=%s", args.label, slug, args.omp_bin,
                 args.model)
    logging.info("dataset=%s kind=%s n=%d workers=%d tools=%s max_time=%d thinking=%s",
                 args.dataset, kind, total, args.workers, args.tools, args.max_time,
                 args.thinking)
    logging.info("agent_dir=%s (isolated: config+providers+caches) scratch=%s",
                 agent_dir, scratch)

    prefix = f"harness_{args.dataset}_result_"
    existing: dict[str, dict] = {}
    if args.resume:
        cp = find_latest_checkpoint(result_folder, args.label, prefix=prefix)
        if cp:
            logging.info("Resuming from checkpoint: %s", cp)
            with open(cp, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    existing[row["item_id"]] = row
        else:
            others = sorted(result_folder.glob(f"{prefix}*.csv"))
            if others:
                logging.warning("No checkpoint for label '%s' under prefix '%s' — the "
                                "harness_*_result_*.csv files present carry another "
                                "condition. Starting fresh.", args.label, prefix)

    results: list[dict | None] = [None] * total
    to_process = []
    for i, item in enumerate(items):
        if item["item_id"] in existing:
            results[i] = existing[item["item_id"]]
        else:
            to_process.append((i, item))
    logging.info("Remaining: %d/%d", len(to_process), total)

    lock = Lock()
    completed = len(existing)
    start = time.time()

    def process(index: int, item: dict) -> None:
        nonlocal completed
        row, _timing = run_item(item, omp_bin=args.omp_bin, model=args.model,
                                tools=args.tools, max_time=args.max_time,
                                thinking=args.thinking, agent_dir=agent_dir,
                                scratch=scratch, arm=args.dataset,
                                system_prompt=resolve_system_prompt(args))
        with lock:
            results[index] = row
            completed += 1
            done = [r for r in results if r is not None]
            if completed % args.checkpoint_every == 0 or completed == total:
                write_csv_atomic(result_folder / checkpoint_name(args.label, len(done),
                                                               prefix=prefix),
                                 done, LEDGER_COLS)
            if completed % 25 == 0 or completed == total:
                rate = completed / max(time.time() - start, 1e-6)
                logging.info("%d/%d done (%.2f items/s, eta %.1f min)", completed, total,
                             rate, (total - completed) / rate / 60 if rate else 0)

    if to_process:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(process, i, it) for i, it in to_process]
            for fut in as_completed(futs):
                fut.result()
    else:
        logging.info("All items already resolved from checkpoint.")
    logging.info("Time taken: %.1fs (%.2f mins)", time.time() - start,
                 (time.time() - start) / 60)

    done = [r for r in results if r is not None]
    ledger = result_folder / f"harness_ledger_{args.dataset}_{slug}.csv"
    write_csv_atomic(ledger, done, LEDGER_COLS)
    proj = write_projection(done, args.dataset, kind, slug, result_folder, items_by_id)
    fail = write_failures(done, args.dataset, slug, result_folder)
    n_fail = sum(1 for r in done if r["failure"])
    n_net = sum(1 for r in done if r["net_attempt"])
    n_esc = sum(1 for r in done if r["path_escape"])
    n_tool = sum(1 for r in done if int(r["tool_calls"] or 0) > 0)
    logging.info("ledger -> %s", ledger)
    logging.info("projection -> %s (scored by the frozen scorer)", proj)
    logging.info("items=%d failures=%d tool_use=%d net_attempt=%d path_escape=%d",
                 len(done), n_fail, n_tool, n_net, n_esc)
    if fail:
        logging.warning("failure ledger -> %s", fail)
    logging.info("wall/item=%.1fs in=%d out=%d (sum over items)",
                 sum(float(r["wall_s"] or 0) for r in done) / max(len(done), 1),
                 sum(int(r["input_tokens"] or 0) for r in done),
                 sum(int(r["output_tokens"] or 0) for r in done))
    if kind == "reading":
        gold = GOLD_REVIEW_DEFAULT if args.dataset == "reading400" else BIDLQA_VAL_MANIFEST
        logging.info("Next: .venv/bin/python code_benchmark/score_reading_eval.py "
                     "--answers %s --gold %s", proj, gold)


# ── speed / token cost ─────────────────────────────────────────────────
# What does the harness COST, over and above the score it changes? Arm A has no
# per-item timing or token counts on disk (its runner logs aggregate wall time
# only), so the cost of the direct call has to be measured too — on the SAME
# items, at the same worker count, with the same prompt and the card's token
# budget. Nothing here is written into the official arm A/B result files.
SPEED_COLS = ["arm", "dataset", "item_id", "kind", "workers", "wall_s", "model_s",
              "overhead_s", "ttft_s", "calls", "prompt_tokens", "fresh_prompt_tokens",
              "cache_read_tokens", "completion_tokens", "note"]
SPEED_SUMMARY_COLS = ["arm", "dataset", "n", "workers", "wall_p50_s", "wall_mean_s",
                      "items_per_min", "prompt_tok_per_item", "completion_tok_per_item",
                      "total_tok_per_item", "overhead_s_per_item", "note"]
# Token budgets of the arm A cards (MC-3b/10/13 = 4, MC-3 = 48).
ARM_A_MAX_TOKENS = {"mc": 4, "reading": 48, "vbench": 512}
# The cost probe names the model explicitly instead of reading OPENAI_MODEL from
# .env — .env currently points at a model the IEC gateway no longer serves, and
# a speed measurement of the wrong model would be worse than no measurement.
COST_BASE_URL = "https://llmapi.iec-uit.com/v1"
COST_MODEL = "Qwen3.5-9B-28K"


def resolve_system_prompt(args) -> str | None:
    """`--system-prompt minimal` -> MINIMAL_SYSTEM_PROMPT; other values verbatim.

    Returning None means "keep omp's own coding-agent system prompt" (the H2
    condition). The sentinel exists so the ablation prompt is defined once, in
    code, instead of being retyped on a command line and drifting from the card.
    """
    value = getattr(args, "system_prompt", None)
    if not value:
        return None
    if value.strip().lower() == "minimal":
        return MINIMAL_SYSTEM_PROMPT
    return value


def _agent_dir_token(agent_dir: Path) -> str:
    """The gateway token, read from the harness's own .env (never hardcoded)."""
    env = agent_dir / ".env"
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("IEC_LLM_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def resolve_cost_endpoint(args) -> tuple[str, str, str]:
    """(base_url, api_key, model) for the direct-call cost probe."""
    base_url = args.cost_base_url or COST_BASE_URL
    model = args.cost_model or COST_MODEL
    api_key = (args.cost_api_key or _agent_dir_token(args.agent_dir.resolve())
               or os.environ.get("OPENAI_API_KEY") or "")
    if not api_key:
        raise SystemExit("Error: no API key for the cost probe — set --cost-api-key, "
                         f"or put IEC_LLM_API_KEY in {args.agent_dir}/.env")
    return base_url, api_key, model


def _pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    return s[min(int(q * len(s)), len(s) - 1)]


def _arm_a_cost_probe(item: dict, *, client, model: str, temperature: float,
                      seed: int, max_tokens: int, workers: int) -> dict:
    """One direct API call, timed, with the response's own usage numbers.

    Same prompt bytes as the arm, same temperature/seed, same budget as the card.
    A speed measurement only — its answers never enter any result file.
    """
    started = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": item["prompt"]}],
        temperature=temperature, seed=seed, max_tokens=max_tokens)
    wall = time.time() - started
    usage = getattr(resp, "usage", None)
    return {"arm": "A_direct", "dataset": item["dataset"], "item_id": item["item_id"],
            "kind": item["kind"], "workers": workers, "wall_s": wall, "model_s": wall,
            "overhead_s": 0.0, "ttft_s": float("nan"), "calls": 1,
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "fresh_prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "cache_read_tokens": 0,
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "note": f"max_tokens={max_tokens}"}


def _arm_b_cost_probe(item: dict, *, args, agent_dir: Path, scratch: Path,
                      workers: int) -> dict:
    _row, t = run_item(item, omp_bin=args.omp_bin, model=args.model, tools=args.tools,
                       max_time=args.max_time, thinking=args.thinking,
                       agent_dir=agent_dir, scratch=scratch, arm=args.dataset,
                       system_prompt=resolve_system_prompt(args))
    return {"arm": "B_omp_h2", "dataset": item["dataset"], "item_id": item["item_id"],
            "kind": item["kind"], "workers": workers,
            "wall_s": t["wall_s"], "model_s": t["model_s"], "overhead_s": t["overhead_s"],
            "ttft_s": t["ttft_s"], "calls": t["calls"],
            "prompt_tokens": t["prompt_tokens"],
            "fresh_prompt_tokens": t["fresh_prompt_tokens"],
            "cache_read_tokens": t["cache_read_tokens"],
            "completion_tokens": t["completion_tokens"],
            "note": "system prompt + tool schemas included in prompt_tokens"}


def _speed_summary(rows: list[dict], dataset: str, workers: int) -> list[dict]:
    out = []
    for arm in ("A_direct", "B_omp_h2"):
        sub = [r for r in rows if r["arm"] == arm and r["workers"] == workers]
        if not sub:
            continue
        n = len(sub)
        wall = [float(r["wall_s"]) for r in sub]
        mean_wall = sum(wall) / n
        out.append({
            "arm": arm, "dataset": dataset, "n": n, "workers": workers,
            "wall_p50_s": f"{_pct(wall, 0.5):.2f}", "wall_mean_s": f"{mean_wall:.2f}",
            "items_per_min": f"{60.0 / mean_wall * workers:.1f}",
            "prompt_tok_per_item": f"{sum(int(r['prompt_tokens']) for r in sub) / n:.0f}",
            "completion_tok_per_item": f"{sum(int(r['completion_tokens']) for r in sub) / n:.0f}",
            "total_tok_per_item": f"{sum(int(r['prompt_tokens']) + int(r['completion_tokens']) for r in sub) / n:.0f}",
            "overhead_s_per_item": f"{sum(float(r['overhead_s']) for r in sub) / n:.2f}",
            "note": sub[0]["note"],
        })
    return out


def _speed_table(summary: list[dict]) -> str:
    head = ("| arm | n | workers | wall p50 | wall TB/s/item | items/min | "
            "prompt tok/item | completion tok/item | total tok/item | overhead/item |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    lines = [head]
    for r in summary:
        lines.append(f"| {r['arm']} | {r['n']} | {r['workers']} | {r['wall_p50_s']}s | "
                     f"{r['wall_mean_s']}s | {r['items_per_min']} | "
                     f"{r['prompt_tok_per_item']} | {r['completion_tok_per_item']} | "
                     f"{r['total_tok_per_item']} | {r['overhead_s_per_item']}s |")
    return "\n".join(lines)


def cmd_speed(args) -> None:
    kind = ARM_A[args.dataset]["kind"]
    items = load_items(args.dataset, args.arm_a_slug)[: args.limit]
    n = len(items)
    slug = sanitize_model(args.label)
    result_folder, _, logs_folder = model_dirs(args.label)
    setup_logging(logs_folder / f"speed_{args.dataset}_{slug}.log")
    agent_dir = args.agent_dir.resolve()
    scratch = (Path(args.scratch) if args.scratch else result_folder / "speed_scratch")
    scratch.mkdir(parents=True, exist_ok=True)
    scratch = scratch.resolve()
    warn_about_scaffold_leaks(agent_dir)

    base_url, api_key, model_a = resolve_cost_endpoint(args)
    client = build_client(base_url, api_key)
    verify_credentials(client, model_a)
    logging.info("speed probe: dataset=%s n=%d workers=%d max_tokens=%s model=%s @ %s",
                 args.dataset, n, args.workers, ARM_A_MAX_TOKENS[kind], model_a, base_url)

    rows: list[dict] = []
    # ── arm A: direct calls, same items, same concurrency ────────────────
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_arm_a_cost_probe, it, client=client, model=model_a,
                          temperature=args.temperature, seed=args.seed,
                          max_tokens=ARM_A_MAX_TOKENS[kind], workers=args.workers)
                for it in items]
        for fut in as_completed(futs):
            rows.append(fut.result())
    a_wall = time.time() - start

    # ── arm B: the harness, same items, same concurrency ─────────────────
    lock = Lock()
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_arm_b_cost_probe, it, args=args, agent_dir=agent_dir,
                          scratch=scratch, workers=args.workers) for it in items]
        for fut in as_completed(futs):
            with lock:
                rows.append(fut.result())
    b_wall = time.time() - start

    rows.sort(key=lambda r: (r["arm"], str(r["item_id"])))
    tag = f"_{args.tag}" if args.tag else ""
    out_rows = result_folder / f"speed_arms_{args.dataset}{tag}_{slug}.csv"
    write_csv_atomic(out_rows, rows, SPEED_COLS)
    summary = _speed_summary(rows, args.dataset, args.workers)
    out_sum = result_folder / f"speed_summary_{args.dataset}{tag}_{slug}.csv"
    write_csv_atomic(out_sum, summary, SPEED_SUMMARY_COLS)

    print(f"\nspeed/token cost — {args.dataset} (n={n}, workers={args.workers}, "
          f"max_tokens={ARM_A_MAX_TOKENS[kind]})")
    print(_speed_table(summary))
    if len(summary) == 2:
        a, b = summary
        print(f"\n  wall/item  x{b['wall_mean_s'] and round(float(b['wall_mean_s'])/float(a['wall_mean_s']), 1)}"
              f"   tokens/item x{round(float(b['total_tok_per_item'])/float(a['total_tok_per_item']), 1)}"
              f"   prompt tokens x{round(float(b['prompt_tok_per_item'])/max(float(a['prompt_tok_per_item']), 1), 1)}"
              f"   completion tokens x{round(float(b['completion_tok_per_item'])/max(float(a['completion_tok_per_item']), 1), 1)}")
        print(f"  batch wall for {n} items: arm A {a_wall:.1f}s ({a_wall/60:.1f} min)"
              f" | arm B {b_wall:.1f}s ({b_wall/60:.1f} min)"
              f" -> x{b_wall/max(a_wall, 1e-6):.1f}")
        oh = float(b["overhead_s_per_item"])
        print(f"  of arm B's wall, {oh}s/item is harness process overhead (spawn + config"
              f" + teardown), the rest is the model call.")
    print(f"  -> {out_rows}\n  -> {out_sum}\n")


# ── compare ─────────────────────────────────────────────────────────────
def _mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar on the discordant pairs (stdlib binomial)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def _paired_bootstrap(diffs: list[int], iters: int = 10000, seed: int = 42) -> tuple[float, float]:
    """95% CI of the mean paired difference, deterministic given the seed."""
    if not diffs:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(diffs)
    means = []
    for _ in range(iters):
        total = 0
        for _ in range(n):
            total += diffs[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[min(int(0.975 * iters), iters - 1)]
    return lo * 100, hi * 100


def _mc_eval_path(folder: Path, dataset: str, slug: str) -> Path:
    """Per-item MC file for one arm, whatever naming that arm used.

    The harness arms write `full_evaluation_<dataset>_<slug>.csv`; the historical
    direct-prompt runs carry their own infix (`full_evaluation_legal_*`,
    `full_evaluation_nli_*`). Both must be readable as the *baseline* side of a
    comparison, because arm-vs-arm (H1 vs H2) is a legitimate question here.
    """
    candidates = [folder / f"full_evaluation_{dataset}_{slug}.csv",
                  folder / ARM_A[dataset]["eval"].format(a=slug)]
    for path in candidates:
        if path.exists():
            return path
    raise SystemExit(f"Error: no per-item MC file for '{slug}' under {folder} "
                     f"(looked for {[p.name for p in candidates]}) — run that arm first")


def _vbench_validity(folder: Path, slug: str, dataset: str, *, harness_arm: bool) -> dict | None:
    """Per-item SCHEMA VALIDITY for a V-Bench arm: {id: 0/1}.

    No gold exists locally, so validity is the only per-item bit both arms can
    produce — for the direct arm it is "the shipped answer cell was non-empty"
    (its own `vbench_valid_summary` was computed exactly that way), for a harness
    arm it is the frozen parser's verdict recorded per item in the ledger.
    Returns None when the direct arm's checkpoint is absent, so the caller can
    fall back to the aggregate comparison and say so.
    """
    if harness_arm:
        rows = read_csv_checked(folder / f"harness_ledger_{dataset}_{slug}.csv",
                                required={"item_id", "valid"}, label="harness ledger")
        return {str(r["item_id"]): int(r["valid"] or 0) for r in rows}
    checkpoints = sorted(folder.glob(f"vbench_result_*_{slug}.csv"))
    if not checkpoints:
        return None
    counts = [(int(m.group(1)), p) for p in checkpoints
              if (m := re.search(r"vbench_result_(\d+)_", p.name))]
    latest = max(counts)[1]
    with open(latest, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {str(r["id"]): int(bool(str(r.get("answer", "")).strip())) for r in rows}


def _arm_a_correct_rows(dataset: str, arm_a: str) -> list[tuple[str, int]]:
    """Per-item arm A correctness, read from the baseline's own frozen outputs.

    Reading keys are `dataset:item_id` — the two reading sources reuse id values
    (squad "5" and drop question_id "5" both exist), so keying on item_id alone
    silently collapsed 400 rows into 393.
    """
    spec = ARM_A[dataset]
    folder = RESULTS_DIR / arm_a
    if spec["kind"] == "vbench_mc":
        letters = _vbench_mc_letters(folder, arm_a, harness_arm=False)
        if letters is None:
            raise SystemExit(f"Error: arm A has no vbench_result_*_{arm_a}.csv — its MC "
                             f"answers are the only local reference for agreement")
        return list(letters.items())
    if spec["kind"] == "vbench":
        per_item = _vbench_validity(folder, arm_a, dataset, harness_arm=False)
        if per_item is not None:
            return list(per_item.items())
        summary = read_csv_checked(folder / spec["scores"].format(a=arm_a),
                                   required={"track", "n", "valid"}, label="arm A")
        row = next((r for r in summary if r["track"] == "agentic"), None)
        if row is None:
            raise SystemExit(f"Error: no agentic row in {folder / spec['scores'].format(a=arm_a)}")
        logging.warning("arm A has no per-item V-Bench checkpoint — comparing AGGREGATE "
                        "validity only (%s/%s); no paired test", row["valid"], row["n"])
        return [("__aggregate__", int(row["valid"]))]
    if spec["kind"] == "mc":
        path = _mc_eval_path(folder, dataset, arm_a)
        rows = read_csv_checked(path, required={"id", "gold_answer", "correct"}, label="arm A")
        return [(str(r["id"]), int(r["correct"])) for r in rows]
    path = folder / spec["scores"].format(a=arm_a)
    rows = read_csv_checked(path, required={"dataset", "item_id", "em"}, label="arm A")
    return [(item_key(r), int(r["em"])) for r in rows]


def _vbench_mc_letters(folder: Path, slug: str, *, harness_arm: bool) -> dict | None:
    """Per-item shipped LETTER for a V-Bench MC arm: {id: "A".."E" or ""}.

    No gold exists locally, so the pairable bit is agreement with arm A, not
    correctness. The direct arm's letters come from its own checkpoint (the same
    `answer` column its submission shipped); a harness arm's from the ledger.
    """
    if harness_arm:
        path = folder / f"harness_ledger_vbench_mc_{slug}.csv"
        if not path.exists():
            return None
        rows = read_csv_checked(path, required={"item_id", "answer"}, label="harness ledger")
        return {str(r["item_id"]): str(r["answer"] or "") for r in rows}
    checkpoints = [p for p in folder.glob(f"vbench_result_*_{slug}.csv")
                   if re.search(r"vbench_result_(\d+)_", p.name)]
    if not checkpoints:
        return None
    latest = max(checkpoints, key=lambda p: int(re.search(r"vbench_result_(\d+)_", p.name).group(1)))
    with open(latest, encoding="utf-8", newline="") as f:
        return {str(r["id"]): str(r.get("answer") or "") for r in csv.DictReader(f)}


def _arm_b_correct_rows(dataset: str, slug: str) -> list[tuple[str, int]]:
    spec = ARM_A[dataset]
    folder = RESULTS_DIR / slug
    if spec["kind"] == "vbench_mc":
        letters = _vbench_mc_letters(folder, slug, harness_arm=True)
        if letters is None:
            raise SystemExit(f"Error: no harness ledger for {dataset} under {folder}")
        return list(letters.items())
    if spec["kind"] == "vbench":
        per_item = _vbench_validity(folder, slug, dataset, harness_arm=True)
        if per_item is None:
            raise SystemExit(f"Error: no harness ledger for {dataset} under {folder}")
        return list(per_item.items())
    if spec["kind"] == "mc":
        path = _mc_eval_path(folder, dataset, slug)
    else:
        name = "reading_scores_bidlqa_val" if dataset == "bidlqa_val" else "reading_scores"
        path = folder / f"{name}_{slug}.csv"
    if not path.exists():
        raise SystemExit(f"Error: {path} not found — run the arm, then score it "
                         "(score_reading_eval.py for reading sets) before comparing")
    if spec["kind"] == "mc":
        rows = read_csv_checked(path, required={"id", "correct"}, label="arm B")
        return [(str(r["id"]), int(r["correct"])) for r in rows]
    rows = read_csv_checked(path, required={"dataset", "item_id", "em"}, label="arm B")
    return [(item_key(r), int(r["em"])) for r in rows]


def cmd_compare(args) -> None:
    slug = sanitize_model(args.label)
    card_hash = measurement_card_hash()
    a_rows = dict(_arm_a_correct_rows(args.dataset, args.arm_a_slug))
    b_rows = dict(_arm_b_correct_rows(args.dataset, slug))
    aggregate_only = "__aggregate__" in a_rows

    if aggregate_only:
        # No per-item table on the arm-A side: report the two rates and stop —
        # a CI or a McNemar over one aggregate pair would be theatre.
        summary_rows = read_csv_checked(RESULTS_DIR / args.arm_a_slug
                                        / ARM_A[args.dataset]["scores"].format(a=args.arm_a_slug),
                                        required={"track", "n", "valid"}, label="arm A")
        row = next(r for r in summary_rows if r["track"] == "agentic")
        n_a, valid_a = int(row["n"]), int(row["valid"])
        n_b = len(b_rows)
        valid_b = sum(b_rows.values())
        rate_a, rate_b = 100.0 * valid_a / n_a, 100.0 * valid_b / n_b
        out = [{"metric": "valid_rate", "group": "ALL", "n": n_b,
                "arm_a": f"{rate_a:.2f}", "arm_b": f"{rate_b:.2f}",
                "delta": f"{rate_b - rate_a:+.2f}", "ci95_low": "", "ci95_high": "",
                "mcnemar_p": "", "a_only": "", "b_only": "", "both": "", "neither": "",
                "arm_b_failures": "", "measurement_card_hash": card_hash}]
        tag = f"_{args.tag}" if args.tag else ""
        path = RESULTS_DIR / slug / f"harness_compare_{args.dataset}{tag}_{slug}.csv"
        write_csv_atomic(path, out, COMPARE_COLS)
        print(f"\n{args.dataset} (schema validity, AGGREGATE ONLY — arm A has no per-item "
              f"table)\n  arm A {valid_a}/{n_a} = {rate_a:.2f}%   arm B {valid_b}/{n_b} = "
              f"{rate_b:.2f}%   delta {rate_b - rate_a:+.2f}")
        print("  NOTE: no paired test — upload arm B's submission to vbench.ai for the "
              "server-side score.\n  -> " + str(path) + "\n")
        return

    if ARM_A[args.dataset]["kind"] == "vbench_mc":
        shared = [k for k in a_rows if k in b_rows]
        if not shared:
            raise SystemExit(f"Error: no shared items between {args.dataset} arms")
        n = len(shared)
        same = sum(1 for k in shared if a_rows[k] and a_rows[k] == b_rows[k])
        blanks_b = sum(1 for k in shared if not b_rows[k])
        blanks_a = sum(1 for k in shared if not a_rows[k])
        rate = 100.0 * same / n
        lo, hi = _paired_bootstrap([int(a_rows[k] == b_rows[k]) for k in shared])
        tag = f"_{args.tag}" if args.tag else ""
        out = [{"metric": "agreement_with_arm_A", "group": "ALL", "n": n,
                "arm_a": "100.00", "arm_b": f"{rate:.2f}",
                "delta": f"{rate - 100.0:+.2f}", "ci95_low": f"{lo * 100 - 100.0:.2f}",
                "ci95_high": f"{hi * 100 - 100.0:.2f}",
                # arm A trivially agrees with itself: McNemar here would test
                # "is the disagreement rate 50%?", which is not a question worth
                # asking. Left empty on purpose.
                "mcnemar_p": "", "a_only": "", "b_only": "",
                "both": same, "neither": n - same,
                "arm_b_failures": blanks_b, "measurement_card_hash": card_hash}]
        path = RESULTS_DIR / slug / f"harness_compare_{args.dataset}{tag}_{slug}.csv"
        write_csv_atomic(path, out, COMPARE_COLS)
        print(f"\n{args.dataset} (AGREEMENT with arm A — no local gold, so this is NOT "
              f"accuracy)\n  n={n} | trùng khớp {same} = {rate:.2f}% "
              f"(CI {lo * 100 - 100.0:+.2f}..{hi * 100 - 100.0:+.2f}) | khác {n - same}"
              f"\n  answer rỗng: arm A {blanks_a} · arm B {blanks_b}")
        print("  Accuracy chỉ có ở server: nộp file trong submissions/<slug>/ để lấy điểm."
              "\n  -> " + str(path) + "\n")
        return

    shared = [k for k in a_rows if k in b_rows]
    if not shared:
        raise SystemExit(f"Error: no shared items between {args.dataset} arms")
    if len(shared) != ARM_A[args.dataset]["n"]:
        logging.warning("compared %d/%d items — the arms do not cover the same set",
                        len(shared), ARM_A[args.dataset]["n"])

    both = sum(1 for k in shared if a_rows[k] and b_rows[k])
    a_only = sum(1 for k in shared if a_rows[k] and not b_rows[k])
    b_only = sum(1 for k in shared if not a_rows[k] and b_rows[k])
    neither = len(shared) - both - a_only - b_only
    n = len(shared)
    rate_a = (both + a_only) / n * 100
    rate_b = (both + b_only) / n * 100
    diffs = [b_rows[k] - a_rows[k] for k in shared]
    lo, hi = _paired_bootstrap(diffs)
    p = _mcnemar_p(a_only, b_only)

    ledger_path = RESULTS_DIR / slug / f"harness_ledger_{args.dataset}_{slug}.csv"
    cost = {}
    if ledger_path.exists():
        led = read_csv_checked(ledger_path, required={"item_id"}, label="ledger")
        cost = {
            "failures": sum(1 for r in led if r.get("failure")),
            "tool_use": sum(1 for r in led if int(r.get("tool_calls") or 0) > 0),
            "net_attempt": sum(1 for r in led if r.get("net_attempt")),
            "path_escape": sum(1 for r in led if r.get("path_escape")),
            "wall_s": sum(float(r.get("wall_s") or 0) for r in led) / max(len(led), 1),
            "input_tokens": sum(int(r.get("input_tokens") or 0) for r in led) / max(len(led), 1),
            "output_tokens": sum(int(r.get("output_tokens") or 0) for r in led) / max(len(led), 1),
            "turns": sum(int(r.get("turns") or 0) for r in led) / max(len(led), 1),
        }

    # The metric NAME is the whole point of a label: a V-Bench agentic row
    # measured against schema validity must never be filed as "EM" (it is not
    # exact match, and there is no gold at all) — MC-26.
    metric = {"mc": "accuracy", "reading": "EM", "vbench": "valid_rate"}[ARM_A[args.dataset]["kind"]]
    out = [{"metric": metric, "group": "ALL", "n": n,
            "arm_a": f"{rate_a:.2f}", "arm_b": f"{rate_b:.2f}",
            "delta": f"{rate_b - rate_a:+.2f}", "ci95_low": f"{lo:.2f}",
            "ci95_high": f"{hi:.2f}", "mcnemar_p": f"{p:.4g}",
            "a_only": a_only, "b_only": b_only, "both": both, "neither": neither,
            "arm_b_failures": cost.get("failures", ""),
            "measurement_card_hash": card_hash}]
    tag = f"_{args.tag}" if args.tag else ""
    path = RESULTS_DIR / slug / f"harness_compare_{args.dataset}{tag}_{slug}.csv"
    write_csv_atomic(path, out, COMPARE_COLS)

    print(f"\n{args.dataset} ({metric}, n={n})  arm A {args.arm_a_slug} vs arm B {args.label}")
    print(f"  arm A {rate_a:.2f}%   arm B {rate_b:.2f}%   delta {rate_b - rate_a:+.2f} "
          f"(95% CI {lo:+.2f}..{hi:+.2f}, McNemar p={p:.4g})")
    print(f"  both {both} | A only {a_only} | B only {b_only} | neither {neither}")
    if cost:
        print(f"  cost/item: wall {cost['wall_s']:.1f}s turns {cost['turns']:.2f} "
              f"in {cost['input_tokens']:.0f} out {cost['output_tokens']:.0f} tok")
        print(f"  audit: failures {cost['failures']} | items using tools "
              f"{cost['tool_use']} | network attempts {cost['net_attempt']} "
              f"| path escapes {cost['path_escape']}")
    print(f"  -> {path}\n")


# ── cli ─────────────────────────────────────────────────────────────────
def parse_args():
    ap = argparse.ArgumentParser(
        description="omp harness arm: same model, same endpoint, agent scaffold instead "
                    "of a direct prompt.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run a dataset through the omp harness")
    run.add_argument("--dataset", required=True, choices=sorted(ARM_A))
    run.add_argument("--label", default=DEFAULT_LABEL,
                     help=f"run label -> model slug / checkpoint namespace (default: {DEFAULT_LABEL})")
    run.add_argument("--model", default=DEFAULT_MODEL,
                     help=f"omp model ref (default: {DEFAULT_MODEL})")
    run.add_argument("--omp-bin", default=DEFAULT_OMP)
    run.add_argument("--agent-dir", type=Path, default=AGENT_DIR_DEFAULT,
                     help="PI_CODING_AGENT_DIR pinning the measured harness (default: .omp-iec)")
    run.add_argument("--tools", default=DEFAULT_TOOLS,
                     help="tool menu, or 'none' for the no-tool ablation arm (H1)")
    run.add_argument("--system-prompt", default=None,
                     help="'minimal' for the no-persona ablation arm (H3) — replaces "
                          f"omp's coding-agent system prompt with {MINIMAL_SYSTEM_PROMPT!r}; "
                          "any other value is passed to omp verbatim; default keeps omp's")
    run.add_argument("--thinking", default="off")
    run.add_argument("--max-time", type=int, default=180,
                     help="per-item wall budget for the agent loop (omp --max-time)")
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--limit", type=int, default=None, help="smoke: first N items only")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--checkpoint-every", type=int, default=25)
    run.add_argument("--scratch", type=Path, default=None,
                     help="where item sandboxes + transcripts go (default: inside the model dir)")
    run.add_argument("--arm-a-slug", default="Qwen3_5-9B-28K",
                     help="arm A model dir, used to verify prompt parity")
    run.set_defaults(func=cmd_run)

    cmp_ = sub.add_parser("compare", help="paired arm A vs arm B on the same items")
    cmp_.add_argument("--dataset", required=True, choices=sorted(ARM_A))
    cmp_.add_argument("--label", default=DEFAULT_LABEL)
    cmp_.add_argument("--arm-a-slug", default="Qwen3_5-9B-28K")
    cmp_.add_argument("--tag", default="",
                      help="suffix for the output filename — use it when comparing a "
                           "second arm against the same label, or the tables overwrite")
    cmp_.set_defaults(func=cmd_compare)

    sp = sub.add_parser("speed",
                        help="cost probe: direct call vs harness on the same items "
                             "(wall time, prompt/completion tokens, process overhead)")
    sp.add_argument("--dataset", required=True, choices=sorted(ARM_A))
    sp.add_argument("--limit", type=int, default=40,
                    help="items per arm (default: 40 — a cost probe, not a benchmark)")
    sp.add_argument("--workers", type=int, default=4)
    sp.add_argument("--label", default=DEFAULT_LABEL)
    sp.add_argument("--model", default=DEFAULT_MODEL)
    sp.add_argument("--omp-bin", default=DEFAULT_OMP)
    sp.add_argument("--agent-dir", type=Path, default=AGENT_DIR_DEFAULT)
    sp.add_argument("--tools", default=DEFAULT_TOOLS)
    sp.add_argument("--system-prompt", default=None,
                    help="'minimal' for the no-persona arm (H3)")
    sp.add_argument("--thinking", default="off")
    sp.add_argument("--max-time", type=int, default=180)
    sp.add_argument("--scratch", type=Path, default=None)
    sp.add_argument("--tag", default="",
                    help="suffix for the output filenames, so several sweeps can coexist")
    sp.add_argument("--arm-a-slug", default="Qwen3_5-9B-28K")
    sp.add_argument("--cost-base-url", default=None, help=f"default: {COST_BASE_URL}")
    sp.add_argument("--cost-model", default=None,
                    help=f"model for the DIRECT call (default: {COST_MODEL}) — named "
                         "explicitly, never read from .env")
    sp.add_argument("--cost-api-key", default=None,
                    help="default: IEC_LLM_API_KEY from <agent-dir>/.env, else OPENAI_API_KEY")
    sp.add_argument("--temperature", type=float, default=0.0)
    sp.add_argument("--seed", type=int, default=42)
    sp.set_defaults(func=cmd_speed)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if args.cmd == "run" and args.limit is not None and args.limit <= 0:
        raise SystemExit("Error: --limit must be > 0")
    args.func(args)


if __name__ == "__main__":
    main()
