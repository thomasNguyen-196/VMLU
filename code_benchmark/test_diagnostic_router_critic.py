"""Offline tests of the router-critic design check (openspec change diagnostic-router-loop, card MC-102).
No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_diagnostic_router_critic
"""
from __future__ import annotations

import unittest

from code_benchmark import analyze_router_critic as arc
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_router_critic as rc
from code_benchmark import run_router_critic as rrc
from code_benchmark import simulate_router_loop as sim
from code_benchmark import vi_multimodel as v1

CONFIG, _ = rc.load_config()
FIXES = dict(CONFIG["prompt"]["fixes"])
HAS_DATA = rc.JUDGED_SCORES.is_file() and all(
    (sim.RUNS / directory / sim.PROFILE / "scores.jsonl").is_file() for directory in sim.GROUPS[arc.WIDE_GROUP])


def reading_item(passage: str, question: str) -> v1.EvalItem:
    prompt = dp.RD_HEAD + passage + dp.RD_QUESTION + question + dp.RD_TAIL
    return v1.EvalItem(dataset_id="vi-multimodel-v1-vi-drop-200", source_dataset="drop", item_id="7",
                       replicate_id="main-000", task="reading", stratum="count", question=question,
                       passage_id="p", prompt=prompt, gold_answer="3")


def row(prediction: str, f1: float, em: float = 0.0, tokens: int = 10) -> dict:
    return {"prediction": prediction, "token_f1": f1, "em": em, "total_tokens": tokens}


class TestParse(unittest.TestCase):
    def test_labels_are_read_whatever_their_case_accents_or_markup(self):
        text = "Phân tích ngắn.\n**Đánh giá:** SAI\nNguyên nhân: `tinh_toan`\nCÁCH SỬA: suy_luan"
        self.assertEqual(rc.parse_critic(text, CONFIG),
                         {"verdict": "sai", "cause": "tinh_toan", "fix": "suy_luan", "format_ok": True})
        folded = "danh gia: dung\nnguyen nhan: khong_co\ncach sua: giu"
        self.assertTrue(rc.parse_critic(folded, CONFIG)["format_ok"])

    def test_unknown_ids_missing_labels_and_trailing_text(self):
        self.assertEqual(rc.parse_critic("Đánh giá: wrong\nCách sửa: giu", CONFIG),
                         {"verdict": None, "cause": None, "fix": "giu", "format_ok": False})
        trailing = rc.parse_critic("Đánh giá: dung\nNguyên nhân: khong_co\nCách sửa: giu\nHết.", CONFIG)
        self.assertEqual((trailing["verdict"], trailing["format_ok"]), ("dung", False))
        self.assertEqual(rc.parse_critic("", CONFIG)["verdict"], None)


class TestPrompt(unittest.TestCase):
    def test_the_prompt_holds_the_passage_question_and_answer_only(self):
        item = reading_item("Đoạn văn có ba con mèo.", "Có bao nhiêu con mèo?")
        prompt = rc.critic_prompt(item, " 2 ", CONFIG)
        expected = (CONFIG["prompt"]["template"].replace("<<PASSAGE>>", "Đoạn văn có ba con mèo.")
                    .replace("<<QUESTION>>", "Có bao nhiêu con mèo?").replace("<<ANSWER>>", "2"))
        self.assertEqual(prompt, expected)
        self.assertIn(rc.EMPTY_ANSWER, rc.critic_prompt(item, "", CONFIG))


