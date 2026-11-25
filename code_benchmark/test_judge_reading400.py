"""Offline tests of the Reading-400 model-as-judge check (no model call)."""
from __future__ import annotations

import unittest

from code_benchmark import judge_reading400 as jr


class TestJudgeReading400(unittest.TestCase):
    def test_confusion_counts_and_kappa(self) -> None:
        pairs = [(True, True)] * 6 + [(True, False)] * 2 + [(False, True)] * 1 + [(False, False)] * 1
        cell = jr.confusion(pairs)
        self.assertEqual((cell["TP"], cell["FP"], cell["FN"], cell["TN"]), (6, 2, 1, 1))
        self.assertEqual(cell["agreement"], 0.7)
        self.assertEqual(cell["precision"], 0.75)
        self.assertEqual(cell["bias_pts"], 10.0)  # metric says 80%, judge 70%
        self.assertAlmostEqual(cell["kappa"], (0.7 - (0.8 * 0.7 + 0.2 * 0.3)) / (1 - 0.62), places=3)

    def test_shards_cover_every_item_once_with_overlap(self) -> None:
        plan = jr.plan_shards(400)
        owned = [i for ids in plan["owned"] for i in ids]
        self.assertEqual(sorted(owned), list(range(400)))
        self.assertTrue(all(len(f) == 115 for f in plan["files"]))
        for k, extra in enumerate(plan["extra"]):
            self.assertTrue(set(extra) <= set(plan["owned"][(k + 1) % 4]))
        self.assertTrue(all(sorted(s) == ["mimo", "qwen"] for s in plan["slots"].values()))

    def test_metrics_on_a_worked_answer(self) -> None:
        values = jr.metric_values("Chênh lệch: 3,28 - 2,67 = **0,61 người**", "0,61")
        self.assertFalse(values["em_v3"])
        self.assertTrue(values["r_eq_1"])
        self.assertLess(values["token_f1"], 0.5)
        self.assertTrue(jr.metric_values("Trả lời: 0,61 người", "0,61")["r_eq_1"])


if __name__ == "__main__":
    unittest.main()
