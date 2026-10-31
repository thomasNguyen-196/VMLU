"""Offline tests of the registered table-loop analysis (card MC-105) on synthetic scored runs of the frozen
manifests. No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_analyze_table_loop
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from code_benchmark import analyze_table_loop as atl
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_table_loop as tl

HAS_INPUTS = all(tl.manifest_path(s).is_file() for s in tl.STUDENTS) and atl.MC104_REPORT.is_file()


def _unit(*parts: str) -> float:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def synthetic_row(student: str, ref: dict) -> dict:
    """Deterministic scores: S right more often than B; a right B answer is confident and repeats itself."""
    arm = dp.arm_of_replicate(ref["replicate_id"])
    item_u = _unit(student, ref["dataset_id"], ref["item_id"])
    right = item_u < 0.6 if arm == "B" else _unit(student, ref["item_id"], ref["replicate_id"]) < 0.85
    row = {key: ref[key] for key in ("dataset_id", "item_id", "replicate_id")}
    row["total_tokens"] = 100 if arm == "B" else 900
    if ref["task"] == "multiple_choice":
        row.update({"gold_answer": "A", "prediction": "A" if right else "BCD"[int(3 * _unit(ref["replicate_id"]))]})
        if arm == "B" and student == "qwen":
            row["confidence"] = 0.95 if right else 0.4
        return row
    answer = "đúng" if right else f"sai {ref['replicate_id']}"
    f1 = 1.0 if right else 0.2
    row.update({"prediction": answer, "token_f1": f1, "em": int(right), "token_f1_v2": f1, "em_v2": int(right)})
    return row


class TestOutcome(unittest.TestCase):
    def test_the_loop_pays_for_two_b_answers_on_reading(self):
        attempts = {r: {"prediction": p, "total_tokens": t, "token_f1": f, "em": 0, "token_f1_v2": f, "em_v2": 0}
                    for r, p, t, f in (("B-r1", "x", 10, 0.1), ("B-r2", "y", 20, 0.2), ("S-r1", "z", 100, 0.9),
                                       ("S-r2", "z", 200, 0.8), ("S-r3", "w", 300, 0.3))}
        outcome = atl.item_outcome("qwen", "reading", attempts, 0.8)
        self.assertEqual(outcome["rounds"], 3)
        self.assertEqual(outcome["cost"], {"always_B": 10, "always_S": 100, "always_vote": 600, "loop": 630})
        self.assertEqual(outcome["scores"]["loop"]["token_f1"], 0.9)  # the vote picks S-r1, the earliest "z"


@unittest.skipUnless(HAS_INPUTS, "needs the frozen table-loop manifests and the MC-104 report")
class TestReport(unittest.TestCase):
    def test_the_report_on_synthetic_runs_has_the_registered_keys_and_sane_numbers(self):
        keys = tl.load_config()[0]["analysis"]["report_keys"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for student in tl.STUDENTS:
                manifest = tl.load_frozen_manifest(student)
                run_dir = root / atl.PROFILES[student]
                run_dir.mkdir(parents=True)
                (run_dir / "run.json").write_text(json.dumps({"status": "complete",
                                                              "manifest_sha256": manifest["manifest_sha256"]}))
                (run_dir / "scores.jsonl").write_text("\n".join(json.dumps(synthetic_row(student, ref))
                                                                for ref in manifest["items"]) + "\n")
            registration = root / "registration.json"
            registration.write_text(json.dumps({"card_ids": {tl.PHASE: "MC-105"}, "analysis": {"report_keys": keys}}))
            with mock.patch.object(tl, "REGISTRATION_PATH", registration):
                report = atl.build_report(root)
        self.assertEqual(list(report), keys)
        self.assertEqual(len(report["primary"]), 12)
        for student in tl.STUDENTS:
            for block in report["datasets"][student].values():
                self.assertEqual(sum(block["loop_rounds"].values()), block["n"])
                policies = block["policies"]
                self.assertGreater(policies["always_S"][block["metric"]], policies["always_B"][block["metric"]])
                self.assertTrue(block["table_reference"])
            self.assertIn("table_reference", report["vmlu_dev"][student])
        self.assertTrue(report["primary"]["qwen:vi-multimodel-v1-vmlu-valid"]["met"])
        self.assertIn("list_price_usd", report["cost"]["mimo"])


if __name__ == "__main__":
    unittest.main()
