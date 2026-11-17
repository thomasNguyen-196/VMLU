"""Offline tests for plot_cost_quality's pure pieces (no run outputs needed)."""
from __future__ import annotations

import unittest

try:
    from code_benchmark import plot_cost_quality as pc
except ImportError:  # executed from code_benchmark/
    import plot_cost_quality as pc  # type: ignore[no-redef]


class Pareto(unittest.TestCase):
    def test_frontier_keeps_only_undominated_deployable_points(self):
        points = [pc.Point("B", "fixed", 100, 60), pc.Point("S", "fixed", 1000, 80),
                  pc.Point("R", "per_item", 500, 75), pc.Point("bad", "fixed", 800, 70),
                  pc.Point("O", "fixed", 300, 95, oracle=True)]
        self.assertEqual([p.label for p in pc.pareto(points)], ["B", "R", "S"])

    def test_equal_cost_keeps_the_better_score(self):
        points = [pc.Point("a", "fixed", 100, 60), pc.Point("b", "fixed", 100, 65)]
        self.assertEqual([p.label for p in pc.pareto(points)], ["b"])


class Formatting(unittest.TestCase):
    def test_vietnamese_numbers(self):
        self.assertEqual(pc.vn_number(10000), "10.000")
        self.assertEqual(pc.vn_number(73.333, 1), "73,3")

    def test_nice_step(self):
        self.assertEqual(pc.nice_step(20), 5)
        self.assertEqual(pc.nice_step(3), 1)

    def test_label_box(self):
        self.assertEqual(pc._box_left(100, "start", 40), 100)
        self.assertEqual(pc._box_left(100, "end", 40), 60)
        self.assertEqual(pc._box_left(100, "middle", 40), 80)


if __name__ == "__main__":
    unittest.main()
