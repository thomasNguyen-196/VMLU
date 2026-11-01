"""Offline tests of the table-loop runner (card MC-105): which attempts the probe takes, the shared gate, the MiMo
session and the execution gates. No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_run_table_loop
"""
from __future__ import annotations

import threading
import unittest
from unittest import mock

from code_benchmark import diagnostic_table_loop as tl
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_table_loop as rtl
from code_benchmark import vi_multimodel as v1
from code_benchmark.test_run_self_loop import MC, PROMPT, EngineState, FakeClient, logprob

CONFIG, _ = tl.load_config()
TABLE_MC = v1.EvalItem(**{**MC.__dict__, "dataset_id": "vi-multimodel-v1-legal-nli-150"})
READING = v1.EvalItem(dataset_id="vi-multimodel-v1-vi-squad-200", source_dataset="squad", item_id="7",
                      replicate_id="B-r1", task="reading", stratum="x", question="Ai?", passage_id="p",
                      prompt="Đọc đoạn văn\n\nCâu hỏi: Ai?\nTrả lời: ", gold_answer="An")


class TestProbe(EngineState):
    def test_the_probe_keeps_this_cards_phase(self):
        request = rtl.make_probe(CONFIG["students"]["qwen"]["probe"], {"Qwen3.5-9B-65K"}, "MC-105", pr.BudgetGuard(1000),
                                 pr.OutageGuard(4), threading.Event())
        client = FakeClient(("B", "Qwen3.5-9B-65K", [logprob("B", 0.7), logprob("A", 0.3)]))
        row = request(client, TABLE_MC, 0, 0)
        self.assertEqual((row["status"], row["phase"], row["measurement_card_id"]), ("complete", tl.PHASE, "MC-105"))
        self.assertAlmostEqual(row["confidence"], 0.7, places=5)
        self.assertEqual(client.kwargs["messages"], [{"role": "user", "content": PROMPT}])

    def test_only_multiple_choice_b_r1_is_probed(self):
        self.assertTrue(rtl.is_probe(TABLE_MC))
        self.assertFalse(rtl.is_probe(READING))
        self.assertFalse(rtl.is_probe(v1.EvalItem(**{**TABLE_MC.__dict__, "replicate_id": "S-r1"})))


class TestQwenGate(EngineState):
    def test_reading_b_goes_to_the_campaign_request_and_a_fatal_row_stops_every_lane(self):
        sent = []

        def campaign_factory(protocol, phase, card_id, guard, **kwargs):
            self.assertEqual((phase, kwargs["max_in_flight"]), (tl.PHASE, None))
            def request(client, item, shard, lane):
                sent.append(item.run_key)
                return {"status": "request_error", "fatal": True, "run_key": item.run_key}
            return request

        with mock.patch.object(rtl.pr, "make_request", campaign_factory):
            request = rtl.make_qwen_request(CONFIG, {"model": {"self_reported_id": "x", "requested_id": "Qwen3.5-9B-65K"}},
                                            "MC-105", pr.BudgetGuard(10_000), pr.OutageGuard(4))
        probe = request(FakeClient(("B", "Qwen3.5-9B-65K", [logprob("B", 0.9), logprob("A", 0.1)])), TABLE_MC, 0, 0)
        self.assertEqual(probe["status"], "complete")
        self.assertTrue(request(None, READING, 0, 1)["fatal"])
        halted = request(None, v1.EvalItem(**{**READING.__dict__, "replicate_id": "B-r2"}), 0, 2)
        self.assertEqual((halted["error_type"], sent), ("halted_before_send", [READING.run_key]))


class TestMimo(EngineState):
    def test_one_routing_session_per_attempt_under_this_cards_prefix(self):
        request = rtl.make_mimo_request(CONFIG["students"]["mimo"], "MC-105", pr.BudgetGuard(10_000), pr.OutageGuard(4),
                                        rtl.ModelPin("mimo"))
        client = FakeClient(("Trả lời: An", "mimo-v2.6-flash", None))
        row = request(client, READING, 0, 0)
        self.assertEqual((row["status"], row["phase"]), ("complete", tl.PHASE))
        self.assertEqual(client.kwargs["extra_headers"], {rtl.rsl.SESSION_HEADER: rtl.session_id(READING.run_key)})
        self.assertTrue(rtl.session_id(READING.run_key).startswith("vmlu-mc105-"))
        self.assertEqual(client.kwargs["max_completion_tokens"], 20000)


class TestGates(unittest.TestCase):
    def test_gates(self):
        manifest = {"config_sha256": "c", "manifest_sha256": "m"}
        registration = {"card_ids": {tl.PHASE: "MC-105"}, "card_files": {tl.PHASE: "missing.md"},
                        "frozen": {"config_sha256": "c", "manifest_sha256": {"qwen": "m", "mimo": "other"}}}
        qwen = {g.name: g.ok for g in rtl.evaluate_gates("qwen", manifest, registration, True, "ok",
                                                         card_text="## MC-105 — test\n")}
        self.assertEqual(qwen, {"card_registered": True, "detail_card": False, "frozen_hashes": True,
                                "route_identity": True})
        mimo = {g.name: g.ok for g in rtl.evaluate_gates("mimo", manifest, registration, False, "no",
                                                         card_text="## MC-104 — other\n")}
        self.assertEqual(mimo, {"card_registered": False, "detail_card": False, "frozen_hashes": False,
                                "route_identity": False})


if __name__ == "__main__":
    unittest.main()
