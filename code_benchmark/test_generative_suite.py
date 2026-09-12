"""Offline parity/robustness tests for test_generative.py (no network access).

Run from the repo root:  .venv/bin/python -m unittest code_benchmark.test_generative_suite
"""
import argparse
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from code_benchmark import test_generative as tg


class _StubMessage:
    def __init__(self, content):
        self.content = content


class _StubChoice:
    def __init__(self, content):
        self.message = _StubMessage(content)


class _StubResponse:
    def __init__(self, content):
        self.choices = [_StubChoice(content)]


class _StubCompletions:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _StubResponse(outcome)


class _StubClient:
    def __init__(self, outcomes):
        self.chat = type("Chat", (), {})()
        self.chat.completions = _StubCompletions(outcomes)


class RetryTests(unittest.TestCase):
    def test_backoff_progression(self):
        self.assertEqual(tg.backoff_sleep(1), 10)
        self.assertEqual(tg.backoff_sleep(2), 20)
        self.assertEqual(tg.backoff_sleep(3), 40)
        self.assertEqual(tg.backoff_sleep(4), 60)
        self.assertEqual(tg.backoff_sleep(9), 60)

    def test_retry_on_503_then_success(self):
        stub = _StubClient([Exception("Error code: 503 - Service start timed out"),
                            Exception("Error code: 503 - Loading model"),
                            "  câu trả lời  "])
        out = tg.call_model_with_retry(stub, "m", [{"role": "user", "content": "x"}],
                                       0.0, 42, 256, max_retries=5, base_sec=0, cap_sec=0)
        # content is returned unmodified; callers strip it when recording
        self.assertEqual(out, "  câu trả lời  ")
        self.assertEqual(stub.chat.completions.calls, 3)

    def test_retry_exhaustion_returns_empty(self):
        stub = _StubClient([Exception("Error code: 503 - Loading model")] * 5)
        out = tg.call_model_with_retry(stub, "m", [{"role": "user", "content": "x"}],
                                       0.0, 42, 256, max_retries=3, base_sec=0, cap_sec=0)
        self.assertEqual(out, "")
        self.assertEqual(stub.chat.completions.calls, 3)

    def test_timeout_is_retryable(self):
        stub = _StubClient([TimeoutError("Request timed out"), "ok"])
        out = tg.call_model_with_retry(stub, "m", [{"role": "user", "content": "x"}],
                                       0.0, 42, 256, max_retries=3, base_sec=0, cap_sec=0)
        self.assertEqual(out, "ok")

    def test_auth_error_fails_fast(self):
        class _Fake401(Exception):
            pass

        stub = _StubClient([_Fake401("Error code: 401 - Unauthorized"), "should not reach"])
        with self.assertRaises(_Fake401):
            tg.call_model_with_retry(stub, "m", [{"role": "user", "content": "x"}],
                                     0.0, 42, 256, max_retries=5, base_sec=0, cap_sec=0)
        self.assertEqual(stub.chat.completions.calls, 1)


class WarmupTests(unittest.TestCase):
    def test_warmup_succeeds_after_503s(self):
        stub = _StubClient([Exception("Error code: 503 - Service start timed out"),
                            Exception("Error code: 503 - Loading model"),
                            "pong"])
        tg.warm_up_endpoint(stub, "m", minutes=1, probe_every=0)
        self.assertEqual(stub.chat.completions.calls, 3)

    def test_warmup_gives_up_after_deadline(self):
        stub = _StubClient([Exception("Error code: 503 - Service start timed out")] * 20)
        with self.assertRaises(SystemExit):
            tg.warm_up_endpoint(stub, "m", minutes=0, probe_every=0)


class DialogTests(unittest.TestCase):
    def test_fresh_conversation(self):
        msgs = tg.dialog_messages(["q1", "q2"], [])
        self.assertEqual(msgs, [{"role": "user", "content": "q1"}])

    def test_partial_resume_has_no_double_user_turns(self):
        msgs = tg.dialog_messages(["q1", "q2", "q3"], ["a1"])
        self.assertEqual(msgs, [{"role": "user", "content": "q1"},
                                {"role": "assistant", "content": "a1"},
                                {"role": "user", "content": "q2"}])

    def test_full_history(self):
        # fully-answered conversation -> complete [user, assistant, ...] transcript
        msgs = tg.dialog_messages(["q1", "q2"], ["a1", "a2"])
        self.assertEqual(len(msgs), 4)
        self.assertEqual(msgs[-1], {"role": "assistant", "content": "a2"})

    def test_normalize_record_clamps_and_rejects_legacy(self):
        item = {"id": "dialog-000", "turns": ["q1", "q2"]}
        norm = tg.normalize_record("dialog", item, {"id": "dialog-000",
                                                    "replies": ["a1", "a2", "extra"], "done": True})
        self.assertEqual(norm["replies"], ["a1", "a2"])
        self.assertTrue(norm["done"])
        # legacy last-reply-only record (no 'replies') -> unusable, re-run
        self.assertIsNone(tg.normalize_record("dialog", item, {"id": "dialog-000", "answer": "a2"}))


class CoTExtractionTests(unittest.TestCase):
    def test_extracts_after_last_ket_luan(self):
        text = "Bước 1:\nTính 2+2=4\nKết luận:\nphương án A\n(dòng thừa)"
        self.assertEqual(tg.extract_cot_final(text), "phương án A")

    def test_inline_ket_luan(self):
        self.assertEqual(tg.extract_cot_final("Bước 1: x\nKết luận: 42"), "42")

    def test_fallback_last_line(self):
        self.assertEqual(tg.extract_cot_final("không có cấu trúc\nđáp án cuối"), "đáp án cuối")

    def test_empty(self):
        self.assertEqual(tg.extract_cot_final(""), "")


