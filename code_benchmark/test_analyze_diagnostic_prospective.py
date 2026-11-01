"""Offline tests for the prospective-campaign analysis plan (no data, no network).

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_analyze_diagnostic_prospective
Expected values are worked out by hand in the comments.
"""
from __future__ import annotations

import dataclasses
import json
import re
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


class TestRealScoringRows(unittest.TestCase):
    """The analysis must consume exactly the rows the scoring wrapper writes to scores.jsonl."""

    @staticmethod
    def scored_rows() -> list[dict]:
        from code_benchmark.test_diagnostic_prospective import make_item, prediction, synthetic_manifest

        def reply(item) -> str:
            arm, index = dp.arm_of_replicate(item.replicate_id), int(item.item_id[1:])
            right = arm == "S" or index < 2  # S is always right; B is right on the first two items only
            if item.task == "multiple_choice":
                letter = "C" if right else "A"
                return f"Xét từng đáp án.\nĐáp án: {letter}" if arm == "S" else letter
            answer = "1998" if right else "1997"
            return f"Đối chiếu đoạn văn.\nTrả lời: {answer}" if arm == "S" else answer

        entries = []
        for index in range(4):
            mc = make_item("multiple_choice", f"M{index}", gold="C")
            rd = dataclasses.replace(make_item("reading", f"R{index}", gold="1998"), passage_id=f"p{index}")
            entries += [(item, arm, k) for k in (1, 2, 3) for item in (mc, rd) for arm in ("B", "S")]
        manifest, rebuilt, items = synthetic_manifest(entries)
        scored, _ = dp.score_arm_rows(manifest, {i.run_key: prediction(i, reply(i)) for i in items}, rebuilt)
        return scored

    def test_rows_from_the_scoring_wrapper_flow_through_the_analysis(self):
        scored = self.scored_rows()
        report = an.analyze(scored, phase="core")
        mc, rd = report["families"]["mc"]["arms"]["S"], report["families"]["reading"]["arms"]["S"]
        # B wrong on items 2-3 in every replicate, S always right: 2 rescues and no regression per family
        self.assertEqual((mc["n_pairs"], mc["rescues"], mc["regressions"]), (4, 2, 0))
        self.assertEqual((rd["n_pairs"], rd["rescues"], rd["regressions"]), (4, 2, 0))
        self.assertEqual(report["item_ties"], 0)
        self.assertEqual(mc["attempt_level"]["attempt_pairs"], 12)
        self.assertEqual(report["baseline_noise"]["mc"]["recovery"], 0.0)  # B never flips on its own here
        self.assertEqual(mc["sensitivity_format_compliant"]["rescues"], 2)  # every S attempt carries the label
        self.assertAlmostEqual(rd["mean_f1_diff"], 0.5)  # token_f1 exists on real reading rows: (0+0+1+1)/4
        self.assertEqual(rd["rescues_format_suspect"], 0)  # B shared no token with the gold on the rescued items

    def test_exports_carry_the_fields_the_reviewer_needs(self):
        scored = self.scored_rows()
        pairs = an.discordant_pairs(scored, "S")
        self.assertEqual(len(pairs), 4)
        self.assertTrue(all(p["gold_answer"] and p["S"][0]["prompt_sha256"] and p["B"][0]["raw_response"] for p in pairs))
        self.assertEqual({p["direction"] for p in pairs}, {"rescue"})
        self.assertEqual(an.semantic_audit_candidates(scored, 0.8), [])  # "1997" shares no token with "1998"


