"""Offline tests of MC-118's registered analysis and judge join on synthetic cells."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from code_benchmark import analyze_reading_agent as an
from code_benchmark import diagnostic_reading_agent as ra


def synthetic_rows(n: int, recall: dict[str, dict[str, float]]) -> dict[str, list[dict]]:
    """recall[model][arm] = the recall every item gets in that cell (both draws)."""
    rows: dict[str, list[dict]] = {model: [] for model in ra.MODELS}
    for model in ra.MODELS:
        for i in range(n):
            for arm in ra.ARMS:
                for draw in (1, 2):
                    value = recall[model][arm] + (0.01 * (i % 3) if arm == "OMPF" else 0.0)
                    rows[model].append({"dataset_id": "d", "item_id": str(i), "replicate_id": f"{arm}-r{draw}",
                                        "arm": arm, "token_recall": value, "token_f1": value / 2, "em": 0,
                                        "raw_response": f"answer {i}", "prediction": "x", "status": "complete"})
    return rows


class TestTests(unittest.TestCase):
    base = {"DSHF": 0.6, "OMPF": 0.6, "OMPS": 0.6, "C": 0.2, "O": 0.9}

    def test_values_match_the_definitions(self) -> None:
        recall = {"qwen": {**self.base, "OMPF": 0.5, "OMPS": 0.6}, "mimo": {**self.base, "OMPF": 0.8, "OMPS": 0.7}}
        rows = synthetic_rows(30, recall)
        cells = {m: an.cells_of(rows[m]) for m in ra.MODELS}
        keys = sorted(cells["qwen"])
        values = an.test_values(cells, keys, "token_recall")
        mean = {k: round(100 * sum(v) / len(v), 2) for k, v in values.items()}
        self.assertEqual(mean["H1"], round(100 * (0.5 + 0.01 - 0.6), 2))  # OMPF carries +0.01 on average
        self.assertEqual(mean["H2"], round(100 * (0.8 + 0.01 - 0.6), 2))
        self.assertEqual(mean["H3"], round(mean["H2"] - mean["H1"], 2))
        self.assertEqual(mean["H4"], round(100 * ((0.7 - 0.81) - (0.6 - 0.51)), 2))

    def test_family_readings(self) -> None:
        recall = {"qwen": {**self.base, "OMPF": 0.4, "OMPS": 0.6}, "mimo": {**self.base, "OMPF": 0.8, "OMPS": 0.6}}
        rows = synthetic_rows(60, recall)
        cells = {m: an.cells_of(rows[m]) for m in ra.MODELS}
        out = an.family(cells, sorted(cells["qwen"]), "token_recall")
        self.assertIn("worse", out["rules"]["H1"]["reading"])
        self.assertIn("better", out["rules"]["H2"]["reading"])
        self.assertEqual(out["rules"]["H3"]["reading"], "the legal interaction recurs on general reading")
        self.assertIn("carries part", out["rules"]["H4"]["reading"])

    def test_h4_is_not_read_without_an_interaction(self) -> None:
        self.assertTrue(an.reading("H4", -5.0, 0.001, False).startswith("reported, not read"))
        self.assertEqual(an.reading("H3", 3.0, 0.2, False), "not detected")

    def test_missing_cells_fail(self) -> None:
        rows = synthetic_rows(2, {m: dict(self.base) for m in ra.MODELS})
        cells = an.cells_of([r for r in rows["qwen"] if r["replicate_id"] != "O-r2"])
        with self.assertRaises(SystemExit):
            an.check_complete(cells, sorted(cells), "qwen")
        with self.assertRaises(SystemExit):
            an.cells_of(rows["qwen"] + rows["qwen"][:1])


class TestJudge(unittest.TestCase):
    def test_build_and_join(self) -> None:
        base = {"DSHF": 0.6, "OMPF": 0.6, "OMPS": 0.6, "C": 0.2, "O": 0.9}
        rows = synthetic_rows(8, {m: dict(base) for m in ra.MODELS})
        items = [ra.v1.EvalItem("d", "squad", str(i), "main-000", "reading", "s", f"q{i}?", f"p{i}", "x", "g")
                 for i in range(8)]
        passages = {f"p{i}": f"passage {i}" for i in range(8)}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(an.ra, "base_items", return_value=items), \
                mock.patch.object(an, "_passages", return_value=passages, create=True), \
                mock.patch.object(an.ra, "load_passages",
                                  return_value={f"k{i}": {"text": f"passage {i}"} for i in range(8)}), \
                mock.patch.object(an.v1, "sha256_bytes", side_effect=lambda b: "p" + b.decode()[1:]
                                  if b.decode().startswith("k") else __import__("hashlib").sha256(b).hexdigest()):
            out = Path(tmp)
            key = an.judge_build(rows, [f"d:{i}" for i in range(8)], out, shards=4, overlap=1)
            self.assertEqual(len(key["units"]), 8)
            self.assertEqual(sum(u["second"] is not None for u in key["units"]), 4)
            for k in range(4):
                text = (out / "shards" / f"shard_{k}.txt").read_text(encoding="utf-8")
                self.assertNotIn("qwen", text)
                self.assertNotIn("DSHF", text)
                with open(out / "labels" / f"shard_{k}.csv", "w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(["jid", "slot", "label", "hedge", "gold_suspect", "reason"])
                    for unit in key["units"]:
                        if unit["owner"] == k or unit["second"] == k:
                            for slot in range(1, 7):
                                writer.writerow([unit["jid"], slot, 1, 0, 0, "ok"])
            report = an.judge_join(rows, out, shards=4)
        self.assertEqual(report["answers"], 48)
        self.assertEqual(report["second_judge"]["agreement"], 1.0)
        self.assertEqual(report["cells"]["qwen:DSHF"]["recall_bias_points"], -40.0)
        self.assertEqual(report["flags"], [])


if __name__ == "__main__":
    unittest.main()
