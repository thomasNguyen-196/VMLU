"""Offline tests for the router v2 held-out set, its runner gates and its evaluation (openspec change
diagnostic-router-v2). Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_router_v2_heldout
Synthetic items and outcomes except where a test says it rebuilds the committed manifest from local sources.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import analyze_diagnostic_router as ar
from code_benchmark import diagnostic_heldout as dh
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_router as router
from code_benchmark import run_router_v2_heldout as runner
from code_benchmark import vi_multimodel as v1

SOURCES_OK = all(path.is_file() for path in (dp.ROOT / "vmlu_mqa_v1.5/valid.jsonl",
                                             dp.ROOT / "v_legal_slsp/bidlqa/ViBidLQA_val.jsonl",
                                             dp.ROOT / "data/bidlqa_val_manifest.csv"))
DROP = "vi-multimodel-v1-vi-drop-200"
V1_RULE = {"router_id": "v1", "conditions": [{"arm": "S", "targets": ["reasoning_gap"], "when": {"dataset": [DROP]}}],
           "default": {"arm": "B", "targets": []}}


def item(dataset_id: str, item_id: str) -> v1.EvalItem:
    if dataset_id == dh.VMLU:
        task, prompt = "multiple_choice", dp.MC_HEAD + "Câu hỏi?\n\nA. một\nB. hai\nC. ba\nD. bốn" + dp.MC_TAIL
    else:
        task, prompt = "reading", dp.RD_HEAD + "Đoạn văn." + dp.RD_QUESTION + "Hỏi?" + dp.RD_TAIL
    return v1.EvalItem(dataset_id=dataset_id, source_dataset="test", item_id=item_id, replicate_id=dp.MAIN_REPLICATE,
                       task=task, stratum="s", question="Hỏi?", passage_id="p", prompt=prompt, gold_answer="A")


def heldout_case():
    """VMLU m1: B answers A, A (agree, right), S1 wrong, S2 right. m2: B answers B, C (disagree, wrong), S1 right,
    S2 wrong. m3: B answers D, D (agree, wrong), S right twice. ViBidLQA r1: B answers '24 giờ' (right) and
    '24 giờ kể từ' (wrong): they disagree, S1 right, S2 wrong. Tokens: B 100, S 500."""
    items = [item(dh.VMLU, "m1"), item(dh.VMLU, "m2"), item(dh.VMLU, "m3"), item(dh.BIDLQA, "r1")]
    spec = {f"{dh.VMLU}:m1": {"B": [(1, "A"), (1, "A")], "S": [(0, "B"), (1, "A")]},
            f"{dh.VMLU}:m2": {"B": [(0, "B"), (0, "C")], "S": [(1, "A"), (0, "D")]},
            f"{dh.VMLU}:m3": {"B": [(0, "D"), (0, "D")], "S": [(1, "A"), (1, "A")]},
            f"{dh.BIDLQA}:r1": {"B": [(1, "24 giờ"), (0, "24 giờ kể từ")], "S": [(1, "24 giờ"), (0, "48 giờ")]}}
    rows = []
    for key, arms in spec.items():
        dataset_id, item_id = key.split(":")
        for arm, draws in arms.items():
            for n, (ok, answer) in enumerate(draws, 1):
                row = {"dataset_id": dataset_id, "item_id": item_id, "replicate_id": f"{arm}-r{n}", "arm": arm,
                       "prediction": answer, "total_tokens": 100 if arm == "B" else 500}
                if dataset_id == dh.BIDLQA:
                    row.update({"em": ok, "token_f1": 1.0 if ok else 0.5})
                else:
                    row["correct"] = ok
                rows.append(row)
    return items, rows


def evaluate(**overrides):
    items, rows = heldout_case()
    the_rule = router.validate_rule(json.loads(dh.RULE_PATH.read_text(encoding="utf-8")), dp.load_protocol()["datasets"])
    arguments = {"rule": the_rule, "rule_sha256": "r" * 64, "registered": {"rule_sha256": "r" * 64, "manifest_sha256": "m" * 64},
                 "manifest_sha256": "m" * 64, "items": items, "rows": rows,
                 "v1_rule": router.validate_rule(copy.deepcopy(V1_RULE), dp.load_protocol()["datasets"]),
                 "families": {"mc": [dh.VMLU], "reading": [dh.BIDLQA]}, "primary_family": "mc"}
    arguments.update(overrides)
    return ar.evaluate_heldout(**arguments)


class TestHeldoutProtocol(unittest.TestCase):
    def test_the_committed_protocol_mirrors_the_campaign(self):
        protocol = dh.load_protocol()
        campaign = dp.load_protocol()
        self.assertEqual({block: protocol[block] for block in dh.MIRRORED}, {block: campaign[block] for block in dh.MIRRORED})
        self.assertFalse(set(protocol["datasets"]) & set(campaign["datasets"]))

    def test_a_protocol_with_another_transport_fails(self):
        protocol = json.loads(dh.PROTOCOL_PATH.read_text(encoding="utf-8"))
        protocol["transport"]["temperature"] = 0.0
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "protocol.json"
            path.write_text(json.dumps(protocol), encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                dh.load_protocol(path)
        self.assertIn("['transport'] differ from the campaign protocol", str(caught.exception))

    def test_the_frozen_rule_is_a_committed_v2_candidate_with_a_probe(self):
        candidates = [path.read_bytes() for path in (dh.DATA_DIR / "router_candidates").glob("*.json")]
        self.assertIn(dh.RULE_PATH.read_bytes(), candidates)
        self.assertIn("probe", router.load_rule(dh.RULE_PATH, dp.load_protocol()["datasets"])[0])

    @unittest.skipUnless(SOURCES_OK, "VMLU valid or ViBidLQA val sources are not available")
    def test_the_frozen_manifest_rebuilds_from_the_sources(self):
        manifest, rebuilt = dh.build_manifest()
        self.assertEqual(manifest, dh.load_frozen_manifest())
        self.assertEqual((manifest["item_count"], manifest["n"]), (600, 2400))
        self.assertEqual(manifest["dataset_counts"], {dh.BIDLQA: 300, dh.VMLU: 300})
        self.assertEqual(len(dp.verify_manifest_rows(manifest, rebuilt)), 2400)
        base = dh.sample_items(dh.load_protocol())
        self.assertEqual(base, dh.sample_items(dh.load_protocol()))  # the draw is deterministic
        self.assertTrue(all(dp.parse_frozen_prompt(i) for i in base))


class TestHeldoutGates(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "card.md").write_text("detail", encoding="utf-8")
        self.rule_path = self.root / dh.RULE_PATH.relative_to(dp.ROOT)
        self.rule_path.parent.mkdir(parents=True)
        self.rule_path.write_bytes(dh.RULE_PATH.read_bytes())
        self.manifest = {"heldout_protocol_sha256": "h" * 64, "campaign_protocol_sha256": "p" * 64,
                         "prompt_templates_sha256": "t" * 64, "manifest_sha256": "m" * 64}
        self.registration = {"card_ids": {"heldout": "MC-994"}, "card_files": {"heldout": "card.md"},
                             "frozen": dict(self.manifest), "router": {"rule_sha256": v1.sha256_file(self.rule_path)}}
        campaign = dp.load_protocol()
        self.env = {"OPENAI_BASE_URL": f"http://{campaign['model']['endpoint_host']}{campaign['model']['endpoint_path']}",
                    "OPENAI_MODEL": campaign["model"]["requested_id"], "OPENAI_API_KEY": "k"}

    def gates(self, **overrides):
        args = {"manifest": self.manifest, "registration": self.registration}
        args.update(overrides)
        return {g.name: g for g in runner.evaluate_gates(dp.load_protocol(), args["manifest"], args["registration"],
                                                          self.env, card_text="## MC-994 — test\n", root=self.root)}

    def test_every_gate_passes_when_registered_and_fails_on_drift(self):
        self.assertTrue(all(g.ok for g in self.gates().values()), {n: g.detail for n, g in self.gates().items()})
        drifted = self.gates(manifest={**self.manifest, "manifest_sha256": "x" * 64})["frozen_hashes"]
        self.assertEqual((drifted.ok, drifted.detail), (False, "differ: ['manifest_sha256']"))
        self.rule_path.write_text(self.rule_path.read_text(encoding="utf-8").replace("v2b", "v2x"), encoding="utf-8")
        self.assertFalse(self.gates()["router_rule"].ok)

    def test_a_rule_without_probe_is_refused(self):
        self.rule_path.write_text(json.dumps(V1_RULE), encoding="utf-8")
        registration = {**self.registration, "router": {"rule_sha256": v1.sha256_file(self.rule_path)}}
        self.assertIn("declares no probe", self.gates(registration=registration)["router_rule"].detail)


class TestHeldoutEvaluation(unittest.TestCase):
    def test_policies_tests_tokens_and_probe_split_of_the_primary_family(self):
        report = evaluate()
        self.assertEqual(tuple(report), ar.HELDOUT_REPORT_KEYS)
        self.assertTrue(report["v1_equals_always_B"])
        first = report["families"]["mc"]["rotations"]["1"]
        policies, tests = first["policies"], first["tests"]
        # v2: m1 B1 right (agree), m2 escalated to S1 right, m3 B1 wrong (agree) -> 2/3; B 1/3; S1 2/3
        self.assertEqual([policies[p]["correct"] for p in ("v2", "always_B", "always_S")], [2, 1, 2])
        self.assertEqual((tests["v2_vs_always_B"]["rescues"], tests["v2_vs_always_B"]["regressions"]), (1, 0))
        self.assertEqual((tests["v2_vs_always_S"]["rescues"], tests["v2_vs_always_S"]["regressions"]), (1, 1))
        # tokens: m1 B1 + B2 = 200, m2 B1 + B2 + S1 = 700, m3 200 -> 1100 / 3
        self.assertAlmostEqual(policies["v2"]["mean_total_tokens"], 1100 / 3)
        self.assertAlmostEqual(first["escalated_share"], 1 / 3)
        self.assertEqual(first["probe_split"]["disagree"], {"items": 1, "B_accuracy": 0.0, "S_accuracy": 1.0})
        self.assertEqual(report["families"]["mc"]["rotations"]["2"]["policies"]["v2"]["correct"], 1)  # m1 B2 only

    def test_the_reading_family_carries_token_f1_and_no_discordance_here(self):
        reading = evaluate()["families"]["reading"]
        first = reading["rotations"]["1"]
        self.assertEqual(first["policies"]["v2"]["correct"], 1)  # escalated: the B answers differ, S1 is right
        self.assertEqual(first["mean_token_f1"], {"v2": 1.0, "always_B": 1.0, "always_S": 1.0})
        self.assertEqual(reading["discordant_rotation_1"], [])

    def test_a_changed_rule_or_manifest_reports_nothing(self):
        with self.assertRaises(SystemExit) as caught:
            evaluate(rule_sha256="x" * 64)
        self.assertIn(f"{'x' * 64} differs from the registered {'r' * 64}", str(caught.exception))
        with self.assertRaises(SystemExit):
            evaluate(manifest_sha256="y" * 64)


@unittest.skipUnless(dh.REGISTRATION_PATH.is_file(), "MC-94 is not registered yet")
class TestHeldoutRegistration(unittest.TestCase):
    def test_the_registration_matches_the_frozen_files_and_the_evaluator(self):
        registration = runner.load_registration()
        self.assertEqual(registration["router"]["report_keys"], list(ar.HELDOUT_REPORT_KEYS))
        self.assertEqual(registration["router"]["rule_sha256"], v1.sha256_file(dh.RULE_PATH))
        frozen = registration["frozen"]
        self.assertEqual(frozen["heldout_protocol_sha256"], v1.sha256_file(dh.PROTOCOL_PATH))
        self.assertEqual(frozen["manifest_sha256"], dh.load_frozen_manifest()["manifest_sha256"])

    def test_limits_other_than_the_registered_ones_are_refused(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            runner.main(["--max-in-flight", "8"])
        self.assertIn("differs from the 4 registered for MC-94", err.getvalue())


if __name__ == "__main__":
    unittest.main()
