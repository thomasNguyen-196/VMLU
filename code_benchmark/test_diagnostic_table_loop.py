"""Offline tests of the table-loop items, manifests and loop rules (card MC-105). No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_diagnostic_table_loop
"""
from __future__ import annotations

import itertools
import random
import unittest

from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_self_loop as sl
from code_benchmark import diagnostic_table_loop as tl
from code_benchmark import vi_multimodel as v1

HAS_MANIFESTS = all(tl.manifest_path(student).is_file() for student in tl.STUDENTS)


def mc(b1: str, b2: str, s: list[str]) -> dict[str, str]:
    return {"B-r1": b1, "B-r2": b2, "S-r1": s[0], "S-r2": s[1], "S-r3": s[2]}


class TestLoop(unittest.TestCase):
    def test_multiple_choice_repeats_the_mc104_rules(self):
        rng = random.Random(5)
        letters = ["A", "B", "C", ""]
        for _ in range(2000):
            b1, b2, *s = (rng.choice(letters) for _ in range(5))
            confidence = rng.choice([None, 0.5, 0.79, 0.8, 0.95])
            replicate, rounds = tl.choose("multiple_choice", "qwen", mc(b1, b2, s), confidence, 0.8)
            self.assertEqual((mc(b1, b2, s)[replicate], rounds), sl.loop_qwen(b1, confidence, s, 0.8))
            replicate, rounds = tl.choose("multiple_choice", "mimo", mc(b1, b2, s), None, 0.8)
            self.assertEqual((mc(b1, b2, s)[replicate], rounds), sl.loop_mimo(b1, b2, s))

    def test_reading_uses_the_two_b_answers_and_the_exact_match_normalization(self):
        def choose(b1, b2, s):
            return tl.choose("reading", "qwen", mc(b1, b2, s), 0.99, 0.8)
        self.assertEqual(choose("Hà Nội", "hà nội.", ["x", "y", "z"]), ("B-r1", 1))  # the probe is ignored
        self.assertEqual(choose("Hà Nội", "Huế", ["  huế ", "x", "y"]), ("S-r1", 2))
        self.assertEqual(choose("Hà Nội", "Huế", ["Đà Nẵng", "Vinh", "vinh"]), ("S-r2", 3))
        self.assertEqual(choose("", "", ["", "", ""]), ("S-r1", 3))  # empty answers never agree
        self.assertEqual(choose("a", "b", ["c", "", "d"]), ("S-r1", 3))  # a tie goes to the earliest

    def test_the_vote_ignores_empty_answers(self):
        self.assertEqual(tl.vote(mc("", "", ["", "B", "B"]), "multiple_choice"), "S-r2")
        for s in itertools.product(["A", "B", ""], repeat=3):
            self.assertEqual(mc("", "", list(s))[tl.vote(mc("", "", list(s)), "multiple_choice")], sl.majority(list(s)))


class TestConfig(unittest.TestCase):
    def test_the_threshold_is_mc104s_and_the_families_cover_the_six_datasets(self):
        config, _ = tl.load_config()
        self.assertEqual(config["loop"]["multiple_choice"]["threshold"], sl.load_config()[0]["loop"]["qwen"]["threshold"])
        families = config["items"]["families"]
        self.assertEqual(sorted(families["multiple_choice"] + families["reading"]), sorted(config["items"]["datasets"]))
        self.assertEqual(sum(config["items"]["datasets"].values()), 2043)


@unittest.skipUnless(HAS_MANIFESTS, "needs the frozen table-loop manifests")
class TestManifests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = {student: tl.build_manifest(student) for student in tl.STUDENTS}

    def test_the_frozen_manifests_rebuild_byte_for_byte(self):
        for student, (manifest, _) in self.built.items():
            self.assertEqual(manifest, tl.load_frozen_manifest(student))

    def test_counts_and_overlap(self):
        qwen, mimo = self.built["qwen"][0], self.built["mimo"][0]
        self.assertEqual((qwen["item_count"], qwen["n"], mimo["n"]), (2043, 9175, 10215))
        self.assertEqual(qwen["seen_in_router_cards"]["vi-multimodel-v1-vmlu-valid"], 660)

    def test_every_b_prompt_is_the_table_prompt_and_every_s_prompt_the_campaign_template(self):
        frozen = {dp.item_key(row["dataset_id"], row["item_id"]): row for row in v1.load_manifest("main")["items"]}
        templates = dp.load_templates()
        for student, (manifest, rebuilt) in self.built.items():
            for ref in manifest["items"]:
                main = frozen[dp.item_key(ref["dataset_id"], ref["item_id"])]
                arm = dp.arm_of_replicate(ref["replicate_id"])
                prompt = rebuilt[dp.run_key(ref)].prompt
                if arm == "B":
                    self.assertEqual(ref["prompt_sha256"], main["prompt_sha256"], (student, ref["item_id"]))
                else:
                    head = templates["s_mc_head" if ref["task"] == "multiple_choice" else "s_reading_head"]
                    self.assertTrue(prompt.startswith(head))

    def test_the_students_differ_only_by_mimos_second_multiple_choice_b(self):
        def keys(student):
            return {dp.run_key(ref) for ref in self.built[student][0]["items"]}
        extra = keys("mimo") - keys("qwen")
        self.assertEqual(keys("qwen") - keys("mimo"), set())
        self.assertEqual(len(extra), 744 + 146 + 150)
        self.assertTrue(all(key.endswith(":B-r2") for key in extra))


if __name__ == "__main__":
    unittest.main()