class TestBReplicateSupplement(unittest.TestCase):
    """MC-91: a second B draw of every wide item. Hand-worked example with 10 multiple-choice items:
    B1 right on 0-4, B2 right on 0, 1, 2, 5, S1 right on 0, 1, 3, 5, 6."""

    B1, B2, S1 = {0, 1, 2, 3, 4}, {0, 1, 2, 5}, {0, 1, 3, 5, 6}

    def rows(self):
        primary = [r for i in range(10) for r in (mc_row("B", i, 1, i in self.B1), mc_row("S", i, 1, i in self.S1))]
        return primary, [mc_row("B", i, 2, i in self.B2) for i in range(10)]

    def report(self):
        return an.noise_reference(*self.rows())

    def test_drift_and_noise_counts(self):
        b = self.report()["families"]["mc"]
        # items 3 and 4 were right then wrong, item 5 wrong then right, 0-2 stay right and 6-9 stay wrong
        self.assertEqual((b["n_items"], b["drift"]["rescues"], b["drift"]["regressions"]), (10, 1, 2))
        self.assertAlmostEqual(b["drift"]["net"], -0.1)
        self.assertEqual(b["drift"]["mcnemar_p"], 1.0)  # 3 discordant items: min(1, 2 * 4 / 8)
        self.assertEqual((b["noise_recovery"], b["noise_regression_rate"]), (1 / 5, 2 / 5))  # B1 wrong on 5, right on 5
        self.assertEqual(b["agreement_rate"], 0.7)
        self.assertEqual(b["accuracy"], {"b1": 0.5, "b2": 0.4, "s1": 0.5})

    def test_s_against_the_independent_baseline_draw(self):
        sb2 = self.report()["families"]["mc"]["s_vs_b2"]
        # B2 wrong on 3, 4, 6-9 and S1 right on 3 and 6; B2 right on 0, 1, 2, 5 and S1 wrong on 2
        self.assertEqual((sb2["rescues"], sb2["regressions"]), (2, 1))
        self.assertEqual((sb2["recovery"], sb2["regression_rate"]), (2 / 6, 1 / 4))
        self.assertAlmostEqual(sb2["net_gain"], 0.1)
        self.assertEqual(len(sb2["net_gain_ci95_pct"]), 2)

    def test_s_against_the_noise_on_items_selected_by_the_first_baseline_draw(self):
        b = self.report()["families"]["mc"]
        wrong, right = b["s_vs_noise_given_b1_wrong"], b["s_vs_noise_given_b1_right"]
        # B1 wrong on 5-9: S1 right on 5 and 6, the second B draw right on 5 only
        self.assertEqual([wrong[k] for k in ("n", "s_count", "b2_count", "s_only", "b2_only")], [5, 2, 1, 1, 0])
        self.assertAlmostEqual(wrong["difference"], 0.2)
        # B1 right on 0-4: S1 wrong on 2 and 4, B2 wrong on 3 and 4 -> S wrong only on 2, B2 wrong only on 3
        self.assertEqual([right[k] for k in ("n", "s_count", "b2_count", "s_only", "b2_only")], [5, 2, 2, 1, 1])
        self.assertEqual(right["difference"], 0.0)
        self.assertEqual((wrong["mcnemar_p"], wrong["mcnemar_p_holm"], right["mcnemar_p_holm"]), (1.0, 1.0, 1.0))

    def test_holm_runs_over_the_conditional_contrasts_of_both_families(self):
        # reading: 8 items; B1 wrong on all of them; S1 right on all, B2 right on none -> s_only 8, p = 2/2^8
        primary = [r for i in range(8) for r in (rd_row("B", i, 1, False), rd_row("S", i, 1, True))]
        noise = [rd_row("B", i, 2, False) for i in range(8)]
        mc_primary, mc_noise = self.rows()
        report = an.noise_reference(primary + mc_primary, noise + mc_noise)
        wrong = report["families"]["reading"]["s_vs_noise_given_b1_wrong"]
        self.assertAlmostEqual(wrong["mcnemar_p"], 2 / 2 ** 8)
        # four tests, the smallest p is multiplied by 4; the others are 1.0 (no B1-right items in reading, so p = 1)
        self.assertAlmostEqual(wrong["mcnemar_p_holm"], 4 * 2 / 2 ** 8)
        self.assertEqual(report["families"]["reading"]["s_vs_noise_given_b1_right"]["n"], 0)

    def test_stable_categories_and_oracle_with_a_noise_floor(self):
        b = self.report()["families"]["mc"]
        self.assertEqual(b["stable"], {"both_correct": 3, "both_wrong": 4, "unstable": 3,
                                       "s_correct_on_both_wrong": 1, "s_wrong_on_both_correct": 1})
        # B or S right on 0-6 (0.7); B1 or B2 right on 0-5 (0.6)
        self.assertEqual((b["oracle"]["observed"], b["oracle"]["null_from_baseline_replicates"]), (0.7, 0.6))
        self.assertAlmostEqual(b["oracle"]["headroom_over_null"], 0.1)

    def test_reading_reports_token_f1_and_the_dataset_split(self):
        primary = [rd_row("B", 0, 1, True), rd_row("S", 0, 1, True), rd_row("B", 1, 1, False, f1=0.5),
                   rd_row("S", 1, 1, True), rd_row("B", 2, 1, False, f1=0.1), rd_row("S", 2, 1, False, f1=0.3)]
        noise = [rd_row("B", 0, 2, True), rd_row("B", 1, 2, False, f1=0.7), rd_row("B", 2, 2, True)]
        block = an.noise_reference(primary, noise)["families"]["reading"]
        # token_f1 is 1.0 when the exact match holds: B1 = (1, .5, .1), B2 = (1, .7, 1), S1 = (1, 1, .3)
        f = block["mean_f1"]
        self.assertAlmostEqual(f["b1"], 1.6 / 3)
        self.assertAlmostEqual(f["b2"], 2.7 / 3)
        self.assertAlmostEqual(f["s1"], 2.3 / 3)
        self.assertAlmostEqual(f["mean_abs_b1_b2_change"], 1.1 / 3)
        self.assertEqual(set(block["by_dataset_descriptive"]), {RD})
        self.assertIsNone(self.report()["families"]["mc"]["mean_f1"])

    def test_missing_items_are_reported_and_a_wrong_replicate_is_refused(self):
        primary, noise = self.rows()
        partial = an.noise_reference(primary, noise[:7])
        self.assertEqual((partial["items_shared"], partial["items_missing_in_noise_run"]), (7, 3))
        with self.assertRaises(ValueError):
            an.noise_reference(primary, [mc_row("B", 0, 3, True)])

    def test_report_keys_match_the_registered_analysis(self):
        registered = dp.load_registration()["supplements"]["wide-b-r2"]["analysis"]
        report = self.report()
        self.assertEqual(tuple(registered["top_level"]), an.NOISE_TOP_KEYS)
        self.assertEqual(tuple(registered["family_metrics"]), an.NOISE_FAMILY_KEYS)
        self.assertEqual(set(report), set(registered["top_level"]))
        self.assertEqual(set(report["families"]["mc"]), set(registered["family_metrics"]))

    def test_second_draw_is_held_to_the_parity_reference_and_prints(self):
        report = self.report()
        self.assertEqual(report["parity_gate_b2"]["datasets"][MC]["observed"], 40.0)
        self.assertFalse(report["parity_gate_b2"]["all_within"])
        text = an.format_noise_report(report)
        for phrase in ("drift B1->B2", "B-vs-B noise", "given B1 wrong", "oracle B/S"):
            self.assertIn(phrase, text)
        line = next(line for line in text.splitlines() if "B-vs-B noise" in line)
        shown = [float(x) for x in re.findall(r"\d+\.\d", line)]
        self.assertTrue(shown and all(0 <= x <= 100 for x in shown), line)  # percentages, not percentages x 100


