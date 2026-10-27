"""Offline tests for the K2 evaluation and runner gates (openspec change diagnostic-k2-retrieval).

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_k2_heldout
Synthetic items and outcomes; the expected values are worked out by hand in the comments.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import analyze_diagnostic_router as ar
from code_benchmark import diagnostic_k2 as k2
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import run_k2_heldout as runner
from code_benchmark import vi_multimodel as v1

TOKENS = {"B": 10, "K": 100, "KS": 400, "O": 50}


def item(item_id: str) -> v1.EvalItem:
    return v1.EvalItem(dataset_id=k2.DATASET, source_dataset="bidlqa", item_id=item_id, replicate_id=dp.MAIN_REPLICATE,
                       task="reading", stratum="all", question="Hỏi?", passage_id=f"p-{item_id}",
                       prompt=v1.build_reading_prompt("Đoạn văn.", "Hỏi?"), gold_answer="A")


def k2_case():
    """Calibration c1, c2: B 0.0, K 0.6 with agreeing answers, KS 0.4 -> always-K 0.6 ties the K cascade (which
    returns K) and the tie goes to the more thorough cascade. Test items, both draws alike so rotation 2 repeats
    rotation 1:
    * t1: K answers agree, K 1.0 (exact), KS 0.5, B 0.0, O 1.0 (exact); own passage at rank 1;
    * t2: K answers differ, K 0.2, KS 0.9 (exact), B 0.0, O 1.0 (exact); own passage at rank 2;
    * t3: K answers differ, K 0.5, KS 0.3, B 0.1, O 0.8; own passage not ranked.
    Router (cascade): t1 -> K 1.0, t2 -> KS 0.9, t3 -> KS 0.3."""
    spec = {  # arm: (token-F1, exact, first and second prediction)
        "c1": {"B": (0.0, 0, "x0", "x0"), "K": (0.6, 0, "x", "x"), "KS": (0.4, 0, "z", "z"), "O": (1.0, 1, "o", "o")},
        "c2": {"B": (0.0, 0, "x0", "x0"), "K": (0.6, 0, "x", "x"), "KS": (0.4, 0, "z", "z"), "O": (1.0, 1, "o", "o")},
        "t1": {"B": (0.0, 0, "n", "n"), "K": (1.0, 1, "a", "a"), "KS": (0.5, 0, "s", "s"), "O": (1.0, 1, "o", "o")},
        "t2": {"B": (0.0, 0, "n", "n"), "K": (0.2, 0, "a", "b"), "KS": (0.9, 1, "s", "s"), "O": (1.0, 1, "o", "o")},
        "t3": {"B": (0.1, 0, "n", "n"), "K": (0.5, 0, "c", "d"), "KS": (0.3, 0, "s", "s"), "O": (0.8, 0, "o", "o")},
    }
    rows = []
    for item_id, arms in spec.items():
        for arm, (f1, em, first, second) in arms.items():
            for draw, prediction in ((1, first), (2, second)):
                rows.append({"dataset_id": k2.DATASET, "item_id": item_id, "replicate_id": f"{arm}-r{draw}", "arm": arm,
                             "token_f1": f1, "em": em, "prediction": prediction, "total_tokens": TOKENS[arm]})
    items = [item(item_id) for item_id in spec]
    ranks = {"c1": 1, "c2": None, "t1": 1, "t2": 2, "t3": None}
    manifest = {"manifest_sha256": "m" * 64, "retrieval_config_sha256": "r" * 64,
                "calibration_items": [f"{k2.DATASET}:c1", f"{k2.DATASET}:c2"],
                "retrieval": {f"{k2.DATASET}:{name}": {"own_rank": rank} for name, rank in ranks.items()}}
    procedure = {**json.loads(k2.PROCEDURE_PATH.read_text(encoding="utf-8")), "calibration_items": 2}
    registered = {"procedure_sha256": "p" * 64, "manifest_sha256": "m" * 64, "retrieval_config_sha256": "r" * 64}
    return procedure, registered, manifest, items, rows


def evaluate(**overrides):
    procedure, registered, manifest, items, rows = k2_case()
    protocol = json.loads(k2.PROTOCOL_PATH.read_text(encoding="utf-8"))
    return ar.evaluate_k2(procedure, overrides.get("digest", "p" * 64), registered, manifest, items,
                          overrides.get("rows", rows), protocol)


class TestStatistics(unittest.TestCase):
    def test_sign_flip_p(self):
        self.assertEqual(ar.sign_flip_p([]), 1.0)
        self.assertEqual(ar.sign_flip_p([0.0, 0.0]), 1.0)
        # ten equal positive differences: only all-plus or all-minus reach the observed sum, 2 / 1024 = 0.002
        p = ar.sign_flip_p([0.1] * 10)
        self.assertTrue(0.0005 < p < 0.006, p)
        self.assertEqual(p, ar.sign_flip_p([0.1] * 10))

    def test_bootstrap_of_a_constant(self):
        self.assertEqual(ar.bootstrap_mean_ci([0.5] * 10), [50.0, 50.0])
        self.assertIsNone(ar.bootstrap_mean_ci([]))


class TestK2Evaluation(unittest.TestCase):
    def test_calibration_choice_and_rule(self):
        report = evaluate()
        self.assertEqual(list(report), list(ar.K2_REPORT_KEYS))
        for rotation in ("1", "2"):
            calibration = report["calibration"][rotation]
            self.assertEqual((calibration["tied"], calibration["choice"]), (["always_K", "k_cascade"], "k_cascade"))
            self.assertEqual(calibration["calibration_tokens"], 2 * (10 + 100 + 100 + 400))
            self.assertEqual(calibration["rule"]["probe"]["arm"], "K")

    def test_policies_tests_and_regret(self):
        block = evaluate()["rotations"]["1"]
        self.assertEqual(block["router_arms"], {"K": 1, "KS": 2})
        policies = block["policies"]
        expected = {"router": (2.2 / 3, 2, (200 + 600 + 600) / 3), "always_B": (0.1 / 3, 0, 10),
                    "always_K": (1.7 / 3, 1, 100), "k_cascade": (2.2 / 3, 2, (200 + 600 + 600) / 3),
                    "always_KS": (1.7 / 3, 1, 400), "O": (2.8 / 3, 2, 50)}
        for policy, (f1, em, tokens) in expected.items():
            self.assertAlmostEqual(policies[policy]["mean_token_f1"], f1, msg=policy)
            self.assertEqual(policies[policy]["em_correct"], em, policy)
            self.assertAlmostEqual(policies[policy]["mean_total_tokens"], tokens, msg=policy)
        tests = block["tests"]
        # against always-K: differences 0, +0.7, -0.2; every sign pattern reaches |0.5|, so p = 1
        self.assertAlmostEqual(tests["router_vs_always_K"]["mean_token_f1_difference"], 0.5 / 3)
        self.assertEqual((tests["router_vs_always_K"]["items_differing"], tests["router_vs_always_K"]["sign_flip_p_holm"]),
                         (2, 1.0))
        self.assertEqual((tests["router_vs_always_K"]["em_rescues"], tests["router_vs_always_K"]["em_regressions"]), (1, 0))
        self.assertEqual((tests["router_vs_always_KS"]["em_rescues"], tests["router_vs_always_KS"]["em_regressions"]), (1, 0))
        self.assertEqual((block["best_in_hindsight"], block["regret"]), ("k_cascade", 0.0))
        hits, misses = block["by_retrieval"]["own_passage_in_top_2"], block["by_retrieval"]["own_passage_missed"]
        self.assertEqual((hits["items"], misses["items"]), (2, 1))
        self.assertAlmostEqual(hits["always_K"], 0.6)
        self.assertAlmostEqual(hits["always_KS"], 0.7)
        self.assertAlmostEqual(misses["O"], 0.8)
        self.assertEqual([d["item_key"].split(":")[1] for d in block["discordant"]], ["t1", "t2"])

    def test_rotation_two_repeats_and_retrieval_counts(self):
        report = evaluate()
        self.assertEqual(report["rotations"]["2"]["policies"]["router"], report["rotations"]["1"]["policies"]["router"])
        self.assertEqual(report["retrieval"]["test"], {"items": 3, "own_rank_1": 1, "own_in_top_2": 2, "own_not_ranked": 1})
        self.assertEqual(report["retrieval"]["calibration"]["own_not_ranked"], 1)

    def test_refusals(self):
        with self.assertRaises(SystemExit):
            evaluate(digest="x" * 64)  # another procedure than the registered one
        _, _, _, _, rows = k2_case()
        with self.assertRaises(SystemExit):
            evaluate(rows=[row for row in rows if row["replicate_id"] != "KS-r2"])  # a missing draw


class TestK2Gates(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "card.md").write_text("detail", encoding="utf-8")
        self.procedure = self.root / k2.PROCEDURE_PATH.relative_to(dp.ROOT)
        self.procedure.parent.mkdir(parents=True, exist_ok=True)
        self.procedure.write_bytes(k2.PROCEDURE_PATH.read_bytes())
        self.manifest = {name: name[0] * 64 for name in runner.FROZEN_KEYS}
        self.registration = {"card_ids": {"heldout": "MC-996"}, "card_files": {"heldout": "card.md"},
                             "frozen": dict(self.manifest),
                             "router": {"procedure_sha256": v1.sha256_file(self.procedure)}}
        campaign = dp.load_protocol()
        self.env = {"OPENAI_BASE_URL": f"http://{campaign['model']['endpoint_host']}{campaign['model']['endpoint_path']}",
                    "OPENAI_MODEL": campaign["model"]["requested_id"], "OPENAI_API_KEY": "k"}

    def gates(self, **overrides):
        args = {"manifest": self.manifest, "registration": self.registration}
        args.update(overrides)
        return {g.name: g for g in runner.evaluate_gates(dp.load_protocol(), args["manifest"], args["registration"],
                                                          self.env, card_text="## MC-996 — test\n", root=self.root)}

    def test_every_gate_passes_when_registered_and_fails_on_drift(self):
        self.assertTrue(all(g.ok for g in self.gates().values()), {n: g.detail for n, g in self.gates().items()})
        drifted = self.gates(manifest={**self.manifest, "retrieval_config_sha256": "x" * 64})["frozen_hashes"]
        self.assertEqual((drifted.ok, drifted.detail), (False, "differ: ['retrieval_config_sha256']"))
        self.assertFalse(self.gates(manifest={**self.manifest, "manifest_sha256": "x" * 64})["frozen_hashes"].ok)
        text = self.procedure.read_text(encoding="utf-8")
        self.procedure.write_text(text.replace('"calibration_items": 60', '"calibration_items": 30'), encoding="utf-8")
        gate = self.gates()["k2_procedure"]
        self.assertEqual((gate.ok, gate.detail), (False, "differs from the registration: ['procedure']"))
        self.assertFalse(self.gates(registration={**self.registration, "card_ids": {"heldout": "MC-997"}})
                         ["card_registered"].ok)


@unittest.skipUnless(k2.REGISTRATION_PATH.is_file(), "MC-96 is not registered yet")
class TestK2Registration(unittest.TestCase):
    def test_the_registration_matches_the_frozen_files_and_the_evaluator(self):
        registration = runner.load_registration()
        self.assertEqual(registration["router"]["report_keys"], list(ar.K2_REPORT_KEYS))
        self.assertEqual(registration["router"]["procedure_sha256"], v1.sha256_file(k2.PROCEDURE_PATH))
        frozen = registration["frozen"]
        self.assertEqual(frozen["k2_protocol_sha256"], v1.sha256_file(k2.PROTOCOL_PATH))
        self.assertEqual(frozen["retrieval_config_sha256"], v1.sha256_file(k2.RETRIEVAL_PATH))
        self.assertEqual(frozen["manifest_sha256"], k2.load_frozen_manifest()["manifest_sha256"])

    def test_limits_other_than_the_registered_ones_are_refused(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            runner.main(["--max-in-flight", "8"])
        self.assertIn("differs from the 4 registered for MC-96", err.getvalue())


if __name__ == "__main__":
    unittest.main()