class PromptTests(unittest.TestCase):
    def test_drop_cot_vs_baseline_verbatim_markers(self):
        item = {"_task": "drop", "context": "CTX", "question": "Q"}
        self.assertIn("Bước 1:", tg.build_extractive_prompt(item, "cot"))
        self.assertIn("#Task:", tg.build_extractive_prompt(item, "baseline"))
        self.assertNotIn("Bước 1:", tg.build_extractive_prompt(item, "baseline"))

    def test_squad_stays_no_cot_even_when_cot_requested(self):
        prompt = tg.build_extractive_prompt({"_task": "squad", "context": "CTX", "question": "Q"}, "cot")
        self.assertIn("NO ANSWER", prompt)
        self.assertNotIn("Bước 1:", prompt)

    def test_effective_max_tokens(self):
        self.assertEqual(tg.effective_max_tokens("cot", None), 512)
        self.assertEqual(tg.effective_max_tokens("baseline", None), 256)
        self.assertEqual(tg.effective_max_tokens("cot", 777), 777)


class CheckpointTests(unittest.TestCase):
    def test_roundtrip_and_atomic_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            cp = Path(td)
            tg.write_checkpoint(cp, [{"id": "1", "answer": "a"}])
            tg.write_checkpoint(cp, [{"id": "1", "answer": "a"},
                                     {"id": "dialog-000", "replies": ["r1"], "done": False}])
            done = tg.load_checkpoint(cp)
            self.assertEqual(done["1"]["answer"], "a")
            self.assertEqual(done["dialog-000"]["replies"], ["r1"])
            self.assertFalse(done["dialog-000"]["done"])
            # tmp file must be gone after the atomic replace
            self.assertEqual([p.name for p in cp.glob("*.tmp")], [])

    def test_legacy_numbered_snapshots_are_merged(self):
        with tempfile.TemporaryDirectory() as td:
            cp = Path(td)
            legacy = cp / "generative_raw_result_3.jsonl"
            legacy.write_text('{"id": "0", "answer": "old"}\n', encoding="utf-8")
            tg.write_checkpoint(cp, [{"id": "0", "answer": "old"}, {"id": "1", "answer": "new"}])
            done = tg.load_checkpoint(cp)
            self.assertEqual(set(done), {"0", "1"})


class RunInferenceIntegrationTests(unittest.TestCase):
    """End-to-end orchestration against a stub client — no network."""

    def setUp(self):
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        self._tmp.cleanup()

    @staticmethod
    def _args(task="dialog", workers=1):
        return argparse.Namespace(task=task, strategy="baseline", few_shot_file=None,
                                  run_tag="", temperature=0.0, seed=42, max_retries=3,
                                  verbose=False, workers=workers)

    def test_dialog_end_to_end(self):
        items = [{"id": "dialog-000", "turns": ["q1", "q2"]},
                 {"id": "dialog-001", "turns": ["q3"]}]
        stub = _StubClient(["r1a", "r1b", "r2a"])
        with tempfile.TemporaryDirectory() as td:
            tg.run_inference(self._args(), stub, "m", 256, items, {}, Path(td), threading.Lock())
            done = tg.load_checkpoint(Path(td))
            self.assertTrue(done["dialog-000"]["done"])
            self.assertEqual(done["dialog-000"]["replies"], ["r1a", "r1b"])
            rows = Path("submission_dialog.csv").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(rows, ['"id","answer"',
                                    '"dialog-000_1","r1a"', '"dialog-000_2","r1b"',
                                    '"dialog-001_1","r2a"'])
            last = Path("submission_dialog_last.csv").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(last), 3)  # header + 2 completed conversations

    def test_dialog_crash_keeps_partial_turns(self):
        items = [{"id": "dialog-000", "turns": ["q1", "q2", "q3"]}]
        stub = _StubClient(["r1", "r2"] + [Exception("Error code: 503 - Loading model")] * 10)
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(tg, "backoff_sleep", lambda attempt, base_sec=10, cap_sec=60: 0), \
                 self.assertRaises(RuntimeError):
                tg.run_inference(self._args(), stub, "m", 256, items, {}, Path(td), threading.Lock())
            done = tg.load_checkpoint(Path(td))
            self.assertEqual(done["dialog-000"]["replies"], ["r1", "r2"])
            self.assertFalse(done["dialog-000"]["done"])

    def test_squad_multi_item_time_flush(self):
        # regression: mid-run completions (not hitting the 100 milestone or the
        # final item) must not raise UnboundLocalError on the time-flush branch
        items = [{"id": str(i), "context": "C", "question": "Q", "_task": "squad"} for i in range(3)]
        stub = _StubClient([f"a{i}" for i in range(3)])
        with tempfile.TemporaryDirectory() as td:
            tg.run_inference(self._args(task="squad"), stub, "m", 256, items, {}, Path(td), threading.Lock())
            done = tg.load_checkpoint(Path(td))
            self.assertEqual(sorted(done), ["0", "1", "2"])

    def test_squad_end_to_end(self):
        items = [{"id": "0", "context": "C", "question": "Q", "_task": "squad"}]
        stub = _StubClient(["LVMH"])
        with tempfile.TemporaryDirectory() as td:
            tg.run_inference(self._args(task="squad"), stub, "m", 256, items, {}, Path(td), threading.Lock())
            rows = Path("submission_squad.csv").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(rows, ['"id","answer"', '"0","LVMH"'])
            done = tg.load_checkpoint(Path(td))
            self.assertEqual(done["0"]["answer"], "LVMH")
            self.assertEqual(done["0"]["question"], "Q")


if __name__ == "__main__":
    unittest.main()
