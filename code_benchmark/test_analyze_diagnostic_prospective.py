"""Offline tests for the prospective-campaign analysis plan (no data, no network).

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_analyze_diagnostic_prospective
Expected values are worked out by hand in the comments.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import analyze_diagnostic_prospective as an
from code_benchmark import diagnostic_prospective as dp

MC, RD = "vi-multimodel-v1-legal-mc-146", "vi-multimodel-v1-vi-squad-200"


def mc_row(arm: str, item: int, replicate: int, correct: bool) -> dict:
    return {"dataset_id": MC, "item_id": f"M{item:03d}", "replicate_id": f"{arm}-r{replicate}", "arm": arm,
            "correct": int(correct), "passage_id": "legal", "prediction": "A" if correct else "B", "gold_answer": "A",
            "raw_response": f"raw-{arm}-{item}-{replicate}", "prompt_sha256": "h" * 64}


def rd_row(arm: str, item: int, replicate: int, em: bool, f1: float = 0.0, passage: str | None = None) -> dict:
    return {"dataset_id": RD, "item_id": f"R{item:03d}", "replicate_id": f"{arm}-r{replicate}", "arm": arm,
            "em": int(em), "token_f1": 1.0 if em else f1, "passage_id": passage or f"p{item}", "prediction": "x",
            "gold_answer": "y", "raw_response": f"raw-{arm}-{item}-{replicate}", "prompt_sha256": "h" * 64}


def worked_example_rows() -> list[dict]:
    """60 MC items, one replicate each: 20 B-incorrect (items 0-19), 8 of them rescued by S (0-7);
    40 B-correct (items 20-59), 3 of them regressed under S (20-22)."""
    rows = []
    for item in range(60):
        b_ok = item >= 20
        s_ok = (b_ok and item not in (20, 21, 22)) or (not b_ok and item < 8)
        rows += [mc_row("B", item, 1, b_ok), mc_row("S", item, 1, s_ok)]
    return rows


class TestStatistics(unittest.TestCase):
    def test_exact_mcnemar_known_values(self):
        self.assertEqual(an.mcnemar_exact_p(0, 5), 0.0625)           # 2 * (1/2)^5
        self.assertEqual(an.mcnemar_exact_p(3, 3), 1.0)              # capped at 1
        self.assertAlmostEqual(an.mcnemar_exact_p(1, 7), 18 / 256)   # n=8, P(X<=1) = 9/256
        self.assertEqual(an.mcnemar_exact_p(0, 0), 1.0)

    def test_holm_adjustment_is_monotone(self):
        adjusted = an.holm_adjust({"S": 0.01, "K": 0.04, "KS": 0.03})
        # sorted 0.01 -> 3*0.01, 0.03 -> 2*0.03, 0.04 -> max(0.06, 1*0.04)
        self.assertAlmostEqual(adjusted["S"], 0.03)
        self.assertAlmostEqual(adjusted["KS"], 0.06)
        self.assertAlmostEqual(adjusted["K"], 0.06)

    def test_wilson_interval_for_four_of_six(self):
        low, high = an.wilson_interval(4, 6)
        self.assertAlmostEqual(low, 30.0, delta=0.1)
        self.assertAlmostEqual(high, 90.3, delta=0.1)

    def test_item_outcome_is_a_strict_majority_and_ties_count_as_incorrect(self):
        three = lambda *bits: [mc_row("B", 0, i + 1, b) for i, b in enumerate(bits)]  # noqa: E731
        self.assertEqual(an.item_outcome(three(True, True, False)), (True, False))
        self.assertEqual(an.item_outcome(three(True, False, False)), (False, False))
        self.assertEqual(an.item_outcome(three(True, False)), (False, True))


class TestPairedOutcomes(unittest.TestCase):
    def test_worked_example_from_the_scoring_spec(self):
        report = an.analyze(worked_example_rows(), phase="core")
        s = report["families"]["mc"]["arms"]["S"]
        self.assertEqual((s["n_pairs"], s["baseline_incorrect"], s["baseline_correct"]), (60, 20, 40))
        self.assertEqual((s["rescues"], s["regressions"]), (8, 3))
        self.assertEqual(s["recovery"], 8 / 20)
        self.assertEqual(s["regression_rate"], 3 / 40)
        self.assertEqual(s["net_gain"], 5 / 60)
        self.assertAlmostEqual(s["mcnemar_p"], an.mcnemar_exact_p(3, 8))
        self.assertEqual(s["mcnemar_p_holm"], s["mcnemar_p"])  # one arm: Holm changes nothing
        low, high = s["net_gain_ci95_pct"]
        self.assertLess(low, 100 * 5 / 60)
        self.assertGreater(high, 100 * 5 / 60)

    def test_replicate_majority_decides_the_item_outcome(self):
        rows = []
        for replicate, (b_ok, s_ok) in enumerate([(False, True), (False, True), (True, False)], start=1):
            rows += [mc_row("B", 0, replicate, b_ok), mc_row("S", 0, replicate, s_ok)]
        s = an.analyze(rows, phase="core")["families"]["mc"]["arms"]["S"]
        self.assertEqual((s["rescues"], s["regressions"]), (1, 0))  # B 1/3 -> incorrect, S 2/3 -> correct

    def test_arms_are_compared_within_a_family_and_holm_spans_the_arms(self):
        rows = []
        for item in range(10):
            rows += [mc_row("B", item, 1, False), mc_row("S", item, 1, True), mc_row("O", item, 1, item < 5)]
        for item in range(6):
            rows += [rd_row("B", item, 1, False), rd_row("S", item, 1, item < 3)]
        report = an.analyze(rows, phase="core")
        mc_arms = report["families"]["mc"]["arms"]
        self.assertEqual(set(mc_arms), {"S", "O"})
        self.assertEqual(set(report["families"]["reading"]["arms"]), {"S"})
        self.assertGreaterEqual(mc_arms["O"]["mcnemar_p_holm"], mc_arms["O"]["mcnemar_p"])
        self.assertEqual(mc_arms["S"]["by_dataset_descriptive"], {MC: {"n_pairs": 10, "rescues": 10, "regressions": 0}})


class TestDiscordantExport(unittest.TestCase):
    def test_rescues_and_regressions_are_both_exported(self):
        pairs = an.discordant_pairs(worked_example_rows(), "S")
        self.assertEqual(len(pairs), 11)
        self.assertEqual(sum(p["direction"] == "rescue" for p in pairs), 8)
        self.assertEqual(sum(p["direction"] == "regression" for p in pairs), 3)
        first = pairs[0]
        self.assertEqual(set(first), {"item_key", "arm", "direction", "format_suspect", "gold_answer", "B", "S"})
        self.assertIsNone(first["format_suspect"])  # multiple-choice rescues carry no format flag
        self.assertEqual(first["S"][0]["prompt_sha256"], "h" * 64)

    def test_reading_near_matches_are_listed_but_never_counted_correct(self):
        rows = [rd_row("B", 0, 1, False, f1=0.9), rd_row("S", 0, 1, False, f1=0.5), rd_row("B", 1, 1, False, f1=0.79)]
        candidates = an.semantic_audit_candidates(rows, 0.8)
        self.assertEqual([(c["item_id"], c["arm"]) for c in candidates], [("R000", "B")])
        self.assertFalse(an.attempt_correct(rows[0]))


class TestOracleCeiling(unittest.TestCase):
    def test_ceiling_is_reported_with_the_b_replicate_null(self):
        rows = []
        for item in range(4):
            # B replicates: item 0 correct once (r2), others never; S r1 correct on items 0-1
            rows += [mc_row("B", item, 1, False), mc_row("B", item, 2, item == 0), mc_row("B", item, 3, False),
                     mc_row("S", item, 1, item < 2)]
        result = an.oracle_ceilings(rows)
        self.assertEqual(result["items"], 4)
        self.assertEqual(result["observed"], 2 / 4)                       # any of (B-r1, S-r1): items 0,1
        self.assertEqual(result["null_from_baseline_replicates"], 1 / 4)  # any of (B-r1, B-r2): item 0
        self.assertEqual(result["headroom_over_null"], 1 / 4)
        self.assertEqual(result["null_capped_items"], 0)

    def test_single_draw_per_arm_has_no_noise_floor(self):
        rows = [r for item in range(3) for r in (mc_row("B", item, 1, False), mc_row("S", item, 1, True))]
        result = an.oracle_ceilings(rows)
        self.assertEqual(result["observed"], 1.0)
        self.assertIsNone(result["null_from_baseline_replicates"])
        self.assertIsNone(result["headroom_over_null"])
        self.assertIn("single draw", result["note"])


class TestNoiseReference(unittest.TestCase):
    def test_baseline_noise_counts_every_ordered_replicate_pair(self):
        rows = [mc_row("B", 0, k, ok) for k, ok in enumerate([True, False, False], start=1)]
        rows += [mc_row("B", 1, k, False) for k in (1, 2, 3)]
        noise = an.baseline_noise(rows)
        # item 0 = [1,0,0]: 6 ordered pairs -> 1->2 and 1->3 regress, 2->1 and 3->1 rescue, 2->3 and 3->2 stay wrong
        # item 1 = [0,0,0]: 6 ordered pairs, all start incorrect and none rescues
        self.assertEqual((noise["ordered_pairs"], noise["first_correct"], noise["first_incorrect"]), (12, 2, 10))
        self.assertEqual((noise["rescues"], noise["regressions"]), (2, 2))
        self.assertEqual(noise["recovery"], 2 / 10)
        self.assertEqual(noise["regression_rate"], 2 / 2)

    def test_single_replicate_has_no_noise_reference(self):
        self.assertIsNone(an.baseline_noise([mc_row("B", 0, 1, True), mc_row("S", 0, 1, False)]))

    def test_attempt_level_pairs_share_a_replicate_number(self):
        rows = []
        for k, (b_ok, s_ok) in enumerate([(False, True), (True, True), (False, False)], start=1):
            rows += [mc_row("B", 0, k, b_ok), mc_row("S", 0, k, s_ok)]
        level = an.attempt_level_counts(rows, "S")
        # pairs (B-rk, S-rk): k=1 rescue, k=2 both correct, k=3 both wrong
        self.assertEqual((level["attempt_pairs"], level["rescues"], level["regressions"]), (3, 1, 0))
        self.assertEqual((level["first_incorrect"], level["first_correct"]), (2, 1))
        self.assertEqual(level["recovery"], 1 / 2)

    def test_report_places_arm_rates_next_to_the_noise_floor(self):
        rows = []
        for item in range(6):
            for k in (1, 2, 3):
                rows += [mc_row("B", item, k, False), mc_row("S", item, k, True)]
        report = an.analyze(rows, phase="core")
        self.assertEqual(report["families"]["mc"]["arms"]["S"]["attempt_level"]["recovery"], 1.0)
        self.assertEqual(report["baseline_noise"]["mc"]["recovery"], 0.0)  # B never flips on its own here
        self.assertIsNone(report["parity_gate"])  # core anchors are a purposive sample: no parity gate


class TestSecondaryAnalyses(unittest.TestCase):
    def test_compliant_only_sensitivity_drops_items_with_a_noncompliant_attempt(self):
        rows = []
        for item in range(4):
            rows.append(mc_row("B", item, 1, False))
            reasoning = mc_row("S", item, 1, True)
            reasoning["format_ok"] = item != 3  # item 3 lacked the final label
            rows.append(reasoning)
        arm = an.analyze(rows, phase="core")["families"]["mc"]["arms"]["S"]
        self.assertEqual(arm["rescues"], 4)
        sensitivity = arm["sensitivity_format_compliant"]
        self.assertEqual((sensitivity["rescues"], sensitivity["n_pairs"], sensitivity["items_excluded"]), (3, 3, 1))

    def test_sensitivity_is_absent_without_format_flags(self):
        arm = an.analyze(worked_example_rows(), phase="core")["families"]["mc"]["arms"]["S"]
        self.assertIsNone(arm["sensitivity_format_compliant"])
        self.assertIsNone(arm["mean_f1_diff"])  # multiple choice carries no token-F1

    def test_reading_f1_difference_and_format_suspect_rescues(self):
        rows = [rd_row("B", 0, 1, False, f1=0.9), rd_row("S", 0, 1, True),   # B near-matched: format-suspect rescue
                rd_row("B", 1, 1, False, f1=0.1), rd_row("S", 1, 1, True),   # substantive rescue
                rd_row("B", 2, 1, True), rd_row("S", 2, 1, True)]
        arm = an.analyze(rows, phase="core")["families"]["reading"]["arms"]["S"]
        self.assertEqual((arm["rescues"], arm["rescues_format_suspect"]), (2, 1))
        # F1 differences: 1.0-0.9, 1.0-0.1, 1.0-1.0 -> mean 1.0/3
        self.assertAlmostEqual(arm["mean_f1_diff"], 1.0 / 3)
        self.assertEqual(len(arm["mean_f1_diff_ci95_pts"]), 2)
        flags = {p["item_key"].split(":")[1]: p["format_suspect"] for p in an.discordant_pairs(rows, "S", f1_threshold=0.8)}
        self.assertEqual(flags, {"R000": True, "R001": False})


class TestParityGate(unittest.TestCase):
    PROTOCOL = {"analysis": {"parity_reference": {"source": "test", "datasets": {
        MC: {"metric": "accuracy", "value": 80.0, "ci95": [70.0, 88.0]},
        RD: {"metric": "em", "value": 50.0, "ci95": [40.0, 60.0]}}}}}

    def test_inside_and_outside_the_reference_interval(self):
        rows = [mc_row("B", i, 1, i < 8) for i in range(10)] + [rd_row("B", i, 1, i < 2) for i in range(10)]
        gate = an.parity_gate(rows, self.PROTOCOL)
        self.assertEqual(gate["datasets"][MC]["observed"], 80.0)
        self.assertTrue(gate["datasets"][MC]["within_reference_ci"])
        self.assertFalse(gate["datasets"][RD]["within_reference_ci"])  # 20% against [40, 60]
        self.assertFalse(gate["all_within"])

    def test_datasets_without_b_attempts_are_not_counted(self):
        gate = an.parity_gate([mc_row("B", i, 1, i < 8) for i in range(10)], self.PROTOCOL)
        self.assertIsNone(gate["datasets"][RD])
        self.assertTrue(gate["all_within"])

    def test_the_real_protocol_carries_all_five_reference_datasets(self):
        reference = dp.load_protocol()["analysis"]["parity_reference"]["datasets"]
        self.assertEqual(set(reference), set(dp.load_protocol()["datasets"]))
        report = an.analyze([mc_row("B", 0, 1, True), mc_row("S", 0, 1, True)], phase="wide")
        self.assertFalse(report["parity_gate"]["all_within"])  # one item at 100% is outside the Legal MC interval
        self.assertEqual(report["parity_gate"]["datasets"][MC]["observed"], 100.0)


class TestPlanConsistency(unittest.TestCase):
    def test_protocol_names_every_metric_the_analysis_reports(self):
        named = set(dp.load_protocol()["analysis"]["metrics"])
        report = an.analyze(worked_example_rows(), phase="core")
        reported = set(next(iter(report["families"]["mc"]["arms"].values()))) - {"arm"}
        reported |= {"item_ties", "semantic_audit_candidates_n", "baseline_noise", "parity_gate"}
        reported |= {f"oracle_routing.{key}" for key in ("observed", "null_from_baseline_replicates", "headroom_over_null")}
        self.assertEqual(reported - named, set(), "metrics reported but not named in the pre-registered plan")
        self.assertEqual(named - reported, set(), "metrics named in the plan but not reported")


class TestCli(unittest.TestCase):
    def test_cli_writes_report_and_discordant_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores.jsonl"
            scores.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in worked_example_rows()), encoding="utf-8")
            out, pairs = Path(tmp) / "report.json", Path(tmp) / "pairs.jsonl"
            self.assertEqual(an.main(["--scores", str(scores), "--phase", "core", "--out", str(out),
                                      "--discordant-out", str(pairs)]), 0)
            self.assertEqual(json.loads(out.read_text())["families"]["mc"]["arms"]["S"]["rescues"], 8)
            self.assertEqual(len(pairs.read_text().splitlines()), 11)


if __name__ == "__main__":
    unittest.main()
