"""Offline tests for analyze_legal_agent_mechanism's pure pieces (no run outputs needed)."""
from __future__ import annotations

import json
import unittest

try:
    from code_benchmark import analyze_legal_agent_mechanism as m
except ImportError:  # executed from code_benchmark/
    import analyze_legal_agent_mechanism as m  # type: ignore[no-redef]


def attempt(arm: str, stage: str, score: float, baseline: float = 0.5, key: str = "d:1") -> dict:
    return {"arm": arm, "key": key, "score": score, "baseline": baseline,
            "features": {"stage": stage, "article_coverage": 1.0, "miss_reason": None}}


class ShownRanges(unittest.TestCase):
    def test_omp_page_note(self):
        self.assertEqual(m.shown_ranges("omp", "a\nb\n[Showing lines 1-250 of 9000. Use :251 to continue]"),
                         [(1, 250)])

    def test_omp_elided_middle(self):
        content = "x\n[Showing lines 1-120 and 880-1000 of 1000; 759 middle lines (…)]"
        self.assertEqual(m.shown_ranges("omp", content), [(1, 120), (880, 1000)])

    def test_omp_without_note_is_whole_file(self):
        self.assertEqual(m.shown_ranges("omp", "whole small file"), [(1, 10**9)])

    def test_dsh_numbered_lines(self):
        content = "<path>/w/a.txt</path>\n<type>file</type>\n<content>\n40: Điều 5\n41: text\n42: more\n</content>"
        self.assertEqual(m.shown_ranges("dsh", content), [(40, 42)])

    def test_dsh_without_lines(self):
        self.assertIsNone(m.shown_ranges("dsh", "<path>/w/a.txt</path>\n<content>\n</content>"))


class MissReason(unittest.TestCase):
    def test_reasons(self):
        self.assertEqual(m.miss_reason([(1, 100), (900, 1000)], [500]), "elided_middle")
        self.assertEqual(m.miss_reason([(1, 100)], [500]), "after_shown")
        self.assertEqual(m.miss_reason([(600, 700)], [500]), "before_shown")
        self.assertEqual(m.miss_reason(None, [500]), "unknown")
        self.assertEqual(m.miss_reason([(1, 100)], []), "unknown")


class ArticleCoverage(unittest.TestCase):
    LINES = ["Điều 1. A", "1. x", "2. y", "Điều 2. B", "1. z"]

    def test_span_stops_before_next_article(self):
        self.assertEqual(m.article_span(self.LINES, 1), (1, 3))
        self.assertEqual(m.article_span(self.LINES, 4), (4, 5))

    def test_coverage(self):
        self.assertEqual(m.coverage((1, 3), [(1, 3)]), 1.0)
        self.assertAlmostEqual(m.coverage((1, 3), [(1, 1)]), 1 / 3)
        self.assertEqual(m.coverage((1, 3), []), 0.0)


class Oaxaca(unittest.TestCase):
    def test_parts_add_up_to_the_gap(self):
        rows = [attempt("L", "read", 1.0), attempt("L", "read", 1.0), attempt("L", "not_found", 0.0),
                attempt("R", "read", 1.0), attempt("R", "not_found", 0.0), attempt("R", "not_found", 1.0)]
        d = m.oaxaca(rows, "L", "R")
        self.assertAlmostEqual(d["gap"], 100 * (2 / 3 - 2 / 3))
        self.assertAlmostEqual(d["rate_part"] + d["within_part"], d["gap"])

    def test_pure_rate_difference(self):
        rows = [attempt("L", "read", 1.0), attempt("L", "read", 1.0),
                attempt("R", "read", 1.0), attempt("R", "not_found", 0.0)]
        d = m.oaxaca(rows, "L", "R")
        self.assertAlmostEqual(d["gap"], 50.0)
        self.assertAlmostEqual(d["rate_part"], 50.0)
        self.assertAlmostEqual(d["within_part"], 0.0)

    def test_adjusted_uses_lift(self):
        rows = [attempt("L", "read", 1.0, baseline=1.0), attempt("R", "read", 1.0, baseline=0.0)]
        self.assertAlmostEqual(m.oaxaca(rows, "L", "R", adjusted=True)["within_part"], -100.0)

    def test_ci_resamples_items(self):
        rows = [attempt(arm, "read" if arm == "L" else "not_found", 1.0 if arm == "L" else 0.0, key=f"d:{i}")
                for i in range(5) for arm in ("L", "R")]
        d = m.oaxaca_with_ci(rows, "L", "R")
        self.assertEqual(d["n_items"], 5)
        self.assertEqual(d["gap_ci95"], [100.0, 100.0])


class ReadStateChecks(unittest.TestCase):
    def test_final_request_is_the_last_text_answer(self):
        def record(messages, response):
            return {"body_received": json.dumps({"messages": messages}), "response": response}
        records = [record([{"role": "user", "content": "q"}], {"content": "", "tool_calls": [{"id": "1"}]}),
                   record([{"role": "user", "content": "q"}, {"role": "tool", "content": "Điều 5. X"}],
                          {"content": "A", "tool_calls": []}),
                   record([{"role": "user", "content": "handoff"}], {"content": "", "tool_calls": []})]
        self.assertIn("Điều 5. X", m.final_request_text(records))

    def test_version_stem(self):
        self.assertEqual(m.version_stem("bo-luat-hinh-su-1999.txt"), m.version_stem("bo-luat-hinh-su-2015.txt"))
        self.assertNotEqual(m.version_stem("luat-dau-thau-2023.txt"), m.version_stem("luat-dat-dai-2024.txt"))

    def test_sign_test(self):
        self.assertAlmostEqual(m.sign_test_p(11, 1), 2 * 13 / 4096)
        self.assertEqual(m.sign_test_p(0, 0), 1.0)
        self.assertEqual(m.sign_test_p(3, 3), 1.0)


class StatedLetter(unittest.TestCase):
    def test_named_answer_beats_a_letter_inside_the_text(self):
        raw = "Theo Phụ lục C của quy chuẩn ...\n\nDo đó, đáp án đúng là:\n\nA"
        self.assertEqual(m.stated_letter(raw), "A")

    def test_bare_letter(self):
        self.assertEqual(m.stated_letter("**D**"), "D")

    def test_conflicting_signals_give_none(self):
        self.assertIsNone(m.stated_letter("D\n\nGiải thích ...\n\nĐáp án đúng là C"))

    def test_mentioning_an_option_is_not_choosing_it(self):
        self.assertIsNone(m.stated_letter("Đáp án C nêu điều kiện không đúng theo Luật"))


class AnswerFormat(unittest.TestCase):
    def test_bare_and_text(self):
        rows = [dict(attempt("L", "read", 1.0), row={"raw_response": "B"}),
                dict(attempt("L", "read", 0.0), row={"raw_response": "Theo Điều 65 ... Đáp án: A"})]
        f = m.answer_format(rows)
        self.assertEqual(f["bare"]["share_pct"], 50.0)
        self.assertEqual(f["with_text"]["mean_score_points"], 0.0)


if __name__ == "__main__":
    unittest.main()
