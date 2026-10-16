"""MC-82 recovery must retain failures without stopping unrelated items.

Run from root: .venv/bin/python -m unittest code_benchmark.test_muse13_direct_recovery
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as N
import unittest
import threading
from unittest.mock import patch

from code_benchmark import run_muse13_direct_20k_mc82 as runner


class Stream:
    def __init__(self, status, *, tools=False, code=None):
        self.data = {"type": "response." + status, "response": {
            "status": status,
            "output": [{"type": "function_call"}] if tools else (
                [{"type": "message", "content": [{"type": "output_text", "text": "A"}]}]
                if status == "completed" else []),
            "error": {"code": code} if code else None,
        }}

    def __iter__(self):
        yield N(model_dump=lambda: self.data)

    def close(self):
        pass


class TestRecovery(unittest.TestCase):
    def item(self, name):
        return N(run_key=f"diagnostic:{name}:main", dataset_id="diagnostic", item_id=name,
                 replicate_id="main", prompt=name)

    def test_idle_worker_steals_pending_item_once_and_resume_retries_only_failure(self):
        items = [self.item(name) for name in ("a", "b", "c", "d")]
        manifest = {"items": [{"dataset_id": i.dataset_id, "item_id": i.item_id,
                    "replicate_id": i.replicate_id,
                    "prompt_sha256": runner.base.v1.sha256_bytes(i.prompt.encode())} for i in items]}
        stolen = threading.Event()
        calls = Counter()
        lock = threading.Lock()

        def request(client, item, shard, lane):
            with lock:
                calls[item.item_id] += 1
                attempt = calls[item.item_id]
            if item.item_id == "a":
                # Its next own-lane item must be taken by the other worker.
                self.assertTrue(stolen.wait(5), "idle worker did not steal")
            if item.item_id == "c":
                stolen.set()
            return {"run_key": item.run_key, "model_id": runner.base.MODEL,
                    "protocol_id": runner.base.PROTOCOL,
                    "prompt_sha256": runner.base.v1.sha256_bytes(item.prompt.encode()),
                    "shard": shard, "lane": lane,
                    "status": "request_error" if item.item_id == "c" and attempt == 1 else "complete"}

        with TemporaryDirectory() as tmp, patch.object(runner.base, "SHARDS", 1), \
                patch.object(runner.base, "LANES", 2), patch.object(runner.base, "request", request):
            out = Path(tmp)
            kwargs = {"score_callback": lambda *args: None, "work_stealing": True}
            runner.base.execute(out, manifest, {}, items, {}, None, False, **kwargs)
            self.assertEqual(calls, Counter(a=1, b=1, c=1, d=1))
            rows = [json.loads(s) for s in (out / "attempts.jsonl").read_text().splitlines()]
            row = next(r for r in rows if r["run_key"] == items[2].run_key)
            self.assertEqual((row["shard"], row["lane"]), (0, 0))
            self.assertEqual((row["worker_shard"], row["worker_lane"]), (0, 1))
            runner.base.execute(out, manifest, {}, items, {}, None, True, **kwargs)
            self.assertEqual(calls, Counter(a=1, b=1, c=2, d=1))
            self.assertEqual(json.loads((out / "run.json").read_text())["status"], "complete")

    def test_terminal_failure_does_not_stop_next_item_and_resume_skips_success(self):
        items = [self.item("failed"), self.item("next")]
        calls = []

        def create(**kwargs):
            name = kwargs["input"][1]["content"]
            calls.append(name)
            return Stream("failed" if calls == ["failed"] else "completed")

        client = N(responses=N(create=create))
        manifest = {"items": [{"dataset_id": i.dataset_id, "item_id": i.item_id,
                    "replicate_id": i.replicate_id,
                    "prompt_sha256": runner.base.v1.sha256_bytes(i.prompt.encode())} for i in items]}
        with TemporaryDirectory() as tmp, patch.object(runner.base, "SHARDS", 1), \
                patch.object(runner.base, "LANES", 1), \
                patch.object(runner.base, "PROTOCOL", runner.PROTOCOL), \
                patch.object(runner.base, "request", runner.response_request), \
                patch("threading.Event.wait", return_value=False):
            out = Path(tmp)
            kwargs = {"score_callback": lambda *args: None, "runner_path": Path(runner.__file__)}
            runner.base.execute(out, manifest, {}, items, {}, client, False, **kwargs)
            first = json.loads((out / "run.json").read_text())
            self.assertEqual(first["status"], "incomplete")
            self.assertEqual(calls, ["failed", "next"])
            runner.base.execute(out, manifest, {}, items, {}, client, True, **kwargs)
            self.assertEqual(calls, ["failed", "next", "failed"])
            self.assertEqual(json.loads((out / "run.json").read_text())["status"], "complete")
            attempts = [json.loads(s) for s in (out / "attempts.jsonl").read_text().splitlines()]
            self.assertEqual([r["status"] for r in attempts], ["request_error", "complete", "complete"])

    def test_503_and_429_back_off_without_global_stop(self):
        for status in (503, 429):
            class Failure(Exception):
                status_code = status

            def create(**kwargs):
                raise Failure()

            row = runner.response_request(N(responses=N(create=create)), self.item("x"), 0, 0)
            self.assertFalse(row["fatal"])
            self.assertGreaterEqual(row["retry_wait_seconds"], 30)

    def test_auth_and_tools_remain_fatal(self):
        for status, tools, code in [("failed", False, "invalid_api_key"), ("completed", True, None)]:
            client = N(responses=N(create=lambda status=status, tools=tools, code=code, **kw:
                                  Stream(status, tools=tools, code=code)))
            row = runner.response_request(client, self.item("x"), 0, 0)
            self.assertTrue(row["fatal"])

    def test_budget_truncation_is_terminal_without_backoff(self):
        stream = Stream("incomplete")
        stream.data["response"]["incomplete_details"] = {"reason": "max_output_tokens"}
        client = N(responses=N(create=lambda **kw: stream))
        row = runner.response_request(client, self.item("x"), 0, 0)
        self.assertEqual(row["status"], "complete")
        self.assertEqual(row["finish_reason"], "length")
        self.assertNotIn("retry_wait_seconds", row)

    def test_http_auth_error_still_stops(self):
        class Unauthorized(Exception):
            status_code = 401

        def create(**kwargs):
            raise Unauthorized()

        row = runner.response_request(N(responses=N(create=create)), self.item("x"), 0, 0)
        self.assertTrue(row["fatal"])


if __name__ == "__main__":
    unittest.main()
