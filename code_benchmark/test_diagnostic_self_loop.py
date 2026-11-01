"""Offline tests of the self-improvement loop (openspec change diagnostic-router-loop, decision 11; card MC-104).
No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_diagnostic_self_loop
"""
from __future__ import annotations

import csv
import json
import unittest
from collections import Counter

from code_benchmark import diagnostic_heldout_v3 as h3
from code_benchmark import diagnostic_k2 as k2
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_self_loop as sl

CONFIG, _ = sl.load_config()
HAS_SOURCES = all(path.is_file() for path in h3.PINNED) and (dp.ROOT / "vmlu_mqa_v1.5" / "dev.jsonl").is_file()
DESIGN = list(CONFIG["threshold_rule"]["inputs_sha256"])
HAS_DESIGN = all((dp.ROOT / path).is_file() for path in DESIGN)


class TestLoop(unittest.TestCase):
    def test_majority_breaks_ties_toward_the_first_answer_and_ignores_empty_ones(self):
        self.assertEqual(sl.majority(["A", "B", "B"]), "B")
        self.assertEqual(sl.majority(["A", "B", "C"]), "A")
        self.assertEqual(sl.majority(["", "C", "C"]), "C")
        self.assertEqual(sl.majority(["", "", ""]), "")

    def test_qwen_keeps_a_confident_answer_and_votes_only_after_a_disagreement(self):
        self.assertEqual(sl.loop_qwen("A", 0.9, ["B", "B", "B"], 0.8), ("A", 1))
        self.assertEqual(sl.loop_qwen("A", 0.5, ["A", "C", "C"], 0.8), ("A", 2))
        self.assertEqual(sl.loop_qwen("A", 0.5, ["B", "C", "C"], 0.8), ("C", 3))
        self.assertEqual(sl.loop_qwen("A", None, ["B", "D", "C"], 0.8), ("B", 3))  # missing confidence is unsure

    def test_mimo_uses_its_two_draws_as_the_signal(self):
        self.assertEqual(sl.loop_mimo("A", "A", ["B", "B", "B"]), ("A", 1))
        self.assertEqual(sl.loop_mimo("A", "B", ["B", "C", "C"]), ("B", 2))
        self.assertEqual(sl.loop_mimo("A", "B", ["C", "D", "D"]), ("D", 3))
        self.assertEqual(sl.loop_mimo("", "", ["C", "C", "A"]), ("C", 3))  # two empty B answers are not agreement

    def test_the_threshold_rule_picks_the_smallest_threshold_within_the_margin(self):
        rows = [(0.95, 1, 1)] * 6 + [(0.7, 0, 1)] * 3 + [(0.85, 1, 0)]
        result = sl.threshold_from_design(rows)  # always-S 90; below 0.75 the loop keeps the wrong 0.7 answers (70)
        self.assertEqual((result["threshold"], result["loop_accuracy"], result["always_s_accuracy"]), (0.75, 100.0, 90.0))


@unittest.skipUnless(HAS_DESIGN, "needs the design data of the threshold rule")
class TestThreshold(unittest.TestCase):
    def test_the_registered_threshold_is_reproduced_from_its_inputs(self):
        for path, digest in CONFIG["threshold_rule"]["inputs_sha256"].items():
            self.assertEqual(sl.v1.sha256_file(dp.ROOT / path), digest)
        calibration = {row["id"]: row for row in csv.DictReader((dp.ROOT / DESIGN[0]).open(encoding="utf-8"))}
        s1 = {}
        for path in DESIGN[1:]:
            for line in (dp.ROOT / path).read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["dataset_id"] == "vi-multimodel-v1-vmlu-valid" and row["replicate_id"] == "S-r1":
                    s1[row["item_id"]] = row["correct"]
        rows = [(float(calibration[i]["confidence"]) if calibration[i]["confidence"] else None,
                 int(calibration[i]["correct"]), s1[i]) for i in sorted(s1) if i in calibration]
        self.assertEqual(len(rows), 660)
        self.assertEqual(sl.threshold_from_design(rows), CONFIG["threshold_rule"]["result"])


@unittest.skipUnless(HAS_SOURCES, "needs the pinned VMLU, VM14K and ViBidLQA sources")
class TestManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = {student: sl.build_manifest(student) for student in sl.STUDENTS}

    def test_counts_and_disjointness_from_earlier_router_items(self):
        expected = {"qwen": 3612, "mimo": 4215}
        mc95 = {(row["dataset_id"], row["item_id"]) for row in h3.load_frozen_manifest()["items"]}
        mc96 = {row["item_id"] for row in k2.load_frozen_manifest()["items"]}
        mc95_bidlqa = k2.excluded_keys()
        for student, (manifest, _) in self.built.items():
            self.assertEqual(manifest["n"], expected[student])
            self.assertEqual(manifest["dataset_counts"], {sl.KNOW: 300, sl.VM14K: 300, sl.VMLU: 303})
            items = {(row["dataset_id"], row["item_id"]) for row in manifest["items"]}
            self.assertFalse({key for key in items if key[0] == sl.VM14K} & mc95)
            knowledge = {item_id for dataset_id, item_id in items if dataset_id in (sl.KNOW, sl.KNOW5)}
            self.assertFalse(knowledge & mc96)
            self.assertFalse(knowledge & mc95_bidlqa)
            unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
            self.assertEqual(manifest["manifest_sha256"], sl.v1.sha256_bytes(sl.v1.canonical_json(unhashed)))

    def test_prompts_carry_the_right_evidence_and_never_the_gold_answer(self):
        manifest, rebuilt = self.built["qwen"]
        text_of = {passage["passage_id"]: passage["text"] for passage in k2.load_corpus()}
        checked = 0
        for item_id, trace in list(manifest["retrieval"].items())[:25]:
            closed = rebuilt[f"{sl.KNOW}:{item_id}:B-r1"]
            own = text_of[closed.passage_id].strip()
            self.assertNotIn(own, closed.prompt)
            self.assertIn(own, rebuilt[f"{sl.KNOW}:{item_id}:O-r1"].prompt)
            top2 = rebuilt[f"{sl.KNOW}:{item_id}:K-r1"].prompt
            top5 = rebuilt[f"{sl.KNOW5}:{item_id}:K-r1"].prompt
            for rank, passage in enumerate(trace["top5"]):
                self.assertIn(text_of[passage].strip(), top5)
                if rank < 2:
                    self.assertIn(text_of[passage].strip(), top2)
            checked += 1
        self.assertEqual(checked, 25)
        mc = [item for item in rebuilt.values() if item.dataset_id in (sl.VMLU, sl.VM14K)]
        templates = dp.load_templates()
        for item in mc[:40]:
            arm = dp.arm_of_replicate(item.replicate_id)
            base = item if arm == "B" else rebuilt[item.run_key.rsplit(":", 1)[0] + ":B-r1"]
            self.assertEqual(item.prompt, dp.build_arm_prompt(base, arm, templates))
        self.assertEqual(Counter(dp.arm_of_replicate(item.replicate_id) for item in mc), {"B": 603, "S": 1809})

    def test_the_mimo_manifest_differs_only_by_its_second_b_draw(self):
        qwen, mimo = (self.built[student][1] for student in sl.STUDENTS)
        self.assertEqual(set(mimo) - set(qwen), {key for key in mimo if key.endswith(":B-r2")})
        self.assertTrue(all(mimo[key].prompt == qwen[key].prompt for key in qwen))


if __name__ == "__main__":
    unittest.main()