class TestReplay(unittest.TestCase):
    cell = {"B1": row("2", 0.0), "B2": row("3", 1.0, 1.0), "S1": row("3", 1.0, 1.0), "Q1": row("ba", 0.5),
            "S2": row("3", 1.0, 1.0), "Q2": row("3", 1.0, 1.0)}

    def chosen(self, judged: dict | None, muse: dict | None = None) -> dict:
        return arc.chosen_rows(self.cell, judged, muse, FIXES)

    def test_the_critic_loop_follows_verdict_and_prescription(self):
        self.assertIs(self.chosen({"verdict": "sai", "fix": "suy_luan"})["critic_loop"], self.cell["S1"])
        self.assertIs(self.chosen({"verdict": "sai", "fix": "trich_dan"})["critic_loop"], self.cell["Q1"])
        self.assertIs(self.chosen({"verdict": "sai", "fix": "giu"})["critic_loop"], self.cell["B1"])
        self.assertIs(self.chosen({"verdict": "sai", "fix": None})["critic_loop"], self.cell["B1"])
        self.assertIs(self.chosen({"verdict": "dung", "fix": "suy_luan"})["critic_loop"], self.cell["B1"])
        unsure = self.chosen({"verdict": "khong_chac", "fix": "suy_luan"})
        self.assertIs(unsure["critic_loop"], self.cell["B1"])
        self.assertIs(unsure["critic_unsure_as_wrong"], self.cell["S1"])
        self.assertIs(self.chosen(None)["critic_loop"], self.cell["B1"])

    def test_rule_loop_and_muse_proxy(self):
        self.assertIs(self.chosen(None)["rule_loop"], self.cell["S1"])  # B1 "2" and B2 "3" disagree
        agreeing = {**self.cell, "B2": row("2", 0.0)}
        self.assertIs(arc.chosen_rows(agreeing, None, None, FIXES)["rule_loop"], agreeing["B1"])
        self.assertIs(self.chosen(None, row("2", 0.0))["muse_proxy"], self.cell["B1"])
        self.assertIs(self.chosen(None, row("3", 1.0))["muse_proxy"], self.cell["S1"])

    def test_detector_and_prescription_counts(self):
        records = [{"judged": {"verdict": "sai", "fix": "suy_luan"}, "b1_f1": 0.0, "fix_f1": 1.0},
                   {"judged": {"verdict": "sai", "fix": "suy_luan"}, "b1_f1": 1.0, "fix_f1": 0.0},
                   {"judged": {"verdict": "dung", "fix": "giu"}, "b1_f1": 0.0, "fix_f1": None},
                   {"judged": None, "b1_f1": 1.0, "fix_f1": None}]
        detector = arc.detector_block(records)
        self.assertEqual((detector["b1_wrong"], detector["caught"], detector["flagged_sai"]), (2, 1, 2))
        self.assertEqual((detector["recall"], detector["precision"]), (0.5, 0.5))
        self.assertEqual(arc.prescription_block(records, FIXES)["suy_luan"], {"n": 2, "rescued": 1, "damaged": 1})


@unittest.skipUnless(HAS_DATA, "needs the MC-90 to MC-92 and MC-97 score files")
class TestManifest(unittest.TestCase):
    def test_items_prompts_and_self_hash(self):
        manifest, rebuilt = rc.build_manifest()
        self.assertEqual((manifest["n"], manifest["dataset_counts"]),
                         (376, {"vi-multimodel-v1-vi-drop-200": 188, "vi-multimodel-v1-vi-squad-200": 188}))
        answers = rc.judged_answers(rc.JUDGED_SCORES, list(CONFIG["items"]["datasets"]))
        for item in list(rebuilt.values())[:20]:
            self.assertEqual(item.replicate_id, rc.REPLICATE)
            answer = answers[dp.item_key(item.dataset_id, item.item_id)].strip() or rc.EMPTY_ANSWER
            self.assertIn(f"Câu trả lời của mô hình: {answer}\n", item.prompt)
        unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        self.assertEqual(manifest["manifest_sha256"], v1.sha256_bytes(v1.canonical_json(unhashed)))


class TestRunnerGates(unittest.TestCase):
    def test_gates(self):
        manifest = {name: "x" for name in rrc.FROZEN_KEYS}
        registration = {"card_ids": {rc.PHASE: "MC-102"}, "card_files": {rc.PHASE: "missing.md"},
                        "frozen": {**manifest, "manifest_sha256": "y"}}
        gates = {gate.name: gate.ok for gate in rrc.evaluate_gates(
            CONFIG, manifest, registration, ("https://opencode.ai/zen/go/v1", CONFIG["route"]["model_id"], True),
            card_text="## MC-102 — test\n")}
        self.assertEqual(gates, {"card_registered": True, "detail_card": False, "frozen_hashes": False,
                                 "route_identity": True})


if __name__ == "__main__":
    unittest.main()
