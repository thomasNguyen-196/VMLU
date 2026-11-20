"""Offline tests of MC-117's runner: stalls, blocked rows and halts (no sandbox, no endpoint).

    .venv/bin/python -m unittest code_benchmark.test_run_legal_agent_omp_prompt
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from code_benchmark import diagnostic_legal_agent_omp_prompt as lp
from code_benchmark import dsh_proxy as px
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_legal_agent_omp as rlo
from code_benchmark import run_legal_agent_omp_prompt as rlp
from code_benchmark import vi_multimodel as v1


def record(outcome: str, model: str | None = "m", content: str = "", tool_calls=None) -> dict:
    return {"n": 1, "outcome": outcome, "status": 200,
            "response": {"model": model, "content": content, "tool_calls": tool_calls or [], "finish_reason": "stop",
                         "done": True, "usage": {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105}}}


def omp_events(answer: str | None) -> list[dict]:
    if answer is None:
        return [{"type": "agent_end", "messages": []}]
    return [{"type": "message_end", "message": {"role": "assistant", "stopReason": "stop",
                                                "content": [{"type": "text", "text": answer}]}}]


def result(records: list[dict], answer: str | None) -> dict:
    return {"records": records, "events": omp_events(answer), "exit_code": 0, "timed_out": False, "wall_s": 2.0}


def item(item_id: str = "1") -> v1.EvalItem:
    return v1.EvalItem(dataset_id="d", source_dataset="d", item_id=item_id, replicate_id="OMPS-r1",
                       task="multiple_choice", stratum="s", question="q", passage_id="", prompt="task", gold_answer="A")


class TestStalls(unittest.TestCase):
    def test_a_stream_with_no_model_is_a_stall(self):
        records = [record("ok"), record("model_drift", model=None), record("model_drift", model="other-model")]
        self.assertEqual(rlp.mark_stalls(records), 1)
        self.assertEqual([r["outcome"] for r in records], ["ok", "network", "model_drift"])
        self.assertEqual(records[1]["error_type"], rlp.STALL)

    def test_a_recovered_stall_is_complete(self):
        r = result([record("ok", tool_calls=[{"name": "grep"}]), record("model_drift", model=None),
                    record("ok", content="Đáp án: B")], "Đáp án: B")
        self.assertEqual(rlo.classify(r)["outcome"], "fatal")  # the registered reading, before this card's fix
        rlp.mark_stalls(r["records"])
        verdict = rlo.classify(r)
        self.assertEqual((verdict["status"], verdict["outcome"]), ("complete", "complete"))

    def test_an_unrecovered_stall_is_technical(self):
        r = result([record("ok", tool_calls=[{"name": "grep"}]), record("model_drift", model=None)], None)
        rlp.mark_stalls(r["records"])
        verdict = rlo.classify(r)
        self.assertEqual((verdict["status"], verdict["outcome"], verdict["fatal"]), ("request_error", "technical", False))

    def test_another_model_stays_fatal(self):
        r = result([record("model_drift", model="other-model"), record("ok", content="B")], "B")
        rlp.mark_stalls(r["records"])
        self.assertTrue(rlo.classify(r)["fatal"])


class TestRowsAndHalts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)
        protocol = {"harness": {"api_protocol": "openai-chat-completions", "max_completion_tokens": 4096},
                    "proxy": {"wall_clock_seconds": 60}}
        self.context = rlp.AttemptContext(
            model="qwen", omp=mock.Mock(), omp_protocol=protocol, docs={"v1": self.output}, corpus_of={"d:1": "v1",
                                                                                                    "d:2": "v1"},
            output=self.output, proxy=px.ProxyConfig(upstream="http://x", api_key="k", model="Qwen3.5-9B-65K",
                                                 expected_response_model="Qwen3.5-9B-65K"),
            session_header=None, profile_id="qwen3-5-9b-65k-omps", card_id="MC-117")

    def tearDown(self):
        self.tmp.cleanup()

    def test_blocked_row_keeps_its_identity(self):
        row = rlp.blocked_row(item(), self.context, 2, 1, "halted_before_send")
        for key, value in (("shard", 2), ("lane", 1), ("model_id", "Qwen3.5-9B-65K"), ("protocol_id", lp.PROTOCOL_ID),
                           ("profile_id", "qwen3-5-9b-65k-omps"), ("measurement_card_id", "MC-117"),
                           ("status", "request_error"), ("arm", "OMPS")):
            self.assertEqual(row[key], value, key)

    def test_a_fatal_attempt_halts_and_later_rows_are_loadable(self):
        fatal = result([record("model_drift", model="other-model")], None)
        attempt_dir = self.output / "attempts" / "x" / "try-1"

        def fake_run_agent(_context, _item):
            return fatal, rlo.classify(fatal), attempt_dir, 0

        request = rlp.make_request("MC-117", "qwen", pr.BudgetGuard(10**9, 0), pr.OutageGuard(4), 2, rlp.rlm.BadRequests())
        with mock.patch.object(rlp, "run_agent", fake_run_agent):
            first = request(self.context, item("1"), 0, 0)
            second = request(self.context, item("2"), 1, 2)
        self.assertTrue(first["fatal"])
        self.assertEqual(first["error_type"], "model_drift")
        self.assertEqual((second["error_type"], second["shard"], second["lane"]), ("halted_before_send", 1, 2))
        self.assertEqual(second["model_id"], "Qwen3.5-9B-65K")

    def test_session_id(self):
        self.assertTrue(rlp.session_id("mimo", "d:1:OMPS-r1", 2).startswith("vmlu-mc117-mimo-"))
        self.assertTrue(rlp.session_id("mimo", "d:1:OMPS-r1", 2).endswith("-t2"))


if __name__ == "__main__":
    unittest.main()
