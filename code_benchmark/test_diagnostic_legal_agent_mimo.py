"""Offline tests for MC-116's inputs (diagnostic_legal_agent_mimo): protocol, harness overlays and manifest."""
from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

try:
    from code_benchmark import diagnostic_legal_agent_mimo as lm
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent_mimo as lm  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]


def _item(dataset: str, item_id: str, replicate: str, prompt: str) -> v1.EvalItem:
    return v1.EvalItem(dataset_id=dataset, source_dataset=dataset, item_id=item_id, replicate_id=replicate,
                       task="multiple_choice", stratum="s", question="q", passage_id="", prompt=prompt, gold_answer="A")


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.protocol = lm.load_protocol()

    def _load(self, protocol):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "protocol.json"
            path.write_text(json.dumps(protocol), encoding="utf-8")
            return lm.load_protocol(path)

    def test_the_registered_protocol_loads(self):
        self.assertEqual(self.protocol["model"]["model_id"], "mimo-v2.6-flash")
        self.assertEqual(tuple(self.protocol["draws"]), (1, 2))

    def test_other_draws_or_models_are_refused(self):
        for key, value in (("draws", [3, 4]), ("protocol_version", 2)):
            bad = copy.deepcopy(self.protocol)
            bad[key] = value
            with self.assertRaises(SystemExit):
                self._load(bad)
        bad = copy.deepcopy(self.protocol)
        bad["model"]["model_id"] = "Qwen3.5-9B-65K"
        with self.assertRaises(SystemExit):
            self._load(bad)

    def test_harness_overlays_change_only_the_model_route(self):
        dsh, omp = lm.harness_protocols(self.protocol)
        self.assertTrue(dsh["harness"]["profile"].endswith("dsh_profile_mimo_v1.yml"))
        self.assertEqual((dsh["harness"]["max_tokens"], dsh["harness"]["context_window"]), (16000, 65024))
        self.assertEqual((omp["harness"]["max_completion_tokens"], omp["harness"]["context_window"]), (16000, 65024))
        self.assertIn("zengo/mimo-v2.6-flash", omp["harness"]["argv"])
        self.assertNotIn("iec/Qwen3.5-9B-65K", omp["harness"]["argv"])
        # MC-112's and MC-113's tools, version and per-attempt limits stay
        self.assertEqual(dsh["harness"]["tools"], ["glob", "grep", "read"])
        self.assertEqual(omp["harness"]["version"], "omp/18.0.0")
        self.assertEqual((dsh["proxy"]["request_cap"], dsh["proxy"]["temperature"]), (30, 1.0))
        self.assertEqual(omp["proxy"]["request_timeout_seconds"], 600)

    def test_a_changed_profile_is_refused(self):
        bad = copy.deepcopy(self.protocol)
        bad["harnesses"]["dsh"]["harness"]["profile_sha256"] = "0" * 64
        with self.assertRaises(SystemExit):
            lm.harness_protocols(bad)


class ManifestTests(unittest.TestCase):
    def test_expand_is_item_major_draw_then_arm(self):
        arms = {arm: _item("d", "1", f"{arm}-r1", f"p-{arm}") for arm in ("DSHF", "OMPF", "B")}
        span = {arm: _item("s", "2", f"{arm}-r1", f"p-{arm}") for arm in ("DSHF", "OMPF", "C")}
        out = lm.expand({"M": [("d:1", arms)], "S": [("s:2", span)]})
        self.assertEqual([item.replicate_id for item in out],
                         ["DSHF-r1", "OMPF-r1", "B-r1", "DSHF-r2", "OMPF-r2", "B-r2",
                          "DSHF-r1", "OMPF-r1", "C-r1", "DSHF-r2", "OMPF-r2", "C-r2"])
        self.assertTrue(all(item.prompt == f"p-{item.replicate_id.split('-')[0]}" for item in out))

    def test_a_task_that_differs_from_mc115_is_refused(self):
        item = _item("d", "1", "DSHF-r1", "task")
        mine = v1.manifest_item(item)
        mc115 = {"items": [{**mine, "replicate_id": "DSHF-r3"}]}
        lm.check_against_mc115([item], mc115)
        changed = dataclasses.replace(item, prompt="another task")
        with self.assertRaises(SystemExit):
            lm.check_against_mc115([changed], mc115)
        with self.assertRaises(SystemExit):  # an MC-115 item and arm missing here
            lm.check_against_mc115([], mc115)

    def test_the_real_manifest_copies_mc115s_tasks(self):
        manifest, rebuilt = lm.build_manifest()
        self.assertEqual((manifest["item_count"], manifest["n"]), (646, 3876))
        self.assertEqual(manifest["arm_counts"], {"B": 492, "C": 800, "DSHF": 1292, "OMPF": 1292})
        self.assertEqual({item.replicate_id[-3:] for item in rebuilt.values()}, {"-r1", "-r2"})
        self.assertEqual(sum(1 for corpus in manifest["corpus_of"].values() if corpus == "v1"), 134)


if __name__ == "__main__":
    unittest.main()
