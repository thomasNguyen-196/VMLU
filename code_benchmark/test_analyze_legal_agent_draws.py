"""Offline tests for MC-115's analysis (analyze_legal_agent_draws), on synthetic cells. Run from the repo root:
  .venv/bin/python -m unittest code_benchmark.test_analyze_legal_agent_draws
"""
from __future__ import annotations

import unittest

from code_benchmark import analyze_legal_agent_draws as a
from code_benchmark import analyze_legal_agent_v2 as alv2


def cell(scores: dict[str, list[float]], metric: str = "correct") -> dict[str, dict[str, float]]:
    """{"DSHF": [d1, d2, d3, d4], ...} -> {"DSHF1": {metric: d1}, ...}"""
    return {f"{arm}{i + 1}": {metric: value} for arm, values in scores.items() for i, value in enumerate(values)}


class Scores(unittest.TestCase):
    def test_item_score_uses_the_named_draws(self):
        c = cell({"DSHF": [1, 0, 1, 1]})
        self.assertEqual(a.item_score(c, "DSHF", "correct", a.ALL_DRAWS), 0.75)
        self.assertEqual(a.item_score(c, "DSHF", "correct", a.OLD_DRAWS), 0.5)
        self.assertEqual(a.item_score(c, "DSHF", "correct", a.NEW_DRAWS), 1.0)

    def test_compare_on_four_draws(self):
        cells = {"k1": cell({"DSHF": [1, 1, 1, 1], "B": [1, 0, 1, 0]}), "k2": cell({"DSHF": [0, 1, 1, 1], "B": [1, 1, 1, 1]})}
        block = a.compare(["k1", "k2"], cells, "DSHF", "B", "correct")
        self.assertEqual((block["DSHF"], block["B"]), (87.5, 75.0))
        self.assertEqual(block["DSHF_versus_B"]["mean_points"], 12.5)
        self.assertEqual((block["DSHF_versus_B"]["better"], block["DSHF_versus_B"]["worse"]), (1, 1))

    def test_drift_is_new_minus_old(self):
        cells = {"k1": cell({"B": [1, 1, 0, 0]}), "k2": cell({"B": [1, 0, 0, 0]})}
        out = a.drift(["k1", "k2"], cells, "B", "correct")
        self.assertEqual((out["draws_1_2"], out["draws_3_4"], out["drift_points"]), (75.0, 0.0, -75.0))

    def test_noise_counts_items_whose_draws_disagree(self):
        cells = {"k1": cell({"B": [1, 1, 1, 1]}), "k2": cell({"B": [1, 0, 1, 1]})}
        self.assertEqual(a.noise(["k1", "k2"], cells, "B", "correct")["items_with_disagreeing_draws_pct"], 50.0)


class Guards(unittest.TestCase):
    def test_a_draw_in_two_cards_fails(self):
        with self.assertRaises(SystemExit):
            a.merge({"k": cell({"B": [1]})}, {"k": cell({"B": [0]})})

    def test_merge_joins_old_and_new_draws(self):
        merged = a.merge({"k": {"B1": {"correct": 1}}}, {"k": {"B3": {"correct": 0}}})
        self.assertEqual(sorted(merged["k"]), ["B1", "B3"])

    def test_a_missing_draw_fails(self):
        cells = {"k": cell({"DSHF": [1, 1, 1, 1], "OMPF": [1, 1, 1, 1], "B": [1, 1, 1]})}
        with self.assertRaises(SystemExit):
            a.check_complete(cells, {"M": ["k"]})
        cells["k"]["B4"] = {"correct": 1}
        a.check_complete(cells, {"M": ["k"]})


class ReadingRule(unittest.TestCase):
    def test_spec_scenario_m2_better_with_margin(self):
        blocks = {"M2": {"DSHF_versus_B": {"mean_points": 3.0, "sign_flip_p": 0.01}}}
        rule = alv2.rules(blocks, {"M2": ["DSHF", "B"]}, 0.05, 2.24, ["M2"])["M2"]
        self.assertTrue(rule["left_better"])
        self.assertEqual(rule["reading"], "DSHF is better than B")

    def test_inside_the_margin_is_no_clear_difference(self):
        blocks = {"M2": {"DSHF_versus_B": {"mean_points": 2.0, "sign_flip_p": 0.001}}}
        rule = alv2.rules(blocks, {"M2": ["DSHF", "B"]}, 0.05, 2.24, ["M2"])["M2"]
        self.assertEqual(rule["reading"], "no clear difference between DSHF and B")


if __name__ == "__main__":
    unittest.main()
