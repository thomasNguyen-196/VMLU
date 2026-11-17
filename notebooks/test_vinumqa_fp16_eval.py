"""Offline contracts for the FP16 eval-only notebook; no GPU or model is loaded."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


NOTEBOOK = Path(__file__).with_name("vinumqa_fp16_eval.ipynb")


def namespace(*tags):
    nb = json.loads(NOTEBOOK.read_text())
    ns = {"__name__": "fp16_notebook_test", "Path": Path}
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        cell_tags = cell.get("metadata", {}).get("tags", [])
        if not set(cell_tags) & set(tags):
            continue
        tree = ast.parse("".join(cell["source"]))
        if "environment" in cell_tags:
            tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        exec(compile(tree, str(cell_tags), "exec"), ns)
    return ns


def fixture(root):
    """Real files at a controlled boundary; not a mocked artifact validator."""
    condition = {"arm": "G_all", "model_id": "Qwen/model", "model_revision": "rev1",
                 "split_hash": "split1"}
    parent = Path(root) / "training" / "G_all" / "seed-42-known"
    adapter = parent / "adapter"
    adapter.mkdir(parents=True)
    (parent / "condition.json").write_text(json.dumps(condition))
    digest = hashlib.sha256(json.dumps(condition, ensure_ascii=False, sort_keys=True,
                                      allow_nan=False).encode()).hexdigest()
    (parent / "training_complete.json").write_text(
        json.dumps({"condition_hash": digest, "optimizer_step": 20}))
    (adapter / "adapter_config.json").write_text('{"peft_type":"LORA"}')
    (adapter / "adapter_model.safetensors").write_bytes(b"controlled weight bytes")
    weights_digest = hashlib.sha256()
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        weights_digest.update(name.encode())
        weights_digest.update((adapter / name).read_bytes())
    expected = {"condition_hash": digest, "adapter_sha256": weights_digest.hexdigest(),
                "model_id": "Qwen/model", "model_revision": "rev1", "split_hash": "split1",
                "optimizer_step": 20}
    return adapter, expected


class TestFp16Evaluation(unittest.TestCase):
    def test_t4_uses_fp16_and_rejects_emulated_bf16(self):
        ns = namespace("core-data", "eval-source-core")
        self.assertIn("select_compute_precision", ns)
        choose = ns["select_compute_precision"]
        self.assertEqual(choose("float16", (7, 5)), "float16")
        self.assertEqual(choose("auto", (7, 5)), "float16")
        with self.assertRaisesRegex(ValueError, "native"):
            choose("bfloat16", (7, 5))

    def test_explicit_fp16_is_kept_even_on_ampere(self):
        ns = namespace("core-data", "eval-source-core")
        self.assertIn("select_compute_precision", ns)
        self.assertEqual(ns["select_compute_precision"]("float16", (8, 0)), "float16")
        self.assertEqual(ns["select_compute_precision"]("bfloat16", (8, 0)), "bfloat16")

    def test_eval_profile_has_no_training_or_final_test(self):
        ns = namespace("config")
        self.assertEqual(ns["TRAIN_ARMS"], ())
        self.assertEqual(ns["EVAL_ARMS"], ("G_all",))
        self.assertTrue(ns["RUN_P"])
        self.assertFalse(ns["ALLOW_FINAL_TEST"])
        self.assertEqual(ns["MAX_EVAL_ITEMS"], 32)

    def test_real_source_adapter_validates(self):
        ns = namespace("environment", "core-data", "eval-source-core")
        self.assertIn("validate_source_adapter", ns)
        with tempfile.TemporaryDirectory() as root:
            adapter, expected = fixture(root)
            result = ns["validate_source_adapter"](adapter, expected)
            self.assertEqual(result["optimizer_step"], 20)
            self.assertEqual(result["condition_hash"], expected["condition_hash"])

    def test_changed_weights_are_rejected(self):
        ns = namespace("environment", "core-data", "eval-source-core")
        self.assertIn("validate_source_adapter", ns)
        with tempfile.TemporaryDirectory() as root:
            adapter, expected = fixture(root)
            (adapter / "adapter_model.safetensors").write_bytes(b"replaced")
            with self.assertRaisesRegex(ValueError, "adapter"):
                ns["validate_source_adapter"](adapter, expected)

    def test_other_split_cannot_be_silently_evaluated(self):
        ns = namespace("environment", "core-data", "eval-source-core")
        self.assertIn("validate_source_adapter", ns)
        with tempfile.TemporaryDirectory() as root:
            adapter, expected = fixture(root)
            expected["split_hash"] = "different-split"
            with self.assertRaisesRegex(ValueError, "split"):
                ns["validate_source_adapter"](adapter, expected)

    def test_resolver_uses_existing_verified_adapter_without_download(self):
        ns = namespace("environment", "core-data", "eval-source-core")
        self.assertIn("resolve_source_adapter", ns)
        with tempfile.TemporaryDirectory() as root:
            adapter, expected = fixture(root)

            def unexpected_download(_handle):
                raise AssertionError("Existing verified artifact must be reused")

            result = ns["resolve_source_adapter"](
                [adapter], [], "owner/notebook/versions/6", expected, unexpected_download)
            self.assertEqual(Path(result["path"]), adapter)

    def test_resolver_recovers_missing_adapter_from_pinned_version(self):
        ns = namespace("environment", "core-data", "eval-source-core")
        self.assertIn("resolve_source_adapter", ns)
        with tempfile.TemporaryDirectory() as root:
            adapter, expected = fixture(root)

            def download(handle):
                if handle != "owner/notebook/versions/6":
                    raise AssertionError("Output version must remain pinned")
                return root

            result = ns["resolve_source_adapter"](
                [], [], "owner/notebook/versions/6", expected, download)
            self.assertEqual(Path(result["path"]), adapter)

    def test_pairing_rejects_an_inference_dtype_change(self):
        ns = namespace("core-data", "paired-core")
        self.assertIn("compare_paired_reports", ns)
        rows = [{"id": "x", "valid": True, "ea": True, "pa": True}]
        report = {"n": 1, "metric_id": "metric", "scores": rows}
        condition = {"split_hash": "s", "metric_id": "metric", "actual_model_id": "m",
                     "actual_model_revision": "r", "actual_tokenizer_revision": "r",
                     "inference_prompt_sha256": "p", "inference_seed": 42,
                     "max_length": 4096, "max_new_tokens": 256, "thinking": False,
                     "eval_ids": ["x"], "inference_runtime": {"model_dtype": "torch.float16"}}
        other = {**condition, "inference_runtime": {"model_dtype": "torch.bfloat16"}}
        with self.assertRaisesRegex(ValueError, "condition"):
            ns["compare_paired_reports"](report, report, condition, other)

    def test_pairing_counts_rescues_and_regressions(self):
        ns = namespace("core-data", "paired-core")
        self.assertIn("compare_paired_reports", ns)
        before = {"n": 2, "metric_id": "metric", "scores": [
            {"id": "x", "valid": True, "ea": False, "pa": False},
            {"id": "y", "valid": True, "ea": True, "pa": True}]}
        after = {"n": 2, "metric_id": "metric", "scores": [
            {"id": "x", "valid": True, "ea": True, "pa": True},
            {"id": "y", "valid": True, "ea": False, "pa": False}]}
        condition = {"split_hash": "s", "metric_id": "metric", "actual_model_id": "m",
                     "actual_model_revision": "r", "actual_tokenizer_revision": "r",
                     "inference_prompt_sha256": "p", "inference_seed": 42,
                     "max_length": 4096, "max_new_tokens": 256, "thinking": False,
                     "eval_ids": ["x", "y"], "inference_runtime": {"model_dtype": "torch.float16"}}
        result = ns["compare_paired_reports"](before, after, condition, condition)
        self.assertEqual(result["rescued_ea"], 1)
        self.assertEqual(result["regressed_ea"], 1)
        self.assertEqual(result["P"]["ea"], 0.5)
        self.assertEqual(result["G_all"]["ea"], 0.5)

    def test_old_or_missing_prediction_id_cannot_enter_the_pair(self):
        ns = namespace("core-data", "paired-core")
        before = {"n": 1, "metric_id": "metric", "scores": [
            {"id": "x", "valid": True, "ea": False, "pa": False}]}
        after = {"n": 1, "metric_id": "metric", "scores": [
            {"id": "old-cached-id", "valid": True, "ea": True, "pa": True}]}
        condition = {"split_hash": "s", "metric_id": "metric", "actual_model_id": "m",
                     "actual_model_revision": "r", "actual_tokenizer_revision": "r",
                     "inference_prompt_sha256": "p", "inference_seed": 42,
                     "max_length": 4096, "max_new_tokens": 256, "thinking": False,
                     "eval_ids": ["x"], "inference_runtime": {"model_dtype": "torch.float16"}}
        with self.assertRaisesRegex(ValueError, "IDs"):
            ns["compare_paired_reports"](before, after, condition, condition)


if __name__ == "__main__":
    unittest.main()
