"""Offline tests of the router results builder (web/data/router-results.json). No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_build_router_results
"""
from __future__ import annotations

import unittest

from code_benchmark import build_router_results as brr

HAS_REPORTS = all((brr.ROOT / path).is_file() for path in brr.REPORTS.values())


class TestRules(unittest.TestCase):
    def test_published_wording_must_match_the_report(self):
        self.assertEqual(brr.settle("MC-0", "not_met", "not_met"), "not_met")
        with self.assertRaises(SystemExit):
            brr.settle("MC-0", "met", "not_met")

    def test_a_win_needs_a_small_p_and_a_gain(self):
        self.assertTrue(brr.better(0.01, 2.0))
        self.assertFalse(brr.better(0.01, -2.0))
        self.assertFalse(brr.better(0.2, 2.0))


@unittest.skipUnless(HAS_REPORTS, "needs the registered analysis reports under all_res/")
class TestBuild(unittest.TestCase):
    def test_every_experiment_is_built_from_its_report(self):
        data = brr.build()
        status = {experiment["cards"]: experiment["status"] for experiment in data["experiments"]}
        self.assertEqual(status, {"MC-90, MC-91, MC-92": "not_met", "MC-93": "not_met", "MC-94": "partial",
                                  "MC-95": "not_met", "MC-96": "not_met", "MC-97": "descriptive", "MC-98": "not_met",
                                  "MC-100": "met", "MC-101": "not_met", "MC-102": "not_met", "MC-103": "descriptive"})
        for experiment in data["experiments"]:
            self.assertTrue(experiment["sources"])
            self.assertTrue(all(len(source["sha256"]) == 64 for source in experiment["sources"]))


if __name__ == "__main__":
    unittest.main()
