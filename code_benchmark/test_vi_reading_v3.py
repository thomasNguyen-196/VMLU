"""Offline tests of the reading scorer vi-reading-v3 and its post-hoc re-scoring (openspec change diagnostic-router-loop,
decision 10). No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_vi_reading_v3
"""
from __future__ import annotations

import unittest

from code_benchmark import analyze_reading_v3 as ar3
from code_benchmark import vi_multimodel as v1
from code_benchmark import vi_reading_v3 as v3

GOLD = "từ 20% đến 30%"


def v2(raw: str, gold: str) -> dict:
    prediction = v1.extract_final_answer(raw)
    return {"prediction": prediction, **v1.score_vi_reading(prediction, gold)}


def reading_row(raw: str, gold: str = GOLD, **extra) -> dict:
    return {"dataset_id": "d", "item_id": "1", "replicate_id": "B-r1", "gold_answer": gold, "raw_response": raw,
            **{key: value for key, value in v2(raw, gold).items()}, **extra}


class TestScorer(unittest.TestCase):
    def test_a_bolded_answer_scores_like_the_plain_one(self):
        self.assertLess(v2(f"**{GOLD}**", GOLD)["token_f1"], 1.0)
        scored = v3.score_reading(f"**{GOLD}**", GOLD)
        self.assertEqual((scored["prediction"], scored["em"], scored["token_f1"]), (GOLD, 1, 1.0))
        self.assertEqual(v3.score_reading(f"`{GOLD}`", GOLD)["em"], 1)

    def test_a_bolded_label_before_a_line_break_keeps_the_answer(self):
        raw = f"**Trả lời:**\n\n{GOLD}"
        self.assertEqual(v2(raw, GOLD)["prediction"], "**")
        self.assertEqual(v3.score_reading(raw, GOLD)["prediction"], GOLD)

    def test_text_without_marks_scores_exactly_as_v2(self):
        for raw in (GOLD, "Trả lời: 25%.", "Đáp án: (B) Hà Nội", "khoảng 1.200 người, theo đoạn văn", "", "Answer: 7"):
            for gold in (GOLD, "25%", "Hà Nội", "7"):
                self.assertEqual(v3.score_reading(raw, gold), v2(raw, gold))

    def test_rescore_row(self):
        mc = {"correct": 1, "prediction": "B", "raw_response": "**B**"}
        self.assertEqual(v3.rescore_row(mc), mc)
        row = reading_row("**Trả lời:** sai", scoring_response=f"**{GOLD}**", arm="S")
        new = v3.rescore_row(row)
        self.assertEqual((new["em"], new["token_f1"], new["scorer_version"], new["arm"]), (1, 1.0, "vi-reading-v3", "S"))
        self.assertEqual((row["raw_response"], new["raw_response"]), ("**Trả lời:** sai", "**Trả lời:** sai"))


class TestRescoring(unittest.TestCase):
    def test_check_v2_fails_closed_on_a_score_that_is_not_v2(self):
        rows = [reading_row(f"**{GOLD}**"), {"correct": 0, "prediction": "A"}]
        ar3.check_v2(rows, "test")
        rows[0] = {**rows[0], "em": 1}
        with self.assertRaises(SystemExit):
            ar3.check_v2(rows, "test")

    def test_summarize_counts_marked_and_changed_answers(self):
        rows = [reading_row(f"**{GOLD}**"), reading_row(GOLD), reading_row("**30%**", gold="30%")]
        block = ar3.summarize(rows)
        self.assertEqual((block["n"], block["marked"], block["changed"]), (3, 2, 2))
        self.assertEqual((block["token_f1"]["v3"], block["em"]["v2"], block["em"]["v3"]), (100.0, 33.33, 100.0))


if __name__ == "__main__":
    unittest.main()
