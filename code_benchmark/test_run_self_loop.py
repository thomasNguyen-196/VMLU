"""Offline tests of the self-loop runner (card MC-104): the letter probe, the MiMo request, the shared gate and the
execution gates. No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_run_self_loop
"""
from __future__ import annotations

import math
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_self_loop as sl
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_self_loop as rsl
from code_benchmark import vi_multimodel as v1

CONFIG, _ = sl.load_config()
PROMPT = v1.build_prompt("Câu hỏi?", ["A. một", "B. hai", "C. ba", "D. bốn"])
MC = v1.EvalItem(dataset_id=sl.VMLU, source_dataset="dev", item_id="01-0001", replicate_id="B-r1", task="multiple_choice",
                 stratum="x", question="Câu hỏi?", passage_id="x", prompt=PROMPT, gold_answer="B")


class FakeError(Exception):
    def __init__(self, status_code):
        super().__init__("upstream text that must not be stored")
        self.status_code = status_code


def logprob(token: str, p: float):
    return SimpleNamespace(token=token, logprob=math.log(p))


class FakeClient:
    def __init__(self, outcome):
        self.outcome, self.calls, self.kwargs = outcome, 0, None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        content, model, top = self.outcome
        logprobs = SimpleNamespace(content=[SimpleNamespace(token=content[:1], top_logprobs=top)]) if top else None
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=1, total_tokens=51, completion_tokens_details=None,
                                prompt_tokens_details=None)
        message = SimpleNamespace(content=content, tool_calls=None, reasoning_content=None)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=message, logprobs=logprobs)],
                               usage=usage, model=model, id="req-1")


class EngineState(unittest.TestCase):
    def setUp(self):
        self.saved = (rsl.base.MODEL, rsl.base.PROFILE, rsl.base.PROTOCOL)
        rsl.base.MODEL, rsl.base.PROFILE, rsl.base.PROTOCOL = "Qwen3.5-9B-65K", "qwen", sl.PROTOCOL_ID

    def tearDown(self):
        rsl.base.MODEL, rsl.base.PROFILE, rsl.base.PROTOCOL = self.saved


class TestProbe(EngineState):
    def probe(self, outcome, cap=10_000):
        guard = pr.BudgetGuard(cap)
        request = rsl.make_probe(CONFIG["students"]["qwen"]["probe"], {"Qwen3.5-9B-65K"}, "MC-104", guard,
                                 pr.OutageGuard(4), threading.Event())
        client = FakeClient(outcome)
        return request(client, MC, 0, 0), client

    def test_the_probe_keeps_the_mc43_condition_and_the_letter_confidence(self):
        top = [logprob("B", 0.6), logprob("A", 0.3), logprob("C", 0.1)]
        row, client = self.probe(("B", "Qwen3.5-9B-65K", top))
        self.assertEqual((client.kwargs["temperature"], client.kwargs["seed"], client.kwargs["max_tokens"],
                          client.kwargs["top_logprobs"], client.kwargs["logprobs"]), (0.0, 42, 4, 20, True))
        self.assertEqual(client.kwargs["messages"], [{"role": "user", "content": PROMPT}])
        self.assertEqual((row["status"], row["letters_found"]), ("complete", 3))
        self.assertAlmostEqual(row["confidence"], 0.6, places=5)
        self.assertEqual(dp.arm_of_replicate(row["replicate_id"]), "B")

    def test_missing_log_probabilities_leave_the_confidence_unknown(self):
        row, _ = self.probe(("B", "Qwen3.5-9B-65K", None))
        self.assertEqual((row["status"], row["confidence"]), ("complete", None))

    def test_drift_and_errors(self):
        drift, _ = self.probe(("B", "other-model", [logprob("B", 0.9), logprob("A", 0.1)]))
        self.assertEqual((drift["error_type"], drift["fatal"]), ("model_identity_drift", True))
        denied, _ = self.probe(FakeError(401))
        self.assertEqual((denied["status"], denied["fatal"]), ("request_error", True))
        self.assertNotIn("upstream", str(denied))
        spent, client = self.probe(("B", "Qwen3.5-9B-65K", None), cap=0)
        self.assertEqual((spent["error_type"], client.calls), ("budget_cap", 0))


