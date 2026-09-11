"""Tests for score_reading_eval.py — the EM/char-F1 scorer for the 400-question set.

These defend the parts a plausible bug would break: the number parser (Vietnamese
decimal/thousand separators), the equivalence rule that makes EM meaningful on
free-text gold, and the char-F1 boundary cases. They do NOT re-test csv plumbing.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from code_benchmark.score_reading_eval import (  # noqa: E402
    canonical_variants,
    char_f1,
    normalize_answer,
    score_pair,
    strip_diacritics,
    to_number,
)


def require_num(s: str) -> float:
    """to_number() returns float | None; fail loudly when a test expected a number."""
    v = to_number(s)
    if v is None:
        raise AssertionError(f"expected a number from {s!r}")
    return v


class TestToNumber(unittest.TestCase):
    """Vietnamese writes 1.234,5 where English writes 1,234.5 — both must parse."""

    def num(self, s: str) -> float:
        return require_num(s)

    def test_vietnamese_decimal_comma(self):
        self.assertAlmostEqual(self.num("0,4"), 0.4)

    def test_vietnamese_thousands_dot(self):
        self.assertAlmostEqual(self.num("32.100"), 32100.0)

    def test_english_thousands_comma(self):
        self.assertAlmostEqual(self.num("32,100"), 32100.0)

    def test_mixed_uses_last_separator_as_decimal(self):
        self.assertAlmostEqual(self.num("1.234,5"), 1234.5)
        self.assertAlmostEqual(self.num("1,234.5"), 1234.5)

    def test_percent_sign_ignored(self):
        self.assertAlmostEqual(self.num("24,9%"), 24.9)

    def test_non_numeric_returns_none(self):
        for s in ("nhiều hơn", "ít hơn", "", "abc", "3 quân đoàn"):
            self.assertIsNone(to_number(s), s)

    def test_two_digit_decimal_is_not_thousands(self):
        """'44,10' is 44.1 — a 2-digit group can never be a thousands separator."""
        self.assertAlmostEqual(self.num("44,10"), 44.10)


class TestNormalize(unittest.TestCase):
    def test_casefold_and_whitespace(self):
        self.assertEqual(normalize_answer("  NhIều   Hơn "), "nhiều hơn")

    def test_strips_trailing_punctuation(self):
        self.assertEqual(normalize_answer("477.000 người."), "477.000 người")

    def test_diacritics_removed_only_in_strip_variant(self):
        self.assertEqual(strip_diacritics("nhiều hơn"), "nhieu hon")
        self.assertNotEqual(normalize_answer("nhiều hơn"), "nhieu hon")


class TestCanonicalVariants(unittest.TestCase):
    def test_percent_forms_collapse_to_one_number(self):
        """EM uses set INTERSECTION, so the three spellings must share '30.4'."""
        forms = canonical_variants("30,40%")
        self.assertIn("30.4", forms)
        self.assertTrue(canonical_variants("30.40%") & forms)
        self.assertTrue(canonical_variants("30,4%") & forms)

    def test_leading_zero_stays_decimal(self):
        """Regression: '0.400' is 0.4. A naive 3-digit rule read it as 400."""
        self.assertAlmostEqual(require_num("0.400"), 0.4)
        self.assertAlmostEqual(require_num("0,400"), 0.4)
        self.assertFalse(canonical_variants("0.400") & canonical_variants("400"))

    def test_equal_numbers_with_different_grouping_match(self):
        self.assertTrue(canonical_variants("32.100") & canonical_variants("32100"))

    def test_different_numbers_do_not_match(self):
        self.assertFalse(canonical_variants("32.100") & canonical_variants("32.200"))

    def test_diacritic_variant_present(self):
        self.assertTrue(canonical_variants("nhiều hơn") & canonical_variants("nhieu hon"))


class TestCharF1(unittest.TestCase):
    def test_identical_is_one(self):
        self.assertAlmostEqual(char_f1("473", "473"), 1.0)

    def test_empty_both_is_one(self):
        self.assertAlmostEqual(char_f1("", ""), 1.0)

    def test_empty_one_side_is_zero(self):
        self.assertAlmostEqual(char_f1("", "473"), 0.0)
        self.assertAlmostEqual(char_f1("473", ""), 0.0)

    def test_partial_overlap_between_zero_and_one(self):
        v = char_f1("32.200", "32.100")
        self.assertGreater(v, 0.0)
        self.assertLess(v, 1.0)

    def test_disjoint_is_zero(self):
        self.assertAlmostEqual(char_f1("abc", "xyz"), 0.0)


class TestScorePair(unittest.TestCase):
    def test_exact_match_true_on_identical(self):
        _, _, em, exact_raw = score_pair("473", "473")
        self.assertTrue(em)
        self.assertTrue(exact_raw)

    def test_exact_raw_catches_whitespace_only_difference(self):
        """A space-padded answer is still 'verbatim' after normalisation — this is
        why exact_raw equals the accepted count (321) rather than a smaller number."""
        _, _, em, exact_raw = score_pair("  473 ", "473")
        self.assertTrue(em)
        self.assertTrue(exact_raw)

    def test_numeric_equivalence_gives_em_without_exact_raw(self):
        _, _, em, exact_raw = score_pair("30.40%", "30,4%")
        self.assertTrue(em)
        self.assertFalse(exact_raw)

    def test_flipped_comparison_is_not_em_but_has_f1(self):
        """'ít hơn' vs 'nhiều hơn' — the trap char-F1 alone would hide."""
        _, f1, em, _ = score_pair("ít hơn", "nhiều hơn")
        self.assertFalse(em)
        self.assertGreater(f1, 0.5)

    def test_blank_prediction_scores_zero(self):
        _, f1, em, _ = score_pair("", "477.000 người")
        self.assertFalse(em)
        self.assertAlmostEqual(f1, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
