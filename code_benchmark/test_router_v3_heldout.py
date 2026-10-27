"""Offline tests for the router v3 held-out set, its runner gates and its evaluation (openspec change
diagnostic-router-v3). Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_router_v3_heldout
Synthetic items and outcomes except where a test says it rebuilds the committed manifest from local sources.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import analyze_diagnostic_router as ar
from code_benchmark import diagnostic_calibration as cal
from code_benchmark import diagnostic_heldout as dh
from code_benchmark import diagnostic_heldout_v3 as h3
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_router as router
from code_benchmark import run_router_v3_heldout as runner
from code_benchmark import vi_multimodel as v1

SOURCES_OK = all(path.is_file() for path in (dp.ROOT / "vmlu_mqa_v1.5/valid.jsonl", h3.VM14K_SOURCE,
                                             h3.BIDLQA_TRAIN_SOURCE, dp.ROOT / "v_legal_slsp/bidlqa/ViBidLQA_val.jsonl",
                                             dp.ROOT / "v_legal_slsp/bidlqa/ViBidLQA_test.jsonl",
                                             dp.ROOT / "data/bidlqa_val_manifest.csv"))


def item(dataset_id: str, item_id: str) -> v1.EvalItem:
    if dataset_id == h3.BIDLQA:
        task, prompt = "reading", dp.RD_HEAD + "Đoạn văn." + dp.RD_QUESTION + "Hỏi?" + dp.RD_TAIL
    else:
        task, prompt = "multiple_choice", dp.MC_HEAD + "Câu hỏi?\n\nA. một\nB. hai\nC. ba\nD. bốn" + dp.MC_TAIL
    return v1.EvalItem(dataset_id=dataset_id, source_dataset="test", item_id=item_id, replicate_id=dp.MAIN_REPLICATE,
                       task=task, stratum="s", question="Hỏi?", passage_id="p", prompt=prompt, gold_answer="A")


def v3_case():
    """VMLU: calibration c1, c2 (B wrong and consistent, S right) -> always-S; test t1 (B right and consistent,
    S wrong), t2 (B wrong and consistent, S right), t3 (B wrong with two different answers, S right). ViBidLQA
    train: calibration r1, r2 (B token-F1 1.0 twice, S 0.5) -> always-B, which ties the v2 cascade on score but
    not on tokens; test u1 likewise. Both rotations draw the same answers. Tokens: B 100, S 500."""
    mc, rd = h3.VMLU, h3.BIDLQA
    spec = {f"{mc}:c1": ([(False, "B")] * 2, [(True, "A")] * 2), f"{mc}:c2": ([(False, "C")] * 2, [(True, "A")] * 2),
            f"{mc}:t1": ([(True, "A")] * 2, [(False, "B")] * 2), f"{mc}:t2": ([(False, "B")] * 2, [(True, "A")] * 2),
            f"{mc}:t3": ([(False, "B"), (False, "C")], [(True, "A")] * 2)}
    for name in ("r1", "r2", "u1"):
        spec[f"{rd}:{name}"] = ([(True, "24 giờ")] * 2, [(False, "24 giờ kể từ"), (False, "48 giờ")])
    items, rows = [], []
    for key, arms in spec.items():
        dataset_id, item_id = key.split(":")
        items.append(item(dataset_id, item_id))
        for arm, draws in zip(("B", "S"), arms, strict=True):
            for n, (ok, answer) in enumerate(draws, 1):
                row = {"dataset_id": dataset_id, "item_id": item_id, "replicate_id": f"{arm}-r{n}", "arm": arm,
                       "prediction": answer, "total_tokens": 100 if arm == "B" else 500}
                row.update({"em": int(ok), "token_f1": 1.0 if ok else 0.5} if dataset_id == rd else {"correct": int(ok)})
                rows.append(row)
    manifest = {"manifest_sha256": "m" * 64,
                "calibration_items": {mc: [f"{mc}:c1", f"{mc}:c2"], rd: [f"{rd}:r1", f"{rd}:r2"]}}
    return items, rows, manifest


def evaluate(**overrides):
    items, rows, manifest = v3_case()
    procedure = cal.validate_procedure({**json.loads(cal.PROCEDURE_PATH.read_text(encoding="utf-8")),
                                        "calibration_items": 2})
    v2_rule = router.validate_rule(json.loads(dh.RULE_PATH.read_text(encoding="utf-8")), dp.load_protocol()["datasets"])
    arguments = {"procedure": procedure, "procedure_sha256": "p" * 64,
                 "registered": {"procedure_sha256": "p" * 64, "manifest_sha256": "m" * 64, "v2_rule_sha256": "r" * 64},
                 "manifest": manifest, "items": items, "rows": rows, "v2_rule": v2_rule, "v2_rule_sha256": "r" * 64,
                 "families": {"mc": [h3.VMLU], "reading": [h3.BIDLQA]}, "primary_family": "mc",
                 "datasets": [h3.BIDLQA, h3.VMLU]}
    arguments.update(overrides)
    return ar.evaluate_v3(**arguments)


class TestV3Protocol(unittest.TestCase):
    def test_the_committed_protocol_mirrors_the_campaign(self):
        protocol, campaign = h3.load_protocol(), dp.load_protocol()
        self.assertEqual({b: protocol[b] for b in h3.MIRRORED}, {b: campaign[b] for b in h3.MIRRORED})
        self.assertFalse(set(protocol["datasets"]) & set(campaign["datasets"]))

    def test_another_transport_or_calibration_size_fails(self):
        for change, message in ((lambda p: p["transport"].update(temperature=0.0), "['transport'] differ"),
                                (lambda p: p["sampling"][h3.VM14K].update(calibration=50), "calibration items")):
            protocol = json.loads(h3.PROTOCOL_PATH.read_text(encoding="utf-8"))
            change(protocol)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "protocol.json"
                path.write_text(json.dumps(protocol), encoding="utf-8")
                with self.assertRaises(SystemExit) as caught:
                    h3.load_protocol(path)
            self.assertIn(message, str(caught.exception))

    @unittest.skipUnless(SOURCES_OK and h3.MANIFEST_PATH.is_file(), "sources or the frozen v3 manifest are missing")
    def test_the_frozen_manifest_rebuilds_from_the_sources(self):
        manifest, rebuilt = h3.build_manifest()
        self.assertEqual(manifest, h3.load_frozen_manifest())
        self.assertEqual((manifest["item_count"], manifest["n"]), (1080, 4320))
        self.assertEqual(manifest["dataset_counts"], {h3.BIDLQA: 360, h3.VMLU: 360, h3.VM14K: 360})
        self.assertEqual(len(dp.verify_manifest_rows(manifest, rebuilt)), 4320)
        base, calibration = h3.sample_items(h3.load_protocol())
        keys = {dp.item_key(i.dataset_id, i.item_id) for i in base}
        self.assertEqual({d: len(k) for d, k in calibration.items()}, {h3.BIDLQA: 60, h3.VMLU: 60, h3.VM14K: 60})
        self.assertTrue({k for ks in calibration.values() for k in ks} <= keys)
        mc94 = {dp.item_key(i.dataset_id, i.item_id) for i in dh.sample_items(dh.load_protocol())}
        self.assertFalse(keys & mc94)  # no MC-94 item, so no router has seen these VMLU items
        self.assertTrue(all(router.features_of(router.request_view(i)) for i in base))


class TestV3Evaluation(unittest.TestCase):
    def test_calibration_chooses_per_dataset_and_never_counts_calibration_items(self):
        report = evaluate()
        self.assertEqual(tuple(report), ar.V3_REPORT_KEYS)
        first = report["calibration"]["1"]
        self.assertEqual(first["choices"], {h3.BIDLQA: "always_B", h3.VMLU: "always_S"})
        self.assertNotIn("probe", first["rule"])  # no dataset chose the cascade
        self.assertEqual(first["datasets"][h3.VMLU]["calibration_tokens"], 2 * (100 + 100 + 500))
        mc = report["families"]["mc"]["rotations"]["1"]
        self.assertEqual(mc["items"], 3)  # t1-t3; c1 and c2 calibrate only
        # v3 (always-S): t2, t3 right; v2: t1 (agree, B), t3 (escalated) right; B: t1; S: t2, t3
        self.assertEqual([mc["policies"][p]["correct"] for p in ar.V3_POLICIES], [2, 2, 1, 2])
        self.assertEqual((mc["tests"]["v3_vs_v2"]["rescues"], mc["tests"]["v3_vs_v2"]["regressions"]), (1, 1))
        self.assertEqual((mc["tests"]["v3_vs_always_S"]["rescues"], mc["tests"]["v3_vs_always_S"]["regressions"]), (0, 0))
        self.assertAlmostEqual(mc["policies"]["v3"]["mean_total_tokens"], 500)
        self.assertAlmostEqual(mc["policies"]["v2"]["mean_total_tokens"], (200 + 200 + 700) / 3)
        self.assertEqual(mc["v3_arms"], {"S": 3})
        vmlu = mc["by_dataset"][h3.VMLU]
        # v2 and always-S tie at 2/3; v2 is cheaper, so it is the best policy in hindsight, and v3 loses nothing
        self.assertEqual((vmlu["choice"], vmlu["best_in_hindsight"], vmlu["regret"]), ("always_S", "v2", 0.0))
        self.assertEqual(len(report["families"]["mc"]["discordant_rotation_1"]), 3)
        reading = report["families"]["reading"]
        self.assertEqual(reading["rotations"]["1"]["by_dataset"][h3.BIDLQA]["scores"]["v3"], 1.0)
        self.assertEqual(reading["discordant_rotation_1"], [
            {"item_key": f"{h3.BIDLQA}:u1", "arm": "B", "probe_agrees": True, "v3": True, "v2": True,
             "always_B": True, "always_S": False}])

    def test_a_changed_procedure_or_stray_calibration_reports_nothing(self):
        with self.assertRaises(SystemExit) as caught:
            evaluate(procedure_sha256="x" * 64)
        self.assertIn(f"{'x' * 64} differs from the registered {'p' * 64}", str(caught.exception))
        _, _, manifest = v3_case()
        manifest["calibration_items"][h3.VMLU].append(f"{h3.VMLU}:elsewhere")
        with self.assertRaises(SystemExit):
            evaluate(manifest=manifest)


class TestV3Gates(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "card.md").write_text("detail", encoding="utf-8")
        self.paths = {}
        for name, source in (("procedure", cal.PROCEDURE_PATH), ("v2_rule", dh.RULE_PATH)):
            target = self.root / source.relative_to(dp.ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            self.paths[name] = target
        self.manifest = {"heldout_protocol_sha256": "h" * 64, "campaign_protocol_sha256": "p" * 64,
                         "prompt_templates_sha256": "t" * 64, "manifest_sha256": "m" * 64}
        self.registration = {"card_ids": {"heldout": "MC-995"}, "card_files": {"heldout": "card.md"},
                             "frozen": dict(self.manifest),
                             "router": {f"{name}_sha256": v1.sha256_file(path) for name, path in self.paths.items()}}
        campaign = dp.load_protocol()
        self.env = {"OPENAI_BASE_URL": f"http://{campaign['model']['endpoint_host']}{campaign['model']['endpoint_path']}",
                    "OPENAI_MODEL": campaign["model"]["requested_id"], "OPENAI_API_KEY": "k"}

    def gates(self, **overrides):
        args = {"manifest": self.manifest, "registration": self.registration}
        args.update(overrides)
        return {g.name: g for g in runner.evaluate_gates(dp.load_protocol(), args["manifest"], args["registration"],
                                                          self.env, card_text="## MC-995 — test\n", root=self.root)}

    def test_every_gate_passes_when_registered_and_fails_on_drift(self):
        self.assertTrue(all(g.ok for g in self.gates().values()), {n: g.detail for n, g in self.gates().items()})
        drifted = self.gates(manifest={**self.manifest, "manifest_sha256": "x" * 64})["frozen_hashes"]
        self.assertEqual((drifted.ok, drifted.detail), (False, "differ: ['manifest_sha256']"))
        text = self.paths["procedure"].read_text(encoding="utf-8")
        self.paths["procedure"].write_text(text.replace('"calibration_items": 60', '"calibration_items": 30'),
                                           encoding="utf-8")
        gate = self.gates()["router_procedure"]
        self.assertEqual((gate.ok, gate.detail), (False, "differ from the registration: ['procedure']"))


@unittest.skipUnless(h3.REGISTRATION_PATH.is_file(), "MC-95 is not registered yet")
class TestV3Registration(unittest.TestCase):
    def test_the_registration_matches_the_frozen_files_and_the_evaluator(self):
        registration = runner.load_registration()
        self.assertEqual(registration["router"]["report_keys"], list(ar.V3_REPORT_KEYS))
        self.assertEqual(registration["router"]["procedure_sha256"], v1.sha256_file(cal.PROCEDURE_PATH))
        self.assertEqual(registration["router"]["v2_rule_sha256"], v1.sha256_file(dh.RULE_PATH))
        frozen = registration["frozen"]
        self.assertEqual(frozen["heldout_protocol_sha256"], v1.sha256_file(h3.PROTOCOL_PATH))
        self.assertEqual(frozen["manifest_sha256"], h3.load_frozen_manifest()["manifest_sha256"])

    def test_limits_other_than_the_registered_ones_are_refused(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            runner.main(["--max-in-flight", "8"])
        self.assertIn("differs from the 4 registered for MC-95", err.getvalue())


if __name__ == "__main__":
    unittest.main()
