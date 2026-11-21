"""Offline tests of MC-117's registered analysis on synthetic cells.

    .venv/bin/python -m unittest code_benchmark.test_analyze_legal_agent_omp_prompt
"""
from __future__ import annotations

import unittest
from unittest import mock

from code_benchmark import analyze_legal_agent_omp_prompt as a


def cell(**arms: list[float]) -> dict:
    return {f"{arm}{d + 1}": {"correct": v} for arm, values in arms.items() for d, v in enumerate(values)}


class TestTests(unittest.TestCase):
    def setUp(self):
        # Qwen: OMPS fixes OMPF on item 0; MiMo: OMPS loses on item 1
        self.cells = {
            "qwen": {"k0": cell(OMPS=[1, 1], OMPF=[0, 0], DSHF=[1, 1]), "k1": cell(OMPS=[1, 0], OMPF=[1, 0], DSHF=[1, 1])},
            "mimo": {"k0": cell(OMPS=[1, 1], OMPF=[1, 1], DSHF=[1, 1]), "k1": cell(OMPS=[0, 0], OMPF=[1, 1], DSHF=[0, 0])},
        }

    def test_changes_and_blocks(self):
        keys = ["k0", "k1"]
        self.assertEqual(a.change(keys, self.cells["qwen"], "correct"), [1.0, 0.0])
        self.assertEqual(a.change(keys, self.cells["mimo"], "correct"), [0.0, -1.0])
        blocks = a.blocks(keys, self.cells, "correct")
        self.assertEqual(blocks["P1"]["OMPS_versus_OMPF"]["mean_points"], 50.0)
        self.assertEqual(blocks["P2"]["OMPS_versus_OMPF"]["mean_points"], -50.0)
        self.assertEqual(blocks["P3"]["mimo_change_versus_qwen_change"]["mean_points"], -100.0)

    def test_remaining_interaction(self):
        # original: MiMo's OMPF - DSHF [0, 1] minus Qwen's [-1, -0.5] = [1, 1.5] -> 125 points;
        # remaining: MiMo's OMPS - DSHF [0, 0] minus Qwen's [0, -0.5] = [0, 0.5] -> 25 points
        with mock.patch.dict(a.ORIGINAL_INTERACTION, {"M": 125.0}):
            r = a.remaining_interaction(["k0", "k1"], self.cells, "correct", "M")
        self.assertEqual((r["original_points"], r["remaining_points"], r["share_removed_pct"]), (125.0, 25.0, 80.0))

    def test_original_interaction_must_match(self):
        with self.assertRaises(SystemExit):
            a.remaining_interaction(["k0", "k1"], self.cells, "correct", "M")

    def test_p3_reading(self):
        block = {"mimo_change_versus_qwen_change": {"ci95_points": [-9.0, -3.0]}}
        self.assertEqual(a.p3_reading(block, {"mean_points": -6.0, "p_holm": 0.003}, 2.24, 0.05),
                         "omp's default prompt carries part of the interaction")
        block = {"mimo_change_versus_qwen_change": {"ci95_points": [-2.0, 2.0]}}
        self.assertIn("carries none", a.p3_reading(block, {"mean_points": 0.1, "p_holm": 1.0}, 2.24, 0.05))
        block = {"mimo_change_versus_qwen_change": {"ci95_points": [-1.0, 3.0]}}
        self.assertIn("carries none", a.p3_reading(block, {"mean_points": 1.0, "p_holm": 1.0}, 0.0, 0.05))
        block = {"mimo_change_versus_qwen_change": {"ci95_points": [-6.0, 3.0]}}
        self.assertEqual(a.p3_reading(block, {"mean_points": -1.0, "p_holm": 0.4}, 2.24, 0.05), "not determined")

    def test_merge_refuses_overlap(self):
        with self.assertRaises(SystemExit):
            a.merge({"k": {"OMPS1": {}}}, {"k": {"OMPS1": {}}})


if __name__ == "__main__":
    unittest.main()
