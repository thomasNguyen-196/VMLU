"""Offline tests for the K2 retrieval set and calibration procedure (openspec change diagnostic-k2-retrieval).

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_diagnostic_k2
Synthetic rows except where a test says it rebuilds the committed manifest from local sources. Expected values
are worked out by hand in the comments.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import diagnostic_k2 as k2
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_router as router
from code_benchmark import vi_multimodel as v1

SOURCES_OK = all(path.is_file() for path in (k2.h3.BIDLQA_TRAIN_SOURCE, dp.ROOT / "v_legal_slsp/bidlqa/ViBidLQA_val.jsonl",
                                             dp.ROOT / "v_legal_slsp/bidlqa/ViBidLQA_test.jsonl"))


def procedure(**overrides):
    base = json.loads(k2.PROCEDURE_PATH.read_text(encoding="utf-8"))
    base.update(overrides)
    return base


def rd(f1, prediction="đáp án", tokens=100):
    return {"em": int(f1 == 1.0), "token_f1": f1, "prediction": prediction, "total_tokens": tokens}


def cells(n, b, k, k2_, ks):
    return [(dict(b), dict(k), dict(k2_), dict(ks)) for _ in range(n)]


class TestConfiguration(unittest.TestCase):
    def test_the_committed_files_load(self):
        config, digest = k2.load_retrieval_config()
        self.assertEqual((config["top_k"], config["query"], len(digest)), (2, "question", 64))
        loaded, digest = k2.load_procedure()
        self.assertEqual((loaded["candidates"], loaded["tie"], len(digest)), (list(k2.CANDIDATES), ["more_thorough"], 64))

    def test_out_of_contract_procedures_are_refused(self):
        bad = [procedure(extra=1), procedure(tie=["fewer_mean_reported_tokens"]),
               procedure(candidates=list(reversed(k2.CANDIDATES))), procedure(score={"reading": "em"}),
               procedure(calibration_items=0), procedure(equal_within=0.01),
               procedure(probe={"arm": "B", "samples": 2, "agreement": "normalized-answer-v1"}),
               procedure(probe={"arm": "S", "samples": 2, "agreement": "normalized-answer-v1"})]
        for value in bad:
            with self.assertRaises(SystemExit):
                k2.validate_procedure(value)

    def test_another_retrieval_configuration_is_refused(self):
        config = json.loads(k2.RETRIEVAL_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            for change in ({"top_k": 3}, {"query": "question_and_passage"}, {"bigrams": False},
                           {"bm25": {**config["bm25"], "k1": 1.5}}):
                path = Path(tmp) / "r.json"
                path.write_text(json.dumps({**config, **change}), encoding="utf-8")
                with self.assertRaises(SystemExit):
                    k2.load_retrieval_config(path)


class TestChoice(unittest.TestCase):
    def test_highest_mean_token_f1_wins(self):
        # 60 items: B 0.1, K 0.6 (its two answers differ), KS 0.8 -> cascade returns KS: K 0.6, cascade 0.8, KS 0.8;
        # the tie of cascade and KS goes to the more thorough always-KS
        result = k2.choose(procedure(), cells(60, rd(0.1), rd(0.6, "a"), rd(0.6, "b"), rd(0.8)))
        self.assertEqual(result["scores"]["k_cascade"], result["scores"]["always_KS"])
        self.assertEqual((result["tied"], result["choice"]), (["k_cascade", "always_KS"], "always_KS"))

    def test_equal_scores_go_to_the_more_thorough_candidate(self):
        # K answers agree on every item, so the cascade returns K: K 0.7, cascade 0.7, KS 0.5 -> the cascade
        result = k2.choose(procedure(), cells(60, rd(0.0), rd(0.7, "x"), rd(0.2, "x"), rd(0.5)))
        self.assertEqual((result["tied"], result["choice"]), (["always_K", "k_cascade"], "k_cascade"))

    def test_the_cascade_costs_both_k_answers_and_returns_ks_on_disagreement(self):
        b, k, k_second, ks = rd(0.0, tokens=10), rd(0.2, "x", tokens=100), rd(0.2, "y", tokens=110), rd(0.9, tokens=400)
        attempt, spent = k2.outcome("k_cascade", b, k, k_second, ks)
        self.assertIs(attempt, ks)
        self.assertEqual(spent, 610)
        attempt, spent = k2.outcome("k_cascade", b, k, dict(k_second, prediction="x"), ks)
        self.assertEqual((attempt["token_f1"], spent), (0.2, 210))
        self.assertEqual(k2.outcome("k_cascade", b, k, {**k_second, "total_tokens": None,
                                                           "prompt_tokens": None}, ks)[1], None)

    def test_a_sample_of_another_size_is_refused(self):
        with self.assertRaises(SystemExit):
            k2.choose(procedure(), cells(59, rd(0.0), rd(0.5), rd(0.5), rd(0.5)))


class TestRules(unittest.TestCase):
    def features(self):
        return router.Features(k2.DATASET, 120, "khi nào ?")

    def test_each_choice_emits_a_rule_that_routes_like_the_candidate(self):
        expected = {"always_B": ("B", False), "always_K": ("K", False), "always_KS": ("KS", False)}
        for choice, (arm, probed) in expected.items():
            rule = k2.emit_rule(procedure(), choice, f"k2-{choice}")
            self.assertNotIn("probe", rule)
            self.assertEqual((router.route(rule, self.features()).arm, router.route(rule, self.features()).probed),
                             (arm, probed))
        rule = k2.emit_rule(procedure(), "k_cascade", "k2-cascade")
        self.assertEqual(rule["probe"]["arm"], "K")
        self.assertTrue(router.needs_probe(rule, self.features()))
        self.assertEqual((router.route(rule, self.features(), False).arm, router.route(rule, self.features(), False).probed),
                         ("KS", True))
        self.assertEqual((router.route(rule, self.features(), True).arm, router.route(rule, self.features(), True).probed),
                         ("K", True))

    def test_the_grammar_takes_a_k_probe_and_refuses_an_s_probe(self):
        rule = k2.emit_rule(procedure(), "k_cascade", "k2-cascade")
        router.validate_rule(rule, [k2.DATASET])
        with self.assertRaises(SystemExit):
            router.validate_rule({**rule, "probe": {**rule["probe"], "arm": "S"}}, [k2.DATASET])


class TestPrompts(unittest.TestCase):
    def test_the_four_arm_prompts(self):
        protocol = json.loads(k2.PROTOCOL_PATH.read_text(encoding="utf-8"))
        own = "Điều 1. Đoạn gốc nói về thời hạn mười ngày."
        item = v1.EvalItem(dataset_id=k2.DATASET, source_dataset="bidlqa", item_id="BIDLQA-TR-0001",
                           replicate_id=dp.MAIN_REPLICATE, task="reading", stratum="all", question="Thời hạn là bao lâu?",
                           passage_id="p", prompt=v1.build_reading_prompt(own, "Thời hạn là bao lâu?"),
                           gold_answer="zzgoldzz")
        prompts = k2.arm_prompts(item, ["  Đoạn thứ nhất.  ", "Đoạn thứ hai."], protocol, dp.load_templates(), "\n\n")
        self.assertEqual(prompts["B"], "Trả lời câu hỏi sau bằng một cụm từ hoặc số ngắn gọn.\n\n"
                                       "Câu hỏi: Thời hạn là bao lâu?\nTrả lời: ")
        retrieved = v1.EvalItem(**{**item.__dict__, "prompt": prompts["K"]})
        parts = dp.parse_frozen_prompt(retrieved)
        self.assertEqual((parts.body, parts.question), ("Đoạn thứ nhất.\n\nĐoạn thứ hai.", "Thời hạn là bao lâu?"))
        self.assertTrue(prompts["KS"].startswith(dp.load_templates()["s_reading_head"] + "Đoạn thứ nhất.\n\nĐoạn thứ hai."))
        self.assertEqual(prompts["O"], item.prompt)
        self.assertTrue(all("zzgoldzz" not in prompt for prompt in prompts.values()))
        self.assertNotIn(own, prompts["K"] + prompts["KS"] + prompts["B"])


@unittest.skipUnless(SOURCES_OK and k2.MANIFEST_PATH.exists(), "needs the local ViBidLQA sources and the frozen manifest")
class TestFrozenManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.rebuilt = k2.build_manifest()

    def test_it_rebuilds_byte_for_byte(self):
        self.assertEqual(self.manifest, k2.load_frozen_manifest())
        dp.verify_manifest_rows(self.manifest, self.rebuilt)

    def test_items_calibration_and_exclusion(self):
        keys = {dp.item_key(row["dataset_id"], row["item_id"]) for row in self.manifest["items"]}
        self.assertEqual((len(keys), self.manifest["n"], len(self.manifest["calibration_items"])), (360, 2880, 60))
        self.assertTrue(set(self.manifest["calibration_items"]) <= keys)
        excluded = k2.excluded_keys()
        self.assertEqual(len(excluded), 360)
        self.assertFalse({key.split(":", 1)[1] for key in keys} & excluded)

    def test_every_k_and_ks_prompt_carries_its_two_passages(self):
        corpus = {passage["passage_id"]: passage["text"].strip() for passage in k2.load_corpus()}
        templates = dp.load_templates()
        for run_key, item in self.rebuilt.items():
            arm = dp.arm_of_replicate(item.replicate_id)
            record = self.manifest["retrieval"][dp.item_key(item.dataset_id, item.item_id)]
            context = "\n\n".join(corpus[pid] for pid in record["passages"])
            if arm == "K":
                self.assertEqual(dp.parse_frozen_prompt(item).body, context, run_key)
            elif arm == "KS":
                self.assertTrue(item.prompt.startswith(templates["s_reading_head"] + context), run_key)


if __name__ == "__main__":
    unittest.main()