class TestSReplicateSupplement(unittest.TestCase):
    """MC-92: a second S draw of every wide item. Hand-worked example with 10 multiple-choice items:
    B1 right on 0-4, B2 right on 0, 1, 2, 5, S1 right on 0, 1, 3, 5, 6, S2 right on 0, 1, 3, 6, 7."""

    B1, B2, S1, S2 = {0, 1, 2, 3, 4}, {0, 1, 2, 5}, {0, 1, 3, 5, 6}, {0, 1, 3, 6, 7}

    def rows(self):
        primary = [r for i in range(10) for r in (mc_row("B", i, 1, i in self.B1), mc_row("S", i, 1, i in self.S1))]
        return (primary, [mc_row("B", i, 2, i in self.B2) for i in range(10)],
                [mc_row("S", i, 2, i in self.S2) for i in range(10)])

    def report(self):
        return an.s_noise_reference(*self.rows())

    def block(self):
        return self.report()["families"]["mc"]

    def test_accuracy_and_the_noise_of_s_itself(self):
        b = self.block()
        self.assertEqual(b["accuracy"], {"b1": 0.5, "b2": 0.4, "s1": 0.5, "s2": 0.5})
        # S1 right on 0, 1, 3, 5, 6 and S2 right on 0, 1, 3, 6, 7: item 7 recovers, item 5 regresses
        self.assertEqual((b["s_drift"]["rescues"], b["s_drift"]["regressions"], b["s_drift"]["mcnemar_p"]), (1, 1, 1.0))
        self.assertEqual((b["s_noise_recovery"], b["s_noise_regression_rate"], b["s_agreement_rate"]), (1 / 5, 1 / 5, 0.8))

    def test_instability_of_the_two_arms(self):
        flips = self.block()["flip_comparison"]
        # B changes on 3, 4, 5; S changes on 5, 7 -> B only {3, 4}, S only {7}
        self.assertEqual((flips["b_flips"], flips["s_flips"], flips["b_only"], flips["s_only"]), (3, 2, 2, 1))
        self.assertEqual((flips["b_flip_rate"], flips["s_flip_rate"]), (0.3, 0.2))
        self.assertEqual(flips["mcnemar_p"], 1.0)  # 3 discordant items: min(1, 2 * 4 / 8)

    def test_items_one_arm_wins_in_both_draws(self):
        wins = self.block()["stable_wins"]
        # S right twice and B wrong twice: item 6; B right twice and S wrong twice: item 2
        self.assertEqual((wins["s_stable_better"], wins["b_stable_better"], wins["sign_test_p"]), (1, 1, 1.0))

    def test_two_draw_effect_and_the_second_s_draw_against_each_b_draw(self):
        b = self.block()
        # per-item mean(S) - mean(B): 0, 0, -1, +.5, -.5, 0, +1, +.5, 0, 0 -> sum 0.5, mean 0.05
        self.assertAlmostEqual(b["two_draw_effect"]["mean_diff"], 0.05)
        self.assertEqual(len(b["two_draw_effect"]["ci95_pct"]), 2)
        vs1, vs2 = b["s2_vs_b"]["vs_b1"], b["s2_vs_b"]["vs_b2"]
        # S2 right on 0, 1, 3, 6, 7: against B1 rescues 6, 7 and regressions 2, 4; against B2 rescues 3, 6, 7 and regressions 2, 5
        self.assertEqual((vs1["rescues"], vs1["regressions"]), (2, 2))
        self.assertEqual((vs2["rescues"], vs2["regressions"]), (3, 2))
        self.assertAlmostEqual(vs2["net_gain"], 0.1)

    def test_oracle_ceilings_have_two_floors(self):
        orc = self.block()["oracle"]
        # B1 or S1 right on 0-6 (.7); B1 or B2 right on 0-5 (.6); S1 or S2 right on 0, 1, 3, 5, 6, 7 (.6)
        self.assertEqual((orc["b_s_first_draws"], orc["null_b"], orc["null_s"]), (0.7, 0.6, 0.6))
        self.assertAlmostEqual(orc["headroom_over_null_b"], 0.1)
        self.assertAlmostEqual(orc["headroom_over_null_s"], 0.1)

    def test_reading_f1_and_holm_over_the_four_primary_tests(self):
        # 8 reading items: B wrong in both draws, S right in both -> S wins 8 items twice, B none: p = 2 / 2^8
        primary = [r for i in range(8) for r in (rd_row("B", i, 1, False, f1=0.2), rd_row("S", i, 1, True))]
        b_noise = [rd_row("B", i, 2, False, f1=0.2) for i in range(8)]
        s_noise = [rd_row("S", i, 2, True) for i in range(8)]
        mc_primary, mc_b, mc_s = self.rows()
        report = an.s_noise_reference(primary + mc_primary, b_noise + mc_b, s_noise + mc_s)
        reading = report["families"]["reading"]
        self.assertEqual(reading["stable_wins"]["s_stable_better"], 8)
        self.assertAlmostEqual(reading["stable_wins"]["sign_test_p"], 2 / 2 ** 8)
        # four primary tests (two families x flips and stable wins): the smallest p is multiplied by 4, the rest stay 1
        self.assertAlmostEqual(reading["stable_wins"]["sign_test_p_holm"], 4 * 2 / 2 ** 8)
        self.assertEqual(reading["flip_comparison"]["mcnemar_p_holm"], 1.0)
        self.assertEqual(report["families"]["mc"]["stable_wins"]["sign_test_p_holm"], 1.0)
        f1 = reading["mean_f1"]  # token_f1 is 1.0 when the exact match holds
        self.assertAlmostEqual(f1["b1"], 0.2)
        self.assertAlmostEqual(f1["s2"], 1.0)
        self.assertEqual((f1["mean_abs_b1_b2_change"], f1["mean_abs_s1_s2_change"]), (0.0, 0.0))
        self.assertIsNone(report["families"]["mc"]["mean_f1"])

    def test_missing_items_format_counts_and_a_wrong_replicate(self):
        primary, b_noise, s_noise = self.rows()
        s_noise = [dict(r, format_ok=(i != 3), completion_tokens=4096 if i == 3 else 300) for i, r in enumerate(s_noise)]
        report = an.s_noise_reference(primary, b_noise, s_noise[:8])
        self.assertEqual((report["items_shared"], report["items_missing"]), (8, 2))
        self.assertEqual(report["s2_format"], {"n": 8, "format_ok": 7, "cut_at_cap": 1})
        with self.assertRaises(ValueError):
            an.s_noise_reference(primary, b_noise, [mc_row("S", 0, 3, True)])

    def test_report_keys_match_the_registered_analysis(self):
        registered = dp.load_registration()["supplements"]["wide-s-r2"]["analysis"]
        report = self.report()
        self.assertEqual(tuple(registered["top_level"]), an.S_NOISE_TOP_KEYS)
        self.assertEqual(tuple(registered["family_metrics"]), an.S_NOISE_FAMILY_KEYS)
        self.assertEqual(set(report), set(registered["top_level"]))
        self.assertEqual(set(report["families"]["mc"]), set(registered["family_metrics"]))
        self.assertEqual(registered["primary_tests"], ["flip_comparison.mcnemar_p", "stable_wins.sign_test_p"])

    def test_the_report_prints_percentages_not_percentages_times_a_hundred(self):
        text = an.format_s_noise_report(self.report())
        for phrase in ("S drift S1->S2", "S-vs-S noise", "instability", "stable wins", "two-draw effect", "oracle B1/S1"):
            self.assertIn(phrase, text)
        line = next(line for line in text.splitlines() if "S-vs-S noise" in line)
        shown = [float(x) for x in re.findall(r"\d+\.\d", line)]
        self.assertTrue(shown and all(0 <= x <= 100 for x in shown), line)


