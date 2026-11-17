"""Check the shipped notebook's actual cells without loading a student model.

Run from root: python3 -m unittest discover -s notebooks -p 'test_vinumqa_baselines.py'
Set FINQA_SCORER_FILE to the pinned upstream evaluate.py to run real scorer parity.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


NOTEBOOK = Path(__file__).with_name("vinumqa_distillation_baselines.ipynb")


def load_namespace(*tags: str) -> dict:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    namespace = {"__name__": "notebook_test"}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code" and set(tags) & set(cell.get("metadata", {}).get("tags", [])):
            exec("".join(cell["source"]), namespace)
    return namespace


def item(item_id: str, program: str = "add(12, 12)", answer: float = 24) -> dict:
    return {"id": item_id, "pre_text": ["Nhóm A có 12, nhóm B có 12."],
            "post_text": [], "table": [["nhóm", "số"], ["A", "12"], ["B", "12"]],
            "qa": {"question": "Tổng hai nhóm?", "program": program, "exe_ans": answer}}


class TestNotebookContract(unittest.TestCase):
    def test_every_code_cell_is_python_and_has_no_saved_output(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        self.assertEqual(notebook["nbformat"], 4)
        codes = [c for c in notebook["cells"] if c["cell_type"] == "code"]
        self.assertGreaterEqual(len(codes), 12)
        for cell in codes:
            ast.parse("".join(cell["source"]))
            self.assertEqual(cell["outputs"], [])
            self.assertIsNone(cell["execution_count"])

    def test_default_config_does_not_install_or_launch_gpu_work(self):
        ns = load_namespace("config")
        self.assertFalse(ns["RUN_P"])
        self.assertEqual(ns["TRAIN_ARMS"], ())
        self.assertEqual(ns["EVAL_ARMS"], ())
        self.assertFalse(ns["INSTALL_GPU_STACK"])
        self.assertFalse(ns["ALLOW_FINAL_TEST"])
        self.assertEqual(ns["EVAL_SPLIT"], "valid")

    def test_source_disjoint_split_uses_report_not_question_identity(self):
        ns = load_namespace("core-data")
        raw = {"train": [item("A/2020/page_1-1"), item("C/2022/page_2-2")],
               "valid": [item("B/2021/page_1-1"), item("C/2022/page_3-3")],
               "test": [item("C/2022/page_4-4")]}
        clean, audit = ns["make_clean_splits"](raw)
        self.assertEqual([x["id"] for x in clean["train"]], ["A/2020/page_1-1"])
        self.assertEqual([x["id"] for x in clean["valid"]], ["B/2021/page_1-1"])
        self.assertEqual(audit["counts"], {"train": 1, "valid": 1, "test": 1})

    def test_duplicate_identity_within_a_split_fails(self):
        ns = load_namespace("core-data")
        row = item("A/2020/page_1-1")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ns["make_clean_splits"]({"train": [row, row], "valid": [], "test": []})

    def test_prompt_does_not_serialize_gold_fields(self):
        ns = load_namespace("core-data")
        row = item("A/2020/page_1-1", "subtract(99331, 77119)", 22212)
        row["qa"]["gold_inds"] = "GOLD_RETRIEVAL_SENTINEL"
        prompt = ns["render_prompt"](row)
        for forbidden in ("99331", "77119", "22212", "GOLD_RETRIEVAL_SENTINEL", "exe_ans"):
            self.assertNotIn(forbidden, prompt)
        self.assertIn("Tổng hai nhóm?", prompt)

    def test_final_test_requires_explicit_flag(self):
        ns = load_namespace("core-data")
        with self.assertRaisesRegex(ValueError, "test"):
            ns["evaluation_rows"]({"test": [item("A/2020/page_1-1")]}, "test", False, None)

    def test_prompt_tokens_are_masked_and_overflow_is_explicit(self):
        ns = load_namespace("core-data")
        feature = ns["make_feature"]([1, 2, 3], [4, 5], 5)
        self.assertEqual(feature["labels"], [-100, -100, -100, 4, 5])
        self.assertIsNone(ns["make_feature"]([1, 2, 3], [4, 5], 4))

    def test_short_training_saves_a_full_checkpoint_before_finishing(self):
        ns = load_namespace("core-data")
        self.assertEqual(ns["training_save_steps"](20), 20)
        self.assertEqual(ns["training_save_steps"](-1), 50)
        self.assertEqual(ns["training_save_steps"](100), 50)

    def test_candidate_metadata_scores_are_not_trusted(self):
        ns = load_namespace("core-data", "core-scoring", "core-packs")
        rows = [item("A/2020/page_1-1"), item("B/2021/page_1-1")]
        candidates = [{"source_id": rows[0]["id"], "candidate_id": "bad", "program": "bad",
                       "ea": True, "pa": True},
                      {"source_id": rows[1]["id"], "candidate_id": "ok", "program": "add(12, 12)"}]

        def score(program, _row):
            return {"valid": program != "bad", "ea": program != "bad", "pa": program != "bad"}

        packs, audit = ns["make_training_packs"](rows, candidates, score, 42)
        for arm in ("G", "B", "C"):
            self.assertEqual([x["id"] for x in packs[arm]], [rows[1]["id"]])
        self.assertEqual(audit["matched_sources"], 1)
        self.assertEqual(len(packs["G_all"]), 2)

    def test_nontraining_candidate_is_rejected(self):
        ns = load_namespace("core-data", "core-scoring", "core-packs")
        with self.assertRaisesRegex(ValueError, "source"):
            ns["make_training_packs"]([item("A/2020/p-1")],
                [{"source_id": "TEST/2025/p-1", "candidate_id": "x", "program": "add(1, 2)"}],
                lambda _p, _r: {"valid": True, "ea": True, "pa": True}, 42)

    def test_inference_condition_changes_with_prompt_and_actual_model(self):
        ns = load_namespace("core-data")
        rows = [item("A/2020/p-1")]
        bind = ns["bind_inference_condition"]
        first = bind({}, rows, ["prompt one"], "model", "rev1", {}, None)
        changed_prompt = bind({}, rows, ["prompt two"], "model", "rev1", {}, None)
        changed_model = bind({}, rows, ["prompt one"], "model", "rev2", {}, None)
        self.assertNotEqual(first, changed_prompt)
        self.assertNotEqual(first, changed_model)

    def test_adapter_base_identity_must_match_training(self):
        ns = load_namespace("core-data")
        trained = {"model_id": "model", "model_revision": "rev1"}
        ns["validate_base_identity"](trained, "model", "rev1")
        with self.assertRaisesRegex(ValueError, "base model"):
            ns["validate_base_identity"](trained, "model", "rev2")

    def test_adapter_hash_tracks_weights_not_only_path(self):
        ns = load_namespace("core-data")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "adapter_config.json").write_text("{}")
            weights = path / "adapter_model.safetensors"
            weights.write_bytes(b"first")
            first = ns["adapter_fingerprint"](path)
            weights.write_bytes(b"second")
            self.assertNotEqual(first, ns["adapter_fingerprint"](path))


class TestUpstreamParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("FINQA_SCORER_FILE")
        if not path:
            raise unittest.SkipTest("Set FINQA_SCORER_FILE for real pinned-scorer parity")
        path = Path(path)
        expected = "845cd131cab843eceff256cf6d392978cc470a7da4a80107beb56027fdca5c13"
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("upstream scorer hash mismatch")
        spec = importlib.util.spec_from_file_location("finqa_upstream_test", path)
        cls.upstream = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.upstream)
        cls.ns = load_namespace("core-data", "core-scoring")

    def test_symbolic_equivalence_and_spurious_numeric_match(self):
        row = item("A/2020/page_1-1")
        correct = self.ns["score_program"]("add(12, 12)", row, self.upstream)
        spurious = self.ns["score_program"]("multiply(12, const_2)", row, self.upstream)
        self.assertTrue(correct["ea"] and correct["pa"])
        self.assertTrue(spurious["ea"])
        self.assertFalse(spurious["pa"])

    def test_invalid_program_stays_in_denominator(self):
        row = item("A/2020/page_1-1")
        for program in ("", "print(24)", "__import__('os')", "divide(12, 0)"):
            result = self.ns["score_program"](program, row, self.upstream)
            self.assertFalse(result["valid"])
            self.assertFalse(result["ea"])

    def test_numeric_string_gold_and_parenthesized_table_label(self):
        row = item("A/2020/page_1-1", "table_sum(Thu nhập (VND), none)", "24.0")
        row["table"] = [["Chỉ tiêu", "2022", "2023"], ["Thu nhập (VND)", "12", "12"]]
        result = self.ns["score_program"](row["qa"]["program"], row, self.upstream)
        self.assertTrue(result["valid"] and result["ea"] and result["pa"])


if __name__ == "__main__":
    unittest.main()
