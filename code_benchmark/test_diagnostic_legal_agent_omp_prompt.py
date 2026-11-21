"""Offline tests of MC-117's inputs (protocol, OMPS specifications, manifest).

    .venv/bin/python -m unittest code_benchmark.test_diagnostic_legal_agent_omp_prompt
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from code_benchmark import diagnostic_legal_agent_omp_prompt as lp
from code_benchmark import vi_multimodel as v1


def item(item_id: str, arm: str, prompt: str = "p") -> v1.EvalItem:
    return v1.EvalItem(dataset_id="d", source_dataset="d", item_id=item_id, replicate_id=f"{arm}-r1",
                       task="multiple_choice", stratum="s", question="q", passage_id="", prompt=prompt, gold_answer="A")


class TestOmpsSpecification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = lp.load_protocol()

    def test_only_the_system_prompt_is_added(self):
        for model in lp.MODELS:
            base = lp.base_omp_protocol(self.protocol, model)
            omps = lp.omp_protocol(self.protocol, model)
            text = lp.prompt_text(self.protocol, model)
            self.assertEqual(omps["harness"]["argv"], [*base["harness"]["argv"], lp.SYSTEM_PROMPT_FLAG, text])
            for key in set(base["harness"]) - {"argv"}:
                self.assertEqual(omps["harness"][key], base["harness"][key], key)
            for key in set(base["proxy"]) - {"system_prompt_sha256"}:
                self.assertEqual(omps["proxy"][key], base["proxy"][key], key)
            self.assertIn("DeepSeek Harness", text)

    def test_a_changed_prompt_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = self.protocol["models"]["qwen"]
            target = root / spec["prompt_file"]
            target.parent.mkdir(parents=True)
            shutil.copyfile(lp.ROOT / spec["prompt_file"], target)
            self.assertTrue(lp.prompt_text(self.protocol, "qwen", root).startswith("You are an AI agent"))
            target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaises(SystemExit):
                lp.prompt_text(self.protocol, "qwen", root)

    def test_unknown_model(self):
        with self.assertRaises(SystemExit):
            lp.model_spec(self.protocol, "gpt")


class TestManifest(unittest.TestCase):
    def test_expand_copies_ompf_items(self):
        parts = {"M": [("d:1", {"OMPF": item("1", "OMPF"), "DSHF": item("1", "DSHF")})],
                 "S": [("d:2", {"OMPF": item("2", "OMPF")})]}
        items = lp.expand(parts)
        self.assertEqual([i.replicate_id for i in items], ["OMPS-r1", "OMPS-r2", "OMPS-r1", "OMPS-r2"])
        self.assertTrue(all(i.prompt == "p" for i in items))

    def test_check_against_mc115(self):
        items = lp.expand({"M": [("d:1", {"OMPF": item("1", "OMPF")})], "S": []})
        row = {**v1.manifest_item(item("1", "OMPF")), "replicate_id": "OMPF-r3"}
        lp.check_against_mc115(items, {"items": [row, {**row, "replicate_id": "DSHF-r3", "item_id": "9"}]})
        drifted = lp.expand({"M": [("d:1", {"OMPF": item("1", "OMPF", prompt="other")})], "S": []})
        with self.assertRaises(SystemExit):
            lp.check_against_mc115(drifted, {"items": [row]})
        with self.assertRaises(SystemExit):
            lp.check_against_mc115(items, {"items": [row, {**row, "item_id": "2"}]})

    def test_counts(self):
        manifest, rebuilt = lp.build_manifest()
        self.assertEqual((manifest["item_count"], manifest["n"]), (646, 1292))
        self.assertEqual(manifest["arm_counts"], {"OMPS": 1292})
        self.assertEqual(len(rebuilt), 1292)


if __name__ == "__main__":
    unittest.main()