class TestPlanConsistency(unittest.TestCase):
    def test_protocol_names_every_metric_the_analysis_reports(self):
        named = set(dp.load_protocol()["analysis"]["metrics"])
        report = an.analyze(worked_example_rows(), phase="core")
        reported = set(next(iter(report["families"]["mc"]["arms"].values()))) - {"arm"}
        reported |= {"item_ties", "semantic_audit_candidates_n", "baseline_noise", "parity_gate"}
        reported |= {f"oracle_routing.{key}" for key in ("observed", "null_from_baseline_replicates", "headroom_over_null")}
        self.assertEqual(reported - named, set(), "metrics reported but not named in the pre-registered plan")
        self.assertEqual(named - reported, set(), "metrics named in the plan but not reported")


def hypothesis_case():
    """Five Legal MC anchors, three replicates per arm (core). Item 0: reasoning_gap, input sufficient, B 0/3, S 3/3.
    Item 1: external_evidence_gap, input insufficient, B 0/3, O 3/3, K 0/3, S 0/3. Item 2: reasoning_gap, B 2/3
    (correct by majority: the historical failure is not reproduced), S 3/3. Item 3: no observed issue, B 3/3, S 1/3.
    Item 4: unresolved, B 1/3, S 1/3."""
    spec = {0: {"B": (0, 0, 0), "S": (1, 1, 1)}, 1: {"B": (0, 0, 0), "S": (0, 0, 0), "O": (1, 1, 1), "K": (0, 0, 0)},
            2: {"B": (1, 0, 1), "S": (1, 1, 1)}, 3: {"B": (1, 1, 1), "S": (1, 0, 0)}, 4: {"B": (1, 0, 0), "S": (0, 1, 0)}}
    rows = [mc_row(arm, item, n, bool(ok)) for item, arms in spec.items() for arm, draws in arms.items()
            for n, ok in enumerate(draws, 1)]

    def judged(outcome, labels=(), sufficiency="sufficient"):
        return {"diagnostic_outcome": outcome, "diagnostic_labels": list(labels), "gold_validity": "valid",
                "input_evidence_sufficiency": sufficiency, "hypothesis_status": {label: "hypothesis" for label in labels}}

    diagnosis = {f"{MC}:M000": judged("issue_observed", ("reasoning_gap",)),
                 f"{MC}:M001": judged("issue_observed", ("external_evidence_gap",), "insufficient"),
                 f"{MC}:M002": judged("issue_observed", ("reasoning_gap",)),
                 f"{MC}:M003": judged("no_observed_issue"), f"{MC}:M004": judged("unresolved")}
    return rows, diagnosis


