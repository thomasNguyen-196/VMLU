"""Offline tests for the router v3 calibration procedure (openspec change diagnostic-router-v3; no data, no network).

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_diagnostic_calibration
Expected values are worked out by hand in the comments.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import diagnostic_calibration as cal
from code_benchmark import diagnostic_router as router

D1, D2, D3 = "vmlu", "vm14k", "bidlqa"


def procedure(**overrides):
    base = json.loads(cal.PROCEDURE_PATH.read_text(encoding="utf-8"))
    base.update(overrides)
    return base


def mc(correct, prediction="A", tokens=100):
    return {"correct": int(correct), "prediction": prediction, "total_tokens": tokens}


def rd(f1, prediction="đáp án", em=0, tokens=100):
    return {"em": em, "token_f1": f1, "prediction": prediction, "total_tokens": tokens}


class TestProcedure(unittest.TestCase):
    def test_the_committed_procedure_loads(self):
        loaded, digest = cal.load_procedure()
        self.assertEqual(loaded["candidates"], list(cal.CANDIDATES))
        self.assertEqual(loaded["calibration_items"], 60)
        self.assertEqual(len(digest), 64)

    def test_out_of_contract_procedures_are_refused(self):
        bad = [procedure(extra=1),
               procedure(score={"multiple_choice": "accuracy", "reading": "em"}),
               procedure(candidates=["always_B", "always_S"]),
               procedure(calibration_items=0),
               procedure(tie=["candidate_order"]),
               procedure(probe={"arm": "S", "samples": 2, "agreement": "normalized-answer-v1"})]
        for value in bad:
            with self.assertRaises(SystemExit):
                cal.validate_procedure(value)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps(procedure(candidates=list(reversed(cal.CANDIDATES)))), encoding="utf-8")
            with self.assertRaises(SystemExit):
                cal.load_procedure(path)


class TestChoice(unittest.TestCase):
    def test_s_best_on_calibration_gives_always_s(self):
        # 60 items; B right on 30 and its two answers always agree, so v2 returns B: B 0.5, v2 0.5, S 50/60
        cells = [(mc(i < 30), mc(i < 30), mc(i < 50, tokens=900)) for i in range(60)]
        result = cal.choose(procedure(), cells, "multiple_choice")
        self.assertEqual(result["choice"], "always_S")
        self.assertAlmostEqual(result["scores"]["always_S"], 50 / 60)
        self.assertEqual(result["mean_tokens"], {"always_B": 100, "v2_cascade": 200, "always_S": 900})

    def test_equal_scores_go_to_the_cheaper_policy(self):
        # B and v2 both 0.5 (v2 never escalates); S 0.4; B is cheaper than v2, which pays the probe
        cells = [(mc(i < 30), mc(i < 30), mc(i < 24)) for i in range(60)]
        self.assertEqual(cal.choose(procedure(), cells, "multiple_choice")["choice"], "always_B")

    def test_the_cascade_wins_when_escalating_disagreements_pays(self):
        # 20 items where B's answers differ: B wrong, S right; 40 agreeing items where B is right and S wrong
        cells = [(mc(0, "A"), mc(0, "B"), mc(1)) for _ in range(20)] + [(mc(1), mc(1), mc(0)) for _ in range(40)]
        result = cal.choose(procedure(), cells, "multiple_choice")
        self.assertEqual(result["scores"], {"always_B": 40 / 60, "v2_cascade": 1.0, "always_S": 20 / 60})
        self.assertEqual(result["choice"], "v2_cascade")
        self.assertAlmostEqual(result["mean_tokens"]["v2_cascade"], (20 * 300 + 40 * 200) / 60)

    def test_reading_is_scored_by_token_f1_not_exact_match(self):
        # S matches exactly on every item but with token-F1 0.6; B never matches exactly but has token-F1 0.8
        cells = [(rd(0.8, "x"), rd(0.8, "x"), rd(0.6, em=1)) for _ in range(60)]
        result = cal.choose(procedure(), cells, "reading")
        self.assertEqual(result["choice"], "always_B")
        self.assertEqual(result["score"], "mean_token_f1")

    def test_an_empty_b_answer_escalates(self):
        cells = [(mc(0, ""), mc(0, ""), mc(1)) for _ in range(60)]  # unparsed B answers never agree
        self.assertEqual(cal.choose(procedure(), cells, "multiple_choice")["scores"]["v2_cascade"], 1.0)

    def test_the_sample_size_is_checked(self):
        with self.assertRaises(SystemExit):
            cal.choose(procedure(), [(mc(1), mc(1), mc(1))] * 59, "multiple_choice")


class TestRuleEmission(unittest.TestCase):
    def rule(self, choices):
        return cal.emit_rule(procedure(), choices, [D1, D2, D3], "v3-test")

    def test_each_choice_routes_like_its_policy(self):
        rule = self.rule({D1: "always_S", D2: "v2_cascade", D3: "always_B"})
        router.validate_rule(copy.deepcopy(rule), [D1, D2, D3])
        self.assertIn("probe", rule)

        def go(dataset, agrees=None):
            return router.route(rule, router.Features(dataset, 100, "câu hỏi"), agrees)

        self.assertEqual((go(D1).arm, go(D1).probed), ("S", False))
        self.assertEqual((go(D3).arm, go(D3).probed), ("B", False))
        self.assertEqual((go(D2, True).arm, go(D2, True).probed), ("B", True))   # answers agree: first B draw
        self.assertEqual((go(D2, False).arm, go(D2, False).probed), ("S", True))  # answers differ: escalate
        with self.assertRaises(SystemExit):
            go(D2)  # the cascade needs the probe outcome

    def test_a_rule_without_a_cascade_declares_no_probe(self):
        rule = self.rule({D1: "always_S", D2: "always_B", D3: "always_B"})
        self.assertNotIn("probe", rule)
        self.assertEqual(rule["default"], {"arm": "B", "targets": []})

    def test_unknown_choices_or_datasets_are_refused(self):
        with self.assertRaises(SystemExit):
            self.rule({D1: "always_K"})
        with self.assertRaises(SystemExit):
            cal.emit_rule(procedure(), {"other": "always_S"}, [D1], "v3-test")


if __name__ == "__main__":
    unittest.main()
