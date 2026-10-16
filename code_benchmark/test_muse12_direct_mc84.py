"""Lock MC-84 request identity and its uniform 20k sampling condition.

Run from root: .venv/bin/python -m unittest code_benchmark.test_qwen_direct_mc84
"""
from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

from code_benchmark import run_muse12_direct_20k_mc84 as runner


class TestMuse12Direct(unittest.TestCase):
    def test_native_request_uses_muse12_identity_without_seed_effort_or_tools(self):
        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            event = N(model_dump=lambda: {"type": "response.completed", "response": {
                "status": "completed", "model": runner.MODEL,
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "A"}]}]}})
            return Stream(event)

        item = N(run_key="diagnostic:1:main", dataset_id="diagnostic", item_id="1", replicate_id="main", prompt="frozen")
        with ExitStack() as stack:
            for module, fields in [(runner.base, ["MODEL", "PROFILE", "PROTOCOL", "CARD_ID", "request"]),
                                   (runner.adapter, ["PROFILE", "PROTOCOL"]), (runner.rest, ["PROFILE", "PROTOCOL"])]:
                for field in fields:
                    stack.enter_context(patch.object(module, field, getattr(module, field)))
            runner.configure()
            row = runner.request(N(responses=N(create=create)), item, 0, 0)
            self.assertEqual(captured["model"], "ocg/muse-spark-1.2-contributor")
            self.assertEqual(captured["max_output_tokens"], 20000)
            self.assertEqual(captured["temperature"], 1)
            self.assertTrue(captured["stream"])
            self.assertEqual(set(captured), {"model", "input", "temperature", "max_output_tokens", "stream"})
            self.assertEqual(row["measurement_card_id"], "MC-84")
            self.assertEqual(row["model_id"], runner.MODEL)
            self.assertEqual(row["protocol_id"], runner.PROTOCOL)
            self.assertEqual(row["status"], "complete")
            self.assertEqual(row["raw_prompt"], "frozen")


class Stream:
    def __init__(self, event):
        self.event = event

    def __iter__(self):
        yield self.event

    def close(self):
        pass


if __name__ == "__main__":
    unittest.main()
