"""Offline tests of the post hoc score-against-tokens analysis (analyze_loop_pareto). No endpoint, no run files.

  .venv/bin/python -m unittest code_benchmark.test_analyze_loop_pareto
"""
from __future__ import annotations

import unittest

from code_benchmark import analyze_loop_pareto as alp
from code_benchmark import diagnostic_self_loop as sl


def mc_row(prediction: str, tokens: int, gold: str = "A", confidence: float | None = None) -> dict:
    row = {"prediction": prediction, "gold_answer": gold, "total_tokens": tokens}
    if confidence is not None:
        row["confidence"] = confidence
    return row


def reading_row(prediction: str, f1: float, tokens: int) -> dict:
    return {"prediction": prediction, "gold_answer": "x", "total_tokens": tokens,
            "token_f1": f1, "em": float(f1 == 1.0), "token_f1_v2": f1, "em_v2": float(f1 == 1.0)}


class ParetoSetTest(unittest.TestCase):
    def test_a_policy_beaten_on_both_is_dropped(self):
        policies = {"cheap": {"score": 50.0, "mean_tokens": 100.0}, "good": {"score": 60.0, "mean_tokens": 200.0},
                    "dear": {"score": 55.0, "mean_tokens": 300.0}}
        self.assertEqual(alp.pareto_set(policies), ["cheap", "good"])

    def test_two_equal_policies_both_stay(self):
        policies = {"a": {"score": 50.0, "mean_tokens": 100.0}, "b": {"score": 50.0, "mean_tokens": 100.0}}
        self.assertEqual(alp.pareto_set(policies), ["a", "b"])

    def test_equal_score_with_more_tokens_is_dropped(self):
        policies = {"a": {"score": 50.0, "mean_tokens": 100.0}, "b": {"score": 50.0, "mean_tokens": 101.0}}
        self.assertEqual(alp.pareto_set(policies), ["a"])


class TableItemTest(unittest.TestCase):
    def test_qwen_confident_item_pays_only_the_probe(self):
        attempts = {"B-r1": mc_row("A", 5, confidence=0.9), "S-r1": mc_row("B", 400),
                    "S-r2": mc_row("B", 400), "S-r3": mc_row("B", 400)}
        item = alp.table_item("qwen", "multiple_choice", attempts, 0.8)
        self.assertTrue(item["sure"])
        self.assertEqual(item["score"]["gate_S"], 1.0)
        self.assertEqual(item["tokens"]["gate_S"], 5)
        self.assertEqual(item["tokens"]["loop"], 5)

    def test_qwen_unsure_item_takes_s1_and_skips_the_vote(self):
        attempts = {"B-r1": mc_row("C", 5, confidence=0.4), "S-r1": mc_row("B", 400),
                    "S-r2": mc_row("A", 300), "S-r3": mc_row("A", 200)}
        item = alp.table_item("qwen", "multiple_choice", attempts, 0.8)
        self.assertFalse(item["sure"])
        self.assertEqual(item["score"]["gate_S"], 0.0)   # S-r1 says B
        self.assertEqual(item["score"]["loop"], 1.0)     # the vote says A
        self.assertEqual(item["tokens"]["gate_S"], 405)
        self.assertEqual(item["tokens"]["loop"], 905)
        self.assertEqual(item["tokens"]["always_vote"], 900)

    def test_mimo_pays_for_both_b_answers(self):
        attempts = {"B-r1": mc_row("C", 50), "B-r2": mc_row("A", 60), "S-r1": mc_row("A", 400),
                    "S-r2": mc_row("A", 1), "S-r3": mc_row("A", 1)}
        item = alp.table_item("mimo", "multiple_choice", attempts, 0.8)
        self.assertEqual(item["score"]["gate_S"], 1.0)
        self.assertEqual(item["tokens"]["gate_S"], 510)
        self.assertEqual(item["tokens"]["loop"], 510)     # S-r1 agrees with B-r2: round 2 ends the loop

    def test_reading_scores_by_token_f1(self):
        attempts = {"B-r1": reading_row("một", 0.2, 30), "B-r2": reading_row("hai", 0.4, 30),
                    "S-r1": reading_row("ba", 0.9, 300), "S-r2": reading_row("bốn", 0.1, 300),
                    "S-r3": reading_row("năm", 0.1, 300)}
        item = alp.table_item("qwen", "reading", attempts, 0.8)
        self.assertEqual(item["score"]["gate_S"], 0.9)
        self.assertEqual(item["tokens"]["gate_S"], 360)


class SelfItemTest(unittest.TestCase):
    def test_qwen_unsure_item_takes_s1(self):
        cell = {"dataset_id": sl.VMLU, "item_id": "x", "gold": "A", "b": ["C"], "s": ["A", "B", "B"],
                "b_tokens": [5], "s_tokens": [300, 200, 100], "confidence": 0.3, "question": ""}
        item = alp.self_item("qwen", cell, 0.8)
        self.assertEqual(item["score"]["gate_S"], 1.0)
        self.assertEqual(item["score"]["loop"], 0.0)       # the vote says B
        self.assertEqual(item["tokens"]["gate_S"], 305)
        self.assertEqual(item["tokens"]["loop"], 605)


class CellBlockTest(unittest.TestCase):
    def test_points_per_thousand_extra_tokens_and_unsure_share(self):
        def item(score_b: float, score_gate: float, sure: bool) -> dict:
            scores = dict.fromkeys(alp.POLICIES, score_b) | {"gate_S": score_gate}
            tokens = dict.fromkeys(alp.POLICIES, 100) | {"gate_S": 600}
            return {**alp.outcome(scores, tokens), "sure": sure}
        block = alp.cell_block([item(0.0, 1.0, False), item(1.0, 1.0, True)])
        self.assertEqual(block["policies"]["gate_S"]["score"], 100.0)
        self.assertEqual(block["policies"]["always_B"]["score"], 50.0)
        self.assertEqual(block["policies"]["gate_S"]["points_per_1k_extra_tokens"], 100.0)
        self.assertIsNone(block["policies"]["loop"]["points_per_1k_extra_tokens"])  # no extra tokens
        self.assertEqual(block["unsure_share"], 50.0)


if __name__ == "__main__":
    unittest.main()
