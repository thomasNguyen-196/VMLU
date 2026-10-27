"""Offline tests for the blind semantic review of the MC-90 reading discordance (no data, no network).

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_diagnostic_semantic_review
Expected values are worked out by hand in the comments.
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace as N

from code_benchmark import diagnostic_semantic_review as sr


def rec(i, dataset="bidlqa", b_em=False, s_em=False, b_f1=0.0, s_f1=0.0):
    return {"item_key": f"ds-{dataset}:{i:03d}", "dataset": dataset, "question": f"question {i}", "gold": f"reference {i}",
            "b_em": b_em, "s_em": s_em, "b_f1": b_f1, "s_f1": s_f1, "b_pred": f"alpha {i}", "s_pred": f"beta {i}"}


def population():
    """5 both-exact, 4 rescues, 3 regressions, 10 + 3 both-inexact with a close answer (bidlqa / drop), 6 far apart."""
    records = [rec(i, b_em=True, s_em=True) for i in range(5)]
    records += [rec(10 + i, s_em=True) for i in range(4)]
    records += [rec(20 + i, b_em=True) for i in range(3)]
    records += [rec(30 + i, b_f1=0.6) for i in range(10)]
    records += [rec(50 + i, dataset="drop", s_f1=0.9) for i in range(3)]
    records += [rec(60 + i, b_f1=0.2, s_f1=0.1) for i in range(6)]
    return records


class TestStratification(unittest.TestCase):
    def test_strata_follow_exact_match_and_token_f1(self):
        cases = [(rec(1, b_em=True, s_em=True), "C"), (rec(2, s_em=True), "R"), (rec(3, b_em=True), "G"),
                 (rec(4, b_f1=0.5), "W_hi:bidlqa"), (rec(5, dataset="squad", s_f1=0.7), "W_hi:squad"),
                 (rec(6, b_f1=0.49, s_f1=0.2), "W_lo")]
        for record, stratum in cases:
            self.assertEqual(sr.stratum_of(record), stratum, record["item_key"])

    def test_whole_strata_and_a_seeded_sample(self):
        strata = {}
        for record in population():
            strata.setdefault(sr.stratum_of(record), []).append(record)
        sizes = {"W_hi:bidlqa": 5, "W_lo": 3}
        chosen = sr.choose(strata, 42, sizes)
        self.assertNotIn("C", chosen)  # both exact: assumed correct, never reviewed
        self.assertEqual({name: len(members) for name, members in chosen.items()},
                         {"G": 3, "R": 4, "W_hi:bidlqa": 5, "W_hi:drop": 3, "W_lo": 3})
        keys = {m["item_key"] for m in strata["W_hi:bidlqa"]}
        self.assertTrue({m["item_key"] for m in chosen["W_hi:bidlqa"]} <= keys)
        self.assertEqual(chosen, sr.choose(strata, 42, sizes))  # deterministic
        self.assertNotEqual([m["item_key"] for m in chosen["W_hi:bidlqa"]],
                            [m["item_key"] for m in sr.choose(strata, 7, sizes)["W_hi:bidlqa"]])

    def test_reading_records_use_the_first_draws_only(self):
        item = N(question="question text", gold_answer="gold text")

        def row(arm, replicate, em, prediction):
            return {"arm": arm, "dataset_id": "vi-multimodel-v1-vi-squad-200", "item_id": "9", "replicate_id": f"{arm}-r{replicate}",
                    "em": em, "token_f1": 1.0 if em else 0.3, "prediction": prediction, "gold_answer": "gold text"}

        rows = [row("B", 1, 0, "first"), row("S", 1, 1, "stepwise"), row("B", 2, 1, "second draw"),
                {"arm": "B", "dataset_id": "vi-multimodel-v1-legal-mc-146", "item_id": "x", "replicate_id": "B-r1", "correct": 1}]
        records = sr.reading_records(rows, {"vi-multimodel-v1-vi-squad-200:9:main-000": item})
        self.assertEqual(len(records), 1)  # the multiple-choice row and the second B draw are ignored
        self.assertEqual((records[0]["b_pred"], records[0]["s_pred"], records[0]["dataset"]), ("first", "stepwise", "squad"))
        self.assertEqual(sr.stratum_of(records[0]), "R")


class TestPacket(unittest.TestCase):
    def build(self, seed=42):
        return sr.build_packet(population(), seed=seed, sizes={"W_hi:bidlqa": 5, "W_lo": 3})

    def test_units_are_blind_complete_and_shuffled(self):
        units, key, design = self.build()
        # R 4 + G 3 units, and 5 + 3 + 3 both-inexact items with two answers each
        self.assertEqual(len(units), 4 + 3 + 2 * (5 + 3 + 3))
        self.assertEqual(design["units"], len(units))
        self.assertEqual(design["population"], {"C": 5, "G": 3, "R": 4, "W_hi:bidlqa": 10, "W_hi:drop": 3, "W_lo": 6})
        for unit in units:
            self.assertEqual(set(unit), set(sr.PACKET_FIELDS))  # no arm, direction or stratum field
        blob = json.dumps(units)
        for leak in ("rescue", "regression", "W_hi", "W_lo", '"arm"', '"stratum"'):
            self.assertNotIn(leak, blob)
        self.assertEqual([k["unit_id"] for k in key], [u["unit_id"] for u in units])
        by_stratum = [k["stratum"] for k in key]
        self.assertNotEqual(by_stratum, sorted(by_stratum))  # the order carries no stratum information
        self.assertEqual(self.build(), (units, key, design))  # same seed, same packet
        self.assertNotEqual(self.build(seed=7)[0], units)

    def test_the_heldout_packet_reviews_only_the_exact_match_discordance(self):
        records = population()
        units, key, design = sr.build_packet(records, sizes=sr.heldout_sizes(records))
        # MC-94: the 4 rescues (B answer reviewed) and 3 regressions (S answer reviewed); nothing both-inexact
        self.assertEqual(Counter((k["stratum"], k["arm"]) for k in key), {("R", "B"): 4, ("G", "S"): 3})
        self.assertEqual(len(units), 7)
        self.assertEqual(design["population"], {"C": 5, "G": 3, "R": 4, "W_hi:bidlqa": 10, "W_hi:drop": 3, "W_lo": 6})
        self.assertEqual(design["sampled"], {"G": 3, "R": 4, "W_hi:bidlqa": 0, "W_hi:drop": 0, "W_lo": 0})

    def test_the_exact_answer_of_a_discordant_item_is_not_shown(self):
        units, key, _ = self.build()
        shown = {k["unit_id"]: (k["arm"], u["candidate_answer"]) for k, u in zip(key, units, strict=True)}
        for k in key:
            arm, text = shown[k["unit_id"]]
            if k["stratum"] == "R":
                self.assertEqual(arm, "B")  # the B answer (the inexact one) of a rescue is reviewed
                self.assertTrue(text.startswith("alpha"))
            if k["stratum"] == "G":
                self.assertEqual(arm, "S")
                self.assertTrue(text.startswith("beta"))

    def test_long_candidates_are_cut(self):
        text = sr.candidate_text("word " * 400)
        self.assertLessEqual(len(text), sr.CANDIDATE_CHARS + 2)
        self.assertTrue(text.endswith("…"))
        self.assertEqual(sr.candidate_text("  a   b\n c "), "a b c")


def estimation_fixture():
    """Hand-worked design: 33 reading items. R and G are censuses; W_hi:bidlqa samples 5 of 10, W_lo 3 of 6.
    Labels as (B, S) for the both-inexact items; one label for R (the B answer) and for G (the S answer)."""
    design = {"population": {"C": 10, "R": 4, "G": 3, "W_hi:bidlqa": 10, "W_lo": 6}, "reading_items": 33}
    key, labels = [], {}

    def add(item, arm, stratum, label):
        unit = f"U{len(key) + 1:04d}"
        key.append({"unit_id": unit, "item_key": item, "arm": arm, "stratum": stratum})
        labels[unit] = label

    for item, label in zip("r1 r2 r3 r4".split(), ("correct", "incorrect", "incorrect", "partial"), strict=True):
        add(item, "B", "R", label)
    for item, label in zip("g1 g2 g3".split(), ("correct", "incorrect", "partial"), strict=True):
        add(item, "S", "G", label)
    both = {"W_hi:bidlqa": [("correct", "correct"), ("incorrect", "correct"), ("correct", "incorrect"),
                            ("incorrect", "incorrect"), ("incorrect", "incorrect")],
            "W_lo": [("incorrect", "incorrect"), ("incorrect", "incorrect"), ("incorrect", "correct")]}
    for stratum, pairs in both.items():
        for index, (b_label, s_label) in enumerate(pairs):
            add(f"{stratum}-{index}", "B", stratum, b_label)
            add(f"{stratum}-{index}", "S", stratum, s_label)
    return design, key, labels


class TestEstimation(unittest.TestCase):
    def test_strict_estimate_matches_the_hand_worked_example(self):
        design, key, labels = estimation_fixture()
        e = sr.estimate(design, key, labels, strict=True)
        # R: B wrong on r2, r3, r4 -> 3 semantic rescues. G: S wrong on g2, g3 -> 2 regressions.
        # W_hi: 10 x (1/5) = 2 rescues and 2 regressions; W_lo: 6 x (1/3) = 2 rescues and none
        self.assertAlmostEqual(e["rescues"]["estimate"], 3 + 2 + 2)
        self.assertAlmostEqual(e["regressions"]["estimate"], 2 + 2 + 0)
        self.assertAlmostEqual(e["net"]["estimate"], 3)
        # only the sampled strata vary: W_hi d = (0, +1, -1, 0, 0) -> s2 = 0.5, var = 10^2 x (1 - 5/10) x 0.5 / 5 = 5
        # W_lo d = (0, 0, +1) -> s2 = 1/3, var = 6^2 x (1 - 3/6) x (1/3) / 3 = 2
        self.assertAlmostEqual(e["net"]["se"], math.sqrt(7))
        self.assertAlmostEqual(e["net_points"]["estimate"], 100 * 3 / 33)
        # B right: 10 (both exact) + 3 (G, B exact) + r1 + W_hi 10 x 2/5 + W_lo 0 = 18; S right: 10 + 4 (R) + g1 + 4 + 2 = 21
        self.assertAlmostEqual(e["semantic_accuracy"]["b"], 18 / 33)
        self.assertAlmostEqual(e["semantic_accuracy"]["s"], 21 / 33)
        self.assertEqual(e["em_reference"], {"rescues": 4, "regressions": 3, "net": 1})

    def test_lenient_estimate_counts_partial_as_right(self):
        design, key, labels = estimation_fixture()
        e = sr.estimate(design, key, labels, strict=False)
        # r4 and g3 are partial: R rescues 2 (r2, r3), G regressions 1 (g2); the sampled strata are unchanged
        self.assertAlmostEqual(e["rescues"]["estimate"], 2 + 2 + 2)
        self.assertAlmostEqual(e["regressions"]["estimate"], 1 + 2 + 0)
        self.assertAlmostEqual(e["net"]["estimate"], 3)
        self.assertAlmostEqual(e["semantic_accuracy"]["b"], 19 / 33)
        self.assertAlmostEqual(e["semantic_accuracy"]["s"], 22 / 33)

    def test_censuses_add_no_sampling_variance(self):
        design, key, labels = estimation_fixture()
        census_only = [k for k in key if k["stratum"] in ("R", "G")]
        design = {**design, "population": {"C": 10, "R": 4, "G": 3}, "reading_items": 17}
        e = sr.estimate(design, census_only, labels, strict=True)
        self.assertEqual(e["net"]["se"], 0.0)
        self.assertAlmostEqual(e["net"]["estimate"], 3 - 2)


class TestAgreementAndConsensus(unittest.TestCase):
    def test_kappa_on_a_worked_example(self):
        a = ["correct", "correct", "partial", "incorrect", "incorrect", "correct"]
        b = ["correct", "partial", "partial", "incorrect", "correct", "correct"]
        # observed 4/6; expected 0.5 x 0.5 + (1/6)(1/3) + (1/3)(1/6) = 0.36111; kappa = (0.66667 - 0.36111) / 0.63889
        self.assertAlmostEqual(sr.cohen_kappa(a, b), 0.478261, places=5)
        self.assertEqual(sr.cohen_kappa(["a"] * 3, ["a"] * 3), None)  # no variation: kappa undefined

    def test_agreement_summary(self):
        key = [{"unit_id": f"U{i}", "item_key": str(i), "arm": "B", "stratum": "R"} for i in range(4)]
        first = {"U0": "correct", "U1": "partial", "U2": "incorrect", "U3": "correct"}
        second = {"U0": "correct", "U1": "incorrect", "U2": "incorrect", "U3": "partial"}
        result = sr.agreement(first, second, key)
        self.assertEqual((result["units"], result["disagreements"], result["raw_agreement"]), (4, 2, 0.5))
        # strict (correct versus not): U0 both correct, U1 and U2 both not, U3 correct versus not -> 3 of 4
        self.assertEqual(result["raw_agreement_strict"], 0.75)

    def test_a_disagreement_needs_a_blind_adjudication(self):
        key = [{"unit_id": "U0", "item_key": "x", "arm": "B", "stratum": "R"},
               {"unit_id": "U1", "item_key": "y", "arm": "B", "stratum": "R"}]
        first, second = {"U0": "correct", "U1": "correct"}, {"U0": "correct", "U1": "incorrect"}
        with self.assertRaises(SystemExit):
            sr.consensus(first, second, {}, key)
        self.assertEqual(sr.consensus(first, second, {"U1": "partial"}, key), {"U0": "correct", "U1": "partial"})
        with self.assertRaises(SystemExit):  # a unit one reviewer skipped
            sr.consensus({"U0": "correct"}, second, {}, key)

    def test_label_files_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.jsonl"
            good = json.dumps({"unit_id": "U1", "label": "correct", "reason": "same"})
            path.write_text(good + "\n", encoding="utf-8")
            self.assertEqual(sr.read_labels(path, {"U1"}), {"U1": "correct"})
            for bad in ({"unit_id": "U9", "label": "correct"}, {"unit_id": "U1", "label": "maybe"}):
                path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
                with self.assertRaises(SystemExit):
                    sr.read_labels(path, {"U1"})
            path.write_text(good + "\n" + good + "\n", encoding="utf-8")  # a duplicate unit
            with self.assertRaises(SystemExit):
                sr.read_labels(path, {"U1"})


class TestRoundTrip(unittest.TestCase):
    def test_aggregate_reads_the_packet_files_labels_and_an_adjudication(self):
        units, key, design = sr.build_packet(population(), seed=42, sizes={"W_hi:bidlqa": 5, "W_lo": 3})
        text = {u["unit_id"]: u["candidate_answer"] for u in units}

        def label(unit):
            return "correct" if text[unit].startswith("beta") else "incorrect"

        first = {k["unit_id"]: label(k["unit_id"]) for k in key}
        second = dict(first)
        flipped = [key[0]["unit_id"], key[1]["unit_id"], key[2]["unit_id"]]
        for unit in flipped:
            second[unit] = "partial"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "design.json").write_text(json.dumps(design), encoding="utf-8")
            (out / "key.json").write_text(json.dumps(key), encoding="utf-8")
            files = []
            for name, labels in (("a.jsonl", first), ("b.jsonl", second)):
                (out / name).write_text("".join(json.dumps({"unit_id": u, "label": v, "reason": "x"}) + "\n" for u, v in labels.items()),
                                        encoding="utf-8")
                files.append(out / name)
            with self.assertRaises(SystemExit):
                sr.aggregate(out, files, None)
            (out / "c.jsonl").write_text("".join(json.dumps({"unit_id": u, "label": first[u], "reason": "x"}) + "\n" for u in flipped),
                                         encoding="utf-8")
            report = sr.aggregate(out, files, out / "c.jsonl")
        self.assertTrue(report["ai_assisted_not_human"])
        self.assertEqual(report["agreement"]["disagreements"], 3)
        self.assertEqual(report["design"]["units"], len(units))
        for mode in ("strict", "lenient"):
            self.assertEqual(report["estimates"][mode]["em_reference"], {"rescues": 4, "regressions": 3, "net": 1})
        self.assertIn("not a blind human review", sr.format_report(report))


if __name__ == "__main__":
    unittest.main()