class TestRecoveryByHypothesis(unittest.TestCase):
    def test_groups_count_rescues_per_arm_and_list_candidates_without_upgrading(self):
        rows, diagnosis = hypothesis_case()
        before = json.loads(json.dumps(diagnosis))
        report = an.recovery_by_hypothesis(rows, diagnosis, "d" * 64)
        self.assertEqual(tuple(report), an.HYPOTHESIS_REPORT_KEYS)
        self.assertEqual(diagnosis, before)
        reasoning = report["groups"]["reasoning_gap"]
        self.assertEqual((reasoning["anchors"], reasoning["b_majority_incorrect"], reasoning["not_reproduced"]), (2, 1, 1))
        self.assertEqual(reasoning["arms"]["S"], {"paired": 2, "rescues": 1, "regressions": 0})
        evidence = report["groups"]["external_evidence_gap"]
        self.assertEqual((evidence["arms"]["O"]["rescues"], evidence["arms"]["K"]["rescues"]), (1, 0))
        self.assertEqual(report["groups"]["no_observed_issue"]["arms"]["S"]["regressions"], 1)
        self.assertEqual(report["groups"]["unresolved"]["no_arm_correct"], 1)
        candidates = {(c["item_key"], c["label"]): c for c in report["contrast_candidates"]}
        self.assertEqual(candidates[(f"{MC}:M000", "reasoning_gap")]["status"], "hypothesis")
        self.assertIn((f"{MC}:M001", "external_evidence_gap"), candidates)
        retrieval = candidates[(f"{MC}:M001", "retrieval_gap")]
        self.assertEqual((retrieval["hypothesis_recorded"], retrieval["status"]), (False, None))
        self.assertIn((f"{MC}:M002", "run_instability"), candidates)  # B replicates 1, 0, 1 disagree
        self.assertNotIn((f"{MC}:M002", "reasoning_gap"), candidates)  # B is right by majority: no rescue

    def test_a_failure_that_is_not_reproduced_is_never_a_rescue(self):
        rows, diagnosis = hypothesis_case()
        report = an.recovery_by_hypothesis(rows, diagnosis, "d" * 64)
        self.assertEqual(report["not_reproduced"], [f"{MC}:M002"])
        self.assertEqual(report["groups"]["reasoning_gap"]["arms"]["S"]["rescues"], 1)  # item 0 only

    def test_a_matched_contrast_needs_the_registered_input_sufficiency(self):
        rows, diagnosis = hypothesis_case()
        diagnosis[f"{MC}:M000"]["input_evidence_sufficiency"] = "insufficient"
        report = an.recovery_by_hypothesis(rows, diagnosis, "d" * 64)
        self.assertNotIn((f"{MC}:M000", "reasoning_gap"),
                         {(c["item_key"], c["label"]) for c in report["contrast_candidates"]})

    def test_an_anchor_without_b_attempts_fails_closed(self):
        rows, diagnosis = hypothesis_case()
        with self.assertRaises(SystemExit):
            an.recovery_by_hypothesis([r for r in rows if r["item_id"] != "M003"], diagnosis, "d" * 64)


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
