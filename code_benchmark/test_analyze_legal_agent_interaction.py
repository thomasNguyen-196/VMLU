"""Offline tests of the exploratory model x harness interaction analysis (synthetic attempts, no run outputs).

    .venv/bin/python -m unittest code_benchmark.test_analyze_legal_agent_interaction
"""
from __future__ import annotations

import random
import unittest

from code_benchmark import analyze_legal_agent_interaction as ai
from code_benchmark import analyze_legal_agent_mechanism as mech


def attempt(model: str, arm: str, key: str, score: float, stage: str | None = "read", baseline: float = 0.5,
            terminal: bool = False) -> dict:
    return {"model": model, "arm": arm, "key": key, "score": score, "baseline": baseline, "terminal": terminal,
            "features": {"stage": stage}}


def synthetic(seed: int = 3, items: int = 40) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(items):
        for model in ai.MODELS:
            for arm in ai.ARMS:
                for _ in ai.DRAWS:
                    stage = "read" if rng.random() < (0.7 if arm == "DSHF" else 0.4) else "not_found"
                    rows.append(attempt(model, arm, f"d:{i}", float(rng.random() < 0.6), stage, rng.random()))
    return rows


class TestInteraction(unittest.TestCase):
    def test_split_from_sums_equals_the_mechanism_split(self):
        rows = synthetic()
        for adjusted in (False, True):
            sums = ai._sums(rows, adjusted)  # noqa: SLF001
            for model in ai.MODELS:
                mine = [a for a in rows if a["model"] == model]
                expected = mech.oaxaca(mine, "OMPF", "DSHF", adjusted)
                got = ai.oaxaca_from_sums(sums, model)
                for name in ("gap", "rate_part", "within_part"):
                    self.assertAlmostEqual(got[name], expected[name], places=9)

    def test_split_parts_add_up_for_the_interaction(self):
        d = ai.decomposition(synthetic())
        inter = d["interaction"]
        self.assertAlmostEqual(inter["gap"], round(inter["rate_part"] + inter["within_part"], 2), delta=0.011)
        self.assertAlmostEqual(inter["gap"], round(d["mimo"]["gap"] - d["qwen"]["gap"], 2), delta=0.011)

    def test_interaction_is_the_difference_of_item_gaps(self):
        rows = [attempt("mimo", "OMPF", "a", 1.0), attempt("mimo", "OMPF", "a", 1.0),
                attempt("mimo", "DSHF", "a", 0.0), attempt("mimo", "DSHF", "a", 1.0),
                attempt("qwen", "OMPF", "a", 0.0), attempt("qwen", "OMPF", "a", 0.0),
                attempt("qwen", "DSHF", "a", 1.0), attempt("qwen", "DSHF", "a", 1.0)]
        result = ai.interaction(rows)
        self.assertEqual(result["items"], 1)
        self.assertEqual(result["mimo_gap_points"], 50.0)
        self.assertEqual(result["qwen_gap_points"], -100.0)
        self.assertEqual(result["interaction_points"], 150.0)

    def test_dropping_terminal_attempts_uses_the_draws_left(self):
        rows = [attempt("mimo", "OMPF", "a", 1.0), attempt("mimo", "DSHF", "a", 0.0, terminal=True),
                attempt("mimo", "DSHF", "a", 1.0), attempt("qwen", "OMPF", "a", 1.0), attempt("qwen", "DSHF", "a", 1.0),
                attempt("mimo", "OMPF", "b", 1.0), attempt("mimo", "DSHF", "b", 0.0, terminal=True),
                attempt("qwen", "OMPF", "b", 1.0), attempt("qwen", "DSHF", "b", 1.0)]
        self.assertEqual(ai.interaction(rows)["interaction_points"], 75.0)
        kept = ai.interaction(rows, drop_terminal=True)
        self.assertEqual(kept["items"], 1)  # item b has no DSHF draw left for MiMo
        self.assertEqual(kept["interaction_points"], 0.0)

    def test_unclean_text(self):
        import unicodedata
        word = "thầu"
        self.assertFalse(ai.unclean_text(word))
        self.assertTrue(ai.unclean_text(unicodedata.normalize("NFD", word)))
        self.assertTrue(ai.unclean_text("lạ̀m"))  # a second tone mark on a toned vowel
        self.assertFalse(ai.unclean_text("Điều 4"))

    def test_reading_rules(self):
        decomp = {"interaction": {"rate_part_ci95": [1.0, 9.0], "rate_part_share_pct": 60.0,
                                  "within_part_ci95": [-3.0, 6.0], "within_part_share_pct": 40.0}}
        whole, kept = {"interaction_points": 10.0}, {"interaction_points": 8.0}
        self.assertEqual(len(ai.readings(decomp, whole, kept)), 1)
        self.assertIn("reaching and reading", ai.readings(decomp, whole, kept)[0])
        kept = {"interaction_points": 4.0}
        self.assertEqual(len(ai.readings(decomp, whole, kept)), 2)
        decomp["interaction"]["rate_part_ci95"] = [-1.0, 9.0]
        self.assertEqual(ai.readings(decomp, whole, {"interaction_points": 9.0}), ["not determined"])


if __name__ == "__main__":
    unittest.main()
