"""Offline tests of harness_flow (synthetic event streams and proxy records).

    .venv/bin/python -m unittest code_benchmark.test_harness_flow
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import harness_flow as hf


def dsh_events() -> list[dict]:
    return [
        {"type": "session"}, {"type": "status", "phase": "turn_start"},
        {"type": "thinking", "text": "tìm luật"},
        {"type": "tool_call", "callId": "c1", "tool": "grep", "input": {"pattern": "đấu thầu", "path": "/w"}},
        {"type": "tool_result", "callId": "c1", "status": "completed", "result": "Found 2 matches\n\nluat-a.txt\nLine 3: x"},
        {"type": "tool_call", "callId": "c2", "tool": "grep", "input": {"pattern": "không có"}},
        {"type": "tool_result", "callId": "c2", "status": "completed", "result": "No matches found"},
        {"type": "tool_call", "callId": "c3", "tool": "read", "input": {"file_path": "/w/luat-a.txt", "offset": 10, "limit": 2}},
        {"type": "tool_result", "callId": "c3", "status": "completed",
         "result": "<path>/w/luat-a.txt</path>\n<content>\n10: Điều 4.\n11: 1. A\n\n(Showing lines 10-11 of 900. Use offset=12 to continue.)\n</content>"},
        {"type": "tool_call", "callId": "c4", "tool": "read", "input": {"file_path": "/w/luat-b.txt"}},
        {"type": "tool_result", "callId": "c4", "status": "completed",
         "result": "<path>/w/luat-b.txt</path>\n<content>\n1: a\n2: b\n</content>"},
        {"type": "final", "reason": {"kind": "completed"}, "text": "B"},
    ]


def omp_events() -> list[dict]:
    assistant = {"role": "assistant", "stopReason": "toolUse", "content": [{"type": "thinking", "thinking": "abc"}]}
    final = {"role": "assistant", "stopReason": "stop", "content": [{"type": "text", "text": "Đáp án: C"}]}
    return [
        {"type": "session"}, {"type": "agent_start"},
        {"type": "message_end", "message": assistant},
        {"type": "tool_execution_start", "toolCallId": "t1", "toolName": "grep", "args": {"pattern": "x"}, "intent": "find"},
        {"type": "tool_execution_end", "toolCallId": "t1", "toolName": "grep", "isError": False,
         "result": {"content": [{"type": "text", "text": "# luat-a.txt\n 3|ngữ cảnh\n*4|khớp\n[Some lines truncated to 768 chars]"}]}},
        {"type": "tool_execution_start", "toolCallId": "t2", "toolName": "read", "args": {"path": "luat-a.txt"}},
        {"type": "tool_execution_end", "toolCallId": "t2", "toolName": "read", "isError": False,
         "result": {"content": [{"type": "text", "text": "1|a\n2|b\n[Showing lines 1-2 and 880-900 of 900. Use :3 to continue]"}]}},
        {"type": "auto_compaction_start", "reason": "threshold", "action": "handoff"},
        {"type": "auto_compaction_end", "action": "handoff", "result": {"summary": "## Goal\nAnswer the law question"}},
        {"type": "notice", "message": "Compaction dead-end recovery: elided 16 heavy blocks (~32,381 tokens)"},
        {"type": "message_end", "message": final},
        {"type": "agent_end", "messages": []},
    ]


def record(n: int, outcome, messages: list[dict], content: str = "", tool_calls=None, tool_choice=None) -> dict:
    body = {"messages": messages}
    if tool_choice:
        body["tool_choice"] = tool_choice
    return {"n": n, "outcome": outcome, "body_received": json.dumps(body, ensure_ascii=False),
            "response": {"content": content, "tool_calls": tool_calls or [],
                         "usage": {"prompt_tokens": 10, "completion_tokens": 2}}}


class TestFlow(unittest.TestCase):
    def test_dsh_tokens_and_windows(self):
        steps = hf.dsh_steps(dsh_events())
        flow = hf.Flow("dsh", steps)
        self.assertEqual(flow.tokens, ["G+", "G0", "Rm", "R", "A"])
        reads = [s for s in steps if s["kind"] == "result" and s["tool"] == "read"]
        self.assertEqual(reads[0]["shown"], [10, 11])
        self.assertEqual(reads[0]["total"], 900)
        self.assertEqual(reads[1]["shown"], [1, 2])
        self.assertIsNone(reads[1]["window"])
        calls = [s for s in steps if s["kind"] == "call"]
        self.assertEqual(calls[2]["path"], "/w/luat-a.txt")
        self.assertEqual(steps[2 + 0]["kind"], "result")

    def test_omp_tokens_compaction_and_notice(self):
        steps = hf.omp_steps(omp_events())
        flow = hf.Flow("omp", steps)
        self.assertEqual(flow.tokens, ["G+", "Re", "C", "A"])
        grep = next(s for s in steps if s["kind"] == "result" and s["tool"] == "grep")
        self.assertEqual(grep["matches"], 1)
        self.assertTrue(grep["truncated"])
        self.assertEqual(grep["files"], ["luat-a.txt"])
        compact = next(s for s in steps if s["kind"] == "compact" and s["phase"] == "end")
        self.assertEqual(compact["summary_lang"], "en")
        notice = next(s for s in steps if s["kind"] == "notice")
        self.assertEqual(notice["tokens"], 32381)
        self.assertEqual(steps[-1], {"actor": "harness", "kind": "end", "reason": "completed"})
        self.assertEqual(next(s for s in steps if s["kind"] == "call")["intent"], "find")

    def test_omp_without_answer_ends_with_its_stop_reason(self):
        events = [e for e in omp_events() if not (e["type"] == "message_end" and e["message"]["stopReason"] == "stop")]
        events.insert(-1, {"type": "message_end", "message": {"role": "assistant", "stopReason": "length", "content": []}})
        steps = hf.omp_steps(events)
        self.assertEqual(steps[-1]["reason"], "max-tokens")
        self.assertEqual(hf.Flow("omp", steps).tokens[-1], "E")

    def test_api_calls_kinds(self):
        two = [{"role": "user", "content": "q"}, {"role": "assistant", "content": ""}]
        records = [record(1, "ok", two[:1], tool_calls=[{"name": "grep"}]),
                   record(2, "network", two),
                   record(3, "ok", two, content="B"),
                   record(4, "ok", two, tool_choice="none"),
                   record(5, None, two),
                   record(6, "refused_cap", two)]
        kinds = [c["kind"] for c in hf.api_calls(records)]
        self.assertEqual(kinds, ["step", "failed", "resend", "handoff", "cancelled", "refused"])

    def test_answer_context_after_handoff(self):
        messages = [{"role": "system", "content": "s"},
                    {"role": "user", "content": [{"type": "text", "text": "Context replaced. The <handoff> below"}]},
                    {"role": "tool", "content": "No matches found"}]
        ctx = hf.answer_context([record(1, "ok", messages, content="A")])
        self.assertTrue(ctx["after_handoff"])
        self.assertEqual(ctx["tool_results"], 1)

    def test_attempt_flow_reads_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "events.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in dsh_events()) + "\n{bad",
                                            encoding="utf-8")
            (d / "proxy_log.jsonl").write_text(json.dumps(record(1, "ok", [{"role": "user", "content": "q"}], "B")),
                                               encoding="utf-8")
            summary = hf.summary(hf.attempt_flow(d, "dsh"))
        self.assertEqual(summary["tokens"], "G+ G0 Rm R A")
        self.assertEqual(summary["empty_greps"], 1)
        self.assertEqual(summary["reads_model_window"], 1)
        self.assertEqual(summary["end"], "completed")

    def test_language_tag(self):
        self.assertEqual(hf.language("Điều 4 quy định về hồ sơ dự thầu"), "vi")
        self.assertEqual(hf.language("Answer the law question about bidding"), "en")


if __name__ == "__main__":
    unittest.main()
