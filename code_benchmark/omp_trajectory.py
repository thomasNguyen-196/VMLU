"""What the model saw in an omp 18.0.0 attempt (openspec change diagnostic-legal-agent-omp, design §9).

The proxy records every request body; their `tool` messages are the tool results that reached the model. This module
turns them into MC-112's observation shape ({tool, read_file, lines, ...}) so that MC-112's `provision_hits` applies
unchanged. Formats, recorded offline against a scripted server (all_res/diagnostic_legal_agent_omp/probe_20261113):

* `read` of a file: the file's lines as they are, no line numbers and no file header; notes in square brackets
  (`[Showing lines 39-63 of 20630. Use :64 to continue]`, `[…139ln elided…]`, `[Some lines truncated to 768 chars]`).
  The file is the call's `path` argument without a selector suffix (`:40-60`, `:64`, `:raw`).
* `grep`: blocks headed `# <file>`, lines `*<n>|<text>` (match) and ` <n>|<text>` (context), a paging note
  `Showing files 1-20 of 293. Use skip=20 …`. A grep of one file has no header: its lines belong to the path argument.
* A large result is spilled to the session's `artifact://<k>`, named in its note. A later `read` of `artifact://<k>`
  (or of the session file `<k>.<tool>.log` the note points to) returns the spilled output: it counts as a read of the
  file when the spilled call was a read of it, and as grep output (`seen` only) when it was a grep.
* `glob`, directory listings, URLs, internal documents and paths outside the folder show no corpus line.
"""
from __future__ import annotations

import json
import re
from typing import Any

try:
    from code_benchmark import diagnostic_legal_agent as la
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent as la  # type: ignore[no-redef]

_NOTE = re.compile(r"^\[(?:…\d+ln elided…|Showing |Some lines |This command |Full output|.*artifact://).*\]$")
_GREP_LINE = re.compile(r"^[ *] *\d+\|(?P<text>.*)$")
_GREP_HEADER = re.compile(r"^# (?P<file>.+)$")
_SELECTOR = re.compile(r"^(?P<path>.+?\.txt)(?::[^/]*)?$")
_ARTIFACT = re.compile(r"^artifact://(?P<k>\d+)(?::.*)?$")
_SESSION_LOG = re.compile(r"/sessions/.+/(?P<k>\d+)\.\w+\.log$")
_SPILL = re.compile(r"artifact://(?P<k>\d+)")
_ERRORS = re.compile(r"^(?:Path '.*' not found|No session - artifacts unavailable|Error:|URL: )")


def path_file(path: str) -> str | None:
    """The corpus file a tool path names, after removing a read selector, or None."""
    match = _SELECTOR.match(path.strip())
    return la.corpus_file(match.group("path")) if match else None


def shown_lines(content: str) -> list[str]:
    """The lines a `read` result showed, without omp's bracketed notes."""
    return [line for line in content.split("\n") if not _NOTE.match(line)]


def parse_grep(content: str, path: str | None = None) -> dict[str, list[str]]:
    """{file: lines shown} of a `grep` result; lines without a header belong to the searched file `path`."""
    out: dict[str, list[str]] = {}
    current = path_file(path) if path else None
    for line in content.split("\n"):
        header = _GREP_HEADER.match(line)
        if header:
            current = la.corpus_file(header.group("file").strip())
            continue
        hit = _GREP_LINE.match(line)
        if hit and current is not None:
            out.setdefault(current, []).append(hit.group("text"))
    return out


def _calls_and_results(records: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, str]]:
    calls: dict[str, dict[str, Any]] = {}
    results: dict[str, str] = {}
    order: list[str] = []
    for record in records:
        try:
            body = json.loads(record.get("body_received") or "")
        except json.JSONDecodeError:
            continue
        for message in body.get("messages") or [] if isinstance(body, dict) else []:
            if message.get("role") == "assistant":
                for call in message.get("tool_calls") or []:
                    if call.get("id") and call["id"] not in calls:
                        function = call.get("function") or {}
                        try:
                            arguments = json.loads(function.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            arguments = {"_unparsed": function.get("arguments")}
                        calls[call["id"]] = {"tool": function.get("name"),
                                             "arguments": arguments if isinstance(arguments, dict) else {}}
                        order.append(call["id"])
            elif message.get("role") == "tool" and message.get("tool_call_id") not in results:
                content = message.get("content")
                if isinstance(content, list):
                    content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
                results[str(message.get("tool_call_id"))] = str(content or "")
    return order, calls, results


def omp_observations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every tool call whose result reached the model, in call order, in MC-112's observation shape. Collected over
    all recorded request bodies, so a result later compacted away still counts once it was sent."""
    order, calls, results = _calls_and_results(records)
    spills: dict[str, dict[str, Any]] = {}
    out = []
    for call_id in order:
        if call_id not in results:
            continue
        call, content = calls[call_id], results[call_id]
        arguments = call["arguments"]
        path = str(arguments.get("path") or "")
        lines: dict[str, list[str]] = {}
        read_file, source = None, None
        status = "error" if _ERRORS.match(content) else "completed"
        if status == "completed" and call["tool"] == "read":
            spilled = _ARTIFACT.match(path) or _SESSION_LOG.search(path)
            if spilled:
                origin = spills.get(spilled.group("k"))
                source = f"artifact://{spilled.group('k')}"
                if origin and origin["tool"] == "read" and origin["read_file"]:
                    read_file = origin["read_file"]
                    lines[read_file] = shown_lines(content)
                elif origin and origin["tool"] == "grep":
                    lines = parse_grep(content, str(origin["arguments"].get("path") or "") or None)
            else:
                read_file = path_file(path)
                if read_file:
                    lines[read_file] = shown_lines(content)
        elif status == "completed" and call["tool"] == "grep":
            lines = parse_grep(content, path or None)
        observation = {"call_id": call_id, "tool": call["tool"], "arguments": arguments, "status": status,
                       "read_file": read_file, "lines": lines, "chars": len(content), "source": source}
        if source is None:  # a spill note names the artifact holding this call's full output
            for match in _SPILL.finditer(content):
                spills.setdefault(match.group("k"), observation)
        out.append(observation)
    return out


def selectors(observations: list[dict[str, Any]]) -> dict[str, int]:
    """Descriptive counts: whole-file reads, range reads, spill read-backs, grep pages beyond the first."""
    counts = {"read_whole": 0, "read_range": 0, "read_spill": 0, "grep_next_page": 0}
    for o in observations:
        path = str(o["arguments"].get("path") or "")
        if o["tool"] == "read" and o["read_file"]:
            key = ("read_spill" if o["source"] else "read_range" if ":" in path.rsplit(".txt", 1)[-1]
                   else "read_whole")
            counts[key] += 1
        elif o["tool"] == "grep" and o["status"] == "completed" and o["arguments"].get("skip"):
            counts["grep_next_page"] += 1
    return counts
