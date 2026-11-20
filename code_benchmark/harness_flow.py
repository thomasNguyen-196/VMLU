"""One action timeline per agent attempt (dsh or omp), from the harness's event stream and the proxy's records.

Every harness calls the same model API. What sets a harness apart is what happens around those calls: which actions
the model takes through it, what the harness shows back, and what the harness does on its own (design §8 of
openspec/changes/diagnostic-legal-agent-omp-prompt). Descriptive; reads files only, never calls a model.

`attempt_flow(attempt_dir, harness)` returns a Flow:
  steps   in order, each {"actor", "kind", ...}:
          model    think(chars) | call(tool, pattern, path, offset, limit, intent) | answer(chars)
          tool     result(tool, error, chars, empty, matches, files, shown, total, window, elided, truncated)
          harness  compact(reason, action, summary_chars, summary_lang) | notice(text, tokens) | end(reason)
  calls   the proxied API requests by request number: kind step | handoff | resend | refused | cancelled | failed,
          with tokens, latency and outcome
  tokens  a compact action string: G+ G0 Gx (grep with matches, none, error), F+ F0 Fx (glob), R (read shown
          whole), Rm (a window the model asked for), Rh (a window the harness cut), Re (omp elided the middle),
          Rx (read error), C (compaction), A (answer), E (ended without an answer)
  answer_context  what the final answering request held: tool results, characters, whether a compaction hand-off
                  had replaced the context
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DSH_FOUND = re.compile(r"^Found (\d+) match", re.MULTILINE)
_OMP_MATCH_LINE = re.compile(r"^\*\d+\|", re.MULTILINE)
_OMP_FILE = re.compile(r"^# (\S+\.txt)\s*$", re.MULTILINE)
_DSH_FILE = re.compile(r"^(\S+\.txt)\s*$", re.MULTILINE)
_OMP_SHOWN = re.compile(r"\[Showing lines (\d+)-(\d+)(?: and (\d+)-(\d+))? of ([\d,]+)")
_DSH_SHOWN = re.compile(r"\(Showing lines (\d+)-(\d+) of ([\d,]+)")
_DSH_LINE = re.compile(r"^(\d+): ?", re.MULTILINE)
_TRUNCATED = re.compile(r"\[Some lines truncated to \d+ chars\]|\(Omitted \d+ bytes|KB limit\)|results limit reached"
                        r"|\(Showing \d+ of \d+ paths")
_NOTICE_TOKENS = re.compile(r"~?([\d,]+) tokens")
_HANDOFF = "Context replaced."
_VI_LETTER = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.IGNORECASE)
END_ANSWERED = "completed"


@dataclass
class Flow:
    harness: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    answer_context: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens(self) -> list[str]:
        out = []
        for s in self.steps:
            if s["kind"] == "result":
                out.append(result_token(s))
            elif s["kind"] == "compact" and s.get("phase") == "end":
                out.append("C")
            elif s["kind"] == "answer":
                out.append("A")
            elif s["kind"] == "end" and s["reason"] != END_ANSWERED:
                out.append("E")
        return out


def language(text: str) -> str:
    """'vi' when at least 3% of the letters carry a Vietnamese diacritic, else 'en' (a rough tag, not a detector)."""
    letters = [ch for ch in unicodedata.normalize("NFC", text) if ch.isalpha()]
    if not letters:
        return "none"
    return "vi" if sum(bool(_VI_LETTER.match(ch)) for ch in letters) / len(letters) >= 0.03 else "en"


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _text(value.get("content"))
    if isinstance(value, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in value)
    return "" if value is None else str(value)


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def describe_result(tool: str, text: str, error: bool, args: dict[str, Any]) -> dict[str, Any]:
    """What the harness showed back for one tool call."""
    out: dict[str, Any] = {"actor": "tool", "kind": "result", "tool": tool, "error": error, "chars": len(text),
                           "truncated": bool(_TRUNCATED.search(text))}
    if tool == "grep":
        found = _DSH_FOUND.search(text)
        out["empty"] = text.strip().startswith("No matches found")
        out["matches"] = 0 if out["empty"] else (int(found.group(1)) if found else len(_OMP_MATCH_LINE.findall(text)))
        out["files"] = sorted(set(_OMP_FILE.findall(text)) | set(_DSH_FILE.findall(text)))
    elif tool == "glob":
        out["empty"] = not text.strip() or text.strip().startswith("No ")
        out["matches"] = 0 if out["empty"] else len([line for line in text.splitlines() if line.strip().endswith(".txt")])
    elif tool == "read":
        omp, dsh = _OMP_SHOWN.search(text), _DSH_SHOWN.search(text)
        asked = any(args.get(k) not in (None, "", 0) for k in ("offset", "limit")) or bool(
            re.search(r":\d", str(args.get("path") or "")))
        if omp:
            out["shown"] = [int(omp.group(1)), int(omp.group(2))]
            out["total"] = int(omp.group(5).replace(",", ""))
            out["elided"] = bool(omp.group(3))
        elif dsh:
            out["shown"] = [int(dsh.group(1)), int(dsh.group(2))]
            out["total"] = int(dsh.group(3).replace(",", ""))
            out["elided"] = False
        elif "<content>" in text:  # dsh shows numbered lines; no note when the window reached the file's end
            numbers = [int(n) for n in _DSH_LINE.findall(text.split("<content>\n", 1)[-1])]
            if numbers:
                out["shown"], out["elided"] = [min(numbers), max(numbers)], False
        # whose window: the model asked for a range, the harness cut the file (a paging note), or the whole file
        out["window"] = "model" if asked else ("harness" if "total" in out else None)
    return out


def result_token(step: dict[str, Any]) -> str:
    tool = step["tool"]
    if tool == "grep":
        return "Gx" if step["error"] else ("G0" if step.get("empty") else "G+")
    if tool == "glob":
        return "Fx" if step["error"] else ("F0" if step.get("empty") else "F+")
    if tool == "read":
        if step["error"]:
            return "Rx"
        if step.get("elided"):
            return "Re"
        return {"model": "Rm", "harness": "Rh"}.get(step.get("window") or "", "R")
    return f"{tool[:1].upper()}?"


def _call(tool: str, args: dict[str, Any], intent: str | None = None) -> dict[str, Any]:
    path = args.get("path") or args.get("file_path") or args.get("filePath")
    return {"actor": "model", "kind": "call", "tool": tool, "pattern": args.get("pattern"), "path": path,
            "offset": args.get("offset"), "limit": args.get("limit"), "intent": intent}


# ---------------------------------------------------------------- the two harnesses' event streams

def dsh_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    calls: dict[str, dict[str, Any]] = {}
    for e in events:
        kind = e.get("type")
        if kind == "thinking":
            steps.append({"actor": "model", "kind": "think", "chars": len(str(e.get("text") or ""))})
        elif kind == "tool_call":
            args = e.get("input") or {}
            calls[str(e.get("callId"))] = {"tool": e.get("tool"), "args": args}
            steps.append(_call(str(e.get("tool")), args))
        elif kind == "tool_result":
            call = calls.get(str(e.get("callId")), {"tool": "?", "args": {}})
            steps.append(describe_result(str(call["tool"]), _text(e.get("result")), e.get("status") != "completed",
                                         call["args"]))
        elif kind == "final":
            reason = (e.get("reason") or {}).get("kind") or "unknown"
            if reason == END_ANSWERED and str(e.get("text") or "").strip():
                steps.append({"actor": "model", "kind": "answer", "chars": len(str(e.get("text")))})
            steps.append({"actor": "harness", "kind": "end", "reason": reason})
    return steps


_OMP_STOP = {"stop": END_ANSWERED, "length": "max-tokens", "error": "error", "aborted": "aborted", "toolUse": "tool-use"}


def omp_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    args_of: dict[str, dict[str, Any]] = {}
    last_stop = None
    answered = False
    for e in events:
        kind = e.get("type")
        if kind == "message_end" and (e.get("message") or {}).get("role") == "assistant":
            message = e["message"]
            last_stop = message.get("stopReason")
            for part in message.get("content") or []:
                if part.get("type") == "thinking":
                    steps.append({"actor": "model", "kind": "think", "chars": len(str(part.get("thinking") or ""))})
            text = "".join(p.get("text", "") for p in message.get("content") or [] if p.get("type") == "text")
            if last_stop == "stop" and text.strip():
                steps.append({"actor": "model", "kind": "answer", "chars": len(text)})
                answered = True
        elif kind == "tool_execution_start":
            args = e.get("args") or {}
            args_of[str(e.get("toolCallId"))] = args
            steps.append(_call(str(e.get("toolName")), args, e.get("intent")))
        elif kind == "tool_execution_end":
            steps.append(describe_result(str(e.get("toolName")), _text(e.get("result")), bool(e.get("isError")),
                                         args_of.get(str(e.get("toolCallId")), {})))
        elif kind == "auto_compaction_start":
            steps.append({"actor": "harness", "kind": "compact", "phase": "start", "reason": e.get("reason"),
                          "action": e.get("action")})
        elif kind == "auto_compaction_end":
            summary = str(((e.get("result") or {}).get("summary")) or "")
            steps.append({"actor": "harness", "kind": "compact", "phase": "end", "action": e.get("action"),
                          "summary_chars": len(summary), "summary_lang": language(summary)})
        elif kind == "notice":
            text = str(e.get("message") or "")
            tokens = _NOTICE_TOKENS.search(text)
            steps.append({"actor": "harness", "kind": "notice", "text": text[:200],
                          "tokens": int(tokens.group(1).replace(",", "")) if tokens else None})
    reason = END_ANSWERED if answered and last_stop == "stop" else _OMP_STOP.get(str(last_stop), str(last_stop))
    steps.append({"actor": "harness", "kind": "end", "reason": reason})
    return steps


# ---------------------------------------------------------------- the proxied API calls

def _messages(record: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        body = json.loads(record.get("body_received") or "")
    except (TypeError, json.JSONDecodeError):
        return []
    return body.get("messages") or [] if isinstance(body, dict) else []


def api_calls(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    previous: dict[str, Any] | None = None
    for r in sorted(records, key=lambda x: _int(x.get("n")) or 0):
        try:
            body = json.loads(r.get("body_received") or "{}")
        except json.JSONDecodeError:
            body = {}
        outcome = r.get("outcome")
        messages = body.get("messages") or [] if isinstance(body, dict) else []
        usage = ((r.get("response") or {}).get("usage") or {}) if isinstance(r.get("response"), dict) else {}
        if str(outcome or "").startswith("refused"):
            kind = "refused"
        elif isinstance(body, dict) and body.get("tool_choice") == "none":
            kind = "handoff"
        elif outcome in (None, "") or r.get("client_gone"):
            kind = "cancelled"
        elif outcome != "ok":
            kind = "failed"
        elif previous and previous["outcome"] != "ok" and previous["n_messages"] == len(messages):
            kind = "resend"
        else:
            kind = "step"
        details = usage.get("completion_tokens_details") or {}
        entry = {"n": _int(r.get("n")), "kind": kind, "outcome": outcome, "n_messages": len(messages),
                 "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                 "reasoning_tokens": details.get("reasoning_tokens") if isinstance(details, dict) else None,
                 "latency_s": r.get("latency_s")}
        out.append(entry)
        previous = entry
    return out


def answer_context(records: list[dict[str, Any]]) -> dict[str, Any]:
    """The last request answered with text and no tool call: what it held when the model answered."""
    finals = [r for r in records if isinstance(r.get("response"), dict) and not r["response"].get("tool_calls")
              and str(r["response"].get("content") or "").strip() and r.get("outcome") == "ok"]
    if not finals:
        return {"answered": False}
    messages = _messages(max(finals, key=lambda r: _int(r.get("n")) or 0))
    texts = [_text(m.get("content")) for m in messages]
    tool_texts = [t for m, t in zip(messages, texts, strict=True) if m.get("role") == "tool"]
    return {"answered": True, "messages": len(messages), "chars": sum(len(t) for t in texts),
            "tool_results": len(tool_texts), "tool_result_chars": sum(len(t) for t in tool_texts),
            "after_handoff": any(_HANDOFF in t for m, t in zip(messages, texts, strict=True) if m.get("role") == "user")}


# ---------------------------------------------------------------- one attempt

def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def attempt_flow(attempt_dir: Path, harness: str) -> Flow:
    if harness not in ("dsh", "omp"):
        raise ValueError(f"unknown harness {harness!r}")
    events = _jsonl(attempt_dir / "events.jsonl")
    records = _jsonl(attempt_dir / "proxy_log.jsonl")
    steps = dsh_steps(events) if harness == "dsh" else omp_steps(events)
    return Flow(harness=harness, steps=steps, calls=api_calls(records), answer_context=answer_context(records))


def summary(flow: Flow) -> dict[str, Any]:
    """Per-attempt counts used by the cell summaries."""
    steps, calls = flow.steps, flow.calls
    results = [s for s in steps if s["kind"] == "result"]
    reads = [s for s in results if s["tool"] == "read" and not s["error"]]
    greps = [s for s in results if s["tool"] == "grep"]
    compactions = [s for s in steps if s["kind"] == "compact" and s.get("phase") == "end"]
    notices = [s for s in steps if s["kind"] == "notice"]
    end = next((s["reason"] for s in reversed(steps) if s["kind"] == "end"), "unknown")
    return {
        "tool_calls": sum(s["kind"] == "call" for s in steps),
        "greps": len(greps), "empty_greps": sum(bool(s.get("empty")) for s in greps),
        "reads": len(reads), "read_errors": sum(s["tool"] == "read" and s["error"] for s in results),
        "reads_harness_window": sum(s.get("window") == "harness" for s in reads),
        "reads_model_window": sum(s.get("window") == "model" for s in reads),
        "reads_elided": sum(bool(s.get("elided")) for s in reads),
        "truncated_results": sum(s["truncated"] for s in results),
        "result_chars": sum(s["chars"] for s in results),
        "think_chars": sum(s.get("chars", 0) for s in steps if s["kind"] == "think"),
        "compactions": len(compactions),
        "compaction_summary_lang": sorted({s["summary_lang"] for s in compactions}),
        "notices": len(notices), "notice_tokens": sum(s.get("tokens") or 0 for s in notices),
        "api_calls": len(calls), "api_by_kind": {k: sum(c["kind"] == k for c in calls)
                                                 for k in ("step", "handoff", "resend", "refused", "cancelled", "failed")},
        "end": end, "answered_after_handoff": bool(flow.answer_context.get("after_handoff")),
        "tokens": " ".join(flow.tokens),
    }
