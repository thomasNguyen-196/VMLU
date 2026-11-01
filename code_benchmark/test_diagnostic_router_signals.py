"""Offline tests for the router-signals study (openspec change diagnostic-router-signals; card MC-99).

The manifest tests read the frozen inputs; the runner tests use a fake transport; the analysis tests use synthetic
items only. Run from the repo root:
  .venv/bin/python -m unittest code_benchmark.test_diagnostic_router_signals
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

import numpy as np

from code_benchmark import analyze_router_signals as ars
from code_benchmark import diagnostic_router_signals as sig
from code_benchmark import run_router_signals as runner


def _answers(model: str = "jev-1.13-free", cost: float = 0, billing: str = "free") -> dict:
    return {"model": model, "answers": {"answer_correct": {"type": "noul", "noul": 0.8},
                                        "group": {"type": "choice", "choice": "tra_cuu", "confidence": 0.6,
                                                  "probabilities": {"tra_cuu": 0.7, "so_hieu": 0.3}}},
            "usage": {"input_tokens": 400, "output_tokens": 40, "cost": cost, "opencode": {"billing_source": billing}}}


class FakeTransport:
    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, body, headers, timeout):
        self.calls.append({"url": url, "body": body, "headers": headers})
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        status, parsed = response
        return status, parsed, json.dumps(parsed), {}


ROW = {"dataset_id": "vi-multimodel-v1-bidlqa-test", "item_id": "X1", "replicate_id": "jev-pre", "kind": "pre",
       "answer_draw": None, "request_sha256": "0" * 64}


class TestManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, _ = sig.load_config()
        cls.manifest, cls.requests = sig.build_manifest()

    def test_frozen_manifest_rebuilds_with_the_registered_counts(self):
        self.assertEqual(self.manifest, sig.load_frozen_manifest())
        self.assertEqual(self.manifest["n"], 2901)
        self.assertEqual(self.manifest["kind_counts"], {"post": 1934, "pre": 967})

    def test_states_carry_no_gold_and_post_hoc_carries_the_b_prediction(self):
        answers, _ = sig.load_answers(self.config)
        for row in self.requests:
            state = row["body"]["state"]
            self.assertLessEqual(set(state), {"passage", "question", "proposed_answer"})
            if row["kind"] == "post":
                key = f"{row['dataset_id']}:{row['item_id']}"
                self.assertEqual(state["proposed_answer"], answers[row["answer_draw"]][key])
                self.assertEqual(set(row["body"]["questions"]), set(self.config["requests"]["post"]["questions"]))
            else:
                self.assertNotIn("proposed_answer", state)
            self.assertEqual(row["body"]["model"], "jev-1.13-free")

    def test_config_validation_fails_closed(self):
        broken = copy.deepcopy(self.config)
        criteria = broken["requests"]["pre"]["questions"]["group"]["criteria"]
        broken["requests"]["pre"]["questions"]["group"]["criteria"] = dict(reversed(list(criteria.items())))
        with self.assertRaisesRegex(SystemExit, "six MC-98 groups"):
            sig.validate_config(broken)
        broken = copy.deepcopy(self.config)
        broken["requests"]["post"]["questions"]["answer_correct"]["criteria"] = "x"
        with self.assertRaisesRegex(SystemExit, "noul question takes only"):
            sig.validate_config(broken)


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.config, _ = sig.load_config()
        self.route = self.config["route"]

    def test_complete_call_records_answers_and_usage_without_the_key(self):
        transport = FakeTransport([(200, _answers())])
        record = runner.call_signal(transport, ROW, {"model": "m"}, self.route, "secret-key", sleep=lambda s: None)
        self.assertEqual(record["status"], "complete")
        self.assertEqual(record["billing_source"], "free")
        self.assertNotIn("secret-key", json.dumps(record))
        self.assertTrue(transport.calls[0]["url"].endswith("/inference/systemone/v1/systemone"))
        self.assertTrue(transport.calls[0]["headers"]["x-opencode-session"].startswith("vmlu-mc99-"))

    def test_rate_limit_is_retried_within_the_registered_count(self):
        waits = []
        transport = FakeTransport([(429, {"error": "slow down"}), (200, _answers())])
        record = runner.call_signal(transport, ROW, {}, self.route, "k", sleep=waits.append)
        self.assertEqual(record["status"], "complete")
        self.assertEqual(len(record["retries"]), 1)
        self.assertEqual(waits, [30])
        always = FakeTransport([(429, {"error": "slow down"})])
        record = runner.call_signal(always, ROW, {}, self.route, "k", sleep=lambda s: None)
        self.assertEqual(record["status"], "request_error")
        self.assertEqual(len(record["retries"]), self.route["max_retries"])

    def test_halts(self):
        auth = runner.call_signal(FakeTransport([(401, {"error": "no"})]), ROW, {}, self.route, "k", lambda s: None)
        self.assertEqual(runner.halt_reason(auth, self.route, 0), "authentication_error")
        paid = runner.call_signal(FakeTransport([(200, _answers(cost=0.01, billing="balance"))]), ROW, {}, self.route,
                                  "k", lambda s: None)
        self.assertEqual(runner.halt_reason(paid, self.route, 0), "non_free_billing")
        other = runner.call_signal(FakeTransport([(200, _answers(model="jev-1.13"))]), ROW, {}, self.route, "k",
                                   lambda s: None)
        self.assertEqual(runner.halt_reason(other, self.route, 0), "model_id_changed")
        down = runner.call_signal(FakeTransport([urllib.error.URLError("down")]), ROW, {}, self.route, "k",
                                  lambda s: None)
        self.assertEqual(down["status"], "network_error")
        self.assertEqual(runner.halt_reason(down, self.route, 4), "endpoint_unresponsive")

    def test_execute_stops_on_non_free_billing_and_writes_signals(self):
        rows = [dict(ROW, item_id=f"X{i}", body={"model": "m"}) for i in range(6)]
        config = copy.deepcopy(self.config)
        config["route"]["max_in_flight"] = 1
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            transport = FakeTransport([(200, _answers()), (200, _answers(cost=0.5, billing="balance")),
                                       (200, _answers())])
            summary = runner.execute(output, rows, config, "k", transport, lambda s: None)
            self.assertEqual(summary["halt_reason"], "non_free_billing")
            self.assertLess(summary["complete"], 6)
            signals = [json.loads(line) for line in (output / "signals.jsonl").read_text().splitlines()]
            self.assertEqual(signals[0]["answer_correct"], 0.8)
            self.assertEqual(signals[0]["group"], "tra_cuu")
            self.assertEqual(signals[0]["group_probabilities"], {"tra_cuu": 0.7, "so_hieu": 0.3})

    def test_gates(self):
        manifest = sig.load_frozen_manifest()
        registration = {"card_ids": {"signals": "MC-99"}, "card_files": {"signals": "README.md"},
                        "frozen": {"config_sha256": manifest["config_sha256"],
                                   "manifest_sha256": manifest["manifest_sha256"]},
                        "route": {key: self.route[key] for key in ("endpoint_host", "path", "model_id")}}
        gates = runner.evaluate_gates(self.config, manifest, registration, True, card_text="## MC-99 — x\n")
        self.assertTrue(all(gate.ok for gate in gates), gates)
        registration["frozen"]["manifest_sha256"] = "0" * 64
        gates = runner.evaluate_gates(self.config, manifest, registration, True, card_text="## MC-99 — x\n")
        self.assertFalse(next(gate for gate in gates if gate.name == "frozen_hashes").ok)


def _item(dataset: str, scores: dict, tokens: dict | None = None, passage: str = "p") -> dict:
    return {"key": f"{dataset}:{len(scores)}", "dataset": dataset, "passage_id": passage, "item_id": "i",
            "score": scores, "tokens": tokens or {name: 10 for name in scores}, "prediction": {}}


class TestAnalysis(unittest.TestCase):
    def test_cross_draw_never_scores_on_the_fitting_draw(self):
        # draw 1 favours B, draw 2 favours S: each draw's choice is scored on the other draw
        items = [_item("d", {"B1": 1.0, "B2": 0.0, "S1": 0.0, "S2": 1.0, "Q1": 0.0, "Q2": 0.0}) for _ in range(30)]
        policy = ars.per_dataset_fixed(items, ars.READING_ARMS)
        # fit on 1 -> B, scored on 2 -> 0; fit on 2 -> S, scored on 1 -> 0
        self.assertEqual(policy["scores"], [0.0] * 30)

    def test_small_groups_take_the_dataset_arm(self):
        items = ([_item("d", {"B1": 1.0, "B2": 1.0, "S1": 0.0, "S2": 0.0, "Q1": 0.0, "Q2": 0.0}) for _ in range(25)]
                 + [_item("d", {"B1": 0.0, "B2": 0.0, "S1": 1.0, "S2": 1.0, "Q1": 0.0, "Q2": 0.0}) for _ in range(5)])
        labels = ["g"] * 25 + ["small"] * 5
        policy = ars.grouped(items, labels, ars.READING_ARMS)
        self.assertEqual(policy["scores"][-1], 0.0)  # the 5-item group falls back to the dataset arm, B
        self.assertEqual(policy["scores"][0], 1.0)

    def test_cascade_cost_adds_s_only_when_escalated(self):
        item = _item("d", {"B1": 0.2, "B2": 0.4, "S1": 0.9, "S2": 0.7}, {"B1": 10, "B2": 12, "S1": 100, "S2": 80})
        keep = ars.cascade([item], lambda it, draw: draw == "1")
        self.assertEqual(keep["tokens"], [(10 + (12 + 80)) / 2])
        self.assertEqual(keep["scores"], [(0.2 + 0.7) / 2])
        self.assertEqual(keep["escalated"], [0.5])

    def test_threshold_is_chosen_on_the_other_draw(self):
        # draw 1: accepting B is best at any tau; draw 2: escalating everything is best
        items = [_item("d", {"B1": 1.0, "S1": 0.0, "B2": 0.0, "S2": 1.0}) for _ in range(10)]
        policy, chosen = ars.crossfit_threshold(items, lambda it, draw: 0.6, [0.5, 0.7])
        self.assertEqual(chosen, {"1": 0.7, "2": 0.5})  # draw 1 uses the tau fitted on draw 2, and vice versa
        self.assertEqual(policy["scores"], [0.0] * 10)

    def test_ridge_rule_learns_a_feature_on_other_folds(self):
        rng = np.random.default_rng(0)
        items, rows = [], []
        for index in range(200):
            good_for_s = index % 2 == 0
            scores = {"B1": 0.0 if good_for_s else 1.0, "B2": 0.0 if good_for_s else 1.0,
                      "S1": 1.0 if good_for_s else 0.0, "S2": 1.0 if good_for_s else 0.0}
            items.append(_item("d", scores, passage=f"p{index}"))
            rows.append([1.0 if good_for_s else 0.0, rng.normal()])
        policy = ars.ridge_rule(items, np.array(rows))
        self.assertGreater(sum(policy["scores"]) / len(items), 0.95)

    def test_reading_rule(self):
        base = {"score": 70.0, "mean_student_tokens": 1000.0}
        self.assertTrue(ars.reading_rule({"score": 71.0, "mean_student_tokens": 2000.0}, base)["quality"])
        self.assertTrue(ars.reading_rule({"score": 69.6, "mean_student_tokens": 500.0}, base)["cost"])
        verdict = ars.reading_rule({"score": 69.2, "mean_student_tokens": 400.0}, base)
        self.assertFalse(verdict["promising"])

    def test_ceiling_and_auroc(self):
        a = [1.0, 0.0, 1.0, 0.0]
        c = [0.0, 1.0, 0.0, 1.0]
        block = ars.ceiling(a, a, c, c)
        self.assertEqual(block["draw_correlation"], 1.0)
        self.assertEqual(block["wins_both_draws"], {"a": 2, "c": 2})
        self.assertEqual(block["single_draw_router_gain_points"], 50.0)
        self.assertEqual(ars.auroc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]), 1.0)
        self.assertEqual(ars.auroc([0.5, 0.5], [True, False]), 0.5)


if __name__ == "__main__":
    unittest.main()
