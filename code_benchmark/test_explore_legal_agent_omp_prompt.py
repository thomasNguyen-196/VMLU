"""Offline tests of the exploratory MC reading in explore_legal_agent_omp_prompt.

    .venv/bin/python -m unittest code_benchmark.test_explore_legal_agent_omp_prompt
"""
from __future__ import annotations

import unittest

from code_benchmark import explore_legal_agent_omp_prompt as e


class TestStatedLetter(unittest.TestCase):
    def test_letter_on_the_last_line(self):
        self.assertEqual(e.stated_letter("Điều 92 ... loại A, loại B.\n\nC", "A"), "C")
        self.assertEqual(e.stated_letter("Giải thích dài.\n\n**B**", "A"), "B")

    def test_stated_phrase(self):
        self.assertEqual(e.stated_letter("Loại C vì ... Vì vậy đáp án đúng là **A**.", "C"), "A")
        self.assertEqual(e.stated_letter("Đáp án: D\nVì cả A, B, C đều đúng.", "A"), "D")

    def test_falls_back_to_the_frozen_letter(self):
        self.assertEqual(e.stated_letter("A\n\nCăn cứ: Điều 91 ...", "A"), "A")
        self.assertEqual(e.stated_letter("", ""), "")


class TestLoneLetter(unittest.TestCase):
    def test_only_a_letter_counts(self):
        for raw in ("B", "**B**", "B.", "(B)", " C \n"):
            self.assertIsNotNone(e.lone_letter(raw), raw)
        for raw in ("B. Vì Điều 5 quy định", "Đáp án: B", "", "AB", "F"):
            self.assertIsNone(e.lone_letter(raw), raw)


if __name__ == "__main__":
    unittest.main()
