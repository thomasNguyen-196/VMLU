"""Offline test of the six-cell flow analysis's divergence step.

    .venv/bin/python -m unittest code_benchmark.test_analyze_harness_flows_mc117
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from code_benchmark import analyze_harness_flows_mc117 as f


def attempt(key: str, arm: str, tokens: list[str]) -> dict:
    return {"model": "qwen", "key": key, "draw": "1", "arm": arm, "flow": SimpleNamespace(tokens=tokens)}


class TestDivergence(unittest.TestCase):
    def test_first_divergent_step_and_identical_pairs(self):
        rows = [attempt("k1", "OMPF", ["G+", "A"]), attempt("k1", "OMPS", ["G+", "Rm", "A"]),
                attempt("k2", "OMPF", ["G0", "G+", "A"]), attempt("k2", "OMPS", ["G0", "G+", "A"]),
                attempt("k3", "OMPF", ["G+", "A"]), attempt("k3", "DSHF", ["G+", "A"])]
        d = f.divergence(rows, "qwen", "OMPF", "OMPS")
        self.assertEqual((d["pairs"], d["identical_pct"], d["first_divergence_step_median"]), (2, 50.0, 1))
        self.assertEqual(d["at_divergence"], [{"OMPF": "A", "OMPS": "Rm", "share_pct": 50.0}])


if __name__ == "__main__":
    unittest.main()
