"""Offline tests of the router results builder (web/data/router-results.json). No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_build_router_results
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from code_benchmark import build_router_results as brr

HAS_REPORTS = all((brr.ROOT / path).is_file() for path in brr.REPORTS.values())


class TestRules(unittest.TestCase):
    def test_published_wording_must_match_the_report(self):
        self.assertEqual(brr.settle("MC-0", "not_met", "not_met"), "not_met")
        with self.assertRaises(SystemExit):
            brr.settle("MC-0", "met", "not_met")

    def test_a_win_needs_a_small_p_and_a_gain(self):
        self.assertTrue(brr.better(0.01, 2.0))
        self.assertFalse(brr.better(0.01, -2.0))
        self.assertFalse(brr.better(0.2, 2.0))

    def test_an_overview_line_names_its_table_tests_and_rows(self):
        block = brr.table("Kết quả", [brr.column("core", "Core", "Tỷ lệ đúng", 60)], [])
        versus = brr.test("Router v1 so với luôn B", diff=5.0, p=0.5, primary=True)
        entry = brr.line([{"title": "other"}, block], "60 câu core", block, "core", ("router", "Router v1"),
                         always_b="always_B", compared=((versus, "so với luôn B"),))
        self.assertEqual(entry["table"], 1)
        self.assertEqual(entry["tests"], [{"test": "Router v1 so với luôn B", "label": "so với luôn B"}])
        self.assertEqual((entry["always_b"], entry["always_s"], entry["others"]), ("always_B", None, []))
        with self.assertRaises(SystemExit):
            brr.line([block], "60 câu core", dict(block), "core", ("router", "Router v1"))

    def test_a_detail_cell_carries_its_difference_from_b(self):
        columns = [brr.column("a", "A", "Tỷ lệ đúng", 10), brr.column("b", "B", "Tỷ lệ đúng", 10)]
        rows = [brr.row("always_B", "Luôn B", "baseline", {"a": brr.cell(69.89), "b": brr.cell(50.0)}),
                brr.row("loop", "Sau", "candidate", {"a": brr.cell(81.99), "b": brr.cell(45.5)}),
                brr.row("O", "Trần", "ceiling", {"b": brr.cell(90.0)}),
                brr.row("table", "Số /table", "reference", {"a": brr.cell(68.55), "b": brr.cell(49.0)})]
        cells = {entry["id"]: {key: value["vs_b"] for key, value in entry["cells"].items()}
                 for entry in brr.table("x", columns, rows)["rows"]}
        self.assertEqual(cells, {"always_B": {"a": None, "b": None}, "loop": {"a": 12.1, "b": -4.5}, "O": {"b": 40.0},
                                 "table": {"a": None, "b": None}})
        two = [brr.row(f"{side}-{arm}", arm, "baseline", {"a": brr.cell(score)})
               for side, arm, score in (("m", "B1", 70.0), ("m", "S1", 75.0), ("q", "B1", 60.0), ("q", "S1", 58.0))]
        paired = brr.table("two models", columns, two, versus={"m-S1": "m-B1", "q-S1": "q-B1"})
        self.assertEqual([entry["cells"]["a"]["vs_b"] for entry in paired["rows"]], [None, 5.0, None, -2.0])
        with self.assertRaises(SystemExit):
            brr.table("two B rows", columns, [*rows, brr.row("B", "B", "baseline", {"a": brr.cell(1.0)})])
        with self.assertRaises(SystemExit):
            brr.table("no B row", columns, rows[1:3])

    def test_the_loop_explanation_reads_the_registered_threshold(self):
        self.assertEqual(brr.registered_threshold(brr.ROOT), 0.8)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (brr.TABLE_LOOP_CONFIG, brr.TABLE_LOOP_REGISTRATION):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes((brr.ROOT / name).read_bytes())
            config = root / brr.TABLE_LOOP_CONFIG
            config.write_bytes(config.read_bytes() + b"\n")
            with self.assertRaises(SystemExit):
                brr.registered_threshold(root)

    def test_the_loop_explanation_takes_its_token_range_from_the_cells(self):
        def experiment(loop_tokens: float) -> dict:
            columns = [brr.column("a", "A", "Tỷ lệ đúng", 10), brr.column("b", "B", "Tỷ lệ đúng", 10)]
            rows = [brr.row("always_B", "Trước", "baseline", {"a": brr.cell(50, tokens=100), "b": brr.cell(50, tokens=200)}),
                    brr.row("loop", "Sau", "candidate", {"a": brr.cell(60, tokens=loop_tokens), "b": brr.cell(60, tokens=900)})]
            return {"tables": [brr.table("Qwen3.5-9B · x", columns, rows)]}
        groups = [{"label": "Qwen3.5-9B", "table": 0, "rows": []}]
        method = brr.loop_method(experiment(250), groups, 0.8)
        self.assertEqual([step["title"] for step in method["steps"]], ["Hỏi thẳng (B)", "Suy luận từng bước (S)", "Bỏ phiếu"])
        self.assertIn("từ 0,80 trở lên", method["steps"][0]["text"])
        self.assertIn("gấp 2,5 đến 4,5 lần", method["note"])
        with self.assertRaises(SystemExit):
            brr.loop_method(experiment(90), groups, 0.8)


@unittest.skipUnless(HAS_REPORTS, "needs the registered analysis reports under all_res/")
class TestBuild(unittest.TestCase):
    def test_every_experiment_is_built_from_its_report(self):
        data = brr.build()
        status = {experiment["cards"]: experiment["status"] for experiment in data["experiments"]}
        self.assertEqual(status, {"MC-90, MC-91, MC-92": "not_met", "MC-93": "not_met", "MC-94": "partial",
                                  "MC-95": "not_met", "MC-96": "not_met", "MC-97": "descriptive", "MC-98": "not_met",
                                  "MC-100": "met", "MC-101": "not_met", "MC-102": "not_met", "MC-103": "descriptive",
                                  "MC-104": "partial", "MC-105": "partial",
                                  "MC-109": "descriptive", "MC-110, MC-110c": "descriptive"})
        for experiment in data["experiments"]:
            self.assertTrue(experiment["sources"])
            self.assertTrue(all(len(source["sha256"]) == 64 for source in experiment["sources"]))

    def test_the_overview_points_at_cells_and_tests_of_each_card(self):
        data = brr.build()
        cards = {experiment["id"]: experiment for experiment in data["experiments"]}
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual(data["benchmark"]["experiment"], "mc-105")
        self.assertEqual([experiment["cards"] for experiment in data["experiments"] if not experiment["overview"]],
                         ["MC-105"])
        source = cards["mc-105"]
        for group, (_, model) in zip(data["benchmark"]["groups"], brr.STUDENTS, strict=True):
            self.assertEqual(group["label"], model)
            self.assertTrue(source["tables"][group["table"]]["title"].startswith(model))
            changes = next(row for row in group["rows"] if row["row"] == "loop")["changes"]
            # The VMLU test column adds a descriptive change for each model (MC-109 for Qwen, MC-110c for MiMo).
            self.assertEqual(set(changes), set(brr.TABLE_DATASETS) | {brr.VMLU_TEST_COLUMN[0]})
            self.assertTrue(all(label.startswith(model) for label in changes.values()))
        line = cards["mc-94"]["overview"][0]
        cells = {row["id"]: row["cells"][line["column"]]["score"] for row in cards["mc-94"]["tables"][line["table"]]["rows"]}
        self.assertEqual([cells[line["tried"]["row"]], cells[line["always_b"]], cells[line["always_s"]]], [76.67, 68.33, 80.0])
        # The detail tables' difference from B agrees with MC-105's registered paired difference in every cell.
        for group in data["benchmark"]["groups"]:
            loop = next(entry for entry in source["tables"][group["table"]]["rows"] if entry["id"] == "loop")
            changes = next(row for row in group["rows"] if row["row"] == "loop")["changes"]
            for key, label in changes.items():
                diff = next(entry["diff"] for entry in source["tests"] if entry["label"] == label)
                self.assertAlmostEqual(loop["cells"][key]["vs_b"], diff, delta=0.011)
        mimo = {entry["id"]: entry["cells"]["vmlu"]["vs_b"] for entry in cards["mc-103"]["tables"][0]["rows"]}
        self.assertEqual((mimo["student-B1"], mimo["reference-B1"]), (None, None))
        self.assertIsNotNone(mimo["student-S1"])
        method = data["benchmark"]["method"]
        self.assertEqual(len(method["steps"]), 3)
        self.assertIn("từ 0,80 trở lên", method["steps"][0]["text"])

    def test_an_overview_name_that_points_nowhere_stops_the_build(self):
        data = brr.build()
        data["experiments"][2]["overview"][0]["tests"][0]["test"] = "a test the card does not have"
        with self.assertRaises(SystemExit):
            brr.validate_overview(data)
        data = brr.build()
        data["experiments"][1]["overview"] = []
        with self.assertRaises(SystemExit):
            brr.validate_overview(data)
        data = brr.build()
        data["benchmark"]["groups"][0]["rows"][1]["changes"]["vmlu-dev"] = "Qwen3.5-9B · VMLU dev: sau so với trước"
        with self.assertRaises(SystemExit):
            brr.validate_overview(data)


if __name__ == "__main__":
    unittest.main()
