"""Offline tests of the registered self-loop analysis (card MC-104) on synthetic scored runs of the frozen
manifests. No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_analyze_self_loop
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from code_benchmark import analyze_self_loop as asl
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_self_loop as sl

HAS_MANIFESTS = all(sl.manifest_path(student).is_file() for student in sl.STUDENTS)


def _unit(*parts: str) -> float:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def synthetic_row(student: str, ref: dict) -> dict:
    """Deterministic scores: S is right more often than B, K top 5 more often than K top 2, O best."""
    arm = dp.arm_of_replicate(ref["replicate_id"])
    u = _unit(student, ref["dataset_id"], ref["item_id"], ref["replicate_id"])
    row = {key: ref[key] for key in ("dataset_id", "item_id", "replicate_id")}
    row["total_tokens"] = {"B": 60, "S": 900, "K": 700, "O": 500}[arm]
    if ref["dataset_id"] in (sl.VMLU, sl.VM14K):
        right = u < (0.9 if arm == "S" else 0.65)
        row.update({"gold_answer": "A", "prediction": "A" if right else "B", "correct": int(right)})
        if arm == "B" and student == "qwen":
            row["confidence"] = 0.95 if right else 0.5
        return row
    level = {"B": 0.1, "K": 0.6, "O": 0.8}[arm] + (0.1 if ref["dataset_id"] == sl.KNOW5 else 0.0)
    f1 = min(1.0, level + 0.2 * u)
    row.update({"token_f1": f1, "em": int(f1 > 0.85), "token_f1_v2": f1, "em_v2": int(f1 > 0.85), "prediction": "x"})
    return row


class TestPolicies(unittest.TestCase):
    def test_each_policy_pays_for_the_requests_it_uses(self):
        cell = {"dataset_id": sl.VMLU, "gold": "A", "b": ["B"], "s": ["A", "A", "C"], "b_tokens": [10],
                "s_tokens": [100, 200, 300], "confidence": 0.5}
        result = asl.policies("qwen", cell, 0.8)
        self.assertEqual(result["loop"], ("A", 610, 3))  # unsure, S-r1 differs from B, vote of S
        self.assertEqual(result["always_vote"], ("A", 600, 1))
        self.assertEqual(result["map"], ("A", 100, 1))  # Qwen's map: VMLU -> S
        mimo = {**cell, "b": ["A", "A"], "b_tokens": [40, 60], "dataset_id": sl.VM14K}
        self.assertEqual(asl.policies("mimo", mimo, 0.8)["loop"], ("A", 100, 1))
        self.assertEqual(asl.policies("mimo", mimo, 0.8)["always_B"], ("A", 40, 1))


@unittest.skipUnless(HAS_MANIFESTS, "needs the frozen self-loop manifests")
class TestReport(unittest.TestCase):
    def test_the_report_on_synthetic_runs_has_the_registered_keys_and_sane_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for student in sl.STUDENTS:
                manifest = sl.load_frozen_manifest(student)
                run_dir = root / asl.PROFILES[student]
                run_dir.mkdir(parents=True)
                (run_dir / "run.json").write_text(json.dumps({"status": "complete",
                                                              "manifest_sha256": manifest["manifest_sha256"]}))
                (run_dir / "scores.jsonl").write_text("\n".join(json.dumps(synthetic_row(student, ref))
                                                                for ref in manifest["items"]) + "\n")
            registration = root / "registration.json"
            keys = sl.load_config()[0]["analysis"]["report_keys"]
            registration.write_text(json.dumps({"card_ids": {sl.PHASE: "MC-104"}, "analysis": {"report_keys": keys}}))
            with mock.patch.object(sl, "REGISTRATION_PATH", registration):
                report = asl.build_report(root)
        self.assertEqual(list(report), keys)
        for student in sl.STUDENTS:
            mc, know = report["multiple_choice"][student], report["knowledge"][student]
            self.assertEqual(mc["n"], 603)
            self.assertEqual(sum(mc["loop_rounds"].values()), 603)
            self.assertGreater(mc["pooled"]["always_S"]["accuracy"], mc["pooled"]["always_B"]["accuracy"])
            self.assertGreater(know["means"]["K5"]["token_f1"], know["means"]["K2"]["token_f1"])
            self.assertEqual(sum(group["items"] for group in know["by_retrieval"].values()), 300)
            self.assertEqual(set(report["primary"][student]), {"loop_beats_B", "loop_not_worse_than_S", "k5_beats_k2"})
        self.assertTrue(report["primary"]["qwen"]["loop_beats_B"]["met"])
        self.assertIn("list_price_usd", report["cost"]["mimo"])


if __name__ == "__main__":
    unittest.main()