class TestQwenGate(EngineState):
    def test_probe_items_go_to_the_probe_and_a_fatal_row_stops_every_lane(self):
        sent = []

        def campaign_factory(*args, **kwargs):
            self.assertIsNone(kwargs["max_in_flight"])  # the outer gate is the only one
            def request(client, item, shard, lane):
                sent.append(item.run_key)
                return {"status": "request_error", "fatal": True, "run_key": item.run_key}
            return request

        with mock.patch.object(rsl.pr, "make_request", campaign_factory):
            request = rsl.make_qwen_request(CONFIG, {"model": {"self_reported_id": "x", "requested_id": "Qwen3.5-9B-65K"}},
                                            "MC-104", pr.BudgetGuard(10_000), pr.OutageGuard(4), {})
        probe_row = request(FakeClient(("B", "Qwen3.5-9B-65K", [logprob("B", 0.9), logprob("A", 0.1)])), MC, 0, 0)
        self.assertEqual(probe_row["status"], "complete")
        s_item = v1.EvalItem(**{**MC.__dict__, "replicate_id": "S-r1"})
        self.assertTrue(request(None, s_item, 0, 1)["fatal"])
        halted = request(None, v1.EvalItem(**{**MC.__dict__, "replicate_id": "S-r2"}), 0, 2)
        self.assertEqual((halted["error_type"], sent), ("halted_before_send", [s_item.run_key]))


class TestMimo(EngineState):
    def test_one_routing_session_per_attempt_and_no_sampling_parameters(self):
        student = CONFIG["students"]["mimo"]
        request = rsl.make_mimo_request(student, "MC-104", pr.BudgetGuard(10_000), pr.OutageGuard(4), rsl.ModelPin("mimo"))
        client = FakeClient(("Trả lời: B", "mimo-v2.6-flash", None))
        row = request(client, MC, 0, 0)
        self.assertEqual(row["status"], "complete")
        self.assertEqual(client.kwargs["extra_headers"], {rsl.SESSION_HEADER: rsl.session_id(MC.run_key)})
        self.assertNotIn("temperature", client.kwargs)
        self.assertNotEqual(rsl.session_id("d:1:B-r1"), rsl.session_id("d:1:B-r2"))
        self.assertTrue(rsl.session_id("d:1:B-r1").startswith("vmlu-mc104-"))


class TestGates(unittest.TestCase):
    def test_gates(self):
        manifest = {"config_sha256": "c", "manifest_sha256": "m"}
        registration = {"card_ids": {sl.PHASE: "MC-104"}, "card_files": {sl.PHASE: "missing.md"},
                        "frozen": {"config_sha256": "c", "manifest_sha256": {"qwen": "m", "mimo": "other"}}}
        gates = {g.name: g.ok for g in rsl.evaluate_gates("qwen", manifest, registration, True, "ok",
                                                          card_text="## MC-104 — test\n")}
        self.assertEqual(gates, {"card_registered": True, "detail_card": False, "frozen_hashes": True,
                                 "route_identity": True})
        mimo = {g.name: g.ok for g in rsl.evaluate_gates("mimo", manifest, registration, False, "no",
                                                         card_text="## MC-103 — other\n")}
        self.assertEqual(mimo, {"card_registered": False, "detail_card": False, "frozen_hashes": False,
                                "route_identity": False})

    def test_only_multiple_choice_b_is_probed(self):
        self.assertTrue(rsl.is_probe(MC))
        self.assertFalse(rsl.is_probe(v1.EvalItem(**{**MC.__dict__, "replicate_id": "S-r1"})))
        self.assertFalse(rsl.is_probe(v1.EvalItem(**{**MC.__dict__, "dataset_id": sl.KNOW})))
        broken = v1.EvalItem(**{**MC.__dict__, "item_id": "x", "prompt": v1.build_prompt("Câu hỏi?", ["một", "hai"])})
        self.assertEqual((rsl.unreadable_probes([MC]), rsl.unreadable_probes([MC, broken])), ([], ["x"]))

    @unittest.skipUnless(sl.manifest_path("qwen").is_file(), "needs the frozen Qwen manifest")
    def test_only_the_two_vm14k_prompts_with_broken_options_lack_readable_letters(self):
        _, rebuilt = sl.build_manifest("qwen")
        unreadable = rsl.unreadable_probes(list(rebuilt.values()))
        self.assertEqual(len(unreadable), 2)
        self.assertTrue(all(rebuilt[f"{sl.VM14K}:{item_id}:B-r1"] for item_id in unreadable))


class TestUnreadableProbe(EngineState):
    def test_an_unreadable_option_block_leaves_the_confidence_missing_without_stopping(self):
        broken = v1.EvalItem(**{**MC.__dict__, "prompt": "Câu hỏi\nC. ba\nD. bốn\nĐáp án: "})
        request = rsl.make_probe(CONFIG["students"]["qwen"]["probe"], {"Qwen3.5-9B-65K"}, "MC-104", pr.BudgetGuard(1000),
                                 pr.OutageGuard(4), threading.Event())
        row = request(FakeClient(("C", "Qwen3.5-9B-65K", [logprob("C", 0.9), logprob("D", 0.1)])), broken, 0, 0)
        self.assertEqual((row["status"], row["confidence"], row["raw_response"]), ("complete", None, "C"))


if __name__ == "__main__":
    unittest.main()
