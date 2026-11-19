"""Offline tests for MC-116's analysis (analyze_legal_agent_mimo) on synthetic cells."""
from __future__ import annotations

import unittest

try:
    from code_benchmark import analyze_legal_agent_mimo as am
except ImportError:  # executed from code_benchmark/
    import analyze_legal_agent_mimo as am  # type: ignore[no-redef]


def _cells(scores):
    """{key: {arm: (draw1, draw2)}} -> cells of rows carrying `correct`."""
    return {key: {f"{arm}{d + 1}": {"correct": v} for arm, pair in arms.items() for d, v in enumerate(pair)}
            for key, arms in scores.items()}


class ModelComparisonTests(unittest.TestCase):
    def test_gap_difference_is_mimos_gap_minus_qwens(self):
        mimo = _cells({"a": {"OMPF": (1, 1), "DSHF": (1, 1)}, "b": {"OMPF": (0, 1), "DSHF": (1, 1)}})
        qwen = _cells({"a": {"OMPF": (0, 0), "DSHF": (1, 1)}, "b": {"OMPF": (0, 0), "DSHF": (1, 1)}})
        out = am.gap_difference(["a", "b"], mimo, qwen, "OMPF", "DSHF", "correct")
        self.assertEqual((out["mimo_gap_points"], out["qwen_gap_points"]), (-25.0, -100.0))
        self.assertEqual(out["mimo_minus_qwen"]["mean_points"], 75.0)

    def test_model_difference_per_arm(self):
        mimo = _cells({"a": {"B": (1, 1)}, "b": {"B": (1, 0)}})
        qwen = _cells({"a": {"B": (0, 0)}, "b": {"B": (1, 0)}})
        out = am.model_difference(["a", "b"], mimo, qwen, "B", "correct")
        self.assertEqual((out["mimo"], out["qwen"], out["mimo_versus_qwen"]["mean_points"]), (75.0, 25.0, 50.0))

    def test_missing_draws_are_refused(self):
        cells = _cells({"a": {"DSHF": (1, 1), "OMPF": (1, 1)}})
        with self.assertRaises(SystemExit):
            am.check_complete(cells, {"M": ["a"]}, am.DRAWS, "MiMo")  # B is missing

    def test_attempt_profile_counts_outcomes_and_means(self):
        rows = [{"arm": "DSHF", "outcome": "complete", "requests": 4, "tool_calls": {"grep": 2, "read": 1},
                 "total_tokens": 1000, "reasoning_tokens": 300, "completion_tokens": 400, "max_completion_tokens_used": 250},
                {"arm": "DSHF", "outcome": "answer_cap", "requests": 6, "tool_calls": {"grep": 1},
                 "total_tokens": 3000, "reasoning_tokens": None, "completion_tokens": 600, "max_completion_tokens_used": 16000}]
        out = am.attempt_profile(rows)["DSHF"]
        self.assertEqual(out["outcomes"], {"answer_cap": 1, "complete": 1})
        self.assertEqual((out["mean_requests"], out["mean_tool_calls"], out["mean_total_tokens"]), (5.0, 2.0, 2000.0))
        self.assertEqual((out["mean_reasoning_tokens"], out["max_completion_tokens_used"]), (300.0, 16000))


if __name__ == "__main__":
    unittest.main()
